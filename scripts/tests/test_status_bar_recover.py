# -*- coding: utf-8 -*-
"""Status Bar ⚠ 에러 프레임 자동 복구 (2026-07-10).

배경: R24 inject 가 ds_catalog 의 stale 'Status Bar' 키로 instance 노드를 blueprint 에
박으면 import 실패 → code.js 가 '⚠ Status Bar' TEXT 를 담은 에러 FRAME 을 만들고,
그 존재가 code.js 의 이름 기반 FORCED 삽입(정상 폴백)까지 억제한다
(실측: imin_signup_home_20260709 — 수동 복구 ~4분). post-fix 의
_recover_error_status_bar_live 가 감지·교체하며, 여기서는 순수 감지 함수를 고정한다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as fmc  # noqa: E402


def _error_frame(name="Status Bar"):
    return {"type": "FRAME", "name": name,
            "children": [{"type": "TEXT", "characters": "⚠ Status Bar"}]}


def test_detects_error_frame():
    assert fmc._is_error_status_bar_frame(_error_frame()) is True


def test_detects_error_frame_name_variants():
    assert fmc._is_error_status_bar_frame(_error_frame("StatusBar")) is True
    assert fmc._is_error_status_bar_frame(_error_frame("status_bar")) is True


def test_healthy_instance_not_flagged():
    node = {"type": "INSTANCE", "name": "Status Bar",
            "children": [{"type": "FRAME", "name": "Time"}]}
    assert fmc._is_error_status_bar_frame(node) is False


def test_plain_frame_without_error_text_not_flagged():
    """이름만 Status Bar 인 정상(수동 제작) FRAME 은 복구 대상 아님 — ⚠ 텍스트가 결정자."""
    node = {"type": "FRAME", "name": "Status Bar",
            "children": [{"type": "TEXT", "characters": "9:41"}]}
    assert fmc._is_error_status_bar_frame(node) is False


def test_other_error_frame_not_flagged():
    """다른 컴포넌트의 ⚠ 에러 프레임(예: Tab Bar)은 이 복구 대상 아님."""
    node = {"type": "FRAME", "name": "Tab Bar",
            "children": [{"type": "TEXT", "characters": "⚠ Tab Bar"}]}
    assert fmc._is_error_status_bar_frame(node) is False


def test_catalog_key_updated():
    """stale 키 회귀 가드 — 카탈로그 키가 실측 신 키인지."""
    from design_rules import ds_catalog
    assert ds_catalog.COMPONENT_KEYS["Status Bar"] == "13557b1ed59ce3f8c2dfbf9df46ec8fa7f772486"
