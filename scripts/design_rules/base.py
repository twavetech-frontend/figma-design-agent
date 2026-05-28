"""Design rule framework — base types + global registry.

Layered enforcement model:
  L1 schema      — blueprint shape/required fields/banned patterns
  L2 lint        — blueprint-time semantic checks (pre-build)
  L3 inject      — blueprint pre-processors (e.g. force Status Bar)
  L4 post-fix    — actual-tree mutators after build (auto-correct)
  L5 verify      — actual-tree assertions (post-build, after fixes)

A Rule may implement any subset of:
  check_blueprint(node, ctx)   -> Iterable[Violation]    (L2)
  inject_blueprint(blueprint)  -> blueprint              (L3, mutates root)
  auto_fix_built(tree, ctx)    -> int                    (L4, returns # fixes)
  check_built(tree, ctx)       -> Iterable[Violation]    (L5)

Rules self-register on import via @register decorator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional


class Severity(str, Enum):
    ERROR = "ERROR"   # blocks build (L2)
    WARN = "WARN"     # logs only (L2)
    INFO = "INFO"


class Phase(str, Enum):
    SCHEMA = "schema"        # L1
    LINT = "lint"            # L2
    INJECT = "inject"        # L3
    POST_FIX = "post_fix"    # L4
    VERIFY = "verify"        # L5


@dataclass
class Violation:
    rule_id: str
    severity: Severity
    path: str
    message: str
    phase: Phase = Phase.LINT
    auto_fixable: bool = False

    def format(self) -> str:
        fix = " [auto-fixable]" if self.auto_fixable else ""
        return f"{self.severity.value} [{self.rule_id}] {self.path}: {self.message}{fix}"


@dataclass
class Rule:
    """A design rule. Subclass or instantiate with callbacks.

    Each Rule has a stable rule_id (e.g. "R24-status-bar") used in
    violations + tests. title/description show up in lint reports.
    """
    rule_id: str
    title: str
    description: str = ""

    # Optional callbacks — assign via subclass override or kwargs in @register
    check_blueprint_fn: Optional[Callable[[dict, dict], Iterable[Violation]]] = None
    inject_blueprint_fn: Optional[Callable[[dict], dict]] = None
    auto_fix_built_fn: Optional[Callable[[dict, dict], int]] = None
    check_built_fn: Optional[Callable[[dict, dict], Iterable[Violation]]] = None

    # Phase membership flags (computed from which fns are set)
    def phases(self) -> List[Phase]:
        ps: List[Phase] = []
        if self.check_blueprint_fn: ps.append(Phase.LINT)
        if self.inject_blueprint_fn: ps.append(Phase.INJECT)
        if self.auto_fix_built_fn: ps.append(Phase.POST_FIX)
        if self.check_built_fn: ps.append(Phase.VERIFY)
        return ps


class Registry:
    """Global rule registry. Singleton, populated at module import time."""

    def __init__(self):
        self._rules: Dict[str, Rule] = {}

    def register(self, rule: Rule) -> Rule:
        if rule.rule_id in self._rules:
            raise ValueError(f"Duplicate rule_id: {rule.rule_id}")
        self._rules[rule.rule_id] = rule
        return rule

    def all(self) -> List[Rule]:
        return list(self._rules.values())

    def get(self, rule_id: str) -> Optional[Rule]:
        return self._rules.get(rule_id)

    # ── Phase runners ──────────────────────────────────────────────

    def run_lint(self, blueprint: dict) -> List[Violation]:
        """L2 — walk blueprint, run every rule's check_blueprint_fn."""
        ctx: Dict[str, Any] = {"blueprint": blueprint}
        violations: List[Violation] = []
        for r in self._rules.values():
            if not r.check_blueprint_fn:
                continue
            try:
                for v in r.check_blueprint_fn(blueprint, ctx):
                    violations.append(v)
            except Exception as e:
                violations.append(Violation(
                    rule_id=r.rule_id, severity=Severity.WARN, path="(rule-error)",
                    message=f"rule check failed: {e}", phase=Phase.LINT,
                ))
        return violations

    def run_inject(self, blueprint: dict) -> dict:
        """L3 — apply each rule's inject_blueprint_fn in registration order."""
        for r in self._rules.values():
            if not r.inject_blueprint_fn:
                continue
            try:
                blueprint = r.inject_blueprint_fn(blueprint) or blueprint
            except Exception as e:
                print(f"[inject] {r.rule_id} failed: {e}")
        return blueprint

    def run_auto_fix(self, tree: dict, ctx: Optional[dict] = None) -> Dict[str, int]:
        """L4 — apply post-fix mutators; returns {rule_id: count}."""
        ctx = ctx or {}
        counts: Dict[str, int] = {}
        for r in self._rules.values():
            if not r.auto_fix_built_fn:
                continue
            try:
                n = r.auto_fix_built_fn(tree, ctx) or 0
                if n:
                    counts[r.rule_id] = n
            except Exception as e:
                print(f"[post-fix] {r.rule_id} failed: {e}")
        return counts

    def run_verify(self, tree: dict, ctx: Optional[dict] = None) -> List[Violation]:
        """L5 — collect post-build violations against actual Figma state."""
        ctx = ctx or {}
        violations: List[Violation] = []
        for r in self._rules.values():
            if not r.check_built_fn:
                continue
            try:
                for v in r.check_built_fn(tree, ctx):
                    violations.append(v)
            except Exception as e:
                violations.append(Violation(
                    rule_id=r.rule_id, severity=Severity.WARN, path="(rule-error)",
                    message=f"verify failed: {e}", phase=Phase.VERIFY,
                ))
        return violations


# Module-level singleton
REGISTRY = Registry()


def register(rule: Rule) -> Rule:
    """Register a rule into the global REGISTRY."""
    return REGISTRY.register(rule)


# ── Helpers for rule authors ──────────────────────────────────────

def walk_blueprint(node: dict, path: str = "root"):
    """Yield (node, path) for every node in a blueprint tree."""
    yield node, path
    for i, child in enumerate(node.get("children") or []):
        cname = child.get("name", f"child[{i}]")
        yield from walk_blueprint(child, f"{path}/{cname}")


def walk_tree(node: dict, path: str = "root"):
    """Yield (node, path) for every node in a built actual-Figma tree."""
    yield node, path
    for i, child in enumerate(node.get("children") or []):
        cname = child.get("name", f"child[{i}]")
        yield from walk_tree(child, f"{path}/{cname}")
