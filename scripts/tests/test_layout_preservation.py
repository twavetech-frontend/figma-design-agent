# -*- coding: utf-8 -*-
"""blueprint 명시 FIXED 폭/padding 보존 회귀 테스트 (2026-06-04).

'내 스케줄' 회귀: post-fix·AUTO_FIX enforcer 들이 author 의 FIXED 폭(2-line Date Cell)·
padding(Sched 카드 paddingLeft)을 파괴 → Step E.7.7 가 blueprint 값을 재단언.
여기서는 그 재단언이 의존하는 **수집 함수**(_collect_fixed_widths / _collect_blueprint_padding)가
blueprint 에서 올바른 경로·값을 뽑는지 검증.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import figma_mcp_client as fc  # noqa: E402


def _bp():
    return {"name": "root", "type": "frame", "children": [
        {"name": "List", "type": "frame",
         "autoLayout": {"layoutMode": "VERTICAL", "paddingLeft": 20, "paddingRight": 20},
         "children": [
             {"name": "Card", "type": "frame",
              "autoLayout": {"layoutMode": "HORIZONTAL", "paddingLeft": 16, "paddingRight": 16,
                             "paddingTop": 16, "paddingBottom": 16, "itemSpacing": 14,
                             "counterAxisAlignItems": "CENTER"},
              "children": [
                  {"name": "Date Cell", "type": "frame", "width": 56, "height": 56,
                   "layoutSizingHorizontal": "FIXED", "layoutSizingVertical": "FIXED",
                   "autoLayout": {"layoutMode": "VERTICAL", "paddingLeft": 14, "paddingTop": 14,
                                  "paddingRight": 14, "paddingBottom": 14}},
                  {"name": "Body", "type": "frame", "layoutSizingHorizontal": "FILL",
                   "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 8}},
              ]},
         ]},
    ]}


# ── _collect_fixed_widths ──────────────────────────────────────

def test_fixed_width_collects_date_cell():
    m = fc._collect_fixed_widths(_bp())
    assert m.get(("root", "List", "Card", "Date Cell")) == 56


def test_fixed_width_skips_fill_and_no_width():
    m = fc._collect_fixed_widths(_bp())
    # Body is FILL → not collected; Card/List have no FIXED+width → not collected
    assert ("root", "List", "Card", "Body") not in m
    assert ("root", "List", "Card") not in m


# ── _collect_blueprint_padding ─────────────────────────────────

def test_padding_collects_card_with_layout():
    m = fc._collect_blueprint_padding(_bp())
    card = m.get(("root", "List", "Card"))
    assert card is not None
    assert card["paddingLeft"] == 16 and card["paddingRight"] == 16
    assert card["layoutMode"] == "HORIZONTAL"
    assert card["counterAxisAlignItems"] == "CENTER"
    assert card["itemSpacing"] == 14


def test_padding_collects_only_numeric_fields():
    bp = {"name": "root", "type": "frame", "children": [
        {"name": "X", "type": "frame",
         "autoLayout": {"layoutMode": "VERTICAL", "paddingTop": 10}}]}
    m = fc._collect_blueprint_padding(bp)
    x = m[("root", "X")]
    assert x["paddingTop"] == 10
    assert "paddingLeft" not in x  # not declared → omitted (not forced to 0)


def test_padding_skips_frames_without_autolayout():
    bp = {"name": "root", "type": "frame", "children": [
        {"name": "Plain", "type": "frame"}]}  # no autoLayout
    assert ("root", "Plain") not in fc._collect_blueprint_padding(bp)


# ── multicol-fill small-element exclusion (width 기준) ──────────

def test_module_imports_and_helpers_exist():
    # 핵심 함수들이 존재 (Step E.7.7 / multicol / bp-padding 회귀 방지의 전제)
    assert callable(fc._enforce_fixed_widths)
    assert callable(fc._enforce_blueprint_padding)
    assert callable(fc._collect_fixed_widths)
    assert callable(fc._collect_blueprint_padding)
