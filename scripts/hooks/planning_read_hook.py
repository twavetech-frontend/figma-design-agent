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


_MCP_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def _read_session():
    try:
        with open(_SESSION_FILE, encoding="utf-8") as fh:
            return fh.read().strip() or None
    except Exception:
        return None


def _init_session(requests):
    """브리지에 MCP initialize 핸드셰이크로 새 세션을 발급받아 .mcp_session 에 저장(실패 시 None).

    🔴 2026-06-05: 브리지가 재시작되면 .mcp_session 의 세션이 만료(stale)되는데, 훅은 그 파일을
    읽기만 해 알림 POST 가 전부 실패했다(통독 progress 가 플러그인에 안 뜸). figma_mcp_client
    가 .mcp_session 을 갱신하기 전에 통독 Read 가 일어나면 stale 세션을 그대로 써 실패. 이제
    훅이 stale 을 만나면 스스로 새 세션을 발급해 자가복구한다. figma_mcp_client.init_session 과
    동일한 핸드셰이크(initialize → notifications/initialized)."""
    try:
        r = requests.post(_MCP_URL, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "planning-read-hook", "version": "1.0"}},
        }, headers=_MCP_HEADERS, timeout=2)
        sid = r.headers.get("mcp-session-id")
        if not sid:
            return None
        h = dict(_MCP_HEADERS); h["mcp-session-id"] = sid
        requests.post(_MCP_URL, json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                      headers=h, timeout=2)
        try:
            with open(_SESSION_FILE, "w", encoding="utf-8") as fh:
                fh.write(sid)
        except Exception:
            pass
        return sid
    except Exception:
        return None


def _post_notify(requests, sid, status, data):
    """notify_plugin 1회 POST. (성공, 세션유효) 튜플 반환. 세션 만료면 (False, False)."""
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {
            "name": "notify_plugin",
            "arguments": {"event": "planning-docs", "data": dict(status=status, **data)},
        },
    }
    h = dict(_MCP_HEADERS); h["mcp-session-id"] = sid
    try:
        r = requests.post(_MCP_URL, json=payload, headers=h, timeout=2)
    except Exception:
        return False, True  # 통신 실패(브리지 down 등) — 세션 문제 아님, 재초기화 무의미
    if r.status_code >= 400:
        return False, False  # 4xx (세션 만료/없음) → 재초기화 후 재시도 가치 있음
    try:
        j = r.json()
        if isinstance(j, dict) and j.get("error"):
            return False, False
    except Exception:
        pass
    return True, True


def _notify_plugin(status, **data):
    """통독 진행 상태를 Figma 플러그인 UI 에 전송 (2026-06-05 사용자: "통독할 때 상태가 보여야").

    figma_mcp_client._notify_plugin 과 동일 경로(MCP notify_plugin 도구). 훅은 기존
    세션(.mcp_session)을 재사용하되, **stale(만료)이면 스스로 새 세션을 발급해 재시도**한다
    (브리지 재시작에도 통독 progress 가 안정적으로 뜨도록). 설계 원칙대로 **절대 흐름을 막지
    않는다** — 짧은 timeout + 모든 예외 삼킴.
    """
    try:
        import requests  # setup 으로 설치됨 — 없으면 알림만 생략
    except Exception:
        return
    sid = _read_session()
    if sid:
        ok, session_valid = _post_notify(requests, sid, status, data)
        if ok:
            return
        if session_valid:
            return  # 브리지 down 등 — 재초기화해도 소용없음
    # 세션 없음/만료 → 새 세션 발급 후 재시도 (자가복구)
    new_sid = _init_session(requests)
    if new_sid:
        _post_notify(requests, new_sid, status, data)


def _digest_total_lines():
    try:
        with open(_DIGEST, "rb") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return 0


def _section_progress(upto_line):
    """digest 의 '## ' 섹션(=기획 문서 1개) 기준 통독 진행을 반환: (현재 섹션 번호, 전체
    섹션 수, 현재 섹션명). (2026-06-05 사용자: "36개 단위로 진행바 표시" + "어떤 기획문서를
    읽고 있는지 표시".)

    digest 의 '## ' 헤더 수 = src/기획/ 의 html 파일 수 = learn-planning 의 'n/36' 학습
    progress 단위와 동일하다(문서가 추가되면 37·38 로 자동 증가 — read_planning_docs 가
    폴더를 재귀 스캔하므로). upto_line(가장 최근 읽은 줄) 이하의 마지막 '## ' 헤더가
    '지금 읽는 문서', 그 헤더의 순번이 '현재 섹션 번호'다."""
    try:
        headers = []  # (line_no, title)
        with open(_DIGEST, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                s = line.strip()
                if s.startswith("## "):
                    headers.append((i, s[3:].strip()))
        total = len(headers)
        cur, name = 0, ""
        for idx, (ln, title) in enumerate(headers, 1):
            if ln <= upto_line:
                cur, name = idx, title
            else:
                break
        return cur, total, name
    except Exception:
        return 0, 0, ""


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
    # 🔴 monotonic 가드(2026-06-08 사용자: "플러그인이 16/36 에서 멈춰있었다"): 이미 통독
    #    ack(.read.json) 됐으면 — 이 Read 의 자체 커버리지가 아직 부분(예: 첫 청크 16/36)이라도
    #    절대 'reading' 으로 되돌리지 않고 'done' 을 보낸다. 비동기 훅 subprocess 가 순서 보장
    #    없이 알림을 보내 done 뒤 stale reading 이 도착해 진행바가 갇히던 회귀 차단(송신 측).
    already_acked = os.path.exists(_ACK)
    if out["complete"] or already_acked:
        cnt = None
        try:
            with open(_META, encoding="utf-8") as fh:
                cnt = json.load(fh).get("count")
        except Exception:
            pass
        _notify_plugin("done", count=cnt)
    else:
        # 36개(문서) 단위 진행 + 현재 읽는 문서명을 함께 전송.
        # currentUc/totalUc → UI 가 'n/36' 으로 표시(learn 단계와 동일 단위), current/total(줄)은 폴백.
        upto = max((b for _, b in merged), default=0)
        cur_uc, total_uc, name = _section_progress(upto)
        _notify_plugin("reading", current=out["covered_lines"], total=total,
                       currentUc=cur_uc, totalUc=total_uc, name=name[:40])


# ── 레퍼런스 Read / self-verify export 커버리지 (2026-06-11 사용자: fable 이 조용히
#    건너뛰는 것 방지 — 통독과 동일하게 코드 게이트화). 통독과 같은 .planning_gate 디렉토리에
#    세션별로 누적하고, figma_mcp_client 의 게이트가 검증한다. 설계 원칙 동일: 절대 흐름을
#    막지 않는다(항상 exit 0). 차단은 빌드 게이트에서만.
def _gate_json_update(fname, key, value):
    """`.planning_gate/<fname>` 의 set 필드(key)에 value 를 합집합으로 누적."""
    _ensure_gate_dir()
    p = os.path.join(_GATE_DIR, fname)
    cur = {}
    try:
        with open(p, encoding="utf-8") as fh:
            cur = json.load(fh)
    except Exception:
        cur = {}
    s = set(cur.get(key) or [])
    s.add(value)
    cur[key] = sorted(s)
    cur["ts"] = int(time.time())
    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(cur, fh, ensure_ascii=False)
    except Exception:
        pass


def _handle_ref_thumb_read(data):
    """Read 대상이 레퍼런스 이미지면 세션별로 basename 누적 → ref_<sid>.json.
    figma_mcp_client 의 레퍼런스 Read 게이트가 검증(절대 규칙 0-G).
    대상 2종: scripts/ref_thumbnails/*.png (uibowl 썸네일) +
    references/external/**/*.jpg|png (mobbin 등 깃 보관 외부 레퍼런스 — 2026-07-09 추가:
    Step A.0 가 이 경로도 요구하는데 훅이 png 썸네일만 기록해 게이트가 영구 차단되던 드리프트)."""
    sid = data.get("session_id")
    fp = (data.get("tool_input") or {}).get("file_path") or ""
    norm = fp.replace("\\", "/")
    if not sid:
        return
    lower = norm.lower()
    is_thumb = "/ref_thumbnails/" in norm and lower.endswith(".png")
    is_external = "/references/" in norm and lower.endswith((".png", ".jpg", ".jpeg"))
    if not (is_thumb or is_external):
        return
    _gate_json_update("ref_%s.json" % sid, "read", os.path.basename(norm))


def _handle_post_export(data):
    """export_node_as_image 호출의 nodeId 를 세션별로 누적 → qa_<sid>.json.
    figma_mcp_client 의 self-verify 게이트가 '빌드가 export 한 섹션을 모델이 재export(=Read)
    했는가' 를 검증(절대 규칙 0-F)."""
    sid = data.get("session_id")
    nid = (data.get("tool_input") or {}).get("nodeId")
    if not sid or not nid:
        return
    _gate_json_update("qa_%s.json" % sid, "exported", str(nid))


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
            tn = data.get("tool_name") or ""
            if "export_node_as_image" in tn:
                _handle_post_export(data)
            else:  # Read
                _handle_post_read(data)          # 기획 digest 통독 커버리지
                _handle_ref_thumb_read(data)     # 레퍼런스 썸네일 Read 커버리지
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
