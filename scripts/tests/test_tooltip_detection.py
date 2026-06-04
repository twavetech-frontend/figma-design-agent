# -*- coding: utf-8 -*-
"""R23 Tooltip/말풍선 자동 swap 회귀 테스트 (2026-06-04).

사용자 보고: stage_detail 하단 '궁금한 건 물어보세요. ✕' 말풍선이 DS Tooltip
컴포넌트가 아니라 raw frame 으로 생성됨. 원인 — 'Tooltip' 이
_VERIFIED_AUTOSWAP_ROLES 에 등록돼 있었으나 detect_tooltip_shape 디텍터가
미구현 + detector 루프 미등록이라 raw 말풍선이 영원히 감지 안 됨.

→ detect_tooltip_shape 가 (a) 라운드+텍스트+x-close 또는 (b) 이름 힌트
(tooltip/툴팁/bubble/말풍선) 인 말풍선을 Tooltip 인스턴스로 confident swap 하고,
래퍼/뱃지/일반 카드는 오스왑하지 않는지 검증.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from design_rules.ds_catalog import (  # noqa: E402
    detect_ds_role_structural,
    detect_tooltip_shape,
    COMPONENT_KEYS,
)

_TOOLTIP_KEY = COMPONENT_KEYS["Tooltip"]


def _bubble(name="Bubble", label="궁금한 건 물어보세요.", *, close=True, cr=10):
    kids = [{"type": "text", "characters": label}]
    if close:
        kids.append({"type": "icon", "name": "ic-x-close", "iconName": "x-close"})
    return {"name": name, "type": "frame", "cornerRadius": cr, "fill": "$token(fg-primary)",
            "autoLayout": {"layoutMode": "HORIZONTAL"}, "children": kids}


def role_of(node, parent=None):
    r = detect_ds_role_structural(node, parent)
    return None if not r else (r[0], r[3])  # (role, confident)


# ── confident swap 대상 ────────────────────────────────────────────────

def test_bubble_with_close_icon_is_confident_tooltip():
    role, conf = role_of(_bubble())
    assert role == "Tooltip" and conf is True


def test_name_hint_tooltip_is_confident():
    n = _bubble(name="Help Tooltip", close=False)
    role, conf = role_of(n)
    assert role == "Tooltip" and conf is True


def test_returns_tooltip_key_and_label():
    r = detect_tooltip_shape(_bubble())
    assert r is not None
    assert r[0] == "Tooltip"
    assert r[1] == _TOOLTIP_KEY
    assert r[2] == "궁금한 건 물어보세요."


# ── 오탐 방지 (swap 금지) ──────────────────────────────────────────────

def test_wrapper_without_direct_text_not_swapped():
    # 'Bubble Wrap' 래퍼 — 직계 TEXT 없음 → swap 금지 (래퍼 오스왑 차단)
    wrap = {"name": "Bubble Wrap", "type": "frame",
            "autoLayout": {"layoutMode": "HORIZONTAL"},
            "children": [_bubble()]}
    assert detect_tooltip_shape(wrap) is None


def test_status_badge_not_tooltip():
    badge = {"name": "Status Pill", "type": "frame", "cornerRadius": 999,
             "children": [{"type": "text", "characters": "진행중"}]}
    assert detect_tooltip_shape(badge) is None


def test_plain_card_without_close_or_name_not_tooltip():
    # 라운드 + 텍스트지만 close 아이콘도 이름 힌트도 없음 → 콘텐츠 카드, swap 금지
    card = {"name": "Info Card", "type": "frame", "cornerRadius": 12,
            "children": [{"type": "text", "characters": "안내 문구"}]}
    assert detect_tooltip_shape(card) is None


def test_instance_node_skipped():
    inst = {"name": "Tooltip", "type": "instance", "componentKey": _TOOLTIP_KEY,
            "children": [{"type": "text", "characters": "x"}]}
    assert detect_tooltip_shape(inst) is None


# ── arrow 방향(대상 정조준) 회귀 테스트 (2026-06-04) ───────────────────
# 사용자 보고: arrow 가 대상(채팅)이 아니라 엉뚱한 버튼(북마크)을 가리킴.
# _tooltip_arrow_for 가 tooltip↔target 기하로 올바른 변형을 고르는지 검증.

import importlib  # noqa: E402

_fc = importlib.import_module("figma_mcp_client")

_T = {"x": 100, "y": 0, "width": 120, "height": 40}


def test_arrow_points_down_when_target_below():
    assert _fc._tooltip_arrow_for(_T, {"x": 130, "y": 60, "width": 44, "height": 40}) == "Bottom center"


def test_arrow_points_up_when_target_above():
    assert _fc._tooltip_arrow_for(_T, {"x": 130, "y": -60, "width": 44, "height": 40}) == "Top center"


def test_arrow_points_right_when_target_right():
    assert _fc._tooltip_arrow_for(_T, {"x": 260, "y": 5, "width": 40, "height": 30}) == "Right"


def test_arrow_points_left_when_target_left():
    assert _fc._tooltip_arrow_for(_T, {"x": 10, "y": 5, "width": 40, "height": 30}) == "Left"


def test_collect_tooltip_targets_reads_marker():
    bp = {"name": "root", "children": [
        {"name": "Wrap", "children": [
            {"name": "Tooltip", "componentKey": "e979943c", "_tooltipTarget": "Chat"}]}]}
    m = _fc._collect_tooltip_targets(bp)
    assert m.get(("root", "Wrap", "Tooltip")) == "Chat"
