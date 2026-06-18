# -*- coding: utf-8 -*-
"""S25 디자인 방향 게이트 + novelty 소프트 게이트 + 시그니처 민감도 (2026-06-15 사용자 룰).

"콘텐츠는 1:1, 비주얼은 매 시안 다르게" — 발산 강제 forcing function 검증.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as f


# ── S25 디자인 방향 선언 게이트 ─────────────────────────────────
def test_design_direction_required_blocks_when_missing():
    bp = {"name": "imin_home_v9", "children": []}
    issues = f._check_design_direction_required(bp)
    assert any(i.startswith("ERROR (S25)") for i in issues), issues


def test_design_direction_passes_with_3_axes():
    bp = {"name": "imin_home_v9", "children": [],
          "_designDirection": {"id": "editorial-asym",
                               "typography": "oversized-hero-32",
                               "color": "mono-brand+1pop",
                               "layout": "asymmetric-cards"}}
    assert f._check_design_direction_required(bp) == []


def test_design_direction_insufficient_axes_blocks():
    bp = {"name": "imin_home_v9", "children": [],
          "_designDirection": {"id": "x", "typography": "a"}}  # 1축뿐
    assert f._check_design_direction_required(bp), "3축 미만은 차단"


def test_design_direction_skipped_bypass():
    bp = {"name": "imin_home_v9", "children": [], "_designDirectionSkipped": "단순 재빌드"}
    assert f._check_design_direction_required(bp) == []


def test_non_archetype_skips_direction_gate():
    bp = {"name": "tmp_tabs", "children": []}
    assert f._check_design_direction_required(bp) == []


# ── S26 와이어/PRD 발산 선언 게이트 ─────────────────────────────
def test_wireframe_divergence_required_blocks_when_missing():
    bp = {"name": "imin_home_v9", "children": []}
    issues = f._check_wireframe_divergence_required(bp)
    assert any(i.startswith("ERROR (S26)") for i in issues), issues


def test_wireframe_divergence_passes_with_3_concrete():
    bp = {"name": "imin_home_v9", "children": [], "_wireframeDivergence": [
        "와이어는 좌측 라벨 나열인데 빌드는 금액을 32px 센터 히어로로 재배치",
        "와이어 단일 컬럼을 2-up 비대칭 카드 그리드로 변경",
        "와이어 평이한 그레이를 brand 액센트+상태색으로 위계화"]}
    assert f._check_wireframe_divergence_required(bp) == []


def test_wireframe_divergence_blocks_vague_items():
    """공허한 한두 단어 항목(<10자)은 차단."""
    bp = {"name": "imin_home_v9", "children": [],
          "_wireframeDivergence": ["색 바꿈", "크기", "정렬"]}
    assert f._check_wireframe_divergence_required(bp), "공허한 항목은 통과 못 함"


def test_wireframe_divergence_skipped_bypass():
    bp = {"name": "imin_home_v9", "children": [], "_wireframeDivergenceSkipped": "PRD 텍스트만"}
    assert f._check_wireframe_divergence_required(bp) == []


def test_wireframe_divergence_non_archetype_skips():
    bp = {"name": "tmp_sheet", "children": []}
    assert f._check_wireframe_divergence_required(bp) == []


def test_text_hierarchy_no_longer_auto_promotes():
    """#4a 폐기 — 카드 안 금액 텍스트를 30px로 자동 승격하지 않음(작성자 자유)."""
    bp = {"name": "r", "type": "frame", "children": [
        {"name": "Card", "type": "frame", "cornerRadius": 16, "fill": "$token(bg-primary)",
         "autoLayout": {"layoutMode": "VERTICAL"},
         "children": [{"type": "text", "text": "1,000,000원"}]}]}
    f._enforce_text_hierarchy(bp)
    amt = bp["children"][0]["children"][0]
    assert amt.get("fontSize") is None, "자동 승격되면 안 됨(작성자 미지정 그대로)"


# ── 시그니처 민감도 ─────────────────────────────────────────────
def _bp(mode, gap, size, align, weight):
    return {"name": "x", "type": "frame", "children": [
        {"type": "frame", "autoLayout": {"layoutMode": mode, "itemSpacing": gap},
         "children": [{"type": "text", "fontSize": size, "textAlignHorizontal": align,
                       "fontName": {"style": weight}}]}]}


def test_signature_drops_when_visual_changes():
    a = _bp("VERTICAL", 20, 16, "LEFT", "Bold")
    b = _bp("HORIZONTAL", 8, 32, "CENTER", "Regular")
    sim = f._signature_similarity(f._visual_signature(a), f._visual_signature(b))
    assert sim < 0.8, f"레이아웃/간격/타이포만 바꿔도 차단선 아래여야: {sim}"


def test_signature_identical_is_one():
    a = _bp("VERTICAL", 20, 16, "LEFT", "Bold")
    assert f._signature_similarity(f._visual_signature(a), f._visual_signature(a)) == 1.0


# ── novelty 소프트 게이트 ───────────────────────────────────────
def test_novelty_gate_blocks_near_duplicate():
    """직전 빌드와 거의 같은 시그니처면 차단."""
    orig = f._NOVELTY_DIR
    try:
        tmp = tempfile.mkdtemp()
        f._NOVELTY_DIR = tmp
        prev = _bp("VERTICAL", 20, 16, "LEFT", "Bold")
        prev["name"] = "imin_home_v8"
        f._novelty_save(prev)
        # 같은 비주얼로 다시 → 차단
        cur = _bp("VERTICAL", 20, 16, "LEFT", "Bold")
        cur["name"] = "imin_home_v9"
        issues = f._check_novelty_gate(cur)
        assert any(i.startswith("ERROR (novelty-gate)") for i in issues), issues
        # 충분히 다른 비주얼로 → 통과
        cur2 = _bp("HORIZONTAL", 8, 32, "CENTER", "Regular")
        cur2["name"] = "imin_home_v9"
        assert f._check_novelty_gate(cur2) == [], "발산하면 통과"
    finally:
        f._NOVELTY_DIR = orig


def test_novelty_gate_same_direction_id_blocks():
    orig = f._NOVELTY_DIR
    try:
        tmp = tempfile.mkdtemp()
        f._NOVELTY_DIR = tmp
        prev = _bp("VERTICAL", 20, 16, "LEFT", "Bold")
        prev["name"] = "imin_home_v8"
        prev["_designDirection"] = {"id": "editorial-asym"}
        f._novelty_save(prev)
        # 비주얼은 달라도 같은 방향 id → 차단
        cur = _bp("HORIZONTAL", 8, 32, "CENTER", "Regular")
        cur["name"] = "imin_home_v9"
        cur["_designDirection"] = {"id": "editorial-asym"}
        issues = f._check_novelty_gate(cur)
        assert any("디자인 방향 id" in i for i in issues), issues
    finally:
        f._NOVELTY_DIR = orig


def test_novelty_gate_bypass_marker():
    orig = f._NOVELTY_DIR
    try:
        tmp = tempfile.mkdtemp()
        f._NOVELTY_DIR = tmp
        prev = _bp("VERTICAL", 20, 16, "LEFT", "Bold"); prev["name"] = "imin_home_v8"
        f._novelty_save(prev)
        cur = _bp("VERTICAL", 20, 16, "LEFT", "Bold")
        cur["name"] = "imin_home_v9"
        cur["_noveltySkipped"] = "그대로 다시"
        assert f._check_novelty_gate(cur) == [], "_noveltySkipped 면 통과"
    finally:
        f._NOVELTY_DIR = orig


def test_novelty_gate_first_build_passes():
    orig = f._NOVELTY_DIR
    try:
        f._NOVELTY_DIR = tempfile.mkdtemp()
        cur = _bp("VERTICAL", 20, 16, "LEFT", "Bold"); cur["name"] = "imin_brandnew_v1"
        assert f._check_novelty_gate(cur) == [], "직전 빌드 없으면 통과"
    finally:
        f._NOVELTY_DIR = orig


if __name__ == "__main__":
    import traceback
    g = dict(globals())
    passed = 0
    for name, fn in g.items():
        if name.startswith("test_") and callable(fn):
            try:
                fn(); passed += 1; print(f"  ✓ {name}")
            except Exception:
                print(f"  ✗ {name}"); traceback.print_exc()
    print(f"✅ {passed} 테스트 통과")
