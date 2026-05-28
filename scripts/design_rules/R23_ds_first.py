"""R23 — Use DS instances for known component patterns instead of raw frames.

Three phases:
  L2 lint   — flag any node whose name matches DS_PATTERNS but isn't yet
              an instance AND can't be auto-resolved. ERROR (not WARN) —
              this used to silently slip through.
  L3 inject — for every name that resolves via ds_catalog.resolve_component_key,
              auto-add `componentKey` and switch type to "instance". Containers
              (NavBar / Tab Bar / Badge Row etc.) are left as raw frames.
  L5 verify — after build, every DS-implied name in the actual tree must be
              type=INSTANCE. If a frame slipped through, error.
"""
from __future__ import annotations

from typing import Iterable, List

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint, walk_tree
from .ds_catalog import (
    DS_PATTERNS, is_container, resolve_component_key,
    detect_button_shape, detect_badge_shape, detect_ds_role_structural,
)


# ── L3 inject — name → componentKey auto-swap ───────────────────

_NAME_TEXT_EXTRACT = __import__("re").compile(
    r"^(?:Gray|Brand|Active|Success|Warning|Pink|Purple|Blue\s*light)\s+Pill\s+(.+)$",
    __import__("re").I,
)


def _extract_instance_text(node: dict, role: str) -> str | None:
    """Pull a text override from name or explicit field.

    Priority:
      1. node['instanceText'] explicit
      2. name pattern "<color> Pill <CONTENT>" → CONTENT
      3. None (use master default)
    """
    if "instanceText" in node:
        return str(node["instanceText"])
    name = node.get("name") or ""
    m = _NAME_TEXT_EXTRACT.match(name.strip())
    if m:
        return m.group(1).strip()
    # 2026-05-28 — 자식 TEXT 의 characters 추출 (badge/button/link/tag 의 라벨).
    # 이전엔 None 반환 → instance 가 마스터 더미("Label"/"Button CTA"/"Click to
    # Download") 로 렌더되던 회귀. status-pill('진행중')/round-tag('1회차')/link('자세히').
    for c in (node.get("children") or node.get("_originalChildren") or []):
        if isinstance(c, dict) and (c.get("type") or "").lower() in ("text", "TEXT".lower()):
            t = c.get("characters") or c.get("text")
            if t and str(t).strip():
                return str(t).strip()
    return None


def _inject_node(node: dict) -> int:
    """Mutate `node` in place to add componentKey + type=instance if applicable.

    Returns 1 if changed, 0 otherwise.
    """
    if not isinstance(node, dict):
        return 0
    ntype = node.get("type", "frame")
    if ntype in ("instance", "INSTANCE"):
        return 0
    if ntype not in ("frame", "FRAME"):
        return 0
    if node.get("componentKey"):
        return 0
    name = node.get("name") or ""
    role = key = None
    text_override = None
    # 1) name-pattern resolution (legacy path — icons, pills, headers, …)
    resolved = resolve_component_key(name) if not is_container(name) else None
    if resolved:
        role, key = resolved
        text_override = _extract_instance_text(node, role)
    else:
        # 2) structural (shape) detection — buttons / badges / tags / inputs /
        #    dropdowns / toggles / checkboxes / radios / sliders / progress.
        #    Only `confident` matches (button/badge/tag, or name-hinted form
        #    controls) are auto-swapped; shape-only hits are surfaced as WARN
        #    by _lint instead (no swap — avoids false-positive instances).
        r = detect_ds_role_structural(node)
        if r and r[3]:
            role, key, text_override = r[0], r[1], r[2]
    if not key:
        return 0
    node["componentKey"] = key
    node["type"] = "instance"
    node["_dsResolvedRole"] = role
    if text_override is not None:
        node["_instanceText"] = text_override
    # DS "Buttons/Button" master ships with leading + trailing icon slots
    # visible by default ("○ Label ○"). A plain CTA wants text only — turn
    # them off via the boolean properties (names incl. the #nodeID suffix
    # are the stable property identifiers).
    if str(role).startswith("Action Button"):
        ip = dict(node.get("instanceProperties") or {})
        ip.setdefault("⬅️ Icon leading#3287:1577", False)
        ip.setdefault("➡️ Icon trailing#3287:2338", False)
        node["instanceProperties"] = ip
    # Strip raw children — instances render via main component
    if "children" in node:
        node["_originalChildren"] = node.pop("children")
    return 1


def _inject(bp: dict) -> dict:
    changed = 0
    for node, _path in walk_blueprint(bp):
        changed += _inject_node(node)
    if changed:
        print(f"[inject R23] auto-swapped {changed} raw frame(s) → DS instance")
    return bp


# ── L2 lint — only flag the truly unresolvable cases ────────────

def _lint(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        ntype = node.get("type", "frame")
        if ntype not in ("frame", "FRAME"):
            continue
        if node.get("componentKey"):
            continue
        name = node.get("name", "") or ""
        # Structural DS gate — a frame that *looks like* a DS component but is
        # a raw FRAME. Buttons = hard ERROR (verified key, inject auto-swaps,
        # so this only fires if something went wrong). Everything else = WARN
        # (surfaces the gap without breaking builds; keys not all battle-tested).
        struct = detect_ds_role_structural(node)
        if struct:
            role = struct[0]
            yield Violation(
                "R23-ds-raw-component", Severity.WARN, path,
                f"frame '{name}' is {role}-shaped but is a raw FRAME — should "
                f"be the DS '{role}' component instance "
                f"(auto-swap is on for toggle/checkbox/radio/input/slider/"
                f"progress/dropdown when keyed; buttons WARN-only pending a "
                f"reliable DS-button sizing pass).",
                Phase.LINT,
            )
            continue
        if is_container(name):
            continue
        for pat, cat in DS_PATTERNS:
            if pat.search(name):
                # If we can resolve a key — it would have been injected; skip.
                resolved = resolve_component_key(name)
                if resolved:
                    continue
                yield Violation(
                    "R23-ds-unresolvable", Severity.ERROR, path,
                    f"frame '{name}' matches DS pattern '{cat}' but no componentKey "
                    f"resolves — add to ds_catalog or rename. Build BLOCKED.",
                    Phase.LINT,
                )
                break


# ── L5 verify — assert built tree has no DS-implied raw frames ─

def _verify(tree: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_tree(tree):
        if node.get("type") not in ("FRAME",):
            continue
        name = node.get("name") or ""
        struct = detect_ds_role_structural(node)
        if struct:
            role = struct[0]
            yield Violation(
                "R23-ds-raw-component", Severity.WARN, path,
                f"built tree has {role}-shaped FRAME '{name}' — should be a DS "
                f"'{role}' instance.",
                Phase.VERIFY,
            )
            continue
        if is_container(name):
            continue
        for pat, cat in DS_PATTERNS:
            if pat.search(name):
                if resolve_component_key(name):
                    yield Violation(
                        "R23-ds-built-as-frame", Severity.ERROR, path,
                        f"built tree has FRAME '{name}' — should have been "
                        f"swapped to INSTANCE during inject (DS pattern: {cat})",
                        Phase.VERIFY,
                    )
                break


register(Rule(
    rule_id="R23-ds-first",
    title="Prefer DS instances over raw frames (auto-swap or BLOCK)",
    description=(
        "Names matching DS patterns are auto-swapped to INSTANCE via ds_catalog "
        "during inject. Unresolvable matches BLOCK the build (ERROR). "
        "Containers (NavBar/TabBar/HeaderRow) are exempt."
    ),
    check_blueprint_fn=_lint,
    inject_blueprint_fn=_inject,
    check_built_fn=_verify,
))
