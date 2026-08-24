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
  🔴 2026-08-14: allow 는 **서브트리 전체** 면제 — 브랜드 로고/일러스트 그룹(my_wallet_gp_1 등)의
  내부 Vector/Ellipse/이미지 크롭은 에셋 고유색이라 토큰 바인딩 대상이 아니다. 이름이 allow 에
  있으면 그 하위 전부 스킵(사용자 수정본의 일러스트 이식이 게이트에 걸리던 문제 해결).
인스턴스 내부(';' id)는 0-K(마스터 제어)라 검사 제외.
"""
import sys

sys.path.insert(0, '/Users/julee/imin/figma-design-agent/scripts')
import figma_mcp_client as fc


_CANON_CACHE = None

def _canon_gradients():
    """PAINT_STYLE_MAP 의 Gradient/Brand 스타일에서 (stop hex 시그니처)→정본 키 맵 파생."""
    global _CANON_CACHE
    if _CANON_CACHE is not None:
        return _CANON_CACHE
    import json as _json, os as _os
    step = {'700': '#5200b0', '600': '#6a00e0', '500': '#7700ff',
            '400': '#9b55ff', '300': '#b685ff', '200': '#cfaeff'}
    out = {}
    try:
        entries = _json.load(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                                '..', 'ds', 'PAINT_STYLE_MAP.json')))
    except Exception:
        entries = []
    for e in entries:
        nm = e.get('name') or ''
        if nm.startswith('Gradient/Brand/'):
            hexes = tuple(step.get(t.strip()) for t in nm.split('/')[-1].split('->'))
            if all(hexes):
                out[hexes] = e['key']
    out.setdefault(('#6a00e0', '#7700ff', '#9b55ff'),
                   '2d6d98a9c0279efe0b0eb1ea7ba3c46e7cae94d7')
    _CANON_CACHE = out
    return out


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
        # allow 노드는 서브트리 전체 면제 (2026-08-14 — 브랜드 에셋 내부색은 검사 대상 아님)
        if name in allow:
            return
        # 🔴 invisible 서브트리 면제 (2026-08-21 — 숨은 card_share 컴포넌트 잔재의 텍스트가
        # FAIL 을 내던 구멍. 렌더에 안 보이는 노드는 바인딩 게이트 대상이 아니다.)
        if n.get('visible') is False:
            return
        # STAR/POLYGON 누락으로 별점 옐로 미바인딩이 게이트를 통과했음 (2026-08-12 사용자 지적)
        if ';' not in node_id and t in ('FRAME', 'TEXT', 'RECTANGLE', 'ELLIPSE', 'VECTOR', 'LINE',
                                        'BOOLEAN_OPERATION', 'STAR', 'POLYGON'):
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
                        # visible:False 페인트는 렌더 무관 — 오탐 제외 (2026-08-14 Oval 링 실측)
                        if s.get('visible') is False:
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
                # 🔴 브랜드 gradient stop 미바인딩 감지 (2026-08-14 사용자: "gradient 값이
                # ds 토큰이 아니야") — DS Gradient/Brand 스텝과 정확 일치하는 stop 인데
                # 변수 바인딩이 없으면 FAIL. 비표준 스텝(앱 아이콘 에셋 등)은 검사 제외.
                _BRAND_STEPS = {'#5200b0', '#6a00e0', '#7700ff', '#9b55ff', '#b685ff', '#cfaeff'}
                for _slot in ('fills', 'strokes'):
                    for _p in (n.get(_slot) or []):
                        if not (isinstance(_p, dict) and str(_p.get('type', '')).startswith('GRADIENT')
                                and _p.get('visible') is not False):
                            continue
                        _stops = _p.get('gradientStops') or []
                        _hexes = [to_hex(_st.get('color', {})) for _st in _stops]
                        if _hexes and all(h in _BRAND_STEPS for h in _hexes):
                            # 정본 = DS color style(fillStyleId). 스타일 미확인 시그니처만
                            # stop 변수 바인딩 폴백 허용 (2026-08-14 사용자: "gradient 는
                            # DS 의 color style 로 정의되어 있어").
                            _CANON = _canon_gradients()
                            _sid = n.get('fillStyleId') or ''
                            _ck = _CANON.get(tuple(_hexes))
                            if _ck:
                                # 정본 키가 있는 시그니처: 그 키가 아니면 FAIL
                                # (legacy 'Gradient-6~5~4_h' 등 잘못된 스타일 잔존 차단 —
                                #  2026-08-14 사용자 재지적)
                                if _ck not in _sid:
                                    bad_paint.append((name, t, 'gradient-wrong-style',
                                                      [_sid or 'unstyled']))
                                continue
                            if _sid:
                                continue
                            _unbound = [h for _st, h in zip(_stops, _hexes) if not _st.get('bound')]
                            if _unbound:
                                bad_paint.append((name, t, 'gradient-unstyled', _unbound))
                # 🔴 아이콘 자리 이미지 크롭 감지 (2026-08-12 사용자: chevron 을 크롭으로 때움) —
                # ≤36px 정사각급 노드의 IMAGE fill = DS 아이콘(type:'icon'/svg_icon/인스턴스)으로
                # 교체해야 할 크롭 의심. 사진 썸네일은 이 크기 범위 밖이라 오탐 없음.
                w = n.get('width') or 0
                h = n.get('height') or 0
                if w <= 36 and h <= 36 and any(
                        isinstance(f, dict) and f.get('type') == 'IMAGE' and f.get('visible') is not False
                        for f in (n.get('fills') or [])):
                    bad_paint.append((name, t, 'icon-crop-suspect', [f'{round(w)}x{round(h)} IMAGE fill']))
            if t == 'TEXT' and name not in allow and (n.get('characters') or '').strip() \
                    and not (n.get('textStyleId') or ''):
                bad_style.append((name, (n.get('characters') or '')[:14]))
            # 🔴 아이콘 자리 텍스트 글리프 화살표 감지 (2026-08-21 사용자: '자세히 보기 >' 재발 ×3) —
            # 라벨 끝/앞의 >, ›, <, ‹, →, ← 글리프 = DS chevron/arrow 아이콘 인스턴스로 교체 대상.
            # icon-crop-suspect(크롭)만 있고 글리프 감지기가 없어 verify PASS 로 새던 구멍.
            if t == 'TEXT' and name not in allow:
                _ch = (n.get('characters') or '').strip()
                _GLYPHS = ('>', '›', '<', '‹', '→', '←', '➜', '❯', '❮')
                if _ch and len(_ch) > 1 and (
                        any(_ch.endswith(' ' + g) or _ch.endswith(g) and _ch[-2:-1] == ' ' for g in _GLYPHS)
                        or any(_ch.startswith(g + ' ') for g in _GLYPHS)):
                    bad_paint.append((name, t, 'icon-glyph-suspect',
                                      [f'글리프 {_ch[-1] if _ch[-1] in _GLYPHS else _ch[0]!r} — DS 아이콘 인스턴스로 교체']))
            # 🔴 raw badge/pill 감지 (2026-08-21 사용자: '쿠폰' 칩을 raw 로 그림 — Badge 컴포넌트 써야) —
            # R23 lint 는 blueprint 빌드 경로 전용이라 라이브 조립/변환 경로엔 게이트가 없던 구멍.
            # pill 급 radius + 짧은 단일 TEXT 라벨 + 소형 FRAME(비 인스턴스) = DS Badge 교체 의심.
            # bare 숫자 셀('1'~'13')·allow 는 제외 (ds_catalog badge 가드와 동일 기준).
            if t == 'FRAME' and ';' not in node_id and name not in allow:
                _h = n.get('height') or 0
                _w = n.get('width') or 0
                _rad = n.get('cornerRadius') or 0
                _kids = [c for c in (n.get('children') or [])]
                _txts = [c for c in _kids if c.get('type') == 'TEXT']
                if 14 <= _h <= 34 and 0 < _w <= 130 and _rad >= max(10, _h / 2 - 2) \
                        and len(_txts) == 1 and len(_kids) == 1:
                    _lbl = (_txts[0].get('characters') or '').strip()
                    if _lbl and len(_lbl) <= 8 and not _lbl.isdigit():
                        bad_paint.append((name, t, 'raw-badge-suspect',
                                          [f'라벨 {_lbl!r} — DS Badge/Pill 인스턴스로 교체(Color prop)']))
            # 🔴 plain frame 감지 (2026-08-24 사용자 지적: "어느순간 일반 프레임을 많이 쓰고 있다")
            # 콘텐츠 컨테이너(흐름형 자식 ≥2)가 layoutMode NONE 이면 FAIL — 오토레이아웃 의무.
            # 예외: 화면 루트(폭 393±2)·오버레이 전용(자식 전부 ABSOLUTE)·allow.
            if t == 'FRAME' and ';' not in node_id and name not in allow \
                    and not n.get('layoutMode') and abs((n.get('width') or 0) - 393) > 2:
                _flow_kids = [c for c in (n.get('children') or [])
                              if c.get('type') in ('FRAME', 'TEXT', 'INSTANCE', 'RECTANGLE')
                              and c.get('layoutPositioning') != 'ABSOLUTE'
                              and c.get('visible') is not False]
                if len(_flow_kids) >= 2:
                    bad_paint.append((name, t, 'plain-frame-suspect',
                                      [f'layoutMode NONE + 흐름형 자식 {len(_flow_kids)}개 — 오토레이아웃 전환 필요(규칙 8)']))
            # 🔴 시트/리스트 행 HUG 감지 (2026-08-24 사용자 지적: 바텀시트 메뉴 item 이 HUG 라
            # 텍스트 폭 75 로 좁아짐 — 규칙 8: 행/항목 FRAME 은 가로 FILL). 이름에 '시트'/'sheet'
            # 포함 컨테이너의 직계 행 FRAME 이 FILL 아니고 부모 폭의 60% 미만이면 FAIL.
            if t == 'FRAME' and ';' not in node_id and name not in allow \
                    and ('시트' in name or 'sheet' in name.lower()):
                _pw = n.get('width') or 0
                for _row in (n.get('children') or []):
                    if _row.get('type') != 'FRAME' or _row.get('layoutPositioning') == 'ABSOLUTE':
                        continue
                    _rw = _row.get('width') or 0
                    _rh = _row.get('height') or 0
                    if 36 <= _rh <= 72 and _pw > 0 and _rw < _pw * 0.6 \
                            and _row.get('layoutSizingHorizontal') != 'FILL':
                        bad_paint.append((_row.get('name') or '', 'FRAME', 'sheet-item-not-fill',
                                          [f'행 폭 {round(_rw)} < 부모 {round(_pw)} — 가로 FILL 필수(규칙 8)']))
            # 🔴 raw Tool Bar 문법 감지 (2026-08-20 사용자 지적 ×2: fill 없는 투명 Tool Bar /
            # 24h·y76 'App bar' 잔재). 텍스트 버튼형 헤더는 raw 허용이지만 정본 문법 강제:
            # 이름에 'Tool Bar' 포함 raw FRAME 은 h=56 + 가시 fill(bg-primary 바인딩) 필수.
            if t == 'FRAME' and ';' not in node_id and 'Tool Bar' in name and name not in allow:
                _fills_tb = [f for f in (n.get('fills') or [])
                             if isinstance(f, dict) and f.get('visible') is not False]
                if not _fills_tb:
                    bad_paint.append((name, t, 'toolbar-no-fill',
                                      ['raw Tool Bar 에 가시 fill 없음 — bg-primary 바인딩 필수(0-O)']))
                if round(n.get('height') or 0) != 56:
                    bad_paint.append((name, t, 'toolbar-bad-height',
                                      [f"h={round(n.get('height') or 0)} — Tool Bar 는 56 고정"]))
            # 구 명명 'App bar' raw 잔존 자체를 차단 (Tool Bar 로 정규화 안 된 신호)
            if t == 'FRAME' and ';' not in node_id and name.strip().lower() in ('app bar', 'top app bar') \
                    and name not in allow:
                bad_paint.append((name, t, 'appbar-legacy-name',
                                  ['구 명명 App bar 잔존 — Tool Bar 문법 정규화 필요(0-W/0-O)']))
            # 🔴 raw 토스트 감지 (2026-08-20 사용자 지적: 토스트 3장 raw pill 조립 — DS Toast
            # SET:27655caa… 가 정본). 다크 반투명 pill + 흰 짧은 텍스트 = Toast 인스턴스 교체 대상.
            if t == 'FRAME' and ';' not in node_id and name not in allow:
                _h2 = n.get('height') or 0
                _w2 = n.get('width') or 0
                _rad2 = n.get('cornerRadius') or 0
                _f = (n.get('fills') or [{}])[0] if (n.get('fills') or []) else {}
                _col = _f.get('color') or {} if isinstance(_f, dict) else {}
                _dark = all(_col.get(k, 1) < 0.35 for k in ('r', 'g', 'b')) and _col
                _kids2 = n.get('children') or []
                _tx2 = [c for c in _kids2 if c.get('type') == 'TEXT']
                if _dark and _rad2 >= 12 and 40 <= _h2 <= 64 and _w2 >= 200 \
                        and len(_tx2) >= 1 and len(_kids2) <= 2:
                    bad_paint.append((name, t, 'raw-toast-suspect',
                                      ["다크 pill 토스트 — DS 'Toast' 인스턴스(SET:27655caa…)로 교체"]))
            # 🔴 raw 모달/시트 X 헤더 감지 (2026-08-13 사용자: 바텀시트 타이틀도 Tool Bar) —
            # 룰 0-W(2026-08-04 개정): 모달 X 헤더 = Tool Bar 인스턴스(View=modal). raw close
            # 버튼 잔존(btn/close, ic_close 류 FRAME)은 헤더 미교체 신호 → FAIL.
            if t == 'FRAME' and ';' not in node_id and name in ('btn/close', 'btn_close', 'ic_close'):
                bad_paint.append((name, t, 'raw-modal-header',
                                  ['모달/시트 헤더는 Tool Bar(View=modal) 인스턴스로 교체']))
        for c in n.get('children', []) or []:
            walk(c['id'], d + 1)

    walk(root)
    # 🔴 화면 최소 높이 852 (2026-08-13 사용자: "화면높이의 최소 사이즈는 852야!") —
    # root 가 화면 프레임(폭 393±1)인데 h<852 면 FAIL. 섹션/컴포넌트 단품(폭≠393)은 제외.
    bad_size = []
    rn = call('get_node_info', {'nodeId': root}) or {}
    rw, rh = rn.get('width') or 0, rn.get('height') or 0
    if abs(rw - 393) <= 1 and rh < 852:
        bad_size.append((rn.get('name'), f'화면 높이 {round(rh)} < 최소 852'))
    print(f'[verify-bindings] 검사 {checked}노드 (root {root})')
    # 🔴 0노드 = root 조회 실패(삭제/오타/세션 끊김) — 공허 PASS 방지 (2026-08-13)
    if checked == 0:
        print('  ✗ 검사 대상 0노드 — root 미존재/조회 실패. PASS 아님.')
        return 1
    if bad_size:
        print(f'  ✗ 화면 크기 위반 {len(bad_size)}건:')
        for b in bad_size:
            print('    ', b)
        bad_paint.extend(bad_size)
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
