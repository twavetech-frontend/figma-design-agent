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
    "_alt", "_on-brand",
    # 🔴 2026-08-14: '_subtle' 은 state 가 아니라 표면 단계 토큰 — ban 목록에서 제외.
    # 사용자 수정본 실측 정본: 변환 트랙 카드 표면 = bg-secondary_subtle(+alpha-black-4 보더).
    # (wallet-withdraw-user-baseline 메모리 — lint 가 정본 토큰을 막던 규칙-게이트 충돌 해소)
    "/bg-disabled", "/bg-active",
    "/bg-primary-solid", "/bg-secondary-solid",
)


def _check_token_name(name: str) -> str | None:
    """Return error message if token name is banned, else None."""
    n = name.strip()
    lower = n.lower()
    # 2026-06-02 사용자 룰: Aqua 보조 액센트 허용. DS 의 Aqua 는 primitive(Colors/Aqua/*)
    # 또는 'Component colors/Utility/Aqua/utility-blue-*' 로만 존재(semantic 단축명 없음)
    # → 'aqua' 가 명시된 토큰은 primitive-prefix ban 에서 예외. (state 변형은 계속 검사)
    if "aqua" not in lower:
        for pref in _BANNED_PRIMITIVE_PREFIXES:
            if n.startswith(pref):
                return f"primitive scale token '{n}' — use semantic Colors/Background|Foreground|Border|Text"
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
