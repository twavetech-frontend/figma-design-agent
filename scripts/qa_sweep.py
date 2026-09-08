#!/usr/bin/env python3
"""qa_sweep — 변환/개조 트랙 완료 게이트 원커맨드 (2026-09-03 신설).

배경(사용자 진단): "제일 문제는 계속 수정해야 될 부분을 못 찾는다는 거야" —
모델의 검증이 '방금 고친 곳'에 묶여 있고, 검사 도구가 낱개라 기억나는 것만 돌리며,
게이트 2개(verify+diff) 통과를 완료로 선언해 아이콘/텍스트/구조 차원이 항상
사용자 첫 발견이 되던 구조를 봉합한다.

검사 4차원을 한 번에 실행한다:
  ① 토큰 바인딩   — verify_bindings (PASS 필수)
  ② 면·색        — ds_convert_lib.region_diff (구역 픽셀 스코어 + 색 성분 진단)
  ③ 아이콘       — ds_convert_lib.icon_sheet gen/ref 병합 시트 (형태·크기 대조)
  ④ 요소 인벤토리 — TEXT 전수(내용·크기·색)와 fontSize/색 팔레트의 gen↔ref 차이 플래그
  ⑤ 소형 요소 실측 — pixel_measure: 도트/아이콘/링/선(≤16px) 지름·굵기를 4x 픽셀 실측해 대조
     (규칙 0-F-3 — 크기/굵기/간격은 눈으로 판독하지 않고 숫자로 잰다)

사용:
  python3 scripts/qa_sweep.py <genId> <refId> [--allow "이름,..."]

🔴 완료 규칙 (완료 보고의 정의):
  - exit 0 + requiredActions 의 이미지 전부 Read + CHECK 항목 전부 해소/설명 없이는
    완료 보고 금지. 게이트 통과 ≠ 완료 — requiredActions 가 비어야 완료다.
  - 수리 1건을 하면 같은 원인의 전수 스캔 후 qa_sweep 재실행 (발견 지점만 고치고
    끝내는 습관 차단 — 2026-09-03 흰 fill 재발 교훈).
"""
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import figma_mcp_client as fc  # noqa: E402
import ds_convert_lib as L  # noqa: E402

OUT_DIR = os.path.join(_HERE, 'qa_screenshots')


def _texts(root_id):
    """TEXT 전수: (chars, fontSize, fill hex) 목록 + fontSize/색 집합."""
    t = L.fetch_tree(root_id)
    rows = []

    def w(n):
        if (n.get('id') or '').startswith('I'):
            return
        if n.get('type') == 'TEXT':
            st = n.get('style') or {}
            fills = [L.to_hex(p.get('color', {})) for p in n.get('fills') or []
                     if isinstance(p, dict) and p.get('type') == 'SOLID'
                     and p.get('visible') is not False]
            rows.append(((n.get('characters') or '').strip()[:20],
                         st.get('fontSize') or n.get('fontSize'),
                         fills[0] if fills else None, n.get('id')))
        for c in n.get('children', []) or []:
            w(c)

    if t:
        w(t)
    return rows


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) < 2:
        print(__doc__)
        return 2
    gen, ref = args[0], args[1]
    allow = ''
    for i, a in enumerate(sys.argv):
        if a == '--allow' and i + 1 < len(sys.argv):
            allow = sys.argv[i + 1]

    fc.ensure_session()
    os.makedirs(OUT_DIR, exist_ok=True)
    checks = []        # (dimension, status 'PASS'|'CHECK', detail)
    required = []      # Read 의무 파일 목록

    # ① 토큰
    cmd = [sys.executable, os.path.join(_HERE, 'verify_bindings.py'), gen]
    if allow:
        cmd += ['--allow', allow]
    r = subprocess.run(cmd, capture_output=True, text=True)
    tail = '\n'.join(r.stdout.strip().splitlines()[-4:])
    print(f'━━ ① 토큰 바인딩\n{tail}')
    checks.append(('tokens', 'PASS' if r.returncode == 0 else 'CHECK', tail[-200:]))

    # ② 면·색
    print('━━ ② 면·색 (region_diff)')
    bands = L.region_diff(gen, ref, out_dir=OUT_DIR)
    flagged = [b for b in bands if b[2]]
    checks.append(('regions', 'PASS' if not flagged else 'CHECK',
                   f'{len(flagged)}구역 초과'))
    required += [b[2] for b in flagged]

    # ③ 아이콘
    print('━━ ③ 아이콘 (icon_sheet)')
    gp = os.path.join(OUT_DIR, 'sweep_icons_gen.png')
    rp = os.path.join(OUT_DIR, 'sweep_icons_ref.png')
    gi = L.icon_sheet(gen, gp)
    ri = L.icon_sheet(ref, rp)
    both = os.path.join(OUT_DIR, 'sweep_icons_both.png')
    try:
        from PIL import Image
        a = Image.open(gp) if gi else None
        b = Image.open(rp) if ri else None
        if a and b:
            cv = Image.new('RGB', (a.size[0] + b.size[0] + 20,
                                   max(a.size[1], b.size[1]) + 16), (205, 205, 215))
            cv.paste(b, (0, 14)); cv.paste(a, (b.size[0] + 20, 14))
            cv.save(both)
            required.append(both)
    except Exception:
        pass
    gs = sorted({(w1, h1) for _, w1, h1, _ in gi})
    rs = sorted({(w1, h1) for _, w1, h1, _ in ri})
    size_only_gen = [s for s in gs if s not in rs]
    checks.append(('icons', 'CHECK' if (gi or ri) else 'PASS',
                   f'gen {len(gi)}개/ref {len(ri)}개, gen 에만 있는 크기 {size_only_gen}'
                   if (gi or ri) else '아이콘 없음'))
    if gi or ri:
        print(f'   gen {len(gi)} / ref {len(ri)} — 병합 시트 Read 로 형태·크기 대조 의무')

    # ④ 요소 인벤토리 (TEXT 크기/색 분포)
    print('━━ ④ 요소 인벤토리 (TEXT)')
    gt, rt = _texts(gen), _texts(ref)
    g_sizes = sorted({r2[1] for r2 in gt if r2[1]})
    r_sizes = sorted({r2[1] for r2 in rt if r2[1]})
    g_colors = sorted({r2[2] for r2 in gt if r2[2]})
    r_colors = sorted({r2[2] for r2 in rt if r2[2]})
    size_diff = [s for s in g_sizes if s not in r_sizes]
    color_diff = [c for c in g_colors if c not in r_colors]
    print(f'   TEXT gen {len(gt)} / ref {len(rt)}')
    print(f'   fontSize gen {g_sizes} / ref {r_sizes}' +
          (f'  🔴 gen 에만: {size_diff}' if size_diff else ''))
    print(f'   색 gen 에만: {color_diff[:8]}' if color_diff else '   색 팔레트 ref 와 일치')
    checks.append(('inventory', 'CHECK' if (size_diff or color_diff) else 'PASS',
                   f'size {size_diff} color {color_diff[:6]}'))

    # ⑤ 소형 요소 픽셀 실측 (규칙 0-F-3, 2026-09-08 사용자: "왜 자꾸 눈으로 보고 판단하지??")
    #    도트/아이콘/링/선 같은 ≤16px 반복 요소의 지름·굵기를 4x export 에서 실측해 gen↔ref 대조.
    #    gen 에 3회 이상 반복되는데 ref 에 ±1px 매칭이 없는 규격 → CHECK (숫자로 해소/설명 의무).
    print('━━ ⑤ 소형 요소 실측 (pixel_measure)')
    try:
        import pixel_measure as pm
        gp4 = os.path.join(OUT_DIR, 'sweep_pm_gen.png')
        rp4 = os.path.join(OUT_DIR, 'sweep_pm_ref.png')
        fc.export_image(gen, gp4, 'PNG', 4)
        fc.export_image(ref, rp4, 'PNG', 4)
        gw = float(((fc.parse_content(fc.call_tool('get_node_info', {'nodeId': gen})).get('json') or {}).get('node') or {}).get('width') or 393)
        rw = float(((fc.parse_content(fc.call_tool('get_node_info', {'nodeId': ref})).get('json') or {}).get('node') or {}).get('width') or 393)
        pmres = pm.run(gp4, gw, rp4, rw, max_size=16, tol=1.0, min_count=3)
        mism = pmres['mismatches']
        checks.append(('pixel-measure', 'CHECK' if mism else 'PASS',
                       ('gen 에만 있는 반복 규격 ' + '; '.join(
                           f"{m['kind']} {m['w']}×{m['h']}" + (f" s{m['stroke']}" if m['stroke'] is not None else '') + f" ×{m['count']}"
                           for m in mism)) if mism else '소형 반복 요소 규격 ref 와 일치'))
    except Exception as e:
        checks.append(('pixel-measure', 'CHECK', f'실측 실패: {e}'))

    # 요약
    ok = all(s == 'PASS' for _, s, _ in checks)
    print('\n📋 QA-SWEEP-JSON')
    print(json.dumps({
        'type': 'qa-sweep', 'gen': gen, 'ref': ref,
        'result': 'pass' if ok and not required else 'needs-review',
        'checks': [{'dim': d, 'status': s, 'detail': dt} for d, s, dt in checks],
        'requiredActions': [
            {'type': 'read', 'paths': sorted(set(required))},
            {'type': 'rule', 'text': 'CHECK 차원은 항목별 해소/설명 후 재실행 — '
                                     'requiredActions 가 비어야 완료 보고 가능'},
        ] if (required or not ok) else [],
    }, ensure_ascii=False, indent=1))
    return 0 if ok and not required else 1


if __name__ == '__main__':
    sys.exit(main())
