# -*- coding: utf-8 -*-
"""규칙 13 회귀 테스트 (2026-06-08): 중요 섹션 = 풀폭 bg-secondary 밴드.

사용자 룰: 메인·모든 탭바 홈 화면에서 목돈 만들기/스테이지 현황/추천 스테이지 같은 중요
섹션은 content 에서 분리해 풀폭 bg-secondary 밴드로 강조한다. 검증:
  1. `_band:true` 노드 → bg-secondary fill·FILL·상하24/좌우20·보더 제거 표준화
  2. 밴드 내부 sub-card(bg-secondary)는 bg-primary + border-secondary 로 자동 흰색화
  3. brand tint·aqua 등 다른 fill 의 내부 요소는 흰색화 안 함(존중)
  4. 홈 화면에서 중요 이름 섹션이 _band 가 아니면 lint WARN, ribbon/summary 는 제외
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import figma_mcp_client as fc  # noqa: E402


def _home_bp():
    return {"rootName": "imin_active_home_v9", "name": "imin_active_home_v9", "type": "frame",
            "children": [
        {"name": "NavBar", "type": "frame", "children": []},
        {"name": "Stage Status Section", "type": "frame", "_band": True, "children": [
            {"name": "Stat Tiles", "type": "frame", "children": [
                {"name": "Stat Tile", "type": "frame", "fill": "$token(bg-secondary)",
                 "children": [{"name": "t", "type": "text", "text": "42개"}]},
            ]},
            {"name": "Amount Card", "type": "frame", "fill": "$token(bg-secondary)",
             "children": [{"name": "a", "type": "text", "text": "1원"}]},
        ]},
        {"name": "Recommend Section", "type": "frame", "_band": True, "children": [
            {"name": "Choice Tile", "type": "frame", "fill": "$token(bg-brand-primary)",
             "children": [{"name": "c", "type": "text", "text": "차근차근"}]},
            {"name": "Stepper", "type": "frame", "fill": "$token(bg-secondary)",
             "children": [{"name": "s", "type": "text", "text": "5개월"}]},
        ]},
    ]}


# ── 1. 밴드 표준화 ──────────────────────────────────────────────
def test_band_standardized():
    bp = _home_bp()
    fc._enforce_section_band(bp)
    ss = bp["children"][1]
    assert ss["fill"] == "$token(bg-secondary)"
    assert ss["layoutSizingHorizontal"] == "FILL"
    assert ss["autoLayout"]["paddingTop"] == 24
    assert ss["autoLayout"]["paddingBottom"] == 24
    assert ss["autoLayout"]["paddingLeft"] == 20
    assert ss["autoLayout"]["paddingRight"] == 20
    # 보더 제거
    for k in fc._STROKE_KEYS:
        assert k not in ss


# ── 2. 내부 sub-card 흰색화 ────────────────────────────────────
def test_inner_subcard_whitened():
    bp = _home_bp()
    fc._enforce_section_band(bp)
    amount = bp["children"][1]["children"][1]  # Amount Card
    assert amount["fill"] == "$token(bg-primary)"
    assert amount["strokeColor"] == "$token(border-secondary)"
    assert amount["strokeWeight"] == 1
    tile = bp["children"][1]["children"][0]["children"][0]  # Stat Tile (중첩)
    assert tile["fill"] == "$token(bg-primary)"  # 깊은 내부도 흰색화


# ── 3. brand tint·aqua 내부는 흰색화 안 함 ────────────────────
def test_inner_tint_preserved():
    bp = _home_bp()
    fc._enforce_section_band(bp)
    choice = bp["children"][2]["children"][0]  # Choice Tile (brand tint)
    assert choice["fill"] == "$token(bg-brand-primary)"  # 존중
    stepper = bp["children"][2]["children"][1]  # Stepper (bg-secondary → 흰색)
    assert stepper["fill"] == "$token(bg-primary)"


# ── 4. lint: 중요 섹션이 _band 아니면 WARN, ribbon 제외 ───────
def test_lint_warns_non_band_important(capsys):
    bp = {"rootName": "imin_done_home", "name": "imin_done_home", "type": "frame", "children": [
        {"name": "Content", "type": "frame", "children": [
            {"name": "Stage Status Section", "type": "frame", "fill": "$token(bg-primary)",
             "children": [{"name": "x", "type": "text", "text": "현황"}]},
            {"name": "Total Summary Ribbon", "type": "frame", "children": []},
        ]},
    ]}
    fc._enforce_section_band(bp)
    out = capsys.readouterr().out
    assert "규칙13-WARN" in out
    assert "Stage Status Section" in out
    assert "Total Summary Ribbon" not in out  # ribbon/summary 제외


def test_lint_silent_when_banded(capsys):
    bp = _home_bp()
    fc._enforce_section_band(bp)
    out = capsys.readouterr().out
    assert "규칙13-WARN" not in out  # 전부 _band 라 경고 없음


def test_non_home_no_lint(capsys):
    bp = {"rootName": "imin_payment_detail", "name": "imin_payment_detail", "type": "frame",
          "children": [{"name": "Recommend Section", "type": "frame",
                        "children": [{"name": "x", "type": "text"}]}]}
    fc._enforce_section_band(bp)
    out = capsys.readouterr().out
    assert "규칙13-WARN" not in out  # 홈 화면 아님 → lint 비대상


# ── 규칙 13-B: 홈 Content 섹션 gap = spacing-2xl(20) ────────────
def _home_content_bp(gap):
    return {"rootName": "imin_active_home_v9", "name": "imin_active_home_v9", "type": "frame",
            "children": [
                {"name": "Content", "type": "frame",
                 "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": gap, "paddingTop": 16},
                 "children": [{"name": "A", "type": "frame", "children": []}]}]}


def test_home_content_gap_corrected_to_20():
    bp = _home_content_bp(32)  # spacing-4xl → spacing-2xl
    fc._enforce_home_content_gap(bp)
    assert bp["children"][0]["autoLayout"]["itemSpacing"] == 20


def test_home_content_gap_already_20_unchanged():
    bp = _home_content_bp(20)
    fc._enforce_home_content_gap(bp)
    assert bp["children"][0]["autoLayout"]["itemSpacing"] == 20


def test_home_content_gap_optout_marker():
    bp = _home_content_bp(32)
    bp["children"][0]["_keepContentGap"] = True
    fc._enforce_home_content_gap(bp)
    assert bp["children"][0]["autoLayout"]["itemSpacing"] == 32  # opt-out 존중


def test_home_content_gap_non_home_skipped():
    bp = _home_content_bp(32)
    bp["rootName"] = bp["name"] = "imin_payment_detail"
    fc._enforce_home_content_gap(bp)
    assert bp["children"][0]["autoLayout"]["itemSpacing"] == 32  # 홈 아님 → 미적용


def test_home_content_gap_only_content_named():
    # 'Content' 이름이 아닌 일반 섹션 프레임은 건드리지 않음
    bp = {"rootName": "imin_home", "name": "imin_home", "type": "frame", "children": [
        {"name": "Stage Status Section", "type": "frame",
         "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 32}, "children": []}]}
    fc._enforce_home_content_gap(bp)
    assert bp["children"][0]["autoLayout"]["itemSpacing"] == 32  # Content 아님 → 유지
