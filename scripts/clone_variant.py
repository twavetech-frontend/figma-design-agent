#!/usr/bin/env python3
"""clone_variant.py — 기존 DS 본 clone + 콘텐츠 치환 + 스테이지 색 + verify 1회 원커맨드 (2026-09-11).

🔴 배경 (사용자: "8분이나 걸렸어? 원인이 뭐야?"): 페이지에 같은 화면의 DS 본이 있을 때(0-G-3
clone 트랙) 손으로 clone → 트리 조회 → 텍스트 치환 → 삭제 → 색 재작업 → verify 6회를 돌려
8분이 걸렸다. 정당한 비용은 1~1.5분. 이 스크립트는 그 흐름을 **트리 1회 조회 + 최소 쓰기 +
verify 1회**로 고정한다(5분 SLA — 목표 ≤2분).

사용:
  python3 scripts/clone_variant.py <spec.json> [--dry-run]
  python3 scripts/figma_mcp_client.py clone-variant <spec.json>

spec.json 형식 (경로는 '/' 구분 이름 경로 — `이름[i]` 로 같은 이름 i번째(0-base),
`TEXT[i]` 로 i번째 TEXT 자식, ':' 가 든 값은 노드 id 그대로):
{
  "source": "4366:128696",                       # clone 할 기존 DS 본 id
  "name": "스테이지상세_참여전_빠른시작_DS",      # 새 root 이름
  "viewport": 852,                               # (선택) root FIXED 높이 + clipsContent
  "delete": ["초기화", "게시글", "Member list/Member row[1]/Gift Pill"],
  "texts": [
    {"path": "Pink Header/stagedetail/top/TEXT[0]", "text": "빠른시작합시다."},
    {"path": "Member list/Member row[1]/TEXT[0]", "text": "벨벨",
     "styleFrom": "Member list/Member row[0]/TEXT[0]"}   # 다른 TEXT 의 스타일(바인딩 포함)로 교체
  ],
  "pinBottom": ["stagedetail/arambubble"],       # ABSOLUTE, y = viewport - height (하단 고정 바)
  "stageMembers": "auto",                        # 13|9|7|5|"auto"(텍스트 '총 입금 13회' 추정)|null
  "stageColorTargets": ["Status Bar", "Pink Header", "순번", "Num circle"],   # (선택) 기본값
  "bindAssets": ["Info Cards/Info card[0]/ic_shield_plus"],   # (선택) 벡터 래퍼 페인트 토큰화
  "instanceProps": [{"path": "Member list/Member row[0]/Badge", "props": {"Label#17537:290": "남은 입금액 1,649,120원"}}],  # (선택) DS 인스턴스 prop(0-K)
  "allow": "Vector,Union",                       # (선택) verify --allow (일러스트 원값)
  "placement": "center"                          # center(0-H-3 기본) | right
}

파이프라인: clone → fetch_tree 1회 → 경로 해석(전부 그 트리에서) → 삭제/텍스트/스타일 복제 →
viewport/pinBottom → 스테이지 색(get_styles 1회) → 레거시 아이콘명 정규화 → bind_semantic_tokens
1회 → bindAssets → 배치 → verify_bindings 1회 → CLONE-VARIANT-SUMMARY JSON.
오프라인 테스트: scripts/tests/test_clone_variant.py (경로 해석·계획 수립은 MCP 없이 순수 함수).
"""
import json
import os
import re
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, 'design_rules'))

_SEG_RE = re.compile(r'^(.*?)(?:\[(\d+)\])?$')
DEFAULT_STAGE_TARGETS = ("Status Bar", "Pink Header", "Stage Header", "순번", "Num circle")


# ── 순수 함수 (오프라인 테스트 대상) ─────────────────────────────────────────────
def resolve_path(tree, path):
    """이름 경로 → 노드 dict. 못 찾으면 KeyError(경로 포함)."""
    if ':' in path and '/' not in path:
        hit = find_by_id(tree, path)
        if hit is None:
            raise KeyError(path)
        return hit
    cur = tree
    segs = [x for x in path.split('/') if x]
    i = 0
    while i < len(segs):
        # 레이어명에 '/' 가 흔함(stagedetail/top) → 남은 세그먼트를 가장 길게 이어 붙인 이름부터 매칭
        matched = None
        for k in range(len(segs) - i, 0, -1):
            seg = '/'.join(segs[i:i + k])
            m = _SEG_RE.match(seg)
            name, idx = m.group(1), int(m.group(2) or 0)
            kids = cur.get('children') or []
            if name == 'TEXT':
                cands = [c for c in kids if c.get('type') == 'TEXT']
            else:
                cands = [c for c in kids if c.get('name') == name]
            if cands:
                if idx >= len(cands):
                    raise KeyError(f"{path} — '{seg}' 없음 (후보 {len(cands)}개, 부모 '{cur.get('name')}')")
                matched, i = cands[idx], i + k
                break
        if matched is None:
            raise KeyError(f"{path} — '{segs[i]}' 없음 (부모 '{cur.get('name')}', 자식 {[c.get('name') for c in cur.get('children') or []][:8]})")
        cur = matched
    return cur


def find_by_id(tree, nid):
    if tree.get('id') == nid:
        return tree
    for c in tree.get('children') or []:
        r = find_by_id(c, nid)
        if r:
            return r
    return None


def walk(tree):
    yield tree
    for c in tree.get('children') or []:
        yield from walk(c)


def all_texts(tree):
    return [n.get('characters') for n in walk(tree) if n.get('type') == 'TEXT' and n.get('characters')]


def stage_targets(tree, names, deleted_ids=()):
    """이름이 targets 에 있는 노드 id 전부 (인스턴스 내부 제외, 삭제 예정 제외)."""
    out = []
    names = set(names)
    for n in walk(tree):
        if n.get('name') in names and n.get('id') not in deleted_ids and ';' not in str(n.get('id')):
            out.append(n['id'])
    return out


def build_plan(spec, tree):
    """spec + clone 트리 → 실행 계획(dict). MCP 호출 없음 — 테스트는 여기까지 검증한다."""
    import ds_catalog as C
    plan = {'delete': [], 'texts': [], 'pinBottom': [], 'stage': None, 'bindAssets': [], 'warnings': []}
    deleted = set()
    for p in spec.get('delete') or []:
        n = resolve_path(tree, p)
        plan['delete'].append({'path': p, 'id': n['id'], 'name': n.get('name')})
        deleted.add(n['id'])
    for t in spec.get('texts') or []:
        n = resolve_path(tree, t['path'])
        if n.get('type') != 'TEXT':
            raise ValueError(f"texts.path 가 TEXT 가 아님: {t['path']} ({n.get('type')})")
        item = {'path': t['path'], 'id': n['id'], 'text': t['text'], 'old': n.get('characters')}
        if t.get('styleFrom'):
            src = resolve_path(tree, t['styleFrom'])
            parent = _parent_of(tree, n['id'])
            idx = [c['id'] for c in parent.get('children') or []].index(n['id'])
            item.update({'styleFromId': src['id'], 'parentId': parent['id'], 'index': idx})
        plan['texts'].append(item)
    vp = spec.get('viewport')
    for p in spec.get('pinBottom') or []:
        n = resolve_path(tree, p)
        if not vp:
            raise ValueError('pinBottom 은 viewport 가 필요')
        plan['pinBottom'].append({'path': p, 'id': n['id'], 'y': vp - (n.get('height') or 0), 'x': 0})
    sm = spec.get('stageMembers')
    if sm == 'auto':
        sm = C.infer_stage_members(all_texts(tree))
        if sm is None:
            plan['warnings'].append("stageMembers=auto 인데 텍스트에서 인원수(5/7/9/13)를 못 찾음 — 색 유지")
    if sm:
        st = C.stage_color_style(sm)
        if not st:
            raise ValueError(f'stageMembers={sm} 에 정의된 스타일 없음 (5/7/9/13)')
        names = spec.get('stageColorTargets') or DEFAULT_STAGE_TARGETS
        plan['stage'] = {'members': int(sm), 'style': st, 'targets': stage_targets(tree, names, deleted)}
    for p in spec.get('bindAssets') or []:
        plan['bindAssets'].append(resolve_path(tree, p)['id'])
    plan['instanceProps'] = []
    for ip in spec.get('instanceProps') or []:   # [{"path": "...", "props": {"Label#17537:290": "..."}}] — DS 인스턴스 prop(0-K: prop 만)
        n = resolve_path(tree, ip['path'])
        plan['instanceProps'].append({'path': ip['path'], 'id': n['id'], 'props': ip['props']})
    return plan


def _parent_of(tree, nid, parent=None):
    if tree.get('id') == nid:
        return parent
    for c in tree.get('children') or []:
        r = _parent_of(c, nid, tree)
        if r is not None:
            return r
    return None


# ── 실행 ────────────────────────────────────────────────────────────────────────
def run(spec, dry_run=False, log=print):
    import figma_mcp_client as fc
    import ds_convert_lib as L
    import rebuild_track as RT

    def call(t, a):
        return fc.parse_content(fc.call_tool(t, a)).get('json') or {}

    t0 = time.time()
    summary = {'source': spec['source'], 'rootId': None, 'name': spec.get('name'), 'steps': [], 'verify': None}

    def step(name, start):
        summary['steps'].append({'step': name, 's': round(time.time() - start, 1)})

    # 0) 소스 트리로 계획 사전 검증 — 경로 오타면 clone 전에 실패(고아 clone 방지, 2026-09-11 실사고)
    s = time.time()
    src_tree = L.fetch_tree(spec['source']) or call('get_node_tree', {'nodeId': spec['source'], 'maxDepth': 25})
    build_plan(spec, src_tree)
    step('preflight', s)

    # 1) clone
    s = time.time()
    c = call('clone_node', {'nodeId': spec['source']})
    root = c.get('id')
    if not root:
        raise RuntimeError(f'clone 실패: {c}')
    summary['rootId'] = root
    if spec.get('name'):
        call('rename_node', {'nodeId': root, 'name': spec['name']})
    step('clone', s)

    # 2) 트리 1회 + 계획
    s = time.time()
    tree = L.fetch_tree(root) or call('get_node_tree', {'nodeId': root, 'maxDepth': 25})
    plan = build_plan(spec, tree)
    for w in plan['warnings']:
        log('  ⚠️ ' + w)
    step('tree+plan', s)
    if dry_run:
        call('delete_node', {'nodeId': root})
        summary['rootId'] = None
        summary['plan'] = plan
        return summary

    # 3) 텍스트 (styleFrom 은 소스 TEXT clone → 같은 자리에 삽입 → 원본 삭제)
    s = time.time()
    for t in plan['texts']:
        nid = t['id']
        if t.get('styleFromId'):
            cl = call('clone_node', {'nodeId': t['styleFromId']}).get('id')
            call('insert_child', {'childId': cl, 'parentId': t['parentId'], 'index': t['index']})
            call('delete_node', {'nodeId': nid})
            nid = cl
        call('set_text_content', {'nodeId': nid, 'text': t['text']})
    # 4) 삭제
    for d in plan['delete']:
        call('delete_node', {'nodeId': d['id']})
    for ip in plan['instanceProps']:
        call('set_instance_properties', {'nodeId': ip['id'], 'properties': ip['props']})
    step('texts+delete', s)

    # 5) viewport / pinBottom
    s = time.time()
    vp = spec.get('viewport')
    if vp:
        call('set_layout_sizing', {'nodeId': root, 'vertical': 'FIXED'})
        call('resize_node', {'nodeId': root, 'width': tree.get('width') or 393, 'height': vp})
        call('set_auto_layout', {'nodeId': root, 'layoutMode': tree.get('layoutMode') or 'VERTICAL', 'clipsContent': True})
    for p in plan['pinBottom']:
        call('set_layout_positioning', {'nodeId': p['id'], 'layoutPositioning': 'ABSOLUTE'})
        call('move_node', {'nodeId': p['id'], 'x': p['x'], 'y': p['y']})
    step('viewport', s)

    # 6) 스테이지 색 (get_styles 1회 — 이름 일치 우선, 키 폴백)
    s = time.time()
    if plan['stage']:
        st = plan['stage']['style']
        sid = None
        for sty in (RT.get_styles_cached().get('colors') or []):
            if sty.get('name') == st['name']:
                sid = sty.get('id') or ('S:%s,' % sty.get('key'))
                break
        sid = sid or ('S:%s,' % st['key'])
        for nid in plan['stage']['targets']:
            call('set_fill_style_id', {'nodeId': nid, 'fillStyleId': sid})
        summary['stage'] = {'members': plan['stage']['members'], 'style': st['name'], 'applied': len(plan['stage']['targets'])}
        log(f"  [stage-color] {plan['stage']['members']}명 → {st['name']} × {len(plan['stage']['targets'])}")
    step('stage-color', s)

    # 7) 아이콘명 정규화 + 토큰 바인딩 1회 + 에셋 페인트
    s = time.time()
    try:
        L.rename_legacy_icon_layers(root)
    except Exception as e:  # noqa: BLE001
        log(f'  ⚠️ rename_legacy_icon_layers: {e}')
    import bind_semantic_tokens as B
    B.run(root)
    flags = []
    cache = {}
    for wid in plan['bindAssets']:
        RT.bind_asset_paints(wid, cache, flags)
    for f in flags:
        log('  ' + f)
    step('bind', s)

    # 8) 배치 (0-H-3 기본 center)
    s = time.time()
    summary['placement'] = fc.position_new_root(root, mode=spec.get('placement'))
    step('place', s)

    # 9) verify 1회
    s = time.time()
    cmd = [sys.executable, os.path.join(_HERE, 'verify_bindings.py'), root]
    if spec.get('allow'):
        cmd += ['--allow', spec['allow']]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout or '') + (r.stderr or '')
    summary['verify'] = 'PASS' if '✓ PASS' in out else 'FAIL'
    summary['verifyTail'] = [ln for ln in out.splitlines() if ln.strip() and 'NotOpenSSL' not in ln and 'warnings.warn' not in ln][-12:]
    step('verify', s)
    summary['elapsed_s'] = round(time.time() - t0, 1)
    return summary


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 1
    dry = '--dry-run' in argv
    spec = json.load(open(argv[0], encoding='utf-8'))
    summary = run(spec, dry_run=dry)
    print('📋 CLONE-VARIANT-SUMMARY')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary.get('verify') == 'FAIL':
        print('✗ verify FAIL — allow 후보/미바인딩을 해소한 뒤 재실행 (완료 보고 금지)')
        return 1
    if summary.get('elapsed_s', 0) > 300:
        print('⚠️ 5분 SLA 초과')
    return 0


if __name__ == '__main__':
    sys.exit(main())
