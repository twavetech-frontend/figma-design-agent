"""Regression tests for spacing-token binding (padding/gap → 3. Spacing/spacing-* vars).

Background:
    2026-05-28 — 사용자: "padding, gap 값이 그냥 절대값으로 들어가 있는데 spacing-
    토큰이 바인딩 되어있지않아. 바인딩 되게 시스템 수정해".
    2026-05-29 — 사용자: "primitive(Spacing/) 값 쓰면 안돼. 3. Spacing 의 spacing- 토큰으로
    바인딩해야 한다." → `_load_spacing_map` 이 시맨틱 'spacing-*' 토큰만 사용 (primitive 'Spacing/' 제외).

    `_bind_spacing_tokens_live` 가 라이브 트리의 auto-layout padding/itemSpacing 최종
    값을 "3. Spacing" 컬렉션의 spacing-* DS 변수에 바인딩한다. 스케일 정확 일치 값만
    (시각 변화 0). 순수 수집 로직은 `_collect_spacing_bindings` 로 분리 — 이 테스트가 회귀 방지.

Run:
    python3 -m pytest scripts/tests/test_spacing_token_binding.py -v
"""
from __future__ import annotations

import os
import sys

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from figma_mcp_client import (  # noqa: E402
    _collect_spacing_bindings,
    _load_spacing_map,
    _SPACING_BIND_FIELDS,
)


# 테스트용 고정 spacing map (실제 TOKEN_MAP 의 부분집합 — 시맨틱 "3. Spacing" 토큰)
SP = {
    0.0: "spacing-none",
    2.0: "spacing-xxs",
    4.0: "spacing-xs",
    6.0: "spacing-sm",
    8.0: "spacing-md",
    12.0: "spacing-lg",
    16.0: "spacing-xl",
    20.0: "spacing-2xl",
    24.0: "spacing-3xl",
    32.0: "spacing-4xl",
}


def _collect(node):
    jobs, off = [], set()
    _collect_spacing_bindings(node, SP, jobs, off)
    return jobs, off


# ── on-scale 값은 바인딩 ────────────────────────────────────────────

def test_padding_on_scale_binds():
    node = {"id": "1:1", "type": "FRAME", "layoutMode": "VERTICAL",
            "paddingLeft": 20, "paddingRight": 20, "paddingTop": 8, "paddingBottom": 24}
    jobs, off = _collect(node)
    assert len(jobs) == 1
    b = jobs[0]["bindings"]
    assert b["paddingLeft"] == "spacing-2xl"
    assert b["paddingTop"] == "spacing-md"
    assert b["paddingBottom"] == "spacing-3xl"
    assert off == set()


def test_itemspacing_gap_binds():
    node = {"id": "1:2", "type": "FRAME", "layoutMode": "HORIZONTAL", "itemSpacing": 12}
    jobs, _ = _collect(node)
    assert jobs[0]["bindings"]["itemSpacing"] == "spacing-lg"


def test_float_value_normalized():
    """20.0 (float) 도 20 토큰에 매칭."""
    node = {"id": "1:3", "type": "FRAME", "layoutMode": "VERTICAL", "paddingLeft": 20.0}
    jobs, _ = _collect(node)
    assert jobs[0]["bindings"]["paddingLeft"] == "spacing-2xl"


# ── off-scale 값은 리터럴 유지 (임의 snap 금지) ──────────────────────

def test_off_scale_not_bound_recorded():
    node = {"id": "1:4", "type": "FRAME", "layoutMode": "VERTICAL",
            "paddingTop": 14, "itemSpacing": 18, "paddingBottom": 28}
    jobs, off = _collect(node)
    assert jobs == []  # 바인딩 없음
    assert off == {14.0, 18.0, 28.0}


def test_mixed_on_and_off_scale():
    node = {"id": "1:5", "type": "FRAME", "layoutMode": "VERTICAL",
            "paddingLeft": 20, "itemSpacing": 18}
    jobs, off = _collect(node)
    assert jobs[0]["bindings"] == {"paddingLeft": "spacing-2xl"}
    assert off == {18.0}


# ── 제외 케이스 ──────────────────────────────────────────────────────

def test_instance_excluded():
    """DS 인스턴스는 spacing 바인딩 제외 (컴포넌트가 제어)."""
    node = {"id": "1:6", "type": "INSTANCE", "layoutMode": "VERTICAL", "paddingLeft": 20}
    jobs, off = _collect(node)
    assert jobs == [] and off == set()


def test_instance_internal_node_excluded():
    """인스턴스 내부 노드(id 에 ';')는 제외."""
    node = {"id": "I123;4:5", "type": "FRAME", "layoutMode": "VERTICAL", "paddingLeft": 20}
    jobs, off = _collect(node)
    assert jobs == [] and off == set()


def test_non_autolayout_frame_excluded():
    """layoutMode NONE 인 frame 은 padding/gap 무의미 — 제외."""
    node = {"id": "1:7", "type": "FRAME", "layoutMode": "NONE", "paddingLeft": 20}
    jobs, off = _collect(node)
    assert jobs == [] and off == set()


def test_missing_spacing_fields_skipped():
    """padding/gap 필드가 없으면(None) 바인딩 없음."""
    node = {"id": "1:8", "type": "FRAME", "layoutMode": "VERTICAL"}
    jobs, off = _collect(node)
    assert jobs == [] and off == set()


def test_zero_padding_binds_to_spacing_0():
    """0px 도 spacing-none 토큰이 있으면 바인딩 (일관성)."""
    node = {"id": "1:9", "type": "FRAME", "layoutMode": "VERTICAL", "paddingLeft": 0}
    jobs, _ = _collect(node)
    assert jobs[0]["bindings"]["paddingLeft"] == "spacing-none"


def test_bool_not_treated_as_number():
    """layoutMode 외 bool 필드가 spacing 으로 오인되지 않음 (방어)."""
    node = {"id": "1:10", "type": "FRAME", "layoutMode": "VERTICAL",
            "paddingLeft": True, "paddingRight": 16}
    jobs, _ = _collect(node)
    # True 는 무시, 16 만 바인딩
    assert jobs[0]["bindings"] == {"paddingRight": "spacing-xl"}


# ── 실제 TOKEN_MAP 로드 ──────────────────────────────────────────────

def test_real_spacing_map_loads_common_values():
    """실제 TOKEN_MAP 에서 핵심 spacing 값들이 시맨틱 spacing-* 토큰으로 로드되는지.

    🔴 2026-05-29 사용자: primitive 'Spacing/' 금지, 'spacing-*' (3. Spacing) 만.
    """
    m = _load_spacing_map()
    # 값 → 시맨틱 토큰 정확 매핑
    expected = {
        0: "spacing-none", 2: "spacing-xxs", 4: "spacing-xs", 6: "spacing-sm",
        8: "spacing-md", 12: "spacing-lg", 16: "spacing-xl", 20: "spacing-2xl",
        24: "spacing-3xl", 32: "spacing-4xl",
    }
    for px, name in expected.items():
        assert float(px) in m, f"{px}px spacing 토큰 누락"
        assert m[float(px)] == name, f"{px}px → {m[float(px)]} (기대: {name})"
    # primitive 'Spacing/' 경로는 절대 포함하면 안 됨
    for fp in m.values():
        assert not fp.startswith("Spacing/"), f"primitive 토큰 누출: {fp}"
        assert fp.startswith("spacing-"), f"시맨틱 아님: {fp}"


def test_spacing_bind_fields_cover_padding_and_gap():
    """바인딩 대상 필드에 4방향 padding + itemSpacing(gap) 포함."""
    for f in ("paddingLeft", "paddingRight", "paddingTop", "paddingBottom", "itemSpacing"):
        assert f in _SPACING_BIND_FIELDS
