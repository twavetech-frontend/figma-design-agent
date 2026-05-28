"""R26 — Aqua / utility-blue-light 사용 금지.

Project policy 2026-05-05 (revised): user explicitly rejected the
introduction of utility-blue-light as a second accent. Stick to brand
purple + semantic grays + error/warning/success only. No aqua, no cyan,
no teal, no utility-blue-light anywhere.

Earlier this session R26 was the *opposite* — promoting utility-blue-light
as a second accent. That was reverted: user said "aqua 컬러 쓰지마라"
2026-05-05.

Triggers:
  • Any blueprint string containing $token(utility-blue-light-*)
  • Any utility-blue / utility-cyan / utility-teal usage
"""
from __future__ import annotations

import re
from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


_TOKEN_RE = re.compile(r"\$token\(\s*([^)]+?)\s*\)")
_FORBIDDEN_PALETTES = (
    "utility-blue-light-",
    "utility-blue-",
    "utility-cyan-",
    "utility-teal-",
)


def _scan_token_refs(obj, depth: int = 0):
    if depth > 12: return
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
            tl = tok.lower()
            for forbidden in _FORBIDDEN_PALETTES:
                if forbidden in tl:
                    yield Violation(
                        "R26-no-aqua", Severity.ERROR, path,
                        f"forbidden token '{tok}'. Aqua/cyan/teal 사용 금지 — "
                        f"brand purple + semantic gray + error/warning/success "
                        f"만 사용. 사용자 명시 reject 2026-05-05.",
                        Phase.LINT,
                    )
                    break


register(Rule(
    rule_id="R26-no-aqua",
    title="No aqua/utility-blue-light tokens (user rejected)",
    description="Stick to brand + semantic. utility-blue-light/cyan/teal 차단.",
    check_blueprint_fn=_check,
))
