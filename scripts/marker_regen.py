#!/usr/bin/env python3
"""marker_regen.py — "마커 재생성": 선택한 화면의 Description Num 마커를 현재 영역 위치로 다시 찍고,
새 영역엔 마커 + 디스크립션 초안 행을, 사라진 영역은 마커·행을 제거한다 (규칙 0-DESC-2, 2026-09-23 사용자 룰).

🔴 배경: 마커는 시트 안이 아니라 섹션의 절대 좌표 노드라, 화면에 요소를 넣거나 영역 크기가 바뀌면 옛 y 에
남는다(고지 시트에 안내 행+버튼 추가 후 122px 어긋남). 사용자: *"프레임을 선택 후 '마커 재생성' 이라고
하면 변경된 위치로 마커가 재생성되고, 요소가 추가되면 마커를 추가하면서 디스크립션도 생성되게."*

사용 (Figma 에서 화면 root 를 선택한 상태):
  python3 scripts/figma_mcp_client.py regen-markers [<screenId>] [--dry-run] [--no-draft] [--fold]
  python3 scripts/marker_regen.py [<screenId>] [--dry-run]

동작:
  1. 화면(선택 노드) · 우측 description 인스턴스(x ≈ 화면 x+폭+82) · 좌측 마커들(x ≈ 화면 x−2) 을 찾는다.
  2. 마커 이름 `Description [n] <영역id>[+<영역id>…]` 에서 담당 영역을 읽는다(한 행이 여러 영역을 묶으면 '+').
     옛 마커(이름 'Description')는 y 순서를 지키는 DP 정렬(align_legacy)로 영역에 귀속시켜 한 번 백필한다.
     `--fold`: 어느 행도 맡지 않은 영역을 초안 행으로 추가하지 않고 가장 가까운 위 행에 접어 넣는다(기존 화면 백필용).
  3. 후보 영역 = root 직계 자식(Status Bar/HomeIndicator/Dim Overlay/Keyboard 제외 — NavBar 는 '헤더/진입' 행의
     대상이라 포함; 'Content'/'Contents'/'Modal Sheet' 랩은 그 직계 자식으로 펼침) 중 높이 ≥ 24 · 보이는 FRAME/INSTANCE.
  4. 병합: 기존 (영역 → 행 텍스트) + 새 영역(마커·초안 행 추가: 영역 이름 + 안의 텍스트/버튼 라벨 나열,
     제목에 '(초안 — 작성 필요)') − 사라진 영역(마커·행 제거). 현재 y 순으로 정렬해 번호를 다시 매긴다.
  5. description 행을 다시 채우고 마커를 전부 지운 뒤 새 이름·위치로 재생성 → REGEN-SUMMARY JSON.
오프라인 테스트: scripts/tests/test_marker_regen.py.
"""
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import screen_description as SD  # noqa: E402

SKIP_ROOT_CHILDREN = {'Status Bar', 'HomeIndicator', 'Home Indicator', 'Dim Overlay', 'Keyboard'}   # NavBar/Tool Bar 는 '헤더/진입' 행의 대상이라 포함
WRAPPERS = {'Content', 'Contents', 'Modal Sheet', 'Sheet', 'Body'}
MIN_AREA_H = 24
LEGACY_TOL = 12          # (참고) 단일 최근접 귀속 허용 오차 — 실제 백필은 align_legacy(DP) 사용
UNMATCH_COST = 150       # DP 정렬에서 마커/영역을 짝 없이 남기는 비용(px) — 이보다 먼 짝은 맺지 않음
MARKER_RE = re.compile(r'^Description\s*\[(\d+)\]\s*(\S+)')


def marker_name(n, section_ids):
    """`Description [n] id1+id2` — 한 행이 여러 영역을 묶어 설명하면 '+' 로 잇는다(첫 id 가 마커 위치 기준)."""
    ids = [section_ids] if isinstance(section_ids, str) else list(section_ids)
    return f"Description [{n}] {'+'.join(ids)}"


def parse_marker(name):
    """→ (n, [ids]) / 옛 마커('Description')는 (None, [])."""
    m = MARKER_RE.match(name or '')
    return (int(m.group(1)), [x for x in m.group(2).split('+') if x]) if m else (None, [])


def align_legacy(marker_ys, areas, unmatch=UNMATCH_COST):
    """옛 마커(root 상대 y 목록, 위→아래) ↔ 영역(위→아래) 단조 정렬(DP). 반환 [영역 id | None] (마커별).
    비용 = 짝이면 |dy|, 짝 없으면 unmatch — 시트 확장으로 +24~122px 밀린 마커도 순서가 지켜지면 제 영역에 붙는다."""
    A = [a['y'] for a in areas]
    n, m = len(marker_ys), len(A)
    INF = float('inf')
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0
    for i in range(n + 1):
        for j in range(m + 1):
            if dp[i][j] == INF:
                continue
            if i < n and dp[i][j] + unmatch < dp[i + 1][j]:
                dp[i + 1][j] = dp[i][j] + unmatch; back[i + 1][j] = (i, j, None)
            if j < m and dp[i][j] + unmatch < dp[i][j + 1]:
                dp[i][j + 1] = dp[i][j] + unmatch; back[i][j + 1] = (i, j, None)
            if i < n and j < m:
                c = dp[i][j] + abs(marker_ys[i] - A[j])
                if c < dp[i + 1][j + 1]:
                    dp[i + 1][j + 1] = c; back[i + 1][j + 1] = (i, j, areas[j]['id'])
    out = [None] * n
    i, j = n, m
    while (i, j) != (0, 0):
        pi, pj, sid = back[i][j]
        if pi == i - 1 and pj == j - 1:
            out[i - 1] = sid
        i, j = pi, pj
    return out


def candidate_areas(tree):
    """root 트리 → [{'id','name','y','h','node'}] 위→아래. y 는 root 기준 상대."""
    out = []

    def push(n, base_y):
        if n.get('visible') is False or n.get('type') not in ('FRAME', 'INSTANCE', 'GROUP'):
            return
        h = n.get('height') or 0
        if h < MIN_AREA_H or (n.get('name') or '').startswith(('Spacer', 'Row Rule')):
            return
        out.append({'id': n['id'], 'name': n.get('name'), 'y': base_y + (n.get('y') or 0), 'h': h, 'node': n})

    for c in tree.get('children') or []:
        nm = c.get('name') or ''
        if nm in SKIP_ROOT_CHILDREN or c.get('visible') is False:
            continue
        if nm in WRAPPERS:
            for g in c.get('children') or []:
                push(g, (c.get('y') or 0))
        else:
            push(c, 0)
    out.sort(key=lambda a: a['y'])
    return out


def draft_row(area):
    """새 영역의 디스크립션 초안 — 안의 텍스트·버튼 라벨을 나열 (날조 없이 실물만, 동작은 확인 필요)."""
    texts, buttons = [], []

    def walk(n):
        if n.get('type') == 'TEXT' and (n.get('characters') or '').strip():
            texts.append(n['characters'].strip().replace('\n', ' '))
        nm = n.get('name') or ''
        if n.get('type') == 'INSTANCE' and (nm.endswith('CTA') or nm.endswith('Button')):
            lab = None
            for t in n.get('children') or []:
                for u in [t] + (t.get('children') or []):
                    if u.get('type') == 'TEXT' and (u.get('characters') or '').strip():
                        lab = u['characters'].strip()
            buttons.append(lab or nm)
        for c in n.get('children') or []:
            walk(c)
    walk(area['node'])
    lines = [f"{area['name']} 영역 (초안 — 작성 필요)", '[기능]']
    for t in texts[:4]:
        lines.append(f"· 텍스트: \"{t[:40]}{'…' if len(t) > 40 else ''}\"")
    for b in buttons[:3]:
        lines.append(f"· 버튼 '{b}': {{동작: 확인 필요}}")
    if not texts and not buttons:
        lines.append('· {내용: 확인 필요}')
    lines += ['[예외처리]', '· {확인 필요}']
    return '\n'.join(lines)


def match_legacy(marker_y_rel, areas, tol=LEGACY_TOL):
    """옛 마커(이름에 영역 id 없음)의 root 상대 y → 가장 가까운 영역 id (tol 밖이면 None)."""
    best, bd = None, tol + 1
    for a in areas:
        d = abs(a['y'] - marker_y_rel)
        if d < bd:
            best, bd = a['id'], d
    return best if bd <= tol else None


def merge(existing, areas, draft=True, fold=False):
    """existing: [{'n','sections':[영역id…],'text'}] → 새 행 목록(현재 y 순).
    행은 sections 중 살아 있는 영역을 모두 커버(첫 것이 마커 위치). 커버되지 않은 영역 → 초안 행 추가
    (fold=True 면 가장 가까운 위 행(없으면 아래 행)에 접어 넣음 — 기존 화면 백필용). 전부 사라진 행 → 제거."""
    by_id = {a['id']: a for a in areas}
    rows, report = [], {'kept': [], 'added': [], 'removed': [], 'orphan': [], 'folded': []}
    covered = set()
    for e in existing:
        alive = [sid for sid in (e.get('sections') or []) if sid in by_id and sid not in covered]
        if alive:
            rows.append({'sections': alive, 'text': e['text'], 'y': by_id[alive[0]]['y'], 'status': 'kept'})
            report['kept'].append(alive[0]); covered.update(alive)
        elif e.get('sections'):
            report['removed'].append({'n': e.get('n'), 'sections': e['sections'], 'text': e['text'][:40]})
        else:
            report['orphan'].append({'n': e.get('n'), 'text': e['text'][:40]})
    rows.sort(key=lambda r: r['y'])
    for a in areas:
        if a['id'] in covered:
            continue
        if fold and rows:
            prev = [r for r in rows if r['y'] <= a['y']]
            host = prev[-1] if prev else rows[0]
            host['sections'].append(a['id']); covered.add(a['id'])
            report['folded'].append({'section': a['id'], 'name': a['name'], 'into': host['sections'][0]})
            continue
        rows.append({'sections': [a['id']], 'text': draft_row(a) if draft else f"{a['name']} 영역\n[기능]\n· {{확인 필요}}", 'y': a['y'], 'status': 'added'})
        report['added'].append({'section': a['id'], 'name': a['name']}); covered.add(a['id'])
    rows.sort(key=lambda r: r['y'])
    if len(rows) > SD.MAX_ROWS:
        raise ValueError(f'행 {len(rows)} > 최대 {SD.MAX_ROWS} — 영역을 묶어서 줄일 것')
    return rows, report


def _read_rows(call, desc_id):
    dt = call('get_node_tree', {'nodeId': desc_id, 'maxDepth': 8, 'skipInstanceChildren': False})
    rows = {}
    for row in dt.get('children') or []:
        nm = str(row.get('name', ''))
        if not nm.startswith('desc ') or row.get('visible') is False:
            continue
        try:
            n = int(nm.split(' ')[1])
        except (IndexError, ValueError):
            continue
        if n < 1:
            continue
        for f in row.get('children') or []:
            if f.get('name') == 'text':
                for x in f.get('children') or []:
                    if x.get('type') == 'TEXT' and (x.get('characters') or '').strip():
                        rows[n] = x['characters']
    return rows


def run(screen_id=None, dry_run=False, draft=True, fold=False, log=print):
    import figma_mcp_client as fc
    import ds_convert_lib as L

    def call(t, a):
        return fc.parse_content(fc.call_tool(t, a)).get('json') or {}

    t0 = time.time()
    fc.ensure_session()
    if not screen_id:
        sel = call('get_selection', {})
        nodes = sel.get('nodes') or sel.get('selection') or []
        if len(nodes) != 1:
            raise RuntimeError(f'화면 root 1개를 선택하세요 (현재 선택 {len(nodes)}개)')
        screen_id = nodes[0]['id']
    info = call('get_node_info', {'nodeId': screen_id})
    if info.get('type') not in ('FRAME', 'INSTANCE') or not info.get('parentId'):
        raise RuntimeError(f'화면 root 가 아님: {screen_id} ({info.get("type")})')
    parent = info['parentId']
    sx, sy, sw, sh = round(info.get('x') or 0), round(info.get('y') or 0), round(info.get('width') or 393), round(info.get('height') or 852)
    sib = call('get_node_tree', {'nodeId': parent, 'maxDepth': 1}).get('children') or []
    desc = [k for k in sib if k.get('name') == 'description' and abs(round(k.get('x') or 0) - (sx + sw + SD.GAP)) <= 6 and abs(round(k.get('y') or 0) - sy) <= 6]
    if not desc:
        raise RuntimeError('우측 description 인스턴스를 못 찾음 — 먼저 `describe <spec.json>` 으로 생성')
    desc_id = desc[0]['id']
    markers = sorted([k for k in sib if str(k.get('name', '')).startswith('Description') and abs(round(k.get('x') or 0) - (sx + SD.MARKER_DX)) <= 2
                      and sy - 5 <= round(k.get('y') or 0) <= sy + sh + 5], key=lambda k: k.get('y') or 0)
    tree = L.fetch_tree(screen_id) or call('get_node_tree', {'nodeId': screen_id, 'maxDepth': 25})
    areas = candidate_areas(tree)
    texts = _read_rows(call, desc_id)
    existing, legacy = [], []
    for i, m in enumerate(markers, start=1):
        n, ids = parse_marker(m.get('name'))
        e = {'n': n if n is not None else i, 'sections': ids, 'text': '', 'markerId': m['id'], 'yrel': round(m.get('y') or 0) - sy}
        existing.append(e)
        if n is None:
            legacy.append(e)
    if legacy:
        claimed = {sid for e in existing for sid in e['sections']}
        free = [a for a in areas if a['id'] not in claimed]
        for e, sid in zip(legacy, align_legacy([e['yrel'] for e in legacy], free)):
            e['sections'] = [sid] if sid else []
    for e in existing:
        e['text'] = texts.get(e['n'], '')
    existing.sort(key=lambda e: e['n'])
    rows, report = merge(existing, areas, draft=draft, fold=fold)
    summary = {'screen': screen_id, 'name': info.get('name'), 'descId': desc_id, 'areas': [(a['name'], a['id'], round(a['y'])) for a in areas],
               'report': report, 'rows': [{'n': i + 1, 'sections': r['sections'], 'status': r['status'], 'y': sy + round(r['y'])} for i, r in enumerate(rows)]}
    if dry_run:
        return summary
    # 행 다시 채우기
    filled = SD._fill_rows(call, desc_id, [{'text': r['text']} for r in rows])
    # 마커 전부 삭제 → 재생성 (이름에 영역 id)
    for m in markers:
        call('delete_node', {'nodeId': m['id']})
    made = []
    for i, r in enumerate(rows, start=1):
        m = call('clone_node', {'nodeId': SD.MARKER_SOURCE}).get('id')
        if not m:
            summary.setdefault('errors', []).append(f'row {i}: 마커 clone 실패')
            continue
        call('insert_child', {'childId': m, 'parentId': parent})
        call('set_instance_properties', {'nodeId': m, 'properties': {SD.COUNT_PROP: str(i)}})
        call('rename_node', {'nodeId': m, 'name': marker_name(i, r['sections'])})
        call('move_node', {'nodeId': m, 'x': sx + SD.MARKER_DX, 'y': sy + round(r['y'])})
        made.append(m)
    summary.update({'rowsFilled': filled, 'markers': made, 'elapsed_s': round(time.time() - t0, 1)})
    return summary


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ('-h', '--help'):
        print(__doc__)
        return 1
    sid = next((a for a in argv if not a.startswith('--')), None)
    summary = run(sid, dry_run='--dry-run' in argv, draft='--no-draft' not in argv, fold='--fold' in argv)
    print('📋 REGEN-SUMMARY')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary.get('errors'):
        return 1
    if summary['report']['added']:
        print(f"✏️ 초안 행 {len(summary['report']['added'])}개 추가됨 — '(초안 — 작성 필요)' 행을 PRD 근거로 채울 것")
    return 0


if __name__ == '__main__':
    sys.exit(main())
