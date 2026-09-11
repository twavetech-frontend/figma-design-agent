"""규칙 0-H-3 (2026-09-10) — 배치 모드 판정 + 뷰포트 중앙 좌표 변환 오프라인 테스트."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import figma_mcp_client as fc  # noqa: E402


def test_placement_mode_default_is_center(monkeypatch):
    monkeypatch.delenv("IMIN_PLACEMENT", raising=False)
    assert fc._placement_mode() == "center"
    assert fc._placement_mode({"name": "x"}) == "center"


def test_placement_mode_priority(monkeypatch):
    monkeypatch.delenv("IMIN_PLACEMENT", raising=False)
    assert fc._placement_mode({"_placement": "right"}) == "right"
    monkeypatch.setenv("IMIN_PLACEMENT", "right")
    assert fc._placement_mode({"_placement": "center"}) == "right"      # env > blueprint
    assert fc._placement_mode({"_placement": "right"}, "center") == "center"  # explicit > env
    monkeypatch.setenv("IMIN_PLACEMENT", "bogus")
    assert fc._placement_mode() == "center"                             # 잘못된 값은 무시


def test_viewport_center_position_page_and_section():
    # 페이지 직속: root 중심이 center 에 오도록
    assert fc._viewport_center_position({"x": 1000, "y": 500}, None, 393, 852) == (804, 74)
    # 섹션 자식: 섹션 절대 좌표만큼 빼서 상대좌표로
    assert fc._viewport_center_position({"x": 1000, "y": 500}, {"x": 600, "y": 200}, 393, 852) == (204, -126)


def test_resolve_parent_abs_prefers_bbox_then_abs_then_xy():
    """2026-09-11 회귀: 섹션 안 clone 을 페이지 좌표로 옮겨 화면 밖으로 날아감 — 섹션 절대 원점 해석."""
    assert fc._resolve_parent_abs({"x": 5, "y": 6}, {"x": -118016, "y": -41850}) == {"x": -118016.0, "y": -41850.0}
    assert fc._resolve_parent_abs({"x": 5, "y": 6, "absoluteBoundingBox": {"x": -1, "y": -2}}) == {"x": -1.0, "y": -2.0}
    assert fc._resolve_parent_abs({"x": 5, "y": 6}) == {"x": 5.0, "y": 6.0}
    # 뷰포트 중앙 → 섹션 상대좌표
    assert fc._viewport_center_position({"x": -114371, "y": -43173}, {"x": -118016, "y": -41850}, 393, 852) == (3448, -1749)
