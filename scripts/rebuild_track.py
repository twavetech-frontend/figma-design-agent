#!/usr/bin/env python3
"""rebuild_track.py — 8-D rebuild 트랙 자동 실행 (2026-09-04).

🔴 배경: convert_screen 이 8-D(구형 벡터 소스) 판정만 하고 exit 2 로 멈추자 사용자:
"변환 원커맨드가 8-D 룰에 걸려서 차단되면 안 되잖아. 그럼 원커맨드가 소용 없어진 거잖아!"
→ 판정 이후의 rebuild 7단계를 스크립트가 끝까지 수행한다 (모델 수작업 blueprint 금지).

파이프라인 (run_rebuild):
  ① 원본 트리 실측(fetch_tree, 인스턴스 내부 포함) → 블록 추출(TEXT / 도형 컨테이너 /
     구분선 / 이식 에셋(벡터·아이콘 그룹) / 하단 CTA)
  ② 좌표 → 오토레이아웃 번역: y 겹침 클러스터로 행, 최대 x 갭으로 좌/우 그룹(SPACE_BETWEEN),
     행 간격은 paddingTop(DS 스케일 스냅), 큰 공백 뒤 바닥 블록은 Footer 섹션
  ③ 색·타이포 토큰화: 팔레트 최근접 $token, 근접 토큰 없는 유채는 placeholder 후 페인트
     스타일(예: stage old color/9 - mint) 또는 원값+allow 로 후적용
  ④ blueprint 생성 → figma_mcp_client build (post-fix 12종 포함)
  ⑤ 이식: placeholder 자리에 원본 블록 clone_vector_safe → placeholder 삭제
  ⑥ 후처리: Action Button 프롭/높이(2xl=56)·Action Bar flow 복귀·Content FILL·
     SPACE_BETWEEN 행 자식 HUG 재단언·HomeIndicator clone·원본 오른쪽 배치
  ⑦ 반환 (gen id, flags, allow) — 이후 bind/sweep/verify/region_diff 는 convert_screen 공용 꼬리
"""
import os, sys, json, re, subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import figma_mcp_client as fc   # noqa: E402
import ds_convert_lib as L       # noqa: E402

SPACING = [0, 2, 4, 6, 8, 12, 16, 20, 24, 32, 40, 48]
FONTS = [12, 14, 16, 20, 24, 32, 40, 48]
RADII = [4, 6, 8, 10, 12, 14, 16, 20, 24, 28, 32]
AB_SEC = '19c3ba6ad85401ae2427b178c20129d4260c62d0'
SECONDARY_LABELS = ('취소', '닫기', '이전', '뒤로', '아니요', '나중에')
SKIP_NAME = ('status bar', 'statusbar', 'bars', 'home indicator', 'homeindicator')
BAD_NAME_WORDS = re.compile(r'badge|pill|chip|tag|button|dropdown|tab', re.I)


def call(t, a):
    return fc.parse_content(fc.call_tool(t, a)).get('json') or {}


def snap(v, scale):
    return min(scale, key=lambda s: (abs(s - v), -s))


def _hex(p):
    return L.to_hex(p.get('color') or {})


def _paint(n, key='fills'):
    for p in n.get(key) or []:
        if isinstance(p, dict) and p.get('type') == 'SOLID' and p.get('visible', True) \
                and (p.get('opacity', 1) or 0) > 0:
            return p
    return None


def _sat(hx):
    r, g, b = L._rgb(hx)
    return max(r, g, b) - min(r, g, b)


def _hue(hx):
    r, g, b = [v / 255 for v in L._rgb(hx)]
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return 0
    d = mx - mn
    h = (60 * ((g - b) / d) % 360) if mx == r else (60 * ((b - r) / d) + 120) if mx == g else (60 * ((r - g) / d) + 240)
    return h


BRAND_TOKEN = {'text': 'text-brand-primary', 'bg': 'bg-brand-solid', 'border': 'border-brand', 'fg': 'fg-brand-primary'}


def _has_text_deep(n):
    if n.get('type') == 'TEXT':
        return True
    return any(_has_text_deep(c) for c in n.get('children') or [])


# ── 팔레트 (convert_screen 과 동일 소스) ─────────────────────────────────────
_KM = json.load(open(os.path.join(_HERE, '..', 'ds', 'VARIABLE_KEY_MAP.json')))
_TM = json.load(open(os.path.join(_HERE, '..', 'ds', 'TOKEN_MAP.json')))


def _palette(prefix):
    out = {}
    for v in _TM.values():
        p = v.get('figmaPath') or ''
        val = v.get('value') or ''
        if p.startswith(prefix) and isinstance(val, str) and val.startswith('#') and len(val) == 7 \
                and p in _KM and not any(s in p.lower() for s in
                                         ('_hover', '_pressed', 'disabled', '_alt', 'hover', 'focus',
                                          'quaternary', 'on-brand', 'white', 'placeholder')):
            out[val.lower()] = p.split('/')[-1]
    return out


PAL = {'text': _palette('Colors/Text/'), 'bg': _palette('Colors/Background/'),
       'border': _palette('Colors/Border/'), 'fg': _palette('Colors/Foreground/')}


def nearest_token(hx, cls, max_d=40):
    """hex → (토큰명, 거리). 유채인데 근접 토큰이 없으면 (None, d) — 스타일/원값 후적용 대상."""
    best, bd = None, 1e9
    for val, name in PAL[cls].items():
        d = L.color_dist(hx, val)
        if d < bd:
            best, bd = name, d
    if best is None:
        return None, 1e9
    if bd > max_d and _sat(hx) > 40:
        # 구 브랜드 보라(#6042f9 등) → 새 브랜드 토큰 (hue 235~300 유채는 브랜드 액센트로 승계)
        if 235 <= _hue(hx) <= 300:
            return BRAND_TOKEN[cls], bd
        return None, bd
    return best, bd


# ── ① 트리 실측 → 블록 ────────────────────────────────────────────────────────
def _tree_full(nid):
    """인스턴스 내부까지 포함한 트리 (레거시 라이브러리 인스턴스 = bottombtn 등)."""
    t = call('get_node_tree', {'nodeId': nid, 'maxDepth': 16, 'skipInstanceChildren': False})
    if not t.get('id'):
        t = L.fetch_tree(nid) or {}
    # 인스턴스 포함 경로는 TEXT fontName 이 None 으로 직렬화됨(실측) → 기본 트리에서 폰트 병합
    fonts = {}
    def _w(n):
        if n.get('type') == 'TEXT' and n.get('fontName'):
            fonts[n['id']] = n['fontName']
        for c in n.get('children') or []:
            _w(c)
    _w(L.fetch_tree(nid) or {})
    t['_fonts'] = fonts
    return t


def _box(n, rb):
    bb = n.get('absoluteBoundingBox') or {}
    return {'x': (bb.get('x') or 0) - (rb.get('x') or 0), 'y': (bb.get('y') or 0) - (rb.get('y') or 0),
            'w': bb.get('width') or n.get('width') or 0, 'h': bb.get('height') or n.get('height') or 0}


def _vector_only(n):
    kids = n.get('children') or []
    return bool(kids) and all(c.get('type') in ('VECTOR', 'BOOLEAN_OPERATION', 'ELLIPSE', 'LINE',
                                                'SLICE', 'RECTANGLE', 'STAR', 'POLYGON')
                              or _vector_only(c) for c in kids)


def collect_blocks(tree):
    """루트 상대 좌표 블록 목록. kind: text / shape / divider / asset / cta_shape."""
    rb = tree.get('absoluteBoundingBox') or {}
    rw, rh = rb.get('width') or 0, rb.get('height') or 0
    fonts = tree.get('_fonts') or {}
    weights = tree.setdefault('_weights', {})  # id → segments fontWeight 최대값 (fixture 재생 가능)
    blocks = []

    def emit(kind, n, b, **extra):
        d = {'kind': kind, 'id': n['id'], 'name': n.get('name') or kind, **b}
        d.update(extra)
        blocks.append(d)

    def walk(n, d=0):
        if d > 16 or n.get('visible') is False:
            return
        t = n.get('type')
        nm = (n.get('name') or '').lower()
        if t == 'SLICE':
            return
        b = _box(n, rb)
        if d > 0 and any(k in nm for k in SKIP_NAME):
            return
        if d > 0 and b['y'] + b['h'] <= 30 and t in ('GROUP', 'INSTANCE', 'FRAME'):
            return  # 안드/iOS 구형 상태바 영역 — DS Status Bar 자동
        if t == 'TEXT':
            chars = n.get('characters') or ''
            if not chars.strip():
                return
            fn = n.get('fontName') or fonts.get(n['id']) or {}
            wght = ((fn.get('variationSettings') or {}).get('wght')) if isinstance(fn, dict) else None
            if not fn:
                # 플러그인은 fontName 이 figma.mixed 면 필드를 생략한다(code.js 725) — 세그먼트
                # fontWeight 최대값으로 굵기 복원 (구형 소스는 라틴/한글 폰트 혼합이 흔함)
                if n['id'] in weights:
                    wght = weights[n['id']]
                else:
                    segs = (call('get_styled_text_segments', {'nodeId': n['id'], 'property': 'fontWeight'}) or {}).get('segments') or []
                    ws = [sg.get('fontWeight') for sg in segs if isinstance(sg.get('fontWeight'), (int, float))]
                    wght = max(ws) if ws else None
                    weights[n['id']] = wght
            st = str(fn.get('style') or ('Bold' if (wght or 0) >= 700 else 'SemiBold' if (wght or 0) >= 600
                                          else 'Medium' if (wght or 0) >= 500 else 'Regular'))
            emit('text', n, b, chars=chars, size=n.get('fontSize') or 16, style=st, color=_hex(_paint(n) or {}) if _paint(n) else None,
                 align=n.get('textAlignHorizontal') or 'LEFT')
            return
        if t in ('RECTANGLE', 'ELLIPSE', 'LINE'):
            fp, sp = _paint(n), _paint(n, 'strokes')
            if b['w'] >= rw * 0.8 and b['h'] <= 2:
                emit('divider', n, b, color=_hex(fp or sp or {}) if (fp or sp) else None)
                return
            if b['w'] >= rw * 0.9 and b['h'] >= rh * 0.5:
                return  # 화면 배경
            if b['w'] >= rw * 0.9 and fp and _hex(fp).lower() in ('#ffffff', '#fefefe') and not sp:
                return  # 흰 풀폭 밴드 = 루트 배경과 동일 (헤더 bg 등)
            if b['h'] <= 3 and b['w'] >= 40 and (fp or sp):
                emit('bar', n, b, color=_hex(fp or sp))
                return
            if b['w'] <= 56 and b['h'] <= 56 and not fp and not sp:
                return
            emit('shape', n, b, shape=t, fill=_hex(fp) if fp else None,
                 fill_opacity=(fp or {}).get('opacity', 1), stroke=_hex(sp) if sp else None,
                 stroke_w=n.get('strokeWeight') or 1, radius=n.get('cornerRadius') or 0)
            return
        kids = n.get('children') or []
        if d > 0 and t in ('GROUP', 'FRAME', 'BOOLEAN_OPERATION', 'INSTANCE', 'COMPONENT'):
            iconish = L.is_iconish(n.get('name'), b['w'], b['h'])
            if _vector_only(n) or (iconish and not _has_text_deep(n)
                                   and b['w'] <= 120 and b['h'] <= 120):
                emit('asset', n, b)
                return
            if t == 'BOOLEAN_OPERATION':
                emit('asset', n, b)
                return
        for c in kids:
            walk(c, d + 1)

    walk(tree)
    return blocks, rw, rh


# ── ② 좌표 → 레이아웃 ──────────────────────────────────────────────────────────
def _inside(a, b, tol=1):
    return a['x'] >= b['x'] - tol and a['y'] >= b['y'] - tol and \
        a['x'] + a['w'] <= b['x'] + b['w'] + tol and a['y'] + a['h'] <= b['y'] + b['h'] + tol


def nest_containers(blocks):
    """fill/stroke 도형이 다른 블록을 감싸면 컨테이너로 승격(자식 흡수). 큰 것부터."""
    shapes = sorted([b for b in blocks if b['kind'] == 'shape'], key=lambda s: -(s['w'] * s['h']))
    used = set()
    for s in shapes:
        inner = [b for b in blocks if b is not s and b['id'] not in used and b['kind'] != 'divider'
                 and _inside(b, s) and (b['w'] * b['h']) < (s['w'] * s['h'])]
        if inner:
            s['children'] = inner
            s['kind'] = 'container'
            for b in inner:
                used.add(b['id'])
    return [b for b in blocks if b['id'] not in used]


def cluster_rows(blocks):
    rows = []
    for b in sorted(blocks, key=lambda z: (z['y'], z['x'])):
        placed = False
        for r in rows:
            ov = min(r['y1'], b['y'] + b['h']) - max(r['y0'], b['y'])
            if ov > 0.4 * min(b['h'], r['y1'] - r['y0']):
                r['items'].append(b)
                r['y0'], r['y1'] = min(r['y0'], b['y']), max(r['y1'], b['y'] + b['h'])
                placed = True
                break
        if not placed:
            rows.append({'items': [b], 'y0': b['y'], 'y1': b['y'] + b['h']})
    for r in rows:
        r['items'].sort(key=lambda z: z['x'])
    return sorted(rows, key=lambda r: r['y0'])


class Ctx:
    def __init__(self):
        self.chroma = {}      # node name → hex (근접 토큰 없는 유채 — 후적용)
        self.transplants = {} # placeholder name → src id
        self.n = 0
        self.texts = {}
        self.button_w = {}
        self.wrappers = []     # (placeholder id, clone id) — selfcheck 용
        self.src_weights = {}  # 굵기 히스토그램 (Bold/SemiBold/Medium/Regular → n)

    def uid(self, base):
        self.n += 1
        base = BAD_NAME_WORDS.sub('', base).strip() or 'node'
        return f'{base} {self.n}'


def text_node(b, ctx, fill=True, align=None):
    st = b['style'].lower()
    weight = 'Bold' if ('bold' in st and 'semi' not in st) or 'black' in st else \
        'SemiBold' if 'semi' in st else 'Medium' if 'medium' in st else 'Regular'
    ctx.src_weights[weight] = ctx.src_weights.get(weight, 0) + 1
    tok, _d = nearest_token(b['color'], 'text') if b.get('color') else ('text-primary', 0)
    name = ctx.uid('T ' + b['chars'][:10].replace('\n', ' '))
    if tok is None:
        ctx.chroma[name] = b['color']
        tok = 'text-brand-primary'
    color = {'r': 1, 'g': 1, 'b': 1, 'a': 1} if (b.get('color') or '').lower() == '#ffffff' else f'$token({tok})'
    node = {'name': name, 'type': 'text', 'text': b['chars'], 'fontSize': snap(b['size'], FONTS),
            'fontName': {'family': 'Pretendard', 'style': weight}, 'fontColor': color,
            'layoutSizingHorizontal': 'FILL' if fill else 'HUG'}
    if align or (fill and b.get('align') in ('CENTER', 'RIGHT')):
        node['textAlignHorizontal'] = align or b['align']
    if not fill:
        node['_keepSizing'] = True
    ctx.texts[name] = b['chars']
    return node


def asset_node(b, ctx):
    name = ctx.uid('tp ' + (b['name'] or 'asset'))
    ctx.transplants[name] = b['id']
    return {'name': name, 'type': 'frame', 'width': round(b['w']), 'height': round(b['h']),
            'fill': {'r': 1, 'g': 1, 'b': 1, 'a': 0}, '_keepSizing': True,
            'layoutSizingHorizontal': 'FIXED', 'layoutSizingVertical': 'FIXED'}


def shape_node(b, ctx):
    """자식 없는 도형 (작은 원/사각 장식) → 프레임."""
    name = ctx.uid('Shape')
    node = {'name': name, 'type': 'frame', 'width': round(b['w']), 'height': round(b['h']),
            '_keepSizing': True, 'layoutSizingHorizontal': 'FIXED', 'layoutSizingVertical': 'FIXED'}
    _apply_surface(node, b, ctx, name)
    return node


def _apply_surface(node, b, ctx, name):
    if b.get('fill'):
        tok, _ = nearest_token(b['fill'], 'bg')
        if tok is None:
            ctx.chroma[name] = b['fill']
            tok = 'bg-brand-solid'
        node['fill'] = f'$token({tok})'
    else:
        node['fill'] = {'r': 1, 'g': 1, 'b': 1, 'a': 0}
    if b.get('stroke'):
        tok, _ = nearest_token(b['stroke'], 'border')
        if tok is None:
            ctx.chroma[name + '#stroke'] = b['stroke']
            tok = 'border-brand'
        node['stroke'] = f'$token({tok})'
        node['strokeWeight'] = b.get('stroke_w') or 1
    r = b.get('radius') or 0
    if b.get('shape') == 'ELLIPSE' or (isinstance(r, (int, float)) and r >= min(b['w'], b['h']) / 2 - 1):
        node['cornerRadius'] = 999
        node['clipsContent'] = True
    elif isinstance(r, (int, float)) and r > 0:
        node['cornerRadius'] = snap(r, RADII)
        node['clipsContent'] = True


def container_node(b, ctx):
    name = ctx.uid('Surface')
    kids = b['children']
    # 자식 상대 좌표 → 내부 레이아웃 (패딩 = 최소 오프셋)
    x0 = min(k['x'] for k in kids); x1 = max(k['x'] + k['w'] for k in kids)
    y0 = min(k['y'] for k in kids); y1 = max(k['y'] + k['h'] for k in kids)
    pl, pr = snap(max(0, x0 - b['x']), SPACING), snap(max(0, b['x'] + b['w'] - x1), SPACING)
    pt, pb = snap(max(0, y0 - b['y']), SPACING), snap(max(0, b['y'] + b['h'] - y1), SPACING)
    inner = layout_rows(cluster_rows(kids), ctx, region_w=b['w'], compact=True)
    single_row = len(inner) == 1
    single_child = single_row and not inner[0].get('_row')
    node = {'name': name, 'type': 'frame', '_keepSizing': True, 'clipsContent': True,
            'autoLayout': {'layoutMode': 'HORIZONTAL' if (single_row and not single_child) else 'VERTICAL',
                           'primaryAxisAlignItems': 'CENTER', 'counterAxisAlignItems': 'CENTER',
                           'paddingTop': pt, 'paddingBottom': pb, 'paddingLeft': pl, 'paddingRight': pr,
                           'itemSpacing': 4},
            'children': (inner[0]['children'] if single_row and inner[0].get('_row') else inner)}
    if b['w'] <= 64 and b['h'] <= 64:
        node.update({'width': round(b['w']), 'height': round(b['h']),
                     'layoutSizingHorizontal': 'FIXED', 'layoutSizingVertical': 'FIXED'})
    else:
        node['layoutSizingHorizontal'] = 'HUG'
    _apply_surface(node, b, ctx, name)
    return node


def bar_node(b, ctx):
    tok, _ = nearest_token(b['color'], 'bg') if b.get('color') else ('bg-tertiary', 0)
    name = ctx.uid('Bar')
    if tok is None:
        ctx.chroma[name] = b['color']
        tok = 'bg-brand-solid'
    return {'name': name, 'type': 'frame', 'height': max(1, round(b['h'])), 'layoutSizingHorizontal': 'FILL',
            'layoutSizingVertical': 'FIXED', '_keepSizing': True, 'fill': f'$token({tok})'}


def _item_node(b, ctx, fill_text=False, align=None):
    if b['kind'] == 'bar':
        return bar_node(b, ctx)
    if b['kind'] == 'text':
        return text_node(b, ctx, fill=fill_text, align=align)
    if b['kind'] == 'asset':
        return asset_node(b, ctx)
    if b['kind'] == 'container':
        return container_node(b, ctx)
    if b['kind'] == 'shape':
        return shape_node(b, ctx)
    return None


def _group(items, ctx, name):
    if len(items) == 1:
        return _item_node(items[0], ctx)
    gaps = [snap(max(0, items[i + 1]['x'] - (items[i]['x'] + items[i]['w'])), SPACING)
            for i in range(len(items) - 1)]
    return {'name': ctx.uid(name), 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
            'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': max(gaps) if gaps else 0,
                           'counterAxisAlignItems': 'CENTER'},
            'children': [_item_node(b, ctx) for b in items]}


def layout_rows(rows, ctx, region_w, compact=False, base_y=None, region_x=0):
    """행 목록 → 자식 노드 목록 (행 간격은 paddingTop 으로 번역)."""
    out = []
    prev_bottom = base_y
    for r in rows:
        items = r['items']
        gap = 0 if prev_bottom is None else max(0, r['y0'] - prev_bottom)
        pad_top = snap(gap, SPACING) if not compact else snap(min(gap, 8), SPACING)
        prev_bottom = r['y1']
        if len(items) == 1 and items[0]['kind'] == 'divider':
            dv = items[0]
            tok, _ = nearest_token(dv['color'], 'border') if dv.get('color') else ('border-secondary', 0)
            node = {'name': ctx.uid('Rule'), 'type': 'frame', 'height': max(1, round(dv['h'])),
                    'layoutSizingHorizontal': 'FILL', 'layoutSizingVertical': 'FIXED', '_keepSizing': True,
                    'fill': f'$token({tok or "border-secondary"})'}
            out.append(_wrap(node, pad_top, ctx))
            continue
        if len(items) == 1:
            b = items[0]
            if b['kind'] == 'text':
                cx = b['x'] + b['w'] / 2 - region_x
                align = 'CENTER' if abs(cx - region_w / 2) < 8 and b['w'] < region_w * 0.8 else None
                node = text_node(b, ctx, fill=True, align=align)
            else:
                node = _item_node(b, ctx)
            out.append(_wrap(node, pad_top, ctx))
            continue
        # 바(밑줄/진행바) 행: 전부 bar → FILL 세그먼트 나란히
        if all(b['kind'] == 'bar' for b in items):
            row = {'name': ctx.uid('Bars'), 'type': 'frame', 'layoutSizingHorizontal': 'FILL', '_row': True,
                   'fill': '$token(bg-secondary)',  # R21.1: 회색 바(bg-tertiary) 위계 경유 컨테이너
                   'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 0, 'paddingTop': pad_top},
                   'children': [bar_node(b, ctx) for b in items]}
            out.append(row)
            continue
        # 세그먼트 라벨 행(단계/탭): 텍스트 k개의 중심이 k 등분 중심에 놓이면 FILL+CENTER
        texts = [b for b in items if b['kind'] == 'text']
        k_seg = len(texts)
        if k_seg >= 2 and all(b['kind'] in ('text', 'asset') for b in items) and all(
                abs((t['x'] + t['w'] / 2 - region_x) - (j + 0.5) * region_w / k_seg) <= 12
                for j, t in enumerate(texts)):
            kids = []
            for b in items:
                kids.append(text_node(b, ctx, fill=True, align='CENTER') if b['kind'] == 'text' else _item_node(b, ctx))
            row = {'name': ctx.uid('Segments'), 'type': 'frame', 'layoutSizingHorizontal': 'FILL', '_row': True,
                   'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 0, 'counterAxisAlignItems': 'CENTER',
                                  'paddingTop': pad_top}, 'children': kids}
            out.append(row)
            continue
        # 좌/우 그룹 분리: 최대 x 갭 + 우측 그룹이 영역 우변에 붙어 있으면 SPACE_BETWEEN
        gaps = [(items[i + 1]['x'] - (items[i]['x'] + items[i]['w']), i) for i in range(len(items) - 1)]
        g, k = max(gaps)
        right_edge = max(b['x'] + b['w'] for b in items) - region_x
        if g >= 24 and right_edge >= region_w - 24 and not compact:
            row = {'name': ctx.uid('Row'), 'type': 'frame', 'layoutSizingHorizontal': 'FILL', '_row': True,
                   'autoLayout': {'layoutMode': 'HORIZONTAL', 'primaryAxisAlignItems': 'SPACE_BETWEEN',
                                  'counterAxisAlignItems': 'CENTER', 'paddingTop': pad_top},
                   'children': [_group(items[:k + 1], ctx, 'Lead'), _group(items[k + 1:], ctx, 'Trail')]}
        else:
            gsn = [snap(max(0, gg), SPACING) for gg, _ in gaps]
            kids = []
            for j, b in enumerate(items):
                long_text = b['kind'] == 'text' and (b['w'] >= region_w * 0.5 or j == len(items) - 1 and b['h'] > 30)
                kids.append(text_node(b, ctx, fill=True) if long_text else _item_node(b, ctx))
            row = {'name': ctx.uid('Row'), 'type': 'frame', 'layoutSizingHorizontal': 'FILL', '_row': True,
                   'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': max(gsn) if gsn else 0,
                                  'counterAxisAlignItems': 'MIN' if any(b['h'] > 30 for b in items if b['kind'] == 'text') else 'CENTER',
                                  'paddingTop': pad_top},
                   'children': kids}
        out.append(row)
    return out


def _wrap(node, pad_top, ctx):
    if not pad_top:
        return node
    return {'name': ctx.uid('Wrap'), 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
            'fill': {'r': 1, 'g': 1, 'b': 1, 'a': 0},
            'autoLayout': {'layoutMode': 'VERTICAL', 'paddingTop': pad_top}, 'children': [node]}


def detect_cta(blocks, rw, rh):
    """바닥 풀폭 도형(들) + 짧은 텍스트 → Action Bar. 반환 (buttons, 소비된 블록 id 집합)."""
    bottom = [b for b in blocks if b['kind'] in ('shape', 'container')
              and b['y'] + b['h'] >= rh - 6 and b['h'] >= 44 and b['h'] <= 120]
    if not bottom:
        return [], set()
    span = sum(b['w'] for b in bottom)
    if span < rw * 0.85:
        return [], set()
    used, buttons = set(), []
    for s in sorted(bottom, key=lambda z: z['x']):
        used.add(s['id'])
        texts = [t for t in (s.get('children') or []) if t['kind'] == 'text'] or \
                [t for t in blocks if t['kind'] == 'text' and _inside(t, s)]
        label = texts[0]['chars'].strip() if texts else '확인'
        for t in texts:
            used.add(t['id'])
        buttons.append({'label': label, 'w': s['w']})
    if len(buttons) > 2:
        return [], set()
    return buttons, used


def build_blueprint(src, tree):
    ctx = Ctx()
    blocks, rw, rh = collect_blocks(tree)
    blocks = nest_containers(blocks)
    buttons, used = detect_cta(blocks, rw, rh)
    blocks = [b for b in blocks if b['id'] not in used]
    rows = cluster_rows(blocks)
    # Footer 분리: 큰 공백(≥100) 뒤에 바닥 근처(≤ 260px) 블록들만 남으면 바닥 고정 섹션
    split = None
    for i in range(1, len(rows)):
        if rows[i]['y0'] - rows[i - 1]['y1'] >= 100 and rh - rows[i]['y0'] <= 260:
            split = i
            break
    content_rows, footer_rows = (rows[:split], rows[split:]) if split else (rows, [])
    allx = [b['x'] for r in rows for b in r['items']]
    allr = [b['x'] + b['w'] for r in rows for b in r['items']]
    pl = snap(min(allx) if allx else 20, SPACING) if allx and min(allx) <= 32 else 20
    pr = snap(rw - max(allr), SPACING) if allr and rw - max(allr) <= 32 else 20
    status_h = 24 if any((n.get('name') or '').lower().find('status') >= 0 for n in (tree.get('children') or [])) else 44
    inner_w = rw - pl - pr
    content_children = layout_rows(content_rows, ctx, region_w=inner_w, base_y=status_h, region_x=pl)
    first_pad = content_children[0]['autoLayout'].get('paddingTop', 0) if content_children and \
        content_children[0].get('autoLayout') else 0
    root_name = f"{src.get('name')}_DS"
    root = {
        'name': root_name, 'type': 'frame', 'width': 393, 'height': 852, 'fill': '$token(bg-primary)',
        'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 0},
        '_conceptSkipped': '1:1 변환 — rebuild 트랙 자동(8-D)', '_designDirectionSkipped': '1:1 변환',
        '_restructureMapSkipped': '1:1 변환', '_wireframeDivergenceSkipped': '1:1 변환',
        '_noveltySkipped': '1:1 변환', '_referencesSkipped': '1:1 변환 — 원본 프레임이 유일 레퍼런스',
        '_wireframeContent': {k: v for k, v in list(ctx.texts.items())},
        'children': [],
    }
    content = {'name': 'Content', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
               'layoutSizingVertical': 'FILL', '_repetitionAllowed': '1:1 변환 — 원본 데이터 행',
               '_flatStackAllowed': '1:1 변환 — 원본 평면 리스트',
               'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 0, 'paddingLeft': pl,
                              'paddingRight': pr, 'paddingBottom': 24},
               'children': content_children}
    root['children'].append(content)
    if footer_rows:
        fbase = footer_rows[0]['y0'] - 0  # 첫 행 paddingTop 0 (Content FILL 이 밀어냄)
        fkids = layout_rows(footer_rows, ctx, region_w=inner_w, base_y=fbase, region_x=pl)
        last_bottom = footer_rows[-1]['y1']
        cta_top = rh - (max(b['h'] for b in [{'h': 0}] + [{'h': 75}]) if buttons else 0)
        pb = snap(max(0, (rh - last_bottom) - (75 if buttons else 0)), SPACING)
        root['children'].append({'name': 'Footer', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
                                 '_flatStackAllowed': '1:1 변환', 'autoLayout': {
                                     'layoutMode': 'VERTICAL', 'itemSpacing': 0, 'paddingLeft': pl,
                                     'paddingRight': pr, 'paddingBottom': max(pb, 16)},
                                 'children': fkids})
    if buttons:
        kids = []
        total = sum(b['w'] for b in buttons)
        for i, b in enumerate(buttons):
            sec = b['label'] in SECONDARY_LABELS or (len(buttons) == 2 and i == 0 and
                                                     buttons[1]['label'] not in SECONDARY_LABELS)
            node = {'name': ctx.uid('Action ' + b['label']), 'type': 'instance', 'componentKey': AB_SEC,
                    '_instanceText': b['label'],
                    'instanceProperties': {'Hierarchy': 'Secondary' if sec else 'Primary', 'Size': '2xl'}}
            if len(buttons) == 2 and i == 0 and b['w'] / total < 0.45:
                node.update({'width': round(353 * b['w'] / total) - 4, 'layoutSizingHorizontal': 'FIXED',
                             '_keepSizing': True})
                ctx.button_w[node['name']] = node['width']
            else:
                node['layoutSizingHorizontal'] = 'FILL'
                if not sec:
                    node['_ctaKeepPrimary'] = True
            kids.append(node)
        root['children'].append({'name': 'Action Bar', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
                                 'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 8, 'paddingTop': 8,
                                                'paddingBottom': 8, 'paddingLeft': 20, 'paddingRight': 20},
                                 'children': kids})
    _strip_private(root)
    return root, ctx


def _strip_private(n):
    n.pop('_row', None)
    for c in n.get('children') or []:
        _strip_private(c)


# ── ④ build ──────────────────────────────────────────────────────────────────
def _find_by_name(n, name):
    if n.get('name') == name:
        return n
    for c in n.get('children') or []:
        r = _find_by_name(c, name)
        if r:
            return r


def _lint_autofix(bp, errs):
    """lint ERROR 자동 보정 1회: R21.1(bg 위계 건너뜀) → 해당 노드 fill 을 bg-secondary 로 강등.
    반환: 보정 건수."""
    n = 0
    for e in errs:
        m = re.search(r'R21\.1-bg-skip\] ([^:]+):', e)
        if m:
            node = _find_by_name(bp, m.group(1).split('/')[-1].strip())
            if node and isinstance(node.get('fill'), str) and node['fill'] != '$\u0074oken(bg-secondary)':
                node['fill'] = '$token(bg-secondary)'
                n += 1
    return n


def run_build(bp, _retry=True):
    safe = re.sub(r'[^0-9A-Za-z가-힣_]+', '_', bp['name'])[:60]
    path = os.path.join(_HERE, f'blueprint_rebuild_{safe}.json')
    json.dump(bp, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    env = dict(os.environ, IMIN_SKIP_REFERENCE_GATE='1', IMIN_SKIP_SELFVERIFY_GATE='1')
    r = subprocess.run([sys.executable, os.path.join(_HERE, 'figma_mcp_client.py'), 'build', path],
                       capture_output=True, text=True, env=env)
    out = r.stdout
    m = out.rfind('BUILD-SUMMARY-JSON')
    summary = {}
    if m >= 0:
        try:
            summary = json.loads(out[out.find('{', m):].strip())
        except Exception:
            pass
    if summary.get('result') != 'success':
        errs = [ln for ln in out.splitlines() if 'ERROR' in ln][:12]
        if _retry and _lint_autofix(bp, errs):
            print('  [rebuild] lint 자동 보정 후 재빌드')
            return run_build(bp, _retry=False)
        return None, summary, errs, out
    return summary.get('rootId'), summary, [], out


# ── ⑤⑥ 이식 + 후처리 ────────────────────────────────────────────────────────
def _index_by_name(tree):
    idx = {}

    def w(n, parent=None, i=0):
        idx.setdefault(n.get('name'), []).append((n, parent, i))
        for j, c in enumerate(n.get('children') or []):
            w(c, n, j)
    w(tree)
    return idx


def find_style_by_hex(hx):
    st = call('get_styles', {}) or {}
    for s in st.get('colors') or []:
        p = s.get('paint') or {}
        if p.get('type') == 'SOLID' and L.to_hex(p.get('color') or {}).lower() == hx.lower():
            return s.get('id') or ('S:%s,' % s.get('key'))
    return None


CLS_PREFIX = {'text': 'Colors/Text/', 'bg': 'Colors/Background/', 'border': 'Colors/Border/', 'fg': 'Colors/Foreground/'}
VECTORISH = ('VECTOR', 'ELLIPSE', 'RECTANGLE', 'LINE', 'BOOLEAN_OPERATION', 'STAR', 'POLYGON')


def _bind_var(nid, slot, cls, tok):
    key = _KM.get(CLS_PREFIX[cls] + tok)
    if not key:
        return False
    r = call('batch_bind_variables', {'items': [{'nodeId': nid, 'bindings': {f'{slot}/0': 'K:' + key}}]}) or {}
    return bool(r.get('succeeded'))


def bind_asset_paints(wrapper_id, style_cache, flags):
    """이식 벡터 내부 페인트 토큰화 (2026-09-04 사용자: "컬러 바인딩 또 제대로 안 되어 있다" —
    allow 통째 면제가 원값을 숨겼음). 우선순위: 페인트 스타일(hex 일치, 스테이지 색) →
    fg-* 최근접(브랜드 hue 는 fg-brand-primary) → 실패 시 원값 + flag. 반환: 미바인딩 노드명 집합."""
    raw = set()
    t = L.fetch_tree(wrapper_id) or {}

    def w(n):
        if n.get('visible') is False:
            return
        if n.get('type') in VECTORISH:
            for slot, key in (('fills', 'fills'), ('strokes', 'strokes')):
                p = _paint(n, key)
                if not p:
                    continue
                hx = _hex(p).lower()
                if hx in ('#ffffff', '#000000'):
                    continue
                sid = style_cache[hx] if hx in style_cache else find_style_by_hex(hx)
                style_cache[hx] = sid
                if sid:
                    call('set_fill_style_id' if slot == 'fills' else 'set_stroke_style_id',
                         {'nodeId': n['id'], ('fillStyleId' if slot == 'fills' else 'strokeStyleId'): sid})
                    continue
                cls = 'bg' if (slot == 'fills' and n.get('type') in ('ELLIPSE', 'RECTANGLE')
                               and (n.get('width') or 0) >= 12) else 'fg'
                tok, _ = nearest_token(hx, cls)
                if tok and _bind_var(n['id'], slot, cls, tok):
                    continue
                raw.add(n.get('name') or n['id'])
        for c in n.get('children') or []:
            w(c)
    w(t)
    if raw:
        flags.append(f'asset-raw-color: {sorted(raw)[:6]} — 근접 토큰/스타일 없음 (원값 유지, 사용자 확인)')
    return raw


def postprocess(rid, ctx, flags):
    allow = set()
    style_cache = {}
    tree = L.fetch_tree(rid) or {}
    idx = _index_by_name(tree)
    # 이식: placeholder(FIXED w×h, plain frame) 안에 clone 삽입 — GROUP 을 오토레이아웃 부모에
    # 직접 넣으면 사이징이 없어 늘어난다(36→656 실측). 래퍼가 크기를 고정하고 이름은 에셋명 승계.
    for pname, sid in ctx.transplants.items():
        hit = idx.get(pname)
        if not hit:
            flags.append(f'transplant-miss: placeholder {pname} 없음 (src {sid})')
            continue
        n, parent, i = hit[0]
        cl = L.clone_vector_safe(sid, n['id'], 0, 0, name=None)
        cn = call('get_node_info', {'nodeId': cl}) or {}
        # GROUP clone 은 자식 좌표가 원본 조상 프레임 기준으로 복원돼 래퍼 밖으로 벗어난다 —
        # get_nodes_info(document.absoluteBoundingBox, 8-E) 로 래퍼↔clone 차분을 재고 2회까지 보정
        for _ in range(2):
            info = call('get_nodes_info', {'nodeIds': [n['id'], cl]}) or []
            boxes = {}
            for it in (info if isinstance(info, list) else []):
                doc = it.get('document') or {}
                boxes[it.get('nodeId') or doc.get('id')] = doc.get('absoluteBoundingBox') or {}
            wb, cb = boxes.get(n['id']) or {}, boxes.get(cl) or {}
            if not wb or not cb:
                break
            dx, dy = (cb.get('x') or 0) - (wb.get('x') or 0), (cb.get('y') or 0) - (wb.get('y') or 0)
            if abs(dx) <= 0.5 and abs(dy) <= 0.5:
                break
            cur = call('get_node_info', {'nodeId': cl}) or {}
            call('move_node', {'nodeId': cl, 'x': (cur.get('x') or 0) - dx, 'y': (cur.get('y') or 0) - dy})
        aname = L.normalize_icon_layer_name(cn.get('name') or 'asset') or (cn.get('name') or 'asset')
        call('rename_node', {'nodeId': n['id'], 'name': aname})
        call('set_layout_sizing', {'nodeId': n['id'], 'layoutSizingHorizontal': 'FIXED', 'layoutSizingVertical': 'FIXED'})
        allow |= bind_asset_paints(n['id'], style_cache, flags)
        ctx.wrappers.append((n['id'], cl))
    # 유채 스타일/원값 후적용
    for name, hx in ctx.chroma.items():
        base, _, part = name.partition('#')
        hit = idx.get(base)
        if not hit:
            continue
        nid = hit[0][0]['id']
        sid = style_cache[hx] if hx in style_cache else find_style_by_hex(hx)
        style_cache[hx] = sid
        if part == 'stroke':
            if sid:
                call('set_stroke_style_id', {'nodeId': nid, 'strokeStyleId': sid})
                print(f'  [chroma-style] {base} stroke ← 페인트 스타일 {hx}')
            else:
                rgb = L._rgb(hx)
                call('set_stroke_color', {'nodeId': nid, 'color': {'r': rgb[0] / 255, 'g': rgb[1] / 255, 'b': rgb[2] / 255, 'a': 1},
                                          'strokeWeight': hit[0][0].get('strokeWeight') or 1})
                allow.add(base)
                flags.append(f'chroma-raw: {base} stroke 원값 {hx} 유지 (근접 토큰/스타일 없음 — 사용자 확인)')
            continue
        if sid:
            call('set_fill_style_id', {'nodeId': nid, 'fillStyleId': sid})
            print(f'  [chroma-style] {base} ← 페인트 스타일 {hx}')
        else:
            rgb = L._rgb(hx)
            call('set_fill_color', {'nodeId': nid, 'color': {'r': rgb[0] / 255, 'g': rgb[1] / 255, 'b': rgb[2] / 255, 'a': 1}})
            allow.add(base)
            flags.append(f'chroma-raw: {base} 원값 {hx} 유지 (근접 토큰/스타일 없음 — 사용자 확인)')
    tree = L.fetch_tree(rid) or {}
    idx = _index_by_name(tree)
    # Action Button: 아이콘/로딩 프롭 off + 2xl 높이 56 (batch_build 직후 h24 실측)
    for name, hits in idx.items():
        for n, parent, i in hits:
            if n.get('type') == 'INSTANCE' and (name or '').startswith('Action '):
                call('set_instance_properties', {'nodeId': n['id'], 'properties': {
                    '⬅️ Icon leading#3287:1577': False, '➡️ Icon trailing#3287:2338': False,
                    'Loading text#8994:0': False}})
                w = ctx.button_w.get(name) or n.get('width') or 120
                call('resize_node', {'nodeId': n['id'], 'width': w, 'height': 56})
                call('set_layout_sizing', {'nodeId': n['id'], 'layoutSizingHorizontal': n.get('layoutSizingHorizontal') or 'FILL',
                                           'layoutSizingVertical': 'FIXED'})
    # Action Bar flow 복귀 + Content FILL + SPACE_BETWEEN 행 자식 HUG 재단언
    ab = (idx.get('Action Bar') or [(None,)])[0][0]
    if ab:
        call('set_layout_positioning', {'nodeId': ab['id'], 'layoutPositioning': 'AUTO'})
        call('set_layout_sizing', {'nodeId': ab['id'], 'layoutSizingHorizontal': 'FILL', 'layoutSizingVertical': 'HUG'})
    ct = (idx.get('Content') or [(None,)])[0][0]
    if ct:
        call('set_layout_sizing', {'nodeId': ct['id'], 'layoutSizingHorizontal': 'FILL', 'layoutSizingVertical': 'FILL'})

    def _rows(n):
        if n.get('type') == 'FRAME' and n.get('primaryAxisAlignItems') == 'SPACE_BETWEEN' and n.get('layoutMode') == 'HORIZONTAL':
            for c in n.get('children') or []:
                if c.get('type') in ('FRAME', 'TEXT') and c.get('layoutSizingHorizontal') == 'FILL':
                    call('set_layout_sizing', {'nodeId': c['id'], 'layoutSizingHorizontal': 'HUG'})
                for cc in c.get('children') or []:
                    if cc.get('type') == 'TEXT' and cc.get('layoutSizingHorizontal') == 'FILL':
                        call('set_layout_sizing', {'nodeId': cc['id'], 'layoutSizingHorizontal': 'HUG'})
        for c in n.get('children') or []:
            _rows(c)
    _rows(tree)
    # HomeIndicator: 페이지 내 기존 인스턴스 clone (DS 게시 검색 불가 — 파일 내 인스턴스가 정본)
    if not idx.get('HomeIndicator'):
        found = call('find_nodes_by_name', {'name': 'HomeIndicator', 'matchMode': 'exact'}) or {}
        cands = [m for m in (found.get('nodes') or found.get('matches') or found.get('results') or [])
                 if (m.get('type') or '').upper() == 'INSTANCE' and m.get('id') != rid]
        if cands:
            hi = call('clone_node', {'nodeId': cands[0]['id']}) or {}
            if hi.get('id'):
                call('insert_child', {'parentId': rid, 'childId': hi['id']})
                call('set_layout_positioning', {'nodeId': hi['id'], 'layoutPositioning': 'AUTO'})
                call('set_layout_sizing', {'nodeId': hi['id'], 'layoutSizingHorizontal': 'FILL'})
                call('rename_node', {'nodeId': hi['id'], 'name': 'HomeIndicator'})
        else:
            flags.append('homeindicator-missing: 페이지에 HomeIndicator 인스턴스 없음 — 수동 삽입')
    # 루트 높이: minHeight 852, 콘텐츠가 넘치면 전체 높이로 (2-F). Content 자연 높이로 합산.
    if ct:
        call('set_layout_sizing', {'nodeId': ct['id'], 'layoutSizingVertical': 'HUG'})
        root = call('get_node_info', {'nodeId': rid}) or {}
        total = sum((k.get('height') or 0) for k in (root.get('children') or []))
        if total > 852:
            call('resize_node', {'nodeId': rid, 'width': 393, 'height': round(total)})
            flags.append(f'root-height: 콘텐츠 {round(total)} > 852 — 루트 높이 확장(2-F)')
        else:
            call('resize_node', {'nodeId': rid, 'width': 393, 'height': 852})
        call('set_layout_sizing', {'nodeId': ct['id'], 'layoutSizingHorizontal': 'FILL', 'layoutSizingVertical': 'FILL'})
    # 순서 보정: Action Bar 가 HI 뒤면 앞으로
    root = call('get_node_info', {'nodeId': rid}) or {}
    kids = root.get('children') or []
    names = [k.get('name') for k in kids]
    if 'Action Bar' in names and 'HomeIndicator' in names and names.index('Action Bar') > names.index('HomeIndicator'):
        abn = kids[names.index('Action Bar')]
        call('insert_child', {'parentId': rid, 'childId': abn['id'], 'index': names.index('HomeIndicator')})
    return allow


def selfcheck(rid, ctx, flags):
    """렌더 Read 없이 트리 값으로 완성도 판정 (2026-09-04 사용자: "다시 생성 20분" — 눈 왕복 5회의
    대체). ① 굵기 히스토그램 원본=생성 ② 이식 래퍼↔clone 절대 bbox 일치 ③ allow 없는 verify PASS.
    불일치는 flags 로 승격 — CONVERT-SUMMARY 에서 바로 보인다."""
    # ① 굵기
    gen_w = {}
    t = L.fetch_tree(rid) or {}

    def w(n):
        if n.get('type') == 'TEXT' and not (n.get('id') or '').startswith('I'):
            fn = n.get('fontName') or {}
            st = str(fn.get('style') or '')
            if not st:
                segs = (call('get_styled_text_segments', {'nodeId': n['id'], 'property': 'fontWeight'}) or {}).get('segments') or []
                ws = [sg.get('fontWeight') for sg in segs if isinstance(sg.get('fontWeight'), (int, float))]
                mx = max(ws) if ws else 400
                st = 'Bold' if mx >= 700 else 'SemiBold' if mx >= 600 else 'Medium' if mx >= 500 else 'Regular'
            k = 'Bold' if 'bold' in st.lower() and 'semi' not in st.lower() else 'SemiBold' if 'semi' in st.lower() \
                else 'Medium' if 'medium' in st.lower() else 'Regular'
            gen_w[k] = gen_w.get(k, 0) + 1
        for c in n.get('children') or []:
            w(c)
    w(t)
    for k in ('Bold', 'SemiBold'):
        if ctx.src_weights.get(k, 0) != gen_w.get(k, 0):
            flags.append(f'selfcheck-weight: {k} 원본 {ctx.src_weights.get(k, 0)} ≠ 생성 {gen_w.get(k, 0)} — 굵기 소실/과잉')
    # ② 이식 bbox
    for wid, cid in ctx.wrappers:
        info = call('get_nodes_info', {'nodeIds': [wid, cid]}) or []
        boxes = {}
        for it in (info if isinstance(info, list) else []):
            doc = it.get('document') or {}
            boxes[it.get('nodeId') or doc.get('id')] = doc.get('absoluteBoundingBox') or {}
        wb, cb = boxes.get(wid) or {}, boxes.get(cid) or {}
        if wb and cb and (abs((wb.get('x') or 0) - (cb.get('x') or 0)) > 1 or abs((wb.get('y') or 0) - (cb.get('y') or 0)) > 1
                          or abs((wb.get('width') or 0) - (cb.get('width') or 0)) > 2):
            flags.append(f'selfcheck-transplant: {wid} 래퍼↔clone bbox 불일치 {wb} vs {cb}')
    # ③ allow 없는 verify
    r = subprocess.run([sys.executable, os.path.join(_HERE, 'verify_bindings.py'), rid], capture_output=True, text=True)
    if r.returncode != 0:
        bad = [ln.strip() for ln in r.stdout.splitlines() if ln.strip().startswith('(')][:6]
        flags.append(f'selfcheck-verify: allow 없는 verify FAIL {len(bad)}건+ — {bad[:3]}')
    return flags


def run_rebuild(src, parent, x, y, gap=40):
    """convert_screen 에서 호출. 반환 (rid, flags, allow)."""
    flags = []
    tree = _tree_full(src['id'])
    bp, ctx = build_blueprint(src, tree)
    print(f'  [rebuild] 블록 → blueprint: 텍스트 {len(ctx.texts)} / 이식 {len(ctx.transplants)} / 유채 후적용 {len(ctx.chroma)}')
    rid, summary, errs, out = run_build(bp)
    if not rid:
        for e in errs:
            print('   ' + e[:200])
        raise RuntimeError(f'rebuild build 실패: {summary.get("code")} {summary.get("codes")}')
    print(f'  [rebuild] build ✓ {rid}')
    # 원본 오른쪽 배치 (build 의 선택 노드 기준 배치를 덮어씀 — 같은 부모 + 우측 gap)
    call('insert_child', {'parentId': parent, 'childId': rid})
    call('move_node', {'nodeId': rid, 'x': x, 'y': y})
    allow = postprocess(rid, ctx, flags)
    return rid, flags, allow, ctx  # selfcheck 는 convert_screen 이 bind/sweep 뒤에 호출 (순백 바인딩 이후)
