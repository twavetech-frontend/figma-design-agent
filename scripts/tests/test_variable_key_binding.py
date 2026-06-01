# -*- coding: utf-8 -*-
"""변수 key 바인딩 폴백 회귀 테스트 (2026-06-01).

파일을 개인 Draft 로 옮기면 figma.teamLibrary 변수 검색이 비어 set_bound_variables
가 silent-skip → 색/spacing 토큰 바인딩 0건. 해결: ds/VARIABLE_KEY_MAP.json 의
figmaPath→key 로 'K:{key}' 를 보내 importVariableByKeyAsync 로 직접 import.

call_tool 이 set_bound_variables 의 바인딩 값을 중앙에서 K:{key} 로 변환하는지 검증.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import figma_mcp_client as fc  # noqa: E402


def _with_keymap(mapping):
    p = os.path.join(os.path.dirname(__file__), "__tmp_varkeymap.json")
    json.dump(mapping, open(p, "w"))
    fc.VARIABLE_KEY_MAP_FILE = p
    fc._variable_key_map = None
    return p


def test_binding_value_no_map_returns_name():
    fc.VARIABLE_KEY_MAP_FILE = "/tmp/__definitely_missing_keymap.json"
    fc._variable_key_map = None
    assert fc._binding_value("Colors/Background/bg-primary") == "Colors/Background/bg-primary"
    assert fc._binding_value(None) is None


def test_binding_value_with_map_returns_key():
    _with_keymap({"Colors/Background/bg-primary": "KEY_BG"})
    assert fc._binding_value("Colors/Background/bg-primary") == "K:KEY_BG"
    assert fc._binding_value("Colors/Unknown/x") == "Colors/Unknown/x"  # not in map → name
    assert fc._binding_value("K:already") == "K:already"                # idempotent


def test_call_tool_central_interception_transforms_bindings():
    _with_keymap({"Colors/Text/text-primary": "KEY_TEXT"})
    captured = {}

    def fake_req(method, params, msg_id=1):
        captured["args"] = params.get("arguments", {})
        return {"result": {"content": [{"type": "text", "text": "{}"}]}}

    orig = fc.mcp_request
    fc.mcp_request = fake_req
    try:
        fc.call_tool("set_bound_variables", {
            "nodeId": "1:1",
            "bindings": {"fills/0": "Colors/Text/text-primary",
                         "strokes/0": "Colors/Other/y",
                         "fontSize": None},
        })
    finally:
        fc.mcp_request = orig

    sent = captured["args"]["bindings"]
    assert sent["fills/0"] == "K:KEY_TEXT", sent     # mapped → key
    assert sent["strokes/0"] == "Colors/Other/y", sent  # unmapped → name
    assert sent["fontSize"] is None, sent            # unbind passes through


def test_non_binding_tool_untouched():
    _with_keymap({"Colors/Text/text-primary": "KEY_TEXT"})
    captured = {}

    def fake_req(method, params, msg_id=1):
        captured["args"] = params.get("arguments", {})
        return {"result": {"content": [{"type": "text", "text": "{}"}]}}

    orig = fc.mcp_request
    fc.mcp_request = fake_req
    try:
        fc.call_tool("set_fill_color", {"nodeId": "1:1", "r": 1, "g": 0, "b": 0})
    finally:
        fc.mcp_request = orig
    assert captured["args"] == {"nodeId": "1:1", "r": 1, "g": 0, "b": 0}


def test_collect_bindings_skips_built_instance_fill():
    """원본 blueprint 가 raw frame(R23 swap 전 deep-copy)이라도, 빌드된 노드가
    INSTANCE 면 fill/stroke 를 rebind 하지 않는다 (DS Badge/Button variant 색 보호).
    2026-06-01 사용자: 'badge color warning 인데 fill 을 맘대로 수정했다'."""
    bp = {"name": "입금 예정", "type": "frame", "fill": "$token(bg-secondary)",
          "children": [{"name": "t", "type": "text", "characters": "입금 예정",
                        "fontColor": "$token(text-primary)"}]}
    built = {"id": "1:1", "type": "INSTANCE", "name": "입금 예정",
             "children": [{"id": "1:2", "type": "TEXT", "name": "Label"}]}
    out = []
    fc._collect_bindings(bp, built, out)
    assert out == [], f"INSTANCE 의 fill/내부 색은 바인딩되면 안 됨, got {out}"


def test_collect_bindings_binds_plain_frame_fill():
    """일반 frame(비-인스턴스)은 정상적으로 fill 바인딩."""
    bp = {"name": "Card", "type": "frame", "fill": "$token(bg-secondary)", "children": []}
    built = {"id": "2:1", "type": "FRAME", "name": "Card", "children": []}
    out = []
    fc._collect_bindings(bp, built, out)
    assert len(out) == 1 and out[0]["bindings"].get("fills/0"), f"frame fill 바인딩 누락: {out}"


def _capture_call(name, args):
    """call_tool 을 통과시키되 plugin 으로 실제 전송된 arguments 를 캡처."""
    captured = {}

    def fake_req(method, params, msg_id=1):
        captured["args"] = params.get("arguments", {})
        captured["sent"] = True
        return {"result": {"content": [{"type": "text", "text": "{}"}]}}

    orig = fc.mcp_request
    fc.mcp_request = fake_req
    try:
        out = fc.call_tool(name, args)
    finally:
        fc.mcp_request = orig
    return captured, out


# ── 절대 규칙 0-K: 컴포넌트 내부('I…;…') 색 변경 차단 ───────────────────────
def test_guard_blocks_internal_fill_color():
    captured, out = _capture_call("set_fill_color", {"nodeId": "I2001:2583;4825:409531", "r": 1, "g": 0, "b": 0})
    assert not captured.get("sent"), "인스턴스 내부 set_fill_color 는 plugin 으로 전송되면 안 됨"
    assert "skipped" in (out[0]["text"] if out else ""), out


def test_guard_blocks_internal_stroke_binding():
    captured, out = _capture_call("set_bound_variables",
                                  {"nodeId": "I1:1;2:2", "bindings": {"strokes/0": "Colors/Border/border-secondary"}})
    assert not captured.get("sent"), "인스턴스 내부 strokes 바인딩은 차단되어야 함"


def test_guard_keeps_non_color_binding_on_internal():
    # 내부 노드라도 색이 아닌 바인딩(spacing/padding)은 통과
    captured, out = _capture_call("set_bound_variables",
                                  {"nodeId": "I1:1;2:2", "bindings": {"paddingLeft": "spacing-md",
                                                                       "fills/0": "Colors/X/y"}})
    assert captured.get("sent"), "비-색 바인딩은 전송되어야 함"
    sent = captured["args"]["bindings"]
    assert "paddingLeft" in sent and "fills/0" not in sent, sent


def test_guard_allows_internal_color_with_optout():
    captured, out = _capture_call("set_fill_color",
                                  {"nodeId": "I1:1;2:2", "r": 1, "g": 1, "b": 1, "_allowComponentColor": True})
    assert captured.get("sent"), "_allowComponentColor=True 면 전송"
    assert "_allowComponentColor" not in captured["args"], "플래그는 plugin 으로 새 나가면 안 됨"


def test_guard_ignores_toplevel_nodes():
    # 최상위(인스턴스 아님) 노드 색은 정상 통과
    captured, out = _capture_call("set_fill_color", {"nodeId": "2001:2493", "r": 1, "g": 0, "b": 0})
    assert captured.get("sent"), "최상위 노드 색은 통과"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {fn.__name__}: {e}")
    # cleanup
    tmp = os.path.join(os.path.dirname(__file__), "__tmp_varkeymap.json")
    if os.path.exists(tmp):
        os.remove(tmp)
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
