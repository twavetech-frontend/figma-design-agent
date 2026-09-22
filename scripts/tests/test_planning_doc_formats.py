# -*- coding: utf-8 -*-
"""기획 문서 형식 확장 회귀 테스트 (2026-09-22).

기존엔 src/기획/ 의 .html 만 읽어, PDF·Word·Markdown 을 넣어도 **조용히 무시**됐다
(기획자가 "넣었는데 왜 반영이 안 되지?" 를 겪던 지점). 이제 .md/.txt/.docx/.pdf 도 학습 대상.

오프라인 테스트 — 임시 폴더를 _PLAN_DIR 로 갈아끼워 실물 기획 폴더와 무관하게 검증한다.
"""
import importlib.util
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_RP = os.path.join(os.path.dirname(__file__), "..", "read_planning_docs.py")
_spec = importlib.util.spec_from_file_location("read_planning_docs_fmt", _RP)
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)


def _docx(path, paragraphs):
    """최소 .docx (zip + word/document.xml) 생성 — 외부 라이브러리 없이."""
    body = "".join(
        "<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % p for p in paragraphs
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>%s</w:body></w:document>" % body
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", xml)


def _plan_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(rp, "_PLAN_DIR", str(tmp_path))
    return tmp_path


def test_supported_exts_cover_common_doc_formats():
    for ext in (".html", ".htm", ".md", ".markdown", ".txt", ".docx", ".pdf"):
        assert ext in rp.SUPPORTED_EXTS


def test_collect_picks_up_non_html_docs(tmp_path, monkeypatch):
    _plan_dir(tmp_path, monkeypatch)
    (tmp_path / "10-UC-A.html").write_text("<p>에이치티엠엘</p>", encoding="utf-8")
    (tmp_path / "11-UC-B.md").write_text("# 마크다운 문서", encoding="utf-8")
    (tmp_path / "12-UC-C.txt").write_text("평문 문서", encoding="utf-8")
    _docx(str(tmp_path / "13-UC-D.docx"), ["워드 문단 1", "워드 문단 2"])
    (tmp_path / "노트.pages").write_text("미지원 형식", encoding="utf-8")  # 제외 대상

    names = [os.path.basename(p) for p in rp.collect_doc_files()]
    assert names == ["10-UC-A.html", "11-UC-B.md", "12-UC-C.txt", "13-UC-D.docx"]


def test_collect_skips_office_temp_and_hidden(tmp_path, monkeypatch):
    _plan_dir(tmp_path, monkeypatch)
    (tmp_path / "20-UC-E.docx").write_bytes(b"")  # 이름만 — 수집 대상
    (tmp_path / "~$20-UC-E.docx").write_bytes(b"")  # Word 임시 파일
    (tmp_path / ".DS_Store.txt").write_text("숨김", encoding="utf-8")

    names = [os.path.basename(p) for p in rp.collect_doc_files()]
    assert names == ["20-UC-E.docx"]


def test_digest_includes_markdown_and_docx_text(tmp_path, monkeypatch):
    _plan_dir(tmp_path, monkeypatch)
    (tmp_path / "10-UC-A.md").write_text("## 스테이지 참여\n최소 5명", encoding="utf-8")
    _docx(str(tmp_path / "11-UC-B.docx"), ["월렛 출금 신청", "1일 1회 제한"])

    digest, count, token = rp.build_digest()
    assert count == 2
    assert len(token) == 12
    assert "스테이지 참여" in digest
    assert "최소 5명" in digest
    assert "월렛 출금 신청" in digest
    assert "1일 1회 제한" in digest
    # 통독 토큰은 여전히 맨 끝 footer 에만 (cheat 방지 불변)
    assert token in digest[-500:]
    assert token not in digest[:-500]


def test_unreadable_file_is_reported_not_silently_dropped(tmp_path, monkeypatch):
    """읽기 실패한 문서는 digest 에 흔적을 남긴다 — 조용한 무시가 원래 문제였다."""
    _plan_dir(tmp_path, monkeypatch)
    (tmp_path / "10-UC-A.txt").write_text("정상 문서", encoding="utf-8")
    (tmp_path / "11-UC-B.docx").write_bytes(b"not-a-zip")  # 깨진 파일

    digest, count, _token = rp.build_digest()
    assert count == 2
    assert "정상 문서" in digest
    assert "[읽기 실패] 11-UC-B.docx" in digest


def test_fingerprint_tracks_non_html_changes(tmp_path, monkeypatch):
    _plan_dir(tmp_path, monkeypatch)
    (tmp_path / "10-UC-A.md").write_text("처음", encoding="utf-8")
    before = rp.fingerprint()["hash"]
    (tmp_path / "11-UC-B.pdf").write_bytes(b"%PDF-1.4 stub")
    assert rp.fingerprint()["hash"] != before
    assert rp.fingerprint()["count"] == 2


def test_garbled_pdf_text_is_detected():
    """폰트 매핑 없는 한글 PDF 는 다른 문자 영역의 글자로 쏟아진다 — 조용히 학습되면 안 된다."""
    garbled = "झప੉૑ ૑ә ӏ஗ ਷ ݺ ఠ ׮ " * 40
    assert rp._looks_garbled(garbled) is True


def test_normal_text_is_not_flagged_as_garbled():
    assert rp._looks_garbled("스테이지 지급 규칙은 순번 배정에 따른다. " * 20) is False
    assert rp._looks_garbled("Stage payout rule applies to members. " * 20) is False
    assert rp._looks_garbled("짧은 문서") is False  # 표본 부족 시 오탐 금지
