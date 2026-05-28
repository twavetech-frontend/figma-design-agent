"""R13 — autoLayout sanity checks.

Three legacy validate_blueprint rules ported from figma_mcp_client.py:
  R13.1  autoLayout.layoutMode/direction must be HORIZONTAL or VERTICAL
  R13.2  autoLayout.padding-as-object → flatten warning
  R13.3  SPACE_BETWEEN parent + FILL child → 0px spacing pitfall
"""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


_VALID_MODES = {"HORIZONTAL", "VERTICAL"}


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        al = node.get("autoLayout")
        if not al:
            continue
        mode = al.get("layoutMode") or al.get("direction")
        if mode and mode not in _VALID_MODES:
            yield Violation(
                "R13.1-layout-mode", Severity.ERROR, path,
                f"invalid layoutMode/direction '{mode}' (must be HORIZONTAL or VERTICAL)",
                Phase.LINT,
            )

        if "padding" in al and isinstance(al["padding"], dict):
            yield Violation(
                "R13.2-padding-object", Severity.WARN, path,
                "autoLayout.padding is an object — auto-flattened, prefer paddingTop/Bottom/Left/Right",
                Phase.LINT, auto_fixable=True,
            )

        if al.get("primaryAxisAlignItems") == "SPACE_BETWEEN":
            for child in node.get("children", []) or []:
                cal = child.get("autoLayout") or {}
                if (child.get("layoutSizingHorizontal") == "FILL"
                        or cal.get("layoutSizingHorizontal") == "FILL"):
                    cname = child.get("name", "?")
                    yield Violation(
                        "R13.3-space-between-fill", Severity.WARN, f"{path} → {cname}",
                        "SPACE_BETWEEN parent + FILL child = 0px spacing",
                        Phase.LINT,
                    )


def _inject(bp: dict) -> dict:
    """R13.3 auto-fix: SPACE_BETWEEN + FILL 자식 → MIN + itemSpacing 으로 교정.

    Why: SPACE_BETWEEN 는 자식 사이 공간을 같이 분배하는데 자식이 FILL 이면
    Figma 는 한 자식에 width 다 주고 나머지 0/1px 로 박살낸다 (Day Strip 회귀).
    FILL 자식 = 균등 분배 의도 → primaryAxisAlignItems MIN + itemSpacing 작은 값.
    2026-05-28 시스템 박힘.
    """
    fixed = 0
    for node, _ in walk_blueprint(bp):
        al = node.get("autoLayout")
        if not al:
            continue
        if al.get("primaryAxisAlignItems") != "SPACE_BETWEEN":
            continue
        has_fill_child = False
        for child in node.get("children", []) or []:
            cal = child.get("autoLayout") or {}
            if (child.get("layoutSizingHorizontal") == "FILL"
                    or cal.get("layoutSizingHorizontal") == "FILL"):
                has_fill_child = True
                break
        if not has_fill_child:
            continue
        al["primaryAxisAlignItems"] = "MIN"
        if "itemSpacing" not in al or al.get("itemSpacing") is None:
            al["itemSpacing"] = 8
        fixed += 1
    if fixed:
        # 인라인 로그 — design_rules base 에 logger 없으므로 print
        print(f"[inject R13.3] SPACE_BETWEEN+FILL → MIN+itemSpacing auto-fix {fixed}건 (Day Strip 회귀 차단)")
    return bp


register(Rule(
    rule_id="R13-auto-layout",
    title="autoLayout sanity",
    description="Valid layoutMode, padding shape, SPACE_BETWEEN/FILL conflict (auto-fix).",
    check_blueprint_fn=_check,
    inject_blueprint_fn=_inject,
))
