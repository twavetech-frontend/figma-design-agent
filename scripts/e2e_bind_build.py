#!/usr/bin/env python3
"""
Phase A End-to-End 테스트
=========================
Clone & Bind 파이프라인의 결정성을 증명.

플로우:
  1. blueprint.json 로드 (레퍼런스 원본)
  2. slots.json 로드 (치환 가능 슬롯 메타)
  3. 가상 PRD 값으로 slot_values 시뮬레이션 (Agent 역할 대체)
  4. lodash-set 방식으로 blueprint에 값 주입
  5. blueprint_sanitizer 통과
  6. batch_build_screen 호출

검증: 같은 slot_values → 같은 blueprint bit-level 동일 여부 확인.

사용:
    python3 scripts/e2e_bind_build.py                          # 기본 시나리오
    python3 scripts/e2e_bind_build.py --scenario missed_2      # 미납 2건 PRD
"""
import json
import sys
import copy
import re
import os
import hashlib
import argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blueprint_sanitizer import sanitize_blueprint


# ── 시나리오별 PRD-유래 slot 값 (실제 배포에선 Agent가 생성) ──
SCENARIOS = {
    "default": {
        # 원본 레퍼런스 값 유지
    },
    "missed_2": {
        "alert.title": "미납 2건 · 4월 22일",
        "alert.sub": "연체 이자가 누적되고 있어요 — 지금 해결하세요",
        "summary.pill.text": "5건 진행 중",
        "summary.earned.amount": "18,500,000",
        "summary.owed.amount": "−3,200,000",
        "schedule.missed.badge": "미납 2",
        "schedule.day1.number": "22",
        "schedule.day1.status": "미납",
        "schedule.day3.number": "24",
        "schedule.day3.status": "오늘",
        "limit.amount": "580",
        "limit.usage_pct": "11.2% 사용",
    },
    "new_user": {
        # 신규 유저 시나리오 — 미납 없음, 금액 작음
        "alert.title": "",  # 빈 값 (실제론 slot에서 배지 제거)
        "summary.pill.text": "1건 진행 중",
        "summary.earned.amount": "1,200,000",
        "summary.owed.amount": "−450,000",
        "schedule.missed.badge": "",
        "schedule.day1.status": "납입",
        "limit.amount": "12",
        "limit.usage_pct": "0.2% 사용",
    }
}


def lodash_set(obj, path_str, value):
    """lodash-path 기반 mutable set. children[3].children[0].text 형태."""
    tokens = re.findall(r'(\w+)|\[(\d+)\]', path_str)
    current = obj
    for i, (key, idx) in enumerate(tokens[:-1]):
        if idx:
            current = current[int(idx)]
        else:
            current = current[key]
    last_key, last_idx = tokens[-1]
    if last_idx:
        current[int(last_idx)] = value
    else:
        current[last_key] = value


def lodash_get(obj, path_str):
    tokens = re.findall(r'(\w+)|\[(\d+)\]', path_str)
    current = obj
    for key, idx in tokens:
        if idx:
            current = current[int(idx)]
        else:
            current = current[key]
    return current


def bind_content(blueprint, slots, slot_values):
    """Content Binder (S4) — slot id에 매핑된 값을 blueprint에 주입.
    value가 slot_values에 없으면 default 유지.
    """
    bp = copy.deepcopy(blueprint)
    applied = []
    skipped = []
    for slot in slots['slots']:
        sid = slot['id']
        if sid in slot_values:
            val = slot_values[sid]
            try:
                lodash_set(bp, slot['path'], val)
                applied.append(sid)
            except Exception as e:
                print(f"  ⚠️ Failed to set {sid}: {e}")
        else:
            skipped.append(sid)
    return bp, applied, skipped


def content_hash(bp):
    """Blueprint의 결정성 해시 (JSON canonical form)."""
    return hashlib.sha256(
        json.dumps(bp, sort_keys=True, ensure_ascii=False).encode('utf-8')
    ).hexdigest()[:16]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', default='default',
                        choices=list(SCENARIOS.keys()))
    parser.add_argument('--ref', default='imin-home',
                        help='Reference ID (default: imin-home)')
    parser.add_argument('--no-build', action='store_true',
                        help='Skip actual Figma build (only produce final blueprint)')
    parser.add_argument('--determinism-check', type=int, default=0,
                        help='Run N iterations and verify bit-level identical blueprints')
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ref_dir = os.path.join(root, 'docs', 'references', args.ref)

    # 1. Reference package load
    print(f"📦 Loading reference package: {args.ref}")
    with open(os.path.join(ref_dir, 'blueprint.json')) as f:
        blueprint = json.load(f)
    with open(os.path.join(ref_dir, 'slots.json')) as f:
        slots = json.load(f)
    with open(os.path.join(ref_dir, 'meta.json')) as f:
        meta = json.load(f)

    print(f"   slots: {len(slots['slots'])}개")
    print(f"   theme: {meta.get('theme')}, brand: {meta.get('brand')}")

    # 2. Scenario에 따라 slot values 선택
    slot_values = SCENARIOS[args.scenario]
    print(f"\n🎯 Scenario: '{args.scenario}' — {len(slot_values)}개 slot 치환")

    # 3. Bind content
    print(f"\n🔗 Content binding...")
    bound_bp, applied, skipped = bind_content(blueprint, slots, slot_values)
    print(f"   치환: {len(applied)}개, default 유지: {len(skipped)}개")

    # 4. Sanitize
    print(f"\n🧹 Sanitizing...")
    final_bp, warnings = sanitize_blueprint(bound_bp)
    if warnings:
        print(f"   경고 {len(warnings)}개 (첫 3개):")
        for w in warnings[:3]:
            print(f"     - {w}")

    # 5. 결정성 해시
    h = content_hash(final_bp)
    print(f"\n🔐 Blueprint hash: {h}")

    # 5b. Determinism check (option)
    if args.determinism_check > 0:
        print(f"\n🔁 Determinism check: {args.determinism_check} iterations")
        hashes = set()
        for i in range(args.determinism_check):
            bp2, _, _ = bind_content(blueprint, slots, slot_values)
            bp2, _ = sanitize_blueprint(bp2)
            hashes.add(content_hash(bp2))
        if len(hashes) == 1:
            print(f"   ✅ ALL {args.determinism_check} iterations produced IDENTICAL blueprint")
        else:
            print(f"   ❌ Non-deterministic: {len(hashes)} distinct hashes")

    # 6. 최종 blueprint 저장
    out = os.path.join(root, 'scripts', f'e2e_final_{args.scenario}.json')
    with open(out, 'w') as f:
        json.dump(final_bp, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Final blueprint saved: {out}")

    # 7. 빌드 (옵션)
    if not args.no_build:
        print(f"\n🏗️  Building in Figma...")
        import subprocess
        r = subprocess.run(
            ['python3', os.path.join(root, 'scripts', 'figma_mcp_client.py'), 'build', out],
            capture_output=True, text=True, timeout=180
        )
        for line in r.stdout.split('\n'):
            if 'rootId:' in line or '전체 완료' in line or 'ERROR' in line:
                print(f"   {line.strip()}")


if __name__ == '__main__':
    main()
