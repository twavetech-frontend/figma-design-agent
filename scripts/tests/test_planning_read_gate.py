# -*- coding: utf-8 -*-
"""기획 통독 강제 게이트 회귀 테스트 (2026-06-04 사용자).

매 디자인 생성 시 서비스 맥락을 충분히 이해한 상태를 시스템이 보장 — 통독 안 하면 빌드 차단.
cheat 방지 핵심: 통독 확인 토큰이 digest **맨 끝**에만 있어, 끝까지 읽어야만 ack 가능.
여기서는 build_digest 의 토큰 생성(결정적 + 끝 위치)을 검증.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import importlib.util  # noqa: E402

_RP = os.path.join(os.path.dirname(__file__), "..", "read_planning_docs.py")
_spec = importlib.util.spec_from_file_location("read_planning_docs", _RP)
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)


def test_build_digest_returns_token():
    digest, count, token = rp.build_digest()
    if count == 0:
        # 기획 폴더 없는 환경 — 게이트는 통과(무관). 토큰 빈 값.
        assert digest == "" and token == ""
        return
    assert count > 0
    assert isinstance(token, str) and len(token) == 12


def test_token_at_end_of_digest():
    digest, count, token = rp.build_digest()
    if count == 0:
        return
    # 토큰은 digest 맨 끝 footer 에만 존재 — 끝까지 읽어야 얻는다
    assert token in digest
    assert digest.index(token) > len(digest) * 0.95  # 마지막 5% 안
    assert "통독 확인 토큰" in digest[-600:]


def test_token_deterministic():
    d1, _c1, t1 = rp.build_digest()
    d2, _c2, t2 = rp.build_digest()
    assert t1 == t2  # 같은 내용 → 같은 토큰 (변경 시에만 토큰 바뀜)


def test_fingerprint_shape():
    fp = rp.fingerprint()
    assert "count" in fp and "hash" in fp
    assert isinstance(fp["hash"], str)


def test_gate_helpers_exist():
    import figma_mcp_client as fc
    assert callable(fc._enforce_planning_read_gate)
    assert callable(fc._planning_read_ok)
    assert callable(fc.cmd_ack_planning)
    assert callable(fc.cmd_learn_planning)


# ── Read 커버리지 훅 (2026-06-05) ────────────────────────────────────────────
_HK = os.path.join(os.path.dirname(__file__), "..", "hooks", "planning_read_hook.py")
_hk_spec = importlib.util.spec_from_file_location("planning_read_hook", _HK)
hk = importlib.util.module_from_spec(_hk_spec)
_hk_spec.loader.exec_module(hk)


def test_merge_ranges():
    assert hk._merge_ranges([[1, 5], [6, 10], [3, 4]]) == [[1, 10]]
    assert hk._merge_ranges([[1, 5], [20, 25]]) == [[1, 5], [20, 25]]
    assert hk._merge_ranges([]) == []


def test_coverage_complete_math():
    # 전체 100줄: 1~100 커버 → 완독
    assert hk._is_complete([[1, 100]], 100)
    # 끝(마지막 8줄) 미도달 → 미완독
    assert not hk._is_complete([[1, 90]], 100)
    # 시작 누락 → 미완독
    assert not hk._is_complete([[5, 100]], 100)
    # 중간 큰 공백으로 97% 미만 → 미완독
    assert not hk._is_complete([[1, 3], [98, 100]], 100)


def test_extract_covered_from_truncation_reminder():
    text = ("[Truncated: PARTIAL view — showing lines 1-705 of 2486 total "
            "(74855 tokens, cap 25000). Call Read with offset=706 ...]")
    ranges, total = hk._extract_covered(text, 2486)
    assert total == 2486
    assert ranges == [[1, 705]]


def test_extract_covered_from_catn_prefixes():
    text = "  2400\t약정철회\n  2401\t순번이전\n  2486\t통독 확인 토큰: abc"
    ranges, _total = hk._extract_covered(text, 2486)
    # 본 줄 번호의 min~max 범위
    assert ranges and ranges[0][0] == 2400 and ranges[-1][1] == 2486


def _digest_lines():
    p = os.path.join(os.path.dirname(__file__), "..", "_planning_digest.txt")
    if not os.path.exists(p):
        return 0
    with open(p, "rb") as fh:
        return sum(1 for _ in fh)


def test_full_read_session_passes_gate(tmp_path):
    """현재 세션이 digest 전체를 Read → 세션 커버리지 완독 → 게이트 통과."""
    import figma_mcp_client as fc
    total = _digest_lines()
    if total == 0:
        return  # digest 없는 환경 — 스킵
    sid = "pytest-full-%d" % os.getpid()
    gate_dir = hk._GATE_DIR
    cur_path = os.path.join(gate_dir, "current_session")
    cov_path = os.path.join(gate_dir, "cov_%s.json" % sid)
    # 기존 current_session 보존
    saved = None
    if os.path.exists(cur_path):
        with open(cur_path, encoding="utf-8") as fh:
            saved = fh.read()
    try:
        # 페이지별 잘림 리마인더로 전체 Read 시뮬레이션
        pages, off = [], 1
        page = 705
        while off <= total:
            end = min(off + page - 1, total)
            pages.append((off, end))
            off = end + 1
        for a, b in pages:
            reminder = "showing lines %d-%d of %d total" % (a, b, total)
            hk._handle_post_read({
                "session_id": sid,
                "tool_input": {"file_path": "scripts/_planning_digest.txt",
                               "offset": a, "limit": b - a + 1},
                "tool_response": reminder,
            })
        assert os.path.exists(cov_path)
        # 현재 세션을 테스트 sid 로 지정 후 게이트 확인
        os.makedirs(gate_dir, exist_ok=True)
        with open(cur_path, "w", encoding="utf-8") as fh:
            fh.write(sid)
        active, ok, _r = fc._planning_session_read_ok()
        assert active and ok
    finally:
        if os.path.exists(cov_path):
            os.remove(cov_path)
        if saved is None:
            if os.path.exists(cur_path):
                os.remove(cur_path)
        else:
            with open(cur_path, "w", encoding="utf-8") as fh:
                fh.write(saved)


def test_partial_read_session_blocks_gate():
    """앞 페이지만 Read → 세션 커버리지 미완독 → 게이트 차단."""
    import figma_mcp_client as fc
    total = _digest_lines()
    if total == 0:
        return
    sid = "pytest-partial-%d" % os.getpid()
    gate_dir = hk._GATE_DIR
    cur_path = os.path.join(gate_dir, "current_session")
    cov_path = os.path.join(gate_dir, "cov_%s.json" % sid)
    saved = None
    if os.path.exists(cur_path):
        with open(cur_path, encoding="utf-8") as fh:
            saved = fh.read()
    try:
        hk._handle_post_read({
            "session_id": sid,
            "tool_input": {"file_path": "scripts/_planning_digest.txt", "offset": 1, "limit": 705},
            "tool_response": "showing lines 1-705 of %d total" % total,
        })
        os.makedirs(gate_dir, exist_ok=True)
        with open(cur_path, "w", encoding="utf-8") as fh:
            fh.write(sid)
        active, ok, _r = fc._planning_session_read_ok()
        assert active and not ok
    finally:
        if os.path.exists(cov_path):
            os.remove(cov_path)
        if saved is None:
            if os.path.exists(cur_path):
                os.remove(cur_path)
        else:
            with open(cur_path, "w", encoding="utf-8") as fh:
                fh.write(saved)
