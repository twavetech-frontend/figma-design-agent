"""R21 — Background color hierarchy.

Strict order top-down:
  bg-primary (root, depth 0)
  → bg-secondary (cards/sections, depth 1)
  → bg-tertiary (insets within secondary, depth 2)
  → bg-quaternary (sub-insets, depth 3)

A node may not skip levels (e.g. bg-primary -> bg-tertiary directly).
A child may use the same level as its parent only if it is structurally
the same kind of surface (rare; warned, not errored).
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple

from .base import Phase, Rule, Severity, Violation, register


_LEVELS = ["bg-primary", "bg-secondary", "bg-tertiary", "bg-quaternary"]
_TOKEN_RE = re.compile(r"^\$token\((.+)\)$")


def _level_of(fill_value) -> Optional[int]:
    """Return 0..3 for known bg-* tokens, None otherwise."""
    if not isinstance(fill_value, str):
        return None
    m = _TOKEN_RE.match(fill_value)
    if not m: return None
    name = m.group(1)
    base = name.split("/")[-1]  # tail after slash
    for i, lv in enumerate(_LEVELS):
        if base == lv:
            return i
    return None


def _node_bg_level(node: dict) -> Optional[int]:
    fill = node.get("fill")
    lv = _level_of(fill)
    if lv is not None: return lv
    fills = node.get("fills")
    if isinstance(fills, list):
        for f in fills:
            if isinstance(f, dict):
                lv = _level_of(f.get("color")) or _level_of(f.get("fill"))
                if lv is not None: return lv
    return None


def _walk(node: dict, path: str, parent_level: Optional[int],
          violations: List[Violation]):
    lv = _node_bg_level(node)
    if lv is not None:
        if parent_level is None:
            # Root sets baseline. Should be 0 (bg-primary).
            if path == "root" and lv != 0:
                violations.append(Violation(
                    "R21.0-root-bg", Severity.ERROR, path,
                    f"root bg level {_LEVELS[lv]} — must be bg-primary",
                    Phase.LINT,
                ))
        else:
            if lv > parent_level + 1:
                skipped = _LEVELS[parent_level + 1: lv]
                violations.append(Violation(
                    "R21.1-bg-skip", Severity.ERROR, path,
                    f"bg jumps from {_LEVELS[parent_level]} to {_LEVELS[lv]} "
                    f"— must traverse {', '.join(skipped)} first",
                    Phase.LINT,
                ))
            elif lv < parent_level:
                # Child going lighter than parent — allowed (e.g. inverse insets)
                # but warn so author confirms intent.
                violations.append(Violation(
                    "R21.2-bg-reverse", Severity.WARN, path,
                    f"child bg {_LEVELS[lv]} is lighter than parent {_LEVELS[parent_level]}",
                    Phase.LINT,
                ))
        next_level = lv
    else:
        next_level = parent_level

    for i, child in enumerate(node.get("children") or []):
        cn = child.get("name", f"child[{i}]")
        _walk(child, f"{path}/{cn}", next_level, violations)


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    out: List[Violation] = []
    _walk(bp, "root", None, out)
    return out


register(Rule(
    rule_id="R21-bg-hierarchy",
    title="Background color hierarchy",
    description="bg-primary → bg-secondary → bg-tertiary → bg-quaternary, no skipping.",
    check_blueprint_fn=_check,
))
