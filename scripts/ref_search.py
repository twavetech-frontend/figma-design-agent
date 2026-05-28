#!/usr/bin/env python3
"""references/uibowl PNG 검색 도구 (2026-05-28 박힘).

빌드 직전 archetype 별 적절한 reference 화면 path 출력 → Claude 가 Read 강제.
사용자 명시: "내가 레퍼런스 이미지를 수백장 첨부해놓은거 아니냐! 너 디자인 생성할때
레퍼런스 이미지 검색은 하냐?" → 검색 도구 신설.

Usage:
    # archetype 별 reference 검색
    python3 scripts/ref_search.py --archetype imin_home --limit 5
    # patternCode 직접 지정
    python3 scripts/ref_search.py --pattern "메인" --limit 5
    # keyword (patternName 부분 일치)
    python3 scripts/ref_search.py --keyword "홈" --limit 5
    # 앱 제한
    python3 scripts/ref_search.py --pattern "메인" --apps toss,kakaopay --limit 3

archetype → patternCodeName 매핑:
    imin_home    → 메인
    imin_stage   → 신청하기, 생성하기, 게이미피케이션
    imin_lounge  → 스토어, 혜택, 쿠폰
    imin_community → 커뮤니티
    imin_payment → 간편결제, 예약·결제
    imin_detail  → 상세정보 (PDP)
    imin_onboarding → 온보딩
    imin_settings → 설정, 마이페이지
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

APPS = ["toss", "kakaopay", "heydealer", "payhere", "socar"]

ARCHETYPE_PATTERN_MAP = {
    "imin_home":       ["메인"],
    "imin_stage":      ["신청하기", "생성하기", "게이미피케이션"],
    "imin_lounge":     ["스토어", "혜택", "쿠폰", "기획전·이벤트"],
    "imin_community":  ["커뮤니티", "글쓰기", "채팅"],
    "imin_payment":    ["간편결제", "예약·결제", "조회하기"],
    "imin_detail":     ["상세정보 (PDP)", "조회하기"],
    "imin_onboarding": ["온보딩", "로그인·회원가입"],
    "imin_settings":   ["설정", "마이페이지", "고객센터·FAQ"],
    "imin_notification": ["푸시알림", "알림"],
    "imin_search":     ["검색", "탐색", "필터"],
    "imin_history":    ["내역", "통계·리포트"],
}

# 2026-05-28 — name 에 keyword 포함 archetype 자동 fallback (이전엔 미등록 archetype 이
# silent skip 되어 ref 학습 누락 → 사용자 분노). cmd_build Step A.0 가 화면 name 으로
# ref_search.py 호출 시 'onboarding_savings_pain' 같은 string 도 imin_onboarding 으로 매칭.
ARCHETYPE_KEYWORD_FALLBACK = [
    ("onboarding", "imin_onboarding"),
    ("login",      "imin_onboarding"),
    ("signup",     "imin_onboarding"),
    ("signin",     "imin_onboarding"),
    ("home",       "imin_home"),
    ("main",       "imin_home"),
    ("stage",      "imin_stage"),
    ("lounge",     "imin_lounge"),
    ("store",      "imin_lounge"),
    ("benefit",    "imin_lounge"),
    ("community",  "imin_community"),
    ("chat",       "imin_community"),
    ("payment",    "imin_payment"),
    ("pay",        "imin_payment"),
    ("detail",     "imin_detail"),
    ("pdp",        "imin_detail"),
    ("settings",   "imin_settings"),
    ("setting",    "imin_settings"),
    ("mypage",     "imin_settings"),
    ("notification","imin_notification"),
    ("alert",      "imin_notification"),
    ("search",     "imin_search"),
    ("filter",     "imin_search"),
    ("history",    "imin_history"),
    ("record",     "imin_history"),
    ("stat",       "imin_history"),
]


def resolve_archetype(name: str) -> str | None:
    """알려진 archetype 이면 그대로, 아니면 keyword fallback 으로 매칭 시도.

    cmd_build 가 화면 name (예: 'onboarding_savings_pain') 으로 호출할 때
    keyword 'onboarding' 포함 → 'imin_onboarding' 으로 매핑.
    """
    if not name:
        return None
    if name in ARCHETYPE_PATTERN_MAP:
        return name
    n = name.lower()
    for kw, target in ARCHETYPE_KEYWORD_FALLBACK:
        if kw in n:
            return target
    return None


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_indexes(apps):
    """각 앱 index.json 로드 → records 합침."""
    root = _project_root()
    all_records = []
    for app in apps:
        idx_path = root / "references" / "uibowl" / app / "index.json"
        if not idx_path.exists():
            continue
        try:
            data = json.loads(idx_path.read_text())
            for r in data.get("records", []):
                r["_app"] = app
                all_records.append(r)
        except Exception as e:
            print(f"  ⚠️ {app}/index.json 로드 실패: {e}", file=sys.stderr)
    return all_records


def _filter(records, patterns=None, keyword=None):
    out = []
    for r in records:
        if patterns:
            if r.get("patternCodeName") not in patterns:
                continue
        if keyword:
            kw = keyword.lower()
            pn = (r.get("patternName") or "").lower()
            desc = (r.get("description") or "").lower()
            pcn = (r.get("patternCodeName") or "").lower()
            if kw not in pn and kw not in desc and kw not in pcn:
                continue
        out.append(r)
    return out


def _dedupe_by_pattern(records, limit_per_pattern=2):
    """같은 patternName 너무 많이 출력 안 함 — 다양한 화면 보여줌."""
    seen = {}
    out = []
    for r in records:
        key = (r.get("_app"), r.get("patternName") or "_blank")
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > limit_per_pattern:
            continue
        out.append(r)
    return out


def _make_thumbnail(src_path: Path, max_dim: int = 1200) -> Path:
    """원본 PNG 가 max_dim 보다 크면 thumbnail 생성. 작으면 원본 그대로 반환.

    thumbnail 경로: scripts/ref_thumbnails/<imgId>.png
    """
    try:
        from PIL import Image
    except ImportError:
        return src_path
    root = _project_root()
    thumb_dir = root / "scripts" / "ref_thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumb_dir / src_path.name
    if thumb_path.exists():
        return thumb_path
    try:
        img = Image.open(src_path)
        w, h = img.size
        if max(w, h) <= max_dim:
            return src_path
        ratio = max_dim / max(w, h)
        new_size = (int(w * ratio), int(h * ratio))
        img.thumbnail(new_size, Image.LANCZOS)
        img.save(thumb_path, "PNG", optimize=True)
        return thumb_path
    except Exception:
        return src_path


def main():
    p = argparse.ArgumentParser(description="uibowl PNG reference search")
    p.add_argument("--archetype", help="imin_home / imin_stage / imin_lounge 등")
    p.add_argument("--pattern", help='patternCodeName 직접 ("메인", "신청하기" 등) — 콤마 구분 가능')
    p.add_argument("--keyword", help="patternName/description/patternCodeName 부분 일치")
    p.add_argument("--apps", help="제한 앱 (콤마 구분, 기본 = 전체 5개)")
    p.add_argument("--limit", type=int, default=8, help="최대 출력 개수 (기본 8)")
    p.add_argument("--per-pattern", type=int, default=2, help="같은 patternName 최대 출력 (기본 2)")
    p.add_argument("--json", action="store_true", help="JSON 출력 (자동화용)")
    p.add_argument("--thumbnail", action="store_true",
                   help="원본 PNG 가 LLM Read 가능한 크기 (≤1500px) 로 thumbnail 자동 생성 후 그 path 반환")
    args = p.parse_args()

    apps = [a.strip() for a in args.apps.split(",")] if args.apps else APPS

    patterns = None
    if args.archetype:
        resolved = resolve_archetype(args.archetype)
        if resolved and resolved != args.archetype:
            print(f"ℹ️  archetype '{args.archetype}' → keyword fallback → '{resolved}'",
                  file=sys.stderr)
        patterns = ARCHETYPE_PATTERN_MAP.get(resolved or args.archetype)
        if not patterns:
            print(f"❌ 알 수 없는 archetype '{args.archetype}'. "
                  f"가능: {', '.join(ARCHETYPE_PATTERN_MAP.keys())}",
                  file=sys.stderr)
            sys.exit(2)
    if args.pattern:
        patterns = [s.strip() for s in args.pattern.split(",")]

    records = _load_indexes(apps)
    filtered = _filter(records, patterns=patterns, keyword=args.keyword)
    filtered = _dedupe_by_pattern(filtered, limit_per_pattern=args.per_pattern)
    filtered = filtered[: args.limit]

    # thumbnail 자동 생성 (LLM Read 가능 크기)
    if args.thumbnail:
        root = _project_root()
        for r in filtered:
            src = root / "references" / r["localPath"]
            if src.exists():
                thumb = _make_thumbnail(src, max_dim=1200)
                r["_thumbPath"] = str(thumb.relative_to(root))

    if args.json:
        print(json.dumps([
            {
                "path": "references/" + r["localPath"],
                "thumbPath": r.get("_thumbPath"),
                "app": r["_app"],
                "patternCodeName": r.get("patternCodeName"),
                "patternName": r.get("patternName"),
                "imgId": r.get("imgId"),
            }
            for r in filtered
        ], ensure_ascii=False, indent=2))
        return

    if not filtered:
        print(f"⚠️ 매칭 결과 없음 (patterns={patterns}, keyword={args.keyword})")
        sys.exit(1)

    print(f"📸 references/uibowl 검색 결과 — {len(filtered)}장 "
          f"(filter: pattern={patterns or '-'}, keyword={args.keyword or '-'}, apps={apps})")
    print("=" * 70)
    for r in filtered:
        p_display = r.get("_thumbPath") or f"references/{r['localPath']}"
        print(f"  [{r['_app']:9s}] {r['patternCodeName']:14s} | {(r.get('patternName') or '-')[:24]:25s} | {p_display}")
    print()
    print("⚠️ Claude: 위 PNG path 들을 Read 도구로 모두 열어 시각 학습 후 빌드 진행할 것.")
    print("   path 만 references[] field 에 박지 말고 실제 이미지의 시각 위계/리듬/컬러 매핑 참고.")


if __name__ == "__main__":
    main()
