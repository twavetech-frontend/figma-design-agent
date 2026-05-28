"""R11 — Typography (Korean → Pretendard)."""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


def _korean_pretendard(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        text = node.get("text") or node.get("characters")
        if not text: continue
        s = str(text)
        if not any('가' <= ch <= '힣' for ch in s):
            continue
        font = node.get("fontFamily") or (node.get("fontName") or {}).get("family", "")
        if font and font not in ("Pretendard", ""):
            yield Violation(
                "R11.1-korean-pretendard", Severity.WARN, path,
                f"Korean text with font '{font}' — should be Pretendard",
                Phase.LINT,
            )


register(Rule(
    rule_id="R11-typography",
    title="Typography",
    description="Korean text must use Pretendard.",
    check_blueprint_fn=_korean_pretendard,
))
