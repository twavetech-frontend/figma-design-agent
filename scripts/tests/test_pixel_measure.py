"""규칙 0-F-3 (2026-09-08) — 소형 요소 픽셀 실측 대조 오프라인 테스트 (합성 이미지, 1초)."""
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import pixel_measure as pm  # noqa: E402


def _draw(path, dev_w, scale, dots):
    """dots: (cx, cy, kind, size, stroke, color) 디바이스 px → scale 배 이미지."""
    im = Image.new('RGB', (dev_w * scale, 200 * scale), 'white')
    d = ImageDraw.Draw(im)
    for cx, cy, kind, size, stroke, color in dots:
        r = size * scale / 2
        box = [cx * scale - r, cy * scale - r, cx * scale + r - 1, cy * scale + r - 1]
        if kind == 'fill':
            d.ellipse(box, fill=color)
        else:
            d.ellipse(box, outline=color, width=int(stroke * scale))
    im.save(path)
    return path


def test_measures_fill_and_ring_sizes(tmp_path):
    p = _draw(str(tmp_path / 'ref.png'), 100, 4, [
        (20, 50, 'fill', 4, None, (85, 200, 192)),
        (40, 50, 'ring', 10, 3, (85, 200, 192)),
        (60, 50, 'fill', 4, None, (184, 182, 201)),   # 밝은 회색 도트도 잡혀야 한다
    ])
    specs, scale = pm.measure_image(p, 100)
    assert scale == 4
    kinds = sorted((s['kind'], s['w'], s['h']) for s in specs)
    assert ('fill', 4.0, 4.0) in kinds
    ring = [s for s in specs if s['kind'] == 'ring'][0]
    assert ring['w'] == 10.0 and abs(ring['stroke'] - 3.0) <= 0.5


def test_compare_flags_gen_only_sizes(tmp_path):
    ref = _draw(str(tmp_path / 'ref.png'), 100, 4, [(20, 50, 'fill', 4, None, (0, 0, 0)), (40, 50, 'ring', 10, 3, (0, 0, 0))])
    gen_bad = _draw(str(tmp_path / 'gen_bad.png'), 100, 4, [(20, 50, 'fill', 8, None, (0, 0, 0)), (40, 50, 'ring', 12, 2, (0, 0, 0))])
    gen_ok = _draw(str(tmp_path / 'gen_ok.png'), 100, 4, [(20, 50, 'fill', 4, None, (0, 0, 0)), (40, 50, 'ring', 10, 3, (0, 0, 0))])
    bad = pm.run(gen_bad, 100, ref, 100, quiet=True)
    assert len(bad['mismatches']) == 2
    ok = pm.run(gen_ok, 100, ref, 100, quiet=True)
    assert ok['mismatches'] == []


def test_large_components_ignored(tmp_path):
    p = str(tmp_path / 'a.png')
    im = Image.new('RGB', (400, 400), 'white')
    ImageDraw.Draw(im).rectangle([10, 10, 300, 300], fill=(85, 200, 192))  # 카드 면
    im.save(p)
    specs, _ = pm.measure_image(p, 100)
    assert specs == []
