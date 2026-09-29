"""flow_connect — 자원 할당·계획·경고 오프라인 테스트 (MCP/osascript 없음, 2026-09-23)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import flow_connect as FC  # noqa: E402

NOCAT = {"arrows": {}, "default": None}   # 실제 카탈로그(등록 화살표)와 무관하게 순수 자원 할당만 검증

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


def test_toolbox_is_template_never_consumed():
    spec = {"section": "S", "_catalog": NOCAT,
            "shapes": [{"key": "q", "kind": "DIAMOND", "text": "?", "anchor": "s2"},
                       {"key": "home", "kind": "SQUARE", "text": "홈", "x": 0, "y": 0}],
            "edges": [{"from": "s1", "to": "s2"}, {"from": "s2", "to": "@q"}, {"from": "@q", "to": "@home"},
                      {"from": "s1", "to": "s5", "connector": "c1"}]}
    plan = FC.build_plan(spec, SECTION, TOOLBOX)
    assert plan['need'] == {'CONNECTOR': 3, 'DIAMOND': 1, 'SQUARE': 1}
    assert plan['alloc'] == {'CONNECTOR': [], 'DIAMOND': [], 'SQUARE': []}          # 원본 소비 없음
    assert plan['dup'] == {'CONNECTOR': 3, 'DIAMOND': 1, 'SQUARE': 1}               # 전부 복제
    assert plan['seed']['CONNECTOR'] == 't1' and plan['seed']['DIAMOND'] == 't3'    # 툴박스 템플릿
    assert plan['seed']['SQUARE'] == 'q1'                                            # 툴박스에 없으면 섹션 노드를 템플릿으로
    assert plan['templates'] == {'CONNECTOR': 't1', 'DIAMOND': 't3'}


def test_consume_pool_is_opt_in_legacy():
    spec = {"section": "S", "_catalog": NOCAT, "consumePool": True, "edges": [{"from": "s1", "to": "s2"}, {"from": "s2", "to": "s5"}, {"from": "s1", "to": "s5"}]}
    plan = FC.build_plan(spec, SECTION, TOOLBOX)
    assert plan['alloc']['CONNECTOR'] == ['t1', 't2'] and plan['dup']['CONNECTOR'] == 1


def test_parallelogram_right_normalized():
    assert FC.kind_of({"type": "SHAPE_WITH_TEXT", "shapeType": "PARALLELOGRAM_RIGHT"}) == 'PARALLELOGRAM'
    assert FC.templates_of([{"id": "p", "type": "SHAPE_WITH_TEXT", "shapeType": "PARALLELOGRAM_RIGHT"}]) == {'PARALLELOGRAM': 'p'}


def test_unknown_shape_key_and_missing_seed_raise():
    try:
        FC.build_plan({"section": "S", "_catalog": NOCAT, "edges": [{"from": "s1", "to": "@nope"}]}, SECTION, [])
    except ValueError as e:
        assert 'shapes key' in str(e)
    else:
        raise AssertionError('ValueError 기대')
    try:
        FC.build_plan({"section": "S", "_catalog": NOCAT, "shapes": [{"key": "p", "kind": "PARALLELOGRAM", "text": "t", "x": 0, "y": 0}]}, SECTION, [])
    except ValueError as e:
        assert 'my tool box' in str(e) and 'PARALLELOGRAM' in str(e)
    else:
        raise AssertionError('ValueError 기대')


def test_long_bottom_bottom_edge_warns_but_right_left_does_not():
    spec = {"section": "S", "_catalog": NOCAT, "edges": [
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


def test_bottom_to_top_shape_edge_warns():
    spec = {"section": "S", "_catalog": NOCAT, "shapes": [{"key": "q", "kind": "DIAMOND", "text": "?", "x": 0, "y": 0}],
            "edges": [{"from": "s1", "fromMagnet": "BOTTOM", "to": "@q", "toMagnet": "TOP"}]}
    plan = FC.build_plan(spec, SECTION, TOOLBOX)
    assert any('BOTTOM→TOP' in w for w in plan['warnings'])      # 도형 x=0 은 s1(x102~495) 범위 밖 → 경고
    below = {"section": "S", "_catalog": NOCAT, "shapes": [{"key": "q", "kind": "DIAMOND", "text": "?", "x": 150, "y": 1400}],
             "edges": [{"from": "s1", "fromMagnet": "BOTTOM", "to": "@q", "toMagnet": "TOP"}]}
    assert FC.build_plan(below, SECTION, TOOLBOX)['warnings'] == []   # 바로 아래면 정상


def test_accept_duplicate_rejects_section_and_wrong_parent():
    src = {"id": "tpl", "type": "CONNECTOR", "parentId": "toolbox"}
    assert FC.accept_duplicate({"id": "new1", "type": "CONNECTOR", "parentId": "toolbox"}, src, set()) is True
    assert FC.accept_duplicate({"id": "toolbox", "type": "SECTION", "parentId": "page"}, src, set()) is False   # 툴박스 섹션 오인 실사고
    assert FC.accept_duplicate({"id": "tpl", "type": "CONNECTOR", "parentId": "toolbox"}, src, set()) is False  # 원본 자신
    assert FC.accept_duplicate({"id": "new1", "type": "CONNECTOR", "parentId": "toolbox"}, src, {"new1"}) is False
    assert FC.accept_duplicate({"id": "x", "type": "CONNECTOR", "parentId": "elsewhere"}, src, set()) is False
