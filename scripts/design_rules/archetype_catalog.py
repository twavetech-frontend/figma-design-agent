"""Generative archetype catalog — turns minimal blueprint into polished output.

Philosophy: rules so far have been restrictive ("don't use raw hex").
Restrictive rules cap quality at "doesn't look broken" — to push quality
UP we need GENERATIVE rules that say "here's what a good X looks like".

Each archetype:
  - matches a node-name pattern
  - has a content template (children) injected if the node has none
  - has visual defaults (effects, layout, color accents)
  - leaves the model creative freedom for content (just provide data via
    archetypeData)

Usage:
    blueprint frame: { name: "Stage Card 1", archetype: "stage-card",
                       archetypeData: { tag: "진행중", amount: "10만원",
                                        period: "13개월 · 모으기",
                                        progress: 35 } }
  → R50 inject expands to full polished card.

Authors set archetypeData to override defaults; if nothing given, sensible
placeholders are used so first build looks rich.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional, Tuple


# ── Token shorthand ────────────────────────────────────────────

def TOK(name: str) -> str:
    """Wrap a token name into $token() form."""
    return f"$token(Colors/{name})"


def _text(content: str, weight: int = 500, size: int = 14,
          color: str = "Foreground/fg-primary", **kw) -> dict:
    n = {
        "name": content[:24],
        "type": "text",
        "characters": content,
        "fontFamily": "Pretendard",
        "fontWeight": weight,
        "fontSize": size,
        "fontColor": TOK(color),
    }
    n.update(kw)
    return n


def _frame(name: str, **kw) -> dict:
    n = {"name": name, "type": "frame"}
    n.update(kw)
    return n


# ── Archetype templates ────────────────────────────────────────

def stage_card_template(node: dict) -> dict:
    """Stage participation card — tag pill, amount, period, progress.

    archetypeData:
      tag: status pill text (default "진행중")
      amount: large amount text (default "10만원")
      period: subtitle (default "13개월 · 모으기")
      progress: 0-100 (default 30)
      accent: "brand"|"success"|"warning"|"error" (default "brand")
    """
    d = node.get("archetypeData") or {}
    tag = d.get("tag", "진행중")
    amount = d.get("amount", "10만원")
    period = d.get("period", "13개월 · 모으기")
    progress = max(0, min(100, int(d.get("progress", 30))))
    accent = d.get("accent", "brand")
    accent_bg = {
        "brand": "Background/bg-brand-solid",
        "success": "Background/bg-success-solid",
        "warning": "Background/bg-warning-solid",
        "error": "Background/bg-error-solid",
    }.get(accent, "Background/bg-brand-solid")

    return {
        "name": node["name"],
        "type": "frame",
        "width": node.get("width", 132),
        "height": node.get("height", 168),
        "layoutSizingHorizontal": node.get("layoutSizingHorizontal", "FIXED"),
        "layoutSizingVertical": node.get("layoutSizingVertical", "FIXED"),
        "fill": TOK("Background/bg-secondary"),
        "cornerRadius": 16,
        "effects": [{
            "type": "DROP_SHADOW", "visible": True,
            "color": {"r": 0, "g": 0, "b": 0, "a": 0.04},
            "offset": {"x": 0, "y": 2}, "radius": 8, "spread": 0,
        }],
        "autoLayout": {
            "layoutMode": "VERTICAL", "primaryAxisAlignItems": "MIN",
            "counterAxisAlignItems": "MIN", "itemSpacing": 8,
            "paddingTop": 14, "paddingBottom": 14,
            "paddingLeft": 14, "paddingRight": 14,
        },
        "children": [
            _frame(
                f"{node['name']} Tag",
                layoutSizingHorizontal="HUG", layoutSizingVertical="HUG",
                fill=TOK("Background/bg-tertiary"),
                cornerRadius=999,
                autoLayout={
                    "layoutMode": "HORIZONTAL", "paddingTop": 4,
                    "paddingBottom": 4, "paddingLeft": 8, "paddingRight": 8,
                    "primaryAxisAlignItems": "CENTER",
                    "counterAxisAlignItems": "CENTER",
                },
                children=[_text(tag, weight=700, size=10,
                                color="Foreground/fg-secondary")]
            ),
            _frame(
                f"{node['name']} Spacer1",
                layoutSizingHorizontal="FILL", height=4,
                layoutSizingVertical="FIXED",
            ),
            _text(amount, weight=700, size=20, color="Foreground/fg-primary"),
            _text(period, weight=500, size=11,
                  color="Foreground/fg-tertiary",
                  layoutSizingHorizontal="FILL"),
            _frame(
                f"{node['name']} Spacer2",
                layoutSizingHorizontal="FILL", height=4,
                layoutSizingVertical="FIXED",
            ),
            _frame(
                f"{node['name']} Progress",
                layoutSizingHorizontal="FILL", height=6,
                layoutSizingVertical="FIXED",
                fill=TOK("Background/bg-tertiary"),
                cornerRadius=3,
                children=[_frame(
                    f"{node['name']} Fill",
                    width=max(2, int((node.get('width', 132) - 28) * progress / 100)),
                    height=6,
                    layoutSizingHorizontal="FIXED",
                    layoutSizingVertical="FIXED",
                    fill=TOK(accent_bg), cornerRadius=3,
                )],
            ),
        ],
    }


def product_card_template(node: dict) -> dict:
    """Lounge product card — image area, name, price.

    archetypeData:
      name: product name (default "상품명")
      price: price label (default "10,000원")
      image_color: hint for placeholder (default "neutral")
    """
    d = node.get("archetypeData") or {}
    name = d.get("name", "상품명")
    price = d.get("price")  # optional
    children = [
        _frame(
            f"{node['name']} Img",
            width=node.get("width", 80),
            height=int(node.get("width", 80) * 1.0),
            layoutSizingHorizontal="FIXED", layoutSizingVertical="FIXED",
            fill=TOK("Background/bg-secondary"),
            cornerRadius=12,
        ),
        _text(name, weight=600, size=11,
              color="Foreground/fg-primary",
              textAlignHorizontal="LEFT",
              layoutSizingHorizontal="FILL"),
    ]
    if price:
        children.append(_text(price, weight=700, size=12,
                              color="Foreground/fg-primary",
                              layoutSizingHorizontal="FILL"))
    return {
        "name": node["name"],
        "type": "frame",
        "width": node.get("width", 80),
        "layoutSizingHorizontal": node.get("layoutSizingHorizontal", "FIXED"),
        "layoutSizingVertical": node.get("layoutSizingVertical", "HUG"),
        "fill": TOK("Background/bg-primary"),
        "autoLayout": {
            "layoutMode": "VERTICAL", "primaryAxisAlignItems": "MIN",
            "counterAxisAlignItems": "MIN", "itemSpacing": 6,
            "paddingTop": 0, "paddingBottom": 0,
            "paddingLeft": 0, "paddingRight": 0,
        },
        "children": children,
    }


def stat_card_template(node: dict) -> dict:
    """Stat card — big number + label + delta indicator.

    archetypeData:
      value: big number (e.g. "312,490원")
      label: caption (e.g. "예치금")
      delta: "+12%" / "-3%" / None
    """
    d = node.get("archetypeData") or {}
    value = d.get("value", "0")
    label = d.get("label", "Label")
    delta = d.get("delta")
    children = [
        _text(label, weight=500, size=12,
              color="Foreground/fg-tertiary"),
        _text(value, weight=700, size=24,
              color="Foreground/fg-primary"),
    ]
    if delta:
        delta_color = ("Foreground/fg-success-primary" if delta.startswith("+")
                       else "Foreground/fg-error-primary")
        children.append(_text(delta, weight=700, size=11, color=delta_color))
    return {
        "name": node["name"],
        "type": "frame",
        "layoutSizingHorizontal": node.get("layoutSizingHorizontal", "FILL"),
        "layoutSizingVertical": node.get("layoutSizingVertical", "HUG"),
        "fill": TOK("Background/bg-secondary"),
        "cornerRadius": 12,
        "effects": [{
            "type": "DROP_SHADOW", "visible": True,
            "color": {"r": 0, "g": 0, "b": 0, "a": 0.04},
            "offset": {"x": 0, "y": 2}, "radius": 8, "spread": 0,
        }],
        "autoLayout": {
            "layoutMode": "VERTICAL", "primaryAxisAlignItems": "MIN",
            "counterAxisAlignItems": "MIN", "itemSpacing": 4,
            "paddingTop": 16, "paddingBottom": 16,
            "paddingLeft": 16, "paddingRight": 16,
        },
        "children": children,
    }


def list_item_card_template(node: dict) -> dict:
    """List item — leading icon + (title + subtitle) + trailing chevron.

    archetypeData:
      title (req), subtitle, leading_icon ("calendar"/"wallet"/...)
    """
    d = node.get("archetypeData") or {}
    title = d.get("title", "Title")
    subtitle = d.get("subtitle", "")
    leading = d.get("leading_icon", "")
    children = []
    if leading:
        children.append(_frame(
            f"{leading} Icon",  # R23 inject will swap
            width=24, height=24,
            layoutSizingHorizontal="FIXED", layoutSizingVertical="FIXED",
        ))
    text_col = _frame(
        f"{node['name']} Text",
        layoutSizingHorizontal="FILL", layoutSizingVertical="HUG",
        autoLayout={"layoutMode": "VERTICAL", "itemSpacing": 2},
        children=([_text(title, weight=700, size=14,
                         color="Foreground/fg-primary")]
                  + ([_text(subtitle, weight=500, size=12,
                            color="Foreground/fg-tertiary")]
                     if subtitle else [])),
    )
    children.append(text_col)
    children.append(_frame(
        "Chevron Right Icon",  # R23 inject swaps to icon
        width=20, height=20,
        layoutSizingHorizontal="FIXED", layoutSizingVertical="FIXED",
    ))
    return {
        "name": node["name"],
        "type": "frame",
        "layoutSizingHorizontal": node.get("layoutSizingHorizontal", "FILL"),
        "layoutSizingVertical": node.get("layoutSizingVertical", "HUG"),
        "fill": TOK("Background/bg-secondary"),
        "cornerRadius": 12,
        "autoLayout": {
            "layoutMode": "HORIZONTAL", "primaryAxisAlignItems": "MIN",
            "counterAxisAlignItems": "CENTER", "itemSpacing": 12,
            "paddingTop": 14, "paddingBottom": 14,
            "paddingLeft": 14, "paddingRight": 14,
        },
        "children": children,
    }


def hero_banner_template(node: dict) -> dict:
    """Hero banner — gradient bg + headline + subline + CTA hint.

    Uses brand-solid bg with white text. Subtle gradient via two
    overlay rectangles (true gradient fills are added in post-fix
    if requested via archetypeData.gradient=True).
    """
    d = node.get("archetypeData") or {}
    headline = d.get("headline", "Hero Headline")
    subline = d.get("subline", "Hero subline goes here")
    return {
        "name": node["name"],
        "type": "frame",
        "layoutSizingHorizontal": node.get("layoutSizingHorizontal", "FILL"),
        "height": node.get("height", 162),
        "layoutSizingVertical": "FIXED",
        "fill": TOK("Background/bg-brand-solid"),
        "cornerRadius": 16,
        "effects": [{
            "type": "DROP_SHADOW", "visible": True,
            "color": {"r": 0.32, "g": 0, "b": 0.69, "a": 0.18},
            "offset": {"x": 0, "y": 6}, "radius": 16, "spread": 0,
        }],
        "autoLayout": {
            "layoutMode": "VERTICAL", "primaryAxisAlignItems": "MIN",
            "counterAxisAlignItems": "MIN", "itemSpacing": 6,
            "paddingTop": 24, "paddingBottom": 24,
            "paddingLeft": 24, "paddingRight": 24,
        },
        "children": [
            _text(headline, weight=700, size=20,
                  color="Background/bg-primary"),
            _text(subline, weight=500, size=13,
                  color="Background/bg-primary"),
        ],
    }


# ── Registry — name pattern → template fn ──────────────────────

ARCHETYPES: list[Tuple[re.Pattern, Callable[[dict], dict]]] = [
    (re.compile(r"^stage\s+card(?:\s+\d+)?$", re.I), stage_card_template),
    (re.compile(r"^product(?:\s+\d+)?$",       re.I), product_card_template),
    (re.compile(r"^stat\s+card(?:\s+\d+)?$",   re.I), stat_card_template),
    (re.compile(r"^list\s+item(?:\s+\d+)?$",   re.I), list_item_card_template),
    (re.compile(r"^hero\s+(?:card|banner)$",   re.I), hero_banner_template),
]


def resolve_archetype(node: dict) -> Optional[Callable[[dict], dict]]:
    """If node matches an archetype, return the template fn; else None."""
    if not isinstance(node, dict):
        return None
    # Explicit archetype override always wins
    explicit = node.get("archetype")
    if explicit:
        for pat, fn in ARCHETYPES:
            # try matching the explicit string against canonical names
            if pat.fullmatch(explicit) or pat.search(explicit):
                return fn
    name = node.get("name") or ""
    for pat, fn in ARCHETYPES:
        if pat.search(name):
            return fn
    return None
