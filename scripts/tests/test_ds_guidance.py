# -*- coding: utf-8 -*-
"""component/search 조회 — ds_guidance 모듈 + COMPONENT_GUIDANCE.json 계약 (2026-07-08).

계약:
  - COMPONENT_GUIDANCE.json 은 우리 소유(커밋 대상) — 이름 유일, guidance[].do 는 bool
  - componentKey 는 가이드 파일에 없고 catalogPrefixes 로 ds_catalog 에서 런타임 해석
  - find: 이름/별칭 정확 일치 → 1건, 애매하면 (None, 후보들)
  - search: 이름(100) > 별칭(80) > 키워드(60) > 본문(30) 랭킹
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ds_guidance as dg  # noqa: E402

ENTRIES = dg.load_guidance()


# ── 가이드 파일 불변식 ─────────────────────────────────────────────────────────

def test_guidance_file_invariants():
    assert len(ENTRIES) >= 8
    names = [e["name"] for e in ENTRIES]
    assert len(names) == len(set(names)), "컴포넌트 이름 중복"
    for e in ENTRIES:
        assert e.get("name") and isinstance(e.get("guidance"), list) and e["guidance"], e.get("name")
        for g in e["guidance"]:
            assert isinstance(g.get("do"), bool), "%s: do 는 bool" % e["name"]
            assert g.get("description"), e["name"]
        if "blueprintExample" in e:
            assert isinstance(e["blueprintExample"], dict)
        assert isinstance(e.get("catalogPrefixes"), list), e["name"]


def test_core_components_present():
    names = {e["name"] for e in ENTRIES}
    for required in ("Status Bar", "Tool Bar", "Tab bar", "Underline tabs",
                     "Segmented_control", "Action Button", "Badge"):
        assert required in names, required


# ── find ────────────────────────────────────────────────────────────────────

def test_find_exact_and_alias():
    e, _ = dg.find("Tab bar", ENTRIES)
    assert e and e["name"] == "Tab bar"
    e, _ = dg.find("하단 탭바", ENTRIES)
    assert e and e["name"] == "Tab bar"
    e, _ = dg.find("NavBar", ENTRIES)  # 별칭 → Tool Bar
    assert e and e["name"] == "Tool Bar"
    e, _ = dg.find("navbar", ENTRIES)  # 대소문자 무시
    assert e and e["name"] == "Tool Bar"


def test_find_miss_returns_candidates():
    e, cands = dg.find("존재하지않는컴포넌트xyz", ENTRIES)
    assert e is None
    assert cands == []
    e, cands = dg.find("", ENTRIES)  # 빈 쿼리 → 전체 후보
    assert e is None and len(cands) == len(ENTRIES)


# ── catalog 키 해석 ─────────────────────────────────────────────────────────

def test_resolve_catalog_keys_tab_bar():
    e, _ = dg.find("Tab bar", ENTRIES)
    keys = dg.resolve_catalog_keys(e)
    assert any(n.startswith("Tab Bar") for n in keys), keys
    # CLAUDE.md 0-M 의 '홈' variant key 가 카탈로그와 일치해야 한다
    home = {n: k for n, k in keys.items() if "홈" in n}
    if home:
        assert list(home.values())[0] == "0faaa55563de4da617964ea93ba07f09bc1279f6"


def test_resolve_catalog_keys_uses_injected_catalog():
    e = {"catalogPrefixes": ["Foo"]}
    keys = dg.resolve_catalog_keys(e, catalog={"Foo bar": "k1", "Baz": "k2"})
    assert keys == {"Foo bar": "k1"}


# ── search ──────────────────────────────────────────────────────────────────

def test_search_ranks_name_over_keyword():
    results = dg.search("badge", ENTRIES, catalog={})
    assert results and results[0]["name"] == "Badge"
    assert results[0]["score"] == 100


def test_search_korean_keyword():
    results = dg.search("인디케이터", ENTRIES, catalog={})
    assert any(r["name"] == "Pagination dot group" for r in results)


def test_search_includes_catalog():
    results = dg.search("checkbox", ENTRIES, catalog={"Checkbox md": "abc123"})
    kinds = {r["kind"] for r in results}
    assert "guidance" in kinds and "catalog" in kinds
    cat = [r for r in results if r["kind"] == "catalog"][0]
    assert cat["snippet"] == "abc123"


def test_search_empty():
    assert dg.search("", ENTRIES, catalog={}) == []


# ── 포맷 ────────────────────────────────────────────────────────────────────

def test_format_entry_dense_and_full():
    e, _ = dg.find("Segmented_control", ENTRIES)
    dense = dg.format_entry(e)
    assert "✓" in dense and "✗" in dense
    assert "_forceSegmented" in dense
    full = dg.format_entry(e, full=True)
    assert "blueprint 예시" in full and len(full) > len(dense)


def test_entry_as_json_shape():
    e, _ = dg.find("Badge", ENTRIES)
    doc = dg.entry_as_json(e)
    assert doc["type"] == "component"
    assert doc["name"] == "Badge"
    assert isinstance(doc["componentKeys"], dict)
    assert all(isinstance(g.get("do"), bool) for g in doc["guidance"])
