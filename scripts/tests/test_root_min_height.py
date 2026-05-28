"""Regression tests for _enforce_root_min_height branching logic.

Background:
    2026-05-24 — `_enforce_root_min_height` 도입. 정책: 콘텐츠 ≤ 852 면 BAB
    ABSOLUTE pin, 콘텐츠 > 852 면 BAB normal flow + root HUG.

    2026-05-26 회귀: v3 s2 (content_bottom=796, BAB height=119) 빌드에서
    BAB 가 위 콘텐츠를 덮어 4번째 list row + closing quote 가 잘려보임.
    원인: 분기 판단이 `content_bottom > 852` 단독 비교라 BAB 높이를 빠뜨림.
    796 < 852 라 ABSOLUTE pin 분기로 갔지만 실제로는 796+119=915 가 852 초과.

    수정: `_should_use_bab_normal_flow(content_bottom, bab_heights)` 헬퍼로
    분리. content + BAB 합산 비교. 이 테스트가 회귀 방지.

Run:
    cd scripts && python3 -m pytest tests/test_root_min_height.py -v
"""
from __future__ import annotations

import os
import sys

# Make scripts/ importable regardless of pytest invocation dir
_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from figma_mcp_client import (  # noqa: E402
    _should_use_bab_normal_flow,
    ROOT_MIN_HEIGHT,
    _is_hug_screen_type,
    _screen_type_from_blueprint,
)


# ── Regression case ────────────────────────────────────────────────

def test_v3_s2_regression_content_under_852_but_total_over():
    """
    🔴 회귀 방지 — v3 s2 (2026-05-26).

    content_bottom 단독으론 852 안에 들어가지만 BAB 합산하면 초과.
    이 케이스는 반드시 B 케이스(BAB normal flow + root HUG) 로 가야 한다.
    True 가 아니면 BAB 가 콘텐츠를 덮는 잘림 회귀가 다시 발생한다.
    """
    assert _should_use_bab_normal_flow(796, [119]) is True


# ── Boundary cases ────────────────────────────────────────────────

def test_short_content_no_bab_under_min_height():
    """짧은 콘텐츠 + BAB 없음 → A 케이스 (root=852, no pinning needed)."""
    assert _should_use_bab_normal_flow(600, []) is False


def test_short_content_with_bab_total_under_min():
    """콘텐츠+BAB 합이 852 안 → A 케이스."""
    assert _should_use_bab_normal_flow(600, [120]) is False


def test_content_alone_exceeds_min_height():
    """BAB 없어도 콘텐츠가 852 초과 → B 케이스."""
    assert _should_use_bab_normal_flow(900, []) is True


def test_content_exactly_min_height_no_bab():
    """콘텐츠 정확히 852, BAB 없음 → 경계 (초과 아니므로 A 케이스)."""
    assert _should_use_bab_normal_flow(852, []) is False


def test_content_exactly_min_height_plus_one_no_bab():
    """콘텐츠 853 → B 케이스 (초과)."""
    assert _should_use_bab_normal_flow(853, []) is True


def test_multiple_bottom_bars_summed():
    """다중 BAB(Tab Bar + CTA Bar) 합산 — 600 + 200 + 80 = 880 > 852."""
    assert _should_use_bab_normal_flow(600, [200, 80]) is True


def test_multiple_bottom_bars_under_min():
    """다중 BAB 라도 합이 안 넘으면 A 케이스 — 400 + 200 + 80 = 680 < 852."""
    assert _should_use_bab_normal_flow(400, [200, 80]) is False


# ── Custom min_height ────────────────────────────────────────────────

def test_custom_min_height():
    """min_height 파라미터 override 동작."""
    assert _should_use_bab_normal_flow(500, [120], min_height=600) is True
    assert _should_use_bab_normal_flow(500, [100], min_height=700) is False


def test_default_min_height_constant():
    """기본값은 ROOT_MIN_HEIGHT (852) 사용."""
    assert ROOT_MIN_HEIGHT == 852
    assert _should_use_bab_normal_flow(853, []) is True
    assert _should_use_bab_normal_flow(852, []) is False


# ── Anti-regression: must not be content_bottom-only ────────────────

def test_must_compare_total_not_content_only():
    """
    이 테스트가 깨지면 누군가가 분기 판단을 content_bottom 단독 비교로
    되돌렸을 가능성이 큼. 그러면 v3 s2 회귀가 재발한다.
    """
    # content 단독으론 852 미만이지만 BAB 합산하면 초과
    assert _should_use_bab_normal_flow(800, [100]) is True
    assert _should_use_bab_normal_flow(700, [200]) is True
    # content 단독으론 852 초과이지만 BAB 빼면 미만 — 어떻든 B 케이스
    assert _should_use_bab_normal_flow(900, [0]) is True


# ── Modal / bottom-sheet → root HUG (2026-05-28) ────────────────────
# 🔴 회귀 방지 — "또 컨텐츠가 다 안보인 상태에서 잘려있다 ... 시스템에 박아".
# 모달 root 가 FIXED 면 후속 height 증가 시 하단 clip. screen_type 이 모달 계열이면
# _enforce_root_min_height 가 A/B 분기 전에 root HUG 로 강제 + return 해야 한다.

def test_modal_screen_types_use_hug():
    """modal / bottom-sheet 계열은 모두 HUG 강제 대상."""
    assert _is_hug_screen_type("modal") is True
    assert _is_hug_screen_type("bottom-sheet") is True
    assert _is_hug_screen_type("bottomsheet") is True
    assert _is_hug_screen_type("bottom_sheet") is True
    # 대소문자/공백 robust
    assert _is_hug_screen_type(" Modal ") is True
    assert _is_hug_screen_type("BOTTOM-SHEET") is True


def test_non_modal_screen_types_not_hug():
    """일반 화면(빈 문자열/None/full screen)은 HUG 대상 아님 — A/B 분기 그대로."""
    assert _is_hug_screen_type("") is False
    assert _is_hug_screen_type(None) is False
    assert _is_hug_screen_type("screen") is False
    assert _is_hug_screen_type("home") is False


def test_screen_type_extracted_from_blueprint():
    """_screenType / screenType 키 모두 인식 (소문자 정규화)."""
    assert _screen_type_from_blueprint({"_screenType": "modal"}) == "modal"
    assert _screen_type_from_blueprint({"screenType": "Bottom-Sheet"}) == "bottom-sheet"
    assert _screen_type_from_blueprint({}) == ""
    assert _screen_type_from_blueprint(None) == ""


def test_modal_blueprint_round_trips_to_hug():
    """blueprint → screen_type → HUG 판정까지 연결 (end-to-end 순수 경로)."""
    bp = {"_screenType": "modal", "rootName": "transaction_schedule_modal"}
    assert _is_hug_screen_type(_screen_type_from_blueprint(bp)) is True
