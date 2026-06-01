# -*- coding: utf-8 -*-
"""R23 button-vs-badge 역할 기반 판별 회귀 테스트 (2026-06-01).

사용자 보고: 리스트 상단 badge 가 직사각형이라 button 컴포넌트로 오스왑됨.
→ detect_ds_role_structural 이 라벨 의미(액션 vs 상태/카테고리/카운트) + 위치
(리스트 내 leading 소형)로 button/badge 를 구분하는지 검증.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from design_rules.ds_catalog import detect_ds_role_structural  # noqa: E402


def _pill(name, label, *, cr=8, fill="$token(bg-secondary)", pl=8, pr=8, pt=4, pb=4,
          w=None, h=None, mode="HORIZONTAL"):
    n = {"name": name, "type": "frame", "cornerRadius": cr, "fill": fill,
         "autoLayout": {"layoutMode": mode, "paddingLeft": pl, "paddingRight": pr,
                        "paddingTop": pt, "paddingBottom": pb},
         "children": [{"name": "t", "type": "text", "characters": label}]}
    if w is not None:
        n["width"] = w
    if h is not None:
        n["height"] = h
    return n


def _row_with(pill, title="제목 텍스트"):
    """pill 을 leading 자식으로, 옆에 title 텍스트가 있는 리스트 행."""
    return {"name": "List Item", "type": "frame",
            "autoLayout": {"layoutMode": "HORIZONTAL"},
            "children": [pill, {"name": "title", "type": "text", "characters": title}]}


def role_of(node, parent=None):
    r = detect_ds_role_structural(node, parent)
    return None if not r else (r[0], r[3])  # (role, confident)


def _is_badge(res):
    return res is not None and res[0].startswith("Badge")


def _is_button(res):
    return res is not None and res[0].startswith("Action Button")


# ── 핵심 회귀 케이스: 리스트 상단 직사각형 badge ──────────────────────────
def test_rectangular_status_badge_in_list_is_badge():
    pill = _pill("Tag", "진행중", cr=4, pt=4, pb=4)  # vp=8 (예전엔 button 으로 오인)
    parent = _row_with(pill)
    res = role_of(pill, parent)
    assert _is_badge(res), f"리스트 상단 '진행중' 태그는 badge 여야 함, got {res}"
    assert res[1] is True, "역할 확정 badge 는 confident=True (auto-swap)"


def test_category_tag_is_badge():
    for word in ("공지", "이벤트", "추천", "신규", "광고"):
        pill = _pill("Tag", word, cr=4)
        assert _is_badge(role_of(pill, _row_with(pill))), f"'{word}' 는 badge 여야 함"


def test_count_pill_is_badge():
    # 주의: "+6" 처럼 len<=2 + 첫 글자 비-alnum 라벨은 _is_label_only_children 의
    # glyph 필터가 화살표로 보고 제외 → 카운트 badge 미검출(기존 한계). 멀티문자 카운트로 검증.
    for word in ("13회", "1회차", "3개", "D-7", "6명"):
        pill = _pill("Count", word, cr=999)
        assert _is_badge(role_of(pill)), f"'{word}' 카운트는 badge 여야 함"


def test_square_badge_without_radius_still_badge_when_worded():
    # cornerRadius 0 (직사각형) 이라도 라벨이 badge 단어면 badge
    pill = _pill("Tag", "미납", cr=0)
    assert _is_badge(role_of(pill, _row_with(pill))), "직사각형 '미납' 도 badge"


def test_leading_small_unworded_pill_in_list_is_badge():
    # 라벨이 사전에 없는 단어라도, 리스트 행의 leading 소형이면 badge 로 판정
    pill = _pill("Tag", "한정판", cr=6, h=22)
    res = role_of(pill, _row_with(pill))
    assert _is_badge(res), f"leading 소형 태그는 badge, got {res}"


# ── 진짜 버튼은 여전히 button (회귀 방지) ───────────────────────────────
def test_named_cta_is_button():
    btn = _pill("Primary CTA", "참여하기", cr=12, pt=16, pb=16, fill="$token(bg-brand-solid)")
    assert _is_button(role_of(btn)), "이름이 CTA 인 버튼은 button"


def test_action_label_is_button():
    for label in ("참여하기", "신청하기", "더보기", "전체보기", "결제하기", "자세히 보기"):
        btn = _pill("X", label, cr=12, pt=14, pb=14)
        assert _is_button(role_of(btn)), f"액션 라벨 '{label}' 는 button"


def test_generously_padded_noun_button_stays_button():
    # 명사 라벨이라도 큰 패딩(=버튼 시그널)이면 button 유지
    btn = _pill("Menu", "마이페이지", cr=12, pt=16, pb=16)
    assert _is_button(role_of(btn)), "큰 패딩 명사 버튼은 button"


def test_submit_button_is_button():
    btn = _pill("Submit Btn", "확인", cr=10, pt=14, pb=14)
    assert _is_button(role_of(btn)), "이름이 Btn 인 버튼은 button"


# ── 원형 번호 마커(아바타/스텝)는 badge 가 아님 (2026-06-01 over-swap 차단) ──────
def test_circular_number_marker_is_not_badge():
    # 도토리 번호 / 회차 step 처럼 원형 + 숫자만 = 아바타 마커, badge 아님
    for num in ("1", "11", "13"):
        marker = _pill("mav", num, cr=999, w=30, h=30, pl=0, pr=0, pt=0, pb=0)
        res = role_of(marker, _row_with(marker, title="도토리 1번"))
        assert not _is_badge(res), f"원형 번호 '{num}' 마커는 badge 가 아니어야 함, got {res}"
        assert not _is_button(res), f"원형 번호 '{num}' 마커는 button 도 아니어야 함, got {res}"


def test_count_with_unit_stays_badge_even_if_round():
    # 단위가 있는 카운트는 원형이어도 badge 유지 (bare 숫자만 마커로 제외됨)
    for word in ("13회", "3개", "5명"):
        pill = _pill("Count", word, cr=999, w=44, h=24)
        assert _is_badge(role_of(pill)), f"'{word}' 는 원형이어도 카운트 badge"


# ── Badge 색 = Color prop (절대 규칙 0-K, 2026-06-01) ──────────────────────
def test_badge_color_prop_options_count():
    from design_rules.ds_catalog import BADGE_COLOR_PROP_OPTIONS
    assert len(BADGE_COLOR_PROP_OPTIONS) == 13, BADGE_COLOR_PROP_OPTIONS
    for expect in ("Gray", "Brand", "Warning", "Success", "Blue light", "Gray blue"):
        assert expect in BADGE_COLOR_PROP_OPTIONS, expect


def test_badge_color_prop_from_role():
    from design_rules.ds_catalog import badge_color_prop_from_role
    assert badge_color_prop_from_role("Badge sm Warning") == "Warning"
    assert badge_color_prop_from_role("Badge sm Brand") == "Brand"
    assert badge_color_prop_from_role("Badge sm Success") == "Success"
    assert badge_color_prop_from_role("Action Button md Primary") is None  # 버튼은 매핑 없음


def test_r23_swap_sets_badge_color_prop():
    """R23 가 badge 를 swap 할 때 Color prop 을 명시적으로 박는가 (fill 대신)."""
    from design_rules.R23_ds_first import _inject_node
    node = {"name": "Tag", "type": "frame", "cornerRadius": 6, "fill": "$token(bg-secondary)",
            "autoLayout": {"layoutMode": "HORIZONTAL", "paddingLeft": 8, "paddingRight": 8,
                           "paddingTop": 4, "paddingBottom": 4},
            "children": [{"name": "t", "type": "text", "characters": "진행중"}]}
    changed = _inject_node(node, None)
    assert changed == 1 and node.get("type") == "instance", node
    ip = node.get("instanceProperties") or {}
    assert ip.get("Color"), f"badge swap 은 Color prop 을 박아야 함: {ip}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
