"""Regression tests for Step F frontend spec export wiring.

Background:
    2026-05-27 회귀: 2026-05-21 이후 모든 빌드에서 frontend spec JSON 추출이 안 됨.
    원인: 메모리 `feedback_frontend_json_export` 는 "cmd_build Step F 가 자동 호출"
    이라 박혀있었지만 실제 `cmd_build` 함수에는 호출 코드가 없었음. 메모리/코드
    sync 깨짐.

    Fix: `figma_mcp_client.py:_export_frontend_spec` 함수 추가 + `cmd_build` 끝부분에
    호출 박음.

    이 테스트는 코드에서 그 호출이 빠지면 즉시 검출 — 누군가 refactor 중 또
    빼버리면 pytest 단계에서 빨간 줄.

Run:
    python3 -m pytest scripts/tests/test_frontend_spec_export.py -v
"""
from __future__ import annotations

import os
import sys
import inspect

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import figma_mcp_client  # noqa: E402


def test_export_frontend_spec_function_exists():
    """_export_frontend_spec 함수가 모듈에 존재해야 한다."""
    assert hasattr(figma_mcp_client, "_export_frontend_spec"), \
        "figma_mcp_client._export_frontend_spec 누락 — Step F 회귀"
    assert callable(figma_mcp_client._export_frontend_spec)


def test_cmd_build_calls_export_frontend_spec():
    """🔴 회귀 방지 — cmd_build 가 _export_frontend_spec 을 호출해야 한다.

    누가 cmd_build 에서 Step F 호출을 빼면 5/21~5/27 회귀가 재발.
    """
    src = inspect.getsource(figma_mcp_client.cmd_build)
    assert "_export_frontend_spec" in src, \
        "cmd_build 에 _export_frontend_spec 호출 없음 — Step F 회귀 (메모리는 박혀있어도 코드에 없음)"


def test_cmd_build_step_f_log_line():
    """빌드 로그에 '[Step F]' 출력 라인 존재 — 사용자가 빌드 직후 시각 확인 가능."""
    src = inspect.getsource(figma_mcp_client.cmd_build)
    assert "Step F" in src, "Step F 로그 라인 누락 — 빌드 시 자동 추출 확인 불가"


def test_gen_frontend_spec_script_exists():
    """scripts/gen_frontend_spec.py 가 존재해야 _export_frontend_spec 이 작동."""
    project_root = os.path.dirname(_SCRIPTS) if os.path.basename(_SCRIPTS) == "scripts" \
        else _SCRIPTS
    gen_script = os.path.join(_SCRIPTS, "gen_frontend_spec.py")
    assert os.path.exists(gen_script), \
        f"gen_frontend_spec.py 누락: {gen_script} — Step F 가 호출할 스크립트 없음"


def test_export_function_uses_subprocess():
    """_export_frontend_spec 은 subprocess 로 gen_frontend_spec.py 호출.

    Inline import 가 아닌 subprocess 호출 보장 (스크립트 자체가 sys.argv 기반).
    """
    src = inspect.getsource(figma_mcp_client._export_frontend_spec)
    assert "subprocess" in src, "_export_frontend_spec 이 subprocess 안 씀 — wiring 회귀"
    assert "gen_frontend_spec" in src, "_export_frontend_spec 이 gen_frontend_spec 안 부름"


def test_export_function_creates_json_dir():
    """json/ 디렉토리 자동 생성 보장 (없으면 makedirs)."""
    src = inspect.getsource(figma_mcp_client._export_frontend_spec)
    assert "makedirs" in src or "mkdir" in src, \
        "_export_frontend_spec 이 json/ 디렉토리 보장 안 함 — 첫 빌드 실패 가능"


def test_export_function_handles_failure_gracefully():
    """추출 실패해도 빌드 자체는 계속돼야 함 (except 또는 try)."""
    src = inspect.getsource(figma_mcp_client.cmd_build)
    # cmd_build 가 _export_frontend_spec 호출 시 try/except 로 감싸는지
    assert "_export_frontend_spec" in src
    # Step F 호출이 try 블록 안에 있어야 빌드 영향 없음
    lines = src.split("\n")
    in_try = False
    found_call_in_try = False
    for ln in lines:
        if "try:" in ln:
            in_try = True
        if "_export_frontend_spec" in ln and "def " not in ln:
            if in_try:
                found_call_in_try = True
        if ln.strip().startswith("except"):
            in_try = False
    assert found_call_in_try, "_export_frontend_spec 호출이 try 블록 밖 — 실패 시 빌드 abort 가능"
