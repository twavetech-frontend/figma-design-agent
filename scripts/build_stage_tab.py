"""Build 'stage' screen — REINTERPRETED from wireframe (16805:68746).

Wireframe = INFORMATION STRUCTURE only. Do NOT copy layout 1:1.
Apply imin DS verified patterns + visual hierarchy:
  - Card #1 = "가장 추천" → Premium CTA Card pattern (brand-section purple bg + alpha-white sub-components)
  - Card #2~#3 = "다른 옵션" → secondary cards (bg-secondary + RoundSelectorGrid)

Information structure extracted:
  - 추천 / 직접 underline tabs
  - Filter conditions (월 납입 / 목돈 시점 / 납입 기간)
  - Maker avatar group
  - 3 stage option cards with 1~13 round selector + payout/interest/benefit
  - Legal footer
"""
import copy
import json

# --- DS semantic raw values (v2 verified) ---
def rgb(r, g, b, a=1):
    return {"r": r/255, "g": g/255, "b": b/255, "a": a}

BG_PRIMARY     = rgb(0xff, 0xff, 0xff)
BG_SECONDARY   = rgb(0xf3, 0xf4, 0xf6)
BG_TERTIARY    = rgb(0xe6, 0xe8, 0xea)
BG_BRAND_PRI   = rgb(0xf4, 0xec, 0xff)
BG_BRAND_SEC   = rgb(0xe6, 0xd4, 0xff)
BG_BRAND_SEC_HR= rgb(0x52, 0x00, 0xb0)  # bg-brand-section (어두운 보라)
BG_BRAND_SOLID = rgb(0x77, 0x00, 0xff)
TEXT_PRIMARY   = rgb(0x2c, 0x37, 0x44)
TEXT_BRAND     = rgb(0x52, 0x00, 0xb0)
TEXT_BRAND_PRI = rgb(0x6a, 0x00, 0xe0)
TEXT_WHITE     = rgb(1, 1, 1)
ALPHA_WHITE_70 = rgb(1, 1, 1, 0.7)
ALPHA_WHITE_30 = rgb(1, 1, 1, 0.3)
ALPHA_WHITE_20 = rgb(1, 1, 1, 0.2)
ALPHA_WHITE_10 = rgb(1, 1, 1, 0.1)
GREY_E6        = rgb(0xe6, 0xe8, 0xea)  # solid grey for slider/stepper btn
FG_SECONDARY   = rgb(0x68, 0x70, 0x79)
FG_QUATERNARY  = rgb(0x9b, 0xa1, 0xae)
BORDER_SEC     = rgb(0xe6, 0xe8, 0xea)
BORDER_PRI     = rgb(0xd2, 0xd6, 0xdb)
ERROR_TEXT     = rgb(0xb4, 0x23, 0x18)


# Reuse imin-home Status Bar / NavBar / Home Tabs / Bottom Nav
imin_home = json.load(open('/Users/julee/imin/figma-design-agent/docs/references/imin-home/blueprint.json'))
status_bar = copy.deepcopy(imin_home['children'][0])
nav_bar    = copy.deepcopy(imin_home['children'][1])
home_tabs  = copy.deepcopy(imin_home['children'][2])  # Underline tabs
bottom_nav = copy.deepcopy(imin_home['children'][16])
bottom_spacer = copy.deepcopy(imin_home['children'][15])


# --- Patch: Home Tabs labels → "추천" / "직접" (active = 추천) ---
def _patch_tabs(tabs_node):
    children = tabs_node.get('children', [])
    if len(children) >= 2:
        # children[0] = Tab Active ("추천"), children[1] = Tab Inactive ("직접")
        for c in children[0].get('children', []):
            if c.get('type') == 'text':
                c['text'] = '추천'
        for c in children[1].get('children', []):
            if c.get('type') == 'text':
                c['text'] = '직접'
_patch_tabs(home_tabs)


# --- Patch: Bottom Nav active = Stages (index 2) ---
def _patch_bottomnav_active(node, active_idx=2):
    tabs = node.get('children', [])
    for i, tab in enumerate(tabs):
        for c in tab.get('children', []):
            if c.get('type') == 'text':
                c['fontColor'] = TEXT_BRAND if i == active_idx else FG_SECONDARY
_patch_bottomnav_active(bottom_nav, active_idx=2)


# ============================================================
# SECTION 1: Maker Group Card (SummaryCard pattern — white bg)
# ============================================================
def _maker_avatar(label, level, is_add=False):
    if is_add:
        avatar_inner = {"name":"avatar-add","type":"icon","iconName":"plus","size":18,"iconColor":TEXT_BRAND}
        circle_fill = BG_BRAND_PRI
        circle_stroke = None
    else:
        avatar_inner = {"name":"avatar-user","type":"icon","iconName":"user-01","size":24,"iconColor":FG_QUATERNARY}
        circle_fill = BG_TERTIARY
        circle_stroke = None

    circle = {
        "name": "Avatar Circle",
        "type": "frame",
        "width": 48, "height": 48,
        "layoutSizingHorizontal": "FIXED",
        "layoutSizingVertical": "FIXED",
        "cornerRadius": 999,
        "fill": circle_fill,
        "clipsContent": True,
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "primaryAxisAlignItems": "CENTER",
            "counterAxisAlignItems": "CENTER",
        },
        "children": [avatar_inner],
    }
    if circle_stroke:
        circle["stroke"] = circle_stroke
        circle["strokeAlign"] = "INSIDE"

    children = [circle]
    if label:
        children.append({
            "name": "Avatar Label", "type": "frame",
            "layoutSizingHorizontal": "HUG",
            "autoLayout": {
                "layoutMode": "VERTICAL",
                "counterAxisAlignItems": "CENTER",
                "itemSpacing": 0,
            },
            "children": [
                {"name":"av-name","type":"text","text":label,"fontSize":11,"fontWeight":600,"fontColor":TEXT_PRIMARY,"textAutoResize":"WIDTH_AND_HEIGHT","textAlignHorizontal":"CENTER"},
                {"name":"av-level","type":"text","text":level,"fontSize":10,"fontWeight":400,"fontColor":FG_SECONDARY,"textAutoResize":"WIDTH_AND_HEIGHT","textAlignHorizontal":"CENTER"},
            ],
        })

    return {
        "name": f"Avatar — {label or 'add'}",
        "type": "frame",
        "layoutSizingHorizontal": "HUG",
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "primaryAxisAlignItems": "CENTER",
            "counterAxisAlignItems": "CENTER",
            "itemSpacing": 6,
        },
        "children": children,
    }

maker_card_wrap = {
    "name": "MakerCard Wrap",
    "type": "frame",
    "layoutSizingHorizontal": "FILL",
    "autoLayout": {
        "layoutMode": "VERTICAL",
        "paddingTop": 16, "paddingBottom": 8,
        "paddingLeft": 16, "paddingRight": 16,
    },
    "children": [{
        "name": "Maker Card",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "cornerRadius": 16,
        "fill": BG_SECONDARY,
        "stroke": BORDER_SEC,
        "strokeAlign": "INSIDE",
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "itemSpacing": 16,
            "paddingTop": 20, "paddingBottom": 20,
            "paddingLeft": 20, "paddingRight": 20,
        },
        "children": [
            # Header — Title + Pill (rule #31)
            {
                "name": "Maker Header",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "primaryAxisAlignItems": "SPACE_BETWEEN",
                    "counterAxisAlignItems": "CENTER",
                },
                "children": [
                    {"name":"mc-title","type":"text","text":"함께 만드는 메이커","fontSize":16,"fontWeight":700,"fontColor":TEXT_PRIMARY,"textAutoResize":"WIDTH_AND_HEIGHT"},
                    {
                        "name": "Count Pill",
                        "type": "frame",
                        "layoutSizingHorizontal": "HUG",
                        "cornerRadius": 999,
                        "fill": BG_BRAND_PRI,
                        "stroke": BG_BRAND_SEC,
                        "strokeAlign": "INSIDE",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "counterAxisAlignItems": "CENTER",
                            "paddingTop": 2, "paddingBottom": 2,
                            "paddingLeft": 8, "paddingRight": 8,
                        },
                        "children": [{
                            "name":"pill-text","type":"text","text":"4명 모집 중","fontSize":12,"fontWeight":700,"fontColor":TEXT_BRAND,"textAutoResize":"WIDTH_AND_HEIGHT",
                        }],
                    },
                ],
            },
            # Avatar row
            {
                "name": "Maker Avatars",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "counterAxisAlignItems": "CENTER",
                    "itemSpacing": 14,
                },
                "children": [
                    _maker_avatar("닉네임여덟자", "lv.1202"),
                    _maker_avatar("닉네임여덟자", "lv.39"),
                    _maker_avatar("닉네임여덟자", "lv.492"),
                    _maker_avatar("닉네임여덟자", "lv.77"),
                    _maker_avatar("",            "",       is_add=True),
                ],
            },
        ],
    }],
}


# ============================================================
# SECTION 2: 가장 추천 — Premium CTA Card (purple brand-bg)
# ============================================================
def _round_cell_alpha(n, is_active):
    """Round cell on brand-bg surface. Active = white solid + brand text. Inactive = alpha-white-10."""
    return {
        "name": f"round-{n}",
        "type": "frame",
        "width": 22, "height": 24,
        "layoutSizingHorizontal": "FIXED",
        "layoutSizingVertical": "FIXED",
        "cornerRadius": 6,
        "fill": GREY_E6 if is_active else ALPHA_WHITE_10,
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "primaryAxisAlignItems": "CENTER",
            "counterAxisAlignItems": "CENTER",
        },
        "children": [{
            "name":"round-num","type":"text","text":str(n),
            "fontSize":10,"fontWeight":700,
            "fontColor":TEXT_BRAND if is_active else ALPHA_WHITE_70,
            "textAutoResize":"WIDTH_AND_HEIGHT",
        }],
    }

def _round_cell_default(n, is_active):
    """Round cell on white surface (secondary card)."""
    return {
        "name": f"round-{n}",
        "type": "frame",
        "width": 22, "height": 24,
        "layoutSizingHorizontal": "FIXED",
        "layoutSizingVertical": "FIXED",
        "cornerRadius": 6,
        "fill": BG_BRAND_SOLID if is_active else BG_TERTIARY,
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "primaryAxisAlignItems": "CENTER",
            "counterAxisAlignItems": "CENTER",
        },
        "children": [{
            "name":"round-num","type":"text","text":str(n),
            "fontSize":10,"fontWeight":700,
            "fontColor":TEXT_WHITE if is_active else FG_SECONDARY,
            "textAutoResize":"WIDTH_AND_HEIGHT",
        }],
    }

def _premium_stage_card(monthly, payout, interest, point="500P", gift="0원"):
    """Card #1 — Premium CTA Card pattern (brand-bg, alpha-white sub-components)."""
    cells = [_round_cell_alpha(n, is_active=(n == 1)) for n in range(1, 14)]

    return {
        "name": "Premium Stage Card #1",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "cornerRadius": 20,
        "fill": BG_BRAND_SEC_HR,  # bg-brand-section #5200b0
        "clipsContent": True,
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "itemSpacing": 8,
            "paddingTop": 20, "paddingBottom": 20,
            "paddingLeft": 20, "paddingRight": 20,
        },
        "children": [
            # Top label "가장 추천" pill
            {
                "name": "Top Label Row",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "primaryAxisAlignItems": "SPACE_BETWEEN",
                    "counterAxisAlignItems": "CENTER",
                },
                "children": [
                    {
                        "name": "Most Pill",
                        "type": "frame",
                        "layoutSizingHorizontal": "HUG",
                        "cornerRadius": 999,
                        "fill": ALPHA_WHITE_20,
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "counterAxisAlignItems": "CENTER",
                            "itemSpacing": 4,
                            "paddingTop": 4, "paddingBottom": 4,
                            "paddingLeft": 10, "paddingRight": 10,
                        },
                        "children": [
                            {"name":"sparkles","type":"icon","iconName":"sparkles","size":12,"iconColor":TEXT_WHITE},
                            {"name":"most-text","type":"text","text":"가장 추천","fontSize":11,"fontWeight":700,"fontColor":TEXT_WHITE,"textAutoResize":"WIDTH_AND_HEIGHT"},
                        ],
                    },
                    {"name":"sub-label","type":"text","text":"1회차 납입 후 즉시 수령","fontSize":11,"fontWeight":500,"fontColor":ALPHA_WHITE_70,"textAutoResize":"WIDTH_AND_HEIGHT"},
                ],
            },
            # Goal title block — emphasize amount
            {
                "name": "Amount Row",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "counterAxisAlignItems": "BASELINE",
                    "itemSpacing": 6,
                    "paddingTop": 4,
                },
                "children": [
                    {"name":"label","type":"text","text":"월","fontSize":14,"fontWeight":500,"fontColor":ALPHA_WHITE_70,"textAutoResize":"WIDTH_AND_HEIGHT"},
                    {"name":"amount","type":"text","text":monthly,"fontSize":32,"fontWeight":800,"fontColor":TEXT_WHITE,"textAutoResize":"WIDTH_AND_HEIGHT"},
                    {"name":"unit","type":"text","text":"× 13개월","fontSize":14,"fontWeight":500,"fontColor":ALPHA_WHITE_70,"textAutoResize":"WIDTH_AND_HEIGHT"},
                ],
            },
            # Payout info pill
            {
                "name": "Pill",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "cornerRadius": 999,
                "fill": ALPHA_WHITE_10,
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "counterAxisAlignItems": "CENTER",
                    "paddingTop": 4, "paddingBottom": 4,
                    "paddingLeft": 8, "paddingRight": 8,
                },
                "children": [{
                    "name":"info-pill","type":"text",
                    "text":f"목돈 {payout} · 1회차 납입 후 수령",
                    "fontSize":12,"fontWeight":500,"fontColor":TEXT_WHITE,
                    "textAutoResize":"WIDTH_AND_HEIGHT",
                }],
            },
            # Round selector panel
            {
                "name": "Controls Panel",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "cornerRadius": 14,
                "fill": ALPHA_WHITE_10,
                "autoLayout": {
                    "layoutMode": "VERTICAL",
                    "itemSpacing": 8,
                    "paddingTop": 12, "paddingBottom": 12,
                    "paddingLeft": 12, "paddingRight": 12,
                },
                "children": [
                    {
                        "name": "Round Header",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "SPACE_BETWEEN",
                            "counterAxisAlignItems": "CENTER",
                        },
                        "children": [
                            {"name":"hl","type":"text","text":"몇 번째 회차로 받을래요?","fontSize":12,"fontWeight":500,"fontColor":TEXT_WHITE,"textAutoResize":"WIDTH_AND_HEIGHT"},
                            {"name":"hr","type":"text","text":"1 / 13회차","fontSize":12,"fontWeight":700,"fontColor":TEXT_WHITE,"textAutoResize":"WIDTH_AND_HEIGHT"},
                        ],
                    },
                    {
                        "name": "Round Selector",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "CENTER",
                            "counterAxisAlignItems": "CENTER",
                            "itemSpacing": 4,
                        },
                        "children": cells,
                    },
                ],
            },
            # Data row — interest + benefit (compact)
            {
                "name": "Data Row",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "primaryAxisAlignItems": "SPACE_BETWEEN",
                    "counterAxisAlignItems": "CENTER",
                    "paddingTop": 4,
                },
                "children": [
                    {
                        "name": "Interest Group",
                        "type": "frame",
                        "layoutSizingHorizontal": "HUG",
                        "autoLayout": {
                            "layoutMode": "VERTICAL",
                            "itemSpacing": 2,
                        },
                        "children": [
                            {"name":"il","type":"text","text":"총 이자","fontSize":11,"fontWeight":500,"fontColor":ALPHA_WHITE_70,"textAutoResize":"WIDTH_AND_HEIGHT"},
                            {"name":"iv","type":"text","text":interest,"fontSize":14,"fontWeight":700,"fontColor":TEXT_WHITE,"textAutoResize":"WIDTH_AND_HEIGHT"},
                        ],
                    },
                    {
                        "name": "Benefit Group",
                        "type": "frame",
                        "layoutSizingHorizontal": "HUG",
                        "autoLayout": {
                            "layoutMode": "VERTICAL",
                            "primaryAxisAlignItems": "MAX",
                            "itemSpacing": 2,
                        },
                        "children": [
                            {"name":"bl","type":"text","text":"추가 혜택","fontSize":11,"fontWeight":500,"fontColor":ALPHA_WHITE_70,"textAutoResize":"WIDTH_AND_HEIGHT","textAlignHorizontal":"RIGHT"},
                            {
                                "name": "Benefit Pills",
                                "type": "frame",
                                "layoutSizingHorizontal": "HUG",
                                "autoLayout": {
                                    "layoutMode": "HORIZONTAL",
                                    "counterAxisAlignItems": "CENTER",
                                    "itemSpacing": 6,
                                },
                                "children": [
                                    {"name":"point","type":"text","text":point,"fontSize":12,"fontWeight":700,"fontColor":TEXT_WHITE,"textAutoResize":"WIDTH_AND_HEIGHT"},
                                    {"name":"sep","type":"text","text":"·","fontSize":12,"fontWeight":500,"fontColor":ALPHA_WHITE_70,"textAutoResize":"WIDTH_AND_HEIGHT"},
                                    {"name":"gift","type":"text","text":gift,"fontSize":12,"fontWeight":500,"fontColor":ALPHA_WHITE_70,"textAutoResize":"WIDTH_AND_HEIGHT"},
                                ],
                            },
                        ],
                    },
                ],
            },
            # CTA Button — solid white + brand text
            {
                "name": "CTA Button",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "cornerRadius": 12,
                "fill": TEXT_WHITE,
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "primaryAxisAlignItems": "CENTER",
                    "counterAxisAlignItems": "CENTER",
                    "paddingTop": 12, "paddingBottom": 12,
                },
                "children": [{
                    "name":"cta-btn","type":"text","text":"이 스테이지 참여하기",
                    "fontSize":16,"fontWeight":700,"fontColor":TEXT_BRAND,
                    "textAutoResize":"WIDTH_AND_HEIGHT",
                }],
            },
        ],
    }


# ============================================================
# SECTION 3: 다른 옵션 — secondary card (white, RoundSelectorGrid)
# ============================================================
def _secondary_stage_card(idx, label, monthly, payout, interest, active_round=1):
    cells = [_round_cell_default(n, is_active=(n == active_round)) for n in range(1, 14)]
    return {
        "name": f"Stage Card #{idx} — {label}",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "cornerRadius": 16,
        "fill": BG_SECONDARY,
        "stroke": BORDER_SEC,
        "strokeAlign": "INSIDE",
        "clipsContent": True,
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "itemSpacing": 12,
            "paddingTop": 20, "paddingBottom": 20,
            "paddingLeft": 20, "paddingRight": 20,
        },
        "children": [
            # Header — option label + monthly amount
            {
                "name": "Card Header",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "primaryAxisAlignItems": "SPACE_BETWEEN",
                    "counterAxisAlignItems": "CENTER",
                },
                "children": [
                    {
                        "name": "Option Pill",
                        "type": "frame",
                        "layoutSizingHorizontal": "HUG",
                        "cornerRadius": 999,
                        "fill": BG_TERTIARY,
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "counterAxisAlignItems": "CENTER",
                            "paddingTop": 2, "paddingBottom": 2,
                            "paddingLeft": 8, "paddingRight": 8,
                        },
                        "children": [{
                            "name":"opt-text","type":"text","text":label,
                            "fontSize":11,"fontWeight":700,"fontColor":FG_SECONDARY,
                            "textAutoResize":"WIDTH_AND_HEIGHT",
                        }],
                    },
                    {
                        "name": "Monthly Group",
                        "type": "frame",
                        "layoutSizingHorizontal": "HUG",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "counterAxisAlignItems": "BASELINE",
                            "itemSpacing": 4,
                        },
                        "children": [
                            {"name":"prefix","type":"text","text":"월","fontSize":12,"fontWeight":500,"fontColor":FG_SECONDARY,"textAutoResize":"WIDTH_AND_HEIGHT"},
                            {"name":"amt","type":"text","text":monthly,"fontSize":18,"fontWeight":700,"fontColor":TEXT_PRIMARY,"textAutoResize":"WIDTH_AND_HEIGHT"},
                            {"name":"period","type":"text","text":"× 13개월","fontSize":12,"fontWeight":500,"fontColor":FG_SECONDARY,"textAutoResize":"WIDTH_AND_HEIGHT"},
                        ],
                    },
                ],
            },
            # Round selector panel (sub-card with bg-tertiary)
            {
                "name": "Round Wrap",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "cornerRadius": 12,
                "fill": BG_TERTIARY,
                "autoLayout": {
                    "layoutMode": "VERTICAL",
                    "itemSpacing": 8,
                    "paddingTop": 12, "paddingBottom": 12,
                    "paddingLeft": 12, "paddingRight": 12,
                },
                "children": [
                    {
                        "name": "Round Header",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "SPACE_BETWEEN",
                            "counterAxisAlignItems": "CENTER",
                        },
                        "children": [
                            {"name":"hl","type":"text","text":f"{active_round}회차 납입 후 목돈 수령","fontSize":12,"fontWeight":500,"fontColor":FG_SECONDARY,"textAutoResize":"WIDTH_AND_HEIGHT"},
                            {"name":"hr","type":"text","text":f"{active_round} / 13","fontSize":12,"fontWeight":700,"fontColor":TEXT_PRIMARY,"textAutoResize":"WIDTH_AND_HEIGHT"},
                        ],
                    },
                    {
                        "name": "Round Selector",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "CENTER",
                            "counterAxisAlignItems": "CENTER",
                            "itemSpacing": 4,
                        },
                        "children": cells,
                    },
                ],
            },
            # Data row — payout / interest
            {
                "name": "Data Row",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "primaryAxisAlignItems": "SPACE_BETWEEN",
                    "counterAxisAlignItems": "CENTER",
                },
                "children": [
                    {
                        "name": "Payout Group",
                        "type": "frame",
                        "layoutSizingHorizontal": "HUG",
                        "autoLayout": {
                            "layoutMode": "VERTICAL",
                            "itemSpacing": 2,
                        },
                        "children": [
                            {"name":"l","type":"text","text":"목돈","fontSize":11,"fontWeight":500,"fontColor":FG_SECONDARY,"textAutoResize":"WIDTH_AND_HEIGHT"},
                            {"name":"v","type":"text","text":payout,"fontSize":16,"fontWeight":700,"fontColor":TEXT_PRIMARY,"textAutoResize":"WIDTH_AND_HEIGHT"},
                        ],
                    },
                    {
                        "name": "Interest Group",
                        "type": "frame",
                        "layoutSizingHorizontal": "HUG",
                        "autoLayout": {
                            "layoutMode": "VERTICAL",
                            "primaryAxisAlignItems": "MAX",
                            "itemSpacing": 2,
                        },
                        "children": [
                            {"name":"l","type":"text","text":"총 이자","fontSize":11,"fontWeight":500,"fontColor":FG_SECONDARY,"textAutoResize":"WIDTH_AND_HEIGHT","textAlignHorizontal":"RIGHT"},
                            {"name":"v","type":"text","text":interest,"fontSize":16,"fontWeight":700,"fontColor":ERROR_TEXT,"textAutoResize":"WIDTH_AND_HEIGHT","textAlignHorizontal":"RIGHT"},
                        ],
                    },
                ],
            },
        ],
    }


# Stage list — #1 premium + #2 #3 secondary cards
stage_list = {
    "name": "Stage List",
    "type": "frame",
    "layoutSizingHorizontal": "FILL",
    "autoLayout": {
        "layoutMode": "VERTICAL",
        "itemSpacing": 12,
        "paddingTop": 16, "paddingBottom": 16,
        "paddingLeft": 16, "paddingRight": 16,
    },
    "children": [
        _premium_stage_card("105,120원", "1,092,200원", "−129,100원"),
        _secondary_stage_card(2, "안정적", "120,000원", "1,560,000원", "−45,000원", active_round=7),
        _secondary_stage_card(3, "공격적", "200,000원", "2,600,000원", "−250,000원", active_round=13),
    ],
}


# ============================================================
# SECTION 4: Legal Footer
# ============================================================
legal_footer = {
    "name": "Legal Footer",
    "type": "frame",
    "layoutSizingHorizontal": "FILL",
    "fill": BG_SECONDARY,
    "autoLayout": {
        "layoutMode": "VERTICAL",
        "itemSpacing": 12,
        "paddingTop": 24, "paddingBottom": 24,
        "paddingLeft": 20, "paddingRight": 20,
    },
    "children": [
        {
            "name":"Terms Row 1","type":"frame","layoutSizingHorizontal":"FILL",
            "autoLayout":{"layoutMode":"HORIZONTAL","itemSpacing":16},
            "children":[
                {"name":"t1","type":"text","text":"이용약관","fontSize":11,"fontWeight":700,"fontColor":FG_SECONDARY,"textAutoResize":"WIDTH_AND_HEIGHT"},
                {"name":"t2","type":"text","text":"스테이지이용약관","fontSize":11,"fontWeight":700,"fontColor":FG_SECONDARY,"textAutoResize":"WIDTH_AND_HEIGHT"},
                {"name":"t3","type":"text","text":"서비스운영정책","fontSize":11,"fontWeight":700,"fontColor":FG_SECONDARY,"textAutoResize":"WIDTH_AND_HEIGHT"},
            ],
        },
        {
            "name":"Terms Row 2","type":"frame","layoutSizingHorizontal":"FILL",
            "autoLayout":{"layoutMode":"HORIZONTAL","itemSpacing":16},
            "children":[
                {"name":"p1","type":"text","text":"개인정보처리방침","fontSize":11,"fontWeight":700,"fontColor":FG_SECONDARY,"textAutoResize":"WIDTH_AND_HEIGHT"},
                {"name":"p2","type":"text","text":"쇼핑이용약관","fontSize":11,"fontWeight":700,"fontColor":FG_SECONDARY,"textAutoResize":"WIDTH_AND_HEIGHT"},
            ],
        },
        {"name":"co1","type":"text","text":"(주)티웨이브 역삼지점  ·  사업자등록번호: 291-85-01499","fontSize":11,"fontWeight":400,"fontColor":FG_SECONDARY,"layoutSizingHorizontal":"FILL"},
        {"name":"co2","type":"text","text":"대표: 서재준  ·  통신판매업신고: 2021-서울강남-05837","fontSize":11,"fontWeight":400,"fontColor":FG_SECONDARY,"layoutSizingHorizontal":"FILL"},
        {"name":"copyright","type":"text","text":"Copyright ⓒ TWAVE. All Rights Reserved.","fontSize":11,"fontWeight":400,"fontColor":FG_SECONDARY,"textAutoResize":"WIDTH_AND_HEIGHT"},
    ],
}


# Assemble blueprint
blueprint = {
    "_meta": {
        "referenceId": "stage-tab-v3",
        "validatedOn": "2026-05-01",
        "source": "Wireframe 16805:68746 — REINTERPRETED with imin DS hierarchy",
        "scope": "추천 스테이지 탭 — Tabs + Maker Card + Premium Stage Card #1 + Secondary Stage Cards #2 #3 + Footer + Bottom Nav",
    },
    "rootName": "stage-tab-v3 (clone-bind)",
    "name": "stage-tab-v3 (clone-bind)",
    "type": "frame",
    "width": 393,
    "height": 2400,
    "fill": BG_PRIMARY,
    "autoLayout": {
        "layoutMode": "VERTICAL",
        "itemSpacing": 0,
        "paddingTop": 0, "paddingBottom": 0,
        "paddingLeft": 0, "paddingRight": 0,
    },
    "children": [
        status_bar,
        nav_bar,
        home_tabs,
        maker_card_wrap,
        stage_list,
        legal_footer,
        bottom_spacer,
        bottom_nav,
    ],
    "statusBar": True,
}

OUT = '/Users/julee/imin/figma-design-agent/scripts/stage_tab_v3_blueprint.json'
with open(OUT, 'w') as f:
    json.dump(blueprint, f, ensure_ascii=False, indent=2)
print(f"wrote {OUT} — {len(blueprint['children'])} top-level sections")
