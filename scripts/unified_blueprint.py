"""Unified Content Model — spec → blueprint 변환 단일 함수.

2026-05-28 사용자 분노 4회 후 박힘. 기존 3-layer (와이어/mock/polish) 분리 구조
회피 — 모든 결정을 하나의 spec 안에서.

architecture:
  archetype_specs/{archetype}.json  — base spec (mock_data + polish + sections)
  wire_content (Claude 가 매번 작성)  — 와이어 콘텐츠 1:1 추출
  ↓
  scenario 결정 (auto: wire_content 분석 → active/empty)
  ↓
  effective_data = scenario == "empty" ? wire_content : mock_data
  ↓
  sections[] walk → 각 type 별 _gen_* 함수
  ↓
  blueprint dict (cmd_build 와 호환)

docs/refactor-A-unified-content-model.md 참조.
"""
from __future__ import annotations

import copy
import json
import os
import re
from typing import Any, Optional


_ARCHETYPE_SPECS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archetype_specs")

# 2026-05-28 — generator 가 명백한 DS 컴포넌트(CTA/badge)를 raw frame 대신 명시적
# instance 로 생성하기 위한 componentKey. R23 휴리스틱 swap 의 false positive/negative
# (CTA 가 chevron 때문에 안 잡히고, 라벨이 버튼으로 잘못 잡히는 문제)를 근본 차단.
try:
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from design_rules.ds_catalog import COMPONENT_KEYS as _DS_KEYS
except Exception:
    _DS_KEYS = {}

_K_ACTION_BTN_PRIMARY = _DS_KEYS.get("Action Button md Primary", "ed0032bcf28f03da97e4b3006f54d30a0fbe5914")
_K_BADGE_BRAND = _DS_KEYS.get("Badge sm Brand", "03b25488b460f514f23ddf39b5b42f7d31e7935e")
# DS Action Button 의 leading/trailing icon BOOLEAN prop (기본 on → off 시켜야 텍스트만)
_BTN_ICON_OFF = {"⬅️ Icon leading#3287:1577": False, "➡️ Icon trailing#3287:2338": False}


# ─────────────────────────────────────────────────────────────
# Spec loader
# ─────────────────────────────────────────────────────────────


def load_archetype_spec(archetype: str) -> Optional[dict]:
    """archetype 이름 → base spec dict. 파일 없으면 None."""
    path = os.path.join(_ARCHETYPE_SPECS_DIR, f"{archetype}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def resolve_archetype(blueprint_name_or_spec: Any) -> Optional[str]:
    """blueprint name / spec 에서 archetype 추출 (imin_home / imin_my / ...)."""
    if isinstance(blueprint_name_or_spec, dict):
        if "archetype" in blueprint_name_or_spec:
            return blueprint_name_or_spec["archetype"]
        name = (blueprint_name_or_spec.get("rootName") or
                blueprint_name_or_spec.get("name") or "")
    else:
        name = str(blueprint_name_or_spec or "")
    name = name.lower().replace(" ", "_")
    for prefix in ("imin_home", "imin_account", "imin_lounge", "imin_stage",
                   "imin_my", "imin_community", "imin_calc", "imin_invite"):
        if prefix in name:
            return prefix
    return None


# ─────────────────────────────────────────────────────────────
# Scenario 결정
# ─────────────────────────────────────────────────────────────


def detect_scenario(wire_content: dict) -> str:
    """wire_content dict 분석 → 'active' | 'empty'.

    empty signal: '0건' / '0개' / '0원' / '없어요' / '없습니다' / 'empty' 키워드 카운트 ≥3
    """
    if not isinstance(wire_content, dict) or not wire_content:
        return "active"
    text = json.dumps(wire_content, ensure_ascii=False)
    signals = (
        text.count("0건") + text.count("0개") +
        text.count("0원") + text.count("없어요") +
        text.count("없습니다") + text.count("empty")
    )
    return "empty" if signals >= 3 else "active"


# ─────────────────────────────────────────────────────────────
# Section generators (A.3.2 — simple template-driven)
# ─────────────────────────────────────────────────────────────


def _gen_nav_bar(data: dict, scenario: str) -> dict:
    """NavBar — 로고 placeholder + 우측 아이콘 그룹."""
    icons = data.get("icons") or ["bell-01", "message-chat-circle"]
    icon_children = [
        {"name": f"icon-{i}", "type": "icon", "iconName": ic, "size": 24,
         "iconColor": "$token(fg-primary)"}
        for i, ic in enumerate(icons)
    ]
    return {
        "name": "NavBar",
        "type": "frame",
        "width": 393,
        "height": 56,
        "layoutSizingHorizontal": "FILL",
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "primaryAxisAlignItems": "SPACE_BETWEEN",
            "counterAxisAlignItems": "CENTER",
            "paddingLeft": 20, "paddingRight": 20,
            "paddingTop": 12, "paddingBottom": 12,
        },
        "children": [
            {"name": "Logo Placeholder", "type": "frame", "width": 80, "height": 32},
            {
                "name": "Nav Right",
                "type": "frame",
                "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 16,
                              "counterAxisAlignItems": "CENTER"},
                "children": icon_children,
            },
        ],
    }


def _gen_mode_tabs(data: dict, scenario: str) -> dict:
    """Underline tab v2 (top 모드 탭). active = brand bold + 2.5px brand underline."""
    tabs = data.get("tabs") or ["거래 현황", "누적 거래"]
    active_idx = data.get("active", 0)

    def tab_node(label: str, is_active: bool) -> dict:
        return {
            "name": f"Mode Tab {'Active' if is_active else 'Inactive'}",
            "type": "frame",
            "layoutSizingHorizontal": "HUG",
            "layoutSizingVertical": "HUG",
            "autoLayout": {
                "layoutMode": "VERTICAL",
                "paddingTop": 16, "itemSpacing": 12,
                "counterAxisAlignItems": "CENTER",
            },
            "children": [
                {
                    "name": f"label-{'active' if is_active else 'inactive'}",
                    "type": "text",
                    "characters": label,
                    "fontSize": 16,
                    "fontWeight": 700 if is_active else 500,
                    "fill": f"$token({'text-primary' if is_active else 'text-tertiary'})",
                },
                {
                    "name": f"underline-{'active' if is_active else 'inactive'}",
                    "type": "rectangle",
                    "height": 2.5,
                    "layoutSizingHorizontal": "FILL",
                    "layoutSizingVertical": "FIXED",
                    **({"fill": "$token(bg-brand-solid)"} if is_active else {}),
                },
            ],
        }

    return {
        "name": "Mode Tabs Wrap",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "fill": "$token(bg-primary)",
        "clipsContent": True,
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "paddingLeft": 24, "paddingRight": 24,
            "paddingTop": 4, "paddingBottom": 8,
            "itemSpacing": 22,
            "counterAxisAlignItems": "MAX",
        },
        "children": [tab_node(label, i == active_idx) for i, label in enumerate(tabs)],
    }


def _gen_tab_bar(data: dict, scenario: str) -> dict:
    """Bottom Tab Bar — 5 tabs FILL, active = brand."""
    tabs = data.get("tabs") or ["홈", "라운지", "스테이지", "커뮤니티", "전체"]
    icons = data.get("icons") or ["home-line", "building-08", "coins-stacked-01",
                                   "users-01", "menu-01"]
    active = data.get("active", "홈")

    def tab_item(label: str, icon_name: str) -> dict:
        is_active = label == active
        color = "fg-brand-primary" if is_active else "fg-secondary"
        weight = 600 if is_active else 500
        return {
            "name": f"Tab {label}",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "layoutSizingVertical": "FILL",
            "autoLayout": {
                "layoutMode": "VERTICAL",
                "primaryAxisAlignItems": "CENTER",
                "counterAxisAlignItems": "CENTER",
                "itemSpacing": 4,
            },
            "children": [
                {"name": "tab-icon", "type": "icon", "iconName": icon_name,
                 "size": 24, "iconColor": f"$token({color})"},
                {"name": "tab-label", "type": "text", "characters": label,
                 "fontSize": 11, "fontWeight": weight,
                 "fill": f"$token(text-{'brand-primary' if is_active else 'secondary'})",
                 "textAlignHorizontal": "CENTER",
                 "layoutSizingHorizontal": "FILL"},
            ],
        }

    return {
        "name": "Tab Bar",
        "type": "frame",
        "width": 393,
        "height": 73,
        "layoutSizingHorizontal": "FILL",
        "fill": "$token(bg-primary)",
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "primaryAxisAlignItems": "SPACE_BETWEEN",
            "counterAxisAlignItems": "CENTER",
            "paddingTop": 8, "paddingBottom": 24,
            "paddingLeft": 0, "paddingRight": 0,
        },
        "strokeWeight": 0,
        "strokeTopWeight": 1,
        "strokeBottomWeight": 0,
        "strokeLeftWeight": 0,
        "strokeRightWeight": 0,
        "children": [tab_item(label, icons[i] if i < len(icons) else "menu-01")
                     for i, label in enumerate(tabs)],
    }


def _gen_fab(data: dict, scenario: str) -> dict:
    """FAB — 56×56 icon-only circle, brand-solid."""
    icon = data.get("icon", "plus")
    fill = data.get("fill", "bg-brand-solid")
    # 2026-05-28 절대 룰 (R57): FAB icon 은 무조건 fg-light (fg-white 는 alias→차단)
    icon_color = data.get("icon_color", "fg-light")
    if icon_color in ("fg-white", "fg-primary_on-brand"):
        icon_color = "fg-light"
    return {
        "name": "FAB",
        "type": "frame",
        "width": 56,
        "height": 56,
        "cornerRadius": 28,
        "fill": f"$token({fill})",
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "primaryAxisAlignItems": "CENTER",
            "counterAxisAlignItems": "CENTER",
            "paddingTop": 0, "paddingBottom": 0,
            "paddingLeft": 0, "paddingRight": 0,
            "itemSpacing": 0,
        },
        "children": [
            {"name": "fab-icon", "type": "icon", "iconName": icon,
             "size": 24, "iconColor": f"$token({icon_color})"},
        ],
    }


def _gen_footer_policy(data: dict, scenario: str) -> dict:
    """Footer policy — bg-secondary 회색 띠, 보더 없음."""
    policies = data.get("policies") or []
    # 5개 policy 를 2 row 로 분배 (3 + 2)
    row1 = policies[:3]
    row2 = policies[3:]

    def policy_link(text: str, primary: bool = False) -> dict:
        return {
            "name": f"p-{text}", "type": "text", "characters": text,
            "fontSize": 12,
            "fontWeight": 600 if primary else 500,
            "fill": f"$token(text-{'secondary' if primary else 'tertiary'})",
        }

    def row(items: list[str]) -> dict:
        return {
            "name": f"Policy Row",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "autoLayout": {
                "layoutMode": "HORIZONTAL", "itemSpacing": 14,
                "primaryAxisAlignItems": "MIN", "counterAxisAlignItems": "CENTER",
            },
            "children": [policy_link(t, i == 0) for i, t in enumerate(items)],
        }

    children = []
    if row1:
        children.append(row(row1))
    if row2:
        children.append(row(row2))

    # 회사 정보 row
    if data.get("company"):
        children.append({
            "name": "Footer Company",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 4},
            "children": [
                {"name": "fc-row1", "type": "frame", "layoutSizingHorizontal": "FILL",
                 "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 12},
                 "children": [
                    {"name": "fc-name", "type": "text", "characters": data["company"],
                     "fontSize": 11, "fontWeight": 600, "fill": "$token(text-secondary)"},
                    {"name": "fc-reg", "type": "text", "characters": data.get("reg_no", ""),
                     "fontSize": 11, "fontWeight": 500, "fill": "$token(text-tertiary)"},
                 ]},
                {"name": "fc-row2", "type": "frame", "layoutSizingHorizontal": "FILL",
                 "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 12},
                 "children": [
                    {"name": "fc-ceo", "type": "text", "characters": data.get("ceo", ""),
                     "fontSize": 11, "fontWeight": 500, "fill": "$token(text-tertiary)"},
                    {"name": "fc-sales", "type": "text", "characters": data.get("sales_no", ""),
                     "fontSize": 11, "fontWeight": 500, "fill": "$token(text-tertiary)"},
                 ]},
            ],
        })

    if data.get("disclaimer"):
        children.append({
            "name": "Footer Disclaimer",
            "type": "text",
            "layoutSizingHorizontal": "FILL",
            "characters": data["disclaimer"],
            "fontSize": 11, "fontWeight": 500,
            "fill": "$token(text-tertiary)",
            "lineHeight": 16,
        })

    if data.get("copyright"):
        children.append({
            "name": "Footer Copyright",
            "type": "text",
            "characters": data["copyright"],
            "fontSize": 11, "fontWeight": 500,
            "fill": "$token(text-tertiary)",
        })

    return {
        "name": "Footer Policy",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "fill": "$token(bg-secondary)",
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "paddingLeft": 20, "paddingRight": 20,
            "paddingTop": 24, "paddingBottom": 28,
            "itemSpacing": 14,
        },
        "children": children,
    }


# ─────────────────────────────────────────────────────────────
# Section generators (A.3.3 — complex)
# ─────────────────────────────────────────────────────────────


def _wrap_section(name: str, padding: dict, children: list, fill: str = "bg-primary") -> dict:
    """공통 section wrap — paddingLeft/Right 20 default."""
    pad = {"paddingLeft": 20, "paddingRight": 20, "paddingTop": 8, "paddingBottom": 8}
    pad.update(padding or {})
    return {
        "name": name,
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "fill": f"$token({fill})",
        "autoLayout": {"layoutMode": "VERTICAL", **pad, "itemSpacing": 0},
        "children": children,
    }


def _gen_top_alert_banner(data: dict, scenario: str) -> dict:
    """납입 기한 지난 N건 alert peach 띠 (active scenario only)."""
    icon = data.get("icon", "alert-triangle")
    text = data.get("text", "납입 기한이 지난 1건이 있어요")
    cta = data.get("cta", "지금 납입 >")
    return {
        "name": "Top Alert Banner",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "fill": "$token(bg-warning-secondary)",
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "paddingLeft": 20, "paddingRight": 20,
            "paddingTop": 12, "paddingBottom": 12,
            "primaryAxisAlignItems": "SPACE_BETWEEN",
            "counterAxisAlignItems": "CENTER",
            "itemSpacing": 8,
        },
        "children": [
            {
                "name": "alert-left",
                "type": "frame",
                "layoutSizingHorizontal": "HUG",
                "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 8,
                              "counterAxisAlignItems": "CENTER"},
                "children": [
                    {"type": "icon", "iconName": icon, "size": 18,
                     "iconColor": "$token(fg-warning-primary)"},
                    {"type": "text", "characters": text, "fontSize": 14,
                     "fontWeight": 600, "fill": "$token(text-primary)"},
                ],
            },
            {"type": "text", "characters": cta, "fontSize": 13,
             "fontWeight": 700, "fill": "$token(text-warning-primary)"},
        ],
    }


def _gen_screen_hero(data: dict, scenario: str) -> dict:
    """Screen Hero — active = currency hero 42px / empty = invitation."""
    is_empty = scenario == "empty"
    inner = data.get("empty" if is_empty else "active", {})

    if is_empty:
        return {
            "name": "Screen Hero",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "layoutSizingVertical": "HUG",
            "autoLayout": {
                "layoutMode": "VERTICAL",
                "paddingLeft": 20, "paddingRight": 20,
                "paddingTop": 20, "paddingBottom": 12,
                "itemSpacing": 6,
            },
            "children": [
                {"name": "hero-caption", "type": "text",
                 "characters": inner.get("caption", "안녕하세요 :)"),
                 "fontSize": 13, "fontWeight": 500, "fill": "$token(text-tertiary)"},
                {"name": "hero-title", "type": "text",
                 "characters": inner.get("title", "오늘부터 스테이지 시작해보세요"),
                 "fontSize": 24, "fontWeight": 700, "fill": "$token(text-primary)"},
                {"name": "hero-sub", "type": "text",
                 "characters": inner.get("sub", "월 10만원으로 1300만원 모으기 도전"),
                 "fontSize": 13, "fontWeight": 500, "fill": "$token(text-secondary)"},
            ],
        }
    else:
        return {
            "name": "Screen Hero",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "layoutSizingVertical": "HUG",
            "autoLayout": {
                "layoutMode": "VERTICAL",
                "paddingLeft": 20, "paddingRight": 20,
                "paddingTop": 20, "paddingBottom": 16,
                "itemSpacing": 4,
            },
            "children": [
                {"name": "hero-caption", "type": "text",
                 "characters": inner.get("caption", "진행 중인 스테이지 3개"),
                 "fontSize": 13, "fontWeight": 500, "fill": "$token(text-tertiary)"},
                {"name": "hero-label", "type": "text",
                 "characters": inner.get("label", "모은 금액"),
                 "fontSize": 14, "fontWeight": 500, "fill": "$token(text-secondary)"},
                {"name": "hero-amount", "type": "text",
                 "characters": inner.get("amount", "1,240,000원"),
                 "fontSize": 42, "fontWeight": 700, "fill": "$token(text-primary)"},
                {
                    "name": "hero-footnote",
                    "type": "frame",
                    "layoutSizingHorizontal": "FILL",
                    "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 6,
                                   "counterAxisAlignItems": "CENTER", "paddingTop": 6},
                    "children": [
                        {"name": "footnote-dot", "type": "rectangle",
                         "width": 6, "height": 6, "cornerRadius": 3,
                         "fill": f"$token(bg-{inner.get('footnote_dot', 'success')}-solid)"},
                        {"type": "text",
                         "characters": inner.get("footnote", "이번 달 240,000원 수령했어요"),
                         "fontSize": 12, "fontWeight": 500, "fill": "$token(text-secondary)"},
                    ],
                },
            ],
        }


def _gen_stage_progress_card(data: dict, scenario: str) -> dict:
    """1.3 스테이지 진행 현황 카드 — 헤더 + summary rows + day strip."""
    is_empty = scenario == "empty"
    count = data.get("count", 0)
    header_tpl = data.get("header_template", "진행중인 {count}건의 스테이지 내역")
    header = header_tpl.format(count=count)
    more = data.get("more_link", "자세히")
    rows = data.get("rows") or []
    day_strip = data.get("day_strip") or []
    day_strip_title = data.get("day_strip_title", "이번 달 일정")

    def summary_row(row: dict) -> dict:
        dot_color = row.get("dot", "secondary")
        return {
            "name": f"Row {row.get('label', '')}",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "autoLayout": {
                "layoutMode": "HORIZONTAL",
                "primaryAxisAlignItems": "SPACE_BETWEEN",
                "counterAxisAlignItems": "CENTER",
            },
            "children": [
                {
                    "name": "row-label",
                    "type": "frame",
                    "layoutSizingHorizontal": "HUG",
                    "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 8,
                                  "counterAxisAlignItems": "CENTER"},
                    "children": [
                        {"name": f"dot-{dot_color}", "type": "frame",
                         "width": 8, "height": 8, "cornerRadius": 4,
                         "fill": f"$token(bg-{dot_color}-solid)"},
                        {"name": "text-label", "type": "text",
                         "characters": row.get("label", ""),
                         "fontSize": 14, "fontWeight": 500,
                         "fill": "$token(text-secondary)"},
                    ],
                },
                {"name": "row-value", "type": "text",
                 "characters": row.get("value", ""),
                 "fontSize": 18, "fontWeight": 700,
                 "fill": f"$token(text-{row.get('color', 'primary')}-primary)"
                         if row.get("color") in ("success", "error", "warning", "brand")
                         else "$token(text-primary)"},
            ],
        }

    def day_cell(cell: dict) -> dict:
        # 2026-05-28 레퍼런스(가로 스크롤 여유 블록): 요일 + 날짜(Bold) + 금액(색상) +
        # 상태. 미납=빨강tint / 오늘=다크 / 지급(+)=초록 / 납입(-)=중립.
        t = cell.get("type", "default")
        val = cell.get("value", "")
        is_today = t == "today"
        is_overdue = t == "overdue"
        is_receive = t == "receive" or val.startswith("+")
        if is_today:
            bg = "bg-fg-primary-solid"
        elif is_overdue:
            bg = "bg-error-secondary"
        else:
            bg = "bg-secondary"
        # 요일/상태 색
        if is_today:
            sub_color = "fg-white"
        elif is_overdue:
            sub_color = "text-error-primary"
        else:
            sub_color = "text-tertiary"
        # 날짜 색
        day_color = "fg-white" if is_today else ("text-error-primary" if is_overdue else "text-primary")
        # 금액 색 (마이너스 빨강 / 플러스 초록 / today 흰)
        if is_today:
            val_color = "fg-white"
        elif is_receive:
            val_color = "text-success-primary"
        elif is_overdue or val.startswith("-"):
            val_color = "text-error-primary"
        else:
            val_color = "text-secondary"
        return {
            "name": f"Day Cell {cell.get('day', '')}{' today' if is_today else ''}",
            "type": "frame",
            "width": 76,
            "layoutSizingHorizontal": "FIXED",
            "layoutSizingVertical": "HUG",
            "fill": f"$token({bg})",
            "cornerRadius": 16,
            "autoLayout": {
                "layoutMode": "VERTICAL",
                "paddingTop": 14, "paddingBottom": 14,
                "paddingLeft": 8, "paddingRight": 8,
                "itemSpacing": 6,
                "counterAxisAlignItems": "CENTER",
            },
            "children": [
                {"name": "day-weekday", "type": "text",
                 "characters": cell.get("weekday", ""),
                 "fontSize": 11, "fontWeight": 500,
                 "fill": f"$token({sub_color})",
                 "textAlignHorizontal": "CENTER"},
                {"name": "day-num", "type": "text",
                 "characters": cell.get("day", ""),
                 "fontSize": 20, "fontWeight": 700,
                 "fill": f"$token({day_color})",
                 "textAlignHorizontal": "CENTER"},
                {"name": "day-val", "type": "text",
                 "characters": val,
                 "fontSize": 13, "fontWeight": 700,
                 "fill": f"$token({val_color})",
                 "textAlignHorizontal": "CENTER"},
                {"name": "day-status", "type": "text",
                 "characters": cell.get("status", ""),
                 "fontSize": 11, "fontWeight": 500,
                 "fill": f"$token({sub_color})",
                 "textAlignHorizontal": "CENTER"},
            ],
        }

    return _wrap_section(
        "Stage Progress Card Wrap",
        {"paddingTop": 16, "paddingBottom": 8},
        [{
            "name": "Stage Progress Card",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "layoutSizingVertical": "HUG",
            "fill": "$token(bg-primary)",
            "cornerRadius": 20,
            "strokeColor": "$token(border-secondary)",
            "strokeWeight": 1,
            "autoLayout": {
                "layoutMode": "VERTICAL",
                "paddingLeft": 20, "paddingRight": 20,
                "paddingTop": 22, "paddingBottom": 22,
                "itemSpacing": 18,
            },
            "children": [
                # Header row
                {
                    "name": "Header Row",
                    "type": "frame",
                    "layoutSizingHorizontal": "FILL",
                    "autoLayout": {
                        "layoutMode": "HORIZONTAL",
                        "primaryAxisAlignItems": "SPACE_BETWEEN",
                        "counterAxisAlignItems": "CENTER",
                    },
                    "children": [
                        {"name": "Header Title", "type": "text", "characters": header,
                         "fontSize": 17, "fontWeight": 700, "fill": "$token(text-primary)"},
                        {
                            "name": "More Link",
                            "type": "frame",
                            "layoutSizingHorizontal": "HUG",
                            "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 2,
                                          "counterAxisAlignItems": "CENTER"},
                            "children": [
                                {"name": "more-text", "type": "text", "characters": more,
                                 "fontSize": 13, "fontWeight": 500,
                                 "fill": "$token(text-tertiary)"},
                                {"type": "icon", "iconName": "chevron-right",
                                 "size": 14, "iconColor": "$token(fg-tertiary)"},
                            ],
                        },
                    ],
                },
                # Summary rows
                {
                    "name": "Summary Rows",
                    "type": "frame",
                    "layoutSizingHorizontal": "FILL",
                    "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 8},
                    "children": [summary_row(r) for r in rows],
                },
                # Divider
                {"name": "Card Divider", "type": "rectangle",
                 "layoutSizingHorizontal": "FILL", "layoutSizingVertical": "FIXED",
                 "height": 1, "fill": "$token(border-secondary)"},
                # Day strip title
                {"name": "Day Strip Title", "type": "text",
                 "characters": day_strip_title,
                 "fontSize": 14, "fontWeight": 700, "fill": "$token(text-primary)",
                 "textAlignHorizontal": "CENTER",
                 "layoutSizingHorizontal": "FILL"},
                # Day strip
                {
                    # 가로 스크롤 day strip (레퍼런스): cell 여유 간격 + clipsContent
                    # 로 마지막 셀 peek → 스와이프 탐색 힌트. name 'Carousel' 로 R45
                    # (clip 해제)·R36(peek) 룰에 carousel 로 인식되게.
                    "name": "Day Strip Carousel",
                    "type": "frame",
                    "layoutSizingHorizontal": "FILL",
                    "autoLayout": {
                        "layoutMode": "HORIZONTAL",
                        "primaryAxisAlignItems": "MIN",
                        "counterAxisAlignItems": "CENTER",
                        "itemSpacing": 8,
                    },
                    "clipsContent": True,
                    "_repetitionAllowed": "day strip 일정 셀 — 가로 스크롤 탐색",
                    "children": [day_cell(c) for c in day_strip],
                },
            ],
        }],
    )


def _gen_attendance_banner(data: dict, scenario: str) -> dict:
    """1.4 출석 체크 배너 — 아이콘 + 헤드라인 + sub."""
    streak = data.get("streak", 0)
    headline_tpl = data.get("headline_template", "연속 {streak}일째 출석 체크 중")
    headline = headline_tpl.format(streak=streak)
    sub = data.get("sub", "매일매일 출석하면 특별한 혜택이!")
    return _wrap_section(
        "Attendance Banner Wrap",
        {"paddingTop": 8, "paddingBottom": 8},
        [{
            "name": "Attendance Banner",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "layoutSizingVertical": "HUG",
            "fill": "$token(bg-primary)",
            "cornerRadius": 18,
            "strokeColor": "$token(border-secondary)",
            "strokeWeight": 1,
            "autoLayout": {
                "layoutMode": "HORIZONTAL",
                "paddingLeft": 16, "paddingRight": 16,
                "paddingTop": 16, "paddingBottom": 16,
                "itemSpacing": 14,
                "counterAxisAlignItems": "CENTER",
            },
            "children": [
                {
                    "name": "Att Icon Wrap",
                    "type": "frame",
                    "width": 44, "height": 44, "cornerRadius": 12,
                    "fill": "$token(bg-brand-primary)",
                    "autoLayout": {"layoutMode": "HORIZONTAL",
                                  "primaryAxisAlignItems": "CENTER",
                                  "counterAxisAlignItems": "CENTER"},
                    "children": [
                        {"type": "icon", "iconName": "calendar-check-02",
                         "size": 22, "iconColor": "$token(fg-brand-primary)"},
                    ],
                },
                {
                    "name": "Att Body",
                    "type": "frame",
                    "layoutSizingHorizontal": "FILL",
                    "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 4},
                    "children": [
                        {"name": "att-headline", "type": "text", "characters": headline,
                         "fontSize": 15, "fontWeight": 700, "fill": "$token(text-primary)"},
                        {"name": "att-sub", "type": "text", "characters": sub,
                         "fontSize": 12, "fontWeight": 500, "fill": "$token(text-tertiary)"},
                    ],
                },
                {"type": "icon", "iconName": "chevron-right", "size": 16,
                 "iconColor": "$token(fg-tertiary)"},
            ],
        }],
    )


def _gen_calc_callout(data: dict, scenario: str) -> dict:
    """1.3b 계산 callout — '얼마까지 모을 수 있는 지 확인해보세요.'"""
    text = data.get("text", "얼마까지 모을 수 있는 지 확인해보세요.")
    return _wrap_section(
        "Calc Callout Wrap",
        {"paddingTop": 8, "paddingBottom": 12},
        [{
            "name": "Calc Callout",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "fill": "$token(bg-brand-section)",
            "cornerRadius": 16,
            "autoLayout": {
                "layoutMode": "HORIZONTAL",
                "paddingLeft": 16, "paddingRight": 16,
                "paddingTop": 14, "paddingBottom": 14,
                "itemSpacing": 12,
                "counterAxisAlignItems": "CENTER",
            },
            "children": [
                {
                    "name": "Calc Icon Wrap",
                    "type": "frame",
                    "width": 36, "height": 36, "cornerRadius": 18,
                    "fill": "$token(bg-primary)",
                    "autoLayout": {"layoutMode": "HORIZONTAL",
                                  "primaryAxisAlignItems": "CENTER",
                                  "counterAxisAlignItems": "CENTER"},
                    "children": [
                        {"type": "icon", "iconName": "help-circle", "size": 20,
                         "iconColor": "$token(fg-brand-primary)"},
                    ],
                },
                {"name": "calc-text", "type": "text",
                 "layoutSizingHorizontal": "FILL",
                 "characters": text,
                 "fontSize": 14, "fontWeight": 600,
                 "fill": "$token(text-primary)"},
                {"type": "icon", "iconName": "chevron-right", "size": 16,
                 "iconColor": "$token(fg-brand-primary)"},
            ],
        }],
    )


def _gen_recommend_stage_card(data: dict, scenario: str) -> dict:
    """1.5 추천 스테이지 카드 — eyebrow + title + currency hero + stepper + round + CTA."""
    section_title = data.get("section_title", "추천 스테이지")
    personal_caption = data.get("personal_caption", "회원님을 위한 추천")
    title = data.get("title", "총 1,300만원 모으기 도전, 13개월에 받아가요")
    label = data.get("label", "예상 수령 금액 (1회차)")
    currency_hero = data.get("currency_hero", "1,300,000원")
    currency_sub = data.get("currency_sub", "월 100,000원 · 13개월 · 납입 후 목표 수령")
    stepper_amount = data.get("stepper_amount") or {"label": "월", "value": "10만원"}
    stepper_period = data.get("stepper_period") or {"label": "기간", "value": "13개월"}
    round_sel = data.get("round_selector") or {"total": 13, "current": 1}
    purpose_tag = data.get("purpose_tag", "1회차")
    purpose_text = data.get("purpose_text", "납입 후 목적 수령")
    show_all_cta = data.get("show_all_cta", "추천 전체 보기 (13개)")

    def stepper(label_text: str, value_text: str) -> dict:
        return {
            "name": f"Stepper {label_text}",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "fill": "$token(bg-secondary)",
            "cornerRadius": 14,
            "autoLayout": {
                "layoutMode": "HORIZONTAL",
                "paddingLeft": 12, "paddingRight": 12,
                "paddingTop": 12, "paddingBottom": 12,
                "itemSpacing": 8,
                "primaryAxisAlignItems": "SPACE_BETWEEN",
                "counterAxisAlignItems": "CENTER",
            },
            "children": [
                {"type": "icon", "iconName": "minus-circle", "size": 20,
                 "iconColor": "$token(fg-tertiary)"},
                {
                    "name": "stepper-body",
                    "type": "frame",
                    "layoutSizingHorizontal": "HUG",
                    "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 2,
                                  "counterAxisAlignItems": "CENTER"},
                    "children": [
                        {"name": "lbl", "type": "text", "characters": label_text,
                         "fontSize": 11, "fontWeight": 500,
                         "fill": "$token(text-tertiary)"},
                        {"name": "val", "type": "text", "characters": value_text,
                         "fontSize": 16, "fontWeight": 700,
                         "fill": "$token(text-primary)"},
                    ],
                },
                {"type": "icon", "iconName": "plus-circle", "size": 20,
                 "iconColor": "$token(fg-brand-primary)"},
            ],
        }

    # round selector — current 는 brand, 나머지는 grey
    total = round_sel.get("total", 13)
    current = round_sel.get("current", 1)
    round_cells = []
    for i in range(1, total + 1):
        is_cur = (i == current)
        round_cells.append({
            "name": f"round-{i}", "type": "frame",
            "width": 22, "height": 22, "cornerRadius": 11,
            "fill": f"$token({'bg-brand-solid' if is_cur else 'bg-secondary'})",
            "autoLayout": {"layoutMode": "HORIZONTAL",
                          "primaryAxisAlignItems": "CENTER",
                          "counterAxisAlignItems": "CENTER"},
            "children": [{
                "name": "n", "type": "text", "characters": str(i),
                "fontSize": 11 if i < 10 else 10,
                "fontWeight": 700 if is_cur else 500,
                "fill": f"$token({'fg-white' if is_cur else 'text-tertiary'})",
                **({"fontColor": "$token(fg-white)"} if is_cur else {}),
            }],
        })

    return _wrap_section(
        "Recommend Stage Wrap",
        {"paddingTop": 16, "paddingBottom": 8},
        [
            # 섹션 타이틀
            {
                "name": "Recommend Title Row",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "primaryAxisAlignItems": "SPACE_BETWEEN",
                    "counterAxisAlignItems": "CENTER",
                    "paddingBottom": 12,
                },
                "children": [
                    {"name": "rec-title", "type": "text", "characters": section_title,
                     "fontSize": 18, "fontWeight": 700, "fill": "$token(text-primary)"},
                ],
            },
            # 카드
            {
                "name": "Recommend Stage Card",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "fill": "$token(bg-primary)",
                "cornerRadius": 20,
                "strokeColor": "$token(border-secondary)",
                "strokeWeight": 1,
                "autoLayout": {
                    "layoutMode": "VERTICAL",
                    "paddingLeft": 18, "paddingRight": 18,
                    "paddingTop": 22, "paddingBottom": 18,
                    "itemSpacing": 18,
                },
                "children": [
                    {"name": "polish-personal-caption", "type": "text",
                     "characters": personal_caption,
                     "fontSize": 12, "fontWeight": 500, "fill": "$token(text-tertiary)"},
                    {"name": "polish-title", "type": "text", "characters": title,
                     "fontSize": 18, "fontWeight": 700, "fill": "$token(text-primary)"},
                    {"name": "polish-label", "type": "text", "characters": label,
                     "fontSize": 12, "fontWeight": 500, "fill": "$token(text-tertiary)"},
                    {"name": "polish-currency", "type": "text", "characters": currency_hero,
                     "fontSize": 32, "fontWeight": 700,
                     "fill": "$token(text-brand-primary)"},
                    {"name": "polish-currency-sub", "type": "text", "characters": currency_sub,
                     "fontSize": 12, "fontWeight": 500, "fill": "$token(text-tertiary)"},
                    # Stepper row
                    {
                        "name": "Stepper Row",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 10,
                                      "primaryAxisAlignItems": "MIN",
                                      "counterAxisAlignItems": "CENTER"},
                        "children": [
                            stepper(stepper_amount["label"], stepper_amount["value"]),
                            stepper(stepper_period["label"], stepper_period["value"]),
                        ],
                    },
                    # Round selector
                    {
                        "name": "Round Selector",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 6,
                                      "primaryAxisAlignItems": "SPACE_BETWEEN",
                                      "counterAxisAlignItems": "CENTER"},
                        "_repetitionAllowed": "round selector cells",
                        "children": round_cells,
                    },
                    # Purpose row
                    {
                        "name": "Round Detail Row",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "autoLayout": {
                            "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "SPACE_BETWEEN",
                            "counterAxisAlignItems": "CENTER",
                        },
                        "children": [
                            {
                                # 회차 라벨 = DS Badge instance (raw pill 로 만들면
                                # detect_button_shape 가 Action Button 으로 오인 swap →
                                # '○ 1회차 ○' 깨짐). 명시적 Badge instance 로 근본 차단.
                                "name": "round-tag",
                                "type": "instance",
                                "componentKey": _K_BADGE_BRAND,
                                "layoutSizingHorizontal": "HUG",
                                "_instanceText": purpose_tag,
                            },
                            {"name": "round-purpose", "type": "text",
                             "characters": purpose_text,
                             "fontSize": 13, "fontWeight": 500,
                             "fill": "$token(text-secondary)"},
                        ],
                    },
                    # CTA = DS Action Button instance (raw frame + trailing chevron 이면
                    # detect_button_shape 가 label-only 아니라 판단해 swap 못함 →
                    # 명시적 instance 로 근본 차단. _instanceText 는 post-fix 가 적용,
                    # icon off 는 ds-button-sizing 이 적용).
                    {
                        "name": "Recommend All CTA",
                        "type": "instance",
                        "componentKey": _K_ACTION_BTN_PRIMARY,
                        "layoutSizingHorizontal": "FILL",
                        "_instanceText": show_all_cta,
                        "instanceProperties": dict(_BTN_ICON_OFF),
                    },
                ],
            },
        ],
    )


def _gen_participating_section(data: dict, scenario: str) -> dict:
    """1.6 참여중/찜한 스테이지 — empty 면 empty state / active 면 4-card grid.

    spec.mock_data.participating.cards 가 있으면 grid, 없으면 empty.
    """
    is_empty = scenario == "empty"
    tabs = data.get("tabs") or ["참여 중인 스테이지", "찜한 스테이지"]
    active_tab = data.get("active_tab", 0)
    cards = data.get("cards") or []

    # Tabs row (참여 중 | 찜한)
    tabs_row = {
        "name": "Participating Tabs Row",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "paddingLeft": 20, "paddingRight": 20,
            "itemSpacing": 18,
            "counterAxisAlignItems": "CENTER",
        },
        "children": [
            {"name": "part-tab-0", "type": "text", "characters": tabs[0],
             "fontSize": 17, "fontWeight": 700 if active_tab == 0 else 500,
             "fill": f"$token({'text-primary' if active_tab == 0 else 'text-tertiary'})"},
            {"name": "part-divider", "type": "rectangle",
             "width": 1, "height": 14, "fill": "$token(border-secondary)"},
            {"name": "part-tab-1", "type": "text", "characters": tabs[1] if len(tabs) > 1 else "",
             "fontSize": 17, "fontWeight": 700 if active_tab == 1 else 500,
             "fill": f"$token({'text-primary' if active_tab == 1 else 'text-tertiary'})"},
        ],
    }

    # Empty state OR Grid
    if is_empty or not cards:
        body = {
            "name": "Participating Empty Wrap",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "autoLayout": {"layoutMode": "VERTICAL",
                          "paddingLeft": 20, "paddingRight": 20},
            "children": [{
                "name": "Empty Card",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "fill": "$token(bg-primary)",
                "cornerRadius": 20,
                "strokeColor": "$token(border-secondary)",
                "strokeWeight": 1,
                "autoLayout": {
                    "layoutMode": "VERTICAL",
                    "paddingLeft": 24, "paddingRight": 24,
                    "paddingTop": 36, "paddingBottom": 36,
                    "itemSpacing": 14,
                    "counterAxisAlignItems": "CENTER",
                },
                "children": [
                    {
                        "name": "Empty Icon Wrap",
                        "type": "frame",
                        "width": 56, "height": 56, "cornerRadius": 28,
                        "layoutSizingHorizontal": "FIXED",
                        "layoutSizingVertical": "FIXED",
                        "fill": "$token(bg-secondary)",
                        "autoLayout": {"layoutMode": "HORIZONTAL",
                                      "primaryAxisAlignItems": "CENTER",
                                      "counterAxisAlignItems": "CENTER"},
                        "children": [{"type": "icon", "iconName": "inbox-01",
                                     "size": 28, "iconColor": "$token(fg-tertiary)"}],
                    },
                    {"name": "empty-title", "type": "text",
                     "characters": "참여 중인 스테이지가 없습니다",
                     "fontSize": 15, "fontWeight": 700, "fill": "$token(text-primary)"},
                    {"name": "empty-sub", "type": "text",
                     "characters": "추천 스테이지에서 첫 스테이지를 시작해보세요",
                     "fontSize": 13, "fontWeight": 500, "fill": "$token(text-tertiary)"},
                ],
            }],
        }
    else:
        # 4-card grid: 2 rows × 2 cards
        def stage_card(spec_card: dict) -> dict:
            progress = spec_card.get("progress", 0)
            bar_w = max(int(160 * progress / 100), 6) if progress > 0 else 0
            return {
                "name": f"Stage Card {spec_card.get('amount', '')}",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "fill": "$token(bg-primary)",
                "strokeColor": "$token(border-secondary)",
                "strokeWeight": 1,
                "cornerRadius": 16,
                "autoLayout": {
                    "layoutMode": "VERTICAL",
                    "paddingTop": 14, "paddingBottom": 14,
                    "paddingLeft": 14, "paddingRight": 14,
                    "itemSpacing": 8,
                },
                "children": [
                    {
                        "name": "status-pill",
                        "type": "frame",
                        "layoutSizingHorizontal": "HUG",
                        "fill": f"$token({spec_card.get('status_color', 'bg-secondary')})",
                        "cornerRadius": 999,
                        "autoLayout": {"layoutMode": "HORIZONTAL",
                                      "paddingTop": 4, "paddingBottom": 4,
                                      "paddingLeft": 10, "paddingRight": 10},
                        "children": [{
                            "type": "text", "characters": spec_card.get("status", ""),
                            "fontSize": 11, "fontWeight": 700,
                            "fill": f"$token({spec_card.get('status_text', 'text-tertiary')})",
                        }],
                    },
                    {"name": "stage-amount", "type": "text",
                     "characters": spec_card.get("amount", ""),
                     "fontSize": 18, "fontWeight": 700, "fill": "$token(text-primary)"},
                    {"name": "stage-subtitle", "type": "text",
                     "characters": spec_card.get("subtitle", ""),
                     "fontSize": 12, "fontWeight": 500, "fill": "$token(text-tertiary)"},
                    {
                        "name": "progress-track",
                        "type": "frame",
                        "layoutSizingHorizontal": "FILL",
                        "layoutSizingVertical": "FIXED",
                        "height": 6,
                        "fill": "$token(bg-secondary)",
                        "cornerRadius": 3,
                        "autoLayout": {"layoutMode": "HORIZONTAL",
                                      "primaryAxisAlignItems": "MIN",
                                      "paddingTop": 0, "paddingBottom": 0,
                                      "paddingLeft": 0, "paddingRight": 0},
                        "children": [{
                            "name": "progress-fill", "type": "rectangle",
                            "width": bar_w, "height": 6, "cornerRadius": 3,
                            "fill": f"$token({spec_card.get('bar_fill', 'bg-tertiary')})",
                        }] if bar_w > 0 else [],
                    },
                    {"type": "text", "characters": spec_card.get("round", ""),
                     "fontSize": 12, "fontWeight": 600, "fill": "$token(text-secondary)"},
                ],
            }

        # 2 rows
        rows = []
        for i in range(0, len(cards), 2):
            row_cards = cards[i:i+2]
            rows.append({
                "name": f"row{i//2 + 1}",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 10,
                              "primaryAxisAlignItems": "MIN",
                              "counterAxisAlignItems": "MIN"},
                "children": [stage_card(c) for c in row_cards],
            })

        body = {
            "name": "Participation Grid",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "_polished": True,
            "_repetitionAllowed": "mock stage cards grid",
            "autoLayout": {
                "layoutMode": "VERTICAL",
                "paddingLeft": 20, "paddingRight": 20,
                "itemSpacing": 10,
            },
            "children": rows,
        }

    return {
        "name": "Participating Wrap",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "fill": "$token(bg-primary)",
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "paddingLeft": 0, "paddingRight": 0,
            "paddingTop": 24, "paddingBottom": 8,
            "itemSpacing": 14,
        },
        "children": [tabs_row, body],
    }


def _gen_lounge_section(data: dict, scenario: str) -> dict:
    """1.7 라운지 — 5 product cards carousel + 예치금."""
    section_title = data.get("section_title", "추천 상품 (라운지)")
    deposit = data.get("deposit", "")
    products = data.get("products") or []

    def product_card(p: dict) -> dict:
        return {
            "name": f"Lounge Card {p.get('brand', '')}",
            "type": "frame",
            "width": 148,
            "layoutSizingHorizontal": "FIXED",
            # 세로는 HUG — Image(120)+Body 콘텐츠에 맞게 자람. FIXED 200 으로 박으면
            # clipsContent(rounded card 필수)에 의해 하단 가격 텍스트가 잘림 (2026-05-28).
            "layoutSizingVertical": "HUG",
            "cornerRadius": 16,
            "fill": "$token(bg-primary)",
            "strokeColor": "$token(border-secondary)",
            "strokeWeight": 1,
            "clipsContent": True,
            "_imagelessAllowed": "imageQuery on inner Image frame",
            "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 0},
            "children": [
                {
                    "name": f"Lounge Image",
                    "type": "frame",
                    "layoutSizingHorizontal": "FILL",
                    "height": 120,
                    "fill": "$token(bg-brand-section)",
                    "imageQuery": p.get("imageQuery", "premium product"),
                    "autoLayout": {"layoutMode": "HORIZONTAL",
                                  "primaryAxisAlignItems": "CENTER",
                                  "counterAxisAlignItems": "CENTER"},
                    "children": [{"type": "icon", "iconName": "gift-01",
                                 "size": 32, "iconColor": "$token(fg-brand-primary)"}],
                },
                {
                    "name": f"Lounge Card Body",
                    "type": "frame",
                    "layoutSizingHorizontal": "FILL",
                    "autoLayout": {"layoutMode": "VERTICAL",
                                  "paddingLeft": 12, "paddingRight": 12,
                                  "paddingTop": 10, "paddingBottom": 12,
                                  "itemSpacing": 4},
                    "children": [
                        {"name": "brand", "type": "text", "characters": p.get("brand", ""),
                         "fontSize": 11, "fontWeight": 500, "fill": "$token(text-tertiary)"},
                        {"name": "name", "type": "text", "characters": p.get("name", ""),
                         "fontSize": 13, "fontWeight": 700, "fill": "$token(text-primary)"},
                        {"name": "price", "type": "text", "characters": p.get("price", ""),
                         "fontSize": 13, "fontWeight": 700,
                         "fill": "$token(text-brand-primary)"},
                    ],
                },
            ],
        }

    return {
        "name": "Lounge Section",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "fill": "$token(bg-primary)",
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "paddingLeft": 0, "paddingRight": 0,
            "paddingTop": 28, "paddingBottom": 12,
            "itemSpacing": 14,
        },
        "children": [
            {
                "name": "Lounge Title Row",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "paddingLeft": 20, "paddingRight": 20,
                    "primaryAxisAlignItems": "SPACE_BETWEEN",
                    "counterAxisAlignItems": "CENTER",
                },
                "children": [
                    {"name": "lounge-title", "type": "text", "characters": section_title,
                     "fontSize": 18, "fontWeight": 700, "fill": "$token(text-primary)"},
                    {"name": "lounge-deposit", "type": "text", "characters": deposit,
                     "fontSize": 12, "fontWeight": 600,
                     "fill": "$token(text-brand-primary)"},
                ],
            },
            {
                "name": "Lounge Carousel",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "clipsContent": True,
                "_repetitionAllowed": "carousel product cards",
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "paddingLeft": 20, "paddingRight": 20,
                    "itemSpacing": 12,
                },
                "children": [product_card(p) for p in products],
            },
        ],
    }


def _gen_subcard_cta(data: dict, scenario: str) -> dict:
    """포인트 모으기 시작 inline CTA (Footer 직전)."""
    icon = data.get("icon", "gift-01")
    title = data.get("title", "포인트 모으기 시작")
    sub = data.get("sub", "출석 체크 + 스테이지 참여로 포인트 받기")
    return _wrap_section(
        "Sub-card CTA",
        {"paddingTop": 8, "paddingBottom": 8},
        [{
            "name": "Points Card",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "fill": "$token(bg-secondary)",
            "cornerRadius": 16,
            "autoLayout": {
                "layoutMode": "HORIZONTAL",
                "paddingLeft": 14, "paddingRight": 14,
                "paddingTop": 14, "paddingBottom": 14,
                "itemSpacing": 12,
                "counterAxisAlignItems": "CENTER",
            },
            "children": [
                {
                    "name": "points-icon-wrap",
                    "type": "frame",
                    "width": 36, "height": 36, "cornerRadius": 12,
                    "fill": "$token(bg-brand-primary)",
                    "autoLayout": {"layoutMode": "HORIZONTAL",
                                  "primaryAxisAlignItems": "CENTER",
                                  "counterAxisAlignItems": "CENTER"},
                    "children": [{"type": "icon", "iconName": icon, "size": 20,
                                 "iconColor": "$token(fg-brand-primary)"}],
                },
                {
                    "name": "points-body",
                    "type": "frame",
                    "layoutSizingHorizontal": "FILL",
                    "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 2},
                    "children": [
                        {"name": "points-title", "type": "text", "characters": title,
                         "fontSize": 14, "fontWeight": 700, "fill": "$token(text-primary)"},
                        {"name": "points-sub", "type": "text", "characters": sub,
                         "fontSize": 12, "fontWeight": 500, "fill": "$token(text-tertiary)"},
                    ],
                },
                {"type": "icon", "iconName": "chevron-right", "size": 16,
                 "iconColor": "$token(fg-tertiary)"},
            ],
        }],
    )


_GENERATORS = {
    # A.3.2 — simple template-driven
    "nav_bar": _gen_nav_bar,
    "mode_tabs": _gen_mode_tabs,
    "tab_bar": _gen_tab_bar,
    "fab": _gen_fab,
    "footer_policy": _gen_footer_policy,
    # A.3.3 — complex generators (2026-05-28 박힘)
    "stage_progress_card": _gen_stage_progress_card,
    "attendance_banner": _gen_attendance_banner,
    "calc_callout": _gen_calc_callout,
    "recommend_stage_card": _gen_recommend_stage_card,
    "participating_section": _gen_participating_section,
    "lounge_section": _gen_lounge_section,
    "top_alert_banner": _gen_top_alert_banner,
    "screen_hero": _gen_screen_hero,
    "subcard_cta": _gen_subcard_cta,
}


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────


def build_unified_blueprint(spec: dict, wire_content: Optional[dict] = None,
                             root_name: Optional[str] = None) -> dict:
    """unified spec → blueprint dict.

    Args:
        spec: archetype base spec (mock_data + polish + sections)
        wire_content: Claude 가 추출한 와이어 콘텐츠 dict (optional)
        root_name: blueprint root name (default: archetype + timestamp)

    Returns:
        blueprint dict (cmd_build 와 호환)

    Flow:
        1. scenario 결정 (auto → wire_content 기반)
        2. effective_data = mock_data (active) or wire_content (empty)
        3. sections[] walk → generator dispatch
        4. _wireframeContent / _scenario / _unified meta 박음
    """
    if not isinstance(spec, dict):
        raise ValueError("spec must be a dict")

    archetype = spec.get("archetype", "imin_home")
    mock_data = spec.get("mock_data") or {}
    polish_flags = spec.get("polish") or {}
    sections_order = spec.get("sections") or []

    # 1. scenario 결정
    scenario = spec.get("scenario", "auto")
    if scenario == "auto":
        scenario = detect_scenario(wire_content or {})

    # 2. effective_data — active 면 mock 우선, empty 면 wire_content 우선 (있으면)
    # 현재는 mock 만 — 와이어 콘텐츠 통합은 A.3.3 에서 generator 별로 처리
    effective_data = copy.deepcopy(mock_data)

    # 3. sections walk
    children = []
    for sec_entry in sections_order:
        if not isinstance(sec_entry, dict):
            continue
        sec_type = sec_entry.get("type")
        if not sec_type:
            continue
        # scenario_only 가드
        scenario_only = sec_entry.get("scenario_only")
        if scenario_only and scenario_only != scenario:
            continue
        # data resolve — data_ref 우선, 없으면 effective_data[section_type], 없으면 suffix 제거 매칭
        data_key = sec_entry.get("data_ref")
        if not data_key:
            data_key = sec_type
            for suffix in ("_card", "_section", "_banner", "_callout", "_policy", "_bar", "_tabs"):
                if data_key.endswith(suffix):
                    data_key = data_key[:-len(suffix)]
                    break
        data = effective_data.get(sec_type) or effective_data.get(data_key) or {}
        # sec_entry 의 inline 데이터 override
        for k, v in sec_entry.items():
            if k not in ("type", "data_ref", "scenario_only"):
                data[k] = v

        gen = _GENERATORS.get(sec_type)
        if not gen:
            print(f"  [unified] ⚠️ unknown section type: {sec_type} — skip")
            continue
        try:
            node = gen(data, scenario)
            children.append(node)
        except Exception as e:
            print(f"  [unified] {sec_type} generator failed: {e}")

    # 4. blueprint dict 조립
    name = root_name or f"{archetype}_unified"
    blueprint = {
        "rootName": name,
        "name": name,
        "type": "frame",
        "width": 393,
        "height": 2860,
        "fill": "$token(bg-primary)",
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "itemSpacing": 0,
            "paddingTop": 0, "paddingBottom": 0,
            "paddingLeft": 0, "paddingRight": 0,
        },
        "children": children,
        # meta
        "_wireframeContent": wire_content or {"_unifiedMode": True},
        "_scenario": scenario,
        "_unified": True,
        "_archetype": archetype,
    }
    # 2026-05-28 사용자 "레퍼런스 안 봤다" — generator 경로가 Step A.0 references
    # 강제를 우회하던 회귀 차단. archetype spec 의 references[] 를 blueprint 에 주입해
    # S20/S21 통과 + Step A.0 PNG export → Claude 가 PNG Read 강제. spec 에 references
    # 없으면 _referencesSkipped 로 build 진행 (단 그땐 ref 학습 누락 경고).
    _refs = spec.get("references")
    if _refs:
        blueprint["references"] = _refs
    else:
        blueprint["_referencesSkipped"] = f"archetype '{archetype}' spec 에 references 미정의 — spec 에 추가 필요"
    # 2026-05-28 (R27): round selector(1~13)·day strip 등 기획 의도 반복은 정상 →
    # _repetitionAllowed 로 bypass (반복 노이즈 검출이 회차/일자 selector 를 오탐).
    blueprint["_repetitionAllowed"] = "imin 회차 selector(1~13) / day strip / 카드 grid — 기획 의도 반복"
    return blueprint


# ─────────────────────────────────────────────────────────────
# CLI for testing
# ─────────────────────────────────────────────────────────────


def _cli():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 unified_blueprint.py <archetype> [wire_content.json] [output.json]")
        print("Example: python3 unified_blueprint.py imin_home")
        sys.exit(1)

    archetype = sys.argv[1]
    spec = load_archetype_spec(archetype)
    if not spec:
        print(f"❌ archetype spec not found: {archetype}")
        sys.exit(1)

    wire = None
    if len(sys.argv) >= 3:
        with open(sys.argv[2]) as f:
            wire = json.load(f)

    bp = build_unified_blueprint(spec, wire_content=wire)
    out = sys.argv[3] if len(sys.argv) >= 4 else f"scripts/blueprint_unified_{archetype}.json"
    with open(out, "w") as f:
        json.dump(bp, f, indent=2, ensure_ascii=False)
    print(f"✅ unified blueprint generated: {out}")
    print(f"   scenario: {bp['_scenario']}")
    print(f"   sections: {len(bp['children'])}")


if __name__ == "__main__":
    _cli()
