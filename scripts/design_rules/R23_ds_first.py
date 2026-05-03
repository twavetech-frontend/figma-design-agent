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
from .ds_catalog import DS_PATTERNS, is_container, resolve_component_key


# ── L3 inject — name → componentKey auto-swap ───────────────────

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
    if is_container(name):
        return 0
    resolved = resolve_component_key(name)
    if not resolved:
        return 0
    role, key = resolved
    node["componentKey"] = key
    node["type"] = "instance"
    node["_dsResolvedRole"] = role  # informational
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
