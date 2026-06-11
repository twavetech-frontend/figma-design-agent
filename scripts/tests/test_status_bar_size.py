# -*- coding: utf-8 -*-
"""Status Bar 393×62 회귀 테스트 — 2026-06-12 사용자 보고.

회귀: R24 inject 와 code.js FORCED 삽입이 vertical 'HUG' 를 강제해 DS 마스터
(393×62 FIXED) 인스턴스가 내부 콘텐츠 자연 높이 63.5 로 재측정·전파됐다.
- R24 inject 노드는 FIXED 62 여야 한다 (HUG/height 50 금지).
- post-fix 백스톱 `_status_bar_fix_needed` 판정이 변형(HUG·≠62)만 정확히 잡아야 한다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as fc
from design_rules import R24_status_bar as r24


# ── R24 inject 노드 스펙 ──────────────────────────────────────────

def _mobile_bp(children=None):
    return {"name": "screen", "type": "frame", "width": 393, "children": children or []}


def test_r24_inject_status_bar_is_fixed_62():
    bp = r24._inject(_mobile_bp())
    sb = bp["children"][0]
    assert "status bar" in sb["name"].lower()
    assert sb["layoutSizingVertical"] == "FIXED"
    assert sb["height"] == r24.STATUS_BAR_HEIGHT == 62
    assert sb["layoutSizingHorizontal"] == "FILL"


def test_r24_inject_skips_when_status_bar_exists():
    bp = _mobile_bp([{"name": "Status Bar", "type": "instance"}])
    out = r24._inject(bp)
    assert len(out["children"]) == 1  # 중복 삽입 없음


def test_r24_verify_warns_on_deformed_height():
    bp = _mobile_bp()
    tree = {"children": [{"name": "Status Bar",
                          "absoluteBoundingBox": {"width": 393, "height": 63.5}}]}
    viols = list(r24._verify(tree, {"blueprint": bp}))
    assert any("63.5" in v.message for v in viols)


def test_r24_verify_passes_on_62():
    bp = _mobile_bp()
    tree = {"children": [{"name": "Status Bar",
                          "absoluteBoundingBox": {"width": 393, "height": 62}}]}
    assert list(r24._verify(tree, {"blueprint": bp})) == []


# ── post-fix 백스톱 판정 ──────────────────────────────────────────

def test_fix_needed_on_hug():
    assert fc._status_bar_fix_needed(
        {"name": "Status Bar", "layoutSizingVertical": "HUG",
         "absoluteBoundingBox": {"width": 393, "height": 62}})


def test_fix_needed_on_height_63_5():
    assert fc._status_bar_fix_needed(
        {"name": "Status Bar", "layoutSizingVertical": "FIXED",
         "absoluteBoundingBox": {"width": 393, "height": 63.5}})


def test_no_fix_on_master_62_fixed():
    assert not fc._status_bar_fix_needed(
        {"name": "Status Bar", "layoutSizingVertical": "FIXED",
         "absoluteBoundingBox": {"width": 393, "height": 62}})


def test_no_fix_within_1px_tolerance():
    assert not fc._status_bar_fix_needed(
        {"name": "Status Bar", "absoluteBoundingBox": {"width": 393, "height": 62.5}})


def test_non_status_bar_ignored():
    assert not fc._status_bar_fix_needed(
        {"name": "NavBar", "layoutSizingVertical": "HUG",
         "absoluteBoundingBox": {"width": 393, "height": 63.5}})


def test_top_level_height_fallback():
    # _collect_tree 류는 width/height 를 top-level 에 둔다 — bbox 없어도 판정
    assert fc._status_bar_fix_needed({"name": "Status Bar", "width": 393, "height": 63.5})


def test_missing_height_no_false_positive():
    assert not fc._status_bar_fix_needed({"name": "Status Bar"})
