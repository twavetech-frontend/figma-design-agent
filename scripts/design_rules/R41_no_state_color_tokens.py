"""R41 — No interaction-state color tokens (hover / pressed / focus / disabled).

Project policy 2026-05-12 (user explicit, repeated frustration):
mobile has no hover state — yet builds keep ending up with fills bound to
`bg-brand-secondary-hover`, `*_hover`, `*-pressed`, `*-disabled`, etc.
That happens two ways:

  1. The blueprint author writes `$token(bg-...-hover)` directly  → caught here.
  2. The post-fix token-binding *sweep* reverse-maps a hex to a `-hover`
     variant because it has the same hex as the base token → fixed in
     figma_mcp_client.py `_build_token_index` exclusion list (now also
     excludes the DASH variants `-hover/-pressed/-focused/-focus/
     -visited/-disabled`, not just the underscore ones).

Default brand background is `bg-brand-primary` (or `bg-brand-solid` for a
full-bleed hero card with white text) — never a state/hover variant.

This rule = the lint-side guard for path (1).
"""
from __future__ import annotations

import re
from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


_TOKEN_RE = re.compile(r"\$token\(\s*([^)]+?)\s*\)")
# state / interaction suffixes — both `_suffix` and `-suffix` forms
_STATE_SUFFIXES = (
    "hover", "pressed", "focused", "focus", "visited", "disabled", "active",
)
_STATE_RE = re.compile(r"[_-](" + "|".join(_STATE_SUFFIXES) + r")$", re.I)


def _scan_token_refs(obj, depth: int = 0):
    if depth > 12:
        return
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _scan_token_refs(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from _scan_token_refs(v, depth + 1)
    elif isinstance(obj, str):
        for m in _TOKEN_RE.finditer(obj):
            yield m.group(1).strip()


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        scan_target = {k: v for k, v in node.items() if k != "children"}
        for tok in _scan_token_refs(scan_target):
            if _STATE_RE.search(tok.strip()):
                base = _STATE_RE.sub("", tok.strip())
                yield Violation(
                    "R41-no-state-color", Severity.ERROR, path,
                    f"interaction-state color token '$token({tok})' — mobile "
                    f"has no hover/pressed/focus/disabled. Use the base token "
                    f"'$token({base})' (default brand bg = bg-brand-primary). "
                    f"User policy 2026-05-12.",
                    Phase.LINT,
                )


register(Rule(
    rule_id="R41-no-state-color",
    title="No interaction-state color tokens (hover/pressed/focus/disabled)",
    description=(
        "Ban $token(*-hover / *_hover / *-pressed / *-disabled / ...) — "
        "mobile has no hover. Default brand background is bg-brand-primary."
    ),
    check_blueprint_fn=_check,
))
