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
import html as _html
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

    chunks = []
    header = (
        "=" * 70 + "\n"
        f"📚 imin 모바일 앱 기획 문서 통합 ({len(files)}개 유스케이스)\n"
        "이 문서는 서비스 전반 맥락(스테이지·납입·지급·쿠폰·이탈·회원 플로우)을 담는다.\n"
        "디자인 생성 시 각 화면이 어느 유스케이스/플로우에 속하는지, 비즈니스 룰·연결\n"
        "화면·상태를 충분히 고려할 것.\n"
        + "=" * 70
    )
    chunks.append(header)
    for f in files:
        try:
            raw = open(f, encoding="utf-8").read()
        except Exception as e:
            chunks.append(f"\n[읽기 실패] {os.path.basename(f)}: {e}")
            continue
        body = _strip_html(raw)
        title = os.path.splitext(os.path.basename(f))[0]
        # Notion page id(끝의 32자리 hex) 제거해 제목 정리
        title = re.sub(r"\s+[0-9a-f]{32}$", "", title)
        chunks.append(f"\n\n{'─' * 60}\n## {title}\n{'─' * 60}\n{body}")

    result = "\n".join(chunks)
    if args.out:
        out_path = args.out if os.path.isabs(args.out) else os.path.join(os.path.dirname(_HERE), args.out)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(result)
        print(f"[기획] {len(files)}개 문서 → {out_path} ({len(result):,}자)")
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
