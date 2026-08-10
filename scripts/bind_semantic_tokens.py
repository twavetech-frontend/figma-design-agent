#!/usr/bin/env python3
"""in-place 시맨틱 토큰 바인딩 (레포 영구판 — 스크래치패드 소실 재발 방지, 2026-08-10).
색(최근접 시맨틱) + spacing/radius(fc live) + 텍스트 스타일(스냅 매칭).
사용: bind_inplace.py <rootId>"""
import sys, json, collections
sys.path.insert(0, '/Users/julee/imin/figma-design-agent/scripts')
import figma_mcp_client as fc

ROOT = sys.argv[1]
fc.ensure_session()
def call(t, a, **kw):
    return fc.parse_content(fc.call_tool(t, a, **kw)).get('json')

def to_hex(c):
    return '#{:02x}{:02x}{:02x}'.format(round(c.get('r',0)*255), round(c.get('g',0)*255), round(c.get('b',0)*255))

KM = json.load(open('/Users/julee/imin/figma-design-agent/ds/VARIABLE_KEY_MAP.json'))
def full_name(suffix):
    for k in KM:
        if k.endswith('/' + suffix) or k == suffix:
            return k
    return None

# 시맨틱 CANON (이 세션 실측 hex → 토큰 suffix), 클래스별
CANON = {
    'text': {'#2f3943': 'text-primary', '#6f7e8d': 'text-secondary', '#8896a4': 'text-tertiary',
             '#b3bdc7': 'text-placeholder', '#7700ff': 'text-brand-primary',
             '#df1634': 'text-error-primary', '#3bbf2e': 'text-success-primary'},
    'bg':   {'#ffffff': 'bg-primary', '#f3f5f7': 'bg-secondary', '#f4ecff': 'bg-brand-primary'},
    'border': {'#dce0e5': 'border-primary', '#eceef1': 'border-secondary'},
    'fg':   {'#2f3943': 'fg-primary', '#9aa6b3': 'fg-tertiary'},
}
def rgb(h):
    return (int(h[1:3],16), int(h[3:5],16), int(h[5:7],16))
def pick(h, cls):
    table = CANON.get(cls) or {}
    if h in table:
        return table[h], 'exact'
    r0, g0, b0 = rgb(h)
    best, bd = None, 1e9
    for hh, name in table.items():
        r1, g1, b1 = rgb(hh)
        d = (r0-r1)**2 + (g0-g1)**2 + (b0-b1)**2
        if d < bd:
            bd, best = d, name
    return best, f'near({int(bd**0.5)})'

stats = collections.Counter()

def bind_paint(nid, slot, i, col, cls, inst):
    tgt = pick(to_hex(col), cls)[0]
    fn = full_name(tgt)
    if not fn:
        stats['키맵 없음'] += 1; return
    setter = 'set_fill_color' if slot == 'fill' else 'set_stroke_color'
    ar = {'nodeId': nid, 'r': col.get('r',0), 'g': col.get('g',0), 'b': col.get('b',0)}
    ab = {'nodeId': nid, 'bindings': {f'{slot}s/{i}': fn}}
    if inst:
        ar['_allowComponentColor'] = True; ab['_allowComponentColor'] = True
    try:
        call(setter, ar)
        call('set_bound_variables', ab)
        chk = (call('get_bound_variables', {'nodeId': nid}) or {}).get('boundVariables') or {}
        arr = chk.get(f'{slot}s') or []
        if i < len(arr) and arr[i]:
            stats['색 바인딩'] += 1
        else:
            stats['실패'] += 1
    except Exception:
        stats['실패'] += 1

def cls_of(node_type, slot):
    if slot == 'stroke':
        return 'border'
    return 'text' if node_type == 'TEXT' else 'bg'

def walk(nid, inst=False, d=0):
    if d > 8:
        return
    n = call('get_node_info', {'nodeId': nid}) or {}
    t = n.get('type')
    is_inst = inst or (t == 'INSTANCE')
    if t in ('FRAME', 'TEXT', 'RECTANGLE', 'ELLIPSE', 'VECTOR') and not is_inst:
        bv = (call('get_bound_variables', {'nodeId': n['id']}) or {}).get('boundVariables') or {}
        for slot in ('fill', 'stroke'):
            paints = n.get(f'{slot}s') or []
            vis = [(i, p) for i, p in enumerate(paints)
                   if isinstance(p, dict) and p.get('type') == 'SOLID' and p.get('visible') is not False]
            if len(vis) != 1:
                continue
            i, p = vis[0]
            col = p.get('color', {})
            if col.get('a', 1) < 0.999 or p.get('opacity', 1) < 0.999:
                stats['알파 유지'] += 1; continue
            arr = bv.get(f'{slot}s') or []
            if i < len(arr) and arr[i]:
                stats['이미 바인딩'] += 1; continue
            h = to_hex(col)
            if h in ('#ffffff', '#000000') and slot == 'fill' and t != 'TEXT':
                # 흰/검 면은 bg-primary만 바인딩(흰), 검정 스킵
                if h == '#000000':
                    continue
            bind_paint(n['id'], slot, i, col, cls_of(t, slot), False)
    for c in n.get('children', []) or []:
        walk(c['id'], is_inst, d + 1)

walk(ROOT)
print('[색]', dict(stats))

fc._bind_spacing_tokens_live(ROOT)
fc._bind_radius_tokens_live(ROOT)

# 텍스트 스타일 (스냅 매칭)
smap = json.load(open('/Users/julee/imin/figma-design-agent/ds/TEXT_STYLE_MAP.json'))
by_key = {}
for e in smap:
    by_key[(e.get('fontSize'), (e.get('style') or '').lower())] = e
SNAP = {11: 12, 13: 12, 15: 14, 17: 16, 18: 16, 22: 24, 26: 24, 28: 24, 30: 32}
sc = call('scan_text_nodes', {'nodeId': ROOT}) or {}
ts = collections.Counter()
for tnode in (sc.get('textNodes') if isinstance(sc, dict) else sc) or []:
    nid = tnode.get('id') or ''
    if ';' in nid:
        continue
    info = call('get_node_info', {'nodeId': nid}) or {}
    if not (info.get('characters') or '').strip():
        continue
    size = info.get('fontSize')
    style = ((info.get('fontName') or {}).get('style') or 'Regular').lower()
    sid = info.get('textStyleId') or ''
    tgt_size = SNAP.get(size, size)
    e = by_key.get((tgt_size, style))
    if not e:
        # weight 폴백: Bold→SemiBold→Medium→Regular 순 근접
        for alt in ('bold', 'semibold', 'medium', 'regular'):
            e = by_key.get((tgt_size, alt))
            if e:
                break
    if not e:
        ts[f'미매칭 {size}px'] += 1; continue
    if sid and e['key'] in sid:
        ts['이미 DS'] += 1; continue
    if tgt_size != size:
        call('set_font_size', {'nodeId': nid, 'fontSize': tgt_size})
        ts[f'스냅 {size}->{tgt_size}'] += 1
    # ⚠️ 파라미터명은 textStyleId, 형식은 "S:{key},{아무값}" — 콤마 뒤가 비면 플러그인
    # 정규식(/^S:([^,]+),(.+)$/)을 못 타 로컬 조회로 떨어져 silent 실패한다 (2026-08-10 회귀).
    call('set_text_style_id', {'nodeId': nid, 'textStyleId': f"S:{e['key']},{nid}"})
    chk = call('get_node_info', {'nodeId': nid}) or {}
    if chk.get('textStyleId'):
        ts['스타일 적용(검증)'] += 1
    else:
        ts['스타일 실패'] += 1
print('[텍스트]', dict(ts))
print('DONE')

print('⚠️ 완료 보고 전: python3 scripts/verify_bindings.py <rootId> 게이트 필수')
