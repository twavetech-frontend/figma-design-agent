# -*- coding: utf-8 -*-
"""size-invariant 가드 — SVG 아이콘 프레임이 가로 FILL 로 늘어나거나 한 축 붕괴 시 정사각 복원 (2026-06-18).

회귀: choice tile 아이콘 'piggy-bank-01' 이 28×28 → 134×28(가로 FILL) / 1×28(붕괴)로 변형돼
vector 가 납작해짐. 원형 가드(_is_circle_square_target)는 cornerRadius=0 라 못 잡음 →
_is_stretched_icon_frame 신설.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as f


def _icon(w, h, child_type="VECTOR"):
    return {"type": "FRAME", "name": "piggy-bank-01",
            "children": [{"type": child_type, "name": "v"}],
            "absoluteBoundingBox": {"width": w, "height": h}}


def test_stretched_icon_detected():
    assert f._is_stretched_icon_frame(_icon(134, 28))   # 가로 FILL 로 늘어남
    assert f._is_stretched_icon_frame(_icon(1, 28))      # 가로 붕괴
    assert f._is_stretched_icon_frame(_icon(16, 36))     # 한 축 붕괴(아바타류)


def test_square_icon_not_targeted():
    assert not f._is_stretched_icon_frame(_icon(28, 28))  # 정상 정사각
    assert not f._is_stretched_icon_frame(_icon(24, 26))  # 거의 정사각(|w-h|≤6)


def test_non_icon_frame_excluded():
    # 텍스트 자식 프레임은 아이콘 아님
    assert not f._is_stretched_icon_frame(
        {"type": "FRAME", "children": [{"type": "TEXT"}],
         "absoluteBoundingBox": {"width": 134, "height": 28}})
    # 빈 프레임
    assert not f._is_stretched_icon_frame(
        {"type": "FRAME", "children": [], "absoluteBoundingBox": {"width": 134, "height": 28}})
    # 큰 면적(아이콘 아님 — min 축이 큼)
    assert not f._is_stretched_icon_frame(_icon(300, 120))


def test_square_side_formula():
    # _enforce_fixed_size_invariants_final 의 side 계산: 큰 축 비현실(>64)이면 작은 축, 아니면 큰 축
    def side(w, h):
        mx, mn = max(w, h), min(w, h)
        return round(mn if mx > 64 else mx)
    assert side(134, 28) == 28   # 늘어남 → 작은 축
    assert side(1, 28) == 28     # 붕괴 → 작은 축(max 28≤64)
    assert side(16, 36) == 36    # 붕괴 → 큰 축(36≤64)


if __name__ == "__main__":
    import traceback
    passed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); passed += 1; print(f"  ✓ {name}")
            except Exception:
                print(f"  ✗ {name}"); traceback.print_exc()
    print(f"✅ {passed} 통과")
