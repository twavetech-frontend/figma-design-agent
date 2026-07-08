# -*- coding: utf-8 -*-
"""manifest 자기서술 — CLI_COMMANDS ↔ main() dispatch 드리프트 가드 (Astryx 패턴, 2026-07-08).

Astryx 계약: "명령을 추가했는데 manifest 에 설명하지 않으면 CI 실패."
main() 의 `cmd == "..."` 분기를 소스에서 스캔해 CLI_COMMANDS 와 집합 동일성을 강제한다.
"""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as fmc  # noqa: E402

_SRC = open(os.path.join(os.path.dirname(__file__), "..", "figma_mcp_client.py"),
            encoding="utf-8").read()


def _dispatch_commands() -> set:
    """main() 본문에서 dispatch 되는 명령 이름 스캔."""
    m = re.search(r"\ndef main\(\):(.*)", _SRC, re.S)
    assert m, "main() 을 소스에서 찾지 못함"
    return set(re.findall(r'cmd == "([a-z\-]+)"', m.group(1)))


def test_drift_guard_dispatch_matches_manifest():
    dispatched = _dispatch_commands()
    manifested = {c["name"] for c in fmc.CLI_COMMANDS}
    missing = sorted(dispatched - manifested)
    stale = sorted(manifested - dispatched)
    assert not missing, ("main() 에 있는데 CLI_COMMANDS(manifest) 미등록: %s — "
                         "명령 추가 시 manifest 에도 등록할 것" % missing)
    assert not stale, "CLI_COMMANDS 에 있는데 main() dispatch 없음(죽은 항목): %s" % stale


def test_manifest_entries_complete():
    names = [c["name"] for c in fmc.CLI_COMMANDS]
    assert len(names) == len(set(names)), "manifest 명령 이름 중복"
    for c in fmc.CLI_COMMANDS:
        assert c.get("name") and c.get("usage") and c.get("description"), c
        assert c["usage"].split()[0] == c["name"], "usage 는 명령 이름으로 시작: %s" % c["name"]


def test_cmd_manifest_json_is_pure(capsys):
    fmc.cmd_manifest(json_out=True)
    doc = json.loads(capsys.readouterr().out)
    assert doc["type"] == "manifest"
    assert doc["name"] == "figma_mcp_client"
    assert len(doc["commands"]) == len(fmc.CLI_COMMANDS)
    assert doc["responseTypes"]["build"] == ["build-summary"]
    assert doc["errorCodesModule"] == "scripts/error_codes.py"


def test_cmd_manifest_human(capsys):
    fmc.cmd_manifest(json_out=False)
    out = capsys.readouterr().out
    for c in fmc.CLI_COMMANDS:
        assert c["name"] in out


def test_json_supported_commands_marked():
    """--json 지원 명령은 manifest 에 json:true 로 표시돼야 한다 (소비자 계약)."""
    by_name = {c["name"]: c for c in fmc.CLI_COMMANDS}
    for name in ("doctor", "component", "search", "manifest"):
        assert by_name[name].get("json") is True, name


@pytest.mark.parametrize("name,expect", [
    ("Tab bar", "0faaa55563de4da617964ea93ba07f09bc1279f6"),
    ("Segmented_control", "_forceSegmented"),
])
def test_cmd_component_json(capsys, name, expect):
    fmc.cmd_component(name, json_out=True, full=True)
    out = capsys.readouterr().out
    doc = json.loads(out)
    assert doc["type"] == "component"
    assert expect in out


def test_cmd_component_not_found_exits(capsys):
    with pytest.raises(SystemExit) as e:
        fmc.cmd_component("없는컴포넌트xyz", json_out=True)
    assert e.value.code == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["error"] == "not found"
