"""R47 — icon-role 노드에 emoji 절대 금지 (2026-05-27 사용자 강력 명시).

icon-role 노드 (FAB, NavBar icons, Tab Bar icons 등) 안 text 가 emoji 면 build 차단.

Detection:
  - 부모 frame 이름이 'fab' / 'icon' / NavBar / 'tab bar' 안 포함 OR
  - 노드 자체 이름이 'icon' / 'fab-icon' / 'tab-*-icon' 등
  - 그 안 text 가 emoji-only (단일 또는 ZWJ 시퀀스, 비-ASCII 비-한글)

Fix guidance (lint 메시지에 명시):
  - DS icon component 인스턴스 사용 (`type: "instance"` + `componentKey`)
  - 또는 `type: "icon"` + `iconName: "wallet-02"` 등
  - 또는 Pretendard Bold ASCII 텍스트 ("+", "→")
"""
from __future__ import annotations

import re
from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


# emoji detection: 비-ASCII + 비-한글/한자 codepoint
# 한글: AC00-D7AF, 자모 1100-11FF, 호환 자모 3130-318F
# 한자: 4E00-9FFF
_KOREAN_HANJA_RE = re.compile(r"[가-힯ᄀ-ᇿ㄰-㆏一-鿿]")
_ASCII_RE = re.compile(r"[\x00-\x7F]")


def _is_emoji_text(text: str) -> bool:
    """Heuristic: 텍스트에 한글·한자·ASCII 외 문자가 있으면 emoji 로 추정."""
    if not text:
        return False
    t = text.strip()
    if not t:
        return False
    # 모든 char 가 ASCII 또는 한글/한자 면 emoji 아님
    for ch in t:
        if _ASCII_RE.match(ch) or _KOREAN_HANJA_RE.match(ch):
            continue
        # 공백·구두점 제외
        if ch in (" ", "\t", "\n", ",", ".", "·", "/", "-", "_", "(", ")"):
            continue
        return True  # emoji 또는 다른 special char
    return False


_ICON_ROLE_NAME_RE = re.compile(r"\b(fab|icon|tab[-_ ]?bar)\b", re.I)
_ICON_NODE_NAME_RE = re.compile(r"icon|fab[-_ ]icon|tab[-_].*[-_]icon|nav[-_].*[-_]icon", re.I)


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        if (node.get("type") or "").lower() != "text":
            continue
        text = node.get("characters") or node.get("text") or ""
        if not _is_emoji_text(text):
            continue
        # icon-role 컨텍스트 확인: path 안에 fab/icon/tab bar 포함 OR 노드 이름이 icon
        path_low = (path or "").lower()
        node_name = node.get("name") or ""
        in_icon_role = (_ICON_ROLE_NAME_RE.search(path_low)
                        or _ICON_NODE_NAME_RE.search(node_name))
        if not in_icon_role:
            continue
        yield Violation(
            "R47-no-emoji-in-icon-role",
            Severity.ERROR,
            path,
            (f"icon-role 노드에 이모티콘 '{text}' 사용 금지 (2026-05-27 사용자 명시). "
             f"DS icon component instance (`type: \"instance\"` + componentKey) "
             f"또는 `type: \"icon\"` + iconName 사용. "
             f"DS instance 색 override 실패 시 fallback 으로 Pretendard Bold ASCII "
             f"텍스트 (\"+\", \"→\" 등) — emoji 폰트 사용 금지."),
            Phase.LINT,
        )


register(Rule(
    rule_id="R47-no-emoji-in-icon-role",
    title="No emoji in icon-role nodes (FAB / NavBar / Tab Bar icons)",
    description=(
        "icon-role 노드 (FAB, NavBar icons, Tab Bar icons 등) 안 text 에 emoji "
        "(💰🔍⭐ 등) 사용 금지. DS icon component 인스턴스 또는 Pretendard Bold "
        "ASCII (+, → 등) 만 허용. 2026-05-27 사용자 강력 명시."
    ),
    check_blueprint_fn=_check,
))
