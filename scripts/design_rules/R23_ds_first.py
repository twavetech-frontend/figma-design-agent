"""R23 — Use DS instances for known component patterns instead of raw frames.

If a node's name matches a known DS component pattern (Pill / Badge / Button
/ Logo / Status Bar / NavBar / Avatar / Tab Bar item / Action Button) AND the
node is type 'frame' (not 'instance' / 'INSTANCE'), warn — author should
swap to create_component_instance with the catalogued componentKey.

The componentKey catalog lives in scripts/design_rules/ds_catalog.py.
"""
from __future__ import annotations

import re
from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint
from .ds_catalog import DS_PATTERNS


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        ntype = node.get("type", "frame")
        if ntype not in ("frame", "FRAME"):
            continue
        # Already an instance? skip.
        if node.get("componentKey"):
            continue
        name = node.get("name", "") or ""
        for pat, cat in DS_PATTERNS:
            if pat.search(name):
                yield Violation(
                    "R23-ds-first", Severity.WARN, path,
                    f"frame '{name}' matches DS pattern '{cat}' — "
                    f"use create_component_instance instead of raw frame",
                    Phase.LINT,
                )
                break


register(Rule(
    rule_id="R23-ds-first",
    title="Prefer DS instances over raw frames",
    description="Pill / Badge / Button / Logo / Status Bar etc. must be DS instances.",
    check_blueprint_fn=_check,
))
