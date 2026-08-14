#!/usr/bin/env python3
"""convert_screen.py — 캡처/원본 프레임 1:1 DS 변환 원커맨드 (2026-08-14).

🔴 적용 범위 (2026-08-14 사용자 명시 — 어기면 안 됨):
  이 스크립트는 **단순 복사 + 토큰 바인딩(1:1 변환 트랙) 전용**이다.
  PRD/와이어프레임을 분석해서 디자인을 "생성"하는 태스크(창의 트랙)에서는 절대 실행 금지 —
  그 경우는 blueprint build 파이프라인(figma_mcp_client.py build: 기획 통독·레퍼런스 학습·
  재구성/발산 게이트 S24~S27)이 정본이다. 와이어를 이 스크립트로 트레이싱하는 것은
  "디자인 생성을 맡길 이유가 없다"(2026-06-15 사용자 핵심 룰) 위반이다.

사용:
  python3 scripts/convert_screen.py <srcId> [<srcId2> ...] [--gap 40] [--allow "이름1,이름2"] [--no-verify]

파이프라인 (전부 in-process — conversion-speed-rules 메모리: subprocess 루프 금지):
  ① clone → 원본들 오른쪽에 배치(같은 부모)   ② DS 스왑: Android bars→Status Bar,
  App bar→Tool Bar(back=Detail / close=modal+x-close), raw CTA→Action Button 2xl Primary
  ③ normalize_screen(393×min852) + Contents 세로 FILL   ④ bind_semantic_tokens (1회)
  ⑤ 미바인딩 잔여 일괄 스냅(시맨틱 최근접, verify 1회 원칙)   ⑥ verify_bindings

함정 반영: create_component_instance 는 parentId 무시 → 생성 직후 insert_child 필수.
Tool Bar 타이틀 20px 재단언(0-W). 스왑 불가 패턴은 raw 유지 + 사유 로그.
표현 불가 요소(멀티라인 textarea 등)는 건드리지 않는다. 브랜드 에셋은 --allow 로 verify 면제.
"""
import sys, os, json, time, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import figma_mcp_client as fc  # noqa: E402
import ds_convert_lib as L      # noqa: E402

SB_KEY = '13557b1ed59ce3f8c2dfbf9df46ec8fa7f772486'
TB_DETAIL = 'SET:c9299ef0c3c7cc271850a048025a3c8d0e82b230:Type=Detail view'
AB_SEC = '19c3ba6ad85401ae2427b178c20129d4260c62d0'
XCLOSE = '4ba052703931aeecf495c7698e5002b6c89d1ad4'

def call(t, a):
    return fc.parse_content(fc.call_tool(t, a)).get('json')

def to_hex(c):
    return '#%02x%02x%02x' % (round(c.get('r', 0) * 255), round(c.get('g', 0) * 255),
                              round(c.get('b', 0) * 255))

# ── 시맨틱 팔레트 (TOKEN_MAP 실값 기반 최근접 스냅) ──────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
KM = json.load(open(os.path.join(_HERE, '..', 'ds', 'VARIABLE_KEY_MAP.json')))
TM = json.load(open(os.path.join(_HERE, '..', 'ds', 'TOKEN_MAP.json')))

def _palette(prefix):
    out = {}
    for v in TM.values():
        p = v.get('figmaPath') or ''
        val = (v.get('value') or '')
        if p.startswith(prefix) and isinstance(val, str) and val.startswith('#') and len(val) == 7 \
                and p in KM and not any(s in p.lower() for s in ('_hover', '_pressed', 'disabled', 'solid', '_alt', 'hover')):
            out[val.lower()] = p
    return out

PAL = {'Text': _palette('Colors/Text/'), 'Background': _palette('Colors/Background/'),
       'Foreground': _palette('Colors/Foreground/'), 'Border': _palette('Colors/Border/')}

# 🔴 정확값 우선 인덱스 (2026-08-14 라운지_검색 뱃지 실측 — bg-primary-solid/bg-error-solid/
# utility-error-200 처럼 클래스 팔레트 필터(solid 제외·prefix 밖)에 걸려 못 찾던 정확 일치
# 토큰을 최근접 스냅보다 먼저 조회). state 변형(_hover 등)은 제외.
EXACT_BY_HEX = {}
for _v in TM.values():
    _p = _v.get('figmaPath') or ''
    _val = _v.get('value')
    if not (isinstance(_val, str) and _val.startswith('#') and len(_val) == 7 and _p in KM):
        continue
    if any(t in _p.lower() for t in ('_hover', '_pressed', 'hover', 'disabled', '_alt', 'focus')):
        continue
    EXACT_BY_HEX.setdefault(_val.lower(), []).append(_p)

_PREF = {('fill', 'TEXT'): ('Colors/Text/', 'Colors/Foreground/'),
         ('fill', '*'): ('Colors/Background/', 'Colors/Foreground/', 'Component colors/Utility/'),
         ('stroke', '*'): ('Colors/Border/', 'Colors/Foreground/', 'Colors/Background/',
                           'Component colors/Utility/')}

def exact_token(hexv, slot, node_type):
    paths = EXACT_BY_HEX.get(hexv) or []
    prefs = _PREF.get((slot, 'TEXT' if node_type == 'TEXT' else '*')) or _PREF[(slot, '*')]         if slot == 'fill' else _PREF[('stroke', '*')]
    if slot == 'fill' and node_type == 'TEXT':
        prefs = _PREF[('fill', 'TEXT')]
    elif slot == 'fill':
        prefs = _PREF[('fill', '*')]
    for pref in prefs:
        for p in paths:
            if p.startswith(pref):
                return p
    return None

def _rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)

# 라운지 배너 장식 블롭 등 — 시맨틱 대응 없는 에셋 고유색 (2026-08-14 5개 배치 반복 실측).
# sweep 미해결/verify 오탐에서 제외하고 verify 호출에 자동 --allow 로 전달할 노드 이름들.
ASSET_ALLOW_DEFAULT = {'Ellipse', 'BrandTint25', 'BG'}
SOFT_TINT_RESTORE = {'#faf7ff': 'BrandTint25'}  # 게시 변수 없는 미세 틴트 — 원값 유지+개명
ASSET_HEXES = {'#f795ae', '#8f95fa', '#55c8c0'}

def _chroma(h):
    r, g, b = _rgb(h)
    return max(r, g, b) - min(r, g, b)

def nearest(hexv, cls, max_d=60):
    table = PAL[cls]
    if hexv in table:
        return table[hexv]
    r0, g0, b0 = _rgb(hexv)
    src_c = _chroma(hexv)
    best, bd = None, 1e9
    for hh, path in table.items():
        # 🔴 2026-08-14 사용자 지적: 유채 소스를 무채 토큰으로 스냅 금지 (미세 퍼플 뭉개짐)
        if src_c >= 5 and _chroma(hh) < 3:
            continue
        r1, g1, b1 = _rgb(hh)
        d = ((r0 - r1) ** 2 + (g0 - g1) ** 2 + (b0 - b1) ** 2) ** 0.5
        if d < bd:
            bd, best = d, path
    if best is None:
        return None
    if src_c >= 5 and bd > 10:   # 유채→유채 근사는 Δ≤10 만
        return None
    return best if bd <= max_d else None

# ── 트리 유틸 ────────────────────────────────────────────────────────────────
def deep(nid, d=0, max_d=12, skip_inst=True):
    """단일 프로세스 재귀 fetch — 인스턴스 내부는 내려가지 않음(0-K)."""
    n = call('get_node_info', {'nodeId': nid}) or {}
    n['_children'] = []
    if d < max_d:
        for c in n.get('children', []) or []:
            cid = c.get('id') or ''
            if ';' in cid:
                continue
            if skip_inst and c.get('type') == 'INSTANCE':
                n['_children'].append({'id': cid, 'name': c.get('name'), 'type': 'INSTANCE',
                                       'width': c.get('width'), 'height': c.get('height'), '_children': []})
                continue
            n['_children'].append(deep(cid, d + 1, max_d, skip_inst))
    return n

def find_all(tree, pred, acc=None):
    acc = acc if acc is not None else []
    if pred(tree):
        acc.append(tree)
    for c in tree.get('_children', []):
        find_all(c, pred, acc)
    return acc

def texts_in(tree, acc=None):
    acc = acc if acc is not None else []
    if tree.get('type') == 'TEXT' and (tree.get('characters') or '').strip():
        acc.append(tree)
    for c in tree.get('_children', []):
        texts_in(c, acc)
    return acc

def child_index(parent_id, child_id):
    p = call('get_node_info', {'nodeId': parent_id}) or {}
    for i, c in enumerate(p.get('children', []) or []):
        if c.get('id') == child_id:
            return i
    return 0

def new_instance(key, parent_id, index):
    """create_component_instance 는 parentId 무시 → 즉시 insert_child (2026-08-14 함정)."""
    inst = call('create_component_instance', {'componentKey': key, 'x': 0, 'y': 0})
    call('insert_child', {'parentId': parent_id, 'childId': inst['id'], 'index': index})
    return inst['id']

# ── DS 스왑 ──────────────────────────────────────────────────────────────────
def swap_status_bar(root_tree):
    cands = find_all(root_tree, lambda n: (n.get('name') or '').lower() in ('bars', 'status bar', 'statusbar')
                     and round(n.get('height') or 0) <= 40)
    for c in cands:
        parent = call('get_node_info', {'nodeId': c['id']}) or {}
        pid = parent.get('parentId')
        idx = child_index(pid, c['id'])
        sb = new_instance(SB_KEY, pid, idx)
        call('delete_node', {'nodeId': c['id']})
        call('resize_node', {'nodeId': sb, 'width': 393, 'height': 62})
        call('set_layout_sizing', {'nodeId': sb, 'horizontal': 'FILL'})
        print(f'  [swap] Status Bar ← {c.get("name")} ({c["id"]})')
        return sb
    return None

def swap_app_bar(root_tree):
    cands = find_all(root_tree, lambda n: 'app bar' in (n.get('name') or '').lower()
                     and n.get('type') == 'FRAME' and 40 <= round(n.get('height') or 0) <= 72)
    for ab in cands:
        has_back = bool(find_all(ab, lambda n: 'arrow_left' in (n.get('name') or '').lower()))
        has_close = bool(find_all(ab, lambda n: 'close' in (n.get('name') or '').lower()))
        tx = texts_in(ab)
        title = tx[0]['characters'] if tx else ''
        info = call('get_node_info', {'nodeId': ab['id']}) or {}
        pid = info.get('parentId')
        idx = child_index(pid, ab['id'])
        tb = new_instance(TB_DETAIL, pid, idx)
        call('delete_node', {'nodeId': ab['id']})
        call('set_layout_sizing', {'nodeId': tb, 'horizontal': 'FILL'})
        view = 'modal' if (has_close and not has_back) else 'Detail'
        call('set_instance_properties', {'nodeId': tb, 'properties': {'View': view, 'Num#17757:3': False}})
        n = call('get_node_info', {'nodeId': tb}) or {}
        tit_id, rb_id = None, None
        def w(x):
            nonlocal tit_id, rb_id
            if x.get('name') == 'Title':
                for c in x.get('children', []) or []:
                    if c.get('type') == 'TEXT' and c.get('name') != 'num':
                        tit_id = c['id']
            if x.get('name') == 'Right Buttons':
                rb_id = x['id']
            for c in x.get('children', []) or []:
                w(c)
        w(n)
        if tit_id and title:
            call('set_text_content', {'nodeId': tit_id, 'text': title})
            call('set_font_size', {'nodeId': tit_id, 'fontSize': 20})  # 0-W 20px 재단언
        elif not title:
            # X-only 헤더 — 기본 타이틀('내 스케줄') 잔존 방지 (2026-08-14 라운지 초대 완료 실측)
            call('set_instance_properties', {'nodeId': tb, 'properties': {'Title#17757:6': False}})
        if rb_id:
            if view == 'modal':
                call('set_instance_properties', {'nodeId': rb_id, 'properties': {'Type': '1 button'}})
                rn = call('get_node_info', {'nodeId': rb_id}) or {}
                inner = []
                def w2(x):
                    if x.get('type') == 'INSTANCE' and x.get('id') != rb_id:
                        inner.append(x['id'])
                    for c in x.get('children', []) or []:
                        w2(c)
                w2(rn)
                if inner:
                    call('swap_instance_component', {'nodeId': inner[0], 'componentKey': XCLOSE})
            else:
                call('set_instance_properties', {'nodeId': rb_id, 'properties': {'Type': 'empty'}})
        print(f'  [swap] Tool Bar({view}) "{title}" ← App bar ({ab["id"]})')
        return tb
    return None

def swap_sheet_headers(root_tree):
    """바텀시트 raw 타이틀+X 헤더 → Tool Bar(View=modal) (0-W, verify raw-modal-header 게이트 짝).
    2026-08-14 내 혜택 바텀시트 실측: /Bottom sheet/Title(h56, btn/close 포함) 통째 교체."""
    cands = find_all(root_tree, lambda n: n.get('type') == 'FRAME'
                     and 40 <= round(n.get('height') or 0) <= 72
                     and 'app bar' not in (n.get('name') or '').lower()
                     and bool(find_all(n, lambda m: 'close' in (m.get('name') or '').lower()
                                       and m.get('id') != n.get('id'))))
    # 중첩 후보 중 최내곽(헤더 자체)만
    ids = {c['id'] for c in cands}
    inner = [c for c in cands if not any(ch['id'] in ids for ch in c.get('_children', []))]
    for hd in inner:
        tx = texts_in(hd)
        title = tx[0]['characters'] if tx else ''
        info = call('get_node_info', {'nodeId': hd['id']}) or {}
        pid = info.get('parentId')
        idx = child_index(pid, hd['id'])
        tb = new_instance(TB_DETAIL, pid, idx)
        call('delete_node', {'nodeId': hd['id']})
        call('set_layout_sizing', {'nodeId': tb, 'horizontal': 'FILL'})
        call('set_instance_properties', {'nodeId': tb, 'properties': {'View': 'modal', 'Num#17757:3': False}})
        # 🔴 2026-08-14 사용자 룰: 시트 헤더에 Tool Bar 인스턴스를 쓰면 시트 프레임에
        # clipsContent=true 필수 — 안 켜면 Tool Bar 사각 모서리가 시트의 상단 코너
        # radius(16) 를 덮어 라운드가 사라진다.
        pinfo = call('get_node_info', {'nodeId': pid}) or {}
        call('set_auto_layout', {'nodeId': pid, 'layoutMode': pinfo.get('layoutMode') or 'VERTICAL',
                                 'clipsContent': True})
        n = call('get_node_info', {'nodeId': tb}) or {}
        tit_id, rb_id = None, None
        def w(x):
            nonlocal tit_id, rb_id
            if x.get('name') == 'Title':
                for c in x.get('children', []) or []:
                    if c.get('type') == 'TEXT' and c.get('name') != 'num':
                        tit_id = c['id']
            if x.get('name') == 'Right Buttons':
                rb_id = x['id']
            for c in x.get('children', []) or []:
                w(c)
        w(n)
        if tit_id and title:
            call('set_text_content', {'nodeId': tit_id, 'text': title})
            call('set_font_size', {'nodeId': tit_id, 'fontSize': 20})
        elif not title:
            call('set_instance_properties', {'nodeId': tb, 'properties': {'Title#17757:6': False}})
        if rb_id:
            call('set_instance_properties', {'nodeId': rb_id, 'properties': {'Type': '1 button'}})
            rn = call('get_node_info', {'nodeId': rb_id}) or {}
            inner_i = []
            def w2(x):
                if x.get('type') == 'INSTANCE' and x.get('id') != rb_id:
                    inner_i.append(x['id'])
                for c in x.get('children', []) or []:
                    w2(c)
            w2(rn)
            if inner_i:
                call('swap_instance_component', {'nodeId': inner_i[0], 'componentKey': XCLOSE})
        print(f'  [swap] Tool Bar(modal) 시트 헤더 "{title}" ← {hd.get("name")} ({hd["id"]})')


def normalize_overlay(root_id):
    """dim 오버레이 화면(root 직속: 배경 스크린 + 'Layer') — 두 레이어를 ABSOLUTE (0,0)
    393×852 로 정규화 (2026-08-14 내 혜택 바텀시트 실측: HORIZONTAL flow 로 밀려 상단 띠 발생)."""
    n = call('get_node_info', {'nodeId': root_id}) or {}
    kids = [c for c in n.get('children', []) or [] if ';' not in (c.get('id') or '')]
    names = [(c.get('name') or '').lower() for c in kids]
    if len(kids) == 2 and any(nm == 'layer' for nm in names):
        h = max(852, round(n.get('height') or 0))
        for c in kids:
            call('set_layout_positioning', {'nodeId': c['id'], 'layoutPositioning': 'ABSOLUTE'})
            call('move_node', {'nodeId': c['id'], 'x': 0, 'y': 0})
            call('resize_node', {'nodeId': c['id'], 'width': 393, 'height': h})
        print('  [overlay] 배경+Layer ABSOLUTE 393x%d 정규화' % h)


def swap_cta(root_tree):
    done = []
    cands = find_all(root_tree, lambda n: (n.get('name') or '').strip().lower() == 'button'
                     and n.get('type') == 'FRAME' and 44 <= round(n.get('height') or 0) <= 64)
    for b in cands:
        tx = texts_in(b)
        if len(tx) != 1:
            print(f'  [skip] raw Button {b["id"]} — 단일 라벨 아님(스왑 불가, raw 유지)')
            continue
        label = tx[0]['characters']
        info = call('get_node_info', {'nodeId': b['id']}) or {}
        # 원본 raw 버튼 fill 이 밝으면(연보라 등) Disabled 상태 (2026-08-14 리뷰작성 실측)
        state = 'Default'
        bf = [f for f in (info.get('fills') or []) if isinstance(f, dict) and f.get('type') == 'SOLID'
              and f.get('visible') is not False]
        if bf:
            c = bf[0].get('color', {})
            if (c.get('r', 0) + c.get('g', 0) + c.get('b', 0)) / 3 > 0.72:
                state = 'Disabled'
        pid = info.get('parentId')
        idx = child_index(pid, b['id'])
        ab = new_instance(AB_SEC, pid, idx)
        call('delete_node', {'nodeId': b['id']})
        call('set_instance_properties', {'nodeId': ab, 'properties': {
            'Hierarchy': 'Primary', 'Size': '2xl', 'State': state, 'Label#17537:16': label,
            '➡️ Icon trailing#3287:2338': False, '⬅️ Icon leading#3287:1577': False,
            'Loading text#8994:0': False}})
        call('set_layout_sizing', {'nodeId': ab, 'horizontal': 'FILL'})
        print(f'  [swap] Action Button 2xl "{label}" ← raw Button ({b["id"]})')
        done.append(ab)
    return done

# ── 미바인딩 잔여 일괄 스냅 (verify 1회 원칙) ────────────────────────────────
BRAND_STEP_TOKENS = {
    '#5200b0': 'Component colors/Utility/Brand/utility-brand-700',
    '#6a00e0': 'Component colors/Utility/Brand/utility-brand-600',
    '#7700ff': 'Component colors/Utility/Brand/utility-brand-500',
    '#9b55ff': 'Component colors/Utility/Brand/utility-brand-400',
    '#b685ff': 'Component colors/Utility/Brand/utility-brand-300',
    '#cfaeff': 'Component colors/Utility/Brand/utility-brand-200'}

# DS gradient color style 키 — ds/PAINT_STYLE_MAP.json 에서 자동 파생 (2026-08-14).
# 이름 'Gradient/Brand/600 -> 500 -> 400' 의 스텝을 utility-brand 팔레트 hex 로 변환해
# (stop 시그니처)→스타일키 맵을 만든다. sync-paint-styles 로 새 gradient 를 추출하면
# 코드 수정 없이 자동 반영된다. ⚠️ 원본 앱 캡처의 f262f3a4…('…-6~5~4_h')는 구 라이브러리
# hover 변형 — stop 값이 base 와 동일해 색으로 구분 불가, 정본 키 일치로만 판정.
BRAND_STEP_HEX = {'700': '#5200b0', '600': '#6a00e0', '500': '#7700ff',
                  '400': '#9b55ff', '300': '#b685ff', '200': '#cfaeff'}

def _load_brand_gradient_styles():
    out = {}
    try:
        entries = json.load(open(os.path.join(_HERE, '..', 'ds', 'PAINT_STYLE_MAP.json')))
    except Exception:
        entries = []
    for e in entries:
        nm = e.get('name') or ''
        if not nm.startswith('Gradient/Brand/'):
            continue
        steps = [t.strip() for t in nm.split('/')[-1].split('->')]
        hexes = tuple(BRAND_STEP_HEX.get(t) for t in steps)
        if all(hexes):
            out[hexes] = 'S:' + e['key'] + ',x'
    # 정본 시드 백업 (맵 파일 유실 시에도 동작)
    out.setdefault(('#6a00e0', '#7700ff', '#9b55ff'),
                   'S:2d6d98a9c0279efe0b0eb1ea7ba3c46e7cae94d7,x')
    return out

BRAND_GRADIENT_STYLES = _load_brand_gradient_styles()

def bind_brand_gradients(n, nid2):
    """DS Gradient/Brand 스텝과 전 stop 정확 일치하는 gradient → stop 별 변수 바인딩
    (2026-08-14 사용자 지적. 비표준 스텝 혼재 = 에셋 고유 그라데이션 → 원값 유지).
    플러그인 fills/N/stops/M 바인딩 지원 필요(cc086f1 이후 재실행)."""
    cnt = 0
    for slot in ('fills', 'strokes'):
        for pi, p in enumerate(n.get(slot) or []):
            if not (isinstance(p, dict) and str(p.get('type', '')).startswith('GRADIENT')
                    and p.get('visible') is not False):
                continue
            stops = p.get('gradientStops') or []
            hexes = [to_hex(st.get('color', {})) for st in stops]
            if not hexes or not all(h in BRAND_STEP_TOKENS for h in hexes):
                continue
            style_key = BRAND_GRADIENT_STYLES.get(tuple(hexes))
            cur = n.get('fillStyleId') or ''
            # 🔴 2026-08-14 사용자 재지적: 원본이 물고 온 legacy _h(hover) 스타일이
            # "fillStyleId 있음"으로 통과되던 구멍 — 정본 키가 아니면 무조건 교체.
            if style_key and slot == 'fills':
                canon_key = style_key.split(':')[1].split(',')[0]
                if canon_key in cur:
                    continue  # 이미 정본
                # 🔴 정본: DS color style 적용 (2026-08-14 사용자 — stop 변수는 폴백일 뿐)
                call('set_fill_style_id', {'nodeId': nid2, 'fillStyleId': style_key})
                cnt += 1
                continue
            for si, h in enumerate(hexes):
                if stops[si].get('bound'):
                    continue
                call('set_bound_variables', {'nodeId': nid2,
                     'bindings': {f'{slot}/{pi}/stops/{si}': 'K:' + KM[BRAND_STEP_TOKENS[h]]}})
                cnt += 1
    return cnt

def sweep_unbound(root_id, allow):
    bound = 0
    left = []
    def walk(nid, d=0):
        nonlocal bound
        if d > 12:
            return
        n = call('get_node_info', {'nodeId': nid}) or {}
        nid2 = n.get('id') or ''
        name = n.get('name') or ''
        if name in allow:
            return
        t = n.get('type')
        if ';' not in nid2 and t in ('FRAME', 'TEXT', 'RECTANGLE', 'ELLIPSE', 'VECTOR', 'LINE',
                                     'BOOLEAN_OPERATION', 'STAR', 'POLYGON'):
            bv = (call('get_bound_variables', {'nodeId': nid2}) or {}).get('boundVariables') or {}
            bound += bind_brand_gradients(n, nid2)
            fills = [f for f in (n.get('fills') or []) if isinstance(f, dict)
                     and f.get('type') == 'SOLID' and f.get('visible') is not False]
            if len(fills) == 1 and not bv.get('fills'):
                hx = to_hex(fills[0].get('color', {}))
                if hx not in ('#ffffff', '#000000') and (fills[0].get('opacity', 1)) >= 0.999:
                    cls = 'Text' if t == 'TEXT' else ('Background' if t in ('FRAME', 'RECTANGLE') else 'Foreground')
                    if hx in SOFT_TINT_RESTORE:
                        call('rename_node', {'nodeId': nid2, 'name': SOFT_TINT_RESTORE[hx]})
                        bound += 1
                    else:
                        path = exact_token(hx, 'fill', t) or nearest(hx, cls)
                        if path:
                            call('set_bound_variables', {'nodeId': nid2, 'bindings': {'fills/0': 'K:' + KM[path]}})
                            bound += 1
                        elif hx not in ASSET_HEXES:
                            left.append((name, t, 'fill', hx))
            # stroke 는 len==1 제약 없이 첫 SOLID 페인트 기준 (라디오 링 등 멀티페인트가
            # len==1 조건에 걸려 3건씩 남던 실측 — 2026-08-14)
            strokes = [s for s in (n.get('strokes') or []) if isinstance(s, dict)
                       and s.get('type') == 'SOLID' and s.get('visible') is not False]
            if strokes and not bv.get('strokes'):
                hx = to_hex(strokes[0].get('color', {}))
                if hx not in ('#ffffff', '#000000'):
                    cls = 'Border' if t in ('FRAME', 'RECTANGLE') else 'Foreground'
                    path = exact_token(hx, 'stroke', t) or nearest(hx, cls) \
                        or nearest(hx, 'Foreground') or nearest(hx, 'Background')
                    if path:
                        call('set_bound_variables', {'nodeId': nid2, 'bindings': {'strokes/0': 'K:' + KM[path]}})
                        bound += 1
                    else:
                        left.append((name, t, 'stroke', hx))
        for c in n.get('children', []) or []:
            walk(c['id'], d + 1)
    walk(root_id)
    print(f'  [sweep] 잔여 스냅 바인딩 {bound}건' + (f' / 미해결 {len(left)}건: {left[:6]}' if left else ''))
    return left

# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print(__doc__)
        return 2
    gap = 40
    allow = set()
    no_verify = '--no-verify' in sys.argv
    for i, a in enumerate(sys.argv):
        if a == '--gap' and i + 1 < len(sys.argv):
            gap = int(sys.argv[i + 1])
        if a == '--allow' and i + 1 < len(sys.argv):
            allow = {s.strip() for s in sys.argv[i + 1].split(',') if s.strip()}
    t0 = time.time()
    fc.ensure_session()

    srcs = []
    for sid in args:
        n = call('get_node_info', {'nodeId': sid}) or {}
        if not n.get('id'):
            print(f'✗ 원본 {sid} 조회 실패')
            return 1
        srcs.append(n)
    right = max((s.get('x') or 0) + (s.get('width') or 0) for s in srcs)
    y0 = min(s.get('y') or 0 for s in srcs)
    parent = srcs[0].get('parentId')

    results = []
    for i, s in enumerate(srcs):
        sid = s['id']
        print(f'== [{i+1}/{len(srcs)}] {s.get("name")} ({sid})')
        cl = call('clone_node', {'nodeId': sid})
        rid = cl['id']
        call('insert_child', {'parentId': parent, 'childId': rid})
        call('move_node', {'nodeId': rid, 'x': right + gap + i * (393 + gap), 'y': y0})
        tree = deep(rid)
        swap_status_bar(tree)
        swap_app_bar(tree)
        swap_sheet_headers(tree)
        swap_cta(tree)
        w, h = L.normalize_screen(rid)
        normalize_overlay(rid)
        print(f'  [normalize] {w}x{h}')
        n2 = call('get_node_info', {'nodeId': rid}) or {}
        for c in n2.get('children', []) or []:
            if (c.get('name') or '') == 'Contents':
                call('set_layout_sizing', {'nodeId': c['id'], 'vertical': 'FILL'})
        # 토큰 바인딩 (스크립트 1회 — 색/spacing/radius/텍스트 스타일 일괄)
        r = subprocess.run([sys.executable, os.path.join(_HERE, 'bind_semantic_tokens.py'), rid],
                           capture_output=True, text=True)
        print('  [bind]', ([ln for ln in r.stdout.splitlines() if ln.startswith('[색]')] or ['?'])[0])
        sweep_unbound(rid, allow)
        results.append(rid)

    ok = True
    if not no_verify:
        for rid in results:
            cmd = [sys.executable, os.path.join(_HERE, 'verify_bindings.py'), rid]
            eff_allow = set(allow) | ASSET_ALLOW_DEFAULT
            if eff_allow:
                cmd += ['--allow', ','.join(sorted(eff_allow))]
            r = subprocess.run(cmd, capture_output=True, text=True)
            tail = r.stdout.strip().splitlines()[-6:]
            print(f'-- verify {rid}')
            print('   ' + '\n   '.join(tail))
            ok = ok and (r.returncode == 0)
    print(f'\n{"✓" if ok else "✗"} 변환 {len(results)}장 — {round(time.time()-t0, 1)}s → {results}')
    print('👉 남은 수동 QA: export_node_as_image 로 각 root 를 Read 해 원본과 구역 대조할 것.')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
