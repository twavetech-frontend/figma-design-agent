# -*- coding: utf-8 -*-
"""doctor 명령 — 환경 진단 체크 검증 (Astryx CLI 패턴, 2026-07-08).

계약:
  - 각 체크는 {id, label, status, message[, fix]} 형태, status ∈ {pass,warn,fail,info}
  - 브리지 미기동이면 bridge=fail + 후속(mcp-session/plugin)=info (판정 불가)
  - fail/warn 항목에는 실행 가능한 fix 안내가 있다
  - cmd_doctor 는 FAIL ≥1 이면 exit 1 (WARN 은 실패 아님)
네트워크는 requests.get 을 mock 해 차단 — 테스트는 헤르메틱.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as fmc  # noqa: E402

VALID_STATUS = {"pass", "warn", "fail", "info"}


def _run_checks_bridge_down(monkeypatch):
    def _raise(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(fmc.requests, "get", _raise)
    # init_session 이 호출되면 안 됨 (브리지 down 이면 skip) — 호출 시 테스트 실패
    monkeypatch.setattr(fmc, "init_session",
                        lambda: pytest.fail("bridge down 인데 init_session 호출됨"))
    return fmc._doctor_checks()


def test_check_shape_and_status_values(monkeypatch):
    checks = _run_checks_bridge_down(monkeypatch)
    assert len(checks) >= 7
    ids = [c["id"] for c in checks]
    assert len(ids) == len(set(ids)), "체크 id 중복"
    for c in checks:
        assert c["status"] in VALID_STATUS, c
        assert c["id"] and c["label"] and c["message"], c


def test_bridge_down_marks_dependents_info(monkeypatch):
    checks = {c["id"]: c for c in _run_checks_bridge_down(monkeypatch)}
    assert checks["bridge"]["status"] == "fail"
    assert "npm run bridge" in checks["bridge"]["fix"]
    # 선행 실패 → 종속 체크는 fail 이 아니라 info (근본 원인 1개만 FAIL)
    assert checks["mcp-session"]["status"] == "info"
    assert checks["plugin"]["status"] == "info"


def test_fail_and_warn_have_fix(monkeypatch):
    for c in _run_checks_bridge_down(monkeypatch):
        if c["status"] in ("fail", "warn"):
            assert c.get("fix"), "fix 없는 %s 항목: %s" % (c["status"], c["id"])


def test_ds_maps_checked_against_repo(monkeypatch):
    """레포에 실존하는 ds 맵들은 pass 로 잡혀야 한다 (파일 기반 체크 실동작 검증)."""
    checks = {c["id"]: c for c in _run_checks_bridge_down(monkeypatch)}
    for cid in ("ds-token-map", "ds-text-styles", "ds-effect-styles", "ds-variable-keys"):
        assert cid in checks
    ds_dir = os.path.join(os.path.dirname(__file__), "..", "..", "ds")
    if os.path.exists(os.path.join(ds_dir, "TOKEN_MAP.json")):
        assert checks["ds-token-map"]["status"] == "pass"


def test_cmd_doctor_exit_code_contract(monkeypatch, capsys):
    """FAIL ≥1 → SystemExit(1). 전부 pass/warn/info → 정상 리턴."""
    monkeypatch.setattr(fmc, "_doctor_checks", lambda: [
        {"id": "x", "label": "X", "status": "fail", "message": "m", "fix": "f"},
    ])
    with pytest.raises(SystemExit) as e:
        fmc.cmd_doctor()
    assert e.value.code == 1

    monkeypatch.setattr(fmc, "_doctor_checks", lambda: [
        {"id": "x", "label": "X", "status": "pass", "message": "m"},
        {"id": "y", "label": "Y", "status": "warn", "message": "m", "fix": "f"},
    ])
    fmc.cmd_doctor()  # no exit
    out = capsys.readouterr().out
    assert "1 passed" in out and "1 warning" in out


def test_cmd_doctor_json_output_is_pure(monkeypatch, capsys):
    """--json 출력은 stdout 전체가 유효한 JSON 이어야 한다 (기계 소비 계약)."""
    import json
    monkeypatch.setattr(fmc, "_doctor_checks", lambda: [
        {"id": "x", "label": "X", "status": "pass", "message": "m"},
    ])
    fmc.cmd_doctor(json_out=True)
    out = capsys.readouterr().out
    doc = json.loads(out)
    assert doc["type"] == "doctor"
    assert doc["summary"]["pass"] == 1
    assert doc["checks"][0]["id"] == "x"
