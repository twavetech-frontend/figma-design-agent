#!/usr/bin/env python3
"""in-place 시맨틱 토큰 바인딩 (레포 영구판 — 스크래치패드 소실 재발 방지, 2026-08-10).
색(최근접 시맨틱) + spacing/radius(fc live) + 텍스트 스타일(스냅 매칭).
사용: CLI `bind_semantic_tokens.py <rootId>` 또는 in-process `import ...; run(rootId)`
(2026-08-24 성능 수리 — 읽기는 get_node_tree 1콜, 쓰기/검증만 개별 콜.
 subprocess 기동+노드당 왕복이 변환 시간의 68% 였던 병목 제거)."""
import sys, json, collections
sys.path.insert(0, '/Users/julee/imin/figma-design-agent/scripts')
import figma_mcp_client as fc
import ds_convert_lib as L  # fetch_tree

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
             '#df1634': 'text-error-primary', '#3bbf2e': 'text-success-primary',
             '#ffffff': 'text-white'},
    'bg':   {'#ffffff': 'bg-primary', '#f3f5f7': 'bg-secondary', '#f4ecff': 'bg-brand-primary'},
    'border': {'#dce0e5': 'border-primary', '#eceef1': 'border-secondary', '#f4ecff': 'bg-brand-primary',
             },
    'fg':   {'#2f3943': 'fg-primary', '#9aa6b3': 'fg-tertiary'},
}
def rgb(h):
    return (int(h[1:3],16), int(h[3:5],16), int(h[5:7],16))
def _chroma(h):
    r, g, b = rgb(h)
    return max(r, g, b) - min(r, g, b)

def pick(h, cls):
    table = CANON.get(cls) or {}
    if h in table:
        return table[h], 'exact'
    r0, g0, b0 = rgb(h)
    src_c = _chroma(h)
    best, bd = None, 1e9
    for hh, name in table.items():
        # 🔴 2026-08-14 사용자 지적(미세 퍼플 3건): 유채 소스(#faf7ff 틴트 등)를 무채 토큰
        # (bg-primary/border-secondary)으로 스냅 금지 — 색상 정보가 뭉개진다.
        if src_c >= 5 and _chroma(hh) < 3:
            continue
        r1, g1, b1 = rgb(hh)
        d = (r0-r1)**2 + (g0-g1)**2 + (b0-b1)**2
        if d < bd:
            bd, best = d, name
    if best is None:
        return None, 'no-chromatic-candidate'
    # 유채→유채 근사는 Δ≤10 만 허용 (#faf7ff→#f4ecff Δ12.7 은 스킵해 원값 유지)
    if src_c >= 5 and bd ** 0.5 > 10:
        return None, f'chromatic-far({int(bd**0.5)})'
    return best, f'near({int(bd**0.5)})'

stats = collections.Counter()

def bind_paint(nid, slot, i, col, cls, inst, stroke_weight=None):
    global stats
    tgt, how = pick(to_hex(col), cls)
    if tgt is None:
        stats[f'유채 스냅 스킵({cls})'] += 1; return
    # 🔴 원거리 근사 스냅 금지 — #7700ff(브랜드 링)가 border-primary(#dce0e5, Δ≈247)로
    # 오스냅돼 restore 원복→strokeWeight 평탄화 연쇄를 유발 (2026-08-13 라디오 active 회귀).
    # 근사는 실측 근사 케이스(#e8e9ec→border-secondary, Δ≈8) 수준만 허용.
    if how.startswith('near') and int(how[5:-1]) > 40:
        stats[f'원거리 스냅 스킵({cls})'] += 1; return
    fn = full_name(tgt)
    if not fn:
        stats['키맵 없음'] += 1; return
    setter = 'set_fill_color' if slot == 'fill' else 'set_stroke_color'
    ar = {'nodeId': nid, 'r': col.get('r',0), 'g': col.get('g',0), 'b': col.get('b',0)}
    # 🔴 MCP 레이어가 strokeWeight 미지정 시 1 로 강제 — 굵은 stroke 벡터(느낌표 등)가
    # 가늘어지던 회귀 (2026-08-12 판매종료 화면). 기존 weight 를 그대로 전달.
    if slot == 'stroke' and isinstance(stroke_weight, (int, float)) and stroke_weight > 0:
        ar['strokeWeight'] = stroke_weight
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

def walk(src, inst=False, d=0):
    """src: 노드 dict(get_node_tree 트리 — boundVariables 포함) 또는 id(폴백)."""
    if d > 8:
        return
    is_dict = isinstance(src, dict)
    n = src if is_dict else (call('get_node_info', {'nodeId': src}) or {})
    t = n.get('type')
    is_inst = inst or (t == 'INSTANCE')
    if t in ('FRAME', 'TEXT', 'RECTANGLE', 'ELLIPSE', 'VECTOR') and not is_inst:
        if is_dict:
            bv = n.get('boundVariables') or {}
        else:
            bv = (call('get_bound_variables', {'nodeId': n['id']}) or {}).get('boundVariables') or {}
        for slot in ('fill', 'stroke'):
            # 🔴 mixed strokeWeight(개별 사이드 보더 — 탭 밑줄 등)는 set_stroke_color 가
            # uniform 으로 평탄화해 4면 박스가 된다 (2026-08-12 라운지 쇼핑홈 탭 회귀) — 스킵
            if slot == 'stroke' and n.get('strokeWeight') == 'mixed':
                continue
            paints = n.get(f'{slot}s') or []
            all_vis = [p for p in paints if isinstance(p, dict) and p.get('visible') is not False]
            vis = [(i, p) for i, p in enumerate(paints)
                   if isinstance(p, dict) and p.get('type') == 'SOLID' and p.get('visible') is not False]
            # ⚠️ 멀티페인트(그라디언트 포함) 절대 건드리지 말 것 — set_fill_color detach 가
            # GRADIENT 를 날려 단일색으로 평탄화한다 (2026-08-10 타임딜 배너 회귀)
            if len(vis) != 1 or len(all_vis) != 1:
                continue
            i, p = vis[0]
            col = p.get('color', {})
            if col.get('a', 1) < 0.999 or p.get('opacity', 1) < 0.999:
                # 🔴 순검정/순흰 반투명은 Alpha 토큰 바인딩 (2026-08-12 사용자: "black 반투명이
                # 바인딩 안 됨"). 유색 반투명만 원값 유지. 실효 알파는 라이브 변수 resolve 값을
                # 따름(문서 스냅샷과 다를 수 있음 — 라운지 실측 60→48%).
                eff = col.get('a', 1) * p.get('opacity', 1)
                hx = to_hex(col)
                fam = 'black' if hx == '#000000' else ('white' if hx == '#ffffff' else None)
                arr0 = bv.get(f'{slot}s') or []
                if fam and not (i < len(arr0) and arr0[i]):
                    steps = [3, 5, 10, 16, 20, 24, 30, 40, 50, 60, 70, 80, 90, 100]
                    # 최근접 스텝의 토큰이 없으면(black 은 16/24 있음, white 는 없음) 실존하는
                    # 차선 스텝으로 폴백 (2026-08-13 Pagenation #fff 24% → white-24 없어 스킵되던 갭)
                    pct, fn2 = None, None
                    for s in sorted(steps, key=lambda s: abs(s / 100 - eff)):
                        cand = full_name(f'alpha-{fam}-{s}')
                        if cand:
                            pct, fn2 = s, cand
                            break
                    if fn2 and abs(pct / 100 - eff) <= 0.06:
                        setter = 'set_fill_color' if slot == 'fill' else 'set_stroke_color'
                        call(setter, {'nodeId': n['id'], 'r': col.get('r', 0), 'g': col.get('g', 0),
                                      'b': col.get('b', 0), 'a': eff})
                        call('set_bound_variables', {'nodeId': n['id'], 'bindings': {f'{slot}s/{i}': fn2}})
                        chk = (call('get_bound_variables', {'nodeId': n['id']}) or {}).get('boundVariables') or {}
                        arr2 = chk.get(f'{slot}s') or []
                        if i < len(arr2) and arr2[i]:
                            stats[f'알파 바인딩({fam}-{pct})'] += 1
                        else:
                            stats['알파 실패'] += 1
                        continue
                stats['알파 유지'] += 1; continue
            arr = bv.get(f'{slot}s') or []
            if i < len(arr) and arr[i]:
                stats['이미 바인딩'] += 1; continue
            h = to_hex(col)
            if h == '#000000':
                # 순검정은 fill/stroke 모두 스킵 — 아이콘/백버튼 검정 stroke 가
                # border-primary 로 스냅돼 연회색으로 훼손되던 회귀 (2026-08-10)
                continue
            bind_paint(n['id'], slot, i, col, cls_of(t, slot), False,
                       stroke_weight=(n.get('strokeWeight') if slot == 'stroke' else None))
    for c in n.get('children', []) or []:
        if is_dict:
            if ';' not in (c.get('id') or ''):
                walk(c, is_inst, d + 1)
        else:
            walk(c['id'], is_inst, d + 1)


def _apply_text_style(nid, info, by_key, SNAP, ts, deco_hint=None):
    """단일 TEXT 노드에 DS 텍스트 스타일 적용 (트리/폴백 공용). deco_hint 는 트리 모드의
    uniformTextDecoration(세그먼트 실사 콜 대체)."""
    if not (info.get('characters') or '').strip():
        return
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
        ts[f'미매칭 {size}px'] += 1
        return
    if sid and e['key'] in sid:
        ts['이미 DS'] += 1
        return
    if tgt_size != size:
        call('set_font_size', {'nodeId': nid, 'fontSize': tgt_size})
        ts[f'스냅 {size}->{tgt_size}'] += 1
    # ⚠️ 파라미터명은 textStyleId, 형식은 "S:{key},{아무값}" — 콤마 뒤가 비면 플러그인
    # 정규식(/^S:([^,]+),(.+)$/)을 못 타 로컬 조회로 떨어져 silent 실패한다 (2026-08-10 회귀).
    deco = info.get('textDecoration') or deco_hint
    # 🔴 2026-08-14: 취소선이 range 단위면 node-level 은 None — 세그먼트로 실사해
    # 균일 데코(STRIKETHROUGH/UNDERLINE)면 스타일 적용 후 node-level 로 재적용한다.
    # 트리 모드는 플러그인이 계산한 uniformTextDecoration(deco_hint)이 이 실사를 대체.
    if (not deco or deco == 'NONE') and deco_hint is None:
        try:
            segs = (call('get_styled_text_segments',
                         {'nodeId': nid, 'property': 'textDecoration'}) or {}).get('segments') or []
            vals = {sg.get('textDecoration') for sg in segs}
            if vals in ({'STRIKETHROUGH'}, {'UNDERLINE'}):
                deco = vals.pop()
        except Exception:
            pass
    call('set_text_style_id', {'nodeId': nid, 'textStyleId': f"S:{e['key']},{nid}"})
    if deco and deco != 'NONE':
        # 스타일 적용이 취소선/밑줄을 리셋한다 — 원본 데코 재적용 (2026-08-10 정가 취소선 회귀)
        call('set_text_decoration', {'nodeId': nid, 'textDecoration': deco})
    chk = call('get_node_info', {'nodeId': nid}) or {}
    if chk.get('textStyleId'):
        ts['스타일 적용(검증)'] += 1
    else:
        ts['스타일 실패'] += 1


def run(ROOT):
    """색 + spacing/radius + 텍스트 스타일 바인딩 — 읽기는 get_node_tree 1콜(폴백: 노드 단위),
    쓰기·적용 검증만 개별 콜. convert_screen 이 in-process 로 호출한다."""
    global stats
    stats = collections.Counter()
    fc.ensure_session()
    tree = L.fetch_tree(ROOT, max_depth=9)
    walk(tree if tree else ROOT)
    print('[색]', dict(stats))

    fc._bind_spacing_tokens_live(ROOT)
    fc._bind_radius_tokens_live(ROOT)

    # 텍스트 스타일 (스냅 매칭)
    smap = json.load(open('/Users/julee/imin/figma-design-agent/ds/TEXT_STYLE_MAP.json'))
    by_key = {}
    for e in smap:
        by_key[(e.get('fontSize'), (e.get('style') or '').lower())] = e
    SNAP = {10: 12, 11: 12, 13: 12, 15: 14, 17: 16, 18: 16, 22: 24, 26: 24, 28: 24, 30: 32}
    ts = collections.Counter()
    if tree:
        # 트리에서 TEXT 직접 수집 — scan_text_nodes(콜드런 60s 이력) + 텍스트당 get_node_info 제거
        texts = []

        def _collect_texts(nn):
            if nn.get('type') == 'TEXT' and ';' not in (nn.get('id') or ''):
                texts.append(nn)
            if nn.get('type') != 'INSTANCE':
                for c in nn.get('children') or []:
                    if ';' not in (c.get('id') or ''):
                        _collect_texts(c)
        _collect_texts(tree)
        for info in texts:
            _apply_text_style(info['id'], info, by_key, SNAP, ts,
                              deco_hint=info.get('uniformTextDecoration') or 'NONE')
    else:
        sc = call('scan_text_nodes', {'nodeId': ROOT}) or {}
        for tnode in (sc.get('textNodes') if isinstance(sc, dict) else sc) or []:
            nid = tnode.get('id') or ''
            if ';' in nid:
                continue
            info = call('get_node_info', {'nodeId': nid}) or {}
            _apply_text_style(nid, info, by_key, SNAP, ts)
    print('[텍스트]', dict(ts))
    print('DONE')

    print('⚠️ 완료 보고 전: python3 scripts/verify_bindings.py <rootId> 게이트 필수')
    return dict(stats)


if __name__ == '__main__':
    run(sys.argv[1])
