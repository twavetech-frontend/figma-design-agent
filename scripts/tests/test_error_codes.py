# -*- coding: utf-8 -*-
"""안정적 에러 코드 + BUILD-SUMMARY-JSON — 계약 검증 (Astryx 패턴, 2026-07-08).

핵심 계약:
  - 코드는 append-only: ERR_<...> 네이밍, GATE_TAG_TO_CODE 의 값은 전부 ERROR_CODES 에 존재
  - 드리프트 가드: figma_mcp_client.py 소스의 게이트 태그("ERROR (S22)" 등)가 미등록이면 실패
    → 새 게이트를 코드 등록 없이 추가하면 CI 에서 잡힌다
  - BUILD-SUMMARY-JSON: 마커 라인 뒤 JSON 1개, code = codes[0]
"""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import error_codes as ec  # noqa: E402
import figma_mcp_client as fmc  # noqa: E402

_CLIENT_SRC = open(os.path.join(os.path.dirname(__file__), "..",
                                "figma_mcp_client.py"), encoding="utf-8").read()


# ── classify_issue ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("issue,code", [
    ("ERROR (S22): config 재사용", "ERR_ARCHETYPE_REUSE"),
    ("ERROR (S23): _wireframeContent 누락", "ERR_WIREFRAME_CONTENT_MISSING"),
    ("ERROR (S24): _concept 누락", "ERR_CONCEPT_MISSING"),
    ("ERROR (S25): _designDirection 누락", "ERR_DESIGN_DIRECTION_MISSING"),
    ("ERROR (S26): _wireframeDivergence 누락", "ERR_WIREFRAME_DIVERGENCE_MISSING"),
    ("ERROR (novelty-gate): 직전 빌드와 너무 유사", "ERR_NOVELTY_DUPLICATE"),
    ("ERROR (R58-modal-no-home-sections): 홈 섹션 유입", "ERR_MODAL_HOME_SECTIONS"),
    ("ERROR (R60-tabs-ds-instance): raw tab frame", "ERR_RULE_LINT"),
    ("ERROR: root fill 이 bg-primary 아님", "ERR_VALIDATION"),
    ("", "ERR_VALIDATION"),
])
def test_classify_issue(issue, code):
    assert ec.classify_issue(issue) == code


def test_codes_for_issues_dedup_keeps_order():
    issues = [
        "ERROR (S23): a", "ERROR (S23): b",
        "ERROR (novelty-gate): c", "ERROR: d",
    ]
    assert ec.codes_for_issues(issues) == [
        "ERR_WIREFRAME_CONTENT_MISSING", "ERR_NOVELTY_DUPLICATE", "ERR_VALIDATION"]
    assert ec.codes_for_issues([]) == []
    assert ec.codes_for_issues(None) == []


# ── 레지스트리 불변식 ──────────────────────────────────────────────────────────

def test_registry_invariants():
    for code, desc in ec.ERROR_CODES.items():
        assert re.match(r"^ERR_[A-Z0-9_]+$", code), code
        assert desc
    for tag, code in ec.GATE_TAG_TO_CODE.items():
        assert code in ec.ERROR_CODES, "%s → 미등록 코드 %s" % (tag, code)


def test_drift_guard_source_gate_tags_registered():
    """figma_mcp_client.py 가 emit 하는 하드 게이트 태그가 전부 코드 매핑에 있어야 한다.
    새 게이트(S27 등)를 태그만 추가하고 error_codes 등록을 빼먹으면 여기서 실패."""
    tags = set(re.findall(r'"ERROR \((S\d+|novelty-[a-z]+)\)', _CLIENT_SRC))
    assert tags, "게이트 태그가 소스에서 안 잡힘 — 정규식/포맷 드리프트"
    unregistered = sorted(t for t in tags if t not in ec.GATE_TAG_TO_CODE)
    assert not unregistered, (
        "error_codes.GATE_TAG_TO_CODE 미등록 게이트 태그: %s — "
        "ERROR_CODES 에 코드 추가 + 태그 등록 필요 (append-only)" % unregistered)


def test_drift_guard_gate_exits_emit_summary():
    """sys.exit(2) 하드 게이트는 종료 직전 _emit_build_summary 를 호출해야 한다
    (기계 판독 계약). 새 게이트가 요약 없이 exit 하면 여기서 실패."""
    for m in re.finditer(r"\n(    .*sys\.exit\(2\))", _CLIENT_SRC):
        # exit 앞 1200자 안에 _emit_build_summary 호출이 있어야 함
        window = _CLIENT_SRC[max(0, m.start() - 1200):m.start()]
        assert "_emit_build_summary(" in window, (
            "sys.exit(2) 게이트가 BUILD-SUMMARY-JSON 없이 종료: ...%s" % m.group(1).strip())


# ── _emit_build_summary 출력 계약 ─────────────────────────────────────────────

def _parse_summary(out: str) -> dict:
    assert fmc._BUILD_SUMMARY_MARKER in out
    tail = out.split(fmc._BUILD_SUMMARY_MARKER)[-1]
    return json.loads(tail)


def test_emit_build_summary_blocked(capsys):
    fmc._emit_build_summary("blocked", codes=["ERR_PLANNING_GATE", "ERR_VALIDATION"],
                            issues=["ERROR (S23): x"], note="n",
                            required_actions=[{"type": "read", "paths": ["a.png"]}])
    doc = _parse_summary(capsys.readouterr().out)
    assert doc["type"] == "build-summary"
    assert doc["result"] == "blocked"
    assert doc["code"] == "ERR_PLANNING_GATE"  # code = codes[0]
    assert doc["codes"] == ["ERR_PLANNING_GATE", "ERR_VALIDATION"]
    assert doc["requiredActions"][0]["type"] == "read"


def test_emit_build_summary_success_minimal(capsys):
    fmc._emit_build_summary("success", root_id="1:2", warnings=["WARN: x"])
    doc = _parse_summary(capsys.readouterr().out)
    assert doc["result"] == "success"
    assert doc["rootId"] == "1:2"
    assert doc["warningCount"] == 1
    assert "codes" not in doc


def test_planning_gate_emits_summary_before_exit(monkeypatch, capsys):
    monkeypatch.delenv("IMIN_SKIP_PLANNING_GATE", raising=False)
    monkeypatch.setattr(fmc, "_planning_read_ok", lambda: (False, "테스트 사유"))
    with pytest.raises(SystemExit) as e:
        fmc._enforce_planning_read_gate()
    assert e.value.code == 2
    doc = _parse_summary(capsys.readouterr().out)
    assert doc["result"] == "blocked"
    assert doc["code"] == "ERR_PLANNING_GATE"
    kinds = {a["type"] for a in doc["requiredActions"]}
    assert {"run", "read"} <= kinds


def test_post_build_required_actions(monkeypatch, tmp_path):
    monkeypatch.setattr(fmc, "_LAST_REFERENCE_THUMBS", ["/tmp/ref1.png", "/tmp/ref2.png"])
    pend = tmp_path / "pending_qa_test.json"
    pend.write_text(json.dumps({
        "root_id": "9:9", "nodeIds": ["9:1", "9:2"],
        "checklist_path": "/tmp/cl.json"}), encoding="utf-8")
    monkeypatch.setattr(fmc, "_pending_selfverify_path", lambda: str(pend))
    actions = fmc._post_build_required_actions()
    by_type = {a["type"]: a for a in actions}
    assert by_type["read"]["paths"] == ["/tmp/ref1.png", "/tmp/ref2.png"]
    assert by_type["export_and_read"]["nodeIds"] == ["9:1", "9:2"]
    assert by_type["export_and_read"]["checklistPath"] == "/tmp/cl.json"
