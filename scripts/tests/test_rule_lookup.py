# -*- coding: utf-8 -*-
"""rule 명령 — CLAUDE.md 압축 인덱스의 retrieval (Phase 5 인덱스화, 2026-07-09).

계약:
- docs/design-rules-detail.md 를 룰 id 로 조회 (절대 규칙 / ### N. / 특수 섹션).
- CLAUDE.md 인덱스에서 참조하는 핵심 룰 id 들이 파싱돼야 한다 (인덱스↔상세 드리프트 가드).
- 미존재 id → exit 1.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as fmc  # noqa: E402

_CLAUDE_MD = os.path.join(os.path.dirname(__file__), "..", "..", "CLAUDE.md")


@pytest.fixture(scope="module")
def sections():
    secs, order = fmc._parse_rule_sections()
    assert len(order) >= 60, "룰 섹션 파싱이 급감 — 앵커 regex/문서 구조 확인"
    return secs


# CLAUDE.md 인덱스가 한 줄로 요약하는 핵심 룰들 — 상세 문서에서 반드시 펼쳐져야 한다
_CORE_IDS = [
    "0", "0-B", "0-D", "0-E", "0-E-3", "0-F", "0-G", "0-J", "0-K", "0-L", "0-M",
    "0-Q", "0-S", "0-U", "0-W", "1", "2", "2-B", "2-C", "2-D", "2-G", "2-G-4",
    "2-I", "8", "9", "10", "13", "14-B", "20", "CREATIVE", "POST-FIX",
    "TROUBLESHOOTING",
]


def test_core_rule_ids_present(sections):
    missing = [rid for rid in _CORE_IDS if rid not in sections]
    assert not missing, "인덱스 참조 룰이 상세 문서에서 파싱 안 됨: %s" % missing


@pytest.mark.parametrize("rid,expect", [
    ("0-J", "_underlineTabs"),
    ("0-J", "_forceSegmented"),
    ("2-G", "Action Button"),
    ("0-M", "0faaa55563de4da617964ea93ba07f09bc1279f6"),  # Tab bar 홈 variant key
    ("0-W", "SET:c9299ef0c3c7cc271850a048025a3c8d0e82b230"),  # Tool Bar set key
    ("2-C", "12 / 14 / 16 / 20 / 24 / 32 / 40 / 48"),
    ("POST-FIX", "spacing-"),
    ("TROUBLESHOOTING", "TEXT_STYLE_MAP"),
    ("CREATIVE", "_designDirection"),
])
def test_section_contains_key_content(sections, rid, expect):
    title, body = sections[rid]
    assert expect in "\n".join(body), "%s 섹션에 '%s' 없음" % (rid, expect)


def test_cmd_rule_output(capsys):
    fmc.cmd_rule("0-K")
    out = capsys.readouterr().out
    assert "절대 규칙 0-K" in out
    assert "variant" in out or "prop" in out


def test_cmd_rule_alias_13b_embedded(capsys):
    fmc.cmd_rule("13-B")  # 규칙 13 섹션에 내장 — alias 로 부모 섹션 반환
    out = capsys.readouterr().out
    assert "13-B" in out and "spacing-2xl" in out


def test_cmd_rule_alias_s24(capsys):
    fmc.cmd_rule("s24")  # 창의 게이트 alias → CREATIVE 섹션
    out = capsys.readouterr().out
    assert "_concept" in out


def test_cmd_rule_list(capsys):
    fmc.cmd_rule(None, list_all=True)
    out = capsys.readouterr().out
    assert "0-K" in out and "CREATIVE" in out


def test_cmd_rule_unknown_exits(capsys):
    with pytest.raises(SystemExit) as e:
        fmc.cmd_rule("존재안함xyz")
    assert e.value.code == 1


def test_claude_md_index_markers_and_pointers():
    """CLAUDE.md 는 인덱스 마커 + rule/component 조회 포인터를 유지해야 한다."""
    src = open(_CLAUDE_MD, encoding="utf-8").read()
    assert "<!-- DESIGN-RULES-INDEX:START -->" in src
    assert "<!-- DESIGN-RULES-INDEX:END -->" in src
    assert "rule <id>" in src
    assert "design-rules-detail.md" in src


def test_claude_md_is_compressed():
    """인덱스화 회귀 가드 — CLAUDE.md 가 다시 700줄 이상으로 부풀면 실패."""
    n = len(open(_CLAUDE_MD, encoding="utf-8").read().splitlines())
    assert n < 700, "CLAUDE.md %d줄 — 상세는 design-rules-detail.md 로 (Phase 5 인덱스 계약)" % n
