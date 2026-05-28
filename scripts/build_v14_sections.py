"""v14 config 의 4 핵심 섹션을 와이어프레임 17015:73113 (imin_home_1) 정밀 매핑으로 재작성."""
import json

CONFIG_PATH = "scripts/config_imin_home_v14.json"

def progress_section():
    """1.3 진행 현황 카드 + Day Strip (14~19일 6 cell × 0원, 17일 today)"""
    # Day Strip cells
    days = [
        ("14일 수", "0원", False),
        ("15일 목", "0원", False),
        ("16일 금", "0원", False),
        ("17일 토", "0원", True),  # today
        ("18일 일", "0원", False),
        ("19일 월", "0원", False),
    ]
    day_cells = []
    for i, (label, amt, is_today) in enumerate(days):
        cell = {
            "name": f"Day Cell {i+1}{' (Today)' if is_today else ''}",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "layoutSizingVertical": "HUG",
            "autoLayout": {
                "layoutMode": "VERTICAL",
                "paddingTop": 10, "paddingBottom": 10, "paddingLeft": 6, "paddingRight": 6,
                "itemSpacing": 6,
                "primaryAxisAlignItems": "CENTER",
                "counterAxisAlignItems": "CENTER",
            },
            "fill": ("$token(bg-brand-primary)" if is_today else "$token(bg-primary)"),
            "cornerRadius": 12,
            "strokeColor": "$token(border-secondary)" if not is_today else None,
            "strokeWeight": 1 if not is_today else 0,
            "children": [
                {
                    "name": "day-label",
                    "type": "text",
                    "text": label,
                    "fontSize": 11,
                    "fontName": {"family": "Pretendard", "style": "Medium"},
                    "fontColor": "$token(text-tertiary)" if not is_today else "$token(text-brand-primary)",
                    "textAlignHorizontal": "CENTER",
                },
                {
                    "name": "Today Dot" if is_today else "dot",
                    "type": "frame",
                    "width": 6, "height": 6,
                    "fill": "$token(bg-brand-solid)" if is_today else "$token(bg-tertiary)",
                    "cornerRadius": 3,
                },
                {
                    "name": "day-amount",
                    "type": "text",
                    "text": amt,
                    "fontSize": 12,
                    "fontName": {"family": "Pretendard", "style": "Bold" if is_today else "Medium"},
                    "fontColor": "$token(text-brand-primary)" if is_today else "$token(text-primary)",
                    "textAlignHorizontal": "CENTER",
                },
            ],
        }
        # strokeColor None 이면 키 자체 제거
        if cell.get("strokeColor") is None:
            cell.pop("strokeColor", None)
            cell.pop("strokeWeight", None)
        day_cells.append(cell)

    return {
        "name": "Progress Section",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "paddingTop": 8, "paddingBottom": 8, "paddingLeft": 16, "paddingRight": 16,
            "itemSpacing": 12,
        },
        "fill": "$token(bg-primary)",
        "children": [
            # Progress Card — header + 2 rows + Day Strip
            {
                "name": "Progress Card",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "autoLayout": {
                    "layoutMode": "VERTICAL",
                    "paddingTop": 20, "paddingBottom": 20, "paddingLeft": 18, "paddingRight": 18,
                    "itemSpacing": 16,
                },
                "fill": "$token(bg-primary)",
                "strokeColor": "$token(border-secondary)",
                "strokeWeight": 1,
                "cornerRadius": 16,
                "children": [
                    # Header row: "진행중인 0건의 스테이지 내역" + "자세히 >"
                    {
                        "name": "Progress Header",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "layoutSizingVertical": "HUG",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "SPACE_BETWEEN",
                            "counterAxisAlignItems": "CENTER",
                            "itemSpacing": 0,
                        },
                        "children": [
                            {
                                "name": "header-text",
                                "type": "text",
                                "text": "진행중인 0건의 스테이지 내역",
                                "fontSize": 16,
                                "fontName": {"family": "Pretendard", "style": "Bold"},
                                "fontColor": "$token(text-primary)",
                            },
                            {
                                "name": "more",
                                "type": "text",
                                "text": "자세히 >",
                                "fontSize": 12,
                                "fontName": {"family": "Pretendard", "style": "Medium"},
                                "fontColor": "$token(text-tertiary)",
                            },
                        ],
                    },
                    # Amount rows
                    {
                        "name": "Amount Summary",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "layoutSizingVertical": "HUG",
                        "autoLayout": {
                            "layoutMode": "VERTICAL",
                            "itemSpacing": 8,
                        },
                        "children": [
                            {
                                "name": "Row Collected",
                                "type": "frame",
                                "layoutSizingHorizontal": "FILL",
                                "layoutSizingVertical": "HUG",
                                "autoLayout": {
                                    "layoutMode": "HORIZONTAL",
                                    "primaryAxisAlignItems": "SPACE_BETWEEN",
                                    "counterAxisAlignItems": "CENTER",
                                },
                                "children": [
                                    {"name": "lab", "type": "text", "text": "모은 금액", "fontSize": 14, "fontName": {"family": "Pretendard", "style": "Medium"}, "fontColor": "$token(text-tertiary)"},
                                    {"name": "val", "type": "text", "text": "+ 0원", "fontSize": 16, "fontName": {"family": "Pretendard", "style": "Bold"}, "fontColor": "$token(text-brand-primary)"},
                                ],
                            },
                            {
                                "name": "Row Borrowed",
                                "type": "frame",
                                "layoutSizingHorizontal": "FILL",
                                "layoutSizingVertical": "HUG",
                                "autoLayout": {
                                    "layoutMode": "HORIZONTAL",
                                    "primaryAxisAlignItems": "SPACE_BETWEEN",
                                    "counterAxisAlignItems": "CENTER",
                                },
                                "children": [
                                    {"name": "lab", "type": "text", "text": "빌린 금액", "fontSize": 14, "fontName": {"family": "Pretendard", "style": "Medium"}, "fontColor": "$token(text-tertiary)"},
                                    {"name": "val", "type": "text", "text": "- 0원", "fontSize": 16, "fontName": {"family": "Pretendard", "style": "Bold"}, "fontColor": "$token(text-primary)"},
                                ],
                            },
                        ],
                    },
                    # Day Strip — 6 cell HORIZONTAL
                    {
                        "name": "Day Strip",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "layoutSizingVertical": "HUG",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "itemSpacing": 6,
                            "primaryAxisAlignItems": "MIN",
                            "counterAxisAlignItems": "MIN",
                        },
                        "children": day_cells,
                    },
                ],
            },
            # Calc CTA hint (1.3 의 마지막)
            {
                "name": "Calc CTA Card",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "paddingTop": 16, "paddingBottom": 16, "paddingLeft": 18, "paddingRight": 18,
                    "itemSpacing": 12,
                    "counterAxisAlignItems": "CENTER",
                },
                "fill": "$token(bg-primary)",
                "strokeColor": "$token(border-secondary)",
                "strokeWeight": 1,
                "cornerRadius": 16,
                "children": [
                    {
                        "name": "calc-help-icon",
                        "type": "frame",
                        "width": 28, "height": 28,
                        "fill": "$token(bg-brand-primary)",
                        "cornerRadius": 14,
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "CENTER",
                            "counterAxisAlignItems": "CENTER",
                        },
                        "children": [
                            {"name": "q", "type": "text", "text": "?", "fontSize": 16, "fontName": {"family": "Pretendard", "style": "Bold"}, "fontColor": "$token(text-brand-primary)"},
                        ],
                    },
                    {
                        "name": "calc-text",
                        "type": "text",
                        "text": "얼마까지 모을 수 있는 지 확인해보세요.",
                        "fontSize": 14,
                        "fontName": {"family": "Pretendard", "style": "Medium"},
                        "fontColor": "$token(text-primary)",
                        "layoutSizingHorizontal": "FILL",
                    },
                ],
            },
        ],
    }


def recommend_section():
    """1.5 추천 스테이지 — 10만원/13개월 pill + 1~13 round selector + 1회차 + 납입 후 목적 수령 + 총 1300만원 모으기 도전 + 추천 전체 보기(13개)"""
    # 13 round selector cells
    round_cells = []
    for i in range(1, 14):
        is_active = (i == 6)
        round_cells.append({
            "name": f"Round {i}{' (Active)' if is_active else ''}",
            "type": "frame",
            "width": 22, "height": 22,
            "fill": "$token(bg-brand-solid)" if is_active else "$token(bg-secondary)",
            "cornerRadius": 11,
            "autoLayout": {
                "layoutMode": "HORIZONTAL",
                "primaryAxisAlignItems": "CENTER",
                "counterAxisAlignItems": "CENTER",
            },
            "children": [
                {
                    "name": "num",
                    "type": "text",
                    "text": str(i),
                    "fontSize": 10,
                    "fontName": {"family": "Pretendard", "style": "Bold" if is_active else "Medium"},
                    "fontColor": "$token(text-primary_on-brand)" if is_active else "$token(text-tertiary)",
                    "textAlignHorizontal": "CENTER",
                },
            ],
        })

    return {
        "name": "Recommend Section",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "paddingTop": 12, "paddingBottom": 12, "paddingLeft": 16, "paddingRight": 16,
            "itemSpacing": 14,
        },
        "fill": "$token(bg-primary)",
        "children": [
            # Section header bar
            {
                "name": "Recommend Title Bar",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "itemSpacing": 8,
                    "paddingLeft": 4,
                    "counterAxisAlignItems": "CENTER",
                },
                "children": [
                    {"name": "bar", "type": "frame", "width": 3, "height": 16, "fill": "$token(bg-brand-solid)", "cornerRadius": 2},
                    {"name": "title", "type": "text", "text": "추천 스테이지", "fontSize": 16, "fontName": {"family": "Pretendard", "style": "Bold"}, "fontColor": "$token(text-primary)"},
                ],
            },
            # Hero Card
            {
                "name": "Recommend Hero Card",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "autoLayout": {
                    "layoutMode": "VERTICAL",
                    "paddingTop": 22, "paddingBottom": 22, "paddingLeft": 22, "paddingRight": 22,
                    "itemSpacing": 18,
                    "counterAxisAlignItems": "CENTER",
                },
                "fill": "$token(bg-primary)",
                "strokeColor": "$token(border-secondary)",
                "strokeWeight": 1,
                "cornerRadius": 20,
                "children": [
                    # Pills row: "10만원" "13개월"
                    {
                        "name": "Pills Row",
                        "type": "frame",
                        "layoutSizingHorizontal": "HUG",
                        "layoutSizingVertical": "HUG",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "itemSpacing": 8,
                            "counterAxisAlignItems": "CENTER",
                        },
                        "children": [
                            {
                                "name": "Monthly Pill",
                                "type": "frame",
                                "layoutSizingHorizontal": "HUG",
                                "layoutSizingVertical": "HUG",
                                "autoLayout": {
                                    "layoutMode": "HORIZONTAL",
                                    "paddingTop": 10, "paddingBottom": 10, "paddingLeft": 18, "paddingRight": 18,
                                    "primaryAxisAlignItems": "CENTER",
                                    "counterAxisAlignItems": "CENTER",
                                    "itemSpacing": 6,
                                },
                                "fill": "$token(bg-secondary)",
                                "cornerRadius": 999,
                                "children": [
                                    {"name": "lab", "type": "text", "text": "10만원", "fontSize": 15, "fontName": {"family": "Pretendard", "style": "Bold"}, "fontColor": "$token(text-primary)"},
                                ],
                            },
                            {
                                "name": "Period Pill",
                                "type": "frame",
                                "layoutSizingHorizontal": "HUG",
                                "layoutSizingVertical": "HUG",
                                "autoLayout": {
                                    "layoutMode": "HORIZONTAL",
                                    "paddingTop": 10, "paddingBottom": 10, "paddingLeft": 18, "paddingRight": 18,
                                    "primaryAxisAlignItems": "CENTER",
                                    "counterAxisAlignItems": "CENTER",
                                    "itemSpacing": 6,
                                },
                                "fill": "$token(bg-secondary)",
                                "cornerRadius": 999,
                                "children": [
                                    {"name": "lab", "type": "text", "text": "13개월", "fontSize": 15, "fontName": {"family": "Pretendard", "style": "Bold"}, "fontColor": "$token(text-primary)"},
                                ],
                            },
                        ],
                    },
                    # Round Selector — 1~13
                    {
                        "name": "Round Selector",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "layoutSizingVertical": "HUG",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "SPACE_BETWEEN",
                            "counterAxisAlignItems": "CENTER",
                            "itemSpacing": 2,
                        },
                        "children": round_cells,
                    },
                    # Round caption: 1회차 / 납입 후 목적 수령
                    {
                        "name": "Round Caption Row",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "layoutSizingVertical": "HUG",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "SPACE_BETWEEN",
                            "counterAxisAlignItems": "CENTER",
                            "paddingTop": 4,
                        },
                        "children": [
                            {
                                "name": "Round Pill",
                                "type": "frame",
                                "layoutSizingHorizontal": "HUG",
                                "layoutSizingVertical": "HUG",
                                "autoLayout": {
                                    "layoutMode": "HORIZONTAL",
                                    "paddingTop": 4, "paddingBottom": 4, "paddingLeft": 10, "paddingRight": 10,
                                    "primaryAxisAlignItems": "CENTER",
                                    "counterAxisAlignItems": "CENTER",
                                },
                                "fill": "$token(bg-brand-primary)",
                                "cornerRadius": 999,
                                "children": [
                                    {"name": "txt", "type": "text", "text": "1회차", "fontSize": 11, "fontName": {"family": "Pretendard", "style": "Bold"}, "fontColor": "$token(text-brand-primary)"},
                                ],
                            },
                            {"name": "subText", "type": "text", "text": "납입 후 목적 수령", "fontSize": 12, "fontName": {"family": "Pretendard", "style": "Medium"}, "fontColor": "$token(text-tertiary)"},
                        ],
                    },
                    # Goal text
                    {
                        "name": "Goal Text",
                        "type": "text",
                        "text": "총 1300만원 모으기 도전",
                        "fontSize": 14,
                        "fontName": {"family": "Pretendard", "style": "Bold"},
                        "fontColor": "$token(text-primary)",
                        "layoutSizingHorizontal": "FILL",
                        "textAlignHorizontal": "CENTER",
                    },
                ],
            },
            # View all link
            {
                "name": "View All Row",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "primaryAxisAlignItems": "MAX",
                    "counterAxisAlignItems": "CENTER",
                },
                "children": [
                    {"name": "viewAll", "type": "text", "text": "추천 전체 보기(13개) >", "fontSize": 12, "fontName": {"family": "Pretendard", "style": "Medium"}, "fontColor": "$token(text-tertiary)"},
                ],
            },
        ],
    }


def stage_tabs_section():
    """1.6 참여 중인 스테이지 / 찜한 스테이지 — placeholder grid 4 + (FAB root-level)"""
    placeholder = lambda i: {
        "name": f"Placeholder {i}",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "FIXED",
        "width": 165, "height": 110,
        "fill": "$token(bg-secondary)",
        "cornerRadius": 12,
        "children": [],
    }
    return {
        "name": "Stage Tabs Section",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "paddingTop": 8, "paddingBottom": 16, "paddingLeft": 16, "paddingRight": 16,
            "itemSpacing": 12,
        },
        "fill": "$token(bg-primary)",
        "children": [
            # Tab row
            {
                "name": "Stage Tab Row",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "itemSpacing": 14,
                    "counterAxisAlignItems": "CENTER",
                },
                "children": [
                    {"name": "tab1", "type": "text", "text": "참여 중인 스테이지", "fontSize": 15, "fontName": {"family": "Pretendard", "style": "Medium"}, "fontColor": "$token(text-tertiary)"},
                    {"name": "divider", "type": "frame", "width": 1, "height": 12, "fill": "$token(bg-tertiary)"},
                    {"name": "tab2_active", "type": "text", "text": "찜한 스테이지", "fontSize": 15, "fontName": {"family": "Pretendard", "style": "Bold"}, "fontColor": "$token(text-primary)"},
                ],
            },
            # Placeholder grid — 2 rows × 2 cols
            {
                "name": "Placeholder Grid Row 1",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "itemSpacing": 10,
                },
                "children": [placeholder(1), placeholder(2)],
            },
            {
                "name": "Placeholder Grid Row 2",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "itemSpacing": 10,
                },
                "children": [placeholder(3), placeholder(4)],
            },
        ],
    }


def lounge_section():
    """1.7 추천 상품 (라운지) — 가로 캐로셀 5 placeholder + 예치금 우상단"""
    cards = []
    for i in range(1, 6):
        cards.append({
            "name": f"Lounge Card {i}",
            "type": "frame",
            "width": 110, "height": 130,
            "layoutSizingHorizontal": "FIXED",
            "layoutSizingVertical": "FIXED",
            "fill": "$token(bg-secondary)",
            "cornerRadius": 12,
            "children": [],
        })
    return {
        "name": "Lounge Section",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "paddingTop": 12, "paddingBottom": 12,
            "paddingLeft": 0, "paddingRight": 0,
            "itemSpacing": 12,
        },
        "fill": "$token(bg-primary)",
        "children": [
            # Title row (paddingLeft for content alignment)
            {
                "name": "Lounge Title Row",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "primaryAxisAlignItems": "SPACE_BETWEEN",
                    "counterAxisAlignItems": "CENTER",
                    "paddingLeft": 16, "paddingRight": 16,
                },
                "children": [
                    {"name": "title", "type": "text", "text": "추천 상품 (라운지)", "fontSize": 16, "fontName": {"family": "Pretendard", "style": "Bold"}, "fontColor": "$token(text-primary)"},
                    {"name": "deposit", "type": "text", "text": "예치금(포인트): 312,490원(100p)", "fontSize": 11, "fontName": {"family": "Pretendard", "style": "Medium"}, "fontColor": "$token(text-tertiary)"},
                ],
            },
            # Horizontal carousel
            {
                "name": "Lounge Carousel",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "paddingLeft": 16, "paddingRight": 0,
                    "itemSpacing": 10,
                },
                "clipsContent": True,
                "children": cards,
            },
        ],
    }


def main():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    customs = cfg["customSections"]
    # customs 매핑 (v12 순서): [0] Trade Status Tabs, [1] Progress Section, [2] Attendance Banner, [3] Recommend, [4] Stage Tabs, [5] Lounge, [6] Footer
    customs[1] = progress_section()
    customs[3] = recommend_section()
    customs[4] = stage_tabs_section()
    customs[5] = lounge_section()
    cfg["customSections"] = customs

    # FAB — 와이어처럼 root level 책갈피 아이콘 (sections list 에 추가)
    # v12 config sections 마지막 = TabBar — FAB 를 그 뒤에 root-level absolute children 으로 박는 것은
    # blueprint_templates.json sections 에 FAB 가 정의되어 있지 않음.
    # 대안: customSections 에 FAB 추가 + post-fix 가 ABSOLUTE 배치.
    # 여기서는 FAB 를 customSections 마지막에 추가 (TabBar 다음).
    # config "sections" 배열에 마지막 custom 추가
    if "sections" in cfg:
        # v12 sections: ['NavBar', 'custom'x7, 'TabBar'] → FAB 추가 ['NavBar', 'custom'x7, 'TabBar', 'custom']
        cfg["sections"] = cfg["sections"] + ["custom"]
    customs.append({
        "name": "FAB",
        "type": "frame",
        "width": 56, "height": 56,
        "layoutSizingHorizontal": "FIXED",
        "layoutSizingVertical": "FIXED",
        "fill": "$token(bg-brand-solid)",
        "cornerRadius": 28,
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "primaryAxisAlignItems": "CENTER",
            "counterAxisAlignItems": "CENTER",
        },
        "children": [
            {
                "name": "fab-icon",
                "type": "text",
                "text": "♥",
                "fontSize": 24,
                "fontName": {"family": "Pretendard", "style": "Bold"},
                "fontColor": "$token(text-primary_on-brand)",
                "textAlignHorizontal": "CENTER",
            },
        ],
    })

    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"v14 config 4 핵심 섹션 와이어 정밀 재작성 완료")
    print(f"  sections: {cfg['sections']}")
    print(f"  customSections: {[c['name'] for c in customs]}")


if __name__ == "__main__":
    main()
