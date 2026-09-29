#!/usr/bin/env python3
"""flow_connect.py — FigJam 커넥터·도형으로 화면 flow 를 잇는 원커맨드 (규칙 0-FLOW, 2026-09-23).

🔴 배경: Figma Design 에디터에서 플러그인은 CONNECTOR/SHAPE_WITH_TEXT 를 만들 수도(figma.createConnector
없음) 복제할 수도(clone: "not supported in the current editor") 없다(2026-09-18 실측 3종). 그러나
**플러그인으로 노드를 선택(focus_node)한 뒤 macOS 에서 Figma 메뉴 'Edit › Duplicate' 를 클릭**하면 같은
부모에 새 id 로 복제된다(사용자: "너가 cmd+d 해서 쓰면 안되는거야?" — ⌘D 키 입력은 플러그인 iframe 이
먹어 실패, 메뉴 클릭만 동작). 복제본은 `set_connector` 로 양끝·magnet·라벨을 재배선한다.

사용:
  python3 scripts/flow_connect.py <spec.json> [--dry-run]
  python3 scripts/figma_mcp_client.py flow <spec.json>
  python3 scripts/figma_mcp_client.py flow --fit <sectionId>     # 기존 도형을 텍스트에 맞춰 키우기(규칙 0-FLOW 도형 크기)

spec.json:
{
  "section": "4802:102913",                   # (선택) 화면·도형·커넥터가 사는 SECTION — 없으면 Figma 선택(섹션 또는 화면들의 부모)
  "toolbox": "4802:104148",                   # (선택) 템플릿 섹션 — 없으면 현재 페이지의 'my tool box' 자동 탐색
  "seed": {"CONNECTOR": "…"},                 # (선택) kind 별 복제 원본 override — 기본은 툴박스 템플릿(원본은 절대 소비 안 함)
  "shapes": [                                 # (선택) 새 도형 — 조건=DIAMOND, 화면 밖 단계/진입점=SQUARE, 외부 절차=PARALLELOGRAM
    {"key": "q_multi", "kind": "DIAMOND", "text": "두 계정 모두\\n스테이지 진행 중?",
     "anchor": "4802:104668", "dx": 10, "dy": 1180}   # anchor 화면 기준 오프셋 (또는 "x","y" 절대)
  ],
  "edges": [                                  # 화살표 — from/to 는 노드 id 또는 "@key"(위 shapes)
    {"type": "tap",                           # (선택) 화살표 용도 = scripts/flow_arrow_catalog.json 의 type (규칙 0-FLOW-2) — 생략 시 default
     "from": "4802:104417", "fromMagnet": "RIGHT", "to": "4802:103071", "toMagnet": "LEFT",
     "label": "동의 후 참여 계속 (UC04)", "lineType": "ELBOWED",
     "connector": "4544:87450"}               # (선택) 기존 커넥터를 재배선 — 없으면 풀/복제에서 할당
  ]
}

배치 관례(0-FLOW): 시작 = 화면 안 버튼/행 노드 RIGHT(또는 BOTTOM) → 끝 = 다음 화면 root LEFT. ⚠️ endpoint 는 **top-level
노드**(화면 root·화면 안 프레임·도형)만 — 인스턴스 내부 노드(`I…;…`)는 'Invalid endpointNodeId'. 화면 BOTTOM → 바로 아래
도형은 TOP 이 아니라 LEFT/RIGHT 로(BOTTOM→TOP 은 라우팅 폭주 실측). 조건 분기는
DIAMOND(라벨 '네'/'아니요 → …'), 화면 밖 진입점·단계는 SQUARE, 본인확인 같은 외부 절차는 PARALLELOGRAM.
도형은 화면 밴드 아래(y ≈ 화면 y + 1180)에 anchor 화면 기준으로 둔다. 🔴 **먼 화면(3슬롯 이상)을 BOTTOM→BOTTOM
으로 잇지 말 것** — Figma 가 elbow 를 화면 중간 높이에 잡아 화면을 가로지른다(2026-09-18 실측). 슬롯 순서를
바꿔 인접시키고 RIGHT→LEFT 로 잇는다(스크립트가 WARN).
🔴 자원 규칙(2026-09-23 사용자): flow 를 이을 땐 **현재 페이지 `my tool box` 섹션의 도형·화살표를 템플릿으로 삼아
필요한 수만큼 복제**한다 — 원본을 옮겨 쓰지 않는다(consumePool 은 레거시, 기본 off). 복제는 플러그인 clone_node
(Design 에디터에서 CONNECTOR 불가)가 아니라 **focus_node + macOS 메뉴 Edit › Duplicate 클릭**(duplicate_via_menu).
파이프라인: 섹션 자식 1회 조회 → 툴박스 탐색 → 계획(kind 별 복제 수) → 메뉴 Duplicate(맥 전용) → 복제본을 섹션으로
insert → 도형 move/텍스트 → set_connector → 남은 복제본 삭제 → FLOW-SUMMARY JSON. macOS 가 아니면 복제 단계에서
멈추고 사용자에게 FigJam 복사·붙여넣기를 요청한다.
오프라인 테스트: scripts/tests/test_flow_connect.py.
"""
import json
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

SLOT = 1050
LONG_EDGE_SLOTS = 3
SHAPE_KINDS = ('DIAMOND', 'SQUARE', 'PARALLELOGRAM', 'ROUNDED_RECTANGLE', 'ELLIPSE')
TOOLBOX_NAME = 'my tool box'     # 현재 페이지의 템플릿 섹션 — 원본은 절대 소비하지 않고 메뉴 Duplicate 로 복제해서 쓴다
DEFAULT_LINE = 'ELBOWED'
TERMINAL_APP = 'Orca'


# ── 순수 계획 ───────────────────────────────────────────────────────────────────
def kind_of(node):
    """CONNECTOR | DIAMOND | SQUARE | PARALLELOGRAM(_RIGHT/_LEFT 통합) | … | None"""
    if node.get('type') == 'CONNECTOR':
        return 'CONNECTOR'
    if node.get('type') == 'SHAPE_WITH_TEXT':
        st = (node.get('shapeType') or 'SQUARE').upper()
        return 'PARALLELOGRAM' if st.startswith('PARALLELOGRAM') else st
    return None


def templates_of(toolbox_children):
    """툴박스 자식 → kind 별 템플릿(첫 노드) id."""
    out = {}
    for n in toolbox_children:
        k = kind_of(n)
        if k and k not in out:
            out[k] = n['id']
    return out


def build_plan(spec, section_children, toolbox_children=()):
    """규칙 0-FLOW: 툴박스(`my tool box`)의 도형·화살표는 **템플릿** — 원본을 옮겨 쓰지 않고 필요한 수만큼
    macOS 메뉴 Duplicate 로 복제한다. 반환 plan(dict). MCP 호출 없음.
    seed 우선순위: spec.seed[kind] > 툴박스 템플릿 > (consumePool 레거시) 섹션 안 기존 노드."""
    edges = spec.get('edges') or []
    shapes = spec.get('shapes') or []
    for sh in shapes:
        if not sh.get('key') or sh.get('kind', '').upper() not in SHAPE_KINDS:
            raise ValueError(f"shapes 항목에 key/kind(DIAMOND|SQUARE|PARALLELOGRAM…) 필요: {sh}")
    for e in edges:
        for k in ('from', 'to'):
            v = e.get(k)
            if not v:
                raise ValueError(f'edge 에 {k} 없음: {e}')
            if str(v).startswith('@') and v[1:] not in {sh['key'] for sh in shapes}:
                raise ValueError(f"edge {k}='{v}' 가 shapes key 에 없음")
    # 커넥터 필요 수를 화살표 type(카탈로그 템플릿)별로 센다 — 'CONNECTOR' 는 type 미지정(카탈로그 default 또는 툴박스 첫 커넥터)
    cat = spec.get('_catalog')
    if cat is None:
        try:
            import flow_arrow_catalog as FAC
            cat = FAC.load()
        except Exception:
            cat = {'arrows': {}, 'default': None}
    need = {}
    for e in edges:
        if e.get('connector'):
            continue
        t = e.get('type') or cat.get('default')
        if t:
            if t not in (cat.get('arrows') or {}):
                raise ValueError(f"edge {e.get('from')}→{e.get('to')}: 화살표 type '{t}' 미등록 — 등록된 type: {sorted(cat.get('arrows') or {})} (arrow-register)")
            k = 'CONNECTOR:' + t
        else:
            k = 'CONNECTOR'
        need[k] = need.get(k, 0) + 1
    for sh in shapes:
        need[sh['kind'].upper()] = need.get(sh['kind'].upper(), 0) + 1
    need = {k: v for k, v in need.items() if v > 0}
    tpl = templates_of(toolbox_children)
    seed = dict(spec.get('seed') or {})
    alloc, dup, missing = {}, {}, []
    pool = {}
    if spec.get('consumePool'):   # 레거시: 툴박스 노드를 직접 소비 (기본 False — 규칙 0-FLOW 위반이라 명시 시에만)
        for n in toolbox_children:
            k = kind_of(n)
            if k:
                pool.setdefault(k, []).append(n['id'])
    for k, cnt in need.items():
        have = pool.get(k, [])[:cnt]
        alloc[k] = have
        dup[k] = cnt - len(have)
        if dup[k] > 0 and not seed.get(k):
            if k.startswith('CONNECTOR:'):
                seed[k] = cat['arrows'][k.split(':', 1)[1]]['templateId']   # 카탈로그 템플릿(용도별 화살표)
            elif tpl.get(k):
                seed[k] = tpl[k]
            else:
                cand = [n['id'] for n in section_children if kind_of(n) == k]
                if cand:
                    seed[k] = cand[0]   # 툴박스에 없으면 섹션 안 기존 노드를 템플릿으로(복제만, 소비 안 함)
                else:
                    missing.append(k)
    if missing:
        raise ValueError(f"'{TOOLBOX_NAME}' 에 {', '.join(missing)} 템플릿이 없음 — 사용자에게 FigJam 에서 해당 도형/화살표를 복사해 '{TOOLBOX_NAME}' 섹션에 붙여 달라고 요청 (플러그인은 생성·clone 불가)")
    byid = {n['id']: n for n in section_children}
    shape_kind = {'@' + sh['key']: sh['kind'].upper() for sh in shapes}
    # 화살표 type 제약(규칙 0-FLOW-2): 예) cond-yes 는 시작이 ◇ 여야 한다 — 위반은 ERROR
    def _kind_of_ref(ref):
        if str(ref).startswith('@'):
            return shape_kind.get(ref)
        n = byid.get(ref)
        return kind_of(n) if n else None
    for e in edges:
        t = e.get('type') or cat.get('default')
        cons = ((cat.get('arrows') or {}).get(t) or {}).get('constraints') or {}
        if cons.get('fromKind'):
            fk = _kind_of_ref(e.get('from'))
            if fk is None and not str(e.get('from')).startswith('@') and e.get('from') not in byid:
                pass   # 화면 내부 노드 등 섹션 직계가 아니면 판정 불가 — 통과
            elif fk != cons['fromKind']:
                raise ValueError(f"edge {e.get('from')}→{e.get('to')}: type '{t}' 은 시작이 {cons['fromKind']} 여야 함(현재 {fk or '화면/노드'}) — 규칙 0-FLOW-2")
        if cons.get('fromMagnet'):   # 2026-09-23 사용자 룰: ◇ 의 '예'는 RIGHT, '아니오'는 BOTTOM 에서만 시작 (같은 면에서 나가면 안 됨)
            fm = (e.get('fromMagnet') or cons['fromMagnet']).upper()
            if fm != cons['fromMagnet']:
                raise ValueError(f"edge {e.get('from')}→{e.get('to')}: type '{t}' 은 시작 magnet 이 {cons['fromMagnet']} 여야 함(현재 {fm}) — 예=RIGHT, 아니오=BOTTOM (규칙 0-FLOW-2)")
        if cons.get('notFromKind'):
            fk = _kind_of_ref(e.get('from'))
            if fk is not None and fk == cons['notFromKind']:
                raise ValueError(f"edge {e.get('from')}→{e.get('to')}: type '{t}' 은 {cons['notFromKind']} 에서 나갈 수 없음 — 조건 가지는 cond-yes/cond-no (규칙 0-FLOW-2)")
        if cons.get('toKind'):
            tk = _kind_of_ref(e.get('to'))
            if tk is not None and tk != cons['toKind']:
                raise ValueError(f"edge {e.get('from')}→{e.get('to')}: type '{t}' 은 끝이 {cons['toKind']} 여야 함(현재 {tk}) — 규칙 0-FLOW-2")
    warnings = []
    # 라벨 관례(0-FLOW-2): cond-yes 는 '네', cond-no 는 '아니요' 로 시작 — 어기면 WARN
    for e in edges:
        t = e.get('type') or cat.get('default')
        lab = (e.get('label') or '').strip()
        if t == 'cond-yes' and lab and not lab.startswith('네'):
            warnings.append(f"edge {e.get('from')}→{e.get('to')}: cond-yes 라벨은 '네 → …' 로 시작해야 함 (현재 '{lab[:20]}')")
        if t == 'cond-no' and lab and not lab.startswith('아니요'):
            warnings.append(f"edge {e.get('from')}→{e.get('to')}: cond-no 라벨은 '아니요 → …' 로 시작해야 함 (현재 '{lab[:20]}')")
        if t in ('cond-yes', 'cond-no') and not lab:
            warnings.append(f"edge {e.get('from')}→{e.get('to')}: {t} 는 라벨('네/아니요 → …') 필수")
    # ◇ 완결성: 이 spec 에서 만드는 ◇ 마다 cond-yes 와 cond-no 가 하나씩은 나가야 함 — 어기면 WARN
    for sh in shapes:
        if sh['kind'].upper() != 'DIAMOND':
            continue
        outs = {(e.get('type') or cat.get('default')) for e in edges if e.get('from') == '@' + sh['key']}
        missing = [t for t in ('cond-yes', 'cond-no') if t not in outs]
        if missing and (cat.get('arrows') or {}):
            warnings.append(f"◇ @{sh['key']}: 나가는 가지에 {', '.join(missing)} 없음 — 조건 도형은 네/아니요 둘 다 있어야 함")
    for e in edges:
        a, b = byid.get(e.get('from')), byid.get(e.get('to'))
        if a and b and abs((a.get('x') or 0) - (b.get('x') or 0)) >= LONG_EDGE_SLOTS * SLOT and \
                (e.get('fromMagnet', 'RIGHT').upper() == 'BOTTOM' and e.get('toMagnet', 'LEFT').upper() == 'BOTTOM'):
            warnings.append(f"edge {e.get('from')}→{e.get('to')}: {LONG_EDGE_SLOTS}슬롯 이상 BOTTOM→BOTTOM — 화면을 가로지름. 슬롯 인접 후 RIGHT→LEFT 권장")
    for e in edges:   # 2026-09-23 실측: BOTTOM→TOP 은 도형이 시작 노드 바로 아래(x 범위 겹침)면 정상, x 가 어긋나면 elbow 폭주(bbox -85k) → 그때만 경고
        if e.get('fromMagnet', 'RIGHT').upper() == 'BOTTOM' and e.get('toMagnet', 'LEFT').upper() == 'TOP' and str(e.get('to', '')).startswith('@'):
            a = byid.get(e.get('from'))
            sh = next((x for x in shapes if '@' + x['key'] == e.get('to')), None)
            if a and sh and 'x' in sh:
                ax0, ax1 = (a.get('x') or 0), (a.get('x') or 0) + (a.get('width') or 393)
                if not (ax0 - 40 <= int(sh['x']) <= ax1):
                    warnings.append(f"edge {e.get('from')}→{e.get('to')}: BOTTOM→TOP 인데 도형 x({sh['x']})가 시작 노드 x 범위({round(ax0)}~{round(ax1)}) 밖 — 라우팅 폭주 실측, toMagnet 을 LEFT/RIGHT 로")
            else:
                warnings.append(f"edge {e.get('from')}→{e.get('to')}: BOTTOM→TOP(도형) — 도형이 시작 노드 바로 아래가 아니면 라우팅 폭주 실측, 결과 bbox 확인")
    return {'need': need, 'alloc': alloc, 'dup': dup, 'seed': seed, 'templates': tpl, 'warnings': warnings,
            'edges': len(edges), 'shapes': len(shapes)}


SHAPE_FONT_PX = 17          # FigJam 도형 기본 텍스트 크기 근사(플러그인이 shapeFontSize 를 주면 그 값 사용)
SHAPE_LINE_H = 1.45
SHAPE_MIN = {'DIAMOND': (304, 264), 'SQUARE': (297, 142), 'PARALLELOGRAM': (320, 176), 'ROUNDED_RECTANGLE': (297, 142), 'ELLIPSE': (297, 142)}


def text_metrics(text, fs=SHAPE_FONT_PX):
    """줄별 근사 폭(한글·전각 1.0fs, 영숫자 0.55fs, 공백 0.3fs, 기타 0.6fs)과 높이 → (max_w, h)."""
    lines = (text or '').split('\n') or ['']
    def cw(ch):
        o = ord(ch)
        if ch == ' ':
            return 0.3
        if 0xAC00 <= o <= 0xD7A3 or 0x3130 <= o <= 0x318F or 0x4E00 <= o <= 0x9FFF or 0xFF00 <= o <= 0xFFEF:
            return 1.0
        if ch.isalnum():
            return 0.58
        return 0.55
    w = max(sum(cw(c) for c in ln) for ln in lines) * fs
    return w, len(lines) * fs * SHAPE_LINE_H


def shape_size_for_text(kind, text, cur=(0, 0), fs=SHAPE_FONT_PX):
    """규칙 0-FLOW: 도형 텍스트가 잘리지(…) 않도록 필요한 (w,h) — 현재 크기보다 크면 그 값, 아니면 현재 크기.
    DIAMOND 는 내접 텍스트 박스가 폭·높이의 절반이라 2배, PARALLELOGRAM 은 빗변 여유 80, 나머지는 여백 40/32."""
    tw, th = text_metrics(text, fs)
    kind = (kind or 'SQUARE').upper()
    if kind == 'DIAMOND':
        need = (2 * tw * 1.1 + 24, 2 * th * 1.1 + 24)   # 10% 여유(근사 오차)
    elif kind.startswith('PARALLELOGRAM'):
        need = (tw + 80, th + 32)
    else:
        need = (tw + 40, th + 32)
    mn = SHAPE_MIN.get('PARALLELOGRAM' if kind.startswith('PARALLELOGRAM') else kind, (297, 142))
    w = max(cur[0] or 0, mn[0], int(round(need[0])))
    h = max(cur[1] or 0, mn[1], int(round(need[1])))
    return w, h


def fit_shape(call, nid, text=None, log=print):
    """도형 1개를 텍스트에 맞춰 키운다(작아지진 않음). 반환 (before, after)."""
    i = call('get_node_info', {'nodeId': nid})
    if i.get('type') != 'SHAPE_WITH_TEXT':
        return None
    kind = (i.get('shapeType') or 'SQUARE').upper()
    txt = text if text is not None else (i.get('shapeText') or '')
    fs = i.get('shapeFontSize') if isinstance(i.get('shapeFontSize'), (int, float)) else SHAPE_FONT_PX
    cur = (i.get('width') or 0, i.get('height') or 0)
    w, h = shape_size_for_text(kind, txt, cur, fs)
    if (w, h) != (round(cur[0]), round(cur[1])) and (w > cur[0] + 1 or h > cur[1] + 1):
        call('resize_node', {'nodeId': nid, 'width': w, 'height': h})
        log(f"  [fit-shape] {nid} {kind} {round(cur[0])}x{round(cur[1])} → {w}x{h} ({txt.splitlines()[0][:18]}…)")
        return cur, (w, h)
    return cur, cur


def fit_shapes_in(call, section_id, log=print):
    kids = call('get_node_tree', {'nodeId': section_id, 'maxDepth': 1}).get('children') or []
    changed = 0
    for k in kids:
        if k.get('type') == 'SHAPE_WITH_TEXT':
            r = fit_shape(call, k['id'], log=log)
            if r and r[0] != r[1]:
                changed += 1
    return changed


def shape_position(shape, anchor_node=None):
    if 'x' in shape and 'y' in shape:
        return int(shape['x']), int(shape['y'])
    if anchor_node is None:
        raise ValueError(f"shape {shape.get('key')}: x/y 또는 anchor 필요")
    return int((anchor_node.get('x') or 0) + shape.get('dx', 48)), int((anchor_node.get('y') or 0) + shape.get('dy', 1180))


def osascript_duplicate_cmd():
    """Figma 메뉴 'Edit › Duplicate' 클릭 AppleScript (키 입력 ⌘D 는 플러그인 iframe 이 먹어 불가)."""
    return ['osascript',
            '-e', 'tell application "Figma" to activate',
            '-e', 'delay 0.4',
            '-e', 'tell application "System Events" to tell process "Figma" to click menu item "Duplicate" of menu "Edit" of menu bar 1']


# ── 실행 ────────────────────────────────────────────────────────────────────────
def find_toolbox(call):
    """현재 페이지에서 `my tool box` 섹션을 찾는다(find_nodes_by_name; 여러 개면 자식이 가장 많은 것)."""
    r = call('find_nodes_by_name', {'name': TOOLBOX_NAME, 'matchMode': 'exact'})
    hits = [m for m in (r.get('matches') or []) if m.get('type') in ('SECTION', 'FRAME')]
    if not hits:
        r = call('find_nodes_by_name', {'name': TOOLBOX_NAME})
        hits = [m for m in (r.get('matches') or []) if m.get('type') in ('SECTION', 'FRAME')]
    if not hits:
        return None
    best, bc = None, -1
    for h in hits:
        kids = call('get_node_tree', {'nodeId': h['id'], 'maxDepth': 1}).get('children') or []
        c = sum(1 for k in kids if kind_of(k))
        if c > bc:
            best, bc = h['id'], c
    return best


def resolve_section_from_selection(call):
    """spec.section 이 없으면 Figma 선택에서: SECTION 이면 그것, 화면(FRAME)들이면 공통 부모."""
    sel = call('get_selection', {})
    nodes = sel.get('nodes') or sel.get('selection') or []
    if not nodes:
        raise RuntimeError('spec.section 이 없고 Figma 선택도 없음 — 섹션 또는 화면을 선택하거나 section 을 지정')
    if nodes[0].get('type') == 'SECTION':
        return nodes[0]['id']
    parents = {call('get_node_info', {'nodeId': n['id']}).get('parentId') for n in nodes}
    if len(parents) != 1:
        raise RuntimeError(f'선택 노드의 부모가 여러 개({len(parents)}) — 같은 섹션 안 노드만 선택')
    return parents.pop()


def accept_duplicate(sel_node, src_info, seen):
    """Duplicate 직후 선택 노드가 진짜 복제본인지 — 같은 type · 같은 부모 · 새 id 만 인정.
    2026-09-29 실사고: 선택이 잠깐 툴박스 SECTION 자체를 돌려줘 섹션이 '복제본'으로 오인돼 대상 섹션 안으로 옮겨짐."""
    if not sel_node or not isinstance(sel_node, dict):
        return False
    sid = sel_node.get('id')
    if not sid or sid == src_info.get('id') or sid in seen:
        return False
    if sel_node.get('type') != src_info.get('type'):
        return False
    par = sel_node.get('parentId')
    return par is None or par == src_info.get('parentId')


def duplicate_via_menu(call, src, n, log=print):
    """focus_node(src) → 메뉴 Duplicate ×n → 새 id 목록(get_selection + accept_duplicate 로 검증)."""
    if sys.platform != 'darwin':
        raise RuntimeError('메뉴 복제는 macOS 전용 — 사용자에게 FigJam 에서 커넥터/도형을 복사해 툴박스에 붙여 달라고 요청')
    out = []
    src_info = call('get_node_info', {'nodeId': src})
    if src_info.get('type') not in ('CONNECTOR', 'SHAPE_WITH_TEXT'):
        raise RuntimeError(f'복제 원본 {src} 가 CONNECTOR/SHAPE_WITH_TEXT 가 아님 ({src_info.get("type")})')
    call('focus_node', {'nodeId': src})
    time.sleep(0.5)
    for i in range(n):
        r = subprocess.run(osascript_duplicate_cmd(), capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f'osascript 실패(Accessibility 권한/Figma 미실행?): {r.stderr.strip()[:200]}')
        time.sleep(1.0)
        sel = call('get_selection', {})
        nodes = sel.get('nodes') or sel.get('selection') or []
        node = nodes[0] if nodes else None
        if node and node.get('id') and 'parentId' not in node:
            node = dict(node, **{k: v for k, v in call('get_node_info', {'nodeId': node['id']}).items() if k in ('type', 'parentId')})
        if accept_duplicate(node, src_info, set(out)):
            out.append(node['id'])
        else:
            log(f'  ⚠️ 복제 {i + 1}/{n} 미확인/거부 (selection={[(x.get("id"), x.get("type")) for x in nodes]})')
            call('focus_node', {'nodeId': src}); time.sleep(0.5)
    subprocess.run(['osascript', '-e', f'tell application "{TERMINAL_APP}" to activate'], capture_output=True)
    return out


def run(spec, dry_run=False, log=print):
    import figma_mcp_client as fc

    def call(t, a):
        return fc.parse_content(fc.call_tool(t, a)).get('json') or {}

    t0 = time.time()
    fc.ensure_session()
    sec = spec.get('section') or resolve_section_from_selection(call)
    kids = call('get_node_tree', {'nodeId': sec, 'maxDepth': 1}).get('children') or []
    tb_id = spec.get('toolbox')
    tb = (call('get_node_tree', {'nodeId': tb_id, 'maxDepth': 1}).get('children') or []) if tb_id else []
    if not templates_of(tb):   # 지정 툴박스가 비었거나 없음 → 현재 페이지 'my tool box' 자동 탐색
        auto = find_toolbox(call)
        if auto and auto != tb_id:
            tb_id = auto
            tb = call('get_node_tree', {'nodeId': tb_id, 'maxDepth': 1}).get('children') or []
    log(f"  [toolbox] {tb_id or '없음'} — 템플릿 {templates_of(tb)}")
    plan = build_plan(spec, kids, tb)
    for w in plan['warnings']:
        log('  ⚠️ ' + w)
    summary = {'section': sec, 'toolbox': tb_id, 'plan': {k: plan[k] for k in ('need', 'alloc', 'dup', 'seed', 'templates', 'warnings')}, 'shapes': {}, 'edges': [], 'errors': []}
    if dry_run:
        return summary

    # 1) 자원 확보: 풀 → 복제
    res = {k: list(v) for k, v in plan['alloc'].items()}
    for k, cnt in plan['dup'].items():
        if cnt > 0:
            log(f'  [dup] {k} ×{cnt} ← {plan["seed"][k]} (메뉴 Duplicate)')
            got = duplicate_via_menu(call, plan['seed'][k], cnt, log)
            if len(got) < cnt:
                summary['errors'].append(f'{k} 복제 {len(got)}/{cnt} — 나머지는 사용자 복사 필요')
            res[k] = res.get(k, []) + got
    for k, ids in res.items():
        for nid in list(ids):
            gi = call('get_node_info', {'nodeId': nid})
            if gi.get('type') not in ('CONNECTOR', 'SHAPE_WITH_TEXT'):   # 안전장치: 섹션/프레임은 절대 옮기거나 지우지 않음
                summary['errors'].append(f'자원 {nid} 가 {gi.get("type")} — 제외')
                ids.remove(nid); continue
            if gi.get('parentId') != sec:
                call('insert_child', {'childId': nid, 'parentId': sec})

    # 2) 도형
    byid = {n['id']: n for n in kids}
    keymap = {}
    for s in spec.get('shapes') or []:
        k = s['kind'].upper()
        if not res.get(k):
            summary['errors'].append(f"shape {s['key']}: {k} 자원 없음")
            continue
        nid = res[k].pop(0)
        x, y = shape_position(s, byid.get(s.get('anchor')))
        call('move_node', {'nodeId': nid, 'x': x, 'y': y})
        call('set_text_content', {'nodeId': nid, 'text': s['text']})
        fit_shape(call, nid, s['text'], log=log)   # 규칙 0-FLOW: 텍스트가 도형을 벗어나면 도형을 키운다
        call('rename_node', {'nodeId': nid, 'name': 'flow_' + s['text'].split('\n')[0][:16]})
        keymap[s['key']] = nid
        summary['shapes'][s['key']] = {'id': nid, 'x': x, 'y': y}

    # 3) 커넥터 배선
    def resolve(v):
        return keymap.get(v[1:], v) if str(v).startswith('@') else v
    try:
        import flow_arrow_catalog as FAC
        cat = FAC.load()
    except Exception:
        cat = {'arrows': {}, 'default': None}
    for e in spec.get('edges') or []:
        cid = e.get('connector')
        t = e.get('type') or cat.get('default')
        entry = (cat.get('arrows') or {}).get(t) if t else None
        d = (entry or {}).get('defaults') or {}
        if not cid:
            k = 'CONNECTOR:' + t if t else 'CONNECTOR'
            if not res.get(k):
                summary['errors'].append(f"edge {e.get('from')}→{e.get('to')}: 커넥터({k}) 부족")
                continue
            cid = res[k].pop(0)
        cons = (entry or {}).get('constraints') or {}
        r = call('set_connector', {'nodeId': cid, 'startNodeId': resolve(e['from']), 'startMagnet': e.get('fromMagnet', cons.get('fromMagnet', d.get('fromMagnet', 'RIGHT'))),
                                   'endNodeId': resolve(e['to']), 'endMagnet': e.get('toMagnet', d.get('toMagnet', 'LEFT')),
                                   'lineType': e.get('lineType', d.get('lineType', DEFAULT_LINE)), 'text': e.get('label', '')})
        ok = bool(r.get('applied') or r.get('id'))
        if ok:   # bbox 폭주 감지(페이지 밖으로 튄 elbow) — 실패로 기록해 재배선 유도
            g = call('get_node_info', {'nodeId': cid})
            if (g.get('x') or 0) < -5000 or (g.get('y') or 0) < -5000 or (g.get('width') or 0) > 20000 or (g.get('height') or 0) > 20000:   # 폭주 = 음수 큰 좌표/거대 bbox (넓은 섹션의 정상 x>20000 은 오탐이었음 2026-09-29)
                ok = False
                summary['errors'].append(f"connector {cid} bbox 폭주({round(g.get('x') or 0)},{round(g.get('y') or 0)},{round(g.get('width') or 0)}×{round(g.get('height') or 0)}) — magnet 조합 변경(BOTTOM→TOP 금지)")
        summary['edges'].append({'connector': cid, 'from': resolve(e['from']), 'to': resolve(e['to']), 'label': e.get('label', ''), 'ok': ok})
        if not ok and not (r.get('applied') or r.get('id')):
            hint = ' — 인스턴스 내부 노드(I…;…)는 endpoint 불가, 화면 root 나 도형을 쓸 것' if ';' in (str(e.get('from')) + str(e.get('to'))) else ''
            summary['errors'].append(f'set_connector 실패 {cid}: {str(r)[:120]}{hint}')
    # 4) 남은 복제본은 삭제 (툴박스 템플릿을 오염시키지 않음)
    leftovers = [nid for ids in res.values() for nid in ids]
    for nid in leftovers:
        if call('get_node_info', {'nodeId': nid}).get('type') in ('CONNECTOR', 'SHAPE_WITH_TEXT'):
            call('delete_node', {'nodeId': nid})
    summary['leftovers_deleted'] = leftovers
    summary['elapsed_s'] = round(time.time() - t0, 1)
    return summary


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 1
    if argv[0] == '--fit':   # 기존 섹션의 도형을 텍스트에 맞춰 키우기만
        import figma_mcp_client as fc
        fc.ensure_session()
        def _call(t, a):
            return fc.parse_content(fc.call_tool(t, a)).get('json') or {}
        n = fit_shapes_in(_call, argv[1])
        print(f'📋 FIT-SHAPES: {n}개 조정')
        return 0
    spec = json.load(open(argv[0], encoding='utf-8'))
    summary = run(spec, dry_run='--dry-run' in argv)
    print('📋 FLOW-SUMMARY')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary.get('errors'):
        print('✗ 일부 실패 — errors 확인 (커넥터 부족이면 사용자에게 FigJam 복사 요청)')
        return 1
    if not summary.get('plan', {}).get('warnings') is None and summary['plan']['warnings']:
        print('⚠️ 장거리 BOTTOM→BOTTOM 경고 — 섹션 export 로 화면 가로지름 여부 확인')
    return 0


if __name__ == '__main__':
    sys.exit(main())
