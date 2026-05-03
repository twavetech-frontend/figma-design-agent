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
        "S00-schema", "R10-layout", "R11-typography", "R12-image-gen",
        "R20-semantic-only", "R21-bg-hierarchy", "R22-brand-text-color",
        "R23-ds-first", "R24-status-bar", "R25-tab-bar-stroke",
        "R30-fill-sizing", "R31-tab-bar-items", "R32-zero-width-text",
        "R33-stroke-alignment", "R34-status-bar-bg", "R40-token-binding",
    }
    missing = expected - ids
    assert not missing, f"missing rules: {missing}"
