"""Reference catalog lookup — search saved uibowl screens by keyword.

Usage from CLI (figma_mcp_client.py):
    python3 scripts/figma_mcp_client.py reference search <keyword> [--app=토스] [--top=5]
    python3 scripts/figma_mcp_client.py reference list [--app=토스]
    python3 scripts/figma_mcp_client.py reference apps

Programmatic:
    from reference_lib import find_references
    refs = find_references("schedule home", app="토스", top=5)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Optional

REFS_ROOT = Path(__file__).parent.parent / "references" / "uibowl"


def list_apps() -> list[str]:
    """List apps with a scraped index.json."""
    if not REFS_ROOT.exists():
        return []
    return sorted([p.name for p in REFS_ROOT.iterdir()
                   if p.is_dir() and (p / "index.json").exists()])


def load_index(app: str) -> Optional[dict]:
    p = REFS_ROOT / app / "index.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def list_records(app: Optional[str] = None) -> list[dict]:
    """Flatten records across one or all apps."""
    apps = [app] if app else list_apps()
    out = []
    for a in apps:
        idx = load_index(a)
        if not idx:
            continue
        for r in idx.get("records", []):
            r = {**r, "_app": a}
            out.append(r)
    return out


def _score(rec: dict, terms: list[str]) -> float:
    """Simple keyword overlap score over patternCodeName + patternName + description."""
    haystack = " ".join([
        rec.get("patternCodeName", ""),
        rec.get("patternName", ""),
        rec.get("description", ""),
        rec.get("appName", ""),
    ]).lower()
    score = 0.0
    for t in terms:
        if not t:
            continue
        if t.lower() in haystack:
            score += 1.0
        # partial token match
        for tok in haystack.split():
            if tok.startswith(t.lower()) and tok != t.lower():
                score += 0.3
    return score


def find_references(keyword: str, app: Optional[str] = None, top: int = 5) -> list[dict]:
    """Find best-matching reference screens by keyword(s)."""
    terms = [t for t in keyword.split() if t]
    records = list_records(app)
    scored = [(r, _score(r, terms)) for r in records]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [r for r, s in scored[:top] if s > 0]


# ── CLI ─────────────────────────────────────────────────────────

def cli(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    rest = argv[1:]
    app = None
    top = 5
    pos = []
    for a in rest:
        if a.startswith("--app="):
            app = a.split("=", 1)[1]
        elif a.startswith("--top="):
            top = int(a.split("=", 1)[1])
        else:
            pos.append(a)
    if cmd == "apps":
        for a in list_apps():
            idx = load_index(a)
            print(f"  {a}: {idx.get('count')} screens "
                  f"({idx.get('categoryName')}, MAU={idx.get('MAU')})")
        return 0
    if cmd == "list":
        for r in list_records(app):
            print(f"  [{r['_app']}] {r['patternCodeName']:20s} {r['imgId'][:12]} "
                  f"{r.get('localPath','')}")
        return 0
    if cmd == "search":
        if not pos:
            print("Usage: reference search <keyword>")
            return 1
        kw = " ".join(pos)
        results = find_references(kw, app=app, top=top)
        print(f"Found {len(results)} match(es) for '{kw}':")
        for r in results:
            print(f"  [{r['_app']}] {r['patternCodeName']:20s} | {r.get('localPath')}")
            print(f"       {r.get('imageUrl','')}")
        return 0
    print(f"Unknown subcommand: {cmd}")
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(cli(sys.argv[1:]))
