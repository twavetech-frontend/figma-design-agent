# -*- coding: utf-8 -*-
"""_keepSizing intent-존중 마커 — _collect_keep_sizing 수집 검증 (2026-06-10)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from figma_mcp_client import _collect_keep_sizing


def _bp(children):
    return {"name": "root", "type": "frame", "children": children}


def test_collects_hug_marker():
    bp = _bp([
        {"name": "Giver Info", "type": "frame", "_keepSizing": True,
         "layoutSizingHorizontal": "HUG"},
        {"name": "Other", "type": "frame", "layoutSizingHorizontal": "FILL"},
    ])
    m = _collect_keep_sizing(bp)
    assert ("root", "Giver Info") in m
    assert m[("root", "Giver Info")]["h"] == "HUG"
    # 마커 없는 노드는 수집 안 됨
    assert ("root", "Other") not in m


def test_collects_fixed_square_with_dims():
    bp = _bp([
        {"name": "One Circle", "type": "frame", "_keepSizing": True,
         "layoutSizingHorizontal": "FIXED", "layoutSizingVertical": "FIXED",
         "width": 220, "height": 220},
    ])
    m = _collect_keep_sizing(bp)
    spec = m[("root", "One Circle")]
    assert spec["h"] == "FIXED" and spec["v"] == "FIXED"
    assert spec["w"] == 220 and spec["ht"] == 220


def test_nested_and_originalchildren():
    bp = _bp([
        {"name": "Wrap", "type": "frame", "children": [
            {"name": "Keep", "type": "frame", "_keepSizing": True, "layoutSizingHorizontal": "HUG"},
        ]},
        {"name": "Swapped", "type": "frame", "_originalChildren": [
            {"name": "DeepKeep", "type": "frame", "_keepSizing": True, "layoutSizingVertical": "FIXED", "height": 56},
        ]},
    ])
    m = _collect_keep_sizing(bp)
    assert ("root", "Wrap", "Keep") in m
    assert ("root", "Swapped", "DeepKeep") in m
    assert m[("root", "Swapped", "DeepKeep")]["ht"] == 56


def test_empty_and_none_safe():
    assert _collect_keep_sizing(None) == {}
    assert _collect_keep_sizing({}) == {}
    assert _collect_keep_sizing(_bp([])) == {}
