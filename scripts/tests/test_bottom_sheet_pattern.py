"""Regression tests for _enforce_bottom_sheet_pattern.

Background:
    2026-05-27 — 사용자 명시 지시: "modal 기본형은 화면 세로사이즈의 반 정도로
    보여져야되. 뒤에는 원래 화면이 있고 그 위에 dimmed 처리된 Overlay가 있고
    그 위에 Modal이 bottom에 붙어서 보여져야되. 수정하고 규칙에 추가하고
    코드에도 박아."

    blueprint root 에 `_screenType: "bottom-sheet"` 명시 시 자동으로:
    - Dim Overlay (alpha-black 50%) 가 root 의 첫 자식
    - Modal Sheet (bg-primary, top-rounded 24, HUG) 가 두번째 자식 — 콘텐츠 wrap
    - Root height = 852 FIXED

Run:
    python3 -m pytest scripts/tests/test_bottom_sheet_pattern.py -v
"""
from __future__ import annotations

import os
import sys
import copy

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from figma_mcp_client import _enforce_bottom_sheet_pattern, _BOTTOM_SHEET_DIM_FILL  # noqa: E402


def _make_bp(children, screen_type="bottom-sheet"):
    return {
        "name": "root", "type": "frame",
        "_screenType": screen_type,
        "width": 393, "height": 852,
        "autoLayout": {"layoutMode": "VERTICAL"},
        "children": copy.deepcopy(children),
    }


# ── Basic wrap behavior ────────────────────────────────────────────────

def test_bottom_sheet_wraps_children():
    """bottom-sheet 타입이면 Dim Overlay + Modal Sheet 자동 wrap."""
    bp = _make_bp([
        {"name": "Header", "type": "frame"},
        {"name": "Body", "type": "frame"},
        {"name": "CTA", "type": "frame"},
    ])
    _enforce_bottom_sheet_pattern(bp)
    names = [c["name"] for c in bp["children"]]
    assert names == ["Dim Overlay", "Modal Sheet"]
    # Modal Sheet 안에 원래 자식들
    modal = bp["children"][1]
    inner = [c["name"] for c in modal["children"]]
    assert inner == ["Header", "Body", "CTA"]


def test_dim_overlay_uses_alpha_black_50():
    """Dim Overlay 의 fill 은 alpha-black 50% (반투명 어둠)."""
    bp = _make_bp([{"name": "X", "type": "frame"}])
    _enforce_bottom_sheet_pattern(bp)
    dim = bp["children"][0]
    assert dim["name"] == "Dim Overlay"
    fills = dim.get("fills", [])
    assert len(fills) == 1
    assert fills[0]["type"] == "SOLID"
    assert fills[0]["opacity"] == 0.5
    assert fills[0]["color"] == {"r": 0, "g": 0, "b": 0}


def test_modal_sheet_top_rounded():
    """Modal Sheet 는 top corners 만 24px rounded."""
    bp = _make_bp([{"name": "X", "type": "frame"}])
    _enforce_bottom_sheet_pattern(bp)
    modal = bp["children"][1]
    assert modal["name"] == "Modal Sheet"
    assert modal["topLeftRadius"] == 24
    assert modal["topRightRadius"] == 24
    assert modal["bottomLeftRadius"] == 0
    assert modal["bottomRightRadius"] == 0


def test_modal_sheet_bg_primary():
    """Modal Sheet 표면은 bg-primary (절대 규칙 0 — 흰)."""
    bp = _make_bp([{"name": "X", "type": "frame"}])
    _enforce_bottom_sheet_pattern(bp)
    assert bp["children"][1]["fill"] == "$token(bg-primary)"


def test_root_height_852_fixed():
    """Root height = 852 FIXED — Modal 이 bottom 에 anchor 되어야 dim 이 위로 펼쳐짐."""
    bp = _make_bp([{"name": "X", "type": "frame"}])
    bp["height"] = 600  # 임의 height 박혀있어도
    _enforce_bottom_sheet_pattern(bp)
    assert bp["height"] == 852
    assert bp["layoutSizingVertical"] == "FIXED"


def test_dim_fills_remaining_space():
    """Dim Overlay 는 height FILL — 위쪽 가용 공간 채움."""
    bp = _make_bp([{"name": "X", "type": "frame"}])
    _enforce_bottom_sheet_pattern(bp)
    dim = bp["children"][0]
    assert dim["layoutSizingVertical"] == "FILL"


def test_modal_sheet_hugs_content():
    """Modal Sheet 는 height HUG — 콘텐츠만큼만 차지."""
    bp = _make_bp([{"name": "X", "type": "frame"}])
    _enforce_bottom_sheet_pattern(bp)
    modal = bp["children"][1]
    assert modal["layoutSizingVertical"] == "HUG"


# ── Edge cases ────────────────────────────────────────────────

def test_non_bottom_sheet_type_no_op():
    """screen_type 이 다른 경우 wrap 안 함."""
    bp = _make_bp([{"name": "X", "type": "frame"}], screen_type="modal")
    _enforce_bottom_sheet_pattern(bp)
    # 그대로 유지
    assert [c["name"] for c in bp["children"]] == ["X"]


def test_no_screen_type_no_op():
    """_screenType 없으면 wrap 안 함."""
    bp = {
        "name": "root", "type": "frame",
        "autoLayout": {"layoutMode": "VERTICAL"},
        "children": [{"name": "X", "type": "frame"}],
    }
    _enforce_bottom_sheet_pattern(bp)
    assert [c["name"] for c in bp["children"]] == ["X"]


def test_idempotent_re_run():
    """이미 wrap 적용된 blueprint 재실행 시 추가 wrap 안 함."""
    bp = _make_bp([{"name": "X", "type": "frame"}])
    _enforce_bottom_sheet_pattern(bp)
    after_1 = copy.deepcopy(bp["children"])
    _enforce_bottom_sheet_pattern(bp)
    after_2 = bp["children"]
    assert [c["name"] for c in after_1] == [c["name"] for c in after_2]
    assert len(after_2) == 2  # 여전히 Dim + Modal


def test_status_bar_preserved_outside_modal():
    """Status Bar 가 있으면 modal 밖에 유지 (Dim 위 디바이스 status bar 표시)."""
    bp = _make_bp([
        {"name": "Status Bar", "type": "frame"},
        {"name": "Header", "type": "frame"},
        {"name": "CTA", "type": "frame"},
    ])
    _enforce_bottom_sheet_pattern(bp)
    names = [c["name"] for c in bp["children"]]
    assert names == ["Status Bar", "Dim Overlay", "Modal Sheet"]
    modal = bp["children"][2]
    inner = [c["name"] for c in modal["children"]]
    # Status Bar 는 modal 안에 안 들어감
    assert inner == ["Header", "CTA"]


def test_alias_screen_types():
    """별칭 — 'bottomsheet', 'sheet' 도 동일하게 동작."""
    for st in ("bottomsheet", "sheet", "Bottom-Sheet"):
        bp = _make_bp([{"name": "X", "type": "frame"}], screen_type=st)
        _enforce_bottom_sheet_pattern(bp)
        assert [c["name"] for c in bp["children"]] == ["Dim Overlay", "Modal Sheet"], \
            f"alias {st!r} should trigger wrap"


# ── Anti-regression ────────────────────────────────────────────────

def test_modal_type_does_not_trigger_bottom_sheet():
    """🔴 회귀 방지 — `_screenType: "modal"` (full modal) 은 bottom-sheet wrap 안 함.

    누군가가 두 type 을 합쳐버리면 기존 full modal 화면들이 회귀한다.
    """
    bp = _make_bp([{"name": "Header", "type": "frame"}], screen_type="modal")
    _enforce_bottom_sheet_pattern(bp)
    assert "Dim Overlay" not in [c["name"] for c in bp["children"]]


def test_constant_dim_fill_color():
    """Dim Overlay fill 상수 — 색·opacity 가 변경되면 검출."""
    assert _BOTTOM_SHEET_DIM_FILL["opacity"] == 0.5
    assert _BOTTOM_SHEET_DIM_FILL["color"] == {"r": 0, "g": 0, "b": 0}
    assert _BOTTOM_SHEET_DIM_FILL["type"] == "SOLID"
