# -*- coding: utf-8 -*-
"""원형/icon-box 정사각 복원 판별 회귀 테스트 (2026-06-04).

회귀: 바텀시트 드래그 핸들(40×4)·월 셀 dot(FILL 로 75×5 로 늘어남)이 cornerRadius=999
라서 `_enforce_fixed_size_invariants_final` 이 max(w,h) 정사각으로 복원 → 거대 원/막대.
→ min(w,h) >= 12 가드로 얇은 장식 요소 제외(진짜 붕괴 아바타는 min~16 유지).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import figma_mcp_client as fc  # noqa: E402

_f = fc._is_circle_square_target


# ── 회귀: 얇은 pill/핸들/dot 은 정사각 대상 아님 ──────────────
def test_drag_handle_not_squared():
    # 드래그 핸들 40×4 cornerRadius 999 → 정사각화하면 40×40 거대 원 (버그)
    assert _f(40, 4, 999) is False


def test_filled_dot_not_squared():
    # dot 5×5 가 FILL 로 75×5 로 늘어남, cr 999 → 75×75 거대 원 (버그)
    assert _f(75, 5, 999) is False


def test_small_dot_unchanged():
    # 안 늘어난 5×5 dot — max 5 < 20 이라 애초에 대상 아님
    assert _f(5, 5, 999) is False


def test_thin_pill_not_squared():
    # 60×6 pill (cr 999) — min 6 < 12 → 제외
    assert _f(60, 6, 999) is False


# ── 진짜 원형/icon-box 는 여전히 복원 대상 ────────────────────
def test_collapsed_avatar_squared():
    # 원형 아바타가 가로 붕괴: 16×30 cornerRadius 999 → 복원 대상 (min 16 >= 12 통과... 단 16<12? no)
    # 한 축이 콘텐츠로 줄어도 min>=12 유지하는 케이스
    assert _f(16, 36, 999) is True


def test_normal_circle_squared_when_offsquare():
    # 36×30 원형 (살짝 비정사각) → 복원 대상
    assert _f(36, 30, 999) is True


def test_iconbox_single_child():
    # 44×40 cornerRadius 8 + 단일 FRAME 자식 = icon-box → 복원
    assert _f(44, 40, 8, "FRAME") is True


def test_iconbox_no_child_not_target():
    # 44×40 cornerRadius 8, 자식 없음(또는 TEXT) → 원형도 icon-box 도 아님
    assert _f(44, 40, 8, None) is False
    assert _f(44, 40, 8, "TEXT") is False


# ── 범위 밖 ──────────────────────────────────────────────────
def test_too_large_not_target():
    assert _f(120, 110, 999) is False  # max 120 > 80


def test_too_small_not_target():
    assert _f(10, 10, 999) is False  # max 10 < 20
