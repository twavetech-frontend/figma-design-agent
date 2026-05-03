"""Design rule registry.

Importing this package auto-loads every R*.py rule module, which
self-registers into REGISTRY via @register at module level.

Usage:
    from scripts.design_rules import REGISTRY
    violations = REGISTRY.run_lint(blueprint)
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from .base import (
    REGISTRY,
    Phase,
    Registry,
    Rule,
    Severity,
    Violation,
    register,
    walk_blueprint,
    walk_tree,
)

# Auto-import every R*.py sibling so its @register calls fire
_pkg_dir = Path(__file__).parent
for mod in pkgutil.iter_modules([str(_pkg_dir)]):
    if mod.name.startswith("R") or mod.name == "schema":
        importlib.import_module(f"{__name__}.{mod.name}")

__all__ = [
    "REGISTRY",
    "Phase",
    "Registry",
    "Rule",
    "Severity",
    "Violation",
    "register",
    "walk_blueprint",
    "walk_tree",
]
