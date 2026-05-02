#!/usr/bin/env python3
"""
Blueprint Sanitizer (S2.3)
==========================
batch_build_screen에 보내기 전 Blueprint를 안전하게 정규화.

참조 사양: docs/architecture/safe-build-spec.md

수정 항목 (우선순위 순):
  1. letterSpacing 객체/문자열 → raw number (object 포맷은 batch_build_screen 붕괴)
  2. hex 문자열 → {r,g,b,a} RGBA 변환
  3. 텍스트 width 누락 → textAutoResize 자동 주입
  4. 아이콘 이름 whitelist 매핑 (flame → fire-01 등)
  5. 금지 속성 제거

사용:
    from blueprint_sanitizer import sanitize_blueprint
    sanitized, warnings = sanitize_blueprint(blueprint)

CLI:
    python3 scripts/blueprint_sanitizer.py <input.json> [<output.json>]
"""
import json
import sys
import re
from typing import Any, List, Tuple, Dict


# ── 아이콘 이름 매핑 (DS whitelist 외 이름 → DS 이름) ──
ICON_ALIASES = {
    # 추측 이름 → DS v1 실제 이름
    'flame': 'fire-01',
    'fire': 'fire-01',
    'check': 'check-circle',
    'warning': 'alert-triangle',
    'warn': 'alert-triangle',
    'info': 'info-circle',
    'error': 'alert-circle',
    'star': 'star-01',
    'favorite': 'star-01',
    'like': 'heart',
    'send': 'send-01',
    'attach': 'paperclip',
    'link': 'link-01',
    'home': 'home-01',
    'user': 'user-01',
    'users': 'users-01',
    'search': 'search-lg',
    'settings': 'settings-01',
    'gift': 'gift-01',
    'shopping': 'shopping-bag-01',
    'cart': 'shopping-cart-01',
    'calendar': 'calendar',
    'clock': 'clock',
    'camera': 'camera-01',
    'edit': 'edit-01',
    'trash': 'trash-01',
    'delete': 'trash-01',
    'plus': 'plus',
    'minus': 'minus',
    'close': 'x-close',
    'x': 'x-close',
    'back': 'chevron-left',
    'forward': 'chevron-right',
}


def sanitize_blueprint(blueprint: dict, *, strict: bool = False) -> Tuple[dict, List[str]]:
    """Blueprint를 in-place 수정 없이 정규화.

    Args:
        blueprint: 원본 Blueprint dict
        strict: True면 경고도 raise. False(기본)면 best-effort 수정

    Returns:
        (sanitized_blueprint, warnings)
    """
    import copy
    bp = copy.deepcopy(blueprint)
    warnings: List[str] = []

    # 재귀 walk + 각 단계 수정
    _walk_and_sanitize(bp, warnings, path="root")

    if strict and warnings:
        raise ValueError(f"Sanitizer found {len(warnings)} issues:\n" + "\n".join(warnings))

    return bp, warnings


def _walk_and_sanitize(node: Any, warnings: List[str], path: str) -> None:
    """재귀 walk하며 각 단계 수정."""
    if isinstance(node, dict):
        _fix_letter_spacing(node, warnings, path)
        _fix_hex_colors(node, warnings, path)
        _fix_text_autoresize(node, warnings, path)
        _fix_icon_names(node, warnings, path)
        _remap_primitive_colors(node, warnings, path)
        _strip_transparent_placeholder_fill(node, warnings, path)

        for k, v in list(node.items()):
            if isinstance(v, (dict, list)):
                _walk_and_sanitize(v, warnings, f"{path}/{k}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk_and_sanitize(item, warnings, f"{path}[{i}]")


# _Primitives raw RGB (0-1) → DS Color modes semantic raw RGB.
# Per user policy 2026-05-01: blueprints must not reference _Primitives scale
# colors (Colors/Brand/300, Colors/Gray/700, etc.) — they have no semantic
# meaning and don't bind to design tokens. The sanitizer rewrites known
# primitive raws to the closest semantic equivalent at build time so every
# fill/stroke can be bound to a "1. Color modes" token.
#
# Keys are quantized 0-255 ints; values are (target_0_255, label).
_PRIMITIVE_TO_SEMANTIC_RGB = {
    # Brand purple — _Primitives Purple 2 → bg-brand / fg-brand / text-brand
    (89, 37, 220):   ((82, 0, 176),    "text-brand-secondary"),
    (105, 56, 239):  ((119, 0, 255),   "bg-brand-solid"),
    (122, 90, 248):  ((155, 85, 255),  "fg-brand-secondary"),
    (62, 28, 150):   ((52, 0, 120),    "bg-brand-section"),
    (235, 233, 254): ((244, 236, 255), "bg-brand-primary"),
    (217, 214, 254): ((230, 212, 255), "bg-brand-secondary"),
    (74, 31, 184):   ((82, 0, 176),    "bg-brand-section_subtle"),
    # Gray light-mode → fg/text semantics
    (24, 29, 39):    ((44, 55, 68),    "fg-primary"),
    (65, 70, 81):    ((44, 55, 68),    "fg-primary"),
    (83, 88, 98):    ((89, 96, 105),   "fg-secondary_hover"),
    (113, 118, 128): ((104, 112, 121), "fg-secondary"),
    # Error / Warning raws (some already match a semantic, kept for logging)
    (240, 68, 56):   ((217, 45, 32),   "bg-error-solid_hover"),
    (220, 104, 3):   ((220, 104, 3),   "fg-warning-primary"),
}


def _strip_transparent_placeholder_fill(node: dict, warnings: List[str], path: str) -> None:
    """`{r:0,g:0,b:0,a:0}` 같은 transparent placeholder fill을 제거.

    이런 fill은 blueprint가 "fill 없음"을 표현하려고 사용하지만, 빌드 후
    token-bind가 paint를 재생성하면서 alpha=1이 되어 까만 띠로 보이는 버그가
    반복적으로 발생함. 명확히 보이지 않게 두려면 fill 키 자체를 삭제한다.

    제거 조건: a==0 (완전 투명). 색상에 관계없이.
    """
    for key in ("fill", "stroke"):
        v = node.get(key)
        if not isinstance(v, dict):
            continue
        try:
            a = float(v.get("a", 1))
        except (TypeError, ValueError):
            continue
        if a == 0:
            del node[key]
            warnings.append(f"REMOVE {path}/{key}: transparent placeholder a=0")


def _remap_primitive_colors(node: dict, warnings: List[str], path: str) -> None:
    """fill/stroke RGB가 _Primitives 색이면 DS 시멘틱 raw로 자동 교체.

    blueprint의 fill 포맷은 {r,g,b,a} (0~1). 0-255로 양자화한 키로 매핑 테이블
    조회 → 매칭되면 시멘틱 raw로 덮어씀. 매칭 없는 raw는 그대로 둠 (이후
    post-fix step 9의 token-bind sweep에서 unmapped로 보고됨).
    """
    for key in ("fill", "stroke", "fontColor", "iconColor"):
        v = node.get(key)
        if not isinstance(v, dict):
            continue
        try:
            r = int(round(v.get("r", 0) * 255))
            g = int(round(v.get("g", 0) * 255))
            b = int(round(v.get("b", 0) * 255))
        except (TypeError, ValueError):
            continue
        rep = _PRIMITIVE_TO_SEMANTIC_RGB.get((r, g, b))
        if not rep:
            continue
        (nr, ng, nb), label = rep
        v["r"] = round(nr / 255, 3)
        v["g"] = round(ng / 255, 3)
        v["b"] = round(nb / 255, 3)
        warnings.append(
            f"REMAP {path}/{key}: ({r},{g},{b}) _Primitives → ({nr},{ng},{nb}) {label}"
        )


def _fix_letter_spacing(node: dict, warnings: List[str], path: str) -> None:
    """letterSpacing 객체/문자열 → raw number 변환 (§ 3.1 Blacklist)."""
    ls = node.get('letterSpacing')
    if ls is None or isinstance(ls, (int, float)):
        return

    if isinstance(ls, dict):
        value = ls.get('value')
        unit = ls.get('unit', '').upper()
        if unit == 'PERCENT' and isinstance(value, (int, float)):
            # -2% → -0.02
            node['letterSpacing'] = value / 100
            warnings.append(f"WARN {path}: letterSpacing {ls} → {value/100}")
        elif unit == 'PIXELS':
            # raw pixel은 의도 불명 — 제거가 안전
            del node['letterSpacing']
            warnings.append(f"WARN {path}: letterSpacing {{value:{value}, unit:PIXELS}} 제거 (의도 불명)")
        else:
            del node['letterSpacing']
            warnings.append(f"WARN {path}: letterSpacing 포맷 unknown — 제거: {ls}")
    elif isinstance(ls, str):
        m = re.match(r'(-?[\d.]+)%', ls.strip())
        if m:
            node['letterSpacing'] = float(m.group(1)) / 100
            warnings.append(f"WARN {path}: letterSpacing '{ls}' → {float(m.group(1))/100}")
        else:
            del node['letterSpacing']
            warnings.append(f"WARN {path}: letterSpacing '{ls}' 파싱 불가 — 제거")


def _fix_hex_colors(node: dict, warnings: List[str], path: str) -> None:
    """hex 문자열 → {r,g,b,a} RGBA 변환 (fill, stroke, fontColor, iconColor)."""
    for key in ('fill', 'stroke', 'fontColor', 'iconColor'):
        v = node.get(key)
        if isinstance(v, str) and v.startswith('#'):
            rgba = _hex_to_rgba(v)
            if rgba:
                node[key] = rgba
                warnings.append(f"WARN {path}: {key}='{v}' → {rgba}")


def _fix_text_autoresize(node: dict, warnings: List[str], path: str) -> None:
    """text 노드에 width/textAutoResize 모두 없으면 WIDTH_AND_HEIGHT 자동 주입."""
    if node.get('type') != 'text':
        return
    if node.get('textAutoResize') or node.get('width') is not None:
        return
    if node.get('layoutSizingHorizontal') in ('FILL', 'FIXED'):
        return  # FILL이면 textAutoResize 불필요
    node['textAutoResize'] = 'WIDTH_AND_HEIGHT'
    warnings.append(f"WARN {path}: text 노드 width 누락 → textAutoResize='WIDTH_AND_HEIGHT' 주입")


def _fix_icon_names(node: dict, warnings: List[str], path: str) -> None:
    """iconName이 DS whitelist 밖 → 유사 이름 매핑."""
    if node.get('type') != 'icon':
        return
    name = node.get('iconName')
    if not name or not isinstance(name, str):
        return
    lower = name.lower().strip()
    if lower in ICON_ALIASES:
        mapped = ICON_ALIASES[lower]
        if mapped != name:
            node['iconName'] = mapped
            warnings.append(f"WARN {path}: iconName '{name}' → '{mapped}' (DS alias)")


def _hex_to_rgba(hex_str: str) -> Dict[str, float]:
    """#rrggbb[aa] → {r,g,b,a} 0~1 범위."""
    h = hex_str.lstrip('#')
    try:
        if len(h) == 6:
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            a = 255
        elif len(h) == 8:
            r, g, b, a = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)
        else:
            return None
        return {
            'r': round(r / 255, 3),
            'g': round(g / 255, 3),
            'b': round(b / 255, 3),
            'a': round(a / 255, 3),
        }
    except ValueError:
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 blueprint_sanitizer.py <input.json> [<output.json>]")
        sys.exit(1)

    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else inp.replace('.json', '_sanitized.json')

    with open(inp) as f:
        bp = json.load(f)

    sanitized, warnings = sanitize_blueprint(bp)

    with open(out, 'w') as f:
        json.dump(sanitized, f, indent=2, ensure_ascii=False)

    print(f"✅ Sanitized: {out}")
    print(f"   Warnings: {len(warnings)}")
    for w in warnings[:10]:
        print(f"   - {w}")
    if len(warnings) > 10:
        print(f"   ... and {len(warnings) - 10} more")


if __name__ == '__main__':
    main()
