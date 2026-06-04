# -*- coding: utf-8 -*-
"""radius-* 토큰 바인딩 회귀 테스트 (2026-06-04 사용자 룰).

cornerRadius 절대값을 radius-* DS 변수에 바인딩(spacing 바인딩과 동형). 토큰 value ==
현재 radius 라 시각 변화 0. 개별 코너(시트 top 16/bottom 0)는 blueprint 값으로 매칭.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import figma_mcp_client as fc  # noqa: E402


# ── _load_radius_map / _radius_token_for ───────────────────────
def test_radius_map_has_scale():
    rm = fc._load_radius_map()
    # 시맨틱 radius-* 토큰만 (figmaPath 'radius-' 시작)
    assert rm.get(14.0) == "radius-xl"
    assert rm.get(16.0) == "radius-2xl"
    assert rm.get(12.0) == "radius-lg"
    assert rm.get(8.0) == "radius-sm"
    assert rm.get(0.0) == "radius-none"


def test_radius_token_exact_match():
    rm = fc._load_radius_map()
    assert fc._radius_token_for(14, rm) == "radius-xl"
    assert fc._radius_token_for(16, rm) == "radius-2xl"
    assert fc._radius_token_for(0, rm) == "radius-none"


def test_radius_token_full_convention():
    rm = fc._load_radius_map()
    # 완전 둥근(>=100): 999/9999 모두 radius-full (Figma 가 절반-사이즈로 clamp → 동일)
    assert fc._radius_token_for(999, rm) == "radius-full"
    assert fc._radius_token_for(9999, rm) == "radius-full"


def test_radius_token_off_scale_none():
    rm = fc._load_radius_map()
    assert fc._radius_token_for(13, rm) is None  # 스케일 밖 → 리터럴 유지
    assert fc._radius_token_for(7, rm) is None


# ── _collect_radius_corners_bp (개별 코너) ─────────────────────
def test_collect_individual_corners():
    bp = {"name": "root", "type": "frame", "children": [
        {"name": "Sheet", "type": "frame", "topLeftRadius": 16, "topRightRadius": 16,
         "bottomLeftRadius": 0, "bottomRightRadius": 0},
        {"name": "Uniform", "type": "frame", "cornerRadius": 14},  # 균일 → 라이브로 처리, 여기 제외
        {"name": "Flat", "type": "frame", "cornerRadius": 0},
    ]}
    m = fc._collect_radius_corners_bp(bp)
    sheet = m.get(("root", "Sheet"))
    assert sheet is not None
    assert sheet["topLeftRadius"] == 16 and sheet["topRightRadius"] == 16
    assert sheet["bottomLeftRadius"] == 0 and sheet["bottomRightRadius"] == 0
    # 균일/flat 은 개별 코너 맵에 없음 (균일은 라이브 cornerRadius 로 바인딩)
    assert ("root", "Uniform") not in m
    assert ("root", "Flat") not in m
