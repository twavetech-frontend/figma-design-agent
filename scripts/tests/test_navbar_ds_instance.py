"""R64 — 상단 NavBar = DS 'Tool Bar' 인스턴스 강제 (절대 규칙 0-W, 2026-06-12).

Run:
    cd scripts && python3 -m pytest tests/test_navbar_ds_instance.py -v
"""
from __future__ import annotations

import os
import sys

# Make scripts/ importable regardless of pytest invocation dir
_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from design_rules.R64_navbar_ds_instance import (  # noqa: E402
    _TOOLBAR_DETAIL_KEY,
    _TOOLBAR_HOME_KEY,
    _check_blueprint,
    _classify,
    _extract_right_icons,
    _inject,
)
from design_rules.ds_catalog import NAV_ICON_KEYS, resolve_nav_icon_key  # noqa: E402


def _home_navbar() -> dict:
    return {
        "name": "NavBar", "type": "frame",
        "autoLayout": {"layoutMode": "HORIZONTAL"},
        "children": [
            {"name": "Logo Placeholder", "type": "frame", "width": 80, "height": 32},
            {"name": "Nav Right", "type": "frame", "children": [
                {"name": "icon-bell", "type": "icon", "iconName": "bell-01"},
            ]},
        ],
    }


def _detail_navbar(title="내 스케줄") -> dict:
    return {
        "name": "NavBar", "type": "frame",
        "autoLayout": {"layoutMode": "HORIZONTAL"},
        "children": [
            {"name": "Nav Back", "type": "frame", "children": [
                {"name": "ic-back", "type": "icon", "iconName": "chevron-left"},
            ]},
            {"name": "Nav Title", "type": "text", "text": title},
        ],
    }


def _bp(navbar, **root_overrides) -> dict:
    root = {"name": "Test Screen", "type": "frame", "width": 393,
            "children": [navbar]}
    root.update(root_overrides)
    return root


# ── classify ──────────────────────────────────────────────────────

def test_classify_home():
    kind, title = _classify(_home_navbar())
    assert kind == "home" and title is None


def test_classify_detail_with_title():
    kind, title = _classify(_detail_navbar("거래 스케줄"))
    assert kind == "detail" and title == "거래 스케줄"


def test_classify_xclose_modal_header_skipped():
    nav = {
        "name": "NavBar", "type": "frame",
        "children": [{"name": "ic-close", "type": "icon", "iconName": "x-close"}],
    }
    assert _classify(nav) == (None, None)


def test_classify_no_hint_skipped():
    nav = {"name": "NavBar", "type": "frame",
           "children": [{"name": "Search Field", "type": "frame"}]}
    assert _classify(nav) == (None, None)


# ── inject ────────────────────────────────────────────────────────

def test_inject_home_navbar_swapped_to_instance():
    bp = _bp(_home_navbar())
    _inject(bp)
    nav = bp["children"][0]
    assert nav["type"] == "instance"
    assert nav["componentKey"] == _TOOLBAR_HOME_KEY
    assert nav["componentKey"].startswith("SET:")
    assert "children" not in nav
    assert nav["layoutSizingHorizontal"] == "FILL"
    assert "_navTitle" not in nav


def test_inject_detail_navbar_swapped_with_title_marker():
    bp = _bp(_detail_navbar("내 스케줄"))
    _inject(bp)
    nav = bp["children"][0]
    assert nav["type"] == "instance"
    assert nav["componentKey"] == _TOOLBAR_DETAIL_KEY
    assert nav["_navTitle"] == "내 스케줄"
    assert nav["_originalChildren"]  # raw children 보존


def test_inject_custom_navbar_opt_out():
    nav = _home_navbar()
    nav["_customNavBar"] = True
    bp = _bp(nav)
    _inject(bp)
    assert bp["children"][0]["type"] == "frame"  # 보존


def test_inject_modal_screen_skipped():
    bp = _bp(_detail_navbar(), _screenType="modal")
    _inject(bp)
    assert bp["children"][0]["type"] == "frame"


def test_inject_bottom_sheet_skipped():
    bp = _bp(_detail_navbar(), _screenType="bottom-sheet")
    _inject(bp)
    assert bp["children"][0]["type"] == "frame"


def test_inject_strips_frame_props():
    nav = _home_navbar()
    nav["fill"] = "$token(bg-primary)"
    nav["height"] = 56
    nav["autoLayout"] = {"layoutMode": "HORIZONTAL", "paddingLeft": 20}
    bp = _bp(nav)
    _inject(bp)
    out = bp["children"][0]
    for k in ("fill", "height", "autoLayout", "paddingLeft"):
        assert k not in out


# ── lint ──────────────────────────────────────────────────────────

def test_lint_warns_on_raw_navbar():
    bp = _bp(_home_navbar())
    vios = list(_check_blueprint(bp, {}))
    assert any("Tool Bar" in v.message for v in vios)


def test_lint_silent_on_instance_navbar():
    bp = _bp({"name": "NavBar", "type": "instance",
              "componentKey": _TOOLBAR_HOME_KEY})
    assert list(_check_blueprint(bp, {})) == []


# ── _collect_tool_bar_configs (figma_mcp_client) ──────────────────

def test_collect_tool_bar_configs():
    import figma_mcp_client as fmc
    bp = _bp(_detail_navbar())
    fmc_bp = _inject(bp)
    cfgs = fmc._collect_tool_bar_configs(fmc_bp)
    assert cfgs == [{"name": "NavBar", "title": "내 스케줄", "icons": []}]


def test_collect_tool_bar_configs_home_no_title():
    import figma_mcp_client as fmc
    bp = _bp(_home_navbar())
    _inject(bp)
    cfgs = fmc._collect_tool_bar_configs(bp)
    assert len(cfgs) == 1 and cfgs[0]["title"] is None


# ── 우측 아이콘 swap (_navIcons) ──────────────────────────────────

def test_extract_right_icons_excludes_back_and_xclose():
    nav = _detail_navbar()
    nav["children"].append({"name": "Nav Right", "type": "frame", "children": [
        {"name": "ic-bell", "type": "icon", "iconName": "bell-01"},
        {"name": "ic-share", "type": "icon", "iconName": "share-07"},
        {"name": "ic-close", "type": "icon", "iconName": "x-close"},
    ]})
    icons = _extract_right_icons(nav)
    assert icons == ["bell-01", "share-07"]  # back(chevron-left)·x-close 제외


def test_extract_right_icons_max_3():
    nav = _home_navbar()
    nav["children"][1]["children"] = [
        {"name": f"ic-{i}", "type": "icon", "iconName": n}
        for i, n in enumerate(["bell-01", "search-lg", "share-07", "settings-01"])
    ]
    assert len(_extract_right_icons(nav)) == 3


def test_inject_captures_nav_icons():
    nav = _detail_navbar("내 스케줄")
    nav["children"].append({"name": "Nav Right", "type": "frame", "children": [
        {"name": "ic-bell", "type": "icon", "iconName": "bell-01"},
    ]})
    bp = _bp(nav)
    _inject(bp)
    out = bp["children"][0]
    assert out["type"] == "instance"
    assert out["_navIcons"] == ["bell-01"]


def test_inject_home_no_icons_no_marker():
    nav = _home_navbar()
    nav["children"][1]["children"] = []  # 우측 아이콘 없음
    bp = _bp(nav)
    _inject(bp)
    assert "_navIcons" not in bp["children"][0]


def test_resolve_nav_icon_key_exact_and_prefix():
    assert resolve_nav_icon_key("bell-01") == NAV_ICON_KEYS["bell-01"]
    assert resolve_nav_icon_key("BELL-01") == NAV_ICON_KEYS["bell-01"]
    assert resolve_nav_icon_key("bell-02") == NAV_ICON_KEYS["bell"]  # prefix 폴백
    assert resolve_nav_icon_key("nonexistent-icon") is None
    assert resolve_nav_icon_key("") is None


def test_collect_tool_bar_configs_includes_icons():
    import figma_mcp_client as fmc
    nav = _home_navbar()  # bell-01 아이콘 1개 포함
    bp = _bp(nav)
    _inject(bp)
    cfgs = fmc._collect_tool_bar_configs(bp)
    assert cfgs[0]["icons"] == ["bell-01"]
