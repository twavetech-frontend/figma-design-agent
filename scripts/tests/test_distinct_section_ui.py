# -*- coding: utf-8 -*-
"""R63 — 인접 섹션 동일 UI 차단 회귀 테스트 (2026-06-04).

사용자 보고: '시작 방법 카드'와 '출석/초대 카드'가 둘 다 [틴트 아이콘 원 + 제목 + 부제]
2-up 그리드라 다른 정보인데 같은 정보처럼 보임. → 인접 카드-그리드 섹션의 구조
시그니처가 같으면 WARN, 시각 언어가 다르면(그리드 vs 리스트) 통과.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from design_rules import R63_distinct_section_ui as R63  # noqa: E402


def _card():
    return {"type": "frame", "cornerRadius": 16, "children": [
        {"type": "frame", "cornerRadius": 999, "children": [{"type": "icon"}]},
        {"type": "text"}, {"type": "text"}]}


def _grid_section(name):
    return {"name": name, "type": "frame", "autoLayout": {"layoutMode": "VERTICAL"},
            "children": [{"type": "frame", "autoLayout": {"layoutMode": "HORIZONTAL"},
                          "children": [_card(), _card()]}]}


def _list_row():
    return {"type": "frame", "cornerRadius": 12, "autoLayout": {"layoutMode": "HORIZONTAL"},
            "children": [{"type": "frame", "cornerRadius": 999, "children": [{"type": "icon"}]},
                         {"type": "frame", "children": [{"type": "text"}, {"type": "text"}]},
                         {"type": "icon"}]}


def _list_section(name):
    return {"name": name, "type": "frame", "autoLayout": {"layoutMode": "VERTICAL"},
            "children": [_list_row(), _list_row()]}


def _warns(bp):
    return list(R63._check_blueprint(bp, {}))


def test_two_identical_grids_warn():
    bp = {"type": "frame", "children": [_grid_section("Start"), _grid_section("Quick")]}
    vs = _warns(bp)
    assert len(vs) == 1
    assert vs[0].rule_id == "R63-distinct-section-ui"


def test_grid_then_list_no_warn():
    bp = {"type": "frame", "children": [_grid_section("Start"), _list_section("Quick")]}
    assert _warns(bp) == []


def test_non_adjacent_grids_no_warn():
    # 사이에 다른(리스트) 섹션이 끼면 인접 아님 → WARN 안 함
    bp = {"type": "frame", "children": [
        _grid_section("Start"), _list_section("Mid"), _grid_section("Other")]}
    assert _warns(bp) == []


def test_single_grid_no_warn():
    bp = {"type": "frame", "children": [_grid_section("Only")]}
    assert _warns(bp) == []


def test_non_card_sections_ignored():
    # 카드 그리드가 아닌 단순 텍스트 섹션 2개는 대상 아님
    txt = lambda n: {"name": n, "type": "frame", "children": [{"type": "text"}]}
    bp = {"type": "frame", "children": [txt("A"), txt("B")]}
    assert _warns(bp) == []


def test_registered_in_registry():
    import design_rules  # noqa: F401  (triggers auto-import of all rules)
    from design_rules.base import REGISTRY
    assert REGISTRY.get("R63-distinct-section-ui") is not None
