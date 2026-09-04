"""rebuild_track 오프라인 회귀 테스트 (2026-09-04 — "다시 생성 20분" 재발 방지 ②).

Figma 왕복 없이 원본 트리 fixture → blueprint 생성만 검증한다. 휴리스틱을 고칠 때 이 테스트가
1초에 회귀를 잡는다 (실물 파이프라인 5회 반복 = 10분의 대체).
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import rebuild_track as RT  # noqa: E402

FX = os.path.join(HERE, 'fixtures', 'rebuild_tree_stagedetail_1_5_1.json')


def _bp():
    fx = json.load(open(FX, encoding='utf-8'))
    RT.call = lambda t, a: (_ for _ in ()).throw(AssertionError(f'offline: MCP call {t}'))  # 왕복 금지
    return RT.build_blueprint(fx['src'], fx['tree'])


def _walk(n, out=None):
    out = [] if out is None else out
    out.append(n)
    for c in n.get('children') or []:
        _walk(c, out)
    return out


def test_no_mcp_roundtrip_and_text_1to1():
    bp, ctx = _bp()
    texts = [n for n in _walk(bp) if n.get('type') == 'text']
    assert len(texts) == 27  # 원본 TEXT 27 (CTA 라벨 2개는 instance 로 전환)
    assert '스테이지에 참여합니다.' in [t['text'] for t in texts]


def test_weights_restored_from_segments():
    # fontName 이 figma.mixed 로 생략된 소스 — segments fontWeight 로 굵기 복원 (실사고: 전부 Regular 로 빌드)
    bp, ctx = _bp()
    bold = [n for n in _walk(bp) if n.get('type') == 'text' and n['fontName']['style'] == 'Bold']
    assert ctx.src_weights.get('Bold', 0) >= 10
    assert len(bold) == ctx.src_weights['Bold']
    assert any(n['text'].startswith('스테이지에') for n in bold)


def test_transplants_are_fixed_placeholders():
    bp, ctx = _bp()
    assert len(ctx.transplants) == 4  # 단계 화살표 / 선물 아이콘 / 쿠폰 원 / 정보 아이콘
    for name in ctx.transplants:
        node = next(n for n in _walk(bp) if n.get('name') == name)
        assert node['layoutSizingHorizontal'] == 'FIXED' and node.get('_keepSizing') is True
        assert node['width'] <= 120 and node['height'] <= 120


def test_table_rows_space_between():
    bp, ctx = _bp()
    rows = [n for n in _walk(bp) if (n.get('autoLayout') or {}).get('primaryAxisAlignItems') == 'SPACE_BETWEEN'
            and n.get('name', '').startswith('Row')]
    assert len(rows) == 7
    for r in rows:
        assert all(c.get('layoutSizingHorizontal') == 'HUG' for c in r['children'])


def test_step_segments_and_bars():
    bp, ctx = _bp()
    seg = next(n for n in _walk(bp) if n.get('name', '').startswith('Segments'))
    labels = [c for c in seg['children'] if c.get('type') == 'text']
    assert [c['text'] for c in labels] == ['1단계', '2단계']
    assert all(c['layoutSizingHorizontal'] == 'FILL' and c.get('textAlignHorizontal') == 'CENTER' for c in labels)
    bars = next(n for n in _walk(bp) if n.get('name', '').startswith('Bars'))
    assert bars['fill'] == '$token(bg-secondary)'  # R21.1 위계 경유
    assert len(bars['children']) == 2 and all(c['layoutSizingHorizontal'] == 'FILL' for c in bars['children'])


def test_cta_action_buttons_and_footer():
    bp, ctx = _bp()
    ab = next(n for n in bp['children'] if n['name'] == 'Action Bar')
    kids = ab['children']
    assert [k['_instanceText'] for k in kids] == ['취소', '다음']
    assert kids[0]['instanceProperties']['Hierarchy'] == 'Secondary' and kids[0]['layoutSizingHorizontal'] == 'FIXED'
    assert kids[1]['instanceProperties']['Hierarchy'] == 'Primary' and kids[1]['layoutSizingHorizontal'] == 'FILL'
    assert kids[0]['width'] < 200
    assert any(n['name'] == 'Footer' for n in bp['children'])
    assert bp['children'][0]['name'] == 'Content' and bp['children'][0]['layoutSizingVertical'] == 'FILL'


def test_names_avoid_lint_trigger_words_and_brand_hue():
    bp, ctx = _bp()
    bad = re.compile(r'badge|pill|chip|tag|button|dropdown|tab', re.I)
    for n in _walk(bp)[1:]:  # 루트 이름은 원본 화면명 승계(stagedetail 의 'tag' 등) — 검사 제외
        assert not bad.search(n.get('name') or ''), n.get('name')
    # 구 브랜드 보라(#6042f9) 는 새 브랜드 토큰으로 승계 — chroma 후적용 목록에 남지 않는다
    assert all(hx.lower() != '#6042f9' for hx in ctx.chroma.values())
    assert any(hx.lower() == '#55c8c0' for hx in ctx.chroma.values())  # 스테이지 민트는 스타일 후적용 대상
