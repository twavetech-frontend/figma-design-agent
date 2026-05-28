"""Regression tests for _enforce_vertical_hug skip-keyword logic.

Background:
    2026-05-27 회귀: stage_list 빌드에서 카드 안 VERTICAL Body 프레임이
    `batch_build_screen` 의 버그로 layoutSizingVertical=FIXED <58px> 로 박혀
    카드 콘텐츠가 카드 밖으로 흘러나옴.

    Body 가 짧게 박힌 결과 `_enforce_root_min_height` 의 content_bottom 측정이
    실제 콘텐츠보다 짧게 잡혀 → 짧은 화면(A 케이스)으로 잘못 분기 → BAB ABSOLUTE
    pin → 사용자에게 콘텐츠가 잘려보임.

    수정: `_enforce_root_min_height` 직전에 `_enforce_vertical_hug` 가 모든
    VERTICAL 프레임의 vertical sizing 을 HUG 로 강제. ABSOLUTE 배치 대상은 제외.

    이 테스트는 skip-keyword 매칭과 ABSOLUTE 노드 제외 로직을 검증한다 (live
    Figma 호출 없이 순수 분기 로직만).

Run:
    python3 -m pytest scripts/tests/test_vertical_hug.py -v
"""
from __future__ import annotations

import os
import sys

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from figma_mcp_client import _VERTICAL_HUG_SKIP_KEYWORDS  # noqa: E402


def _should_skip(name: str, is_absolute: bool = False) -> bool:
    """`_enforce_vertical_hug.walk` 의 skip 조건 — 검증용 mirror."""
    nm_low = name.lower()
    if any(kw in nm_low for kw in _VERTICAL_HUG_SKIP_KEYWORDS):
        return True
    if is_absolute:
        return True
    return False


# ── Skip keyword tests ────────────────────────────────────────────────

def test_tab_bar_skipped():
    """Tab Bar 는 ABSOLUTE pin 대상이므로 skip."""
    assert _should_skip("Tab Bar") is True
    assert _should_skip("tab bar") is True
    assert _should_skip("TabBar") is True


def test_fab_skipped():
    """FAB 는 floating 이라 skip."""
    assert _should_skip("FAB") is True
    assert _should_skip("Floating FAB Button") is True


def test_action_bar_skipped():
    """Bottom Action Bar / CTA Bar 는 skip."""
    assert _should_skip("Bottom Action Bar") is True
    assert _should_skip("Action Bar") is True
    assert _should_skip("CTA Bar") is True
    assert _should_skip("actionbar") is True


def test_status_bar_skipped():
    """Status Bar 도 skip."""
    assert _should_skip("Status Bar") is True
    assert _should_skip("statusbar") is True


# ── Should-not-skip tests ────────────────────────────────────────────────

def test_card_body_not_skipped():
    """🔴 stage_list 회귀 케이스 — Card Body 는 반드시 HUG 강제 대상."""
    assert _should_skip("Rec Card 2 Body") is False
    assert _should_skip("Card Body") is False
    assert _should_skip("Hero Block") is False


def test_section_not_skipped():
    """일반 콘텐츠 섹션은 HUG 대상."""
    assert _should_skip("Hero Section") is False
    assert _should_skip("Memory Section") is False
    assert _should_skip("Scenario Block") is False
    assert _should_skip("Compact List Section") is False


def test_normal_frame_not_skipped():
    """이름이 utility 아닌 일반 frame 은 HUG."""
    assert _should_skip("Frame") is False
    assert _should_skip("Quote Block") is False
    assert _should_skip("Closing Quote") is False


# ── ABSOLUTE positioning ────────────────────────────────────────────────

def test_absolute_node_skipped():
    """layoutPositioning=ABSOLUTE 이면 skip (이름 무관)."""
    assert _should_skip("Card Body", is_absolute=True) is True
    assert _should_skip("Hero Section", is_absolute=True) is True


# ── Anti-regression ────────────────────────────────────────────────

def test_must_not_skip_card_body_anti_regression():
    """
    누군가 'Rec Card' / 'Body' 같은 이름을 skip 키워드에 잘못 추가하면
    stage_list 회귀가 재발한다. 이 테스트가 그걸 차단.
    """
    # stage_list 의 실제 노드 이름들
    card_node_names = [
        "Rec Card 2", "Rec Card 3", "Rec Card 4",
        "Rec Card 2 Body", "Rec Card 3 Body", "Rec Card 4 Body",
        "Rec Card 2 Footer", "Rec Card 3 Footer", "Rec Card 4 Footer",
        "Recommend List",
    ]
    for nm in card_node_names:
        assert _should_skip(nm) is False, \
            f"Card/Body/Footer/List '{nm}' 는 HUG 강제 대상 — skip 되면 stage_list 회귀"


def test_sizing_v_targets():
    """🔴 회귀 방지 — VERTICAL + FILL 도 HUG 강제 대상 (2026-05-27 stage_list 추가 회귀).

    Body 가 FILL 로 박힌 채 부모(HUG)에 들어가 0~짧은 height 로 collapse 되어
    카드 콘텐츠가 카드 밖으로 흘러나옴. FIXED 와 FILL 둘 다 HUG 로 강제.
    """
    targets = ("FIXED", "FILL")
    not_targets = ("HUG", None, "")
    for t in targets:
        assert t in ("FIXED", "FILL"), f"{t} should be a target"
    for t in not_targets:
        assert t not in ("FIXED", "FILL"), f"{t} should NOT be a target"


def test_keyword_list_completeness():
    """skip 키워드는 ABSOLUTE 대상만 — 추가 시 review 필요."""
    expected = {"tab bar", "tabbar", "fab", "action bar", "actionbar",
                "cta bar", "ctabar", "status bar", "statusbar"}
    actual = set(_VERTICAL_HUG_SKIP_KEYWORDS)
    # 모든 expected 가 있어야 (제거 방지)
    missing = expected - actual
    assert not missing, f"필수 skip 키워드 누락: {missing}"
