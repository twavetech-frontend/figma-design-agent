# -*- coding: utf-8 -*-
"""CTA 유도 caption = text-secondary 회귀 테스트 (2026-06-08 사용자).

사용자 명시: "'함께 모은 목돈, 다시 모아볼까요?' 같은 텍스트는 중요도에서 최상은 아니거든.
그러면 컬러를 secondary 를 써야 하지 않겠어?" — CTA 를 유도하는 권유 문구는 hero/타이틀 같은
최상위 중요도가 아니므로 text-secondary. text-primary 는 최상위 중요도에만.

검증: CTA(라벨 있는 액션 버튼) 바로 앞 형제 TEXT 가 작은 비-Bold primary 면 secondary 로 교정.
hero(큰/Bold)·CTA 앞 아님·opt-out 은 primary 유지.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import figma_mcp_client as fc  # noqa: E402

P = "$token(text-primary)"
S = "$token(text-secondary)"


def _T(text, size, style, color, **kw):
    n = {"name": text, "type": "text", "text": text, "fontSize": size,
         "fontName": {"family": "Pretendard", "style": style}, "fontColor": color}
    n.update(kw)
    return n


def _cta(name="목돈 모으러 가기"):
    return {"name": name, "type": "instance", "componentKey": "k", "_instanceText": name}


def _wrap(*kids):
    return {"children": [{"name": "Sec", "type": "frame", "children": list(kids)}]}


def _first_text(bp):
    return bp["children"][0]["children"][0]


def test_caption_before_cta_to_secondary():
    bp = _wrap(_T("함께 모은 목돈, 다시 모아볼까요?", 14, "SemiBold", P), _cta())
    fc._enforce_cta_caption_secondary(bp)
    assert _first_text(bp)["fontColor"] == S


def test_medium_caption_before_cta_to_secondary():
    bp = _wrap(_T("지금 시작해 보세요", 16, "Medium", P), _cta("시작하기"))
    fc._enforce_cta_caption_secondary(bp)
    assert _first_text(bp)["fontColor"] == S


def test_hero_before_cta_kept_primary():
    # 큰 Bold hero 는 최상위 중요도 → primary 유지
    bp = _wrap(_T("총 1,300만원 모으기", 24, "Bold", P), _cta("참여하기"))
    fc._enforce_cta_caption_secondary(bp)
    assert _first_text(bp)["fontColor"] == P


def test_bold_small_before_cta_kept_primary():
    # 작아도 Bold 면 강조 의도 → 유지
    bp = _wrap(_T("꼭 확인하세요", 15, "Bold", P), _cta("확인"))
    fc._enforce_cta_caption_secondary(bp)
    assert _first_text(bp)["fontColor"] == P


def test_optout_marker_kept_primary():
    bp = _wrap(_T("중요 안내", 14, "SemiBold", P, _keepTextColor=True), _cta())
    fc._enforce_cta_caption_secondary(bp)
    assert _first_text(bp)["fontColor"] == P


def test_not_before_cta_kept_primary():
    bp = _wrap(_T("본문 A", 14, "Medium", P), _T("본문 B", 14, "Medium", P))
    fc._enforce_cta_caption_secondary(bp)
    assert _first_text(bp)["fontColor"] == P


def test_already_secondary_noop():
    bp = _wrap(_T("권유", 14, "SemiBold", S), _cta())
    fc._enforce_cta_caption_secondary(bp)
    assert _first_text(bp)["fontColor"] == S


def test_raw_button_frame_also_triggers():
    bp = _wrap(_T("권유 문구", 14, "SemiBold", P),
               {"name": "Submit Button", "type": "frame", "children": [_T("제출", 16, "Bold", "$token(fg-light)")]})
    fc._enforce_cta_caption_secondary(bp)
    assert _first_text(bp)["fontColor"] == S


# ── 2026-09-23 회귀: Input field 앞 필드 라벨이 caption 으로 오인돼 secondary 가 되던 사고 ─────────────
def _input(name="Detail Input"):
    return {"name": name, "type": "instance", "componentKey": "k-input", "_instanceText": "상황을 자세히 적어 주세요",
            "instanceProperties": {"Size": "md", "State": "Placeholder"}}


def test_input_field_with_placeholder_is_not_cta():
    assert fc._bp_is_cta(_input()) is False
    assert fc._bp_is_cta(_input("Search Input")) is False
    assert fc._bp_is_cta(_cta()) is True


def test_field_label_before_input_keeps_primary():
    bp = _wrap(_T("상세 내용", 14, "SemiBold", P, name="Field Label"), _input())
    fc._enforce_cta_caption_secondary(bp)
    assert _first_text(bp)["fontColor"] == P


def test_label_named_text_before_real_cta_keeps_primary():
    bp = _wrap(_T("금액", 14, "Regular", P, name="KV Label"), _cta())
    fc._enforce_cta_caption_secondary(bp)
    assert _first_text(bp)["fontColor"] == P
    bp = _wrap(_T("다시 모아볼까요?", 14, "Regular", P, name="Caption"), _cta())
    fc._enforce_cta_caption_secondary(bp)
    assert _first_text(bp)["fontColor"] == S


def test_qa_same_name_text_color_flags_split(capsys):
    bp = {"children": [
        {"name": "A", "type": "frame", "children": [_T("이의신청 사유", 14, "SemiBold", P, name="Field Label")]},
        {"name": "B", "type": "frame", "children": [_T("상세 내용", 14, "SemiBold", S, name="Field Label")]},
    ]}
    assert fc._qa_same_name_text_color(bp) == 1
    assert "Field Label" in capsys.readouterr().out
    bp["children"][1]["children"][0]["fontColor"] = P
    assert fc._qa_same_name_text_color(bp) == 0
