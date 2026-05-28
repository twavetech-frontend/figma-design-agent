"""S21 — Reference search MUST be logged before build.

Project policy 2026-05-06 (user explicit): every design build MUST go
through a real reference search across the collected uibowl library
(references/uibowl/{toss,kakaopay,heydealer,payhere,socar}/) BEFORE
writing the blueprint. The agent must search keywords, inspect
candidates, then pick the closest match per section and copy its layout
faithfully — not just write a path string.

Concrete failure pattern (v24 / early v25): blueprint had a `references[]`
array with paths but the agent never actually opened those images;
visual quality dropped because the layout was guessed, not copied.

S20 already requires `references[]` to exist. S21 raises the bar: each
references[] entry must have a `_searchLog` companion proving the search
was performed, with at least:
  • queries: list of strings used to search
  • candidates: ≥3 candidate ref paths considered
  • chosen: the picked ref (must equal references[i].ref)
  • copyNotes: 1+ sentence on what visual elements were copied

Format on the blueprint root:

  references: [
    { section: "Recommend Card", ref: "uibowl/toss/abc.png",
      extract: "brand-purple full-bleed card with...",
      _searchLog: {
        queries: ["보라 카드 추천", "brand-purple savings card"],
        candidates: ["uibowl/toss/abc.png", "uibowl/toss/def.png",
                     "uibowl/kakaopay/ghi.png"],
        chosen: "uibowl/toss/abc.png",
        copyNotes: "Copied padding 24/20/20/20, cornerRadius 24, 36px
                    Bold amount, white sub-card with 3 stepper rows."
      } }
  ]

A blueprint may bypass S21 globally with `_referencesSkipped` (already
honored by S20) for trivial modals/test fixtures.
"""
from __future__ import annotations

from typing import Iterable, List

from .base import Phase, Rule, Severity, Violation, register


REQUIRED_LOG_FIELDS = ("queries", "candidates", "chosen", "copyNotes")
MIN_CANDIDATES = 3


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    if bp.get("_referencesSkipped"):
        return
    refs = bp.get("references")
    if not isinstance(refs, list) or not refs:
        # S20 already handles missing/empty references entirely
        return
    for i, ref in enumerate(refs):
        if not isinstance(ref, dict):
            continue
        section_name = ref.get("section", f"#{i}")
        log = ref.get("_searchLog")
        if not isinstance(log, dict):
            yield Violation(
                "S21-reference-search-log",
                Severity.ERROR,
                "root",
                (f"references[{i}] '{section_name}' missing _searchLog. "
                 f"Every reference MUST document the search: queries[], "
                 f"candidates (≥{MIN_CANDIDATES}), chosen, copyNotes. "
                 f"Run `figma_mcp_client.py reference search <terms>`, "
                 f"open the top images, then record the trail."),
                Phase.LINT,
            )
            continue
        # Validate required fields
        for f in REQUIRED_LOG_FIELDS:
            if not log.get(f):
                yield Violation(
                    "S21-reference-search-log",
                    Severity.ERROR,
                    "root",
                    (f"references[{i}] '{section_name}' _searchLog "
                     f"missing field '{f}'. Required: queries, "
                     f"candidates, chosen, copyNotes."),
                    Phase.LINT,
                )
        # Candidates must be ≥3 to prove a real search happened
        cands = log.get("candidates")
        if isinstance(cands, list) and len(cands) < MIN_CANDIDATES:
            yield Violation(
                "S21-reference-search-log",
                Severity.ERROR,
                "root",
                (f"references[{i}] '{section_name}' has only "
                 f"{len(cands)} candidate(s); ≥{MIN_CANDIDATES} required "
                 f"to demonstrate a real search across the library."),
                Phase.LINT,
            )
        # chosen must match ref
        chosen = log.get("chosen")
        if isinstance(chosen, str) and isinstance(ref.get("ref"), str):
            if chosen.strip() != ref["ref"].strip():
                yield Violation(
                    "S21-reference-search-log",
                    Severity.WARN,
                    "root",
                    (f"references[{i}] '{section_name}' chosen "
                     f"'{chosen}' does not equal ref '{ref['ref']}'. "
                     f"Update one to match."),
                    Phase.LINT,
                )
        # copyNotes too short = signals lazy fill-in
        notes = log.get("copyNotes")
        if isinstance(notes, str) and len(notes.strip()) < 30:
            yield Violation(
                "S21-reference-search-log",
                Severity.WARN,
                "root",
                (f"references[{i}] '{section_name}' copyNotes too short "
                 f"({len(notes)} chars) — describe what visual elements "
                 f"were copied (≥30 chars)."),
                Phase.LINT,
            )


register(Rule(
    rule_id="S21-reference-search-log",
    title="Each reference must include a search log proving the lookup happened",
    description=(
        "references[i]._searchLog with queries / candidates (≥3) / chosen "
        "/ copyNotes is required before build. Prevents path-only "
        "references that skip actual reference inspection."
    ),
    check_blueprint_fn=_check,
))
