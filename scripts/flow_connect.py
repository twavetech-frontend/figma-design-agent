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

spec.json:
{
  "section": "4802:102913",                   # 화면·도형·커넥터가 사는 SECTION(부모)
  "toolbox": "4544:87444",                    # (선택) 사용자가 FigJam 에서 붙여 둔 여분 풀(먼저 소진)
  "seed": {"CONNECTOR": "4544:87446", "DIAMOND": "4544:87445", "SQUARE": "4544:87469"},
                                              # (선택) 풀이 모자랄 때 메뉴 Duplicate 할 원본 — 없으면 섹션에서 자동 탐색
  "shapes": [                                 # (선택) 새 도형 — 조건=DIAMOND, 화면 밖 단계/진입점=SQUARE, 외부 절차=PARALLELOGRAM
    {"key": "q_multi", "kind": "DIAMOND", "text": "두 계정 모두\\n스테이지 진행 중?",
     "anchor": "4802:104668", "dx": 10, "dy": 1180}   # anchor 화면 기준 오프셋 (또는 "x","y" 절대)
  ],
  "edges": [                                  # 화살표 — from/to 는 노드 id 또는 "@key"(위 shapes)
    {"from": "4802:104417", "fromMagnet": "RIGHT", "to": "4802:103071", "toMagnet": "LEFT",
     "label": "동의 후 참여 계속 (UC04)", "lineType": "ELBOWED",
     "connector": "4544:87450"}               # (선택) 기존 커넥터를 재배선 — 없으면 풀/복제에서 할당
  ]
}

배치 관례(0-FLOW): 시작 = 화면 안 버튼/행 노드 RIGHT(또는 BOTTOM) → 끝 = 다음 화면 root LEFT. 조건 분기는
DIAMOND(라벨 '네'/'아니요 → …'), 화면 밖 진입점·단계는 SQUARE, 본인확인 같은 외부 절차는 PARALLELOGRAM.
도형은 화면 밴드 아래(y ≈ 화면 y + 1180)에 anchor 화면 기준으로 둔다. 🔴 **먼 화면(3슬롯 이상)을 BOTTOM→BOTTOM
으로 잇지 말 것** — Figma 가 elbow 를 화면 중간 높이에 잡아 화면을 가로지른다(2026-09-18 실측). 슬롯 순서를
바꿔 인접시키고 RIGHT→LEFT 로 잇는다(스크립트가 WARN).
파이프라인: 섹션 자식 1회 조회 → 계획(풀 할당·복제 수) → 메뉴 Duplicate(맥 전용) → 도형 insert/move/텍스트 →
커넥터 insert → set_connector → FLOW-SUMMARY JSON. macOS 가 아니면 복제 단계에서 멈추고 사용자에게
FigJam 복사·붙여넣기를 요청한다.
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
DEFAULT_LINE = 'ELBOWED'
TERMINAL_APP = 'Orca'


# ── 순수 계획 ───────────────────────────────────────────────────────────────────
def kind_of(node):
    if node.get('type') == 'CONNECTOR':
        return 'CONNECTOR'
    if node.get('type') == 'SHAPE_WITH_TEXT':
        return (node.get('shapeType') or 'SQUARE').upper()
    return None


def build_plan(spec, section_children, toolbox_children=()):
    """풀(툴박스) 우선 할당 → 부족분은 seed 복제. 반환 plan(dict). MCP 호출 없음."""
    edges = spec.get('edges') or []
    shapes = spec.get('shapes') or []
    for s in shapes:
        if not s.get('key') or s.get('kind', '').upper() not in SHAPE_KINDS:
            raise ValueError(f"shapes 항목에 key/kind(DIAMOND|SQUARE|PARALLELOGRAM…) 필요: {s}")
    for e in edges:
        for k in ('from', 'to'):
            v = e.get(k)
            if not v:
                raise ValueError(f'edge 에 {k} 없음: {e}')
            if str(v).startswith('@') and v[1:] not in {s['key'] for s in shapes}:
                raise ValueError(f"edge {k}='{v}' 가 shapes key 에 없음")
    pool = {}
    for n in toolbox_children:
        k = kind_of(n)
        if k:
            pool.setdefault(k, []).append(n['id'])
    need = {'CONNECTOR': sum(1 for e in edges if not e.get('connector'))}
    for s in shapes:
        need[s['kind'].upper()] = need.get(s['kind'].upper(), 0) + 1
    alloc, dup = {}, {}
    for k, cnt in need.items():
        have = pool.get(k, [])[:cnt]
        alloc[k] = have
        dup[k] = cnt - len(have)
    seed = dict(spec.get('seed') or {})
    for k, cnt in dup.items():
        if cnt > 0 and not seed.get(k):
            cand = [n['id'] for n in section_children if kind_of(n) == k]
            if not cand:
                raise ValueError(f'{k} 복제 원본(seed) 없음 — 섹션에도 없음. 사용자에게 FigJam 에서 1개 붙여 달라고 요청')
            seed[k] = cand[0]
    byid = {n['id']: n for n in section_children}
    warnings = []
    for e in edges:
        a, b = byid.get(e.get('from')), byid.get(e.get('to'))
        if a and b and abs((a.get('x') or 0) - (b.get('x') or 0)) >= LONG_EDGE_SLOTS * SLOT and \
                (e.get('fromMagnet', 'RIGHT').upper() == 'BOTTOM' and e.get('toMagnet', 'LEFT').upper() == 'BOTTOM'):
            warnings.append(f"edge {e.get('from')}→{e.get('to')}: {LONG_EDGE_SLOTS}슬롯 이상 BOTTOM→BOTTOM — 화면을 가로지름. 슬롯 인접 후 RIGHT→LEFT 권장")
    return {'need': need, 'alloc': alloc, 'dup': dup, 'seed': seed, 'warnings': warnings,
            'edges': len(edges), 'shapes': len(shapes)}


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
def duplicate_via_menu(call, src, n, log=print):
    """focus_node(src) → 메뉴 Duplicate ×n → 새 id 목록(get_selection 으로 확인)."""
    if sys.platform != 'darwin':
        raise RuntimeError('메뉴 복제는 macOS 전용 — 사용자에게 FigJam 에서 커넥터/도형을 복사해 툴박스에 붙여 달라고 요청')
    out = []
    call('focus_node', {'nodeId': src})
    time.sleep(0.5)
    for i in range(n):
        r = subprocess.run(osascript_duplicate_cmd(), capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f'osascript 실패(Accessibility 권한/Figma 미실행?): {r.stderr.strip()[:200]}')
        time.sleep(1.0)
        sel = call('get_selection', {})
        ids = [x.get('id') for x in (sel.get('nodes') or sel.get('selection') or [])]
        if ids and ids[0] != src and ids[0] not in out:
            out.append(ids[0])
        else:
            log(f'  ⚠️ 복제 {i + 1}/{n} 미확인 (selection={ids})')
    subprocess.run(['osascript', '-e', f'tell application "{TERMINAL_APP}" to activate'], capture_output=True)
    return out


def run(spec, dry_run=False, log=print):
    import figma_mcp_client as fc

    def call(t, a):
        return fc.parse_content(fc.call_tool(t, a)).get('json') or {}

    t0 = time.time()
    fc.ensure_session()
    sec = spec['section']
    kids = call('get_node_tree', {'nodeId': sec, 'maxDepth': 1}).get('children') or []
    tb = []
    if spec.get('toolbox'):
        tb = call('get_node_info', {'nodeId': spec['toolbox']}).get('children') or []
    plan = build_plan(spec, kids, tb)
    for w in plan['warnings']:
        log('  ⚠️ ' + w)
    summary = {'section': sec, 'plan': {k: plan[k] for k in ('need', 'alloc', 'dup', 'seed', 'warnings')}, 'shapes': {}, 'edges': [], 'errors': []}
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
        for nid in ids:
            if call('get_node_info', {'nodeId': nid}).get('parentId') != sec:
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
        call('rename_node', {'nodeId': nid, 'name': 'flow_' + s['text'].split('\n')[0][:16]})
        keymap[s['key']] = nid
        summary['shapes'][s['key']] = {'id': nid, 'x': x, 'y': y}

    # 3) 커넥터 배선
    def resolve(v):
        return keymap.get(v[1:], v) if str(v).startswith('@') else v
    for e in spec.get('edges') or []:
        cid = e.get('connector')
        if not cid:
            if not res.get('CONNECTOR'):
                summary['errors'].append(f"edge {e.get('from')}→{e.get('to')}: 커넥터 부족")
                continue
            cid = res['CONNECTOR'].pop(0)
        r = call('set_connector', {'nodeId': cid, 'startNodeId': resolve(e['from']), 'startMagnet': e.get('fromMagnet', 'RIGHT'),
                                   'endNodeId': resolve(e['to']), 'endMagnet': e.get('toMagnet', 'LEFT'),
                                   'lineType': e.get('lineType', DEFAULT_LINE), 'text': e.get('label', '')})
        ok = bool(r.get('applied') or r.get('id'))
        summary['edges'].append({'connector': cid, 'from': resolve(e['from']), 'to': resolve(e['to']), 'label': e.get('label', ''), 'ok': ok})
        if not ok:
            summary['errors'].append(f'set_connector 실패 {cid}: {str(r)[:120]}')
    # 4) 남은 자원은 툴박스로
    leftovers = [nid for ids in res.values() for nid in ids]
    if leftovers and spec.get('toolbox'):
        for nid in leftovers:
            call('insert_child', {'childId': nid, 'parentId': spec['toolbox']})
    summary['leftovers'] = leftovers
    summary['elapsed_s'] = round(time.time() - t0, 1)
    return summary


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 1
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
