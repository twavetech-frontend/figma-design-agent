#!/usr/bin/env python3
"""빌드된 Figma 화면 → 프론트엔드 개발용 프레임워크 중립 레이아웃 스펙 JSON.

flexbox 기반(direction/gap/padding/justify/align/sizing) 노드 트리로 변환하고,
색상은 DS 토큰명 + hex 값을 함께 담는다. React/RN/Vue 어디서든 매핑 가능.

사용법: python3 scripts/gen_frontend_spec.py <rootNodeId> [출력파일]
"""
import sys
import os
import json
import time

sys.path.insert(0, 'scripts')
import figma_mcp_client as f

# ── DS 토큰 역인덱스 (hex → 시맨틱 토큰 후보 목록) ────────────────
_TOKEN_BY_HEX = None
_STATE_WORDS = ('hover', 'pressed', 'focus', 'disabled', '_alt', 'active')
# 역할별 figmaPath 우선순위 (낮을수록 우선)
_ROLE_PREF = {
    'text': ['colors/text/', 'component colors/utility/', 'colors/foreground/',
             'colors/background/'],
    'background': ['colors/background/', 'component colors/utility/',
                   'colors/foreground/'],
    'border': ['colors/border/', 'colors/background/', 'component colors/utility/'],
}


def token_index():
    global _TOKEN_BY_HEX
    if _TOKEN_BY_HEX is not None:
        return _TOKEN_BY_HEX
    _TOKEN_BY_HEX = {}
    try:
        tm = json.load(open('ds/TOKEN_MAP.json'))
    except Exception:
        return _TOKEN_BY_HEX
    for entry in tm.values():
        if not isinstance(entry, dict) or entry.get('type') != 'COLOR':
            continue
        val = entry.get('value')
        if not isinstance(val, str):
            continue
        val = val.lower().lstrip('#')
        path = entry.get('figmaPath') or ''
        if not val or not path:
            continue
        if len(val) == 8:
            val = val[:6]
        _TOKEN_BY_HEX.setdefault(val, []).append(path)
    return _TOKEN_BY_HEX


def pick_token(hex6, role):
    """hex(6자리)에 대해 역할에 가장 맞는 시맨틱 토큰 단축명을 고른다.

    - hover/pressed 등 state 변형 토큰은 제외
    - 프리미티브(숫자 단축명, 예 '100')만 매칭되면 토큰 없음(None) — hex만 사용
    """
    cands = token_index().get(hex6.lower())
    if not cands:
        return None
    non_state = [p for p in cands if not any(w in p.lower() for w in _STATE_WORDS)]
    pool = non_state or cands
    prefs = _ROLE_PREF.get(role, _ROLE_PREF['background'])

    def score(path):
        p = path.lower()
        rank = next((i for i, pre in enumerate(prefs) if pre in p), len(prefs))
        primitive = path.split('/')[-1].isdigit()
        return (primitive, rank, len(path))

    best = min(pool, key=score)
    short = best.split('/')[-1]
    return None if short.isdigit() else short


def rgba_to_hex(c, opacity=1.0):
    r = round(c.get('r', 0) * 255)
    g = round(c.get('g', 0) * 255)
    b = round(c.get('b', 0) * 255)
    a = c.get('a', opacity)
    hexv = f'#{r:02X}{g:02X}{b:02X}'
    if a is not None and a < 0.999:
        hexv += f'{round(a * 255):02X}'
    return hexv


def color_spec(c, opacity=1.0, role='background', bound=None):
    """RGBA → {token, value}.

    bound: 빌드가 바인딩한 변수의 단축 토큰명(정답). 있으면 그대로 사용.
    없으면 hex 역추적으로 best-effort 매칭. role: text/background/border.
    """
    hexv = rgba_to_hex(c, opacity)
    token = bound or pick_token(hexv[1:7], role)
    return {'token': token, 'value': hexv}


def first_solid(fills):
    if not fills:
        return None
    for fl in fills:
        if fl.get('type') == 'SOLID' and fl.get('visible', True):
            return fl
    return None


# ── 정렬 매핑 ────────────────────────────────────────────────────
_AXIS = {'MIN': 'start', 'CENTER': 'center', 'MAX': 'end',
         'SPACE_BETWEEN': 'space-between', 'SPACE_AROUND': 'space-around',
         'BASELINE': 'baseline'}


def fetch(node_id):
    c = f.call_tool('get_node_info', {'nodeId': node_id})
    for it in c:
        if it.get('type') == 'text':
            t = it['text']
            try:
                return json.loads(t[t.index('{'):])
            except Exception:
                pass
    return None


CONTAINER = ('FRAME', 'GROUP', 'COMPONENT', 'COMPONENT_SET', 'INSTANCE', 'SECTION')


def bound_tokens(node_id):
    """노드에 바인딩된 변수의 단축 토큰명을 {fill, stroke}로 반환 (빌드 바인딩 = 정답)."""
    out = {}
    for it in f.call_tool('get_bound_variables', {'nodeId': node_id}):
        if it.get('type') != 'text':
            continue
        t = it['text']
        try:
            d = json.loads(t[t.index('{'):])
        except Exception:
            continue
        bv = d.get('boundVariables') or {}
        for key, field in (('fills', 'fill'), ('strokes', 'stroke')):
            arr = bv.get(key)
            if isinstance(arr, list) and arr and isinstance(arr[0], dict) \
                    and arr[0].get('name'):
                out[field] = arr[0]['name'].split('/')[-1]
    return out


def deep_fetch(node, seen):
    """get_node_info 깊이 제한에 잘린 컨테이너를 재귀 재조회 + 바인딩 변수 첨부."""
    nid = node.get('id')
    if node.get('children') is None and node.get('type') in CONTAINER \
            and nid and nid not in seen:
        seen.add(nid)
        full = fetch(nid)
        if full:
            node = full
    nid = node.get('id')
    if nid:
        node['_bv'] = bound_tokens(nid)
    for i, ch in enumerate(node.get('children', []) or []):
        node['children'][i] = deep_fetch(ch, seen)
    return node


# ── 노드 → 프론트엔드 스펙 변환 ──────────────────────────────────
def to_spec(n):
    t = n.get('type', 'FRAME')
    spec = {
        'type': {'TEXT': 'text', 'VECTOR': 'icon', 'INSTANCE': 'instance'}.get(t, 'frame'),
        'name': n.get('name'),
    }
    w, h = n.get('width'), n.get('height')
    if w is not None and h is not None:
        spec['size'] = {'width': round(w), 'height': round(h)}

    # 절대 배치 (Tab Bar 등)
    if n.get('layoutPositioning') == 'ABSOLUTE':
        spec['position'] = {'mode': 'absolute',
                            'x': round(n.get('x', 0)), 'y': round(n.get('y', 0))}

    # 레이아웃 (auto-layout)
    mode = n.get('layoutMode')
    if mode and mode != 'NONE':
        layout = {'direction': 'row' if mode == 'HORIZONTAL' else 'column',
                  'gap': n.get('itemSpacing', 0),
                  'padding': [n.get('paddingTop', 0), n.get('paddingRight', 0),
                              n.get('paddingBottom', 0), n.get('paddingLeft', 0)]}
        if n.get('primaryAxisAlignItems'):
            layout['justify'] = _AXIS.get(n['primaryAxisAlignItems'], 'start')
        if n.get('counterAxisAlignItems'):
            layout['align'] = _AXIS.get(n['counterAxisAlignItems'], 'start')
        layout['sizingHorizontal'] = (n.get('layoutSizingHorizontal') or 'FIXED').lower()
        layout['sizingVertical'] = (n.get('layoutSizingVertical') or 'FIXED').lower()
        if n.get('clipsContent'):
            layout['clipContent'] = True
        spec['layout'] = layout

    # 스타일
    style = {}
    bv = n.get('_bv') or {}
    bg = first_solid(n.get('fills'))
    if bg:
        style['background'] = color_spec(bg['color'], bg.get('opacity', 1),
                                         'background', bv.get('fill'))
    stroke = first_solid(n.get('strokes'))
    if stroke:
        style['border'] = {'width': n.get('strokeWeight', 1),
                           'color': color_spec(stroke['color'], stroke.get('opacity', 1),
                                               'border', bv.get('stroke')),
                           'align': (n.get('strokeAlign') or 'INSIDE').lower()}
    cr = n.get('cornerRadius')
    if isinstance(cr, (int, float)) and cr:
        style['borderRadius'] = cr
    elif n.get('topLeftRadius'):
        style['borderRadius'] = [n.get('topLeftRadius', 0), n.get('topRightRadius', 0),
                                 n.get('bottomRightRadius', 0), n.get('bottomLeftRadius', 0)]
    effects = n.get('effects') or []
    shadows = []
    for e in effects:
        if e.get('type') == 'DROP_SHADOW' and e.get('visible', True):
            shadows.append({
                'x': e.get('offset', {}).get('x', 0),
                'y': e.get('offset', {}).get('y', 0),
                'blur': e.get('radius', 0), 'spread': e.get('spread', 0),
                'color': rgba_to_hex(e.get('color', {}), e.get('color', {}).get('a', 1)),
            })
    if shadows:
        style['shadow'] = shadows
    if n.get('opacity') is not None and n['opacity'] < 1:
        style['opacity'] = n['opacity']
    if style:
        spec['style'] = style

    # 텍스트
    if t == 'TEXT':
        text = {'content': n.get('characters', '')}
        if n.get('fontSize'):
            text['fontSize'] = n['fontSize']
        fn = n.get('fontName') or {}
        if fn.get('family'):
            text['fontFamily'] = fn['family']
        if isinstance(n.get('fontWeight'), (int, float)):
            text['fontWeight'] = n['fontWeight']
        elif fn.get('style'):
            text['fontWeight'] = fn['style']
        if n.get('textAlignHorizontal'):
            text['align'] = n['textAlignHorizontal'].lower()
        lh = n.get('lineHeight')
        if isinstance(lh, dict) and lh.get('value'):
            text['lineHeight'] = lh['value']
        tc = first_solid(n.get('fills'))
        if tc:
            text['color'] = color_spec(tc['color'], tc.get('opacity', 1), 'text',
                                       bv.get('fill'))
            spec.get('style', {}).pop('background', None)
        spec['text'] = text

    kids = n.get('children') or []
    if kids:
        spec['children'] = [to_spec(k) for k in kids]
    return spec


def export_frontend_spec(root_id, out=None):
    """빌드된 화면(root_id)을 프론트엔드 레이아웃 스펙 JSON으로 저장하고 경로를 반환.

    out 미지정 시 json/<화면이름>_<날짜>_<시간>.json 으로 저장.
    """
    f.ensure_session()
    root = fetch(root_id)
    if not root:
        raise ValueError(f'node not found: {root_id}')
    root = deep_fetch(root, set())
    if not out:
        screen_name = (root.get('name') or 'screen').strip().replace(' ', '_')
        stamp = time.strftime('%Y%m%d_%H%M%S')
        os.makedirs('json', exist_ok=True)
        out = os.path.join('json', f'{screen_name}_{stamp}.json')
    spec = {
        'schema': 'imin-frontend-layout-spec/v1',
        'description': 'Framework-neutral layout spec. colors = {token, value}; '
                       'layout = flexbox(direction/gap/padding/justify/align/sizing).',
        'screen': to_spec(root),
    }
    json.dump(spec, open(out, 'w'), ensure_ascii=False, indent=2)
    return out


def main():
    if len(sys.argv) < 2:
        print('usage: gen_frontend_spec.py <rootNodeId> [out.json]')
        sys.exit(1)
    out = export_frontend_spec(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print('exported:', out)


if __name__ == '__main__':
    main()
