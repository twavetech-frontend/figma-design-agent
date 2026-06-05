# -*- coding: utf-8 -*-
"""기획 통독 Read 커버리지 훅 (2026-06-05 사용자: "Read 커버리지 훅으로 구현").

목적: "새 세션이 _planning_digest.txt 를 *끝까지* 읽었는가" 를 시스템이 분간한다.
토큰 ack 는 1회 영속이라 새 세션을 분간 못 하므로(메모리 [[navbar-style-and-segmented-size-rules]]
와 별개), 실제 Read 호출의 **반환 줄 범위**를 세션별로 누적해 빌드 게이트가 검증한다.

Claude Code 훅 두 이벤트에서 호출된다 (.claude/settings.json):
  - UserPromptSubmit → 현재 Claude 세션 ID 를 scripts/.planning_gate/current_session 에 기록
    (게이트가 "현재 세션" 을 식별하는 유일한 수단).
  - PostToolUse(matcher=Read) → Read 대상이 _planning_digest.txt 면, tool_response 에서
    실제 반환된 줄 번호(cat -n prefix + "showing lines X-Y of N total" 리마인더)를 파싱해
    cov_<sid>.json 의 covered 범위에 합집합으로 누적. 전체 커버 시 통독 ack(.read.json)도
    자동 기록(수동 ack-planning 불필요).

설계 원칙: **절대 Claude 흐름을 막지 않는다** — 모든 예외를 삼키고 항상 exit 0.
실제 차단은 figma_mcp_client.py 의 빌드 게이트에서만 한다.
"""
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)
_REPO = os.path.dirname(_SCRIPTS)
_GATE_DIR = os.path.join(_SCRIPTS, ".planning_gate")
_DIGEST = os.path.join(_SCRIPTS, "_planning_digest.txt")
_DIGEST_BASENAME = "_planning_digest.txt"
_META = _DIGEST + ".meta.json"
_ACK = _DIGEST + ".read.json"
_SESSION_FILE = os.path.join(_SCRIPTS, ".mcp_session")
_MCP_URL = "http://127.0.0.1:8769/mcp"

# 완독 판정 기준 (게이트와 동일하게 유지)
_COMPLETE_RATIO = 0.97  # 전체 줄의 97% 이상
_END_SLACK = 8          # 마지막 N줄(토큰/footer 위치)에 도달
_START_SLACK = 3        # 첫 N줄에서 시작


def _ensure_gate_dir():
    os.makedirs(_GATE_DIR, exist_ok=True)


def _notify_plugin(status, **data):
    """통독 진행 상태를 Figma 플러그인 UI 에 전송 (2026-06-05 사용자: "통독할 때 상태가 보여야").

    figma_mcp_client._notify_plugin 과 동일 경로(MCP notify_plugin 도구)이나, 훅은 무거운
    모듈 import 없이 기존 세션(SESSION_FILE)을 재사용해 직접 1회 POST 한다. 설계 원칙대로
    **절대 흐름을 막지 않는다** — 짧은 timeout + 모든 예외 삼킴 (플러그인 미연결/브리지 down 무해).
    """
    try:
        import requests  # setup 으로 설치됨 — 없으면 알림만 생략
    except Exception:
        return
    try:
        with open(_SESSION_FILE, encoding="utf-8") as fh:
            sid = fh.read().strip()
    except Exception:
        return
    if not sid:
        return
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {
            "name": "notify_plugin",
            "arguments": {"event": "planning-docs", "data": dict(status=status, **data)},
        },
    }
    headers = {"Content-Type": "application/json", "mcp-session-id": sid}
    try:
        requests.post(_MCP_URL, json=payload, headers=headers, timeout=2)
    except Exception:
        pass


def _digest_total_lines():
    try:
        with open(_DIGEST, "rb") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return 0


def _current_section_name(upto_line):
    """digest 에서 upto_line 줄까지 중 마지막 '## ' 섹션 헤더 제목 반환 (2026-06-05 사용자:
    "어떤 기획문서를 읽고 있는지 표시되어야해"). digest 는 각 유스케이스를 '## 05-UC-... 제목'
    헤더로 구분하므로, 가장 최근 읽은 위치(upto_line) 이하의 마지막 헤더가 '지금 읽는 문서'다."""
    try:
        name = ""
        with open(_DIGEST, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if i > upto_line:
                    break
                s = line.strip()
                if s.startswith("## "):
                    name = s[3:].strip()
        return name
    except Exception:
        return ""


def _digest_hash():
    try:
        with open(_META, encoding="utf-8") as fh:
            return json.load(fh).get("hash")
    except Exception:
        return None


def _merge_ranges(ranges):
    """[[a,b],...] 정렬·병합."""
    if not ranges:
        return []
    norm = sorted([a, b] if a <= b else [b, a] for a, b in ranges)
    out = [list(norm[0])]
    for a, b in norm[1:]:
        if a <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _covered_count(ranges):
    return sum(b - a + 1 for a, b in ranges)


def _is_complete(ranges, total):
    if total <= 0 or not ranges:
        return False
    mn = min(a for a, _ in ranges)
    mx = max(b for _, b in ranges)
    if mn > _START_SLACK or mx < total - _END_SLACK:
        return False
    return _covered_count(ranges) >= _COMPLETE_RATIO * total


def _response_to_text(tool_response):
    """tool_response(구조가 버전마다 다름)를 하나의 텍스트로 평탄화."""
    if tool_response is None:
        return ""
    if isinstance(tool_response, str):
        return tool_response
    # dict/list 등 — 흔한 키 우선, 없으면 통째 dump (escaped \n, \t 포함)
    parts = []
    if isinstance(tool_response, dict):
        for k in ("content", "text", "output", "file", "data"):
            v = tool_response.get(k)
            if isinstance(v, str):
                parts.append(v)
    try:
        parts.append(json.dumps(tool_response, ensure_ascii=False))
    except Exception:
        parts.append(str(tool_response))
    return "\n".join(parts)


# cat -n prefix: "<공백>123\t" — 실제 탭 또는 JSON-escaped(\t) 모두 매칭.
_LINE_PREFIX = re.compile(r"(?:^|\n|\\n)\s*(\d+)(?:\t|\\t)")
_TRUNC = re.compile(r"showing lines (\d+)-(\d+) of (\d+)\s*total")


def _extract_covered(text, total):
    """반환 텍스트에서 실제로 본 줄 번호 범위들을 추출."""
    ranges = []
    # 1) 잘림 리마인더가 있으면 정확한 [A,B] + total
    for m in _TRUNC.finditer(text):
        a, b, n = int(m.group(1)), int(m.group(2)), int(m.group(3))
        ranges.append([a, b])
        if n > total:
            total = n
    # 2) cat -n prefix 로 본 줄 번호 수집 (잘리지 않은 마지막 페이지 포함)
    nums = [int(x) for x in _LINE_PREFIX.findall(text)]
    if nums:
        lo = max(1, min(nums))
        hi = max(nums)
        if total:
            hi = min(hi, total)
        ranges.append([lo, hi])
    # total 범위로 클램프
    if total:
        ranges = [[max(1, a), min(b, total)] for a, b in ranges if a <= total]
    return _merge_ranges(ranges), total


def _prune_old_sessions(keep_days=7):
    cutoff = time.time() - keep_days * 86400
    try:
        for name in os.listdir(_GATE_DIR):
            if name.startswith("cov_") and name.endswith(".json"):
                p = os.path.join(_GATE_DIR, name)
                try:
                    if os.path.getmtime(p) < cutoff:
                        os.remove(p)
                except Exception:
                    pass
    except Exception:
        pass


def _write_ack_if_complete(merged, total):
    """완독 시 통독 ack(.read.json) 자동 기록 — 수동 ack-planning 생략 가능."""
    if not _is_complete(merged, total):
        return
    try:
        with open(_META, encoding="utf-8") as fh:
            meta = json.load(fh)
    except Exception:
        return
    tok = meta.get("read_token")
    if not tok:
        return
    ack = {"read_token": tok, "hash": meta.get("hash"), "count": meta.get("count")}
    try:
        with open(_ACK, "w", encoding="utf-8") as fh:
            json.dump(ack, fh, ensure_ascii=False)
    except Exception:
        pass


def _handle_user_prompt(data):
    sid = data.get("session_id")
    if not sid:
        return
    _ensure_gate_dir()
    try:
        with open(os.path.join(_GATE_DIR, "current_session"), "w", encoding="utf-8") as fh:
            fh.write(str(sid))
    except Exception:
        pass
    _prune_old_sessions()


def _handle_post_read(data):
    sid = data.get("session_id")
    tool_input = data.get("tool_input") or {}
    fp = tool_input.get("file_path") or ""
    if not sid or os.path.basename(fp) != _DIGEST_BASENAME:
        return
    total = _digest_total_lines()
    if total <= 0:
        return
    text = _response_to_text(data.get("tool_response"))
    new_ranges, total = _extract_covered(text, total)
    if not new_ranges:
        # 폴백: tool_input.offset/limit 으로 근사 (리마인더/prefix 파싱 실패 시)
        off = tool_input.get("offset") or 1
        lim = tool_input.get("limit")
        end = min(total, off + lim - 1) if lim else total
        new_ranges = [[max(1, off), end]]

    _ensure_gate_dir()
    cov_path = os.path.join(_GATE_DIR, "cov_%s.json" % sid)
    cur_hash = _digest_hash()
    prev = []
    try:
        with open(cov_path, encoding="utf-8") as fh:
            obj = json.load(fh)
        if obj.get("hash") == cur_hash:  # digest 바뀌면 이전 커버리지 무효
            prev = obj.get("covered") or []
    except Exception:
        pass

    merged = _merge_ranges(prev + new_ranges)
    out = {
        "hash": cur_hash,
        "total": total,
        "covered": merged,
        "covered_lines": _covered_count(merged),
        "complete": _is_complete(merged, total),
        "ts": int(time.time()),
    }
    try:
        with open(cov_path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False)
    except Exception:
        pass
    _write_ack_if_complete(merged, total)

    # 플러그인 UI 에 통독 진행 상태 표시 — 통독 중이면 진행률, 완독이면 완료.
    if out["complete"]:
        cnt = None
        try:
            with open(_META, encoding="utf-8") as fh:
                cnt = json.load(fh).get("count")
        except Exception:
            pass
        _notify_plugin("done", count=cnt)
    else:
        # 가장 멀리(=가장 최근) 읽은 줄 근처의 UC 섹션명을 함께 전송 → UI 가 "지금 읽는 문서" 표시.
        upto = max((b for _, b in merged), default=0)
        _notify_plugin("reading", current=out["covered_lines"], total=total,
                       name=_current_section_name(upto)[:40])


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)
    try:
        event = data.get("hook_event_name") or ""
        if event == "UserPromptSubmit":
            _handle_user_prompt(data)
        elif event == "PostToolUse":
            _handle_post_read(data)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
