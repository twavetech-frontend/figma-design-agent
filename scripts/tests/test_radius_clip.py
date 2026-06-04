# -*- coding: utf-8 -*-
"""절대규칙 0-Q 회귀 테스트 (2026-06-04): radius 있는 frame 은 꼭 clipsContent=true.

회귀: bottom sheet Modal Sheet(개별 코너 topLeftRadius=16)의 Clip content 가 체크 안 됨.
원인 — R45 가 clip 을 false 로 끄는데 get_nodes_info 가 개별 코너를 None 으로 직렬화해
라이브 rounded 예외가 시트를 놓침. → blueprint 단계 강제 + Step E.7.7 blueprint name-path
재단언으로 해결. 여기서는 blueprint 단계 enforcer + path 수집을 검증.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import figma_mcp_client as fc  # noqa: E402


def _bp():
    return {"name": "root", "type": "frame", "children": [
        {"name": "Sheet", "type": "frame", "topLeftRadius": 16, "topRightRadius": 16,
         "children": [{"name": "t", "type": "text"}]},
        {"name": "Card", "type": "frame", "cornerRadius": 12,
         "children": [{"name": "u", "type": "text"}]},
        {"name": "Pill", "type": "frame", "cornerRadius": 999,
         "children": [{"name": "v", "type": "text"}]},
        {"name": "Flat", "type": "frame", "cornerRadius": 0,
         "children": [{"name": "w", "type": "text"}]},
        {"name": "NoKids", "type": "frame", "cornerRadius": 12},  # 자식 없음 → clip 불필요
    ]}


# ── blueprint 단계 강제 ────────────────────────────────────────
def test_individual_corner_radius_gets_clip():
    bp = _bp()
    fc._enforce_radius_clip_blueprint(bp)
    assert bp["children"][0]["clipsContent"] is True  # Sheet (개별 코너)


def test_uniform_radius_gets_clip():
    bp = _bp()
    fc._enforce_radius_clip_blueprint(bp)
    assert bp["children"][1]["clipsContent"] is True  # Card
    assert bp["children"][2]["clipsContent"] is True  # Pill (999)


def test_zero_radius_no_clip():
    bp = _bp()
    fc._enforce_radius_clip_blueprint(bp)
    assert bp["children"][3].get("clipsContent") is None  # Flat


def test_explicit_clip_false_preserved():
    bp = {"name": "root", "type": "frame", "children": [
        {"name": "Special", "type": "frame", "cornerRadius": 12,
         "clipsContent": False, "children": [{"name": "t", "type": "text"}]}]}
    fc._enforce_radius_clip_blueprint(bp)
    assert bp["children"][0]["clipsContent"] is False  # 명시 false 존중


# ── name-path 수집 (Step E.7.7 재단언의 전제) ──────────────────
def test_collect_paths_includes_radius_frames():
    paths = fc._collect_radius_clip_paths(_bp())
    keys = {"/".join(p) for p in paths}
    assert "root/Sheet" in keys
    assert "root/Card" in keys
    assert "root/Pill" in keys
    assert "root/Flat" not in keys
    assert "root/NoKids" not in keys  # 자식 없으면 제외
