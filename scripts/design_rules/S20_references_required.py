"""S20 — Blueprint root must declare references[] before build.

Process gate: every design build must be informed by visual references
from references/uibowl/. Authors must run `reference brief` first, then
attach the chosen references to the blueprint root:

    {
      "name": "imin_home_v8",
      "references": [
        {"section": "Stage Progress Card",
         "ref": "uibowl/toss/cm7k18gas0004l80cn7clbzsm.png",
         "extract": "card shadow + tag pill style"},
        ...
      ],
      "children": [...]
    }

If references[] is missing or empty, lint ERRORs and build is blocked.
For tiny single-section designs the rule may be bypassed by setting
"_referencesSkipped": "<reason>" at root.

Exception: if the discoverySource is null/missing the design isn't
authored from PRD/wireframe and won't be checked. (R0 wireframe-or-PRD
rule covers that.)
"""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    if not isinstance(bp, dict):
        return
    refs = bp.get("references")
    if isinstance(refs, list) and refs:
        # Validate shape: each entry needs ref + extract
        for i, r in enumerate(refs):
            if not isinstance(r, dict):
                yield Violation("S20.1-shape", Severity.ERROR, f"references[{i}]",
                                "must be an object {section, ref, extract}",
                                Phase.LINT)
                continue
            if not r.get("ref"):
                yield Violation("S20.2-ref-path", Severity.ERROR, f"references[{i}]",
                                "missing 'ref' (path under references/)",
                                Phase.LINT)
            if not r.get("extract"):
                yield Violation("S20.3-extract", Severity.WARN, f"references[{i}]",
                                "missing 'extract' description — explain WHAT visual element you borrowed",
                                Phase.LINT)
        return
    if bp.get("_referencesSkipped"):
        yield Violation("S20.0-skipped", Severity.WARN, "root",
                        f"references skipped: '{bp['_referencesSkipped']}'",
                        Phase.LINT)
        return
    yield Violation(
        "S20-references-required", Severity.ERROR, "root",
        "blueprint.references[] is required. Run "
        "`python3 scripts/figma_mcp_client.py reference brief <bp>` to get "
        "suggestions, pick which Toss/Kakaopay screens informed each section, "
        "and attach to root. Set _referencesSkipped: '<reason>' to bypass.",
        Phase.LINT,
    )


register(Rule(
    rule_id="S20-references-required",
    title="Reference attachment required pre-build",
    description=(
        "Blueprint root must declare references[] (at least one) describing "
        "which uibowl Toss/Kakaopay screens informed the visual design. "
        "Bypass with _referencesSkipped: <reason> for trivial designs."
    ),
    check_blueprint_fn=_check,
))
