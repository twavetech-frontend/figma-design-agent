"""R44 — Disabled slot cell pattern (참여 불가).

Rule (from user, 2026-05-24):
  A "참여 불가 / disabled / locked" cell in a number-selector grid must
  visually match the legend swatch: a gray-filled square (bg-tertiary)
  with the lock icon centered, and **no number text**.

  Many blueprints today emit a disabled slot that still has the number
  text PLUS a small lock icon at the corner — that's wrong:
    - The number reads as "selectable" even though the lock says otherwise.
    - The legend's "참여 불가" swatch is a filled gray square with a lock,
      not a number — the slot must match it for users to map legend→cells.

Detection (shape-based, parent-name-agnostic):
  Any FRAME blueprint node whose direct children include
    (a) a digit-only TEXT node, AND
    (b) a lock-shaped icon node
  is a disabled slot. Legend swatches don't have the number text, so they
  do not match — no risk of false positives.

Phases:
  L3 inject   — strip the digit TEXT child, force fill=$token(bg-tertiary),
                clear stroke, center the lock via auto-layout. Idempotent.
  L5 verify   — assert no built FRAME still has both a digit TEXT and a
                lock-named child.
"""
from __future__ import annotations

import re
from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


_DIGIT_RE = re.compile(r"^\d+$")
_LOCK_NAME_RE = re.compile(r"\b(lock|lk|padlock)\b", re.I)


def _is_lock_icon(child: dict) -> bool:
    name = (child.get("name") or "").strip()
    typ = (child.get("type") or "").lower()
    # Blueprint icon nodes are typically type="icon"; allow vector/instance too.
    if typ not in ("icon", "vector", "instance"):
        return False
    return bool(_LOCK_NAME_RE.search(name))


def _is_number_text(child: dict) -> bool:
    if (child.get("type") or "").lower() != "text":
        return False
    text = (child.get("text") or child.get("characters") or "").strip()
    return bool(_DIGIT_RE.match(text))


def _is_disabled_slot(node: dict) -> bool:
    """A frame that has BOTH a digit-text child and a lock-icon child."""
    if (node.get("type") or "").lower() != "frame":
        return False
    children = node.get("children") or []
    return any(_is_number_text(c) for c in children) and any(
        _is_lock_icon(c) for c in children
    )


def _inject(blueprint: dict) -> dict:
    """Strip digit text + force gray fill on disabled slots. Idempotent."""
    for node, _path in walk_blueprint(blueprint):
        if not _is_disabled_slot(node):
            continue
        # 1) Drop the digit text child — keep the lock + anything else.
        node["children"] = [
            c for c in (node.get("children") or []) if not _is_number_text(c)
        ]
        # 2) Force the gray fill that matches the legend swatch.
        node["fill"] = "$token(bg-tertiary)"
        # 3) Filled-look — clear any stroke that was used for the outlined
        #    "available" cell style.
        node.pop("stroke", None)
        node.pop("strokeColor", None)
        # 4) Center the lock icon via auto-layout (safe defaults).
        al = node.setdefault("autoLayout", {})
        al.setdefault("layoutMode", "VERTICAL")
        al["primaryAxisAlignItems"] = "CENTER"
        al["counterAxisAlignItems"] = "CENTER"
        # Conservative padding — keep whatever the cell already had,
        # only fill in if completely missing.
        for k in ("paddingTop", "paddingBottom", "paddingLeft", "paddingRight"):
            al.setdefault(k, 0)
    return blueprint


def _check_built(tree: dict, ctx: dict) -> Iterable[Violation]:
    """Post-build assertion: built tree must not retain digit+lock combo."""
    def walk(node, path="root"):
        children = node.get("children") or []
        if node.get("type") == "FRAME":
            has_digit_text = any(
                c.get("type") == "TEXT"
                and _DIGIT_RE.match((c.get("characters") or "").strip())
                for c in children
            )
            has_lock = any(
                _LOCK_NAME_RE.search(c.get("name") or "")
                and c.get("type") in ("INSTANCE", "VECTOR", "FRAME", "GROUP")
                for c in children
            )
            if has_digit_text and has_lock:
                yield Violation(
                    rule_id="R44-disabled-slot",
                    severity=Severity.WARN,
                    path=f"{path}/{node.get('name', '?')}",
                    message=(
                        "Disabled slot still has number text + lock — "
                        "expected lock-only on gray fill (bg-tertiary)."
                    ),
                    phase=Phase.VERIFY,
                )
        for i, c in enumerate(children):
            yield from walk(c, f"{path}/{c.get('name', f'child[{i}]')}")
    yield from walk(tree)


register(Rule(
    rule_id="R44-disabled-slot",
    title="Disabled slot = gray fill + lock icon only (no number)",
    description=(
        "Number-selector grid: any cell with BOTH a digit text and a lock "
        "icon must be reduced to lock-only on bg-tertiary, matching the "
        "'참여 불가' legend swatch. Detected by child shape (digit text + "
        "lock icon) so legend swatches (lock-only, no digit) are safe."
    ),
    inject_blueprint_fn=_inject,
    check_built_fn=_check_built,
))
