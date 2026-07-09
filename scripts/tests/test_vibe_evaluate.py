# -*- coding: utf-8 -*-
"""vibe-tests 채점기 — 5차원 스코어러 검증 (Phase 4a, 2026-07-08).

good/bad fixture blueprint 로 채점기 자체를 검증한다 (에이전트 불필요, 오프라인).
계약: 각 차원 0~100 정수, good > bad 가 모든 차원에서 성립.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vibe_tests"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import evaluate as ev  # noqa: E402

CASE = {
    "id": "fixture-case",
    "wireframeContent": {
        "header": "진행중인 0건의 스테이지 내역",
        "rows": {"collected": "모은 금액", "value": "+ 0원"},
        "cta": "시작하기",
    },
    "expected": {
        "dsComponents": ["Tab Bar", "Tool Bar"],
        "forbiddenPatterns": ["status-bar-node", "raw-tab-bar-frame",
                              "segmented-view-tabs", "raw-navbar-frame"],
    },
}

GOOD_BP = {
    "name": "imin_signup_home_vibe", "type": "frame",
    "fill": "$token(bg-primary)",
    "layoutSizingHorizontal": "FIXED", "width": 393,
    "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 0},
    "_wireframeContent": CASE["wireframeContent"],
    "_concept": {"idea": "빈 상태를 시작 유도 히어로로 반전",
                 "diffs": ["히어로를 카드 밖 풀블리드로", "데이 스트립을 캡슐형으로", "CTA 를 히어로 안으로"]},
    "_designDirection": {"id": "airy-hero-v1", "typography": "oversized-hero-32",
                         "color": "mono-brand+1pop", "layout": "hero-first-asymmetric",
                         "spacing": "airy-loose-24"},
    "_wireframeDivergence": ["와이어는 3행 리스트였는데 빌드는 히어로+2col 로 재배치",
                             "와이어 균일 14px 텍스트를 32/16/14 위계로 재구성",
                             "와이어 무채색을 brand 액센트 1점 배치로 변경"],
    "references": [{"path": "uibowl", "extract": "hero rhythm"}],
    "children": [
        {"name": "NavBar", "type": "instance",
         "componentKey": "SET:c9299ef0c3c7cc271850a048025a3c8d0e82b230:Type=Home",
         "layoutSizingHorizontal": "FILL"},
        {"name": "Content", "type": "frame", "layoutSizingHorizontal": "FILL",
         "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 20,
                        "paddingLeft": 20, "paddingRight": 20,
                        "paddingTop": 20, "paddingBottom": 20},
         "children": [
             {"type": "text", "text": "진행중인 0건의 스테이지 내역", "fontSize": 16,
              "fontColor": "$token(text-primary)"},
             {"type": "text", "text": "모은 금액 + 0원", "fontSize": 14,
              "fontColor": "$token(text-secondary)"},
             {"type": "text", "text": "시작하기", "fontSize": 16,
              "fontColor": "$token(text-brand-primary)"},
         ]},
        {"name": "Tab Bar", "type": "instance",
         "componentKey": "0faaa55563de4da617964ea93ba07f09bc1279f6",
         "layoutSizingHorizontal": "FILL"},
    ],
}

BAD_BP = {
    "name": "imin_signup_home_vibe", "type": "frame",
    "fill": "$token(bg-secondary)",
    "children": [
        {"name": "Status Bar", "type": "frame", "children": [
            {"type": "text", "text": "9:41"}]},
        {"name": "NavBar", "type": "frame", "children": [
            {"type": "text", "text": "imin"}]},
        {"name": "View Tabs", "type": "instance", "componentKey": "47a01673a46dc3bc9bfd62948c10e5fa9f2e5e78",
         "_segLabels": ["거래 현황", "누적 거래"]},
        {"name": "Card", "type": "frame", "layoutSizingHorizontal": "HUG", "children": [
            {"type": "text", "text": "전혀 다른 더미 텍스트"}]},
        {"name": "Tab Bar", "type": "frame", "children": [
            {"type": "text", "text": "홈"}, {"type": "text", "text": "커뮤니티"}]},
    ],
}


def test_scores_are_bounded_ints():
    for bp in (GOOD_BP, BAD_BP):
        for fn in (ev.score_validity, ev.score_rules, ev.score_declarations):
            s = fn(bp)["score"]
            assert isinstance(s, int) and 0 <= s <= 100
        assert 0 <= ev.score_content(bp, CASE)["score"] <= 100
        assert 0 <= ev.score_ds(bp, CASE)["score"] <= 100


def test_content_coverage():
    good = ev.score_content(GOOD_BP, CASE)
    bad = ev.score_content(BAD_BP, CASE)
    assert good["score"] == 100 and good["missing"] == []
    assert bad["score"] < 40 and "시작하기" in bad["missing"]


def test_content_whitespace_normalized():
    """빌드 텍스트에 줄바꿈이 있어도 커버로 인정 (0-E 의 whitespace 정규화와 동일)."""
    bp = {"type": "frame", "children": [
        {"type": "text", "text": "진행중인 0건의\n스테이지 내역 모은 금액 + 0원 시작하기"}]}
    assert ev.score_content(bp, CASE)["score"] == 100


def test_content_covers_instance_markers():
    """4c 보정 — _navTitle/_instanceText/_segLabels 안의 값도 커버로 인정
    (DS 인스턴스 마커가 콘텐츠를 담는다: Tool Bar 타이틀, Action Button 라벨)."""
    case = {"wireframeContent": {"nav": {"title": "내 스케줄"},
                                 "cta": "참여 확정하기", "tabs": {"a": "입금", "b": "지급"}}}
    bp = {"type": "frame", "children": [
        {"name": "NavBar", "type": "instance", "componentKey": "SET:x:Type=Detail view",
         "_navTitle": "내 스케줄"},
        {"name": "Toggle", "type": "instance", "componentKey": "k",
         "_segLabels": ["입금", "지급"], "_forceSegmented": True},
        {"name": "CTA", "type": "instance", "componentKey": "k2",
         "_instanceText": "참여 확정하기"},
    ]}
    assert ev.score_content(bp, case)["score"] == 100


def test_content_skips_icon_logo_keys():
    """4c 알려진 비대칭 — 아이콘/로고 식별자 키는 텍스트 커버리지 대상에서 제외
    (DS 컴포넌트에 시각 요소로 내장 — blueprint 텍스트로 잴 수 없음)."""
    case = {"wireframeContent": {"navbar": {"logo": "imin", "icons": ["bell", "chat"]},
                                 "title": "라운지"}}
    bp = {"type": "frame", "children": [{"type": "text", "text": "라운지"}]}
    s = ev.score_content(bp, case)
    assert s["score"] == 100 and s["total"] == 1


def test_rules_excludes_pipeline_process_rules():
    """4c 알려진 비대칭 — S20/S21(레퍼런스 경로/검색 로그)은 build Step A.0 이 주입하는
    프로세스 룰이라 vibe-tests D2 에서 제외."""
    s = ev.score_rules(GOOD_BP)
    for rid in s["errorRules"] + s["warnRules"]:
        assert not rid.startswith(("S20", "S21")), rid


def test_declarations_good_vs_bad():
    assert ev.score_declarations(GOOD_BP)["score"] == 100
    bad = ev.score_declarations(BAD_BP)
    assert bad["score"] == 0
    assert bad["detail"] == {"concept": False, "designDirection": False,
                             "wireframeDivergence": False}


def test_declarations_partial():
    bp = dict(GOOD_BP)
    bp = json.loads(json.dumps(bp))
    del bp["_wireframeDivergence"]
    bp["_concept"]["diffs"] = ["하나뿐"]  # diffs < 3 → concept 불충분
    s = ev.score_declarations(bp)
    assert s["detail"]["designDirection"] is True
    assert s["detail"]["concept"] is False
    assert s["score"] == 33


def test_ds_good_covers_expected_no_forbidden():
    s = ev.score_ds(GOOD_BP, CASE)
    assert s["score"] == 100
    assert s["missingComponents"] == [] and s["forbiddenHits"] == {}


def test_ds_bad_detects_forbidden_patterns():
    s = ev.score_ds(BAD_BP, CASE)
    hits = s["forbiddenHits"]
    assert "status-bar-node" in hits
    assert "raw-tab-bar-frame" in hits
    assert "segmented-view-tabs" in hits
    assert "raw-navbar-frame" in hits
    assert "Tab Bar" in s["missingComponents"]
    assert s["score"] < 40


def test_rules_good_better_than_bad():
    g, b = ev.score_rules(GOOD_BP), ev.score_rules(BAD_BP)
    assert g["score"] >= b["score"]


def test_similarity_and_adjust():
    sim_same = ev.sample_similarity([GOOD_BP, json.loads(json.dumps(GOOD_BP))])
    assert sim_same is not None and sim_same >= 0.99
    assert ev.similarity_adjust(sim_same) == -10
    sim_diff = ev.sample_similarity([GOOD_BP, BAD_BP])
    assert sim_diff < sim_same
    assert ev.sample_similarity([GOOD_BP]) is None
    assert ev.similarity_adjust(None) == 0
    assert ev.similarity_adjust(0.3) == 10


def test_evaluate_case_shape_and_ordering():
    rep = ev.evaluate_case(CASE, [GOOD_BP, BAD_BP])
    assert set(rep["dims"]) == set(ev.DIMS)
    assert rep["sampleCount"] == 2
    assert 0 <= rep["total"] <= 100
    good_only = ev.evaluate_case(CASE, [GOOD_BP])
    bad_only = ev.evaluate_case(CASE, [BAD_BP])
    assert good_only["total"] > bad_only["total"]


def test_evaluate_iteration_end_to_end(tmp_path):
    iter_dir = tmp_path / "it1"
    (iter_dir / "blueprints").mkdir(parents=True)
    ts = {"config": "full", "cases": [CASE]}
    ts_path = tmp_path / "ts.json"
    ts_path.write_text(json.dumps(ts, ensure_ascii=False), encoding="utf-8")
    for i, bp in enumerate((GOOD_BP, BAD_BP), 1):
        (iter_dir / "blueprints" / ("fixture-case-%d.json" % i)).write_text(
            json.dumps(bp, ensure_ascii=False), encoding="utf-8")
    rep = ev.evaluate_iteration(str(iter_dir), str(ts_path))
    assert rep["type"] == "vibe-report" and rep["caseCount"] == 1
    md = ev.render_markdown(rep)
    assert "fixture-case" in md and "| **평균** |" in md


def test_default_testset_sanity():
    """커밋된 배터리 파일 자체의 불변식 — expected 존재 + 케이스 id 유일."""
    with open(ev.DEFAULT_TESTSET, encoding="utf-8") as fh:
        ts = json.load(fh)
    ids = [c["id"] for c in ts["cases"]]
    assert len(ids) == len(set(ids))
    for c in ts["cases"]:
        assert c.get("prdBrief") and isinstance(c.get("wireframeContent"), dict)
        assert c.get("expected", {}).get("dsComponents")


def test_default_testset_battery_complete():
    """Phase 4b 배터리 계약 — 12케이스, 설계 4장 복잡도 분포(3/6/3)."""
    with open(ev.DEFAULT_TESTSET, encoding="utf-8") as fh:
        ts = json.load(fh)
    assert len(ts["cases"]) == 12
    cx = {}
    for c in ts["cases"]:
        cx[c["complexity"]] = cx.get(c["complexity"], 0) + 1
    assert cx == {"simple": 3, "moderate": 6, "complex": 3}
    # 콘텐츠 dict 는 실제 채점 가능해야 — string 값 ≥5개
    for c in ts["cases"]:
        assert len(ev._content_values(c["wireframeContent"])) >= 5, c["id"]


def test_default_testset_drift_guards():
    """배터리 ↔ 채점기 드리프트 가드 — 미지원 패턴/유령 컴포넌트가 배터리에 들어오면 실패."""
    with open(ev.DEFAULT_TESTSET, encoding="utf-8") as fh:
        ts = json.load(fh)
    catalog = ev._catalog()
    for c in ts["cases"]:
        for pat in c["expected"].get("forbiddenPatterns") or []:
            assert pat in ev._FORBIDDEN_MATCHERS, (
                "%s: 매처 없는 forbiddenPattern '%s'" % (c["id"], pat))
        for prefix in c["expected"]["dsComponents"]:
            in_catalog = any(n.startswith(prefix) for n in catalog)
            assert in_catalog or prefix.startswith("Tool Bar"), (
                "%s: 카탈로그에 없는 expected 컴포넌트 '%s'" % (c["id"], prefix))
    # 모달/시트 케이스는 탭바 케이스와 forbidden 구성이 달라야 한다 (탭바 자체가 없음)
    by_id = {c["id"]: c for c in ts["cases"]}
    assert "raw-navbar-frame" not in by_id["payment-sheet"]["expected"]["forbiddenPatterns"]
    assert "raw-navbar-frame" not in by_id["tx-modal"]["expected"]["forbiddenPatterns"]
