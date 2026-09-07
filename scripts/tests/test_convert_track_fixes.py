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


def test_home_indicator_removed_when_keyboard():
    """규칙 0-Y-2 (2026-09-07): 키보드 화면은 HomeIndicator 삭제 대상, 키보드 없으면 유지."""
    kids = [{"id": "1:1", "name": "Status Bar"}, {"id": "1:2", "name": "Content"},
            {"id": "1:3", "name": "Keyboard", "type": "INSTANCE"},
            {"id": "1:4", "name": "HomeIndicator", "type": "INSTANCE"}]
    assert fc._home_indicators_to_remove_for_keyboard(kids) == ["1:4"]
    no_kb = [k for k in kids if k["name"] != "Keyboard"]
    assert fc._home_indicators_to_remove_for_keyboard(no_kb) == []
    # 소스 raw 'keyboard' GROUP 도 키보드로 인정, 인스턴스 내부(';') HI 는 제외
    kids2 = [{"id": "2:1", "name": "keyboard", "type": "GROUP"},
             {"id": "I2:2;3:4", "name": "Bars/Home Indicator/iPhone/Light - Portrait", "type": "INSTANCE"},
             {"id": "2:3", "name": "Bars/Home Indicator/iPhone/Light - Portrait", "type": "INSTANCE"}]
    assert fc._home_indicators_to_remove_for_keyboard(kids2) == ["2:3"]


def test_ds_convert_lib_has_keyboard():
    import ds_convert_lib as lib
    assert lib.has_keyboard({"children": [{"name": "Keyboard", "type": "INSTANCE"}]})
    assert not lib.has_keyboard({"children": [{"name": "Keyboard", "visible": False}]})
    assert not lib.has_keyboard({"children": [{"name": "HomeIndicator"}]})
    assert not lib.has_keyboard(None)
