"""
Build "내 스테이지" 전체 모달 화면 — 와이어프레임 기반.

Sections:
1. Modal Header (X close)
2. Summary Card (4건 진행중 + 모은/빌린 금액)
3. Schedule Card (월 탭 가로 스크롤 + 필터 + 3컬럼 통계)
4. Transaction List (2026년 1월 + 거래 카드들)
"""
import json
import copy


def hex_rgba(hex_str, a=1.0):
    """#rrggbb → {r,g,b,a} 0-1 floats"""
    h = hex_str.lstrip("#")
    return {
        "r": int(h[0:2], 16) / 255,
        "g": int(h[2:4], 16) / 255,
        "b": int(h[4:6], 16) / 255,
        "a": a,
    }


# Light theme palette (semantic name → light hex; design system 토큰이 dark mode라 직접 매핑)
C = {
    "white": hex_rgba("#ffffff"),
    "transparent": {"r": 0, "g": 0, "b": 0, "a": 0},
    # Background
    "bg-base": hex_rgba("#f5f5f7"),       # 모달 베이스 (살짝 회색)
    "bg-card": hex_rgba("#ffffff"),
    "bg-secondary": hex_rgba("#fafafa"),  # light gray 배경
    "bg-tertiary": hex_rgba("#f5f5f5"),
    # Border
    "border-card": hex_rgba("#e9eaeb"),
    "border-error": hex_rgba("#fda29b"),  # error-300
    # Text
    "fg-primary": hex_rgba("#181d27"),    # gray-900
    "fg-secondary": hex_rgba("#414651"),  # gray-700
    "fg-tertiary": hex_rgba("#535862"),   # gray-600
    "fg-quaternary": hex_rgba("#717680"), # gray-500
    "fg-disabled": hex_rgba("#a4a7ae"),   # gray-400
    "fg-white": hex_rgba("#ffffff"),
    # Brand
    "bg-brand-solid": hex_rgba("#6938ef"),    # brand-600 light
    "bg-brand-primary": hex_rgba("#f4f3ff"),  # brand-50 옅은 배경
    "border-brand": hex_rgba("#d9d6fe"),      # brand-200
    "fg-brand-primary": hex_rgba("#5925dc"),  # brand-700 텍스트
    # Error
    "bg-error-primary": hex_rgba("#f04438"),  # error-500
    "bg-error-soft": hex_rgba("#fef3f2"),     # error-50
    "fg-error-primary": hex_rgba("#d92d20"),  # error-600
    "border-error": hex_rgba("#fecdca"),      # error-200
    # Success
    "bg-success-primary": hex_rgba("#17b26a"), # success-500
    "fg-success-primary": hex_rgba("#079455"), # success-600
    # Warning
    "fg-warning-primary": hex_rgba("#dc6803"),
}

# ----- Helper functions -----
def text(name, content, size=14, weight="Regular", color=C["fg-primary"],
         autoresize="WIDTH_AND_HEIGHT", align="LEFT", layout_sizing=None):
    node = {
        "name": name, "type": "text", "text": content,
        "fontSize": size,
        "fontName": {"family": "Pretendard", "style": weight},
        "fontColor": color,
        "textAutoResize": autoresize,
        "textAlignHorizontal": align,
    }
    if layout_sizing:
        node["layoutSizingHorizontal"] = layout_sizing
    return node


def frame(name, layout_mode=None, sizing_h="HUG", sizing_v="HUG", **kwargs):
    f = {"name": name, "type": "frame",
         "layoutSizingHorizontal": sizing_h,
         "layoutSizingVertical": sizing_v}
    if layout_mode:
        al = {"layoutMode": layout_mode}
        for k in ("itemSpacing", "paddingTop", "paddingBottom", "paddingLeft", "paddingRight",
                  "primaryAxisAlignItems", "counterAxisAlignItems"):
            if k in kwargs:
                al[k] = kwargs.pop(k)
        f["autoLayout"] = al
    f.update(kwargs)
    return f


# ============ SECTION 1 — Modal Header ============
def build_modal_header():
    return {
        "name": "Modal Header",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "fill": {"r": 1, "g": 1, "b": 1, "a": 1},
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "paddingTop": 12, "paddingBottom": 12, "paddingLeft": 20, "paddingRight": 20,
            "counterAxisAlignItems": "CENTER",
            "primaryAxisAlignItems": "MAX",
            "itemSpacing": 0,
        },
        "children": [
            {
                "name": "Close Button",
                "type": "frame",
                "layoutSizingHorizontal": "FIXED",
                "layoutSizingVertical": "FIXED",
                "width": 32, "height": 32,
                "fill": {"r": 0, "g": 0, "b": 0, "a": 0},
                "cornerRadius": 999,
                "autoLayout": {
                    "layoutMode": "VERTICAL",
                    "primaryAxisAlignItems": "CENTER",
                    "counterAxisAlignItems": "CENTER",
                },
                "children": [
                    text("close-x", "✕", size=22, weight="Medium",
                         color=C["fg-primary"], align="CENTER"),
                ]
            }
        ]
    }


# ============ SECTION 2 — Summary Card ============
def build_summary_card():
    return {
        "name": "Summary Wrap",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "fill": {"r": 0, "g": 0, "b": 0, "a": 0},
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "paddingTop": 4, "paddingBottom": 0, "paddingLeft": 16, "paddingRight": 16,
        },
        "children": [
            {
                "name": "Summary Card",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "fill": {"r": 1, "g": 1, "b": 1, "a": 1},
                "stroke": C["border-card"],
                "strokeWeight": 1,
                "cornerRadius": 16,
                "autoLayout": {
                    "layoutMode": "VERTICAL",
                    "itemSpacing": 14,
                    "paddingTop": 18, "paddingBottom": 18, "paddingLeft": 18, "paddingRight": 18,
                },
                "children": [
                    # Title row: "진행중인 4건의 스테이지 내역" + 정상/주의 아이콘
                    {
                        "name": "Title Row",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "counterAxisAlignItems": "CENTER",
                            "itemSpacing": 8,
                            "primaryAxisAlignItems": "MIN",
                        },
                        "children": [
                            {
                                "name": "Status Pill",
                                "type": "frame",
                                "layoutSizingHorizontal": "HUG",
                                "fill": C["bg-brand-primary"],
                                "stroke": C["border-brand"],
                                "strokeWeight": 1,
                                "cornerRadius": 999,
                                "autoLayout": {
                                    "layoutMode": "HORIZONTAL",
                                    "paddingTop": 3, "paddingBottom": 3, "paddingLeft": 9, "paddingRight": 9,
                                    "counterAxisAlignItems": "CENTER",
                                },
                                "children": [
                                    text("pill-text", "4건 진행 중", size=12, weight="Bold",
                                         color=C["fg-brand-primary"])
                                ]
                            },
                            text("title", "스테이지 내역", size=15, weight="SemiBold",
                                 color=C["fg-primary"], layout_sizing="FILL"),
                            {
                                "name": "Icon Check",
                                "type": "svg_icon",
                                "iconKey": "check_circle",
                                "iconSize": 20,
                                "iconColor": C["fg-success-primary"],
                                "layoutSizingHorizontal": "FIXED",
                                "layoutSizingVertical": "FIXED",
                                "width": 20, "height": 20,
                            },
                            {
                                "name": "Icon Sparkle",
                                "type": "svg_icon",
                                "iconKey": "sparkles",
                                "iconSize": 20,
                                "iconColor": C["fg-brand-primary"],
                                "layoutSizingHorizontal": "FIXED",
                                "layoutSizingVertical": "FIXED",
                                "width": 20, "height": 20,
                            },
                        ]
                    },
                    # 모은 금액 row
                    {
                        "name": "Earned Row",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "SPACE_BETWEEN",
                            "counterAxisAlignItems": "CENTER",
                        },
                        "children": [
                            text("earned-label", "모은 금액", size=14, weight="Medium",
                                 color=C["fg-tertiary"]),
                            {
                                "name": "Earned Group",
                                "type": "frame",
                                "layoutSizingHorizontal": "HUG",
                                "autoLayout": {
                                    "layoutMode": "HORIZONTAL",
                                    "itemSpacing": 4,
                                    "counterAxisAlignItems": "CENTER",
                                },
                                "children": [
                                    text("earned-sign", "+", size=15, weight="SemiBold",
                                         color=C["fg-success-primary"]),
                                    text("earned-amount", "14,420,320원", size=15, weight="SemiBold",
                                         color=C["fg-success-primary"]),
                                ]
                            }
                        ]
                    },
                    # 빌린 금액 row
                    {
                        "name": "Borrowed Row",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "SPACE_BETWEEN",
                            "counterAxisAlignItems": "CENTER",
                        },
                        "children": [
                            text("borrowed-label", "빌린 금액", size=14, weight="Medium",
                                 color=C["fg-tertiary"]),
                            {
                                "name": "Borrowed Group",
                                "type": "frame",
                                "layoutSizingHorizontal": "HUG",
                                "autoLayout": {
                                    "layoutMode": "HORIZONTAL",
                                    "itemSpacing": 4,
                                    "counterAxisAlignItems": "CENTER",
                                },
                                "children": [
                                    text("borrowed-sign", "−", size=15, weight="SemiBold",
                                         color=C["fg-error-primary"]),
                                    text("borrowed-amount", "5,240,010원", size=15, weight="SemiBold",
                                         color=C["fg-error-primary"]),
                                ]
                            }
                        ]
                    },
                ]
            }
        ]
    }


# ============ SECTION 3 — Schedule Card ============
def month_cell(eng, num, is_active=False, has_dot=False):
    children = [
        text("month-eng", eng, size=11, weight="Medium",
             color=C["fg-quaternary"] if not is_active else C["fg-white"],
             align="CENTER", layout_sizing="FILL"),
    ]
    if is_active:
        # 활성: 보라 원형 배경 안에 숫자
        active_circle = {
            "name": "Active Circle",
            "type": "frame",
            "layoutSizingHorizontal": "FIXED",
            "layoutSizingVertical": "FIXED",
            "width": 32, "height": 32,
            "cornerRadius": 999,
            "fill": C["bg-brand-solid"],
            "autoLayout": {
                "layoutMode": "VERTICAL",
                "primaryAxisAlignItems": "CENTER",
                "counterAxisAlignItems": "CENTER",
            },
            "children": [
                text("month-num", str(num), size=14, weight="Bold",
                     color=C["fg-white"], align="CENTER"),
            ]
        }
        children.append(active_circle)
        children.append(text("month-label", "이번달", size=10, weight="Medium",
                              color=C["fg-brand-primary"], align="CENTER", layout_sizing="FILL"))
    else:
        children.append(text("month-num", str(num), size=15, weight="SemiBold",
                              color=C["fg-secondary"], align="CENTER", layout_sizing="FILL"))
        if has_dot:
            children.append({
                "name": "Dot",
                "type": "frame",
                "layoutSizingHorizontal": "FIXED",
                "layoutSizingVertical": "FIXED",
                "width": 4, "height": 4,
                "cornerRadius": 999,
                "fill": C["bg-brand-solid"],
            })

    return {
        "name": f"Month Cell {eng}",
        "type": "frame",
        "layoutSizingHorizontal": "FIXED",
        "width": 40,
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "itemSpacing": 4,
            "counterAxisAlignItems": "CENTER",
            "primaryAxisAlignItems": "CENTER",
            "paddingTop": 4, "paddingBottom": 4,
        },
        "children": children
    }


def stat_col(label, value, value_color=C["fg-primary"]):
    return {
        "name": f"Stat {label}",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "itemSpacing": 4,
            "counterAxisAlignItems": "CENTER",
            "primaryAxisAlignItems": "CENTER",
        },
        "children": [
            text("label", label, size=12, weight="Medium",
                 color=C["fg-tertiary"], align="CENTER", layout_sizing="FILL"),
            text("value", value, size=15, weight="Bold",
                 color=value_color, align="CENTER", layout_sizing="FILL"),
        ]
    }


def build_schedule_card():
    return {
        "name": "Schedule Wrap",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "fill": {"r": 0, "g": 0, "b": 0, "a": 0},
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "paddingTop": 12, "paddingBottom": 0, "paddingLeft": 16, "paddingRight": 16,
        },
        "children": [
            {
                "name": "Schedule Card",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "fill": {"r": 1, "g": 1, "b": 1, "a": 1},
                "stroke": C["border-card"],
                "strokeWeight": 1,
                "cornerRadius": 16,
                "autoLayout": {
                    "layoutMode": "VERTICAL",
                    "itemSpacing": 16,
                    "paddingTop": 18, "paddingBottom": 0, "paddingLeft": 0, "paddingRight": 0,
                },
                "children": [
                    # 타이틀
                    text("schedule-title", "거래 스케줄", size=15, weight="SemiBold",
                         color=C["fg-primary"], align="CENTER", layout_sizing="FILL"),
                    # Month tabs row
                    {
                        "name": "Month Row",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "counterAxisAlignItems": "CENTER",
                            "primaryAxisAlignItems": "SPACE_BETWEEN",
                            "paddingLeft": 12, "paddingRight": 12,
                            "itemSpacing": 0,
                        },
                        "children": [
                            {
                                "name": "Arrow Left",
                                "type": "svg_icon",
                                "iconKey": "chevron_left",
                                "iconSize": 18,
                                "iconColor": C["fg-quaternary"],
                                "layoutSizingHorizontal": "FIXED",
                                "layoutSizingVertical": "FIXED",
                                "width": 18, "height": 18,
                            },
                            month_cell("Oct", 10, has_dot=False),
                            month_cell("Nov", 11, has_dot=True),
                            month_cell("Dec", 12, has_dot=True),
                            month_cell("Jan", 1, is_active=True),
                            month_cell("Feb", 2, has_dot=True),
                            month_cell("Mar", 3, has_dot=True),
                            month_cell("Apr", 4, has_dot=False),
                            {
                                "name": "Arrow Right",
                                "type": "svg_icon",
                                "iconKey": "chevron_right",
                                "iconSize": 18,
                                "iconColor": C["fg-quaternary"],
                                "layoutSizingHorizontal": "FIXED",
                                "layoutSizingVertical": "FIXED",
                                "width": 18, "height": 18,
                            },
                        ]
                    },
                    # 필터 dropdown
                    {
                        "name": "Filter Row",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "MAX",
                            "paddingLeft": 18, "paddingRight": 18, "paddingBottom": 4,
                        },
                        "children": [
                            {
                                "name": "Filter Pill",
                                "type": "frame",
                                "layoutSizingHorizontal": "HUG",
                                "fill": C["bg-secondary"],
                                "cornerRadius": 8,
                                "autoLayout": {
                                    "layoutMode": "HORIZONTAL",
                                    "itemSpacing": 4,
                                    "paddingTop": 6, "paddingBottom": 6, "paddingLeft": 10, "paddingRight": 8,
                                    "counterAxisAlignItems": "CENTER",
                                },
                                "children": [
                                    text("filter-text", "납입", size=12, weight="Medium",
                                         color=C["fg-secondary"]),
                                    {
                                        "name": "Caret",
                                        "type": "svg_icon",
                                        "iconKey": "chevron_down",
                                        "iconSize": 14,
                                        "iconColor": C["fg-tertiary"],
                                        "layoutSizingHorizontal": "FIXED",
                                        "layoutSizingVertical": "FIXED",
                                        "width": 14, "height": 14,
                                    }
                                ]
                            }
                        ]
                    },
                    # 3 stat columns row
                    {
                        "name": "Stats Row",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "fill": C["bg-secondary"],
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "itemSpacing": 0,
                            "paddingTop": 16, "paddingBottom": 16, "paddingLeft": 12, "paddingRight": 12,
                        },
                        "children": [
                            stat_col("월 납입액", "1,300,000원", value_color=C["fg-brand-primary"]),
                            stat_col("납입 완료액", "300,000원", value_color=C["fg-success-primary"]),
                            stat_col("남은 납입액", "1,000,000원", value_color=C["fg-primary"]),
                        ]
                    },
                ]
            }
        ]
    }


# ============ SECTION 4 — Transaction List ============
def date_box(day, dday, status):
    """status: missed | today | upcoming | past"""
    if status == "missed":
        bg = C["bg-error-primary"]
        text_color = C["fg-white"]
        stroke = None
    elif status == "today":
        bg = C["bg-brand-solid"]
        text_color = C["fg-white"]
        stroke = None
    elif status == "upcoming":
        bg = C["bg-secondary"]
        text_color = C["fg-secondary"]
        stroke = None
    else:  # past
        bg = C["bg-secondary"]
        text_color = C["fg-tertiary"]
        stroke = None

    box = {
        "name": f"Date Box {day}",
        "type": "frame",
        "layoutSizingHorizontal": "FIXED",
        "layoutSizingVertical": "FIXED",
        "width": 52, "height": 60,
        "fill": bg,
        "cornerRadius": 10,
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "primaryAxisAlignItems": "CENTER",
            "counterAxisAlignItems": "CENTER",
            "itemSpacing": 2,
            "paddingTop": 8, "paddingBottom": 8,
        },
        "children": [
            text("day", day, size=15, weight="Bold", color=text_color, align="CENTER", layout_sizing="FILL"),
            text("dday", dday, size=11, weight="Medium", color=text_color, align="CENTER", layout_sizing="FILL"),
        ]
    }
    return box


def cta_pill(label, variant):
    """variant: action | done"""
    if variant == "action":
        return {
            "name": "CTA Pill",
            "type": "frame",
            "layoutSizingHorizontal": "HUG",
            "fill": C["bg-brand-solid"],
            "cornerRadius": 999,
            "autoLayout": {
                "layoutMode": "HORIZONTAL",
                "paddingTop": 7, "paddingBottom": 7, "paddingLeft": 12, "paddingRight": 12,
                "counterAxisAlignItems": "CENTER",
            },
            "children": [
                text("label", label, size=12, weight="Bold", color=C["fg-white"]),
            ]
        }
    elif variant == "missed-action":
        return {
            "name": "CTA Pill",
            "type": "frame",
            "layoutSizingHorizontal": "HUG",
            "fill": C["bg-error-primary"],
            "cornerRadius": 999,
            "autoLayout": {
                "layoutMode": "HORIZONTAL",
                "paddingTop": 7, "paddingBottom": 7, "paddingLeft": 12, "paddingRight": 12,
                "counterAxisAlignItems": "CENTER",
            },
            "children": [
                text("label", label, size=12, weight="Bold", color=C["fg-white"]),
            ]
        }
    else:  # done text-only
        return text("status-text", label, size=12, weight="Medium", color=C["fg-tertiary"])


def progress_bar(round_text, status, kind):
    """round_text 'N/M회차' → fill ratio bar.
    Track 4px, fill brand/error/success based on status.
    """
    try:
        cur, total = round_text.replace("회차", "").split("/")
        ratio = int(cur) / int(total)
    except Exception:
        ratio = 0.5
    # Fill width: track 가용폭 약 240 (Info Group FILL 기준이라 측정 어렵지만 FIXED ratio가 아닌 FIXED width 계산)
    # 안전하게 track을 FILL로 두고 fill을 width 계산: assume track inner width ≈ 220 (info group total - cta)
    # Better: use 1200 base then ratio for width
    track_width = 220
    fill_width = max(int(track_width * ratio), 8)

    if kind == "미납" or status == "missed":
        fill_color = C["bg-error-primary"]
    elif status == "today":
        fill_color = C["bg-brand-solid"]
    elif kind == "지급":
        fill_color = C["bg-success-primary"]
    elif ratio >= 1.0:
        fill_color = C["bg-success-primary"]
    else:
        fill_color = C["bg-brand-solid"]

    return {
        "name": "Round Progress Track",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "FIXED",
        "height": 4,
        "cornerRadius": 999,
        "fill": C["bg-tertiary"],
        "clipsContent": False,
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "counterAxisAlignItems": "CENTER",
        },
        "children": [{
            "name": "Round Progress Fill",
            "type": "frame",
            "layoutSizingHorizontal": "FIXED",
            "layoutSizingVertical": "FIXED",
            "width": fill_width,
            "height": 4,
            "cornerRadius": 999,
            "fill": fill_color,
            "clipsContent": False,
        }]
    }


def transaction_card(day, dday, status, kind, round_text, amount, cta_label, cta_variant):
    """status: missed/today/upcoming/past, kind: 미납/납입/지급"""
    # status icon (top right next to round_text)
    if kind == "미납":
        kind_color = C["fg-error-primary"]
    elif status == "today":
        kind_color = C["fg-brand-primary"]
    else:
        kind_color = C["fg-primary"]

    card = {
        "name": f"Tx Card {day}",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "fill": {"r": 1, "g": 1, "b": 1, "a": 1},
        "stroke": C["border-card"] if status != "missed" else C["border-error"],
        "strokeWeight": 1,
        "cornerRadius": 14,
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "itemSpacing": 12,
            "paddingTop": 14, "paddingBottom": 14, "paddingLeft": 14, "paddingRight": 14,
        },
        "children": [
            # Top row: date box + info + cta
            {
                "name": "Card Top Row",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "itemSpacing": 14,
                    "counterAxisAlignItems": "CENTER",
                },
                "children": [
                    date_box(day, dday, status),
                    {
                        "name": "Info Group",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {
                            "layoutMode": "VERTICAL",
                            "itemSpacing": 4,
                        },
                        "children": [
                            text("round", f"{kind} ({round_text})", size=13, weight="SemiBold",
                                 color=kind_color, layout_sizing="FILL"),
                            text("amount", amount, size=15, weight="Bold",
                                 color=C["fg-primary"], layout_sizing="FILL"),
                        ]
                    },
                    cta_pill(cta_label, cta_variant),
                ]
            },
            # Bottom progress bar
            progress_bar(round_text, status, kind),
        ]
    }
    return card


def build_transaction_list():
    return {
        "name": "Transactions Wrap",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "fill": {"r": 0, "g": 0, "b": 0, "a": 0},
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "itemSpacing": 12,
            "paddingTop": 12, "paddingBottom": 24, "paddingLeft": 16, "paddingRight": 16,
        },
        "children": [
            # Section header: 2026년 1월 + 총 8건
            {
                "name": "List Header",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "primaryAxisAlignItems": "SPACE_BETWEEN",
                    "counterAxisAlignItems": "CENTER",
                    "paddingTop": 4, "paddingBottom": 4, "paddingLeft": 4, "paddingRight": 4,
                },
                "children": [
                    text("month-title", "2026년 1월", size=16, weight="Bold",
                         color=C["fg-primary"]),
                    text("count", "총 8건", size=13, weight="Medium",
                         color=C["fg-tertiary"]),
                ]
            },
            # 거래 카드 5개
            transaction_card("29일", "D+3", "missed", "미납",
                             "1/5회차", "100,000원", "납입 하기", "missed-action"),
            transaction_card("1일", "오늘", "today", "납입",
                             "1/5회차", "100,000원", "납입 처리 완료", "done"),
            transaction_card("2일", "D-1", "upcoming", "납입",
                             "5/5회차", "100,000원", "납입 완료", "done"),
            transaction_card("10일", "D-10", "upcoming", "납입",
                             "1/13회차", "100,000원", "선납 하기", "action"),
            transaction_card("10일", "D-10", "upcoming", "지급",
                             "1/13회차", "300,000원", "지급 예정", "done"),
        ]
    }


# ============ ROOT ============
root = {
    "_meta": {"description": "내 스테이지 모달 — 와이어프레임 기반"},
    "rootName": "imin-my-stage-modal",
    "name": "imin-my-stage-modal",
    "type": "frame",
    "width": 393,
    "height": 1500,
    "fill": C["bg-base"],
    "autoLayout": {
        "layoutMode": "VERTICAL",
        "itemSpacing": 0,
        "paddingTop": 0, "paddingBottom": 0,
    },
    "children": [
        build_modal_header(),
        build_summary_card(),
        build_schedule_card(),
        build_transaction_list(),
    ],
    "statusBar": True,
}

with open("/Users/julee/imin/figma-design-agent/scripts/my_stage_modal_blueprint.json", "w") as f:
    json.dump(root, f, ensure_ascii=False, indent=2)
print("Saved blueprint to scripts/my_stage_modal_blueprint.json")
