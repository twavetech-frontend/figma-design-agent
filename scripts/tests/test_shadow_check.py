"""shadow_check 오프라인 테스트 — 합성 이미지(흰 배경 + 카드 + 아래쪽 그라데이션)."""
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import shadow_check as sc  # noqa: E402

BOX = (20, 100, 160, 60)  # x,y,w,h (디바이스 px)


def _draw(path, dev_w=200, scale=2, shadow=True, strength=30, depth=24):
    im = Image.new('L', (dev_w * scale, 300 * scale), 255)
    d = ImageDraw.Draw(im)
    x, y, w, h = BOX
    if shadow:
        # 카드 아래로 갈수록 옅어지는 램프 + 좌우 약한 램프
        for i in range(depth):
            v = 255 - int(strength * (1 - i / depth))
            d.rectangle([x * scale, (y + h + i) * scale, (x + w) * scale, (y + h + i + 1) * scale - 1], fill=v)
            v2 = 255 - int(strength * 0.3 * (1 - i / depth))
            d.rectangle([(x - i - 1) * scale, y * scale, (x - i) * scale - 1, (y + h) * scale], fill=v2)
            d.rectangle([(x + w + i) * scale, y * scale, (x + w + i + 1) * scale - 1, (y + h) * scale], fill=v2)
    d.rectangle([x * scale, y * scale, (x + w) * scale - 1, (y + h) * scale - 1], fill=255, outline=200)
    im.save(path)
    return path


def test_ramp_detects_gradient_and_flat(tmp_path):
    with_s = _draw(str(tmp_path / 's.png'), shadow=True)
    no_s = _draw(str(tmp_path / 'n.png'), shadow=False)
    ds = sc.measure_box(with_s, 200, BOX)
    dn = sc.measure_box(no_s, 200, BOX)
    assert ds['bottom'] >= sc.SHADOW_THR and sc.judge(ds) == 'shadow'
    assert dn['bottom'] is not None and abs(dn['bottom']) < sc.NONE_THR and sc.judge(dn) == 'none'


def test_compare_flags_missing_shadow_only(tmp_path):
    ref = _draw(str(tmp_path / 'ref.png'), shadow=True)
    gen_no = _draw(str(tmp_path / 'gen_no.png'), shadow=False)
    gen_ok = _draw(str(tmp_path / 'gen_ok.png'), shadow=True, strength=24)
    r = sc.compare(gen_no, 200, ref, 200, [BOX], ['Notice Card'], [0], quiet=True)
    assert r['result'] == 'mismatch' and 'Notice Card' in r['flags'][0] and 'ref 그림자 있음' in r['flags'][0]
    r2 = sc.compare(gen_ok, 200, ref, 200, [BOX], ['Notice Card'], [2], quiet=True)
    assert r2['result'] == 'match' and r2['flags'] == []


def test_ref_scale_conversion(tmp_path):
    """ref 가 gen 보다 넓은(402 vs 393) 캡처여도 박스를 배율 환산해 같은 카드를 잰다."""
    ref = _draw(str(tmp_path / 'ref402.png'), dev_w=204, shadow=True)  # 204/200 = 1.02 배율
    gen = _draw(str(tmp_path / 'gen.png'), dev_w=200, shadow=False)
    r = sc.compare(gen, 200, ref, 204, [BOX], quiet=True)
    assert r['rows'][0]['ref_judge'] == 'shadow'


def test_refine_box_realigns_to_border_after_vertical_drift(tmp_path):
    """gen 레이아웃이 위로 20px 밀려도 ref 박스를 실제 보더에 재정렬해 그림자를 잰다."""
    ref = _draw(str(tmp_path / 'ref.png'), shadow=True)
    drifted = (BOX[0], BOX[1] - 20, BOX[2], BOX[3])   # 잘못 옮겨진 박스(실제보다 20 위)
    rb = sc.refine_box(ref, 200, drifted)
    assert abs(rb[1] - BOX[1]) <= 1.5 and abs(rb[3] - BOX[3]) <= 2
    assert sc.judge(sc.measure_box(ref, 200, rb)) == 'shadow'


CALIB = {
    'Shadows/shadow-basic': {'bottom': 6.0, 'left': 3.2, 'right': 3.0, 'extent': 22},
    'Shadows/shadow-md': {'bottom': 13.3, 'left': 3.0, 'right': 2.5, 'extent': 10},
    'Shadows/shadow-xl': {'bottom': 21.2, 'left': 4.3, 'right': 4.0, 'extent': 30},
    'Shadows/shadow-2xl': {'bottom': 20.6, 'left': 5.0, 'right': 4.8, 'extent': 48},
}


def test_recommend_nearest_style_uses_extent_to_break_ties():
    """캡처 floating 카드 실측(18.6/4.6/4.4, 퍼짐≈25) — Δ 만 보면 2xl 과 xl 이 비슷하지만 퍼짐 길이로 xl."""
    ref = {'bottom': 18.6, 'left': 4.6, 'right': 4.4, 'extent': 25}
    name, dist = sc.recommend_style(ref, CALIB)
    assert name == 'Shadows/shadow-xl'
    faint = {'bottom': 6.5, 'left': 3.0, 'right': 3.0, 'extent': 20}
    assert sc.recommend_style(faint, CALIB)[0] == 'Shadows/shadow-basic'


def test_ramp_extent_measures_spread():
    ramp = [230, 234, 238, 242, 246, 249, 251, 252, 253, 253, 253, 253]
    assert sc.ramp_extent(ramp, tol=2.0) == 6  # 251 부터 far(253)-2 이상
    assert sc.ramp_extent([255] * 12) == 0


def test_compare_flag_carries_recommendation(tmp_path):
    ref = _draw(str(tmp_path / 'ref.png'), shadow=True)
    gen_no = _draw(str(tmp_path / 'gen_no.png'), shadow=False)
    r = sc.compare(gen_no, 200, ref, 200, [BOX], ['Notice Card'], [0], quiet=True, calib=CALIB)
    assert r['rows'][0]['recommend'] and r['rows'][0]['recommend']['style'].startswith('Shadows/')
    assert '권장 Shadows/' in r['flags'][0]


def test_apply_recommendations_binds_only_missing():
    calls = []

    class FakeFC:
        def _load_effect_style_map(self):
            return {'Shadows/shadow-xl': 'KEY_XL'}

        def call_tool(self, name, params):
            calls.append((name, params)); return {}
    rows = [{'name': 'A', 'gen_judge': 'none', 'recommend': {'style': 'Shadows/shadow-xl', 'distance': 3.0}},
            {'name': 'B', 'gen_judge': 'shadow', 'recommend': {'style': 'Shadows/shadow-xl', 'distance': 1.0}},
            {'name': 'C', 'gen_judge': 'none', 'recommend': None}]
    done = sc.apply_recommendations(FakeFC(), rows, ['1:1', '1:2', '1:3'])
    assert done == [('A', 'Shadows/shadow-xl', True)]
    assert calls == [('set_effect_style_id', {'nodeId': '1:1', 'effectStyleId': 'S:KEY_XL,1:1'})]
