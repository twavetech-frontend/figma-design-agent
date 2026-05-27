"""Regression tests for _enforce_text_hierarchy parent-layout guard.

Background:
    2026-05-23 — `_enforce_text_hierarchy` 도입. 카드 안 통화 hero 텍스트
    (부호/콤마)를 30px Bold 로 자동 승격.

    2026-05-27 회귀: stage_list 빌드에서 카드 안의 *인라인* 금액 텍스트
    (HORIZONTAL row 안의 r2-amt "20,800,000원" 17px) 가 30px Bold 로 승격되어
    row 의 다른 자식(suffix "받아요" / pill 외곽)이 깨지고 카드 밖으로 흘러나옴.

    수정: 텍스트의 *직계 부모* layoutMode 가 HORIZONTAL 이면 hero 승격 skip.
    VERTICAL 부모의 직계 자식 hero 만 승격 (원래 의도).

Run:
    python3 -m pytest scripts/tests/test_text_hierarchy.py -v
"""
from __future__ import annotations

import os
import sys

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from figma_mcp_client import _enforce_text_hierarchy, _HERO_TEXT_SIZE  # noqa: E402


def _make_card(text_node: dict, parent_layout: str = "VERTICAL") -> dict:
    """카드 안에 자식 row(HORIZONTAL 또는 VERTICAL) + 그 안 text_node 로 구성."""
    return {
        "name": "root", "type": "frame",
        "autoLayout": {"layoutMode": "VERTICAL"},
        "children": [
            {
                "name": "Card", "type": "frame",
                "cornerRadius": 16, "fill": "$token(bg-primary)",
                "stroke": "$token(border-secondary)",
                "autoLayout": {"layoutMode": "VERTICAL"},
                "children": [
                    {
                        "name": "Row", "type": "frame",
                        "autoLayout": {"layoutMode": parent_layout},
                        "children": [text_node],
                    }
                ],
            }
        ],
    }


def test_vertical_parent_hero_amount_bumped():
    """VERTICAL 부모 직계 hero 금액 → 30px Bold 로 승격 (원래 의도)."""
    text = {"type": "text", "text": "1,000,000원", "fontSize": 17}
    bp = _make_card(text, parent_layout="VERTICAL")
    _enforce_text_hierarchy(bp)
    assert text["fontSize"] == _HERO_TEXT_SIZE  # 30
    assert (text.get("fontName") or {}).get("style") == "Bold"


def test_horizontal_parent_inline_amount_preserved():
    """
    🔴 회귀 방지 — stage_list v3 (2026-05-27).

    HORIZONTAL row 안 인라인 금액은 원래 fontSize 유지.
    승격되면 row 의 sibling("받아요" suffix / pill 외곽) 이 깨진다.
    """
    text = {"type": "text", "text": "20,800,000원", "fontSize": 17}
    bp = _make_card(text, parent_layout="HORIZONTAL")
    _enforce_text_hierarchy(bp)
    assert text["fontSize"] == 17  # 변경 없음
    assert (text.get("fontName") or {}).get("style") != "Bold"


def test_horizontal_parent_small_caption_preserved():
    """HORIZONTAL row 안 작은 caption("50,000P" 12px) 도 보존."""
    text = {"type": "text", "text": "50,000P", "fontSize": 12}
    bp = _make_card(text, parent_layout="HORIZONTAL")
    _enforce_text_hierarchy(bp)
    assert text["fontSize"] == 12


def test_non_amount_text_not_bumped():
    """금액 패턴 아닌 텍스트(부호/콤마 없음)는 승격 안 함."""
    text = {"type": "text", "text": "받아요", "fontSize": 17}
    bp = _make_card(text, parent_layout="VERTICAL")
    _enforce_text_hierarchy(bp)
    assert text["fontSize"] == 17


def test_text_outside_card_not_bumped():
    """카드 밖 텍스트는 승격 안 함 (rule scope = 카드 안)."""
    bp = {
        "name": "root", "type": "frame",
        "autoLayout": {"layoutMode": "VERTICAL"},
        "children": [
            {"type": "text", "text": "1,000,000원", "fontSize": 14},
        ],
    }
    _enforce_text_hierarchy(bp)
    assert bp["children"][0]["fontSize"] == 14


def test_already_hero_size_unchanged():
    """이미 28px 이상이면 그대로 (재실행 안전)."""
    text = {"type": "text", "text": "1,000,000원", "fontSize": 36}
    bp = _make_card(text, parent_layout="VERTICAL")
    _enforce_text_hierarchy(bp)
    assert text["fontSize"] == 36  # 36 그대로


def test_must_not_bump_horizontal_inline_amount():
    """
    anti-regression — 누군가 parent_layout 가드를 빼면 이 테스트가 깨진다.
    stage_list 의 모든 r{N}-amt / r{N}-yield 가 HORIZONTAL row 안.
    """
    samples = ["19,974,790원", "+1,000원", "-50,000P", "493,500원"]
    for s in samples:
        text = {"type": "text", "text": s, "fontSize": 13}
        bp = _make_card(text, parent_layout="HORIZONTAL")
        _enforce_text_hierarchy(bp)
        assert text["fontSize"] == 13, f"HORIZONTAL parent inline {s!r} should NOT be bumped"
