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


# ── Section keyword extraction ──────────────────────────────────

# Map common section name patterns → search keywords for reference lookup.
# This catalog feeds `reference brief` so Claude doesn't have to think which
# keyword to search for each section.
_SECTION_KEYWORDS = [
    # (regex on lowercased section name, keyword(s) to search)
    (r"\bnav\s*bar|header", "헤더 navigation"),
    (r"\btab\s*bar|bottom\s*nav", "탭 navigation"),
    (r"\bhero|banner|carousel", "메인 hero"),
    (r"\bstage|progress|회차|납입", "진행 progress 적립"),
    (r"\bschedule|calendar|일정", "스케줄 calendar"),
    (r"\battendance|출석", "출석 attendance"),
    (r"\bpoint|예치금|포인트", "포인트 결제"),
    (r"\bproduct|상품|라운지|lounge", "상품 추천"),
    (r"\brecommend|추천", "추천"),
    (r"\bwallet|월렛", "지갑 wallet"),
    (r"\bpayment|결제|송금", "결제 송금"),
    (r"\baccount|계좌", "계좌 자산"),
    (r"\bsettings|마이|profile", "마이 settings"),
    (r"\bnotification|알림", "알림 notification"),
    (r"\bsearch|검색", "검색 search"),
    (r"\bhistory|내역", "내역 history"),
]


def keywords_for_section(name: str) -> list[str]:
    """Return search keywords inferred from a section name."""
    nl = (name or "").lower()
    out = []
    for pat, kw in _SECTION_KEYWORDS:
        if __import__("re").search(pat, nl):
            out.append(kw)
    if not out and nl:
        # fallback: tokenize the name
        out.append(" ".join(nl.split()[:3]))
    return out


def brief_blueprint(bp: dict, top: int = 3) -> list[dict]:
    """Walk a blueprint root, suggest references per top-level section.

    Strategy:
      1. Map section name → search keywords via _SECTION_KEYWORDS catalog
      2. Search keyword(s) — keep matches above threshold
      3. If no match, fall back to a deterministic sample of records (so
         every section gets at least a visual anchor to look at; author
         picks/discards manually)

    Returns: [{section, keywords, candidates:[{ref, app, patternCodeName, _kwUsed}]}]
    """
    all_records = list_records()
    suggestions = []
    children = bp.get("children") or []
    for idx, child in enumerate(children):
        name = child.get("name") or "?"
        if (name or "").lower() in {"status bar", "navbar", "tab bar"}:
            continue
        kws = keywords_for_section(name)
        seen_ids = set()
        candidates = []
        for kw in kws:
            for r in find_references(kw, top=top):
                if r["imgId"] in seen_ids:
                    continue
                seen_ids.add(r["imgId"])
                candidates.append({
                    "ref": r.get("localPath"),
                    "imgUrl": r.get("imageUrl"),
                    "app": r.get("appName"),
                    "patternCodeName": r.get("patternCodeName"),
                    "_kwUsed": kw,
                })
        # Fallback — sample 2 from each app deterministically by section index
        if not candidates and all_records:
            apps_seen = set()
            stride = max(1, len(all_records) // max(top, 1))
            for i, r in enumerate(all_records[(idx * 3) % max(1, len(all_records))::stride]):
                key = (r.get('_app'), r['imgId'])
                if r['imgId'] in seen_ids: continue
                seen_ids.add(r['imgId'])
                candidates.append({
                    "ref": r.get("localPath"),
                    "imgUrl": r.get("imageUrl"),
                    "app": r.get("appName"),
                    "patternCodeName": r.get("patternCodeName"),
                    "_kwUsed": "(fallback sample)",
                })
                if len(candidates) >= top:
                    break
        suggestions.append({
            "section": name,
            "keywords": kws,
            "candidates": candidates[:top],
        })
    return suggestions


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
    if cmd == "brief":
        if not pos:
            print("Usage: reference brief <blueprint.json>")
            return 1
        bp_path = pos[0]
        with open(bp_path) as f:
            bp = json.load(f)
        sugg = brief_blueprint(bp, top=top)
        print(f"📋 Reference brief for '{bp.get('name')}' — {len(sugg)} sections")
        print()
        for s in sugg:
            print(f"## {s['section']}")
            print(f"   keywords: {s['keywords']}")
            if not s["candidates"]:
                print(f"   ⚠️  no reference match — search manually or skip")
            for c in s["candidates"]:
                print(f"   • [{c['app']}] {c['patternCodeName']} — {c['ref']}")
            print()
        # Also emit a JSON form authors can copy into blueprint.references
        ready = [{"section": s["section"], "ref": c["ref"], "app": c["app"],
                  "extract": "(fill in: visual element to borrow)"}
                 for s in sugg for c in s["candidates"][:1]]
        print("---")
        print("Suggested blueprint.references (copy/edit/paste into blueprint root):")
        print(json.dumps(ready, indent=2, ensure_ascii=False))
        return 0
    print(f"Unknown subcommand: {cmd}")
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(cli(sys.argv[1:]))
