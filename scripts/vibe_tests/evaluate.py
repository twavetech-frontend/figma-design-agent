# -*- coding: utf-8 -*-
"""Blueprint vibe-tests — 오프라인 결정적 채점기 (Phase 4a, 2026-07-08).

설계: docs/vibe-tests-design.md. Astryx universal-eval 패턴 — 같은 채점 로직을 모든
케이스/구성에 적용, LLM 채점 없음, 브리지/Figma 불필요.

5차원 (각 0~100):
  D1 구조 유효성  — validate_blueprint ERROR 건당 -20
  D2 룰 준수     — design_rules lint ERROR 건당 -15 / WARN 건당 -3
  D3 콘텐츠 충실도 — wireframeContent string value 의 blueprint TEXT 커버리지 % (0-E)
  D4 창의 발산    — 게이트 선언 품질(_concept/_designDirection/_wireframeDivergence 각 1/3)
                   + 같은 케이스 N샘플 간 novelty 시그니처 유사도 보정(±10)
  D5 DS 정합     — expected.dsComponents 커버리지(70) + forbiddenPatterns 무검출(30)

사용:
  python3 scripts/vibe_tests/evaluate.py --iteration <iter> [--testset <path>]
  → results/<iter>/scores.json + report.md
"""
import argparse
import copy
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)
for _p in (_SCRIPTS, os.path.join(_SCRIPTS, "design_rules")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_TESTSET = os.path.join(_HERE, "test-sets", "default.json")
RESULTS_DIR = os.path.join(_HERE, "results")


def _clamp(v: float) -> int:
    return int(round(max(0.0, min(100.0, v))))


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", "", str(s or ""))


# ── blueprint 워커 ───────────────────────────────────────────────────────────

def _walk(node):
    if isinstance(node, dict):
        yield node
        for c in node.get("children") or []:
            yield from _walk(c)


def _all_texts(bp: dict) -> str:
    parts = []
    for n in _walk(bp):
        for f in ("text", "characters"):
            v = n.get(f)
            if isinstance(v, str) and v:
                parts.append(v)
    return _norm_text("".join(parts))


def _content_values(obj) -> list:
    """wireframeContent dict 의 모든 string 값 (중첩 dict/list 포함, 키 제외)."""
    out = []
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(_content_values(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_content_values(v))
    elif isinstance(obj, str) and obj.strip():
        out.append(obj)
    return out


# ── D1 구조 유효성 ───────────────────────────────────────────────────────────

def score_validity(bp: dict) -> dict:
    import figma_mcp_client as fmc
    b = fmc._flatten_padding_objects(copy.deepcopy(bp))
    issues = fmc.validate_blueprint(b)
    errors = [i for i in issues if i.startswith("ERROR")]
    return {"score": _clamp(100 - 20 * len(errors)),
            "errors": errors[:20], "errorCount": len(errors)}


# ── D2 룰 준수 ──────────────────────────────────────────────────────────────

def score_rules(bp: dict) -> dict:
    from design_rules import REGISTRY, Severity
    violations = REGISTRY.run_lint(copy.deepcopy(bp))
    errs = [v for v in violations if v.severity == Severity.ERROR]
    warns = [v for v in violations if v.severity == Severity.WARN]
    return {"score": _clamp(100 - 15 * len(errs) - 3 * len(warns)),
            "errorRules": [v.rule_id for v in errs],
            "warnRules": [v.rule_id for v in warns]}


# ── D3 콘텐츠 충실도 (0-E) ───────────────────────────────────────────────────

def score_content(bp: dict, case: dict) -> dict:
    wc = case.get("wireframeContent") or {}
    values = [v for v in _content_values(wc) if not str(v).startswith("_")]
    if not values:
        return {"score": 100, "covered": 0, "total": 0, "missing": []}
    hay = _all_texts(bp)
    missing = [v for v in values if _norm_text(v) not in hay]
    covered = len(values) - len(missing)
    return {"score": _clamp(100.0 * covered / len(values)),
            "covered": covered, "total": len(values), "missing": missing[:15]}


# ── D4 창의 발산 ────────────────────────────────────────────────────────────

def score_declarations(bp: dict) -> dict:
    """게이트 선언 3종 품질 — 각 1/3. 형식 + 최소 구체성(길이/중복) 검사."""
    detail = {}
    # _concept: idea ≥5자 + diffs ≥3개(각 ≥5자)
    c = bp.get("_concept")
    ok_c = (isinstance(c, dict) and len(str(c.get("idea") or "")) >= 5
            and isinstance(c.get("diffs"), list)
            and len([d for d in c["diffs"] if len(str(d)) >= 5]) >= 3)
    detail["concept"] = bool(ok_c)
    # _designDirection: id + 4축 중 ≥3축 구체(≥4자)
    d = bp.get("_designDirection")
    axes = [a for a in ("typography", "color", "layout", "spacing")
            if isinstance(d, dict) and len(str(d.get(a) or "")) >= 4]
    ok_d = isinstance(d, dict) and bool(str(d.get("id") or "")) and len(axes) >= 3
    detail["designDirection"] = bool(ok_d)
    # _wireframeDivergence: ≥3개, 각 ≥10자, 전부 동일 금지
    w = bp.get("_wireframeDivergence")
    items = [str(x) for x in w if len(str(x)) >= 10] if isinstance(w, list) else []
    ok_w = len(items) >= 3 and len(set(items)) >= 3
    detail["wireframeDivergence"] = bool(ok_w)
    n_ok = sum(1 for v in detail.values() if v)
    return {"score": _clamp(100.0 * n_ok / 3), "detail": detail}


def sample_similarity(bps: list):
    """같은 케이스 N샘플 간 novelty 시그니처 최대 쌍 유사도 (0~1). 1샘플이면 None."""
    if len(bps) < 2:
        return None
    import figma_mcp_client as fmc
    sigs = [fmc._visual_signature(b) for b in bps]
    best = 0.0
    for i in range(len(sigs)):
        for j in range(i + 1, len(sigs)):
            best = max(best, fmc._signature_similarity(sigs[i], sigs[j]))
    return round(best, 3)


def similarity_adjust(sim) -> int:
    """설계 6장: 유사도 ≥0.8 → -10 ('다 똑같다'), <0.6 → +10 (발산), 그 외 0."""
    if sim is None:
        return 0
    if sim >= 0.8:
        return -10
    if sim < 0.6:
        return +10
    return 0


# ── D5 DS 정합 ──────────────────────────────────────────────────────────────

def _catalog() -> dict:
    try:
        import ds_catalog
        return dict(ds_catalog.COMPONENT_KEYS)
    except Exception:
        return {}


def _used_instance_keys(bp: dict) -> set:
    return {n.get("componentKey") for n in _walk(bp)
            if (n.get("type") or "").lower() == "instance" and n.get("componentKey")}


def _expected_covered(prefix: str, used_keys: set, catalog: dict) -> bool:
    """expected 컴포넌트(카탈로그 이름 prefix)가 blueprint 인스턴스로 사용됐는가."""
    valid = {k for name, k in catalog.items() if name.startswith(prefix)}
    if any(k in valid for k in used_keys):
        return True
    # Tool Bar 는 SET:<setKey>:<variant> 형식 (0-W)
    if prefix.startswith("Tool Bar"):
        return any(str(k).startswith("SET:") for k in used_keys)
    return False


_FORBIDDEN_MATCHERS = {}


def _matcher(name):
    def deco(fn):
        _FORBIDDEN_MATCHERS[name] = fn
        return fn
    return deco


@_matcher("status-bar-node")
def _m_status_bar(bp):
    """Status Bar 를 blueprint 에 직접 넣음 (규칙 1 — 빌드가 자동 삽입)."""
    return [n.get("name") for n in (bp.get("children") or [])
            if isinstance(n, dict) and "statusbar" in _norm_text(n.get("name", "")).lower()]


@_matcher("raw-tab-bar-frame")
def _m_raw_tab_bar(bp):
    """하단 탭바를 인스턴스가 아니라 raw frame 으로 그림 (0-M)."""
    hits = []
    for n in _walk(bp):
        nm = _norm_text(n.get("name", "")).lower()
        if (("tabbar" in nm or "bottomnav" in nm)
                and (n.get("type") or "").lower() == "frame" and n.get("children")):
            hits.append(n.get("name"))
    return hits


@_matcher("segmented-view-tabs")
def _m_seg_view_tabs(bp):
    """뷰 전환 탭을 _forceSegmented 없이 Segmented_control 로 작성 (0-J)."""
    return [n.get("name") for n in _walk(bp)
            if n.get("_segLabels") and not n.get("_forceSegmented")]


@_matcher("raw-navbar-frame")
def _m_raw_navbar(bp):
    """상단 NavBar 를 인스턴스가 아니라 raw frame 으로 그림 (0-W). _customNavBar 는 허용."""
    hits = []
    for n in _walk(bp):
        nm = _norm_text(n.get("name", "")).lower()
        if (("navbar" in nm or "toolbar" in nm)
                and (n.get("type") or "").lower() == "frame"
                and not n.get("_customNavBar") and n.get("children")):
            hits.append(n.get("name"))
    return hits


def score_ds(bp: dict, case: dict, catalog: dict = None) -> dict:
    catalog = catalog if catalog is not None else _catalog()
    exp = (case.get("expected") or {})
    expected = exp.get("dsComponents") or []
    forbidden = exp.get("forbiddenPatterns") or []
    used = _used_instance_keys(bp)

    cov_part, missing = 70.0, []
    if expected:
        covered = [p for p in expected if _expected_covered(p, used, catalog)]
        missing = [p for p in expected if p not in covered]
        cov_part = 70.0 * len(covered) / len(expected)

    forb_part, hits = 30.0, {}
    for pat in forbidden:
        fn = _FORBIDDEN_MATCHERS.get(pat)
        found = fn(bp) if fn else []
        if found:
            hits[pat] = found[:5]
            forb_part -= 15.0
    return {"score": _clamp(cov_part + max(0.0, forb_part)),
            "missingComponents": missing, "forbiddenHits": hits}


# ── 케이스/이터레이션 평가 ─────────────────────────────────────────────────────

DIMS = ("d1_validity", "d2_rules", "d3_content", "d4_divergence", "d5_ds")


def evaluate_case(case: dict, blueprints: list) -> dict:
    """케이스 1개 = 같은 태스크의 N개 blueprint 샘플."""
    samples = []
    for bp in blueprints:
        samples.append({
            "d1_validity": score_validity(bp),
            "d2_rules": score_rules(bp),
            "d3_content": score_content(bp, case),
            "d4_divergence": score_declarations(bp),
            "d5_ds": score_ds(bp, case),
        })
    sim = sample_similarity(blueprints)
    adj = similarity_adjust(sim)
    dims = {}
    for d in DIMS:
        vals = [s[d]["score"] for s in samples]
        dims[d] = _clamp(sum(vals) / len(vals)) if vals else 0
    dims["d4_divergence"] = _clamp(dims["d4_divergence"] + adj)
    total = _clamp(sum(dims.values()) / len(DIMS))
    return {"id": case.get("id"), "sampleCount": len(blueprints),
            "similarity": sim, "similarityAdjust": adj,
            "dims": dims, "total": total, "samples": samples}


def evaluate_iteration(iter_dir: str, testset_path: str = None) -> dict:
    with open(testset_path or DEFAULT_TESTSET, encoding="utf-8") as fh:
        testset = json.load(fh)
    bp_dir = os.path.join(iter_dir, "blueprints")
    cases_out, missing_cases = [], []
    for case in testset.get("cases") or []:
        cid = case["id"]
        bps = []
        if os.path.isdir(bp_dir):
            for fn in sorted(os.listdir(bp_dir)):
                if fn.startswith(cid + "-") and fn.endswith(".json"):
                    try:
                        with open(os.path.join(bp_dir, fn), encoding="utf-8") as fh:
                            bps.append(json.load(fh))
                    except Exception as e:
                        print("  ⚠️ %s 파싱 실패: %s" % (fn, e))
        if not bps:
            missing_cases.append(cid)
            continue
        cases_out.append(evaluate_case(case, bps))

    # 전 케이스 공통 위반 Top-N (설계 7장 — Phase 5 '최다 에러 유발 룰' 근거)
    rule_counts = {}
    for c in cases_out:
        for s in c["samples"]:
            for rid in s["d2_rules"]["errorRules"] + s["d2_rules"]["warnRules"]:
                rule_counts[rid] = rule_counts.get(rid, 0) + 1
    top = sorted(rule_counts.items(), key=lambda kv: -kv[1])[:8]

    dims_avg = {d: (_clamp(sum(c["dims"][d] for c in cases_out) / len(cases_out))
                    if cases_out else 0) for d in DIMS}
    return {"type": "vibe-report", "iteration": os.path.basename(iter_dir),
            "config": testset.get("config", "full"),
            "caseCount": len(cases_out), "missingCases": missing_cases,
            "dimsAvg": dims_avg,
            "total": _clamp(sum(c["total"] for c in cases_out) / len(cases_out)) if cases_out else 0,
            "topViolations": [{"rule": r, "count": n} for r, n in top],
            "cases": cases_out}


def render_markdown(report: dict) -> str:
    lines = ["# vibe-tests report — %s (config: %s)" % (report["iteration"], report["config"]),
             "", "| case | D1 | D2 | D3 | D4 | D5 | sim | total |",
             "|------|----|----|----|----|----|-----|-------|"]
    for c in report["cases"]:
        d = c["dims"]
        lines.append("| %s | %d | %d | %d | %d | %d | %s | **%d** |" % (
            c["id"], d["d1_validity"], d["d2_rules"], d["d3_content"],
            d["d4_divergence"], d["d5_ds"],
            ("%.2f" % c["similarity"]) if c["similarity"] is not None else "-", c["total"]))
    d = report["dimsAvg"]
    lines.append("| **평균** | %d | %d | %d | %d | %d |  | **%d** |" % (
        d["d1_validity"], d["d2_rules"], d["d3_content"], d["d4_divergence"],
        d["d5_ds"], report["total"]))
    if report["topViolations"]:
        lines += ["", "## 공통 위반 Top-N (룰 문서/enforcer 개선 후보)"]
        for tv in report["topViolations"]:
            lines.append("- %s × %d" % (tv["rule"], tv["count"]))
    if report["missingCases"]:
        lines += ["", "⚠️ blueprint 미제출 케이스: %s" % ", ".join(report["missingCases"])]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="blueprint vibe-tests 오프라인 채점")
    ap.add_argument("--iteration", required=True, help="results/<iter> 이름")
    ap.add_argument("--testset", default=DEFAULT_TESTSET)
    args = ap.parse_args()
    iter_dir = (args.iteration if os.path.isabs(args.iteration)
                else os.path.join(RESULTS_DIR, args.iteration))
    if not os.path.isdir(iter_dir):
        print("results 디렉토리 없음: %s" % iter_dir)
        sys.exit(1)
    report = evaluate_iteration(iter_dir, args.testset)
    with open(os.path.join(iter_dir, "scores.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    md = render_markdown(report)
    with open(os.path.join(iter_dir, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    print(md)
    print("→ %s/scores.json + report.md" % iter_dir)


if __name__ == "__main__":
    main()
