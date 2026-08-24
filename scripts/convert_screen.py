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

# 🔴 스왑/정규화 단계가 감지한 문제 — 화면별 CONVERT-SUMMARY flags 로 승격 (2026-08-24:
# navbar-right-icon-unresolved 🚩 가 print 로만 남아 flags:[] 로 나갔고, 로그 tail 필터에
# 잘려 시각 QA 까지 발견이 밀린 실측 낭비 ~5분. 🚩 는 반드시 여기에도 append 할 것.)
RUN_FLAGS = []

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

_PREF = {('fill', 'TEXT'): ('Colors/Text/', 'Colors/Foreground/', 'Component colors/Utility/'),
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
def _adapt_tree(n):
    """get_node_tree 결과를 deep() 반환 형태(_children)로 변환 — 인스턴스는 stub(0-K)."""
    kids = []
    for c in n.get('children') or []:
        cid = c.get('id') or ''
        if ';' in cid:
            continue
        if c.get('type') == 'INSTANCE':
            kids.append({'id': cid, 'name': c.get('name'), 'type': 'INSTANCE',
                         'width': c.get('width'), 'height': c.get('height'), '_children': []})
        else:
            kids.append(_adapt_tree(c))
    n['_children'] = kids
    return n


def deep(nid, d=0, max_d=12, skip_inst=True):
    """서브트리 fetch — get_node_tree 1콜 우선 (2026-08-24 성능 수리), 구버전 플러그인이면
    노드 단위 재귀 폴백. 인스턴스 내부는 내려가지 않음(0-K)."""
    if d == 0:
        t = L.fetch_tree(nid, max_depth=max_d)
        if t:
            return _adapt_tree(t)
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
        # 🔴 0-W: 검색바 내장 헤더는 Tool Bar 로 표현 불가 — raw 유지 (2026-08-14 라운지_검색
        # 실측: 'Input' 프레임(서치 아이콘+텍스트+클리어)이 타이틀로 강등되던 회귀)
        if find_all(ab, lambda n: (n.get('name') or '').strip().lower() in ('input', 'search', 'search bar', 'searchbar')
                    or 'ic_search' in (n.get('name') or '').lower()):
            print(f'  [skip] App bar {ab["id"]} — 검색바 내장 헤더(Tool Bar 표현 불가, raw 유지)')
            continue
        # 🔴 2026-08-21 커뮤니티 실측: 숨김(back visible=False) 노드를 back 으로 오인해
        # 메인탭 화면에 back 이 생기던 구멍 — visible 체크 추가.
        has_back = bool(find_all(ab, lambda n: 'arrow_left' in (n.get('name') or '').lower()
                                 and n.get('visible') is not False))
        has_close = bool(find_all(ab, lambda n: 'close' in (n.get('name') or '').lower()
                                  and n.get('visible') is not False))
        tx = texts_in(ab)
        title = tx[0]['characters'] if tx else ''
        # 🔴 텍스트 액션 버튼('확인/취소/완료' 등) 내장 헤더는 Tool Bar 인스턴스로 표현 불가 —
        # raw 유지 후 normalize_text_button_header 가 정본 문법으로 정규화 (2026-08-24
        # 채팅 상대 선택 실측 3장: 인스턴스 교체가 우측 '확인' 버튼을 삼켜 유실).
        if any((t.get('characters') or '').strip() in TEXT_BTN_ACTION_WORDS
               and t.get('visible') is not False for t in tx):
            print(f'  [skip] App bar {ab["id"]} — 텍스트 액션 버튼 내장(raw 정본 문법으로 정규화)')
            continue
        # 🔴 우측 아이콘 자동 이관 (2026-08-18 배송지 수정 휴지통 실측 — Right empty 고정이
        # 원본 우측 액션을 지우던 구멍). ic_* 아이콘 이름을 NAV_ICON_KEYS 로 해석, 미해석은 flag.
        from design_rules.ds_catalog import NAV_ICON_KEYS  # noqa: E402
        right_icons = []
        for ic in find_all(ab, lambda n: (n.get('name') or '').lower().startswith('ic_')
                           and 'arrow_left' not in (n.get('name') or '').lower()
                           and 'close' not in (n.get('name') or '').lower()
                           and n.get('visible') is not False):
            nm_ic = (ic.get('name') or '').lower()
            key_ic = NAV_ICON_KEYS.get(nm_ic) or NAV_ICON_KEYS.get(nm_ic.replace('ic_', '').replace('_', '-'))
            if not key_ic:
                for kk, vv in NAV_ICON_KEYS.items():
                    if kk.replace('-', '_') in nm_ic or kk in nm_ic:
                        key_ic = vv
                        break
            right_icons.append((nm_ic, key_ic))
        # 🔴 2026-08-21 커뮤니티 실측: 우측 액션이 ic_* 명명이 아닌 경우(raw 'Button' 프레임에
        # 벡터로 그린 검색 아이콘, 'btn/activity' 인스턴스 등) 이관 루프가 못 잡고 조용히
        # empty 로 떨어지던 구멍 — 이름 fuzzy 해석 시도 + 미해석은 unresolved 로 승격.
        if not right_icons:
            for act in find_all(ab, lambda n: n.get('visible') is not False
                                and n.get('type') in ('INSTANCE', 'FRAME')
                                and (((n.get('name') or '').lower().startswith('btn/'))
                                     or (n.get('name') or '').strip().lower() == 'button')
                                and 'back' not in (n.get('name') or '').lower()
                                and 'close' not in (n.get('name') or '').lower()):
                nm_a = (act.get('name') or '').lower()
                key_a = None
                for kk, vv in NAV_ICON_KEYS.items():
                    if kk.replace('-', '_') in nm_a or kk in nm_a:
                        key_a = vv
                        break
                # 🔴 컨테이너 이름('Button')이 안 풀리면 **자손 이름**으로 해석 (2026-08-24
                # 채팅 실측: 'Button' 프레임 안 GROUP 'btn_top_make_chat' — 컨테이너만 보고
                # unresolved 로 떨어지던 구멍)
                if not key_a:
                    for dn in find_all(act, lambda n: bool(n.get('name'))):
                        nm_d = (dn.get('name') or '').lower()
                        if nm_d == nm_a:
                            continue
                        key_a = NAV_ICON_KEYS.get(nm_d)
                        if not key_a:
                            for kk, vv in NAV_ICON_KEYS.items():
                                if kk.replace('-', '_') in nm_d or kk in nm_d:
                                    key_a = vv
                                    break
                        if key_a:
                            nm_a = nm_d
                            break
                right_icons.append((nm_a, key_a))
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
            def _fill_right(icon_keys):
                call('set_instance_properties', {'nodeId': rb_id, 'properties':
                     {'Type': '1 button' if len(icon_keys) == 1 else '2 button'}})
                rn = call('get_node_info', {'nodeId': rb_id}) or {}
                inner = []
                def w2(x):
                    if x.get('type') == 'INSTANCE' and x.get('id') != rb_id:
                        inner.append(x['id'])
                    for c in x.get('children', []) or []:
                        w2(c)
                w2(rn)
                tops = [i for i in inner if i.count(';') <= 1] or inner
                for slot_i, kk in enumerate(icon_keys[:2]):
                    if slot_i < len(tops):
                        call('swap_instance_component', {'nodeId': tops[slot_i], 'componentKey': kk})
            resolved = [k for _, k in right_icons if k]
            unresolved = [nm for nm, k in right_icons if not k]
            if view == 'modal':
                _fill_right([XCLOSE])
            elif resolved:
                _fill_right(resolved)
                print(f'  [swap] NavBar 우측 아이콘 이관: {resolved}')
            else:
                call('set_instance_properties', {'nodeId': rb_id, 'properties': {'Type': 'empty'}})
            if unresolved:
                print(f'  🚩 [detect] navbar-right-icon-unresolved: {unresolved} — '
                      f'search_design_system 으로 키 확보 후 NAV_ICON_KEYS 등록 필요')
                RUN_FLAGS.append(f'navbar-right-icon-unresolved: {unresolved} — Right Buttons 가 '
                                 f'empty 로 떨어짐. search_design_system 키 확보→NAV_ICON_KEYS 등록→swap')
        print(f'  [swap] Tool Bar({view}) "{title}" ← App bar ({ab["id"]})')
        return tb
    return None

def normalize_text_button_header(root_tree):
    """텍스트 버튼형 헤더(취소/올리기 등) Tool Bar 문법 정규화 (2026-08-20 사용자 지시 ×3).

    Tool Bar 인스턴스 프롭으로 좌우 텍스트 버튼은 표현 불가 → raw 허용 유일 케이스지만,
    raw 라도 정본 문법을 강제한다:
      이름 'Tool Bar(텍스트 버튼형)' / 393x56 / Status Bar 아래 y62(부모 gap 0) /
      좌우 padding 20 + SPACE_BETWEEN + 세로 CENTER / **fill = bg-primary 바인딩 필수**(0-O).
    감지: h<=40 의 얇은 raw 헤더 frame 에 '취소'/'올리기'/'완료'/'등록' 류 텍스트 버튼 2개 이하.
    swap_app_bar 가 'app bar' 이름·40~72h 필터 밖이라 놓치던 클래스('Top app bar' 80h 내부
    'App bar' 24h — 2026-08-20 블로그 3장 실측)."""
    _vk = json.load(open(os.path.join(os.path.dirname(__file__), '..', 'ds', 'VARIABLE_KEY_MAP.json')))
    _bg = [v for k, v in _vk.items() if k.endswith('Background/bg-primary')]
    ACTION_WORDS = TEXT_BTN_ACTION_WORDS
    # 후보: 얇은 바(16~40h — 2026-08-20 블로그 클래스) + 타이틀 동반 56h App bar
    # (2026-08-24 채팅 상대 선택 클래스). w≥200 로 개별 텍스트 버튼('확인' 36w) 오인 차단.
    cands = find_all(root_tree, lambda n: n.get('type') == 'FRAME'
                     and 16 <= round(n.get('height') or 0) <= 64
                     and round(n.get('width') or 0) >= 200
                     and (n.get('y') or 0) < 140)
    for hd in cands:
        tx = texts_in(hd)
        labels = [(t.get('characters') or '').strip() for t in tx]
        if not labels:
            continue
        # 액션 정확 일치 라벨 ≥1 + 비액션(타이틀) 라벨 ≤1
        action_labels = [l for l in labels if l in ACTION_WORDS]
        title_labels = [l for l in labels if l not in ACTION_WORDS]
        if not action_labels or len(title_labels) > 1:
            continue
        hid = hd['id']
        info = call('get_node_info', {'nodeId': hid}) or {}
        if not info.get('id'):
            continue  # stale (다른 스왑이 이미 삭제)
        pid = info.get('parentId')
        # 부모(Navigation) 정규화: 118h + gap 0 → flow 상 Tool Bar y62.
        # 🔴 자식 2개(bars+헤더) 구성일 때만 — Search bar 등 형제가 더 있으면 리사이즈 금지
        # (2026-08-24: Navigation 174h 를 118 로 눌러 검색바가 잘리는 오폭 방지)
        _pn = call('get_node_info', {'nodeId': pid}) or {} if pid else {}
        if pid and len(_pn.get('children') or []) <= 2:
            call('rename_node', {'nodeId': pid, 'name': 'Navigation'})
            call('set_auto_layout', {'nodeId': pid, 'layoutMode': 'VERTICAL', 'itemSpacing': 0})
            call('set_layout_sizing', {'nodeId': pid, 'horizontal': 'FIXED', 'vertical': 'FIXED'})
            call('resize_node', {'nodeId': pid, 'width': 393, 'height': 118})
        call('rename_node', {'nodeId': hid, 'name': 'Tool Bar(텍스트 버튼형 — 인스턴스 미표현 케이스)'})
        call('resize_node', {'nodeId': hid, 'width': 393, 'height': 56})
        call('set_auto_layout', {'nodeId': hid, 'layoutMode': 'HORIZONTAL', 'paddingLeft': 20,
                                 'paddingRight': 20, 'primaryAxisAlignItems': 'SPACE_BETWEEN',
                                 'counterAxisAlignItems': 'CENTER'})
        call('set_layout_sizing', {'nodeId': hid, 'horizontal': 'FIXED', 'vertical': 'FIXED'})
        call('resize_node', {'nodeId': hid, 'width': 393, 'height': 56})
        # 🔴 fill = bg-primary (0-O — fill 없는 투명 Tool Bar 금지, 2026-08-20 사용자 지적)
        call('set_fill_color', {'nodeId': hid, 'color': {'r': 1, 'g': 1, 'b': 1, 'a': 1}})
        if _bg:
            call('set_bound_variables', {'nodeId': hid, 'bindings': {'fills/0': 'K:' + _bg[0]}})
        # 타이틀(비액션 라벨) 20px 재단언 (0-W — Body xl/SemiBold 가 정본)
        for t in tx:
            if (t.get('characters') or '').strip() in title_labels:
                call('set_font_size', {'nodeId': t['id'], 'fontSize': 20})
        # 실측 assert (룰 17: 호출 성공 ≠ 적용)
        chk = call('get_node_info', {'nodeId': hid}) or {}
        if round(chk.get('height') or 0) != 56 or not (chk.get('fills') or []):
            print(f'  🚩 [detect] toolbar-normalize-failed: {hid} h={chk.get("height")} — 수동 확인 필요')
            RUN_FLAGS.append(f'toolbar-normalize-failed: {hid} h={chk.get("height")} — 수동 확인 필요')
        else:
            print(f'  [swap] 텍스트 버튼 헤더 → Tool Bar 문법 정규화 ({hid}: {labels})')
        return hid
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


def fix_grid_cells(root_id):
    """393 확장 후 wrap 그리드 재편 (2026-08-14 라운지_검색 실측 — 3차 개정).
    ① wrap HORIZONTAL 의 등폭 FIXED 셀들을 열 수(cols)로 판정 ② 셀 FIXED 재계산이 아니라
    **행(Row) 구조로 재편 + 셀 FILL**(사용자: "그리드 아이템 width 가 fill 이 아니잖아")
    ③ 셀 세로 HUG ④ Thumbnail 은 1:1 비율(높이=셀 폭) 재단언.
    wrap 에서 FILL 은 4-up 붕괴하므로 반드시 행 분해가 선행되어야 한다(실측)."""
    fixed = [0]
    def walk(nid, d=0):
        if d > 10:
            return
        n = call('get_node_info', {'nodeId': nid}) or {}
        kids = [c for c in n.get('children', []) or [] if ';' not in (c.get('id') or '')]
        if n.get('layoutMode') == 'HORIZONTAL':
            pw0 = n.get('width') or 0
            # 🔴 오버레이 레이어 오폭 가드 (2026-08-18 장바구니 모달 실측): ABSOLUTE 자식과
            # 풀폭(부모의 60%+) 자식은 그리드 셀이 아니다 — 재편하면 852 레이어가 클립된다.
            cells = [c for c in kids if c.get('type') == 'FRAME'
                     and (c.get('layoutPositioning') or 'AUTO') != 'ABSOLUTE'
                     and (c.get('width') or 0) < pw0 * 0.6]
            ws = [round(c.get('width') or 0) for c in cells]
            if len(cells) >= 2 and len(set(ws)) == 1 and 40 < ws[0]:
                pw = pw0
                pad_l = n.get('paddingLeft') or 0
                pad_r = n.get('paddingRight') or 0
                g = n.get('itemSpacing') or 0
                cols = max(1, int((pw - pad_l - pad_r + g) // (ws[0] + g)))
                cols = min(cols, len(cells))
                if cols < len(cells):  # wrap 그리드 → 행 재편
                    lid = n['id']
                    call('set_auto_layout', {'nodeId': lid, 'layoutMode': 'VERTICAL',
                         'itemSpacing': 16, 'paddingLeft': pad_l, 'paddingRight': pad_r,
                         'paddingTop': n.get('paddingTop') or 0,
                         'paddingBottom': n.get('paddingBottom') or 0})
                    rows = []
                    for _ in range((len(cells) + cols - 1) // cols):
                        row = call('create_frame', {'x': 0, 'y': 0, 'width': 100, 'height': 100,
                                                    'name': 'Row', 'parentId': lid})
                        call('set_auto_layout', {'nodeId': row['id'], 'layoutMode': 'HORIZONTAL',
                                                 'itemSpacing': g})
                        call('set_layout_sizing', {'nodeId': row['id'],
                                                   'horizontal': 'FILL', 'vertical': 'HUG'})
                        call('set_fill_color', {'nodeId': row['id'], 'r': 0, 'g': 0, 'b': 0, 'a': 0})
                        rows.append(row['id'])
                    for i, c in enumerate(cells):
                        call('insert_child', {'parentId': rows[i // cols],
                                              'childId': c['id'], 'index': i % cols})
                        call('set_layout_sizing', {'nodeId': c['id'],
                                                   'horizontal': 'FILL', 'vertical': 'HUG'})
                        ci = call('get_node_info', {'nodeId': c['id']}) or {}
                        cw = round(ci.get('width') or ws[0])
                        for gch in ci.get('children', []) or []:
                            if (gch.get('name') or '') == 'Thumbnail':
                                call('set_layout_sizing', {'nodeId': gch['id'], 'horizontal': 'FILL'})
                                call('resize_node', {'nodeId': gch['id'],
                                                     'width': round(gch.get('width') or cw),
                                                     'height': cw})  # 1:1 비율
                        fixed[0] += 1
                    print(f'  [grid] {len(cells)}셀 → {len(rows)}행×{cols}열 재편(셀 FILL·썸네일 1:1)')
                    return  # 재편한 서브트리는 재방문 불필요
        for c in kids:
            walk(c['id'], d + 1)
    walk(root_id)


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


# 내비/헤더 텍스트 액션 버튼 라벨 (swap_app_bar skip · normalize_text_button_header 공유)
TEXT_BTN_ACTION_WORDS = ('취소', '올리기', '완료', '등록', '저장', '다음', '확인')


def _is_dialog_action_row(n):
    """chrome 없는 다이얼로그 액션 행/텍스트 버튼 판별 (2026-08-24 채팅_Modals 실측 —
    모달 '알림끄기/나가기' 행이 Primary 2xl 보라 CTA 로 오스왑. 눌림 상태(연회색
    하이라이트 fill #f3f5f7)까지 커버). 조건: 무채 연한 fill(투명/흰/≥0.9 연회색, 채도<0.05)
    + 보더 없음 + 단일 **진한 라벨**(text-primary 급, max ch<0.4).
    Disabled CTA 는 라벨이 밝은 회색/흰색이라 여기 안 걸린다. swap_cta 스킵과 diagnose
    raw-button 감지기가 같은 판정을 공유한다(스킵한 행을 flag 로 재고발하는 충돌 방지)."""
    fills = [f for f in (n.get('fills') or []) if isinstance(f, dict)
             and f.get('type') == 'SOLID' and f.get('visible') is not False]
    strokes = [s for s in (n.get('strokes') or []) if isinstance(s, dict)
               and s.get('type') == 'SOLID' and s.get('visible') is not False]
    if strokes:
        return False
    for f in fills:
        c = f.get('color') or {}
        vs = [c.get(k, 0) for k in 'rgb']
        if min(vs) < 0.9 or (max(vs) - min(vs)) > 0.05:
            return False
    kids = n.get('_children') or n.get('children') or []
    tx = [c for c in kids if c.get('type') == 'TEXT' and (c.get('characters') or '').strip()]
    if len(tx) != 1:
        return False
    lc = ((tx[0].get('fills') or [{}])[0] or {}).get('color') or {}
    return bool(lc) and max(lc.get(k, 1) for k in 'rgb') < 0.4


def swap_cta(root_tree):
    done = []
    cands = find_all(root_tree, lambda n: (n.get('name') or '').strip().lower() == 'button'
                     and n.get('type') == 'FRAME' and 24 <= round(n.get('height') or 0) <= 64
                     and n.get('visible') is not False)  # 숨김 노드는 스왑 금지 (2026-08-14 '선택' 버튼 노출 회귀)
    for b in cands:
        tx = texts_in(b)
        if len(tx) != 1:
            print(f'  [skip] raw Button {b["id"]} — 단일 라벨 아님(스왑 불가, raw 유지)')
            continue
        # 🔴 소형 라벨 버튼(수정/주소검색 등, h24~42) = Action Button **md** (2026-08-14 사용자
        # 지적 — CTA(h44+)만 버튼으로 정의했던 커버리지 구멍. md Outline 이 정본:
        # wallet-withdraw-user-baseline 룰 2). stroke+무채 fill → Outline, 유채 fill → Primary.
        if round(b.get('height') or 0) <= 42:
            info0 = call('get_node_info', {'nodeId': b['id']}) or {}
            if not info0.get('id'):
                print(f'  [skip] raw Button {b["id"]} — stale(이미 삭제됨)')
                continue
            # 내비/헤더 안 텍스트 버튼('확인' 등)은 raw 정본 문법 유지 — Action Button 스왑 금지
            # (2026-08-24 채팅 상대 선택 실측: 헤더 '확인'이 md Outline 으로 오스왑)
            _pn0 = (call('get_node_info', {'nodeId': info0.get('parentId')}) or {}).get('name') or ''
            if 'tool bar' in _pn0.lower() or 'app bar' in _pn0.lower():
                print(f'  [skip] raw Button {b["id"]} "{tx[0]["characters"]}" — 내비 텍스트 버튼(raw 유지)')
                continue
            def _chr(paints):
                ps = [f for f in (paints or []) if isinstance(f, dict)
                      and f.get('type') == 'SOLID' and f.get('visible') is not False]
                if not ps:
                    return 0
                c0 = ps[0].get('color', {})
                vs = [round(c0.get(k, 0) * 255) for k in 'rgb']
                return max(vs) - min(vs)
            fill_chr = _chr(info0.get('fills'))
            stroke_chr = _chr(info0.get('strokes'))
            # 🔴 위계 판정 (2026-08-18 사용자 교정 — 수정/주소검색 실측): 유채 fill → Primary,
            # 유채(보라) 보더 → **Secondary**(흰 면+보라 보더+보라 라벨), 무채 보더 → Outline.
            hier = 'Primary' if fill_chr >= 20 else ('Secondary' if stroke_chr >= 20 else 'Outline')
            label0 = tx[0]['characters']
            pid0 = info0.get('parentId')
            idx0 = child_index(pid0, b['id'])
            ab0 = new_instance(AB_SEC, pid0, idx0)
            call('delete_node', {'nodeId': b['id']})
            call('set_instance_properties', {'nodeId': ab0, 'properties': {
                'Hierarchy': hier, 'Size': 'md', 'State': 'Default', 'Label#17537:16': label0,
                '➡️ Icon trailing#3287:2338': False, '⬅️ Icon leading#3287:1577': False,
                'Loading text#8994:0': False}})
            print(f'  [swap] Action Button md {hier} "{label0}" ← 소형 raw Button ({b["id"]})')
            done.append(ab0)
            continue
        label = tx[0]['characters']
        if _is_dialog_action_row(b):
            print(f'  [skip] raw Button {b["id"]} "{label}" — chrome 없는 다이얼로그 액션 행/'
                  f'텍스트 버튼(눌림 하이라이트 포함), raw 유지')
            continue
        info = call('get_node_info', {'nodeId': b['id']}) or {}
        if not info.get('id'):
            print(f'  [skip] raw Button {b["id"]} — stale(이미 삭제됨)')
            continue
        bf = [f for f in (info.get('fills') or []) if isinstance(f, dict) and f.get('type') == 'SOLID'
              and f.get('visible') is not False]
        # 원본 raw 버튼 fill 이 밝으면(연보라 등) Disabled 상태 (2026-08-14 리뷰작성 실측)
        state = 'Default'
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
    jobs = []  # (nodeId, field, 'K:key') — 끝에서 batch_bind_variables 1콜 (2026-08-24 배치화)
    # 1콜 트리 우선 (2026-08-24 성능 수리) — 노드당 get_node_info+get_bound_variables 왕복 제거
    _tree = L.fetch_tree(root_id)

    def walk(src, d=0):
        nonlocal bound
        if d > 12:
            return
        n = src if isinstance(src, dict) else (call('get_node_info', {'nodeId': src}) or {})
        nid2 = n.get('id') or ''
        name = n.get('name') or ''
        if name in allow:
            return
        t = n.get('type')
        if ';' not in nid2 and t in ('FRAME', 'TEXT', 'RECTANGLE', 'ELLIPSE', 'VECTOR', 'LINE',
                                     'BOOLEAN_OPERATION', 'STAR', 'POLYGON'):
            if isinstance(src, dict):
                bv = n.get('boundVariables') or {}
            else:
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
                            jobs.append({'nodeId': nid2, 'bindings': {'fills/0': 'K:' + KM[path]}})
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
                        jobs.append({'nodeId': nid2, 'bindings': {'strokes/0': 'K:' + KM[path]}})
                    else:
                        left.append((name, t, 'stroke', hx))
        for c in n.get('children', []) or []:
            if isinstance(src, dict):
                if c.get('type') != 'INSTANCE' and ';' not in (c.get('id') or ''):
                    walk(c, d + 1)
            else:
                walk(c['id'], d + 1)
    walk(_tree if _tree else root_id)
    # batch 1콜 적용 (2026-08-24 — 123건 개별 콜 → 1콜. K: 키는 플러그인 배치 리졸버가 임포트)
    if jobs:
        br = call('batch_bind_variables', {'items': jobs}) or {}
        ok_n = br.get('succeeded')
        if ok_n is None:
            # 구버전 플러그인(K: 미지원/batch items 형식 차이) 폴백 — 단건 순차
            ok_n = 0
            for j in jobs:
                try:
                    call('set_bound_variables', j)
                    ok_n += 1
                except Exception:
                    pass
        bound += int(ok_n or 0)
        if br.get('failed'):
            print(f"  [sweep] ⚠️ batch 실패 {br.get('failed')}건 — 수동 확인 필요")
    print(f'  [sweep] 잔여 스냅 바인딩 {bound}건' + (f' / 미해결 {len(left)}건: {left[:6]}' if left else ''))
    return left

# ── 진단 (detect → fable 이 사고하며 수정) ──────────────────────────────────
# 🔴 2026-08-14 사용자 방향 전환: "스크립트로 돌렸을 때 문제가 생기면 detecting 해서
# 생각하고 사고해서 수정하는 쪽으로". 스크립트는 기계 실행 + 이상 감지까지만 담당하고,
# 감지된 flag 는 마지막 CONVERT-SUMMARY-JSON 에 실려 모델(fable)이 항목별로 판단·수정한다.
def diagnose(src_id, gen_id):
    """실측된 실패 클래스 감지기. 반환: flag 문자열 리스트 (비면 이상 없음)."""
    flags = []
    gen = call('get_node_info', {'nodeId': gen_id}) or {}
    gx0 = (gen.get('absoluteBoundingBox') or {}).get('x') or 0

    stats = {'maxx': 0, 'grid_fixed': [], 'strike_gen': 0, 'raw_buttons': [], 'clipped': [],
             'raw_tabbars': []}

    # 1콜 트리 우선 (2026-08-24 성능 수리) — dict 면 로컬 순회, str(id) 면 노드 단위 폴백
    def walk_gen(src, d=0, pname=''):
        if d > 10:
            return
        is_dict = isinstance(src, dict)
        n = src if is_dict else (call('get_node_info', {'nodeId': src}) or {})
        bb = n.get('absoluteBoundingBox') or {}
        if bb.get('x') is not None:
            stats['maxx'] = max(stats['maxx'], (bb.get('x') or 0) + (bb.get('width') or 0) - gx0)
        kids = [c for c in n.get('children', []) or [] if ';' not in (c.get('id') or '')]
        # wrap 그리드 잔존: HORIZONTAL 에 등폭 FIXED 셀이 열수보다 많이 남음
        if n.get('layoutMode') == 'HORIZONTAL':
            cells = [c for c in kids if c.get('type') == 'FRAME'
                     and (c if is_dict else (call('get_node_info', {'nodeId': c['id']}) or {}))
                     .get('layoutSizingHorizontal') == 'FIXED']
            ws = [round(c.get('width') or 0) for c in cells]
            if len(cells) >= 3 and len(set(ws)) == 1 and ws[0] > 40:
                stats['grid_fixed'].append(n['id'])
        # 클립 의심: 화면급 자식(h>=700)이 낮은 컨테이너에 들어가 잘림 (2026-08-18 모달 오폭 실측)
        ph = n.get('height') or 0
        for c in kids:
            if c.get('type') == 'FRAME' and (c.get('height') or 0) >= 700 and 0 < ph < (c.get('height') or 0) - 50 \
                    and (c.get('layoutPositioning') or 'AUTO') != 'ABSOLUTE':
                stats['clipped'].append(n['id'])
                break
        # raw Button 잔존 (스왑 커버리지 감시 — 2026-08-14 수정/주소검색 실측)
        # 내비/헤더('Tool Bar'/'App bar' 부모) 안 텍스트 버튼은 raw 정본 문법 — 재고발 금지
        # (2026-08-24: swap 이 의도적으로 skip 한 '확인'을 flag 로 되살리던 충돌)
        _in_nav = 'tool bar' in pname.lower() or 'app bar' in pname.lower()
        if n.get('type') == 'FRAME' and (n.get('name') or '').strip().lower() == 'button' \
                and 24 <= round(n.get('height') or 0) <= 64 and n.get('visible') is not False \
                and not _is_dialog_action_row(n) and not _in_nav:
            stats['raw_buttons'].append(n['id'])
        # raw 하단 탭바/GNB 잔존 (2026-08-21 커뮤니티 실측 — Bar/GNB/Feed 가 무플래그 통과,
        # DS 'Tab bar' 인스턴스(0-M)로 교체돼야 함)
        _nm_l = (n.get('name') or '').lower()
        if n.get('type') == 'FRAME' and n.get('visible') is not False \
                and 56 <= round(n.get('height') or 0) <= 96 \
                and ('gnb' in _nm_l or 'tab bar' in _nm_l or 'tabbar' in _nm_l
                     or 'bottom nav' in _nm_l):
            stats['raw_tabbars'].append(n['id'])
        # 취소선 카운트 (트리 모드: 플러그인이 계산한 hasStrikethrough 플래그 사용)
        if n.get('type') == 'TEXT':
            if is_dict:
                if n.get('hasStrikethrough'):
                    stats['strike_gen'] += 1
            else:
                try:
                    segs = (call('get_styled_text_segments',
                                 {'nodeId': n['id'], 'property': 'textDecoration'}) or {}).get('segments') or []
                    if any(sg.get('textDecoration') == 'STRIKETHROUGH' for sg in segs):
                        stats['strike_gen'] += 1
                except Exception:
                    pass
        for c in kids:
            if is_dict:
                if c.get('type') != 'INSTANCE':
                    walk_gen(c, d + 1, n.get('name') or '')
            else:
                walk_gen(c['id'], d + 1, n.get('name') or '')

    _gen_tree = L.fetch_tree(gen_id)
    if _gen_tree:
        for c in _gen_tree.get('children', []) or []:
            if ';' not in (c.get('id') or '') and c.get('type') != 'INSTANCE':
                walk_gen(c)
    else:
        for c in gen.get('children', []) or []:
            if ';' not in (c.get('id') or ''):
                walk_gen(c['id'])

    # 원본 취소선 카운트
    strike_src = [0]

    def _count_strike_tree(nn):
        if nn.get('type') == 'TEXT' and nn.get('hasStrikethrough'):
            strike_src[0] += 1
        for c in nn.get('children') or []:
            if ';' not in (c.get('id') or '') and c.get('type') != 'INSTANCE':
                _count_strike_tree(c)

    def walk_src(nid, d=0):
        if d > 10:
            return
        n = call('get_node_info', {'nodeId': nid}) or {}
        if n.get('type') == 'TEXT':
            try:
                segs = (call('get_styled_text_segments',
                             {'nodeId': n['id'], 'property': 'textDecoration'}) or {}).get('segments') or []
                if any(sg.get('textDecoration') == 'STRIKETHROUGH' for sg in segs):
                    strike_src[0] += 1
            except Exception:
                pass
        for c in n.get('children', []) or []:
            if ';' not in (c.get('id') or ''):
                walk_src(c['id'], d + 1)

    _src_tree = L.fetch_tree(src_id)
    if _src_tree:
        _count_strike_tree(_src_tree)
    else:
        walk_src(src_id)

    if 0 < stats['maxx'] < 369:
        flags.append(f"left-pinned: 콘텐츠 우측 경계 {round(stats['maxx'])} < 369 — 360 잔재 의심")
    if stats['grid_fixed']:
        flags.append(f"grid-fixed-cells: 등폭 FIXED 셀 잔존 {stats['grid_fixed'][:3]} — 행 재편+FILL 필요")
    if strike_src[0] > stats['strike_gen']:
        flags.append(f"strikethrough-lost: 취소선 원본 {strike_src[0]}건 → 변환본 {stats['strike_gen']}건")
    if stats.get('clipped'):
        flags.append(f"clipped-content: 자식이 부모보다 큰 클립 의심 {stats['clipped'][:3]} — 구조 밀림/오폭 점검")
    if stats.get('raw_buttons'):
        flags.append(f"raw-button: DS 미스왑 raw Button 잔존 {stats['raw_buttons'][:4]} — Action Button 인스턴스로 교체")
    if stats.get('raw_tabbars'):
        flags.append(f"raw-tabbar: raw 하단 탭바/GNB 잔존 {stats['raw_tabbars'][:3]} — "
                     f"DS 'Tab bar' 인스턴스(0-M, active variant 키)로 교체 후 원본 삭제")
    return flags


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    _skip = set()
    for _i, _a in enumerate(sys.argv):
        if _a in ('--gap', '--allow') and _i + 1 < len(sys.argv):
            _skip.add(_i + 1)  # 옵션 값이 srcId 로 새지 않게 (2026-08-14 실측 버그)
    args = [a for _i, a in enumerate(sys.argv[1:], 1)
            if not a.startswith('--') and _i not in _skip]
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
        RUN_FLAGS.clear()  # 화면별 수집 — 스왑 단계 🚩 를 diagnose flags 와 합류
        _ts = time.time()
        _stage_t = {}

        def _lap(k):
            nonlocal _ts
            _stage_t[k] = round(time.time() - _ts, 1)
            _ts = time.time()

        cl = call('clone_node', {'nodeId': sid})
        rid = cl['id']
        call('insert_child', {'parentId': parent, 'childId': rid})
        call('move_node', {'nodeId': rid, 'x': right + gap + i * (393 + gap), 'y': y0})
        _lap('clone')
        tree = deep(rid)
        _lap('deep')
        swap_status_bar(tree)
        swap_app_bar(tree)
        normalize_text_button_header(tree)
        swap_sheet_headers(tree)
        swap_cta(tree)
        _lap('swaps')
        w, h = L.normalize_screen(rid)
        normalize_overlay(rid)
        fix_grid_cells(rid)
        print(f'  [normalize] {w}x{h}')
        n2 = call('get_node_info', {'nodeId': rid}) or {}
        for c in n2.get('children', []) or []:
            if (c.get('name') or '') == 'Contents':
                call('set_layout_sizing', {'nodeId': c['id'], 'vertical': 'FILL'})
        _lap('normalize')
        # 토큰 바인딩 — in-process 호출 (2026-08-24 성능 수리: subprocess 기동+세션 재초기화
        # +노드당 왕복이 장당 30s 병목이었음. 읽기는 get_node_tree 1콜)
        import bind_semantic_tokens as _bst
        _bst.run(rid)
        _lap('bind')
        sweep_unbound(rid, allow)
        _lap('sweep')
        flags = list(RUN_FLAGS) + diagnose(sid, rid)
        _lap('diagnose')
        print(f'  [⏱] {" ".join(f"{k}:{v}s" for k, v in _stage_t.items())}')
        for f in flags:
            print(f'  🚩 [detect] {f}')
        results.append({'src': sid, 'gen': rid, 'flags': flags})

    ok = True
    if not no_verify:
        for entry in results:
            rid = entry['gen']
            cmd = [sys.executable, os.path.join(_HERE, 'verify_bindings.py'), rid]
            eff_allow = set(allow) | ASSET_ALLOW_DEFAULT
            if eff_allow:
                cmd += ['--allow', ','.join(sorted(eff_allow))]
            r = subprocess.run(cmd, capture_output=True, text=True)
            tail = r.stdout.strip().splitlines()[-6:]
            print(f'-- verify {rid}')
            print('   ' + '\n   '.join(tail))
            entry['verify'] = 'PASS' if r.returncode == 0 else 'FAIL'
            ok = ok and (r.returncode == 0)
    gen_ids = [e['gen'] for e in results]
    n_flags = sum(len(e['flags']) for e in results)
    print(f'\n{"✓" if ok and not n_flags else "✗"} 변환 {len(results)}장 — {round(time.time()-t0, 1)}s → {gen_ids}')
    # 🔴 기계 판독 요약 — flags 는 fable 이 항목별로 사고하며 수정해야 하는 목록 (BUILD-SUMMARY 패턴)
    print('\n📋 CONVERT-SUMMARY-JSON')
    print(json.dumps({'type': 'convert-summary',
                      'result': 'ok' if ok and not n_flags else 'needs-review',
                      'screens': results,
                      'requiredActions': (
                          (['각 flags 항목을 fable 이 직접 판단·수정 후 해당 화면 재verify'] if n_flags else []) +
                          ['전 장(export_node_as_image → Read) 렌더를 원본과 대조 — N장이면 N장 전부'])},
                     ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
