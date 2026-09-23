"""screen_description — 계획 수립 오프라인 테스트 (MCP 왕복 없음, 2026-09-23).
fixture = clone_variant 의 05_stagedetail 트리(부모 상대 x/y, absoluteBoundingBox 없음)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', 'design_rules'))
import screen_description as SD  # noqa: E402

FX = os.path.join(HERE, 'fixtures', 'clone_variant_stagedetail.json')
TREE = json.load(open(FX, encoding='utf-8'))

SPEC = {
    "screen": "4366:128696",
    "rows": [
        {"section": "Status Bar", "title": "상단 영역", "text": "[기능]\n· 상태바"},
        {"section": "Pink Header", "title": "헤더 영역", "text": "[기능]\n· 인원수 색"},
        {"section": "Member list", "text": "멤버 영역\n[기능]\n· 순번 목록\n[예외처리]\n· 없음"},
    ],
}


def test_row_text_prefixes_title():
    assert SD.row_text({"title": "T", "text": "b"}) == "T\nb"
    assert SD.row_text({"text": "b"}) == "b"


def test_plan_resolves_sections_and_marker_y_in_screen_order():
    plan = SD.build_plan(SPEC, TREE)
    assert [r['n'] for r in plan['rows']] == [1, 2, 3]
    ys = [r['markerY'] for r in plan['rows']]
    assert ys[0] == 0 and ys[1] == 62            # Status Bar y0, Pink Header y62 (부모 상대 누적)
    assert ys == sorted(ys)
    assert plan['warnings'] == []


def test_plan_warns_on_missing_header_and_order():
    spec = {"screen": "x", "rows": [
        {"section": "Pink Header", "text": "헤더만"},
        {"section": "Status Bar", "text": "[기능]\n· 상태바"},
    ]}
    plan = SD.build_plan(spec, TREE)
    assert any("'[기능]'" in w for w in plan['warnings'])
    assert any('순서' in w for w in plan['warnings'])


def test_plan_rejects_empty_and_too_many_rows():
    for bad in ({"screen": "x", "rows": []}, {"screen": "x", "rows": [{"text": "a"}] * 20}):
        try:
            SD.build_plan(bad, TREE)
        except ValueError:
            pass
        else:
            raise AssertionError('ValueError 기대')


def test_skip_markers_ignores_sections():
    plan = SD.build_plan(dict(SPEC, skipMarkers=True), TREE)
    assert all(r['markerY'] is None for r in plan['rows'])
