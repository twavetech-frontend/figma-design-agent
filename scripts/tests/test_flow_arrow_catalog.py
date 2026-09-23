"""flow_arrow_catalog — 용도별 화살표 템플릿 선택 오프라인 테스트 (2026-09-23)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import flow_arrow_catalog as FAC  # noqa: E402
import flow_connect as FC  # noqa: E402

SECTION = [{"id": "s1", "type": "FRAME", "x": 0, "y": 0}, {"id": "s2", "type": "FRAME", "x": 1050, "y": 0},
           {"id": "c0", "type": "CONNECTOR", "name": "flow_arrow", "x": 0, "y": 900}]
TOOLBOX = [{"id": "t_tap", "type": "CONNECTOR"}, {"id": "t_auto", "type": "CONNECTOR"}]


def _cat():
    cat = {'toolbox': 'tb', 'arrows': {}, 'default': None}
    FAC.register(cat, 'tap', 't_tap', '사용자 탭', when=['버튼 탭'], style={'strokeWeight': 4})
    FAC.register(cat, 'auto', 't_auto', '시스템 자동 전이', defaults={'lineType': 'ELBOWED', 'fromMagnet': 'RIGHT', 'toMagnet': 'LEFT'})
    return cat


def test_register_sets_default_and_template_lookup():
    cat = _cat()
    assert cat['default'] == 'tap'
    assert FAC.template_for(cat, 'auto')[0] == 't_auto'
    assert FAC.template_for(cat, None)[0] == 't_tap'
    try:
        FAC.template_for(cat, 'nope')
    except KeyError as e:
        assert 'tap' in str(e)
    else:
        raise AssertionError('KeyError 기대')


def test_plan_counts_connectors_per_type_and_seeds_from_catalog():
    cat = _cat()
    spec = {"section": "S", "_catalog": cat,
            "edges": [{"from": "s1", "to": "s2", "type": "tap"}, {"from": "s2", "to": "s1", "type": "auto"}, {"from": "s1", "to": "s2"}]}
    plan = FC.build_plan(spec, SECTION, TOOLBOX)
    assert plan['need'] == {'CONNECTOR:tap': 2, 'CONNECTOR:auto': 1}      # type 생략 → default(tap)
    assert plan['seed']['CONNECTOR:tap'] == 't_tap' and plan['seed']['CONNECTOR:auto'] == 't_auto'
    assert plan['dup'] == {'CONNECTOR:tap': 2, 'CONNECTOR:auto': 1}


def test_unregistered_type_raises():
    spec = {"section": "S", "_catalog": _cat(), "edges": [{"from": "s1", "to": "s2", "type": "mystery"}]}
    try:
        FC.build_plan(spec, SECTION, TOOLBOX)
    except ValueError as e:
        assert 'mystery' in str(e) and 'arrow-register' in str(e)
    else:
        raise AssertionError('ValueError 기대')


def test_empty_catalog_falls_back_to_plain_connector():
    spec = {"section": "S", "_catalog": {'arrows': {}, 'default': None}, "edges": [{"from": "s1", "to": "s2"}]}
    plan = FC.build_plan(spec, SECTION, TOOLBOX)
    assert plan['need'] == {'CONNECTOR': 1} and plan['seed']['CONNECTOR'] == 't_tap'


def test_cond_yes_must_start_from_diamond():
    cat = _cat()
    cat['arrows']['tap']['constraints'] = {}
    FAC.register(cat, 'cond-yes', 't_yes', '◇ 네 가지', style={}, defaults={})
    cat['arrows']['cond-yes']['constraints'] = {'fromKind': 'DIAMOND'}
    tb = TOOLBOX + [{"id": "t_yes", "type": "CONNECTOR"}, {"id": "t_dia", "type": "SHAPE_WITH_TEXT", "shapeType": "DIAMOND"}]
    ok = {"section": "S", "_catalog": cat, "shapes": [{"key": "q", "kind": "DIAMOND", "text": "?", "x": 0, "y": 0}],
          "edges": [{"from": "@q", "to": "s2", "type": "cond-yes"}]}
    assert FC.build_plan(ok, SECTION, tb)['need'] == {'CONNECTOR:cond-yes': 1, 'DIAMOND': 1}
    bad = {"section": "S", "_catalog": cat, "edges": [{"from": "s1", "to": "s2", "type": "cond-yes"}]}
    try:
        FC.build_plan(bad, SECTION, tb)
    except ValueError as e:
        assert 'DIAMOND' in str(e) and '0-FLOW-2' in str(e)
    else:
        raise AssertionError('ValueError 기대')
