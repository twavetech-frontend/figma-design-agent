"""cmd_build 전역 drop-shadow strip 이 DS effect style 바인딩(2-B-3 shadow-basic)을 보존하는지 —
2026-09-11 회귀(post-fix 가 막 붙인 카드 elevation 을 cmd_build 가 도로 지움) 재발 방지."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import figma_mcp_client as fc  # noqa: E402

DROP_RAW = {'type': 'DROP_SHADOW', 'visible': True, 'offset': {'x': 0, 'y': 4}, 'radius': 12}
DS_INNER = {'type': 'INNER_SHADOW', 'visible': True, 'offset': {'x': 0, 'y': 1}, 'radius': 0}
DS_DROP = {'type': 'DROP_SHADOW', 'visible': True, 'offset': {'x': 0, 'y': 10}, 'radius': 24}


def _tree(children):
    return {'id': '1:1', 'name': 'root', 'type': 'FRAME', 'children': children}


def test_raw_drop_shadow_is_stripped():
    t = _tree([{'id': '1:2', 'name': 'Card', 'type': 'FRAME', 'effects': [DROP_RAW]}])
    assert fc._shadow_strip_targets(t) == ['1:2']


def test_ds_shadow_basic_signature_is_kept():
    t = _tree([{'id': '1:3', 'name': 'Additional Deposit Notice', 'type': 'FRAME', 'effects': [DS_INNER, DS_DROP]}])
    assert fc._shadow_strip_targets(t) == []
    assert fc._is_ds_bound_shadow(t['children'][0]) is True


def test_effect_style_id_is_kept_even_if_single_drop():
    t = _tree([{'id': '1:4', 'name': 'Summary Card', 'type': 'FRAME', 'effectStyleId': 'S:abc', 'effects': [DROP_RAW]}])
    assert fc._shadow_strip_targets(t) == []


def test_ds_fingerprint_table_match_is_kept():
    md = {'type': 'DROP_SHADOW', 'visible': True, 'offset': {'x': 0, 'y': 4}, 'radius': 6}  # shadow-md
    t = _tree([{'id': '1:5', 'name': 'Card', 'type': 'FRAME', 'effects': [md]}])
    assert fc._shadow_strip_targets(t) == []


def test_instance_internal_and_polish_names_skipped():
    t = _tree([{'id': 'I1:6;2:2', 'name': 'x', 'type': 'FRAME', 'effects': [DROP_RAW]},
               {'id': '1:7', 'name': 'Hero Banner', 'type': 'FRAME', 'effects': [DROP_RAW],
                'children': [{'id': '1:8', 'name': 'inner', 'type': 'FRAME', 'effects': [DROP_RAW]}]}])
    assert fc._shadow_strip_targets(t) == ['1:8']


def test_stacked_ds_shadow_xl_is_kept():
    """shadow-xl = DROP(3,3)+DROP(8,8)+DROP(20,24) 스택 — 첫 DROP 만 보면 표에 없어 지워지던 구멍."""
    xl = [{'type': 'DROP_SHADOW', 'visible': True, 'offset': {'x': 0, 'y': 3}, 'radius': 3},
          {'type': 'DROP_SHADOW', 'visible': True, 'offset': {'x': 0, 'y': 8}, 'radius': 8},
          {'type': 'DROP_SHADOW', 'visible': True, 'offset': {'x': 0, 'y': 20}, 'radius': 24}]
    t = _tree([{'id': '1:9', 'name': 'Notice', 'type': 'FRAME', 'effects': xl}])
    assert fc._shadow_strip_targets(t) == []
