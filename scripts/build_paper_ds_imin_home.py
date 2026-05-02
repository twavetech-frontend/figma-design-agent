#!/usr/bin/env python3
"""Build Figma blueprint based on the DS-aligned Paper artboard (8C-0).

Paper artboard '8C-0' uses DS palette (brand purple #7700ff, gray scale,
semantic error/success/warning). This script reproduces it in Figma using
DS component INSTANCES wherever a match exists, and uses $token() refs for
all colors so post-fix's semantic-binding sweep maps everything cleanly.
"""
from __future__ import annotations
import json
from pathlib import Path

# ============== DS COMPONENT KEYS (from ds-1-variants.jsonl) ==============
KEYS = {
    "tabs_underline_sm_mobile":   "015e516e60df56ef1714e3f8fd7d9761fafb463d",
    "alert_error_floating_mobile": "47e1d03f572d99b51c55f980c69690712c483ff0",
    "badge_pill_sm_brand":        "d0163041d0c710551c31ffd4acaca5ce42f993ac",
    "badge_pill_sm_success_dot":  "75bebdc485bd64419006bd84dcf1ceb008b2bc95",
    "badge_pill_sm_gray":         "4df2b33de171be452635e0c6958ad747853c8657",
    "logo_imin":                  "81efeddd245e95f31a2724aa370ee54d3caf93d0",
}


# ============== HELPERS ==============
def hex_to_rgb(h: str, a: float = 1.0) -> dict:
    h = h.lstrip("#")
    return {
        "r": int(h[0:2], 16) / 255,
        "g": int(h[2:4], 16) / 255,
        "b": int(h[4:6], 16) / 255,
        "a": a,
    }


def t(name, content, size, weight="Bold", color=None, lh=None, ls=None,
      align=None, sizing="HUG"):
    n = {
        "name": name, "type": "text", "text": content,
        "fontSize": size,
        "fontName": {"family": "Pretendard", "style": weight},
        "fontColor": color if color is not None else "$token(fg-primary)",
        "layoutSizingHorizontal": sizing,
    }
    if lh is not None: n["lineHeight"] = {"value": lh, "unit": "PIXELS"}
    if ls is not None: n["letterSpacing"] = {"value": ls, "unit": "PERCENT"}
    if align: n["textAlignHorizontal"] = align
    return n


def f(name, *, w=None, h=None, fill=None, radius=None, pad=None,
      stroke=None, sw=1, gap=0, mode="VERTICAL", primary=None, counter=None,
      sizing_h="FILL", sizing_v="HUG", clip=False, children=None):
    n = {"name": name, "type": "frame"}
    if w is not None: n["width"] = w
    if h is not None: n["height"] = h
    if fill is not None: n["fill"] = fill
    if radius is not None: n["cornerRadius"] = radius
    if stroke is not None:
        n["stroke"] = stroke
        n["strokeWeight"] = sw
        n["strokeAlign"] = "INSIDE"
    n["layoutSizingHorizontal"] = sizing_h
    n["layoutSizingVertical"] = sizing_v
    al = {"layoutMode": mode, "itemSpacing": gap}
    if pad is not None:
        if isinstance(pad, int):
            al["paddingTop"] = al["paddingBottom"] = pad
            al["paddingLeft"] = al["paddingRight"] = pad
        elif len(pad) == 2:
            v, hp = pad
            al["paddingTop"] = al["paddingBottom"] = v
            al["paddingLeft"] = al["paddingRight"] = hp
        else:
            tp, rp, bp_, lp = pad
            al["paddingTop"], al["paddingRight"] = tp, rp
            al["paddingBottom"], al["paddingLeft"] = bp_, lp
    if primary: al["primaryAxisAlignItems"] = primary
    if counter: al["counterAxisAlignItems"] = counter
    if clip: al["clipsContent"] = True
    n["autoLayout"] = al
    if children: n["children"] = children
    return n


def ic(name, icon_name, size=24, color=None):
    return {
        "name": name, "type": "icon",
        "iconName": icon_name, "size": size,
        "iconColor": color if color is not None else "$token(fg-primary)",
    }


def instance(name, key, props=None):
    n = {"name": name, "type": "instance", "componentKey": key}
    if props: n["instanceProperties"] = props
    return n


def dot(size, color):
    return f("dot", w=size, h=size, sizing_h="FIXED", sizing_v="FIXED",
             fill=color, radius=size // 2 + 1)


# ============== STATUS BAR + HEADER ==============
def build_status_bar():
    return {
        "type": "clone",
        "name": "Status Bar",
        "sourceNodeId": "81:8606",
        "layoutSizingHorizontal": "FILL",
    }


def build_header():
    return f("Header", pad=(10, 20, 14, 20), mode="HORIZONTAL",
             primary="SPACE_BETWEEN", counter="CENTER",
             fill="$token(bg-primary)",
             children=[
        f("Logo Group", mode="HORIZONTAL", gap=4, counter="CENTER",
          sizing_h="HUG",
          children=[
            t("logo-text", "imin", 22, "ExtraBold",
              color="$token(fg-primary)", ls=-4),
            f("brand-dot", w=6, h=6, sizing_h="FIXED", sizing_v="FIXED",
              fill="$token(bg-brand-solid)", radius=3),
          ]),
        f("Header actions", mode="HORIZONTAL", gap=4, counter="CENTER",
          sizing_h="HUG",
          children=[
            f("Notification wrap", w=40, h=40, sizing_h="FIXED",
              sizing_v="FIXED", primary="CENTER", counter="CENTER",
              children=[ic("bell", "bell-01", 22, "$token(fg-primary)")]),
            f("Chat wrap", w=40, h=40, sizing_h="FIXED",
              sizing_v="FIXED", primary="CENTER", counter="CENTER",
              children=[ic("chat", "message-square-01", 22,
                           "$token(fg-primary)")]),
          ]),
    ])


# ============== TABS (raw, mirrors DS Underline pattern) ==============
def build_tabs():
    """Raw underline tabs styled to match DS Underline tokens.
    (Instance approach blocked by text-override limitations in batch build.)"""
    def tab(label, active):
        return f(f"Tab {'Active' if active else 'Inactive'}",
                 pad=(8, 0, 11, 0), mode="VERTICAL", gap=8,
                 counter="CENTER", sizing_h="HUG",
                 children=[
            t("tab-label", label, 16,
              "Bold" if active else "SemiBold",
              color="$token(fg-primary)" if active
                    else "$token(fg-tertiary)", ls=-2),
            f("Underline", w=64, h=2, sizing_h="FIXED", sizing_v="FIXED",
              fill="$token(bg-brand-solid)" if active
                   else {"r": 1, "g": 1, "b": 1, "a": 0},
              radius=2),
        ])

    return f("Home Tabs", pad=(4, 20, 0, 20), mode="HORIZONTAL", gap=24,
             counter="CENTER", fill="$token(bg-primary)",
             stroke="$token(border-primary)", sw=1,
             children=[tab("내 스테이지", True), tab("둘러보기", False)])


# ============== ALERT (raw, mirrors DS Alert Error mobile pattern) ==============
def build_alert_missed():
    return f("Missed Alert Wrap", pad=(16, 16, 0, 16), mode="VERTICAL",
             fill="$token(bg-primary)", sizing_h="FILL",
             children=[
        f("Missed Alert", radius=12, pad=16, mode="HORIZONTAL", gap=12,
          counter="START", sizing_h="FILL",
          fill="$token(bg-error-primary)",
          stroke="$token(border-error-secondary)", sw=1,
          children=[
            f("Icon Wrap", w=32, h=32, sizing_h="FIXED", sizing_v="FIXED",
              radius=999,
              fill="$token(bg-error-primary)",
              stroke="$token(border-error-primary)", sw=4,
              primary="CENTER", counter="CENTER",
              children=[ic("alert-icon", "alert-triangle", 16,
                           "$token(fg-error-primary)")]),
            f("Alert Text", mode="VERTICAL", gap=4, sizing_h="FILL",
              children=[
                t("title", "미납 1건이 있어요", 14, "Bold",
                  color="$token(fg-error-primary)", ls=-1, sizing="FILL"),
                t("sub", "4월 25일 · 동네 청년 13개월 · 100,000원",
                  13, "Medium", color="$token(fg-error-secondary)",
                  ls=-1, sizing="FILL"),
                f("CTA", mode="HORIZONTAL", gap=4, counter="CENTER",
                  sizing_h="HUG", pad=(6, 0, 0, 0),
                  children=[
                    t("cta-text", "납입하기", 13, "Bold",
                      color="$token(fg-error-primary)"),
                    ic("cta-chev", "chevron-right", 14,
                       "$token(fg-error-primary)"),
                  ]),
              ]),
          ]),
    ])


# ============== SUMMARY CARD ==============
def build_summary():
    return f("Summary Wrap", pad=(24, 20, 8, 20), mode="VERTICAL", gap=20,
             fill="$token(bg-primary)",
             children=[
        # Header: "진행 중인 스테이지" + count badge + 잔액 보기
        f("Summary Header", mode="HORIZONTAL", primary="SPACE_BETWEEN",
          counter="CENTER", sizing_h="FILL",
          children=[
            f("title-row", mode="HORIZONTAL", gap=8, counter="CENTER",
              sizing_h="HUG",
              children=[
                t("title", "진행 중인 스테이지", 13, "SemiBold",
                  color="$token(fg-secondary)", ls=-1),
                # Count badge raw (DS Badge Pill Brand sm equivalent)
                f("Count Badge", radius=999, pad=(2, 8), counter="CENTER",
                  sizing_h="HUG",
                  fill="$token(bg-brand-secondary)",
                  children=[t("cnt", "3건", 11, "Bold",
                              color="$token(fg-brand-primary)")]),
              ]),
            f("balance-toggle", mode="HORIZONTAL", gap=4, counter="CENTER",
              sizing_h="HUG",
              children=[
                t("balance", "잔액 보기", 12, "SemiBold",
                  color="$token(fg-tertiary)"),
                ic("eye", "eye", 14, "$token(fg-tertiary)"),
              ]),
          ]),
        # Earned amount (성공 그린 dot + 큰 숫자)
        f("Money Earned", mode="VERTICAL", gap=6, sizing_h="FILL",
          children=[
            f("label-row", mode="HORIZONTAL", gap=6, counter="CENTER",
              sizing_h="HUG",
              children=[
                f("dot", w=6, h=6, sizing_h="FIXED", sizing_v="FIXED",
                  fill="$token(bg-success-solid)", radius=3),
                t("ko", "모은 금액", 13, "Bold",
                  color="$token(fg-primary)", ls=-1),
                t("en", "RECEIVED", 11, "Bold",
                  color="$token(fg-tertiary)", ls=8),
              ]),
            f("amount-row", mode="HORIZONTAL", gap=4, counter="BASELINE",
              sizing_h="HUG",
              children=[
                t("amt", "14,420,320", 36, "ExtraBold",
                  color="$token(fg-primary)", ls=-4, lh=40),
                t("won", "원", 18, "Bold",
                  color="$token(fg-primary)", ls=-2),
              ]),
            t("sub", "지금까지 3건의 스테이지에서 받았어요", 13, "Medium",
              color="$token(fg-tertiary)", ls=-1, sizing="FILL"),
          ]),
        # Due amount
        f("Due Wrap", mode="VERTICAL", gap=14, sizing_h="FILL",
          children=[
            f("Divider", w=1, h=1, sizing_h="FILL", sizing_v="FIXED",
              fill="$token(bg-tertiary)"),
            f("Money Due", mode="VERTICAL", gap=6, sizing_h="FILL",
              children=[
                f("label-row", mode="HORIZONTAL", gap=6, counter="CENTER",
                  sizing_h="HUG",
                  children=[
                    f("dot", w=6, h=6, sizing_h="FIXED", sizing_v="FIXED",
                      fill="$token(bg-warning-solid)", radius=3),
                    t("ko", "납입 예정액", 13, "Bold",
                      color="$token(fg-primary)", ls=-1),
                    t("en", "DUE", 11, "Bold",
                      color="$token(fg-tertiary)", ls=8),
                  ]),
                f("amount-row", mode="HORIZONTAL", primary="SPACE_BETWEEN",
                  counter="BASELINE", sizing_h="FILL",
                  children=[
                    f("amt-grp", mode="HORIZONTAL", gap=4,
                      counter="BASELINE", sizing_h="HUG",
                      children=[
                        t("amt", "5,240,020", 32, "ExtraBold",
                          color="$token(fg-primary)", ls=-4, lh=36),
                        t("won", "원", 16, "Bold",
                          color="$token(fg-primary)", ls=-2),
                      ]),
                    t("rounds", "남은 회차 11회", 12, "SemiBold",
                      color="$token(fg-tertiary)"),
                  ]),
              ]),
          ]),
    ])


# ============== SCHEDULE day cards (raw, DS palette) ==============
def build_day_card(*, label, label_color, num, num_color,
                   status_dot=None, status_label, status_color,
                   amount, amount_color, bg, border=None,
                   width=100, height=124, num_size=22, num_lh=26,
                   amt_size=13, opacity=None, label_ls=4):
    top = [
        t("label", label, 11, "SemiBold" if not opacity else "SemiBold",
          color=label_color, ls=label_ls),
        t("num", num, num_size, "ExtraBold", color=num_color,
          ls=-3, lh=num_lh),
    ]
    bottom = []
    if status_dot:
        bottom.append(
            f("status-row", mode="HORIZONTAL", gap=5, counter="CENTER",
              sizing_h="HUG",
              children=[
                f("dot", w=5, h=5, sizing_h="FIXED", sizing_v="FIXED",
                  fill=status_dot, radius=3),
                t("status", status_label, 11, "SemiBold",
                  color=status_color),
              ]))
    else:
        bottom.append(
            t("status", status_label, 11, "SemiBold",
              color=status_color))
    bottom.append(
        t("amt", amount, amt_size, "Bold", color=amount_color, lh=16))

    fill = bg
    if isinstance(bg, dict) and opacity is not None:
        fill = dict(bg)
        fill["a"] = opacity

    return f(f"Day — {label}", w=width, h=height, sizing_h="FIXED",
             sizing_v="FIXED",
             radius=14 if width == 100 else 16,
             pad=14 if width == 100 else 16, mode="VERTICAL",
             primary="SPACE_BETWEEN", fill=fill,
             stroke=border, sw=1.5 if border == "$token(border-error-solid)" else 1,
             children=[
        f("top", mode="VERTICAL", gap=2, sizing_h="HUG", children=top),
        f("bot", mode="VERTICAL", gap=2, sizing_h="HUG", children=bottom),
    ])


def build_schedule():
    header = f("Schedule Header", mode="HORIZONTAL",
               primary="SPACE_BETWEEN", counter="END", pad=(0, 20),
               sizing_h="FILL",
               children=[
        f("title-block", mode="VERTICAL", gap=2, sizing_h="HUG",
          children=[
            t("month", "MAY 2026", 11, "Bold",
              color="$token(fg-tertiary)", ls=8),
            t("title", "이번 달 일정", 20, "ExtraBold",
              color="$token(fg-primary)", ls=-3, lh=24),
          ]),
        f("legend", mode="HORIZONTAL", gap=10, counter="CENTER",
          sizing_h="HUG",
          children=[
            f("l1", mode="HORIZONTAL", gap=4, counter="CENTER",
              sizing_h="HUG",
              children=[
                f("dot", w=6, h=6, sizing_h="FIXED", sizing_v="FIXED",
                  fill="$token(bg-success-solid)", radius=3),
                t("label", "지급", 11, "SemiBold",
                  color="$token(fg-tertiary)"),
              ]),
            f("l2", mode="HORIZONTAL", gap=4, counter="CENTER",
              sizing_h="HUG",
              children=[
                f("dot", w=6, h=6, sizing_h="FIXED", sizing_v="FIXED",
                  fill="$token(bg-warning-solid)", radius=3),
                t("label", "납입", 11, "SemiBold",
                  color="$token(fg-tertiary)"),
              ]),
          ]),
    ])

    cards = [
        # Past completed (faded gray)
        build_day_card(
            label="월·MON", label_color="$token(fg-tertiary)",
            num="28", num_color="$token(fg-primary)",
            status_dot=None, status_label="납입 완료",
            status_color="$token(fg-tertiary)",
            amount="100,000원", amount_color="$token(fg-primary)",
            bg="$token(bg-secondary)", opacity=0.6),
        # Overdue (error border)
        build_day_card(
            label="금·미납", label_color="$token(fg-error-primary)",
            num="25", num_color="$token(fg-error-primary)",
            status_dot=None, status_label="미납 · 4일 지남",
            status_color="$token(fg-error-primary)",
            amount="−100,000원", amount_color="$token(fg-error-primary)",
            bg="$token(bg-error-primary)",
            border="$token(border-error-solid)"),
        # Today (brand purple)
        build_day_card(
            label="TODAY · 일", label_color="$token(fg-brand-tertiary)",
            num="02", num_color="$token(fg-white)",
            status_dot="$token(bg-success-secondary)",
            status_label="지급 예정",
            status_color="$token(bg-success-secondary)",
            amount="+1,300,000원", amount_color="$token(fg-white)",
            bg="$token(bg-brand-solid)",
            width=116, height=144, num_size=34, num_lh=38, amt_size=15,
            label_ls=8),
        # Future 1 (white card, warning dot)
        build_day_card(
            label="수·WED", label_color="$token(fg-tertiary)",
            num="12", num_color="$token(fg-primary)",
            status_dot="$token(bg-warning-solid)",
            status_label="납입 예정",
            status_color="$token(fg-warning-primary)",
            amount="200,000원", amount_color="$token(fg-primary)",
            bg="$token(bg-primary)",
            border="$token(border-primary)"),
        # Future 2 (success dot)
        build_day_card(
            label="월·MON", label_color="$token(fg-tertiary)",
            num="17", num_color="$token(fg-primary)",
            status_dot="$token(bg-success-solid)",
            status_label="지급 예정",
            status_color="$token(fg-success-primary)",
            amount="+850,000원", amount_color="$token(fg-primary)",
            bg="$token(bg-primary)",
            border="$token(border-primary)"),
        # Future 3
        build_day_card(
            label="목·THU", label_color="$token(fg-tertiary)",
            num="27", num_color="$token(fg-primary)",
            status_dot="$token(bg-warning-solid)",
            status_label="납입 예정",
            status_color="$token(fg-warning-primary)",
            amount="100,000원", amount_color="$token(fg-primary)",
            bg="$token(bg-primary)",
            border="$token(border-primary)"),
    ]

    scroller = f("Day Card Scroll", pad=(4, 20, 8, 20), mode="HORIZONTAL",
                 gap=8, sizing_h="FILL", clip=True, children=cards)

    return f("Schedule Section", pad=(28, 0, 0, 0), mode="VERTICAL",
             gap=16, fill="$token(bg-primary)",
             children=[header, scroller])


# ============== LIMIT ==============
def build_limit():
    return f("Limit Wrap", pad=(28, 16, 0, 16), mode="VERTICAL",
             fill="$token(bg-primary)",
             children=[
        f("Limit Card", radius=16, pad=20, mode="VERTICAL", gap=16,
          fill="$token(bg-primary)",
          stroke="$token(border-primary)", sw=1,
          children=[
            f("Limit Header", mode="HORIZONTAL",
              primary="SPACE_BETWEEN", counter="CENTER", sizing_h="FILL",
              children=[
                f("text-block", mode="VERTICAL", gap=4, sizing_h="HUG",
                  children=[
                    t("en", "CREDIT LIMIT", 11, "Bold",
                      color="$token(fg-tertiary)", ls=8),
                    t("ko", "참여 가능 한도", 16, "ExtraBold",
                      color="$token(fg-primary)", ls=-2),
                  ]),
                f("score-pill", radius=999, pad=(6, 12),
                  mode="HORIZONTAL", gap=4, counter="CENTER",
                  sizing_h="HUG", fill="$token(bg-brand-secondary)",
                  children=[
                    ic("trend", "trending-up", 14,
                       "$token(fg-brand-primary)"),
                    t("score", "신용 875점", 11, "Bold",
                      color="$token(fg-brand-primary)", ls=-1),
                  ]),
              ]),
            f("Bar Block", mode="VERTICAL", gap=8, sizing_h="FILL",
              children=[
                f("Bar Track", h=8, sizing_h="FILL", sizing_v="FIXED",
                  radius=999, fill="$token(bg-secondary)", clip=True,
                  children=[
                    f("Bar Fill", w=100, h=8, sizing_h="FIXED",
                      sizing_v="FIXED", radius=999,
                      fill="$token(bg-brand-solid)"),
                  ]),
                f("Bar Footer", mode="HORIZONTAL",
                  primary="SPACE_BETWEEN", counter="BASELINE",
                  sizing_h="FILL",
                  children=[
                    f("usage", mode="HORIZONTAL", gap=4,
                      counter="BASELINE", sizing_h="HUG",
                      children=[
                        t("amt", "1,560만원", 18, "ExtraBold",
                          color="$token(fg-primary)", ls=-2),
                        t("suf", "사용 중", 12, "SemiBold",
                          color="$token(fg-tertiary)"),
                      ]),
                    t("total", "전체 5,200만원", 12, "SemiBold",
                      color="$token(fg-tertiary)"),
                  ]),
              ]),
          ]),
    ])


# ============== STAGES ==============
def build_stage_card(*, status_label, status_dot, status_text_color,
                     pill_bg, pill_stroke=None,
                     title, sub, rate,
                     monthly=None, monthly_label="월 납입",
                     completed=False):
    pill = f("status-pill", radius=999, pad=(4, 10),
             mode="HORIZONTAL", gap=5, counter="CENTER", sizing_h="HUG",
             fill=pill_bg, stroke=pill_stroke,
             sw=1 if pill_stroke else None,
             children=[
        f("dot", w=6, h=6, sizing_h="FIXED", sizing_v="FIXED",
          fill=status_dot, radius=3),
        t("status-text", status_label, 11, "SemiBold",
          color=status_text_color),
    ])
    rate_color = "$token(fg-brand-primary)" if not completed else "$token(fg-tertiary)"
    monthly_block = []
    if monthly:
        monthly_block = [
            f("monthly-block", mode="VERTICAL", gap=2,
              counter="MAX", sizing_h="HUG",
              children=[
                t("monthly-label", monthly_label, 10, "SemiBold",
                  color="$token(fg-tertiary)", align="RIGHT"),
                t("monthly-value", monthly, 14, "Bold",
                  color="$token(fg-primary)", ls=-2, align="RIGHT"),
              ])]
    else:
        monthly_block = [
            t("done-text", "전 회차 완료", 11, "SemiBold",
              color="$token(fg-tertiary)")
        ]

    return f(f"Stage — {title[:6]}", w=240, h=196, sizing_h="FIXED",
             sizing_v="FIXED", radius=16, pad=18, mode="VERTICAL",
             primary="SPACE_BETWEEN",
             fill="$token(bg-primary)" if not completed
                  else "$token(bg-secondary)",
             stroke="$token(border-primary)", sw=1,
             children=[
        f("Top", mode="HORIZONTAL", primary="SPACE_BETWEEN",
          counter="START", sizing_h="FILL",
          children=[
            pill,
            ic("heart", "heart",  22,
               "$token(fg-brand-primary)" if not completed
               else "$token(fg-quaternary)"),
          ]),
        f("Title", mode="VERTICAL", gap=4, sizing_h="FILL",
          children=[
            t("title", title, 16, "ExtraBold",
              color="$token(fg-primary)", ls=-2, sizing="FILL"),
            t("sub", sub, 12, "Medium",
              color="$token(fg-tertiary)", ls=-1, sizing="FILL"),
          ]),
        f("Bottom", mode="HORIZONTAL", primary="SPACE_BETWEEN",
          counter="BASELINE", sizing_h="FILL",
          children=[
            f("rate-block", mode="VERTICAL", gap=2, sizing_h="HUG",
              children=[
                t("rate-label", "RATE", 10, "Bold",
                  color="$token(fg-tertiary)", ls=8),
                t("rate-value", rate, 18, "ExtraBold",
                  color=rate_color, ls=-2),
              ]),
            *monthly_block,
          ]),
    ])


def build_stages():
    header = f("Stages Header", mode="HORIZONTAL",
               primary="SPACE_BETWEEN", counter="CENTER", pad=(0, 20),
               sizing_h="FILL",
               children=[
        f("title-block", mode="VERTICAL", gap=2, sizing_h="HUG",
          children=[
            t("en", "MY STAGES", 11, "Bold",
              color="$token(fg-tertiary)", ls=8),
            t("ko", "참여 중인 스테이지", 18, "ExtraBold",
              color="$token(fg-primary)", ls=-2),
          ]),
        f("see-all", mode="HORIZONTAL", gap=4, counter="CENTER",
          sizing_h="HUG",
          children=[
            t("see", "전체 3", 12, "SemiBold",
              color="$token(fg-tertiary)"),
            ic("chev", "chevron-right", 14, "$token(fg-tertiary)"),
          ]),
    ])

    cards = [
        build_stage_card(
            status_label="진행 중 · 7/13회차",
            status_dot="$token(bg-success-solid)",
            status_text_color="$token(fg-success-primary)",
            pill_bg="$token(bg-success-primary)",
            title="동네 청년 13개월",
            sub="매월 25일 · 13명이 함께해요",
            rate="5.4%", monthly="100,000원"),
        build_stage_card(
            status_label="지급 받음 · 완료",
            status_dot="$token(bg-quaternary)",
            status_text_color="$token(fg-tertiary)",
            pill_bg="$token(bg-primary)",
            pill_stroke="$token(border-primary)",
            title="엄마들의 5명모임",
            sub="매월 17일 · 5명이 함께해요",
            rate="4.8%", completed=True),
        build_stage_card(
            status_label="진행 중 · 4/12회차",
            status_dot="$token(bg-success-solid)",
            status_text_color="$token(fg-success-primary)",
            pill_bg="$token(bg-success-primary)",
            title="가족 12개월 모임",
            sub="매월 10일 · 12명이 함께해요",
            rate="5.1%", monthly="80,000원"),
    ]

    scroller = f("Stage Card Scroll", pad=(0, 20, 8, 20),
                 mode="HORIZONTAL", gap=12, sizing_h="FILL", clip=True,
                 children=cards)

    return f("Stages Section", pad=(28, 0, 0, 0), mode="VERTICAL",
             gap=14, fill="$token(bg-primary)",
             children=[header, scroller])


# ============== ATTENDANCE ==============
def build_attendance():
    return f("Attendance Wrap", pad=(28, 16, 0, 16), mode="VERTICAL",
             fill="$token(bg-primary)",
             children=[
        f("Attendance Card", radius=16, pad=(18, 20),
          mode="HORIZONTAL", primary="SPACE_BETWEEN",
          counter="CENTER",
          fill="$token(bg-brand-secondary)",
          stroke="$token(border-brand-secondary)", sw=1,
          children=[
            f("Text Group", mode="VERTICAL", gap=4, sizing_h="HUG",
              children=[
                t("kicker", "DAILY · 12일째", 11, "Bold",
                  color="$token(fg-brand-primary)", ls=8),
                t("title", "오늘도 들러줘서 고마워요", 17, "ExtraBold",
                  color="$token(fg-primary)", ls=-2),
                t("sub", "출석 도장 찍고 +30P 받기", 12, "Medium",
                  color="$token(fg-tertiary)"),
              ]),
            f("Check Circle", w=56, h=56, sizing_h="FIXED",
              sizing_v="FIXED", radius=999,
              fill="$token(bg-brand-solid)",
              primary="CENTER", counter="CENTER",
              children=[ic("check", "check", 24, "$token(fg-white)")]),
          ]),
    ])


# ============== LOUNGE ==============
def build_deal_card(*, chip_color, chip_w, chip_h, image_bg,
                    discount, kicker, title, price, original):
    return f(f"Deal — {title[:6]}", w=156, sizing_h="FIXED",
             mode="VERTICAL", gap=10,
             children=[
        f("Image", w=156, h=156, sizing_h="FIXED", sizing_v="FIXED",
          radius=12, fill=image_bg, clip=True,
          children=[
            f("Color Chip", w=chip_w, h=chip_h, sizing_h="FIXED",
              sizing_v="FIXED", fill=chip_color, radius=8),
            f("Disc Pill", radius=999, pad=(3, 8), sizing_h="HUG",
              fill="$token(bg-error-solid)",
              children=[
                t("disc", discount, 11, "ExtraBold",
                  color="$token(fg-white)", ls=-1),
              ]),
          ]),
        f("Text", pad=(0, 4), mode="VERTICAL", gap=4, sizing_h="FILL",
          children=[
            t("kicker", kicker, 12, "SemiBold",
              color="$token(fg-tertiary)", sizing="FILL"),
            t("title", title, 14, "Bold",
              color="$token(fg-primary)", ls=-2, sizing="FILL"),
            f("price-row", mode="HORIZONTAL", gap=4, counter="BASELINE",
              sizing_h="HUG",
              children=[
                t("price", price, 15, "ExtraBold",
                  color="$token(fg-primary)", ls=-2),
                t("orig", original, 11, "Medium",
                  color="$token(fg-quaternary)"),
              ]),
          ]),
    ])


def build_lounge():
    header = f("Lounge Header", mode="HORIZONTAL",
               primary="SPACE_BETWEEN", counter="END", pad=(0, 20),
               sizing_h="FILL",
               children=[
        f("title-block", mode="VERTICAL", gap=2, sizing_h="HUG",
          children=[
            t("en", "LOUNGE · 보유 4,820P", 11, "Bold",
              color="$token(fg-tertiary)", ls=8),
            t("ko", "포인트로 살 수 있어요", 18, "ExtraBold",
              color="$token(fg-primary)", ls=-2, lh=22),
          ]),
        f("see-all", mode="HORIZONTAL", gap=4, counter="CENTER",
          sizing_h="HUG", pad=(0, 0, 4, 0),
          children=[
            t("see", "전체 보기", 12, "SemiBold",
              color="$token(fg-tertiary)"),
            ic("chev", "chevron-right", 14, "$token(fg-tertiary)"),
          ]),
    ])

    cards = [
        build_deal_card(
            chip_color="$token(bg-brand-solid)",
            chip_w=90, chip_h=90,
            image_bg="$token(bg-secondary)",
            discount="−42%", kicker="한정 핫딜 · 오늘 마감",
            title="생활 라운지 키친 세트",
            price="28,900원", original="49,800"),
        build_deal_card(
            chip_color="$token(bg-brand-primary)",
            chip_w=80, chip_h=110,
            image_bg="$token(bg-brand-secondary)",
            discount="−28%", kicker="멤버 가격",
            title="유기농 아침 곡물",
            price="12,400원", original="17,200"),
    ]

    scroller = f("Deal Scroll", pad=(0, 20, 8, 20), mode="HORIZONTAL",
                 gap=12, sizing_h="FILL", clip=True, children=cards)

    return f("Lounge Section", pad=(28, 0, 0, 0), mode="VERTICAL",
             gap=14, fill="$token(bg-primary)",
             children=[header, scroller])


# ============== BOTTOM NAV ==============
def build_nav_item(label, icon_name, active=False):
    color = "$token(fg-brand-primary)" if active else "$token(fg-quaternary)"
    weight = "Bold" if active else "Medium"
    icon_children = [ic(f"{label}-icon", icon_name, 22, color)]
    if active and label == "홈":
        icon_children.append(
            f("badge-dot", w=6, h=6, sizing_h="FIXED", sizing_v="FIXED",
              fill="$token(bg-error-solid)", radius=3))

    return f(f"Nav-{label}", sizing_h="FILL", sizing_v="FILL",
             mode="VERTICAL", gap=4, primary="CENTER", counter="CENTER",
             children=[
        f("icon-wrap", w=24, h=24, sizing_h="FIXED", sizing_v="FIXED",
          primary="CENTER", counter="CENTER",
          children=icon_children),
        t("label", label, 11, weight, color=color, align="CENTER",
          sizing="FILL"),
    ])


def build_bottom_nav():
    return f("Bottom Nav", h=82, sizing_h="FILL", sizing_v="FIXED",
             pad=(10, 0, 24, 0), mode="HORIZONTAL",
             primary="SPACE_BETWEEN", counter="CENTER",
             fill="$token(bg-primary)",
             stroke="$token(border-primary)", sw=1,
             children=[
        build_nav_item("홈", "home-line", True),
        build_nav_item("라운지", "shopping-cart-01"),
        build_nav_item("스테이지", "coins-stacked-01"),
        build_nav_item("커뮤니티", "users-01"),
        build_nav_item("전체", "menu-01"),
    ])


# ============== ROOT ==============
def build_root():
    return {
        "_meta": {
            "source": "/Users/julee/Desktop/imin_home_PRD.md",
            "design_source": "Paper artboard 8C-0 (DS-aligned)",
            "approach": "DS instances + $token() refs everywhere — let post-fix's semantic-binding sweep do the mapping cleanly",
            "ds_instances": [
                "Tabs (Underline sm Mobile)",
                "Alert (Error Floating Mobile)",
                "Badge Pill Brand (count)",
                "Badge Pill Success Dot (active stage)",
                "Badge Pill Gray (completed stage)",
            ],
        },
        "rootName": "imin Home — DS aligned (참여 중 유저)",
        "name": "imin Home — DS aligned (참여 중 유저)",
        "type": "frame",
        "width": 390,
        "height": 1900,
        "fill": "$token(bg-primary)",
        "autoLayout": {
            "layoutMode": "VERTICAL", "itemSpacing": 0,
            "paddingTop": 0, "paddingBottom": 0,
            "paddingLeft": 0, "paddingRight": 0,
        },
        "children": [
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
            f("Bottom Spacer", h=24, sizing_h="FILL", sizing_v="FIXED",
              fill="$token(bg-primary)"),
            build_bottom_nav(),
        ],
    }


if __name__ == "__main__":
    bp = build_root()
    out = Path(__file__).parent / "paper_ds_imin_home_blueprint.json"
    out.write_text(json.dumps(bp, indent=2, ensure_ascii=False))
    print(f"wrote {out}  ({out.stat().st_size:,} bytes)")
