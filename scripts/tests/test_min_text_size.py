"""규칙 2-C-2 — 텍스트 크기 하한 enforcer 의 Body xs(12) 허용 범위 (2026-09-30).

사용자: "body xs 텍스트 토큰을 하나도 쓰지 않았더라. 왜 그런거지?" — footer 만 예외라 조건 문구·메타·고지까지 14 로 올라갔다.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import figma_mcp_client as fmc  # noqa: E402


def _t(name, size, **extra):
    d = {"name": name, "type": "text", "text": "조건 문구 예시", "fontSize": size}
    d.update(extra)
    return d


def _run(children):
    bp = {"name": "root", "type": "frame", "children": children}
    fmc._enforce_min_text_size(bp)
    return {c["name"]: c["fontSize"] for c in bp["children"]}


def test_fine_named_texts_keep_body_xs():
    out = _run([_t("Cell Sub", 12), _t("Tile Cond", 12), _t("Meta Opened", 12), _t("Notice Text", 12),
                _t("Final Caption", 12), _t("Benefits Note", 12), _t("Input Helper", 12)])
    assert all(v == 12 for v in out.values()), out


def test_generic_texts_still_floor_to_14():
    out = _run([_t("Cell Label", 12), _t("Item Title", 12), _t("KV Value", 12), _t("Body Copy", 13)])
    assert all(v == 14 for v in out.values()), out


def test_fine_marker_and_footer_keep_12_but_never_below():
    out = _run([_t("Any Text", 12, _fine=True), _t("Any Text 2", 10, _fine=True), _t("Tile Cond", 9)])
    assert out == {"Any Text": 12, "Any Text 2": 12, "Tile Cond": 12}
    bp = {"name": "root", "type": "frame", "children": [{"name": "Footer", "type": "frame", "children": [_t("Copy", 12), _t("Tiny", 8)]}]}
    fmc._enforce_min_text_size(bp)
    assert [c["fontSize"] for c in bp["children"][0]["children"]] == [12, 12]


def test_is_fine_text_word_boundary():
    assert fmc._is_fine_text("Cell Sub") and fmc._is_fine_text("Group Cond") and fmc._is_fine_text("notice_text")
    assert not fmc._is_fine_text("Subtitle Big")      # 'subtitle' 은 단어 'sub' 가 아님
    assert not fmc._is_fine_text("Metadata Label")    # 'metadata' ≠ 'meta'
    assert fmc._is_fine_text("Whatever", {"_fine": True})
