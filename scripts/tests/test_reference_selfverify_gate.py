# -*- coding: utf-8 -*-
"""레퍼런스 Read 게이트 / self-verify 게이트 — 2026-06-11.

fable 등 모델이 레퍼런스 PNG Read·self-verify 를 조용히 건너뛰는 것을 코드로 차단하는
하드 게이트의 통과/차단/폴백/우회 분기를 검증한다. (통독 게이트와 동일 철학.)
"""
import os
import sys
import json
import importlib.util
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as fc


@pytest.fixture
def gate(tmp_path, monkeypatch):
    """게이트 디렉토리 + 현재 세션을 격리하고, bypass 환경변수를 제거한다."""
    monkeypatch.setattr(fc, "_planning_gate_dir", lambda: str(tmp_path))
    monkeypatch.setattr(fc, "_current_claude_session", lambda: "testsid")
    for k in ("IMIN_SKIP_REFERENCE_GATE", "IMIN_SKIP_SELFVERIFY_GATE"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


def _write(tmp, name, obj):
    with open(os.path.join(str(tmp), name), "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


# ── 레퍼런스 Read 게이트 ──────────────────────────────────────────────
def test_ref_gate_bypass(gate, monkeypatch):
    monkeypatch.setenv("IMIN_SKIP_REFERENCE_GATE", "1")
    monkeypatch.setattr(fc, "_LAST_REFERENCE_THUMBS", ["/x/ref_thumbnails/a.png"])
    fc._enforce_reference_read_gate()  # 우회 → exit 없음


def test_ref_gate_no_thumbs_passes(gate, monkeypatch):
    monkeypatch.setattr(fc, "_LAST_REFERENCE_THUMBS", [])
    fc._enforce_reference_read_gate()  # 검색 결과 없음 → 무관, 통과


def test_ref_gate_hook_inactive_passes(gate, monkeypatch):
    monkeypatch.setattr(fc, "_current_claude_session", lambda: None)
    monkeypatch.setattr(fc, "_LAST_REFERENCE_THUMBS", ["/x/ref_thumbnails/a.png"])
    fc._enforce_reference_read_gate()  # 훅 비활성 → 폴백 통과


def test_ref_gate_all_read_passes(gate, monkeypatch):
    _write(gate, "ref_testsid.json", {"read": ["a.png", "b.png"]})
    monkeypatch.setattr(fc, "_LAST_REFERENCE_THUMBS",
                        ["/x/ref_thumbnails/a.png", "/y/ref_thumbnails/b.png"])
    fc._enforce_reference_read_gate()  # 전부 Read → 통과


def test_ref_gate_missing_blocks(gate, monkeypatch):
    _write(gate, "ref_testsid.json", {"read": ["a.png"]})  # b.png 미Read
    monkeypatch.setattr(fc, "_LAST_REFERENCE_THUMBS",
                        ["/x/ref_thumbnails/a.png", "/y/ref_thumbnails/b.png"])
    with pytest.raises(SystemExit) as e:
        fc._enforce_reference_read_gate()
    assert e.value.code == 2


# ── self-verify 게이트 ────────────────────────────────────────────────
def test_sv_gate_no_pending_passes(gate):
    fc._enforce_selfverify_gate("build")  # pending 없음 → 통과


def test_sv_gate_bypass(gate, monkeypatch):
    monkeypatch.setenv("IMIN_SKIP_SELFVERIFY_GATE", "1")
    _write(gate, "pending_qa_testsid.json",
           {"root_id": "r", "nodeIds": ["1:1"], "checklist_path": ""})
    fc._enforce_selfverify_gate("build")  # 우회


def test_sv_gate_hook_inactive_passes(gate, monkeypatch):
    monkeypatch.setattr(fc, "_current_claude_session", lambda: None)
    fc._enforce_selfverify_gate("build")  # 훅 비활성 → 통과


def test_sv_gate_all_exported_passes_and_clears(gate):
    cl = os.path.join(str(gate), "cl.json")
    json.dump({"checklist": [{"status": "PASS"}]}, open(cl, "w"))
    _write(gate, "pending_qa_testsid.json",
           {"root_id": "r", "nodeIds": ["1:1", "1:2"], "checklist_path": cl})
    _write(gate, "qa_testsid.json", {"exported": ["1:1", "1:2"]})
    fc._enforce_selfverify_gate("build")  # 전부 재export → 통과
    assert not os.path.exists(os.path.join(str(gate), "pending_qa_testsid.json"))  # 마커 삭제


def test_sv_gate_missing_export_blocks(gate):
    _write(gate, "pending_qa_testsid.json",
           {"root_id": "r", "nodeIds": ["1:1", "1:2"], "checklist_path": ""})
    _write(gate, "qa_testsid.json", {"exported": ["1:1"]})  # 1:2 미export
    with pytest.raises(SystemExit) as e:
        fc._enforce_selfverify_gate("build")
    assert e.value.code == 2


def test_checklist_unfilled_count(gate):
    cl = os.path.join(str(gate), "cl.json")
    json.dump({"checklist": [{"status": "PASS"}, {"status": "FILL_IN"}, {"status": ""}]},
              open(cl, "w"))
    assert fc._checklist_unfilled_count(cl) == 2          # FILL_IN + 빈값
    assert fc._checklist_unfilled_count("/nonexistent") == -1


def test_record_pending_roundtrip(gate):
    cl = "/tmp/x.json"
    fc._record_pending_selfverify("9:9", [{"nodeId": "1:1"}, {"label": "x"}], cl)
    p = os.path.join(str(gate), "pending_qa_testsid.json")
    assert os.path.exists(p)
    obj = json.load(open(p))
    assert obj["root_id"] == "9:9" and obj["nodeIds"] == ["1:1"]  # nodeId 없는 항목 제외


# ── hook 헬퍼 (planning_read_hook) ────────────────────────────────────
@pytest.fixture
def hook(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "planning_read_hook",
        os.path.join(os.path.dirname(__file__), "..", "hooks", "planning_read_hook.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "_GATE_DIR", str(tmp_path))
    return mod, tmp_path


def test_hook_ref_thumb_read_records(hook):
    mod, tmp = hook
    mod._handle_ref_thumb_read({
        "session_id": "sid1",
        "tool_input": {"file_path": "/repo/scripts/ref_thumbnails/abc.png"},
    })
    obj = json.load(open(os.path.join(str(tmp), "ref_sid1.json")))
    assert obj["read"] == ["abc.png"]


def test_hook_ref_thumb_ignores_non_thumb(hook):
    mod, tmp = hook
    mod._handle_ref_thumb_read({
        "session_id": "sid1",
        "tool_input": {"file_path": "/repo/scripts/_planning_digest.txt"},
    })
    assert not os.path.exists(os.path.join(str(tmp), "ref_sid1.json"))


def test_hook_post_export_records_nodeid(hook):
    mod, tmp = hook
    mod._handle_post_export({"session_id": "sid1", "tool_input": {"nodeId": "12:34"}})
    mod._handle_post_export({"session_id": "sid1", "tool_input": {"nodeId": "12:35"}})
    obj = json.load(open(os.path.join(str(tmp), "qa_sid1.json")))
    assert set(obj["exported"]) == {"12:34", "12:35"}  # 합집합 누적
