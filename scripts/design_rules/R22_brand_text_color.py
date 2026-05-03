"""R22 — Text on brand-solid background must be white / explicit on-brand token.

When a TEXT node sits inside a frame with fill bg-brand-solid (or similar
saturated brand bg), its fontColor MUST be one of:
  $token(bg-primary)        — true white (used as text)
  $token(fg-on-brand)       — explicit on-brand token
  $token(text-primary_on-brand)
  RGBA dict where r=g=b≈1
Default black ({0,0,0}) is a violation — invisible on dark brand bg.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional

from .base import Phase, Rule, Severity, Violation, register


_TOKEN_RE = re.compile(r"^\$token\((.+)\)$")
# Only SOLID (saturated) brand bgs require white text — light tints
# like bg-brand-primary (#f4ecff) are pale and accept normal text colors.
_BRAND_BG_NAMES = ("bg-brand-solid", "bg-brand-section",
                   "bg-success-solid", "bg-error-solid", "bg-warning-solid")
_OK_ON_BRAND_TOKENS = (
    "bg-primary",                    # white surface used as text fg
    "fg-on-brand",
    "fg-white", "text-white",
    "text-primary_on-brand",
    "fg-primary_on-brand",
)


def _token_tail(s) -> Optional[str]:
    if not isinstance(s, str): return None
    m = _TOKEN_RE.match(s)
    if not m: return None
    return m.group(1).split("/")[-1]


def _is_brand_solid_bg(fill) -> bool:
    tail = _token_tail(fill)
    return bool(tail) and tail in _BRAND_BG_NAMES


def _is_white_or_on_brand(fc) -> bool:
    if isinstance(fc, dict):
        r = fc.get("r", 0); g = fc.get("g", 0); b = fc.get("b", 0)
        return r > 0.95 and g > 0.95 and b > 0.95
    tail = _token_tail(fc)
    return bool(tail) and tail in _OK_ON_BRAND_TOKENS


def _walk(node: dict, path: str, brand_ancestor: bool, out: List[Violation]):
    on_brand = brand_ancestor or _is_brand_solid_bg(node.get("fill"))
    if on_brand and node.get("type") in ("text", "TEXT"):
        fc = node.get("fontColor")
        if fc is None:
            out.append(Violation(
                "R22.1-brand-text-default", Severity.ERROR, path,
                "TEXT under brand-solid bg has no fontColor — defaults to black (invisible)",
                Phase.LINT,
            ))
        elif not _is_white_or_on_brand(fc):
            out.append(Violation(
                "R22.2-brand-text-color", Severity.ERROR, path,
                f"TEXT on brand-solid bg has non-white fontColor={fc!r} "
                f"— use $token(bg-primary) or $token(fg-on-brand)",
                Phase.LINT,
            ))
    for i, child in enumerate(node.get("children") or []):
        cn = child.get("name", f"child[{i}]")
        _walk(child, f"{path}/{cn}", on_brand, out)


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    out: List[Violation] = []
    _walk(bp, "root", False, out)
    return out


register(Rule(
    rule_id="R22-brand-text-color",
    title="Text color on brand backgrounds",
    description="Text on bg-brand-solid must be white or fg-on-brand — never default black.",
    check_blueprint_fn=_check,
))
