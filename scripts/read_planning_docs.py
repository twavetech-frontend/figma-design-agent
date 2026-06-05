# -*- coding: utf-8 -*-
"""기획 문서 통합 리더 — src/기획/ 의 모든 HTML(Notion export)을 깨끗한 텍스트로 합쳐 출력.

🔴 "디자인 생성 준비" 프로세스의 **마지막 단계**에서 호출 (CLAUDE.md). 새 세션에서
imin 모바일 앱 서비스 맥락(스테이지/납입/지급/쿠폰/이탈/회원 유스케이스 전반)을 100%
이해한 상태로 만들기 위함. HTML 태그를 제거하고 유스케이스별 구조(메타정보/플로우/
비즈니스 룰/연결 화면/수용 기준/백엔드)를 1개 digest 로 묶어 stdout 출력 → Claude 가
**한 번의 Read 로 전체 맥락 흡수**.

사용:
    python3 scripts/read_planning_docs.py            # stdout 으로 통합 텍스트
    python3 scripts/read_planning_docs.py --list     # 파일 목록만
    python3 scripts/read_planning_docs.py --out scripts/_planning_digest.txt  # 파일로 저장
"""
import argparse
import hashlib
import html as _html
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLAN_DIR = os.path.join(os.path.dirname(_HERE), "src", "기획")


def _strip_html(raw: str) -> str:
    # script/style 통째 제거
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    # 블록 경계는 줄바꿈으로 보존 (구조 가독성)
    raw = re.sub(r"</(p|div|tr|li|h[1-6]|table|section|article|br)\s*>", "\n", raw, flags=re.I)
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    # 나머지 태그 제거
    txt = re.sub(r"<[^>]+>", " ", raw)
    txt = _html.unescape(txt)
    # 공백 정리
    txt = re.sub(r"[ \t ]+", " ", txt)
    lines = [ln.strip() for ln in txt.splitlines()]
    # 연속 빈 줄 축약 + 빈 줄 제거
    out = []
    for ln in lines:
        if ln:
            out.append(ln)
    return "\n".join(out)


def _collect_html_files():
    files = []
    for root, _dirs, names in os.walk(_PLAN_DIR):
        for n in names:
            if n.lower().endswith(".html"):
                files.append(os.path.join(root, n))
    # UC 번호 순으로 정렬 (파일명 앞 숫자)
    def _key(p):
        base = os.path.basename(p)
        m = re.match(r"\s*(\d+)", base)
        return (int(m.group(1)) if m else 9999, base)
    return sorted(files, key=_key)


def fingerprint() -> dict:
    """src/기획/ 의 현재 상태 지문 (파일 목록 + mtime + size 의 해시).

    파일 추가/삭제/수정(mtime·size 변동) 시 hash 가 바뀐다 → 변경 감지에 사용.
    폴더 없으면 {'count':0,'hash':'empty'}.
    """
    if not os.path.isdir(_PLAN_DIR):
        return {"count": 0, "hash": "empty", "files": []}
    items = []
    for f in _collect_html_files():
        try:
            st = os.stat(f)
        except OSError:
            continue
        items.append([os.path.relpath(f, os.path.dirname(_HERE)), int(st.st_mtime), st.st_size])
    h = hashlib.sha1(json.dumps(items, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"count": len(items), "hash": h, "files": items}


def build_digest(progress=None):
    """모든 기획 HTML → 통합 digest 문자열. progress(current,total,name) 콜백 호출(있으면).

    Returns (digest_text, file_count, read_token). 폴더 없거나 0건이면 ("", 0, "").

    🔴 digest 맨 끝에 **통독 확인 토큰**(read_token)을 붙인다. 빌드 게이트는 이 토큰으로
    ack 해야 통과 → 토큰이 파일 맨 끝에 있어 **끝까지 통독해야만** ack 가능(통독 강제).
    """
    if not os.path.isdir(_PLAN_DIR):
        return "", 0, ""
    files = _collect_html_files()
    if not files:
        return "", 0, ""
    total = len(files)
    header = (
        "=" * 70 + "\n"
        f"📚 imin 모바일 앱 기획 문서 통합 ({total}개 유스케이스)\n"
        "이 문서는 서비스 전반 맥락(스테이지·납입·지급·쿠폰·이탈·회원 플로우)을 담는다.\n"
        "디자인 생성 시 각 화면이 어느 유스케이스/플로우에 속하는지, 비즈니스 룰·연결\n"
        "화면·상태를 충분히 고려할 것.\n"
        + "=" * 70
    )
    chunks = [header]
    for i, f in enumerate(files, 1):
        title = os.path.splitext(os.path.basename(f))[0]
        title = re.sub(r"\s+[0-9a-f]{32}$", "", title)
        if progress:
            try:
                progress(i, total, title)
            except Exception:
                pass
        try:
            raw = open(f, encoding="utf-8").read()
            body = _strip_html(raw)
        except Exception as e:
            chunks.append(f"\n[읽기 실패] {os.path.basename(f)}: {e}")
            continue
        chunks.append(f"\n\n{'─' * 60}\n## {title}\n{'─' * 60}\n{body}")
    body_text = "\n".join(chunks)
    # 통독 확인 토큰 = 본문 해시 앞 12자 (내용 바뀌면 토큰도 바뀜)
    read_token = hashlib.sha1(body_text.encode("utf-8")).hexdigest()[:12]
    footer = (
        "\n\n" + "=" * 70 + "\n"
        "🔚 기획 문서 통독 완료 지점.\n"
        f"통독 확인 토큰: {read_token}\n"
        f"→ 이 토큰으로 `python3 scripts/figma_mcp_client.py ack-planning {read_token}` 를 실행해야\n"
        "   디자인 빌드가 통과된다 (통독 안 하면 빌드 차단). 토큰은 이 파일 끝에만 있으므로\n"
        "   여기까지 읽었다면 서비스 맥락을 충분히 흡수한 것.\n"
        + "=" * 70
    )
    return body_text + footer, total, read_token


def main():
    ap = argparse.ArgumentParser(description="기획 문서 통합 리더")
    ap.add_argument("--list", action="store_true", help="파일 목록만 출력")
    ap.add_argument("--out", help="결과를 파일로 저장 (없으면 stdout)")
    args = ap.parse_args()

    if not os.path.isdir(_PLAN_DIR):
        print(f"[기획] 폴더 없음: {_PLAN_DIR} — 기획 문서 단계 건너뜀", file=sys.stderr)
        return 0

    files = _collect_html_files()
    if not files:
        print(f"[기획] HTML 문서 0건: {_PLAN_DIR}", file=sys.stderr)
        return 0

    if args.list:
        for f in files:
            print(os.path.relpath(f, os.path.dirname(_HERE)))
        return 0

    result, _count, _token = build_digest()
    if args.out:
        out_path = args.out if os.path.isabs(args.out) else os.path.join(os.path.dirname(_HERE), args.out)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(result)
        print(f"[기획] {_count}개 문서 → {out_path} ({len(result):,}자)")
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
