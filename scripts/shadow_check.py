"""shadow_check — 카드 경계 바깥 밝기 램프로 그림자(elevation) 유무를 ref↔gen 대조 (규칙 0-F-3 확장, 2026-09-11).

배경(사용자 지적): 캡처의 floating 카드에 drop shadow 가 있었는데 생성본엔 없었고, 어떤 게이트도
그림자를 검사하지 않아 "육안 대조 통과" 로 넘어갔다. 그림자는 카드 박스 *바깥* 픽셀에만 나타나므로
텍스트 밴드·소형 성분·region_diff(평균 색차) 로는 잡히지 않는다 — 경계 바깥 밝기 램프를 잰다.

측정: 카드 박스의 아래/좌/우 변에서 바깥쪽으로 `depth` px 만큼, 변과 평행한 선분의 평균 밝기(L)를
1px 단위로 수집 → `delta = 먼 배경 밝기(끝 4px 평균) − 경계 인접 밝기(첫 2px 평균)`.
delta ≥ SHADOW_THR 이면 그림자 있음. (흰 배경 위 shadow-basic 실측: 아래 Δ≈24, 좌우 Δ≈6.)

사용:
  python3 scripts/shadow_check.py <genId> <refId>          # 카드 자동 탐색(흰+보더+radius≥8) + 4x export
  python3 scripts/shadow_check.py --img gen.png:393 ref.png:402 --box x,y,w,h [--box ...]
  python3 scripts/shadow_check.py <genId> <refId> --apply    # ref 에만 그림자인 카드에 권장 DS 스타일 즉시 바인딩
  python3 scripts/shadow_check.py --calibrate <cardId>       # DS Shadows/* 램프 시그니처 실측 → ds/SHADOW_RAMP_CALIBRATION.json
출력: 표(+권장 스타일·거리) + `🌫 SHADOW-CHECK-JSON`. qa_sweep ⑦ 차원으로도 호출된다.
추천 = ref 램프(아래/좌/우 Δ + 퍼짐 길이)와 캘리브레이션 표의 거리 최소 스타일 — 눈으로 고르지 않는다(0-F-3).
"""
from __future__ import annotations

import json
import os
import sys

from PIL import Image

SHADOW_THR = 6.0     # delta ≥ 6 → 그림자 있음 (요약 카드 옅은 그림자 Δ4 는 '없음' 취급 — 노이즈 여유)
NONE_THR = 3.0       # delta < 3 → 그림자 없음 (그 사이는 판정 보류)


def _gray(path):
    im = Image.open(path).convert('L')
    return im, im.load(), im.size


def _skip_border(vals, max_skip=4, dark=200):
    """램프 앞부분의 보더 픽셀(lum<dark, 최대 max_skip 개) 제거 — refine_box 가 보더 안쪽 끝에 맞추므로
    바깥 1~3px 는 보더 자체다."""
    i = 0
    while i < min(max_skip, len(vals)) and vals[i] is not None and vals[i] < dark:
        i += 1
    return vals[i:]


def edge_ramp(path, dev_w, box, side='bottom', depth=24, inset=6):
    """box=(x,y,w,h) 디바이스 px. side 변 바깥으로 depth px 의 평균 밝기 리스트(경계에서 먼 순서 아님 — 가까운 순)."""
    im, px, (W, H) = _gray(path)
    sc = W / float(dev_w)
    x, y, w, h = box
    out = []
    for d in range(1, depth + 1):
        vals = []
        if side == 'bottom':
            yy = int((y + h + d) * sc)
            xs = range(int((x + inset) * sc), int((x + w - inset) * sc), 2)
            if 0 <= yy < H:
                vals = [px[xx, yy] for xx in xs if 0 <= xx < W]
        elif side == 'top':
            yy = int((y - d) * sc)
            xs = range(int((x + inset) * sc), int((x + w - inset) * sc), 2)
            if 0 <= yy < H:
                vals = [px[xx, yy] for xx in xs if 0 <= xx < W]
        elif side == 'left':
            xx = int((x - d) * sc)
            ys = range(int((y + inset) * sc), int((y + h - inset) * sc), 2)
            if 0 <= xx < W:
                vals = [px[xx, yy] for yy in ys if 0 <= yy < H]
        elif side == 'right':
            xx = int((x + w + d) * sc)
            ys = range(int((y + inset) * sc), int((y + h - inset) * sc), 2)
            if 0 <= xx < W:
                vals = [px[xx, yy] for yy in ys if 0 <= yy < H]
        out.append(sum(vals) / len(vals) if vals else None)
    return out


def ramp_delta(ramp):
    """먼 배경(끝 4px 평균) − 경계 인접(첫 2px 평균). None 이 섞이면 가능한 값만 사용."""
    vals = [v for v in ramp if v is not None]
    if len(vals) < 6:
        return None
    near = sum(vals[:2]) / 2.0
    far = sum(vals[-4:]) / 4.0
    return round(far - near, 1)


def refine_box(path, dev_w, box, search=40, thr=245, min_cover=0.85):
    """배율 환산만으로 옮긴 박스를 실제 카드 보더에 맞춰 재정렬 (gen↔ref 세로 레이아웃 드리프트 대응).

    보더 행/열은 카드 변 전체에 걸쳐 연속(coverage≈1)이고 텍스트 행은 부분적(coverage<0.6)이므로,
    (thr=245: 캡처의 border-primary 급 연회색 보더 lum≈239 도 잡히도록 — 235 면 요약 카드 보더를 놓침)
    ±search px 안에서 **변을 따라 비흰(lum<thr) 픽셀 커버리지 ≥ min_cover 인 후보** 중 기대 위치에
    가장 가까운 것을 고른다(단일 열 최암값 방식은 카드 안 텍스트를 보더로 오인 — 2026-09-11 실측).
    후보가 없으면 원래 값 유지."""
    im, px, (W, H) = _gray(path)
    sc = W / float(dev_w)
    x, y, w, h = box
    inset = int(w * 0.15)  # 코너 radius 영역 제외

    def row_cover(yy):
        xs = range(int((x + inset) * sc), int((x + w - inset) * sc), 2)
        vals = [px[xx, yy] for xx in xs if 0 <= xx < W]
        return (sum(1 for v in vals if v < thr) / len(vals)) if vals else 0.0

    def col_cover(xx):
        ins = int(h * 0.15)
        ys = range(int((y + ins) * sc), int((y + h - ins) * sc), 2)
        vals = [px[xx, yy] for yy in ys if 0 <= yy < H]
        return (sum(1 for v in vals if v < thr) / len(vals)) if vals else 0.0

    def runs_in(lo, hi, cover_fn, limit, inner):
        """커버리지 후보를 연속 런으로 묶어 각 런의 **안쪽 끝**(디바이스 px) 목록을 돌려준다.
        (보더 바로 바깥의 그림자 행도 lum<thr 로 커버리지를 통과해 런이 바깥으로 이어진다 —
        카드 안쪽은 흰 면이라 런의 안쪽 끝이 진짜 보더. inner=+1: 아래/우측 변, -1: 위/좌측 변.)"""
        cands = [p for p in range(int(lo * sc), int(hi * sc)) if 0 <= p < limit and cover_fn(p) >= min_cover]
        if not cands:
            return []
        runs, cur = [], [cands[0]]
        for p in cands[1:]:
            if p - cur[-1] <= 2:
                cur.append(p)
            else:
                runs.append(cur); cur = [p]
        runs.append(cur)
        return [(min(r) if inner > 0 else max(r)) / sc for r in runs]

    def pair(lo_list, hi_list, e_lo, e_hi, size):
        """(시작, 끝) 후보 쌍 중 **크기가 기대 크기와 가장 가까운** 쌍을 고른다(위치 근접은 보조).
        같은 화면의 아이템 구분선·인접 카드 보더가 검색창에 함께 들어와 '가장 가까운 선' 만으로는
        오선택되던 실측(캡처 floating 카드: 보더 824.5 vs 아이템 구분선 847) 대응."""
        best = None
        for a in (lo_list or [None]):
            for b in (hi_list or [None]):
                aa = a if a is not None else e_lo
                bb = b if b is not None else e_hi
                cost = abs((bb - aa) - size) + 0.2 * (abs(aa - e_lo) + abs(bb - e_hi))
                if best is None or cost < best[0]:
                    best = (cost, aa, bb)
        return best[1], best[2]

    tops = runs_in(y - search, y + search, row_cover, H, -1)
    bots = runs_in(y + h - search, y + h + search, row_cover, H, +1)
    lefts = runs_in(x - search, x + search, col_cover, W, -1)
    rights = runs_in(x + w - search, x + w + search, col_cover, W, +1)
    top, bot = pair(tops, bots, y, y + h, h)
    left, right = pair(lefts, rights, x, x + w, w)
    nx = left if left is not None else x
    ny = top if top is not None else y
    nw = (right - nx) if right is not None else w
    nh = (bot - ny) if bot is not None else h
    if nw < w * 0.5 or nh < h * 0.5:
        return box
    return (nx, ny, nw, nh)


def ramp_extent(ramp, tol=2.0):
    """경계에서 배경 밝기(끝 4px 평균)−tol 에 도달할 때까지의 px 수 = 그림자 퍼짐 길이. 램프 없으면 0."""
    vals = [v for v in ramp if v is not None]
    if len(vals) < 6:
        return None
    # 배경 = 램프 중 가장 밝은 값(그림자는 배경보다 어둡기만 하다). 끝 4px 평균을 쓰면 카드 아래
    # depth 안에 다음 아이템 텍스트가 들어올 때 배경이 낮게 잡혀 퍼짐이 과소 측정된다.
    far = max(vals)
    for i, v in enumerate(vals):
        if v >= far - tol:
            return i
    return len(vals)


def measure_box(path, dev_w, box, depth=24):
    """카드 1개의 3변(bottom/left/right) delta. top 은 offset-y 그림자에서 거의 0 이라 제외."""
    out = {}
    for side in ('bottom', 'left', 'right'):
        r = _skip_border(edge_ramp(path, dev_w, box, side, depth + 4))
        out[side] = ramp_delta(r)
    out['extent'] = ramp_extent(_skip_border(edge_ramp(path, dev_w, box, 'bottom', 48)))
    return out


CALIB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ds', 'SHADOW_RAMP_CALIBRATION.json')


def load_calibration(path=None):
    """DS Shadows/* 스타일별 램프 시그니처 {name: {bottom,left,right,extent}} — 흰 배경 353×90 카드 실측.
    파일이 없으면 2026-09-11 실측 내장값."""
    path = path or CALIB_PATH
    try:
        with open(path, encoding='utf-8') as fh:
            d = json.load(fh)
            return d.get('styles') or d
    except Exception:
        return dict(DEFAULT_CALIBRATION)


DEFAULT_CALIBRATION = {  # 2026-09-11 실측 (--calibrate 4506:84426, 흰 배경 353×90 카드) — ds/SHADOW_RAMP_CALIBRATION.json 과 동일
    'Shadows/shadow-basic': {'bottom': 6.6, 'left': 3.2, 'right': 3.0, 'extent': 15},
    'Shadows/shadow-md': {'bottom': 13.3, 'left': 3.0, 'right': 2.5, 'extent': 5},
    'Shadows/shadow-lg': {'bottom': 21.0, 'left': 3.7, 'right': 3.3, 'extent': 15},
    'Shadows/shadow-xl': {'bottom': 23.3, 'left': 4.3, 'right': 4.0, 'extent': 27},
    'Shadows/shadow-2xl': {'bottom': 23.1, 'left': 5.0, 'right': 4.8, 'extent': 38},
}


def recommend_style(ref_deltas, calib=None):
    """ref 램프(bottom/left/right/extent) 에 가장 가까운 DS 스타일 → (name, distance). 거리 =
    |Δb|+|Δl|+|Δr| + 0.3·|extent 차| (퍼짐 길이도 반영 — 2xl 은 Δ 는 비슷해도 48px 로 두 배 퍼짐)."""
    calib = calib or load_calibration()
    best = None
    for name, sig in calib.items():
        d = 0.0
        for k in ('bottom', 'left', 'right'):
            a, b = ref_deltas.get(k), sig.get(k)
            if a is None or b is None:
                continue
            d += abs(a - b)
        ea, eb = ref_deltas.get('extent'), sig.get('extent')
        if ea is not None and eb is not None:
            d += 0.3 * abs(ea - eb)
        if best is None or d < best[1]:
            best = (name, round(d, 1))
    return best


def judge(deltas):
    """3변 delta → 'shadow' | 'none' | 'unsure'. bottom 이 주 판정, 좌우는 보조."""
    b = deltas.get('bottom')
    if b is None:
        return 'unsure'
    if b >= SHADOW_THR:
        return 'shadow'
    if b < NONE_THR:
        return 'none'
    return 'unsure'


def compare(gen_png, gen_w, ref_png, ref_w, boxes, names=None, gen_effects=None, quiet=False, calib=None):
    """boxes: gen 디바이스 px 기준 카드 박스 목록. ref 는 ref_w/gen_w 배율로 좌표 환산(상단 앵커).
    gen_effects: 박스별 gen 노드 effects 개수(있으면 표에 병기). 반환 {'rows','flags','result'}."""
    k = ref_w / float(gen_w)
    calib = calib or load_calibration()
    rows, flags = [], []
    for i, box in enumerate(boxes):
        nm = (names or [None] * len(boxes))[i] or f'card#{i}'
        rbox = refine_box(ref_png, ref_w, (box[0] * k, box[1] * k, box[2] * k, box[3] * k))
        gbox = refine_box(gen_png, gen_w, box)
        gd = measure_box(gen_png, gen_w, gbox)
        rd = measure_box(ref_png, ref_w, rbox)
        gj, rj = judge(gd), judge(rd)
        eff = None if gen_effects is None else gen_effects[i]
        rec = recommend_style(rd, calib) if rj == 'shadow' else None
        rows.append({'name': nm, 'box': [round(v, 1) for v in gbox], 'ref_box': [round(v, 1) for v in rbox], 'ref': rd, 'gen': gd,
                     'ref_judge': rj, 'gen_judge': gj, 'gen_effects': eff,
                     'recommend': ({'style': rec[0], 'distance': rec[1]} if rec else None)})
        if rj == 'shadow' and gj != 'shadow':
            flags.append(f"{nm}: ref 그림자 있음(아래 Δ{rd['bottom']}) / gen 없음(Δ{gd['bottom']}"
                         + (f", effects {eff}" if eff is not None else '')
                         + (f") → 권장 {rec[0]} (거리 {rec[1]})" if rec else ') — DS Shadows 스타일 바인딩 필요'))
        elif gj == 'shadow' and rj == 'none':
            flags.append(f"{nm}: gen 에만 그림자(아래 Δ{gd['bottom']}) / ref Δ{rd['bottom']} — 제거 검토")
    if not quiet:
        print(f'[shadow-check] 카드 {len(rows)}개  (Δ = 먼 배경 − 경계 인접 밝기, ≥{SHADOW_THR} 그림자)')
        print('   %-28s %-26s %-26s %s' % ('card', 'ref(b/l/r)', 'gen(b/l/r)', 'judge ref→gen'))
        for r in rows:
            f = lambda d: '/'.join('-' if d[s] is None else str(d[s]) for s in ('bottom', 'left', 'right')) + (f" ext{d.get('extent')}" if d.get('extent') is not None else '')
            rec = r.get('recommend')
            print('   %-28s %-30s %-30s %s→%s%s' % (r['name'][:28], f(r['ref']), f(r['gen']), r['ref_judge'], r['gen_judge'],
                                                    (f"  권장 {rec['style'].split('/')[-1]}(거리 {rec['distance']})" if rec else '')))
        if flags:
            print(f'   🔴 불일치 {len(flags)}건:')
            for x in flags:
                print('      - ' + x)
        else:
            print('   ✓ 그림자 유무 ref 와 일치')
    return {'rows': rows, 'flags': flags, 'result': 'mismatch' if flags else 'match'}


# ── 라이브: gen 트리에서 카드 후보 자동 수집 ───────────────────────────────────────

def _card_boxes_from_tree(fc, gen_id):
    """gen 루트에서 흰 fill + 보이는 stroke + radius≥8 + width≥80 인 비-인스턴스 FRAME 을 카드로 수집.
    좌표는 루트 absoluteBoundingBox 기준 상대 디바이스 px. 반환 (boxes, names, effects_counts)."""
    items = fc.parse_content(fc.call_tool('get_nodes_info', {'nodeIds': [gen_id]})).get('json')
    if not isinstance(items, list) or not items:
        return [], [], []
    root = items[0].get('document') or items[0]
    rb = root.get('absoluteBoundingBox') or {}
    rx, ry = rb.get('x', 0), rb.get('y', 0)
    boxes, names, effs, ids = [], [], [], []

    def white_border(n):
        if (n.get('type') or '').upper() != 'FRAME' or ';' in (n.get('id') or ''):
            return False
        fills = n.get('fills') or []
        if not (fills and isinstance(fills[0], dict) and fills[0].get('visible', True) and fills[0].get('type') == 'SOLID'):
            return False
        c = fills[0].get('color') or {}
        if not (c.get('r', 0) > 0.93 and c.get('g', 0) > 0.93 and c.get('b', 0) > 0.93):
            return False
        strokes = n.get('strokes') or []
        if not (strokes and isinstance(strokes[0], dict) and strokes[0].get('visible', True)):
            return False
        cr = n.get('cornerRadius')
        bb = n.get('absoluteBoundingBox') or {}
        # 카드만(칩/버튼 제외): 폭 ≥200 & 높이 ≥48
        return isinstance(cr, (int, float)) and cr >= 8 and (bb.get('width') or 0) >= 200 and (bb.get('height') or 0) >= 48

    def walk(n):
        if not isinstance(n, dict):
            return
        if white_border(n):
            bb = n['absoluteBoundingBox']
            boxes.append((bb['x'] - rx, bb['y'] - ry, bb['width'], bb['height']))
            names.append(n.get('name') or n.get('id'))
            effs.append(len([e for e in (n.get('effects') or []) if isinstance(e, dict) and e.get('visible', True)]))
            ids.append(n.get('id'))
            return  # 카드 안의 카드는 세지 않음
        for c in n.get('children') or []:
            walk(c)
    walk(root)
    return boxes, names, effs, ids


def apply_recommendations(fc, rows, ids, only_missing=True):
    """추천 스타일을 gen 카드에 바인딩(set_effect_style_id S:{key},{id}). only_missing=True 면 ref 에 그림자가
    있는데 gen 에 없는 카드만. 반환 [(name, style, ok)]."""
    smap = fc._load_effect_style_map()
    done = []
    for r, nid in zip(rows, ids):
        rec = r.get('recommend')
        if not rec or not nid:
            continue
        if only_missing and r.get('gen_judge') == 'shadow':
            continue
        key = smap.get(rec['style'])
        if not key:
            done.append((r['name'], rec['style'], False)); continue
        try:
            fc.call_tool('set_effect_style_id', {'nodeId': nid, 'effectStyleId': f"S:{key},{nid}"})
            done.append((r['name'], rec['style'], True))
        except Exception:
            done.append((r['name'], rec['style'], False))
    return done


def calibrate(card_id, out_path=None, out_dir='scripts/qa_screenshots'):
    """DS Shadows/* 스타일을 주어진 카드(흰 배경 위 흰+보더 카드)에 차례로 바인딩해 램프 시그니처를 실측하고
    ds/SHADOW_RAMP_CALIBRATION.json 에 저장. 끝나면 원래 effect style(있으면)로 복구."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import figma_mcp_client as fc  # noqa
    smap = fc._load_effect_style_map()

    def _info(nid):
        j = fc.parse_content(fc.call_tool('get_node_info', {'nodeId': nid})).get('json') or {}
        return j.get('node', j) if isinstance(j, dict) else {}   # 응답이 {node:{…}} 또는 노드 자체 — 둘 다 처리

    info = _info(card_id)
    # 루트(화면) 찾기: 부모를 따라 올라가 SECTION/PAGE 직전
    cur = card_id; root_id = card_id
    for _ in range(12):
        pid = _info(cur).get('parentId')
        if not pid:
            break
        if (_info(pid).get('type') or '') in ('SECTION', 'PAGE', 'DOCUMENT'):
            root_id = cur; break
        cur = pid
    rw = float(_info(root_id).get('width') or 393)
    print(f'[shadow-check] calibrate: card {card_id} / root {root_id} ({rw:.0f}px)')
    boxes, names, _effs, ids = _card_boxes_from_tree(fc, root_id)
    if card_id not in ids:
        raise SystemExit(f'[shadow-check] {card_id} 는 카드 후보(흰+보더+radius≥8, 폭≥200)가 아님 — 후보: {list(zip(ids, names))}')
    box = boxes[ids.index(card_id)]
    orig = info.get('effectStyleId')
    styles = {}
    os.makedirs(out_dir, exist_ok=True)
    for name in ('Shadows/shadow-basic', 'Shadows/shadow-md', 'Shadows/shadow-lg', 'Shadows/shadow-xl', 'Shadows/shadow-2xl'):
        key = smap.get(name)
        if not key:
            continue
        fc.call_tool('set_effect_style_id', {'nodeId': card_id, 'effectStyleId': f"S:{key},{card_id}"})
        png = os.path.join(out_dir, 'shadow_calib.png')
        fc.export_image(root_id, png, 'PNG', 4)
        styles[name] = measure_box(png, rw, box)
        print(f"  {name:22s} {styles[name]}")
    if orig:
        fc.call_tool('set_effect_style_id', {'nodeId': card_id, 'effectStyleId': orig})
    out = {'_note': 'DS Shadows/* 램프 시그니처 (흰 배경 위 카드 경계 바깥 밝기 Δ: 먼 배경−경계 인접, extent=퍼짐 px). '
                    'shadow_check.py --calibrate <cardId> 로 재측정.', 'card': card_id, 'box': [round(v, 1) for v in box], 'styles': styles}
    with open(out_path or CALIB_PATH, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(f"[shadow-check] 캘리브레이션 저장 → {out_path or CALIB_PATH}")
    return styles


def run(gen_id, ref_id, gen_png=None, ref_png=None, out_dir='scripts/qa_screenshots', quiet=False, apply=False):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import figma_mcp_client as fc  # noqa
    os.makedirs(out_dir, exist_ok=True)
    gen_png = gen_png or os.path.join(out_dir, 'shadow_gen.png')
    ref_png = ref_png or os.path.join(out_dir, 'shadow_ref.png')
    if not os.path.exists(gen_png):
        fc.export_image(gen_id, gen_png, 'PNG', 4)
    if not os.path.exists(ref_png):
        fc.export_image(ref_id, ref_png, 'PNG', 4)
    gw = float(((fc.parse_content(fc.call_tool('get_node_info', {'nodeId': gen_id})).get('json') or {}).get('node') or {}).get('width') or 393)
    rw = float(((fc.parse_content(fc.call_tool('get_node_info', {'nodeId': ref_id})).get('json') or {}).get('node') or {}).get('width') or 393)
    boxes, names, effs, ids = _card_boxes_from_tree(fc, gen_id)
    if not boxes:
        if not quiet:
            print('[shadow-check] 카드 후보(흰+보더+radius≥8) 없음 — 검사 대상 없음')
        return {'rows': [], 'flags': [], 'result': 'match', 'applied': []}
    res = compare(gen_png, gw, ref_png, rw, boxes, names, effs, quiet=quiet)
    res['applied'] = []
    if apply and res['flags']:
        res['applied'] = apply_recommendations(fc, res['rows'], ids)
        if not quiet:
            for nm, st, ok in res['applied']:
                print(f"   {'✓' if ok else '✗'} {nm} ← {st}")
    return res


def main(argv):
    if '--img' in argv:
        i = argv.index('--img')
        g, r = argv[i + 1], argv[i + 2]
        gp, gw = g.rsplit(':', 1); rp, rw = r.rsplit(':', 1)
        boxes = []
        for j, a in enumerate(argv):
            if a == '--box':
                boxes.append(tuple(float(v) for v in argv[j + 1].split(',')))
        res = compare(gp, float(gw), rp, float(rw), boxes)
    elif '--calibrate' in argv:
        calibrate(argv[argv.index('--calibrate') + 1])
        return 0
    else:
        res = run(argv[0], argv[1], apply=('--apply' in argv))
    print('\n🌫 SHADOW-CHECK-JSON')
    print(json.dumps({'type': 'shadow-check', **res}, ensure_ascii=False))
    return 1 if res['flags'] else 0


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    sys.exit(main(sys.argv[1:]))
