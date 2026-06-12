"""Step F frontend spec export — 폐기 확인 테스트 (정책 반전 회귀 방지).

Background:
    (구) 2026-05-27: cmd_build Step F 가 _export_frontend_spec 을 호출해 json/ 에
    frontend spec 을 추출해야 한다는 회귀 테스트였다.
    (현) 2026-06-05 사용자: "디자인 생성되면 json 폴더에 json 생성되게 하는것도 삭제해.
    생성할 필요없어졌어" → Step F·_export_frontend_spec **폐기**. CLAUDE.md '오래된 산출물
    자동 정리' 블록에 문서화. 이 테스트는 방향을 뒤집어 **부활 회귀**(누가 다시 json/ spec
    export 를 붙이는 것)를 검출한다.

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


def test_export_frontend_spec_removed():
    """_export_frontend_spec 은 2026-06-05 폐기 — 모듈에 없어야 한다."""
    assert not hasattr(figma_mcp_client, "_export_frontend_spec"), \
        "_export_frontend_spec 부활 — 2026-06-05 사용자 폐기 지시 위반 (json/ spec 생성 금지)"


def test_cmd_build_does_not_call_export_frontend_spec():
    """cmd_build 가 _export_frontend_spec 을 호출하지 않아야 한다 (Step F 폐기).

    주석에 함수명이 남는 건 허용 — 주석/문자열 아닌 '호출' 라인만 검출."""
    src = inspect.getsource(figma_mcp_client.cmd_build)
    calls = [ln for ln in src.split("\n")
             if "_export_frontend_spec" in ln.split("#", 1)[0]]
    assert not calls, \
        f"cmd_build 에 _export_frontend_spec 호출 부활 — 2026-06-05 폐기 정책 위반: {calls}"
