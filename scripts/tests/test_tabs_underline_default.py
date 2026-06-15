# -*- coding: utf-8 -*-
"""R60 — 콘텐츠/뷰 전환 탭은 underline tabs 가 기본, Segmented_control 은 _forceSegmented 만 (2026-06-12).

사용자 룰: 입금/지급 같은 뷰 전환 탭이 Segmented_control 로 빌드되던 회귀 → underline tabs 로 변환.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from design_rules import R60_tabs_ds_instance as R60


def _find(node, pred):
    if pred(node):
        return node
    for c in (node.get("children") or []):
        r = _find(c, pred)
        if r:
            return r
    return None


def _is_underline_tabs(n):
    return isinstance(n, dict) and n.get("_underlineTabs") is True


def test_seg_view_tabs_converted_to_underline():
    """_segLabels(Segmented_control) 뷰 전환 탭 → underline tabs frame."""
    bp = {"name": "Root", "type": "frame", "children": [
        {"name": "View Tabs", "type": "instance",
         "componentKey": "2ee9d12d4c904650ab496b9bcdf874a648e73ceb",
         "_segLabels": ["입금", "지급"], "_segActive": 0,
         "layoutSizingHorizontal": "FILL"},
    ]}
    R60._inject(bp)
    vt = _find(bp, lambda n: n.get("name") == "View Tabs")
    assert vt is not None
    assert vt["type"] == "frame", "instance 가 frame 으로 변환돼야 함"
    assert vt.get("_underlineTabs") is True
    assert "_segLabels" not in vt, "_segLabels 마커 제거"
    assert "componentKey" not in vt, "componentKey 제거"
    # 라벨 2개 cell
    cells = vt.get("children") or []
    assert len(cells) == 2
    labels = []
    for c in cells:
        for cc in (c.get("children") or []):
            if (cc.get("type") or "").lower() == "text":
                labels.append(cc.get("text"))
    assert labels == ["입금", "지급"], labels
    # active(0) 탭의 underline 에 fill, inactive 는 None
    und0 = [x for x in (cells[0].get("children") or []) if "Underline" in (x.get("name") or "")][0]
    und1 = [x for x in (cells[1].get("children") or []) if "Underline" in (x.get("name") or "")][0]
    assert und0.get("fill"), "active 밑줄 bar fill 있어야"
    assert und1.get("fill") in (None,), "inactive 밑줄 bar fill 없어야"


def test_force_segmented_kept():
    """_forceSegmented:true 면 Segmented_control 유지 (변환 안 함)."""
    bp = {"name": "Root", "type": "frame", "children": [
        {"name": "Sort Toggle", "type": "instance",
         "componentKey": "47a01673a46dc3bc9bfd62948c10e5fa9f2e5e78",
         "_segLabels": ["주", "월", "년"], "_segActive": 1,
         "_forceSegmented": True},
    ]}
    R60._inject(bp)
    node = _find(bp, lambda n: n.get("name") == "Sort Toggle")
    assert node["type"] == "instance", "_forceSegmented 는 instance 유지"
    assert node.get("_segLabels") == ["주", "월", "년"], "_segLabels 보존"
    assert not node.get("_underlineTabs")


def test_raw_tab_nav_frame_converted_to_underline():
    """raw tab-nav frame(이름 힌트 + 텍스트 cell) → underline tabs."""
    bp = {"name": "Root", "type": "frame", "children": [
        {"name": "Mode Tabs Wrap", "type": "frame", "layoutMode": "HORIZONTAL",
         "autoLayout": {"layoutMode": "HORIZONTAL"},
         "children": [
            {"name": "Tab Active", "type": "frame", "children": [
                {"type": "text", "text": "거래현황", "fontSize": 18}]},
            {"name": "Tab", "type": "frame", "children": [
                {"type": "text", "text": "누적거래", "fontSize": 18}]},
         ]},
    ]}
    R60._inject(bp)
    wrap = _find(bp, lambda n: n.get("name") == "Mode Tabs Wrap")
    assert wrap["type"] == "frame"
    assert wrap.get("_underlineTabs") is True
    labels = []
    for c in (wrap.get("children") or []):
        for cc in (c.get("children") or []):
            if (cc.get("type") or "").lower() == "text":
                labels.append(cc.get("text"))
    assert labels == ["거래현황", "누적거래"], labels
    # active = 첫 탭(이름에 'active')
    cells = wrap.get("children") or []
    und0 = [x for x in (cells[0].get("children") or []) if "Underline" in (x.get("name") or "")][0]
    assert und0.get("fill"), "active(첫) 탭 밑줄 fill"


def test_underline_marker_not_touched():
    """이미 _underlineTabs 인 노드는 그대로 둠."""
    bp = {"name": "Root", "type": "frame", "children": [
        {"name": "View Tabs", "type": "frame", "_underlineTabs": True,
         "children": [
            {"name": "Tab 추천", "type": "frame", "children": [
                {"type": "text", "text": "추천", "fontSize": 22}]}]},
    ]}
    before = bp["children"][0]["children"][0]["children"][0]["text"]
    R60._inject(bp)
    after = bp["children"][0]["children"][0]["children"][0]["text"]
    assert before == after == "추천"


if __name__ == "__main__":
    test_seg_view_tabs_converted_to_underline()
    test_force_segmented_kept()
    test_raw_tab_nav_frame_converted_to_underline()
    test_underline_marker_not_touched()
    print("✅ 모든 테스트 통과")
