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
- 완료 보고 전: verify_layout + verify_bindings + 1x 원본 나란히 비교
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
        out.append({
            'id': n.get('id'), 'name': n.get('name'), 'type': n.get('type'),
            'x': n.get('x'), 'y': n.get('y'), 'w': n.get('width'), 'h': n.get('height'),
            'fills': fills, 'strokes': strokes, 'paints': paints_n,
            'mixed': n.get('strokeWeight') == 'mixed',
            'deco': n.get('textDecoration') if n.get('type') == 'TEXT' else None,
            'chars': (n.get('characters') or '')[:20] if n.get('type') == 'TEXT' else '',
            'children': len(n.get('children') or []),
        })
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
                call(setter, {'nodeId': gid, 'r': r0[0] / 255, 'g': r0[1] / 255, 'b': r0[2] / 255})
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


def side_by_side(src_png, gen_png, out_png, scale_w=420):
    """1x 원본/생성본 나란히 비교 이미지 생성 (완료 보고 전 필수 확인용)."""
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
