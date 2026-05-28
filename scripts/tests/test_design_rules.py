"""Tests for the design_rules registry.

These tests are independent of any live Figma session — they exercise
pure-Python rule logic against in-memory blueprint dicts.

Run:
    cd scripts && python3 -m pytest tests/test_design_rules.py -v
"""
from __future__ import annotations

import os
import sys
import pytest

# Make scripts/ importable regardless of pytest invocation dir
_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from design_rules import REGISTRY, Severity  # noqa: E402


# ── Test fixtures ────────────────────────────────────────────────

def make_root(**overrides) -> dict:
    """Minimal mobile-sized root that passes most rules."""
    bp = {
        "name": "Test Root",
        "type": "frame",
        "width": 393,
        "fill": "$token(Colors/Background/bg-primary)",
        "statusBar": True,
        "_referencesSkipped": "test fixture",
        "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 0},
        "children": [
            {"name": "Status Bar", "type": "frame", "height": 50,
             "layoutSizingHorizontal": "FILL"},
            {"name": "Content", "type": "frame",
             "layoutSizingHorizontal": "FILL", "width": 393,
             "fill": "$token(Colors/Background/bg-secondary)",
             "autoLayout": {"layoutMode": "VERTICAL"},
             "children": []},
        ],
    }
    bp.update(overrides)
    return bp


def lint_ids(bp):
    """Return set of rule_ids from lint violations."""
    return [v.rule_id for v in REGISTRY.run_lint(bp)]


# ── Schema (S00) ─────────────────────────────────────────────────

def test_schema_rejects_raw_hex():
    bp = make_root()
    bp["children"][1]["fill"] = "#ff0000"
    ids = lint_ids(bp)
    assert any("S10" in i or "S00" in i for i in ids), \
        f"raw hex should be flagged, got {ids}"


def test_schema_rejects_primitive_token():
    bp = make_root()
    bp["children"][1]["fill"] = "$token(Colors/Brand/600)"
    ids = lint_ids(bp)
    assert any("S11" in i or "S00" in i for i in ids), \
        f"primitive token should be flagged, got {ids}"


def test_schema_rejects_state_token():
    bp = make_root()
    bp["children"][1]["fill"] = "$token(Colors/Background/bg-disabled)"
    ids = lint_ids(bp)
    assert any("S11" in i or "S00" in i for i in ids), \
        f"state token should be flagged, got {ids}"


def test_schema_accepts_semantic_token():
    bp = make_root()
    bp["children"][1]["fill"] = "$token(Colors/Background/bg-secondary)"
    errs = [v for v in REGISTRY.run_lint(bp) if v.severity == Severity.ERROR]
    assert not errs, f"clean blueprint shouldn't error: {[e.format() for e in errs]}"


# ── R21 bg hierarchy ─────────────────────────────────────────────

def test_bg_hierarchy_blocks_skip():
    """bg-primary -> bg-tertiary directly is forbidden."""
    bp = make_root()
    bp["children"][1]["fill"] = "$token(Colors/Background/bg-tertiary)"
    ids = lint_ids(bp)
    assert any("R21.1-bg-skip" in i for i in ids), f"got {ids}"


def test_bg_hierarchy_allows_step():
    """primary -> secondary -> tertiary is fine."""
    bp = make_root()
    bp["children"][1]["children"] = [
        {"name": "Inset", "type": "frame", "layoutSizingHorizontal": "FILL",
         "fill": "$token(Colors/Background/bg-tertiary)"}
    ]
    errs = [v for v in REGISTRY.run_lint(bp)
            if v.severity == Severity.ERROR and v.rule_id.startswith("R21")]
    assert not errs, f"unexpected R21 errors: {[e.format() for e in errs]}"


# ── R22 brand text color ─────────────────────────────────────────

def test_brand_text_no_color_fails():
    """TEXT under bg-brand-solid with no fontColor → black on dark = ERROR."""
    bp = make_root()
    bp["children"][1]["fill"] = "$token(Colors/Background/bg-brand-solid)"
    bp["children"][1]["children"] = [
        {"name": "Label", "type": "text", "characters": "Hello"}
    ]
    ids = lint_ids(bp)
    assert any("R22" in i for i in ids), f"got {ids}"


def test_brand_text_white_passes():
    bp = make_root()
    bp["children"][1]["fill"] = "$token(Colors/Background/bg-brand-solid)"
    bp["children"][1]["children"] = [
        {"name": "Label", "type": "text", "characters": "Hello",
         "fontColor": {"r": 1, "g": 1, "b": 1, "a": 1}}
    ]
    errs = [v for v in REGISTRY.run_lint(bp)
            if v.severity == Severity.ERROR and v.rule_id.startswith("R22")]
    assert not errs


# ── R24 status bar ───────────────────────────────────────────────

def test_status_bar_inject_when_missing():
    bp = make_root()
    bp["children"] = bp["children"][1:]  # remove status bar
    REGISTRY.run_inject(bp)
    assert bp["children"][0]["name"] == "Status Bar"


def test_status_bar_inject_idempotent():
    bp = make_root()
    n = len(bp["children"])
    REGISTRY.run_inject(bp)
    assert len(bp["children"]) == n, "should not duplicate Status Bar"


# ── R25 tab bar stroke ───────────────────────────────────────────

def test_tab_bar_4_sided_stroke_fails():
    bp = make_root()
    bp["children"].append({
        "name": "Tab Bar", "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "stroke": "$token(Colors/Border/border-secondary)",
        "strokeWeight": 1,
    })
    ids = lint_ids(bp)
    assert any("R25" in i for i in ids), f"got {ids}"


def test_tab_bar_per_side_stroke_passes():
    bp = make_root()
    bp["children"].append({
        "name": "Tab Bar", "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "stroke": "$token(Colors/Border/border-secondary)",
        "strokeWeight": 0,
        "strokeTopWeight": 1,
    })
    errs = [v for v in REGISTRY.run_lint(bp)
            if v.severity == Severity.ERROR and v.rule_id.startswith("R25")]
    assert not errs


# ── Registry meta ────────────────────────────────────────────────

# ── R23 ds-first inject + lint ───────────────────────────────────

def test_r23_inject_swaps_bell_to_instance():
    bp = make_root()
    bp["children"].append({"name": "Bell Btn", "type": "frame", "width": 24, "height": 24})
    REGISTRY.run_inject(bp)
    bell = next(c for c in bp["children"] if c["name"] == "Bell Btn")
    assert bell["type"] == "instance", "Bell Btn should be auto-swapped to instance"
    assert bell.get("componentKey"), "componentKey should be auto-injected"


def test_r23_inject_swaps_pill_to_instance():
    bp = make_root()
    bp["children"].append({"name": "Active Pill", "type": "frame"})
    REGISTRY.run_inject(bp)
    pill = next(c for c in bp["children"] if c["name"] == "Active Pill")
    assert pill["type"] == "instance"
    assert pill.get("componentKey"), "Pill should resolve to a brand pill key"


def test_r23_lint_blocks_unresolvable_ds_pattern():
    """A name matching a DS pattern with no catalog match must ERROR."""
    bp = make_root()
    bp["children"].append({"name": "ZZZ Avatar custom unknown", "type": "frame"})
    # First inject (no resolver match) → still raw frame
    REGISTRY.run_inject(bp)
    avatar = next(c for c in bp["children"] if "Avatar" in c["name"])
    assert avatar["type"] == "frame", "no resolver → no swap"
    # Then lint → expect ERROR
    violations = REGISTRY.run_lint(bp)
    errs = [v for v in violations if v.severity == Severity.ERROR
            and v.rule_id == "R23-ds-unresolvable"]
    assert errs, "unresolvable DS pattern should hard-block build"


def test_r23_container_left_as_frame():
    """NavBar / Tab Bar are containers; they must NOT be swapped."""
    bp = make_root()
    bp["children"].append({"name": "NavBar", "type": "frame", "children": [
        {"name": "Bell Btn", "type": "frame"}
    ]})
    REGISTRY.run_inject(bp)
    nav = next(c for c in bp["children"] if c["name"] == "NavBar")
    assert nav["type"] == "frame", "NavBar is a container, not an instance"
    # but its child should be swapped
    bell = nav.get("_originalChildren", nav.get("children", []))
    # When NavBar is a container, its bell child is processed normally
    # (NavBar itself doesn't lose children)
    assert nav.get("children") is not None, "NavBar should still have children"
    bell_node = nav["children"][0]
    assert bell_node["type"] == "instance", "Bell Btn inside container should still swap"


def test_r23_does_not_swap_wrappers():
    """Wrapper names like 'Home Tabs', 'Stage Progress Wrap', 'Recommend Stage Card'
    must NOT be auto-swapped to icons. Container guard prevents this."""
    bp = make_root()
    bp["children"].extend([
        {"name": "Home Tabs", "type": "frame"},
        {"name": "Stage Progress Wrap", "type": "frame"},
        {"name": "Recommend Stage Card", "type": "frame"},
        {"name": "Lounge Section", "type": "frame"},
        {"name": "Stage Tabs Section", "type": "frame"},
        {"name": "Day Cells Row", "type": "frame"},
    ])
    REGISTRY.run_inject(bp)
    for c in bp["children"]:
        if c["name"] in {"Home Tabs", "Stage Progress Wrap", "Recommend Stage Card",
                         "Lounge Section", "Stage Tabs Section", "Day Cells Row"}:
            assert c["type"] == "frame", \
                f"{c['name']} should remain frame, got {c['type']}"


def test_r23_strict_icon_suffix():
    """'Home Icon' swaps; bare 'Home' does not."""
    bp = make_root()
    bp["children"].extend([
        {"name": "Home Icon", "type": "frame"},
        {"name": "Home", "type": "frame"},  # ambiguous, no suffix → no swap
    ])
    REGISTRY.run_inject(bp)
    home_icon = next(c for c in bp["children"] if c["name"] == "Home Icon")
    home_bare = next(c for c in bp["children"] if c["name"] == "Home")
    assert home_icon["type"] == "instance"
    assert home_bare["type"] == "frame"


def test_r23_idempotent():
    bp = make_root()
    bp["children"].append({"name": "Bell Btn", "type": "frame"})
    REGISTRY.run_inject(bp)
    REGISTRY.run_inject(bp)  # second run should be no-op
    bell = next(c for c in bp["children"] if c["name"] == "Bell Btn")
    assert bell["type"] == "instance"


def test_registry_loads_all_rules():
    rules = REGISTRY.all()
    ids = {r.rule_id for r in rules}
    expected = {
        "S00-schema", "S20-references-required",
        "R05-archetype-inject",
        "R10-layout", "R11-typography", "R13-auto-layout",
        "R20-semantic-only", "R21-bg-hierarchy", "R22-brand-text-color",
        "R23-ds-first", "R24-status-bar", "R25-tab-bar-stroke",
        "R30-fill-sizing", "R31-tab-bar-items", "R32-zero-width-text",
        "R33-stroke-alignment", "R34-status-bar-bg",
        "R35-underline-tab-active", "R36-carousel-peek",
        "S21-reference-search-log", "R40-token-binding",
    }
    missing = expected - ids
    assert not missing, f"missing rules: {missing}"


# ── R35 (Underline Tab Active) ───────────────────────────────────

def _tab_nav_bp(active_has_stroke: bool):
    active = {
        "name": "Tab 내 스테이지 (Active)", "type": "frame",
        "autoLayout": {"layoutMode": "HORIZONTAL"},
        "children": [{"name": "label", "type": "text",
                      "characters": "내 스테이지"}],
    }
    if active_has_stroke:
        active["strokeBottomWeight"] = 2
        active["stroke"] = "$token(fg-brand-primary)"
    bp = {
        "name": "Test Root", "type": "frame", "width": 393,
        "statusBar": True, "_referencesSkipped": "test",
        "autoLayout": {"layoutMode": "VERTICAL"},
        "children": [
            {"name": "Home Tabs", "type": "frame",
             "layoutMode": "HORIZONTAL",
             "autoLayout": {"layoutMode": "HORIZONTAL"},
             "children": [
                 active,
                 {"name": "Tab 둘러보기", "type": "frame",
                  "autoLayout": {"layoutMode": "HORIZONTAL"},
                  "children": [{"name": "label", "type": "text",
                                "characters": "둘러보기"}]},
             ]},
        ],
    }
    return bp


def test_r35_lint_warns_when_active_missing_underline():
    bp = _tab_nav_bp(active_has_stroke=False)
    vs = REGISTRY.run_lint(bp)
    warns = [v for v in vs if v.rule_id == "R35-underline-tab-active"]
    assert warns, "R35 should warn when active tab has no underline"


def test_r35_inject_adds_brand_underline_to_active_only():
    bp = _tab_nav_bp(active_has_stroke=False)
    bp = REGISTRY.run_inject(bp)
    home = next(c for c in bp["children"] if c.get("name") == "Home Tabs")
    active, inactive = home["children"]
    assert active.get("strokeBottomWeight") == 2
    assert "brand" in (active.get("stroke") or "").lower()
    assert (inactive.get("strokeBottomWeight") or 0) == 0


def test_r35_lint_silent_after_inject():
    bp = _tab_nav_bp(active_has_stroke=False)
    bp = REGISTRY.run_inject(bp)
    vs = REGISTRY.run_lint(bp)
    warns = [v for v in vs if v.rule_id == "R35-underline-tab-active"]
    assert not warns


def test_r35_skips_segmented_control():
    """Segmented control (R29 territory): parent has fill + cornerRadius=999,
    active child has fill + radius. R35 must not fire."""
    bp = {
        "name": "Test Root", "type": "frame", "width": 393,
        "statusBar": True, "_referencesSkipped": "t",
        "autoLayout": {"layoutMode": "VERTICAL"},
        "children": [
            {"name": "Trade Status Tabs", "type": "frame",
             "layoutMode": "HORIZONTAL",
             "autoLayout": {"layoutMode": "HORIZONTAL"},
             "fill": "$token(bg-tertiary)",
             "cornerRadius": 999,
             "children": [
                 {"name": "Tab 거래 (Active)", "type": "frame",
                  "fill": "$token(bg-primary)", "cornerRadius": 999,
                  "autoLayout": {"layoutMode": "HORIZONTAL"},
                  "children": [{"name": "label", "type": "text",
                                "characters": "거래"}]},
                 {"name": "Tab 누적", "type": "frame",
                  "autoLayout": {"layoutMode": "HORIZONTAL"},
                  "children": [{"name": "label", "type": "text",
                                "characters": "누적"}]},
             ]},
        ],
    }
    vs = REGISTRY.run_lint(bp)
    warns = [v for v in vs if v.rule_id == "R35-underline-tab-active"]
    assert not warns, "R35 must not fire on segmented control"
    bp2 = REGISTRY.run_inject(bp)
    seg = next(c for c in bp2["children"] if c.get("name") == "Trade Status Tabs")
    active = seg["children"][0]
    assert (active.get("strokeBottomWeight") or 0) == 0, \
        "R35 must not arm underline on segmented control active item"


def test_r35_skips_bottom_nav_with_icons():
    """Bottom Tab Bar items have icon+label (2+ texts? actually icon node
    is not TEXT but is a frame). Confirm R35 only fires on label-only nav.
    Here we simulate a tab item with icon (frame) + label (text) — so
    _count_text_children == 1 still — but the parent name 'Bottom Nav' is
    not in hints AND no child has (Active). With no Active marker AND no
    name hint, _is_tab_nav returns False."""
    bp = {
        "name": "Test Root", "type": "frame", "width": 393,
        "statusBar": True, "_referencesSkipped": "t",
        "autoLayout": {"layoutMode": "VERTICAL"},
        "children": [
            {"name": "Bottom Nav", "type": "frame",
             "layoutMode": "HORIZONTAL",
             "autoLayout": {"layoutMode": "HORIZONTAL"},
             "children": [
                 {"name": "Tab Home", "type": "frame",
                  "autoLayout": {"layoutMode": "VERTICAL"},
                  "children": [
                      {"name": "icon", "type": "frame", "children": []},
                      {"name": "label", "type": "text",
                       "characters": "홈"},
                  ]},
                 {"name": "Tab Me", "type": "frame",
                  "autoLayout": {"layoutMode": "VERTICAL"},
                  "children": [
                      {"name": "icon", "type": "frame", "children": []},
                      {"name": "label", "type": "text",
                       "characters": "나"},
                  ]},
             ]},
        ],
    }
    vs = REGISTRY.run_lint(bp)
    warns = [v for v in vs if v.rule_id == "R35-underline-tab-active"]
    assert not warns, "R35 must not fire on bottom nav with icons"


def test_s20_references_required():
    """Blueprint without references[] must ERROR."""
    bp = {"name": "X", "type": "frame", "width": 393, "statusBar": True,
          "children": []}
    vs = REGISTRY.run_lint(bp)
    errs = [v for v in vs if v.severity == Severity.ERROR
            and v.rule_id.startswith("S20")]
    assert errs, "missing references should ERROR"


def test_s20_bypass_with_skipped_reason():
    bp = {"name": "X", "type": "frame", "width": 393, "statusBar": True,
          "_referencesSkipped": "trivial modal", "children": []}
    vs = REGISTRY.run_lint(bp)
    errs = [v for v in vs if v.severity == Severity.ERROR
            and v.rule_id.startswith("S20")]
    assert not errs


def test_s20_accepts_proper_references():
    bp = {"name": "X", "type": "frame", "width": 393, "statusBar": True,
          "references": [
              {"section": "Hero", "ref": "uibowl/toss/x.png",
               "extract": "gradient bg + bold headline"}],
          "children": []}
    vs = REGISTRY.run_lint(bp)
    errs = [v for v in vs if v.severity == Severity.ERROR
            and v.rule_id.startswith("S20")]
    assert not errs
