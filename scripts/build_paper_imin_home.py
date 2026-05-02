#!/usr/bin/env python3
"""Build Figma blueprint reproducing the Paper 'pastoral' imin home design.

Paper artboard: 1-0 (390×1796), file 'Forgiving nebula'.
Mood: pastoral / botanical (off-white #FAFAF6, sage #2E5E3E, terracotta #B84A3D).

This script keeps Paper's exact palette as raw frames (the DS purple palette
would clash with Paper's pastoral mood). Status bar is cloned from the
imin-home reference; Bottom Nav follows project template.
"""
from __future__ import annotations
import json
from pathlib import Path

# ============== DS COMPONENT KEYS ==============
LOGO_KEY = "81efeddd245e95f31a2724aa370ee54d3caf93d0"

# ============== PAPER PALETTE ==============
PALETTE = {
    "bg_base":         "#FAFAF6",
    "card_white":      "#FFFFFF",
    "card_warm_light": "#F2EFE7",
    "card_warm_med":   "#EDE9DD",
    "border":          "#E8E5DC",
    "text_primary":    "#1A1F1A",
    "text_secondary":  "#6B7264",
    "text_muted":      "#A8AAA1",
    "text_subtle":     "#9EA59A",
    "near_black":      "#1A1F1A",
    "green_deep":      "#2E5E3E",
    "green_sage":      "#9FBFA6",
    "green_mint":      "#9FE6B4",
    "red_terra":       "#B84A3D",
    "red_lightbg":     "#FBEDEA",
    "red_border":      "#F1D6D0",
    "red_deep":        "#7A2A20",
    "red_text":        "#9A4339",
    "orange_dot":      "#C7836A",
    "orange_deep":     "#8A4F3B",
    "off_white":       "#FAFAF6",
    "tab_underline":   "#1A1F1A",
}


def hex_to_rgb(h: str, a: float = 1.0) -> dict:
    h = h.lstrip("#")
    return {
        "r": int(h[0:2], 16) / 255,
        "g": int(h[2:4], 16) / 255,
        "b": int(h[4:6], 16) / 255,
        "a": a,
    }


def C(name: str, alpha: float = 1.0) -> dict:
    return hex_to_rgb(PALETTE[name], alpha)


# ============== TEXT HELPER ==============
def t(name: str, content: str, size: int, weight: str = "Bold",
      color: dict | None = None, lh: int | None = None,
      ls: float | None = None, align: str | None = None,
      sizing: str = "HUG") -> dict:
    n = {
        "name": name,
        "type": "text",
        "text": content,
        "fontSize": size,
        "fontName": {"family": "Pretendard", "style": weight},
        "fontColor": color if color is not None else C("text_primary"),
        "layoutSizingHorizontal": sizing,
    }
    if lh is not None:
        n["lineHeight"] = {"value": lh, "unit": "PIXELS"}
    if ls is not None:
        n["letterSpacing"] = {"value": ls, "unit": "PERCENT"}
    if align is not None:
        n["textAlignHorizontal"] = align
    return n


# ============== FRAME HELPER ==============
def f(name: str, *, w: int | None = None, h: int | None = None,
      fill: dict | None = None, radius: int | None = None,
      pad=None, stroke: dict | None = None, sw: float = 1.0,
      gap: int = 0, mode: str = "VERTICAL", primary: str | None = None,
      counter: str | None = None, sizing_h: str = "FILL",
      sizing_v: str = "HUG", clip: bool = False,
      children: list | None = None) -> dict:
    n = {"name": name, "type": "frame"}
    if w is not None:
        n["width"] = w
    if h is not None:
        n["height"] = h
    if fill is not None:
        n["fill"] = fill
    if radius is not None:
        n["cornerRadius"] = radius
    if stroke is not None:
        n["stroke"] = stroke
        n["strokeWeight"] = sw
        n["strokeAlign"] = "INSIDE"
    n["layoutSizingHorizontal"] = sizing_h
    n["layoutSizingVertical"] = sizing_v
    al = {"layoutMode": mode, "itemSpacing": gap}
    if pad is not None:
        if isinstance(pad, int):
            al["paddingTop"] = al["paddingBottom"] = al["paddingLeft"] = al["paddingRight"] = pad
        elif len(pad) == 2:
            v, hp = pad
            al["paddingTop"] = al["paddingBottom"] = v
            al["paddingLeft"] = al["paddingRight"] = hp
        else:
            tp, rp, bp_, lp = pad
            al["paddingTop"], al["paddingRight"] = tp, rp
            al["paddingBottom"], al["paddingLeft"] = bp_, lp
    if primary:
        al["primaryAxisAlignItems"] = primary
    if counter:
        al["counterAxisAlignItems"] = counter
    if clip:
        al["clipsContent"] = True
    n["autoLayout"] = al
    if children:
        n["children"] = children
    return n


def ic(name: str, icon_name: str, size: int = 24,
       color: dict | None = None) -> dict:
    return {
        "name": name, "type": "icon",
        "iconName": icon_name, "size": size,
        "iconColor": color if color is not None else C("text_primary"),
    }


def dot(size: int, color: dict) -> dict:
    return f("dot", w=size, h=size, sizing_h="FIXED", sizing_v="FIXED",
             fill=color, radius=size // 2 + 1)


# ============== STATUS BAR + HEADER ==============
def build_status_bar() -> dict:
    """iOS status bar — clone from reference where possible."""
    # Use clone pattern from imin-home reference. If clone fails, the bar
    # will be a simple raw frame (graceful degradation).
    return {
        "type": "clone",
        "name": "Status Bar",
        "sourceNodeId": "81:8606",
        "layoutSizingHorizontal": "FILL",
    }


def build_header() -> dict:
    return f("Header", pad=(8, 22, 12, 22), mode="HORIZONTAL",
             primary="SPACE_BETWEEN", counter="CENTER",
             fill=C("off_white"),
             children=[
        f("Logo Group", mode="HORIZONTAL", gap=2, counter="CENTER",
          sizing_h="HUG",
          children=[
            t("logo-text", "imin", 20, "ExtraBold", color=C("near_black"),
              ls=-3),
            f("dot-marker", w=6, h=6, sizing_h="FIXED", sizing_v="FIXED",
              fill=C("red_terra"), radius=3),
          ]),
        f("Header actions", mode="HORIZONTAL", gap=14, counter="CENTER",
          sizing_h="HUG",
          children=[
            f("Notification wrap", w=24, h=24, sizing_h="FIXED",
              sizing_v="FIXED", primary="CENTER", counter="CENTER",
              children=[ic("bell-icon", "bell-01", 22,
                           C("text_primary"))]),
            f("Chat wrap", w=24, h=24, sizing_h="FIXED",
              sizing_v="FIXED", primary="CENTER", counter="CENTER",
              children=[ic("chat-icon", "message-chat-circle", 22,
                           C("text_primary"))]),
          ]),
    ])


# ============== TABS ==============
def build_tabs() -> dict:
    """Underline tabs with Paper's near-black underline (not DS purple)."""
    def tab(label: str, active: bool) -> dict:
        return f(f"Tab {'Active' if active else 'Inactive'}",
                 pad=(6, 0, 8, 0), mode="VERTICAL", gap=6,
                 counter="CENTER", sizing_h="HUG",
                 children=[
            t("tab-label", label, 17,
              "ExtraBold" if active else "SemiBold",
              color=C("near_black") if active else C("text_secondary"),
              ls=-2),
            f("Underline", w=40, h=3, sizing_h="FIXED", sizing_v="FIXED",
              fill=C("near_black") if active else hex_to_rgb("#FFFFFF", a=0),
              radius=2),
        ])

    return f("Home Tabs", pad=(4, 22, 8, 22), mode="HORIZONTAL", gap=20,
             fill=C("off_white"), counter="CENTER",
             children=[tab("내 스테이지", True), tab("둘러보기", False)])


# ============== ALERT (미납) ==============
def build_alert_missed() -> dict:
    return f("Missed Alert Wrap", pad=(18, 22, 0, 22), mode="VERTICAL",
             fill=C("off_white"),
             children=[
        f("Missed Alert Card", radius=14, pad=(14, 16),
          fill=C("red_lightbg"), stroke=C("red_border"), sw=1,
          mode="HORIZONTAL", gap=12, counter="CENTER",
          children=[
            f("Alert Icon", w=32, h=32, sizing_h="FIXED", sizing_v="FIXED",
              radius=999, fill=C("red_terra"),
              primary="CENTER", counter="CENTER",
              children=[ic("alert-icon", "alert-triangle", 16,
                           C("red_lightbg"))]),
            f("Alert Text", mode="VERTICAL", gap=2, sizing_h="FILL",
              children=[
                t("alert-title", "미납 1건이 있어요", 14, "Bold",
                  color=C("red_deep"), ls=-2, sizing="FILL"),
                t("alert-sub", "4월 25일 · 동네 청년 13개월 · 100,000원",
                  12, "Medium", color=C("red_text"), ls=-1, sizing="FILL"),
              ]),
            # CTA pill — raw frame (Paper terracotta ≠ DS Destructive red)
            f("Alert CTA", radius=999, pad=(8, 12), mode="HORIZONTAL",
              gap=4, counter="CENTER", sizing_h="HUG",
              fill=C("red_terra"),
              children=[
                t("cta-text", "납입하기", 12, "Bold",
                  color=C("red_lightbg"), ls=-1),
                ic("cta-chevron", "chevron-right", 12,
                   C("red_lightbg")),
              ]),
          ]),
    ])


# ============== SUMMARY CARD ==============
def build_summary() -> dict:
    """Two-row summary: 모은 금액 / 납입 예정액."""
    def section_dot(color_name: str) -> dict:
        return f("dot-wrap", w=8, h=8, sizing_h="FIXED", sizing_v="FIXED",
                 fill=C(color_name), radius=4)

    return f("Summary Wrap", pad=(28, 24, 8, 24), mode="VERTICAL", gap=24,
             fill=C("off_white"),
             children=[
        # Header row: pill + 잔액 보기
        f("Summary Header", mode="HORIZONTAL", primary="SPACE_BETWEEN",
          counter="CENTER", sizing_h="FILL",
          children=[
            f("title-row", mode="HORIZONTAL", gap=8, counter="CENTER",
              sizing_h="HUG",
              children=[
                t("summary-title", "진행 중인 스테이지", 14, "SemiBold",
                  color=C("text_secondary"), ls=-1),
                f("count-pill", radius=999, pad=(2, 8), counter="CENTER",
                  sizing_h="HUG", fill=C("near_black"),
                  children=[
                    t("count", "3건", 11, "Bold", color=C("off_white"))
                  ]),
              ]),
            f("balance-action", mode="HORIZONTAL", gap=4, counter="CENTER",
              sizing_h="HUG",
              children=[
                t("balance-text", "잔액 보기", 12, "SemiBold",
                  color=C("text_secondary")),
                ic("eye-icon", "eye", 14, C("text_secondary")),
              ]),
          ]),
        # Money row 1 - 모은 금액
        f("Money Earned", mode="VERTICAL", gap=6, sizing_h="FILL",
          children=[
            f("label-row", mode="HORIZONTAL", gap=6, counter="CENTER",
              sizing_h="HUG",
              children=[
                section_dot("green_deep"),
                t("label-ko", "모은 금액", 12, "Bold",
                  color=C("text_primary"), ls=-1),
                t("label-en", "RECEIVED", 11, "Bold",
                  color=C("text_secondary"), ls=8),
              ]),
            f("amount-row", mode="HORIZONTAL", gap=4, counter="BASELINE",
              sizing_h="HUG",
              children=[
                t("amount", "14,420,320", 36, "ExtraBold",
                  color=C("text_primary"), ls=-3, lh=40),
                t("won", "원", 18, "Bold",
                  color=C("text_primary"), ls=-2),
              ]),
            t("amount-sub", "지금까지 3건의 스테이지에서 받았어요", 12,
              "Medium", color=C("text_secondary"), ls=-1, sizing="FILL"),
          ]),
        # Divider + Money row 2 - 납입 예정액
        f("Money Due Wrap", mode="VERTICAL", gap=14, sizing_h="FILL",
          children=[
            f("Divider", w=1, h=1, sizing_h="FILL", sizing_v="FIXED",
              fill=C("border")),
            f("Money Due", mode="VERTICAL", gap=6, sizing_h="FILL",
              children=[
                f("label-row", mode="HORIZONTAL", gap=6, counter="CENTER",
                  sizing_h="HUG",
                  children=[
                    section_dot("orange_dot"),
                    t("label-ko", "납입 예정액", 12, "Bold",
                      color=C("orange_deep"), ls=-1),
                    t("label-en", "DUE", 11, "Bold",
                      color=C("text_secondary"), ls=8),
                  ]),
                f("amount-row", mode="HORIZONTAL", primary="SPACE_BETWEEN",
                  counter="BASELINE", sizing_h="FILL",
                  children=[
                    f("amount-group", mode="HORIZONTAL", gap=4,
                      counter="BASELINE", sizing_h="HUG",
                      children=[
                        t("amount", "5,240,020", 32, "ExtraBold",
                          color=C("orange_deep"), ls=-3, lh=36),
                        t("won", "원", 16, "Bold",
                          color=C("orange_deep"), ls=-2),
                      ]),
                    t("rounds", "남은 회차 11회", 12, "Medium",
                      color=C("text_secondary"), ls=-1),
                  ]),
              ]),
          ]),
    ])


# ============== SCHEDULE (이번 달 일정) ==============
def build_day_card(*, day_label: str, day_label_color: str,
                   day_num: str, day_num_color: str,
                   status_dot: str | None, status_label: str,
                   status_color: str, amount: str, amount_color: str,
                   bg: str, border: str | None = None,
                   width: int = 104, height: int = 126,
                   day_size: int = 24, day_lh: int = 28,
                   amount_size: int = 13, day_letter_space: float = -4,
                   opacity_card: float | None = None) -> dict:
    children_top = [
        t("day-label", day_label, 11, "SemiBold",
          color=C(day_label_color), ls=4),
        t("day-num", day_num, day_size, "ExtraBold",
          color=C(day_num_color), ls=day_letter_space, lh=day_lh),
    ]
    bottom_inner = []
    if status_dot:
        bottom_inner.append(
            f("status-row", mode="HORIZONTAL", gap=5, counter="CENTER",
              sizing_h="HUG",
              children=[
                f("dot", w=5, h=5, sizing_h="FIXED", sizing_v="FIXED",
                  fill=C(status_dot), radius=3),
                t("status", status_label, 11, "SemiBold",
                  color=C(status_color)),
              ]))
    else:
        bottom_inner.append(
            t("status", status_label, 11, "SemiBold",
              color=C(status_color)))
    bottom_inner.append(
        t("amount", amount, amount_size, "Bold",
          color=C(amount_color), lh=16))

    fill = C(bg)
    if opacity_card is not None:
        # apply alpha to fill for past-card faded look
        fill = C(bg, alpha=opacity_card)

    card = f(f"Day — {day_label}", w=width, h=height, sizing_h="FIXED",
             sizing_v="FIXED", radius=18 if width == 104 else 20,
             pad=14 if width == 104 else 16, mode="VERTICAL",
             primary="SPACE_BETWEEN", fill=fill,
             stroke=C(border) if border else None,
             sw=1.5 if border == "red_terra" else 1,
             children=[
        f("top-block", mode="VERTICAL", gap=1, sizing_h="HUG",
          children=children_top),
        f("bottom-block", mode="VERTICAL", gap=2, sizing_h="HUG",
          children=bottom_inner),
    ])
    return card


def build_schedule() -> dict:
    # Header
    header = f("Schedule Header", mode="HORIZONTAL", primary="SPACE_BETWEEN",
               counter="CENTER", pad=(0, 24), sizing_h="FILL",
               children=[
        f("title-block", mode="VERTICAL", gap=2, sizing_h="HUG",
          children=[
            t("month-label", "MAY 2026", 11, "SemiBold",
              color=C("text_secondary"), ls=8),
            t("title", "이번 달 일정", 20, "ExtraBold",
              color=C("text_primary"), ls=-3, lh=24),
          ]),
        f("legend", mode="HORIZONTAL", gap=10, counter="CENTER",
          sizing_h="HUG",
          children=[
            f("legend-1", mode="HORIZONTAL", gap=4, counter="CENTER",
              sizing_h="HUG",
              children=[
                f("dot", w=6, h=6, sizing_h="FIXED", sizing_v="FIXED",
                  fill=C("green_deep"), radius=3),
                t("label", "지급", 11, "SemiBold",
                  color=C("text_secondary")),
              ]),
            f("legend-2", mode="HORIZONTAL", gap=4, counter="CENTER",
              sizing_h="HUG",
              children=[
                f("dot", w=6, h=6, sizing_h="FIXED", sizing_v="FIXED",
                  fill=C("orange_dot"), radius=3),
                t("label", "납입", 11, "SemiBold",
                  color=C("text_secondary")),
              ]),
          ]),
    ])

    # Day card scroller — 6 cards, varying state
    cards = [
        # Past completed (faded)
        build_day_card(day_label="월·MON", day_label_color="text_secondary",
                       day_num="28", day_num_color="text_primary",
                       status_dot=None, status_label="납입 완료",
                       status_color="text_secondary",
                       amount="100,000원", amount_color="text_primary",
                       bg="card_warm_light", opacity_card=0.55),
        # Overdue (red bordered)
        build_day_card(day_label="금·미납", day_label_color="red_terra",
                       day_num="25", day_num_color="red_deep",
                       status_dot=None, status_label="미납 · 4일 지남",
                       status_color="red_terra",
                       amount="−100,000원", amount_color="red_deep",
                       bg="red_lightbg", border="red_terra"),
        # Today (large dark)
        build_day_card(day_label="TODAY · 일",
                       day_label_color="green_sage",
                       day_num="02", day_num_color="off_white",
                       status_dot="green_mint", status_label="지급 예정",
                       status_color="green_mint",
                       amount="+1,300,000원", amount_color="off_white",
                       bg="near_black", width=118, height=148,
                       day_size=36, day_lh=40, amount_size=15),
        # Future 1 (수·WED 12, 납입 예정 200,000원)
        build_day_card(day_label="수·WED", day_label_color="text_secondary",
                       day_num="12", day_num_color="text_primary",
                       status_dot="orange_dot", status_label="납입 예정",
                       status_color="orange_deep",
                       amount="200,000원", amount_color="text_primary",
                       bg="card_white", border="border"),
        # Future 2 (월·MON 17, 지급 예정 +850,000원)
        build_day_card(day_label="월·MON", day_label_color="text_secondary",
                       day_num="17", day_num_color="text_primary",
                       status_dot="green_deep", status_label="지급 예정",
                       status_color="green_deep",
                       amount="+850,000원", amount_color="text_primary",
                       bg="card_white", border="border"),
        # Future 3 (목·THU 27, 납입 예정 100,000원)
        build_day_card(day_label="목·THU", day_label_color="text_secondary",
                       day_num="27", day_num_color="text_primary",
                       status_dot="orange_dot", status_label="납입 예정",
                       status_color="orange_deep",
                       amount="100,000원", amount_color="text_primary",
                       bg="card_white", border="border"),
    ]

    scroller = f("Day Card Scroll", pad=(4, 24, 8, 24), mode="HORIZONTAL",
                 gap=10, sizing_h="FILL", clip=True,
                 children=cards)

    return f("Schedule Section", pad=(28, 0, 0, 0), mode="VERTICAL",
             gap=14, fill=C("off_white"),
             children=[header, scroller])


# ============== LIMIT (참여 가능 한도) ==============
def build_limit() -> dict:
    return f("Limit Wrap", pad=(28, 22, 0, 22), mode="VERTICAL",
             fill=C("off_white"),
             children=[
        f("Limit Card", radius=22, pad=22, mode="VERTICAL", gap=18,
          fill=C("card_white"), stroke=C("border"), sw=1,
          children=[
            f("Limit Header", mode="HORIZONTAL", primary="SPACE_BETWEEN",
              counter="CENTER", sizing_h="FILL",
              children=[
                f("limit-text", mode="VERTICAL", gap=4, sizing_h="HUG",
                  children=[
                    t("label-en", "CREDIT LIMIT", 11, "SemiBold",
                      color=C("text_secondary"), ls=8),
                    t("label-ko", "참여 가능 한도", 16, "ExtraBold",
                      color=C("text_primary"), ls=-2),
                  ]),
                f("score-pill", radius=999, pad=(6, 12), mode="HORIZONTAL",
                  gap=4, counter="CENTER", sizing_h="HUG",
                  fill=C("card_warm_light"),
                  children=[
                    ic("trend-icon", "trending-up", 14,
                       C("green_deep")),
                    t("score", "신용 875점", 11, "Bold",
                      color=C("text_primary"), ls=-1),
                  ]),
              ]),
            # Bar + bottom row
            f("Bar Block", mode="VERTICAL", gap=8, sizing_h="FILL",
              children=[
                f("Bar Track", h=8, sizing_h="FILL", sizing_v="FIXED",
                  radius=999, fill=C("card_warm_light"),
                  children=[
                    f("Bar Fill", w=90, h=8, sizing_h="FIXED",
                      sizing_v="FIXED", radius=999, fill=C("green_deep")),
                  ]),
                f("Bar Footer", mode="HORIZONTAL", primary="SPACE_BETWEEN",
                  counter="BASELINE", sizing_h="FILL",
                  children=[
                    f("usage-group", mode="HORIZONTAL", gap=4,
                      counter="BASELINE", sizing_h="HUG",
                      children=[
                        t("usage-amt", "1,560만원", 18, "ExtraBold",
                          color=C("text_primary"), ls=-2),
                        t("usage-suffix", "사용 중", 12, "SemiBold",
                          color=C("text_secondary")),
                      ]),
                    t("total", "전체 5,200만원", 12, "SemiBold",
                      color=C("text_secondary")),
                  ]),
              ]),
          ]),
    ])


# ============== STAGES (참여 중인 스테이지) ==============
def build_stage_card(*, status_label: str, status_dot: str,
                     status_text_color: str, title: str, sub: str,
                     rate: str, monthly: str | None = None,
                     completed: bool = False) -> dict:
    pill_bg = "card_warm_light" if completed else "card_white"
    pill_border = "border"
    pill = f("status-pill", radius=999, pad=(6, 10), mode="HORIZONTAL",
             gap=5, counter="CENTER", sizing_h="HUG",
             fill=C(pill_bg), stroke=C(pill_border), sw=1,
             children=[
        f("dot", w=6, h=6, sizing_h="FIXED", sizing_v="FIXED",
          fill=C(status_dot), radius=3),
        t("status-text", status_label, 11, "SemiBold",
          color=C(status_text_color)),
    ])

    bottom_children = [
        f("rate-block", mode="VERTICAL", gap=2, sizing_h="HUG",
          children=[
            t("rate-label", "RATE", 10, "Bold",
              color=C("text_secondary"), ls=8),
            t("rate-value", rate, 18, "ExtraBold",
              color=C("text_primary"), ls=-2),
          ]),
    ]
    if monthly:
        bottom_children.append(
            f("monthly-block", mode="VERTICAL", gap=2, sizing_h="HUG",
              counter="MAX",
              children=[
                t("monthly-label", "월 납입", 10, "SemiBold",
                  color=C("text_secondary"), align="RIGHT"),
                t("monthly-value", monthly, 14, "Bold",
                  color=C("text_primary"), ls=-2, align="RIGHT"),
              ]))

    return f(f"Stage Card — {title[:6]}", w=240, h=200, sizing_h="FIXED",
             sizing_v="FIXED", radius=22, pad=20, mode="VERTICAL",
             primary="SPACE_BETWEEN",
             fill=C("card_white"), stroke=C("border"), sw=1,
             children=[
        f("Top Row", mode="HORIZONTAL", primary="SPACE_BETWEEN",
          counter="START", sizing_h="FILL",
          children=[
            pill,
            ic("heart-icon", "heart", 22,
               C("green_deep") if not completed else C("text_muted")),
          ]),
        f("Title Block", mode="VERTICAL", gap=4, sizing_h="FILL",
          children=[
            t("title", title, 16, "ExtraBold",
              color=C("text_primary"), ls=-2, sizing="FILL"),
            t("sub", sub, 12, "Medium",
              color=C("text_secondary"), ls=-1, sizing="FILL"),
          ]),
        f("Bottom Row", mode="HORIZONTAL", primary="SPACE_BETWEEN",
          counter="BASELINE", sizing_h="FILL",
          children=bottom_children),
    ])


def build_stages() -> dict:
    header = f("Stages Header", mode="HORIZONTAL", primary="SPACE_BETWEEN",
               counter="CENTER", pad=(0, 24), sizing_h="FILL",
               children=[
        f("title-block", mode="VERTICAL", gap=2, sizing_h="HUG",
          children=[
            t("section-en", "MY STAGES", 11, "SemiBold",
              color=C("text_secondary"), ls=8),
            t("section-ko", "참여 중인 스테이지", 18, "ExtraBold",
              color=C("text_primary"), ls=-2),
          ]),
        f("see-all", mode="HORIZONTAL", gap=4, counter="CENTER",
          sizing_h="HUG",
          children=[
            t("see-text", "전체 3", 12, "SemiBold",
              color=C("text_secondary")),
            ic("chev-right", "chevron-right", 14, C("text_secondary")),
          ]),
    ])

    cards = [
        build_stage_card(
            status_label="진행 중 · 7/13회차", status_dot="green_deep",
            status_text_color="green_deep", title="동네 청년 13개월",
            sub="매월 25일 · 13명이 함께해요", rate="5.4%",
            monthly="100,000원"),
        build_stage_card(
            status_label="지급 받음 · 완료", status_dot="text_muted",
            status_text_color="text_secondary", title="엄마들의 5명모임",
            sub="매월 17일 · 5명이 함께해요", rate="4.8%",
            monthly="—", completed=True),
        build_stage_card(
            status_label="진행 중 · 4/12회차", status_dot="green_deep",
            status_text_color="green_deep", title="가족 12개월 모임",
            sub="매월 10일 · 12명이 함께해요", rate="5.1%",
            monthly="80,000원"),
    ]

    scroller = f("Stage Card Scroll", pad=(0, 24, 8, 24), mode="HORIZONTAL",
                 gap=12, sizing_h="FILL", clip=True, children=cards)

    return f("Stages Section", pad=(28, 0, 0, 0), mode="VERTICAL", gap=14,
             fill=C("off_white"), children=[header, scroller])


# ============== ATTENDANCE ==============
def build_attendance() -> dict:
    return f("Attendance Wrap", pad=(32, 22, 0, 22), mode="VERTICAL",
             fill=C("off_white"),
             children=[
        f("Attendance Card", radius=22, pad=(18, 20), mode="HORIZONTAL",
          primary="SPACE_BETWEEN", counter="CENTER",
          fill=C("near_black"), clip=True,
          children=[
            f("Text Group", mode="VERTICAL", gap=6, sizing_h="HUG",
              children=[
                t("kicker", "DAILY · 12일째", 11, "Bold",
                  color=C("green_sage"), ls=8),
                t("title", "오늘도 들러줘서 고마워요", 18, "ExtraBold",
                  color=C("off_white"), ls=-3),
                t("sub", "출석 도장 찍고 +30P 받기", 12, "Medium",
                  color=C("text_muted"), ls=-1),
              ]),
            f("Check Circle", w=64, h=64, sizing_h="FIXED",
              sizing_v="FIXED", radius=999, fill=C("green_deep"),
              primary="CENTER", counter="CENTER",
              children=[ic("check-icon", "check", 28, C("off_white"))]),
          ]),
    ])


# ============== LOUNGE ==============
def build_lounge_card(*, color_chip_bg: str, chip_w: int, chip_h: int,
                      bg_card: str, discount: str, kicker: str,
                      title: str, price: str, original: str) -> dict:
    return f(f"Deal — {title[:6]}", w=160, sizing_h="FIXED", mode="VERTICAL",
             gap=10,
             children=[
        # Image area
        f("Image", w=160, h=160, sizing_h="FIXED", sizing_v="FIXED",
          radius=18, fill=C(bg_card), clip=True,
          children=[
            # Color chip centered
            f("Color Chip", w=chip_w, h=chip_h, sizing_h="FIXED",
              sizing_v="FIXED", fill=C(color_chip_bg), radius=8),
            # Discount pill (top-left)
            f("Discount Pill", radius=999, pad=(4, 8), sizing_h="HUG",
              fill=C("near_black"),
              children=[
                t("disc", discount, 11, "ExtraBold",
                  color=C("off_white"), ls=-1),
              ]),
          ]),
        # Text block
        f("Deal Text", pad=(0, 4), mode="VERTICAL", gap=4, sizing_h="FILL",
          children=[
            t("kicker", kicker, 12, "SemiBold",
              color=C("text_secondary"), ls=-1, sizing="FILL"),
            t("title", title, 14, "Bold",
              color=C("text_primary"), ls=-2, sizing="FILL"),
            f("price-row", mode="HORIZONTAL", gap=4, counter="BASELINE",
              sizing_h="HUG",
              children=[
                t("price", price, 15, "ExtraBold",
                  color=C("text_primary"), ls=-2),
                t("original", original, 11, "Medium",
                  color=C("text_subtle")),
              ]),
          ]),
    ])


def build_lounge() -> dict:
    header = f("Lounge Header", mode="HORIZONTAL", primary="SPACE_BETWEEN",
               counter="END", pad=(0, 24), sizing_h="FILL",
               children=[
        f("title-block", mode="VERTICAL", gap=2, sizing_h="HUG",
          children=[
            t("section-en", "LOUNGE · 보유 4,820P", 11, "SemiBold",
              color=C("text_secondary"), ls=8),
            t("section-ko", "포인트로 살 수 있어요", 20, "ExtraBold",
              color=C("text_primary"), ls=-3, lh=24),
          ]),
        f("see-all", mode="HORIZONTAL", gap=4, counter="CENTER",
          sizing_h="HUG", pad=(0, 0, 4, 0),
          children=[
            t("see-text", "전체 보기", 12, "SemiBold",
              color=C("text_secondary")),
            ic("chev-right", "chevron-right", 14, C("text_secondary")),
          ]),
    ])

    cards = [
        build_lounge_card(color_chip_bg="orange_dot", chip_w=90, chip_h=90,
                          bg_card="border", discount="−42%",
                          kicker="한정 핫딜 · 오늘 마감",
                          title="생활 라운지 키친 세트",
                          price="28,900원", original="49,800"),
        build_lounge_card(color_chip_bg="green_deep", chip_w=80, chip_h=110,
                          bg_card="card_warm_med", discount="−28%",
                          kicker="멤버 가격", title="유기농 아침 곡물",
                          price="12,400원", original="17,200"),
    ]

    scroller = f("Lounge Scroll", pad=(4, 24, 8, 24), mode="HORIZONTAL",
                 gap=12, sizing_h="FILL", clip=True, children=cards)

    return f("Lounge Section", pad=(28, 0, 0, 0), mode="VERTICAL", gap=14,
             fill=C("off_white"), children=[header, scroller])


# ============== BOTTOM NAV (Paper-styled) ==============
def build_nav_item(label: str, icon_name: str, active: bool) -> dict:
    color = C("near_black") if active else C("text_muted")
    weight = "Bold" if active else "Medium"
    children = [
        f("icon-wrap", w=24, h=24, sizing_h="FIXED", sizing_v="FIXED",
          primary="CENTER", counter="CENTER",
          children=[ic(f"{label}-icon", icon_name, 22, color)]),
        t("label", label, 11, weight, color=color, ls=-1, align="CENTER",
          sizing="FILL"),
    ]
    # Add active dot indicator (Paper has red dot on home)
    if active and label == "홈":
        children[0]["children"].append(
            f("active-dot", w=6, h=6, sizing_h="FIXED", sizing_v="FIXED",
              fill=C("red_terra"), radius=3))
    return f(f"Nav-{label}", sizing_h="FILL", sizing_v="FILL",
             mode="VERTICAL", gap=4, primary="CENTER", counter="CENTER",
             children=children)


def build_bottom_nav() -> dict:
    return f("Bottom Nav", h=82, sizing_h="FILL", sizing_v="FIXED",
             pad=(10, 0, 24, 0), mode="HORIZONTAL", primary="SPACE_BETWEEN",
             counter="CENTER", fill=C("off_white"),
             children=[
        build_nav_item("홈", "home-line", True),
        build_nav_item("라운지", "shopping-cart-01", False),
        build_nav_item("스테이지", "coins-stacked-01", False),
        build_nav_item("커뮤니티", "users-01", False),
        build_nav_item("전체", "menu-01", False),
    ])


# ============== ROOT ==============
def build_root() -> dict:
    children = [
        build_status_bar(),
        build_header(),
        build_tabs(),
        build_alert_missed(),
        build_summary(),
        build_schedule(),
        build_limit(),
        build_stages(),
        build_attendance(),
        build_lounge(),
        # spacer before bottom nav (so content doesn't touch it)
        f("Bottom Spacer", h=40, sizing_h="FILL", sizing_v="FIXED",
          fill=C("off_white")),
        build_bottom_nav(),
    ]
    return {
        "_meta": {
            "source": "/Users/julee/Desktop/imin_home_PRD.md",
            "design_source": "Paper artboard 1-0 (Forgiving nebula, 390×1796)",
            "mood": "pastoral / botanical (off-white base, sage green, terracotta)",
            "approach": "Paper-faithful raw frames; status bar cloned from imin-home; logo as DS instance post-build",
            "ds_instances": ["Logo (post-build): 81efeddd245e95f31a2724aa370ee54d3caf93d0"],
        },
        "rootName": "imin Home — Paper시안 (참여 중 유저)",
        "name": "imin Home — Paper시안 (참여 중 유저)",
        "type": "frame",
        "width": 390,
        "height": 1900,
        "fill": C("off_white"),
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "itemSpacing": 0,
            "paddingTop": 0,
            "paddingBottom": 0,
            "paddingLeft": 0,
            "paddingRight": 0,
        },
        "children": children,
    }


if __name__ == "__main__":
    bp = build_root()
    out = Path(__file__).parent / "paper_imin_home_blueprint.json"
    out.write_text(json.dumps(bp, indent=2, ensure_ascii=False))
    print(f"wrote {out}  ({out.stat().st_size:,} bytes)")
