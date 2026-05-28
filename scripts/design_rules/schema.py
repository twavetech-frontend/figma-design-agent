"""L1 — Blueprint structural schema.

Hard constraints that make a blueprint *parseable*:
  - root must be a dict with name + type
  - every node has type ∈ {frame, FRAME, text, TEXT, rectangle, ...}
  - color fields must NOT be raw hex strings (#RRGGBB) — must be $token() or RGBA dict
  - $token() values must NOT name primitive scales or banned state tokens

This runs BEFORE semantic R*-rules (which assume a well-formed tree).
"""
from __future__ import annotations

import re
from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


_ALLOWED_TYPES = {
    "frame", "FRAME",
    "text", "TEXT",
    "rectangle", "RECTANGLE",
    "ellipse", "ELLIPSE",
    "line", "LINE",
    "vector", "VECTOR",
    "instance", "INSTANCE",
    "image", "IMAGE",
    "group", "GROUP",
    # Codebase-specific shorthands handled by builder
    "icon", "ICON",
}

_COLOR_FIELDS = ("fill", "fontColor", "iconColor", "stroke", "strokeColor", "color")

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{3,8}$")
_TOKEN_RE = re.compile(r"^\$token\(([^)]+)\)$")

# Primitive scales — never allowed in $token()
_BANNED_PRIMITIVE_PREFIXES = (
    "Colors/Base/",
    "Colors/Brand/",
    "Colors/Gray ",          # "Gray light/", "Gray dark/", "Gray cool/", etc.
    "Component colors/",
    "_Primitives/",
    "Primitives/",
)

# State / modifier variants — banned for default state
_BANNED_STATE_SUBSTR = (
    "_hover", "_pressed", "_focused", "_focus", "_visited",
    "_subtle", "_alt", "_on-brand",
    "/bg-disabled", "/bg-active",
    "/bg-primary-solid", "/bg-secondary-solid",
)


def _check_token_name(name: str) -> str | None:
    """Return error message if token name is banned, else None."""
    n = name.strip()
    for pref in _BANNED_PRIMITIVE_PREFIXES:
        if n.startswith(pref):
            return f"primitive scale token '{n}' — use semantic Colors/Background|Foreground|Border|Text"
    lower = n.lower()
    for sub in _BANNED_STATE_SUBSTR:
        if sub in lower:
            return f"state/modifier token '{n}' — banned for default rendering"
    return None


def _check_blueprint(bp: dict, ctx: dict) -> Iterable[Violation]:
    if not isinstance(bp, dict):
        yield Violation("S00-root-shape", Severity.ERROR, "root",
                        "blueprint root must be a dict", Phase.SCHEMA)
        return

    if not bp.get("name"):
        yield Violation("S01-root-name", Severity.ERROR, "root",
                        "root.name is required", Phase.SCHEMA)

    for node, path in walk_blueprint(bp):
        ntype = node.get("type", "frame")
        if ntype not in _ALLOWED_TYPES:
            yield Violation("S02-node-type", Severity.ERROR, path,
                            f"unknown type '{ntype}'", Phase.SCHEMA)

        # Color field shape
        for key in _COLOR_FIELDS:
            if key not in node:
                continue
            val = node[key]
            if isinstance(val, str):
                if _HEX_RE.match(val):
                    yield Violation(
                        "S10-no-raw-hex", Severity.ERROR, path,
                        f"{key}='{val}' is raw hex — use $token() or RGBA dict",
                        Phase.SCHEMA,
                    )
                    continue
                m = _TOKEN_RE.match(val)
                if m:
                    err = _check_token_name(m.group(1))
                    if err:
                        yield Violation(
                            "S11-banned-token", Severity.ERROR, f"{path}.{key}",
                            err, Phase.SCHEMA,
                        )


register(Rule(
    rule_id="S00-schema",
    title="Blueprint structural schema",
    description="Required fields, allowed types, no raw hex, no banned tokens.",
    check_blueprint_fn=_check_blueprint,
))
