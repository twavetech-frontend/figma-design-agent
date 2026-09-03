#!/usr/bin/env python3
"""벡터 프레임 → DS 변환 공용 라이브러리 (2026-08-11 신설).

배경: 화면마다 즉석 휴리스틱으로 변환하다 6종 사고가 반복됨 —
① 일괄 스트레치로 절대배치 내부 어긋남 ② auto layout 전환 시 x마진 소실/과대
③ wrap 그리드 FILL 붕괴 ④ FRAME resize 시 constraints 스트레치
⑤ GROUP resize 미동작(자식 위치 안 따라옴) ⑥ bind 파괴 스냅 + 이름 매칭 오복원.

이 모듈은 변환 규칙을 코드로 고정한다:
- snapshot(root): 전 노드 실측(JSON) — 판단·검증의 단일 기준
- clone_with_map(src, parent): 클론 + 원본↔클론 id 1:1 매핑(구조 병렬 walk)
- restore_by_map(map, thresh): bind 후 파괴 스냅을 id 기반으로 원값 복원
  (이름 매칭 금지 — 동명 노드 오복원 사고의 근본 차단)
- widen_children_393(node, snap): 요소 타입별 393 변환 결정 트리
- verify_layout(gen_root, snap): 좌표/크기 자동 대조 리포트 (FAIL 시 완료 보고 금지)

원칙:
- GROUP 은 리사이즈하지 않는다 (내부 개별 보정 → 원크기 중앙 → 최후 2x export 이미지)
- 간격은 padding/itemSpacing 만 (spacer 프레임 금지)
- 말단 카드까지 오토레이아웃 재구성이 기본, 클론 보존은 벡터 아트만
- 🔴 화면 root 는 폭 393 + **최소 높이 852** (원본이 더 작아도 852 로 확장 — normalize_screen 필수,
  2026-08-13 사용자 룰. verify 의 화면 크기 게이트가 h<852 를 FAIL 로 차단)
- 완료 보고 전: verify_layout + verify_bindings + **region_compare 전 구역 Read**
  (전체 축소 side_by_side 만으로 판정 금지 — 2026-08-12 사용자: "이런 거 너가 찾아내야")
- 실측값을 blueprint 로 옮길 때 실측 y/gap ↔ 작성 padding 을 표로 대조 (실측해 놓고
  손감으로 다른 값을 쓰는 것이 카드 gap 회귀의 원인)
- snapshot 의 FLAG_MIXED_SEGMENTS(세그 혼합 텍스트) / FLAG_FRAME_STROKE(프레임 보더) 는
  반드시 후속 실측(get_styled_text_segments / 사이드·두께)으로 해소한 뒤 작성
"""
import json
import sys

sys.path.insert(0, '/Users/julee/imin/figma-design-agent/scripts')
import figma_mcp_client as fc


def call(t, a, **kw):
    return fc.parse_content(fc.call_tool(t, a, **kw)).get('json')


def to_hex(c):
    return '#{:02x}{:02x}{:02x}'.format(
        round(c.get('r', 0) * 255), round(c.get('g', 0) * 255), round(c.get('b', 0) * 255))


def _rgb(h):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


def color_dist(a, b):
    r0, g0, b0 = _rgb(a); r1, g1, b1 = _rgb(b)
    return ((r0 - r1) ** 2 + (g0 - g1) ** 2 + (b0 - b1) ** 2) ** 0.5


def snapshot(root_id, max_depth=12):
    """전 노드 실측 스냅샷: [{id,name,type,x,y,w,h,fills,strokes,deco,chars,mixed}] (walk 순서)."""
    out = []

    def walk(nid, d=0):
        if d > max_depth:
            return
        n = call('get_node_info', {'nodeId': nid}) or {}
        fills = [to_hex(f.get('color', {})) for f in n.get('fills') or []
                 if isinstance(f, dict) and f.get('type') == 'SOLID' and f.get('visible') is not False]
        strokes = [to_hex(s.get('color', {})) for s in n.get('strokes') or []
                   if isinstance(s, dict) and s.get('type') == 'SOLID']
        paints_n = len([f for f in n.get('fills') or [] if isinstance(f, dict) and f.get('visible') is not False])
        rec = {
            'id': n.get('id'), 'name': n.get('name'), 'type': n.get('type'),
            'x': n.get('x'), 'y': n.get('y'), 'w': n.get('width'), 'h': n.get('height'),
            'fills': fills, 'strokes': strokes, 'paints': paints_n,
            'mixed': n.get('strokeWeight') == 'mixed',
            'deco': n.get('textDecoration') if n.get('type') == 'TEXT' else None,
            'chars': (n.get('characters') or '')[:20] if n.get('type') == 'TEXT' else '',
            'children': len(n.get('children') or []),
        }
        # 🔴 해석 필수 신호 (2026-08-12 커뮤니티 화면 회귀 4건의 근본 원인 — 실측에 찍혔는데 지나침):
        # TEXT 인데 fills 가 빈 배열 = styled segments 혼합(#EVENT 인디고류) → get_styled_text_segments 로 세그별 색 실측 후 세그 분리 재구성.
        if n.get('type') == 'TEXT' and not fills and paints_n == 0:
            rec['FLAG_MIXED_SEGMENTS'] = True
        # 컨테이너 FRAME 에 stroke = 액티브 밑줄/보더 표현일 수 있음(탭 Button 하단 #000 보더) → 사이드·두께 확인 의무.
        if n.get('type') == 'FRAME' and strokes:
            rec['FLAG_FRAME_STROKE'] = strokes
        out.append(rec)
        for c in n.get('children', []) or []:
            walk(c['id'], d + 1)

    walk(root_id)
    return out


def clone_with_map(src_id, parent_id, x, y, name=None):
    """클론 + 구조 병렬 walk 로 원본↔클론 id 1:1 매핑 dict 반환."""
    cl = call('clone_node', {'nodeId': src_id})
    rid = cl['id']
    call('insert_child', {'childId': rid, 'parentId': parent_id})
    call('move_node', {'nodeId': rid, 'x': x, 'y': y})
    if name:
        call('rename_node', {'nodeId': rid, 'name': name})
    mapping = {}

    def walk(sid, gid, d=0):
        if d > 12:
            return
        mapping[gid] = sid
        s = call('get_node_info', {'nodeId': sid}) or {}
        g = call('get_node_info', {'nodeId': gid}) or {}
        for a, b in zip(s.get('children', []) or [], g.get('children', []) or []):
            walk(a['id'], b['id'], d + 1)

    walk(src_id, rid)
    return rid, mapping


def restore_by_map(mapping, thresh=40, skip_black=True):
    """bind 후 파괴 스냅 원값 복원 — id 기반(이름 매칭 금지). ΔRGB > thresh 만 복원.
    멀티페인트/mixed 는 건드리지 않음. 복원 건수 반환."""
    fixed = 0
    for gid, sid in mapping.items():
        g = call('get_node_info', {'nodeId': gid}) or {}
        s = call('get_node_info', {'nodeId': sid}) or {}
        if not g.get('id') or not s.get('id'):
            continue
        for slot, setter in [('fills', 'set_fill_color'), ('strokes', 'set_stroke_color')]:
            if slot == 'strokes' and g.get('strokeWeight') == 'mixed':
                continue
            gp = [p for p in g.get(slot) or []
                  if isinstance(p, dict) and p.get('type') == 'SOLID' and p.get('visible') is not False]
            sp = [p for p in s.get(slot) or []
                  if isinstance(p, dict) and p.get('type') == 'SOLID' and p.get('visible') is not False]
            gall = [p for p in g.get(slot) or [] if isinstance(p, dict) and p.get('visible') is not False]
            if len(gp) != 1 or len(sp) != 1 or len(gall) != 1:
                continue
            gh = to_hex(gp[0].get('color', {})); sh = to_hex(sp[0].get('color', {}))
            if gh == sh or (skip_black and sh == '#000000'):
                continue
            if color_dist(gh, sh) > thresh:
                r0 = _rgb(sh)
                ar = {'nodeId': gid, 'r': r0[0] / 255, 'g': r0[1] / 255, 'b': r0[2] / 255}
                # 🔴 MCP set_stroke_color 는 strokeWeight 미지정 시 1 로 강제 — 굵은 라디오
                # active 링(sw 5)이 얇아지던 회귀 (2026-08-13). 원본 weight 재단언.
                if slot == 'strokes':
                    ssw = s.get('strokeWeight')
                    if isinstance(ssw, (int, float)) and ssw > 0:
                        ar['strokeWeight'] = ssw
                call(setter, ar)
                fixed += 1
        # 취소선/밑줄 보존
        if g.get('type') == 'TEXT' and s.get('textDecoration') and s.get('textDecoration') != 'NONE' \
                and g.get('textDecoration') != s.get('textDecoration'):
            call('set_text_decoration', {'nodeId': gid, 'textDecoration': s.get('textDecoration')})
    return fixed


def verify_layout(gen_root, snap_by_gen_id, tol=2.0):
    """생성본 좌표를 스냅샷(기대값 dict: gen_id → {x,y,w,h})과 대조. 어긋남 목록 반환."""
    bad = []

    def walk(nid, d=0):
        if d > 12:
            return
        n = call('get_node_info', {'nodeId': nid}) or {}
        exp = snap_by_gen_id.get(n.get('id'))
        if exp:
            for k, cur in (('x', n.get('x')), ('y', n.get('y')), ('w', n.get('width')), ('h', n.get('height'))):
                want = exp.get(k)
                if want is not None and cur is not None and abs(cur - want) > tol:
                    bad.append((n.get('name'), k, round(cur, 1), round(want, 1)))
        for c in n.get('children', []) or []:
            walk(c['id'], d + 1)

    walk(gen_root)
    return bad


def normalize_icon_layer_name(name):
    """레거시 아이콘 레이어명 정규화 (2026-08-24 사용자 룰 0-L-2).

    'ico/empty/chat' → 'ic_empty_chat': ① 선두 'ico' 세그먼트('ico' 바로 뒤가 / _ - 또는
    이름 끝) → 'ic' ② '/' 전부 '_'. 'icon/...' 처럼 ico 뒤에 글자가 이어지는 이름은
    prefix 를 건드리지 않고 슬래시만 정규화한다. 대상 아니면 None."""
    if not name or '/' not in name or not name.lower().startswith('ico'):
        return None
    out = name
    if len(out) == 3 or out[3] in '/_-':
        out = 'ic' + out[3:]
    out = out.replace('/', '_')
    return out if out != name else None


def rename_legacy_icon_layers(root_id):
    """서브트리의 레거시 아이콘 이름(ico/*) 전수 정규화 — 변환 파이프라인 clone 직후 호출.
    인스턴스 내부(0-K)는 제외. 반환: 변경 건수."""
    tree = fetch_tree(root_id)
    jobs = []

    def _walk_t(n):
        nm = n.get('name') or ''
        new = normalize_icon_layer_name(nm)
        if new and ';' not in (n.get('id') or ''):
            jobs.append((n['id'], nm, new))
        if n.get('type') != 'INSTANCE':
            for c in n.get('children') or []:
                if ';' not in (c.get('id') or ''):
                    _walk_t(c)

    if tree:
        _walk_t(tree)
    else:
        # 폴백: 노드 단위 (구버전 플러그인)
        def _deep_r(nid, d=0):
            if d > 10:
                return
            n = call('get_node_info', {'nodeId': nid}) or {}
            nm = n.get('name') or ''
            new = normalize_icon_layer_name(nm)
            if new:
                jobs.append((n['id'], nm, new))
            for c in n.get('children') or []:
                if c.get('type') != 'INSTANCE' and ';' not in (c.get('id') or ''):
                    _deep_r(c['id'], d + 1)
        _deep_r(root_id)
    for nid, old, new in jobs:
        call('rename_node', {'nodeId': nid, 'name': new})
    return len(jobs)


_TREE_OK = None  # None=미확인 / True=지원 / False=미지원(구버전 플러그인)


def fetch_tree(nid, max_depth=25):
    """서브트리 1콜 fetch — get_node_tree (2026-08-24 성능 수리: 노드당 get_node_info
    직렬 왕복이 변환 시간의 대부분이던 병목 제거, 장당 ~70s→~10s 목표).
    구버전 플러그인(명령 미지원)이면 None 반환 — 호출측은 노드 단위 폴백을 유지한다.
    플러그인 재실행으로 활성화. 반환 트리: 노드마다 get_node_info 필드 + boundVariables
    키 요약(dict, 키 존재=바인딩 있음) + absoluteBoundingBox + hasStrikethrough(TEXT).
    인스턴스 내부는 미포함(0-K) — 인스턴스 노드의 children 은 얕은 요약."""
    global _TREE_OK
    if _TREE_OK is False:
        return None
    try:
        t = call('get_node_tree', {'nodeId': nid, 'maxDepth': max_depth})
        if isinstance(t, dict) and t.get('id'):
            if _TREE_OK is None:
                print('  [tree] get_node_tree 1콜 트리 경로 사용')
            _TREE_OK = True
            return t
    except Exception:
        pass
    if _TREE_OK is None:
        print('  [tree] get_node_tree 미지원(플러그인 구버전) — 노드 단위 폴백. '
              'Figma 에서 플러그인 재실행하면 빨라짐')
    _TREE_OK = False
    return None


def enforce_text_fill(root_id):
    """VERTICAL 부모 안 HUG TEXT → 가로 FILL 자동 교정 (규칙 8 — verify `text-not-fill`
    게이트와 짝인 enforcer, 2026-08-24 신설: 빈 상태 문구가 세 번 연속 수동 교정되던 반복 제거).
    예외는 verify 와 동일 — HUG 부모(칩/pill 라벨)·ABSOLUTE·인스턴스 내부. 정렬은 노드
    속성(textAlignHorizontal)이라 FILL 전환으로 변하지 않는다. 반환: 교정 건수."""
    tree = fetch_tree(root_id)
    if not tree:
        return 0
    jobs = []

    def _walk(n):
        if n.get('layoutMode') == 'VERTICAL' and n.get('layoutSizingHorizontal') != 'HUG':
            for c in n.get('children') or []:
                if c.get('type') == 'TEXT' and c.get('layoutSizingHorizontal') == 'HUG' \
                        and c.get('layoutPositioning') != 'ABSOLUTE' \
                        and c.get('visible') is not False and ';' not in (c.get('id') or ''):
                    jobs.append(c['id'])
        if n.get('type') != 'INSTANCE':
            for c in n.get('children') or []:
                if ';' not in (c.get('id') or ''):
                    _walk(c)
    _walk(tree)
    for nid in jobs:
        call('set_layout_sizing', {'nodeId': nid, 'horizontal': 'FILL'})
    if jobs:
        print(f'  [normalize] TEXT 가로 FILL 교정 {len(jobs)}건 (규칙 8 — text-not-fill enforcer)')
    return len(jobs)


def enforce_single_status_bar(root_id):
    """🔴 Status Bar 는 한 화면 최상단에 정확히 1개 (2026-08-24 사용자 룰 — 규칙 1 강령).

    캡처가 배경+오버레이(딤/사이드바)에 각각 bars 를 갖는 중복 구조를 정규화:
    Status Bar 류(이름 bars/status bar, h≤70)는 **화면에서 가장 위(abs y 최소)** 1개만
    남기고 삭제. HomeIndicator 도 같은 원리(최하단, abs y 최대 1개)로 단일화 — 852 확장
    시 오버레이 ABSOLUTE HI 가 화면 중간에 뜨던 실측 결함의 뿌리.
    반환: (sb_removed, hi_removed)."""
    tree = fetch_tree(root_id)
    if not tree:
        return (0, 0)
    root_y = (tree.get('absoluteBoundingBox') or {}).get('y') or 0
    sbs, his = [], []

    def _walk(n):
        nm = (n.get('name') or '').strip().lower()
        ay = ((n.get('absoluteBoundingBox') or {}).get('y') or 0) - root_y
        if nm in ('bars', 'status bar', 'statusbar') and round(n.get('height') or 0) <= 70 \
                and ';' not in (n.get('id') or '') and n.get('visible') is not False:
            sbs.append((ay, n['id']))
        if nm in ('homeindicator', 'home indicator') and ';' not in (n.get('id') or '') \
                and n.get('visible') is not False:
            his.append((ay, n['id']))
        if n.get('type') != 'INSTANCE':
            for c in n.get('children') or []:
                if ';' not in (c.get('id') or ''):
                    _walk(c)
    _walk(tree)

    sb_removed = hi_removed = 0
    if len(sbs) > 1:
        keep = min(sbs)[1]  # 최상단 1개
        for _, nid in sbs:
            if nid != keep:
                call('delete_node', {'nodeId': nid})
                sb_removed += 1
    if len(his) > 1:
        keep = max(his)[1]  # 최하단 1개
        for _, nid in his:
            if nid != keep:
                call('delete_node', {'nodeId': nid})
                hi_removed += 1
    if sb_removed or hi_removed:
        print(f'  [normalize] Status Bar 중복 {sb_removed}건 / HomeIndicator 중복 {hi_removed}건 '
              f'삭제 — 한 화면 1개(규칙 1)')
    return (sb_removed, hi_removed)


def normalize_screen(root_id, width=393, min_height=852):
    """화면 root 표준화 — 변환/클론 파이프라인의 필수 단계 (2026-08-13 사용자 룰:
    "화면높이의 최소 사이즈는 852야!" — 원본이 780 이어도 852 로 확장).
    ① 폭 393 고정 ② h < 852 면 852 로 확장 ③ FIXED 360 잔재 자식 FILL 재단언.
    하단 고정 요소(홈바/CTA/탭바)는 콘텐츠 영역이 FILL 이면 자동으로 바닥 유지 —
    콘텐츠 영역이 FILL 이 아닐 때만 경고를 출력한다(spacer 로 채우지 말 것).
    verify_bindings 의 화면 크기 게이트(w≈393 & h<852 FAIL)와 짝."""
    n = call('get_node_info', {'nodeId': root_id}) or {}
    h = n.get('height') or 0
    call('resize_node', {'nodeId': root_id, 'width': width, 'height': max(h, min_height)})
    has_fill_v = False
    for c in n.get('children', []) or []:
        ci = call('get_node_info', {'nodeId': c['id']}) or {}
        if ci.get('layoutSizingHorizontal') == 'FIXED' and round(ci.get('width') or 0) == 360:
            call('set_layout_sizing', {'nodeId': c['id'], 'layoutSizingHorizontal': 'FILL'})
        if ci.get('layoutSizingVertical') == 'FILL':
            has_fill_v = True
    # 🔴 내부 행의 FIXED 300~360 잔재도 FILL 재단언 (2026-08-13 사용자: "총액 금액들이
    # 오른쪽에 딱 안붙어있다!" — 393 확장 시 우측 정렬 행이 원본 폭으로 굳어 우측 여백 생김).
    # 캐로셀 카드(172) 등 의도 FIXED 는 범위 밖이라 안전.
    def _overflow_shift_row(nn, parent):
        """스와이프/오버플로 상태 행 감지 (2026-08-24 채팅 스와이프 3장 실측):
        HORIZONTAL 부모 안 풀폭(≥350) FIXED 행 + 형제 합폭 > 부모 폭 = 의도된 시프트
        뷰포트(행이 밀려 일부가 화면 밖으로 클립되는 상태). FILL 재맞춤이 이 시프트를
        파괴한다 — 새 화면폭 FIXED 로 확장 + 부모 clipsContent 가 정답."""
        if not parent or parent.get('layoutMode') != 'HORIZONTAL':
            return False
        if round(nn.get('width') or 0) < 350:
            return False
        kids = [k for k in (parent.get('children') or []) if k.get('visible') is not False]
        total = sum((k.get('width') or 0) for k in kids)
        return total > (parent.get('width') or 0) + 4

    def _fix_node(nn, parent):
        """FIXED 300~360 잔재 판정 + 교정 (트리/폴백 공용). nn 은 dict."""
        nid = nn.get('id')
        if nn.get('type') in ('FRAME', 'INSTANCE') and nn.get('layoutSizingHorizontal') == 'FIXED' \
                and 300 <= round(nn.get('width') or 0) <= 360:
            if _overflow_shift_row(nn, parent):
                call('resize_node', {'nodeId': nid, 'width': width,
                                     'height': nn.get('height') or 0})
                call('set_auto_layout', {'nodeId': parent['id'], 'layoutMode': 'HORIZONTAL',
                                         'clipsContent': True})
                print(f'  [normalize] 오버플로 시프트 행 보존: {nid} → {width} FIXED '
                      f'+ 부모 {parent["id"]} clip (FILL 재맞춤 제외)')
            else:
                call('set_layout_sizing', {'nodeId': nid, 'layoutSizingHorizontal': 'FILL'})

    tree = fetch_tree(root_id)
    if tree:
        # 1콜 트리 순회 (INSTANCE 노드 자체는 교정 대상, 내부로는 안 내려감 — 0-K)
        def _walk_t(nn, parent, d=0):
            if d > 9:
                return
            _fix_node(nn, parent)
            if nn.get('type') == 'INSTANCE':
                return
            for c in nn.get('children') or []:
                if ';' not in (c.get('id') or ''):
                    _walk_t(c, nn, d + 1)
        _walk_t(tree, None)
    else:
        # 폴백: 노드 단위 재귀 (구버전 플러그인)
        def _deep(nid, d=0, parent=None):
            if d > 9:
                return
            nn = call('get_node_info', {'nodeId': nid}) or {}
            _fix_node(nn, parent)
            for c in nn.get('children', []) or []:
                if c.get('type') == 'INSTANCE':
                    _fix_node(c, nn)  # 인스턴스 자체 sizing 만 교정, 내부 미진입(0-K)
                else:
                    _deep(c['id'], d + 1, nn)
        _deep(root_id)
    if h < min_height and n.get('layoutMode') in ('VERTICAL',) and not has_fill_v:
        print(f'  ⚠️ [normalize] {root_id}: h {round(h)}→{min_height} 확장했으나 세로 FILL 자식이 없어 '
              f'하단 요소가 위에 붙을 수 있음 — 콘텐츠 영역을 FILL 로 지정할 것 (spacer 금지)')
    n2 = call('get_node_info', {'nodeId': root_id}) or {}
    return n2.get('width'), n2.get('height')


def side_by_side(src_png, gen_png, out_png, scale_w=420):
    """1x 원본/생성본 나란히 비교 이미지 생성 (완료 보고 전 필수 확인용).
    ⚠️ 전체 축소 한 장은 1차 실루엣 확인용일 뿐 — 최종 판정은 region_compare 로 할 것
    (2026-08-12: 축소 대조만 믿고 탭 밑줄/태그 보더/카드 gap/세그 색 4건을 놓침)."""
    from PIL import Image
    a = Image.open(src_png)
    b = Image.open(gen_png)
    H = max(a.size[1], b.size[1]) + 10
    W = a.size[0] + b.size[0] + 20
    canvas = Image.new('RGB', (W, H), (240, 240, 240))
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.size[0] + 20, 0))
    canvas.resize((scale_w, int(H * scale_w / W))).save(out_png)
    return out_png


def region_compare(src_png, gen_png, out_dir, n_regions=5, overlap=0.06):
    """화면을 세로 N구역으로 나눠 원본/생성본을 **동배율(폭 맞춤, 축소 없음)** 나란히 크롭.
    반환된 이미지 전부를 Read 로 눈검사한 뒤에만 완료 보고 — 디테일(밑줄/보더/gap/세그 색)은
    전체 축소본에서 뭉개져 여기서만 보인다. 두 이미지 높이가 달라도 구역 비율로 정렬."""
    import os
    from PIL import Image
    a = Image.open(src_png)
    b = Image.open(gen_png)
    tw = max(a.size[0], b.size[0])
    outs = []
    for i in range(n_regions):
        f0 = max(0.0, i / n_regions - overlap / 2)
        f1 = min(1.0, (i + 1) / n_regions + overlap / 2)
        ca = a.crop((0, int(a.size[1] * f0), a.size[0], int(a.size[1] * f1)))
        cb = b.crop((0, int(b.size[1] * f0), b.size[0], int(b.size[1] * f1)))
        ca = ca.resize((tw, int(ca.size[1] * tw / ca.size[0])))
        cb = cb.resize((tw, int(cb.size[1] * tw / cb.size[0])))
        H = max(ca.size[1], cb.size[1])
        canvas = Image.new('RGB', (tw * 2 + 16, H), (245, 245, 245))
        canvas.paste(ca, (0, 0))
        canvas.paste(cb, (tw + 16, 0))
        p = os.path.join(out_dir, f'region_{i+1}of{n_regions}.png')
        canvas.save(p)
        outs.append(p)
    return outs


# ── 오토레이아웃 조립 헬퍼 (2026-08-24 사용자 지적: plain frame 남발 방지) ──────────
# create_frame 의 layoutMode 파라미터는 플러그인이 조용히 무시한다(2026-08-21 실측).
# 라이브 조립에서 콘텐츠 컨테이너는 반드시 이 헬퍼로 생성할 것 — plain frame 은
# 화면 루트·오버레이 전용만 허용 (verify plain-frame-suspect 게이트가 차단).
def new_auto_frame(call, parent_id, name, layout='VERTICAL', gap=0, pad=None,
                   w=None, h=None, fill_alpha0=True, x=0, y=0, **al_extra):
    """오토레이아웃 프레임 생성 3연타(create→set_auto_layout→sizing)를 원자화.
    pad: int(전방향) 또는 dict(paddingLeft 등). 반환: nodeId."""
    import json as _j
    r = call('create_frame', {'x': x, 'y': y, 'width': w or 100, 'height': h or 40,
                              'name': name, 'parentId': parent_id,
                              'fillColor': {'r': 1, 'g': 1, 'b': 1, 'a': 1}})
    nid = (_j.loads(r[0]['text']) if isinstance(r, list) else r).get('id')
    if fill_alpha0:
        call('set_fill_color', {'nodeId': nid, 'color': {'r': 1, 'g': 1, 'b': 1, 'a': 0}})
    al = {'nodeId': nid, 'layoutMode': layout, 'itemSpacing': gap}
    if isinstance(pad, int):
        al.update({'paddingLeft': pad, 'paddingRight': pad, 'paddingTop': pad, 'paddingBottom': pad})
    elif isinstance(pad, dict):
        al.update(pad)
    al.update(al_extra)
    call('set_auto_layout', al)
    if w and h:
        call('set_layout_sizing', {'nodeId': nid, 'horizontal': 'FIXED', 'vertical': 'FIXED'})
        call('resize_node', {'nodeId': nid, 'width': w, 'height': h})
    else:
        call('set_layout_sizing', {'nodeId': nid, 'horizontal': 'HUG', 'vertical': 'HUG'})
    return nid


# ── 구형(360) 변환 정합 헬퍼 3종 (2026-09-03 스테이지 상세 사고 코드화) ──────────
# 사고: normalize 가 헤더만 393 확장하고 절대배치 본문(게시글/순번/입력바)은 360 잔존
# → 우변 기준 3종 혼재(우측 33px 갭·정렬 뒤죽박죽). GROUP 48개도 게이트 사각지대.
# 아이콘 프레임은 오토레이아웃 전환 절대 금지(사용자 확정 ×2 — 내부 스택 재배열로 파괴됨).

ICONISH_KEYS = ('ic_', 'ico_', 'gift', 'icon', 'daram', 'point', 'profile', 'crown',
                'bubble', 'clap', 'arrow', 'bitmap', 'oval', 'mask')


def is_iconish(name, w=None, h=None):
    """아이콘/그래픽 원자 판정 — 오토레이아웃 전환·정규화 리사이즈 불가침 대상."""
    nm = (name or '').lower()
    if any(k in nm for k in ICONISH_KEYS):
        return True
    if w is not None and h is not None and w <= 56 and h <= 56:
        return True
    return False


def normalize_absolute_360(root_id, width=393, old_width=360):
    """절대배치 서브트리의 360 기준 잔존을 393 으로 일괄 정규화 (검증 규칙 3종):
    ① 풀폭 배경(w≈old_width, x≈0, RECT/FRAME) → width 로 resize
    ② 우측 앵커(우변 old_width-40..old_width-14, x>180) → x += delta (부모 abs 실시간 조회 —
       스냅샷 좌표 오염 함정 방지)
    ③ 좌측 시작 넓은 콘텐츠(x≤180, w≥150, TEXT/RECT/FRAME) → w += delta
    아이콘(is_iconish)은 전부 불가침. 우측 앵커는 통째 이동 후 내부 재귀 중단."""
    delta = width - old_width
    t = fetch_tree(root_id)
    if not t:
        return {}
    rb = t.get('absoluteBoundingBox') or {}
    rx = rb.get('x') or 0
    stats = {'full': 0, 'right': 0, 'widen': 0}

    def walk(n, depth=0):
        nid = n.get('id') or ''
        if nid.startswith('I') or depth > 11:
            return
        nb = n.get('absoluteBoundingBox') or {}
        ax = nb.get('x') or 0
        w0, h0 = nb.get('width') or 0, nb.get('height') or 0
        x0 = ax - rx
        x1 = x0 + w0
        iconish = is_iconish(n.get('name'), w0, h0)
        if depth > 0 and not iconish and not n.get('layoutMode'):
            if old_width - 5 <= w0 <= old_width + 2 and x0 <= 1 \
                    and n.get('type') in ('RECTANGLE', 'FRAME'):
                call('resize_node', {'nodeId': nid, 'width': width, 'height': h0})
                stats['full'] += 1
            elif old_width - 40 <= x1 <= old_width - 13 and x0 > 180 \
                    and n.get('type') in ('FRAME', 'GROUP'):
                # 부모 abs 실시간 조회 후 상대좌표로 이동 (get_node_info x/y 는 None 함정)
                info = call('get_node_info', {'nodeId': nid}) or {}
                pt = call('get_node_info', {'nodeId': info.get('parentId')}) or {}
                pb = pt.get('absoluteBoundingBox') or pt
                pax = pb.get('x') if isinstance(pb, dict) else None
                pay = pb.get('y') if isinstance(pb, dict) else None
                if pax is None:
                    return
                nb2 = (call('get_node_info', {'nodeId': nid}) or {}).get('absoluteBoundingBox') or nb
                call('move_node', {'nodeId': nid,
                                   'x': ((nb2.get('x') or ax) - pax) + delta,
                                   'y': (nb2.get('y') or 0) - pay})
                stats['right'] += 1
                return
            elif x0 <= 180 and w0 >= 150 and old_width - 40 <= x1 <= old_width - 13 \
                    and n.get('type') in ('TEXT', 'RECTANGLE', 'FRAME'):
                call('resize_node', {'nodeId': nid, 'width': w0 + delta, 'height': h0})
                stats['widen'] += 1
        for c in n.get('children') or []:
            if ';' not in (c.get('id') or ''):
                walk(c, depth + 1)

    walk(t)
    if any(stats.values()):
        print(f'  [normalize-360] 절대배치 정규화 — 풀폭 {stats["full"]} / 우측앵커 {stats["right"]} / 확장 {stats["widen"]}')
    return stats


def convert_struct_groups(root_id):
    """구조 GROUP → FRAME 전환 (8-C — 2026-09-03 사용자 확정). 안전 원칙:
    - 벡터-only 그룹·아이콘(is_iconish)은 절대 전환 안 함 (그래픽 원자)
    - 전환은 그룹 하나마다 fresh tree 로 좌표 재조회 (스냅샷 오염 방지)
    - 오토레이아웃 부여는 '명백한 비겹침 스택(자식 2~8, 전 자식 서로 비겹침)'만,
      그 외는 plain FRAME + '(overlay)' 표기 — 자동 스택화 과욕이 2차 피해의 뿌리였다.
    반환: {'frame': n, 'stacked': n, 'overlay': n}"""
    stats = {'frame': 0, 'stacked': 0, 'overlay': 0}

    def find_next_group():
        t = fetch_tree(root_id)
        if not t:
            return None
        found = []

        def w(n, depth=0):
            nid = n.get('id') or ''
            if nid.startswith('I') or depth > 11:
                return
            kids = n.get('children') or []
            if n.get('type') == 'GROUP':
                bb = n.get('absoluteBoundingBox') or {}
                vec_only = all(c.get('type') in ('VECTOR', 'BOOLEAN_OPERATION', 'ELLIPSE',
                                                 'LINE', 'SLICE') for c in kids) if kids else True
                if not vec_only and not is_iconish(n.get('name'), bb.get('width'), bb.get('height')):
                    found.append(n)
                    return  # 바깥 그룹부터 (자식 그룹은 다음 라운드 fresh tree 에서)
            for c in kids:
                if ';' not in (c.get('id') or ''):
                    w(c, depth + 1)

        w(t)
        return found[0] if found else None

    for _ in range(60):  # 무한루프 가드
        g = find_next_group()
        if not g:
            break
        gid = g['id']
        gb = g.get('absoluteBoundingBox') or {}
        gx, gy = gb.get('x') or 0, gb.get('y') or 0
        kids = g.get('children') or []
        boxes = [(c, c.get('absoluteBoundingBox') or {}) for c in kids]
        info = call('get_node_info', {'nodeId': gid}) or {}
        par = info.get('parentId')
        # ⚠️ get_node_info 는 absoluteBoundingBox 를 안 줄 수 있음(x/y None 함정과 짝) —
        # 부모 abs 는 get_nodes_info(document.absoluteBoundingBox)로 (2026-09-03 좌표 폭주 실사고)
        _pn = fc.parse_content(fc.call_tool('get_nodes_info', {'nodeIds': [par]})).get('json') or []
        pb = ((_pn[0].get('document') if _pn else {}) or {}).get('absoluteBoundingBox') or {}
        if pb.get('x') is None:
            print(f'  [group→frame] 부모 abs 미확보 — 스킵 {gid}')
            break
        fr = call('create_frame', {'parentId': par, 'x': gx - (pb.get('x') or 0),
                                   'y': gy - (pb.get('y') or 0),
                                   'width': gb.get('width') or 1, 'height': gb.get('height') or 1,
                                   'name': g.get('name')}) or {}
        fid = fr.get('id')
        if not fid:
            break
        call('set_fill_color', {'nodeId': fid, 'color': {'r': 1, 'g': 1, 'b': 1, 'a': 0}})
        for c, b in boxes:
            call('insert_child', {'parentId': fid, 'childId': c['id'], 'index': 99})
            call('move_node', {'nodeId': c['id'], 'x': (b.get('x') or 0) - gx,
                               'y': (b.get('y') or 0) - gy})
        try:
            call('delete_node', {'nodeId': gid})
        except Exception:
            pass
        stats['frame'] += 1

        def nonoverlap(axis):
            ln = 'height' if axis == 'y' else 'width'
            spans = sorted(((b.get(axis) or 0), (b.get(axis) or 0) + (b.get(ln) or 0))
                           for _, b in boxes)
            return all(spans[i + 1][0] >= spans[i][1] - 1 for i in range(len(spans) - 1))

        if 2 <= len(kids) <= 8 and nonoverlap('y'):
            axis, ln, mode = 'y', 'height', 'VERTICAL'
        elif 2 <= len(kids) <= 8 and nonoverlap('x'):
            axis, ln, mode = 'x', 'width', 'HORIZONTAL'
        else:
            call('rename_node', {'nodeId': fid, 'name': (g.get('name') or '') + ' (overlay)'})
            stats['overlay'] += 1
            continue
        order = sorted(boxes, key=lambda cb: cb[1].get(axis) or 0)
        for i, (c, b) in enumerate(order):
            call('insert_child', {'parentId': fid, 'childId': c['id'], 'index': i})
        gaps = [max(0, (order[i + 1][1].get(axis) or 0) -
                    ((order[i][1].get(axis) or 0) + (order[i][1].get(ln) or 0)))
                for i in range(len(order) - 1)]
        gap = round(sum(gaps) / len(gaps)) if gaps else 0
        call('set_auto_layout', {'nodeId': fid, 'layoutMode': mode, 'itemSpacing': gap})
        stats['stacked'] += 1
    if any(stats.values()):
        print(f'  [group→frame] 구조 GROUP 전환 {stats["frame"]} (스택 {stats["stacked"]} / overlay {stats["overlay"]})')
    return stats
