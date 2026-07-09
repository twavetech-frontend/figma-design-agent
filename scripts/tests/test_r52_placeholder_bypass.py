# -*- coding: utf-8 -*-
"""R52 ↔ 0-E-3 충돌 해소 (2026-07-09) — `_placeholderAllowed` 는 R52 bypass.

배경: 와이어에 콘텐츠가 없는 CMS/동적 라운지 카드는 0-E-3(콘텐츠 날조 금지)에 따라
흰 면+보더 placeholder + `_placeholderAllowed` 로 작성하는 게 정답인데, R52 는
imageQuery/_imagelessAllowed 만 인정해 ERROR 를 냈다 (vibe-tests home-signup D2=0
단독 원인). 이제 두 마커 모두 bypass.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from design_rules.R52_lounge_imagequery import _check  # noqa: E402


def _lounge_card(**extra):
    card = {
        "name": "Lounge Card 1", "type": "frame", "width": 140, "height": 140,
        "fill": "$token(bg-primary)",
        "children": [{"type": "text", "text": "라운지"}],
    }
    card.update(extra)
    return {"name": "root", "type": "frame", "children": [card]}


def test_bare_lounge_card_fires():
    assert len(list(_check(_lounge_card(), {}))) == 1


def test_placeholder_allowed_bypasses():
    """0-E-3 CMS placeholder 마커 — R52 미발화 (충돌 해소 핵심)."""
    assert list(_check(_lounge_card(_placeholderAllowed=True), {})) == []


def test_imageless_allowed_bypasses():
    assert list(_check(_lounge_card(_imagelessAllowed="의도적"), {})) == []


def test_imagequery_bypasses():
    assert list(_check(_lounge_card(imageQuery="cozy lounge cafe"), {})) == []


def test_vibe_home_signup_samples_now_pass():
    """실측 회귀 케이스 — 20260709-indexed 의 home-signup 샘플이 로컬에 있으면
    R52 위반 0건이어야 한다 (없으면 skip — results/ 는 gitignore)."""
    import json
    import pytest
    base = os.path.join(os.path.dirname(__file__), "..", "vibe_tests", "results",
                        "20260709-indexed", "blueprints")
    if not os.path.isdir(base):
        pytest.skip("vibe results 없음 (gitignore 산출물)")
    for n in (1, 2):
        p = os.path.join(base, "home-signup-%d.json" % n)
        if not os.path.exists(p):
            continue
        bp = json.load(open(p, encoding="utf-8"))
        assert list(_check(bp, {})) == [], "home-signup-%d 에 R52 위반 잔존" % n
