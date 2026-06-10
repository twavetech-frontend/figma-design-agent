# -*- coding: utf-8 -*-
"""레이아웃 스멜 결정적 검출 — _detect_layout_smells (2026-06-10).
순수 함수: _collect_tree 출력 형태(dict + _children_full)를 받아 WARN 문자열 리스트 반환."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from figma_mcp_client import _detect_layout_smells


def F(name, **kw):
    n = {"name": name, "type": "FRAME"}
    n.update(kw)
    n.setdefault("_children_full", [])
    return n


def T(chars, **kw):
    n = {"name": "t", "type": "TEXT", "characters": chars}
    n.update(kw)
    return n


# ── 1) SPACE_BETWEEN + 콘텐츠 든 FILL 자식 (선물 Giver Info 회귀) ──
def test_space_between_fill_content_child_flagged():
    row = F("Gift Bottom", layoutMode="HORIZONTAL", primaryAxisAlignItems="SPACE_BETWEEN",
            width=235, _children_full=[
                T("20,000원", layoutSizingHorizontal="HUG", width=70),
                F("Giver Info", layoutSizingHorizontal="FILL", width=165,
                  _children_full=[F("Dot", width=24), T("유정아범", width=60)]),
            ])
    s = _detect_layout_smells(row)
    assert any("SPACE_BETWEEN" in x and "Giver Info" in x for x in s)


def test_space_between_empty_fill_spacer_ok():
    # 콘텐츠 없는 FILL 스페이서는 정당 — flag 안 함
    row = F("Header", layoutMode="HORIZONTAL", primaryAxisAlignItems="SPACE_BETWEEN", width=300,
            _children_full=[
                T("Title", layoutSizingHorizontal="HUG", width=80),
                F("Spacer", layoutSizingHorizontal="FILL", width=180, _children_full=[]),
                T("Action", layoutSizingHorizontal="HUG", width=40),
            ])
    assert _detect_layout_smells(row) == []


def test_space_between_all_hug_ok():
    row = F("Row", layoutMode="HORIZONTAL", primaryAxisAlignItems="SPACE_BETWEEN", width=300,
            _children_full=[T("A", layoutSizingHorizontal="HUG", width=40),
                            T("B", layoutSizingHorizontal="HUG", width=40)])
    assert _detect_layout_smells(row) == []


# ── 2) 짧은 텍스트 wrap ("후기 공유" → "후/기", 탭 라벨) ──
def test_short_text_wrapped_flagged_with_fontsize():
    box = F("Review Share Box", _children_full=[T("후기 공유", fontSize=11, height=28)])  # 28 >= 11*1.7
    assert any("후기 공유" in x for x in _detect_layout_smells(box))


def test_short_text_wrapped_flagged_without_fontsize():
    box = F("Tab", _children_full=[T("커뮤니티", height=40)])  # fontSize 없음 → height>=36
    assert any("커뮤니티" in x for x in _detect_layout_smells(box))


def test_short_text_single_line_ok():
    box = F("Tab", _children_full=[T("전체", fontSize=22, height=30)])  # 30 < 22*1.7=37.4
    assert _detect_layout_smells(box) == []


def test_explicit_newline_not_flagged():
    box = F("Hero", _children_full=[T("줄1\n줄2", fontSize=16, height=44)])
    assert _detect_layout_smells(box) == []


def test_long_text_multiline_not_flagged():
    # 긴 텍스트(>6자)는 정상적으로 2줄 가능 — 짧은 텍스트만 대상
    box = F("Body", _children_full=[T("이것은 충분히 긴 본문 텍스트", fontSize=15, height=50)])
    assert _detect_layout_smells(box) == []


# ── 3) 폭 붕괴 (<4px, 2-col FILL collapse) ──
def test_collapsed_width_flagged():
    row = F("Steppers", layoutMode="HORIZONTAL", _children_full=[
        F("기간", width=1.5, _children_full=[T("x")]),
        F("월 입금", width=300, _children_full=[T("y")]),
    ])
    assert any("붕괴" in x and "기간" in x for x in _detect_layout_smells(row))


def test_empty_and_none_safe():
    assert _detect_layout_smells(None) == []
    assert _detect_layout_smells({}) == []
    assert _detect_layout_smells(F("x")) == []
