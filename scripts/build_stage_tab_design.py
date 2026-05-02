#!/usr/bin/env python3
"""Generate full Stage Tab Design blueprint with 3 inline TimelineBar Stage Cards."""
import json
from pathlib import Path

BP_PATH = Path(__file__).parent / "blueprint_stage_tab_design.json"
OUT_PATH = Path(__file__).parent / "blueprint_stage_tab_design_final.json"

with BP_PATH.open() as f:
    bp = json.load(f)


def stage_card(monthly_fmt: str, payout_at: int, total_months: int, payout: str, interest: str, points: str, fee: str):
    """TimelineBar Stage Card matching sections-3.jsx spec."""
    cells = []
    for n in range(1, total_months + 1):
        is_payout = (n == payout_at)
        cells.append({
            "name": f"cell-{n}",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "height": 22,
            "cornerRadius": 4,
            "fill": "$token(bg-brand-solid)" if is_payout else "$token(bg-brand-secondary)",
            "autoLayout": {
                "layoutMode": "HORIZONTAL",
                "primaryAxisAlignItems": "CENTER",
                "counterAxisAlignItems": "CENTER"
            },
            "children": [
                {
                    "name": "n",
                    "type": "text",
                    "characters": str(n),
                    "fontSize": 9,
                    "fontWeight": 700,
                    "fontFamily": "Pretendard",
                    "color": "$token(fg-white)" if is_payout else "$token(fg-brand-primary)",
                    "textAlignHorizontal": "CENTER"
                }
            ]
        })

    return {
        "name": "Stage Card",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "cornerRadius": 14,
        "fill": "$token(bg-primary)",
        "stroke": "$token(border-secondary)",
        "strokeWeight": 1,
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "paddingTop": 16,
            "paddingBottom": 14,
            "paddingLeft": 16,
            "paddingRight": 16,
            "itemSpacing": 0
        },
        "effects": [
            {
                "type": "DROP_SHADOW",
                "color": {"r": 0.039, "g": 0.051, "b": 0.094, "a": 0.04},
                "offset": {"x": 0, "y": 1},
                "radius": 2,
                "spread": 0,
                "visible": True,
                "blendMode": "NORMAL"
            }
        ],
        "children": [
            # Title
            {
                "name": "Title Row",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "primaryAxisAlignItems": "CENTER",
                    "counterAxisAlignItems": "CENTER",
                    "paddingBottom": 10
                },
                "children": [
                    {
                        "name": "title",
                        "type": "text",
                        "characters": f"→ 월 {monthly_fmt} 씩 {total_months}개월 모으기",
                        "fontSize": 13,
                        "fontWeight": 600,
                        "fontFamily": "Pretendard",
                        "letterSpacing": -0.26,
                        "color": "$token(fg-secondary)",
                        "textAlignHorizontal": "CENTER",
                        "layoutSizingHorizontal": "FILL"
                    }
                ]
            },
            # Timeline cells row
            {
                "name": "Timeline Row",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "itemSpacing": 2,
                    "counterAxisAlignItems": "CENTER"
                },
                "children": cells
            },
            # Payout caption
            {
                "name": "Payout Caption",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "primaryAxisAlignItems": "CENTER",
                    "counterAxisAlignItems": "CENTER",
                    "paddingTop": 6,
                    "paddingBottom": 0
                },
                "children": [
                    {
                        "name": "caption",
                        "type": "text",
                        "characters": f"{payout_at}회차 납입 후 목돈 수령",
                        "fontSize": 12,
                        "fontWeight": 600,
                        "fontFamily": "Pretendard",
                        "letterSpacing": -0.12,
                        "color": "$token(fg-secondary)",
                        "textAlignHorizontal": "CENTER",
                        "layoutSizingHorizontal": "FILL"
                    }
                ]
            },
            # Divider + Amount block
            {
                "name": "Amount Block",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "strokeTopWeight": 1,
                "strokeWeight": 0,
                "stroke": "$token(border-secondary)",
                "autoLayout": {
                    "layoutMode": "VERTICAL",
                    "paddingTop": 12,
                    "itemSpacing": 6
                },
                "children": [
                    {
                        "name": "Payout Row",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "SPACE_BETWEEN",
                            "counterAxisAlignItems": "CENTER"
                        },
                        "children": [
                            {
                                "name": "label",
                                "type": "text",
                                "characters": f"목돈 ({payout_at}회차 납입 후 수령)",
                                "fontSize": 13,
                                "fontWeight": 500,
                                "fontFamily": "Pretendard",
                                "letterSpacing": -0.13,
                                "color": "$token(fg-tertiary)"
                            },
                            {
                                "name": "value",
                                "type": "text",
                                "characters": payout,
                                "fontSize": 14,
                                "fontWeight": 700,
                                "fontFamily": "Pretendard",
                                "letterSpacing": -0.14,
                                "color": "$token(fg-primary)"
                            }
                        ]
                    },
                    {
                        "name": "Interest Row",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "SPACE_BETWEEN",
                            "counterAxisAlignItems": "CENTER"
                        },
                        "children": [
                            {
                                "name": "label",
                                "type": "text",
                                "characters": "총 이자",
                                "fontSize": 13,
                                "fontWeight": 500,
                                "fontFamily": "Pretendard",
                                "letterSpacing": -0.13,
                                "color": "$token(fg-tertiary)"
                            },
                            {
                                "name": "value",
                                "type": "text",
                                "characters": interest,
                                "fontSize": 14,
                                "fontWeight": 700,
                                "fontFamily": "Pretendard",
                                "letterSpacing": -0.14,
                                "color": "$token(fg-error-primary)"
                            }
                        ]
                    }
                ]
            },
            # Benefit row
            {
                "name": "Benefit Row Wrapper",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "VERTICAL",
                    "paddingTop": 10
                },
                "children": [
                    {
                        "name": "Benefit Row",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "cornerRadius": 8,
                        "fill": "$token(bg-secondary)",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "SPACE_BETWEEN",
                            "counterAxisAlignItems": "CENTER",
                            "paddingTop": 8,
                            "paddingBottom": 8,
                            "paddingLeft": 10,
                            "paddingRight": 10
                        },
                        "children": [
                            {
                                "name": "label",
                                "type": "text",
                                "characters": "추가 혜택 (스테이지 시작시 지급)",
                                "fontSize": 11,
                                "fontWeight": 500,
                                "fontFamily": "Pretendard",
                                "letterSpacing": -0.11,
                                "color": "$token(fg-tertiary)"
                            },
                            {
                                "name": "Badges",
                                "type": "frame",
                                "layoutSizingHorizontal": "HUG",
                                "autoLayout": {
                                    "layoutMode": "HORIZONTAL",
                                    "counterAxisAlignItems": "CENTER",
                                    "itemSpacing": 6
                                },
                                "children": [
                                    {
                                        "name": "Points Badge",
                                        "type": "frame",
                                        "layoutSizingHorizontal": "HUG",
                                        "cornerRadius": 999,
                                        "fill": "$token(bg-brand-secondary)",
                                        "autoLayout": {
                                            "layoutMode": "HORIZONTAL",
                                            "counterAxisAlignItems": "CENTER",
                                            "itemSpacing": 3,
                                            "paddingTop": 3,
                                            "paddingBottom": 3,
                                            "paddingLeft": 8,
                                            "paddingRight": 8
                                        },
                                        "children": [
                                            {"name": "ic", "type": "text", "characters": "◆", "fontSize": 9, "fontWeight": 500, "fontFamily": "Pretendard", "color": "$token(fg-brand-primary)"},
                                            {"name": "p", "type": "text", "characters": points, "fontSize": 11, "fontWeight": 700, "fontFamily": "Pretendard", "letterSpacing": -0.11, "color": "$token(fg-brand-primary)"}
                                        ]
                                    },
                                    {
                                        "name": "Fee Badge",
                                        "type": "frame",
                                        "layoutSizingHorizontal": "HUG",
                                        "cornerRadius": 999,
                                        "fill": "$token(bg-primary)",
                                        "stroke": "$token(border-primary)",
                                        "strokeWeight": 1,
                                        "autoLayout": {
                                            "layoutMode": "HORIZONTAL",
                                            "counterAxisAlignItems": "CENTER",
                                            "paddingTop": 3,
                                            "paddingBottom": 3,
                                            "paddingLeft": 8,
                                            "paddingRight": 8
                                        },
                                        "children": [
                                            {"name": "f", "type": "text", "characters": fee, "fontSize": 11, "fontWeight": 700, "fontFamily": "Pretendard", "letterSpacing": -0.11, "color": "$token(fg-tertiary)"}
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }


# 3 stage cards with different data
cards = [
    stage_card("105,120원", 1, 13, "1,092,200원", "-129,100원", "500P", "0원"),
    stage_card("200,000원", 3, 12, "2,400,000원", "-168,500원", "1,200P", "0원"),
    stage_card("83,000원", 2, 10, "830,000원", "-64,200원", "300P", "0원"),
]

# Replace $ref placeholders
for i, child in enumerate(bp["children"]):
    if child.get("name") == "Stage Card 1 Wrapper":
        child["children"] = [cards[0]]
    elif child.get("name") == "Stage Card 2 Wrapper":
        child["children"] = [cards[1]]
    elif child.get("name") == "Stage Card 3 Wrapper":
        child["children"] = [cards[2]]

with OUT_PATH.open("w") as f:
    json.dump(bp, f, ensure_ascii=False, indent=2)

print(f"Wrote {OUT_PATH}")
print(f"Size: {OUT_PATH.stat().st_size} bytes")
