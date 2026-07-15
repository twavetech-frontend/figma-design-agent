# -*- coding: utf-8 -*-
"""와이어 트레이싱 3중 게이트 회귀 테스트 (2026-07-14~15 사용자 룰).

배경: 새 세션마다 와이어 배치를 그대로 옮기는 트레이싱이 재발
("와이어프레임이랑 아주 똑같다! 이러면 디자인 생성 맡길 이유가 없지").
선언형 게이트는 형식화로 뚫린다는 실측 → 3중 코드 게이트:
  S26-structural — 발산 선언 중 구조 레벨 어휘 ≥2 강제
  R65-flat-stack — 본문 세로 스택의 맨몸 콘텐츠 나열(트레이싱 시그니처) 차단
  S27-restructure — 재구성 맵 선언을 blueprint 실물과 대조 (커버리지/통합/실재)

이 테스트가 깨지면 게이트가 완화·드리프트된 것 — 트레이싱 재발 경보다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as f
from design_rules import REGISTRY


# ── 픽스처 ──────────────────────────────────────────────────────

def _traced_flat(name="imin_stage_test_v1"):
    """트레이싱 시그니처: 본문에 맨몸 텍스트 나열 + 코스메틱 발산 선언."""
    return {
        "name": name, "type": "frame", "fill": "$token(bg-primary)",
        "autoLayout": {"layoutMode": "VERTICAL"},
        "_wireframeDivergence": [
            "점선 셀을 솔리드 아웃라인으로 변경했습니다",
            "이모지를 DS 아이콘으로 치환했습니다",
            "배지 색을 시맨틱 컬러로 매핑했습니다",
        ],
        "children": [{
            "name": "Detail Body", "type": "frame",
            "autoLayout": {"layoutMode": "VERTICAL"},
            "children": [
                {"type": "text", "text": "헤드라인입니다", "fontSize": 20},
                {"type": "text", "text": "안내 문구입니다", "fontSize": 16},
                {"type": "text", "text": "19:03:54", "fontSize": 32},
                {"name": "Rows", "type": "frame",
                 "autoLayout": {"layoutMode": "VERTICAL"},
                 "children": [{"type": "text", "text": "라벨", "fontSize": 16}]},
                {"name": "Card A", "type": "frame", "fill": "$token(bg-secondary)",
                 "autoLayout": {"layoutMode": "VERTICAL"}, "children": []},
                {"name": "Card B", "type": "frame", "fill": "$token(bg-secondary)",
                 "autoLayout": {"layoutMode": "VERTICAL"}, "children": []},
            ]}],
    }


def _redesigned(name="imin_stage_test_v2"):
    """재설계본: 표면 그룹 + 구조 발산 선언 + 유효한 재구성 맵."""
    return {
        "name": name, "type": "frame", "fill": "$token(bg-primary)",
        "autoLayout": {"layoutMode": "VERTICAL"},
        "_wireframeDivergence": [
            "헤드라인·모집현황·수치를 하나의 개요 카드로 통합해 첫 표면으로 승격",
            "조건 테이블을 카드 표면에 수납하고 링크를 풋터로 병합",
            "순번 그리드와 범례를 순번 카드로 그룹핑해 3표면 리듬으로 재구성",
        ],
        "_restructureMap": {
            "wireSections": ["헤드라인", "모집현황", "조건 테이블", "순번", "범례"],
            "surfaces": [
                {"name": "Overview Card", "absorbs": ["헤드라인", "모집현황"]},
                {"name": "Cond Card", "absorbs": ["조건 테이블"]},
                {"name": "Seat Card", "absorbs": ["순번", "범례"]},
            ],
        },
        "children": [{
            "name": "Detail Body", "type": "frame",
            "autoLayout": {"layoutMode": "VERTICAL"},
            "children": [
                {"name": "Overview Card", "type": "frame", "fill": "$token(bg-primary)",
                 "stroke": "$token(border-primary)",
                 "autoLayout": {"layoutMode": "VERTICAL"},
                 "children": [{"type": "text", "text": "헤드라인", "fontSize": 20}]},
                {"name": "Cond Card", "type": "frame", "fill": "$token(bg-primary)",
                 "stroke": "$token(border-primary)",
                 "autoLayout": {"layoutMode": "VERTICAL"},
                 "children": [{"type": "text", "text": "지급액", "fontSize": 16}]},
                {"name": "Seat Card", "type": "frame", "fill": "$token(bg-primary)",
                 "stroke": "$token(border-primary)",
                 "autoLayout": {"layoutMode": "VERTICAL"},
                 "children": [{"type": "text", "text": "순번", "fontSize": 16}]},
            ]}],
    }


# ── S26-structural ──────────────────────────────────────────────

def test_s26_blocks_cosmetic_only_divergence():
    issues = f._check_wireframe_divergence_required(_traced_flat())
    assert any("S26-structural" in i for i in issues), issues


def test_s26_passes_structural_divergence():
    assert f._check_wireframe_divergence_required(_redesigned()) == []


# ── R65 flat-stack ──────────────────────────────────────────────

def test_r65_flags_flat_stack_tracing():
    v = REGISTRY.run_lint(_traced_flat())
    assert any(x.rule_id == "R65-flat-stack-tracing" for x in v), \
        [x.rule_id for x in v]


def test_r65_passes_surfaced_body():
    v = REGISTRY.run_lint(_redesigned())
    assert not any(x.rule_id == "R65-flat-stack-tracing" for x in v), \
        [(x.rule_id, x.message) for x in v if x.rule_id == "R65-flat-stack-tracing"]


def test_r65_skips_table_inside_surface_card():
    bp = _redesigned()
    # 카드 안 7행 라벨-값 테이블 — 정당한 평면 리스트 (오탐 금지)
    card = bp["children"][0]["children"][1]
    card["children"] = [{"name": "Row %d" % i, "type": "frame",
                         "autoLayout": {"layoutMode": "VERTICAL"},
                         "children": [{"type": "text", "text": "라벨 %d" % i, "fontSize": 16}]}
                        for i in range(7)]
    card["autoLayout"] = {"layoutMode": "VERTICAL"}
    v = REGISTRY.run_lint(bp)
    assert not any(x.rule_id == "R65-flat-stack-tracing" for x in v)


# ── S27 재구성 맵 ────────────────────────────────────────────────

def test_s27_blocks_missing_map():
    issues = f._check_restructure_map_required(_traced_flat())
    assert any(i.startswith("ERROR (S27)") for i in issues), issues


def test_s27_blocks_one_to_one_wrapping():
    bp = _redesigned()
    bp["_restructureMap"]["surfaces"] = [
        {"name": "Overview Card", "absorbs": ["헤드라인"]},
        {"name": "Cond Card", "absorbs": ["조건 테이블"]},
        {"name": "Seat Card", "absorbs": ["순번"]},
    ]
    bp["_restructureMap"]["wireSections"] = ["헤드라인", "조건 테이블", "순번"]
    issues = f._check_restructure_map_required(bp)
    assert any("S27-consolidation" in i for i in issues), issues


def test_s27_blocks_missing_coverage():
    bp = _redesigned()
    bp["_restructureMap"]["surfaces"][0]["absorbs"] = ["헤드라인"]  # 모집현황 미흡수
    issues = f._check_restructure_map_required(bp)
    assert any("S27-coverage" in i for i in issues), issues


def test_s27_blocks_phantom_surface():
    bp = _redesigned()
    bp["_restructureMap"]["surfaces"][0]["name"] = "존재하지 않는 카드"
    issues = f._check_restructure_map_required(bp)
    assert any("S27-exists" in i for i in issues), issues


def test_s27_passes_valid_map():
    assert f._check_restructure_map_required(_redesigned()) == []


def test_s27_bypass_with_reason():
    bp = _traced_flat()
    bp["_restructureMapSkipped"] = "설정 메뉴형 평면 리스트 화면"
    assert f._check_restructure_map_required(bp) == []
