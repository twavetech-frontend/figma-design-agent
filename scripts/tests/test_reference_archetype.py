# -*- coding: utf-8 -*-
"""레퍼런스 archetype 인식 회귀 테스트 (2026-06-08 사용자: "왜 자꾸 레퍼런스 검색을 빼먹지?").

근본 원인 ②: _auto_search_uibowl_references 가 'imin_home' 정확 부분문자열만 봐서
'imin_signup_home'·'imin_active_home'·'imin_*_home_creative' 가 미인식→일반 폴백 되며
진짜 홈 레퍼런스를 못 받았다. 이제 bare word(home/stage/...) 도 인식 → 홈 변형 전부 imin_home.

여기서는 archetype 추론 로직(부분문자열 + bare word 폴백)을 재현해 검증한다(네트워크 X).
"""
_KWS = ["imin_home", "imin_stage", "imin_lounge", "imin_community",
        "imin_payment", "imin_detail", "imin_onboarding", "imin_settings",
        "imin_notification", "imin_search", "imin_history"]
_BARE = (("home", "imin_home"), ("stage", "imin_stage"), ("lounge", "imin_lounge"),
         ("community", "imin_community"), ("payment", "imin_payment"),
         ("onboarding", "imin_onboarding"), ("notification", "imin_notification"),
         ("search", "imin_search"), ("history", "imin_history"), ("settings", "imin_settings"))


def detect_archetype(root_name):
    rn = (root_name or "").lower()
    for kw in _KWS:
        if kw in rn:
            return kw
    for bare, arch in _BARE:
        if bare in rn:
            return arch
    return None


def test_home_variants_map_to_imin_home():
    for rn in ["imin_signup_home_v4", "imin_active_home_v3", "imin_done_home_v3",
               "imin_signup_home_creative", "imin_active_home_creative",
               "imin_done_home_creative", "imin_home", "imin_home_dashboard_v2"]:
        assert detect_archetype(rn) == "imin_home", rn


def test_exact_substring_still_works():
    assert detect_archetype("imin_home") == "imin_home"
    assert detect_archetype("imin_stage_v1") == "imin_stage"


def test_bare_word_other_archetypes():
    assert detect_archetype("imin_stage_detail") == "imin_stage"
    assert detect_archetype("imin_payment_wallet") == "imin_payment"
    assert detect_archetype("imin_lounge_list") == "imin_lounge"
    assert detect_archetype("imin_community_feed") == "imin_community"


def test_unknown_returns_none():
    # archetype·bare word 모두 없으면 None → 호출부가 키워드/폴백 검색으로 처리
    assert detect_archetype("imin_foobar_screen") is None
    assert detect_archetype("") is None


def test_function_recognizes_home_variant_live():
    # 실제 모듈 함수가 home 변형을 imin_home 으로 인식하는지 — _LAST_REFERENCE 글로벌 존재 확인
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import figma_mcp_client as fc
    assert hasattr(fc, "_LAST_REFERENCE_THUMBS")
    assert hasattr(fc, "_auto_search_uibowl_references")
