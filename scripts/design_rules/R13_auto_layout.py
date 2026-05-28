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


register(Rule(
    rule_id="R13-auto-layout",
    title="autoLayout sanity",
    description="Valid layoutMode, padding shape, SPACE_BETWEEN/FILL conflict.",
    check_blueprint_fn=_check,
))
