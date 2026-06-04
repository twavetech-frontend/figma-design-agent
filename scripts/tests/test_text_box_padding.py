# -*- coding: utf-8 -*-
"""텍스트 박스 상하 여백 강제 회귀 테스트 (2026-06-04).

사용자 보고: 라운드 필 박스 안 라벨+값 텍스트('완료한 스테이지 / 3,000개')가 세로 패딩
0 으로 박스 모서리에 딱 붙음. batch_build 가 HORIZONTAL row 안 FILL 박스의 세로 패딩을
떨어뜨려서 발생 → _enforce_text_box_padding_live 의 판별(_text_box_needs_padding)이
이런 박스를 잡고 정상 박스는 건드리지 않는지 검증.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import figma_mcp_client as fc  # noqa: E402

_needs = fc._text_box_needs_padding


def _box(pt=0, pb=0, isp=8, cr=10, fill=True, ntext=2, mode="VERTICAL"):
    n = {"type": "FRAME", "layoutMode": mode, "cornerRadius": cr,
         "paddingTop": pt, "paddingBottom": pb, "itemSpacing": isp,
         "children": [{"type": "TEXT"} for _ in range(ntext)]}
    n["fills"] = [{"type": "SOLID", "visible": True}] if fill else []
    return n


def test_zero_padding_box_needs_fix():
    assert _needs(_box(pt=0, pb=0)) is True


def test_adequate_padding_box_ok():
    assert _needs(_box(pt=16, pb=16, isp=8)) is False


def test_tight_itemspacing_needs_fix():
    assert _needs(_box(pt=14, pb=14, isp=2)) is True


def test_transparent_text_group_skipped():
    # fill 없음(투명 텍스트 그룹) → 박스 아님, 건드리지 않음
    assert _needs(_box(pt=0, pb=0, fill=False)) is False


def test_no_corner_radius_skipped():
    # cornerRadius 0 (네모 텍스트 블록) → 박스 아님
    assert _needs(_box(pt=0, pb=0, cr=0)) is False


def test_single_text_skipped():
    # TEXT 1개 → 라벨+값 쌍 아님
    assert _needs(_box(pt=0, pb=0, ntext=1)) is False


def test_horizontal_frame_skipped():
    assert _needs(_box(pt=0, pb=0, mode="HORIZONTAL")) is False


def test_padding_none_treated_as_zero():
    # get_nodes_info 가 padding 을 None 으로 줄 때(=0) 도 잡아야 함
    n = _box(pt=0, pb=0)
    n["paddingTop"] = None
    n["paddingBottom"] = None
    assert _needs(n) is True
