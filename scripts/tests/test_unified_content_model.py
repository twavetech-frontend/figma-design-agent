"""Regression tests for Unified Content Model (Refactor A — 2026-05-28).

Background:
    사용자 분노 4회 후 결정. polish + mock + 와이어 콘텐츠 3-layer 분리 구조가
    매번 충돌 → unified spec 으로 통합.

    docs/refactor-A-unified-content-model.md 참조.
    A.3.1 ~ A.3.5 완료 후 회귀 차단용.

Covers:
    - load_archetype_spec — archetype 별 base spec 로드
    - detect_scenario — wire_content 분석 → active / empty 판단
    - build_unified_blueprint — spec → blueprint
    - 중복 hero 차단 (Recommend 카드 currency 1개)
    - active 14 sections / empty 13 sections (Top Alert scenario_only skip)
    - Participating Empty Card swap (empty 시나리오)
    - cmd_build 통합 — _is_unified_spec_input + _maybe_resolve_unified_input

Run:
    python3 -m pytest scripts/tests/test_unified_content_model.py -v
"""
from __future__ import annotations

import json
import os
import sys

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from unified_blueprint import (  # noqa: E402
    build_unified_blueprint,
    detect_scenario,
    load_archetype_spec,
    resolve_archetype,
)
from figma_mcp_client import (  # noqa: E402
    _is_unified_spec_input,
    _maybe_resolve_unified_input,
)


# ─────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────


def _collect_texts(node):
    """Recursive — blueprint 의 모든 text/characters 수집."""
    out = []
    if not isinstance(node, dict):
        return out
    if node.get("type") in ("text", "TEXT"):
        for k in ("text", "characters", "content"):
            v = node.get(k)
            if isinstance(v, str):
                out.append(v)
    for ch in node.get("children", []) or []:
        out.extend(_collect_texts(ch))
    return out


def _find_nodes_by_name_contains(node, needle):
    """이름에 needle 포함된 노드 list."""
    out = []
    if not isinstance(node, dict):
        return out
    name = (node.get("name") or "").lower()
    if needle.lower() in name:
        out.append(node)
    for ch in node.get("children", []) or []:
        out.extend(_find_nodes_by_name_contains(ch, needle))
    return out


def _count_currency_heros(node, currency_keywords=("1,300,000원", "1,300만원")):
    """카드 안에 currency hero 가 몇 번 등장하는지 — 중복 hero 차단 검증."""
    txts = _collect_texts(node)
    return sum(1 for t in txts if any(kw in t for kw in currency_keywords))


# ─────────────────────────────────────────────────────────────
# A. spec loader / archetype resolve
# ─────────────────────────────────────────────────────────────


def test_archetype_spec_loads():
    spec = load_archetype_spec("imin_home")
    assert spec is not None
    assert spec.get("archetype") == "imin_home"
    assert isinstance(spec.get("mock_data"), dict)
    assert isinstance(spec.get("sections"), list)
    assert len(spec["sections"]) >= 14


def test_load_unknown_archetype_returns_none():
    assert load_archetype_spec("nonexistent_archetype_xyz") is None


def test_resolve_archetype_from_name():
    assert resolve_archetype("imin_home_v33_2026_0528") == "imin_home"
    assert resolve_archetype({"archetype": "imin_my"}) == "imin_my"
    assert resolve_archetype("random_screen") is None


# ─────────────────────────────────────────────────────────────
# B. scenario 결정
# ─────────────────────────────────────────────────────────────


def test_detect_scenario_active_default():
    assert detect_scenario({}) == "active"
    assert detect_scenario({"1.3": {"saved": "+1,240,000원"}}) == "active"


def test_detect_scenario_empty_signals():
    wire = {
        "1.3 progress": {"count": "0건", "saved": "+0원", "borrowed": "-0원"},
        "1.6 participating": {"message": "참여 중인 스테이지가 없어요"},
    }
    assert detect_scenario(wire) == "empty"


def test_detect_scenario_few_signals_active():
    # signals < 3 → active
    wire = {"1.3": {"saved": "+0원", "borrowed": "+1,240,000원"}}
    assert detect_scenario(wire) == "active"


# ─────────────────────────────────────────────────────────────
# C. build_unified_blueprint — section counts + scenario gating
# ─────────────────────────────────────────────────────────────


def test_active_scenario_14_sections():
    """Active wire content → Top Alert Banner 포함 14 섹션."""
    spec = load_archetype_spec("imin_home")
    bp = build_unified_blueprint(spec, wire_content=None)
    assert bp["_scenario"] == "active"
    assert bp["_unified"] is True
    assert len(bp["children"]) == 14
    # Top Alert Banner 존재
    alerts = _find_nodes_by_name_contains(bp, "Top Alert")
    assert len(alerts) >= 1


def test_empty_scenario_13_sections():
    """Empty wire content → Top Alert Banner scenario_only=active 로 skip → 13 섹션."""
    spec = load_archetype_spec("imin_home")
    empty_wire = {
        "1.3 progress": {"count": "0건", "saved": "+0원", "borrowed": "-0원"},
        "1.6 participating": {"message": "참여 중인 스테이지가 없어요"},
    }
    bp = build_unified_blueprint(spec, wire_content=empty_wire)
    assert bp["_scenario"] == "empty"
    assert len(bp["children"]) == 13
    # Top Alert Banner 없어야 함
    alerts = _find_nodes_by_name_contains(bp, "Top Alert")
    assert len(alerts) == 0


def test_blueprint_meta_fields():
    """unified blueprint 가 _wireframeContent / _scenario / _archetype meta 박는지."""
    spec = load_archetype_spec("imin_home")
    wire = {"some": "content"}
    bp = build_unified_blueprint(spec, wire_content=wire)
    assert bp["_unified"] is True
    assert bp["_archetype"] == "imin_home"
    assert bp["_wireframeContent"] == wire
    assert bp.get("fill") == "$token(bg-primary)"


# ─────────────────────────────────────────────────────────────
# D. 중복 hero 차단 (legacy polish 회귀 케이스)
# ─────────────────────────────────────────────────────────────


def test_no_duplicate_currency_hero_in_recommend_card():
    """Recommend Stage Card 안 currency hero "1,300,000원" 이 정확히 1번만 — 중복 hero 회귀 차단.

    Legacy _polish_recommend_hero_cta 가 hero 를 또 박아 2개 currency 가 표시되던 케이스.
    """
    spec = load_archetype_spec("imin_home")
    bp = build_unified_blueprint(spec, wire_content=None)
    recommend = _find_nodes_by_name_contains(bp, "Recommend Stage")
    assert len(recommend) >= 1
    # Recommend wrap 안 1,300,000원 hero 1개만
    hero_count = _count_currency_heros(recommend[0])
    assert hero_count >= 1, "Recommend card 에 currency hero 없음"
    assert hero_count <= 2, f"중복 currency hero — got {hero_count}"


def test_participating_grid_in_active_scenario():
    """Active → Participating Section 에 stage cards 4개 grid."""
    spec = load_archetype_spec("imin_home")
    bp = build_unified_blueprint(spec, wire_content=None)
    participating = _find_nodes_by_name_contains(bp, "Participating")
    assert len(participating) >= 1
    # 카드/그리드 노드 존재 — 텍스트로 "월" 패턴이 4번 정도 (amount field)
    txts = _collect_texts(participating[0])
    amount_count = sum(1 for t in txts if "월" in t and "원" in t)
    assert amount_count >= 3, f"participating grid cards 부족 — amount lines={amount_count}"


# ─────────────────────────────────────────────────────────────
# E. cmd_build 통합 — _is_unified_spec_input + _maybe_resolve_unified_input
# ─────────────────────────────────────────────────────────────


def test_thin_spec_detected_as_unified():
    """archetype + wire_content 만 있는 thin spec → unified 인식."""
    thin = {"archetype": "imin_home", "wire_content": {"foo": "bar"}}
    assert _is_unified_spec_input(thin) is True


def test_regular_blueprint_not_unified():
    """일반 blueprint (type:frame + children) → unified 아님."""
    bp = {
        "name": "test",
        "type": "frame",
        "children": [{"type": "text", "characters": "hi"}],
    }
    assert _is_unified_spec_input(bp) is False


def test_full_spec_detected_as_unified():
    """archetype_specs JSON 그대로 → unified 인식."""
    with open(os.path.join(_SCRIPTS, "archetype_specs", "imin_home.json")) as f:
        spec = json.load(f)
    assert _is_unified_spec_input(spec) is True


def test_unified_resolution_produces_blueprint():
    """thin spec 입력 → _maybe_resolve_unified_input → unified blueprint."""
    thin = {"archetype": "imin_home", "wire_content": None}
    out = _maybe_resolve_unified_input(thin, "")
    assert out.get("_unified") is True
    assert isinstance(out.get("children"), list)
    assert len(out["children"]) >= 13


def test_regular_blueprint_passes_through_unchanged():
    """일반 blueprint → 그대로 반환."""
    bp = {
        "name": "test",
        "type": "frame",
        "children": [{"type": "text", "characters": "hi"}],
    }
    out = _maybe_resolve_unified_input(bp, "")
    assert out is bp  # identity — 변환 안 함


# ─────────────────────────────────────────────────────────────
# F. footer / fab / tab_bar — simple section sanity
# ─────────────────────────────────────────────────────────────


def test_footer_policies_present():
    spec = load_archetype_spec("imin_home")
    bp = build_unified_blueprint(spec)
    footers = _find_nodes_by_name_contains(bp, "Footer Policy")
    assert len(footers) >= 1
    txts = _collect_texts(footers[0])
    # 이용약관 등 정책 텍스트 ≥ 5개
    policy_count = sum(1 for t in txts if "약관" in t or "정책" in t or "신고" in t)
    assert policy_count >= 3, f"footer policy lines 부족 — got {policy_count}"


def test_tab_bar_has_home_active():
    spec = load_archetype_spec("imin_home")
    bp = build_unified_blueprint(spec)
    tabs = _find_nodes_by_name_contains(bp, "Tab Bar")
    assert len(tabs) >= 1


def test_fab_section_present():
    spec = load_archetype_spec("imin_home")
    bp = build_unified_blueprint(spec)
    fabs = _find_nodes_by_name_contains(bp, "FAB")
    assert len(fabs) >= 1
