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
import ds_convert_lib as L  # fetch_tree (get_node_tree 1콜 — 2026-08-24 성능 수리)


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


_TOKEN_HEXES = None

def _no_near_token(hexes, max_delta=16):
    """모든 hex 가 TOKEN_MAP 실값과 근접(채널 Δ≤16)하지 않으면 True — 앱 고유 에셋 색 의심.
    (2026-08-24 채팅 stage 셀 실측: 판정을 수동 조사로 풀어 3분 낭비 → 게이트가 스스로
    '--allow 후보' 를 제안하도록 신설. 유채→무채 스냅 금지 가드와 짝 — 스냅하지 말고 allow.)"""
    global _TOKEN_HEXES
    if _TOKEN_HEXES is None:
        import json as _json, os as _os
        try:
            tm = _json.load(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                               '..', 'ds', 'TOKEN_MAP.json')))
            _TOKEN_HEXES = [tuple(int(v['value'][i:i + 2], 16) for i in (1, 3, 5))
                            for v in tm.values()
                            if isinstance(v.get('value'), str) and v['value'].startswith('#')
                            and len(v['value']) == 7]
        except Exception:
            _TOKEN_HEXES = []
    if not _TOKEN_HEXES:
        return False
    for hx in hexes:
        if not (isinstance(hx, str) and hx.startswith('#') and len(hx) == 7):
            return False
        r = tuple(int(hx[i:i + 2], 16) for i in (1, 3, 5))
        if any(max(abs(a - b) for a, b in zip(r, t)) <= max_delta for t in _TOKEN_HEXES):
            return False
    return True


def _custom_theme_header(n, parent):
    """유채 커스텀 배경 헤더(그룹 채팅 핑크 테마 등) 판정 — Tool Bar 인스턴스는 흰 배경
    고정+내부 색 변경 금지(0-K)라 이런 헤더는 raw 유지가 정본. appbar-legacy-name/
    raw-modal-header 게이트 면제 근거 (2026-08-24 사이드바 실측). 자체 fill 유채,
    또는 투명 + 부모 fill 유채."""
    def _chromatic(paints):
        for f in (paints or []):
            if isinstance(f, dict) and f.get('type') == 'SOLID' and f.get('visible') is not False:
                c = f.get('color') or {}
                vs = [round(c.get(k, 0) * 255) for k in 'rgb']
                if max(vs) - min(vs) >= 20:
                    return True
        return False
    # 그라데이션 헤더(이미지 뷰어 딤 스크림 등)도 Tool Bar 인스턴스로 표현 불가 (2026-08-24)
    if any(isinstance(f, dict) and str(f.get('type', '')).startswith('GRADIENT')
           and f.get('visible') is not False for f in (n.get('fills') or [])):
        return True
    fills = [f for f in (n.get('fills') or []) if isinstance(f, dict)
             and f.get('type') == 'SOLID' and f.get('visible') is not False]
    if _chromatic(fills):
        return True
    return not fills and parent is not None and _chromatic(parent.get('fills'))


def _overlaps_2d(kids):
    """자식들이 2D 로 서로 겹치는 조합(아바타 스택 등) — 오토레이아웃 표현 불가라 plain
    frame 이 정당. plain-frame-suspect 자동 면제 근거 (2026-08-24 채팅 Icon 스택 실측)."""
    rects = [(k.get('x') or 0, k.get('y') or 0, k.get('width') or 0, k.get('height') or 0)
             for k in kids]
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            ax, ay, aw, ah = rects[i]
            bx, by, bw, bh = rects[j]
            ox = max(0, min(ax + aw, bx + bw) - max(ax, bx))
            oy = max(0, min(ay + ah, by + bh) - max(ay, by))
            # 실질 교차(>1px 양축)면 겹침 조합 — 일반 흐름형 배치는 자식이 겹치지 않으므로
            # 오탐 없음. 대각 아바타 스택은 교차 면적이 작아(18%) 비율 임계는 못 잡는다.
            if aw and ah and bw and bh and ox > 1 and oy > 1:
                return True
    return False


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
    allow_candidates = set()  # 에셋 색 의심 노드명 — FAIL 시 --allow 후보로 제안
    sb_nodes = []  # (absY, id) — Status Bar 류. 한 화면 최상단 1개 게이트 (2026-08-24 규칙 1 강령)
    checked = 0

    # 1콜 트리 우선 (2026-08-24 성능 수리 — 노드당 get_node_info+get_bound_variables 왕복이
    # verify 시간의 대부분이었음). 트리 모드는 인스턴스 서브트리에 미진입(0-K — 내부는
    # 마스터 제어라 검사 대상 아님. 얕은 요약을 검사하면 textStyleId 부재 오탐이 나므로 스킵).
    def walk(src, d=0, parent=None, themed=False):
        nonlocal checked
        if d > 9:
            return
        is_dict = isinstance(src, dict)
        n = src if is_dict else (call('get_node_info', {'nodeId': src}) or {})
        node_id = n.get('id') or ''
        t = n.get('type')
        name = n.get('name') or ''
        # 유채 커스텀 테마 컨텍스트 — 조상 중 유채 배경 헤더가 있으면 서브트리에 전파
        themed = themed or (t == 'FRAME' and _custom_theme_header(n, parent))
        # FAIL 항목에 노드 id 병기 — 이름만 찍혀 트리 재조회를 강제하던 낭비 제거 (2026-08-24)
        disp = f'{name} <{node_id}>'
        # 🔴 Status Bar 는 한 화면 최상단 1개 (2026-08-24 사용자 룰 — 규칙 1 강령) — 수집 후
        # walk 끝에서 중복/위치 판정. abs y 는 트리 모드에서만 존재(폴백은 개수만 검사).
        if name.strip().lower() in ('bars', 'status bar', 'statusbar') \
                and ';' not in node_id and round(n.get('height') or 0) <= 70:
            sb_nodes.append((((n.get('absoluteBoundingBox') or {}).get('y')), node_id, disp))
        # allow 노드는 서브트리 전체 면제 (2026-08-14 — 브랜드 에셋 내부색은 검사 대상 아님)
        if name in allow:
            return
        # 'id:<nodeId>' allow = 해당 노드의 **페인트 검사만** 면제(서브트리 미면제) —
        # 루트 커스텀 배경(그룹채팅 핑크 등) 원값 유지용. 이름 allow 로 루트를 면제하면
        # 화면 전체 게이트가 꺼지는 구멍 방지 (2026-08-24 채팅 상세 실측).
        _id_allowed = f'id:{node_id}' in allow
        # 🔴 invisible 서브트리 면제 (2026-08-21 — 숨은 card_share 컴포넌트 잔재의 텍스트가
        # FAIL 을 내던 구멍. 렌더에 안 보이는 노드는 바인딩 게이트 대상이 아니다.)
        if n.get('visible') is False:
            return
        # STAR/POLYGON 누락으로 별점 옐로 미바인딩이 게이트를 통과했음 (2026-08-12 사용자 지적)
        if ';' not in node_id and t in ('FRAME', 'TEXT', 'RECTANGLE', 'ELLIPSE', 'VECTOR', 'LINE',
                                        'BOOLEAN_OPERATION', 'STAR', 'POLYGON'):
            checked += 1
            if is_dict:
                bv = n.get('boundVariables') or {}
            else:
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
                # 🔴 fill 의 순백/순검은 검사 대상 (2026-08-25 사용자: "컬러 토큰 바인딩이
                # 빠져있는 것들이 있다") — TEXT 순검=text-primary·순백=on-brand, 표면 순백=
                # bg-primary 로 bind 가 확정 바인딩하므로 미바인딩 잔존은 FAIL. 예외: 불투명
                # 순검 '면'(다크 앵커/에셋 모호)만 종전대로 제외. stroke 는 오스냅 회귀
                # (2026-08-10/08-24) 탓에 종전대로 제외.
                if t != 'TEXT':
                    cols = [c for c in cols if c != '#000000']
                scols = [c for c in scols if c not in ('#ffffff', '#000000')]
                if cols and _id_allowed:
                    cols = []
                if scols and _id_allowed:
                    scols = []
                if cols and not bv.get('fills'):
                    # 근접 토큰이 아예 없는 유채 = 앱 에셋 색 의심 — 스냅 대신 allow 후보 제안
                    if _no_near_token(cols):
                        allow_candidates.add(name)
                        cols = cols + ['asset-color 의심(근접 토큰 없음) — --allow 후보']
                    bad_paint.append((disp, t, 'fill', cols))
                if scols and not bv.get('strokes'):
                    if _no_near_token([c for c in scols if isinstance(c, str)]):
                        allow_candidates.add(name)
                        scols = scols + ['asset-color 의심(근접 토큰 없음) — --allow 후보']
                    bad_paint.append((disp, t, 'stroke', scols))
                if acols and not bv.get('fills'):
                    bad_paint.append((disp, t, 'fill-alpha', acols))
                if sacols and not bv.get('strokes'):
                    bad_paint.append((disp, t, 'stroke-alpha', sacols))
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
                                    bad_paint.append((disp, t, 'gradient-wrong-style',
                                                      [_sid or 'unstyled']))
                                continue
                            if _sid:
                                continue
                            _unbound = [h for _st, h in zip(_stops, _hexes) if not _st.get('bound')]
                            if _unbound:
                                bad_paint.append((disp, t, 'gradient-unstyled', _unbound))
                # 🔴 아이콘 자리 이미지 크롭 감지 (2026-08-12 사용자: chevron 을 크롭으로 때움) —
                # ≤36px 정사각급 노드의 IMAGE fill = DS 아이콘(type:'icon'/svg_icon/인스턴스)으로
                # 교체해야 할 크롭 의심. 사진 썸네일은 이 크기 범위 밖이라 오탐 없음.
                w = n.get('width') or 0
                h = n.get('height') or 0
                if w <= 36 and h <= 36 and any(
                        isinstance(f, dict) and f.get('type') == 'IMAGE' and f.get('visible') is not False
                        for f in (n.get('fills') or [])):
                    bad_paint.append((disp, t, 'icon-crop-suspect', [f'{round(w)}x{round(h)} IMAGE fill']))
            if t == 'TEXT' and name not in allow and (n.get('characters') or '').strip() \
                    and not (n.get('textStyleId') or ''):
                bad_style.append((disp, (n.get('characters') or '')[:14]))
            # 🔴 아이콘 자리 텍스트 글리프 화살표 감지 (2026-08-21 사용자: '자세히 보기 >' 재발 ×3) —
            # 라벨 끝/앞의 >, ›, <, ‹, →, ← 글리프 = DS chevron/arrow 아이콘 인스턴스로 교체 대상.
            # icon-crop-suspect(크롭)만 있고 글리프 감지기가 없어 verify PASS 로 새던 구멍.
            if t == 'TEXT' and name not in allow:
                _ch = (n.get('characters') or '').strip()
                _GLYPHS = ('>', '›', '<', '‹', '→', '←', '➜', '❯', '❮')
                if _ch and len(_ch) > 1 and (
                        any(_ch.endswith(' ' + g) or _ch.endswith(g) and _ch[-2:-1] == ' ' for g in _GLYPHS)
                        or any(_ch.startswith(g + ' ') for g in _GLYPHS)):
                    bad_paint.append((disp, t, 'icon-glyph-suspect',
                                      [f'글리프 {_ch[-1] if _ch[-1] in _GLYPHS else _ch[0]!r} — DS 아이콘 인스턴스로 교체']))
            # 🔴 raw badge/pill 감지 (2026-08-21 사용자: '쿠폰' 칩을 raw 로 그림 — Badge 컴포넌트 써야) —
            # R23 lint 는 blueprint 빌드 경로 전용이라 라이브 조립/변환 경로엔 게이트가 없던 구멍.
            # pill 급 radius + 짧은 단일 TEXT 라벨 + 소형 FRAME(비 인스턴스) = DS Badge 교체 의심.
            # bare 숫자 셀('1'~'13')·allow 는 제외 (ds_catalog badge 가드와 동일 기준).
            if t == 'FRAME' and ';' not in node_id and name not in allow:
                _h = n.get('height') or 0
                _w = n.get('width') or 0
                _rad = n.get('cornerRadius') or 0
                if not isinstance(_rad, (int, float)):
                    _rad = 999  # 'mixed'(개별 코너) — pill 의심 판정은 크기/라벨 조건에 맡김
                _kids = [c for c in (n.get('children') or [])]
                _txts = [c for c in _kids if c.get('type') == 'TEXT']
                if 14 <= _h <= 34 and 0 < _w <= 130 and _rad >= max(10, _h / 2 - 2) \
                        and len(_txts) == 1 and len(_kids) == 1:
                    _lbl = (_txts[0].get('characters') or '').strip()
                    # 'n/N' 카운트 오버레이(피드 캐러셀 표준 — 2026-08-21 사용자 확정 룰 14)는
                    # raw 가 정본 — Badge 교체 대상 아님
                    import re as _re
                    if _re.fullmatch(r'\d+\s*/\s*\d+', _lbl or ''):
                        _lbl = ''
                    if _lbl and len(_lbl) <= 8 and not _lbl.isdigit():
                        bad_paint.append((disp, t, 'raw-badge-suspect',
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
                # 2D 겹침 조합(아바타 스택 등)은 오토레이아웃 표현 불가 — 자동 면제 (2026-08-24)
                if len(_flow_kids) >= 2 and not _overlaps_2d(_flow_kids):
                    bad_paint.append((disp, t, 'plain-frame-suspect',
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
                        bad_paint.append((f"{_row.get('name') or ''} <{_row.get('id')}>", 'FRAME', 'sheet-item-not-fill',
                                          [f'행 폭 {round(_rw)} < 부모 {round(_pw)} — 가로 FILL 필수(규칙 8)']))
            # 🔴 raw Tool Bar 문법 감지 (2026-08-20 사용자 지적 ×2: fill 없는 투명 Tool Bar /
            # 24h·y76 'App bar' 잔재). 텍스트 버튼형 헤더는 raw 허용이지만 정본 문법 강제:
            # 이름에 'Tool Bar' 포함 raw FRAME 은 h=56 + 가시 fill(bg-primary 바인딩) 필수.
            if t == 'FRAME' and ';' not in node_id and 'Tool Bar' in name and name not in allow:
                _fills_tb = [f for f in (n.get('fills') or [])
                             if isinstance(f, dict) and f.get('visible') is not False]
                if not _fills_tb:
                    bad_paint.append((disp, t, 'toolbar-no-fill',
                                      ['raw Tool Bar 에 가시 fill 없음 — bg-primary 바인딩 필수(0-O)']))
                if round(n.get('height') or 0) != 56:
                    bad_paint.append((disp, t, 'toolbar-bad-height',
                                      [f"h={round(n.get('height') or 0)} — Tool Bar 는 56 고정"]))
            # 🔴 레거시 아이콘 이름 게이트 (0-L-2, 2026-08-24 사용자 룰) — 'ico'+'/' 경로형
            # 이름은 ic_스네이크로 정규화돼야 함 ('ico/empty/chat' → 'ic_empty_chat').
            if ';' not in node_id and name not in allow:
                _new_nm = L.normalize_icon_layer_name(name)
                if _new_nm:
                    bad_paint.append((disp, t, 'legacy-icon-name',
                                      [f"'{name}' → '{_new_nm}' — ico/경로명 금지, "
                                       f"ds_convert_lib.rename_legacy_icon_layers 로 정규화(0-L-2)"]))
            # 구 명명 'App bar' raw 잔존 자체를 차단 (Tool Bar 로 정규화 안 된 신호).
            # 유채 커스텀 테마 헤더는 raw 유지가 정본 — 면제 (2026-08-24)
            if t == 'FRAME' and ';' not in node_id and name.strip().lower() in ('app bar', 'top app bar') \
                    and name not in allow and not themed and not dark_screen \
                    and not _custom_theme_header(n, parent):
                bad_paint.append((disp, t, 'appbar-legacy-name',
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
                    bad_paint.append((disp, t, 'raw-toast-suspect',
                                      ["다크 pill 토스트 — DS 'Toast' 인스턴스(SET:27655caa…)로 교체"]))
            # 🔴 raw 모달/시트 X 헤더 감지 (2026-08-13 사용자: 바텀시트 타이틀도 Tool Bar) —
            # 룰 0-W(2026-08-04 개정): 모달 X 헤더 = Tool Bar 인스턴스(View=modal). raw close
            # 버튼 잔존(btn/close, ic_close 류 FRAME)은 헤더 미교체 신호 → FAIL.
            if t == 'FRAME' and ';' not in node_id and name in ('btn/close', 'btn_close', 'ic_close') \
                    and not themed and not dark_screen:
                bad_paint.append((disp, t, 'raw-modal-header',
                                  ['모달/시트 헤더는 Tool Bar(View=modal) 인스턴스로 교체']))
            # 🔴 Status/Tool Bar ABSOLUTE 금지 (2026-08-24 사용자: "왜 ignore autolayout 시킨거야?
            # 개발단에선 그렇게 안되있는데") — 시스템 바는 flow 상단 자식이 정본(규칙 8-C).
            # ABSOLUTE 는 진짜 오버레이(FAB/토스트/딤/하단 핀 CTA/HomeIndicator)만 허용.
            for _c in (n.get('children') or []):
                _cn = _c.get('name') or ''
                if _c.get('layoutPositioning') == 'ABSOLUTE' and _cn not in allow \
                        and ('Status Bar' in _cn or 'Tool Bar' in _cn or _cn.strip() == 'Navigation'):
                    bad_paint.append((f"{_cn} <{_c.get('id')}>", _c.get('type') or '', 'bar-absolute-positioning',
                                      ['Status/Tool Bar 는 flow 상단 자식(개발 구현 동일) — ABSOLUTE 금지(8-C)']))
            # 🔴 TEXT 가로 FILL 의무 (2026-08-24 사용자: "텍스트 필드 width 는 특별한 경우 아니면
            # 기본 fill + parent frame 역시 fill") — VERTICAL 스택 안 TEXT 가 HUG 면 FAIL.
            # 예외: HUG 컨테이너(칩/pill/그리드 셀) 안 라벨 · HORIZONTAL 행 나란한 세그먼트 · allow.
            if ';' not in node_id and n.get('layoutMode') == 'VERTICAL' \
                    and n.get('layoutSizingHorizontal') != 'HUG' and name not in allow:
                for _c in (n.get('children') or []):
                    if _c.get('type') == 'TEXT' and _c.get('layoutSizingHorizontal') == 'HUG' \
                            and _c.get('layoutPositioning') != 'ABSOLUTE' \
                            and _c.get('visible') is not False \
                            and (_c.get('name') or '') not in allow:
                        bad_paint.append((f"{_c.get('name') or ''} <{_c.get('id')}>", 'TEXT', 'text-not-fill',
                                          [f"부모 {name!r}(VERTICAL) 안 TEXT 가 HUG — 가로 FILL 필수(규칙 8, 부모 랩도 FILL)"]))
        if is_dict:
            if n.get('type') != 'INSTANCE':
                for c in n.get('children', []) or []:
                    if ';' not in (c.get('id') or ''):
                        walk(c, d + 1, n, themed)
        else:
            for c in n.get('children', []) or []:
                walk(c['id'], d + 1, n, themed)

    _tree = L.fetch_tree(root, max_depth=10)

    # 다크 시스템 바 화면(이미지 뷰어 등 — bars fill 다크) 사전 판정: DS 바는 라이트 전용이라
    # raw 보존이 정본 → appbar-legacy-name/raw-modal-header 면제 (2026-08-24 실측)
    _rw = (_tree or {}).get('width') or 0
    _rh = (_tree or {}).get('height') or 0

    def _detect_dark(n):
        nm = (n.get('name') or '').lower()
        _dark_fill = False
        for f in (n.get('fills') or []):
            if isinstance(f, dict) and f.get('type') == 'SOLID' and f.get('visible') is not False:
                c = f.get('color') or {}
                # 반투명 딤은 다크 화면이 아님 — 실효 불투명 ≥0.9 만 (2026-08-24)
                if max(c.get(k, 0) for k in 'rgb') < 0.35 \
                        and f.get('opacity', 1) * c.get('a', 1) >= 0.9:
                    _dark_fill = True
        # ① 다크 raw bars(스왑 전) ② 화면급 다크 면(이미지 뷰어 검정 배경 — bars 가 DS 로
        #    교체된 뒤에도 다크 화면으로 인식되도록, 2026-08-24)
        if _dark_fill and nm in ('bars', 'status bar', 'statusbar') and round(n.get('height') or 0) <= 70:
            return True
        if _dark_fill and _rw and _rh and (n.get('width') or 0) >= _rw * 0.9 \
                and (n.get('height') or 0) >= _rh * 0.6:
            return True
        if n.get('type') != 'INSTANCE':
            for c in n.get('children') or []:
                if _detect_dark(c):
                    return True
        return False
    dark_screen = bool(_tree) and _detect_dark(_tree)

    walk(_tree if _tree else root)

    # 규칙 1 강령: Status Bar 한 화면 1개 + 최상단 (2026-08-24 사용자 룰)
    if len(sb_nodes) > 1:
        _keep = min(sb_nodes, key=lambda s: (s[0] if s[0] is not None else 9e9))
        for s in sb_nodes:
            if s[1] != _keep[1]:
                bad_paint.append((s[2], 'FRAME', 'status-bar-duplicate',
                                  ['Status Bar 는 한 화면 1개(규칙 1) — 중복 삭제 필요'
                                   ' (enforce_single_status_bar)']))
    if sb_nodes and _tree:
        _ry = (_tree.get('absoluteBoundingBox') or {}).get('y')
        _top = min(sb_nodes, key=lambda s: (s[0] if s[0] is not None else 9e9))
        if _ry is not None and _top[0] is not None and (_top[0] - _ry) > 2:
            bad_paint.append((_top[2], 'FRAME', 'status-bar-not-top',
                              [f'Status Bar 가 최상단이 아님 (y offset {round(_top[0] - _ry)}) — 규칙 1']))
    # 🔴 화면 최소 높이 852 (2026-08-13 사용자: "화면높이의 최소 사이즈는 852야!") —
    # root 가 화면 프레임(폭 393±1)인데 h<852 면 FAIL. 섹션/컴포넌트 단품(폭≠393)은 제외.
    bad_size = []
    rn = _tree if _tree else (call('get_node_info', {'nodeId': root}) or {})
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
    if allow_candidates:
        print(f'  → allow 후보(에셋 색 의심 — 스냅 금지): --allow "{",".join(sorted(allow_candidates))}"')
    return 1


if __name__ == '__main__':
    sys.exit(main())
