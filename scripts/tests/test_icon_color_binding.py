# -*- coding: utf-8 -*-
"""SVG 아이콘 색 → fg-* 토큰 nearest 바인딩 회귀 테스트 (2026-06-09 사용자 룰).

code.js colorizeVectors 가 아이콘 VECTOR 의 stroke/fill 을 리터럴 RGB 로 박아 변수에
안 묶이던 회귀를 라이브에서 교정(`_bind_icon_color_tokens_live`). 여기선 순수 함수
(_load_fg_color_palette / _nearest_fg_token / _first_visible_solid_paint /
_paint_already_bound)만 검증한다(라이브 트리 콜 없음).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import figma_mcp_client as fc  # noqa: E402


def _rgb(hexstr):
    h = hexstr.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)


# ── 팔레트 ─────────────────────────────────────────────────────
def test_fg_palette_only_foreground_no_alt_hover():
    pal = fc._load_fg_color_palette()
    assert pal, "fg-* 팔레트가 비어있으면 안 됨"
    for fp, rgb in pal:
        assert fp.startswith("Colors/Foreground/fg-")
        assert not fp.lower().endswith("_alt")      # 규칙 0-B
        assert "_hover" not in fp.lower()           # 정적 아이콘 무관
        assert len(rgb) == 3 and all(0 <= c <= 1 for c in rgb)


# ── nearest 매칭 (사용자 예시 색들) ─────────────────────────────
def test_nearest_maps_canonical_icon_colors():
    pal = fc._load_fg_color_palette()
    cases = {
        "#2c3744": "Colors/Foreground/fg-primary",        # 사용자 스샷의 벨 아이콘 stroke
        "#7700ff": "Colors/Foreground/fg-brand-primary",
        "#ffffff": "Colors/Foreground/fg-light",
        "#b1b6be": "Colors/Foreground/fg-tertiary",
        "#687079": "Colors/Foreground/fg-secondary",
    }
    for hx, want in cases.items():
        fp, d = fc._nearest_fg_token(_rgb(hx), pal)
        assert fp == want, f"{hx} → {fp} (기대 {want})"
        assert d <= fc._ICON_COLOR_SNAP_THRESH, f"{hx} 거리 {d} 가 임계 초과"


def test_near_exact_color_snaps_within_threshold():
    """살짝 어긋난 색(AA/반올림)도 임계 이내면 fg-primary 로 스냅."""
    pal = fc._load_fg_color_palette()
    fp, d = fc._nearest_fg_token(_rgb("#2d3845"), pal)  # #2c3744 근처
    assert fp == "Colors/Foreground/fg-primary"
    assert d <= fc._ICON_COLOR_SNAP_THRESH


def test_aqua_is_far_from_fg_palette_left_literal():
    """aqua #009eaa 는 전경 팔레트와 멀어 임계를 넘어야 한다(리터럴 유지 → 안 바뀜)."""
    pal = fc._load_fg_color_palette()
    fp, d = fc._nearest_fg_token(_rgb("#009eaa"), pal)
    assert d > fc._ICON_COLOR_SNAP_THRESH, f"aqua 거리 {d} — 임계 이내면 잘못 스냅됨"


# ── paint 헬퍼 ─────────────────────────────────────────────────
def test_first_visible_solid_paint():
    assert fc._first_visible_solid_paint(None) is None
    assert fc._first_visible_solid_paint([]) is None
    # invisible 은 skip, 다음 visible SOLID 채택
    paints = [
        {"type": "SOLID", "visible": False, "color": {"r": 0, "g": 0, "b": 0}},
        {"type": "SOLID", "visible": True, "color": {"r": 1, "g": 0, "b": 0}},
    ]
    p = fc._first_visible_solid_paint(paints)
    assert p and p["color"]["r"] == 1
    # GRADIENT 등 비-SOLID 는 무시
    assert fc._first_visible_solid_paint([{"type": "GRADIENT_LINEAR"}]) is None


def test_paint_already_bound_detects_paint_level_alias():
    node = {"boundVariables": {}}
    bound_paint = {"type": "SOLID", "color": {"r": 0, "g": 0, "b": 0},
                   "boundVariables": {"color": {"type": "VARIABLE_ALIAS", "id": "X"}}}
    free_paint = {"type": "SOLID", "color": {"r": 0, "g": 0, "b": 0}}
    assert fc._paint_already_bound(node, bound_paint, "strokes") is True   # 멱등: 재실행 skip
    assert fc._paint_already_bound(node, free_paint, "strokes") is False
    # node 레벨 boundVariables 로도 감지
    node2 = {"boundVariables": {"fills": [{"type": "VARIABLE_ALIAS", "id": "Y"}]}}
    assert fc._paint_already_bound(node2, free_paint, "fills") is True


def test_icon_vector_types_excludes_decorative_shapes():
    """장식 RECTANGLE/ELLIPSE 는 fg 팔레트 매칭 대상이 아니다(bg 토큰일 수 있음)."""
    assert "VECTOR" in fc._ICON_VECTOR_TYPES
    assert "BOOLEAN_OPERATION" in fc._ICON_VECTOR_TYPES
    assert "RECTANGLE" not in fc._ICON_VECTOR_TYPES
    assert "ELLIPSE" not in fc._ICON_VECTOR_TYPES


# ── svg_icon 프레임 감지 (숨은 fill 정리 패스) ─────────────────
def _icon_frame(w=28, h=28, kids=None):
    return {
        "type": "FRAME", "id": "I1", "name": "bell",
        "absoluteBoundingBox": {"width": w, "height": h},
        "_children_full": kids if kids is not None else [{"type": "VECTOR", "id": "V1"}],
    }


def test_is_svg_icon_frame_detects_wrapper():
    assert fc._is_svg_icon_frame(_icon_frame()) is True
    # 여러 vector path 도 허용
    assert fc._is_svg_icon_frame(_icon_frame(kids=[
        {"type": "VECTOR"}, {"type": "VECTOR"}])) is True


def test_is_svg_icon_frame_rejects_non_icon():
    # 자식 없음
    assert fc._is_svg_icon_frame(_icon_frame(kids=[])) is False
    # 너무 큼(카드)
    assert fc._is_svg_icon_frame(_icon_frame(w=320, h=200)) is False
    # VECTOR 없이 장식 도형만
    assert fc._is_svg_icon_frame(_icon_frame(kids=[{"type": "RECTANGLE"}])) is False
    # TEXT 자식 섞임(아이콘 아님)
    assert fc._is_svg_icon_frame(_icon_frame(kids=[
        {"type": "VECTOR"}, {"type": "TEXT"}])) is False
    # FRAME 아님
    assert fc._is_svg_icon_frame({"type": "VECTOR", "absoluteBoundingBox": {"width": 20, "height": 20},
                                  "_children_full": []}) is False
