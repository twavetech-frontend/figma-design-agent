"""2026-09-04 변환 16분 회귀 4종 오프라인 테스트 — 순수 판별 함수 + 에러 코드 등록."""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import figma_mcp_client as fc  # noqa: E402
import error_codes as ec  # noqa: E402


def test_skip_reference_step_on_convert_track(monkeypatch):
    monkeypatch.setenv("IMIN_CONVERT_TRACK", "1")
    assert fc._should_skip_reference_step({"name": "x"})


def test_skip_reference_step_on_references_skipped_reason(monkeypatch):
    monkeypatch.delenv("IMIN_CONVERT_TRACK", raising=False)
    assert fc._should_skip_reference_step({"_referencesSkipped": "1:1 캡처 변환"})
    assert fc._should_skip_reference_step({"_referencesSkipped": "   "}) is None
    assert fc._should_skip_reference_step({"_referencesSkipped": True}) is None  # boolean 금지
    assert fc._should_skip_reference_step({"name": "imin_home"}) is None


def test_root_height_mode_prefers_flow_when_fill_child():
    assert fc._pick_root_height_mode(True, True, False) == "B"
    assert fc._pick_root_height_mode(True, True, True) == "B"
    assert fc._pick_root_height_mode(False, True, True) == "A-flow"
    assert fc._pick_root_height_mode(False, True, False) == "A"
    assert fc._pick_root_height_mode(False, False, True) == "A"


def test_action_button_height_table():
    assert fc._action_button_expected_height("2xl") == 56
    assert fc._action_button_expected_height("SM") == 24
    assert fc._action_button_expected_height(None) is None
    assert fc._action_button_expected_height("huge") is None


def test_icon_unresolved_error_code_registered():
    assert "ERR_ICON_UNRESOLVED" in ec.ERROR_CODES
