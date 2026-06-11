# -*- coding: utf-8 -*-
"""NavBar back 버튼 오른쪽 padding 표준 (2026-06-10 사용자 룰) — 상수·토큰 매핑 회귀 방지.

back 버튼 노출 시 Nav Back frame paddingRight = spacing-xl(16) 바인딩.
실제 적용은 _enforce_navbar_style_live(라이브, 중첩 함수)가 하며 라이브로 검증됨 —
여기선 값이 바뀌지 않도록 상수와 토큰 정합성만 고정한다.
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as fc


def test_constants():
    assert fc._NAV_BACK_PAD_RIGHT == 16
    assert fc._NAV_BACK_PAD_TOKEN == "spacing-xl"


def test_token_value_matches_padding():
    """바인딩 토큰(spacing-xl)의 실제 값이 paddingRight 와 같아야 시각 변화 0."""
    here = os.path.join(os.path.dirname(__file__), "..", "..", "ds", "TOKEN_MAP.json")
    if not os.path.exists(here):
        return  # DS 토큰 없으면 skip (CI 환경)
    m = json.load(open(here))
    items = m.get("tokens", m) if isinstance(m, dict) else m
    val = None
    for v in (items.values() if isinstance(items, dict) else []):
        if isinstance(v, dict) and v.get("figmaPath", "").split("/")[-1] == fc._NAV_BACK_PAD_TOKEN:
            val = v.get("value")
            break
    num = float(str(val).replace("px", "").strip())
    assert num == fc._NAV_BACK_PAD_RIGHT, f"{fc._NAV_BACK_PAD_TOKEN} value {val} != {fc._NAV_BACK_PAD_RIGHT}"
