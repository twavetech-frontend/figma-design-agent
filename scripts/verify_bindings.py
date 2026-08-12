#!/usr/bin/env python3
"""DS 변환 완료 게이트 — 토큰 바인딩 전수 실사 (2026-08-10 신설).

배경: 재구성/변환 화면에서 "바인딩 완료" 보고 후 실제로는 텍스트 스타일이 전부
미적용이던 회귀(사용자 보고 ×2). 원인은 set_text_style_id 의 silent 실패
(textStyleId "S:key," 형식 — 콤마 뒤가 비면 플러그인 정규식 /^S:([^,]+),(.+)$/ 을
못 타 로컬 조회로 떨어짐)를 카운터가 성공으로 오집계한 것.

이 스크립트는 **결과 상태만** 실사한다(적용 로그를 믿지 않는다):
  - SOLID fill/stroke 가 있는데 boundVariables 가 빈 노드 (흰/검 순수값 제외)
  - characters 가 있는데 textStyleId 가 빈 TEXT 노드
FAIL ≥1 → exit 1. 변환 작업은 이 게이트가 0건일 때만 완료 보고한다.

사용: python3 scripts/verify_bindings.py <rootId> [--allow "이름1,이름2"]
  --allow: 의도적 원값 복원 노드(브랜드 로고, DS 밖 색 소실 방지 등) 이름 스킵.
인스턴스 내부(';' id)는 0-K(마스터 제어)라 검사 제외.
"""
import sys

sys.path.insert(0, '/Users/julee/imin/figma-design-agent/scripts')
import figma_mcp_client as fc


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print('사용법: verify_bindings.py <rootId> [--allow "이름1,이름2"]')
        return 2
    root = args[0]
    allow = set()
    for i, a in enumerate(sys.argv):
        if a == '--allow' and i + 1 < len(sys.argv):
            allow = {s.strip() for s in sys.argv[i + 1].split(',') if s.strip()}

    fc.ensure_session()

    def call(t, a):
        return fc.parse_content(fc.call_tool(t, a)).get('json')

    def to_hex(c):
        return '#{:02x}{:02x}{:02x}'.format(
            round(c.get('r', 0) * 255), round(c.get('g', 0) * 255), round(c.get('b', 0) * 255))

    bad_paint = []
    bad_style = []
    checked = 0

    def walk(nid, d=0):
        nonlocal checked
        if d > 9:
            return
        n = call('get_node_info', {'nodeId': nid}) or {}
        node_id = n.get('id') or ''
        t = n.get('type')
        name = n.get('name') or ''
        if ';' not in node_id and t in ('FRAME', 'TEXT', 'RECTANGLE', 'ELLIPSE', 'VECTOR', 'LINE', 'BOOLEAN_OPERATION'):
            checked += 1
            bv = (call('get_bound_variables', {'nodeId': node_id}) or {}).get('boundVariables') or {}
            if name not in allow:
                all_vis = [f for f in (n.get('fills') or []) if isinstance(f, dict) and f.get('visible') is not False]
                cols = []
                acols = []  # 순검정/순흰 반투명 — Alpha 토큰 바인딩 대상 (2026-08-12)
                # 멀티페인트(그라디언트 등 포함)는 바인딩 불가 대상 — 검사 제외
                if len(all_vis) == 1:
                    for f in all_vis:
                        if f.get('type') != 'SOLID':
                            continue
                        eff = f.get('opacity', 1) * (f.get('color') or {}).get('a', 1)
                        hx = to_hex(f.get('color', {}))
                        if eff >= 0.999:
                            cols.append(hx)
                        elif eff > 0.005 and hx in ('#ffffff', '#000000'):
                            acols.append((hx, round(eff, 2)))
                scols = []
                sacols = []
                # mixed strokeWeight(개별 사이드)여도 stroke '색'은 페인트 레벨 — 검사 대상
                # (2026-08-12: Tab 하단 라인 #eceef1 미바인딩이 mixed 제외 뒤에 숨었음).
                # 바인딩은 set_bound_variables 로만 (색 setter 는 평탄화).
                if True:
                    for s in (n.get('strokes') or []):
                        if not (isinstance(s, dict) and s.get('type') == 'SOLID'):
                            continue
                        eff = s.get('opacity', 1) * (s.get('color') or {}).get('a', 1)
                        hx = to_hex(s.get('color', {}))
                        if eff >= 0.999:
                            scols.append(hx)
                        elif eff > 0.005 and hx in ('#ffffff', '#000000'):
                            # 완전 투명(알파 0)은 시각 무의미 — 바인딩 대상 아님
                            sacols.append((hx, round(eff, 2)))
                cols = [c for c in cols if c not in ('#ffffff', '#000000')]
                scols = [c for c in scols if c not in ('#ffffff', '#000000')]
                if cols and not bv.get('fills'):
                    bad_paint.append((name, t, 'fill', cols))
                if scols and not bv.get('strokes'):
                    bad_paint.append((name, t, 'stroke', scols))
                if acols and not bv.get('fills'):
                    bad_paint.append((name, t, 'fill-alpha', acols))
                if sacols and not bv.get('strokes'):
                    bad_paint.append((name, t, 'stroke-alpha', sacols))
            if t == 'TEXT' and name not in allow and (n.get('characters') or '').strip() \
                    and not (n.get('textStyleId') or ''):
                bad_style.append((name, (n.get('characters') or '')[:14]))
        for c in n.get('children', []) or []:
            walk(c['id'], d + 1)

    walk(root)
    print(f'[verify-bindings] 검사 {checked}노드 (root {root})')
    if bad_paint:
        print(f'  ✗ 색 미바인딩 {len(bad_paint)}건:')
        for b in bad_paint[:15]:
            print('    ', b)
    if bad_style:
        print(f'  ✗ 텍스트 스타일 미적용 {len(bad_style)}건:')
        for b in bad_style[:15]:
            print('    ', b)
    if not bad_paint and not bad_style:
        print('  ✓ PASS — 색/텍스트 스타일 바인딩 전수 확인')
        return 0
    print('  → FAIL: 바인딩 완료 보고 금지. bind 재실행 후 재검증할 것.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
