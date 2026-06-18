# -*- coding: utf-8 -*-
"""흰 카드 Shadows/shadow-basic 자동 elevation 표준 (2026-06-18 사용자: "표준으로 박아줘, 빌드마다 자동").

흰 면+보더 카드에 DS shadow-basic 자동 바인딩. 배너 placeholder 제외(_noShadow/_placeholderAllowed),
월렛 등 개별코너 카드는 _cardShadow 강제.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as f


def test_collect_markers_force_and_skip():
    bp = {"name": "root", "children": [
        {"name": "Banner Card", "_placeholderAllowed": "CMS"},
        {"name": "Limit Callout", "_noShadow": True},
        {"name": "Wallet Bar", "_cardShadow": True},
        {"name": "Choice Tile", "children": [{"name": "x"}]},
    ]}
    force, skip = f._collect_card_shadow_markers(bp)
    assert force == {"Wallet Bar"}
    assert skip == {"Banner Card", "Limit Callout"}


def test_collect_markers_nested():
    bp = {"name": "r", "children": [
        {"name": "Section", "children": [
            {"name": "Inner Card", "_cardShadow": True}]}]}
    force, skip = f._collect_card_shadow_markers(bp)
    assert "Inner Card" in force


def test_collect_markers_empty():
    assert f._collect_card_shadow_markers({}) == (set(), set())
    assert f._collect_card_shadow_markers(None) == (set(), set())


def test_effect_style_map_has_shadow_basic():
    """ds/EFFECT_STYLE_MAP.json fallback 으로 shadow-basic 키가 로드돼야 (작업 파일 0건이어도)."""
    m = f._load_effect_style_map()
    # 키 맵이 커밋돼 있으면 shadow-basic 이 있어야 함
    assert "Shadows/shadow-basic" in m, "ds/EFFECT_STYLE_MAP.json 에 shadow-basic 키 필요"
    assert len(m["Shadows/shadow-basic"]) > 10  # 키는 긴 hex


if __name__ == "__main__":
    import traceback
    p = 0
    for n, fn in list(globals().items()):
        if n.startswith("test_") and callable(fn):
            try:
                fn(); p += 1; print(f"  ✓ {n}")
            except Exception:
                print(f"  ✗ {n}"); traceback.print_exc()
    print(f"✅ {p} 통과")
