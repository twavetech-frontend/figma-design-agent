"""회귀 테스트 — R50/R51/R52 + R13.3 inject (2026-05-28).

신설 4개 시스템 fix가 새 세션 회귀를 차단하는지 검증.
"""
from __future__ import annotations

import pytest

from scripts.design_rules import REGISTRY, Severity


def _run_lint(bp: dict):
    return list(REGISTRY.run_lint(bp))


def _run_inject(bp: dict):
    return REGISTRY.run_inject(bp)


# ----- R50: placeholder content 차단 ------


def test_r50_grey_placeholder_card_blocks_build():
    """라운지 카드가 bg-secondary + children=1(텍스트만) → ERROR."""
    bp = {
        "name": "imin_home_test",
        "type": "frame",
        "children": [{
            "name": "Lounge Card 1",
            "type": "frame",
            "width": 132,
            "height": 200,
            "fill": "$token(bg-secondary)",
            "children": [
                {"type": "text", "text": "휴식 라운지", "fontSize": 13},
            ],
        }],
    }
    violations = _run_lint(bp)
    r50 = [v for v in violations if v.rule_id == "R50-no-placeholder-content"]
    assert len(r50) == 1, f"R50 ERROR 1건 기대, 실제: {[v.rule_id for v in violations]}"
    assert r50[0].severity == Severity.ERROR


def test_r50_imageQuery_passes():
    """imageQuery 있으면 통과."""
    bp = {
        "name": "imin_home_test",
        "type": "frame",
        "children": [{
            "name": "Lounge Card 1",
            "type": "frame",
            "width": 132,
            "height": 200,
            "fill": "$token(bg-secondary)",
            "imageQuery": "cozy cafe lounge interior",
            "children": [{"type": "text", "text": "휴식 라운지"}],
        }],
    }
    violations = _run_lint(bp)
    r50 = [v for v in violations if v.rule_id == "R50-no-placeholder-content"]
    assert len(r50) == 0


def test_r50_bypass_via_placeholder_allowed():
    bp = {
        "name": "test",
        "type": "frame",
        "children": [{
            "name": "Empty Card 1",
            "type": "frame",
            "width": 353,
            "height": 78,
            "fill": "$token(bg-secondary)",
            "_placeholderAllowed": "skeleton loading state",
            "children": [],
        }],
    }
    violations = _run_lint(bp)
    r50 = [v for v in violations if v.rule_id == "R50-no-placeholder-content"]
    assert len(r50) == 0


def test_r50_skips_small_placeholders():
    """80×60 미만은 검사 안 함 (작은 dot/badge 보호)."""
    bp = {
        "name": "test",
        "type": "frame",
        "children": [{
            "name": "Empty Card 1",
            "type": "frame",
            "width": 24,
            "height": 24,
            "fill": "$token(bg-secondary)",
            "children": [],
        }],
    }
    violations = _run_lint(bp)
    r50 = [v for v in violations if v.rule_id == "R50-no-placeholder-content"]
    assert len(r50) == 0


def test_r50_FILL_card_caught_v15_regression():
    """v15 회귀 — width 필드 없이 layoutSizingHorizontal=FILL 카드도 잡아야 함."""
    bp = {
        "name": "Participation Section",
        "type": "frame",
        "children": [{
            "name": "Empty Card 1",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "layoutSizingVertical": "FIXED",
            "height": 78,
            "fill": "$token(bg-secondary)",
            "cornerRadius": 16,
            "children": [],
        }, {
            "name": "Empty Card 2",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "layoutSizingVertical": "FIXED",
            "height": 78,
            "fill": "$token(bg-secondary)",
            "cornerRadius": 16,
            "children": [],
        }],
    }
    violations = _run_lint(bp)
    r50 = [v for v in violations if v.rule_id == "R50-no-placeholder-content"]
    assert len(r50) == 2, f"v15 회귀: FILL 카드 2개 잡아야 함, 실제: {len(r50)}건"
    assert all(v.severity == Severity.ERROR for v in r50)


# ----- R51: hero scale 자동 승격 ------


def test_r51_currency_hero_promoted_only_if_no_fontsize():
    """카드 안 통화 텍스트 + 노드 이름 hero/goal — 사용자가 fontSize 명시 안 한
    경우에만 30 Bold 자동 승격. 명시 fontSize 박혀있으면 사용자 의도 보존 (2026-05-28 fix)."""
    # case A: fontSize 명시 없음 → R51 가 30 박음
    bp_no_fs = {
        "name": "test",
        "type": "frame",
        "children": [{
            "name": "Goal Hero",
            "type": "text",
            "text": "총 1,300만원 모으기 도전",
            "fontName": {"family": "Pretendard", "style": "SemiBold"},
        }],
    }
    out = _run_inject(bp_no_fs)
    hero = out["children"][0]
    assert hero["fontSize"] == 30
    assert hero["fontName"]["style"] == "Bold"

    # case B: fontSize 22 명시 → 보존 (사용자 의도)
    bp_with_fs = {
        "name": "test",
        "type": "frame",
        "children": [{
            "name": "Goal Hero",
            "type": "text",
            "text": "총 1,300만원 모으기 도전",
            "fontSize": 22,
            "fontName": {"family": "Pretendard", "style": "SemiBold"},
        }],
    }
    out2 = _run_inject(bp_with_fs)
    hero2 = out2["children"][0]
    assert hero2["fontSize"] == 22, f"명시 22 보존 실패: {hero2['fontSize']}"


def test_r51_short_text_not_promoted():
    """짧은 텍스트(+0원) 는 hero 가 아님 → skip."""
    bp = {
        "name": "test",
        "type": "frame",
        "children": [{
            "name": "amount",
            "type": "text",
            "text": "+0원",
            "fontSize": 16,
        }],
    }
    out = _run_inject(bp)
    assert out["children"][0]["fontSize"] == 16


def test_r51_hero_subelement_not_promoted_v16_regression():
    """v16 회귀 — hero-caption / hero-label / hero-footnote sub-element 가
    'hero' 단어 매칭으로 R51 잡혀 30px 거대 폰트 박힌 사고. sub 접미사 노드는 skip."""
    bp = {
        "name": "Screen Hero",
        "type": "frame",
        "children": [
            {"name": "hero-caption", "type": "text", "text": "진행 중인 스테이지 0개", "fontSize": 13},
            {"name": "hero-label",   "type": "text", "text": "모은 금액", "fontSize": 14},
            {"name": "hero-amount",  "type": "text", "text": "0원", "fontSize": 42},
            {"name": "hero-footnote-text", "type": "text", "text": "출석 체크 시작하면 혜택 받을 수 있어요", "fontSize": 12},
        ],
    }
    out = _run_inject(bp)
    # sub-element 모두 원래 fontSize 보존
    assert out["children"][0]["fontSize"] == 13, "hero-caption 승격 차단 실패"
    assert out["children"][1]["fontSize"] == 14, "hero-label 승격 차단 실패"
    assert out["children"][3]["fontSize"] == 12, "hero-footnote 승격 차단 실패"


def test_r51_lounge_product_price_not_promoted_v17_regression():
    """v17 회귀 — Lounge card 안 product-price '9,800원' 이 currency 패턴 매칭으로
    R51 잡혀 30px 박힌 사고. product/price 접미사 노드 자동 skip."""
    bp = {
        "name": "Lounge Card 1",
        "type": "frame",
        "width": 120,
        "children": [
            {"name": "product-name",   "type": "text", "text": "스타벅스 아메리카노", "fontSize": 13},
            {"name": "product-price",  "type": "text", "text": "9,800원", "fontSize": 12},
            {"name": "product-points", "type": "text", "text": "8,200P 사용", "fontSize": 11},
        ],
    }
    out = _run_inject(bp)
    assert out["children"][1]["fontSize"] == 12, "product-price 승격 차단 실패"


def test_r51_polish_description_not_promoted_v17_hierarchy():
    """v17 위계 회귀 — polish-title 'description' 텍스트가 currency 패턴 매칭으로
    R51 잡혀 currency hero 와 동급 크기 박힘. polish-* 접두사 자동 skip."""
    bp = {
        "name": "Recommend Stage Card",
        "type": "frame",
        "children": [
            {"name": "polish-personal-caption", "type": "text", "text": "회원님을 위한 추천", "fontSize": 12},
            {"name": "polish-title",            "type": "text", "text": "총 1,300만원 모으기 도전, 13개월에 받아가요", "fontSize": 18},
            {"name": "polish-label",            "type": "text", "text": "예상 수령 금액 (1회차)", "fontSize": 12},
            {"name": "polish-currency",         "type": "text", "text": "1,300,000원", "fontSize": 32},
            {"name": "polish-currency-sub",     "type": "text", "text": "월 100,000원 · 13개월 · 납입 후 목표 수령", "fontSize": 12},
        ],
    }
    out = _run_inject(bp)
    # 모든 polish-* 노드 원래 fontSize 보존 (위계 깨짐 방지)
    for ch in out["children"]:
        original = {
            "polish-personal-caption": 12,
            "polish-title": 18,
            "polish-label": 12,
            "polish-currency": 32,
            "polish-currency-sub": 12,
        }[ch["name"]]
        assert ch["fontSize"] == original, f"{ch['name']} fontSize {ch['fontSize']} (원래 {original})"


def test_r51_stage_amount_not_promoted_v19_hierarchy_regression():
    """v19 위계 회귀 — Stage Card 4-card grid 의 'stage-amount' text (월 10만원 등 6자)
    가 R51 currency 패턴으로 30px 승격됨. 5만원(5자)만 통과해 4개 중 1개만 정상.
    name='stage-amount' 박히면 _HERO_SUB_RE 의 'amount'/'stage' 매칭으로 자동 skip."""
    bp = {
        "name": "Participation Grid",
        "type": "frame",
        "children": [
            {"name": "Stage Card 월 10만원", "type": "frame", "children": [
                {"name": "status-pill", "type": "frame", "children": [
                    {"type": "text", "text": "진행중", "fontSize": 12},
                ]},
                {"name": "stage-amount",   "type": "text", "text": "월 10만원", "fontSize": 18},
                {"name": "stage-subtitle", "type": "text", "text": "13개월 · 6.9%", "fontSize": 12},
            ]},
            {"name": "Stage Card 월 30만원", "type": "frame", "children": [
                {"name": "stage-amount",   "type": "text", "text": "월 30만원", "fontSize": 18},
            ]},
            {"name": "Stage Card 월 5만원", "type": "frame", "children": [
                {"name": "stage-amount",   "type": "text", "text": "월 5만원", "fontSize": 18},
            ]},
            {"name": "Stage Card 월 20만원", "type": "frame", "children": [
                {"name": "stage-amount",   "type": "text", "text": "월 20만원", "fontSize": 18},
            ]},
        ],
    }
    out = _run_inject(bp)
    # 모든 4 카드의 stage-amount 가 18px 보존되어야 위계 정상
    def find_all(n, name):
        results = []
        if n.get("name") == name:
            results.append(n)
        for c in n.get("children", []) or []:
            results += find_all(c, name)
        return results
    amounts = find_all(out, "stage-amount")
    assert len(amounts) == 4, f"stage-amount 4개 필요, 실제 {len(amounts)}"
    for a in amounts:
        assert a["fontSize"] == 18, f"{a['text']} fontSize {a['fontSize']} (18 보존되어야 — 위계)"


def test_r51_already_big_not_touched():
    bp = {
        "name": "test",
        "type": "frame",
        "children": [{
            "name": "Goal Hero",
            "type": "text",
            "text": "총 1,300만원 모으기 도전",
            "fontSize": 28,
        }],
    }
    out = _run_inject(bp)
    assert out["children"][0]["fontSize"] == 28


# ----- R52: 라운지 imageQuery 강제 ------


def test_r52_lounge_card_without_imagequery_errors():
    bp = {
        "name": "test",
        "type": "frame",
        "children": [{
            "name": "Lounge Card 2",
            "type": "frame",
            "width": 132,
            "height": 200,
            "fill": "$token(bg-secondary)",
            "children": [{"type": "text", "text": "라운지"}],
        }],
    }
    violations = _run_lint(bp)
    r52 = [v for v in violations if v.rule_id == "R52-lounge-imagequery"]
    assert len(r52) == 1
    assert r52[0].severity == Severity.ERROR


def test_r52_with_imagequery_passes():
    bp = {
        "name": "test",
        "type": "frame",
        "children": [{
            "name": "Lounge Card 1",
            "type": "frame",
            "width": 132,
            "height": 200,
            "fill": "$token(bg-secondary)",
            "imageQuery": "cafe interior",
            "children": [{"type": "text", "text": "라운지"}],
        }],
    }
    violations = _run_lint(bp)
    r52 = [v for v in violations if v.rule_id == "R52-lounge-imagequery"]
    assert len(r52) == 0


# ----- R13.3 inject auto-fix ------


def test_r13_3_space_between_fill_auto_fix():
    """SPACE_BETWEEN + FILL children → MIN + itemSpacing 자동 교정 (Day Strip 회귀 차단)."""
    bp = {
        "name": "test",
        "type": "frame",
        "children": [{
            "name": "Day Strip",
            "type": "frame",
            "autoLayout": {
                "layoutMode": "HORIZONTAL",
                "primaryAxisAlignItems": "SPACE_BETWEEN",
            },
            "children": [
                {"name": "cell1", "type": "frame", "layoutSizingHorizontal": "FILL"},
                {"name": "cell2", "type": "frame", "layoutSizingHorizontal": "FILL"},
            ],
        }],
    }
    out = _run_inject(bp)
    ds_al = out["children"][0]["autoLayout"]
    assert ds_al["primaryAxisAlignItems"] == "MIN", "SPACE_BETWEEN → MIN 교정 실패"
    assert ds_al.get("itemSpacing", 0) > 0


# ----- R53 cell row alignment ------


def test_r53_unifies_cell_alignment():
    """Day Strip 회귀 — 3개 이상 같은 구조 cell 의 alignment 통일."""
    bp = {
        "name": "test",
        "type": "frame",
        "children": [{
            "name": "Day Strip",
            "type": "frame",
            "autoLayout": {"layoutMode": "HORIZONTAL"},
            "children": [
                {"name": "cell1", "type": "frame",
                 "autoLayout": {"layoutMode": "VERTICAL", "counterAxisAlignItems": "MIN"},
                 "children": [{"type": "text", "text": "어제", "textAlignHorizontal": "LEFT"}]},
                {"name": "cell2", "type": "frame",
                 "autoLayout": {"layoutMode": "VERTICAL", "counterAxisAlignItems": "CENTER"},
                 "children": [{"type": "text", "text": "오늘", "textAlignHorizontal": "CENTER"}]},
                {"name": "cell3", "type": "frame",
                 "autoLayout": {"layoutMode": "VERTICAL", "counterAxisAlignItems": "MIN"},
                 "children": [{"type": "text", "text": "16일", "textAlignHorizontal": "LEFT"}]},
            ],
        }],
    }
    out = _run_inject(bp)
    cells = out["children"][0]["children"]
    # CENTER 가 1개라도 있으면 모두 CENTER 로 통일
    text_aligns = [c["children"][0].get("textAlignHorizontal") for c in cells]
    assert all(t == "CENTER" for t in text_aligns), f"text align 통일 실패: {text_aligns}"


# ----- R54 underline width ------


def test_r54_underline_FILL_unified():
    bp = {
        "type": "frame",
        "children": [{
            "name": "Mode Tabs Wrap",
            "type": "frame",
            "autoLayout": {"layoutMode": "HORIZONTAL"},
            "children": [
                {"name": "Tab Active", "type": "frame",
                 "autoLayout": {"layoutMode": "VERTICAL"},
                 "children": [
                     {"type": "text", "text": "거래 현황"},
                     {"name": "underline", "type": "rectangle", "height": 2.5,
                      "layoutSizingHorizontal": "HUG"},
                 ]},
                {"name": "Tab Inactive", "type": "frame",
                 "autoLayout": {"layoutMode": "VERTICAL"},
                 "children": [
                     {"type": "text", "text": "누적 거래"},
                     {"name": "underline", "type": "rectangle", "height": 3,
                      "layoutSizingHorizontal": "HUG"},
                 ]},
            ],
        }],
    }
    out = _run_inject(bp)
    cells = out["children"][0]["children"]
    for cell in cells:
        ul = [ch for ch in cell["children"] if "underline" in (ch.get("name") or "").lower()][0]
        assert ul["layoutSizingHorizontal"] == "FILL"
        assert ul["height"] == 2.5


# ----- R55 stepper icon visibility ------


def test_r55_stepper_icon_promoted():
    bp = {
        "type": "frame",
        "children": [{
            "name": "Stepper Amount",
            "type": "frame",
            "children": [
                {"type": "icon", "iconName": "minus", "iconColor": "$token(fg-tertiary)"},
                {"type": "text", "text": "10만원"},
                {"type": "icon", "iconName": "plus", "iconColor": "$token(fg-tertiary)"},
            ],
        }],
    }
    out = _run_inject(bp)
    stepper = out["children"][0]
    icons = [c for c in stepper["children"] if c.get("type") == "icon"]
    for icon in icons:
        assert icon["iconColor"] == "$token(fg-secondary)", f"icon color 승격 실패: {icon}"


# ----- R56 lounge fallback ------


def test_r56_no_duplicate_icon_wrap_v15_regression():
    """v15 회귀 — 카드에 이미 icon-wrap 자식 있으면 R56 이 또 박지 않아야."""
    bp = {
        "type": "frame",
        "children": [{
            "name": "Lounge Card 1",
            "type": "frame",
            "width": 120,
            "height": 200,
            "fill": "$token(bg-primary)",
            "imageQuery": "cozy cafe lounge",
            "children": [
                {"name": "card-icon-wrap", "type": "frame", "width": 44, "height": 44,
                 "children": [{"type": "icon", "iconName": "coffee", "size": 24}]},
                {"type": "text", "text": "휴식 라운지"},
                {"type": "text", "text": "1,200p ~"},
            ],
        }],
    }
    out = _run_inject(bp)
    card = out["children"][0]
    icon_wraps = [c for c in card["children"] if "icon-wrap" in (c.get("name") or "").lower()]
    assert len(icon_wraps) == 1, f"R56 중복 fallback: icon-wrap {len(icon_wraps)}개 박힘 (1개여야)"


def test_r56_lounge_card_fallback_icon():
    bp = {
        "type": "frame",
        "children": [{
            "name": "Lounge Card 1",
            "type": "frame",
            "width": 120,
            "height": 200,
            "fill": "$token(bg-secondary)",
            "imageQuery": "cozy cafe lounge interior",
            "children": [{"type": "text", "text": "휴식 라운지"}],
        }],
    }
    out = _run_inject(bp)
    card = out["children"][0]
    types = [(c.get("type") or "").lower() for c in card["children"]]
    # icon wrap + text + (subtitle) — 최소 frame(icon wrap) + text 1+
    assert "frame" in types, f"icon wrap 자동 추가 실패: {types}"


# ----- 시나리오 인지 (2026-05-28 옵션 Z) ------


def test_detect_empty_state_zero_wireframe():
    """_wireframeContent dict 가 0건/0원 우세면 empty state."""
    from scripts.figma_mcp_client import _detect_empty_state_scenario
    bp = {
        "_wireframeContent": {
            "progress": {"count": "진행중인 0건의 스테이지 내역", "saved": "+0원", "borrowed": "-0원"},
            "attendance": {"streak": "연속 0일째 출석 체크 중"},
        },
    }
    assert _detect_empty_state_scenario(bp) is True


def test_detect_full_data_scenario():
    """풀데이터 시나리오 — currency 텍스트 풍부 + 0원 없음."""
    from scripts.figma_mcp_client import _detect_empty_state_scenario
    bp = {
        "type": "frame",
        "children": [
            {"type": "text", "text": "14,420,320원"},
            {"type": "text", "text": "5,240,020원"},
            {"type": "text", "text": "월 30만원"},
            {"type": "text", "text": "월 10만원"},
        ],
    }
    assert _detect_empty_state_scenario(bp) is False


def test_detect_empty_state_by_zero_count():
    """'0건' 패턴만으로도 empty state."""
    from scripts.figma_mcp_client import _detect_empty_state_scenario
    bp = {
        "type": "frame",
        "children": [{"type": "text", "text": "진행중 0건"}],
    }
    assert _detect_empty_state_scenario(bp) is True


# ----- Day Strip reference 패턴 (2026-05-28 사용자 reference 박음) ------


def test_day_strip_full_data_reference_pattern():
    """풀데이터 시나리오 — _enrich_day_strip_full 가 reference 시각 패턴 적용:
    cell bg 시맨틱 (미납 peach / 오늘 dark / 지급 green) + 4단계 텍스트."""
    from scripts.figma_mcp_client import _enrich_day_strip_full
    # Day Strip 을 Progress Card 안에 박음 (section title inject 대상)
    day_strip = {
        "name": "Day Strip",
        "type": "frame",
        "children": [
                {"type": "frame", "children": [
                    {"type": "text", "text": "화"},
                    {"type": "text", "text": "12"},
                    {"type": "text", "text": "-32만"},
                ]},
                {"type": "frame", "children": [
                    {"type": "text", "text": "토"},
                    {"type": "text", "text": "18"},
                    {"type": "text", "text": "-45만"},
                ]},
                {"type": "frame", "children": [
                    {"type": "text", "text": "수"},
                    {"type": "text", "text": "22"},
                    {"type": "text", "text": "-30만"},
                ]},
                {"type": "frame", "children": [
                    {"type": "text", "text": "금"},
                    {"type": "text", "text": "25"},
                    {"type": "text", "text": "+260만"},
                ]},
                {"type": "frame", "children": [
                    {"type": "text", "text": "월"},
                    {"type": "text", "text": "28"},
                    {"type": "text", "text": "-45만"},
                ]},
                {"type": "frame", "children": [
                    {"type": "text", "text": "수"},
                    {"type": "text", "text": "3"},
                    {"type": "text", "text": "+180만"},
                ]},
            ],
        }
    bp = {
        "type": "frame",
        "children": [{
            "name": "Progress Card",
            "type": "frame",
            "children": [day_strip],
        }],
    }
    n = _enrich_day_strip_full(bp, is_empty=False)
    assert n == 6
    cells = day_strip["children"]  # day_strip ref 직접 사용
    # cell 1 (미납 화12): peach bg + red text
    assert "bg-error-secondary" in cells[0]["fill"]
    # cell 2 (오늘 토18): dark bg + white text
    assert "bg-fg-primary-solid" in cells[1]["fill"]
    # cell 4 (지급 금25): bg-secondary + amount text-success
    assert "bg-secondary" in cells[3]["fill"]
    # cell 마다 cornerRadius 12
    for c in cells:
        assert c["cornerRadius"] == 12
    # 일자 (text 2번째) 모두 20px Bold
    for c in cells:
        day_num = [x for x in c["children"] if x.get("name") == "day-number"][0]
        assert day_num["fontSize"] == 20
        assert day_num["fontName"]["style"] == "Bold"
    # status-label 자동 추가
    for c in cells:
        labels = [x for x in c["children"] if x.get("name") == "status-label"]
        assert len(labels) == 1


def test_day_strip_section_title_with_unpaid_pill():
    """풀데이터 — section title row + 미납 N pill 자동 inject."""
    from scripts.figma_mcp_client import _enrich_day_strip_full
    bp = {
        "type": "frame",
        "children": [{
            "name": "Progress Card",
            "type": "frame",
            "children": [{
                "name": "Day Strip",
                "type": "frame",
                "children": [
                    {"type":"frame","children":[{"type":"text","text":"화"},{"type":"text","text":"12"},{"type":"text","text":"-32만"}]},
                ] * 2,  # 2 cells 만 (간단 fixture)
            }],
        }],
    }
    _enrich_day_strip_full(bp, is_empty=False)
    progress_card = bp["children"][0]
    titles = [c for c in progress_card["children"] if (c.get("name") or "").lower() == "day-strip-title"]
    assert len(titles) == 1
    title_children = titles[0]["children"]
    # title text "이번 달 일정"
    text_nodes = [c for c in title_children if (c.get("type") or "").lower() == "text"]
    assert any("이번 달" in (t.get("text") or "") for t in text_nodes)
    # unpaid pill ('미납 N')
    pill_nodes = [c for c in title_children if "pill" in (c.get("name") or "").lower()]
    assert len(pill_nodes) == 1


def test_day_strip_parent_layout_forced_MIN_v20_overlap_regression():
    """v20 회귀 — Day Strip parent 가 SPACE_BETWEEN + HUG cells 였을 때 cells overlap.
    _enrich_day_strip_full 마지막에 parent autoLayout 강제 (HORIZONTAL + MIN + itemSpacing 6)."""
    from scripts.figma_mcp_client import _enrich_day_strip_full
    day_strip = {
        "name": "Day Strip",
        "type": "frame",
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "primaryAxisAlignItems": "SPACE_BETWEEN",  # 잘못 박힌 상태
            "counterAxisAlignItems": "CENTER",
            "itemSpacing": 6,
        },
        "children": [
            {"type":"frame","children":[{"type":"text","text":"화"},{"type":"text","text":"12"},{"type":"text","text":"-32만"}]},
            {"type":"frame","children":[{"type":"text","text":"토"},{"type":"text","text":"18"},{"type":"text","text":"-45만"}]},
            {"type":"frame","children":[{"type":"text","text":"수"},{"type":"text","text":"22"},{"type":"text","text":"-30만"}]},
        ],
    }
    bp = {"type":"frame","children":[{"name":"Progress Card","type":"frame","children":[day_strip]}]}
    _enrich_day_strip_full(bp, is_empty=False)
    # MIN 으로 자동 변경 → cells overlap 회피
    assert day_strip["autoLayout"]["primaryAxisAlignItems"] == "MIN"
    assert day_strip["clipsContent"] is False


def test_day_strip_empty_state_pattern():
    """empty state 시나리오 — 모든 cell 회색, 오늘만 dark+white, status='예정'/'오늘'."""
    from scripts.figma_mcp_client import _enrich_day_strip_full
    day_strip = {
        "name": "Day Strip",
        "type": "frame",
        "children": [
            {"type":"frame","children":[{"type":"text","text":"어제"},{"type":"text","text":"0원"}]},
            {"type":"frame","children":[{"type":"text","text":"오늘"},{"type":"text","text":"0원"}]},
            {"type":"frame","children":[{"type":"text","text":"16일"},{"type":"text","text":"0원"}]},
        ],
    }
    bp = {
        "type": "frame",
        "children": [{"name":"Progress Card","type":"frame","children":[day_strip]}],
    }
    n = _enrich_day_strip_full(bp, is_empty=True)
    assert n == 3
    cells = day_strip["children"]
    # cell 2 (오늘) dark+white
    assert "bg-fg-primary-solid" in cells[1]["fill"]
    # 나머지 cell 회색
    assert "bg-secondary" in cells[0]["fill"]
    assert "bg-secondary" in cells[2]["fill"]


def test_r51_explicit_fontsize_preserved_v20_hierarchy():
    """v20 회귀 — 사용자/_polish 가 명시한 fontSize 17 이 currency 매칭으로 30 박힘.
    R51 inject 가 fontSize 명시되면 무조건 skip 해야 위계 보존."""
    bp = {
        "name": "Amount Row",
        "type": "frame",
        "children": [
            {"type": "text", "text": "+14,420,320원", "fontSize": 17, "fontName": {"family":"Pretendard","style":"Bold"}},
            {"type": "text", "text": "-5,240,020원",  "fontSize": 17, "fontName": {"family":"Pretendard","style":"Bold"}},
            {"type": "text", "text": "이번 달 1,240,000원 수령했어요", "fontSize": 12},
        ],
    }
    out = _run_inject(bp)
    # 모든 명시 fontSize 보존
    for ch in out["children"]:
        original = {"+14,420,320원": 17, "-5,240,020원": 17, "이번 달 1,240,000원 수령했어요": 12}[ch["text"]]
        assert ch["fontSize"] == original, f"{ch['text']} fontSize {ch['fontSize']} (명시 {original} 보존 실패)"


def test_enforce_text_hierarchy_preserves_explicit_fontsize():
    """_enforce_text_hierarchy (별도 룰) 도 fontSize 명시 시 보존."""
    from scripts.figma_mcp_client import _enforce_text_hierarchy
    bp = {
        "type": "frame",
        "children": [{
            "name": "Progress Card",
            "type": "frame",
            "cornerRadius": 16,
            "fill": "$token(bg-primary)",
            "autoLayout": {"layoutMode": "VERTICAL"},
            "children": [
                {"type": "text", "text": "+14,420,320원", "fontSize": 17, "fontName": {"family":"Pretendard","style":"Bold"}},
                {"type": "text", "text": "-5,240,020원",  "fontSize": 17, "fontName": {"family":"Pretendard","style":"Bold"}},
            ],
        }],
    }
    _enforce_text_hierarchy(bp)
    amounts = bp["children"][0]["children"]
    assert amounts[0]["fontSize"] == 17, f"+14M 명시 17 보존 실패: {amounts[0]['fontSize']}"
    assert amounts[1]["fontSize"] == 17, f"-5M 명시 17 보존 실패: {amounts[1]['fontSize']}"


def test_r13_3_space_between_no_fill_children_untouched():
    bp = {
        "name": "test",
        "type": "frame",
        "children": [{
            "type": "frame",
            "autoLayout": {
                "layoutMode": "HORIZONTAL",
                "primaryAxisAlignItems": "SPACE_BETWEEN",
            },
            "children": [
                {"name": "left", "type": "text"},
                {"name": "right", "type": "text"},
            ],
        }],
    }
    out = _run_inject(bp)
    assert out["children"][0]["autoLayout"]["primaryAxisAlignItems"] == "SPACE_BETWEEN"
