"""flow_connect — 자원 할당·계획·경고 오프라인 테스트 (MCP/osascript 없음, 2026-09-23)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import flow_connect as FC  # noqa: E402

SECTION = [
    {"id": "s1", "type": "FRAME", "name": "imin_a", "x": 102, "y": 120},
    {"id": "s2", "type": "FRAME", "name": "imin_b", "x": 1152, "y": 120},
    {"id": "s5", "type": "FRAME", "name": "imin_e", "x": 4302, "y": 120},
    {"id": "c1", "type": "CONNECTOR", "name": "flow_arrow", "x": 500, "y": 900},
    {"id": "d1", "type": "SHAPE_WITH_TEXT", "shapeType": "DIAMOND", "name": "flow_cond", "x": 200, "y": 1300},
    {"id": "q1", "type": "SHAPE_WITH_TEXT", "shapeType": "SQUARE", "name": "flow_sq", "x": 900, "y": 1300},
]
TOOLBOX = [
    {"id": "t1", "type": "CONNECTOR", "name": "flow_arrow"},
    {"id": "t2", "type": "CONNECTOR", "name": "flow_arrow"},
    {"id": "t3", "type": "SHAPE_WITH_TEXT", "shapeType": "DIAMOND", "name": "x"},
]


def test_pool_first_then_duplicate_from_auto_seed():
    spec = {"section": "S",
            "shapes": [{"key": "q", "kind": "DIAMOND", "text": "?", "anchor": "s2"},
                       {"key": "home", "kind": "SQUARE", "text": "홈", "x": 0, "y": 0}],
            "edges": [{"from": "s1", "to": "s2"}, {"from": "s2", "to": "@q"}, {"from": "@q", "to": "@home"},
                      {"from": "s1", "to": "s5", "connector": "c1"}]}
    plan = FC.build_plan(spec, SECTION, TOOLBOX)
    assert plan['need'] == {'CONNECTOR': 3, 'DIAMOND': 1, 'SQUARE': 1}
    assert plan['alloc']['CONNECTOR'] == ['t1', 't2'] and plan['dup']['CONNECTOR'] == 1
    assert plan['alloc']['DIAMOND'] == ['t3'] and plan['dup']['DIAMOND'] == 0
    assert plan['dup']['SQUARE'] == 1 and plan['seed']['SQUARE'] == 'q1'   # 섹션에서 자동 탐색
    assert plan['seed']['CONNECTOR'] == 'c1'


def test_unknown_shape_key_and_missing_seed_raise():
    try:
        FC.build_plan({"section": "S", "edges": [{"from": "s1", "to": "@nope"}]}, SECTION, [])
    except ValueError as e:
        assert 'shapes key' in str(e)
    else:
        raise AssertionError('ValueError 기대')
    try:
        FC.build_plan({"section": "S", "shapes": [{"key": "p", "kind": "PARALLELOGRAM", "text": "t", "x": 0, "y": 0}]}, SECTION, [])
    except ValueError as e:
        assert 'seed' in str(e)
    else:
        raise AssertionError('ValueError 기대')


def test_long_bottom_bottom_edge_warns_but_right_left_does_not():
    spec = {"section": "S", "edges": [
        {"from": "s1", "to": "s5", "fromMagnet": "BOTTOM", "toMagnet": "BOTTOM"},
        {"from": "s1", "to": "s5", "fromMagnet": "RIGHT", "toMagnet": "LEFT"},
    ]}
    plan = FC.build_plan(spec, SECTION, TOOLBOX)
    assert len(plan['warnings']) == 1 and 'BOTTOM→BOTTOM' in plan['warnings'][0]


def test_shape_position_anchor_offsets_and_absolute():
    assert FC.shape_position({"anchor": "s2"}, {"x": 1152, "y": 120}) == (1200, 1300)
    assert FC.shape_position({"x": 5, "y": 6}) == (5, 6)


def test_duplicate_uses_menu_click_not_keystroke():
    cmd = ' '.join(FC.osascript_duplicate_cmd())
    assert 'click menu item "Duplicate" of menu "Edit"' in cmd
    assert 'keystroke' not in cmd
