"""규칙 0-G-3 (2026-09-11) — 현재 페이지에 같은 화면이 있으면 검토/결정 선언 없이는 빌드 차단.
사용자 지적: "현재 페이지에 같은 디자인이 존재하는데 다른 디자인들을 검색하지 않고 처음부터 다시 디자인한거야"."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import figma_mcp_client as fc  # noqa: E402


def _index(tmp_path):
    idx = {"screens": [
        {"id": "1:1", "name": "내 스케줄(입금_추가입금)", "section": "5. 나 > 정산관리"},
        {"id": "1:2", "name": "목돈지원금쿠폰_1만원권_DS", "section": "5. 나 > 쿠폰"},
        {"id": "1:3", "name": "쿠폰_DS", "section": "5. 나 > 쿠폰"},
        {"id": "1:4", "name": "홈", "section": "1. 홈"}],
        "sections": [], "assets": [],
        "texts": [{"id": "t1", "chars": "목돈지원금 쿠폰", "screen": "쿠폰_DS"}]}
    p = tmp_path / "_figma_index_test.json"
    p.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    return str(p)


def _bp(nav_title, **root):
    bp = {"name": "imin_x_20260911", "type": "frame", "children": [
        {"name": "NavBar", "type": "instance", "componentKey": "SET:x", "_navTitle": nav_title}]}
    bp.update(root)
    return bp


def test_keys_come_from_nav_title_and_wireframe_content():
    bp = _bp("내 스케줄", _wireframeContent={"sheetTitle": "목돈지원금 쿠폰"}, _existingSearchKeys=["쿠폰"])
    assert fc._existing_search_keys(bp) == ["내 스케줄", "목돈지원금 쿠폰", "쿠폰"]


def test_matches_by_name_and_by_text(tmp_path):
    keys, m = fc._existing_design_matches(_bp("내 스케줄"), _index(tmp_path))
    assert [x["id"] for x in m] == ["1:1"] and m[0]["via"] == "name"
    keys, m = fc._existing_design_matches(_bp("목돈지원금 쿠폰"), _index(tmp_path))
    # 이름 부분 일치(목돈지원금쿠폰_1만원권_DS) + TEXT 일치(쿠폰_DS) 둘 다 후보
    assert {x["id"] for x in m} == {"1:2", "1:3"} and {x["via"] for x in m} == {"name", "text"}


def test_gate_blocks_without_review_and_passes_with_declaration(tmp_path, capsys):
    idx = _index(tmp_path)
    assert fc._enforce_existing_design_gate(_bp("내 스케줄"), idx, exit_on_block=False) is False
    with pytest.raises(SystemExit):
        fc._enforce_existing_design_gate(_bp("내 스케줄"), idx)
    out = capsys.readouterr().out
    assert "ERR_EXISTING_DESIGN_UNREVIEWED" in out and "1:1" in out
    ok = fc._enforce_existing_design_gate(
        _bp("내 스케줄", _existingReviewed=["1:1"], _existingDecision={"mode": "clone", "reason": "기존 벡터 본을 변환 트랙으로 DS 화"}), idx)
    assert ok is True


def test_gate_rejects_wrong_id_or_thin_reason(tmp_path):
    idx = _index(tmp_path)
    assert fc._enforce_existing_design_gate(_bp("내 스케줄", _existingReviewed=["9:9"], _existingDecision={"mode": "clone", "reason": "충분히 긴 사유입니다"}), idx, exit_on_block=False) is False
    assert fc._enforce_existing_design_gate(_bp("내 스케줄", _existingReviewed=["1:1"], _existingDecision={"mode": "clone", "reason": "짧음"}), idx, exit_on_block=False) is False


def test_gate_passes_when_no_match_or_skipped(tmp_path):
    idx = _index(tmp_path)
    assert fc._enforce_existing_design_gate(_bp("존재하지 않는 화면"), idx) is True
    assert fc._enforce_existing_design_gate(_bp("내 스케줄", _existingReviewedSkipped="신규 기능 — 기존 본 없음 확인"), idx) is True


def test_error_code_registered():
    import error_codes as ec
    assert "ERR_EXISTING_DESIGN_UNREVIEWED" in ec.ERROR_CODES
    assert ec.classify_issue("ERROR (0-G-3): x") == "ERR_EXISTING_DESIGN_UNREVIEWED"


def test_convert_track_is_exempt(tmp_path, monkeypatch):
    """변환 트랙(convert_screen/rebuild_track → build)은 소스 노드가 곧 기존 디자인 — 게이트 면제."""
    monkeypatch.setenv("IMIN_CONVERT_TRACK", "1")
    assert fc._enforce_existing_design_gate(_bp("내 스케줄"), _index(tmp_path)) is True
