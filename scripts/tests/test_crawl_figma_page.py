"""crawl_figma_page 오프라인 회귀 테스트 (2026-09-04).

회귀: 플러그인 순간 단절 시 MCP error 응답을 조용히 None 으로 삼켜 섹션 12개가 통째로 빠진
채 '성공'으로 보고됨(95/921 화면). 이제 에러는 집계(FAILS)·재접속 재시도·exit 1 이어야 한다.
"""
import json, os, sys, types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import crawl_figma_page as CR  # noqa: E402


class _Resp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


def _fake_http(script):
    """script: list of callables(payload) -> dict  (순서대로 소비)."""
    calls = []

    def post(url, json=None, headers=None, timeout=None):
        calls.append(json["params"]["name"])
        return _Resp(script.pop(0)(json))
    return types.SimpleNamespace(post=post), calls


def _ok(node):
    return lambda p: {"result": {"content": [{"type": "text", "text": json.dumps(node)}]}}


def _err(msg):
    return lambda p: {"error": {"code": -32000, "message": msg}}


def setup_function(_):
    CR.FAILS.clear()
    CR.RECONNECT_WAIT = 0.01
    CR.fc.get_session_id = lambda: "sid"


def test_mcp_error_is_recorded_not_swallowed():
    CR.fc._http, calls = _fake_http([_err("Node not found with ID: 1:2")])
    assert CR.call("get_node_info", {"nodeId": "1:2"}) is None
    assert CR.FAILS and "Node not found" in CR.FAILS[0][2]


def test_plugin_disconnect_waits_and_retries():
    CR.fc._http, calls = _fake_http([
        _err("Not connected to Figma plugin"),      # 최초 호출 실패
        _ok({"id": "0:0", "type": "DOCUMENT"}),      # 재접속 폴링 성공
        _ok({"id": "1:2", "type": "SECTION", "children": []}),  # 재시도 성공
    ])
    r = CR.call("get_node_info", {"nodeId": "1:2"})
    assert r is not None and CR.FAILS == []
    assert calls == ["get_node_info", "get_document_info", "get_node_info"]


def test_failed_section_leaves_placeholder_and_failed_stat():
    page = {"id": "0:1", "type": "PAGE", "children": [
        {"id": "9:1", "type": "SECTION", "name": "2. 커뮤니티", "width": 5000},
    ]}
    CR.fc._http, _ = _fake_http([_ok(page), _err("boom")])
    xml, stats = CR.crawl("0:1", log=lambda *a, **k: None)
    assert stats["failed"] == 1 and len(CR.FAILS) == 1
    assert 'name="2. 커뮤니티"' in xml and 'crawl="failed"' in xml


def test_main_exits_1_when_any_failure(tmp_path, monkeypatch):
    page = {"id": "0:1", "type": "PAGE", "children": [
        {"id": "9:1", "type": "SECTION", "name": "S", "width": 5000},
    ]}
    CR.fc._http, _ = _fake_http([_ok(page), _err("boom")])
    out = tmp_path / "p.xml"
    monkeypatch.setattr(sys, "argv", ["crawl", "--out", str(out)])
    assert CR.main() == 1 and out.exists()


def test_help_does_not_crawl(monkeypatch):
    CR.fc._http, calls = _fake_http([])
    monkeypatch.setattr(sys, "argv", ["crawl", "--help"])
    assert CR.main() == 0 and calls == []
