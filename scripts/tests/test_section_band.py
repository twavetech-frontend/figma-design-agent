# -*- coding: utf-8 -*-
"""규칙 13 회귀 테스트 (🔻 2026-06-18 색 강제 삭제): `_band` = 풀폭 *구조*만, 색은 자율.

사용자 룰(2026-06-18): "중요 섹션 frame fill 을 bg-secondary 로 고정하는 건 삭제, 자율 판단.
섹션 안 블록도 꼭 secondary 로 채울 필요 없어." 검증:
  1. `_band:true` 노드 → FILL + padding fill-in 만. **fill 은 강제하지 않는다(미지정이면 미설정).**
  2. 밴드 내부 sub-card 의 색은 **흰색화하지 않는다**(bg-secondary 면 그대로 유지).
  3. 작성자가 명시한 fill(밴드·내부 모두)은 그대로 존중.
  4. 밴드 nudge lint 폐기 — 어떤 출력도 없어야.
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


# ── 1. _band = 풀폭 구조만 (fill 강제 안 함) ───────────────────
def test_band_structure_only_no_fill_forced():
    bp = _home_bp()
    fc._enforce_section_band(bp)
    ss = bp["children"][1]  # Stage Status Section (_band, fill 미지정)
    assert "fill" not in ss or ss.get("fill") is None, "fill 을 강제하면 안 됨(자율)"
    assert ss["layoutSizingHorizontal"] == "FILL"  # 풀폭 구조는 유지
    assert ss["autoLayout"]["paddingTop"] == 24
    assert ss["autoLayout"]["paddingBottom"] == 24
    assert ss["autoLayout"]["paddingLeft"] == 20
    assert ss["autoLayout"]["paddingRight"] == 20


# ── 2. 내부 sub-card 흰색화 안 함 (색 유지) ────────────────────
def test_inner_subcard_not_whitened():
    bp = _home_bp()
    fc._enforce_section_band(bp)
    amount = bp["children"][1]["children"][1]  # Amount Card (bg-secondary)
    assert amount["fill"] == "$token(bg-secondary)", "내부 블록 색을 흰색화하면 안 됨(자율)"
    assert "strokeColor" not in amount, "보더 자동부착도 안 함"
    tile = bp["children"][1]["children"][0]["children"][0]  # Stat Tile (중첩)
    assert tile["fill"] == "$token(bg-secondary)"  # 깊은 내부도 그대로


# ── 3. 작성자 명시 fill 은 밴드·내부 모두 존중 ────────────────
def test_explicit_fills_respected():
    bp = _home_bp()
    # 밴드에 명시 fill 을 주면 그대로 유지
    bp["children"][2]["fill"] = "$token(bg-brand-primary)"
    fc._enforce_section_band(bp)
    rec = bp["children"][2]
    assert rec["fill"] == "$token(bg-brand-primary)"  # 명시 밴드 fill 존중
    choice = rec["children"][0]
    assert choice["fill"] == "$token(bg-brand-primary)"  # 내부 brand tint 존중
    stepper = rec["children"][1]
    assert stepper["fill"] == "$token(bg-secondary)"  # 내부 bg-secondary 도 그대로(흰색화 X)


# ── 4. 밴드 nudge lint 폐기 — 어떤 안내도 없어야 ──────────────
def test_no_band_lint_output(capsys):
    bp = {"rootName": "imin_done_home", "name": "imin_done_home", "type": "frame", "children": [
        {"name": "Content", "type": "frame", "children": [
            {"name": "Stage Status Section", "type": "frame", "fill": "$token(bg-primary)",
             "children": [{"name": "x", "type": "text", "text": "현황"}]},
        ]},
    ]}
    fc._enforce_section_band(bp)
    out = capsys.readouterr().out
    assert "규칙13-INFO" not in out and "규칙13-WARN" not in out  # lint 폐기


# ── 규칙 13-B: 홈 Content 섹션 gap = spacing-2xl(20) ────────────
def _home_content_bp(gap):
    return {"rootName": "imin_active_home_v9", "name": "imin_active_home_v9", "type": "frame",
            "children": [
                {"name": "Content", "type": "frame",
                 "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": gap, "paddingTop": 16},
                 "children": [{"name": "A", "type": "frame", "children": []}]}]}


def test_home_content_gap_explicit_respected():
    # 🔻 2026-06-12 fill-in-only 강등: author 명시 gap(32)은 존중 — 변경하지 않는다(WARN만)
    bp = _home_content_bp(32)
    fc._enforce_home_content_gap(bp)
    assert bp["children"][0]["autoLayout"]["itemSpacing"] == 32


def test_home_content_gap_filled_when_missing():
    # 미지정(None)일 때만 기본값 20(spacing-2xl)을 채운다
    bp = _home_content_bp(None)
    del bp["children"][0]["autoLayout"]["itemSpacing"]
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
