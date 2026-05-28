"""R53 — HORIZONTAL parent 의 sibling VERTICAL cell 들 alignment 통일 (2026-05-28).

문제: Day Strip 처럼 HORIZONTAL parent 에 여러 VERTICAL cell 이 있을 때, 각 cell 의
counterAxisAlignItems 와 자식 텍스트 textAlignHorizontal 이 다르면 alignment 깨짐.

예: v15 Day Strip
  - 어제 cell: counterAxis=CENTER + 텍스트 LEFT → 좌측 정렬
  - 오늘 cell (pill): counterAxis=CENTER + 텍스트 CENTER → 가운데
  - 16~19일 cell: counterAxis=CENTER + 텍스트 LEFT 또는 LEFT → 좌측

Fix (inject): HORIZONTAL parent 안 sibling VERTICAL cell 들 중 ≥3개가 같은 구조
(VERTICAL + same children types) 이면, 모든 cell 의 counterAxisAlignItems 와
자식 텍스트 textAlignHorizontal 을 통일 (다수결).
"""
from __future__ import annotations

from .base import Rule, register, walk_blueprint


def _is_vertical_cell(node: dict) -> bool:
    if (node.get("type") or "").lower() != "frame":
        return False
    al = node.get("autoLayout") or {}
    return al.get("layoutMode") == "VERTICAL"


def _cell_signature(node: dict) -> str:
    """cell 내부 자식 type sequence — 같은 패턴 카운트용."""
    types = []
    for ch in (node.get("children") or []):
        types.append((ch.get("type") or "").lower())
    return ",".join(types)


def _inject(bp: dict) -> dict:
    fixed = 0
    for node, _ in walk_blueprint(bp):
        al = node.get("autoLayout") or {}
        if al.get("layoutMode") != "HORIZONTAL":
            continue
        kids = node.get("children") or []
        # VERTICAL cell sibling 들만
        cells = [k for k in kids if _is_vertical_cell(k)]
        if len(cells) < 3:
            continue
        # 같은 signature 가 다수면 alignment 통일 대상
        sigs = [_cell_signature(c) for c in cells]
        from collections import Counter
        sig_counter = Counter(sigs)
        majority_sig, count = sig_counter.most_common(1)[0]
        if count < 3:
            continue
        # 모든 cell 의 counterAxis 통일 (다수결, 기본 CENTER)
        ca_values = [(c.get("autoLayout") or {}).get("counterAxisAlignItems") or "CENTER" for c in cells]
        ca_counter = Counter(ca_values)
        majority_ca = ca_counter.most_common(1)[0][0]
        # 각 cell 내 텍스트 textAlignHorizontal 다수결
        text_aligns = []
        for c in cells:
            for ch in (c.get("children") or []):
                if (ch.get("type") or "").lower() == "text":
                    text_aligns.append(ch.get("textAlignHorizontal") or "LEFT")
        if text_aligns:
            ta_counter = Counter(text_aligns)
            # CENTER 이 1개라도 있고 LEFT 가 1개라도 있으면 CENTER 로 강제
            # (cell row 의 일반적인 표현은 CENTER)
            majority_ta = "CENTER" if "CENTER" in text_aligns else ta_counter.most_common(1)[0][0]
        else:
            majority_ta = None
        # 통일 적용
        for c in cells:
            c_al = c.setdefault("autoLayout", {})
            if c_al.get("counterAxisAlignItems") != majority_ca:
                c_al["counterAxisAlignItems"] = majority_ca
                fixed += 1
            if majority_ta:
                for ch in (c.get("children") or []):
                    if (ch.get("type") or "").lower() == "text":
                        if ch.get("textAlignHorizontal") != majority_ta:
                            ch["textAlignHorizontal"] = majority_ta
                            # layoutSizingHorizontal FILL 박아 CENTER 정렬 작동
                            ch["layoutSizingHorizontal"] = "FILL"
                            fixed += 1
    if fixed:
        print(f"[inject R53] HORIZONTAL cell row alignment 통일 {fixed}건 (Day Strip 회귀 차단)")
    return bp


register(Rule(
    rule_id="R53-cell-row-alignment",
    title="HORIZONTAL cell row sibling alignment unify",
    description=(
        "HORIZONTAL parent 안 ≥3개의 같은 구조 VERTICAL cell sibling 의 "
        "counterAxisAlignItems + 자식 텍스트 textAlignHorizontal 통일 강제. "
        "Day Strip 회귀 차단. 2026-05-28 사용자 명시."
    ),
    inject_blueprint_fn=_inject,
))
