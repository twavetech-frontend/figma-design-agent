# -*- coding: utf-8 -*-
"""DS 컴포넌트 가이드 조회 — component / search 명령의 로직 (Astryx CLI 패턴, 2026-07-08).

데이터 소스 3층을 합쳐 조회한다:
  1. ds/COMPONENT_GUIDANCE.json — 우리 소유 do/don't 가이드 (룰 요약, 커밋 대상)
  2. design_rules/ds_catalog.COMPONENT_KEYS — componentKey 해석 (catalogPrefixes 런타임 매칭
     — 키를 가이드 파일에 중복 저장하지 않아 드리프트 방지)
  3. ds/DS_COMPONENT_DOCS.json — 자동 sync 문서 (variants/props, --full 에서만)

출력은 dense(기본, 컴포넌트당 수백 자) — 에이전트 컨텍스트 토큰 절약. --full 로 상세.
"""
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
GUIDANCE_PATH = os.path.join(_ROOT, "ds", "COMPONENT_GUIDANCE.json")
DS_DOCS_PATH = os.path.join(_ROOT, "ds", "DS_COMPONENT_DOCS.json")


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-]+", "", (s or "").casefold())


def load_guidance(path: str = None) -> list:
    with open(path or GUIDANCE_PATH, encoding="utf-8") as fh:
        return json.load(fh).get("components") or []


def _catalog_keys() -> dict:
    """ds_catalog.COMPONENT_KEYS (이름 → 키). import 실패 시 빈 dict."""
    try:
        dr = os.path.join(_HERE, "design_rules")
        for p in (_HERE, dr):
            if p not in sys.path:
                sys.path.insert(0, p)
        import ds_catalog  # noqa: E402
        return dict(ds_catalog.COMPONENT_KEYS)
    except Exception:
        return {}


def resolve_catalog_keys(entry: dict, catalog: dict = None) -> dict:
    """entry.catalogPrefixes 로 COMPONENT_KEYS 에서 매칭되는 이름→키를 뽑는다."""
    catalog = catalog if catalog is not None else _catalog_keys()
    prefixes = entry.get("catalogPrefixes") or []
    out = {}
    for name, key in catalog.items():
        if any(name.startswith(p) for p in prefixes):
            out[name] = key
    return out


def find(name: str, entries: list = None):
    """이름/별칭/키워드로 컴포넌트 1건 찾기.

    Returns (entry|None, candidates: list[str]).
    정확 일치(이름/별칭) → 1건. 부분 일치가 1건이면 그것, 여럿이면 (None, 후보들).
    """
    entries = entries if entries is not None else load_guidance()
    q = _norm(name)
    if not q:
        return None, [e["name"] for e in entries]
    # 1) 이름/별칭 정확 일치
    for e in entries:
        names = [e.get("name", "")] + list(e.get("aliases") or [])
        if any(_norm(n) == q for n in names):
            return e, []
    # 2) 이름/별칭/키워드 부분 일치
    partial = []
    for e in entries:
        hay = [e.get("name", "")] + list(e.get("aliases") or []) + list(e.get("keywords") or [])
        if any(q in _norm(h) or _norm(h) in q for h in hay if h):
            partial.append(e)
    if len(partial) == 1:
        return partial[0], []
    return None, [e["name"] for e in partial]


def search(query: str, entries: list = None, catalog: dict = None, limit: int = 12) -> list:
    """가이드 + 카탈로그 통합 랭킹 검색.

    Returns [{kind: "guidance"|"catalog", name, score, snippet}] score 내림차순.
    """
    entries = entries if entries is not None else load_guidance()
    catalog = catalog if catalog is not None else _catalog_keys()
    q = _norm(query)
    results = []
    if not q:
        return results
    for e in entries:
        score = 0
        if q in _norm(e.get("name", "")) or _norm(e.get("name", "")) in q:
            score = 100
        elif any(q in _norm(a) or _norm(a) in q for a in (e.get("aliases") or [])):
            score = 80
        elif any(q in _norm(k) or _norm(k) in q for k in (e.get("keywords") or [])):
            score = 60
        elif any(q in _norm(g.get("description", "")) for g in (e.get("guidance") or [])):
            score = 30
        if score:
            first = (e.get("guidance") or [{}])[0].get("description", "")
            results.append({"kind": "guidance", "name": e["name"], "score": score,
                            "rule": e.get("rule"), "snippet": first[:110]})
    for name, key in catalog.items():
        if q in _norm(name):
            results.append({"kind": "catalog", "name": name, "score": 40, "snippet": key})
    results.sort(key=lambda r: (-r["score"], r["name"]))
    return results[:limit]


def _ds_doc_for(entry: dict) -> dict:
    """DS_COMPONENT_DOCS.json 에서 이름 매칭되는 자동 sync 문서 1건 (없으면 {})."""
    try:
        with open(DS_DOCS_PATH, encoding="utf-8") as fh:
            comps = json.load(fh).get("components") or []
    except Exception:
        return {}
    names = [entry.get("name", "")] + list(entry.get("aliases") or [])
    for c in comps:
        cand = [c.get("name", ""), c.get("figmaComponentName", "")]
        if any(_norm(a) and (_norm(a) in _norm(x) or _norm(x) in _norm(a))
               for a in names for x in cand if x):
            return c
    return {}


def format_entry(entry: dict, full: bool = False) -> str:
    """dense 텍스트 포맷 (기본). full=True 면 blueprintExample + DS 자동문서 variants/props."""
    lines = []
    rule = entry.get("rule")
    aliases = ", ".join(entry.get("aliases") or [])
    lines.append("■ %s%s%s" % (entry["name"],
                               " (CLAUDE.md 규칙 %s)" % rule if rule else "",
                               "  [별칭: %s]" % aliases if aliases else ""))
    for g in entry.get("guidance") or []:
        lines.append("  %s %s" % ("✓" if g.get("do") else "✗", g.get("description", "")))
    keys = resolve_catalog_keys(entry)
    if keys:
        lines.append("  componentKeys (ds_catalog):")
        for name, key in sorted(keys.items()):
            lines.append("    %s = %s" % (name, key))
    if full:
        ex = entry.get("blueprintExample")
        if ex:
            lines.append("  blueprint 예시:")
            for ln in json.dumps(ex, ensure_ascii=False, indent=2).splitlines():
                lines.append("    " + ln)
        doc = _ds_doc_for(entry)
        if doc:
            vs = ", ".join(v.get("name", "") for v in (doc.get("variants") or []))
            ps = ", ".join(p.get("name", "") for p in (doc.get("props") or []))
            if vs:
                lines.append("  DS 문서 variants: %s" % vs)
            if ps:
                lines.append("  DS 문서 props: %s" % ps)
    return "\n".join(lines)


def entry_as_json(entry: dict, full: bool = False) -> dict:
    doc = {
        "type": "component",
        "name": entry.get("name"),
        "rule": entry.get("rule"),
        "aliases": entry.get("aliases") or [],
        "guidance": entry.get("guidance") or [],
        "componentKeys": resolve_catalog_keys(entry),
    }
    if full:
        if entry.get("blueprintExample"):
            doc["blueprintExample"] = entry["blueprintExample"]
        ds_doc = _ds_doc_for(entry)
        if ds_doc:
            doc["dsDoc"] = {"variants": ds_doc.get("variants"), "props": ds_doc.get("props")}
    return doc
