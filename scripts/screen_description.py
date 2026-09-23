#!/usr/bin/env python3
"""screen_description.py — 화면 우측 디스크립션 instance + 섹션 넘버 마커 원커맨드 (규칙 0-DESC, 2026-09-23).

🔴 배경 (2026-09-18 PRD 1인 다계정 14화면, 사용자: "디스크립션 생성과 flow 연결은 아주 중요한 작업이었고
성공적으로 완료됐다 — 규칙화 + 코드화"): 홈 화면 우측의 `description` 인스턴스(140:64004)와 화면 위의
`Description Num` 마커(140:70842)를 화면마다 손으로 clone·insert·move·prop·텍스트 채우기를 반복했다(화면당
MCP 호출 ~40회). 이 스크립트는 그 절차를 **스펙 1개 → 디스크립션 1개 + 마커 n개** 로 고정한다.

사용:
  python3 scripts/screen_description.py <spec.json> [--dry-run]
  python3 scripts/figma_mcp_client.py describe <spec.json>

spec.json:
{
  "screen": "4802:106047",                 # 화면 root id (섹션/페이지 직계 자식)
  "rows": [                                # 디스크립션 행 = 화면의 기능 영역 순서(위→아래), 최대 19행
    {"section": "Content/Intro",           # 마커를 붙일 영역 — clone_variant.resolve_path 경로 또는 노드 id
     "title": "헤더 / 진입 영역",           # (선택) 첫 줄 제목
     "text": "[기능]\n· …\n[예외처리]\n· …"}  # 본문 — [기능]/[예외처리] + '·' 불릿, 근거는 (UC03-2 · BR04) 표기,
  ],                                       #        미결정은 {항목: 확인 필요} 로 남긴다
  "update": "4802:105021",                 # (선택) 기존 description id — 행만 다시 채우고 마커는 재생성
  "skipMarkers": false,                    # (선택) 마커 생략
  "descSource": "140:64004",               # (선택) description 컴포넌트 인스턴스 소스
  "markerSource": "140:70842",             # (선택) Description Num 마커 소스
  "gap": 82                                # (선택) 화면 우변 → 디스크립션 좌변 간격 (관례 82 → x+475)
}

배치 관례(0-DESC): 디스크립션 x = 화면 x + 화면 폭 + 82, y = 화면 y. 마커 x = 화면 x − 2,
y = 화면 y + (영역 y − 화면 y). 디스크립션 행 번호 = 마커 Count. 디스크립션·마커는 화면과 같은 부모(섹션).
파이프라인: get_node_info(화면) → fetch_tree 1회 → 영역 경로 해석(전부 그 트리) → description clone/insert/
move/rename → Show desc i 프롭 → 행 텍스트 채우기 → 마커 clone/insert/Count/move → DESCRIBE-SUMMARY JSON.
오프라인 테스트: scripts/tests/test_screen_description.py (계획 수립은 MCP 없이 순수 함수).
"""
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

DESC_SOURCE = '140:64004'
MARKER_SOURCE = '140:70842'
GAP = 82
MARKER_DX = -2
MAX_ROWS = 19
SHOW_PROP = 'Show desc {i}#35:{i}'
COUNT_PROP = 'Count'


def row_text(row):
    """title 이 있으면 첫 줄로 붙인 본문."""
    t = (row.get('text') or '').rstrip()
    title = (row.get('title') or '').strip()
    return f"{title}\n{t}" if title else t


def _rel_y(tree, nid):
    """트리(부모 상대 x/y)에서 root 기준 상대 y. absoluteBoundingBox 가 있으면 그 차이를 우선."""
    root_ab = tree.get('absoluteBoundingBox') or {}

    def walk(n, acc):
        if n.get('id') == nid:
            ab = n.get('absoluteBoundingBox') or {}
            if ab.get('y') is not None and root_ab.get('y') is not None:
                return ab['y'] - root_ab['y']
            return acc
        for c in n.get('children') or []:
            r = walk(c, acc + (c.get('y') or 0))
            if r is not None:
                return r
        return None
    return walk(tree, 0)


def build_plan(spec, tree):
    """spec + 화면 트리 → 계획(dict). MCP 호출 없음."""
    import clone_variant as CV
    rows = spec.get('rows') or []
    if not rows:
        raise ValueError('rows 가 비어 있음')
    if len(rows) > MAX_ROWS:
        raise ValueError(f'rows 는 최대 {MAX_ROWS}행 (description 컴포넌트 한계)')
    plan = {'rows': [], 'width': tree.get('width') or 393, 'warnings': []}
    for i, row in enumerate(rows, start=1):
        txt = row_text(row)
        if not txt:
            raise ValueError(f'row {i}: text 비어 있음')
        item = {'n': i, 'text': txt, 'section': row.get('section'), 'id': None, 'markerY': None}
        if row.get('section') and not spec.get('skipMarkers'):
            n = CV.resolve_path(tree, row['section'])
            item['id'] = n['id']
            item['markerY'] = _rel_y(tree, n['id'])
        elif not spec.get('skipMarkers'):
            plan['warnings'].append(f'row {i}: section 없음 → 마커 생략')
        if '[기능]' not in txt:
            plan['warnings'].append(f"row {i}: '[기능]' 헤더 없음 (관례: [기능]/[예외처리] + '·' 불릿)")
        plan['rows'].append(item)
    ys = [r['markerY'] for r in plan['rows'] if r['markerY'] is not None]
    if ys != sorted(ys):
        plan['warnings'].append('rows 순서가 화면 위→아래 순서와 다름 (마커 번호가 뒤섞임)')
    return plan


def _fill_rows(call, desc_id, rows):
    call('set_instance_properties', {'nodeId': desc_id, 'properties': {SHOW_PROP.format(i=i): (1 <= i <= len(rows)) for i in range(0, MAX_ROWS + 1)}})
    dt = call('get_node_tree', {'nodeId': desc_id, 'maxDepth': 8, 'skipInstanceChildren': False})
    ok = 0
    for row in dt.get('children') or []:
        if not str(row.get('name', '')).startswith('desc '):
            continue
        try:
            n = int(row['name'].split(' ')[1])
        except (IndexError, ValueError):
            continue
        if not (1 <= n <= len(rows)):
            continue
        for f in row.get('children') or []:
            if f.get('name') != 'text':
                continue
            for x in f.get('children') or []:
                if x.get('type') == 'TEXT' and call('set_text_content', {'nodeId': x['id'], 'text': rows[n - 1]['text']}).get('id'):
                    ok += 1
    return ok


def run(spec, dry_run=False, log=print):
    import figma_mcp_client as fc
    import ds_convert_lib as L

    def call(t, a):
        return fc.parse_content(fc.call_tool(t, a)).get('json') or {}

    t0 = time.time()
    fc.ensure_session()
    screen = spec['screen']
    info = call('get_node_info', {'nodeId': screen})
    if not info.get('id'):
        raise RuntimeError(f'화면 노드 없음: {screen} → {info}')
    parent = info.get('parentId')
    sx, sy, sw = round(info.get('x') or 0), round(info.get('y') or 0), round(info.get('width') or 393)
    tree = L.fetch_tree(screen) or call('get_node_tree', {'nodeId': screen, 'maxDepth': 25})
    plan = build_plan(spec, tree)
    for w in plan['warnings']:
        log('  ⚠️ ' + w)
    summary = {'screen': screen, 'name': info.get('name'), 'parent': parent, 'descId': None, 'markers': [], 'rows': len(plan['rows']),
               'placement': {'descX': sx + sw + int(spec.get('gap', GAP)), 'y': sy, 'markerX': sx + MARKER_DX}}
    if dry_run:
        summary['plan'] = plan
        return summary

    # 1) description
    gap = int(spec.get('gap', GAP))
    if spec.get('update'):
        desc = spec['update']
    else:
        desc = call('clone_node', {'nodeId': spec.get('descSource', DESC_SOURCE)}).get('id')
        if not desc:
            raise RuntimeError('description clone 실패')
        call('insert_child', {'childId': desc, 'parentId': parent})
        call('rename_node', {'nodeId': desc, 'name': 'description'})
    call('move_node', {'nodeId': desc, 'x': sx + sw + gap, 'y': sy})
    summary['descId'] = desc
    summary['rowsFilled'] = _fill_rows(call, desc, plan['rows'])

    # 2) 마커 (update 면 화면 좌변 x−2 의 기존 마커를 지우고 재생성)
    if not spec.get('skipMarkers'):
        if spec.get('update'):
            sib = call('get_node_tree', {'nodeId': parent, 'maxDepth': 1}).get('children') or []
            for k in sib:
                if str(k.get('name', '')).startswith('Description') and abs(round(k.get('x') or 0) - (sx + MARKER_DX)) <= 2 and sy - 5 <= round(k.get('y') or 0) <= sy + (info.get('height') or 3000):
                    call('delete_node', {'nodeId': k['id']})
        for r in plan['rows']:
            if r['markerY'] is None:
                continue
            m = call('clone_node', {'nodeId': spec.get('markerSource', MARKER_SOURCE)}).get('id')
            if not m:
                summary.setdefault('errors', []).append(f"row {r['n']}: 마커 clone 실패")
                continue
            call('insert_child', {'childId': m, 'parentId': parent})
            call('set_instance_properties', {'nodeId': m, 'properties': {COUNT_PROP: str(r['n'])}})
            call('rename_node', {'nodeId': m, 'name': f"Description [{r['n']}] {r['id']}"})   # 영역 id 를 심어 '마커 재생성'(regen-markers)이 추적 — 여러 영역은 regen 이 '+' 로 묶음
            call('move_node', {'nodeId': m, 'x': sx + MARKER_DX, 'y': sy + round(r['markerY'])})
            summary['markers'].append({'n': r['n'], 'id': m, 'y': sy + round(r['markerY'])})
    summary['elapsed_s'] = round(time.time() - t0, 1)
    return summary


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 1
    spec = json.load(open(argv[0], encoding='utf-8'))
    summary = run(spec, dry_run='--dry-run' in argv)
    print('📋 DESCRIBE-SUMMARY')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary.get('errors'):
        return 1
    if not summary.get('plan') and summary.get('rowsFilled', 0) != summary.get('rows'):
        print(f"✗ 행 채우기 불일치: {summary.get('rowsFilled')}/{summary.get('rows')} — description 컴포넌트 구조(desc N/text/TEXT) 확인")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
