#!/usr/bin/env python3
"""pixel_measure — 소형 요소(도트·아이콘·선·링) 픽셀 실측 대조 (2026-09-08 규칙 0-F-3).

배경(사용자 3연속 지적, 최근본스테이지 순번 도트): 2x 스크린샷을 눈으로 보고 "채움 도트 ≈ 8px" 로
판독 → 실측은 4px. 두 번 더 눈대중으로 고치다 사용자 분노. **눈으로만 보고 크기/굵기/간격을
판단하지 말 것 — 숫자로 잰다.**

기능:
  - 이미지(4x export 권장)에서 배경(흰)이 아닌 픽셀의 연결 성분을 RLE+union-find 로 추출
  - 소형 성분(디바이스 px 기준 max_size 이하)만 골라 (종류 fill/ring, 폭, 높이, 링 굵기) 로 정규화
  - gen ↔ ref 히스토그램 대조: gen 에만 있는 규격(±tol) 을 mismatch 로 보고 → exit 1

사용:
  python3 scripts/pixel_measure.py <genId> <refId> [--scale 4] [--max 40] [--tol 1] [--min-count 3]
  python3 scripts/pixel_measure.py --img gen.png:393 ref.png:402      # 이미 export 한 이미지
  (band 집중 측정) --band y0:y1 [--x x0:x1]   # 디바이스 px 좌표, gen/ref 각각 같은 밴드

출력: 표 + `📏 PIXEL-MEASURE-JSON` 블록. qa_sweep 의 ⑤ 차원으로도 호출된다.
"""
import json
import os
import re
import sys
from collections import Counter

from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(_HERE, 'qa_screenshots')
BG_THRESHOLD = 225   # 이 값보다 밝으면(모든 채널) 배경으로 본다


def _mask_rows(im, threshold=BG_THRESHOLD):
    """RGB → 행별 bytes 마스크(0x01 = 전경). PIL point 로 벡터화."""
    g = im.convert('RGB')
    r, gch, b = g.split()
    lut = [1 if v < threshold else 0 for v in range(256)]
    m = r.point(lut, 'L')
    m2 = gch.point(lut, 'L')
    m3 = b.point(lut, 'L')
    # 전경 = 한 채널이라도 threshold 미만 (밝은 회색 도트도 잡기 위해 OR)
    from PIL import ImageChops
    mm = ImageChops.lighter(ImageChops.lighter(m, m2), m3)
    W, H = mm.size
    raw = mm.tobytes()
    return [raw[y * W:(y + 1) * W] for y in range(H)], W, H


_RUN = re.compile(b'\x01+')


def components(im, threshold=BG_THRESHOLD):
    """연결 성분 목록: dict(x0,y0,x1,y1,area). 4-연결(런 겹침) 기준. 순수 파이썬이지만
    RLE + union-find 라 4x export(≈6M px)도 수 초."""
    rows, W, H = _mask_rows(im, threshold)
    parent = []

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    runs = []          # (y, x0, x1, id)
    prev = []
    for y, row in enumerate(rows):
        cur = []
        for m in _RUN.finditer(row):
            rid = len(parent)
            parent.append(rid)
            x0, x1 = m.start(), m.end() - 1
            cur.append((x0, x1, rid))
            for px0, px1, pid in prev:
                if px0 <= x1 and x0 <= px1:
                    union(pid, rid)
            runs.append((y, x0, x1, rid))
        prev = cur
    comps = {}
    for y, x0, x1, rid in runs:
        r = find(rid)
        c = comps.get(r)
        if c is None:
            comps[r] = {'x0': x0, 'y0': y, 'x1': x1, 'y1': y, 'area': x1 - x0 + 1}
        else:
            c['x0'] = min(c['x0'], x0); c['x1'] = max(c['x1'], x1)
            c['y0'] = min(c['y0'], y); c['y1'] = max(c['y1'], y)
            c['area'] += x1 - x0 + 1
    return list(comps.values()), rows, W, H


def describe(c, rows, scale):
    """성분 → (kind, w, h, stroke) 디바이스 px. ring = 중심이 배경(비어 있음)."""
    w = (c['x1'] - c['x0'] + 1) / scale
    h = (c['y1'] - c['y0'] + 1) / scale
    cx = (c['x0'] + c['x1']) // 2
    cy = (c['y0'] + c['y1']) // 2
    hollow = rows[cy][cx] == 0
    stroke = None
    if hollow:
        x = c['x0']
        while x < cx and rows[cy][x] == 1:
            x += 1
        stroke = (x - c['x0']) / scale
    return ('ring' if hollow else 'fill', round(w, 1), round(h, 1), round(stroke, 1) if stroke is not None else None)


def measure_image(path, dev_w, max_size=40, min_size=2, band=None, xr=None):
    """이미지의 소형 성분 규격 목록. band/xr 는 디바이스 px 범위(포함)."""
    im = Image.open(path)
    scale = im.size[0] / float(dev_w)
    comps, rows, W, H = components(im)
    out = []
    for c in comps:
        d = describe(c, rows, scale)
        if d[1] < min_size or d[2] < min_size or d[1] > max_size or d[2] > max_size:
            continue
        cy = (c['y0'] + c['y1']) / 2 / scale
        cx = (c['x0'] + c['x1']) / 2 / scale
        if band and not (band[0] <= cy <= band[1]):
            continue
        if xr and not (xr[0] <= cx <= xr[1]):
            continue
        out.append({'kind': d[0], 'w': d[1], 'h': d[2], 'stroke': d[3],
                    'x': round(cx, 1), 'y': round(cy, 1)})
    out.sort(key=lambda e: (e['y'], e['x']))
    return out, scale


def _key(e, tol):
    """히스토그램 키: tol 단위로 양자화(±tol 허용)."""
    q = lambda v: None if v is None else round(v / tol) * tol if tol else v
    return (e['kind'], q(e['w']), q(e['h']), q(e['stroke']))


def compare(gen_specs, ref_specs, tol=1.0, min_count=1):
    """gen 에만 있는 규격(ref 에 ±tol 로 매칭 없음)을 mismatch 로. 반환 (mismatches, gen_hist, ref_hist).
    min_count: gen 에서 그 규격이 min_count 회 이상 반복될 때만 보고(글리프 조각 노이즈 억제 —
    도트/아이콘/스텝 같은 반복 요소가 대상)."""
    gh = Counter(_key(e, tol) for e in gen_specs)
    rh = Counter(_key(e, tol) for e in ref_specs)

    def near(k, hist):
        for k2 in hist:
            if k2[0] != k[0]:
                continue
            if all((a is None and b is None) or (a is not None and b is not None and abs(a - b) <= tol)
                   for a, b in zip(k[1:], k2[1:])):
                return k2
        return None
    mism = []
    for k, n in gh.items():
        if n >= min_count and not near(k, rh):
            mism.append({'kind': k[0], 'w': k[1], 'h': k[2], 'stroke': k[3], 'count': n})
    return mism, gh, rh


def _fmt_hist(h):
    return ', '.join(f"{k[0]} {k[1]}×{k[2]}" + (f" s{k[3]}" if k[3] is not None else '') + f" ×{n}"
                     for k, n in sorted(h.items(), key=lambda kv: (-kv[1], kv[0][1] or 0))[:12])


def run(gen_path, gen_w, ref_path, ref_w, max_size=40, tol=1.0, band=None, xr=None, quiet=False, min_count=1):
    gs, _ = measure_image(gen_path, gen_w, max_size=max_size, band=band, xr=xr)
    rs, _ = measure_image(ref_path, ref_w, max_size=max_size, band=band, xr=xr)
    mism, gh, rh = compare(gs, rs, tol, min_count=min_count)
    if not quiet:
        print(f'[pixel-measure] 소형 성분(≤{max_size}px) gen {len(gs)}개 / ref {len(rs)}개'
              + (f'  band y{band[0]}~{band[1]}' if band else ''))
        print(f'   ref : {_fmt_hist(rh) or "-"}')
        print(f'   gen : {_fmt_hist(gh) or "-"}')
        if mism:
            print(f'   🔴 gen 에만 있는 규격 {len(mism)}종 (ref 에 ±{tol}px 매칭 없음):')
            for m in mism:
                print(f"      - {m['kind']} {m['w']}×{m['h']}" + (f" stroke {m['stroke']}" if m['stroke'] is not None else '')
                      + f" ×{m['count']}")
        else:
            print('   ✓ gen 의 모든 소형 규격이 ref 에 존재')
    return {'gen_count': len(gs), 'ref_count': len(rs), 'mismatches': mism,
            'gen_hist': [{'kind': k[0], 'w': k[1], 'h': k[2], 'stroke': k[3], 'count': n} for k, n in gh.items()],
            'ref_hist': [{'kind': k[0], 'w': k[1], 'h': k[2], 'stroke': k[3], 'count': n} for k, n in rh.items()]}


def _parse_range(s):
    a, b = s.split(':')
    return (float(a), float(b))


def main():
    argv = sys.argv[1:]
    if not argv or '-h' in argv or '--help' in argv:
        print(__doc__)
        return 0
    opt = {}
    pos = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--scale', '--max', '--tol', '--band', '--x', '--min-count'):
            opt[a] = argv[i + 1]; i += 2
        elif a == '--img':
            opt['img'] = (argv[i + 1], argv[i + 2]); i += 3
        else:
            pos.append(a); i += 1
    scale = int(opt.get('--scale', 4))
    max_size = float(opt.get('--max', 40))
    tol = float(opt.get('--tol', 1))
    min_count = int(opt.get('--min-count', 1))
    band = _parse_range(opt['--band']) if '--band' in opt else None
    xr = _parse_range(opt['--x']) if '--x' in opt else None
    if 'img' in opt:
        (g, r) = opt['img']
        gp, gw = g.rsplit(':', 1); rp, rw = r.rsplit(':', 1)
        gen_path, gen_w, ref_path, ref_w = gp, float(gw), rp, float(rw)
    else:
        if len(pos) < 2:
            print('사용: pixel_measure.py <genId> <refId> [--scale 4] [--band y0:y1] | --img gen.png:393 ref.png:402')
            return 2
        sys.path.insert(0, _HERE)
        import figma_mcp_client as fc
        os.makedirs(OUT_DIR, exist_ok=True)
        gen_path = os.path.join(OUT_DIR, 'pm_gen.png')
        ref_path = os.path.join(OUT_DIR, 'pm_ref.png')
        fc.export_image(pos[0], gen_path, 'PNG', scale)
        fc.export_image(pos[1], ref_path, 'PNG', scale)
        gi = fc.parse_content(fc.call_tool('get_node_info', {'nodeId': pos[0]})).get('json') or {}
        ri = fc.parse_content(fc.call_tool('get_node_info', {'nodeId': pos[1]})).get('json') or {}
        gen_w = float((gi.get('node', gi)).get('width') or 393)
        ref_w = float((ri.get('node', ri)).get('width') or 393)
    res = run(gen_path, gen_w, ref_path, ref_w, max_size=max_size, tol=tol, band=band, xr=xr, min_count=min_count)
    print('\n📏 PIXEL-MEASURE-JSON')
    print(json.dumps({'type': 'pixel-measure', 'result': 'pass' if not res['mismatches'] else 'mismatch',
                      **res}, ensure_ascii=False))
    return 0 if not res['mismatches'] else 1


if __name__ == '__main__':
    sys.exit(main())
