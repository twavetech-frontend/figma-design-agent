#!/usr/bin/env python3
"""
Figma MCP HTTP Client — 디자인 생성, 수정, 바인딩을 위한 Python 클라이언트

Usage:
    # 0. 환경 진단 (준비 상태 통합 체크 — 브리지/세션/플러그인/DS맵/통독 게이트)
    python3 scripts/figma_mcp_client.py doctor [--json]

    # 0-b. DS 컴포넌트 가이드 조회 / 검색 / CLI 자기서술
    python3 scripts/figma_mcp_client.py component "Tab bar" [--full] [--json]
    python3 scripts/figma_mcp_client.py component --list
    python3 scripts/figma_mcp_client.py search "탭" [--json]
    python3 scripts/figma_mcp_client.py manifest [--json]

    # 1. 세션 초기화 (필수 — 첫 실행 시)
    python3 scripts/figma_mcp_client.py init

    # 2. 단일 도구 호출
    python3 scripts/figma_mcp_client.py call get_selection '{}'
    python3 scripts/figma_mcp_client.py call get_node_info '{"nodeId":"51:33050"}'

    # 3. batch_build_screen (디자인 생성)
    python3 scripts/figma_mcp_client.py build blueprint.json

    # 4. DS 변수 바인딩
    python3 scripts/figma_mcp_client.py bind bindings.json

    # 5. 인터랙티브 모드
    python3 scripts/figma_mcp_client.py interactive
"""

import json
import sys
import os
import time
import re
import requests
from typing import Any, Optional, List, Dict

# Unified Content Model (Refactor A — 2026-05-28)
# archetype spec + wire_content → blueprint 단일 경로
_scripts_dir_for_unified = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir_for_unified not in sys.path:
    sys.path.insert(0, _scripts_dir_for_unified)

# 안정적 기계 판독 에러 코드 (Astryx 패턴, 2026-07-08) — BUILD-SUMMARY-JSON 의 code 필드.
# 에이전트는 사람용 prose 가 아니라 이 코드로 분기한다 (append-only 계약, error_codes.py).
from error_codes import codes_for_issues as _codes_for_issues  # noqa: E402
try:
    from unified_blueprint import (  # type: ignore
        build_unified_blueprint as _unified_build,
        load_archetype_spec as _unified_load_spec,
    )
    _UNIFIED_AVAILABLE = True
except Exception as _e:
    _UNIFIED_AVAILABLE = False
    print(f"[unified] import 실패 — legacy mode only: {_e}")

# 127.0.0.1 사용 — localhost는 Windows에서 IPv6(::1) 우선 해석 후 IPv4 폴백이라 호출마다 지연
MCP_URL = "http://127.0.0.1:8769/mcp"
# HTTP keep-alive — MCP 호출마다 새 TCP 연결을 열지 않도록 세션 재사용
# (post-fix는 수백 회 호출 → Windows 연결 생성/해제 오버헤드 누적 방지)
_http = requests.Session()
SESSION_FILE = os.path.join(os.path.dirname(__file__), ".mcp_session")
TOKEN_MAP_FILE = os.path.join(os.path.dirname(__file__), "..", "ds", "TOKEN_MAP.json")
# figmaPath → DS variable key. Lets set_bound_variables import by key
# (importVariableByKeyAsync) instead of relying on figma.teamLibrary discovery,
# which returns nothing when the file lives in a personal Draft. Mirrors the
# TEXT_STYLE_MAP.json key-import path. Populated by `sync-variable-keys`.
VARIABLE_KEY_MAP_FILE = os.path.join(os.path.dirname(__file__), "..", "ds", "VARIABLE_KEY_MAP.json")

# Cached token map (loaded once per process)
_token_map: Optional[Dict[str, dict]] = None
_variable_key_map: Optional[Dict[str, str]] = None


def _load_variable_key_map() -> Dict[str, str]:
    """Load ds/VARIABLE_KEY_MAP.json → {figmaPath: variableKey}. {} if absent."""
    global _variable_key_map
    if _variable_key_map is not None:
        return _variable_key_map
    _variable_key_map = {}
    try:
        path = os.path.normpath(VARIABLE_KEY_MAP_FILE)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _variable_key_map = {str(k): str(v) for k, v in data.items() if v}
    except Exception as e:
        print(f"  [var-key] VARIABLE_KEY_MAP.json 로드 실패 (이름 바인딩으로 진행): {e}")
        _variable_key_map = {}
    return _variable_key_map


def _binding_value(figma_path: Optional[str]) -> Optional[str]:
    """figmaPath → 바인딩 값. key 맵에 키가 있으면 'K:{key}'(직접 import, Draft 안전),
    없으면 figmaPath 그대로(팀 라이브러리 이름 검색). figma_path 없으면 None."""
    if not figma_path:
        return figma_path
    key = _load_variable_key_map().get(figma_path)
    return f"K:{key}" if key else figma_path


# 🎨 DS Badge `Color` prop 의 13개 유효 옵션 (2026-06-01 사용자 명시, 절대 규칙 0-K).
BADGE_COLOR_PROP_OPTIONS = (
    "Gray", "Brand", "Error", "Warning", "Success", "Blue light", "Blue",
    "Indigo", "Purple", "Pink", "Orange", "Blue gray", "Gray blue",
)


def set_badge_color(node_id: str, color: str) -> bool:
    """Badge 인스턴스 색을 'Color' prop 으로 변경 (fill/stroke 직접 변경 금지 — 절대 규칙 0-K).

    color 는 BADGE_COLOR_PROP_OPTIONS 의 13개 중 하나. set_instance_properties 로
    variant 만 바꾼다 → master 가 fill·stroke·label 색을 일관되게 제어한다.
    """
    if color not in BADGE_COLOR_PROP_OPTIONS:
        # 대소문자/공백 보정 시도
        match = next((o for o in BADGE_COLOR_PROP_OPTIONS if o.lower() == str(color).strip().lower()), None)
        if not match:
            print(f"❌ set_badge_color: '{color}' 는 유효한 Badge Color 옵션이 아님. "
                  f"가능: {', '.join(BADGE_COLOR_PROP_OPTIONS)}")
            return False
        color = match
    try:
        call_tool("set_instance_properties", {"nodeId": node_id, "properties": {"Color": color}})
        print(f"  [badge-color] {node_id} → Color={color}")
        return True
    except Exception as e:
        print(f"  [badge-color] {node_id} 실패: {e}")
        return False


def load_token_map() -> Dict[str, dict]:
    """Load TOKEN_MAP.json and build a lookup by figmaPath."""
    global _token_map
    if _token_map is not None:
        return _token_map

    token_map_path = os.path.normpath(TOKEN_MAP_FILE)
    if not os.path.exists(token_map_path):
        print(f"WARNING: TOKEN_MAP.json not found at {token_map_path}. Token references won't be resolved.")
        _token_map = {}
        return _token_map

    with open(token_map_path) as f:
        raw = json.load(f)

    # Build lookup: figmaPath → {value, type}
    # e.g. "Colors/Background/bg-brand-solid" → {"value": "#1570ef", "type": "COLOR"}
    _token_map = {}
    for css_var, info in raw.items():
        figma_path = info.get("figmaPath", "")
        if figma_path:
            _token_map[figma_path] = info
            # Also index by the last segment for convenience
            # e.g. "bg-brand-solid" → same info
            short_name = figma_path.rsplit("/", 1)[-1] if "/" in figma_path else figma_path
            if short_name not in _token_map:
                _token_map[short_name] = info
    return _token_map


def hex_to_rgba(hex_color: str) -> Dict[str, float]:
    """Convert hex color (#RRGGBB or #RRGGBBAA) to Figma RGBA dict (0-1 range)."""
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        a = 255
    elif len(h) == 8:
        r, g, b, a = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)
    else:
        return {"r": 0, "g": 0, "b": 0, "a": 1}
    return {"r": round(r / 255, 3), "g": round(g / 255, 3), "b": round(b / 255, 3), "a": round(a / 255, 3)}


def _strip_alt_token(token_name: str) -> str:
    """⚠️ 시스템 규칙: '-alt' / '_alt' 변형 토큰 금지 — 기본 토큰명으로 정규화.

    예) bg-secondary-alt / bg-secondary_alt → bg-secondary
    """
    for suffix in ("-alt", "_alt", " alt"):
        if token_name.endswith(suffix):
            base = token_name[: -len(suffix)]
            print(f"[규칙] '-alt' 토큰 금지 — '{token_name}' → '{base}' 로 교정")
            return base
    return token_name


_AQUA_STEP_RE = re.compile(r"(\d{2,3})\s*$")


def _normalize_aqua_token(token_name: str) -> Optional[str]:
    """Aqua 보조 액센트 토큰 → primitive 'Colors/Aqua/{N}' 로 정규화 (2026-06-02 룰).

    DS 의 semantic Aqua(`Component colors/Utility/Aqua/utility-blue-{N}`)는 GitHub
    토큰 export 에 아직 없고, 그 last-segment `utility-blue-{N}` 는 **Utility/Blue**
    와 충돌(같은 이름 → 파랑으로 오매칭)한다. 그래서 'aqua' 가 명시된 참조는 값이
    동일한 primitive `Colors/Aqua/{N}`(TOKEN_MAP + VARIABLE_KEY_MAP 에 존재)로 보낸다.

    매칭 (대소문자 무시, 'aqua' 가 들어있을 때만 — Blue 오염 방지):
      Component colors/Utility/Aqua/utility-blue-300  → Colors/Aqua/300
      utility-aqua-300 · aqua-300 · Aqua/300          → Colors/Aqua/300
    이미 'Colors/Aqua/...' 면 그대로 둔다(호출부 exact-match 가 처리).
    """
    if not token_name:
        return None
    low = token_name.lower()
    if low.startswith("colors/aqua/"):
        return None  # 이미 정식 primitive 경로
    if "aqua" not in low:
        return None  # aqua 명시 없으면 손대지 않음 (utility-blue=파랑 보존)
    m = _AQUA_STEP_RE.search(token_name)
    if not m:
        return None
    return f"Colors/Aqua/{m.group(1)}"


def _aqua_binding_path(token_name: str) -> Optional[str]:
    """Aqua 토큰 → **변수 바인딩용 figmaPath** (semantic 우선).

    바인딩은 색 해석과 다르다: semantic `Component colors/Utility/Aqua/utility-aqua-{N}`
    가 VARIABLE_KEY_MAP 에 있으면 그 경로를 쓴다(게시된 키 → importVariableByKeyAsync
    성공). primitive `Colors/Aqua/{N}` 키는 _Primitives 컬렉션이라 미게시 → import 실패하므로
    fallback 일 뿐. (2026-06-02 — sync-variable-keys 로 두 키 모두 추출됨.)
    """
    prim = _normalize_aqua_token(token_name)  # "Colors/Aqua/{N}" or None
    if not prim:
        return None
    n = prim.rsplit("/", 1)[-1]
    vk = _load_variable_key_map()
    semantic = f"Component colors/Utility/Aqua/utility-aqua-{n}"
    if vk.get(semantic):
        return semantic
    if vk.get(prim):
        return prim
    return semantic  # best-effort (central handler falls back to name search)


def resolve_token_ref(value: str) -> Optional[Dict[str, float]]:
    """Resolve a $token(name) reference to RGBA.

    Supported formats:
        "$token(bg-brand-solid)"
        "$token(Colors/Background/bg-brand-solid)"
        "$token(fg-brand-primary)" — matches "fg-brand-primary (600)" etc.

    ⚠️ 시스템 규칙:
    - '-alt' / '_alt' 변형 토큰은 기본 토큰으로 강제 정규화한다.
    - 마지막 세그먼트 '정확 일치'를 최우선으로 매칭한다 — 그렇지 않으면
      "bg-secondary" 가 "bg-secondary_alt" 로 오매칭된다.
    """
    if not isinstance(value, str) or not value.startswith("$token("):
        return None
    token_name = _strip_alt_token(value[7:-1])  # strip "$token(" and ")" + reject -alt
    token_map = load_token_map()

    def _lookup(name: str) -> Optional[Dict[str, float]]:
        # Exact match (map key)
        info = token_map.get(name)
        if info and info.get("type") == "COLOR":
            return hex_to_rgba(info["value"])
        # Pass 1: figmaPath 마지막 세그먼트 '정확 일치' 우선 (_alt 오매칭 방지)
        for path, info_item in token_map.items():
            if info_item.get("type") != "COLOR":
                continue
            figma_path = info_item.get("figmaPath", path)
            last_segment = figma_path.rsplit("/", 1)[-1] if "/" in figma_path else figma_path
            if last_segment == name:
                return hex_to_rgba(info_item["value"])
        # Pass 2: 괄호 변형 매칭만 허용 ("fg-brand-primary" → "fg-brand-primary (600)")
        # ※ '_' prefix 매칭 절대 금지 — bg-secondary 가 bg-secondary_alt 로 오매칭됨
        for path, info_item in token_map.items():
            if info_item.get("type") != "COLOR":
                continue
            figma_path = info_item.get("figmaPath", path)
            last_segment = figma_path.rsplit("/", 1)[-1] if "/" in figma_path else figma_path
            if last_segment.startswith(name + " "):
                return hex_to_rgba(info_item["value"])
        return None

    # 정식 토큰명 우선 — 토큰 export 에 utility-aqua 가 들어오면 그대로 해석된다.
    hit = _lookup(token_name)
    if hit is not None:
        return hit
    # Aqua 보조 액센트 폴백 — semantic utility-aqua 가 아직 export 에 없을 때 primitive Colors/Aqua/{N}
    alias = _normalize_aqua_token(token_name)
    if alias and alias != token_name:
        hit = _lookup(alias)
        if hit is not None:
            return hit

    print(f"WARNING: Token '{token_name}' not found in TOKEN_MAP.json")
    return None


def _flatten_padding_objects(node: Any) -> Any:
    """Recursively convert padding objects to individual paddingTop/Bottom/Left/Right.

    autoLayout.padding = {top:12, bottom:12, left:20, right:20}
    → autoLayout.paddingTop=12, paddingBottom=12, paddingLeft=20, paddingRight=20
    """
    if isinstance(node, dict):
        result = {}
        for k, v in node.items():
            if k == "autoLayout" and isinstance(v, dict) and "padding" in v and isinstance(v["padding"], dict):
                v = dict(v)  # shallow copy
                p = v.pop("padding")
                if "top" in p: v["paddingTop"] = p["top"]
                if "bottom" in p: v["paddingBottom"] = p["bottom"]
                if "left" in p: v["paddingLeft"] = p["left"]
                if "right" in p: v["paddingRight"] = p["right"]
            result[k] = _flatten_padding_objects(v)
        return result
    elif isinstance(node, list):
        return [_flatten_padding_objects(item) for item in node]
    return node


def validate_blueprint(blueprint: dict) -> list:
    """Validate blueprint JSON before building. Returns list of error/warning strings."""
    issues = []

    def _check_node(node: dict, path: str = "root"):
        if not isinstance(node, dict):
            return  # non-dict (int 등) 노드 방어 — generator artifact
        # Check autoLayout
        al = node.get("autoLayout")
        if al:
            mode = al.get("layoutMode") or al.get("direction")
            if mode and mode not in ("HORIZONTAL", "VERTICAL"):
                issues.append(f"ERROR {path}: invalid layoutMode/direction '{mode}' (must be HORIZONTAL or VERTICAL)")

            # Check padding is not an object (should be flat)
            if "padding" in al and isinstance(al["padding"], dict):
                issues.append(f"WARN {path}: padding is an object — will be auto-flattened, but prefer paddingTop/Bottom/Left/Right")

            # Check SPACE_BETWEEN + FILL conflict
            if al.get("primaryAxisAlignItems") == "SPACE_BETWEEN":
                for child in node.get("children", []):
                    child_al = child.get("autoLayout", {})
                    if child.get("layoutSizingHorizontal") == "FILL" or child_al.get("layoutSizingHorizontal") == "FILL":
                        issues.append(f"WARN {path} → {child.get('name','?')}: SPACE_BETWEEN parent + FILL child = 0px spacing")

        # Check fill/fontColor is not raw hex string
        for color_key in ("fill", "fontColor", "iconColor", "stroke"):
            val = node.get(color_key)
            if isinstance(val, str) and val.startswith("#"):
                issues.append(f"ERROR {path}: {color_key}='{val}' is hex string — use $token() or {{r,g,b,a}} object")

        # Check font for Korean text
        text = node.get("text") or node.get("characters")
        if text and any('\uac00' <= ch <= '\ud7a3' for ch in str(text)):
            font = node.get("fontFamily") or node.get("fontName", {}).get("family", "")
            if font and font not in ("Pretendard", ""):
                issues.append(f"WARN {path}: Korean text with font '{font}' — should use Pretendard")

        # R1: FRAME children of root/sections must be FILL (not HUG)
        node_type = node.get("type", "frame")
        is_frame = node_type in ("frame", "FRAME")
        parent_has_layout = bool(node.get("autoLayout"))

        if is_frame and path != "root":
            sizing_h = node.get("layoutSizingHorizontal", "")
            # Frames inside auto-layout parents should be FILL
            if sizing_h == "HUG" or (sizing_h == "" and parent_has_layout):
                node_name = node.get("name", "?")
                # Skip small frames (icons, tags, chips, indicators, dots)
                w = node.get("width", 999)
                skip_keywords = ("Tag", "Chip", "Badge", "Dot", "Icon", "Indicator", "Nav Right", "DI1 Left", "DI2 Left", "DI3 Left")
                _validate_skip_re = re.compile(
                    r'\b(?:' + '|'.join(re.escape(kw.lower()) for kw in skip_keywords) + r')\b'
                )
                is_small = w <= 60
                is_skip = bool(_validate_skip_re.search(node_name.lower()))
                # Only warn for section/card-level frames and their direct children
                depth = path.count("/")
                if not is_small and not is_skip and depth <= 3:
                    issues.append(f"WARN {path}: FRAME '{node_name}' has layoutSizingHorizontal='{sizing_h or 'unset'}' — should be FILL")

        # R2: Tab Bar and FAB must have ABSOLUTE positioning note
        node_name = node.get("name", "")
        if "Tab Bar" in node_name or "FAB" in node_name:
            pos = node.get("layoutPositioning", "")
            if pos != "ABSOLUTE":
                issues.append(f"WARN {path}: '{node_name}' needs layoutPositioning='ABSOLUTE' (batch_build_screen won't apply it — must be set in post-processing)")

        # R3: Hero/Banner section should have HORIZONTAL carousel wrapper
        if ("Banner" in node_name or "Hero" in node_name or "Carousel" in node_name):
            children = node.get("children", [])
            banner_children = [c for c in children if "Banner" in c.get("name", "") and c.get("type", "frame") in ("frame", "FRAME")]
            if len(banner_children) >= 2:
                layout_mode = (node.get("autoLayout", {}).get("layoutMode", "") or
                               node.get("autoLayout", {}).get("direction", ""))
                clips = node.get("clipsContent", False)
                if layout_mode != "HORIZONTAL":
                    issues.append(f"WARN {path}: Carousel '{node_name}' has {len(banner_children)} banners but layoutMode='{layout_mode}' — should be HORIZONTAL")
                if not clips:
                    issues.append(f"WARN {path}: Carousel '{node_name}' needs clipsContent=true to show only first banner")

        # R4: FAB with text should be pill-shaped (width >= 100)
        if "FAB" in node_name:
            w = node.get("width", 0)
            children = node.get("children", [])
            has_text = any(c.get("type") in ("text", "TEXT") for c in children)
            if has_text and w < 100:
                issues.append(f"WARN {path}: FAB has text but width={w} — use pill shape (width >= 100)")

        # R5: CTA/Button frames with text children must have vertical padding
        # Without padding, HUG sizing collapses height to text-only (~20px instead of ~52px)
        cta_keywords = ("CTA Button", "CTA", "Button")
        if is_frame and al and any(kw.lower() in node_name.lower() for kw in cta_keywords):
            children = node.get("children", [])
            has_text = any(c.get("type") in ("text", "TEXT") for c in children)
            pt = al.get("paddingTop", 0)
            pb = al.get("paddingBottom", 0)
            if has_text and pt == 0 and pb == 0:
                issues.append(f"WARN {path}: CTA/Button '{node_name}' has no vertical padding in autoLayout — add paddingTop/Bottom (e.g. 16) for proper height")

        # Check children
        for i, child in enumerate(node.get("children", [])):
            if not isinstance(child, dict):
                continue  # non-dict (int 등) 잘못된 노드 — skip (sanitize 가 제거하지만 방어)
            child_name = child.get("name", f"child[{i}]")
            _check_node(child, f"{path}/{child_name}")

    _check_node(blueprint)
    return issues


_resolved_color_log: List[Dict[str, str]] = []

def resolve_tokens_in_blueprint(node: Any, _parent_key: str = "", _node_name: str = "") -> Any:
    """Recursively resolve all $token() references in a blueprint JSON."""
    global _resolved_color_log
    if isinstance(node, str):
        resolved = resolve_token_ref(node)
        if resolved is not None:
            # Log color tokens used in fill/color fields for verification
            color_fields = ("fill", "fontColor", "iconColor", "stroke")
            if _parent_key in color_fields:
                token_name = node[7:-1]
                token_map = load_token_map()
                info = token_map.get(token_name)
                hex_val = info["value"] if info else "?"
                if not info:
                    for path, info_item in token_map.items():
                        fp = info_item.get("figmaPath", path)
                        seg = fp.rsplit("/", 1)[-1] if "/" in fp else fp
                        if seg == token_name or seg.startswith(token_name + " ") or seg.startswith(token_name + "_"):
                            hex_val = info_item["value"]
                            break
                _resolved_color_log.append({
                    "token": token_name, "hex": hex_val,
                    "field": _parent_key, "node": _node_name
                })
            return resolved
        return node
    elif isinstance(node, dict):
        result = {}
        name = node.get("name", _node_name)
        for k, v in node.items():
            resolved = resolve_tokens_in_blueprint(v, _parent_key=k, _node_name=name)
            result[k] = resolved
        return result
    elif isinstance(node, list):
        return [resolve_tokens_in_blueprint(item, _parent_key=_parent_key, _node_name=_node_name) for item in node]
    return node


def print_resolved_color_summary():
    """Print a summary of resolved color tokens for visual verification."""
    global _resolved_color_log
    if not _resolved_color_log:
        return
    # Deduplicate by token name + field
    seen = set()
    unique = []
    for entry in _resolved_color_log:
        key = (entry["token"], entry["field"])
        if key not in seen:
            seen.add(key)
            unique.append(entry)

    print(f"\n  🎨 사용된 색상 토큰 ({len(unique)}개) — 의도한 색상이 맞는지 확인하세요:")
    for e in unique:
        print(f"     {e['field']:12} {e['token']:30} → {e['hex']}")
    print()
    _resolved_color_log = []


def _count_token_refs(node: Any) -> int:
    """Count $token() references in a JSON structure."""
    if isinstance(node, str):
        return 1 if node.startswith("$token(") else 0
    elif isinstance(node, dict):
        return sum(_count_token_refs(v) for v in node.values())
    elif isinstance(node, list):
        return sum(_count_token_refs(item) for item in node)
    return 0


def get_session_id() -> Optional[str]:
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE) as f:
            return f.read().strip()
    return None


def save_session_id(sid: str):
    with open(SESSION_FILE, "w") as f:
        f.write(sid)


def mcp_request(method: str, params: Optional[dict] = None, msg_id: int = 1) -> dict:
    """Send a JSON-RPC request to the MCP HTTP endpoint."""
    payload = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params:
        payload["params"] = params

    headers = {"Content-Type": "application/json"}
    sid = get_session_id()
    if sid:
        headers["mcp-session-id"] = sid

    resp = _http.post(MCP_URL, json=payload, headers=headers, timeout=300)

    # Save session ID from response
    new_sid = resp.headers.get("mcp-session-id")
    if new_sid:
        save_session_id(new_sid)

    return resp.json()


def init_session() -> str:
    """Initialize MCP session."""
    result = mcp_request("initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "figma-py-client", "version": "1.0"}
    })
    sid = get_session_id()
    print(f"Session initialized: {sid}")

    # Send initialized notification
    payload = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    headers = {"Content-Type": "application/json"}
    if sid:
        headers["mcp-session-id"] = sid
    _http.post(MCP_URL, json=payload, headers=headers, timeout=10)

    return sid


# ── call_tool 타이밍 계측 (2026-07-13 — post-fix 471s 회귀 진단용) ──────────────
# 도구별 (호출수, 누적초) 를 기록하고, 임계 초과 단건은 즉시 [slow-call] 로 프린트.
# cmd_post_fix / cmd_build 끝에서 _print_call_stats() 로 상위 오프렌더 출력.
_CALL_STATS: Dict[str, list] = {}
_SLOW_CALL_SEC = float(os.environ.get("IMIN_SLOW_CALL_SEC", "3"))


def _record_call_stat(name: str, secs: float, args: dict) -> None:
    st = _CALL_STATS.setdefault(name, [0, 0.0])
    st[0] += 1
    st[1] += secs
    if secs >= _SLOW_CALL_SEC:
        nid = args.get("nodeId") or args.get("nodeIds") or ""
        print(f"  [slow-call] {name} {secs:.1f}s" + (f" nodeId={nid}" if nid else ""))


def _print_call_stats(label: str = "") -> None:
    """도구별 누적 시간 상위 8개 출력 후 리셋 — 어디서 시간이 새는지 로그로 남김."""
    if not _CALL_STATS:
        return
    total_n = sum(v[0] for v in _CALL_STATS.values())
    total_s = sum(v[1] for v in _CALL_STATS.values())
    top = sorted(_CALL_STATS.items(), key=lambda kv: -kv[1][1])[:8]
    print(f"\n  [call-stats{(' ' + label) if label else ''}] "
          f"MCP 호출 {total_n}건 / {total_s:.1f}s — 상위:")
    for nm, (n, s) in top:
        print(f"    {nm:32s} {n:4d}건  {s:7.1f}s  (평균 {s / max(n, 1):.2f}s)")
    _CALL_STATS.clear()


def call_tool(name: str, args: dict, msg_id: int = 1) -> List[dict]:
    """Call an MCP tool and return content array."""
    # 방어: set_image_fill에 url 파라미터 사용 차단
    if name == "set_image_fill" and "url" in args:
        raise ValueError(
            "set_image_fill does NOT support 'url'. "
            "Use 'imageData' (base64-encoded PNG/JPEG). "
            "Read the file with open(path,'rb') and base64.b64encode()."
        )
    # 🔴 절대 규칙 (2026-06-01 사용자 명시): "모든 component 의 fill·stroke·label color
    # 를 절대 변경하지 말 것." DS 컴포넌트 인스턴스 내부 노드(id 에 ';' = I{id};{sub})의
    # 색은 master/variant 가 제어한다 — 일반 바인딩/보정이 절대 덮으면 안 된다(badge fill·
    # stroke·label 색 변경 금지). 의도적 enforcer(FAB 아이콘 fg-light 등)만 args 에
    # _allowComponentColor=True 를 넣어 예외. 이 중앙 가드로 새 세션에서도 재발 차단.
    _allow_comp_color = bool(args.get("_allowComponentColor"))
    if "_allowComponentColor" in args:
        args = {k: v for k, v in args.items() if k != "_allowComponentColor"}
    if not _allow_comp_color:
        nid = args.get("nodeId")
        is_internal = isinstance(nid, str) and ";" in nid  # 인스턴스 내부 노드
        if is_internal and name in ("set_fill_color", "set_stroke_color"):
            return [{"type": "text", "text": json.dumps(
                {"skipped": "component-internal color write blocked (절대 규칙)",
                 "nodeId": nid}, ensure_ascii=False)}]
        if is_internal and name == "set_bound_variables" and isinstance(args.get("bindings"), dict):
            kept = {k: v for k, v in args["bindings"].items()
                    if not (str(k).startswith("fills/") or str(k).startswith("strokes/"))}
            if not kept:
                return [{"type": "text", "text": json.dumps(
                    {"skipped": "component-internal color binding blocked (절대 규칙)",
                     "nodeId": nid}, ensure_ascii=False)}]
            args = {**args, "bindings": kept}
    # 중앙 처리: 모든 변수 바인딩 값을 가능하면 'K:{key}'(직접 import, Draft 안전)로 변환.
    # VARIABLE_KEY_MAP 에 키가 없으면 figmaPath 이름 그대로(팀 라이브러리 검색) 유지.
    # 모든 set_bound_variables 호출부(색·타이포·spacing·border 등)를 한 곳에서 커버.
    if name == "set_bound_variables" and isinstance(args.get("bindings"), dict):
        args = {**args, "bindings": {
            k: (_binding_value(v) if isinstance(v, str) else v)
            for k, v in args["bindings"].items()}}
    _t0 = time.time()
    result = mcp_request("tools/call", {
        "name": name,
        "arguments": args
    }, msg_id)
    _record_call_stat(name, time.time() - _t0, args)

    if "error" in result:
        raise Exception(f"MCP error: {result['error']}")

    content = result.get("result", {}).get("content", [])
    return content


def _try_extract_json(text: str):
    """텍스트에서 JSON 객체/배열을 추출. 전체 파싱 → 줄 단위 → 중괄호 추출 순서로 시도."""
    # 1) 전체 문자열이 JSON인 경우
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # 2) 줄 단위로 JSON 시도 (MCP 응답: "한글 설명\n{JSON}" 형태)
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('{') or line.startswith('['):
            try:
                return json.loads(line)
            except (json.JSONDecodeError, TypeError):
                pass

    # 3) 텍스트 내 첫 번째 { ... } 블록 추출
    start = text.find('{')
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i+1])
                    except (json.JSONDecodeError, TypeError):
                        break
    return None


def parse_content(content: List[dict]) -> dict:
    """Parse MCP response content — handles text, image, and mixed types."""
    texts = []
    images = []
    parsed_json = None

    for item in content:
        ctype = item.get("type", "text")
        if ctype == "text":
            text = item.get("text", "")
            texts.append(text)
            # Try to extract JSON from text
            result = _try_extract_json(text)
            if result is not None:
                parsed_json = result
        elif ctype == "image":
            images.append({
                "mimeType": item.get("mimeType", "image/png"),
                "data_length": len(item.get("data", "")),
            })

    return {
        "texts": texts,
        "images": images,
        "json": parsed_json,
        "raw": content,
    }


def export_image(node_id: str, path: str, fmt: str = "PNG", scale: float = 1.5) -> str:
    """export_node_as_image → 파일 저장 원스텝 (2026-08-24 신설).

    ⚠️ parse_content 는 image 페이로드를 data_length 로 치환한다 — 이미지가 필요하면
    이 헬퍼를 쓰거나 raw content 의 type=='image' 항목에서 data 를 직접 꺼낼 것.
    (이 사양을 몰라 8장 export 를 3회 왕복한 실측 낭비가 신설 사유. QA 렌더 대조는
    전부 이 함수로: fc.export_image('123:45', 'scripts/qa_screenshots/gen1.png'))"""
    import base64
    content = call_tool("export_node_as_image",
                        {"nodeId": node_id, "format": fmt, "scale": scale})
    b64 = next((it.get("data") for it in content
                if isinstance(it, dict) and it.get("type") == "image" and it.get("data")), None)
    if not b64:
        texts = [it.get("text") for it in content
                 if isinstance(it, dict) and it.get("type") == "text"]
        raise RuntimeError(f"export_node_as_image 이미지 없음 (node {node_id}): {texts[:1]}")
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64))
    return path


def _ensure_bridge_server():
    """Bridge 서버가 안 떠있으면 자동으로 시작한다."""
    import subprocess
    try:
        requests.get("http://127.0.0.1:8769/mcp", timeout=1)
        return  # 이미 떠있음
    except Exception:
        pass

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bridge_js = os.path.join(project_root, "out", "bridge", "index.js")
    if not os.path.exists(bridge_js):
        # 빌드 안 돼있으면 빌드 먼저
        print("[BRIDGE] out/bridge/index.js 없음 — npm run build:main 실행 중...")
        subprocess.run(["npm", "run", "build:main"], cwd=project_root,
                       capture_output=True, timeout=30)

    if not os.path.exists(bridge_js):
        print("[BRIDGE] 빌드 실패 — Bridge 서버를 수동으로 시작해 주세요: npm run bridge")
        return

    print("[BRIDGE] Bridge 서버 자동 시작 중...")
    log_file = open("/tmp/bridge-server.log", "w")
    subprocess.Popen(
        ["node", bridge_js],
        stdout=log_file, stderr=log_file,
        cwd=project_root,
        start_new_session=True  # 부모 프로세스 종료 시에도 유지
    )

    # 서버 준비 대기 (최대 5초)
    for i in range(10):
        time.sleep(0.5)
        try:
            requests.get("http://127.0.0.1:8769/mcp", timeout=1)
            print(f"[BRIDGE] 서버 준비 완료 ({(i+1)*0.5:.1f}s)")
            return
        except Exception:
            pass

    print("[BRIDGE] 서버 시작 대기 초과 — 로그 확인: cat /tmp/bridge-server.log")


def ensure_session():
    """Ensure we have a valid session, init if needed."""
    _ensure_bridge_server()
    sid = get_session_id()
    if not sid:
        print("No session found, initializing...")
        init_session()
    else:
        # Test session validity
        try:
            call_tool("get_selection", {})
        except Exception:
            print("Session expired, re-initializing...")
            init_session()


# ─── High-level commands ───


def cmd_init():
    _ensure_bridge_server()
    init_session()
    print("Ready.")


def _notify_plugin(event: str, **data) -> None:
    """플러그인 UI 에 one-way progress 알림 전송 (실패 무시). MCP 도구 notify_plugin 사용."""
    try:
        call_tool("notify_plugin", {"event": event, "data": data})
    except Exception:
        pass  # 알림은 부가기능 — 실패해도 본 작업 진행


def _extract_tool_json(content) -> dict:
    """call_tool 이 돌려준 content array 에서 첫 text 항목을 JSON 으로 파싱(실패 시 {})."""
    if not content:
        return {}
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            try:
                return json.loads(item.get("text") or "")
            except Exception:
                return {}
    return {}


def _wait_for_ds_loading_done(timeout: float = 90.0) -> None:
    """🔴 통독(learn-planning) progress 를 시작하기 전에 브리지의 '디자인 시스템 문서 로딩'
    완료를 대기한다 (2026-06-05 사용자: "learn-planning 을 디자인 시스템 로딩 완료 후에
    시작하도록 코드에 박아").

    브리지 도구 `get_ds_loading_status` 를 폴링:
      - 'done'  → DS 로딩 완료, 통독 시작 (통과)
      - 'loading' → DS 로딩 진행 중, 대기
      - 'idle'  → 플러그인 미연결/로딩 없음. connected 직후 레이스로 잠깐 idle 일 수 있어
                  3초 재확인 후에도 idle 이면 통과(통독 progress 는 어차피 UI 에 못 뜸).
    구버전 브리지(도구 없음)·통신 에러는 게이트 없이 그냥 통과(하위호환). 타임아웃도 진행."""
    start = time.time()
    announced = False
    idle_since = None
    while time.time() - start < timeout:
        try:
            res = call_tool("get_ds_loading_status", {})
        except Exception:
            return  # 도구 없음(구버전 브리지) 또는 통신 에러 — 막지 않고 진행
        status = _extract_tool_json(res).get("status")
        if status == "done":
            if announced:
                print("[기획] ✓ 디자인 시스템 로딩 완료 — 기획 통독 시작")
            return
        if status == "loading":
            idle_since = None
            if not announced:
                print("[기획] 디자인 시스템 로딩 완료 대기 중... (완료 후 통독 시작)")
                announced = True
        else:  # 'idle' 또는 None
            if idle_since is None:
                idle_since = time.time()
            elif time.time() - idle_since >= 3.0:
                return  # 3초간 계속 idle = 플러그인 미연결/DS 로딩 없음 — 통독 진행
        time.sleep(1.0)
    print("[기획] ⚠ DS 로딩 대기 타임아웃 — 통독 진행")


def _load_planning_module():
    import importlib.util
    _here = os.path.dirname(os.path.abspath(__file__))
    _rp_path = os.path.join(_here, "read_planning_docs.py")
    spec = importlib.util.spec_from_file_location("read_planning_docs", _rp_path)
    rp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rp)
    return rp


def _planning_meta_path(out_rel: str = "scripts/_planning_digest.txt") -> str:
    _here = os.path.dirname(os.path.abspath(__file__))
    out_path = out_rel if os.path.isabs(out_rel) else os.path.join(os.path.dirname(_here), out_rel)
    return out_path + ".meta.json"


def _planning_changed(out_rel: str = "scripts/_planning_digest.txt"):
    """기획 문서가 마지막 학습 이후 변경(추가/수정/삭제)됐는지 + 현재 fingerprint 반환.

    Returns (changed: bool, fp: dict, digest_exists: bool).
    digest/meta 가 없으면 changed=True (아직 학습 안 함).
    """
    rp = _load_planning_module()
    fp = rp.fingerprint()
    _here = os.path.dirname(os.path.abspath(__file__))
    out_path = out_rel if os.path.isabs(out_rel) else os.path.join(os.path.dirname(_here), out_rel)
    meta_path = out_path + ".meta.json"
    digest_exists = os.path.exists(out_path)
    if not digest_exists or not os.path.exists(meta_path):
        return True, fp, digest_exists
    try:
        with open(meta_path, encoding="utf-8") as fh:
            prev = json.load(fh)
        return (prev.get("hash") != fp.get("hash")), fp, digest_exists
    except Exception:
        return True, fp, digest_exists


def _planning_read_ack_path(out_rel: str = "scripts/_planning_digest.txt") -> str:
    """통독 ack 파일 경로 (digest 옆 .read.json)."""
    _here = os.path.dirname(os.path.abspath(__file__))
    out_path = out_rel if os.path.isabs(out_rel) else os.path.join(os.path.dirname(_here), out_rel)
    return out_path + ".read.json"


# ── Read 커버리지 게이트 (2026-06-05 사용자: "Read 커버리지 훅으로 구현") ────────────
# 토큰 ack 는 1회 영속이라 "새 세션이 끝까지 읽었는가" 를 분간 못 한다. PostToolUse(Read)
# 훅(scripts/hooks/planning_read_hook.py)이 _planning_digest.txt Read 의 실제 반환 줄
# 범위를 세션별 cov_<sid>.json 에 누적하고, UserPromptSubmit 훅이 현재 세션 ID 를
# current_session 에 기록한다. 훅이 활성(=current_session 존재)이면 이 게이트가 **현재
# 세션의 완독 커버리지**를 요구한다(비활성이면 기존 토큰 ack 로 폴백).
_PLANNING_COMPLETE_RATIO = 0.97
_PLANNING_END_SLACK = 8
_PLANNING_START_SLACK = 3


def _planning_gate_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".planning_gate")


def _current_claude_session():
    """UserPromptSubmit 훅이 기록한 현재 Claude 세션 ID. 없으면 None(훅 비활성)."""
    p = os.path.join(_planning_gate_dir(), "current_session")
    try:
        with open(p, encoding="utf-8") as fh:
            sid = fh.read().strip()
        return sid or None
    except Exception:
        return None


def _planning_covered_count(ranges) -> int:
    return sum(b - a + 1 for a, b in ranges)


def _planning_coverage_complete(ranges, total: int) -> bool:
    if total <= 0 or not ranges:
        return False
    mn = min(a for a, _ in ranges)
    mx = max(b for _, b in ranges)
    if mn > _PLANNING_START_SLACK or mx < total - _PLANNING_END_SLACK:
        return False
    return _planning_covered_count(ranges) >= _PLANNING_COMPLETE_RATIO * total


def _planning_session_read_ok(out_rel: str = "scripts/_planning_digest.txt"):
    """현재 Claude 세션이 digest 를 끝까지 Read 했는지.

    Returns (active: bool, ok: bool, reason: str).
    active=False → 훅 비활성(current_session 없음) → 호출측이 토큰 ack 로 폴백.
    """
    sid = _current_claude_session()
    if not sid:
        return False, False, "Read 커버리지 훅 비활성"
    cov_path = os.path.join(_planning_gate_dir(), "cov_%s.json" % sid)
    if not os.path.exists(cov_path):
        return True, False, "이 세션에서 digest 통독 기록 없음 — Read 도구로 끝까지 통독 필요"
    try:
        with open(cov_path, encoding="utf-8") as fh:
            cov = json.load(fh)
    except Exception:
        return True, False, "이 세션 커버리지 손상 — 재통독 필요"
    meta_path = _planning_meta_path(out_rel)
    try:
        with open(meta_path, encoding="utf-8") as fh:
            meta_hash = json.load(fh).get("hash")
    except Exception:
        meta_hash = None
    if cov.get("hash") != meta_hash:
        return True, False, "이 세션 통독이 옛 digest 기준 — 재통독 필요"
    _here = os.path.dirname(os.path.abspath(__file__))
    out_path = out_rel if os.path.isabs(out_rel) else os.path.join(os.path.dirname(_here), out_rel)
    try:
        with open(out_path, "rb") as fh:
            total = sum(1 for _ in fh)
    except Exception:
        total = cov.get("total", 0)
    ranges = cov.get("covered") or []
    if _planning_coverage_complete(ranges, total):
        return True, True, "이 세션 통독 완료 (Read 커버리지 %d/%d줄)" % (
            _planning_covered_count(ranges), total)
    return True, False, "이 세션 통독 불완전 (%d/%d줄) — Read 도구로 끝까지 통독 필요" % (
        _planning_covered_count(ranges), total)


def _planning_read_ok(out_rel: str = "scripts/_planning_digest.txt"):
    """기획 통독 게이트 통과 여부. Returns (ok: bool, reason: str).

    digest 존재 + 기획 폴더 변경 없음(fingerprint 일치)을 먼저 검사(항상 필수).
    그 다음:
      - Read 커버리지 훅 활성 시 → **현재 세션의 완독 커버리지**를 요구(새 세션 강제).
      - 훅 비활성(cron/CLI) 시 → 기존 토큰 ack(read_token 일치)로 폴백.
    기획 폴더 0건이면 ok=True(무관).
    """
    rp = _load_planning_module()
    fp = rp.fingerprint()
    if fp.get("count", 0) == 0:
        return True, "기획 폴더 없음 — 무관"
    meta_path = _planning_meta_path(out_rel)
    ack_path = _planning_read_ack_path(out_rel)
    _here = os.path.dirname(os.path.abspath(__file__))
    out_path = out_rel if os.path.isabs(out_rel) else os.path.join(os.path.dirname(_here), out_rel)
    if not os.path.exists(out_path) or not os.path.exists(meta_path):
        return False, "digest 없음 — learn-planning 미실행"
    try:
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)
    except Exception:
        return False, "meta 손상 — learn-planning 재실행"
    if meta.get("hash") != fp.get("hash"):
        return False, "기획 문서 변경됨 — learn-planning 재실행 + 재통독 필요"

    # 훅 활성 시: 현재 세션 완독이면 즉시 통과. 아니면 fingerprint 기준 영속 ack 폴백.
    # 🔴 2026-08-14 사용자 승인: ack 는 세션이 아니라 **fingerprint 기준 영속** — 기획 문서가
    # 안 바뀌었으면(위에서 hash 일치 확인됨) 과거 세션의 유효 ack 로 재통독 없이 통과.
    # 문서가 바뀌면 learn-planning 이 ack 를 무효화하므로 "변경 시 재통독" 취지는 유지된다.
    active, sess_ok, sess_reason = _planning_session_read_ok(out_rel)
    if active and sess_ok:
        return True, sess_reason

    # 훅 비활성(cron/CLI) 또는 이 세션 미통독: 토큰 ack (fingerprint 영속) 폴백
    if not os.path.exists(ack_path):
        return False, "통독 ack 없음 — digest 통독 후 ack-planning 필요"
    try:
        with open(ack_path, encoding="utf-8") as fh:
            ack = json.load(fh)
    except Exception:
        return False, "ack 손상 — 재통독 + ack-planning 필요"
    if ack.get("read_token") != meta.get("read_token"):
        return False, "ack 토큰 불일치 — 최신 digest 통독 후 ack-planning 필요"
    return True, "통독 완료"


def cmd_ack_planning(token: str, out_rel: str = "scripts/_planning_digest.txt"):
    """🔴 기획 통독 확인 ack — digest 끝의 통독 확인 토큰으로 검증 후 ack 기록.

    digest 맨 끝에만 토큰이 있으므로, 정확한 토큰을 제출했다 = 끝까지 통독했다.
    ack 후에야 디자인 빌드 게이트가 통과된다.
    """
    meta_path = _planning_meta_path(out_rel)
    if not os.path.exists(meta_path):
        print("[기획] meta 없음 — 먼저 `learn-planning` 실행 후 digest 통독")
        sys.exit(1)
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    expected = meta.get("read_token")
    if not token or token.strip() != expected:
        print(f"❌ [기획] 통독 토큰 불일치 (제출={token!r}). digest 파일 **맨 끝**의 "
              f"'통독 확인 토큰'을 끝까지 통독한 뒤 정확히 입력할 것.")
        print(f"   digest: {out_rel} — Read 도구로 끝까지 읽으면 토큰이 마지막에 있음.")
        sys.exit(1)
    ack = {"read_token": expected, "hash": meta.get("hash"), "count": meta.get("count")}
    with open(_planning_read_ack_path(out_rel), "w", encoding="utf-8") as fh:
        json.dump(ack, fh, ensure_ascii=False)
    _notify_plugin("planning-docs", status="done", count=meta.get("count"))
    print(f"✅ [기획] 통독 확인 완료 (토큰 {expected}) — 이제 디자인 빌드 게이트 통과. "
          f"서비스 맥락 이해 상태로 디자인 생성 가능.")


# ── BUILD-SUMMARY-JSON — 기계 판독 빌드 결과 요약 (Astryx 패턴, 2026-07-08) ────────
# cmd_build 의 모든 종료 지점(게이트 차단·검증 실패·성공·빌드 실패)에서 stdout **마지막
# 블록**으로 구조화 요약을 출력한다. 목적: 에이전트가 빌드 로그를 tail/grep 으로 필터해도
# (0-G 레퍼런스 Read 누락의 근본 원인) 결과·필수 후속 액션을 항상 기계 판독으로 받게 한다.
# 계약:
#   - 마커 라인 "📋 BUILD-SUMMARY-JSON" 다음에 JSON 1개 (그 아래 다른 출력 없음)
#   - result: "success" | "blocked" | "failed"
#   - code/codes: error_codes.py 의 안정 코드 (prose 분기 금지)
#   - requiredActions: [{type: "read"|"run"|"export_and_read"|"fill_checklist", ...}]
#     → type=read 의 paths 는 **반드시 Read 도구로 열어야 하는** 파일들 (0-G/0-F)
_BUILD_SUMMARY_MARKER = "📋 BUILD-SUMMARY-JSON"


def _emit_build_summary(result: str, codes: list = None, root_id: str = None,
                        issues: list = None, warnings: list = None,
                        required_actions: list = None, note: str = None) -> None:
    doc: dict = {"type": "build-summary", "result": result}
    if codes:
        doc["code"] = codes[0]
        doc["codes"] = codes
    if root_id:
        doc["rootId"] = root_id
    if issues:
        doc["issues"] = issues[:40]
    if warnings:
        doc["warningCount"] = len(warnings)
    if required_actions:
        doc["requiredActions"] = required_actions
    if note:
        doc["note"] = note
    print("\n" + _BUILD_SUMMARY_MARKER)
    print(json.dumps(doc, ensure_ascii=False, indent=2))


def _post_build_required_actions() -> list:
    """빌드 성공 후 에이전트가 반드시 수행해야 하는 후속 액션 목록 (0-G 레퍼런스 Read +
    0-F self-verify). 게이트가 다음 build/cleanup-qa 에서 미이행을 차단하므로, 요약에
    구조화해 미리 알린다."""
    actions = []
    if _LAST_REFERENCE_THUMBS:
        actions.append({
            "type": "read",
            "why": "레퍼런스 시각 학습 (절대 규칙 0-G) — 미Read 시 다음 build 차단",
            "paths": list(_LAST_REFERENCE_THUMBS),
        })
    try:
        pend_path = _pending_selfverify_path()
        if os.path.exists(pend_path):
            with open(pend_path, encoding="utf-8") as fh:
                pend = json.load(fh)
            actions.append({
                "type": "export_and_read",
                "why": "self-verify (절대 규칙 0-F) — 섹션 PNG 재export(scale=2)+Read, "
                       "미이행 시 다음 build/cleanup-qa 차단",
                "nodeIds": pend.get("nodeIds") or [],
                "checklistPath": pend.get("checklist_path"),
            })
    except Exception:
        pass
    return actions


def _enforce_planning_read_gate(root_name: str = None) -> None:
    """🔴 디자인 빌드 하드 게이트 — 기획 통독 안 했으면 빌드 차단 (references S20~S23 패턴).

    매번 디자인 생성 시 기획 맥락을 충분히 이해한 상태를 시스템이 보장.
    bypass: 환경변수 IMIN_SKIP_PLANNING_GATE=1 (긴급 시).

    🔴 2026-08-14 사용자 승인: **변환 트랙(비 imin_* root) 은 면제** — 캡처 1:1 DS 변환은
    기획 재해석이 아니라 기존 화면 옮기기라 통독이 선행 조건이 아니다. 창의 하드 게이트
    (S24~S27)가 imin_* 만 대상인 것과 동일 기준으로 정렬.
    """
    if root_name is not None and not str(root_name).strip().lower().startswith("imin"):
        print(f"ℹ️ [기획] 통독 게이트 면제 — 비 imin_* root '{root_name}' (변환/비창의 트랙, "
              "2026-08-14 사용자 승인)")
        return
    if os.environ.get("IMIN_SKIP_PLANNING_GATE") == "1":
        print("⚠️ [기획] 통독 게이트 우회됨 (IMIN_SKIP_PLANNING_GATE=1)")
        return
    try:
        ok, reason = _planning_read_ok()
    except Exception as e:
        print(f"  [기획-게이트] 검사 실패 (무시): {e}")
        return
    if ok:
        return
    print("\n" + "=" * 64)
    print("❌ 빌드 차단 — 기획 문서 통독이 필요합니다 (시스템 강제)")
    print(f"   사유: {reason}")
    print("   imin 서비스 맥락을 이해한 상태에서만 디자인을 생성할 수 있습니다. 절차:")
    print("   1) python3 scripts/figma_mcp_client.py learn-planning")
    print("   2) scripts/_planning_digest.txt 를 Read 도구로 **이 세션에서 끝까지** 통독")
    print("      (Read 커버리지 훅이 실제 읽은 줄 범위를 추적 — 끝까지 읽으면 ack 자동 기록)")
    print("      ※ 훅 비활성 환경이면 추가로: ack-planning <digest 끝의 토큰>")
    print("   (긴급 우회: IMIN_SKIP_PLANNING_GATE=1)")
    print("=" * 64)
    _emit_build_summary("blocked", codes=["ERR_PLANNING_GATE"], note=reason,
                        required_actions=[
                            {"type": "run",
                             "command": "python3 scripts/figma_mcp_client.py learn-planning"},
                            {"type": "read",
                             "why": "이 세션에서 digest 를 끝까지 통독 (Read 커버리지 훅이 추적)",
                             "paths": ["scripts/_planning_digest.txt"]},
                        ])
    sys.exit(2)


# ── 레퍼런스 Read 게이트 / self-verify 게이트 (2026-06-11 사용자: fable 이 레퍼런스 Read·
#    self-verify 를 조용히 건너뛰는 것 방지 — 통독과 동일하게 코드 게이트화). 통독 hook
#    (planning_read_hook.py)이 PostToolUse 에서 ref 썸네일 Read 와 export_node_as_image 호출을
#    세션별로 누적(.planning_gate/ref_<sid>.json · qa_<sid>.json). 여기서 빌드/정리 시 검증한다.
#    hook 비활성 환경(cron/CLI)이면 게이트는 통과(경고만) — 통독 게이트와 동일 폴백.
def _gate_session_set(prefix: str, key: str):
    """현재 세션의 .planning_gate/<prefix>_<sid>.json 의 set 필드. hook 비활성이면 None."""
    sid = _current_claude_session()
    if not sid:
        return None
    p = os.path.join(_planning_gate_dir(), "%s_%s.json" % (prefix, sid))
    try:
        with open(p, encoding="utf-8") as fh:
            return set(json.load(fh).get(key) or [])
    except Exception:
        return set()  # 세션은 있으나 아직 기록 없음


def _find_unresolved_icons(root_id: str) -> list:
    """빌드 트리에서 'icon-missing:*' placeholder 노드 수집 (2026-09-04)."""
    try:
        tr = parse_content(call_tool("get_node_tree", {"nodeId": root_id, "maxDepth": 12})).get("json") or {}
    except Exception:
        return []
    out = []

    def walk(n):
        if not isinstance(n, dict):
            return
        if str(n.get("name") or "").startswith("icon-missing:"):
            out.append({"id": n.get("id"), "name": n.get("name")})
        for c in n.get("children") or []:
            walk(c)
    walk(tr.get("node", tr) if isinstance(tr, dict) else {})
    return out


def _should_skip_reference_step(blueprint: dict) -> Optional[str]:
    """Step A.0 레퍼런스 검색 + 0-G Read 게이트를 건너뛸 사유 (없으면 None). 2026-09-04.
    - IMIN_CONVERT_TRACK=1 : 1:1 변환 트랙 — 레퍼런스 = 원본 캡처, 외부 레퍼런스 무의미
    - root._referencesSkipped 가 비어있지 않은 문자열 : 작성자가 사유를 명시한 bypass(S20)"""
    if os.environ.get("IMIN_CONVERT_TRACK") == "1":
        return "변환 트랙(IMIN_CONVERT_TRACK=1) — 레퍼런스는 원본 캡처"
    rs = (blueprint or {}).get("_referencesSkipped") if isinstance(blueprint, dict) else None
    if isinstance(rs, str) and rs.strip():
        return f"_referencesSkipped: {rs.strip()[:60]}"
    return None


def _enforce_reference_read_gate() -> None:
    """🔴 레퍼런스 Read 하드 게이트 (절대 규칙 0-G) — Step A.0 가 검색한 썸네일을 이 세션에서
    Read 안 했으면 빌드 차단. 모델(fable 등)이 레퍼런스 시각학습을 조용히 건너뛰는 것 방지.
    bypass: IMIN_SKIP_REFERENCE_GATE=1."""
    if os.environ.get("IMIN_SKIP_REFERENCE_GATE") == "1":
        print("⚠️ [레퍼런스] Read 게이트 우회됨 (IMIN_SKIP_REFERENCE_GATE=1)")
        return
    if not _LAST_REFERENCE_THUMBS:
        return  # 검색 결과 없음(레퍼런스 미매칭) — 강제 불가
    read = _gate_session_set("ref", "read")
    if read is None:
        print("  [레퍼런스-게이트] Read 커버리지 훅 비활성 — 게이트 skip (0-G 수동 준수)")
        return
    want = {os.path.basename(p) for p in _LAST_REFERENCE_THUMBS}
    missing = sorted(want - read)
    if not missing:
        print(f"  [레퍼런스-게이트] ✓ 이 세션이 레퍼런스 {len(want)}장 모두 Read 함")
        return
    print("\n" + "=" * 64)
    print("❌ 빌드 차단 — 레퍼런스 썸네일을 이 세션에서 Read 해야 합니다 (절대 규칙 0-G)")
    print(f"   위 Step A.0 가 출력한 레퍼런스 {len(want)}장 중 {len(missing)}장 미Read:")
    for p in _LAST_REFERENCE_THUMBS:
        if os.path.basename(p) in missing:
            print(f"     - {p}")
    print("   → 위 PNG 들을 Read 도구로 열어 시각 학습한 뒤 references[] 에 반영하고 다시 build.")
    print("   (긴급 우회: IMIN_SKIP_REFERENCE_GATE=1)")
    print("=" * 64)
    _emit_build_summary("blocked", codes=["ERR_REFERENCE_READ_PENDING"],
                        required_actions=[{
                            "type": "read",
                            "why": "레퍼런스 시각 학습 (절대 규칙 0-G) 후 다시 build",
                            "paths": [p for p in _LAST_REFERENCE_THUMBS
                                      if os.path.basename(p) in missing],
                        }])
    sys.exit(2)


def _pending_selfverify_path() -> str:
    sid = _current_claude_session() or "_nohook"
    return os.path.join(_planning_gate_dir(), "pending_qa_%s.json" % sid)


def _record_pending_selfverify(root_id: str, exported: list, checklist_path: str) -> None:
    """빌드의 self-verify export 직후 — '미완료 self-verify' 마커 기록. 다음 build/cleanup-qa
    시작 시 _enforce_selfverify_gate 가 검증한다.
    🔴 변환 트랙(convert_screen → rebuild_track 이 서브프로세스로 build 호출, IMIN_CONVERT_TRACK=1)은
    기록하지 않는다 — 그 트랙은 rebuild_track.selfcheck + region_diff 가 0-F 를 대체하며, 마커가 남으면
    이후 cleanup-qa/build 가 엉뚱한 재export 를 요구한다 (2026-09-04 사용자 "정리해")."""
    if os.environ.get("IMIN_CONVERT_TRACK") == "1":
        return
    try:
        os.makedirs(_planning_gate_dir(), exist_ok=True)
        with open(_pending_selfverify_path(), "w", encoding="utf-8") as fh:
            json.dump({
                "root_id": root_id,
                "nodeIds": [e.get("nodeId") for e in (exported or []) if e.get("nodeId")],
                "checklist_path": checklist_path,
                "ts": int(time.time()),
            }, fh, ensure_ascii=False)
    except Exception:
        pass


def _checklist_unfilled_count(checklist_path: str) -> int:
    """checklist 의 status 가 아직 FILL_IN/빈값 인 항목 수 (못 읽으면 -1)."""
    try:
        with open(checklist_path, encoding="utf-8") as fh:
            cl = json.load(fh)
    except Exception:
        return -1
    return sum(1 for c in (cl.get("checklist") or [])
               if (c.get("status") or "").upper() in ("", "FILL_IN"))


def _enforce_selfverify_gate(context: str = "build") -> None:
    """🔴 self-verify 하드 게이트 (절대 규칙 0-F) — 직전 빌드의 섹션 PNG 를 이 세션에서
    재export(=Read) 안 했으면 다음 build/cleanup-qa 차단. 모델이 self-verify 를 조용히
    건너뛰고 '완료' 보고하는 것 방지. bypass: IMIN_SKIP_SELFVERIFY_GATE=1."""
    if os.environ.get("IMIN_SKIP_SELFVERIFY_GATE") == "1":
        return
    sid = _current_claude_session()
    if not sid:
        return  # hook 비활성 — 폴백 통과
    pend_path = _pending_selfverify_path()
    if not os.path.exists(pend_path):
        return  # 미완료 self-verify 없음
    try:
        with open(pend_path, encoding="utf-8") as fh:
            pend = json.load(fh)
    except Exception:
        try:
            os.remove(pend_path)
        except Exception:
            pass
        return
    want = set(pend.get("nodeIds") or [])
    exported = _gate_session_set("qa", "exported") or set()
    missing = sorted(want - exported)
    unfilled = _checklist_unfilled_count(pend.get("checklist_path") or "")
    if not missing:
        # 섹션 PNG 재export 됨 → 통과. checklist 미작성은 강한 경고(차단 X — 핵심은 '이미지를 봤나').
        if unfilled > 0:
            print(f"  ⚠️ [self-verify] 섹션 PNG 는 재export 했으나 checklist {unfilled}개 항목이 "
                  f"FILL_IN — {pend.get('checklist_path')} 를 PASS/FAIL/NA 로 채울 것 (0-F).")
        try:
            os.remove(pend_path)
        except Exception:
            pass
        return
    print("\n" + "=" * 64)
    print(f"❌ {context} 차단 — 직전 빌드의 self-verify 가 미완료입니다 (절대 규칙 0-F)")
    print(f"   root {pend.get('root_id')} 의 섹션 PNG {len(want)}장 중 {len(missing)}장 미재export:")
    for nid in missing:
        print(f"     - {nid}")
    print("   → 위 nodeId 들을 export_node_as_image(scale=2) 로 재export + Read 하고,")
    print(f"     checklist({pend.get('checklist_path')}) 12개 항목을 PASS/FAIL/NA 로 채울 것.")
    print("   (긴급 우회: IMIN_SKIP_SELFVERIFY_GATE=1)")
    print("=" * 64)
    _emit_build_summary("blocked", codes=["ERR_SELF_VERIFY_PENDING"],
                        root_id=pend.get("root_id"),
                        required_actions=[
                            {"type": "export_and_read",
                             "why": "self-verify (절대 규칙 0-F) — 섹션 PNG 재export(scale=2)+Read",
                             "nodeIds": missing},
                            {"type": "fill_checklist",
                             "path": pend.get("checklist_path")},
                        ])
    sys.exit(2)


def cmd_learn_planning(out_rel: str = "scripts/_planning_digest.txt", force: bool = False):
    """🔴 디자인 생성 준비 마지막 단계 — src/기획/ 기획 문서 학습 + 플러그인 progress 표시.

    36개 유스케이스 HTML 을 통합 digest 로 만들며 플러그인 UI 에 '기획 문서 학습 중 (n/총)'
    progress 를 보여준다(2026-06-04 사용자). 완료 후 digest 경로를 출력 → Claude 가 Read 로 통독.

    🔴 변경 감지: 기획 문서가 마지막 학습과 동일(fingerprint 일치)하면 재생성 스킵(효율) —
    변경(추가/수정/삭제)됐을 때만 재학습. `--force` 로 무조건 재학습.
    """
    rp = _load_planning_module()
    _here = os.path.dirname(os.path.abspath(__file__))
    out_path = out_rel if os.path.isabs(out_rel) else os.path.join(os.path.dirname(_here), out_rel)
    meta_path = out_path + ".meta.json"

    _ensure_bridge_server()
    init_session()  # 플러그인 연결 (알림이 UI 에 도달하려면 세션 필요)

    fp = rp.fingerprint()
    if fp.get("count", 0) == 0:
        print(f"[기획] src/기획/ 문서 0건 — 학습 단계 건너뜀 ({rp._PLAN_DIR})")
        _notify_plugin("planning-docs", status="done", count=0)
        return

    changed, _fp2, digest_exists = _planning_changed(out_rel)

    # 🔴 2026-09-04 사용자 지적("통독 ack 가 매 세션 무효화 — 원인 찾아 해결"):
    #   2026-06-05 "매번 새로 작성" 룰이 변경 감지 스킵을 없애고 ack 를 **무조건** 삭제해,
    #   2026-08-14 승인 룰(ack 는 fingerprint 기준 영속 — 문서 안 바뀌면 재통독 없이 통과)을
    #   코드가 뒤집고 있었다(CLAUDE.md 서술과도 불일치). 이제:
    #   - fingerprint 동일 + digest/ack 유효 → 재생성 스킵(플러그인엔 done 알림), ack 유지.
    #   - fingerprint 동일 + ack 없음 → 재생성 없이 통독 안내만.
    #   - 변경 or --force → 재생성. read_token 은 본문 sha1 이라 내용이 같으면 토큰도 같으므로
    #     ack 는 **토큰이 바뀐 경우에만** 무효화한다.
    if digest_exists and not changed and not force:
        ok, reason = _planning_read_ok(out_rel)
        _notify_plugin("planning-docs", status="done", count=fp["count"])
        if ok:
            print(f"[기획] ✓ 기획 문서 변경 없음(fingerprint 일치) — digest 재사용, 통독 ack 유효 ({reason})")
            print(f"[기획]    재통독 불필요. 강제 재학습: learn-planning --force")
            return
        try:
            with open(meta_path, encoding="utf-8") as fh:
                _tok = json.load(fh).get("read_token", "")
        except Exception:
            _tok = ""
        print(f"[기획] 기획 문서 변경 없음 — digest 재사용 ({reason})")
        print(f"[기획] 👉 {out_path} 를 Read 도구로 **끝까지** 통독 → "
              f"`python3 scripts/figma_mcp_client.py ack-planning {_tok}`")
        return

    total = fp["count"]
    why = "최초 학습" if not digest_exists else ("강제 재학습" if force else "재학습 (기획 문서 변경 감지)")
    print(f"[기획] {total}개 유스케이스 문서 학습 시작 ({why})...")
    # 🔴 디자인 시스템 로딩 완료 후 통독 시작 (2026-06-05 사용자 룰). 플러그인 연결 직후
    #    브리지가 DS 문서를 동기화하는 동안 대기 → 완료되면 통독 progress 를 UI 에 띄운다.
    #    이래야 플러그인 UI 에서 'DS 로딩 → 기획 통독' 이 순서대로 또렷이 보인다.
    _wait_for_ds_loading_done()
    _notify_plugin("planning-docs", status="loading")

    def _progress(cur, tot, name):
        short = (name or "")[:40]
        _notify_plugin("planning-docs", status="syncing", current=cur, total=tot, name=short)
        if cur == 1 or cur % 6 == 0 or cur == tot:
            print(f"  [기획] {cur}/{tot} — {short}")

    digest, count, read_token = rp.build_digest(progress=_progress)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(digest)
    meta = dict(fp)
    meta["read_token"] = read_token
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False)
    # 이전 통독 ack 무효화 — 단, 토큰(본문 sha1)이 그대로면 내용이 동일하므로 ack 유지
    # (--force 재학습이나 mtime 만 바뀐 경우에 재통독을 강요하지 않기 위해, 2026-09-04)
    ack_kept = False
    try:
        _ack = _planning_read_ack_path(out_rel)
        if os.path.exists(_ack):
            with open(_ack, encoding="utf-8") as fh:
                _prev_tok = json.load(fh).get("read_token")
            if _prev_tok != read_token:
                os.remove(_ack)
                print("[기획] 이전 통독 ack 무효화 (digest 내용 변경) — 재통독 필요")
            else:
                ack_kept = True
    except Exception:
        pass

    _notify_plugin("planning-docs", status="done", count=count)
    print(f"[기획] ✓ {count}개 유스케이스 학습 digest 생성 → {out_path} ({len(digest):,}자)")
    if ack_kept:
        print("[기획] ✓ digest 내용 동일(토큰 일치) — 기존 통독 ack 유지, 재통독 불필요")
        return
    print(f"[기획] 👉 다음(필수): 이 파일을 Read 도구로 **끝까지** 통독 → 맨 끝 토큰으로")
    print(f"[기획]    `python3 scripts/figma_mcp_client.py ack-planning {read_token}` 실행")
    print(f"[기획]    (통독+ack 해야 디자인 빌드가 통과됨 — 시스템 강제)")


def cmd_call(tool_name: str, args_json: str, compact: bool = False):
    ensure_session()
    args = json.loads(args_json) if args_json else {}
    content = call_tool(tool_name, args)
    result = parse_content(content)

    if result["json"]:
        # 2026-05-28 — compact 면 한 줄 JSON 출력. 검증 스크립트가 `tail -1 | json.loads`
        # 로 안정 파싱하도록 (이전 indent=2 pretty-print 는 여러 줄이라 파싱 실패 → 추측 패치 회귀).
        if compact:
            print("__JSON__" + json.dumps(result["json"], ensure_ascii=False))
        else:
            print(json.dumps(result["json"], indent=2, ensure_ascii=False))
    else:
        for t in result["texts"]:
            print(t)
    if result["images"]:
        print(f"\n[{len(result['images'])} image(s) returned]")


# ⚠️ Step A (2026-05-28) — 사용자 결정형 polished 디자인 자동 export
# imin_home archetype 빌드 시 [feedback_user_modified_design_rules] 의 16941:51284
# (사용자가 직접 polish 한 holy-grail 디자인) 을 build 직전 PNG export 해서
# Claude 가 빌드 진행 전 시각 reference 를 갱신하도록 강제. 새 세션 회귀 차단.

_CANONICAL_REFS = {
    "imin_home": {
        "node_id": "16941:51284",
        "file_key": "SsgiLsXVMkf0wv8OhRGwks",
        "memo": ("사용자가 직접 polish 한 imin_home 결정형 reference. "
                 "카드 위계, brand bg 위 sub-component, Pill 패턴, "
                 "텍스트 컬러 룰 — 이 시각을 reference 로 디자인하라."),
    },
}


def _auto_export_canonical_reference(blueprint: dict) -> None:
    """archetype 별로 사용자 결정형 reference 노드를 PNG export 하고 경로 알림.

    Claude 가 빌드 직전에 export 된 PNG 를 Read 해서 시각 풍부함을
    학습 후 blueprint 작성하도록 시스템에 박힌 hook.
    """
    if not isinstance(blueprint, dict):
        return
    root_name = (blueprint.get("rootName") or blueprint.get("name") or "").lower()
    # archetype 매칭
    matched = None
    for archetype, ref in _CANONICAL_REFS.items():
        if archetype in root_name:
            matched = (archetype, ref)
            break
    if not matched:
        return
    archetype, ref = matched
    node_id = ref["node_id"]
    try:
        result = call_tool("export_node_as_image", {
            "nodeId": node_id,
            "format": "PNG",
            "scale": 1,
        })
        # 파일 경로 추정 — figma MCP 가 cache 에 저장
        print(f"\n📐 [Step A] 결정형 reference auto-export: {archetype}")
        print(f"  Node: {node_id}  (file: {ref['file_key']})")
        print(f"  → Claude: 빌드 전 이 reference 이미지를 Read 해서 시각 풍부함 학습 필수")
        print(f"  Memo: {ref['memo']}")
    except Exception as e:
        # reference 노드가 다른 파일에 있을 때 등 — fail soft
        print(f"  [Step A] 결정형 reference export skipped ({e})")


# ── Step A.0 — references/uibowl 자동 검색 (2026-05-28) ──────────────────────
# 사용자 명시: "내가 레퍼런스 이미지를 수백장 첨부해놓은거 아니냐! 너 디자인 생성할때
# 레퍼런스 이미지 검색은 하냐?" → archetype 매칭 PNG path 자동 출력 + Read 강제.

# 마지막 빌드의 reference 썸네일 경로 — cmd_build 끝에서 재출력(tail-visible)용
_LAST_REFERENCE_THUMBS: list = []
_LAST_REFERENCE_LABEL: str = ""


def _auto_search_uibowl_references(blueprint: dict) -> None:
    """archetype 인식해 references/uibowl 자동 검색 + thumbnail 생성.

    빌드 진행 전 Claude 가 PNG path 들을 Read 강제 (CLAUDE.md 절대 규칙 0-G).
    """
    if not isinstance(blueprint, dict):
        return
    root_name = (blueprint.get("rootName") or blueprint.get("name") or "").lower()
    if not root_name:
        return

    # archetype 추론 — root_name 에서 imin_xxx 패턴 추출
    archetype = None
    for kw in ["imin_home", "imin_stage", "imin_lounge", "imin_community",
               "imin_payment", "imin_detail", "imin_onboarding", "imin_settings",
               "imin_notification", "imin_search", "imin_history"]:
        if kw in root_name:
            archetype = kw
            break
    # 🔴 2026-06-08 (사용자: "새 세션 최초 생성 때도 레퍼런스 안 봤다"): home/stage 등 '변형 이름'
    # (imin_signup_home·imin_active_home·imin_*_home_creative 등)도 archetype 인식한다. 예전엔
    # 'imin_home' 정확 부분문자열만 봐서 'imin_signup_home' 이 미인식→일반 폴백 되며 진짜 홈
    # 레퍼런스를 못 받았다. bare word(home/stage/...) 가 이름에 있으면 해당 archetype 으로.
    if archetype is None:
        for bare, arch in (("home", "imin_home"), ("stage", "imin_stage"),
                           ("lounge", "imin_lounge"), ("community", "imin_community"),
                           ("payment", "imin_payment"), ("onboarding", "imin_onboarding"),
                           ("notification", "imin_notification"), ("search", "imin_search"),
                           ("history", "imin_history"), ("settings", "imin_settings")):
            if bare in root_name:
                archetype = arch
                break

    # ⚠️ 2026-05-28 사용자 분노 (근본 원인 수정): 예전엔 archetype 미인식 시 여기서
    # 조용히 return → 모달·신규 화면(예: transaction_schedule_modal)은 레퍼런스 검색이
    # 경고 한 줄 없이 통째로 누락됐다. 이제 절대 silent-skip 하지 않는다:
    #   1) root_name 토큰 + 와이어 키워드로 --keyword 검색 시도
    #   2) 그래도 없으면 일반 fintech 레퍼런스(imin_home)로 폴백
    #   3) 어느 경우든 SECTION-REFERENCE-PNG 출력 + "archetype 미인식" 경고를 크게 띄움
    import subprocess
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ref_script = os.path.join(project_root, "scripts", "ref_search.py")
    if not os.path.exists(ref_script):
        print("  [Step A.0] ⚠️ ref_search.py 없음 — 레퍼런스 검색 불가")
        return

    search_args = None
    fallback_note = ""
    if archetype:
        search_args = ["--archetype", archetype]
    else:
        # 키워드 후보: root_name 토큰(영문) + 와이어 콘텐츠에서 의미 토큰 추출
        import re as _re
        toks = [t for t in _re.split(r"[_\-\s]+", root_name)
                if t and t not in ("imin", "modal", "screen", "page", "view", "v1", "v2")]
        kw_hits = None
        for t in toks:
            try:
                r = subprocess.run(["python3", ref_script, "--keyword", t,
                                    "--limit", "6", "--thumbnail", "--json"],
                                   cwd=project_root, capture_output=True, text=True, timeout=30)
                import json as _j
                if r.returncode == 0 and r.stdout.strip() and _j.loads(r.stdout):
                    kw_hits = t
                    break
            except Exception:
                pass
        if kw_hits:
            search_args = ["--keyword", kw_hits]
            fallback_note = f"archetype 미인식 → 키워드 '{kw_hits}' 검색"
        else:
            search_args = ["--archetype", "imin_home"]
            fallback_note = (f"⚠️ archetype·키워드 모두 미인식 (root_name='{root_name}') "
                             f"→ 일반 fintech 레퍼런스로 폴백. 화면 성격에 맞는지 직접 판단 필수")

    try:
        result = subprocess.run(
            ["python3", ref_script, *search_args,
             "--limit", "6", "--thumbnail", "--json"],
            cwd=project_root,
            capture_output=True, text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"  [Step A.0] ref_search 실패: {result.stderr[:200]}")
            return
        import json as _json
        refs = _json.loads(result.stdout)
        if not refs:
            print(f"  [Step A.0] ⚠️ 매칭 reference 없음 (search={search_args}) — 레퍼런스 학습 누락! 직접 ref_search 로 검색 권장")
            return

        label = archetype if archetype else f"FALLBACK ({fallback_note})"
        # 🔴 썸네일 경로 저장 — cmd_build 끝에서 재출력해 `tail -N` 으로 로그 봐도 안 놓치게
        # (2026-06-08 근본 원인: 빌드 출력을 tail/grep 으로 필터해 Step A.0 의 reference 프롬프트를
        #  통째로 못 봐 0-G 를 매번 빠뜨렸다 → 끝에서 다시 띄운다.)
        global _LAST_REFERENCE_THUMBS, _LAST_REFERENCE_LABEL
        # 🔴 영상(mp4 등)은 Read 도구로 열 수 없어 게이트 필수 대상에서 제외 (2026-06-12 게이트 버그
        # 수정: ref_search 가 video 레퍼런스의 thumbPath 로 원본 mp4 경로를 그대로 줘 빌드가
        # 영구 차단되던 회귀). 이미지 썸네일만 Read 강제.
        _IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
        _LAST_REFERENCE_THUMBS = [r["thumbPath"] for r in refs
                                  if str(r.get("thumbPath", "")).lower().endswith(_IMG_EXTS)]
        _LAST_REFERENCE_LABEL = label
        print(f"\n📚 [Step A.0] references/uibowl 자동 검색 — {label}")
        if fallback_note:
            print(f"  ⚠️ {fallback_note}")
        print("=" * 70)
        for r in refs:
            print(f"  [{r['app']:9s}] {r['patternCodeName']:14s} | {(r.get('patternName') or '-')[:20]:20s} | {r['thumbPath']}")
        print()
        print("📌 SECTION-REFERENCE-PNG ⚠️  Claude 강제 절차 (CLAUDE.md 절대 규칙 0-G):")
        print("    1. 위 PNG 6장을 모두 Read 도구로 열어 시각 학습")
        print("       (path 만 references[] 박지 말고 실제 이미지 시각 위계/리듬/컬러 매핑 참고)")
        print("    2. 학습 결과를 _enrich_imin_home_polish 또는 라이브 fix 에 반영")
        print("    3. references[] 의 ref/extract/copyNotes 에 실제 본 내용 박을 것")
        print("=" * 70)
    except Exception as e:
        print(f"  [Step A.0] reference 검색 실패 (무시): {e}")


# ── Step A.5 — imin_home polish baseline auto-inject (2026-05-28) ─────────────
# [feedback_imin_home_polish_baseline] catalog 의 시각 패턴을 blueprint 에 자동
# 박음. 17389:51811 의 폴리시 수준이 자동 baseline 으로 도달.

# ═══════════════════════════════════════════════════════════════════
# ⚠️ HARD-ENFORCED FUNCTIONS (2026-05-28 사용자 분노 후 무조건 실행 코드)
# ═══════════════════════════════════════════════════════════════════
# 룰 파일 (design_rules/R*.py) 은 phase 별 조건부 실행이라 회귀가 반복됨.
# 아래 _HARD_* 함수들은 cmd_build / cmd_post_fix 에 무조건 호출되도록 박혀있음.
# 가드 조건 최소화 — 사용자 명시 "룰 말고 무조건 실행 코드 만들어".


# Day Strip cell 폭이 ~50px 이라 짧아야 함. 단독 "0원" 은 짧은 mock 으로.
_MOCK_FILL_PATTERNS_LONG = [
    # (regex_pattern, replacement) — large frame currency 용 (긴 mock)
    (r"진행중인?\s*0건의?", "진행중인 3건의"),
    (r"\+0원", "+1,240,000원"),
    (r"-0원", "-340,000원"),
    (r"연속\s*0일째", "연속 7일째"),
    (r"^0개$", "3개"),
    (r"^0건$", "3건"),
]
# Day Strip cell 같은 좁은 영역용 (≤ 6자 mock). 6개 cell 다른 수치로.
_MOCK_DAY_STRIP_AMOUNTS = ["+24만", "+18만", "+30만", "+15만", "+22만", "+28만"]


def _HARD_fill_mock_data_when_empty(blueprint: dict) -> None:
    """⚠️ [DEPRECATED 2026-05-28 — Refactor A] 무조건 실행: empty state 시나리오
    (0원/0건/0일) 감지되면 와이어 콘텐츠를 mock 활성 데이터로 자동 치환.

    🚨 새 코드는 **unified spec** (`scripts/archetype_specs/imin_home.json`) +
    `build_unified_blueprint()` 사용. 그쪽 generator 가 mock_data 를 직접 박음 —
    regex 치환 없음. 이 함수는 legacy blueprint 입력 fallback 에서만 호출됨.
    cmd_build 의 `_unified_mode` 분기에서 자동 skip.

    Why (legacy): 사용자 "왜 자꾸 데이터가 없는 empty 화면으로만 생성하냐! 적절한
    데이터가 보여진 화면으로 생성해야지 임마!!!!!". L1 와이어 1:1 룰 폐기 — 디자인은
    "데이터 있는 활성 상태" 가 default.

    Detection: _detect_empty_state_scenario 와 동일. archetype 검사 없음 (모든 화면).
    """
    import re
    if not isinstance(blueprint, dict):
        return
    # imin_home 아니면 skip (다른 archetype 안전)
    root_name = (blueprint.get("rootName") or blueprint.get("name") or "").lower()
    if "imin_" not in root_name:
        return
    if not _detect_empty_state_scenario(blueprint):
        return

    fixed = 0
    # Day Strip cell 의 "0원" 은 좁은 폭이라 짧은 mock 사용. cell index 별 다른 수치.
    day_strip_idx = [0]
    def walk(n, in_day_strip=False):
        nonlocal fixed
        if not isinstance(n, dict):
            return
        # Day Strip 안 진입
        nm = (n.get("name") or "").lower()
        if "day strip" in nm or "day-strip" in nm:
            in_day_strip = True
        if (n.get("type") or "").lower() == "text":
            t = n.get("text") or n.get("characters") or ""
            new_t = t
            if in_day_strip and t.strip() in ("0원", "+0원", "-0원"):
                # 좁은 cell 용 짧은 mock
                idx = day_strip_idx[0] % len(_MOCK_DAY_STRIP_AMOUNTS)
                new_t = _MOCK_DAY_STRIP_AMOUNTS[idx]
                day_strip_idx[0] += 1
            else:
                # 일반 영역은 긴 mock
                for pat, rep in _MOCK_FILL_PATTERNS_LONG:
                    new_t = re.sub(pat, rep, new_t)
            if new_t != t:
                if "text" in n:
                    n["text"] = new_t
                if "characters" in n:
                    n["characters"] = new_t
                fixed += 1
        for c in n.get("children", []) or []:
            walk(c, in_day_strip)
    walk(blueprint)

    if fixed:
        print(f"[HARD] empty state → mock data 자동 치환 {fixed}건 (사용자 명시 2026-05-28)")
        # 치환 후엔 empty 신호가 사라져야 polish 가 풀데이터 모드로 작동
        # _wireframeContent 도 mock 치환 알림
        wc = blueprint.get("_wireframeContent")
        if isinstance(wc, dict):
            wc["_mockFilled"] = f"{fixed}건 0원/0건/0일 → mock 데이터 자동 치환 (2026-05-28 사용자 룰)"


def _HARD_lounge_card_visual_after_build(root_node_id: str) -> int:
    """⚠️ 무조건 실행 (2026-05-28 사용자 분노 fix): 빌드 트리의 Lounge Card 안
    회색 빈 frame (자식 0~1개 + bg-secondary) 을 brand-section + center gift icon 으로
    자동 치환. R50 placeholder 차단의 라이브 버전.

    이전 R50/R52 는 build-time lint 만이라 polish 가 imageQuery 덮어쓰면 차단 못함.
    이 함수는 빌드 후 트리를 직접 탐색해 placeholder shape 검출 → live fix.
    """
    fixed = 0
    try:
        root_info = call_tool("get_node_info", {"nodeId": root_node_id})
    except Exception as e:
        print(f"  [HARD-lounge] root info fail: {e}")
        return 0

    GREY_RGB = (0.95, 0.96, 0.96)  # bg-secondary approx

    def is_greyish(fills):
        if not fills:
            return False
        for f in fills:
            if f.get("type") == "SOLID":
                c = f.get("color") or {}
                r, g, b = c.get("r", 0), c.get("g", 0), c.get("b", 0)
                if 0.9 < r < 1 and 0.9 < g < 1 and 0.9 < b < 1:
                    return True
        return False

    # Lounge 카드의 image frame 이름 패턴 (이름에 "image" / "photo" 포함)
    def walk(node, in_lounge=False, lounge_card_root=False):
        nonlocal fixed
        if not isinstance(node, dict):
            return
        nm = (node.get("name") or "").lower()
        # Lounge Card N (top-level card)
        is_card_root = (
            ("lounge" in nm and "card" in nm and "body" not in nm and "image" not in nm)
        )
        if is_card_root:
            in_lounge = True
            lounge_card_root = True
        # placeholder 검출: in_lounge 자손 중 image-named frame OR 회색 큰 frame
        if in_lounge and not lounge_card_root and node.get("type") == "FRAME":
            children = node.get("children") or []
            is_image_named = "image" in nm or "photo" in nm
            w = node.get("width", 0) or 0
            h = node.get("height", 0) or 0
            # 회색 placeholder OR 이름이 image/photo 인데 image fill 없음
            grey = is_greyish(node.get("fills"))
            has_image_fill = any(
                (f.get("type") in ("IMAGE",)) for f in (node.get("fills") or [])
            )
            should_fix = (
                (is_image_named and not has_image_fill and h >= 60) or
                (grey and len(children) == 0 and w >= 80 and h >= 60)
            )
            if should_fix:
                # bg-brand-section + 가운데 gift icon 그릴 frame
                try:
                    bs = resolve_token_ref("$token(bg-brand-section)") or {"r":0.95,"g":0.92,"b":1,"a":1}
                    call_tool("set_fill_color", {
                        "nodeId": node["id"], "r": bs["r"], "g": bs["g"], "b": bs["b"], "a": bs.get("a",1.0),
                    })
                    fp = _token_to_figma_path("bg-brand-section")
                    if fp:
                        try:
                            call_tool("set_bound_variables", {"nodeId": node["id"], "bindings": {"fills/0": fp}})
                        except Exception:
                            pass
                    # autoLayout center
                    try:
                        call_tool("set_auto_layout", {
                            "nodeId": node["id"], "layoutMode": "HORIZONTAL",
                            "primaryAxisAlignItems": "CENTER",
                            "counterAxisAlignItems": "CENTER",
                            "paddingTop": 8, "paddingBottom": 8, "paddingLeft": 8, "paddingRight": 8,
                        })
                    except Exception:
                        pass
                    fixed += 1
                except Exception as e:
                    print(f"  [HARD-lounge] node {node.get('id')} fix fail: {e}")
        for c in node.get("children") or []:
            walk(c, in_lounge, False)

    walk(root_info)
    if fixed:
        print(f"[HARD] Lounge 빈 회색 카드 → bg-brand-section + center 자동 fix {fixed}건")
    return fixed


def _HARD_empty_icon_circle_after_build(root_node_id: str) -> int:
    """⚠️ 무조건 실행 (2026-05-28 사용자 분노 fix): Empty Icon Wrap 류 frame
    (이름에 'empty icon' / 'inbox' / '없습니다' 부모 + icon-wrap 자식) 을
    56×56 cornerRadius 28 HUG×HUG 원형으로 강제. FILL 가로 막대 회귀 차단.
    """
    fixed = 0
    try:
        root_info = call_tool("get_node_info", {"nodeId": root_node_id})
    except Exception as e:
        print(f"  [HARD-empty-icon] root info fail: {e}")
        return 0

    def walk(node):
        nonlocal fixed
        if not isinstance(node, dict):
            return
        nm = (node.get("name") or "").lower()
        # icon-wrap 패턴: name contains "empty" + "icon" / "inbox" / "icon-wrap" + 가까운 형제에 "없습니다"
        if (("empty" in nm and "icon" in nm) or
            ("empty" in nm and "wrap" in nm) or
            "inbox" in nm):
            if node.get("type") == "FRAME":
                try:
                    call_tool("set_layout_sizing", {
                        "nodeId": node["id"], "horizontal": "FIXED", "vertical": "FIXED",
                    })
                    call_tool("resize_node", {
                        "nodeId": node["id"], "width": 56, "height": 56,
                    })
                    call_tool("set_corner_radius", {
                        "nodeId": node["id"], "radius": 28,
                    })
                    fixed += 1
                except Exception as e:
                    print(f"  [HARD-empty-icon] {node.get('id')} fix fail: {e}")
        for c in node.get("children") or []:
            walk(c)

    walk(root_info)
    if fixed:
        print(f"[HARD] Empty Icon Wrap 56×56 circle 강제 fix {fixed}건")
    return fixed


def _HARD_strip_duplicate_recommend_hero(root_node_id: str) -> int:
    """⚠️ 무조건 실행 (2026-05-28 사용자 분노 fix): Recommend Stage Card 안에
    동일 금액 hero text (예: '1,300만원') 가 2회 이상 있으면 두 번째부터 제거.
    polish + 와이어 hero 중복 회귀 차단.
    """
    fixed = 0
    try:
        root_info = call_tool("get_node_info", {"nodeId": root_node_id})
    except Exception as e:
        print(f"  [HARD-dedupe-hero] root info fail: {e}")
        return 0

    def find_recommend(n):
        if not isinstance(n, dict):
            return None
        nm = (n.get("name") or "").lower()
        if "recommend" in nm and "card" in nm:
            return n
        for c in n.get("children") or []:
            r = find_recommend(c)
            if r:
                return r
        return None

    card = find_recommend(root_info)
    if not card:
        return 0

    seen = {}
    to_delete = []
    def walk(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "TEXT":
            t = (node.get("characters") or "").strip()
            font_size = node.get("fontSize") or 0
            # 금액 hero 패턴: "X만원" 또는 "X,XXX,XXX원" — fontSize >= 24
            if (font_size >= 24 and "원" in t and
                any(ch.isdigit() for ch in t)):
                key = t
                if key in seen:
                    to_delete.append(node["id"])
                else:
                    seen[key] = node["id"]
        for c in node.get("children") or []:
            walk(c)
    walk(card)

    for nid in to_delete:
        try:
            call_tool("delete_node", {"nodeId": nid})
            fixed += 1
        except Exception as e:
            print(f"  [HARD-dedupe-hero] delete {nid} fail: {e}")
    if fixed:
        print(f"[HARD] Recommend Card 중복 hero 제거 {fixed}건")
    return fixed


def _HARD_strip_redundant_join_cta(root_node_id: str) -> int:
    """⚠️ 무조건 실행 (2026-05-28 사용자 분노 fix): Recommend Stage Card 안에
    동일 브랜드 CTA 가 2개 이상이면 "참여하기" (polish-injected) 를 제거.
    와이어에 명시되지 않은 CTA 자동 추가 차단.
    """
    fixed = 0
    try:
        root_info = call_tool("get_node_info", {"nodeId": root_node_id})
    except Exception as e:
        return 0

    def find_recommend(n):
        if not isinstance(n, dict):
            return None
        nm = (n.get("name") or "").lower()
        if "recommend" in nm and "card" in nm:
            return n
        for c in n.get("children") or []:
            r = find_recommend(c)
            if r:
                return r
        return None

    card = find_recommend(root_info)
    if not card:
        return 0

    # brand-solid pill 카운트
    brand_ctas = []
    def walk(node, depth=0):
        if not isinstance(node, dict):
            return
        nm = (node.get("name") or "").lower()
        # "join action strip" = polish 가 박은 "참여하기" pill 이름
        if "join action" in nm or "join-action" in nm:
            # CTA 텍스트 확인
            def has_text(n, target):
                if (n.get("type") == "TEXT" and target in (n.get("characters") or "")):
                    return True
                for c in n.get("children") or []:
                    if has_text(c, target):
                        return True
                return False
            if has_text(node, "참여하기"):
                brand_ctas.append(node["id"])
        for c in node.get("children") or []:
            walk(c, depth+1)
    walk(card)

    # "추천 전체 보기" CTA 이미 있으면 "참여하기" 는 중복 — 제거
    has_show_all = False
    def walk2(node):
        nonlocal has_show_all
        if not isinstance(node, dict):
            return
        if node.get("type") == "TEXT":
            t = node.get("characters") or ""
            if "추천 전체 보기" in t or "전체 보기" in t:
                has_show_all = True
        for c in node.get("children") or []:
            walk2(c)
    walk2(card)

    if has_show_all and brand_ctas:
        for nid in brand_ctas:
            try:
                call_tool("delete_node", {"nodeId": nid})
                fixed += 1
            except Exception as e:
                print(f"  [HARD-strip-cta] delete {nid} fail: {e}")
    if fixed:
        print(f"[HARD] Recommend Card 중복 '참여하기' CTA 제거 {fixed}건 (와이어에 없음)")
    return fixed


def _HARD_ENFORCE_IMIN_HOME_INVARIANTS(root_node_id: str) -> None:
    """⚠️ 무조건 실행 — cmd_post_fix 끝에서 호출. 사용자 명시 "룰 말고 무조건
    실행 코드" (2026-05-28).
    """
    print("\n" + "="*60)
    print("[HARD-ENFORCE] 사용자 명시 무조건 실행 룰 적용 중...")
    print("="*60)
    for fn, label in [
        (_HARD_empty_icon_circle_after_build, "Empty Icon Wrap 56×56 circle"),
        (_HARD_lounge_card_visual_after_build, "Lounge 빈 회색 카드 fix"),
        (_HARD_strip_duplicate_recommend_hero, "Recommend 중복 hero 제거"),
        (_HARD_strip_redundant_join_cta, "Recommend 중복 CTA 제거"),
    ]:
        try:
            fn(root_node_id)
        except Exception as e:
            print(f"  [HARD] {label} 실패 (무시): {e}")


def _enrich_imin_home_polish(blueprint: dict) -> None:
    """⚠️ [DEPRECATED 2026-05-28 — Refactor A] imin_home archetype 자동 polish.

    🚨 새 코드는 **unified spec** + `build_unified_blueprint()` 사용. 그쪽 generator
    (`_gen_screen_hero` / `_gen_stage_progress_card` / `_gen_subcard_cta` 등) 가
    polish baseline 을 직접 박음. 이 함수는 legacy blueprint 입력 fallback 전용 —
    cmd_build 의 `_unified_mode` 분기에서 자동 skip.

    Why (legacy 보존): 점진 마이그레이션 — 기존 손작성 blueprint 회귀 위험 차단.
    unified spec 으로 전환되면 sub-함수 7개와 함께 제거 가능.

    적용 항목:
      P1. Top Alert Banner — NavBar 다음 자동 prepend (이미 있으면 skip)
      P2. Hero Currency Screen-level — Progress Card 의 첫 currency text 를
          카드 outside 화면 hero 로 추출 (42px Bold)
      P3. Day Strip 4단계 — cell 마다 amount + status_label 자동 추가 +
          시맨틱 색 매핑 (미납=danger, 지급=success, 오늘=dark)
      P4. Sub-card CTA — Footer 직전 자동 prepend (포인트/혜택 sub-card)
      P5. Attendance dot row — 출석 banner 가 텍스트만이면 7 dots 변환

    archetype 미일치 시 무조건 no-op (다른 archetype 안전).
    """
    if not isinstance(blueprint, dict):
        return
    root_name = (blueprint.get("rootName") or blueprint.get("name") or "").lower()
    if "imin_home" not in root_name:
        return

    enrichments = []

    # 2026-05-28 시나리오 인지 (사용자 옵션 Z): 와이어 콘텐츠가 0건/0원 empty state
    # 시나리오 면 mock polish (Top Alert / Hero 0원 / Day Strip status / 포인트 CTA)
    # 비활성화 + invitation 패턴 대체. 와이어 풀데이터면 그대로 적용.
    is_empty = _detect_empty_state_scenario(blueprint)

    # P1. Top Alert Banner — 풀데이터 시나리오에서만 박음 (empty 면 skip — 모순 차단)
    if not is_empty and not _has_top_alert_banner(blueprint):
        _inject_top_alert_banner(blueprint)
        enrichments.append("Top Alert Banner")

    # P3. Day Strip 4단계 — empty state 면 status_label 박지 않음 (시맨틱 의미 없음)
    n_cells = _enrich_day_strip_full(blueprint, is_empty=is_empty)
    if n_cells:
        label = "labels skipped (empty)" if is_empty else "4-layer"
        enrichments.append(f"Day Strip {label} ({n_cells} cells)")

    # P2. Hero — empty state 면 invitation hero ("스테이지 시작하기"), 풀데이터면 currency 42px
    if not _has_screen_hero(blueprint):
        _inject_screen_hero(blueprint, is_empty=is_empty)
        enrichments.append("Screen Hero (invitation)" if is_empty else "Screen Hero (currency 42px)")

    # P4. Sub-card CTA — empty 면 invitation, 풀데이터면 포인트 사용 CTA
    if not _has_subcard_cta(blueprint):
        _inject_subcard_cta(blueprint, is_empty=is_empty)
        enrichments.append("Sub-card CTA (invitation)" if is_empty else "Sub-card CTA (Points)")

    # P5 (2026-05-28 오후 2시 빌드 baseline): Recommend Stage Card 의 hero CTA polish
    n = _polish_recommend_hero_cta(blueprint)
    if n:
        enrichments.append(f"Recommend Hero CTA (개인화 + currency brand + pill button)")

    # P6: Participation Section 의 4-card grid (status pill + progress bar)
    n = _polish_participation_grid(blueprint)
    if n:
        enrichments.append(f"Participation 4-card grid ({n} cards)")

    # P7: Lounge cards 실 상품명 + 가격 + P 사용 hint
    n = _polish_lounge_real_products(blueprint)
    if n:
        enrichments.append(f"Lounge 실 상품 ({n} cards)")

    if enrichments:
        print(f"\n🎨 [Step A.5] imin_home polish baseline injected: {', '.join(enrichments)}")
        print(f"  [feedback_imin_home_polish_baseline] catalog 적용 — 17389:51811 reference")


def _detect_empty_state_scenario(blueprint: dict) -> bool:
    """와이어 콘텐츠가 0건/0원 empty state 시나리오인지 판단 (2026-05-28 사용자 옵션 Z).

    Detection:
      1. root._wireframeContent dict 안 "0개"/"0원"/"0건"/"없어요"/"empty" 키워드 우세
      2. blueprint 안 text 노드 중 currency 텍스트 (₩/원) 가 모두 "+0원"/"-0원"/"0원"
      3. "진행중 N건" 패턴에서 N=0
    하나라도 강한 신호 있으면 empty state 로 판단.

    Why: 와이어 0건 시나리오에 "납입 기한 지난 1건" alert / "0원" 42px hero / 미납·지급
    상태 / "0P 기프티콘으로 바꿔보세요" 같은 mock polish 박는 게 콘텐츠 모순.
    풀데이터 시나리오 (수치 있음) 면 polish 그대로.
    """
    if not isinstance(blueprint, dict):
        return False

    # 1) _wireframeContent dict 검사
    wc = blueprint.get("_wireframeContent")
    if isinstance(wc, dict):
        wc_text = json.dumps(wc, ensure_ascii=False)
        empty_signals = (
            wc_text.count("0건") + wc_text.count("0개") +
            wc_text.count("0원") + wc_text.count("없어요") +
            wc_text.count("없습니다") + wc_text.count("empty")
        )
        if empty_signals >= 3:
            return True

    # 2) blueprint 안 text 노드 currency 분석
    currencies = []
    zero_currencies = 0

    def walk(n):
        nonlocal zero_currencies
        if not isinstance(n, dict):
            return
        if (n.get("type") or "").lower() == "text":
            t = n.get("text") or n.get("characters") or ""
            if "원" in t and any(c.isdigit() or c in "+-" for c in t):
                currencies.append(t)
                # "0원" / "+0원" / "-0원" 패턴
                stripped = t.replace("+", "").replace("-", "").replace(",", "").replace(" ", "")
                if stripped.startswith("0원") or stripped == "0원":
                    zero_currencies += 1
        for c in n.get("children", []) or []:
            walk(c)

    walk(blueprint)

    # currency 텍스트 ≥3 개이고 80%+ 가 0원 이면 empty state
    if len(currencies) >= 3 and zero_currencies / len(currencies) >= 0.7:
        return True

    # 3) "진행중 0건" 같은 직접 패턴
    def has_zero_count(n):
        if not isinstance(n, dict):
            return False
        if (n.get("type") or "").lower() == "text":
            t = n.get("text") or n.get("characters") or ""
            if "0건" in t or "0개" in t:
                return True
        for c in n.get("children", []) or []:
            if has_zero_count(c):
                return True
        return False

    if has_zero_count(blueprint):
        return True

    return False


def _has_node_by_name(blueprint: dict, *patterns: str) -> bool:
    pats = tuple(p.lower() for p in patterns)
    def walk(n):
        nm = (n.get("name") or "").lower()
        if any(p in nm for p in pats):
            return True
        for c in n.get("children", []) or []:
            if walk(c):
                return True
        return False
    return walk(blueprint)


def _has_top_alert_banner(bp: dict) -> bool:
    return _has_node_by_name(bp, "alert banner", "top alert", "alert-banner")


def _has_screen_hero(bp: dict) -> bool:
    return _has_node_by_name(bp, "screen hero", "screen-hero", "hero currency")


def _has_subcard_cta(bp: dict) -> bool:
    return _has_node_by_name(bp, "sub-card", "sub_card", "points card", "포인트")


def _inject_top_alert_banner(bp: dict) -> None:
    """NavBar 다음 자리에 Top Alert Banner 자동 prepend."""
    children = bp.get("children") or []
    if not children:
        return
    banner = {
        "name": "Top Alert Banner",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "fill": "$token(bg-warning-secondary)",
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "paddingLeft": 20, "paddingRight": 20,
            "paddingTop": 12, "paddingBottom": 12,
            "primaryAxisAlignItems": "SPACE_BETWEEN",
            "counterAxisAlignItems": "CENTER",
            "itemSpacing": 8,
        },
        "children": [
            {
                "name": "alert-left",
                "type": "frame",
                "layoutSizingHorizontal": "HUG",
                "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 8, "counterAxisAlignItems": "CENTER"},
                "children": [
                    {"type": "icon", "iconName": "alert-triangle", "size": 18, "iconColor": "$token(fg-warning-primary)"},
                    {"type": "text", "text": "납입 기한이 지난 1건이 있어요", "fontSize": 14, "fontName": {"family":"Pretendard","style":"SemiBold"}, "fontColor": "$token(text-primary)"},
                ],
            },
            {
                "type": "text",
                "text": "지금 납입 >",
                "fontSize": 13,
                "fontName": {"family": "Pretendard", "style": "Bold"},
                "fontColor": "$token(text-warning-primary)",
            },
        ],
    }
    # NavBar 다음 자리에 prepend (NavBar 가 첫 자식이면 [1] 자리)
    insert_idx = 0
    for i, c in enumerate(children):
        if "navbar" in (c.get("name") or "").lower() or "nav bar" in (c.get("name") or "").lower():
            insert_idx = i + 1
            break
    children.insert(insert_idx, banner)
    bp["children"] = children


def _inject_screen_hero(bp: dict, is_empty: bool = False) -> None:
    """Progress Section 위에 Screen Hero 자동 prepend.

    is_empty=True: invitation hero ("스테이지 시작하기" 큰 텍스트 + 보조 메모) —
      0원 hero 박는 모순 회피.
    is_empty=False: currency hero (42px Bold black) — 풀데이터 임팩트.
    """
    children = bp.get("children") or []
    prog_idx = None
    for i, c in enumerate(children):
        nm = (c.get("name") or "").lower()
        if "progress" in nm or "summary" in nm:
            prog_idx = i
            break
    if prog_idx is None:
        return

    if is_empty:
        # invitation hero — 0건 사용자에게 적합
        hero = {
            "name": "Screen Hero",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "layoutSizingVertical": "HUG",
            "autoLayout": {
                "layoutMode": "VERTICAL",
                "paddingLeft": 20, "paddingRight": 20,
                "paddingTop": 20, "paddingBottom": 12,
                "itemSpacing": 6,
            },
            "children": [
                {"name": "hero-caption",  "type": "text", "text": "안녕하세요 :)", "fontSize": 13, "fontName": {"family":"Pretendard","style":"Medium"}, "fontColor": "$token(text-tertiary)"},
                {"name": "hero-title",    "type": "text", "text": "오늘부터 스테이지 시작해보세요", "fontSize": 24, "fontName": {"family":"Pretendard","style":"Bold"}, "fontColor": "$token(text-primary)"},
                {"name": "hero-sub",      "type": "text", "text": "월 10만원으로 1300만원 모으기 도전", "fontSize": 13, "fontName": {"family":"Pretendard","style":"Medium"}, "fontColor": "$token(text-secondary)"},
            ],
        }
    else:
        # currency hero — 풀데이터 임팩트
        hero = {
            "name": "Screen Hero",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "layoutSizingVertical": "HUG",
            "autoLayout": {
                "layoutMode": "VERTICAL",
                "paddingLeft": 20, "paddingRight": 20,
                "paddingTop": 20, "paddingBottom": 16,
                "itemSpacing": 4,
            },
            "children": [
                {"name": "hero-caption",  "type": "text", "text": "진행 중인 스테이지 3개", "fontSize": 13, "fontName": {"family":"Pretendard","style":"Medium"}, "fontColor": "$token(text-tertiary)"},
                {"name": "hero-label",    "type": "text", "text": "모은 금액", "fontSize": 14, "fontName": {"family":"Pretendard","style":"Medium"}, "fontColor": "$token(text-secondary)"},
                {"name": "hero-amount",   "type": "text", "text": "14,420,320원", "fontSize": 42, "fontName": {"family":"Pretendard","style":"Bold"}, "fontColor": "$token(text-primary)"},
                {
                    "name": "hero-footnote",
                    "type": "frame",
                    "layoutSizingHorizontal": "FILL",
                    "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 6, "counterAxisAlignItems": "CENTER", "paddingTop": 6},
                    "children": [
                        {"name": "footnote-dot", "type": "rectangle", "width": 6, "height": 6, "cornerRadius": 3, "fill": "$token(bg-success-solid)"},
                        {"type": "text", "text": "이번 달 1,240,000원 수령했어요", "fontSize": 12, "fontName":{"family":"Pretendard","style":"Medium"}, "fontColor": "$token(text-secondary)"},
                    ],
                },
            ],
        }
    children.insert(prog_idx, hero)
    bp["children"] = children


def _enrich_day_strip_full(bp: dict, is_empty: bool = False) -> int:
    """Day Strip reference 패턴 자동 적용 (2026-05-28 사용자 reference 박힘).

    Reference 시각 패턴:
      - cell vertical stack: 요일(12px medium) / 일자(20px Bold) / 금액(12px SemiBold sign) / 상태(11px medium)
      - cell bg 시맨틱:
        * 미납: bg-error-secondary (peach) + text-error-primary
        * 오늘: bg-fg-primary-solid (dark) + fg-white
        * 납입: bg-secondary (light gray) + text-secondary/tertiary
        * 지급: bg-secondary + text-success-primary green +sign
        * 예정 (empty): bg-secondary 가벼운 + text-tertiary
      - cell cornerRadius 12, paddingTop/Bottom 12 paddingLeft/Right 14
      - Day Strip parent: HORIZONTAL, itemSpacing 8, paddingLeft 20 (peek scroll)

    is_empty=True: 모든 cell 가벼운 회색 + 오늘만 dark, status="예정"/"오늘"
    is_empty=False: 시맨틱 컬러 매핑 (미납 peach / 오늘 dark / 지급 green / 납입 gray)

    + Day Strip 위에 section title row 자동 inject ("이번 달 일정" + "미납 N" pill)
    """
    fixed = 0

    # 시나리오 별 cell spec — (status, status_color, bg_token, day_color)
    if is_empty:
        # 모든 cell 가벼운 회색, 오늘만 강조. 0원 데이터 보존.
        FULL_SPECS = [
            {"status": "예정",     "status_color": "text-tertiary", "bg": "bg-secondary",            "day_color": "text-tertiary",  "amount_color": "text-tertiary"},
            {"status": "오늘",     "status_color": "fg-white",      "bg": "bg-fg-primary-solid",     "day_color": "fg-white",       "amount_color": "fg-white"},
            {"status": "예정",     "status_color": "text-tertiary", "bg": "bg-secondary",            "day_color": "text-tertiary",  "amount_color": "text-tertiary"},
            {"status": "예정",     "status_color": "text-tertiary", "bg": "bg-secondary",            "day_color": "text-tertiary",  "amount_color": "text-tertiary"},
            {"status": "예정",     "status_color": "text-tertiary", "bg": "bg-secondary",            "day_color": "text-tertiary",  "amount_color": "text-tertiary"},
            {"status": "예정",     "status_color": "text-tertiary", "bg": "bg-secondary",            "day_color": "text-tertiary",  "amount_color": "text-tertiary"},
        ]
        unpaid_count = 0  # empty 시 미납 0
    else:
        # 풀데이터 시맨틱 매핑
        FULL_SPECS = [
            {"status": "미납",     "status_color": "text-error-primary",   "bg": "bg-error-secondary",      "day_color": "text-error-primary",  "amount_color": "text-error-primary"},
            {"status": "오늘 납입","status_color": "fg-white",             "bg": "bg-fg-primary-solid",     "day_color": "fg-white",            "amount_color": "fg-white"},
            {"status": "납입",     "status_color": "text-tertiary",        "bg": "bg-secondary",            "day_color": "text-primary",        "amount_color": "text-secondary"},
            {"status": "지급",     "status_color": "text-success-primary", "bg": "bg-secondary",            "day_color": "text-primary",        "amount_color": "text-success-primary"},
            {"status": "납입",     "status_color": "text-tertiary",        "bg": "bg-secondary",            "day_color": "text-primary",        "amount_color": "text-secondary"},
            {"status": "납입",     "status_color": "text-tertiary",        "bg": "bg-secondary",            "day_color": "text-primary",        "amount_color": "text-secondary"},
        ]
        unpaid_count = 1

    def walk(node, parent=None):
        nonlocal fixed
        nm = (node.get("name") or "").lower()
        if "day strip" in nm and isinstance(node.get("children"), list):
            # 2026-05-28 cell 겹침 fix: SPACE_BETWEEN + HUG cells 합이 부모 폭 초과 시
            # cells 가 음수 간격으로 overlap. MIN + itemSpacing 6 으로 강제 — peek scroll 의도.
            al = node.setdefault("autoLayout", {})
            al["layoutMode"] = "HORIZONTAL"
            al["primaryAxisAlignItems"] = "MIN"
            al["counterAxisAlignItems"] = "CENTER"
            # ⚠️ 2026-05-28 wrap 회귀 fix: 6 cells * 48px + 5 itemSpacing * 4 = 308 < 313 (parent w).
            # batch_build_screen 의 FILL 무시 버그 우회 — FIXED width 명시.
            al["itemSpacing"] = 4
            node["clipsContent"] = False
            cells = node.get("children")
            for i, cell in enumerate(cells):
                if i >= len(FULL_SPECS):
                    continue
                spec = FULL_SPECS[i]
                # cell 자체 bg + cornerRadius + padding 박음
                cell["fill"] = f"$token({spec['bg']})"
                cell["cornerRadius"] = 12
                al = cell.setdefault("autoLayout", {})
                al.setdefault("layoutMode", "VERTICAL")
                al["paddingTop"] = 10
                al["paddingBottom"] = 10
                al["paddingLeft"] = 4   # was 14 — 6 cells × HUG overflow 회귀 fix (2026-05-28)
                al["paddingRight"] = 4
                al["itemSpacing"] = 4
                al["counterAxisAlignItems"] = "CENTER"
                # ⚠️ FIXED 48px (2026-05-28 사용자 분노 fix): batch_build_screen 이 FILL 무시 →
                # HUG cells 합이 container 폭 초과 시 텍스트 한 글자씩 세로 wrap 회귀.
                # FIXED 48px 명시로 우회 (6 cells × 48 + 5 × 4 = 308 < 313 parent inner).
                cell["width"] = 48
                cell["layoutSizingHorizontal"] = "FIXED"
                cell["layoutSizingVertical"] = "HUG"

                # cell 안 텍스트들 정리 + reference 4단계 스택 박음
                text_kids = [c for c in (cell.get("children") or []) if (c.get("type") or "").lower() == "text"]
                if len(text_kids) < 2:
                    continue
                # 요일/일자 보존 → 컬러+사이즈 reference 매칭
                weekday = text_kids[0]
                day_num = text_kids[1]
                # ⚠️ 좁은 cell (~52px FILL) 용 fontSize 축소 (2026-05-28 wrap 회귀 fix)
                weekday["fontSize"] = 11
                weekday["fontName"] = {"family":"Pretendard","style":"Medium"}
                weekday["fontColor"] = f"$token({spec['day_color']})"
                weekday["name"] = "day-weekday"
                weekday["textAlignHorizontal"] = "CENTER"
                day_num["fontSize"] = 15  # was 20 — 좁은 cell wrap 회귀 fix
                day_num["fontName"] = {"family":"Pretendard","style":"Bold"}
                day_num["fontColor"] = f"$token({spec['day_color']})"
                day_num["name"] = "day-number"
                day_num["textAlignHorizontal"] = "CENTER"
                # 기존 cells 안 "0원" 텍스트 → amount 로 보존 (3번째 있으면)
                amount = text_kids[2] if len(text_kids) >= 3 else None
                if amount:
                    amount["fontSize"] = 10  # was 12 — 좁은 cell wrap 회귀 fix
                    amount["fontName"] = {"family":"Pretendard","style":"SemiBold"}
                    amount["fontColor"] = f"$token({spec['amount_color']})"
                    amount["name"] = "day-amount"
                    amount["textAlignHorizontal"] = "CENTER"
                # status 자식 추가 (없으면)
                has_status = any((c.get("name") or "") == "status-label" or "status" in (c.get("name") or "").lower() for c in cell.get("children", []))
                if not has_status:
                    cell.setdefault("children", []).append({
                        "type": "text",
                        "text": spec["status"],
                        "fontSize": 10,  # 좁은 cell wrap 회귀 fix (2026-05-28)
                        "fontName": {"family": "Pretendard", "style": "Medium"},
                        "fontColor": f"$token({spec['status_color']})",
                        "name": "status-label",
                        "textAlignHorizontal": "CENTER",
                    })
                fixed += 1
        for c in node.get("children", []) or []:
            walk(c, node)

    walk(bp)

    # Day Strip 위에 section title row inject (이번 달 일정 + 미납 N pill)
    if fixed > 0:
        _inject_day_strip_section_title(bp, unpaid_count=unpaid_count, is_empty=is_empty)

    return fixed


def _inject_day_strip_section_title(bp: dict, unpaid_count: int = 0, is_empty: bool = False) -> None:
    """Day Strip 위에 '이번 달 일정' section title row 자동 inject.

    좌: title "이번 달 일정" (17px Bold)
    우: "미납 N" pill (red bg) — N>0 일 때만
    """
    target_parent = None
    target_idx = None

    def find(node):
        nonlocal target_parent, target_idx
        children = node.get("children") or []
        for i, c in enumerate(children):
            if (c.get("name") or "").lower() == "day strip":
                target_parent = node
                target_idx = i
                return True
            if find(c):
                return True
        return False

    find(bp)
    if target_parent is None or target_idx is None:
        return

    # 이미 위에 section title 있으면 skip
    if target_idx > 0:
        prev = target_parent["children"][target_idx - 1]
        if "day strip" in (prev.get("name") or "").lower() and "title" in (prev.get("name") or "").lower():
            return
        # 또는 그냥 이미 title row 있으면 skip
        if "day-strip-title" in (prev.get("name") or "").lower():
            return

    title_children = [
        {"type": "text", "text": "이번 달 일정",
         "fontSize": 17, "fontName": {"family":"Pretendard","style":"Bold"},
         "fontColor": "$token(text-primary)",
         "name": "day-strip-title-text"},
    ]
    if unpaid_count > 0:
        title_children.append({
            "name": "day-strip-unpaid-pill",
            "type": "frame",
            "fill": "$token(bg-error-secondary)",
            "cornerRadius": 999,
            "autoLayout": {
                "layoutMode": "HORIZONTAL",
                "paddingLeft": 10, "paddingRight": 10,
                "paddingTop": 3, "paddingBottom": 3,
            },
            "children": [{
                "type": "text", "text": f"미납 {unpaid_count}",
                "fontSize": 11, "fontName": {"family":"Pretendard","style":"Bold"},
                "fontColor": "$token(text-error-primary)",
            }],
        })

    title_row = {
        "name": "day-strip-title",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "paddingLeft": 0, "paddingRight": 0,
            "paddingTop": 0, "paddingBottom": 8,
            "primaryAxisAlignItems": "SPACE_BETWEEN",
            "counterAxisAlignItems": "CENTER",
        },
        "children": title_children,
    }

    target_parent["children"].insert(target_idx, title_row)


def _inject_subcard_cta(bp: dict, is_empty: bool = False) -> None:
    """Footer 직전에 Sub-card CTA (내 포인트) 자동 prepend.

    is_empty=True: "포인트 모으기 시작 >" invitation CTA.
    is_empty=False: "내 포인트 12,500P / 라운지에서 기프티콘으로 바꿔보세요" — 풀데이터.
    """
    children = bp.get("children") or []
    insert_idx = None
    for i, c in enumerate(children):
        nm = (c.get("name") or "").lower()
        if "footer" in nm:
            insert_idx = i
            break
    if insert_idx is None:
        return
    sub_card = {
        "name": "Sub-card CTA",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "paddingLeft": 20, "paddingRight": 20,
            "paddingTop": 8, "paddingBottom": 16,
        },
        "children": [{
            "name": "Points Card",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "layoutSizingVertical": "HUG",
            "fill": "$token(bg-secondary)",
            "cornerRadius": 16,
            "autoLayout": {
                "layoutMode": "HORIZONTAL",
                "paddingLeft": 16, "paddingRight": 16,
                "paddingTop": 14, "paddingBottom": 14,
                "itemSpacing": 12,
                "counterAxisAlignItems": "CENTER",
                "primaryAxisAlignItems": "SPACE_BETWEEN",
            },
            "children": [
                {
                    "name": "points-left",
                    "type": "frame",
                    "layoutSizingHorizontal": "HUG",
                    "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 10, "counterAxisAlignItems": "CENTER"},
                    "children": [
                        {
                            "name": "gift-icon-wrap",
                            "type": "frame",
                            "width": 32, "height": 32,
                            "cornerRadius": 8,
                            "fill": "$token(bg-brand-primary)",
                            "autoLayout": {"layoutMode": "HORIZONTAL", "primaryAxisAlignItems": "CENTER", "counterAxisAlignItems": "CENTER", "paddingLeft": 0, "paddingRight": 0, "paddingTop": 0, "paddingBottom": 0},
                            "children": [{"type": "icon", "iconName": "gift-01", "size": 18, "iconColor": "$token(fg-brand-primary)"}],
                        },
                        {
                            "name": "points-text",
                            "type": "frame",
                            "layoutSizingHorizontal": "HUG",
                            "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 2},
                            "children": (
                                [
                                    {"type": "text", "text": "포인트 모으기 시작", "fontSize": 14, "fontName": {"family":"Pretendard","style":"Bold"}, "fontColor": "$token(text-primary)"},
                                    {"type": "text", "text": "출석 체크 + 스테이지 참여로 포인트 받기", "fontSize": 12, "fontName": {"family":"Pretendard","style":"Medium"}, "fontColor": "$token(text-tertiary)"},
                                ] if is_empty else
                                [
                                    {"type": "text", "text": "내 포인트 12,500P", "fontSize": 14, "fontName": {"family":"Pretendard","style":"Bold"}, "fontColor": "$token(text-primary)"},
                                    {"type": "text", "text": "라운지에서 기프티콘으로 바꿔보세요", "fontSize": 12, "fontName": {"family":"Pretendard","style":"Medium"}, "fontColor": "$token(text-tertiary)"},
                                ]
                            ),
                        },
                    ],
                },
                {"type": "icon", "iconName": "chevron-right", "size": 18, "iconColor": "$token(fg-tertiary)"},
            ],
        }],
    }
    children.insert(insert_idx, sub_card)
    bp["children"] = children


# ── 2026-05-28 오후 2시 빌드 baseline polish 함수 ────────────────────────────
# 사용자 명시: "적어도 오후 2시에 만든 수준까진 생성해야". 17389:51811 (저번주) +
# 오후 2시 빌드 의 두 reference 시각 패턴을 imin_home archetype 자동 baseline 으로.


def _find_node_by_name(bp: dict, *patterns):
    """이름 매칭 첫 노드 반환 (부분 일치)."""
    pats = tuple(p.lower() for p in patterns)
    def walk(n):
        nm = (n.get("name") or "").lower()
        if any(p in nm for p in pats):
            return n
        for c in n.get("children", []) or []:
            r = walk(c)
            if r:
                return r
        return None
    return walk(bp)


def _polish_recommend_hero_cta(bp: dict) -> int:
    """Recommend Stage Card 를 오후 2시 빌드 패턴 (개인화 + currency hero brand
    + inner sub-card + brand-solid pill CTA) 으로 변형.

    기존 카드 안 구조 (Steppers + Round Selector + Hero text) 를 보존하면서
    상단에 polish header 추가 + 하단에 brand-solid pill CTA 추가.
    """
    card = _find_node_by_name(bp, "Recommend Stage Card", "recommend card")
    if not card or card.get("_polished"):
        return 0

    # ⚠️ Idempotent 부분 inject (2026-05-28 사용자 명시 "skip 하지 말고 fix"):
    # 와이어 콘텐츠 인지 → polish 의 hero/CTA 중 와이어와 중복되는 것만 빼고 inject.
    # skip 전체 차단 X, 중복만 빠짐.
    existing_texts = []
    def collect_texts(n):
        if not isinstance(n, dict):
            return
        if (n.get("type") or "").lower() == "text":
            t = n.get("text") or n.get("characters") or ""
            existing_texts.append(t)
        for c in n.get("children") or []:
            collect_texts(c)
    collect_texts(card)
    has_hero_already = any(("만원" in t or "원" in t) and len(t) >= 4 for t in existing_texts)
    has_cta_already = any("전체 보기" in t or "참여하기" in t for t in existing_texts)

    # 카드 안 hero 텍스트 (currency) 찾기 — 보통 "총 1,300만원 모으기 도전" 같은
    hero_text = None
    def find_hero(n):
        nonlocal hero_text
        if (n.get("type") or "").lower() == "text":
            t = n.get("text") or n.get("characters") or ""
            if "만원" in t or "도전" in t or "모으기" in t:
                hero_text = t
                return
        for c in n.get("children", []) or []:
            find_hero(c)
    find_hero(card)
    if not hero_text:
        hero_text = "총 1,300,000원 모으기 도전, 13개월에 받아가요"

    # 카드 최상단에 polish header 추가
    # ⚠️ 부분 inject: 와이어에 hero 있으면 polish-currency (32px hero) 만 빼고 inject
    polish_header = [
        {"name": "polish-personal-caption", "type": "text", "text": "회원님을 위한 추천",
         "fontSize": 12, "fontName": {"family":"Pretendard","style":"Medium"},
         "fontColor": "$token(text-tertiary)"},
        {"name": "polish-title", "type": "text", "text": hero_text,
         "fontSize": 18, "fontName": {"family":"Pretendard","style":"Bold"},
         "fontColor": "$token(text-primary)"},
        {"name": "polish-label", "type": "text", "text": "예상 수령 금액 (1회차)",
         "fontSize": 12, "fontName": {"family":"Pretendard","style":"Medium"},
         "fontColor": "$token(text-tertiary)"},
    ]
    if not has_hero_already:
        polish_header.append({
            "name": "polish-currency", "type": "text", "text": "1,300,000원",
            "fontSize": 32, "fontName": {"family":"Pretendard","style":"Bold"},
            "fontColor": "$token(text-brand-primary)"})
    polish_header.append({
        "name": "polish-currency-sub", "type": "text",
        "text": "월 100,000원 · 13개월 · 납입 후 목표 수령",
        "fontSize": 12, "fontName": {"family":"Pretendard","style":"Medium"},
        "fontColor": "$token(text-tertiary)"})

    # brand-solid pill button (큰 CTA) — R23 swap 회피 (button/pill 단어 회피)
    cta_pill = {
        "name": "Join Action Strip",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "fill": "$token(bg-brand-solid)",
        "cornerRadius": 999,
        "autoLayout": {
            "layoutMode": "HORIZONTAL",
            "primaryAxisAlignItems": "CENTER",
            "counterAxisAlignItems": "CENTER",
            "paddingTop": 14, "paddingBottom": 14,
            "paddingLeft": 24, "paddingRight": 24,
            "itemSpacing": 8,
        },
        "children": [
            {"type": "text", "text": "참여하기", "fontSize": 16,
             "fontName": {"family":"Pretendard","style":"Bold"},
             "fontColor": "$token(fg-white)"},
            {"type": "icon", "iconName": "arrow-right", "size": 18,
             "iconColor": "$token(fg-white)"},
        ],
    }

    # 기존 children 에서 중복 hero/CTA 노드 제거 — polish-title 이 대체
    # ⚠️ broad 매칭 (2026-05-28 fix): goal hero / goal row / goal_hero / Goal_Currency 등
    existing = card.get("children") or []
    def is_dup_hero_node(c):
        nm = (c.get("name") or "").lower().replace(" ", "_").replace("-", "_")
        return "goal" in nm and ("hero" in nm or "row" in nm or "currency" in nm)
    existing = [c for c in existing if not is_dup_hero_node(c)]
    # polish header 박고 끝에 CTA 박음 — 와이어에 CTA 이미 있으면 polish CTA pill skip (중복 차단)
    if has_cta_already:
        card["children"] = polish_header + existing
        print(f"  [polish-recommend] CTA pill inject 생략 — 와이어에 이미 CTA 있음")
    else:
        card["children"] = polish_header + existing + [cta_pill]
    card["_polished"] = True
    return 1


def _polish_participation_grid(bp: dict) -> int:
    """Participation Section 의 empty state 박스를 4개 mock 스테이지 카드 grid 로 변환.

    각 카드: status pill (진행중/곧 지급/신규/예정) + 큰 금액 + subtitle + progress bar + 회차.
    """
    # ⚠️ broad 매칭 (2026-05-28 사용자 분노 fix): "Participating Wrap" / "참여 중" /
    # "Participation" 등 다양한 이름 받게 함. 이전엔 "Participation Section" 만 매칭해서
    # custom 섹션 이름 다르면 mock grid 박지 못해 모순 발생 (위 mock 데이터인데 1.6 만 empty).
    section = _find_node_by_name(
        bp, "Participation Section", "Participating Wrap",
        "Participating Section", "참여 중", "참여중",
    )
    if not section or section.get("_polished"):
        return 0

    # Empty State Stack 찾아 4-card grid 로 교체 — broad 매칭 (Empty Wrap / Empty Card / 없습니다)
    empty_stack = None
    for ch in section.get("children", []) or []:
        nm = (ch.get("name") or "").lower()
        if "empty" in nm or "없습니다" in nm or "no_stage" in nm:
            empty_stack = ch
            break
    if not empty_stack:
        # 자손에서도 찾기 (Participating Empty Wrap > Empty Card)
        def find_empty(n):
            nm = (n.get("name") or "").lower()
            if "empty" in nm:
                return n
            for c in n.get("children") or []:
                r = find_empty(c)
                if r:
                    return r
            return None
        empty_stack = find_empty(section)
    if not empty_stack:
        return 0

    MOCK_CARDS = [
        {"status": "진행중", "status_color": "bg-brand-primary", "status_text": "text-brand-primary",
         "amount": "월 10만원", "subtitle": "13개월 · 6.9%", "round": "5회차 / 13", "progress": 38, "bar_fill": "bg-brand-solid"},
        {"status": "곧 지급", "status_color": "bg-warning-secondary", "status_text": "text-warning-primary",
         "amount": "월 30만원", "subtitle": "12개월 · 5.8%", "round": "11회차 / 12", "progress": 91, "bar_fill": "bg-warning-solid"},
        {"status": "신규", "status_color": "bg-success-secondary", "status_text": "text-success-primary",
         "amount": "월 5만원", "subtitle": "6개월 · 4.5%", "round": "1회차 / 6", "progress": 16, "bar_fill": "bg-success-solid"},
        {"status": "예정", "status_color": "bg-secondary", "status_text": "text-tertiary",
         "amount": "월 20만원", "subtitle": "10개월 · 5.2%", "round": "0회차 / 10", "progress": 0, "bar_fill": "bg-tertiary"},
    ]

    def card(spec):
        return {
            "name": f"Stage Card {spec['amount']}",
            "type": "frame",
            "layoutSizingHorizontal": "FILL",
            "layoutSizingVertical": "HUG",
            "fill": "$token(bg-primary)",
            "strokeColor": "$token(border-secondary)",
            "strokeWeight": 1,
            "cornerRadius": 16,
            "autoLayout": {
                "layoutMode": "VERTICAL",
                "paddingTop": 14, "paddingBottom": 14,
                "paddingLeft": 14, "paddingRight": 14,
                "itemSpacing": 8,
            },
            "children": [
                {
                    "name": "status-pill",
                    "type": "frame",
                    "layoutSizingHorizontal": "HUG",
                    "fill": f"$token({spec['status_color']})",
                    "cornerRadius": 999,
                    "autoLayout": {
                        "layoutMode": "HORIZONTAL",
                        "paddingTop": 4, "paddingBottom": 4,
                        "paddingLeft": 10, "paddingRight": 10,
                    },
                    "children": [{"type": "text", "text": spec["status"], "fontSize": 11,
                                  "fontName": {"family":"Pretendard","style":"Bold"},
                                  "fontColor": f"$token({spec['status_text']})"}],
                },
                # 2026-05-28 회귀 fix: amount text 에 name "stage-amount" 명시 →
                # R51 _HERO_SUB_RE 의 'amount'/'stage' 매칭으로 자동 30px 승격 차단.
                # 위계: amount 18px (hero 보다 작음). 5만원만 정상이고 다른 3개 30px 박히던 사고 차단.
                {"name": "stage-amount", "type": "text", "text": spec["amount"], "fontSize": 18,
                 "fontName": {"family":"Pretendard","style":"Bold"},
                 "fontColor": "$token(text-primary)"},
                {"name": "stage-subtitle", "type": "text", "text": spec["subtitle"], "fontSize": 12,
                 "fontName": {"family":"Pretendard","style":"Medium"},
                 "fontColor": "$token(text-tertiary)"},
                {
                    "name": "progress-track",
                    "type": "frame",
                    "layoutSizingHorizontal": "FILL",
                    "layoutSizingVertical": "FIXED",
                    "height": 6,
                    "fill": "$token(bg-secondary)",
                    "cornerRadius": 3,
                    "autoLayout": {
                        "layoutMode": "HORIZONTAL",
                        "primaryAxisAlignItems": "MIN",
                        "paddingLeft": 0, "paddingRight": 0,
                        "paddingTop": 0, "paddingBottom": 0,
                    },
                    "children": [{
                        "name": "progress-fill",
                        "type": "rectangle",
                        "width": max(int(353 * spec["progress"] / 100), 6),
                        "height": 6,
                        "cornerRadius": 3,
                        "fill": f"$token({spec['bar_fill']})",
                    }],
                },
                {"type": "text", "text": spec["round"], "fontSize": 12,
                 "fontName": {"family":"Pretendard","style":"SemiBold"},
                 "fontColor": "$token(text-secondary)"},
            ],
        }

    # 2x2 grid: 2 rows × 2 cards
    grid = {
        "name": "Participation Grid",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "paddingLeft": 20, "paddingRight": 20,
            "itemSpacing": 10,
        },
        "children": [
            {
                "name": "row1",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 10},
                "children": [card(MOCK_CARDS[0]), card(MOCK_CARDS[1])],
            },
            {
                "name": "row2",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 10},
                "children": [card(MOCK_CARDS[2]), card(MOCK_CARDS[3])],
            },
        ],
    }

    # Empty State Stack 자리에 grid 삽입
    idx = section["children"].index(empty_stack)
    section["children"][idx] = grid
    section["_polished"] = True
    return 4


def _polish_lounge_real_products(bp: dict) -> int:
    """Lounge Carousel 의 카드들을 실 상품명 + 가격 + P 사용 hint 패턴으로 변환.

    icon-wrap 보존하되 아래에 가격 + brand color 포인트 사용 hint 추가.

    ⚠️ 가드 (2026-05-28 사용자 분노 fix):
    카드가 이미 imageQuery 또는 product 콘텐츠 (≥2 text + image frame) 가지면 skip.
    와이어가 이미 콘텐츠 박혀있는데 mock 으로 덮으면 imageQuery 사라지고 빈 회색 박스됨.
    """
    carousel = _find_node_by_name(bp, "Lounge Carousel")
    if not carousel or carousel.get("_polished"):
        return 0

    REAL_PRODUCTS = [
        {"name": "스타벅스 아메리카노", "price": "9,800원", "points": "8,200P 사용"},
        {"name": "베이커리 케이크",     "price": "12,000원", "points": "12,000P 사용"},
        {"name": "CGV 영화 관람권",     "price": "18,000원", "points": "16,500P 사용"},
        {"name": "올리브영 5,000원권",  "price": "5,000원",  "points": "5,000P 사용"},
        {"name": "교보문고 도서상품권", "price": "10,000원", "points": "10,000P 사용"},
    ]

    count = 0
    for i, card in enumerate(carousel.get("children", []) or []):
        if not card.get("name", "").startswith("Lounge Card"):
            continue
        if i >= len(REAL_PRODUCTS):
            break
        prod = REAL_PRODUCTS[i]

        # ⚠️ 와이어 콘텐츠 보존 (2026-05-28 사용자 분노 fix):
        # 기존 image frame (imageQuery 있는 자식) + body frame (텍스트 ≥2) 보존.
        # 빈 카드일 때만 mock 콘텐츠 새로 inject.
        existing_children = card.get("children", []) or []

        def _is_image_frame(ch):
            if not isinstance(ch, dict):
                return False
            if ch.get("imageQuery") or ch.get("imageUrl") or ch.get("image"):
                return True
            nm = (ch.get("name") or "").lower()
            return "image" in nm or "photo" in nm

        def _is_body_frame(ch):
            if not isinstance(ch, dict):
                return False
            nm = (ch.get("name") or "").lower()
            if "body" in nm:
                text_count = sum(
                    1 for g in (ch.get("children") or [])
                    if isinstance(g, dict) and (g.get("type") or "").lower() == "text"
                )
                return text_count >= 2
            return False

        has_image = any(_is_image_frame(c) for c in existing_children)
        has_body = any(_is_body_frame(c) for c in existing_children)

        if has_image and has_body:
            # 와이어 카드 그대로 보존 — polish 안 함
            continue

        # 빈 카드 → 와이어 콘텐츠 보존하면서 mock 추가
        new_children = []
        # icon-wrap / image-frame 보존
        for ch in existing_children:
            ch_name = (ch.get("name") or "").lower()
            if "icon-wrap" in ch_name or "card-icon-wrap" in ch_name or _is_image_frame(ch):
                new_children.append(ch)
        # body 가 부족하면 mock 텍스트 추가
        if not has_body:
            new_children.extend([
                {"name": "product-name", "type": "text", "text": prod["name"],
                 "fontSize": 13, "fontName": {"family":"Pretendard","style":"Bold"},
                 "fontColor": "$token(text-primary)"},
                {"name": "product-price", "type": "text", "text": prod["price"],
                 "fontSize": 12, "fontName": {"family":"Pretendard","style":"Medium"},
                 "fontColor": "$token(text-secondary)"},
                {"name": "product-points", "type": "text", "text": prod["points"],
                 "fontSize": 11, "fontName": {"family":"Pretendard","style":"SemiBold"},
                 "fontColor": "$token(text-brand-primary)"},
            ])
        card["children"] = new_children
        card.setdefault("fill", "$token(bg-primary)")
        card.setdefault("strokeColor", "$token(border-secondary)")
        card.setdefault("strokeWeight", 1)
        al = card.setdefault("autoLayout", {})
        al.setdefault("primaryAxisAlignItems", "MIN")  # SPACE_BETWEEN 폐기 — 텍스트 짤림 위험
        count += 1
    carousel["_polished"] = True
    return count


# ⚠️ 시스템 규칙 — 루트 프레임 배경색은 반드시 bg-primary
# 에이전트가 bg-secondary 등 다른 값을 넣어도 빌드 파이프라인이 무조건 교정한다.

def _enforce_root_bg_primary(blueprint: dict) -> None:
    """루트 프레임 fill을 $token(bg-primary)로 강제 (빌드 전 blueprint 교정)."""
    if not isinstance(blueprint, dict):
        return
    current = blueprint.get("fill")
    if current != "$token(bg-primary)":
        blueprint["fill"] = "$token(bg-primary)"
        print(f"[규칙] 루트 프레임 fill 강제 교정: {current!r} → $token(bg-primary)")


# 🔴 바텀시트 root = black 50% (2026-06-04 사용자): 흰 root 위 흰 시트는 radius 가 안 보여,
# root 를 dim(black 50%)으로 해 시트 모서리를 또렷하게. 절대규칙 0(root=bg-primary)의 유일 예외.
_BOTTOM_SHEET_ROOT_DIM = {"r": 0.0, "g": 0.0, "b": 0.0, "a": 0.5}


def _enforce_root_bg_primary_live(root_node_id: str, screen_type: Optional[str] = None) -> None:
    """빌드된 루트 노드의 배경을 bg-primary로 강제 (런타임 보장 — post-fix용).

    🔴 예외: bottom-sheet 는 root fill = black 50% (dim). 시트 radius 가시화 (사용자 룰).
    """
    if _is_bottom_sheet_screen_type(screen_type):
        try:
            call_tool("set_fill_color", {
                "nodeId": root_node_id,
                "r": _BOTTOM_SHEET_ROOT_DIM["r"], "g": _BOTTOM_SHEET_ROOT_DIM["g"],
                "b": _BOTTOM_SHEET_ROOT_DIM["b"], "a": _BOTTOM_SHEET_ROOT_DIM["a"],
            })
            print("  [규칙] 바텀시트 루트 배경 → black 50% (dim) 적용")
        except Exception as e:
            print(f"  [규칙] 바텀시트 루트 dim 설정 실패 (무시): {e}")
        return
    rgba = resolve_token_ref("$token(bg-primary)") or {"r": 0.988, "g": 0.988, "b": 0.992, "a": 1.0}
    try:
        call_tool("set_fill_color", {
            "nodeId": root_node_id,
            "r": rgba["r"], "g": rgba["g"], "b": rgba["b"], "a": rgba.get("a", 1.0),
        })
    except Exception as e:
        print(f"  [규칙] 루트 fill 리터럴 설정 실패 (무시): {e}")
    fp = _token_to_figma_path("bg-primary")
    if fp:
        try:
            call_tool("set_bound_variables", {
                "nodeId": root_node_id,
                "bindings": {"fills/0": fp},
            })
            print("  [규칙] 루트 프레임 배경 → bg-primary 강제 적용 완료")
        except Exception as e:
            print(f"  [규칙] 루트 bg-primary 변수 바인딩 실패 (무시): {e}")


_NAVBAR_NAME_HINTS = ("navbar", "nav bar", "app bar", "appbar", "top bar",
                      "topbar", "header bar", "nav header")


# 🔴 NavBar 좌측 back 버튼 노출 시 Nav Back frame 오른쪽 padding 표준 (2026-06-10 사용자 룰).
# back↔타이틀 간격을 spacing-xl(16) 토큰으로 통일·바인딩.
_NAV_BACK_PAD_RIGHT = 16
_NAV_BACK_PAD_TOKEN = "spacing-xl"


def _enforce_navbar_style_live(root_node_id: str) -> int:
    """절대 규칙 (2026-06-04 사용자): 상단 NavBar 스타일 강제.
      1. NavBar frame fill = bg-primary (리터럴 + 변수 바인딩)
      1-b. NavBar frame 자체 stroke 없어야 함 (제거)
      2. NavBar 안 좌측 back btn frame 은 stroke 없어야 함 (제거)
      3. back btn frame 오른쪽 padding = spacing-xl(16) 바인딩 (2026-06-10) — back↔타이틀 간격 표준
    """
    nav_bg = resolve_token_ref("$token(bg-primary)") or {"r": 0.988, "g": 0.988, "b": 0.992, "a": 1.0}
    nav_fp = _token_to_figma_path("bg-primary")
    fixed = [0]

    def _is_back_btn(n):
        if (n.get("type") or "").upper() != "FRAME":
            return False
        nm = (n.get("name") or "").lower()
        if any(w in nm for w in ("back", "뒤로")):
            return True
        # 좌향 화살표 아이콘만 든 프레임 = back 버튼 (이름 변형에 견고하도록 넓게 매칭)
        _LEFT_ARROW = ("chevron-left", "arrow-left", "arrow-narrow-left",
                       "arrow-circle-left", "caret-left", "chevron-circle-left")
        for ch in (n.get("_children_full") or n.get("children") or []):
            inm = (ch.get("name") or "").lower()
            icn = (ch.get("iconName") or "").lower()
            if any(a in inm for a in _LEFT_ARROW) or any(a in icn for a in _LEFT_ARROW):
                return True
        return False

    def walk(n):
        if not isinstance(n, dict):
            return
        nm = (n.get("name") or "").lower()
        if (n.get("type") or "").upper() == "FRAME" and (n.get("layoutMode") or "").upper() == "HORIZONTAL" \
                and any(h in nm for h in _NAVBAR_NAME_HINTS):
            # 1. NavBar fill = bg-primary
            try:
                call_tool("set_fill_color", {"nodeId": n["id"], "r": nav_bg["r"], "g": nav_bg["g"],
                                             "b": nav_bg["b"], "a": nav_bg.get("a", 1.0)})
                if nav_fp:
                    call_tool("set_bound_variables", {"nodeId": n["id"], "bindings": {"fills/0": nav_fp}})
                fixed[0] += 1
            except Exception as e:
                print(f"  [navbar] fill 실패(무시): {e}")
            # 1-b. NavBar frame 자체 stroke 제거 (2026-06-04 사용자 추가)
            try:
                call_tool("set_stroke_color", {"nodeId": n["id"], "r": 0, "g": 0, "b": 0,
                                               "a": 0, "strokeWeight": 0})
            except Exception as e:
                print(f"  [navbar] frame stroke 제거 실패(무시): {e}")
            # 2. 좌측 back btn stroke 제거 (NavBar 서브트리 전체에서 탐색 — 중첩 허용)
            def _strip_back(node):
                for ch in (node.get("_children_full") or node.get("children") or []):
                    if _is_back_btn(ch):
                        try:
                            call_tool("set_stroke_color", {"nodeId": ch["id"], "r": 0, "g": 0,
                                                           "b": 0, "a": 0, "strokeWeight": 0})
                            fixed[0] += 1
                        except Exception as e:
                            print(f"  [navbar] back btn stroke 제거 실패(무시): {e}")
                        # 🔴 2026-06-10 사용자 룰: NavBar 좌측 back 버튼 노출 시 Nav Back frame
                        # 오른쪽 padding = spacing-xl(16) 로 설정 + 토큰 바인딩 (back↔타이틀 간격 표준).
                        try:
                            call_tool("set_auto_layout", {
                                "nodeId": ch["id"],
                                "layoutMode": (ch.get("layoutMode") or "HORIZONTAL"),
                                "paddingRight": _NAV_BACK_PAD_RIGHT})
                            call_tool("set_bound_variables", {
                                "nodeId": ch["id"], "bindings": {"paddingRight": _NAV_BACK_PAD_TOKEN}})
                            fixed[0] += 1
                        except Exception as e:
                            print(f"  [navbar] back btn paddingRight 실패(무시): {e}")
                    else:
                        _strip_back(ch)
            _strip_back(n)
        for ch in (n.get("_children_full") or n.get("children") or []):
            walk(ch)

    try:
        walk(_collect_tree(root_node_id))
    except Exception as e:
        print(f"  [navbar] 트리 수집 실패(무시): {e}")
    if fixed[0]:
        print(f"  [navbar] ✓ NavBar bg-primary + back btn stroke 제거 ({fixed[0]}건)")
    return fixed[0]


# ── 색상 + 폴리시 규칙 (회사 피드백 2026-05-22, 2026-05-23 재조정) ──────────
# 브랜드 컬러는 절제된 단일 액센트, 피드백 컬러는 진짜 상태 정보에만 소량.
# 평면 그레이 박스 나열은 와이어프레임처럼 보이므로 카드에 입체감을 강제한다.
_COLOR_FIELDS = ("fill", "fontColor", "iconColor", "stroke")
_FEEDBACK_KEYWORDS = ("success", "warning", "error")


def _token_name_of(value) -> Optional[str]:
    if isinstance(value, str) and value.startswith("$token(") and value.endswith(")"):
        return value[7:-1].strip()
    return None


# Modal 패턴 — 상단 X만, Footer·Tab Bar·상단 탭 메뉴·기타 nav 아이콘 제거
_MODAL_DISALLOWED_NAME_PARTS = ("footer", "tab bar", "tabbar",
                                "tab row", "top tab", "section tab")
_MODAL_NAV_NONX_PARTS = ("logo", "bell", "chat", "alarm", "알림", "채팅",
                         "message", "search", "검색")


_BOTTOM_SHEET_DIM_FILL = {
    "type": "SOLID",
    "color": {"r": 0, "g": 0, "b": 0},
    "opacity": 0.5,
}


def _enforce_bottom_sheet_pattern(blueprint: dict) -> None:
    """Bottom Sheet Modal 기본형 패턴 강제 (2026-05-27 사용자 지시).

    **Why:** Modal 기본형은 화면 세로 절반 정도로 표시되고, 뒤에 원래 화면 위 dimmed
    overlay 가 깔린 채 bottom 에 붙어서 보여진다. 단순히 콘텐츠만 가운데 그리면
    modal 의 시각적 컨텍스트(dim + bottom anchor) 가 표현 안 됨.

    Blueprint root 에 `_screenType: "bottom-sheet"` 명시 시 작동:
    - Root: 852 FIXED (디바이스 viewport)
    - 1st child: **Dim Overlay** (FILL, fill=alpha-black 50%) — height auto-grow 로 위쪽
      가용 공간 채움. 뒤 원래 화면을 어둡게 가린 효과.
    - 2nd child: **Modal Sheet** (FILL, HUG, bg-primary, top-rounded 24) — 콘텐츠 wrap.
    - Modal 안 콘텐츠는 자동 추출 (root.children 중 Dim 외 노드들 모두 Modal Sheet 안으로).

    빌드 후 결과: 뒤 dim + 하단 흰 sheet (top rounded) + 콘텐츠.

    **Full Modal 과 구분:** `_screenType: "modal"` 은 기존 full modal 패턴 (X만, footer
    제거). bottom-sheet 는 더 가벼운 modal 기본형 (dim + 반 화면).
    """
    if not isinstance(blueprint, dict):
        return
    st = (blueprint.get("_screenType") or blueprint.get("screenType") or "").lower()
    if st not in ("bottom-sheet", "bottomsheet", "sheet"):
        return

    children = blueprint.get("children") or []
    if not isinstance(children, list) or not children:
        return

    # 이미 wrap 적용된 경우 (Dim Overlay + Modal Sheet) skip — idempotent
    names = [(c.get("name") or "") for c in children if isinstance(c, dict)]
    if "Dim Overlay" in names and "Modal Sheet" in names:
        return

    # 콘텐츠를 Modal Sheet 로 wrap. Status Bar 가 있으면 그것만 유지하고 나머지 wrap.
    status_bar_child = None
    modal_kids = []
    for c in children:
        if not isinstance(c, dict):
            continue
        if "status bar" in (c.get("name") or "").lower():
            status_bar_child = c
        else:
            modal_kids.append(c)

    # 🔴 2026-06-04 사용자: root fill = black 50%(dim) 로 통일 → Dim Overlay 는 색 없는
    # FILL 스페이서(투명). 시트를 하단으로 미는 역할만. (root 가 dim 을 제공하므로 이중 dim 방지.)
    dim = {
        "name": "Dim Overlay",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "FILL",
        "fills": [],
    }
    modal = {
        "name": "Modal Sheet",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "fill": "$token(bg-primary)",
        # 🔴 절대규칙 (2026-06-04 사용자): bottom sheet 상단 모서리 radius = 16.
        "topLeftRadius": 16,
        "topRightRadius": 16,
        "bottomLeftRadius": 0,
        "bottomRightRadius": 0,
        # 🔴 절대규칙 (2026-06-04 사용자): radius 있는 frame 은 꼭 clipsContent=true.
        "clipsContent": True,
        # 🔴 2026-04 사용자: 콘텐츠 가로 padding 20 은 시트가 갖는다 (시트는 풀폭, 안쪽 20 인셋).
        # 🔴 2026-06-10 사용자: 시트 상단 padding = 8(spacing-md). 핸들이 상단에 타이트하게 붙는다
        #    (기존 12 → 8). paddingBottom 24(safe area) 와 의도적 비대칭이므로 _asymPad 마커로
        #    symmetric-vpad enforcer(pt==pb 강제) 를 우회한다. itemSpacing 18 로 섹션 간격.
        "_asymPad": True,
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "itemSpacing": 18,
            "paddingTop": 8, "paddingBottom": 24,
            "paddingLeft": 20, "paddingRight": 20,
        },
        "children": modal_kids,
    }

    new_children = []
    if status_bar_child is not None:
        new_children.append(status_bar_child)
    new_children.extend([dim, modal])
    blueprint["children"] = new_children

    # 🔴 Root: 852 FIXED (시트 하단 고정) + **상하좌우 padding 0** (2026-06-04 사용자:
    # "root frame 위아래 padding값은 필요없어"). 시트가 root 와 동일한 풀폭 + 바닥에 완전 밀착
    # (root paddingBottom 이 있으면 시트 아래 dim 띠가 생김). 콘텐츠 인셋(가로 20·하단 safe
    # area 24)은 Modal Sheet 가 가진다.
    blueprint["height"] = 852
    blueprint["layoutSizingVertical"] = "FIXED"
    blueprint["width"] = 393
    _root_al = blueprint.get("autoLayout")
    if isinstance(_root_al, dict):
        _root_al["paddingLeft"] = 0
        _root_al["paddingRight"] = 0
        _root_al["paddingTop"] = 0
        _root_al["paddingBottom"] = 0
        _root_al["itemSpacing"] = 0

    print(f"[규칙] Bottom Sheet 패턴 강제 — Dim Overlay + Modal Sheet wrap "
          f"({len(modal_kids)}개 자식을 Modal Sheet 안으로)")


def _enforce_radius_clip_blueprint(blueprint: dict) -> None:
    """🔴 절대규칙 (2026-06-04 사용자): radius 값이 있는 frame 은 꼭 clipsContent=true.

    "frame에 radius 값을 넣으면 꼭!! Clip content 옵션 체크가 되어야 한다."

    **Why 라이브 enforcer 만으론 부족** — Modal Sheet 처럼 **개별 코너 radius**(topLeftRadius
    등)를 쓰는 frame 은 `get_nodes_info` 가 코너 값을 None 으로 직렬화해 라이브 검출이 안 된다.
    blueprint 단계 값은 정확하므로 여기서 박는다 — batch_build 가 `spec.clipsContent` 를 반영.

    대상: cornerRadius>0 또는 개별 코너(top/bottom Left/Right Radius)>0 인 frame.
    제외: instance(master 제어). clipsContent 가 이미 명시돼 있으면 존중(명시적 false 도 유지).
    """
    if not isinstance(blueprint, dict):
        return
    touched = [0]

    def _has_radius(n: dict) -> bool:
        cr = n.get("cornerRadius")
        if isinstance(cr, (int, float)) and cr > 0:
            return True
        for k in ("topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius"):
            v = n.get(k)
            if isinstance(v, (int, float)) and v > 0:
                return True
        return False

    def walk(n):
        if not isinstance(n, dict):
            return
        t = (n.get("type") or "frame").lower()
        if t in ("frame", "") and _has_radius(n) and n.get("clipsContent") is None:
            n["clipsContent"] = True
            touched[0] += 1
        for c in n.get("children", []) or []:
            walk(c)

    walk(blueprint)
    if touched[0]:
        print(f"[규칙] radius>0 frame {touched[0]}건 → clipsContent=true (blueprint 강제)")


def _enforce_modal_pattern(blueprint: dict) -> None:
    """Modal 화면 패턴 강제 — 상단 X만, Footer·Tab Bar·기타 nav 아이콘 제거 (2026-05-24).

    Blueprint root 에 `_screenType: "modal"` 명시 시 작동. Full modal 은:
    - 상단 헤더: X 닫기 버튼만 (로고·알림·채팅 등 nav 아이콘 없음)
    - Footer·Tab Bar 없음 (홈 위로 슬라이드업되는 단일 화면)
    - NavBar 우측 정렬(MAX) 로 X 가 우측 상단에 위치
    """
    if not isinstance(blueprint, dict):
        return
    st = (blueprint.get("_screenType") or blueprint.get("screenType") or "").lower()
    if st != "modal":
        return

    removed = [0]

    def strip(node, in_navbar):
        is_navbar = any(p in (node.get("name") or "").lower() for p in ("navbar", "nav bar"))
        in_navbar_now = in_navbar or is_navbar
        kids = node.get("children")
        if not isinstance(kids, list):
            return
        keep = []
        for c in kids:
            nm = (c.get("name") or "").lower()
            if any(d in nm for d in _MODAL_DISALLOWED_NAME_PARTS):
                removed[0] += 1
                continue
            if in_navbar_now and any(p in nm for p in _MODAL_NAV_NONX_PARTS):
                removed[0] += 1
                continue
            keep.append(c)
        node["children"] = keep
        for c in keep:
            strip(c, in_navbar_now)

    strip(blueprint, False)

    # NavBar 찾아서 우측 정렬 (X 가 우측 상단에 위치)
    def find_navbar(node):
        if any(p in (node.get("name") or "").lower() for p in ("navbar", "nav bar")):
            return node
        for c in node.get("children", []) or []:
            r = find_navbar(c)
            if r:
                return r
        return None

    nav = find_navbar(blueprint)
    if nav:
        al = nav.get("autoLayout") or {}
        al["layoutMode"] = al.get("layoutMode") or "HORIZONTAL"
        al["primaryAxisAlignItems"] = "MAX"
        nav["autoLayout"] = al

    if removed[0]:
        print(f"[규칙] Modal 패턴 강제 — Footer/Tab Bar/non-X nav 노드 {removed[0]}건 제거 (X 닫기만 유지)")


# 정보 그룹 divider — 루트 위 섹션 사이에 가는 라인을 넣어 그룹 시각 구분
# (Status Bar / NavBar / Action Bar / Tab Bar / Footer 같은 utility 프레임은 제외)
_DIVIDER_UTIL_PARTS = ("status bar", "navbar", "nav bar", "tab bar", "tabbar",
                       "action bar", "footer", "tab row", "top tab", "section tab")


def _enforce_tooltip_ignore_auto_layout(blueprint: dict) -> None:
    """Tooltip 류 노드는 ignore auto layout (layoutPositioning=ABSOLUTE) 강제 (2026-05-24 룰).

    "궁금한 건 물어보세요" 같은 floating tooltip은 부모 normal flow를 차지하면 안 된다 —
    인접 콘텐츠 위에 떠 있는 hint. 이름에 'tooltip'/'tooltip wrap'/'tooltip row'가 들어간
    노드 (또는 그 자식)를 자동으로 ABSOLUTE로 표시.

    blueprint 단계에서 표시하고, 실제 좌표는 post-fix가 부모 width 안에서 자동 배치.
    """
    found = 0

    def walk(node):
        nonlocal found
        if not isinstance(node, dict):
            return
        name = (node.get("name") or "").lower()
        # tooltip / tooltip wrap / tooltip row → 자체를 ABSOLUTE로
        if "tooltip" in name and node.get("layoutPositioning") != "ABSOLUTE":
            node["layoutPositioning"] = "ABSOLUTE"
            found += 1
        for c in node.get("children") or []:
            walk(c)

    walk(blueprint)
    if found:
        print(f"[규칙] Tooltip ignore auto layout — {found}개 노드 ABSOLUTE 처리")


def _enforce_section_dividers(blueprint: dict) -> None:
    """⛔ 2026-05-27 폐기 — 사용자 명시: 섹션 사이에 divider 라인 자동 삽입 금지.

    "frame에 border를 추가하라니깐 엉뚱하게 섹션 사이에 선을 넣고있냐!!!" (2026-05-27).
    정보 그룹 경계는 **카드 자체의 border** 로 표현 — [[feedback_no_drop_shadow]]
    + `_enforce_white_card_border` 가 담당.

    기존 blueprint 에 "Section Divider" 노드가 명시되어 있어도 제거 (입력 무시).
    """
    removed = [0]

    def walk(node):
        if not isinstance(node, dict):
            return
        ch = node.get("children")
        if isinstance(ch, list):
            new_ch = []
            for c in ch:
                name = (c.get("name") if isinstance(c, dict) else "") or ""
                if "divider" in name.lower() and "section" in name.lower():
                    removed[0] += 1
                    continue
                new_ch.append(c)
            node["children"] = new_ch
            for c in new_ch:
                walk(c)

    walk(blueprint)
    if removed[0]:
        print(f"[규칙] Section Divider 폐기 — blueprint 의 divider 노드 {removed[0]}건 제거 (2026-05-27 룰)")
    return

    # ↓↓ 아래 코드는 폐기됨 (참조용으로 남김, 실행 안 됨) ↓↓
    children = blueprint.get("children")
    if not isinstance(children, list) or len(children) < 2:
        return

    def is_util(node):
        return any(p in (node.get("name") or "").lower() for p in _DIVIDER_UTIL_PARTS)

    def is_divider(node):
        return "divider" in (node.get("name") or "").lower()

    def has_heading(node):
        """섹션 안에 fontSize ≥ 17 인 TEXT 가 깊이 3 안에 있으면 '타이틀 섹션'."""
        if not isinstance(node, dict):
            return False
        stack = [(node, 0)]
        while stack:
            n, d = stack.pop()
            if d > 3 or not isinstance(n, dict):
                continue
            for c in (n.get("children") or []):
                if not isinstance(c, dict):
                    continue
                if (c.get("type") or "").lower() == "text":
                    fs = c.get("fontSize")
                    if isinstance(fs, (int, float)) and fs >= 17:
                        return True
                else:
                    stack.append((c, d + 1))
        return False

    def zero_padding_top(node):
        """섹션의 autoLayout.paddingTop 을 0 으로 (divider padding 과 겹침 방지)."""
        al = node.get("autoLayout")
        if isinstance(al, dict):
            al["paddingTop"] = 0
        elif node.get("paddingTop"):
            node["paddingTop"] = 0

    def zero_padding_bottom(node):
        """섹션의 autoLayout.paddingBottom 을 0 으로 (divider 와 위 섹션 사이 갭 정리)."""
        al = node.get("autoLayout")
        if isinstance(al, dict):
            al["paddingBottom"] = 0
        elif node.get("paddingBottom"):
            node["paddingBottom"] = 0

    new_children = []
    inserted = 0
    has_seen_title = False
    for c in children:
        is_section = not is_util(c) and not is_divider(c)
        # divider 삽입 조건: title-heading 보유 섹션 + 이미 다른 title 섹션을 거친 뒤
        # (첫 title 섹션 앞에는 divider 없음 — 화면 첫 정보 그룹은 자연스럽게 시작)
        if is_section and has_heading(c) and has_seen_title and (not new_children or not is_divider(new_children[-1])):
            # divider 는 위·아래 padding 20px 컨테이너 안의 1px 라인 — 콘텐츠와 띄워서 보이게
            new_children.append({
                "name": "Section Divider",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "HUG",
                "autoLayout": {
                    "layoutMode": "VERTICAL",
                    "paddingTop": 20, "paddingBottom": 20,
                    "paddingLeft": 0, "paddingRight": 0,
                    "itemSpacing": 0,
                },
                # fill 생략 = 투명 (batch_build_screen이 "transparent" 문자열을 검정으로 fallback하는 이슈 회피)
                "children": [{
                    "name": "Divider Line",
                    "type": "frame",
                    "layoutSizingHorizontal": "FILL",
                    "height": 1,
                    "fill": "$token(border-secondary)",
                }],
            })
            inserted += 1
            zero_padding_top(c)  # 아래 섹션 paddingTop=0
            # 위 섹션 paddingBottom=0 — divider 양쪽 갭이 divider padding(20+20)만으로 결정되도록
            for prev in reversed(new_children[:-1]):
                if not is_divider(prev) and not is_util(prev):
                    zero_padding_bottom(prev)
                    break
        new_children.append(c)
        if is_section and has_heading(c):
            has_seen_title = True
    blueprint["children"] = new_children
    if inserted:
        print(f"[규칙] 섹션 divider 자동 삽입 — {inserted}건 (타이틀 섹션 앞 + 위·아래 20px, 아래 섹션 paddingTop=0)")


def _enforce_color_restraint(blueprint: dict) -> None:
    """색상 사용 advisory (2026-05-23 정책).

    브랜드 컬러는 절제된 단일 액센트, 피드백 컬러는 진짜 상태 정보에만 소량.
    정책이 미묘해 자동 치환은 하지 않는다 — 과거 강제 치환(피드백 제거 + 브랜드
    ≤2)이 화면을 완전 무채색 와이어프레임처럼 만들어 제거됨. 사용량을 집계해
    로그로 보고하고, 0이거나 과다하면 경고한다.
    """
    counts = {"brand": 0, "feedback": 0, "aqua": 0}

    def walk(node):
        if not isinstance(node, dict):
            return
        for field in _COLOR_FIELDS:
            name = _token_name_of(node.get(field))
            if not name:
                continue
            low = name.lower()
            if any(k in low for k in _FEEDBACK_KEYWORDS):
                counts["feedback"] += 1
            elif "aqua" in low:
                counts["aqua"] += 1
            elif "brand" in low:
                counts["brand"] += 1
        for child in node.get("children", []) or []:
            walk(child)

    walk(blueprint)
    print(f"[색상] 브랜드 액센트 {counts['brand']}곳 · Aqua {counts['aqua']}곳 · "
          f"상태 컬러 {counts['feedback']}곳")
    if counts["brand"] == 0:
        print("  ⚠️  브랜드 액센트 0곳 — 완전 무채색은 와이어프레임처럼 보임. "
              "주 액션·active 등에 브랜드 컬러를 단일 액센트로 줄 것.")
    # 🔴 2026-06-05 사용자 룰 (정책 재반전): "이젠 아쿠아 컬러 사용을 자제하도록".
    # 2026-06-02 의 'Aqua 보조 액센트 권장' 을 폐기 — 이제 Aqua 사용 시 자제 권고.
    if counts["aqua"] > 0:
        print(f"  ⚠️  Aqua {counts['aqua']}곳 사용 — 사용자 룰(2026-06-05): Aqua 컬러 사용을 자제할 것. "
              "브랜드 퍼플(주 액센트) + 상태색(진짜 상태에만) 위주로, Aqua 는 꼭 필요한 경우가 아니면 "
              "중립(bg-secondary/text-secondary) 또는 brand tint(bg-brand-secondary/text-brand-primary)로 대체.")
    if counts["feedback"] > 8:
        print(f"  ⚠️  상태 컬러 {counts['feedback']}곳 — 진짜 상태 정보(미납·완료 등)에만 "
              "절제 사용할 것. 장식·태그·통계 전반에 색을 까는 건 금지.")


# 그레이로 채운 카드 fill — 카드 표면 규칙(2026-05-23)에서 bg-primary+보더로 교정 대상
_GREY_CARD_FILLS = ("bg-secondary", "bg-tertiary")
# 보더 관련 키 — Footer 예외 처리에서 일괄 제거
_STROKE_KEYS = ("stroke", "strokes", "strokeWeight", "strokeTopWeight",
                "strokeBottomWeight", "strokeLeftWeight", "strokeRightWeight")


# 세로 패딩 대칭 강제 — 의도적 비대칭만 허용할 frame 이름(상하 다른 게 자연스러운 chrome/특수)
_ASYM_PAD_EXEMPT_NAME_KW = (
    "navbar", "nav bar", "app bar", "top bar", "header bar", "status bar", "status ribbon",
    "ribbon", "hero", "tab bar", "tabbar", "fab", "wallet", "footer",
    "button", "btn", "cta", "submit", "banner", "carousel", "stepper",
)


def _enforce_symmetric_vpad(blueprint: dict) -> None:
    """컨테이너 frame 의 세로 패딩 비대칭(paddingTop != paddingBottom) 자동 교정 (2026-06-05 사용자 룰).

    사용자: *"특별한 이유 없는 비대칭을 하지 못하도록 규칙을 만들어라."* — 무의식적으로 상/하
    padding 을 다르게 박던 회귀(Content pt=12/pb=24, Hero pt=16/pb=12 등) 차단. **세로 패딩은
    기본 대칭(pt==pb)**, 비대칭이 정말 필요하면 노드에 `"_asymPad": true` 마커를 박아야 한다.

    🔻 2026-06-15 fill-in-only/advisory 로 강등 (사용자 룰: 콘텐츠 영역 간격을 창의적으로):
    비대칭 세로 패딩은 **디자인 도구**(리듬·강조)일 수 있으므로 더는 강제 교정하지 않는다.
    - 작은 비대칭(차이 ≤ 4px)은 무의식적 오타일 가능성이 커서 max 로 fill-in 교정(가독성 보존).
    - 큰 비대칭(차이 > 4px)은 의도로 보고 **존중**(advisory WARN 만 — 의도면 _asymPad 로 침묵).
    대상: autoLayout VERTICAL + 자식 2개 이상 컨테이너. DS 인스턴스·chrome/특수 이름 제외.
    (가로 pl/pr 은 캐로셀 peek 등 정당한 비대칭이 많아 건드리지 않음 — 세로만.)"""
    fixed = [0]

    def walk(n):
        if not isinstance(n, dict):
            return
        if (n.get("type") in (None, "frame", "FRAME")) and n.get("_asymPad") is not True:
            al = n.get("autoLayout")
            nm = (n.get("name") or "").lower()
            kids = n.get("children") or []
            if (isinstance(al, dict) and (al.get("layoutMode") or "").upper() == "VERTICAL"
                    and len(kids) >= 2 and not any(k in nm for k in _ASYM_PAD_EXEMPT_NAME_KW)):
                pt = al.get("paddingTop", 0) or 0
                pb = al.get("paddingBottom", 0) or 0
                if isinstance(pt, (int, float)) and isinstance(pb, (int, float)) and pt != pb:
                    if abs(pt - pb) <= 4:
                        # 작은 차이 = 무의식적 오타 → fill-in 교정
                        m = max(pt, pb)
                        al["paddingTop"] = m
                        al["paddingBottom"] = m
                        fixed[0] += 1
                    else:
                        # 큰 비대칭 = 의도된 디자인 → 존중(advisory). 의도면 _asymPad 로 침묵.
                        print(f"[스타일-기본값] '{n.get('name')}' 세로 패딩 비대칭 "
                              f"(pt={pt}/pb={pb}) — author 의도 존중(교정 안 함). "
                              f"무의식적이면 대칭 권장, 의도면 _asymPad 마커로 침묵.")
        for c in (n.get("children") or []):
            walk(c)
    walk(blueprint)
    if fixed[0]:
        print(f"[규칙] 세로 패딩 미세 비대칭(≤4px) 교정 {fixed[0]}건 (큰 비대칭은 존중)")


# 규칙 13 — '중요 섹션' 이름 패턴 (구 lint 용, 2026-06-18 lint 폐기 후 미사용/참조용).
# 🔻 2026-06-18: 중요 섹션을 bg-secondary 밴드로 강제하던 룰 삭제 — 밴드 여부·색은 작성자 자율.
_BAND_IMPORTANT_NAME_KW = (
    "목돈 만들기", "목돈만들기", "시작 유도", "start guide",
    "스테이지 현황", "현황 섹션", "stage status",
    "추천 스테이지", "추천 섹션", "recommend section", "recommend stage",
)
# 밴드로 강제하지 않는(보조) 섹션 — 이름이 위 패턴과 겹쳐도 제외 (총 스테이지 수 ribbon 등)
_BAND_IMPORTANT_EXCLUDE_KW = ("ribbon", "status bar", "total", "summary")


def _is_home_blueprint(blueprint: dict) -> bool:
    nm = ((blueprint.get("rootName") or "") + " " + (blueprint.get("name") or "")).lower()
    return any(k in nm for k in ("home", "메인", "main dashboard", "main_home"))


def _enforce_section_band(blueprint: dict) -> None:
    """_band 섹션 = 풀폭(FILL) **구조만** 표준화. 🔻 2026-06-18 색 강제 전면 삭제 (사용자 결정).

    🔴 사용자 명시(2026-06-18): *"중요 섹션 frame fill color 를 bg-secondary 로 고정하는 건 삭제하고,
    자율적으로 판단해서 넣거나 primary 를 쓰거나 하는 걸로. 섹션 안 블록을 꼭 secondary 로 채울
    필요는 없어."*

    구 동작(삭제): ① `_band` 섹션 fill 이 없으면 bg-secondary 로 강제. ② 밴드 내부 sub-card 의
    bg-secondary fill 을 bg-primary(흰)로 흰색화 + 보더. → **둘 다 폐기.** 밴드 fill·내부 블록 fill
    같은 **색은 전적으로 작성자가 자율 판단**한다(bg-primary / bg-secondary / brand-tint / 무fill 등).

    이 함수는 이제 **구조만** 표준화: `_band` → 풀폭 `layoutSizingHorizontal=FILL` + 좌우/상하 padding
    fill-in(미지정일 때만). **fill·보더·내부 색은 건드리지 않는다(author 존중).** lint(밴드 nudge)도 제거.
    ⚠️ 풀폭이 되려면 좌우 padding 있는 프레임 안에 두면 안 된다(content 의 가로 padding 0 또는 root 직계).
    """
    cnt = [0]

    def walk(n):
        if not isinstance(n, dict):
            return
        if n.get("_band") is True and (n.get("type") or "frame") in ("frame", "FRAME"):
            # 색은 손대지 않는다 (fill 없으면 없는 대로 = 작성자 의도). 구조만 풀폭 FILL.
            n["layoutSizingHorizontal"] = "FILL"
            al = n.get("autoLayout")
            if not isinstance(al, dict):
                al = {"layoutMode": "VERTICAL", "itemSpacing": 0}
                n["autoLayout"] = al
            al.setdefault("layoutMode", "VERTICAL")
            # 패딩은 fill-in-only — author 명시값 존중, 미지정(0/None)일 때만 기본값.
            if not al.get("paddingTop"):
                al["paddingTop"] = 24
            if not al.get("paddingBottom"):
                al["paddingBottom"] = 24
            if not al.get("paddingLeft"):
                al["paddingLeft"] = 20
            if not al.get("paddingRight"):
                al["paddingRight"] = 20
            cnt[0] += 1
        for c in (n.get("children") or []):
            walk(c)
    walk(blueprint)
    if cnt[0]:
        print(f"[규칙] _band 섹션 풀폭 구조 표준화 {cnt[0]}건 "
              f"(FILL + padding fill-in; 색·내부 블록 fill 은 author 자율 — 강제 안 함)")

    # 🔻 2026-06-18 밴드 nudge lint 제거 — 어느 섹션을 강조/밴드/색 처리할지는 작성자 자율.
    if False:  # (구 규칙13-INFO lint 폐기, 하위 호환 위해 블록만 비활성)
        missing = []

        def lint(n, in_band=False):
            if not isinstance(n, dict):
                return
            nm = (n.get("name") or "")
            nm_low = nm.lower()
            is_band = bool(n.get("_band"))
            if (not in_band and not is_band
                    and (n.get("type") or "frame") in ("frame", "FRAME")
                    and any(k in nm or k in nm_low for k in _BAND_IMPORTANT_NAME_KW)
                    and not any(k in nm_low for k in _BAND_IMPORTANT_EXCLUDE_KW)):
                missing.append(nm)
            for c in (n.get("children") or []):
                lint(c, in_band or is_band)
        lint(blueprint)
        if missing:
            print(f"[규칙13-INFO] 홈 화면 중요 섹션이 풀폭 밴드(_band)가 아님: {', '.join(missing[:6])} "
                  f"— 밴드는 강조의 *한 수단*(기본값). 다른 방식(컬러 히어로 카드·타이포 위계 등)으로 "
                  f"강조했다면 OK (2026-06-12 룰 2계층).")


# 🔴 규칙 13-B — 홈 화면 Content(섹션 스택) 프레임 gap = spacing-2xl(20) (2026-06-08 사용자 룰)
_HOME_CONTENT_GAP = 20  # spacing-2xl — 섹션 간 간격(32=spacing-4xl 은 과함)
# Content 스택으로 볼 프레임 이름(섹션들을 담는 세로 컨테이너). 정확/접두 매칭.
_HOME_CONTENT_NAMES = ("content", "content mid", "content top", "content bottom")


def _enforce_home_content_gap(blueprint: dict) -> None:
    """홈 화면의 Content(섹션 스택) 프레임 itemSpacing 을 spacing-2xl(20) 로 강제 (2026-06-08).

    사용자 명시: *"content gap이 32로 spacing-4xl 로 설정되있는데, spacing-2xl 이여야 해 … 코드에 박아."*
    메인·모든 탭바 홈 화면의 섹션 스택(Content) 간격은 32(spacing-4xl)가 과해 20(spacing-2xl)로
    통일한다. post-fix `_bind_spacing_tokens_live` 가 20→spacing-2xl 토큰으로 자동 바인딩.

    대상: `_is_home_blueprint` 화면의 **VERTICAL auto-layout** + 이름이 'Content'/'Content Mid' 등
    (`_HOME_CONTENT_NAMES`) 인 프레임. 의도적 다른 간격은 노드에 `"_keepContentGap": true` 로 opt-out.
    """
    if not _is_home_blueprint(blueprint):
        return
    cnt = [0]

    def walk(n):
        if not isinstance(n, dict):
            return
        nm = (n.get("name") or "").strip().lower()
        if (nm in _HOME_CONTENT_NAMES and not n.get("_keepContentGap")
                and (n.get("type") or "frame") in ("frame", "FRAME")):
            al = n.get("autoLayout")
            if isinstance(al, dict) and (al.get("layoutMode") or "").upper() == "VERTICAL":
                # 🔻 2026-06-12 fill-in-only 로 강등 (전면 개편): author 명시 gap 존중(WARN 만),
                # 미지정(None)일 때만 기본값 20(spacing-2xl)을 채운다.
                cur = al.get("itemSpacing")
                if cur is None:
                    al["itemSpacing"] = _HOME_CONTENT_GAP
                    cnt[0] += 1
                elif isinstance(cur, (int, float)) and not isinstance(cur, bool) and cur != _HOME_CONTENT_GAP:
                    print(f"[스타일-기본값] '{n.get('name')}' Content gap={cur} — author 명시 존중"
                          f"(기본 권장 20=spacing-2xl, 스케일 값이면 토큰 바인딩됨)")
        for c in (n.get("children") or []):
            walk(c)
    walk(blueprint)
    if cnt[0]:
        print(f"[규칙13-B] 홈 Content 섹션 gap 기본값 채움 {cnt[0]}건 → spacing-2xl(20) (fill-in-only)")


# 🔴 규칙 — CTA 유도 caption 텍스트 = text-secondary (2026-06-08 사용자 룰)
_CAPTION_CTA_MAX_SIZE = 16  # 이보다 크면 hero/title 로 보고 제외
_CTA_NAME_KW = ("button", "btn", "cta", "모으러", "참여", "하기", "가기", "신청",
                "결제", "납입", "제출", "확인", "시작", "받기", "보내기", "구매")


def _bp_is_cta(node: dict) -> bool:
    """blueprint 노드가 CTA(라벨 있는 액션 버튼)인가 — 라벨 텍스트 instance 또는 button 이름 frame."""
    if not isinstance(node, dict):
        return False
    t = (node.get("type") or "").lower()
    nl = (node.get("name") or "").lower()
    if t == "instance" and node.get("componentKey"):
        if node.get("_instanceText"):
            return True  # 라벨 박힌 DS 버튼 = CTA
        return any(k in nl for k in _CTA_NAME_KW)
    if t in ("frame", "") and (nl.endswith(" button") or nl.endswith(" btn")
                               or nl.endswith(" cta") or nl in ("button", "cta")):
        return True
    return False


def _enforce_cta_caption_secondary(blueprint: dict) -> None:
    """CTA 바로 앞의 권유/안내 caption(작은 비-Bold 텍스트)이 text-primary 면 text-secondary 로 교정.

    사용자 명시(2026-06-08): *"'함께 모은 목돈, 다시 모아볼까요?' 같은 텍스트는 중요도에서 최상은
    아니거든. 그러면 컬러를 secondary 를 써야 하지 않겠어?"* — CTA 를 유도하는 권유 문구는 화면
    최상위 정보(hero 수치·타이틀)가 아니므로 `text-secondary`(연한 회색)가 맞다. `text-primary`(진한)는
    hero/타이틀 등 최상위 중요도에만.

    대상: 컨테이너 자식 중 **CTA 의 바로 앞 형제 TEXT** 가 — fontColor=text-primary,
    fontSize ≤ 16(hero/title 제외), weight ≠ Bold(강조 의도 제외) — 이면 text-secondary 로.
    의도적 primary 유지는 노드에 `"_keepTextColor": true` 로 opt-out.
    """
    cnt = [0]

    def walk(n):
        if not isinstance(n, dict):
            return
        ch = n.get("children") or []
        for i, c in enumerate(ch):
            if i > 0 and _bp_is_cta(c):
                prev = ch[i - 1]
                if (isinstance(prev, dict) and (prev.get("type") or "").lower() == "text"
                        and not prev.get("_keepTextColor")):
                    col = prev.get("fontColor")
                    size = prev.get("fontSize") or 0
                    style = ((prev.get("fontName") or {}).get("style") or "")
                    if (isinstance(col, str) and "text-primary" in col
                            and isinstance(size, (int, float)) and not isinstance(size, bool)
                            and size <= _CAPTION_CTA_MAX_SIZE
                            and style.lower() != "bold"):
                        prev["fontColor"] = "$token(text-secondary)"
                        cnt[0] += 1
        for c in ch:
            walk(c)
    walk(blueprint)
    if cnt[0]:
        print(f"[규칙] CTA 유도 caption {cnt[0]}건 → text-secondary (최상위 중요도 아님; opt-out: _keepTextColor)")


def _is_footer(node: dict) -> bool:
    """맨 아래 Footer 섹션인가 — 이름에 'footer' 포함."""
    return "footer" in (node.get("name") or "").lower()


def _is_icon_button(node: dict) -> bool:
    """아이콘만 든 작은 버튼(back/search/nav 등) 판별 — 카드/표면 enforcer 제외용.

    🔴 2026-06-09 사용자 룰: 상단바/헤더 아이콘 버튼에는 fill 박스·radius·stroke 를 기본으로
    넣지 않는다('별도 요청 없으면 기본으로 넣지마'). 그래서 카드 표면/보더 enforcer 가 이런
    버튼을 '카드'로 오인해 bg-primary 로 바꾸고 border 를 붙이던 회귀를 차단한다.
    blueprint(type 'icon'/'svg_icon') 와 라이브(VECTOR / 'ic-' 프레임) 자식 형태를 모두 인식.
    opt-out: 노드에 `_buttonChrome: True` 면 의도된 스타일 버튼이므로 제외하지 않음.
    """
    if not isinstance(node, dict):
        return False
    if (node.get("type") or "frame") not in (None, "frame", "FRAME"):
        return False
    if node.get("_buttonChrome"):
        return False
    kids = node.get("children") or []
    if not kids:
        return False
    bb = node.get("absoluteBoundingBox") or {}
    w = node.get("width") if isinstance(node.get("width"), (int, float)) else bb.get("width")
    h = node.get("height") if isinstance(node.get("height"), (int, float)) else bb.get("height")
    if isinstance(w, (int, float)) and w > 60:
        return False
    if isinstance(h, (int, float)) and h > 60:
        return False

    def _icon_child(c):
        if not isinstance(c, dict):
            return False
        ct = (c.get("type") or "").lower()
        cn = (c.get("name") or "").lower()
        if ct in ("icon", "svg_icon", "vector", "line", "star", "polygon", "boolean_operation"):
            return True
        if c.get("iconName"):
            return True
        # 빌드 후 svg 아이콘은 'ic-...' 프레임(내부 vector) 으로 렌더됨
        if ct in ("frame", "group") and (cn.startswith("ic-") or cn.startswith("ic ") or "icon" in cn):
            return True
        return False

    return all(_icon_child(c) for c in kids)


def _is_card_like(node: dict) -> bool:
    """카드형 프레임 판별 — cornerRadius ≥ 8 + fill + children. (아이콘 버튼은 제외.)"""
    if not isinstance(node, dict):
        return False
    if node.get("type") not in (None, "frame", "FRAME"):
        return False
    if _is_icon_button(node):   # 상단바 아이콘 버튼은 카드 아님 (2026-06-09)
        return False
    radius = node.get("cornerRadius") or node.get("topLeftRadius") or 0
    try:
        radius = float(radius)
    except (TypeError, ValueError):
        radius = 0
    return radius >= 8 and node.get("fill") is not None and bool(node.get("children"))


def _enforce_card_surface(blueprint: dict) -> None:
    """🔻 2026-06-12 스타일 기본값으로 강등 (전면 개편) — 더 이상 fill 을 변경하지 않는다.

    구 동작(2026-05-23 룰): 최상위 그레이 카드를 흰 카드+보더로 강제 flip. 이게 모든 화면을
    같은 모양으로 수렴시키는 뿌리 중 하나였다(사용자 2026-06-12: "수천 번 생성해도 거의 똑같아").
    → 이제 **author 명시 fill 을 존중**하고 advisory WARN 만 출력한다 (룰 2계층: 스타일=기본값).
    Footer 분기만 fill-in-only 로 유지: fill 이 *없을 때만* bg-primary 기본값을 채운다.
    """
    flipped = [0]
    footer_fixed = [0]

    # 2026-05-28 polish-aware: hero/alert/participation/sub-card/attendance 이름 패턴은
    # bg-secondary 카드 그대로 보존 ([feedback_imin_home_polish_baseline] 의 17389:51811
    # 패턴 — 옅은 lavender 참여중 카드 / sub-card 포인트 카드 / alert banner 등)
    POLISH_KEEP_GREY_RE = ("hero", "alert", "banner", "participation",
                            "sub-card", "sub_card", "attendance", "dot-row", "dot_row",
                            "points", "reward")

    grey_cards = []

    def walk(node, inside_card, in_footer):
        if not isinstance(node, dict):
            return
        is_footer = (not in_footer) and _is_footer(node)
        if is_footer:
            # Footer 기본값 — fill-in-only: fill 이 없을 때만 bg-primary (명시 fill 존중)
            if not node.get("fill"):
                node["fill"] = "$token(bg-primary)"
                footer_fixed[0] += 1
        nm_low = (node.get("name") or "").lower()
        polish_keep = any(kw in nm_low for kw in POLISH_KEEP_GREY_RE)
        is_card = (not in_footer and not is_footer) and _is_card_like(node)
        if is_card and not inside_card and not polish_keep and not node.get("_keepSurface"):
            fill_name = _token_name_of(node.get("fill"))
            if fill_name and fill_name.lower() in _GREY_CARD_FILLS:
                grey_cards.append(node.get("name") or "?")  # advisory — 변경하지 않음
        for child in node.get("children", []) or []:
            walk(child, inside_card or is_card, in_footer or is_footer)

    walk(blueprint, False, False)
    if grey_cards:
        print(f"[스타일-기본값] 최상위 그레이 카드 {len(grey_cards)}건 — author 명시 존중(변경 안 함). "
              f"기본 권장은 흰 카드+보더(2-B), 보더리스 면이 의도면 OK: {', '.join(grey_cards[:5])}")
    if footer_fixed[0]:
        print(f"[규칙] Footer fill 기본값 채움 — bg-primary ({footer_fixed[0]}건, fill-in-only)")


def _enforce_card_elevation(blueprint: dict) -> None:
    """⛔ 2026-05-27 폐기 — 사용자 명시: drop-shadow 적용 절대 금지.

    이전 룰(카드 입체감을 위해 subtle shadow 자동 주입)을 사용자가 폐기.
    대신 fill=bg-primary 인 frame 은 border-secondary 보더로 표면을 정의한다
    ([[feedback_card_surface]] + [[feedback_no_drop_shadow]]).

    blueprint 에 effects 가 명시되어 있어도 모두 제거한다 — 입력이 무시되도록 강제.
    """
    removed = [0]

    def walk(node):
        if not isinstance(node, dict):
            return
        if node.get("effects"):
            node["effects"] = []
            removed[0] += 1
        for child in node.get("children", []) or []:
            walk(child)

    walk(blueprint)
    if removed[0]:
        print(f"[규칙] drop-shadow 자동 제거 — blueprint 의 effects {removed[0]}건 제거 (2026-05-27 룰)")


def _enforce_white_card_border(blueprint: dict) -> None:
    """fill=bg-primary 인 모든 frame 에 border-secondary 1px 자동 추가 (2026-05-27 사용자 명시).

    drop-shadow 제거와 동시에 흰 표면을 border 로 정의한다.
    - 대상: type=frame + fill=$token(bg-primary) + children 있음 (카드형)
    - 제외: 루트 자체, 이미 stroke 있는 frame
    - strokeWeight 1: 사용자 명시 (2026-05-27 갱신)
    """
    # 🔻 2026-06-12 시인성-한정으로 강등 (전면 개편): 모든 흰 카드에 보더를 박던 구 동작이
    # '1px 보더 카드 나열' 룩을 강제해 화면들이 수렴 → 이제 **뒤 배경과 같은 색이라 경계가
    # 안 보이는 카드(흰-on-흰)에만** 보더를 채운다(시인성 = 정합성). 대비가 있는 배치
    # (흰 카드 on 회색 밴드, 회색 카드 on 흰 배경)는 author 의도 존중 — 보더 추가 안 함.
    BG_PRIMARY = "$token(bg-primary)"
    added = [0]

    def walk(node, is_root, backing):
        if not isinstance(node, dict):
            return
        if (not is_root) and node.get("type") in (None, "frame", "FRAME") \
                and node.get("fill") == BG_PRIMARY \
                and backing == BG_PRIMARY \
                and node.get("children") \
                and not _is_icon_button(node) \
                and not node.get("stroke") and not node.get("strokeColor"):
            node["strokeColor"] = "$token(border-secondary)"
            node["strokeWeight"] = 1
            added[0] += 1
        child_backing = node.get("fill") if isinstance(node.get("fill"), str) and node.get("fill") else backing
        for child in node.get("children", []) or []:
            walk(child, False, child_backing)

    walk(blueprint, True, BG_PRIMARY)  # 루트 배경 = bg-primary (절대 규칙 0)
    if added[0]:
        print(f"[규칙] 흰-on-흰 카드 시인성 보더 — {added[0]}건에 border-secondary 1px (대비 있는 카드는 미추가)")


# 브랜드 틴트 '면'(블록/카드 표면) 토큰 — 면 표면에 쓰면 무거운 secondary 계열
_BRAND_TINT_SURFACE_TOKENS = {
    "bg-brand-secondary", "bg-brand-secondary-hover",
    "bg-brand-primary_alt", "bg-brand-primary-alt",
}


def _enforce_brand_tint_surface_primary(blueprint: dict) -> None:
    """브랜드 틴트 '면'(자식 가진 frame 표면)은 bg-brand-primary 사용 (2026-06-05 사용자 룰).

    `bg-brand-secondary`(#e6d4ff)는 더 진해 면(블록/카드) 표면에 쓰면 시각적으로
    무겁다 → children 을 가진 frame(틴트 면)이 brand-secondary 계열 fill 이면
    `bg-brand-primary`(#f4ecff, 더 연함)로 교정한다. 작은 액센트/상태(badge·dot 등
    자식 없는 요소·DS 인스턴스)는 대상 아님(secondary 유지 가능).
    사용자: "이런건 컬러를 bg-brand-primary 를 사용게 시각적으로 맞아."
    """
    cnt = [0]

    def _tok(fill):
        if not isinstance(fill, str):
            return None
        s = fill.strip()
        if s.startswith("$token(") and s.endswith(")"):
            return s[7:-1].strip()
        return None

    # 🔻 2026-06-12 advisory 로 강등 (전면 개편) — author 명시 fill 존중, WARN 만.
    names = []

    def walk(n):
        if not isinstance(n, dict):
            return
        if n.get("type") in ("frame", "FRAME") and n.get("children"):
            if _tok(n.get("fill")) in _BRAND_TINT_SURFACE_TOKENS:
                names.append(n.get("name") or "?")
                cnt[0] += 1
        for c in (n.get("children") or []):
            walk(c)
    walk(blueprint)
    if cnt[0]:
        print(f"[스타일-기본값] 진한 브랜드 틴트 면 {cnt[0]}건 — author 명시 존중(변경 안 함). "
              f"기본 권장은 bg-brand-primary(연한 면): {', '.join(names[:5])}")


_BAND_VPAD = 24   # 채워진 풀폭 밴드 섹션의 상/하 padding (= spacing-3xl, spacing 바인더가 토큰 바인딩)


def _enforce_section_bg_gap_padding(root_node_id: str) -> int:
    """섹션 bg 색 경계의 padding 정렬 (2026-06-05 사용자 룰).

    루트 직계 섹션을 위→아래로 훑으며, 바로 위 섹션과 **보이는 SOLID 배경색이 다른** 섹션을 처리:
      - **채워진 밴드**(자체 bg fill 보유): 상/하 padding = 24(`_BAND_VPAD`, = spacing-3xl). 사용자:
        "위아래 패딩값 24로 맞추고 토큰 바인딩도 해". (좌우 padding 은 그대로 — 보통 20.) 24 는
        post-fix 의 `_bind_spacing_tokens_live` 가 spacing-3xl 로 자동 바인딩.
      - **빈/흰 섹션**(fill 없음): 상단 padding = 좌우 padding(대칭) — 색 경계에서 균형 여백.
    같은 색 경계는 손대지 않음. NavBar·Status Bar·Tab Bar·Wallet 등 고정 바 제외."""
    SKIP = ("status bar", "navbar", "nav bar", "tab bar", "tabbar", "wallet")

    def _bg(node):
        fills = node.get("fills") or []
        if fills and isinstance(fills[0], dict):
            f = fills[0]
            if f.get("type") == "SOLID" and f.get("visible", True):
                c = f.get("color") or {}
                return (round(c.get("r", 0), 3), round(c.get("g", 0), 3), round(c.get("b", 0), 3))
        return None  # 무배경(투명) = 루트색으로 간주

    fixed = [0]
    try:
        doc = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_node_id]})).get("json")[0]["document"]
    except Exception as e:
        print(f"  [section-bg-gap] root fetch fail: {e}")
        return 0
    root_bg = _bg(doc) or (0.988, 0.990, 0.992)  # bg-primary 기본
    kids = [c for c in (doc.get("children") or []) if (c.get("type") or "").upper() == "FRAME"]
    prev_bg = root_bg
    for ch in kids:
        nm = (ch.get("name") or "").lower()
        cur_fill = _bg(ch)              # None = 무배경
        cur_bg = cur_fill or root_bg
        if not any(s in nm for s in SKIP) and cur_bg != prev_bg:
            lm = ch.get("layoutMode") or "VERTICAL"  # ⚠️ set_auto_layout 은 layoutMode 필수
            try:
                if cur_fill is not None:
                    # 채워진 밴드 → 상/하 padding 24 (대칭, spacing-3xl 자동 바인딩)
                    pt = ch.get("paddingTop"); pb = ch.get("paddingBottom")
                    if pt != _BAND_VPAD or pb != _BAND_VPAD:
                        call_tool("set_auto_layout", {"nodeId": ch["id"], "layoutMode": lm,
                                  "paddingTop": _BAND_VPAD, "paddingBottom": _BAND_VPAD})
                        fixed[0] += 1
                else:
                    # 빈/흰 섹션 → 상단 padding = 좌우 padding (대칭)
                    pl = ch.get("paddingLeft"); pt = ch.get("paddingTop")
                    if isinstance(pl, (int, float)) and pl > 0 and pt != pl:
                        call_tool("set_auto_layout", {"nodeId": ch["id"], "layoutMode": lm,
                                  "paddingTop": pl})
                        fixed[0] += 1
            except Exception as e:
                print(f"  [section-bg-gap] '{ch.get('name')}' fail: {e}")
        prev_bg = cur_bg
    if fixed[0]:
        print(f"  [section-bg-gap] ✓ bg 색 경계 {fixed[0]}건 정렬 (밴드 상/하 {_BAND_VPAD} · 흰 섹션 pt=pl)")
    return fixed[0]


def _enforce_indicator_symmetric_gap(root_node_id: str) -> int:
    """캐로셀 인디케이터(Pagination dot group)가 마지막 자식인 프레임은 위 gap = 아래 padding
    (대칭) 으로 맞춘다 (2026-06-05 사용자 룰).

    Hero 같은 VERTICAL 프레임에서 [Banner Carousel, Indicator] 구조일 때, 인디케이터 위의
    itemSpacing(gap)과 프레임 paddingBottom 이 다르면 인디케이터가 위아래로 비대칭이라 불안정해
    보인다 → paddingBottom = itemSpacing 으로 통일. 인디케이터(Pagination dot group / 이름에
    'indicator'/'pagination') 인스턴스를 마지막 자식으로 가진 VERTICAL 프레임만 대상."""
    fixed = [0]

    def _is_indicator(n):
        nm = (n.get("name") or "").lower()
        return ("pagination" in nm or "indicator" in nm or "인디케이터" in nm)

    def walk(node):
        if not isinstance(node, dict):
            return
        if (node.get("type") or "").upper() == "FRAME" and (node.get("layoutMode") or "").upper() == "VERTICAL":
            kids = node.get("children") or []
            if kids and _is_indicator(kids[-1]):
                gap = node.get("itemSpacing")
                pb = node.get("paddingBottom")
                if isinstance(gap, (int, float)) and pb != gap:
                    try:
                        # ⚠️ set_auto_layout 은 layoutMode 필수 — 미지정 시 plugin 이 throw(무효)
                        call_tool("set_auto_layout", {"nodeId": node["id"],
                                  "layoutMode": node.get("layoutMode") or "VERTICAL",
                                  "paddingBottom": gap})
                        fixed[0] += 1
                    except Exception as e:
                        print(f"  [indicator-gap] '{node.get('name')}' fail: {e}")
        for ch in node.get("children", []) or []:
            walk(ch)
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_node_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [indicator-gap] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [indicator-gap] ✓ 인디케이터 프레임 {fixed[0]}건 아래 padding = 위 gap 으로 정렬")
    return fixed[0]


# DS 'Status Bar' 마스터 스펙 높이 (393×62) — 2026-06-12 사용자 명시
_STATUS_BAR_H = 62.0


def _status_bar_fix_needed(node: dict, expected_h: float = _STATUS_BAR_H) -> bool:
    """순수 판정: Status Bar 노드가 사이징 변형으로 복구가 필요한가.

    2026-06-12 회귀: R24 inject·code.js 강제 삽입이 vertical 'HUG' 를 박아 마스터
    고정 높이 62 가 내부 콘텐츠 자연 높이 63.5 로 재측정됐다. HUG 이거나 높이가
    62±1 을 벗어나면 복구 대상."""
    if not isinstance(node, dict):
        return False
    name = (node.get("name") or "").lower()
    if "status" not in name or "bar" not in name:
        return False
    if node.get("layoutSizingVertical") == "HUG":
        return True
    h = _node_wh(node)[1]
    if isinstance(h, (int, float)) and h > 0 and abs(float(h) - expected_h) > 1.0:
        return True
    return False


_STATUS_BAR_NAMES = ("status bar", "statusbar", "status_bar")


def _is_error_status_bar_frame(node) -> bool:
    """R24 inject 의 componentKey 가 stale/미게시라 import 실패했을 때 code.js 가 남기는
    '⚠ Status Bar' 텍스트를 담은 에러 FRAME 감지 (순수 함수 — 테스트 대상)."""
    if not isinstance(node, dict):
        return False
    if (node.get("type") or "").upper() != "FRAME":
        return False
    if (node.get("name") or "").strip().lower() not in _STATUS_BAR_NAMES:
        return False
    for ch in (node.get("children") or []):
        txt = ch.get("characters") or ch.get("text") or ""
        if (ch.get("type") or "").upper() == "TEXT" and "⚠" in txt:
            return True
    return False


def _recover_error_status_bar_live(root_node_id: str) -> bool:
    """🔴 Status Bar 에러 프레임 자동 복구 (2026-07-10, 사용자 지시 옵션 1).

    R24 inject 가 stale 키로 instance 노드를 blueprint 에 박으면 import 실패 →
    ⚠ 에러 FRAME 이 되고, 'Status Bar 노드가 이미 있음'으로 인식돼 code.js 의 이름 기반
    FORCED 삽입(정상 폴백)까지 억제된다. 여기서 에러 프레임을 감지해 같은 페이지 다른
    화면의 Status Bar INSTANCE 를 clone 으로 교체한다 — 키가 다시 stale 해져도 빌드가
    자가 복구 (실측 회귀: imin_signup_home_20260709, 수동 복구 ~4분 → 자동화).
    직후 _enforce_status_bar_size_live 가 FILL×FIXED 62 를 재단언한다."""
    try:
        info = parse_content(call_tool("get_node_info", {"nodeId": root_node_id})).get("json") or {}
    except Exception:
        return False
    err = None
    for c in (info.get("children") or [])[:3]:
        if _is_error_status_bar_frame(c):
            err = c
            break
    if not err:
        return False
    # 같은 페이지의 다른 프레임 첫 자식에서 Status Bar INSTANCE 소스 탐색
    try:
        doc = parse_content(call_tool("get_document_info", {})).get("json") or {}
    except Exception:
        return False
    source_id = None
    for pc in (doc.get("children") or []):
        if pc.get("id") == root_node_id or (pc.get("type") or "").upper() != "FRAME":
            continue
        if (pc.get("width") or 0) < 300:  # 모바일 화면 프레임만 후보
            continue
        try:
            pinfo = parse_content(call_tool("get_node_info", {"nodeId": pc["id"]})).get("json") or {}
        except Exception:
            continue
        for cc in (pinfo.get("children") or [])[:2]:
            if ((cc.get("type") or "").upper() == "INSTANCE"
                    and (cc.get("name") or "").strip().lower() in _STATUS_BAR_NAMES):
                source_id = cc.get("id")
                break
        if source_id:
            break
    if not source_id:
        print("  [status-bar-recover] ⚠ 에러 프레임 발견 — 페이지에 복제할 Status Bar 인스턴스가 없어 수동 처리 필요 "
              "(DS 파일 연결 후 ds_catalog 'Status Bar' 키 갱신 권장)")
        return False
    try:
        cloned = parse_content(call_tool("clone_node", {"nodeId": source_id})).get("json") or {}
        new_id = cloned.get("id")
        if not new_id:
            return False
        call_tool("insert_child", {"parentId": root_node_id, "childId": new_id, "index": 0})
        call_tool("delete_node", {"nodeId": err.get("id")})
        print(f"  [status-bar-recover] ✓ ⚠ 에러 프레임 → Status Bar 인스턴스 clone({source_id}) 교체 (stale 키 자동 복구)")
        return True
    except Exception as e:
        print(f"  [status-bar-recover] ⚠ 복구 실패: {e}")
        return False


def _enforce_tool_bar_title_style_live(root_node_id: str) -> int:
    """🔴 Tool Bar 타이틀 = Body xl/Semibold(20px) 강제 (2026-08-06 사용자 회귀 보고 ×2).

    근본 원인: 파일에 import 캐시된 Tool Bar 컴포넌트 마스터가 **구버전(타이틀 16px
    Body md)** 일 수 있다 — importComponentSetByKeyAsync 는 파일 내 기존 컴포넌트를
    재사용하므로 라이브러리가 20px 로 업데이트돼도 새 인스턴스는 계속 16px 로 생성된다.
    근본 해결 = Figma 'Assets > 라이브러리 업데이트' 수락(수동). 이 enforcer 는 그 전까지
    모든 경로(빌드·수동 인스턴스 생성)에서 타이틀을 DS 정본 20px 로 재단언하는 백스톱.
    ⚠️ Status Bar 등 다른 인스턴스는 건드리지 않는다(이름 필터). 빈 텍스트 스킵."""
    try:
        sm = _load_text_style_map()
        xl = sm.get((20, "semibold"))
    except Exception:
        xl = None
    if not xl:
        return 0
    try:
        info = parse_content(call_tool("get_node_info", {"nodeId": root_node_id})).get("json") or {}
    except Exception:
        return 0
    fixed = 0

    def _tb_ids(n, depth=0):
        out = []
        if not isinstance(n, dict) or depth > 4:
            return out
        nm = (n.get("name") or "").lower()
        if (n.get("type") or "").upper() == "INSTANCE" and ("tool bar" in nm or "navbar" in nm):
            out.append(n.get("id"))
            return out
        for c in n.get("children") or []:
            try:
                ci = parse_content(call_tool("get_node_info", {"nodeId": c.get("id")})).get("json") or {}
            except Exception:
                continue
            out += _tb_ids(ci, depth + 1)
        return out

    for tb in _tb_ids(info):
        try:
            scan = parse_content(call_tool("scan_text_nodes", {"nodeId": tb})).get("json") or {}
            tnodes = scan.get("textNodes") or []
        except Exception:
            tnodes = []
        for t in tnodes:
            ch = (t.get("characters") or "").strip()
            if not ch:
                continue
            try:
                ni = parse_content(call_tool("get_node_info", {"nodeId": t.get("id")})).get("json") or {}
            except Exception:
                continue
            fs = ni.get("fontSize")
            if isinstance(fs, (int, float)) and abs(fs - 20) > 0.5:
                try:
                    call_tool("set_text_style_id", {"nodeId": t.get("id"),
                                                    "textStyleId": f"S:{xl},{tb}"})
                    fixed += 1
                    print(f"  [tool-bar-title] ✓ '{ch[:12]}' {fs}→20px (구버전 마스터 백스톱 — "
                          f"라이브러리 업데이트 필요)")
                except Exception:
                    pass
    return fixed


# ── Action Button Size → 마스터 높이 (2026-09-04 실측: Secondary 키 19c3ba… 인스턴스) ──
AB_SIZE_HEIGHT = {"sm": 24, "md": 32, "lg": 40, "xl": 48, "2xl": 56}


def _action_button_expected_height(size: Optional[str]) -> Optional[int]:
    return AB_SIZE_HEIGHT.get((size or "").strip().lower()) if size else None


def _enforce_action_button_height_live(root_id: str) -> int:
    """DS Action Button 인스턴스 세로 HUG/축소 복구 — FIXED + Size 별 마스터 높이 (2026-09-04).

    회귀: 하단 액션바의 Action Button 2xl 이 post-fix 뒤 174×24(HUG → 내부 'Text padding' 24 로
    붕괴)가 돼 라벨이 잘렸다. 프롭(Size=2xl)은 정상이었으므로 높이만 재단언하면 된다.
    대상: INSTANCE 이면서 Size+Hierarchy 프롭을 가진 노드(= Action Button 계열). 가로 FILL 은
    resize 가 FIXED 로 바꾸므로 원래 값을 재단언한다."""
    fixed = 0
    try:
        tree = parse_content(call_tool("get_node_tree", {"nodeId": root_id, "maxDepth": 6})).get("json") or {}
    except Exception as e:
        print(f"  [action-button-height] tree 조회 실패: {e}")
        return 0
    node = tree.get("node", tree) if isinstance(tree, dict) else {}
    cands = []

    def walk(n):
        if not isinstance(n, dict):
            return
        nid = n.get("id") or ""
        if n.get("type") == "INSTANCE" and ";" not in nid:
            nm = (n.get("name") or "").lower()
            if any(k in nm for k in ("button", "btn", "cta")):
                cands.append(n)
            return  # 인스턴스 내부는 내려가지 않음
        for c in n.get("children") or []:
            walk(c)
    walk(node)
    for n in cands:
        nid = n["id"]
        try:
            props = (parse_content(call_tool("get_instance_properties", {"nodeId": nid})).get("json") or {}).get("properties") or {}
        except Exception:
            continue
        if "Size" not in props or "Hierarchy" not in props:
            continue
        size = (props.get("Size") or {}).get("value")
        expect = _action_button_expected_height(size)
        if not expect:
            continue
        w, h = _node_wh(n)
        vsz = (n.get("layoutSizingVertical") or "").upper()
        if vsz != "HUG" and abs((h or 0) - expect) <= 1.5:
            continue
        hsz = (n.get("layoutSizingHorizontal") or "").upper()
        try:
            call_tool("set_layout_sizing", {"nodeId": nid, "vertical": "FIXED"})
            call_tool("resize_node", {"nodeId": nid, "width": w or expect * 2, "height": expect})
            if hsz == "FILL":
                call_tool("set_layout_sizing", {"nodeId": nid, "horizontal": "FILL"})
            fixed += 1
            print(f"  [action-button-height] '{n.get('name')}' Size={size} {vsz or '-'}/{round(h or 0)} → FIXED {expect}")
        except Exception as e:
            print(f"  [action-button-height] '{n.get('name')}' 실패: {e}")
    return fixed


def _is_keyboard_node(n: dict) -> bool:
    """DS 'Keyboard' 인스턴스 판정(이름 기반, 직계 자식용). 소스 캡처의 raw 'keyboard' GROUP 도
    같은 이름을 쓰므로 INSTANCE/FRAME/GROUP 모두 인정 — 규칙 0-Y-2 의 판정은 '키보드가 화면에
    있는가'이지 DS 여부가 아니다."""
    nm = (n.get("name") or "").strip().lower().replace(" ", "")
    return nm == "keyboard" or nm.startswith("keyboard/") or nm.endswith("_keyboard")


def _is_home_indicator_node(n: dict) -> bool:
    nm = (n.get("name") or "").strip().lower().replace(" ", "")
    return nm == "homeindicator" or nm.startswith("homeindicator/") or "bars/homeindicator" in nm


def _home_indicators_to_remove_for_keyboard(kids: list) -> list:
    """🔴 규칙 0-Y-2 (2026-09-07 사용자 룰): 화면에 키보드가 있으면 최하단 HomeIndicator 는 불필요
    (iOS 키보드 컴포넌트가 HI 영역까지 포함). 루트 직계 자식 목록에서 키보드가 있을 때 삭제해야 할
    HomeIndicator 노드 id 들을 반환(키보드 없으면 빈 리스트). 순수 함수 — 오프라인 테스트 대상."""
    if not any(_is_keyboard_node(c) for c in kids):
        return []
    return [c["id"] for c in kids if _is_home_indicator_node(c) and c.get("id") and ";" not in c["id"]]


def _remove_home_indicator_when_keyboard_live(root_id: str) -> int:
    """post-fix 백스톱 — 루트 직계에 Keyboard 가 있으면 HomeIndicator 인스턴스를 삭제(규칙 0-Y-2).
    반환: 삭제 건수."""
    try:
        info = parse_content(call_tool("get_node_info", {"nodeId": root_id})).get("json") or {}
        root = info.get("node", info)
    except Exception:
        return 0
    targets = _home_indicators_to_remove_for_keyboard(root.get("children") or [])
    removed = 0
    for nid in targets:
        try:
            call_tool("delete_node", {"nodeId": nid})
            removed += 1
        except Exception as e:
            print(f"  [home-indicator-keyboard] 삭제 실패 {nid}: {e}")
    if removed:
        print(f"  [home-indicator-keyboard] ✓ 키보드 화면 — HomeIndicator {removed}개 삭제 (규칙 0-Y-2)")
    return removed


def _ensure_home_indicator_live(root_id: str, screen_type: Optional[str] = None) -> bool:
    """변환 트랙(IMIN_CONVERT_TRACK=1) 전용 — 루트에 HomeIndicator 가 없으면 페이지 내 기존
    인스턴스를 clone 해 flow 마지막 자식(가로 FILL)으로 삽입 (2026-09-04).
    DS 게시 검색에 HomeIndicator 키가 없어(인덱스 한계) 파일 내 clone 이 정본 경로.
    모달/바텀시트는 대상 아님. 페이지 전역 find 는 느리므로(≈14s) 같은 부모 섹션을 먼저 본다.
    🔴 키보드가 있는 화면은 대상 아님 (규칙 0-Y-2, 2026-09-07)."""
    if os.environ.get("IMIN_CONVERT_TRACK") != "1":
        return False
    if _is_hug_screen_type(screen_type) or _is_bottom_sheet_screen_type(screen_type):
        return False
    try:
        info = parse_content(call_tool("get_node_info", {"nodeId": root_id})).get("json") or {}
        root = info.get("node", info)
    except Exception:
        return False
    kids = root.get("children") or []
    if any(_is_keyboard_node(c) for c in kids):
        print("  [home-indicator-ensure] 키보드 화면 — HomeIndicator 삽입 안 함 (규칙 0-Y-2)")
        return False
    if any("homeindicator" in (c.get("name") or "").lower().replace(" ", "") for c in kids):
        return False
    src = None
    scopes = [root.get("parentId"), "0:1"]
    for scope in [sc for sc in scopes if sc]:
        try:
            r = parse_content(call_tool("find_nodes_by_name", {"name": "HomeIndicator", "scopeNodeId": scope})).get("json") or {}
        except Exception:
            continue
        for m in r.get("matches") or []:
            if m.get("type") == "INSTANCE" and m.get("id") != root_id and (m.get("width") or 0) >= 300:
                src = m["id"]
                break
        if src:
            break
    if not src:
        print("  [home-indicator-ensure] ⚠️ 페이지에 HomeIndicator 인스턴스 없음 — 수동 삽입 필요")
        return False
    try:
        cl = parse_content(call_tool("clone_node", {"nodeId": src})).get("json") or {}
        cid = cl.get("id") or cl.get("nodeId")
        call_tool("insert_child", {"parentId": root_id, "childId": cid})
        call_tool("set_layout_positioning", {"nodeId": cid, "layoutPositioning": "AUTO"})
        call_tool("set_layout_sizing", {"nodeId": cid, "horizontal": "FILL"})
        print(f"  [home-indicator-ensure] ✓ HomeIndicator clone({src}) → 루트 마지막 자식(flow, FILL)")
        return True
    except Exception as e:
        print(f"  [home-indicator-ensure] clone 실패: {e}")
        return False


def _enforce_home_indicator_fill_live(root_node_id: str) -> int:
    """🔴 HomeIndicator 인스턴스 = 가로 FILL 강제 (2026-08-04 사용자 룰 —
    "왜 자꾸 homeindicator instance 가 width 360 고정으로 들어와지는거야. width=fill 로").

    구 화면(360)에서 클론/복제된 HomeIndicator 가 FIXED 360 으로 남아 393 루트에서
    우측 33px 이 비는 회귀의 백스톱. auto-layout 부모면 FILL, 아니면 루트 폭으로 resize."""
    try:
        info = parse_content(call_tool("get_node_info", {"nodeId": root_node_id})).get("json") or {}
    except Exception:
        return 0
    root_w = info.get("width") or 393
    fixed = 0

    def _walk(n, parent_lm):
        nonlocal fixed
        if not isinstance(n, dict):
            return
        nm = (n.get("name") or "").lower().replace(" ", "")
        if "homeindicator" in nm and (n.get("type") or "").upper() == "INSTANCE":
            w = n.get("width") or 0
            sizh = n.get("layoutSizingHorizontal")
            if sizh != "FILL" or abs(w - root_w) > 1:
                nid = n.get("id")
                try:
                    if parent_lm in ("VERTICAL", "HORIZONTAL"):
                        call_tool("set_layout_sizing", {"nodeId": nid, "layoutSizingHorizontal": "FILL"})
                    else:
                        h = n.get("height") or 34
                        call_tool("resize_node", {"nodeId": nid, "width": root_w, "height": h})
                    fixed += 1
                    print(f"  [home-indicator-fill] ✓ '{n.get('name')}' {w}→FILL/{root_w}")
                except Exception as e:
                    print(f"  [home-indicator-fill] fail {nid}: {e}")
            return
        for c in n.get("children") or []:
            _walk(c, (n.get("layoutMode") or "").upper())

    _walk(info, "")
    return fixed


def _enforce_status_bar_size_live(root_node_id: str) -> int:
    """🔴 Status Bar = 가로 FILL × 세로 FIXED 62 강제 (2026-06-12 사용자 회귀 보고).

    원인 2곳(R24 inject 의 HUG, code.js FORCED 삽입의 HUG)은 소스에서 고쳤고, 이
    enforcer 는 ① 이미 변형(63.5 HUG)된 기존 화면 복구 ② 향후 어떤 경로로든 다시
    HUG/오차가 생겨도 post-fix 가 잡는 백스톱. INSTANCE 본체의 resize/sizing 은
    내부 색 변경이 아니므로 절대 규칙 0-K 와 무관.
    ⚠️ resize_node 는 가로까지 FIXED 로 고정하므로 직후 horizontal FILL 재단언 필수."""
    try:
        info = parse_content(call_tool("get_node_info", {"nodeId": root_node_id})).get("json") or {}
    except Exception:
        return 0
    fixed = 0
    # Status Bar 는 루트 첫 자식이 정상 — 보수적으로 직계 앞 3개만 검사
    for c in (info.get("children") or [])[:3]:
        if not _status_bar_fix_needed(c):
            continue
        nid = c.get("id")
        if not nid:
            continue
        try:
            call_tool("set_layout_sizing", {"nodeId": nid, "layoutSizingVertical": "FIXED"})
        except Exception:
            pass
        try:
            w = _node_wh(c)[0] or 393
            call_tool("resize_node", {"nodeId": nid, "width": w, "height": _STATUS_BAR_H})
        except Exception:
            pass
        try:
            call_tool("set_layout_sizing", {"nodeId": nid, "layoutSizingHorizontal": "FILL"})
        except Exception:
            pass
        print(f"  [status-bar-size] ✓ '{c.get('name')}' → FILL × FIXED {int(_STATUS_BAR_H)}px (HUG 변형 복구)")
        fixed += 1
    if not fixed:
        print(f"  [status-bar-size] OK — Status Bar {int(_STATUS_BAR_H)}px 정상")
    return fixed


def _enforce_wallet_bar_radius(root_node_id: str) -> int:
    """월렛 바(마이 월렛)의 top-left/top-right 코너 radius = 16 강제 (2026-06-05 사용자 룰).

    하단 고정 월렛 바는 시트처럼 위쪽 두 코너만 둥글게(16=radius-2xl), 아래는 0. blueprint 가
    개별 코너를 안 박았거나 빠뜨려도 라이브에서 박는다(평평한 사각형 회귀 차단). radius>0 이므로
    clipsContent 는 0-Q 클립 enforcer 가 별도로 보장. radius 16 은 post-fix radius 바인더가
    radius-2xl 토큰으로 자동 바인딩."""
    fixed = [0]

    def _is_wallet_bar(node, nm: str, is_root: bool) -> bool:
        # 🔴 2026-08-14 회귀 수정: 기존 매칭('wallet'/'월렛' 이름이면 전부)이 너무 넓어
        # root 프레임("월렛 출금_금액입력" 등 화면명에 '월렛' 포함)까지 top radius 16 을
        # 박았다. 이 enforcer 의 원 의도는 **하단 고정 월렛 '바'** 하나뿐이므로:
        #   ① root 는 절대 대상 아님  ② '바(bar)' 이름이거나 ABSOLUTE 하단 고정일 때만.
        if is_root:
            return False
        if "wallet" not in nm and "월렛" not in nm:
            return False
        if "bar" in nm or "바" in nm.split()[-1:]:
            return True
        return (node.get("layoutPositioning") or "").upper() == "ABSOLUTE"

    def walk(node, is_root=False):
        if not isinstance(node, dict):
            return
        nm = (node.get("name") or "").lower()
        if (node.get("type") or "").upper() == "FRAME" and _is_wallet_bar(node, nm, is_root):
            if node.get("topLeftRadius") != 16 or node.get("topRightRadius") != 16:
                try:
                    call_tool("set_corner_radius", {"nodeId": node["id"], "radius": 16,
                              "corners": [True, True, False, False]})
                    fixed[0] += 1
                except Exception as e:
                    print(f"  [wallet-radius] '{node.get('name')}' fail: {e}")
            return  # 월렛 바 내부는 더 안 내려감
        for ch in node.get("children", []) or []:
            walk(ch)
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_node_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0], is_root=True)
    except Exception as e:
        print(f"  [wallet-radius] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [wallet-radius] ✓ 월렛 바 {fixed[0]}건 top-left/top-right radius 16 적용")
    return fixed[0]


def _enforce_stepper_two_row_live(root_node_id: str) -> int:
    """스테퍼 그룹(기간/월입금 같은 `− 값 +` 컨트롤 묶음)은 세로 2-row 스택으로 강제
    (2026-06-08 사용자 룰).

    가로 2-up(2-col)로 두면 각 control 폭이 좁아(~126px) 값 박스가 ~50px 로 줄어들어,
    큰 값("110만원"·"160만원")이 `−`/`+` 와 겹치거나 2줄로 줄바꿈된다. 두 스테퍼를 세로
    2-row 로 스택하면 각 control 이 전폭이 되어 값이 원래 크기로 한 줄에 들어간다.

    감지: 직계 FRAME 자식 중 2개 이상이 각각 `control`(직계 TEXT 에 '−' 와 '+' 둘 다 포함하는
    HORIZONTAL frame)을 품은 '스테퍼 그룹' 프레임. (생성기 컨벤션: 그룹 이름 'Steppers',
    자식 'Stepper' > 'control' > [−btn, 값, +btn].) 이름에 의존하지 않고 구조로 감지.

    강제: 그룹 → VERTICAL(gap 10) + 세로 HUG / 각 스테퍼 → 가로 FILL·세로 HUG /
    control → HORIZONTAL primary=MIN counter=CENTER gap 8 / 값 텍스트(−·+ 아님) → 가로 FILL·
    가운데 정렬. (값 FILL + − 좌 / + 우 = 겹침 불가.) DS 인스턴스·내부(';') 제외."""
    fixed = [0]

    def _subtree_has_minus_plus(n):
        """n 서브트리에 '−' 와 '+' TEXT 가 모두 있으면 True (− / + 가 stepper-btn frame 안에
        한 단계 더 들어가 있어도 잡도록 서브트리 전체 스캔)."""
        chars = []

        def collect(m):
            if (m.get("type") or "").upper() == "TEXT":
                chars.append(m.get("characters", ""))
            for cc in m.get("children", []) or []:
                collect(cc)
        collect(n)
        return ("−" in chars) and ("+" in chars)

    def _find_control(n):
        """n 서브트리에서 서브트리에 '−'·'+' 를 모두 품은 HORIZONTAL control frame 반환
        (가장 안쪽 = − 값 + 를 직접 묶는 행). 직계 자식부터 깊이 우선으로 더 안쪽을 우선."""
        if not isinstance(n, dict):
            return None
        # 자식 중 더 안쪽 control 이 있으면 그것을 우선 (control 은 − 값 + 를 직접 감싸는 최내곽)
        for ch in n.get("children", []) or []:
            r = _find_control(ch)
            if r:
                return r
        if (n.get("type") or "").upper() == "FRAME" and (n.get("layoutMode") or "").upper() == "HORIZONTAL" \
                and _subtree_has_minus_plus(n):
            return n
        return None

    def _fix_group(group, stepper_kids):
        # 그룹 → VERTICAL 스택
        try:
            call_tool("set_auto_layout", {"nodeId": group["id"], "layoutMode": "VERTICAL",
                      "itemSpacing": 10, "primaryAxisAlignItems": "MIN", "counterAxisAlignItems": "MIN"})
            call_tool("set_layout_sizing", {"nodeId": group["id"], "layoutSizingVertical": "HUG"})
        except Exception as e:
            print(f"  [stepper-2row] group '{group.get('name')}' fail: {e}")
            return
        for sk in stepper_kids:
            try:
                call_tool("set_layout_sizing", {"nodeId": sk["id"], "layoutSizingHorizontal": "FILL"})
                call_tool("set_layout_sizing", {"nodeId": sk["id"], "layoutSizingVertical": "HUG"})
            except Exception:
                pass
            ctrl = _find_control(sk)
            if not ctrl:
                continue
            try:
                call_tool("set_auto_layout", {"nodeId": ctrl["id"], "layoutMode": "HORIZONTAL",
                          "primaryAxisAlignItems": "MIN", "counterAxisAlignItems": "CENTER", "itemSpacing": 8})
            except Exception:
                pass
            for v in ctrl.get("children", []) or []:
                if (v.get("type") or "").upper() == "TEXT" and v.get("characters", "") not in ("−", "+", ""):
                    try:
                        call_tool("set_layout_sizing", {"nodeId": v["id"], "layoutSizingHorizontal": "FILL"})
                        call_tool("set_text_align", {"nodeId": v["id"], "textAlignHorizontal": "CENTER"})
                    except Exception:
                        pass
        fixed[0] += 1

    def walk(node):
        if not isinstance(node, dict):
            return
        if (node.get("type") or "").upper() == "INSTANCE" or ";" in node.get("id", ""):
            return
        if (node.get("type") or "").upper() == "FRAME":
            kids = [c for c in (node.get("children") or []) if (c.get("type") or "").upper() == "FRAME"]
            stepper_kids = [c for c in kids if _find_control(c)]
            # 스테퍼 그룹 = control 을 품은 직계 frame 자식이 2개 이상
            # (이미 VERTICAL 이어도 값 FILL/control 정렬을 항상 멱등 정규화 — 빌드 중 FILL→HUG
            #  리셋 회귀 대비. _fix_group 은 idempotent.)
            if len(stepper_kids) >= 2:
                _fix_group(node, stepper_kids)
                return  # 그룹 처리 후 내부 재귀 불필요
        for ch in node.get("children", []) or []:
            walk(ch)
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_node_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [stepper-2row] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [stepper-2row] ✓ 스테퍼 그룹 {fixed[0]}건 세로 2-row 스택 + 값 FILL 적용")
    return fixed[0]


def _enforce_brand_tint_surface_primary_live(root_node_id: str) -> int:
    """🔻 2026-06-12 no-op 으로 강등 (전면 개편) — author 명시 fill 존중 (룰 2계층: 스타일=기본값).

    구 동작: 진한 브랜드 틴트 면(#e6d4ff/#cfaeff)을 라이브에서 연한 bg-brand-primary 로 강제 교정.
    blueprint 단계의 advisory WARN(_enforce_brand_tint_surface_primary)만 남긴다."""
    return 0


def _enforce_brand_tint_surface_primary_live_LEGACY(root_node_id: str) -> int:
    """(보존) 구 동작 — 필요 시 수동 호출용."""
    SEC = (0.902, 0.831, 1.0)    # #e6d4ff bg-brand-secondary
    SECH = (0.812, 0.682, 1.0)   # #cfaeff bg-brand-secondary-hover
    PRIM = (0.957, 0.925, 1.0)   # #f4ecff bg-brand-primary
    fixed = [0]

    def near(c, t):
        return (abs(c.get("r", 0) - t[0]) < 0.02 and abs(c.get("g", 0) - t[1]) < 0.02
                and abs(c.get("b", 0) - t[2]) < 0.02)

    def walk(node):
        if not isinstance(node, dict):
            return
        if (node.get("type") or "").upper() == "INSTANCE":
            return
        nid = node.get("id", "")
        if node.get("type") in ("FRAME", "frame") and node.get("children") and ";" not in nid:
            fills = node.get("fills") or []
            if fills and isinstance(fills[0], dict):
                f = fills[0]
                if f.get("type") == "SOLID" and f.get("visible", True):
                    c = f.get("color") or {}
                    if near(c, SEC) or near(c, SECH):
                        try:
                            call_tool("set_fill_color", {"nodeId": nid,
                                "color": {"r": PRIM[0], "g": PRIM[1], "b": PRIM[2], "a": 1}})
                            fp = _token_to_figma_path("bg-brand-primary")
                            if fp:
                                call_tool("set_bound_variables", {"nodeId": nid,
                                    "bindings": {"fills/0": fp}})
                            fixed[0] += 1
                        except Exception as e:
                            print(f"  [brand-tint-surface-live] '{node.get('name')}' fail: {e}")
        for ch in node.get("children", []) or []:
            walk(ch)
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_node_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [brand-tint-surface-live] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [brand-tint-surface-live] ✓ 브랜드 틴트 면 {fixed[0]}건 → bg-brand-primary")
    return fixed[0]


# 텍스트 크기 정책 (2026-06-05 사용자 룰): 기본 16 / 보조 14 / 12 는 정말 작은 경우만.
_TEXT_FLOOR_BODY = 14   # 일반 텍스트 하한 (보조 라벨/캡션 포함)
_TEXT_FLOOR_FINE = 12   # 푸터·미세 문구(법적 고지 등) 하한 — 12 미만 금지


def _is_symbol_only_text(t: str) -> bool:
    """장식/기호 전용 텍스트(●, >, −, + 등)는 크기 강제 대상에서 제외."""
    s = (t or "").strip()
    if len(s) <= 1:
        return True
    return not any(ch.isalnum() or ('가' <= ch <= '힣') for ch in s)


def _enforce_min_text_size(blueprint: dict) -> None:
    """텍스트 크기 하한 강제 (2026-06-05 사용자 룰): 12pt 남용 차단.

    기본 16 / 보조 14 / 12 는 푸터·미세 문구일 때만. 일반 텍스트의 fontSize 가
    14 미만이면 14 로, 푸터(조상 이름에 'footer') 안 미세 문구는 12 미만이면 12 로 올린다.
    장식 기호(●/>/−/+)·이미 하한 이상은 건드리지 않는다. (제목·hero 는 영향 없음.)
    """
    bumped = [0]

    def walk(node, in_footer):
        if not isinstance(node, dict):
            return
        nm = (node.get("name") or "").lower()
        in_footer = in_footer or ("footer" in nm)
        if node.get("type") in ("text", "TEXT"):
            txt = node.get("text") or node.get("characters") or ""
            cur = node.get("fontSize")
            if isinstance(cur, (int, float)) and not _is_symbol_only_text(txt):
                floor = _TEXT_FLOOR_FINE if in_footer else _TEXT_FLOOR_BODY
                if cur < floor:
                    node["fontSize"] = floor
                    bumped[0] += 1
        for c in (node.get("children") or []):
            walk(c, in_footer)
    walk(blueprint, False)
    if bumped[0]:
        print(f"[규칙] 텍스트 크기 하한 — {bumped[0]}건 상향 (기본16/보조14/푸터·미세12)")


def _enforce_min_text_size_live(root_node_id: str) -> int:
    """라이브: 작은 텍스트(<14, 푸터<12)를 하한으로 상향.

    🔴 절대 규칙: **텍스트 스타일 바인딩을 깨지 않는다.** raw `set_font_size` 금지 —
    그건 DS text style 바인딩을 detach 한다. 대신 같은 weight 의 **더 큰 DS 텍스트 스타일**
    (size=floor)을 `set_text_style_id` 로 입혀 크기를 키운다(바인딩 유지). DS 스케일에 12/14
    스타일이 전 weight 로 존재한다. DS 인스턴스 내부(';')·장식 기호 제외.

    get_nodes_info 는 TEXT 폰트 속성을 node.style 하위(style.fontSize/fontStyle)에 둔다."""
    style_map = _load_text_style_map()
    if not style_map:
        print("  [min-text-size-live] DS text-style 맵 비어있음 — 건너뜀")
        return 0
    fixed = [0]
    # (floor, bucket) → 실제 적용 시 size>=floor 가 되는 DS 스타일 key (run 내 캐시).
    # ⚠️ ds/TEXT_STYLE_MAP.json 이 stale 하면 (예: 14키가 실제 12px) 적용해도 floor 미달 →
    # 다음 스케일로 올려 재검증한다. 바인딩은 항상 유지(set_text_style_id 만 사용).
    resolved = {}

    def _node_style_size(nid):
        try:
            r = parse_content(call_tool("get_nodes_info", {"nodeIds": [nid]})).get("json")
            if isinstance(r, list) and r:
                return ((r[0].get("document") or {}).get("style") or {}).get("fontSize")
        except Exception:
            pass
        return None

    def _resolve_key(floor, bucket, sample_nid):
        if (floor, bucket) in resolved:
            return resolved[(floor, bucket)]
        for t in [s for s in _ds_text_size_scale(style_map) if s >= floor]:
            key = style_map.get((t, bucket)) or style_map.get((t, "medium"))
            if not key:
                continue
            try:
                call_tool("set_text_style_id", {"nodeId": sample_nid,
                          "textStyleId": f"S:{key},{root_node_id}"})
            except Exception:
                continue
            real = _node_style_size(sample_nid)
            if isinstance(real, (int, float)) and real >= floor:
                resolved[(floor, bucket)] = key   # 이 노드는 이미 적용됨
                return key
        resolved[(floor, bucket)] = None
        return None

    def walk(node, in_footer):
        if not isinstance(node, dict):
            return
        if (node.get("type") or "").upper() == "INSTANCE":
            return  # 컴포넌트가 제어 — 건드리지 않음
        nm = (node.get("name") or "").lower()
        in_footer = in_footer or ("footer" in nm)
        nid = node.get("id", "")
        if (node.get("type") or "").upper() == "TEXT" and ";" not in nid:
            tstyle = node.get("style") or {}
            size = tstyle.get("fontSize")
            txt = node.get("characters") or node.get("text") or ""
            if isinstance(size, (int, float)) and not _is_symbol_only_text(txt):
                floor = _TEXT_FLOOR_FINE if in_footer else _TEXT_FLOOR_BODY
                if size < floor:
                    bucket = _weight_bucket(tstyle.get("fontStyle"))
                    cached = resolved.get((floor, bucket), "MISS")
                    if cached == "MISS":
                        key = _resolve_key(floor, bucket, nid)  # 해석 + 이 노드 적용
                        if key:
                            fixed[0] += 1
                    elif cached:
                        try:
                            call_tool("set_text_style_id", {"nodeId": nid,
                                      "textStyleId": f"S:{cached},{root_node_id}"})
                            fixed[0] += 1
                        except Exception as e:
                            print(f"  [min-text-size-live] '{txt[:12]}' fail: {e}")
        for ch in node.get("children", []) or []:
            walk(ch, in_footer)
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_node_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0], False)
    except Exception as e:
        print(f"  [min-text-size-live] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [min-text-size-live] ✓ 작은 텍스트 {fixed[0]}건 → 더 큰 DS 텍스트 스타일 재적용(바인딩 유지)")
    return fixed[0]


def _enforce_white_card_border_live(root_node_id: str) -> int:
    """빌드 후 라이브 트리에서 fill=bg-primary frame 에 보더 1px 강제 (2026-05-27 사용자 분노).

    batch_build_screen 이 blueprint 의 strokeColor/strokeWeight 를 무시하는 버그 회피.
    빌드 트리 walk + bg-primary frame 인데 stroke 없는 것 다 잡아서 박는다.
    - 대상: type=FRAME + fill=#FCFCFD (bg-primary) + children 있음
    - 제외: 루트 자체, 자식이 단일 텍스트인 layout group (Banner Left, Status Marks 등)
    - 🔴 보더 색 (2026-06-02 사용자 룰): **뒤(배경) fill 이 bg-primary 면 border-primary**,
      그 외(bg-secondary/tertiary 등 위) 면 border-secondary. 흰 배경 위 흰 카드는 연한
      border-secondary 로는 경계가 안 보여 — 더 진한 border-primary 로 카드를 정의한다.
      기존에 border-secondary 가 박힌 카드도 흰 배경 위면 border-primary 로 업그레이드.
    - weight: 1px
    """
    BORDER2_R, BORDER2_G, BORDER2_B = 0.902, 0.910, 0.918  # border-secondary
    BORDER1_R, BORDER1_G, BORDER1_B = 0.824, 0.839, 0.859  # border-primary (더 진함)
    BG_PRIMARY_R, BG_PRIMARY_G, BG_PRIMARY_B = 0.988, 0.990, 0.992  # #FCFCFD
    fixed = [0]

    def _is_bg_primary(node):
        fills = node.get("fills") or []
        if not fills:
            return False
        f = fills[0]
        if f.get("type") != "SOLID" or not f.get("visible", True):
            return False
        c = f.get("color") or {}
        return abs(c.get("r", 0) - BG_PRIMARY_R) < 0.02 \
            and abs(c.get("g", 0) - BG_PRIMARY_G) < 0.02 \
            and abs(c.get("b", 0) - BG_PRIMARY_B) < 0.02

    def _stroke_matches(node, tr, tg, tb):
        """이미 목표 색(tr,tg,tb) + weight 1 stroke 가 있으면 True (갱신 불필요)."""
        strokes = node.get("strokes") or []
        if not strokes:
            return False
        if node.get("strokeWeight") != 1:
            return False
        for s in strokes:
            if s.get("visible", True) and s.get("type") == "SOLID":
                c = s.get("color") or {}
                if (abs(c.get("r", 0) - tr) < 0.02 and abs(c.get("g", 0) - tg) < 0.02
                        and abs(c.get("b", 0) - tb) < 0.02):
                    return True
        return False

    def _is_card_like(node):
        """카드 판정 — wrapper 섹션은 제외 (2026-05-27 사용자 명시).

        혼합 케이스(예: 'Attendance Banner Wrap') 처리: wrapper 키워드 + cornerRadius < 8
        이면 wrapper. cornerRadius >= 8 이면 카드 (둥근 모서리는 카드의 시각적 표식).
        """
        if not node.get("children"):
            return False
        if _is_icon_button(node):   # 아이콘 버튼은 카드 아님 (2026-06-09) — 보더 자동부착 차단
            return False
        name = (node.get("name") or "").lower()
        cr = node.get("cornerRadius") or 0
        cr_val = cr if isinstance(cr, (int, float)) else 0
        # wrapper 키워드 검사 — 'banner' 등 카드 키워드와 혼합돼도 cornerRadius 로 판정
        if any(k in name for k in ("section", "wrap", "container", "row", "stack", "group", "list")):
            if cr_val < 8:
                return False  # wrapper 확정 (둥글지 않은 그룹 frame)
            # cornerRadius >= 8 이면 wrapper 이름이지만 카드 (드물지만 가능)
        # 명시적 카드 키워드 OR cornerRadius 둥근 모서리
        if any(k in name for k in ("card", "banner", "hero")):
            return True
        if cr_val >= 8:
            return True
        return False

    def walk(node, is_root, bg_behind_primary):
        if not isinstance(node, dict):
            return
        # DS 인스턴스(badge/button/tag 등) 내부는 master 가 fill/stroke 제어 —
        # 절대 손대지 않는다 (2026-05-28 사용자 "badge 에 stroke 은 없는거란다").
        if (node.get("type") or "").upper() == "INSTANCE":
            return
        # 이 노드가 솔리드 배경을 가지면, 자식 입장에서 "뒤 배경"이 갱신된다.
        child_bg_primary = bg_behind_primary
        if (node.get("type") in ("FRAME", "frame")) and (node.get("fills") or []):
            f0 = (node.get("fills") or [{}])[0]
            if f0.get("type") == "SOLID" and f0.get("visible", True):
                child_bg_primary = _is_bg_primary(node)
        if node.get("type") not in ("FRAME", "frame"):
            for ch in node.get("children", []) or []:
                walk(ch, False, child_bg_primary)
            return
        # 🔻 2026-06-12 시인성-한정으로 강등 (전면 개편): 뒤 배경과 대비가 있는 카드(흰 카드 on
        # 회색 밴드 등)에는 보더를 추가하지 않는다 — author 의도 존중. **흰-on-흰(경계가 안
        # 보이는 배치)만** border-primary 로 카드를 정의한다(시인성 = 정합성이라 유지).
        tr, tg, tb, tok = BORDER1_R, BORDER1_G, BORDER1_B, "border-primary"
        if (not is_root) and bg_behind_primary and _is_bg_primary(node) and _is_card_like(node) \
                and not _stroke_matches(node, tr, tg, tb):
            try:
                call_tool("set_stroke_color", {
                    "nodeId": node["id"],
                    "r": tr, "g": tg, "b": tb, "a": 1,
                    "strokeWeight": 1,
                })
                # 토큰 재바인딩 — set_stroke_color 가 raw RGB 박으면 token alias 풀림
                # _token_to_figma_path 로 정확한 figmaPath 얻어서 사용 (직접 hardcode 시 not-found silent-skip)
                try:
                    fp = _token_to_figma_path(tok)
                    if fp:
                        call_tool("set_bound_variables", {
                            "nodeId": node["id"],
                            "bindings": {"strokes/0": fp},
                        })
                except Exception:
                    pass  # binding 실패해도 raw RGB 는 유지
                fixed[0] += 1
            except Exception as e:
                print(f"  [white-card-border-live] '{node.get('name')}' fail: {e}")
        for ch in node.get("children", []) or []:
            walk(ch, False, child_bg_primary)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_node_id]})).get("json")
        if isinstance(items, list) and items:
            # 루트 배경은 항상 bg-primary (절대 규칙 0) → 최상위 카드 뒤 = bg-primary
            walk(items[0].get("document") or items[0], True, True)
    except Exception as e:
        print(f"  [white-card-border-live] root fetch fail: {e}")

    if fixed[0]:
        print(f"  [white-card-border-live] ✓ 흰-on-흰 카드 {fixed[0]}건 시인성 보더(border-primary) "
              f"(대비 있는 카드는 author 의도 존중 — 미추가)")
    else:
        print(f"  [white-card-border-live] OK — 흰-on-흰 시인성 보더 필요 카드 없음")
    return fixed[0]


def _strip_icon_button_chrome_live(root_node_id: str) -> int:
    """상단바/헤더 아이콘 버튼의 자동 chrome(stroke·중립 fill 박스·radius) 제거 (2026-06-09 사용자 룰).

    사용자: "상단바 좌/우 버튼에 radius·stroke 를 왜 넣냐 — 별도 요청 없으면 기본으로 넣지마."
    아이콘만 든 작은 버튼(back/search/nav 등)은 기본적으로 '아이콘만'이어야 한다. 카드 표면/보더
    enforcer 가 카드로 오인해 붙인 fill+border 와, 작성 시 무심코 넣은 radius 까지 라이브에서 제거.
    - 대상: `_is_icon_button` (작은 프레임 + 자식이 전부 아이콘/vector, `_buttonChrome` 마커 없음)
    - 제거: stroke(strokeWeight 0) + 중립 fill(bg-primary/secondary/tertiary 박스 → 투명) + cornerRadius 0
    - 보존: 의도된 브랜드/색 fill(중립 아님)은 남김(스타일 버튼일 수 있음). DS INSTANCE·내부(';') 제외.
    """
    NEUTRAL = (  # 중립 박스 fill (제거 대상) — bg-primary/secondary/tertiary 근사 RGB
        (0.988, 0.990, 0.992),  # bg-primary
        (0.953, 0.957, 0.965),  # bg-secondary
        (0.910, 0.918, 0.929),  # bg-tertiary
    )
    stripped = [0]

    def _is_neutral_fill(node):
        fills = node.get("fills") or []
        if not fills:
            return False
        f = fills[0]
        if f.get("type") != "SOLID" or not f.get("visible", True):
            return False
        c = f.get("color") or {}
        for nr, ng, nb in NEUTRAL:
            if abs(c.get("r", 0) - nr) < 0.025 and abs(c.get("g", 0) - ng) < 0.025 and abs(c.get("b", 0) - nb) < 0.025:
                return True
        return False

    # 하단 chrome 바(액션바/탭바/FAB/월렛)는 의도된 스타일 버튼이므로 strip 제외 —
    # 사용자 룰은 '상단바' 아이콘 버튼 대상(2026-06-09). bottom bar 버튼 박스는 보존.
    BAR_KW = ("action bar", "actionbar", "cta bar", "tab bar", "tabbar", "bottom", "fab", "wallet", "월렛")

    def walk(node, in_bar=False):
        if not isinstance(node, dict):
            return
        if (node.get("type") or "").upper() == "INSTANCE":
            return  # DS 컴포넌트 색은 master 가 제어 (규칙 0-K)
        nm_low = (node.get("name") or "").lower()
        node_in_bar = in_bar or any(k in nm_low for k in BAR_KW)
        nid = node.get("id") or ""
        if (not node_in_bar) and ";" not in nid and _is_icon_button(node):
            # 1) stroke 제거
            if node.get("strokes"):
                try:
                    call_tool("set_stroke_color", {"nodeId": nid, "r": 0, "g": 0, "b": 0, "a": 1, "strokeWeight": 0})
                except Exception:
                    pass
            # 2) 중립 fill 박스 제거(투명) — 의도된 색 fill 은 보존
            if _is_neutral_fill(node):
                try:
                    call_tool("set_fill_color", {"nodeId": nid, "clear": True})
                except Exception:
                    pass
            # 3) radius 제거
            cr = node.get("cornerRadius")
            if isinstance(cr, (int, float)) and cr > 0:
                try:
                    call_tool("set_corner_radius", {"nodeId": nid, "radius": 0})
                except Exception:
                    pass
            stripped[0] += 1
            return  # 버튼 내부(아이콘)는 더 내려가지 않음
        for ch in node.get("children", []) or []:
            walk(ch, node_in_bar)

    try:
        walk(_collect_tree(root_node_id))
    except Exception as e:
        print(f"  [icon-button-chrome] 트리 조회 실패: {e}")
        return 0
    if stripped[0]:
        print(f"  [icon-button-chrome] ✓ 아이콘 버튼 {stripped[0]}건 chrome 제거 (stroke·중립fill·radius — 기본 무chrome)")
    else:
        print(f"  [icon-button-chrome] OK — chrome 박힌 아이콘 버튼 없음")
    return stripped[0]


# Hero 금액 텍스트 패턴 — 부호(+/−) 또는 천단위 콤마가 있는 명확한 통화 표기
# 예: "+ 0원", "- 0원", "+1,300,000원", "12,500P", "1,000만원"
_HERO_AMOUNT_RE = __import__("re").compile(
    r"^\s*[+\-−]\s*[\d,]+\s*(원|만원|P|p|포인트)\s*$"           # 부호 prefix
    r"|^\s*[\d]{1,3}(,\d{3})+\s*(원|만원|P|p|포인트)\s*$"        # 천단위 콤마
)
_HERO_TEXT_SIZE = 30


def _enforce_text_hierarchy(blueprint: dict) -> None:
    """🔻 2026-06-18 폐기(no-op) — 사용자 결정(#4a 삭제).

    구 동작: 카드 안 통화 hero 금액 텍스트를 30px Bold 로 *자동 승격*. 와이어를 창의적으로
    변형(타이포 위계를 작성자가 자유롭게 결정)하는 것과 충돌 → 삭제. 타이포 위계는 이제
    전적으로 작성자(blueprint fontSize)가 정한다. DS 스케일(2-C)·접근성 하한(min-text-size)만
    정합성 차원에서 유지. 함수 시그니처는 하위호환 위해 유지(no-op)."""
    return


_DIGIT_ONLY_RE = re.compile(r"^\d+$")
_LOCK_NAME_RE = re.compile(r"\b(lock|lk|padlock)\b", re.I)


def _enforce_disabled_slot_pattern(blueprint: dict) -> None:
    """R44 — 참여 불가 슬롯은 lock 아이콘만 있는 회색 박스 (2026-05-24 룰).

    Number-selector grid 안의 "disabled / 참여 불가" 셀이 *숫자 텍스트 + 작은
    lock 아이콘* 으로 그려지면 사용자에게 "선택 가능한데 잠긴 것" 처럼 잘못
    읽힌다. legend swatch 와 동일하게 **lock 아이콘만 있는 bg-tertiary 채움
    박스** 로 정리한다.

    Detection (shape-only, parent-name 무관):
      - 노드가 FRAME
      - 자식 중 digit-only TEXT (예: "6") 가 있음
      - 자식 중 lock-named 아이콘 (lock / lk / padlock) 이 있음

    Legend swatch (예: sw3) 는 lock 만 있고 digit text 가 없으므로 매칭되지
    않는다 — false positive 없음.

    Fix:
      1) digit-only TEXT 자식 제거
      2) fill = $token(bg-tertiary), stroke 제거
      3) auto-layout primaryAxis/counterAxis = CENTER (lock 가운데)
    """
    fixed = 0

    def is_lock_icon(c: dict) -> bool:
        if not isinstance(c, dict):
            return False
        typ = (c.get("type") or "").lower()
        if typ not in ("icon", "vector", "instance"):
            return False
        return bool(_LOCK_NAME_RE.search(c.get("name") or ""))

    def is_digit_text(c: dict) -> bool:
        if not isinstance(c, dict):
            return False
        if (c.get("type") or "").lower() != "text":
            return False
        # blueprint TEXT nodes use 'text' OR 'characters' depending on author.
        s = (c.get("text") or c.get("characters") or "").strip()
        return bool(_DIGIT_ONLY_RE.match(s))

    def walk(node):
        nonlocal fixed
        if not isinstance(node, dict):
            return
        if (node.get("type") or "").lower() == "frame":
            children = node.get("children") or []
            has_digit = any(is_digit_text(c) for c in children)
            has_lock = any(is_lock_icon(c) for c in children)
            if has_digit and has_lock:
                node["children"] = [c for c in children if not is_digit_text(c)]
                node["fill"] = "$token(bg-tertiary)"
                node.pop("stroke", None)
                node.pop("strokeColor", None)
                al = node.setdefault("autoLayout", {})
                al.setdefault("layoutMode", "VERTICAL")
                al["primaryAxisAlignItems"] = "CENTER"
                al["counterAxisAlignItems"] = "CENTER"
                for k in ("paddingTop", "paddingBottom", "paddingLeft", "paddingRight"):
                    al.setdefault(k, 0)
                fixed += 1
        for c in node.get("children", []) or []:
            walk(c)

    walk(blueprint)
    if fixed:
        print(f"[규칙] R44 disabled slot — {fixed}개 셀 정리 (숫자 제거 + bg-tertiary fill)")


def _is_unified_spec_input(data: Any) -> bool:
    """입력 JSON 이 unified spec 인지 감지.

    Unified spec 시그니처:
      - archetype 키 존재 AND (frame 노드 형태가 아님)
      - sections 가 있으면 list of {"type": ...} (spec entry 패턴)
      - 또는 _unified: True 명시
      - type:"frame" / children 의 frame 노드 형식이면 regular blueprint
    """
    if not isinstance(data, dict):
        return False
    if data.get("_unified") is True:
        return True
    if data.get("type") in ("frame", "FRAME"):
        return False  # 일반 blueprint
    if "archetype" not in data:
        return False

    # children 이 이미 박혀 있고 frame/text 노드 형식 → 일반 blueprint
    ch = data.get("children")
    if isinstance(ch, list) and ch and isinstance(ch[0], dict) and ch[0].get("type") in ("frame", "FRAME", "text", "TEXT"):
        return False

    # sections 가 있으면 spec entry 패턴 검증
    secs = data.get("sections")
    if isinstance(secs, list) and secs:
        return all(
            isinstance(s, dict) and "type" in s and "children" not in s and "autoLayout" not in s
            for s in secs[:3]
        )

    # sections 없음 + archetype 있음 → thin spec (base spec 로드해서 sections 가져옴)
    return True


def _maybe_resolve_unified_input(input_data: dict, source_path: str = "") -> dict:
    """입력이 unified spec 이면 build_unified_blueprint() 로 blueprint 변환.

    Resolution order:
      1. 입력이 archetype + wire_content 만 있는 thin spec → archetype_specs/<archetype>.json
         로드 후 base spec + input override 머지
      2. 입력 자체가 full spec (mock_data + sections) → 그대로 사용
      3. unified 아닌 일반 blueprint → 그대로 return

    Returns:
        unified blueprint dict (with _unified=True meta) 또는 input as-is
    """
    if not _UNIFIED_AVAILABLE:
        return input_data
    if not _is_unified_spec_input(input_data):
        return input_data

    archetype = input_data.get("archetype")
    wire_content = input_data.get("wire_content")
    root_name = input_data.get("rootName") or input_data.get("name")

    # base spec 로드 시도 (thin spec 인 경우)
    has_inline_mock = isinstance(input_data.get("mock_data"), dict) and input_data["mock_data"]
    if not has_inline_mock:
        base_spec = _unified_load_spec(archetype) if archetype else None
        if not base_spec:
            print(f"  [unified] archetype spec 없음: {archetype} — legacy mode 로 계속")
            return input_data
        # input override (sections / polish / scenario 등은 input 우선)
        merged = dict(base_spec)
        for k, v in input_data.items():
            if k == "wire_content":
                continue
            merged[k] = v
        spec = merged
    else:
        spec = input_data

    print(f"\n🧬 [Unified] archetype={archetype} — base spec + wire_content → unified blueprint")
    blueprint = _unified_build(spec, wire_content=wire_content, root_name=root_name)
    print(f"   scenario={blueprint.get('_scenario')} / sections={len(blueprint.get('children', []))}")
    return blueprint


_FONT_WEIGHT_WORDS = {
    "thin": 100, "extralight": 200, "extra light": 200, "ultralight": 200,
    "light": 300, "regular": 400, "normal": 400, "book": 400,
    "medium": 500, "semibold": 600, "semi bold": 600, "demibold": 600,
    "bold": 700, "extrabold": 800, "extra bold": 800, "heavy": 800,
    "black": 900,
}


def _normalize_text_font_weight(node: Any) -> int:
    """blueprint TEXT 노드의 문자열 fontWeight 를 숫자로 강제 변환.

    플러그인 createText 의 getFontStyle 는 숫자 weight 만 매핑(700→Bold)하고
    문자열은 default→Regular 로 무시한다. "Bold"/"SemiBold"/"medium" 등 문자열을
    숫자(700/600/500…)로 교정해 위계가 항상 적용되도록 보장. (2026-05-28 시스템 강제)

    반환: 변환한 노드 수.
    """
    count = 0
    if isinstance(node, dict):
        fw = node.get("fontWeight")
        if isinstance(fw, str):
            key = fw.strip().lower()
            num = _FONT_WEIGHT_WORDS.get(key)
            if num is None and key.isdigit():
                num = int(key)
            if num is not None:
                node["fontWeight"] = num
                count += 1
        for v in node.values():
            if isinstance(v, (dict, list)):
                count += _normalize_text_font_weight(v)
    elif isinstance(node, list):
        for it in node:
            count += _normalize_text_font_weight(it)
    return count


def _position_new_root_to_right(root_id: str, gap: int = 200) -> None:
    """새 root frame 을 페이지의 다른 children 우측 빈 공간으로 이동 (2026-06-01 사용자 룰).

    🔴 2026-08-20 선택 노드 우선 배치: 사용자가 Figma 에서 노드를 선택한 채 빌드하면
    ("선택 노드 분석해서 오른쪽에 생성" 표준 명령) — 새 root 를 **선택 노드와 같은 부모에
    insert_child 한 뒤 부모 상대좌표로 선택 노드 바로 오른쪽(gap 50)** 에 나란히 배치한다.
    페이지 전체 maxRight 배치는 페이지가 거대하면(섹션 폭 1.5만px+) 화면 밖 저 멀리 떨어지고,
    선택 노드가 섹션 자식이면 좌표계(섹션 상대 vs 페이지 절대)가 달라 숫자만 맞춰도 어긋난다 —
    같은 부모로 넣으면 좌표계 문제가 소멸한다.

    fallback (선택 없음/자기 자신/폭<200 소형 노드/조회 실패): 기존 페이지 maxRight + gap 배치.
      1. get_document_info 로 currentPage children + bounds(x,y,width) 수집
      2. 다른 children(= 새 root 제외) 의 maxRight = max(x + width) 계산
      3. maxRight + gap 위치로 새 root 를 move_node
      4. 페이지가 비었거나(자기 자신뿐) move 실패 시 silent — (0,0) 유지

    silent fail safe — figma 측 직렬화 이슈 등으로 위치 파악 못 해도 빌드는 계속.
    """
    # ── 선택 노드 우선 배치 (2026-08-20) ──────────────────────
    try:
        sel = parse_content(call_tool("get_selection", {})).get("json") or {}
        sel_nodes = sel.get("selection") or []
        if len(sel_nodes) == 1 and sel_nodes[0].get("id") != root_id:
            sel_id = sel_nodes[0]["id"]
            info = parse_content(call_tool("get_node_info", {"nodeId": sel_id})).get("json") or {}
            sx, sy = info.get("x"), info.get("y")
            sw = info.get("width") or (info.get("absoluteBoundingBox") or {}).get("width")
            parent_id = info.get("parentId")
            if sx is not None and sy is not None and sw and float(sw) >= 200:
                if parent_id:
                    call_tool("insert_child", {"parentId": parent_id, "childId": root_id})
                target_x = int(float(sx) + float(sw) + 50)
                call_tool("move_node", {"nodeId": root_id, "x": target_x, "y": int(float(sy))})
                print(f"  [auto-position] ✓ 새 root → 선택 노드({sel_nodes[0].get('name')}) 우측 "
                      f"동일 부모({parent_id}) x={target_x}, y={int(float(sy))} (gap=50)")
                return
    except Exception as e:
        print(f"  [auto-position] 선택 노드 배치 실패({e}) — 페이지 maxRight 폴백")

    doc_content = call_tool("get_document_info", {})
    doc = parse_content(doc_content).get("json") or {}
    children = doc.get("children") or []

    max_right = 0
    siblings_seen = 0
    for ch in children:
        cid = ch.get("id")
        if not cid or cid == root_id:
            continue  # 자기 자신은 제외
        try:
            x = float(ch.get("x") or 0)
            w = float(ch.get("width") or 0)
        except (TypeError, ValueError):
            continue
        siblings_seen += 1
        right = x + w
        if right > max_right:
            max_right = right

    if siblings_seen == 0:
        print(f"  [auto-position] 페이지 비어있음 — (0,0) 유지")
        return

    target_x = int(max_right + gap)
    call_tool("move_node", {"nodeId": root_id, "x": target_x, "y": 0})
    print(f"  [auto-position] ✓ 새 root → x={target_x}, y=0 "
          f"(기존 {siblings_seen}개 화면 우측, maxRight={max_right:.0f} + gap={gap})")


def _recover_built_root_id(root_name: str, attempts: int = 8, sleep_s: float = 8.0):
    """batch_build_screen 이 client timeout 으로 끊겼을 때, plugin 이 끝낸 root 노드를 찾는다.

    plugin 은 batch_build_screen 응답을 못 보내도 노드 생성은 끝까지 진행하는 경우가 많다.
    이때 cmd_build 가 예외로 죽으면 색 바인딩·text style·post-fix 가 전부 스킵된다.
    get_document_info 를 폴링(plugin 이 batch 마무리 중이면 그 호출도 늦거나 timeout 나므로
    재시도)해, root_name 과 일치하는 가장 최근(가장 큰 id) FRAME 의 id 를 돌려준다.
    (2026-06-01 재발방지 — timeout 나도 완성품이 나오게)"""
    for i in range(attempts):
        try:
            doc = parse_content(call_tool("get_document_info", {})).get("json") or {}
        except Exception:
            doc = {}
        children = doc.get("children") if isinstance(doc, dict) else None
        if isinstance(children, list) and children:
            matches = [c for c in children
                       if isinstance(c, dict) and c.get("name") == root_name
                       and c.get("type") in ("FRAME", "frame")]
            if matches:
                def _idnum(c):
                    try:
                        return int(str(c.get("id", "0:0")).split(":")[-1])
                    except Exception:
                        return 0
                rid = sorted(matches, key=_idnum)[-1].get("id")
                print(f"   [recover] '{root_name}' root 발견 (시도 {i+1}/{attempts}): {rid}")
                return rid
        if i < attempts - 1:
            print(f"   [recover] plugin 아직 빌드 마무리 중… 재시도 {i+1}/{attempts}")
            time.sleep(sleep_s)
    return None


def cmd_build(blueprint_file: str):
    """Build a screen from a blueprint JSON file.

    Supports $token() references in color fields. Before building,
    all $token(name) values are resolved to RGBA using TOKEN_MAP.json.

    또한 입력이 **unified spec** (archetype + sections[].type 형식) 이면
    `build_unified_blueprint()` 로 변환 후 빌드. unified mode 일 땐
    legacy Step A.4 / A.5 (mock fill + polish baseline) skip.

    Example blueprint color:
        "fill": "$token(bg-brand-solid)"
        "fontColor": "$token(fg-brand-primary)"
    These are resolved to {"r": ..., "g": ..., "b": ..., "a": ...} at build time.
    """
    ensure_session()

    with open(blueprint_file) as f:
        blueprint = json.load(f)

    # 🔴 기획 통독 하드 게이트 — 통독+ack 안 했으면 빌드 차단 (2026-06-04 사용자: 매 디자인
    # 생성 시 서비스 맥락을 충분히 이해한 상태 시스템 보장). references S20~S23 와 동일 철학.
    # 2026-08-14: root 이름을 넘겨 비 imin_*(변환 트랙)는 면제 — blueprint 로드를 게이트 앞으로 이동.
    _enforce_planning_read_gate(blueprint.get("name") or blueprint.get("archetype"))

    # 🔴 직전 빌드 self-verify 미완료면 새 빌드 차단 (2026-06-11 — 절대 규칙 0-F 코드 게이트화).
    # 모델(fable 등)이 self-verify 를 조용히 건너뛰고 다음 화면으로 넘어가는 것 방지.
    _enforce_selfverify_gate("build")

    # ⚠️ Refactor A (2026-05-28): unified spec 입력 감지 → build_unified_blueprint()
    blueprint = _maybe_resolve_unified_input(blueprint, blueprint_file)
    _unified_mode = bool(blueprint.get("_unified"))
    if _unified_mode:
        print("🧬 [Build Mode] UNIFIED — Step A.4/A.5 legacy 함수 skip")
    else:
        # archetype 빌드인데 unified spec 으로 전환 안 한 경우 가이드
        _root_name_lc = (blueprint.get("name") or "").lower().replace(" ", "_")
        if any(p in _root_name_lc for p in ("imin_home", "imin_account", "imin_lounge", "imin_my")):
            print("💡 [Build Mode] LEGACY — archetype 빌드는 unified spec 권장:")
            print("   {\"archetype\":\"imin_home\",\"wire_content\":{...}}  ← thin spec")
            print("   archetype_specs/imin_home.json 의 mock_data/polish/sections 자동 사용")

    # ⚠️ Step A.0 (2026-05-28 박힘 — 사용자: "레퍼런스 이미지 검색은 하냐?")
    # references/uibowl 의 1500+ PNG 를 archetype 별 검색 + thumbnail 자동 생성.
    # 빌드 진행 전 Claude 가 PNG Read 강제 (CLAUDE.md 절대 규칙 0-G).
    _skip_ref_reason = _should_skip_reference_step(blueprint)
    if _skip_ref_reason:
        # 🔴 2026-09-04: 1:1 변환 트랙(IMIN_CONVERT_TRACK=1) 또는 root._referencesSkipped(사유
        # 문자열)가 있으면 Step A.0 검색 + 0-G Read 게이트를 건너뛴다 — 레퍼런스가 캡처 자체인
        # 변환에서 FALLBACK 키워드 검색 결과(무관 화면) Read 를 강제해 빌드가 1회 차단되던 낭비.
        print(f"  [Step A.0] skip — {_skip_ref_reason}")
    else:
        _auto_search_uibowl_references(blueprint)

        # 🔴 레퍼런스 Read 하드 게이트 (2026-06-11 — 절대 규칙 0-G 코드 게이트화): Step A.0 가
        # 검색해 출력한 썸네일을 이 세션에서 Read 안 했으면 빌드 차단. 모델(fable 등)이 레퍼런스
        # 시각학습을 조용히 건너뛰는 것 방지. (검색은 코드 강제였으나 Read 는 모델 자율이었음.)
        _enforce_reference_read_gate()

    # ⚠️ Step A (2026-05-28 박힘): imin_home archetype → 사용자 결정형 polished
    # 디자인 (16941:51284) 자동 export + 로그. Claude 가 매번 새 세션에서 시각
    # reference 를 안 보고 빌드해 "와이어 1:1 복제 회귀" 가 반복되어 박음.
    _auto_export_canonical_reference(blueprint)

    # ⚠️ Step A.4 (2026-05-28 박힘 — 사용자 명시 "데이터 있는 화면으로 생성"):
    # 와이어가 empty state(0원/0건/0일) 면 mock data 로 자동 치환.
    # L1 와이어 1:1 룰 폐기 — 사용자가 "데이터 보이는 화면" 명시 지시.
    # Refactor A (2026-05-28): unified mode 면 generator 가 이미 mock/wire 통합 → skip
    if _unified_mode:
        print("  [Step A.4] unified mode → mock fill skip (generator 가 처리)")
    else:
        _HARD_fill_mock_data_when_empty(blueprint)

    # ⚠️ Step A.5 (2026-05-28 박힘 — 사용자 신뢰 파탄 후): imin_home polish baseline
    # 자동 inject. [feedback_imin_home_polish_baseline] catalog 의 시각 패턴을
    # blueprint 에 자동 박음 — 와이어 콘텐츠 보존 + 시각 enrichment.
    # Refactor A (2026-05-28): unified mode 면 generator 가 polish baseline 박음 → skip
    if _unified_mode:
        print("  [Step A.5] unified mode → polish baseline skip (generator 가 처리)")
    else:
        _enrich_imin_home_polish(blueprint)

    # ⚠️ 시스템 규칙 (2026-05-28 사용자 분노 "텍스트 크기·굵기 위계 무시"): 플러그인
    # createText 의 getFontStyle 는 *숫자* fontWeight 만 인식(700→Bold). blueprint 가
    # "Bold"/"SemiBold" 같은 문자열을 주면 default→Regular(400) 로 전부 무시돼 텍스트가
    # 평평해진다. 빌드 전 문자열 weight 를 숫자로 강제 변환 (어느 세션에서 작성하든 보장).
    _normalize_text_font_weight(blueprint)

    # ⚠️ 텍스트 크기 하한 (2026-06-05): 기본16/보조14/12는 미세문구만 — 12pt 남용 차단
    _enforce_min_text_size(blueprint)

    # ⚠️ 시스템 규칙: 루트 프레임 배경은 반드시 bg-primary — 다른 값이 와도 강제 교정
    _enforce_root_bg_primary(blueprint)

    # ⚠️ 시스템 규칙: modal 패턴 → 색상 advisory → 카드 표면 → elevation → 타이포 위계 → 섹션 divider → tooltip ignore auto layout → disabled slot 패턴
    _enforce_modal_pattern(blueprint)
    _enforce_bottom_sheet_pattern(blueprint)  # 2026-05-27 — bottom sheet modal 기본형
    _enforce_radius_clip_blueprint(blueprint)  # 2026-06-04 — radius>0 frame 은 clipsContent=true
    _enforce_color_restraint(blueprint)
    _enforce_card_surface(blueprint)
    _enforce_card_elevation(blueprint)  # 2026-05-27 — shadow 자동 주입 폐기 (제거기로 작동)
    _enforce_no_large_brand_fill(blueprint)  # 2026-05-27 — 큰 면적 frame brand fill 금지
    _enforce_symmetric_vpad(blueprint)  # 2026-06-05 — 세로 패딩 대칭 강제(무의식적 비대칭 차단)
    _enforce_section_band(blueprint)  # 2026-06-05 — 중요 섹션 풀폭 밴드(_band) 표준화
    _enforce_home_content_gap(blueprint)  # 2026-06-08 — 홈 Content 섹션 gap=spacing-2xl(20)
    _enforce_brand_tint_surface_primary(blueprint)  # 2026-06-05 — 브랜드 틴트 면=bg-brand-primary
    _enforce_white_card_border(blueprint)  # 2026-05-27 — fill=bg-primary frame 자동 border
    _enforce_text_hierarchy(blueprint)  # 🔻 2026-06-18 no-op(폐기) — 타이포 위계는 작성자 자유
    _enforce_cta_caption_secondary(blueprint)  # 2026-06-08 — CTA 유도 caption=text-secondary
    _enforce_section_dividers(blueprint)
    _enforce_tooltip_ignore_auto_layout(blueprint)
    _enforce_disabled_slot_pattern(blueprint)

    # 자동 바인딩용 원본 보존 ($token() 참조가 살아있는 사본 — resolve 전에 떠둠)
    original_blueprint = json.loads(json.dumps(blueprint))

    # Step E.0: ⚠️ archetype config reuse 검출 + _wireframeContent 의무 (2026-05-27 절대 룰 0-E)
    #          + S24 컨셉 선언 게이트 + novelty 시그니처 비교 (2026-06-12 전면 개편)
    archetype_issues = _check_no_archetype_reuse(blueprint, blueprint_file)
    wc_required_issues = _check_wireframe_content_required(blueprint)
    concept_issues = _check_concept_required(blueprint)
    # S25 디자인 방향 선언 + novelty 소프트 게이트 (2026-06-15 — 발산 강제: "100번 생성해도
    # 다 똑같다" 차단). 콘텐츠는 1:1, 비주얼은 매 시안 다른 방향.
    direction_issues = _check_design_direction_required(blueprint)
    novelty_issues = _check_novelty_gate(original_blueprint)
    # S26 와이어/PRD 발산 선언 (2026-06-18 — "와이어 이미지를 그대로 똑같은 UI로 구현" 차단).
    # 0-C/0-N(와이어 1:1 복제 금지)을 advisory→하드 게이트로 승격.
    divergence_issues = _check_wireframe_divergence_required(blueprint)
    # S27 재구성 맵 (2026-07-15 — 새 세션마다 와이어 트레이싱이 재발하던 문제의 결정타:
    # 선언을 실물(blueprint 트리)과 대조. "포장된 트레이싱"(섹션 1:1 카드 래핑)도 차단).
    restructure_issues = _check_restructure_map_required(blueprint)
    archetype_issues = (archetype_issues + wc_required_issues + concept_issues
                        + direction_issues + novelty_issues + divergence_issues
                        + restructure_issues)
    if archetype_issues:
        print(f"\n[archetype-check] {len(archetype_issues)}건 발견:")
        for ai in archetype_issues:
            print(f"  {ai}")

    # Step 0.5: ⚠️ design_rules REGISTRY — LINT + INJECT phase (2026-05-27 dispatcher 박힘)
    # 이전엔 R/S 룰들이 register 만 되고 호출 안 됐음 — 사용자 분노 fix
    registry_issues: list = []
    try:
        # design_rules 폴더가 scripts/ 안 — sys.path 추가 후 import
        import sys as _sys
        _scripts_dir = os.path.dirname(os.path.abspath(__file__))
        if _scripts_dir not in _sys.path:
            _sys.path.insert(0, _scripts_dir)
        from design_rules import REGISTRY as _REG, Severity as _Sev  # noqa: E402

        # LINT phase
        print("\n[design_rules:LINT] 룰 검증 중...")
        lint_violations = _REG.run_lint(blueprint)
        lint_errors = [v for v in lint_violations if v.severity == _Sev.ERROR]
        lint_warns = [v for v in lint_violations if v.severity == _Sev.WARN]
        if lint_violations:
            print(f"  [LINT] {len(lint_errors)} ERROR / {len(lint_warns)} WARN")
            for v in lint_violations[:30]:
                print(f"    {v.format()}")
            if len(lint_violations) > 30:
                print(f"    ... +{len(lint_violations)-30}개")
        else:
            print("  [LINT] ✓ 모든 룰 통과")
        # ERROR 를 registry_issues 에 박아 build 차단 분기에 합산
        for v in lint_errors:
            registry_issues.append(f"ERROR ({v.rule_id}): {v.path}: {v.message}")
        for v in lint_warns:
            registry_issues.append(f"WARN ({v.rule_id}): {v.path}: {v.message}")

        # INJECT phase — blueprint 변형
        print("[design_rules:INJECT] 룰 자동 주입 중...")
        blueprint = _REG.run_inject(blueprint)
        print("  [INJECT] ✓ 완료")
    except Exception as e:
        print(f"  [design_rules] dispatcher 실패 — 무시하고 계속: {e}")

    # 2026-05-28 — children 에 섞인 non-dict(int 등) 노드 sanitize. generator/inject/
    # _enforce pre-process 중 어떤 경로가 children 리스트에 잘못된 int 를 넣어
    # validate_blueprint 가 AttributeError 로 죽는 회귀 차단. 디자인 노드는 항상 dict.
    _n_stripped = [0]
    def _strip_non_dict_children(node):
        if isinstance(node, dict):
            ch = node.get("children")
            if isinstance(ch, list):
                clean = [c for c in ch if isinstance(c, dict)]
                if len(clean) != len(ch):
                    _n_stripped[0] += len(ch) - len(clean)
                    node["children"] = clean
                for c in clean:
                    _strip_non_dict_children(c)
    _strip_non_dict_children(blueprint)
    if _n_stripped[0]:
        print(f"  [sanitize] children 의 non-dict 노드 {_n_stripped[0]}개 제거 (generator artifact)")

    # Step 1: Validate blueprint before any processing
    issues = validate_blueprint(blueprint)
    issues = issues + archetype_issues + registry_issues  # 모든 이슈 합산
    errors = [i for i in issues if i.startswith("ERROR")]
    warns = [i for i in issues if i.startswith("WARN")]
    if errors:
        print(f"\n{'='*50}")
        print(f"BLUEPRINT VALIDATION FAILED — {len(errors)} error(s), {len(warns)} warning(s):")
        for issue in issues:
            print(f"  {issue}")
        print(f"{'='*50}\n")
        print("Fix errors before building. Use --force to skip validation.")
        if "--force" not in sys.argv:
            _emit_build_summary("blocked", codes=_codes_for_issues(errors),
                                issues=errors, warnings=warns,
                                note="blueprint 수정 후 다시 build (--force 로 검증 skip 가능)")
            return
    elif warns:
        print(f"Blueprint validation: {len(warns)} warning(s)")
        for w in warns:
            print(f"  {w}")

    # Step 2: Flatten padding objects in autoLayout before build
    blueprint = _flatten_padding_objects(blueprint)

    # Step 3: Resolve $token() references to RGBA using latest TOKEN_MAP.json
    token_count = _count_token_refs(blueprint)
    if token_count > 0:
        print(f"Resolving {token_count} $token() references from TOKEN_MAP.json...")
        blueprint = resolve_tokens_in_blueprint(blueprint)
        print_resolved_color_summary()

    children_count = len(blueprint.get('children', []))
    root_name = blueprint.get('name', 'unnamed')
    print(f"Building '{root_name}' with {children_count} top-level children...")

    # ── Step 3.5: Yoga 레이아웃 시뮬레이션 (서버 불필요, CLI 직접 호출) ──
    sim_result = None
    print("\n[SIM] Yoga 레이아웃 시뮬레이션 중...")
    sim_start = time.time()
    try:
        import subprocess
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        yoga_js = os.path.join(project_root, "out", "yoga-cli", "index.js")
        if os.path.exists(yoga_js):
            # 빌드 산출물을 node로 직접 실행 — npx 불필요.
            # Windows에서 ["npx", ...]는 npx.cmd를 못 찾아 WinError 2로 실패하므로 회피.
            yoga_cmd = ["node", yoga_js]
        else:
            # fallback: 소스를 npx tsx로 실행 (Windows는 npx.cmd)
            npx_bin = "npx.cmd" if os.name == "nt" else "npx"
            yoga_cmd = [npx_bin, "tsx", os.path.join(project_root, "src", "yoga-cli.ts")]
        proc = subprocess.run(
            yoga_cmd,
            input=json.dumps(blueprint),
            capture_output=True, text=True, timeout=10,
            cwd=project_root
        )
        if proc.returncode == 0 and proc.stdout.strip():
            sim_result = json.loads(proc.stdout)
        elif proc.stderr:
            print(f"[SIM] CLI 오류: {proc.stderr.strip()}")

        if sim_result:
            issues_count = sim_result.get("issues_count", 0)
            elapsed = sim_result.get("elapsed_ms", 0)
            layout_info = sim_result.get("layout", {})

            if issues_count > 0:
                print(f"[SIM] {issues_count}개 이슈 탐지 ({elapsed}ms)")
                for issue in sim_result.get("issues", [])[:10]:
                    print(f"  - [{issue.get('type')}] {issue.get('message')}")
                fixed = sim_result.get("fixedBlueprint")
                if fixed:
                    blueprint = fixed
                    print(f"[SIM] Blueprint 자동 수정 적용 완료")
            else:
                print(f"[SIM] 이슈 없음 ({elapsed}ms)")

            if layout_info.get("suggestedRootHeight"):
                print(f"[SIM] 사전 계산: contentBottom={layout_info.get('contentBottom')}, "
                      f"fabY={layout_info.get('suggestedFabY')}, "
                      f"tabY={layout_info.get('suggestedTabBarY')}, "
                      f"rootH={layout_info.get('suggestedRootHeight')}")

        print(f"[SIM] 완료 ({time.time() - sim_start:.1f}s)")
    except Exception as e:
        print(f"[SIM] 시뮬레이션 실패 (무시하고 계속): {e}")

    # Step C: 빌드 실행
    start = time.time()
    try:
        content = call_tool("batch_build_screen", {"blueprint": blueprint})
        result = parse_content(content)
    except Exception as build_err:
        # ⚠️ batch_build_screen 이 client timeout(기본 300s)으로 끊겨도 plugin 은 노드
        # 생성을 끝까지 진행하는 경우가 많다. 예외로 cmd_build 가 여기서 죽으면 색 변수
        # 바인딩(E.5)·text style(E.5.5)·post-fix 등 후속이 전부 스킵되어, 색/스타일이
        # 안 박힌 반쪽 화면이 남는다(2026-06-01 사용자 보고된 3개 회귀의 공통 뿌리).
        # → 생성된 root 를 복구해 후속 단계를 그대로 잇는다. (재발방지)
        print(f"\n⚠️ batch_build_screen 응답 끊김: {build_err}")
        print("   plugin 은 노드 생성을 계속했을 수 있음 → 생성된 root 탐색 중...")
        recovered = _recover_built_root_id(blueprint.get("name"))
        if not recovered:
            print("   ❌ root 복구 실패 — plugin 연결/상태 확인 필요. 빌드 중단.")
            raise
        result = {"json": {"rootId": recovered}, "texts": [], "images": [], "raw": []}
        print(f"   ✓ root 복구: {recovered} — 후속 단계(색 바인딩·text style·post-fix) 계속 진행")
    build_elapsed = time.time() - start

    # Step D: 빌드 결과 추출
    root_id = None
    total_nodes = None
    node_map = None
    if result["json"]:
        root_id = result["json"].get("rootId") or result["json"].get("nodeId")
        total_nodes = result["json"].get("totalNodes")
        node_map = result["json"].get("nodeMap")

    print(f"\n{'='*50}")
    print(f"BUILD COMPLETE in {build_elapsed:.1f}s")
    if root_id:
        print(f"  rootId: {root_id}")
    if total_nodes:
        print(f"  totalNodes: {total_nodes}")
    if node_map is not None:
        print(f"  nodeMap keys: {len(node_map)}")
        if len(node_map) == 0:
            print(f"  ⚠️ nodeMap이 비어있음 — 이미지 이름 매칭 불가할 수 있음")
        for i, (name, nid) in enumerate(node_map.items()):
            if i >= 10:
                print(f"  ... and {len(node_map) - 10} more")
                break
            print(f"    {name}: {nid}")
    print(f"{'='*50}")

    if result["images"]:
        print(f"[Screenshot returned: {result['images'][0]['data_length']} bytes]")

    # Step D.5 — 새 root 우측 빈 공간 자동 배치 (2026-06-01 사용자 룰)
    # batch_build_screen 은 새 root 를 (0,0) 에 박는다 → 같은 페이지에 다른 화면이
    # 있으면 정확히 겹친다. 페이지의 다른 children 의 maxRight 를 구해 새 root 를
    # (maxRight + gap, 0) 로 이동해 겹침을 자동 차단.
    if root_id:
        try:
            _position_new_root_to_right(root_id, gap=200)
        except Exception as e:
            print(f"  [auto-position] skipped (무시하고 계속): {e}")

    # Step E-0: 루트 clipsContent + FIXED 설정 (layoutMode 재설정 금지!)
    # ★ 주의: set_auto_layout으로 layoutMode를 재설정하면 Figma가 자식들의
    #   layoutSizingHorizontal을 HUG로 리셋함 → 반드시 개별 속성만 설정
    if root_id:
        try:
            # clipsContent만 별도 설정 (layoutMode 재설정 없이)
            # get_node_info로 현재 layoutMode 확인 후 필요 시에만 설정
            try:
                root_info_content = call_tool("get_node_info", {"nodeId": root_id})
                root_info = parse_content(root_info_content).get("json") or {}
                root_layout = root_info.get("layoutMode", "")
            except Exception:
                root_layout = ""

            if root_layout != "VERTICAL":
                # auto-layout이 아직 미설정인 경우에만 설정
                call_tool("set_auto_layout", {
                    "nodeId": root_id,
                    "layoutMode": "VERTICAL",
                    "itemSpacing": 0,
                    "paddingTop": 0,
                    "paddingBottom": 0,
                    "paddingLeft": 0,
                    "paddingRight": 0,
                    "clipsContent": True
                })
                print("\n✅ 루트 auto-layout VERTICAL 설정 완료 (최초)")
            else:
                # 이미 VERTICAL → layoutMode 재설정 금지 (자식 sizing 리셋 방지)
                # clipsContent는 batch_build_screen에서 이미 설정됨
                print("\n✅ 루트 이미 VERTICAL — layoutMode 재설정 건너뜀 (자식 sizing 보호)")

            # ★ 핵심: layoutSizingVertical을 FIXED로 설정
            # ABSOLUTE 자식(FAB/Tab Bar)이 흐름에서 빠지면 HUG가 높이를 축소시키므로
            # FIXED로 강제 설정하여 post-fix의 resize_node가 작동하도록 보장
            call_tool("set_layout_sizing", {
                "nodeId": root_id,
                "vertical": "FIXED"
            })
        except Exception as e:
            print(f"\n⚠️ 루트 설정 실패 (무시): {e}")

    # Step E: post-fix (2회 실행 — 1회차: FILL 수정 + 배치, 2회차: 레이아웃 안정화 후 최종 배치)
    if root_id:
        # ⚠️ 2026-05-24 사용자 "다 박아" — latest 빌드 정보를 저장. cmd_post_fix가
        # 인자 없이 호출돼도 blueprint auto-load하여 토큰 재바인딩 가능.
        try:
            _save_latest_build(root_id, os.path.abspath(blueprint_file))
        except Exception:
            pass
        print("\n🔧 자동 후처리 실행 중...")
        sim_layout = sim_result.get("layout") if sim_result else None
        cmd_post_fix(root_id, pre_computed_layout=sim_layout, original_blueprint=original_blueprint, injected_blueprint=blueprint)
        print("\n🔧 후처리 2회차 (레이아웃 안정화 후 최종 배치)...")
        cmd_post_fix(root_id, original_blueprint=original_blueprint, injected_blueprint=blueprint)
    else:
        print("⚠️  rootId를 찾을 수 없어 post-fix를 건너뜁니다.")

    # Step E.5: DS 변수 자동 바인딩 (색상·타이포) — $token() blueprint 기반
    if root_id:
        print("\n🔗 DS 변수 자동 바인딩 중...")
        try:
            auto_bind_design(root_id, original_blueprint)
        except Exception as e:
            print(f"  [auto-bind] 실패 (무시하고 계속): {e}")

    # Step E.5.4: imageQuery 노드에 실사진 자동 적용 (2026-05-28 사용자 명시 —
    # placeholder 보라 블록 금지). keyless 이미지 소스에서 받아 set_image_fill +
    # placeholder icon 삭제. 네트워크 실패 시 placeholder 유지.
    if root_id:
        print("\n🖼️  imageQuery 실사진 자동 적용 중...")
        try:
            apply_image_queries(root_id, original_blueprint)
        except Exception as e:
            print(f"  [apply-images] 실패 (무시하고 계속): {e}")

    # Step E.5.5: DS Text Style 자동 적용 (2026-05-24 복원 — 머지로 소실된 기능 복구)
    if root_id:
        print("\n🔤 DS Text Style 자동 적용 중...")
        try:
            _apply_ds_text_styles(root_id)
        except Exception as e:
            print(f"  [text-style] 실패 (무시하고 계속): {e}")

    # Step E.5.6: DS Effect Style (Shadows/*) 자동 적용 (2026-05-26)
    # 빌드 시 frame.effects 가 raw 값으로 박혀 있어도 fingerprint 매칭으로 DS 스타일에 바인딩.
    if root_id:
        # 2026-05-27 사용자 룰 — non-interactive UI (badge/pill/progress bar/icon wrap)
        # 에서 drop shadow 제거. interaction surface (카드/버튼) 에만 elevation 의미.
        print("\n🌑 비-interaction UI shadow 제거 중...")
        try:
            _remove_shadow_from_non_interactive(root_id)
        except Exception as e:
            print(f"  [no-shadow-deco] 실패 (무시하고 계속): {e}")

        # 2026-05-27 — DS Effect Style (Shadows) 자동 적용 폐기.
        # 사용자 명시: drop-shadow 적용 절대 금지. 빌드된 트리의 모든 frame effects 제거로 대체.
        print("\n🌑 빌드 트리 drop-shadow 전면 제거 중...")
        try:
            cleared = _strip_all_drop_shadows(root_id)
            if cleared:
                print(f"  [no-shadow] ✓ frame {cleared}건의 drop-shadow 제거 완료")
            else:
                print("  [no-shadow] OK — drop-shadow 가진 frame 없음")
        except Exception as e:
            print(f"  [no-shadow] 실패 (무시하고 계속): {e}")

    # Step E.6: QA — blueprint text 노드 무결성 검증 (이모지/아이콘 오변환 사고 차단)
    if root_id:
        print("\n🔎 QA — 텍스트 노드 무결성 검증 중...")
        try:
            _qa_blueprint_integrity(original_blueprint, root_id)
        except Exception as e:
            print(f"  [QA] 실패 (무시하고 계속): {e}")

    # Step E.6.5: QA — 와이어 콘텐츠 매치 검증 (2026-05-27 룰 0-E)
    if root_id:
        print("\n🔎 QA — 와이어 콘텐츠 매치 검증 중...")
        try:
            _qa_wireframe_content_match(original_blueprint, root_id)
        except Exception as e:
            print(f"  [QA-wc] 실패 (무시하고 계속): {e}")

    # Step E.7: QA — 가시성(대비) + 레이아웃(겹침/데드밴드) 자동 검사
    if root_id:
        print("\n🔎 QA — 대비/레이아웃 시각 검사 중...")
        try:
            _qa_visual_checks(root_id)
        except Exception as e:
            print(f"  [QA] 시각 검사 실패 (무시하고 계속): {e}")

    # Step E.7.5: ⚠️ design_rules REGISTRY — AUTO_FIX + VERIFY phase (2026-05-27)
    if root_id:
        try:
            import sys as _sys
            _scripts_dir = os.path.dirname(os.path.abspath(__file__))
            if _scripts_dir not in _sys.path:
                _sys.path.insert(0, _scripts_dir)
            from design_rules import REGISTRY as _REG, Severity as _Sev  # noqa: E402

            # tree 한 번 가져옴 (룰들이 공유)
            try:
                _c = call_tool("get_nodes_info", {"nodeIds": [root_id]})
                _items = parse_content(_c).get("json")
                _tree = _items[0].get("document") if isinstance(_items, list) and _items else {"id": root_id}
            except Exception:
                _tree = {"id": root_id}
            _ctx = {"root_id": root_id, "blueprint": original_blueprint}

            # AUTO_FIX phase
            print("\n[design_rules:AUTO_FIX] 룰 자동 fix 중...")
            counts = _REG.run_auto_fix(_tree, _ctx)
            if counts:
                for rid, n in counts.items():
                    print(f"  [{rid}] 자동 fix {n}건")
            else:
                print("  [AUTO_FIX] ✓ 자동 fix 대상 없음")

            # VERIFY phase
            print("[design_rules:VERIFY] 빌드 후 룰 검증 중...")
            v_violations = _REG.run_verify(_tree, _ctx)
            v_errors = [v for v in v_violations if v.severity == _Sev.ERROR]
            v_warns = [v for v in v_violations if v.severity == _Sev.WARN]
            if v_violations:
                print(f"  [VERIFY] {len(v_errors)} ERROR / {len(v_warns)} WARN")
                for v in v_violations[:20]:
                    print(f"    {v.format()}")
                if len(v_violations) > 20:
                    print(f"    ... +{len(v_violations)-20}개")
            else:
                print("  [VERIFY] ✓ 모든 룰 통과")
        except Exception as e:
            print(f"  [design_rules:post] dispatcher 실패 — 무시하고 계속: {e}")

    # ⚠️ Step E.7.6 — 고정 사이즈 invariant 최종 재강제 (2026-05-28 회귀 fix).
    # design_rules AUTO_FIX phase (E.7.5) 는 cmd_post_fix 의 final invariant *이후* 에
    # 돌기 때문에, R36(carousel-vfix) 같은 룰이 FAB/원형 frame 의 vertical 을 HUG 로
    # 바꿔 56×56 → 56×24 로 다시 찌그러뜨릴 수 있다 (실측: 'R36 carousel-vfix: FAB
    # V=HUG'). post-fix 뒤 어떤 룰이 또 건드려도 56×56 이 마지막 말이 되도록 여기서
    # 순서 무관하게 최종 보장. (R36 detection 자체도 FAB 제외하도록 고쳤지만, 다른
    # 룰의 미래 회귀까지 막는 defense-in-depth.)
    if root_id:
        try:
            n_inv2 = _enforce_fixed_size_invariants_final(root_id)
            if n_inv2:
                print(f"\n[Step E.7.6] 고정 사이즈 invariant 재강제 {n_inv2}건 (AUTO_FIX 후 회귀 차단)")
        except Exception as e:
            print(f"  [size-invariant-2] 실패 (무시): {e}")

    # ⚠️ Step E.7.7 — blueprint 명시 FIXED 폭/padding 최종 복원 (2026-06-04).
    # design_rules AUTO_FIX(E.7.5)·spacing 바인더가 author padding(paddingLeft 0 회귀)·
    # FIXED 폭(Date Cell)을 다시 망치므로, **모든 단계의 맨 끝**에서 blueprint 값을 재단언해
    # 최종 권한을 갖는다. (cmd_post_fix 안에서 해도 AUTO_FIX 가 뒤에 돌아 덮어써서 무력화됨.)
    if root_id:
        try:
            _final_bp = blueprint if isinstance(blueprint, dict) else original_blueprint
            n_fw = _enforce_fixed_widths(root_id, _collect_fixed_widths(_final_bp))
            n_bp = _enforce_blueprint_padding(root_id, _collect_blueprint_padding(_final_bp))
            # 🔴 intent 존중 (2026-06-10): `_keepSizing` 노드의 선언 H/V 사이징을 최종 재단언.
            # FILL/vertical-hug enforcer 가 author HUG/FIXED 를 망쳐도 여기서 되돌린다.
            n_ks = _enforce_keep_sizing_live(root_id, _collect_keep_sizing(_final_bp))
            n_tf = _enforce_text_fill_live(root_id, _collect_text_fill_keys(_final_bp))
            if n_fw or n_bp or n_ks or n_tf:
                print(f"[Step E.7.7] blueprint FIXED 폭 {n_fw}건 + padding {n_bp}건 + _keepSizing {n_ks}건 + TEXT FILL {n_tf}건 최종 복원")
        except Exception as e:
            print(f"  [bp-final] 실패 (무시): {e}")

        # 🔴 인디케이터 대칭 gap 최종 재단언 (2026-06-08 사용자: "dot indicator 가 아래 frame 에
        # 딱 붙어있다"). 원인: blueprint 가 Hero paddingBottom=0 으로 작성되면 post-fix 의
        # _enforce_indicator_symmetric_gap(pb=gap 교정)이 바로 위 _enforce_blueprint_padding(E.7.7)
        # 의 blueprint 값(pb=0) 재단언에 덮여 무력화 → 인디케이터가 아래 섹션(밴드)에 밀착.
        # blueprint padding 재단언 *직후* 다시 적용해 '인디케이터 위 gap = 아래 padding' 규칙이
        # 최종 권한을 갖게 한다(authoring 이 pb≠gap 이어도 견고). [[autofix-runs-after-postfix]]
        try:
            _enforce_indicator_symmetric_gap(root_id)
        except Exception as e:
            print(f"  [indicator-gap-final] 실패 (무시): {e}")

        # 절대규칙 0-O (2026-06-04): NavBar fill=bg-primary + 좌측 back btn stroke 제거.
        # AUTO_FIX·white-card-border *이후* 에 해야 back btn 에 border 가 재부착되지 않는다.
        try:
            _enforce_navbar_style_live(root_id)
        except Exception as e:
            print(f"  [navbar] 실패 (무시): {e}")

        # 절대규칙 0-Q (2026-06-04): radius>0 frame 은 clipsContent=true. R45(post-fix +
        # AUTO_FIX 두 곳)가 시트/카드 clip 을 false 로 끄는데, get_nodes_info 가 개별 코너
        # radius 를 None 으로 직렬화해 R45 의 rounded-card 예외가 시트를 놓친다 → **AUTO_FIX
        # 이후** blueprint 의 radius 정보로 name-path 매칭해 clip=true 를 최종 재단언.
        try:
            _final_bp2 = blueprint if isinstance(blueprint, dict) else original_blueprint
            n_clip = _enforce_radius_clip_live(root_id, _collect_radius_clip_paths(_final_bp2))
            if n_clip:
                print(f"[Step E.7.7] radius>0 frame {n_clip}건 clipsContent=true 최종 재단언")
        except Exception as e:
            print(f"  [radius-clip-final] 실패 (무시): {e}")

        # 🔴 바텀시트 root = black 50%(dim) 최종 재단언 (2026-06-04 사용자) — AUTO_FIX 가
        # root 를 bg-primary 로 되돌릴 수 있으므로 맨 끝에서 다시 dim 으로.
        try:
            _st2 = (_screen_type_from_blueprint(_final_bp2)
                    or _screen_type_from_blueprint(original_blueprint))
            if _is_bottom_sheet_screen_type(_st2):
                _enforce_root_bg_primary_live(root_id, screen_type=_st2)
        except Exception as e:
            print(f"  [root-dim-final] 실패 (무시): {e}")

        # 🔵 레이아웃 스멜 검사 (2026-06-10) — 모든 레이아웃 재단언이 끝난 *최종 상태*에서
        # 결정적으로 회귀 패턴(SPACE_BETWEEN+FILL 뭉침 / 짧은 텍스트 wrap / 폭 붕괴)을 노출.
        # 스크린샷 self-verify 전에 '여길 보라'를 가리킨다. 차단 안 함(WARN).
        try:
            print("\n🔎 QA — 레이아웃 스멜 검사 중...")
            _qa_layout_smells(root_id)
        except Exception as e:
            print(f"  [smell] 실패 (무시): {e}")

    # Step G: NavBar 로고 인스턴스 교체
    if node_map and "Logo Placeholder" in node_map:
        print("\n🔲 NavBar 로고 교체 중...")
        try:
            placeholder_id = node_map["Logo Placeholder"]
            navbar_id = node_map.get("NavBar")
            if navbar_id:
                # 로고 컴포넌트 인스턴스 생성
                logo_content = call_tool("create_component_instance", {
                    # Imin DS Logo (DS v7 957912b0 폐기, 2026-06-02)
                    "componentKey": "81efeddd245e95f31a2724aa370ee54d3caf93d0"
                })
                logo_result = parse_content(logo_content)
                logo_id = None
                if logo_result.get("json"):
                    logo_id = logo_result["json"].get("id")
                if logo_id:
                    # NavBar에 첫 번째 자식으로 삽입
                    call_tool("insert_child", {
                        "parentId": navbar_id,
                        "childId": logo_id,
                        "index": 0
                    })
                    # 기존 placeholder 삭제
                    call_tool("delete_node", {"nodeId": placeholder_id})
                    print(f"  ✅ 로고 인스턴스 교체 완료 (placeholder {placeholder_id} → logo {logo_id})")
                else:
                    print(f"  ⚠️ 로고 인스턴스 생성 실패")
        except Exception as e:
            print(f"  ⚠️ 로고 교체 실패 (무시): {e}")

    # ⚠️ Step F (frontend spec → json/) 폐기 (2026-06-05 사용자: "디자인 생성되면 json 폴더에
    # json 생성되게 하는것도 삭제해. 생성할 필요없어졌어"). 더 이상 빌드 때 json/ 에 frontend
    # spec 을 쓰지 않는다. _export_frontend_spec / gen_frontend_spec.py 는 호출하지 않는다.

    # ⚠️ Step H (2026-05-28 박음) — self-verify 강제 시스템.
    # Claude 가 "검증 ✅" 보고 전 무조건 섹션별 zoom-in PNG 6장 Read + 12-checklist
    # 작성하도록 강제. 코드는 LLM 행동을 강제 못하지만 (1) PNG 자동 export
    # (2) checklist 빈 템플릿 생성 (3) stdout 강력 경고로 self-verify-required 표식.
    # 사용자가 화면에서 SECTION-QA-PNG 라인을 보면 Claude 가 검증 skip 했는지 즉시 파악 가능.
    if root_id:
        try:
            _self_verify_section_qa_export(root_id, blueprint)
        except Exception as e:
            print(f"  ⚠️ Step H self-verify export 실패 (무시): {e}")

    total_elapsed = time.time() - start
    print(f"\n{'='*50}")
    _print_call_stats("build-tail")  # post-fix 이후 구간(바인딩/QA)의 시간 분해
    print(f"전체 완료: {total_elapsed:.1f}s (빌드 {build_elapsed:.1f}s + 후처리)")
    # ⚠️ 2026-05-24 사용자 "다 박아" — latest rootId 명시 (post-fix/screenshot/binding 재사용용)
    if root_id:
        print(f"⭐ LATEST ROOT: {root_id}  (saved → .latest_build.json)")
        print(f"   re-screenshot:  python3 scripts/figma_mcp_client.py call export_node_as_image '{{\"nodeId\":\"{root_id}\",\"format\":\"PNG\",\"scale\":1}}'")
        print(f"   re-post-fix:    python3 scripts/figma_mcp_client.py post-fix {root_id}")
    print(f"{'='*50}")

    # 🔴 레퍼런스 Read 리마인더 — 빌드 끝에서 재출력(tail-visible). 근본 원인(2026-06-08):
    # 빌드 출력을 `tail -N`/`grep` 으로 필터해 Step A.0(빌드 *앞부분*)의 SECTION-REFERENCE-PNG
    # 프롬프트를 통째로 못 봐 0-G 를 매번 빠뜨렸다 → 끝에서 한 번 더 띄워 어떤 로그 보기에도 걸리게.
    if _LAST_REFERENCE_THUMBS:
        print("📌 SECTION-REFERENCE-PNG (재안내) ⚠️  절대 규칙 0-G — 빌드 진행/완료보고 전에 아래"
              f" 레퍼런스 {len(_LAST_REFERENCE_THUMBS)}장을 Read 로 열어 시각 학습({_LAST_REFERENCE_LABEL}):")
        for p in _LAST_REFERENCE_THUMBS:
            print(f"    Read: {p}")
        print("    (path 만 references[] 박지 말 것 — 실제 시각 위계/리듬/컬러/카드 패턴 반영)")
        print(f"{'='*50}")

    # 🔴 2026-06-05 절대 규칙 0-R (사용자: "디자인 생성이 완료되면 디자인 생성 시 만들었던
    #    블루프린트 json 파일은 자동 삭제 되도록 할 것! 코드로도 강제해"):
    #    빌드 성공(root_id 존재) 시 그 빌드에 쓴 blueprint/spec json 을 즉시 자동 삭제.
    if root_id:
        # novelty 시그니처 저장 (2026-06-12 전면 개편) — 다음 생성의 '같음' 비교 기준.
        # original_blueprint = $token 참조가 살아있는 사본 (resolve 전) — 시그니처에 적합.
        _novelty_save(original_blueprint)
        _cleanup_build_input(blueprint_file)

    # 🔴 BUILD-SUMMARY-JSON — 항상 stdout 마지막 블록 (Astryx 패턴, 2026-07-08).
    # 에이전트가 로그를 tail/grep 으로 봐도 결과 + 필수 후속 액션(0-G Read / 0-F self-verify)
    # 을 기계 판독으로 받는다. prose 대신 code 로 분기할 것 (scripts/error_codes.py).
    if root_id:
        _acts = _post_build_required_actions()
        _codes = []
        _missing_icons = _find_unresolved_icons(root_id)
        if _missing_icons:
            # 🔴 2026-09-04: 회색 placeholder 아이콘은 조용한 성공이 아니다 — 코드+필수 액션으로 승격.
            _codes.append("ERR_ICON_UNRESOLVED")
            print("\n❌ [ICON] 미해석 아이콘 placeholder 잔존 — svg_icon(batch_build_screen parentId + svgData) 로 교체 필요:")
            for m in _missing_icons:
                print(f"     - {m['name']} ({m['id']})")
            _acts = list(_acts or []) + [{
                "type": "replace_icons",
                "why": "type:'icon' 해석 실패 → 회색 placeholder. svg_icon+svgData 로 교체 후 색 바인딩 (verify 가 icon-missing FAIL)",
                "nodeIds": [m["id"] for m in _missing_icons],
                "names": [m["name"] for m in _missing_icons],
            }]
        _emit_build_summary("success", root_id=root_id, warnings=warns, codes=_codes or None,
                            required_actions=_acts)
    else:
        _emit_build_summary("failed", codes=["ERR_BUILD_FAILED"], warnings=warns,
                            note="batch_build_screen 실패 — 브리지/플러그인 상태 확인 "
                                 "(python3 scripts/figma_mcp_client.py doctor)")


def _cleanup_build_input(input_path: str) -> None:
    """🔴 절대 규칙 0-R (2026-06-05): 디자인 생성 완료 후 사용한 blueprint/spec json 자동 삭제.

    빌드가 끝나면 화면은 Figma 에 생성됐으니 blueprint json 은 불필요 → 레포·scripts/ 에
    산출물이 쌓이지 않도록 즉시 삭제(생성 7일 대기하는 cleanup_old_blueprints 와 별개로,
    빌드 직후 즉시). **소스/입력 자산은 보존:**
      - blueprint_templates.json (assemble 워크플로우 소스 템플릿)
      - archetype_specs/*.json (unified spec 소스 — 홈 등 unified 빌드는 이 spec 으로 생성)
      - 이름에 'PRD' (사용자 입력 PRD) · 'wireframe_content' (와이어 콘텐츠 dict)
    삭제 대상: 빌드 입력으로 쓴 `blueprint_*.json` · `spec_*.json` · `*assembled*.json` ·
    `*_blueprint.json` 산출물.
    """
    try:
        if not input_path or not os.path.exists(input_path):
            return
        base = os.path.basename(input_path)
        low = base.lower()
        # 보존 예외 — 소스/입력 자산
        if base in ("blueprint_templates.json",):
            return
        if "prd" in low or "wireframe_content" in low:
            return
        norm = input_path.replace("\\", "/")
        if "/archetype_specs/" in norm or norm.startswith("archetype_specs/"):
            return
        # 삭제 대상 판별 — 빌드 입력 blueprint/spec 산출물만
        is_target = low.endswith(".json") and (
            low.startswith("blueprint_") or low.startswith("spec_")
            or "assembled" in low or low.endswith("_blueprint.json"))
        if not is_target:
            print(f"  🧹 [cleanup] '{base}' 는 blueprint/spec 산출물 패턴이 아님 — 보존")
            return
        os.remove(input_path)
        print(f"  🧹 [cleanup] 빌드 완료 — 사용한 blueprint json 자동 삭제: {base} (절대 규칙 0-R)")
    except Exception as e:
        print(f"  [cleanup] blueprint 자동 삭제 실패(무시): {e}")


def _self_verify_section_qa_export(root_id: str, blueprint: dict) -> None:
    """Step H — 빌드 후 self-verify 강제 시스템 (2026-05-28 사용자 옵션 B).

    Claude 가 "검증 ✅" 보고 전 무조건 섹션별 zoom-in PNG 4~6장 + checklist 12개
    채우도록 강제. 코드는 LLM 행동을 직접 강제할 수 없으므로:
      (1) 자동으로 섹션 검출해 PNG export (scale=2)
      (2) self_verify_checklist.json 빈 템플릿 생성 (각 빌드별 디렉토리)
      (3) stdout 에 강력한 경고 ("📸 SECTION-QA-PNG ⚠️") 출력 → 사용자 화면에
          도 보이므로 Claude 가 검증 skip 했는지 즉시 파악 가능

    [feedback_self_verify_required_after_build] 메모리 룰에 박힌 강제 절차.
    """
    import os
    import json as _json

    # 1) 빌드 트리에서 주요 섹션 탐색 (이름 패턴 매칭, 라벨별 첫 매치)
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        doc = items[0].get("document") if items else None
    except Exception:
        doc = None
    if not doc:
        print("  ⚠️ Step H self-verify: tree 조회 실패 — skip")
        return

    # archetype 별 섹션 라벨 그룹 — imin_home 기준 6장
    section_groups = [
        ("Header_NavBar",        ["NavBar", "Status Bar"]),
        ("Top_Tabs_Hero",        ["Mode Tabs", "Progress Card", "Hero", "Balance Card"]),
        ("Day_Strip_Row",        ["Day Strip", "Stage Strip", "Schedule Row"]),
        ("Recommend_Card",       ["Recommend Stage Card", "Recommend Card", "Stage Card"]),
        ("Empty_or_List",        ["Participation", "Empty", "List", "Carousel"]),
        ("Footer_TabBar_FAB",    ["Tab Bar", "FAB", "Footer Section"]),
    ]

    sections_to_export = []
    seen_labels = set()

    def walk(node):
        nm = (node.get("name") or "")
        nm_low = nm.lower()
        for label, patterns in section_groups:
            if label in seen_labels:
                continue
            for p in patterns:
                if p.lower() in nm_low:
                    sections_to_export.append((label, node.get("id"), nm))
                    seen_labels.add(label)
                    break
        for c in node.get("children", []) or []:
            walk(c)

    walk(doc)

    # 2) PNG export — scale=2, plugin cache 에 저장됨
    exported = []
    for label, nid, name in sections_to_export:
        try:
            call_tool("export_node_as_image", {
                "nodeId": nid,
                "format": "PNG",
                "scale": 2,
            })
            exported.append({"label": label, "nodeId": nid, "name": name})
        except Exception as e:
            print(f"    [Step H] {label} export 실패: {e}")

    # 3) checklist 빈 템플릿 생성
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    qa_dir = os.path.join(project_root, "scripts", "qa_screenshots",
                          root_id.replace(":", "_"))
    os.makedirs(qa_dir, exist_ok=True)
    checklist_path = os.path.join(qa_dir, "self_verify_checklist.json")

    checklist = {
        "_BLOCKING_INSTRUCTION": (
            "⚠️ Claude 보고 직전 강제 절차 (절대 룰): "
            "위 exported_sections 의 모든 nodeId 를 export_node_as_image (scale=2) 로 "
            "재export 후 결과 PNG 를 Read. 그 후 아래 checklist 12개 각각 "
            "PASS / FAIL / NA 로 status 채우고 evidence 에 시각 증거 1줄 인용. "
            "이 checklist 미완료 상태로 사용자에게 '검증 ✅' '완료' 보고 금지 — "
            "[feedback_self_verify_required_after_build] 메모리 룰 위반."
        ),
        "root_id": root_id,
        "blueprint_name": blueprint.get("rootName") or blueprint.get("name", ""),
        "exported_sections": exported,
        "checklist": [
            {"id": "C01-content-1to1",       "question": "와이어 모든 텍스트/숫자/카운트가 빌드에 1:1 박혀있나",                     "status": "FILL_IN", "evidence": ""},
            {"id": "C02-no-grey-placeholder","question": "회색 빈 placeholder 박스 (children≤1 + 라벨만) 없나",                    "status": "FILL_IN", "evidence": ""},
            {"id": "C03-real-image-cards",   "question": "라운지/상품/카드의 실 시각 콘텐츠 (사진/일러스트/아이콘) 들어있나",       "status": "FILL_IN", "evidence": ""},
            {"id": "C04-cell-row-alignment", "question": "Day Strip / cell row 모든 cell 의 텍스트 alignment 일치하나",            "status": "FILL_IN", "evidence": ""},
            {"id": "C05-hero-28plus",        "question": "Hero 텍스트 28~36px Bold 인가",                                          "status": "FILL_IN", "evidence": ""},
            {"id": "C06-tabbar-label-order", "question": "Tab Bar 라벨 순서가 와이어와 일치하나",                                   "status": "FILL_IN", "evidence": ""},
            {"id": "C07-tabbar-icon-match",  "question": "Tab Bar 아이콘이 라벨 의미와 일치하나 (커뮤니티=users / 라운지=shop 등)", "status": "FILL_IN", "evidence": ""},
            {"id": "C08-underline-width",    "question": "Underline tab active/inactive underline width·height 일치하나",         "status": "FILL_IN", "evidence": ""},
            {"id": "C09-stepper-icons",      "question": "Stepper minus/plus 아이콘 시인성 충분한가 (대비 ≥3:1)",                  "status": "FILL_IN", "evidence": ""},
            {"id": "C10-fab-icon-correct",   "question": "FAB 아이콘 의도와 일치하나, 이모티콘 아닌가",                              "status": "FILL_IN", "evidence": ""},
            {"id": "C11-card-hierarchy",     "question": "카드 위계 (hero vs 보조) 시각 차등화 (size/shadow/border) 됐나",         "status": "FILL_IN", "evidence": ""},
            {"id": "C12-polished-not-wire",  "question": "와이어 1:1 복제처럼 보이지 않나 (brand 액센트 의미 매핑, 시각 리듬)",    "status": "FILL_IN", "evidence": ""},
        ],
        "summary": {"pass": 0, "fail": 0, "na": 0,
                    "BLOCKING": "FILL_IN — 12개 다 채울 때까지 사용자 보고 금지"},
    }
    with open(checklist_path, "w") as f:
        _json.dump(checklist, f, indent=2, ensure_ascii=False)

    # 4) stdout 강력 경고 — 사용자 화면에도 보임
    print("\n" + "=" * 60)
    print("📸 SECTION-QA-PNG ⚠️  보고 전 self-verify 필수 (옵션 B 박힘)")
    print("=" * 60)
    print(f"섹션별 zoom-in 후보 {len(exported)}장:")
    for e in exported:
        print(f"  • {e['label']:24s} → '{e['name']}' ({e['nodeId']})")
    print(f"\n📋 Checklist: {os.path.relpath(checklist_path, project_root)}")
    print("⚠️  Claude self-verify 강제 절차:")
    print("    1. 위 각 nodeId 를 export_node_as_image scale=2 로 재 export + Read")
    print("    2. checklist 12개 항목 PASS/FAIL/NA + evidence 1줄 채우기")
    print("    3. FAIL ≥1 건 시 즉시 live-fix 또는 사용자에게 솔직 보고")
    print("    4. 절대 미완료 상태로 '검증 ✅' / '완료' 보고 금지")
    print("    → [feedback_self_verify_required_after_build] 메모리 룰")
    print("=" * 60)

    # 🔴 self-verify 게이트 마커 기록 (2026-06-11 — 0-F 코드 게이트화): 이 섹션 PNG 들을
    # 이 세션에서 재export(=Read) 하기 전엔 다음 build/cleanup-qa 가 차단된다. 모델이
    # self-verify 를 조용히 건너뛰는 것 방지. (exported 가 비면 마커 안 남김 = 강제 불가.)
    if exported:
        _record_pending_selfverify(root_id, exported, checklist_path)


def _collect_tree(node_id: str, depth: int = 0, max_depth: int = 6) -> dict:
    """노드 트리 수집 — get_nodes_info(복수)로 전체 재귀 트리를 1콜에 받는다.

    get_node_info는 트리를 ~43노드에서 잘라서 반환하므로 사용 금지. get_nodes_info는
    풀 리치 재귀 트리를 한 번에 반환 → per-node 재호출 제거 (post-fix 수백 콜 → 1콜).
    absoluteBoundingBox(절대좌표)를 부모 기준 상대좌표로 변환해 기존 동작과 호환.
    실패 시 legacy(per-node get_node_info)로 폴백.
    """
    try:
        content = call_tool("get_nodes_info", {"nodeIds": [node_id]})
        items = parse_content(content).get("json")
        root = None
        if isinstance(items, list) and items:
            root = items[0].get("document") or items[0]
        elif isinstance(items, dict):
            root = items.get("document") or items
    except Exception:
        root = None

    if not root or not root.get("id"):
        return _collect_tree_legacy(node_id, depth, max_depth)

    def _norm(n: dict, parent_abb: Optional[dict], d: int) -> dict:
        abb = n.get("absoluteBoundingBox") or {}
        if abb:
            if "width" in abb:
                n["width"] = abb["width"]
            if "height" in abb:
                n["height"] = abb["height"]
            # 절대좌표 → 부모 기준 상대좌표 (get_node_info의 x/y와 동일 의미)
            if parent_abb:
                n["x"] = abb.get("x", 0) - parent_abb.get("x", 0)
                n["y"] = abb.get("y", 0) - parent_abb.get("y", 0)
            else:
                n["x"] = abb.get("x", 0)
                n["y"] = abb.get("y", 0)
        kids = n.get("children", []) if d < max_depth else []
        n["_children_full"] = [_norm(c, abb, d + 1) for c in kids if isinstance(c, dict)]
        return n

    return _norm(root, None, depth)


def _collect_tree_legacy(node_id: str, depth: int = 0, max_depth: int = 6) -> dict:
    """[폴백] 노드 트리를 재귀적으로 수집 (최대 depth 6).

    get_node_info로 노드 정보를 가져오고, children의 각 id에 대해 재귀 호출.
    get_node_info 실패 시 get_nodes_info를 fallback으로 사용.
    결과 노드에 _children_full 키로 완전한 자식 정보를 포함.
    """
    node = None

    # 1차: get_node_info
    try:
        content = call_tool("get_node_info", {"nodeId": node_id})
        result = parse_content(content)
        node = result.get("json") or {}
    except Exception:
        node = {}

    # 2차 fallback: get_nodes_info (get_node_info 실패 시)
    if not node or not node.get("id"):
        try:
            content2 = call_tool("get_nodes_info", {"nodeIds": [node_id]})
            result2 = parse_content(content2)
            items = result2.get("json") or []
            if isinstance(items, list) and items:
                doc = items[0].get("document") or items[0]
                if doc.get("id"):
                    node = doc
        except Exception:
            pass

    if not node or not node.get("id"):
        return {"id": node_id, "type": "UNKNOWN", "_children_full": []}

    children_full = []
    if depth < max_depth:
        children = node.get("children", [])
        for child in children:
            child_id = child.get("id") if isinstance(child, dict) else child
            if child_id:
                child_node = _collect_tree_legacy(str(child_id), depth + 1, max_depth)
                children_full.append(child_node)

    node["_children_full"] = children_full
    return node


def _fix_fill_sizing(tree: dict) -> int:
    """FRAME 노드의 layoutSizingHorizontal을 FILL로 수정.

    스킵 조건:
    - width <= 60 (아이콘 등 고정 크기)
    - 이름에 icon/chevron/dot/Tag/Badge/Indicator/Nav Right/Vector 포함
    - HORIZONTAL 부모 안의 Banner Card (캐로셀 배너는 FIXED 유지)
    - FAB / Tab Bar (ABSOLUTE 배치 대상 — FILL로 바꾸면 width가 전체로 늘어남)
    - SPACE_BETWEEN 부모에서 이미 ABSOLUTE인 노드
    - SPACE_BETWEEN 부모의 마지막 자식이 HUG이면 보존 (우측 정렬 유틸리티)
    """
    SKIP_KEYWORDS = ("icon", "chevron", "dot", "Tag", "Badge", "Indicator",
                     "Nav Right", "Vector", "Icon", "Chevron", "Dot")
    # 단어 경계 매칭용 정규식 — substring 매칭("tag" ⊂ "stage") 버그 방지
    _SKIP_RE = re.compile(
        r'\b(?:' + '|'.join(re.escape(kw.lower()) for kw in SKIP_KEYWORDS) + r')\b'
    )
    # FAB/Tab Bar는 ABSOLUTE로 배치되므로 FILL 변환하면 안 됨
    ABSOLUTE_NAME_KEYWORDS = ("fab", "tab bar", "tabbar")
    fix_count = 0
    _fill_queue: List[dict] = []  # 2026-07-13 — 개별 호출 대신 배치 큐

    # 2026-05-28 — 원형/icon-box frame 식별 (cornerRadius >= w/2 또는 단일 icon 자식)
    # 이전 회귀: piggy-bank box (72×72 cornerRadius 18) + circle (40×40 cornerRadius 999)
    # 가 FILL 강제되어 stadium pill 형태로 망가짐 → 매 빌드마다 라이브 fix 필요했음.
    def _is_circle_or_iconbox(n: dict) -> bool:
        cr = n.get("cornerRadius") or 0
        w = n.get("width") or 0
        if w > 0 and cr >= (w / 2) - 1:  # 원형 (반지름 = width/2)
            return True
        # icon-box 패턴: 단일 frame 자식 → 그 안 VECTOR 하나
        kids = n.get("_children_full") or []
        if len(kids) == 1:
            ch = kids[0]
            if (ch.get("type") or "").upper() in ("FRAME", "INSTANCE"):
                grand = ch.get("_children_full") or []
                if len(grand) == 1 and (grand[0].get("type") or "").upper() == "VECTOR":
                    return True
        return False

    def _walk(node: dict, parent_layout_mode: str = "",
              parent_align: str = "", is_last_child: bool = False):
        nonlocal fix_count
        node_type = (node.get("type") or "").upper()
        node_name = node.get("name") or ""
        node_id = node.get("id")
        width = node.get("width", 999)
        sizing_h = node.get("layoutSizingHorizontal", "")

        is_frame = node_type in ("FRAME", "COMPONENT", "INSTANCE")

        if is_frame and node_id != tree.get("id"):
            skip = False
            name_lower = node_name.lower()
            # 원형/icon-box frame 은 FIXED width 유지 — FILL 강제 시 stadium pill 됨
            if _is_circle_or_iconbox(node):
                skip = True
            # INSTANCE는 컴포넌트 마스터가 크기를 제어 — FILL 변환 금지
            if node_type == "INSTANCE":
                skip = True
            # HUG 보존 규칙:
            #   VERTICAL 부모의 HUG FRAME → FILL로 수정 (가로 채움 필수)
            #   HORIZONTAL 부모의 HUG FRAME → 유지 (FILL이면 tab/tag 레이아웃 깨짐)
            #   부모 layoutMode 미확인("")일 때는 skip 안 함 — _collect_tree 실패 시
            #   빈 문자열이 되어 VERTICAL 자식까지 skip되는 버그 방지
            if sizing_h == "HUG" and parent_layout_mode and parent_layout_mode != "VERTICAL":
                skip = True
            if width <= 60:
                skip = True
            # 키워드 매칭 (단어 경계, 대소문자 무시)
            if _SKIP_RE.search(name_lower):
                skip = True
            # HORIZONTAL 부모 안의 모든 FRAME 자식은 FILL 강제 안 함
            # - 카루셀 카드(Date/MyStage/Hero/Deal/Banner Card 등)는 FIXED width 유지
            # - 탭/배너/스테퍼 행의 자식 그룹은 HUG가 정상
            # (FAB/Tab Bar는 위에서 별도 skip 처리됨)
            if parent_layout_mode == "HORIZONTAL":
                skip = True
            # FAB / Tab Bar → ABSOLUTE 대상이므로 FILL 금지
            if any(kw in name_lower for kw in ABSOLUTE_NAME_KEYWORDS):
                skip = True
            # 이미 ABSOLUTE로 설정된 노드
            if node.get("layoutPositioning") == "ABSOLUTE":
                skip = True
            # SPACE_BETWEEN 부모의 마지막 자식(HUG) → 우측 정렬 유지
            if (parent_align == "SPACE_BETWEEN" and is_last_child
                    and sizing_h in ("HUG", "")):
                skip = True

            if not skip and sizing_h != "FILL":
                _fill_queue.append({"nodeId": node_id, "horizontal": "FILL"})
                print(f"  FILL 수정: {node_name} ({node_id}) [{sizing_h} → FILL]")

        # 자식 노드 재귀
        current_layout = node.get("layoutMode", "")
        current_align = node.get("primaryAxisAlignItems", "")
        children = node.get("_children_full", [])
        for i, child in enumerate(children):
            _walk(child, current_layout, current_align,
                  is_last_child=(i == len(children) - 1))

    _walk(tree)

    # ★ 안전장치: 루트부터 재귀적으로 FRAME 자식을 FILL 강제 (FAB/Tab Bar 제외)
    # _walk에서 데이터 누락이나 조건 스킵으로 빠져나갈 수 있으므로,
    # VERTICAL 부모의 모든 FRAME 자식을 재귀적으로 검증/수정
    ABSOLUTE_NAME_KEYWORDS_LOWER = ("fab", "tab bar", "tabbar")

    def _force_fill_recursive(parent_node: dict, depth: int = 0, max_depth: int = 4):
        """VERTICAL 부모의 FRAME 자식을 재귀적으로 FILL 강제."""
        nonlocal fix_count
        parent_layout = (parent_node.get("layoutMode") or "").upper()
        # 루트(depth=0)이거나 VERTICAL 부모인 경우 자식 검사
        is_vertical_parent = (depth == 0) or parent_layout == "VERTICAL"

        for child in parent_node.get("_children_full", []):
            child_type = (child.get("type") or "").upper()
            child_name = (child.get("name") or "").lower()
            child_id = child.get("id")
            child_sizing = child.get("layoutSizingHorizontal", "")

            if (is_vertical_parent
                    and child_type in ("FRAME", "COMPONENT") and child_id
                    and child_sizing != "FILL"
                    and child.get("width", 999) > 60
                    and not _is_circle_or_iconbox(child)
                    and not any(kw in child_name for kw in ABSOLUTE_NAME_KEYWORDS_LOWER)
                    and not _SKIP_RE.search(child_name)
                    and child.get("layoutPositioning") != "ABSOLUTE"):
                _fill_queue.append({"nodeId": child_id, "horizontal": "FILL"})
                depth_label = "루트 자식" if depth == 0 else f"depth {depth + 1}"
                print(f"  FILL 강제({depth_label}): {child.get('name', '?')} ({child_id}) [{child_sizing} → FILL]")

            # 재귀: FRAME/COMPONENT 자식의 하위도 검사
            if child_type in ("FRAME", "COMPONENT") and depth < max_depth:
                _force_fill_recursive(child, depth + 1, max_depth)

    _force_fill_recursive(tree)

    # 2026-07-13 — 개별 set_layout_sizing 라운드트립 대신 배치 1콜 (post-fix 471s 회귀 fix).
    # dedup: 같은 nodeId 가 walk/강제 두 경로에서 중복 큐잉될 수 있음.
    _seen_ids = set()
    _deduped = []
    for it in _fill_queue:
        if it["nodeId"] in _seen_ids:
            continue
        _seen_ids.add(it["nodeId"])
        _deduped.append(it)
    fix_count += _set_sizing_batch(_deduped)

    return fix_count


def _fix_layout_and_positions(tree: dict, pre_computed_layout: dict = None) -> dict:
    """Tab Bar/FAB를 ABSOLUTE로 루트 하단에 배치하고, 인접 섹션 간 갭 조정.

    Returns:
        dict with content_bottom, fab_y, tab_y, root_height
    """
    root_id = tree.get("id")
    children = tree.get("_children_full", [])

    # 자식 분류
    content_nodes = []
    tab_bar = None
    fab = None

    for child in children:
        name = (child.get("name") or "").lower()
        if "tab bar" in name or "tabbar" in name:
            tab_bar = child
        elif "fab" in name:
            fab = child
        else:
            content_nodes.append(child)

    # Fast path: 사전 계산값이 있으면 get_nodes_info 재조회 건너뜀
    if pre_computed_layout and pre_computed_layout.get("suggestedFabY"):
        print(f"  [PRECOMP] 사전 계산값 사용 (contentBottom={pre_computed_layout.get('contentBottom')}, "
              f"fabY={pre_computed_layout.get('suggestedFabY')}, "
              f"tabY={pre_computed_layout.get('suggestedTabBarY')}, "
              f"rootH={pre_computed_layout.get('suggestedRootHeight')})")

    # ★ FILL 수정 후 Figma에서 최신 y/height 다시 조회
    #   (_collect_tree는 FILL 수정 전에 실행되므로 캐시된 y/height가 stale)
    all_nodes = content_nodes + ([fab] if fab else []) + ([tab_bar] if tab_bar else [])
    refresh_ids = [n.get("id") for n in all_nodes if n.get("id")]
    if refresh_ids:
        try:
            refresh_content = call_tool("get_nodes_info", {"nodeIds": refresh_ids})
            refresh_result = parse_content(refresh_content)
            refresh_items = refresh_result.get("json") or []
            if isinstance(refresh_items, list):
                id_to_fresh = {}
                for item in refresh_items:
                    doc = item.get("document") or item
                    bb = doc.get("absoluteBoundingBox") or {}
                    nid = doc.get("id")
                    if nid and bb:
                        # absoluteBoundingBox를 부모(루트) 기준 로컬 좌표로 변환
                        root_bb = tree.get("absoluteBoundingBox") or {}
                        root_y = root_bb.get("y", 0)
                        id_to_fresh[nid] = {
                            "y": bb.get("y", 0) - root_y,
                            "height": bb.get("height", 0),
                            "width": bb.get("width", 0),
                        }
                refreshed = 0
                for node in all_nodes:
                    nid = node.get("id")
                    if nid in id_to_fresh:
                        fresh = id_to_fresh[nid]
                        old_h = node.get("height", 0)
                        node["y"] = fresh["y"]
                        node["height"] = fresh["height"]
                        node["width"] = fresh["width"]
                        if abs(old_h - fresh["height"]) > 1:
                            refreshed += 1
                if refreshed:
                    print(f"  위치 갱신: {refreshed}건 (FILL 수정 후 높이 변경 반영)")
        except Exception as e:
            print(f"  ⚠️ 위치 갱신 실패 (기존 값 사용): {e}")

    # 인접 섹션 간 갭 제거 (둘 다 투명 배경이면)
    for i in range(1, len(content_nodes)):
        prev = content_nodes[i - 1]
        curr = content_nodes[i]

        prev_fills = prev.get("fills", [])
        curr_fills = curr.get("fills", [])

        # 투명 여부 판단: fills가 비어있거나, 모든 fill의 opacity/a가 0이거나, visible=false
        def _is_transparent(fills):
            if not fills:
                return True
            for f in fills:
                if f.get("visible") is False:
                    continue
                opacity = f.get("opacity", 1)
                color = f.get("color", {})
                a = color.get("a", 1)
                if opacity > 0 and a > 0:
                    return False
            return True

        if _is_transparent(prev_fills) and _is_transparent(curr_fills):
            prev_bottom = (prev.get("y") or 0) + (prev.get("height") or 0)
            curr_y = curr.get("y") or 0
            if curr_y > prev_bottom:
                try:
                    call_tool("move_node", {
                        "nodeId": curr.get("id"),
                        "x": curr.get("x", 0),
                        "y": prev_bottom
                    })
                    print(f"  갭 제거: {curr.get('name')} y={curr_y} → {prev_bottom}")
                    curr["y"] = prev_bottom
                except Exception as e:
                    print(f"  갭 제거 실패: {curr.get('name')}: {e}")

    # ★ content_bottom 계산: 갭 제거 후, Figma에서 최신 좌표를 다시 조회
    #    FILL 수정 + 갭 제거로 y/height가 변경되었으므로 캐시 데이터는 부정확
    content_ids = [n.get("id") for n in content_nodes if n.get("id")]
    if content_ids:
        try:
            fresh_content = call_tool("get_nodes_info", {"nodeIds": content_ids})
            fresh_result = parse_content(fresh_content)
            fresh_items = fresh_result.get("json") or []
            if isinstance(fresh_items, list):
                root_bb = tree.get("absoluteBoundingBox") or {}
                root_y = root_bb.get("y", 0)
                for item in fresh_items:
                    doc = item.get("document") or item
                    bb = doc.get("absoluteBoundingBox") or {}
                    nid = doc.get("id")
                    if nid and bb:
                        for node in content_nodes:
                            if node.get("id") == nid:
                                node["y"] = bb.get("y", 0) - root_y
                                node["height"] = bb.get("height", 0)
                                break
                print(f"  content_bottom 재조회 완료 ({len(fresh_items)}건)")
        except Exception as e:
            print(f"  ⚠️ content_bottom 재조회 실패 (기존 값 사용): {e}")

    # ★ content_bottom 최종 계산: get_nodes_info의 absoluteBoundingBox로 정확한 값 사용
    #    _collect_tree 캐시 데이터는 FILL 수정 전이라 부정확할 수 있음
    content_bottom = 0
    root_id = tree.get("id")
    try:
        root_info_content = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        root_info_result = parse_content(root_info_content)
        root_info_items = root_info_result.get("json") or []
        if isinstance(root_info_items, list) and root_info_items:
            doc = root_info_items[0].get("document") or root_info_items[0]
            root_bb = doc.get("absoluteBoundingBox", {})
            root_y = root_bb.get("y", 0)
            for c in doc.get("children", []):
                c_name = (c.get("name") or "").lower()
                c_lp = c.get("layoutPositioning", "AUTO")
                if c_lp == "ABSOLUTE" or "fab" in c_name or "tab bar" in c_name or "tab_bar" in c_name:
                    continue
                c_bb = c.get("absoluteBoundingBox", {})
                c_bottom = (c_bb.get("y", 0) - root_y) + c_bb.get("height", 0)
                if c_bottom > content_bottom:
                    content_bottom = c_bottom
            print(f"  content_bottom (최종 조회): {round(content_bottom)}")
    except Exception as e:
        print(f"  ⚠️ content_bottom 최종 조회 실패, 캐시 사용: {e}")
        for node in content_nodes:
            bottom = (node.get("y") or 0) + (node.get("height") or 0)
            if bottom > content_bottom:
                content_bottom = bottom

    result = {"content_bottom": content_bottom, "fab_y": None, "tab_y": None, "root_height": None}

    # ── Tab Bar / FAB 배치 좌표 계산 ──
    # ⚠️ 시스템 규칙 (2026-05-27 사용자 룰): FAB icon-only 56×56 원형, 우측 20px, 상단 20px gap.
    #    Tab Bar 있으면 Tab Bar 위 20px, 없으면 콘텐츠 마지막 요소 위 20px.
    TAB_BAR_H = 73
    FAB_H = 56              # 2026-05-27: 44 (pill) → 56 (icon-only 원형)
    FAB_GAP = 20            # 2026-05-27: 16 → 20 (사용자 룰)
    FAB_RIGHT_MARGIN = 20   # 2026-05-27: 우측 20px (사용자 룰)
    if tab_bar:
        tab_y = content_bottom                    # Tab Bar는 콘텐츠에 밀착
        fab_y = tab_y - FAB_H - FAB_GAP           # FAB는 Tab Bar 위 20px
    else:
        tab_y = None
        fab_y = content_bottom - FAB_H - FAB_GAP  # Tab Bar 없으면 콘텐츠 마지막 요소 위 20px

    # FAB 배치
    if fab:
        try:
            call_tool("set_layout_positioning", {
                "nodeId": fab.get("id"),
                "layoutPositioning": "ABSOLUTE"
            })
        except Exception as e:
            print(f"  FAB ABSOLUTE 설정 실패 (무시): {e}")
        # FAB 크기 복원 (2026-05-27: icon-only 56×56 원형 표준) — FILL 변환으로 늘어났을 수 있음
        fab_width = fab.get("width", 56)
        if fab_width > 100:  # FILL로 늘어난 경우
            try:
                call_tool("set_layout_sizing", {
                    "nodeId": fab.get("id"),
                    "horizontal": "HUG"
                })
                print(f"  FAB 크기 복원: width {fab_width} → HUG")
            except Exception as e:
                print(f"  FAB 크기 복원 실패: {e}")
        # 우측 20px (root width 393 가정 — 다른 width 면 _enforce_root_min_height 가 재조정)
        fab_x = 393 - FAB_H - FAB_RIGHT_MARGIN  # 393 - 56 - 20 = 317
        try:
            call_tool("move_node", {
                "nodeId": fab.get("id"),
                "x": fab_x,
                "y": fab_y
            })
            print(f"  FAB 배치: x={fab_x}, y={fab_y} (우측 {FAB_RIGHT_MARGIN}px, 상단 gap {FAB_GAP}px)")
            result["fab_y"] = fab_y
        except Exception as e:
            print(f"  FAB 이동 실패: {e}")

    # Tab Bar 배치 (tab_y는 위에서 계산됨 — 콘텐츠 하단 밀착)
    if tab_bar:
        try:
            call_tool("set_layout_positioning", {
                "nodeId": tab_bar.get("id"),
                "layoutPositioning": "ABSOLUTE"
            })
        except Exception as e:
            print(f"  Tab Bar ABSOLUTE 설정 실패 (무시): {e}")
        # ABSOLUTE 전환 시 Figma가 FILL→HUG로 자동 변경하여 width가 축소됨
        # → width=393 강제 + FIXED로 설정하여 전체 너비 유지
        try:
            call_tool("resize_node", {
                "nodeId": tab_bar.get("id"),
                "width": tree.get("width", 393),
                "height": 73
            })
            call_tool("set_layout_sizing", {
                "nodeId": tab_bar.get("id"),
                "horizontal": "FIXED"
            })
            print(f"  Tab Bar 크기 복원: width={tree.get('width', 393)}, FIXED")
        except Exception as e:
            print(f"  Tab Bar 크기 복원 실패: {e}")
        try:
            call_tool("move_node", {
                "nodeId": tab_bar.get("id"),
                "x": 0,
                "y": tab_y
            })
            print(f"  Tab Bar 배치: y={tab_y}, x=0")
            result["tab_y"] = tab_y
        except Exception as e:
            print(f"  Tab Bar 이동 실패: {e}")

    # 루트 프레임 높이 조정 — Tab Bar 하단까지. FAB는 콘텐츠 위로 뜨므로 높이에 영향 없음.
    if tab_bar:
        root_height = tab_y + TAB_BAR_H
    else:
        root_height = content_bottom

    # 안전장치: 계산 높이가 비정상적으로 낮으면 원본 유지
    original_height = tree.get("height") or tree.get("absoluteBoundingBox", {}).get("height", 0)
    if original_height > 100 and root_height < original_height * 0.3:
        print(f"  ⚠️ 높이 급감 감지: {original_height} → {root_height}. 원본 유지.")
        root_height = original_height

    try:
        # ★ 핵심 수정: resize 전에 layoutSizingVertical을 FIXED로 설정
        # set_auto_layout(VERTICAL)이 기본적으로 HUG를 설정하므로,
        # ABSOLUTE 자식이 흐름에서 빠지면 HUG가 높이를 content_bottom으로 축소시킴.
        # FIXED로 설정해야 resize_node로 지정한 높이가 유지됨.
        call_tool("set_layout_sizing", {
            "nodeId": root_id,
            "vertical": "FIXED"
        })
        call_tool("resize_node", {
            "nodeId": root_id,
            "width": tree.get("width", 393),
            "height": root_height
        })
        print(f"  루트 프레임 높이: {root_height} (FIXED)")
        result["root_height"] = root_height
    except Exception as e:
        print(f"  루트 높이 조정 실패: {e}")

    return result


# 루트 minHeight + bottom bar bottom-pin (2026-05-24 룰)
ROOT_MIN_HEIGHT = 852
_BOTTOM_BAR_PARTS = ("tab bar", "tabbar", "bottom action bar", "action bar", "cta bar", "fab")


def _should_use_bab_normal_flow(
    content_bottom: float,
    bab_heights: List[float],
    min_height: int = None,
) -> bool:
    """긴 콘텐츠 분기 판단 — content + BAB 합이 min_height 초과 시 True (B 케이스).

    이 헬퍼는 _enforce_root_min_height 내부 분기 로직을 단위 테스트하기 위해 분리됨.

    2026-05-26 회귀 fix: 이전엔 content_bottom 단독으로 비교해 BAB 높이를 빠뜨림.
    v3 s2 (content=796, BAB=119) 가 단독 비교에선 852 안에 든다고 판단돼
    ABSOLUTE pin 분기로 가서 BAB 가 위 콘텐츠를 덮어 잘림 발생. content+BAB 합산
    필수. 테스트는 scripts/tests/test_root_min_height.py 참고.
    """
    if min_height is None:
        min_height = ROOT_MIN_HEIGHT
    total = int(content_bottom) + sum(int(h) for h in bab_heights)
    return total > min_height


_VERTICAL_HUG_SKIP_KEYWORDS = (
    "tab bar", "tabbar", "fab", "action bar", "actionbar",
    "cta bar", "ctabar", "status bar", "statusbar",
)


_BORDER_SECONDARY_RGB = (0.898, 0.906, 0.922)
_BUTTON_NAME_RE = re.compile(r"\b(btn|button)\b|^cta\b|cta$", re.I)


def _enforce_button_border_on_same_bg(root_id: str) -> int:
    """Button 의 fill 이 부모 fill 과 같은 색이면 border-secondary stroke 자동 추가 (2026-05-27).

    **Why:** Summary Card 가 bg-primary (흰색) 로 강제된 후, 그 안의 outline 버튼
    (예: '내역 보기') 도 bg-primary 면 둘 다 흰색이라 button 이 안 보임 (그림자만
    살짝). 사용자 분노 — "구분 안 됨". outline 의도면 border 가 필수.

    Detection (shape + name):
      - FRAME with name matching btn/button/cta
      - cornerRadius >= 20 (pill 형태) OR (50 <= height <= 60) — 버튼 추정
      - 자기 fills RGB 가 부모 fills RGB 와 동일 (±0.02)
      - 이미 strokes 있으면 skip

    Fix: strokes = border-secondary 1px (RGB 0.898/0.906/0.922).
    """
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        if not items:
            return 0
        doc = items[0].get("document") or items[0]
    except Exception as e:
        print(f"  [btn-border] tree 조회 실패: {e}")
        return 0

    fixed = [0]

    def _first_solid_rgb(fills):
        if not isinstance(fills, list):
            return None
        for p in fills:
            if not isinstance(p, dict) or p.get("type") != "SOLID":
                continue
            if p.get("visible") is False:
                continue
            c = p.get("color") or {}
            return (c.get("r", 0), c.get("g", 0), c.get("b", 0))
        return None

    def _rgb_eq(a, b, tol=0.02):
        return (a is not None and b is not None
                and abs(a[0] - b[0]) < tol
                and abs(a[1] - b[1]) < tol
                and abs(a[2] - b[2]) < tol)

    def walk(node, parent_fill=None):
        if not isinstance(node, dict):
            return
        # DS 인스턴스 내부는 master 제어 — fill/stroke 손대지 않음 (badge stroke 금지)
        if (node.get("type") or "").upper() == "INSTANCE":
            return
        self_fill = _first_solid_rgb(node.get("fills"))
        is_frame = (node.get("type") or "").upper() == "FRAME"
        name = node.get("name") or ""
        if is_frame and _BUTTON_NAME_RE.search(name):
            bb = node.get("absoluteBoundingBox") or {}
            h = bb.get("height", 0) or 0
            cr = node.get("cornerRadius") or 0
            is_button_shape = (cr >= 20) or (40 <= h <= 64)
            has_stroke = bool(node.get("strokes"))
            if (is_button_shape and self_fill and parent_fill
                    and _rgb_eq(self_fill, parent_fill) and not has_stroke):
                try:
                    call_tool("set_stroke_color", {
                        "nodeId": node.get("id"),
                        "r": _BORDER_SECONDARY_RGB[0],
                        "g": _BORDER_SECONDARY_RGB[1],
                        "b": _BORDER_SECONDARY_RGB[2],
                        "a": 1,
                        "strokeWeight": 1,
                    })
                    fixed[0] += 1
                    print(f"  [btn-border] '{name}' fill==parent → border-secondary 1px 추가")
                except Exception as e:
                    print(f"  [btn-border] '{name}' set 실패: {e}")
        # 자식 walk — 자기 fill 이 있으면 자기를 parent_fill 로 전달
        child_parent = self_fill if self_fill else parent_fill
        for c in node.get("children") or []:
            walk(c, child_parent)

    walk(doc)
    if fixed[0] == 0:
        print("  [btn-border] OK — same-bg button 없음")
    return fixed[0]


def _fix_fill_sibling_1px(root_id: str) -> int:
    """batch_build_screen 의 FILL sibling 1px 버그 자동 fix (2026-05-27).

    **Why:** 같은 부모 안에 두 개 이상의 `layoutSizingHorizontal=FILL` 자식이 있을 때,
    `batch_build_screen` 이 종종 한 자식의 width 를 **1px** 로 박고 다른 자식이
    부모 inner-width 전부를 차지하는 버그가 있다. 결과:
      - Segmented Tabs: Tab Active=1px, Tab 누적 거래=353px (라벨이 -5.5px 음수 x)
      - Summary Actions: Schedule Btn=1px, Pay Btn=325px (라벨 안 보임)

    Fix: 모든 frame 자식 중 `layoutSizingHorizontal=FILL` + `width<10` 인 노드를
    detect → sibling 들 중 FILL 인 자식들에 부모 inner-width 를 균등 분배해 resize.

    height 는 보존(layoutSizingVertical 안 건드림).
    """
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        if not items:
            return 0
        doc = items[0].get("document") or items[0]
    except Exception as e:
        print(f"  [fill-1px] tree 조회 실패: {e}")
        return 0

    fixed = [0]

    def walk(node):
        kids = node.get("children") or []
        # FILL 자식들 중 width<10 인 게 있으면 sibling 들 균등 분배
        fill_kids = [k for k in kids if isinstance(k, dict)
                     and k.get("layoutSizingHorizontal") == "FILL"]
        if len(fill_kids) >= 2:
            buggy = [k for k in fill_kids
                     if ((k.get("absoluteBoundingBox") or {}).get("width") or 0) < 10]
            if buggy:
                # 2026-05-28 fix: buggy 발견 시, 같은 부모 안 모든 FRAME 자식을 FILL 로 강제
                # 후 균등 분배. Day Strip 사례 — Today=FIXED 313px 가 sibling FILL 들과
                # 함께 박혀 균등 분배 대상에서 빠지는 회귀 차단.
                all_frame_kids = [k for k in kids if isinstance(k, dict)
                                  and (k.get("type") or "FRAME").upper() == "FRAME"]
                if len(all_frame_kids) > len(fill_kids):
                    # FIXED 형제가 있음 → 모두 FILL 로 강제 후 fill_kids 재계산
                    for k in all_frame_kids:
                        if k.get("layoutSizingHorizontal") != "FILL":
                            try:
                                call_tool("set_layout_sizing", {
                                    "nodeId": k.get("id"),
                                    "horizontal": "FILL",
                                })
                                k["layoutSizingHorizontal"] = "FILL"
                            except Exception:
                                pass
                    fill_kids = all_frame_kids
                # 부모 inner-width 계산
                parent_bb = node.get("absoluteBoundingBox") or {}
                pw = parent_bb.get("width") or 0
                pad_l = node.get("paddingLeft") or 0
                pad_r = node.get("paddingRight") or 0
                spacing = node.get("itemSpacing") or 0
                inner_w = pw - pad_l - pad_r - spacing * (len(fill_kids) - 1)
                if inner_w > 0:
                    per_kid = int(inner_w / len(fill_kids))
                    for k in fill_kids:
                        kid_bb = k.get("absoluteBoundingBox") or {}
                        kid_h = kid_bb.get("height") or 0
                        try:
                            call_tool("resize_node", {
                                "nodeId": k.get("id"),
                                "width": per_kid,
                                "height": kid_h,
                            })
                            # resize_node 가 sizing 을 FIXED 로 박으므로 FILL 복원
                            call_tool("set_layout_sizing", {
                                "nodeId": k.get("id"),
                                "horizontal": "FILL",
                            })
                            fixed[0] += 1
                        except Exception as e:
                            print(f"  [fill-1px] resize 실패 '{k.get('name')}': {e}")
                    print(f"  [fill-1px] parent '{node.get('name')}' FILL siblings "
                          f"{len(fill_kids)}개 → 각 {per_kid}px 균등 분배 "
                          f"(buggy 1px: {len(buggy)}개)")
        for c in kids:
            if isinstance(c, dict):
                walk(c)

    walk(doc)
    if fixed[0] == 0:
        print("  [fill-1px] OK — width<10 FILL 자식 없음")
    return fixed[0]


def _enforce_carousel_hug_v(root_id: str) -> int:
    """HORIZONTAL carousel scroll 의 layoutSizingVertical 을 HUG 로 강제 (2026-05-27).

    **Why:** Lounge Scroll / Stage Card Scroll / Schedule Scroll 같은 가로 carousel 이
    `batch_build_screen` 후 vertical FILL 로 박히면, 부모 Section 안에서 자기 콘텐츠가
    아닌 부모 height 에 맞춰진다. 부모 Section 이 HUG 이고 다른 sibling (Title Row 등)
    이 작은 height 면 carousel 도 작아지고 (예: 93px), 안의 카드들 (240px+) 이 overflow
    → 다음 섹션 (Footer / Tab Bar) 을 시각적으로 침범. 사용자는 "잘리고 안 보임" 인식.

    R36 `_ensure_carousel_hug_v` 가 있지만 carousel detect 가 까다로워 정상 carousel
    (peek 문제 없는) 은 skip. 이름 기반 (Scroll / Carousel / Banner Row) 으로
    unconditional HUG 강제.

    Skip: VERTICAL frame, ABSOLUTE frame, Tab Bar / Status Bar / NavBar 같은 utility.
    """
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        if not items:
            return 0
        doc = items[0].get("document") or items[0]
    except Exception as e:
        print(f"  [carousel-hug] tree 조회 실패: {e}")
        return 0

    fixed = [0]
    CAROUSEL_KEYWORDS = ("scroll", "carousel", "banner row", "hero row")

    def walk(node, depth=0):
        if depth > 0:
            nm_low = (node.get("name") or "").lower()
            layout_mode = (node.get("layoutMode") or "").upper()
            sizing_v = node.get("layoutSizingVertical")
            is_carousel_name = any(kw in nm_low for kw in CAROUSEL_KEYWORDS)
            if (is_carousel_name and layout_mode == "HORIZONTAL"
                    and sizing_v != "HUG"
                    and node.get("layoutPositioning") != "ABSOLUTE"):
                try:
                    call_tool("set_layout_sizing", {
                        "nodeId": node.get("id"),
                        "vertical": "HUG",
                    })
                    fixed[0] += 1
                    print(f"  [carousel-hug] '{node.get('name')}' V={sizing_v} → HUG")
                except Exception as e:
                    print(f"  [carousel-hug] '{node.get('name')}' set 실패: {e}")
        for c in node.get("children") or []:
            walk(c, depth + 1)

    walk(doc)
    if fixed[0] == 0:
        print("  [carousel-hug] OK — 모든 carousel scroll 이 이미 HUG")
    return fixed[0]


def _enforce_vertical_hug(root_id: str) -> int:
    """VERTICAL layoutMode 프레임의 layoutSizingVertical 을 HUG 로 강제 (2026-05-27).

    **Why:** `batch_build_screen` 이 카드 안 VERTICAL Body/Section 프레임의
    `layoutSizingVertical` 을 FIXED <콘텐츠보다 작은 값> 으로 박는 버그가 있다.
    카드 콘텐츠가 카드 밖으로 흘러나오고, 그 결과 `_enforce_root_min_height` 의
    content_bottom 측정이 실제보다 짧게 잡혀 → 짧은 화면(A 케이스)으로 잘못
    분기 → BAB ABSOLUTE pin → 사용자에게 콘텐츠가 잘려보임 (2026-05-27 stage_list 회귀).

    이 룰은 모든 VERTICAL 프레임을 HUG 로 강제하되, ABSOLUTE 배치 대상(Tab Bar /
    FAB / Action Bar / Status Bar) 은 제외한다. 그 후 `_enforce_root_min_height`
    가 올바른 content_bottom 으로 분기 결정.

    회귀 테스트: scripts/tests/test_vertical_hug.py
    """
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        if not items:
            return 0
        doc = items[0].get("document") or items[0]
    except Exception as e:
        print(f"  [vertical-hug] tree 조회 실패: {e}")
        return 0

    fixed = [0]

    def walk(node, depth=0, parent_mode="", parent_clips=False):
        if depth > 0:  # root 자체는 제외 (별도 _enforce_root_min_height 가 결정)
            nm_low = (node.get("name") or "").lower()
            layout_mode = (node.get("layoutMode") or "").upper()
            sizing_v = node.get("layoutSizingVertical")
            # ABSOLUTE 배치 대상은 제외
            skip = any(kw in nm_low for kw in _VERTICAL_HUG_SKIP_KEYWORDS)
            # ABSOLUTE 노드도 제외
            if node.get("layoutPositioning") == "ABSOLUTE":
                skip = True
            # 부모가 HORIZONTAL carousel (clipsContent=true) 인 카드: FIXED height 는
            # 보통 의도된 디자인이라 손대지 않는다(HUG 시 빈 카드 42px collapse 회귀).
            # 단, 콘텐츠가 카드 height 를 **넘쳐 잘리는** 경우(Lounge Card: Image120+
            # Body84 > FIXED200 → 하단 가격 잘림, 2026-05-28 사용자 분노)는 예외 —
            # overflow 면 HUG 로 풀어 콘텐츠가 다 보이게 한다.
            if parent_mode == "HORIZONTAL" and parent_clips:
                skip = True
                cbb = node.get("absoluteBoundingBox") or {}
                card_bottom = (cbb.get("y") or 0) + (cbb.get("height") or 0)
                child_bottom = card_bottom
                for ch in node.get("children", []) or []:
                    chbb = ch.get("absoluteBoundingBox") or {}
                    cb = (chbb.get("y") or 0) + (chbb.get("height") or 0)
                    if cb > child_bottom:
                        child_bottom = cb
                if child_bottom > card_bottom + 1.5:  # 콘텐츠 overflow → HUG 허용
                    skip = False
            # 2026-05-27 확장: FILL 도 잡는다. 카드(HUG) 안의 Body(FILL) 가
            # 부모 height 에 맞춰 0px 로 collapse 되어 stage_list 회귀 재발.
            if (not skip and layout_mode == "VERTICAL"
                    and sizing_v in ("FIXED", "FILL")):
                try:
                    call_tool("set_layout_sizing", {
                        "nodeId": node.get("id"),
                        "vertical": "HUG",
                    })
                    fixed[0] += 1
                except Exception:
                    pass
        my_mode = (node.get("layoutMode") or "").upper()
        my_clips = bool(node.get("clipsContent"))
        for c in node.get("children", []) or []:
            walk(c, depth + 1, my_mode, my_clips)

    walk(doc)
    if fixed[0]:
        print(f"  [vertical-hug] VERTICAL FIXED → HUG 강제 {fixed[0]}건 "
              f"(batch_build height-FIXED 버그 회피)")
    else:
        print(f"  [vertical-hug] OK — VERTICAL frame 전부 HUG/FILL")
    return fixed[0]


def _enforce_horizontal_row_hug_v_live(root_id: str) -> int:
    """HORIZONTAL row 의 layoutSizingVertical=FIXED 회귀 → HUG 강제 (2026-05-27).

    batch_build_screen 이 blueprint 에 height 명시 안 한 HORIZONTAL frame 도
    layoutSizingVertical=FIXED 로 박는 버그가 있어 row 가 텍스트 24px 인데 83px 같이
    쓸데없이 큰 박스가 됨. _enforce_vertical_hug 는 VERTICAL frame 만 잡아 사각지대.

    판정:
    - parent type=FRAME + layoutMode=HORIZONTAL + layoutSizingVertical=FIXED
    - 자식 모두 layoutSizingVertical=HUG (FILL/FIXED 자식 없음)
    - 자식 중 ABSOLUTE 없음 (FAB/sticky 제외)
    - parent 의 height 가 자식 max height 보다 큼 (의도된 height 아님)

    Fix: parent layoutSizingVertical = HUG
    """
    fixed = [0]

    def _qualifies(node):
        """텍스트-only HORIZONTAL row 의 FIXED → HUG 강제 (정밀 룰).

        ⚠️ get_nodes_info 가 height/width 반환 안 함 — 자식 타입 기반으로 정확히 매칭.
        - HORIZONTAL FRAME + FIXED vertical + 자식 전부 TEXT → HUG 강제
        - 자식이 FRAME 섞이면 (Banner Left + Check Btn 등) 의도된 height 가능성 → skip
        - 자식이 다 ICON/VECTOR 인 row (예: Status Bar Levels) 도 의도된 height → skip
        """
        if node.get("type") != "FRAME":
            return False
        if node.get("layoutMode") != "HORIZONTAL":
            return False
        if node.get("layoutSizingVertical") != "FIXED":
            return False
        if node.get("layoutPositioning") == "ABSOLUTE":
            return False  # FAB/sticky bar 등 의도된 ABSOLUTE
        # ⚠️ 2026-06-02: 원형/작은 정사각 셀(회차 셀렉터 Round N 등)은 HUG 로 만들면
        # 높이가 텍스트(~14px)로 붕괴해 정원이 타원(pill)으로 찌부러진다. cornerRadius
        # 가 절반 이상(원형)이거나 폭이 작은(≤60) 정사각 셀은 FIXED 정사각 유지 — skip.
        _w, _h = _node_wh(node)
        _cr = node.get("cornerRadius") or 0
        if _w and _cr >= (_w / 2) - 3:
            return False  # 원형 셀 — FIXED 정사각 유지
        if 0 < _w <= 60 and _h and abs(_w - _h) <= 8:
            return False  # 작은 정사각 셀 (숫자/아이콘 칩) — FIXED 유지
        children = node.get("children") or []
        if not children:
            return False
        # 자식이 TEXT(또는 얇은 세로 divider) 인 경우만 잡기 — 가장 안전.
        # 2026-05-28: part-divider(RECTANGLE) 가 섞인 'Participating Tabs Row' 가
        # FIXED 83 으로 박혀 위아래 허전한 회귀 → divider RECTANGLE/LINE 도 허용.
        def _allowed(c):
            t = c.get("type")
            if t == "TEXT":
                return True
            if t in ("RECTANGLE", "LINE"):
                nm = (c.get("name") or "").lower()
                return any(k in nm for k in ("divider", "separator", "line"))
            return False
        if not all(_allowed(c) for c in children):
            return False
        # 자식 ABSOLUTE 가드
        for c in children:
            if c.get("layoutPositioning") == "ABSOLUTE":
                return False
        return True

    def walk(node):
        if not isinstance(node, dict):
            return
        if _qualifies(node):
            try:
                call_tool("set_layout_sizing", {"nodeId": node["id"], "vertical": "HUG"})
                fixed[0] += 1
            except Exception as e:
                print(f"  [hrow-hug-v] '{node.get('name')}' fail: {e}")
        for c in node.get("children") or []:
            walk(c)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [hrow-hug-v] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [hrow-hug-v] ✓ HORIZONTAL row {fixed[0]}건 vertical FIXED → HUG (불필요 height 제거)")
    else:
        print(f"  [hrow-hug-v] OK — HORIZONTAL row 높이 적정")
    return fixed[0]


def _enforce_grid_row_cards_fill_live(root_id: str) -> int:
    """HORIZONTAL grid row 안의 카드 자식들을 FILL 로 강제 (2026-05-27 사용자 회귀 fix).

    batch_build_screen 이 blueprint 의 layoutSizingHorizontal=FILL 을 무시하고
    카드를 HUG 로 빌드하는 경우가 있어 카드가 좁아져 텍스트 줄바꿈 발생.
    HORIZONTAL parent 의 자식들이 모두 카드형 + HUG 면 자동 FILL 강제.

    판정:
    - parent type=FRAME + layoutMode=HORIZONTAL + 자식 2~4 개
    - parent name 에 'grid' OR 'cards' 키워드 OR 자식 전부 name 에 'card'/'Card' 포함
    - 모든 자식 type=FRAME + layoutSizingHorizontal=HUG
    """
    fixed = [0]

    def _is_card_grid(parent):
        if parent.get("type") != "FRAME" or parent.get("layoutMode") != "HORIZONTAL":
            return False
        children = parent.get("children") or []
        if not (2 <= len(children) <= 4):
            return False
        # 모든 자식 FRAME + HUG 사이즈
        for c in children:
            if c.get("type") != "FRAME":
                return False
            if c.get("layoutSizingHorizontal") != "HUG":
                return False
        # parent name 에 'grid'/'cards' 또는 자식 전부 'card' 키워드
        pname = (parent.get("name") or "").lower()
        if "grid" in pname or "cards" in pname:
            return True
        if all("card" in (c.get("name") or "").lower() for c in children):
            return True
        return False

    def walk(node):
        if not isinstance(node, dict):
            return
        if _is_card_grid(node):
            for c in node.get("children") or []:
                try:
                    call_tool("set_layout_sizing", {"nodeId": c["id"], "horizontal": "FILL"})
                    fixed[0] += 1
                except Exception as e:
                    print(f"  [grid-row-fill] '{c.get('name')}' fail: {e}")
        for c in node.get("children") or []:
            walk(c)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [grid-row-fill] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [grid-row-fill] ✓ grid row 안 카드 {fixed[0]}건 HUG → FILL 강제 (좁아져 텍스트 wrap 차단)")
    else:
        print(f"  [grid-row-fill] OK — grid row 카드 사이즈 정상")
    return fixed[0]


def _strip_section_wrapper_borders_live(root_id: str) -> int:
    """wrapper 섹션 frame(Section/Wrap/Container/Row/List/Stack/Group) 에 잘못 박힌 stroke 제거 (2026-05-27).

    사용자 명시: "섹션 프레임 자체에 border 가 들어가있어! 없어야 한다".
    이전 `_enforce_white_card_border_live` 가 section 키워드를 카드로 false-positive
    분류하던 케이스 회귀 차단. 카드는 'card'/'banner'/'hero' 또는 cornerRadius>=8 만 인정.
    """
    WRAPPER_KW = ("section", "wrap", "container", "row", "stack", "group", "list")
    fixed = [0]

    def _is_wrapper(node):
        """wrapper 판정 — cornerRadius 기반 (혼합 케이스 처리, 2026-05-27 사용자 분노 fix).

        "Attendance Banner Wrap" 같이 wrapper 키워드 + 카드 키워드 혼합돼도 cornerRadius=0
        이면 wrapper 로 판정. 카드는 둥근 모서리(cornerRadius >= 8) 시각적 표식 필수.
        """
        name = (node.get("name") or "").lower()
        if not any(k in name for k in WRAPPER_KW):
            return False
        cr = node.get("cornerRadius") or 0
        if isinstance(cr, (int, float)) and cr >= 8:
            return False  # 둥근 모서리 = 카드 (wrapper 아님)
        return True  # wrapper 키워드 + cornerRadius < 8 → wrapper 확정

    def walk(node):
        if not isinstance(node, dict):
            return
        # DS 인스턴스 내부는 master 제어 — stroke 손대지 않음
        if (node.get("type") or "").upper() == "INSTANCE":
            return
        if node.get("type") in ("FRAME", "frame") and _is_wrapper(node):
            strokes = node.get("strokes") or []
            if strokes:
                try:
                    call_tool("set_stroke_color", {
                        "nodeId": node["id"],
                        "r": 0, "g": 0, "b": 0, "a": 0,
                        "strokeWeight": 0,
                    })
                    fixed[0] += 1
                except Exception as e:
                    print(f"  [strip-wrapper-border] '{node.get('name')}' fail: {e}")
        for ch in node.get("children", []) or []:
            walk(ch)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [strip-wrapper-border] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [strip-wrapper-border] ✓ wrapper 섹션 {fixed[0]}건의 잘못된 stroke 제거")
    else:
        print(f"  [strip-wrapper-border] OK — wrapper 섹션 stroke 없음")
    return fixed[0]


def _enforce_badge_no_stroke_live(root_id: str) -> int:
    """DS Badge/Tag 인스턴스의 stroke 제거 (2026-05-28 사용자 절대 룰).

    사용자 명시: "badge 에 stroke 은 없는거란다" + "badge 는 임의로 fill color 바꾸지마!
    오직 Props 에 color option 만 선택". badge 색은 component property(color variant)로만
    제어하고, **stroke 은 무조건 없다**. swap 된 badge variant 가 outline(보더)을 들고
    있거나 이전 룰이 brand 보더를 박았으면 여기서 일괄 제거.

    - 대상: type=INSTANCE + name 에 badge/tag/pill/chip/round-tag 포함 + strokes 있음
    - fill 은 절대 건드리지 않는다 (master/variant 제어). stroke 만 strokeWeight 0 으로.
    """
    fixed = [0]

    def walk(node):
        if not isinstance(node, dict):
            return
        ntype = (node.get("type") or "").upper()
        nl = (node.get("name") or "").lower()
        if ntype == "INSTANCE" and any(k in nl for k in ("badge", "tag", "pill", "chip")):
            if node.get("strokes"):
                try:
                    call_tool("set_stroke_color", {
                        "nodeId": node["id"], "r": 0, "g": 0, "b": 0, "a": 0, "strokeWeight": 0,
                    })
                    fixed[0] += 1
                    print(f"  [badge-no-stroke] '{node.get('name')}' stroke 제거 (badge 는 보더 없음)")
                except Exception as e:
                    print(f"  [badge-no-stroke] '{node.get('name')}' fail: {e}")
            # badge 인스턴스 내부는 master 제어 — 더 내려가지 않음
            return
        for c in node.get("children", []) or []:
            walk(c)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [badge-no-stroke] root fetch fail: {e}")
    if fixed[0] == 0:
        print("  [badge-no-stroke] OK — badge stroke 없음")
    return fixed[0]


def _enforce_fab_size_live(root_id: str) -> int:
    """FAB 는 무조건 56×56 icon-only 원형 (2026-05-27 사용자 명시 절대 룰).

    blueprint 가 width/height 를 다르게 작성했어도 live 트리에서 강제 교정.
    - 대상: name 이 "FAB"/"Fab"/"fab" 이거나 type=FRAME + width≤80 + cornerRadius≥20 + bottom-right 위치
    - Fix: resize_node(56, 56) + set_corner_radius(28) + set_layout_sizing(FIXED, FIXED)
    """
    fixed = [0]

    def _is_fab(node):
        name = (node.get("name") or "").strip()
        if name in ("FAB", "Fab", "fab"):
            return True
        # icon-only round 휴리스틱: width ≤ 80 + cornerRadius ≥ 20 + ABSOLUTE 위치
        if node.get("type") not in ("FRAME", "frame"):
            return False
        w = node.get("width") or 0
        cr = node.get("cornerRadius") or 0
        if w <= 80 and isinstance(cr, (int, float)) and cr >= 20 \
                and node.get("layoutPositioning") == "ABSOLUTE":
            return True
        return False

    def walk(node):
        if not isinstance(node, dict):
            return
        if _is_fab(node):
            try:
                w = node.get("width") or 0
                h = node.get("height") or 0
                cr = node.get("cornerRadius") or 0
                if abs(w - 56) > 0.5 or abs(h - 56) > 0.5 or cr != 28:
                    call_tool("set_layout_sizing", {"nodeId": node["id"], "horizontal": "FIXED", "vertical": "FIXED"})
                    call_tool("resize_node", {"nodeId": node["id"], "width": 56, "height": 56})
                    call_tool("set_corner_radius", {"nodeId": node["id"], "cornerRadius": 28})
                    fixed[0] += 1
            except Exception as e:
                print(f"  [fab-size] '{node.get('name')}' fail: {e}")
            return  # FAB 안은 walk 안 함 (icon 만 있음)
        for ch in node.get("children", []) or []:
            walk(ch)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [fab-size] root fetch fail: {e}")
    return fixed[0]


def _enforce_fab_icon_color_live(root_id: str) -> int:
    """FAB 안 icon 색은 무조건 fg-light (#ffffff) — 2026-05-28 사용자 명시 절대 룰.

    brand-solid 위 흰 아이콘이 정석. blueprint 가 fg-white / 검정 / 임의색 으로
    박았어도, set_fill_color/set_stroke_color 가 raw RGB 박았어도, live 트리에서
    FAB 자손 모든 VECTOR/ICON 의 fills[0] · strokes[0] 을 fg-light 로 강제 + 바인딩.

    회귀 차단: 새 세션에서 generator/post-fix 가 fg-white(alias) / fg-primary_on-brand
    /검정 박아도 이 함수가 마지막에 fg-light 로 덮어씀.
    """
    fixed = [0]

    def _is_fab(node):
        name = (node.get("name") or "").strip()
        if name in ("FAB", "Fab", "fab"):
            return True
        if node.get("type") not in ("FRAME", "frame"):
            return False
        w = node.get("width") or 0
        cr = node.get("cornerRadius") or 0
        if w <= 80 and isinstance(cr, (int, float)) and cr >= 20 \
                and node.get("layoutPositioning") == "ABSOLUTE":
            return True
        return False

    fp = None
    try:
        fp = _token_to_figma_path("fg-light")
    except Exception:
        fp = "Colors/Foreground/fg-light"

    def _paint_white(node_id: str, has_fills: bool, has_strokes: bool):
        # 의도적 FAB 아이콘 색 강제 — 중앙 component-color 가드 예외(_allowComponentColor)
        try:
            if has_fills:
                call_tool("set_fill_color", {"nodeId": node_id, "r": 1, "g": 1, "b": 1, "a": 1, "_allowComponentColor": True})
                if fp:
                    try:
                        call_tool("set_bound_variables", {"nodeId": node_id, "bindings": {"fills/0": fp}, "_allowComponentColor": True})
                    except Exception:
                        pass
            if has_strokes:
                call_tool("set_stroke_color", {"nodeId": node_id, "r": 1, "g": 1, "b": 1, "a": 1, "_allowComponentColor": True})
                if fp:
                    try:
                        call_tool("set_bound_variables", {"nodeId": node_id, "bindings": {"strokes/0": fp}, "_allowComponentColor": True})
                    except Exception:
                        pass
            fixed[0] += 1
        except Exception as e:
            print(f"  [fab-icon-color] '{node_id}' fail: {e}")

    def _walk_fab_descendants(node):
        if not isinstance(node, dict):
            return
        ntype = (node.get("type") or "").upper()
        # VECTOR 또는 ICON-shape (작은 24px 이하 frame) 모두 처리
        if ntype == "VECTOR" or (ntype == "FRAME" and (node.get("width") or 0) <= 32 and not node.get("children")):
            fills = node.get("fills") or []
            strokes = node.get("strokes") or []
            has_visible_fill = any((f.get("visible") is not False) and (f.get("type") == "SOLID") for f in fills if isinstance(f, dict))
            has_visible_stroke = any((s.get("visible") is not False) and (s.get("type") == "SOLID") for s in strokes if isinstance(s, dict))
            if has_visible_fill or has_visible_stroke:
                _paint_white(node["id"], has_visible_fill, has_visible_stroke)
        for ch in node.get("children", []) or []:
            _walk_fab_descendants(ch)

    def _walk_root(node):
        if not isinstance(node, dict):
            return
        if _is_fab(node):
            for ch in node.get("children", []) or []:
                _walk_fab_descendants(ch)
            return  # FAB 안 다 처리했음
        for ch in node.get("children", []) or []:
            _walk_root(ch)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            _walk_root(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [fab-icon-color] root fetch fail: {e}")
    return fixed[0]


def _enforce_icon_on_brand_bg_contrast(root_id: str) -> int:
    """brand bg frame 안 같은 brand 계열 icon → white 강제 (2026-05-28).

    사례: Hero Icon Box (bg-brand-solid 0.32,0,0.69 진한 보라) +
    piggy-bank Vector stroke (brand-primary 0.42,0,0.88 같은 보라) → invisible.

    검출:
      - frame fills[0] = brand-purple (r∈[0.2,0.6], g<0.25, b∈[0.5,1.0])
      - 자손 VECTOR/icon-frame 의 stroke/fill 이 같은 brand hue (color distance < 0.25)
    교정: stroke/fill 을 white (1,1,1) + fg-light 토큰 바인딩.

    회귀 차단: blueprint 가 brand bg + brand icon stroke 박았어도 자동 fix.
    """
    fixed = [0]

    def _is_brand_purple(rgb):
        if not rgb:
            return False
        r = rgb.get("r", 0)
        g = rgb.get("g", 0)
        b = rgb.get("b", 0)
        return 0.2 <= r <= 0.6 and g <= 0.25 and 0.5 <= b <= 1.0

    def _color_distance(a, b):
        if not a or not b:
            return 1.0
        return (abs(a.get("r", 0) - b.get("r", 0))
                + abs(a.get("g", 0) - b.get("g", 0))
                + abs(a.get("b", 0) - b.get("b", 0)))

    fp = None
    try:
        fp = _token_to_figma_path("fg-light")
    except Exception:
        fp = "Colors/Foreground/fg-light"

    def _paint_white(node_id, has_fills, has_strokes):
        # 의도적 brand 위 아이콘 색 강제 — 중앙 component-color 가드 예외(_allowComponentColor)
        try:
            if has_fills:
                call_tool("set_fill_color", {"nodeId": node_id, "r": 1, "g": 1, "b": 1, "a": 1, "_allowComponentColor": True})
                if fp:
                    try:
                        call_tool("set_bound_variables", {"nodeId": node_id, "bindings": {"fills/0": fp}, "_allowComponentColor": True})
                    except Exception:
                        pass
            if has_strokes:
                call_tool("set_stroke_color", {"nodeId": node_id, "r": 1, "g": 1, "b": 1, "a": 1, "_allowComponentColor": True})
                if fp:
                    try:
                        call_tool("set_bound_variables", {"nodeId": node_id, "bindings": {"strokes/0": fp}, "_allowComponentColor": True})
                    except Exception:
                        pass
            fixed[0] += 1
        except Exception as e:
            print(f"  [icon-on-brand] '{node_id}' fail: {e}")

    def _walk_icons_inside(node, bg_color):
        if not isinstance(node, dict):
            return
        ntype = (node.get("type") or "").upper()
        is_icon_target = ntype == "VECTOR" or (
            ntype == "FRAME" and (node.get("width") or 0) <= 48 and not node.get("children")
        )
        if is_icon_target:
            fills = node.get("fills") or []
            strokes = node.get("strokes") or []
            has_fill_bad = False
            has_stroke_bad = False
            for f in fills:
                if isinstance(f, dict) and f.get("visible") is not False and f.get("type") == "SOLID":
                    if _color_distance(f.get("color"), bg_color) < 0.45:
                        has_fill_bad = True
                        break
            for s in strokes:
                if isinstance(s, dict) and s.get("visible") is not False and s.get("type") == "SOLID":
                    if _color_distance(s.get("color"), bg_color) < 0.45:
                        has_stroke_bad = True
                        break
            if has_fill_bad or has_stroke_bad:
                _paint_white(node["id"], has_fill_bad, has_stroke_bad)
        for ch in node.get("children", []) or []:
            _walk_icons_inside(ch, bg_color)

    def _walk_root(node):
        if not isinstance(node, dict):
            return
        ntype = (node.get("type") or "").upper()
        # FAB 는 별도 _enforce_fab_icon_color_live 가 처리 → 여기서 skip
        name = (node.get("name") or "").lower()
        if "fab" in name or name == "fab":
            return
        if ntype in ("FRAME", "INSTANCE", "COMPONENT"):
            fills = node.get("fills") or []
            for f in fills:
                if isinstance(f, dict) and f.get("visible") is not False and f.get("type") == "SOLID":
                    if _is_brand_purple(f.get("color")):
                        for ch in node.get("children", []) or []:
                            _walk_icons_inside(ch, f.get("color"))
                        break
        for ch in node.get("children", []) or []:
            _walk_root(ch)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            _walk_root(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [icon-on-brand] root fetch fail: {e}")
    return fixed[0]


def _build_button_label_map(blueprint: Optional[dict]) -> dict:
    """blueprint 의 button-shape frame name → label 맵. post-fix 가 swap 된
    DS 버튼 인스턴스의 더미 'Button CTA' 텍스트를 원래 라벨로 교정하는 데 사용."""
    m = {}
    if not blueprint:
        return m
    try:
        from design_rules.ds_catalog import detect_button_shape
    except Exception:
        return m
    root = blueprint.get("root") or blueprint

    def walk(n):
        if isinstance(n, dict):
            try:
                b = detect_button_shape(n)
                if b and b[2]:
                    m[(n.get("name") or "")] = b[2]
            except Exception:
                pass
            for c in (n.get("children") or n.get("_originalChildren") or []):
                walk(c)
        elif isinstance(n, list):
            for c in n:
                walk(c)
    walk(root)
    return m


def _enforce_ds_button_sizing(root_id: str, label_map: Optional[dict] = None) -> int:
    """DS Action Button 인스턴스 라이브 교정 (2026-05-28 사용자 "버튼이 제일 중요").

    R23 가 버튼 raw frame → DS 'Action Button' 인스턴스로 auto-swap 한 뒤 남는
    3대 문제를 한 번에 교정:
      1. sizing 붕괴 — width < 60 → VERTICAL 부모면 FILL / HORIZONTAL 이면 HUG,
         height < 40 → FIXED 48 (md 표준)
      2. leading/trailing 아이콘 노출 — Icon leading/trailing BOOLEAN prop → false
      3. 더미 'Button CTA' 라벨 — blueprint 의 원래 label 로 내부 TEXT 교체
    """
    label_map = label_map or {}
    fixed = [0]

    def _fix_instance(nid, name, w, h, parent_layout):
        # 1) sizing — VERTICAL 부모의 단독 CTA 는 항상 가로 FILL (2026-05-28 사용자
        #    "버튼을 가로로 채워야지"). HORIZONTAL 부모(버튼 그룹)면 좁을 때만 HUG.
        try:
            if parent_layout == "VERTICAL":
                call_tool("set_layout_sizing", {"nodeId": nid, "horizontal": "FILL"})
            elif w < 60:
                call_tool("set_layout_sizing", {"nodeId": nid, "horizontal": "HUG"})
            if h < 40:
                call_tool("set_layout_sizing", {"nodeId": nid, "vertical": "FIXED"})
                call_tool("resize_node", {"nodeId": nid,
                                          "width": max(w, 100) if w >= 60 else 200, "height": 48})
        except Exception as e:
            print(f"  [ds-button-sizing] sizing '{nid}' fail: {e}")
        # 2) icon off — BOOLEAN props named icon leading/trailing → false
        try:
            props = parse_content(call_tool("get_instance_properties", {"nodeId": nid})).get("json") or {}
            pdict = props.get("properties") or {}
            off = {}
            for pname, pinfo in pdict.items():
                pl = pname.lower()
                if isinstance(pinfo, dict) and pinfo.get("type") == "BOOLEAN" \
                        and ("icon leading" in pl or "icon trailing" in pl) and pinfo.get("value"):
                    off[pname] = False
            # ⚠️ 2026-08-04 사용자 룰 (2026-05-28 'lg 기본' 을 개정): "기본 화면들에서
            # CTA 버튼의 크기는 2xl". 전폭(VERTICAL 부모) 하단 CTA 의 Size VARIANT 를 2xl 로 강제.
            if parent_layout == "VERTICAL":
                for pname, pinfo in pdict.items():
                    if (isinstance(pinfo, dict) and pinfo.get("type") == "VARIANT"
                            and pname.lower() == "size"
                            and str(pinfo.get("value")).lower() != "2xl"):
                        off[pname] = "2xl"
            if off:
                call_tool("set_instance_properties", {"nodeId": nid, "properties": off})
        except Exception as e:
            print(f"  [ds-button-sizing] icon-off '{nid}' fail: {e}")
        # 3) label override — 더미 텍스트 → blueprint label
        label = label_map.get(name)
        if label:
            try:
                scan = parse_content(call_tool("scan_text_nodes", {"nodeId": nid})).get("json") or {}
                tnodes = scan.get("textNodes") or []
                if tnodes:
                    call_tool("set_text_content", {"nodeId": tnodes[0]["id"], "text": label})
            except Exception as e:
                print(f"  [ds-button-sizing] label '{nid}' fail: {e}")
        fixed[0] += 1

    def _walk(node, parent_layout=""):
        if not isinstance(node, dict):
            return
        ntype = (node.get("type") or "").upper()
        name = node.get("name") or ""
        nl = name.lower()
        is_btn = ntype == "INSTANCE" and ("action button" in nl or nl == "button"
                                          or nl.endswith(" button") or nl.endswith(" btn")
                                          or nl.endswith(" cta") or "cta" in nl)
        if is_btn:
            _fix_instance(node["id"], name, node.get("width") or 0,
                          node.get("height") or 0, parent_layout)
        cur_layout = (node.get("layoutMode") or "").upper()
        for c in node.get("children", []) or []:
            _walk(c, cur_layout)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            _walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [ds-button-sizing] root fetch fail: {e}")
    return fixed[0]


def _enforce_consecutive_cta_hierarchy(root_id: str, blueprint: Optional[dict] = None) -> int:
    """🔴 연속 전폭 CTA 위계 차등 (2026-06-05 사용자: "CTA 버튼이 위 아래 연속적으로 있을땐
    좀 더 덜 중요한 버튼의 위계를 tertiary 나 outline 으로 설정").

    세로로 인접한 전폭 DS Action Button 'Primary' 인스턴스가 2개 이상이면 한 화면에 같은
    강조색 CTA 가 위계 없이 경쟁한다 → **맨 아래(주 액션·엄지 영역) 1개만 Primary 로 두고
    위쪽들을 'Outline' 으로 자동 다운그레이드**(set_instance_properties Hierarchy). blueprint
    CTA 에 `_ctaKeepPrimary: true` 마커가 있으면 그 버튼(들)을 Primary 로 유지하고 같은 그룹의
    나머지를 Outline 으로 내린다.

    '연속' = 두 전폭 Primary CTA 사이 세로 간격이 GAP(320px, 카드 1개 경계 정도) 미만.
    멀리 떨어진(스크롤상 다른 맥락) CTA 는 건드리지 않는다. Outline flip 실패 시 Tertiary→
    Secondary 로 폴백(variant set 마다 Hierarchy 옵션이 다를 수 있어). 라이브 후처리 —
    button sizing/variant flip *이후* 에 돌아 Primary 로 확정된 CTA 만 대상.
    """
    GAP = 320
    keep_names = set()

    def _ck(node):
        if not isinstance(node, dict):
            return
        if node.get("_ctaKeepPrimary") and node.get("name"):
            keep_names.add(node["name"])
        for c in (node.get("children") or node.get("_originalChildren") or []):
            _ck(c)
    if blueprint:
        _ck(blueprint.get("root") or blueprint)

    cta = []

    def _walk(node):
        if not isinstance(node, dict):
            return
        ntype = (node.get("type") or "").upper()
        name = node.get("name") or ""
        nl = name.lower()
        is_btn = ntype == "INSTANCE" and ("action button" in nl or nl == "button"
                                          or nl.endswith(" button") or nl.endswith(" btn")
                                          or nl.endswith(" cta") or "cta" in nl)
        if is_btn:
            w, h = _node_wh(node)
            bb = node.get("absoluteBoundingBox") or {}
            y = bb.get("y")
            if w and w >= 250 and isinstance(y, (int, float)):  # 전폭 CTA 만
                hier = None
                label = ""
                try:
                    props = parse_content(call_tool("get_instance_properties", {"nodeId": node["id"]})).get("json") or {}
                    for pn, pi in (props.get("properties") or {}).items():
                        if not isinstance(pi, dict):
                            continue
                        pl = pn.lower()
                        if pl == "hierarchy":
                            hier = str(pi.get("value"))
                        elif pl.startswith("label"):  # 'Label#17537:16' 등 — CTA 문구
                            label = str(pi.get("value") or "")
                except Exception:
                    pass
                cta.append({"id": node["id"], "name": name, "top": y, "bottom": y + (h or 0), "hier": hier, "label": label})
        for c in node.get("children", []) or []:
            _walk(c)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            _walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [cta-hierarchy] root fetch fail: {e}")
        return 0

    prim = sorted([c for c in cta if (c["hier"] or "").lower() == "primary"], key=lambda c: c["top"])
    if len(prim) < 2:
        return 0

    # 연속 그룹핑 (세로 간격 < GAP)
    groups, cur = [], []
    for c in prim:
        if cur and (c["top"] - cur[-1]["bottom"]) < GAP:
            cur.append(c)
        else:
            if cur:
                groups.append(cur)
            cur = [c]
    if cur:
        groups.append(cur)

    def _flip_outline(nid):
        for opt in ("Outline", "Tertiary", "Secondary"):
            try:
                call_tool("set_instance_properties", {"nodeId": nid, "properties": {"Hierarchy": opt}})
                return opt
            except Exception:
                continue
        return None

    # 🔴 2026-06-05 사용자: "화면상에서 맥락을 고려해 더 중요한 액션을 primary 로". 어느 CTA 가
    #    더 중요한지는 의미 판단이라 코드가 완벽히 알 순 없다 → 3단 우선순위:
    #      1) blueprint `_ctaKeepPrimary` 마커 (Claude 가 맥락 판단으로 명시 — 최우선/원칙)
    #      2) 라벨 의미 휴리스틱 — '주 액션' 동사(납입/참여/확인/제출 등)가 '보조'(출금/취소/
    #         나중에 등)보다 우선. 그룹 일부만 주 액션이면 그것을 Primary 유지.
    #      3) 둘 다 판단 불가(모두 주 액션 / 모두 중립)면 맨 아래(엄지 영역) 폴백.
    _PRIMARY_ACTION_HINT = ("납입", "결제", "제출", "참여", "신청", "확인", "시작", "다음",
                            "완료", "동의", "송금", "이체", "보내기", "주문", "등록", "예약",
                            "가입", "인증", "충전하기")
    _SECONDARY_ACTION_HINT = ("출금", "취소", "나중", "더보기", "공유", "저장", "닫기",
                              "건너", "임시", "삭제", "뒤로", "이전")

    def _action_weight(lbl):
        s = lbl or ""
        if any(h in s for h in _SECONDARY_ACTION_HINT):
            return -1
        if any(h in s for h in _PRIMARY_ACTION_HINT):
            return 1
        return 0

    n = 0
    for g in groups:
        if len(g) < 2:
            continue
        g = sorted(g, key=lambda c: c["top"])
        marked = [c for c in g if c["name"] in keep_names]
        if marked:
            keeper_ids = {c["id"] for c in marked}  # 1) Claude 맥락 마커 (최우선)
        else:
            weights = [(_action_weight(c.get("label")), c) for c in g]
            top_w = max(w for w, _ in weights)
            best = [c for w, c in weights if w == top_w]
            if top_w > min(w for w, _ in weights):  # 2) 의미 차등 — 가장 중요한 액션만 Primary
                keeper_ids = {sorted(best, key=lambda c: c["top"])[-1]["id"]}
            else:                                    # 3) 동률 → 맨 아래 폴백
                keeper_ids = {g[-1]["id"]}
        for c in g:
            if c["id"] in keeper_ids:
                continue
            opt = _flip_outline(c["id"])
            if opt:
                print(f"  [cta-hierarchy] '{c['name']}' Primary → {opt} (연속 CTA 위계 차등)")
                n += 1
    if n:
        print(f"  [cta-hierarchy] ✓ 연속 전폭 Primary CTA {n}건 다운그레이드 (주 액션만 Primary 유지)")
    return n


def _enforce_horizontal_repeated_cta_tertiary(root_id: str) -> int:
    """🔴 수평 연속 동일 성격 CTA → Tertiary (2026-06-05 사용자: "fab 버튼도 있는 화면에서
    수평으로 연속된 버튼 같은 경우는 성격까지 같다면 버튼 위계를 tertiary 로 설정").

    캐로셀 등에서 가로로 나열된 DS Action Button 이 2개 이상이고 **라벨(성격)이 동일**하면
    (예: 추천 카드 2장의 '참여하기' × 2) 위계 경쟁이 무의미 + brand 과다(FAB 가 이미 화면의
    brand 주 액션)이므로 전부 **Tertiary**(폴백 Outline→Secondary)로 다운그레이드한다.
    FAB 가 있는 화면에만 적용(brand 강조점이 이미 있다는 전제 — 사용자 명시 "fab 도 있는 화면").
    '수평/같은 행' = 같은 라벨 CTA 들의 top 편차 < 40px 이고 x 는 서로 다름(겹침 아님).
    세로 규칙 `_enforce_consecutive_cta_hierarchy`(전폭 width≥250)와 대상이 갈린다 —
    캐로셀 카드 CTA 는 폭<250 이라 세로 규칙은 건드리지 않음.
    """
    cta = []
    has_fab = [False]

    def _walk(node):
        if not isinstance(node, dict):
            return
        ntype = (node.get("type") or "").upper()
        name = node.get("name") or ""
        nl = name.lower()
        if "fab" in nl:
            has_fab[0] = True
        is_btn = ntype == "INSTANCE" and ("action button" in nl or nl == "button"
                                          or nl.endswith(" button") or nl.endswith(" btn")
                                          or nl.endswith(" cta") or "cta" in nl)
        if is_btn:
            bb = node.get("absoluteBoundingBox") or {}
            x, y = bb.get("x"), bb.get("y")
            label, hier = "", None
            try:
                props = parse_content(call_tool("get_instance_properties", {"nodeId": node["id"]})).get("json") or {}
                for pn, pi in (props.get("properties") or {}).items():
                    if not isinstance(pi, dict):
                        continue
                    pl = pn.lower()
                    if pl == "hierarchy":
                        hier = str(pi.get("value"))
                    elif pl.startswith("label"):
                        label = str(pi.get("value") or "")
            except Exception:
                pass
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                cta.append({"id": node["id"], "name": name, "label": label.strip(),
                            "x": x, "top": y, "hier": hier})
        for c in node.get("children", []) or []:
            _walk(c)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            _walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [cta-horiz-tertiary] root fetch fail: {e}")
        return 0

    if not has_fab[0]:
        return 0  # FAB(brand 주 액션) 있는 화면에만 적용

    by_label = {}
    for c in cta:
        if c["label"]:
            by_label.setdefault(c["label"], []).append(c)

    def _flip_tertiary(nid):
        for opt in ("Tertiary", "Outline", "Secondary"):
            try:
                call_tool("set_instance_properties", {"nodeId": nid, "properties": {"Hierarchy": opt}})
                return opt
            except Exception:
                continue
        return None

    n = 0
    for lbl, group in by_label.items():
        if len(group) < 2:
            continue
        if (max(c["top"] for c in group) - min(c["top"] for c in group)) >= 40:
            continue  # 같은 행 아님 (세로로 떨어진 동일 라벨 — 수평 반복 아님)
        xs = sorted(c["x"] for c in group)
        if xs[-1] - xs[0] < 20:
            continue  # x 가 거의 같음 — 겹침/단일, 수평 나열 아님
        for c in group:
            if (c["hier"] or "").lower() == "tertiary":
                continue
            opt = _flip_tertiary(c["id"])
            if opt:
                print(f"  [cta-horiz-tertiary] '{c['name']}' ({lbl}) → {opt} (수평 반복 동일 성격 CTA)")
                n += 1
    if n:
        print(f"  [cta-horiz-tertiary] ✓ 수평 반복 동일 성격 CTA {n}건 → Tertiary (FAB 화면)")
    return n


def _collect_instance_text_paths(blueprint: Optional[dict]) -> dict:
    """inject 된 blueprint 에서 {이름 경로 tuple: _instanceText} 맵 수집.
    R23 가 swap 한 instance 노드의 원래 텍스트(_instanceText)를 빌드 후 적용하기 위함."""
    out = {}
    if not isinstance(blueprint, dict):
        return out
    root = blueprint.get("root") or blueprint

    def walk(node, chain):
        if not isinstance(node, dict):
            return
        nm = node.get("name") or ""
        cur = chain + (nm,)
        if node.get("componentKey") and node.get("_instanceText"):
            out[cur] = str(node["_instanceText"])
        for c in (node.get("children") or node.get("_originalChildren") or []):
            walk(c, cur)
    walk(root, ())
    return out


def _collect_instance_variant_paths(blueprint: Optional[dict]) -> dict:
    """inject 된 blueprint 에서 {이름 경로 tuple: instanceProperties dict} 맵 수집.

    ⚠️ batch_build_screen 의 create_component_instance 는 blueprint 의 instanceProperties
    (Hierarchy=Primary, Color=Warning 등 variant flip)를 **적용하지 않는다** — 인스턴스만
    만들고 끝. 그래서 'Action Button md Secondary' 키로 import 후 Hierarchy=Primary 로
    flip 하려던 CTA 가 매 빌드마다 Secondary(연보라) 로 남는 회귀가 있었다(매번 수동 flip).
    이 맵을 빌드 후 set_instance_properties 로 적용해 자동화한다. (2026-06-04)

    `instanceProperties` 또는 `_instanceVariants` 키 둘 다 인식."""
    out = {}
    if not isinstance(blueprint, dict):
        return out
    root = blueprint.get("root") or blueprint

    def walk(node, chain):
        if not isinstance(node, dict):
            return
        nm = node.get("name") or ""
        cur = chain + (nm,)
        props = node.get("instanceProperties") or node.get("_instanceVariants")
        if node.get("componentKey") and isinstance(props, dict) and props:
            out[cur] = dict(props)
        for c in (node.get("children") or node.get("_originalChildren") or []):
            walk(c, cur)
    walk(root, ())
    return out


def _enforce_ds_instance_variants(root_id: str, path_variant_map: dict) -> int:
    """빌드 트리 DS instance 에 blueprint 의 instanceProperties(variant/prop) 적용 (2026-06-04).

    create_component_instance 가 무시하는 Hierarchy/Color/Size/State 등 variant flip 을
    빌드 후 경로 매칭으로 set_instance_properties 적용. CTA Secondary→Primary 자동 flip.
    """
    if not path_variant_map:
        return 0
    fixed = [0]

    def walk(node, chain):
        if not isinstance(node, dict):
            return
        nm = node.get("name") or ""
        cur = chain + (nm,)
        if (node.get("type") or "").upper() == "INSTANCE" and cur in path_variant_map:
            try:
                call_tool("set_instance_properties",
                          {"nodeId": node["id"], "properties": path_variant_map[cur]})
                fixed[0] += 1
            except Exception as e:
                print(f"  [ds-instance-variant] '{node.get('id')}' fail: {e}")
        for c in node.get("children", []) or []:
            walk(c, cur)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0], ())
    except Exception as e:
        print(f"  [ds-instance-variant] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [ds-instance-variant] ✓ instance {fixed[0]}건 variant/prop 적용 "
              f"(Hierarchy/Color/Size flip — 매번 수동 flip 제거)")
    return fixed[0]


def _infer_tooltip_arrow(node: dict, parent: Optional[dict]) -> str:
    """tooltip 인스턴스 위치로 arrow 방향 추론 (2026-06-04).

    대부분 tooltip 은 대상 위에 떠 **아래(Bottom)** 를 가리킨다. 부모 영역 대비
    가로 위치로 left/center/right 를 결정한다. 추론 실패 시 'Bottom center'.
    """
    nb = node.get("absoluteBoundingBox") or {}
    pb = (parent or {}).get("absoluteBoundingBox") or {}
    try:
        ncx = nb["x"] + nb["width"] / 2.0
        frac = (ncx - pb["x"]) / max(1.0, pb["width"]) if pb else 0.5
    except (KeyError, TypeError):
        frac = 0.5
    if frac < 0.34:
        return "Bottom left"
    if frac > 0.66:
        return "Bottom right"
    return "Bottom center"


def _tt_bbox(n: dict) -> dict:
    return (n.get("absoluteBoundingBox") or {}) if isinstance(n, dict) else {}


def _collect_tooltip_targets(blueprint: Optional[dict]) -> dict:
    """blueprint 에서 {이름 경로 tuple: target 노드 이름} 맵 수집 (2026-06-04).

    tooltip 인스턴스에 `_tooltipTarget`(가리킬 대상 노드 이름) 마커가 있으면 수집.
    빌드 후 _enforce_tooltip_arrow_live 가 이 맵으로 arrow 방향+위치를 대상에 맞춘다.
    """
    out = {}
    if not isinstance(blueprint, dict):
        return out
    root = blueprint.get("root") or blueprint

    def walk(node, chain):
        if not isinstance(node, dict):
            return
        cur = chain + (node.get("name") or "",)
        tgt = node.get("_tooltipTarget")
        if node.get("componentKey") and isinstance(tgt, str) and tgt.strip():
            out[cur] = tgt.strip()
        for c in (node.get("children") or node.get("_originalChildren") or []):
            walk(c, cur)
    walk(root, ())
    return out


def _tooltip_arrow_for(tb: dict, gb: dict) -> str:
    """두 bbox(tooltip tb, target gb)로 arrow variant 결정 (pure — 테스트용).

    arrow 는 '대상이 있는 쪽'에 달려 그쪽을 가리킨다:
      target 이 tooltip 아래 → 'Bottom center', 위 → 'Top center',
      오른쪽 → 'Right', 왼쪽 → 'Left'. (상하 우선 — 말풍선 통념)
    """
    ty, th = tb.get("y", 0), tb.get("height", 0)
    gx, gy = gb.get("x", 0), gb.get("y", 0)
    gw, gh = gb.get("width", 0), gb.get("height", 0)
    tx, tw = tb.get("x", 0), tb.get("width", 0)
    if gy >= ty + th - 2:          # target 이 아래
        return "Bottom center"
    if gy + gh <= ty + 2:          # target 이 위
        return "Top center"
    if gx >= tx + tw - 2:          # target 이 오른쪽
        return "Right"
    return "Left"                  # target 이 왼쪽


def _point_tooltip_at(node: dict, parent: Optional[dict], target: dict) -> bool:
    """tooltip 의 arrow 가 target 중심을 가리키도록 Arrow variant + 위치(부모 padding) 교정.

    - target 이 tooltip 아래면 Bottom*, 위면 Top*, 우/좌면 Right/Left arrow.
    - Bottom/Top: 'X center' arrow + 부모(HORIZONTAL) paddingLeft 로 tooltip 가로중심
      = target 가로중심 정렬 → 중앙 arrow 가 정확히 대상 위/아래를 찍는다.
    - Left/Right: 부모(VERTICAL) paddingTop 으로 세로중심 정렬.
    """
    tb, gb = _tt_bbox(node), _tt_bbox(target)
    if not tb or not gb:
        return False
    tx, ty, tw, th = tb.get("x", 0), tb.get("y", 0), tb.get("width", 0), tb.get("height", 0)
    gx, gy, gw, gh = gb.get("x", 0), gb.get("y", 0), gb.get("width", 0), gb.get("height", 0)
    gcx, gcy = gx + gw / 2.0, gy + gh / 2.0
    arrow = _tooltip_arrow_for(tb, gb)
    below = arrow == "Bottom center"
    above = arrow == "Top center"
    pmode = (parent.get("layoutMode") or "").upper() if isinstance(parent, dict) else ""

    if below or above:
        try:
            call_tool("set_instance_properties", {"nodeId": node["id"], "properties": {"Arrow": arrow}})
        except Exception as e:
            print(f"  [tooltip-arrow] '{node.get('id')}' set arrow fail: {e}")
            return False
        # arrow 추가로 width 변동 가능 — 재측정
        tw2 = _tt_bbox(_get_node_min(node["id"])).get("width", tw) or tw
        if pmode == "HORIZONTAL":
            pb = _tt_bbox(parent)
            if pb:
                new_pl = int(max(0, round(gcx - pb.get("x", 0) - tw2 / 2.0)))
                _set_wrap_padding(parent, paddingLeft=new_pl)
        return True
    else:  # arrow == "Left" / "Right"
        try:
            call_tool("set_instance_properties", {"nodeId": node["id"], "properties": {"Arrow": arrow}})
        except Exception as e:
            print(f"  [tooltip-arrow] '{node.get('id')}' set arrow fail: {e}")
            return False
        if pmode == "VERTICAL":
            pb = _tt_bbox(parent)
            if pb:
                new_pt = int(max(0, round(gcy - pb.get("y", 0) - th / 2.0)))
                _set_wrap_padding(parent, paddingTop=new_pt)
        return True


def _get_node_min(node_id: str) -> dict:
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [node_id]})).get("json")
        if isinstance(items, list) and items:
            return items[0].get("document") or items[0]
    except Exception:
        pass
    return {}


def _set_wrap_padding(parent: dict, **pad) -> None:
    """부모 auto-layout wrap 의 padding 일부만 갱신 (나머지 값 보존)."""
    args = {"nodeId": parent["id"], "layoutMode": parent.get("layoutMode") or "HORIZONTAL"}
    for k in ("paddingLeft", "paddingRight", "paddingTop", "paddingBottom", "itemSpacing"):
        v = pad.get(k, parent.get(k))
        if v is not None:
            args[k] = v
    for k in ("primaryAxisAlignItems", "counterAxisAlignItems"):
        if parent.get(k):
            args[k] = parent[k]
    try:
        call_tool("set_auto_layout", args)
    except Exception as e:
        print(f"  [tooltip-arrow] wrap padding 갱신 실패: {e}")


def _enforce_tooltip_arrow_live(root_id: str, target_map: Optional[dict] = None) -> int:
    """빌드된 Tooltip 인스턴스의 arrow 가 항상 '실제 대상'을 가리키도록 강제 (2026-06-04 사용자 룰).

    사용자 명시: "일반적인 툴팁은 위아래좌우로 가리키는 arrow 가 보여야 한다 / arrow 가
    엉뚱한 버튼(북마크)이 아니라 대상(채팅)을 가리켜야 한다."

    동작 (2단):
      1. `_tooltipTarget` 마커가 있는 tooltip → target 노드를 트리에서 찾아 arrow
         방향(Bottom/Top/Left/Right center) + 부모 padding 위치를 대상 중심에 맞춘다.
      2. 마커 없는 tooltip → Arrow=None 이면 기하학 추론(_infer_tooltip_arrow)으로
         최소한 가리키는 arrow 를 보장 (idempotent backstop).

    ⚠️ get_nodes_info(복수형)만 componentProperties/absoluteBoundingBox 를 노출한다.
    """
    target_map = target_map or {}
    root = _get_node_min(root_id)
    if not root:
        print("  [tooltip-arrow] root fetch fail")
        return 0

    # 이름 → 노드 인덱스 (target 해소용)
    name_idx: dict = {}
    tooltips: list = []  # (node, parent, path)

    def walk(n, parent, chain):
        if not isinstance(n, dict):
            return
        nm = n.get("name") or ""
        cur = chain + (nm,)
        name_idx.setdefault(nm, []).append(n)
        if (n.get("type") or "").upper() == "INSTANCE":
            cp = n.get("componentProperties") or {}
            if isinstance(cp.get("Arrow"), dict):
                tooltips.append((n, parent, cur))
        for c in n.get("children", []) or []:
            walk(c, n, cur)
    walk(root, None, ())

    fixed = 0
    for node, parent, path in tooltips:
        cur_arrow = (node.get("componentProperties") or {}).get("Arrow", {}).get("value")
        target_name = target_map.get(path)
        target = None
        if target_name and name_idx.get(target_name):
            tb = _tt_bbox(node)
            tcx = tb.get("x", 0) + tb.get("width", 0) / 2.0
            tcy = tb.get("y", 0) + tb.get("height", 0) / 2.0

            def _d(cn):
                cb = _tt_bbox(cn)
                if not cb:
                    return float("inf")
                return abs(cb.get("x", 0) + cb.get("width", 0) / 2.0 - tcx) + \
                    abs(cb.get("y", 0) + cb.get("height", 0) / 2.0 - tcy)
            target = min(name_idx[target_name], key=_d)
        if target is not None:
            if _point_tooltip_at(node, parent, target):
                fixed += 1
                print(f"  [tooltip-arrow] '{node.get('id')}' → '{target_name}' 가리킴")
        elif cur_arrow in (None, "None", ""):
            arrow = _infer_tooltip_arrow(node, parent)
            try:
                call_tool("set_instance_properties", {"nodeId": node["id"], "properties": {"Arrow": arrow}})
                fixed += 1
                print(f"  [tooltip-arrow] '{node.get('id')}' Arrow None → {arrow}")
            except Exception as e:
                print(f"  [tooltip-arrow] '{node.get('id')}' fail: {e}")
    if fixed:
        print(f"  [tooltip-arrow] ✓ Tooltip {fixed}건 arrow 방향/위치 교정 (대상 정조준)")
    return fixed


def _tbp_num(v, d=0):
    return v if isinstance(v, (int, float)) else d


def _text_box_needs_padding(n: dict, min_gap: int = 6) -> bool:
    """라운드 필 박스 안 라벨+값 텍스트가 모서리에 밀착했는지 (순수 판별 — 테스트용).

    True 조건: VERTICAL FRAME + 보이는 SOLID fill + cornerRadius≥6 + 직계 TEXT≥2
    + (세로 패딩 < 12 또는 itemSpacing < min_gap). 투명 텍스트 그룹/DS 인스턴스 제외.
    """
    if not isinstance(n, dict):
        return False
    if (n.get("type") or "").upper() != "FRAME" or (n.get("layoutMode") or "") != "VERTICAL":
        return False
    fills = n.get("fills")
    has_fill = isinstance(fills, list) and any(
        isinstance(f, dict) and f.get("type") == "SOLID" and f.get("visible", True) for f in fills)
    if not has_fill or _tbp_num(n.get("cornerRadius")) < 6:
        return False
    tkids = [c for c in (n.get("children") or []) if (c.get("type") or "").upper() == "TEXT"]
    if len(tkids) < 2:
        return False
    return (_tbp_num(n.get("paddingTop")) < 12 or _tbp_num(n.get("paddingBottom")) < 12
            or _tbp_num(n.get("itemSpacing")) < min_gap)


def _collect_fixed_widths(blueprint: Optional[dict]) -> dict:
    """blueprint 에서 명시적 FIXED 폭 프레임의 {이름경로: width} 수집 (2026-06-04).

    여러 enforcer(_fix_fill_sizing/multicol-fill/batch_build)가 author 가 명시한
    `layoutSizingHorizontal:"FIXED"` + width 를 무시하고 FILL 로 늘리는 회귀가 있어
    (2-line Date Cell 56→161), 빌드 후 이 맵으로 원래 FIXED 폭을 재단언한다.
    """
    out = {}
    if not isinstance(blueprint, dict):
        return out
    root = blueprint.get("root") or blueprint

    def walk(node, chain):
        if not isinstance(node, dict):
            return
        cur = chain + (node.get("name") or "",)
        if (node.get("type") or "").lower() == "frame" \
                and (node.get("layoutSizingHorizontal") or "").upper() == "FIXED" \
                and isinstance(node.get("width"), (int, float)):
            out[cur] = node["width"]
        for c in (node.get("children") or node.get("_originalChildren") or []):
            walk(c, cur)
    walk(root, ())
    return out


def _collect_blueprint_padding(blueprint: Optional[dict]) -> dict:
    """blueprint 에서 명시 autoLayout padding 을 가진 프레임의 {이름경로: layout dict} 수집.

    여러 post-fix enforcer 가 author 의 padding 을 파괴(paddingLeft 0 회귀 등)하므로
    빌드 후 이 맵으로 원래 padding 을 재단언한다. (2026-06-04)
    """
    out = {}
    if not isinstance(blueprint, dict):
        return out
    root = blueprint.get("root") or blueprint

    def walk(node, chain):
        if not isinstance(node, dict):
            return
        cur = chain + (node.get("name") or "",)
        al = node.get("autoLayout")
        if isinstance(al, dict) and (node.get("type") or "").lower() == "frame":
            pads = {k: al[k] for k in ("paddingLeft", "paddingRight", "paddingTop", "paddingBottom")
                    if isinstance(al.get(k), (int, float))}
            if pads:
                pads["layoutMode"] = al.get("layoutMode") or "VERTICAL"
                for k in ("primaryAxisAlignItems", "counterAxisAlignItems", "itemSpacing"):
                    if al.get(k) is not None:
                        pads[k] = al[k]
                out[cur] = pads
        for cc in (node.get("children") or node.get("_originalChildren") or []):
            walk(cc, cur)
    walk(root, ())
    return out


def _enforce_blueprint_padding(root_id: str, pad_map: dict) -> int:
    """빌드 트리에서 blueprint 가 명시한 autoLayout padding 을 재단언 (2026-06-04 — 회귀 차단).

    post-fix enforcer 들이 paddingLeft 등을 0 으로 파괴한 프레임을 원래 값으로 복원.
    built 값이 None(직렬화 누락)이거나 blueprint 와 다르면 재설정. INSTANCE 는 제외.
    """
    if not pad_map:
        return 0
    fixed = [0]

    def walk(n, chain):
        if not isinstance(n, dict):
            return
        cur = chain + (n.get("name") or "",)
        if cur in pad_map and (n.get("type") or "").upper() == "FRAME":
            # ⚠️ get_nodes_info 의 padding 직렬화가 불안정(None/stale)해 '바뀐 것만' 판정이
            # 카드를 놓친다 → blueprint padding 을 **무조건 재단언**(멱등). FRAME 만(인스턴스
            # 제외)이라 호출 수도 적다.
            try:
                call_tool("set_auto_layout", dict(pad_map[cur], nodeId=n["id"]))
                fixed[0] += 1
            except Exception as e:
                print(f"  [bp-padding] '{n.get('id')}' fail: {e}")
        for cc in n.get("children", []) or []:
            walk(cc, cur)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0], ())
    except Exception as e:
        print(f"  [bp-padding] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [bp-padding] ✓ blueprint 명시 padding {fixed[0]}개 복원 (enforcer 파괴 차단)")
    return fixed[0]


def _collect_text_fill_keys(blueprint: Optional[dict]) -> set:
    """blueprint 에서 layoutSizingHorizontal=FILL 을 명시한 TEXT 의 (부모경로, 텍스트20자) 수집.

    2026-07-13 회귀 2회: HORIZONTAL 행(타이틀 FILL + 우측 아이콘)에서 build/enforcer 가
    TEXT 의 FILL 을 HUG 로 풀어 아이콘이 타이틀 옆에 붙음 (북마크 우측 정렬 파괴).
    bp-padding 과 같은 철학으로 E.7.7 에서 최종 재단언한다.
    """
    out = set()
    if not isinstance(blueprint, dict):
        return out
    root = blueprint.get("root") or blueprint

    def walk(node, chain):
        if not isinstance(node, dict):
            return
        nm = node.get("name") or ""
        cur = chain + ((nm,) if nm else ())
        if (node.get("type") or "").lower() == "text" \
                and (node.get("layoutSizingHorizontal") or "").upper() == "FILL":
            out.add((chain, (node.get("text") or "")[:20]))
        for c in (node.get("children") or node.get("_originalChildren") or []):
            walk(c, cur)
    walk(root, ())
    return out


def _enforce_text_fill_live(root_id: str, keys: set) -> int:
    """빌드 트리에서 blueprint 명시 TEXT FILL 을 재단언 (배치 1콜, 멱등)."""
    if not keys:
        return 0
    queue = []

    def walk(n, chain):
        if not isinstance(n, dict):
            return
        nm = n.get("name") or ""
        if (n.get("type") or "").upper() == "TEXT":
            key = (chain, (n.get("characters") or "")[:20])
            if key in keys and (n.get("layoutSizingHorizontal") or "").upper() != "FILL":
                queue.append({"nodeId": n["id"], "horizontal": "FILL"})
            return
        cur = chain + ((nm,) if nm else ())
        for c in n.get("children", []) or []:
            walk(c, cur)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0], ())
    except Exception as e:
        print(f"  [text-fill-final] root fetch fail: {e}")
        return 0
    n = _set_sizing_batch(queue)
    if n:
        print(f"  [text-fill-final] ✓ blueprint 명시 TEXT FILL {n}건 복원 (타이틀+우측 아이콘 행 정렬)")
    return n


def _collect_radius_clip_paths(blueprint: Optional[dict]) -> dict:
    """🔴 절대규칙 0-Q (2026-06-04): radius>0 frame 의 {이름경로: layoutMode} 수집.

    R45(post-fix + AUTO_FIX)가 시트/카드 clip 을 false 로 끄는데, get_nodes_info 가 개별
    코너 radius 를 None 으로 직렬화해 라이브 검출이 안 된다 → blueprint 의 radius 정보로
    name-path 를 모아 Step E.7.7(AUTO_FIX 이후)에서 clip=true 를 재단언한다.
    """
    out = {}
    if not isinstance(blueprint, dict):
        return out
    root = blueprint.get("root") or blueprint

    def _has_radius(n):
        cr = n.get("cornerRadius")
        if isinstance(cr, (int, float)) and cr > 0:
            return True
        for k in ("topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius"):
            v = n.get(k)
            if isinstance(v, (int, float)) and v > 0:
                return True
        return False

    def walk(node, chain):
        if not isinstance(node, dict):
            return
        cur = chain + (node.get("name") or "",)
        if (node.get("type") or "frame").lower() == "frame" and _has_radius(node) \
                and (node.get("children") or node.get("_originalChildren")):
            al = node.get("autoLayout") or {}
            out[cur] = al.get("layoutMode") or node.get("layoutMode") or "NONE"
        for c in (node.get("children") or node.get("_originalChildren") or []):
            walk(c, cur)
    walk(root, ())
    return out


def _enforce_radius_clip_live(root_id: str, clip_map: dict) -> int:
    """빌드 트리에서 radius>0 frame 의 clipsContent=true 재단언 (2026-06-04 절대규칙 0-Q).

    R45 가 clip 을 false 로 끈 뒤(get_nodes_info 가 개별 코너를 None 으로 줘서 R45 의 rounded
    예외가 시트를 놓침) Step E.7.7 에서 blueprint name-path 매칭으로 무조건 true 로 되돌린다.
    """
    if not clip_map:
        return 0
    fixed = [0]

    def walk(n, chain):
        if not isinstance(n, dict):
            return
        cur = chain + (n.get("name") or "",)
        if cur in clip_map and (n.get("type") or "").upper() == "FRAME" \
                and n.get("clipsContent") is not True:
            lm = clip_map[cur]
            if lm in (None, "NONE", ""):
                lm = n.get("layoutMode") or "VERTICAL"
            try:
                call_tool("set_auto_layout", {"nodeId": n["id"], "layoutMode": lm, "clipsContent": True})
                fixed[0] += 1
            except Exception as e:
                print(f"  [radius-clip] '{n.get('id')}' fail: {e}")
        for cc in n.get("children", []) or []:
            walk(cc, cur)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0], ())
    except Exception as e:
        print(f"  [radius-clip] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [radius-clip] ✓ radius>0 frame {fixed[0]}개 clipsContent=true 복원")
    return fixed[0]


def _enforce_fixed_widths(root_id: str, width_map: dict) -> int:
    """빌드 트리에서 blueprint 가 FIXED 로 명시한 폭을 재단언 (2026-06-04 — 회귀 차단).

    enforcer 들이 늘려놓은 FIXED-width 프레임을 원래 폭으로 되돌린다(2px 초과 차이 시).
    """
    if not width_map:
        return 0
    fixed = [0]

    def walk(n, chain):
        if not isinstance(n, dict):
            return
        cur = chain + (n.get("name") or "",)
        if cur in width_map and (n.get("type") or "").upper() in ("FRAME", "INSTANCE"):
            want = width_map[cur]
            cur_w = (n.get("absoluteBoundingBox") or {}).get("width")
            if isinstance(cur_w, (int, float)) and abs(cur_w - want) > 2:
                try:
                    call_tool("set_layout_sizing", {"nodeId": n["id"], "horizontal": "FIXED"})
                    call_tool("resize_node", {"nodeId": n["id"], "width": want,
                                              "height": (n.get("absoluteBoundingBox") or {}).get("height") or want})
                    fixed[0] += 1
                except Exception as e:
                    print(f"  [fixed-width] '{n.get('id')}' fail: {e}")
        for c in n.get("children", []) or []:
            walk(c, cur)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0], ())
    except Exception as e:
        print(f"  [fixed-width] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [fixed-width] ✓ blueprint 명시 FIXED 폭 {fixed[0]}개 복원 (FILL 늘어남 차단)")
    return fixed[0]


def _collect_keep_sizing(blueprint: Optional[dict]) -> dict:
    """blueprint 에서 `_keepSizing: true` 노드의 {이름경로: 선언 사이징} 수집 (2026-06-10).

    🔴 하네스 원칙(intent 존중): FILL 강제·vertical-hug 등 가드레일이 author 가 *명시한*
    HUG/FIXED 사이징을 망치는 회귀(선물 카드 'Giver Info' HUG→FILL 로 가격/증정자 붙음,
    축하 'One Circle' FIXED→가로 FILL 로 타원)를 막는다. 빌드 후 *모든 enforcer 뒤*(E.7.7)
    에서 이 맵으로 선언 사이징을 최종 재단언 → author 의 의도가 마지막 권한을 갖는다.

    작성법: 사이징을 보호할 노드에 `"_keepSizing": true` + 원하는 layoutSizingHorizontal/
    Vertical(+ FIXED 면 width/height) 을 명시. 양축 FIXED 면 정확 치수까지 복원된다.
    """
    out = {}
    if not isinstance(blueprint, dict):
        return out
    root = blueprint.get("root") or blueprint

    def walk(node, chain):
        if not isinstance(node, dict):
            return
        cur = chain + (node.get("name") or "",)
        if node.get("_keepSizing") is True:
            spec = {
                "h": (node.get("layoutSizingHorizontal") or "").upper() or None,
                "v": (node.get("layoutSizingVertical") or "").upper() or None,
            }
            if isinstance(node.get("width"), (int, float)):
                spec["w"] = node["width"]
            if isinstance(node.get("height"), (int, float)):
                spec["ht"] = node["height"]
            out[cur] = spec
        for c in (node.get("children") or node.get("_originalChildren") or []):
            walk(c, cur)
    walk(root, ())
    return out


def _enforce_keep_sizing_live(root_id: str, keep_map: dict) -> int:
    """`_keepSizing` 노드의 선언 사이징(H/V + 양축 FIXED 정확 치수)을 최종 재단언 (2026-06-10).

    어느 enforcer 가 FILL/HUG 로 바꿔놨든 author 선언으로 되돌린다. E.7.7(AUTO_FIX 이후)에서
    호출해 최종 권한을 갖게 한다. DS INSTANCE 내부(';' 노드)는 색·사이즈 보호(규칙 0-K)로 제외.
    """
    if not keep_map:
        return 0
    fixed = [0]

    def walk(n, chain):
        if not isinstance(n, dict):
            return
        cur = chain + (n.get("name") or "",)
        nid = n.get("id")
        if (cur in keep_map and nid and ";" not in str(nid)
                and (n.get("type") or "").upper() in ("FRAME", "INSTANCE", "COMPONENT")):
            spec = keep_map[cur]
            bb = n.get("absoluteBoundingBox") or {}
            try:
                sizing = {}
                if spec.get("h"):
                    sizing["horizontal"] = spec["h"]
                if spec.get("v"):
                    sizing["vertical"] = spec["v"]
                if sizing:
                    sizing["nodeId"] = nid
                    call_tool("set_layout_sizing", sizing)
                # 양축 FIXED + 치수 명시면 정확 치수까지 재단언(타원/찌부 차단). 2px 초과 차이만.
                if spec.get("h") == "FIXED" and spec.get("v") == "FIXED" \
                        and isinstance(spec.get("w"), (int, float)) and isinstance(spec.get("ht"), (int, float)):
                    cw, ch = bb.get("width"), bb.get("height")
                    if (not isinstance(cw, (int, float)) or abs(cw - spec["w"]) > 2
                            or not isinstance(ch, (int, float)) or abs(ch - spec["ht"]) > 2):
                        call_tool("resize_node", {"nodeId": nid, "width": spec["w"], "height": spec["ht"]})
                fixed[0] += 1
            except Exception as e:
                print(f"  [keep-sizing] '{nid}' fail: {e}")
        for c in n.get("children", []) or []:
            walk(c, cur)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0], ())
    except Exception as e:
        print(f"  [keep-sizing] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [keep-sizing] ✓ _keepSizing 노드 {fixed[0]}개 선언 사이징 최종 재단언 (intent 존중)")
    return fixed[0]


def _enforce_text_box_padding_live(root_id: str, min_pad: int = 14, min_gap: int = 6) -> int:
    """라운드 필 박스 안 텍스트(라벨+값)가 상하 모서리에 붙는 것 차단 (2026-06-04 사용자 룰).

    사용자 명시: "프레임 안 텍스트가 위아래로 딱 붙어있으면 안 된다." — batch_build_screen
    이 HORIZONTAL row 안 FILL 박스의 세로 패딩을 0 으로 떨어뜨리는 경우가 있어(stat 박스
    '완료한 스테이지/3,000개' 가 패딩 0 → 텍스트가 박스 위/아래 모서리에 붙음) 라이브 교정.

    대상: VERTICAL auto-layout FRAME 중 (1) 보이는 SOLID fill (2) cornerRadius ≥ 6
    (= 시각적 '박스/칩') (3) 직계 TEXT 자식 ≥ 2 (라벨+값) 인데 세로 패딩 < 12 또는
    itemSpacing < min_gap → paddingTop/Bottom = max(현재, min_pad), itemSpacing = max(현재, min_gap).
    투명 텍스트 그룹(fill 없음/cornerRadius 0)·DS 인스턴스 내부는 제외. idempotent.

    ⚠️ get_nodes_info 가 padding 을 None(=0/직렬화 누락)으로 줄 수 있어, 박스류는 좌우도
    min_pad 로 정규화한다(작은 info 박스 표준 = 14).
    """
    fixed = [0]

    def walk(n):
        if not isinstance(n, dict):
            return
        if _text_box_needs_padding(n, min_gap):
            pt, pb = _tbp_num(n.get("paddingTop")), _tbp_num(n.get("paddingBottom"))
            isp = _tbp_num(n.get("itemSpacing"))
            pl = _tbp_num(n.get("paddingLeft"), min_pad) or min_pad
            pr = _tbp_num(n.get("paddingRight"), min_pad) or min_pad
            args = {"nodeId": n["id"], "layoutMode": "VERTICAL",
                    "paddingTop": max(pt, min_pad), "paddingBottom": max(pb, min_pad),
                    "paddingLeft": pl, "paddingRight": pr,
                    "itemSpacing": max(isp, min_gap)}
            if n.get("counterAxisAlignItems"):
                args["counterAxisAlignItems"] = n["counterAxisAlignItems"]
            try:
                call_tool("set_auto_layout", args)
                fixed[0] += 1
            except Exception as e:
                print(f"  [text-box-pad] '{n.get('id')}' fail: {e}")
        for c in n.get("children", []) or []:
            walk(c)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [text-box-pad] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [text-box-pad] ✓ 텍스트 박스 {fixed[0]}개 상하 여백 복원 (모서리 밀착 차단)")
    return fixed[0]


def _enforce_multicol_fill_live(root_id: str) -> int:
    """2-col(N-col) FILL 붕괴 자동 복구 (2026-06-04 사용자 룰 — 재발 방지).

    HORIZONTAL auto-layout 부모에서 FILL 컬럼이 1px 로 붕괴하고 형제가 전폭(FIXED)을
    차지하는 batch_build_screen 버그([[two-col-fill-card-collapse]])를 라이브에서 교정.
    붕괴 신호(직계 frame/instance 자식 중 width ≤ 3px)가 보이면, 작은 고정 요소
    (아이콘/버튼 ≤56px FIXED)를 제외한 모든 '컬럼' 자식을 layoutSizingHorizontal=FILL
    로 재설정해 균등 분배를 복원한다. 붕괴가 없으면 no-op (idempotent).

    ⚠️ get_nodes_info(복수형)만 absoluteBoundingBox/layoutMode/layoutSizingHorizontal 노출.
    """
    def _w(n):
        b = n.get("absoluteBoundingBox") or {}
        return b.get("width")

    def _is_fixed_small(c):
        # 작은 고정 요소(아이콘/날짜셀/버튼 박스 등)는 **폭으로** 판별 — get_nodes_info 의
        # layoutSizingHorizontal 직렬화가 불안정(None)이라 플래그에 의존하면 56px 날짜셀이
        # 컬럼으로 오인돼 FILL 로 늘어남(2026-06-04 회귀). 4~64px = 컬럼 아님 → FILL 제외.
        w = _w(c)
        return isinstance(w, (int, float)) and 3 < w <= 64

    fixed = [0]

    def walk(n):
        if not isinstance(n, dict):
            return
        # DS 컴포넌트 내부(INSTANCE 자식)는 건드리지 않음 — FRAME 부모만 처리
        if (n.get("type") or "").upper() == "FRAME" and (n.get("layoutMode") or "").upper() == "HORIZONTAL":
            kids = [c for c in (n.get("children") or [])
                    if (c.get("type") or "").upper() in ("FRAME", "INSTANCE")]
            collapsed = [c for c in kids
                         if isinstance(_w(c), (int, float)) and 0 < _w(c) <= 3]
            to_fill = {}  # id -> node (dedup)
            if collapsed and len(kids) >= 2:
                for c in kids:
                    if not _is_fixed_small(c):
                        to_fill[c["id"]] = c
            # ⚠️ 둥근 '타일/카드' 컬럼 불균형 (2026-06-05 재발방지): batch_build 가 한 타일만
            # 전폭, 형제를 ~20px 로 찌부러뜨리는 2-col 붕괴는 ≤3px 가드를 비껴간다([[two-col-fill-card-collapse]]).
            # cornerRadius 4~60(둥근 타일, 원형 999/아이콘 제외) + children 보유 + 같은 HORIZONTAL
            # 부모의 그런 타일이 2개+ 인데 폭이 2.5배 넘게 불균형이면 전부 FILL 로 균등 복원.
            tiles = [c for c in kids
                     if (c.get("type") or "").upper() == "FRAME" and c.get("children")
                     and isinstance(c.get("cornerRadius"), (int, float)) and 4 <= c["cornerRadius"] <= 60
                     and isinstance(_w(c), (int, float))]
            if len(tiles) >= 2:
                tw = [_w(c) for c in tiles]
                if min(tw) > 0 and max(tw) > 2.5 * min(tw):
                    for c in tiles:
                        to_fill[c["id"]] = c
            for c in to_fill.values():
                queue[c["id"]] = {"nodeId": c["id"], "horizontal": "FILL"}
        for c in n.get("children", []) or []:
            walk(c)

    queue: Dict[str, dict] = {}  # 2026-07-13 — 개별 호출 대신 배치 (dedup by nodeId)
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [multicol-fill] root fetch fail: {e}")
    fixed[0] = _set_sizing_batch(list(queue.values()))
    if fixed[0]:
        print(f"  [multicol-fill] ✓ 붕괴 컬럼 {fixed[0]}개 FILL 복원 (2-col collapse 차단)")
    return fixed[0]


def _fix_collapsed_text_width_live(root_id: str) -> int:
    """긴 텍스트가 좁은 컨테이너에 갇혀 *글자단위로 줄바꿈*되는 붕괴를 라이브 교정 (2026-06-18 사용자 QA).

    회귀: 카드 타이틀 '27년 6월 25일에 7,000,000원 받아요.' 가 폭 22px 컨테이너(Quote Texts)에
    갇혀 한 글자씩 세로로 쌓임. 생성기는 FILL 을 설정했지만 batch_build 가 떨어뜨리고
    `_enforce_multicol_fill_live`(≤3px 가드)도 22px 를 비껴감 → 별도 가드.

    감지: TEXT 의 폭이 fontSize*4 미만(=한 줄에 4글자도 못 들어감)인데 글자수>6(긴 텍스트) →
    컨테이너 폭 붕괴. 복원: 그 TEXT + 붕괴한 조상 프레임(폭<80px)들을 layoutSizingHorizontal=FILL.
    DS 인스턴스 내부(';')·장식 텍스트 제외. idempotent.
    """
    fixed = [0]

    def _w(n):
        b = n.get("absoluteBoundingBox") or {}
        return b.get("width") or 0

    def walk(n, parents):
        if not isinstance(n, dict):
            return
        if (n.get("type") or "").upper() == "TEXT":
            chars = (n.get("characters") or "").strip()
            w = _w(n)
            style = n.get("style") or {}
            fs = style.get("fontSize") or n.get("fontSize") or 14
            if len(chars) > 6 and 0 < w < fs * 4 and ";" not in (n.get("id") or ""):
                # 붕괴한 TEXT + 좁은(<80px) 조상 프레임들을 FILL 로 복원 (넓은 부모 만나면 중단)
                targets = [n]
                for p in reversed(parents):
                    if (p.get("type") or "").upper() == "FRAME" and 0 < _w(p) < 80 \
                            and ";" not in (p.get("id") or ""):
                        targets.append(p)
                    else:
                        break
                for t in targets:
                    try:
                        call_tool("set_layout_sizing", {"nodeId": t["id"], "horizontal": "FILL"})
                        fixed[0] += 1
                    except Exception as e:
                        print(f"  [collapsed-text] '{t.get('id')}' fail: {e}")
                print(f"  [collapsed-text] ✓ 붕괴 텍스트 복원 \"{chars[:18]}\" (폭 {round(w)}px → FILL)")
        for c in n.get("children", []) or []:
            walk(c, parents + [n])

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0], [])
    except Exception as e:
        print(f"  [collapsed-text] root fetch fail: {e}")
    if fixed[0]:
        print(f"  [collapsed-text] ✓ 폭 붕괴 텍스트/컨테이너 {fixed[0]}개 FILL 복원")
    return fixed[0]


def _enforce_ds_instance_text(root_id: str, path_text_map: dict) -> int:
    """빌드 트리 DS instance 의 내부 첫 TEXT 를 원래 콘텐츠로 override (2026-05-28).

    R23 swap 후 마스터 더미('Label'/'Button CTA'/'Click to Download')가 남는 회귀 차단.
    blueprint 경로(이름 chain) 매칭으로 status-pill 4개처럼 같은 이름도 부모로 구분.
    """
    if not path_text_map:
        return 0
    fixed = [0]

    def walk(node, chain):
        if not isinstance(node, dict):
            return
        nm = node.get("name") or ""
        cur = chain + (nm,)
        if (node.get("type") or "").upper() == "INSTANCE" and cur in path_text_map:
            try:
                scan = parse_content(call_tool("scan_text_nodes", {"nodeId": node["id"]})).get("json") or {}
                tnodes = scan.get("textNodes") or []
                if tnodes:
                    call_tool("set_text_content", {"nodeId": tnodes[0]["id"], "text": path_text_map[cur]})
                    fixed[0] += 1
            except Exception as e:
                print(f"  [ds-instance-text] '{node.get('id')}' fail: {e}")
        for c in node.get("children", []) or []:
            walk(c, cur)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0], ())
    except Exception as e:
        print(f"  [ds-instance-text] root fetch fail: {e}")
    return fixed[0]


def _collect_mode_tabs_config(blueprint: Optional[dict]) -> Optional[dict]:
    """blueprint 에서 _dsModeTabs 마커 {labels, active} 수집 (Mode Tabs Wrap 에 부착)."""
    found = [None]

    def walk(n):
        if found[0] is not None or not isinstance(n, dict):
            return
        cfg = n.get("_dsModeTabs")
        if isinstance(cfg, dict):
            found[0] = cfg
            return
        for c in n.get("children") or []:
            walk(c)

    walk(blueprint)
    return found[0]


def _collect_tool_bar_configs(blueprint: dict) -> List[dict]:
    """blueprint 에서 DS Tool Bar 인스턴스 설정 수집 (절대 규칙 0-W, 2026-06-12).

    R64 inject(또는 hand-author)가 만든 Tool Bar 인스턴스 노드의 `_navTitle`(서브 화면
    중앙 타이틀) 마커를 모은다. componentKey 가 Tool Bar 셋("SET:c9299ef0…")이거나
    `_navTitle` 이 있는 instance 노드가 대상."""
    out: List[dict] = []

    def walk(n):
        if not isinstance(n, dict):
            return
        key = str(n.get("componentKey") or "")
        if (n.get("type") or "").lower() == "instance" and (
                key.startswith("SET:c9299ef0c3c7cc271850a048025a3c8d0e82b230")
                or n.get("_navTitle") or n.get("_navIcons") is not None):
            # icons: None = 마커 없음(마스터 기본 유지) / [] = 명시적 empty / [..] = swap 대상
            out.append({"name": n.get("name"), "title": n.get("_navTitle"),
                        "icons": n.get("_navIcons"),
                        "modal": bool(n.get("_navModal"))})
            return
        for c in n.get("children") or []:
            walk(c)

    walk(blueprint)
    return out


# Right Buttons variant 값 (2026-06-12 사용자: "없으면 empty, 하나면 1 button, 둘이면 2 button")
_TOOLBAR_RIGHT_TYPE = {0: "empty", 1: "1 button", 2: "2 button"}
# 구버전 DS variant 이름 폴백 (DS 업데이트 전 게시본 캐시 대응)
_TOOLBAR_RIGHT_TYPE_LEGACY = {1: "1 Symbol", 2: "2 Symbol"}


def _swap_tool_bar_icons(toolbar_id: str, icons: List[str]) -> int:
    """DS Tool Bar 인스턴스 우측 버튼 설정 + 중첩 아이콘 swap (절대 규칙 0-W).

    구조: Tool Bar → 'Right Buttons'(_button top sets) → 'button N' FRAME →
    '_button N_type' INSTANCE → 아이콘 INSTANCE.
    🔴 우측 버튼 개수 = Right Buttons 의 `Type` variant (2026-06-12 사용자 룰):
      0개(icons=[]) → "empty" / 1개 → "1 button" / 2개 → "2 button" (최대 2).
    flip 후 각 버튼의 중첩 아이콘 인스턴스를 `swap_instance_component`(plugin) 로
    NAV_ICON_KEYS 키로 교체. 맵에 없는 아이콘은 skip + WARN (마스터 기본 유지)."""
    import sys as _sys
    _scripts_dir = os.path.dirname(os.path.abspath(__file__))
    if _scripts_dir not in _sys.path:
        _sys.path.insert(0, _scripts_dir)
    from design_rules.ds_catalog import resolve_nav_icon_key  # noqa: E402

    icons = [str(i) for i in icons if i]
    if len(icons) > 2:
        print(f"  ⚠️ [tool-bar] 우측 버튼은 최대 2개 — {len(icons)}개 중 앞 2개만 사용")
        icons = icons[:2]

    def _subtree():
        try:
            c = call_tool("get_nodes_info", {"nodeIds": [toolbar_id]})
            items = parse_content(c).get("json")
            return items[0].get("document") if isinstance(items, list) and items else None
        except Exception as e:
            print(f"  [tool-bar] 서브트리 수집 실패: {e}")
            return None

    def _button_children(kids):
        """Right Buttons 직계의 버튼 노드 — 구버전: 'button N' FRAME / 신버전(2026-06-12
        DS 업데이트): '_button_type' INSTANCE (frame 래퍼 없이 바로)."""
        out = []
        for k in kids or []:
            nm = (k.get("name") or "").lower()
            t = (k.get("type") or "").upper()
            if t == "FRAME" and nm.startswith("button"):
                out.append(k)
            elif t == "INSTANCE" and "_button" in nm and "type" in nm:
                out.append(k)
        return out

    def _find_right_buttons(node):
        """Right Buttons (_button top sets) 인스턴스 — 이름 매칭 우선(empty 상태 포함),
        폴백으로 버튼 자식 구조 매칭."""
        if not isinstance(node, dict):
            return None
        if (node.get("type") or "").upper() == "INSTANCE":
            nm = (node.get("name") or "").lower()
            if "back" not in nm and "logo" not in nm:
                if "right buttons" in nm or "button top sets" in nm:
                    return node
                if _button_children(node.get("children")):
                    return node
        for ch in node.get("children") or []:
            r = _find_right_buttons(ch)
            if r is not None:
                return r
        return None

    tree = _subtree()
    if not tree:
        return 0
    rb = _find_right_buttons(tree)
    if not rb:
        if not icons:
            print("  [tool-bar] Right Buttons 이미 empty (버튼 없음) — OK")
            return 1
        print("  [tool-bar] Right Buttons 인스턴스 없음 — 아이콘 swap skip")
        return 0

    def _flip_right_type(rb_id: str, count: int) -> bool:
        """Type variant flip — 새 이름(empty/N button) 우선, 구 이름(N Symbol) 폴백.
        set_instance_properties 응답의 적용된 Type 값으로 성공 여부 검증."""
        candidates = [_TOOLBAR_RIGHT_TYPE[count]]
        if count in _TOOLBAR_RIGHT_TYPE_LEGACY:
            candidates.append(_TOOLBAR_RIGHT_TYPE_LEGACY[count])
        for val in candidates:
            try:
                res = parse_content(call_tool("set_instance_properties", {
                    "nodeId": rb_id, "properties": {"Type": val}})).get("json") or {}
                applied = ((res.get("properties") or {}).get("Type") or {}).get("value")
                if applied == val:
                    print(f"  [tool-bar] Right Buttons → Type={val}")
                    return True
            except Exception as e:
                print(f"  [tool-bar] Type={val} flip 실패: {e}")
        print(f"  ⚠️ [tool-bar] Right Buttons Type flip 실패 (count={count}) — variant 이름 확인 필요")
        return False

    # 1) 아이콘 개수에 맞춰 Type variant flip (empty / 1 button / 2 button) — flip 후
    #    내부 id 가 바뀌므로 재수집
    cur_btns = _button_children(rb.get("children"))
    if len(icons) != len(cur_btns):
        if _flip_right_type(rb["id"], len(icons)):
            if not icons:
                return 1  # empty — swap 할 아이콘 없음, 완료
            tree = _subtree()
            rb = _find_right_buttons(tree) if tree else None
            if not rb:
                return 0
        elif not icons:
            return 0
    elif not icons:
        return 1  # 이미 0개

    # 2) 버튼 순서대로 중첩 아이콘 인스턴스 찾기 → swap
    def _btn_no(n):
        nm = (n.get("name") or "")
        digits = "".join(ch for ch in nm if ch.isdigit())
        return int(digits) if digits else 0

    def _find_icon_instance(btn):
        """버튼 노드 → 아이콘 INSTANCE. 신버전: btn 자체가 '_button_type' INSTANCE →
        첫 INSTANCE 자식이 아이콘. 구버전: 'button N' FRAME → '_button type' INSTANCE →
        첫 INSTANCE 자식."""
        if (btn.get("type") or "").upper() == "INSTANCE":
            for g in btn.get("children") or []:
                if (g.get("type") or "").upper() == "INSTANCE":
                    return g
            return btn  # 아이콘이 바로 박힌 변형 폴백
        for ch in btn.get("children") or []:
            if (ch.get("type") or "").upper() == "INSTANCE":
                for g in ch.get("children") or []:
                    if (g.get("type") or "").upper() == "INSTANCE":
                        return g
                return ch
        return None

    btns = sorted(_button_children(rb.get("children")), key=_btn_no)
    done = 0
    for i, icon_name in enumerate(icons):
        if i >= len(btns):
            break
        key = resolve_nav_icon_key(icon_name)
        if not key:
            print(f"  ⚠️ [tool-bar] 아이콘 '{icon_name}' NAV_ICON_KEYS 에 없음 — swap skip "
                  f"(ds_catalog.NAV_ICON_KEYS 에 키 추가 필요)")
            continue
        target = _find_icon_instance(btns[i])
        if not target:
            print(f"  ⚠️ [tool-bar] button {i+1} 내부 아이콘 인스턴스 못 찾음 — skip")
            continue
        try:
            call_tool("swap_instance_component", {"nodeId": target["id"], "componentKey": key})
            print(f"  [tool-bar] ✓ 우측 버튼 {i+1} 아이콘 → {icon_name}")
            done += 1
        except Exception as e:
            print(f"  ⚠️ [tool-bar] 아이콘 swap 실패 ({icon_name}): {e}")
    return done


def _configure_tool_bar(root_id: str, configs: List[dict]) -> int:
    """빌드된 DS 'Tool Bar' 인스턴스의 중앙 타이틀 적용 (절대 규칙 0-W, 2026-06-12).

    Detail view variant 의 타이틀 TEXT 는 인스턴스 내부 노드(`I{id};{sub}`)라
    scan_text_nodes 로 찾아 set_text_content 한다 (seg-tabs 와 동일 패턴).
    Tool Bar 내부 TEXT 는 타이틀 1개뿐이라 첫 TEXT 에 적용.
    `_navIcons` 마커가 있으면 우측 버튼 개수(Type=empty/1 button/2 button) 설정 +
    중첩 아이콘 인스턴스 swap (`_swap_tool_bar_icons`). `_navIcons: []` = 명시적 empty."""
    todo = [c for c in configs if c.get("title") or c.get("icons") is not None or c.get("modal")]
    if not todo:
        return 0
    try:
        tree = _collect_tree(root_id)
    except Exception as e:
        print(f"  [tool-bar] tree 수집 실패: {e}")
        return 0

    # name → built instance id 매핑 (이름 일치 우선, 폴백 'Tool Bar')
    instances: List[dict] = []

    def find(n):
        if not isinstance(n, dict):
            return
        nm = (n.get("name") or "").lower()
        if (n.get("type") or "").upper() == "INSTANCE" and (
                any(h in nm for h in _NAVBAR_NAME_HINTS) or "tool bar" in nm):
            instances.append(n)
            return
        for c in n.get("_children_full") or []:
            find(c)

    find(tree)
    done = 0
    for cfg in todo:
        inst = next((i for i in instances if i.get("name") == cfg.get("name")), None) \
            or (instances[0] if instances else None)
        if not inst:
            print(f"  [tool-bar] '{cfg.get('name')}' 인스턴스 없음 — skip")
            continue
        iid = inst.get("id")
        if cfg.get("modal"):
            # 🔴 2026-08-04 사용자 룰 ("X 헤더도 Tool Bar 인스턴스"): View=modal variant flip
            # + Back/Num(및 타이틀 없으면 Title) BOOLEAN off. x-close 는 _navIcons 로 처리.
            try:
                call_tool("set_instance_properties", {"nodeId": iid, "properties": {"View": "modal"}})
                _props = parse_content(call_tool("get_instance_properties", {"nodeId": iid})).get("json") or {}
                _pd = _props.get("properties") or {}
                _bools = {}
                for _pn, _pi in _pd.items():
                    _pl = _pn.lower()
                    if isinstance(_pi, dict) and _pi.get("type") == "BOOLEAN" and _pi.get("value"):
                        if "back" in _pl or "num" in _pl or ("title" in _pl and not cfg.get("title")):
                            _bools[_pn] = False
                if _bools:
                    call_tool("set_instance_properties", {"nodeId": iid, "properties": _bools})
                print(f"  [tool-bar] ✓ View=modal (X 헤더) + off {list(_bools.keys())}")
            except Exception as e:
                print(f"  [tool-bar] modal 구성 실패(무시): {e}")
        if cfg.get("title"):
            # 🔴 2026-07-03 실측: SET:…:Type=Detail view 키로 import 하면 batch_build 가 항상
            # 기본 **Home** variant(로고+우측 채팅)로 떨어진다(variant 미적용). title 이 있으면
            # 서브(Detail) 화면이므로 View variant 를 flip 해야 back+타이틀이 나온다.
            # ⚠️ variant 값은 'Detail view' 가 아니라 **'Detail'** (라이브 실측). flip 후에야
            # 타이틀 TEXT 노드가 생긴다(flip 전 scan_text_nodes=[]). modal 이면 flip 생략.
            for _vv in (() if cfg.get("modal") else ("Detail", "Detail view")):
                try:
                    _r = call_tool("set_instance_properties",
                                   {"nodeId": iid, "properties": {"View": _vv}})
                    _txt = (_r[0].get("text", "") if isinstance(_r, list) and _r else "")
                    if "Error" not in _txt:
                        print(f"  [tool-bar] ✓ View variant → {_vv} (Home→Detail flip)")
                        break
                except Exception:
                    pass
            try:
                text_nodes = []
                for x in call_tool("scan_text_nodes", {"nodeId": iid}):
                    if x.get("type") == "text":
                        d = json.loads(x["text"])
                        text_nodes.extend(d.get("textNodes", []))
                if not text_nodes:
                    print(f"  [tool-bar] '{cfg.get('name')}' 내부 타이틀 TEXT 없음 — skip")
                else:
                    call_tool("set_text_content", {"nodeId": text_nodes[0].get("id"),
                                                   "text": str(cfg["title"])})
                    print(f"  [tool-bar] ✓ '{cfg.get('name')}' 타이틀 → '{cfg['title']}'")
                    # 🔴 2026-08-06 사용자 회귀 보고 ("tool bar title 이 16px — DS 는 20px"):
                    # 파일에 import 캐시된 Tool Bar 마스터가 구버전(타이틀 16 Body md)일 수 있어
                    # 타이틀에 DS 정본 Body xl/Semibold(20px) 를 항상 재단언한다. 근본 해결은
                    # Figma 라이브러리 업데이트 수락(수동)이며 이 백스톱은 그 전까지의 방어선.
                    try:
                        _sm = _load_text_style_map()
                        _xl = _sm.get((20, "semibold"))
                        if _xl:
                            call_tool("set_text_style_id",
                                      {"nodeId": text_nodes[0].get("id"),
                                       "textStyleId": f"S:{_xl},{iid}"})
                            print("  [tool-bar] ✓ 타이틀 Body xl/Semibold(20px) 재단언")
                    except Exception:
                        pass
                    done += 1
                    # 🔴 2026-07-14: Detail 마스터의 잔여 카운트 TEXT('num'='5' 등)가 타이틀
                    # 옆에 그대로 노출되던 회귀 — 타이틀 외 짧은 텍스트는 비운다.
                    for tn in text_nodes[1:]:
                        raw = (tn.get("characters") or tn.get("name") or "")
                        if len(str(raw).strip()) <= 6:
                            try:
                                call_tool("set_text_content", {"nodeId": tn.get("id"), "text": ""})
                                print(f"  [tool-bar] ✓ 잔여 카운트 TEXT('{raw}') 제거")
                            except Exception:
                                pass
            except Exception as e:
                print(f"  [tool-bar] 타이틀 적용 실패(무시): {e}")
        if cfg.get("icons") is not None:
            try:
                done += _swap_tool_bar_icons(iid, cfg["icons"])
            except Exception as e:
                print(f"  [tool-bar] 아이콘 swap 실패(무시): {e}")
    return done


def _collect_seg_tabs_config(blueprint: dict) -> Optional[dict]:
    """blueprint 에서 _segLabels 마커 {name, labels, active} 수집 (Segmented_control)."""
    found = [None]

    def walk(n):
        if found[0] is not None or not isinstance(n, dict):
            return
        seg = n.get("_segLabels")
        if isinstance(seg, list) and seg:
            found[0] = {"name": n.get("name"), "labels": seg,
                        "active": n.get("_segActive", 0)}
            return
        for c in n.get("children") or []:
            walk(c)

    walk(blueprint)
    return found[0]


def _enforce_segmented_size_md_live(root_id: str) -> int:
    """절대규칙 0-P (2026-06-04): 모든 Segmented_control 인스턴스의 Size 를 md 로 강제.

    `_segLabels` 마커가 없어 `_configure_segmented_control` 이 안 도는 hand-author 인스턴스도
    md 가 되도록, 라이브 트리를 직접 walk 해 Segmented_control 인스턴스를 찾아 Size=md 설정.
    특수 size 가 필요하면 `_configure_segmented_control`(이 함수 *뒤* 실행, config.size)가 덮어쓴다.
    감지: INSTANCE 이고 (이름에 'segmented' 포함 또는 componentProperties 에 'Show Segment' 키 존재).
    """
    n_fixed = [0]

    def _is_seg(n):
        if (n.get("type") or "").upper() != "INSTANCE":
            return False
        nm = (n.get("name") or "").lower()
        if "segmented" in nm:
            return True
        cp = n.get("componentProperties") or {}
        return any(str(k).startswith("Show Segment") for k in cp.keys())

    def walk(n):
        if not isinstance(n, dict):
            return
        if _is_seg(n):
            cp = n.get("componentProperties") or {}
            cur = None
            for k, v in cp.items():
                if str(k).split("#")[0] == "Size" and isinstance(v, dict):
                    cur = v.get("value")
            if cur != "md":
                try:
                    call_tool("set_instance_properties", {"nodeId": n["id"], "properties": {"Size": "md"}})
                    n_fixed[0] += 1
                except Exception as e:
                    print(f"  [seg-size] Size=md 설정 실패(무시): {e}")
        for c in (n.get("_children_full") or n.get("children") or []):
            walk(c)

    try:
        walk(_collect_tree(root_id))
    except Exception as e:
        print(f"  [seg-size] 트리 수집 실패(무시): {e}")
    if n_fixed[0]:
        print(f"  [seg-size] ✓ Segmented_control Size=md 강제 ({n_fixed[0]}건)")
    return n_fixed[0]


def _configure_segmented_control(root_id: str, config: Optional[dict]) -> int:
    """Imin DS Segmented_control 인스턴스를 N개 세그먼트 + 라벨 + 선택으로 설정 (2026-06-02).

    🔴 prop 기반 (사용자 룰): 세그먼트 라벨/선택을 nested 텍스트 노드 id 가 아니라
    세그먼트 인스턴스의 **컴포넌트 prop** (`Label#…` TEXT, `Active` on/off) 으로 설정한다.
    텍스트노드 deepest-id 는 variant 마다 달라 깨지지만, prop 키는 안정적이라 견고하다.
    - 세그먼트 개수: `Show Segment {n}#16713:{n-3}` (n=3..8) 불리언으로 제어
    - 라벨: 각 세그먼트 인스턴스의 `Label#…` prop
    - 선택: 각 세그먼트 인스턴스의 `Active` = on/off
    """
    if not config:
        return 0
    labels = config.get("labels") or []
    active = config.get("active", 0)
    name = config.get("name")
    if not labels:
        return 0
    try:
        tree = _collect_tree(root_id)
    except Exception as e:
        print(f"  [seg-tabs] tree 수집 실패: {e}")
        return 0

    # Segmented_control 인스턴스 찾기 (마커 노드 이름 우선, 없으면 'Segmented_control')
    inst = [None]

    def find(n):
        if inst[0] or not isinstance(n, dict):
            return
        nm = n.get("name")
        if (n.get("type") or "").upper() == "INSTANCE" and (
                nm == name or nm == "Segmented_control"):
            inst[0] = n.get("id")
            return
        for c in n.get("_children_full") or []:
            find(c)

    find(tree)
    if not inst[0]:
        print("  [seg-tabs] Segmented_control 인스턴스 없음 — skip")
        return 0
    iid = inst[0]
    # 🔴 절대 규칙 (2026-06-04 사용자): Segmented_control 의 Size 는 특수상황 아니면 md 고정.
    # config.size 로 override 가능(특수 케이스), 기본 md.
    try:
        call_tool("set_instance_properties", {"nodeId": iid, "properties": {"Size": config.get("size", "md")}})
    except Exception as e:
        print(f"  [seg-tabs] Size 설정 실패(무시): {e}")
    # 세그먼트 개수: 3~8 표시 여부
    show = {}
    for seg_n in range(3, 9):
        show[f"Show Segment {seg_n}#16713:{seg_n - 3}"] = (seg_n <= len(labels))
    try:
        call_tool("set_instance_properties", {"nodeId": iid, "properties": show})
    except Exception as e:
        print(f"  [seg-tabs] Show Segment 설정 실패: {e}")

    # 세그먼트 인스턴스 id (순서 보존) — 텍스트 노드 스캔으로 파악
    segids = []
    try:
        for x in call_tool("scan_text_nodes", {"nodeId": iid}):
            if x.get("type") == "text":
                d = json.loads(x["text"])
                for tn in d.get("textNodes", []):
                    parts = (tn.get("id") or "").split(";")
                    if len(parts) >= 2:
                        seg = parts[0] + ";" + parts[1]
                        if seg not in segids:
                            segids.append(seg)
    except Exception as e:
        print(f"  [seg-tabs] 세그먼트 스캔 실패: {e}")
        return 0

    done = 0
    for i, seg in enumerate(segids[:len(labels)]):
        try:
            props = parse_content(call_tool("get_instance_properties",
                                            {"nodeId": seg})).get("json", {}).get("properties", {})
            lblkey = next((k for k in props if k.startswith("Label")), None)
            new = {"Active": "on" if i == active else "off"}
            if lblkey:
                new[lblkey] = labels[i]
            call_tool("set_instance_properties", {"nodeId": seg, "properties": new})
            done += 1
        except Exception as e:
            print(f"  [seg-tabs] 세그먼트 {i} 설정 실패: {e}")
    print(f"  [seg-tabs] Segmented_control 설정 완료 — {done}/{len(labels)} 세그먼트 "
          f"(라벨 prop + Active, active={active})")
    return done


def _configure_ds_mode_tabs(root_id: str, config: Optional[dict]) -> int:
    """DS "Horizontal tabs" 컨테이너 인스턴스를 N개 탭으로 trim + 라벨 설정 (2026-05-29).

    컨테이너는 탭 10개 고정 → 앞 N개만 라벨 set + 보이게, 나머지/badge 는 set_node_visible
    (plugin 신규 도구) 로 숨김, 인스턴스는 HUG 로 축소. active 탭은 Current=True.
    plugin 에 set_node_visible 추가 후 full 자동화 (이전엔 use_figma 수동 단계 필요).
    [[ds-mode-tabs-component]] 참조.
    """
    if not config:
        return 0
    labels = config.get("labels") or []
    active = config.get("active", 0)
    if not labels:
        return 0
    try:
        tree = _collect_tree(root_id)
    except Exception as e:
        print(f"  [mode-tabs] tree 수집 실패: {e}")
        return 0

    inst = [None]

    def find_inst(n):
        if inst[0] is not None or not isinstance(n, dict):
            return
        if n.get("name") == "Mode Tabs" and (n.get("type") or "").upper() == "INSTANCE":
            inst[0] = n
            return
        for c in n.get("_children_full") or []:
            find_inst(c)

    find_inst(tree)
    if inst[0] is None:
        print("  [mode-tabs] 'Mode Tabs' 인스턴스 없음 — skip")
        return 0

    def find_named(n, name):
        if not isinstance(n, dict):
            return None
        if n.get("name") == name:
            return n
        for c in n.get("_children_full") or []:
            r = find_named(c, name)
            if r:
                return r
        return None

    def direct_child(n, name):
        for c in n.get("_children_full") or []:
            if c.get("name") == name:
                return c
        return None

    tabs_frame = find_named(inst[0], "Tabs")
    if not tabs_frame:
        print("  [mode-tabs] 'Tabs' frame 없음 — skip")
        return 0
    tab_btns = [c for c in (tabs_frame.get("_children_full") or [])
                if (c.get("type") or "").upper() == "INSTANCE"]
    if not tab_btns:
        return 0

    n_keep = min(len(labels), len(tab_btns))
    hide_ids = []

    # active != 0 일 때만 Current 조정 (default 는 tab0=True). variant swap 이 라벨 override
    # 를 리셋할 수 있으니 라벨 set 전에 먼저 수행.
    if active != 0:
        for i in range(n_keep):
            try:
                call_tool("set_instance_properties",
                          {"nodeId": tab_btns[i]["id"],
                           "properties": {"Current": "True" if i == active else "False"}})
            except Exception:
                pass

    for i in range(n_keep):
        btn = tab_btns[i]
        txt = direct_child(btn, "Text") or find_named(btn, "Text")
        if txt and txt.get("id"):
            try:
                call_tool("set_text_content", {"nodeId": txt["id"], "text": labels[i]})
            except Exception as e:
                print(f"  [mode-tabs] label {i} 실패: {e}")
        badge = find_named(btn, "Badge")
        if badge and badge.get("id"):
            hide_ids.append(badge["id"])

    for i in range(n_keep, len(tab_btns)):
        if tab_btns[i].get("id"):
            hide_ids.append(tab_btns[i]["id"])

    if hide_ids:
        try:
            call_tool("set_node_visible", {"nodeIds": hide_ids, "visible": False})
        except Exception as e:
            print(f"  [mode-tabs] hide 실패: {e}")
    try:
        call_tool("set_layout_sizing", {"nodeId": inst[0]["id"], "horizontal": "HUG"})
    except Exception as e:
        print(f"  [mode-tabs] HUG 실패: {e}")
    print(f"  [mode-tabs] ✓ DS Horizontal tabs trim — {n_keep}탭 라벨 + "
          f"{len(hide_ids)}개 hide + HUG (set_node_visible 자동화)")
    return 1


def _node_wh(n: dict):
    """노드의 (width, height) — get_nodes_info 는 top-level width/height 가 없고
    absoluteBoundingBox 에만 담아 반환한다. _collect_tree 류는 top-level 에 둔다.
    두 경로 모두 안전하게 처리 (2026-06-02 회귀 fix: size-invariant 가드가 None 만
    읽어 통째로 무력화돼 원형 셀이 HUG 로 찌부러지던 뿌리)."""
    if not isinstance(n, dict):
        return (0, 0)
    w = n.get("width")
    h = n.get("height")
    if not isinstance(w, (int, float)) or not isinstance(h, (int, float)):
        bb = n.get("absoluteBoundingBox") or n.get("absoluteRenderBounds") or {}
        if isinstance(bb, dict):
            if not isinstance(w, (int, float)):
                w = bb.get("width")
            if not isinstance(h, (int, float)):
                h = bb.get("height")
    return (w if isinstance(w, (int, float)) else 0,
            h if isinstance(h, (int, float)) else 0)


def _is_circle_square_target(w, h, cr, single_child_type=None) -> bool:
    """정사각 복원 대상(원형/icon-box)인지 판별 (순수 함수, 테스트 가능).

    True 면 `_enforce_fixed_size_invariants_final` 이 max(w,h) 정사각으로 복원한다.
    - 정상축 max(w,h) 가 20~80 범위
    - 🔴 min(w,h) >= 12 (2026-06-04): 얇은 pill/드래그 핸들(40×4)/FILL 로 늘어난
      dot(75×5)을 제외 — 이들은 cr=999 라도 장식 요소이지 정사각 대상이 아니다.
      진짜 붕괴한 원형 아바타/icon-box 는 한 축이 콘텐츠 폭(~16px)까지만 줄어 min>=12 유지.
    - cornerRadius 가 999 류(>=100)거나 정상축 절반 이상이면 원형, 또는
      양축 20~80 + 단일 FRAME/INSTANCE/VECTOR 자식이면 icon-box.
    """
    if not (isinstance(w, (int, float)) and isinstance(h, (int, float))):
        return False
    mx, mn = max(w, h), min(w, h)
    if not (20 <= mx <= 80):
        return False
    if mn < 12:
        return False
    if cr >= 100 or cr >= (mx / 2) - 3:
        return True
    if 20 <= mn <= 80 and single_child_type in ("FRAME", "INSTANCE", "VECTOR"):
        return True
    return False


def _enforce_fixed_size_invariants_final(root_id: str) -> int:
    """최종 강제 레이어 (2026-05-28) — post-fix 모든 룰 끝난 뒤 순서 무관하게
    고정 사이즈 invariant 보장. vertical-hug 류 룰이 FAB/circle/icon-box 를
    24px 로 찌그러뜨리는 회귀를 마지막에 복원.

      - FAB (name 'FAB') → 56×56 FIXED, cornerRadius 28
      - 원형/icon-box (cornerRadius >= w/2, 20<=w<=80, w!=h) → max(w,h) 정사각 FIXED
    """
    fixed = [0]

    def _is_circle_iconbox(n):
        w, h = _node_wh(n)
        if not (isinstance(w, (int, float)) and isinstance(h, (int, float))):
            return False
        kids = n.get("children") or []
        kid_type = (kids[0].get("type") or "").upper() if len(kids) == 1 else None
        return _is_circle_square_target(w, h, n.get("cornerRadius") or 0, kid_type)

    def walk(node, parent_layout=""):
        if not isinstance(node, dict):
            return
        ntype = (node.get("type") or "").upper()
        name = (node.get("name") or "")
        nl = name.lower()
        nid = node.get("id")
        w, h = _node_wh(node)
        # DS 버튼 인스턴스 가로 FILL — VERTICAL 부모의 단독 CTA 는 항상 가로 채움
        # (2026-05-28 사용자 "버튼을 가로로 채워야지"). 이 final layer 의 card-padding
        # set_auto_layout 이 CTA child sizing 을 HUG 로 리셋하는 회귀를, child 를 부모보다
        # 늦게 방문하는 walk 순서를 이용해 마지막에 FILL 로 복원 (순서 무관 보장).
        is_btn = ntype == "INSTANCE" and ("action button" in nl or nl == "button"
                                          or nl.endswith(" button") or nl.endswith(" btn")
                                          or nl.endswith(" cta") or "cta" in nl)
        if is_btn and parent_layout == "VERTICAL" \
                and node.get("layoutSizingHorizontal") != "FILL":
            try:
                call_tool("set_layout_sizing", {"nodeId": nid, "horizontal": "FILL"})
                fixed[0] += 1
            except Exception as e:
                print(f"  [size-invariant] cta-fill '{nid}' fail: {e}")
        # FAB → 56×56
        if name in ("FAB", "Fab", "fab") and ntype in ("FRAME", "INSTANCE"):
            if abs(w - 56) > 0.5 or abs(h - 56) > 0.5:
                try:
                    call_tool("set_layout_sizing", {"nodeId": nid, "horizontal": "FIXED", "vertical": "FIXED"})
                    call_tool("resize_node", {"nodeId": nid, "width": 56, "height": 56})
                    call_tool("set_corner_radius", {"nodeId": nid, "cornerRadius": 28})
                    fixed[0] += 1
                except Exception as e:
                    print(f"  [size-invariant] FAB '{nid}' fail: {e}")
        # 원형/icon-box → 정사각 (찌그러진 것만)
        elif ntype == "FRAME" and node.get("componentKey") is None and _is_circle_iconbox(node) and abs(w - h) > 1.5:
            side = round(max(w, h))
            try:
                call_tool("set_layout_sizing", {"nodeId": nid, "horizontal": "FIXED", "vertical": "FIXED"})
                call_tool("resize_node", {"nodeId": nid, "width": side, "height": side})
                fixed[0] += 1
            except Exception as e:
                print(f"  [size-invariant] circle '{nid}' fail: {e}")
        # 🔴 SVG 아이콘 프레임이 FILL 로 늘어남/한 축 붕괴 → 정사각 복원 (2026-06-18 사용자 QA).
        # cornerRadius=0 라 위 원형 가드(_is_circle_iconbox)가 못 잡는 케이스. 회귀 사례:
        # choice tile 아이콘 'piggy-bank-01' 가 28×28 → 134×28(가로 FILL)로 늘어나 vector 가 납작해짐.
        # 자연 아이콘 크기 추정: 큰 축이 비현실적(>64)이면 작은 축(=늘어난 케이스), 아니면 큰 축(=붕괴).
        elif (ntype == "FRAME" and node.get("componentKey") is None and ";" not in (nid or "")
              and _is_stretched_icon_frame(node)):
            mx, mn = max(w, h), min(w, h)
            side = round(mn if mx > 64 else mx)
            if 8 <= side <= 64:
                try:
                    call_tool("set_layout_sizing", {"nodeId": nid, "horizontal": "FIXED", "vertical": "FIXED"})
                    call_tool("resize_node", {"nodeId": nid, "width": side, "height": side})
                    fixed[0] += 1
                    print(f"  [size-invariant] ✓ 아이콘 프레임 정사각 복원 '{name}' {round(w)}×{round(h)} → {side}×{side}")
                except Exception as e:
                    print(f"  [size-invariant] icon-frame '{nid}' fail: {e}")
        # 카드 padding 복원 (batch_build 가 grid row 안 카드의 padding 을 누락 →
        # 요소가 경계에 붙음). 실제 카드 surface 만 (cornerRadius>=12) padding 16 복원.
        # ⚠️ 2026-05-28 사용자 분노 (근본 원인): 예전엔 이름에 "card" 가 들어간 *모든*
        # 프레임("Card Inner"/"Card Top Row"/"Card Score Row")을 잡아 (a) layoutMode 를
        # VERTICAL 로 강제(가로 row 가 세로로 쌓임) + (b) padding 16 누적(우측 들여쓰기)
        # 시켰다. 이제: 하위 프레임 이름 제외 + cornerRadius>=12 실제 카드만 +
        # **layoutMode 보존**(절대 뒤집지 않음 — 기존 mode 그대로 재설정).
        elif (ntype == "FRAME" and not node.get("componentKey")
              and "card" in name.lower()
              and "carousel" not in name.lower()
              and not any(t in name.lower() for t in (
                  "row", "inner", "wrap", "group", "header", "title", "score",
                  "body", "list", "stack", "cell", "top", "bottom", "icon", "label"))
              and (node.get("cornerRadius") or 0) >= 12   # 실제 카드 surface 만
              and (node.get("paddingLeft") or 0) < 8):  # padding 없는 카드만 (있으면 skip)
            try:
                cur_mode = node.get("layoutMode") or "VERTICAL"
                if cur_mode == "NONE":
                    cur_mode = "VERTICAL"
                call_tool("set_auto_layout", {
                    "nodeId": nid, "layoutMode": cur_mode,   # 기존 mode 보존 (HORIZONTAL 안 뒤집음)
                    "paddingLeft": 16, "paddingRight": 16,
                    "paddingTop": 16, "paddingBottom": 16,
                })
                fixed[0] += 1
            except Exception as e:
                print(f"  [size-invariant] card-pad '{nid}' fail: {e}")
        # day cell — batch_build 가 carousel 안 cell 의 FIXED+padding 을 무시(FILL 45.5 +
        # padding 0)해 텍스트가 경계에 붙고 status 넘침. 빌드 후 FIXED 76 + padding 강제.
        elif "day cell" in name.lower() and ntype == "FRAME":
            need = (node.get("layoutSizingHorizontal") != "FIXED"
                    or (node.get("paddingLeft") or 0) < 4
                    or abs((node.get("width") or 0) - 76) > 1.5)
            if need:
                try:
                    call_tool("set_auto_layout", {
                        "nodeId": nid, "layoutMode": "VERTICAL",
                        "paddingTop": 14, "paddingBottom": 14,
                        "paddingLeft": 8, "paddingRight": 8,
                        "counterAxisAlignItems": "CENTER", "itemSpacing": 6,
                    })
                    call_tool("set_layout_sizing", {"nodeId": nid, "horizontal": "FIXED", "vertical": "HUG"})
                    call_tool("resize_node", {"nodeId": nid, "width": 76, "height": h if h > 0 else 102})
                    call_tool("set_layout_sizing", {"nodeId": nid, "vertical": "HUG"})
                    fixed[0] += 1
                except Exception as e:
                    print(f"  [size-invariant] day-cell '{nid}' fail: {e}")
        cur_layout = (node.get("layoutMode") or "").upper()
        for c in node.get("children", []) or []:
            walk(c, cur_layout)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [size-invariant] root fetch fail: {e}")
    return fixed[0]


# 루트가 FIXED 가 아니라 HUG 여야 하는 screen_type (모달 계열) — 2026-05-28.
# FIXED 로 두면 후속 height 증가 시 하단 clip (CLAUDE.md 2-D). 회귀 테스트:
# scripts/tests/test_root_min_height.py
# 🔴 2026-06-04 사용자: bottom-sheet 는 HUG 가 아니라 852 FIXED 여야 한다 (dim 이 위를
# 채우고 시트가 하단에 밀착). HUG 는 full modal 만 (하단 바 없어 852 floor 무의미 + 후속
# height 증가 clip 방지). bottom-sheet 는 _BOTTOM_SHEET_TYPES 로 분리해 852 FIXED + dim FILL.
_HUG_SCREEN_TYPES = frozenset({"modal"})
_BOTTOM_SHEET_TYPES = frozenset({"bottom-sheet", "bottomsheet", "bottom_sheet", "sheet"})


def _is_hug_screen_type(screen_type: Optional[str]) -> bool:
    """screen_type 이 full modal 이면 True (root 를 HUG 로 강제). bottom-sheet 는 제외."""
    return (screen_type or "").strip().lower() in _HUG_SCREEN_TYPES


def _is_bottom_sheet_screen_type(screen_type: Optional[str]) -> bool:
    """screen_type 이 bottom-sheet 계열이면 True (root 852 FIXED + dim FILL + 시트 하단 밀착)."""
    return (screen_type or "").strip().lower() in _BOTTOM_SHEET_TYPES


def _screen_type_from_blueprint(bp: Optional[dict]) -> str:
    """blueprint dict 에서 _screenType / screenType 추출 (소문자). 없으면 ''."""
    if not isinstance(bp, dict):
        return ""
    return (bp.get("_screenType") or bp.get("screenType") or "").strip().lower()


def _resolve_screen_type(root_id: str, tree: Optional[dict],
                         original_blueprint: Optional[dict] = None,
                         injected_blueprint: Optional[dict] = None) -> str:
    """root 의 screen_type 을 가능한 모든 출처에서 결정 (2026-05-28).

    우선순위:
      1. original_blueprint._screenType
      2. injected_blueprint._screenType
      3. .latest_build.json 의 blueprintPath 파일 _screenType
      4. 트리 구조 휴리스틱 — 하단 바(Tab Bar/BAB/FAB) 없음 + close-x(X) 있음 → 'modal'

    Why: standalone `post-fix <rootId>` 처럼 blueprint 가 안 넘어오는 경로에서도
    모달을 인식해 root HUG 를 강제하기 위함 (하단 clip 회귀 차단).
    """
    for bp in (original_blueprint, injected_blueprint):
        st = _screen_type_from_blueprint(bp)
        if st:
            return st
    try:
        latest = _load_latest_build()
        bp_path = latest.get("blueprintPath")
        if bp_path and os.path.exists(bp_path):
            with open(bp_path, encoding="utf-8") as f:
                st = _screen_type_from_blueprint(json.load(f))
                if st:
                    return st
    except Exception:
        pass
    # 트리 휴리스틱 — 하단 바 없음 + X 닫기 있음 → modal
    try:
        children = (tree or {}).get("_children_full", []) or []
        has_bottom_bar = any(
            any(p in (c.get("name") or "").lower() for p in _BOTTOM_BAR_PARTS)
            for c in children
        )
        if not has_bottom_bar:
            def _has_close_x(node: dict, depth: int = 0) -> bool:
                if depth > 4:
                    return False
                nm = (node.get("name") or "").lower()
                if "close-x" in nm or "x-close" in nm or nm in ("x", "닫기"):
                    return True
                return any(_has_close_x(ch, depth + 1)
                           for ch in node.get("_children_full", []) or [])
            if _has_close_x(tree or {}):
                return "modal"
    except Exception:
        pass
    return ""


def _pick_root_height_mode(content_overflows: bool, has_bars: bool, has_fill_flow_child: bool) -> str:
    """_enforce_root_min_height 분기 (순수 함수 — 테스트 대상, 2026-09-04).
    'B' = 긴 콘텐츠 → 바 flow + 루트 HUG / 'A-flow' = 세로 FILL 콘텐츠 자식 → 루트 FIXED 852 +
    바 flow / 'A' = 짧은 콘텐츠 → 루트 852 + 바 ABSOLUTE 핀."""
    if content_overflows and has_bars:
        return "B"
    if has_bars and has_fill_flow_child:
        return "A-flow"
    return "A"


def _flow_fill_child_names(root_id: str) -> list:
    """루트 직계 flow 자식 중 layoutSizingVertical == FILL 인 이름 목록(하단 바 제외)."""
    try:
        tr = parse_content(call_tool("get_node_tree", {"nodeId": root_id, "maxDepth": 1})).get("json") or {}
    except Exception:
        return []
    node = tr.get("node", tr) if isinstance(tr, dict) else {}
    out = []
    for c in node.get("children") or []:
        nm = (c.get("name") or "").lower()
        if any(p in nm for p in _BOTTOM_BAR_PARTS):
            continue
        if c.get("layoutPositioning") == "ABSOLUTE":
            continue
        if (c.get("layoutSizingVertical") or "").upper() == "FILL":
            out.append(c.get("name") or c.get("id"))
    return out


def _enforce_root_min_height(root_id: str, screen_type: Optional[str] = None) -> None:
    """루트 height 정책 — 콘텐츠 길이에 따라 두 가지 분기 (2026-05-24):

    A) **콘텐츠 ≤ ROOT_MIN_HEIGHT (852) 인 짧은 화면**
       - root height = ROOT_MIN_HEIGHT (852)
       - 하단 바(BAB / Tab Bar / CTA Bar / FAB)를 ABSOLUTE + constraint MAX 로
         루트 하단(852 - bar_h)에 pin → 빈 공간 위에 떠 있음.

    B) **콘텐츠 > ROOT_MIN_HEIGHT 인 긴 화면**
       - 하단 바를 normal flow(AUTO)로 전환 — 콘텐츠 아래 자연스럽게 자리잡음.
       - root layoutSizingVertical = HUG → 콘텐츠 + 하단 바 모두 포함하도록 자동 확장.
       - ABSOLUTE pin 그대로 두면 BAB 가 콘텐츠를 덮어 잘려보임(2026-05-24 v14 회귀).

    C) **Modal / Bottom-sheet (`screen_type` in {modal, bottom-sheet})** — 2026-05-28 사용자 분노
       ("또 컨텐츠가 다 안보인 상태에서 잘려있다 ... 시스템에 박아"):
       - root layoutSizingVertical = **HUG** (FIXED 금지) → 콘텐츠 전체를 항상 포함.
       - CLAUDE.md 절대 규칙 2-D: "모달 root 가 FIXED(852)면 하단 CTA 가 잘린다".
       - **Why FIXED 가 잘리나**: 이 함수는 호출 시점의 content_bottom 을 측정해 FIXED 로
         박는데, 이후 단계(auto-bind / text-style / FILL 재배치 / 수동 fix)에서 카드 높이가
         늘어나면 root 는 그대로라 하단이 clip 됨. 모달엔 pin 할 하단 바도 없으므로 852
         floor 가 무의미 — HUG 가 유일하게 안전 (어떤 후속 변경에도 자동 확장).
       - return early — A/B 분기 타지 않음.

    FAB 는 floating button 이므로 A/B 케이스 모두 ABSOLUTE 유지.
    """
    # 🔴 Bottom Sheet (2026-06-04 사용자): root 852 FIXED + dim FILL(위 채움) + 시트 하단 밀착.
    # 가로는 root 풀폭(시트 FILL), 콘텐츠 가로 padding 20 은 Modal Sheet 가 가짐(패턴에서 설정).
    if _is_bottom_sheet_screen_type(screen_type):
        st = (screen_type or "").strip().lower()
        try:
            call_tool("set_layout_sizing", {"nodeId": root_id, "vertical": "FIXED"})
            call_tool("resize_node", {"nodeId": root_id, "width": 393, "height": 852})
            # Dim Overlay 는 vertical FILL 이라야 위 가용공간을 채워 시트를 하단으로 민다.
            tr = _collect_tree(root_id)
            for c in (tr.get("_children_full") or tr.get("children") or []):
                if (c.get("name") or "") == "Dim Overlay":
                    call_tool("set_layout_sizing", {"nodeId": c["id"], "horizontal": "FILL", "vertical": "FILL"})
                # 🔴 절대규칙 (2026-06-04 사용자): 시트 상단 모서리 radius = 16 재단언 +
                # radius 있으니 clipsContent=true (get_nodes_info 가 개별 코너를 None 으로
                # 직렬화해 일반 clip enforcer 가 시트를 놓치므로 이름으로 직접 강제).
                if (c.get("name") or "") == "Modal Sheet":
                    try:
                        call_tool("set_corner_radius", {"nodeId": c["id"], "radius": 16,
                                                        "corners": [True, True, False, False]})
                    except Exception:
                        pass
                    try:
                        call_tool("set_auto_layout", {"nodeId": c["id"],
                                                      "layoutMode": c.get("layoutMode") or "VERTICAL",
                                                      "clipsContent": True})
                    except Exception:
                        pass
            print(f"[규칙] 바텀시트(screen_type={st}) — root 852 FIXED + Dim FILL + 시트 하단 밀착 + 상단 radius 16")
        except Exception as e:
            print(f"  [바텀시트] 실패 (무시): {e}")
        return
    if _is_hug_screen_type(screen_type):
        st = (screen_type or "").strip().lower()
        try:
            call_tool("set_layout_sizing", {"nodeId": root_id, "vertical": "HUG"})
            print(f"[규칙] 모달(screen_type={st}) — root vertical HUG 강제 "
                  f"(FIXED 시 후속 height 증가로 하단 clip — CLAUDE.md 2-D)")
        except Exception as e:
            print(f"  [모달 HUG] 실패 (무시): {e}")
        return
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        result = parse_content(info)
        items = result.get("json") or []
        if not items:
            return
        doc = items[0].get("document") or items[0]
        root_bb = doc.get("absoluteBoundingBox") or {}
        root_h = root_bb.get("height") or 0
        root_w = root_bb.get("width") or 393
        root_y = root_bb.get("y") or 0

        # 자식 분류 — name 매칭으로 bottom bar vs content
        children = doc.get("children") or []
        content_bottom = 0
        bottom_bars = []
        for c in children:
            nm = (c.get("name") or "").lower()
            bb = c.get("absoluteBoundingBox") or {}
            cy = (bb.get("y") or 0) - root_y
            ch = bb.get("height") or 0
            cx = (bb.get("x") or 0) - (root_bb.get("x") or 0)
            if any(p in nm for p in _BOTTOM_BAR_PARTS):
                bottom_bars.append({
                    "id": c.get("id"), "name": c.get("name"),
                    "height": ch, "x": cx,
                })
            else:
                # 콘텐츠 extent — ABSOLUTE 자식은 제외
                if c.get("layoutPositioning") != "ABSOLUTE":
                    content_bottom = max(content_bottom, cy + ch)

        tabish = [b for b in bottom_bars if "fab" not in (b["name"] or "").lower()]
        fabs   = [b for b in bottom_bars if "fab" in (b["name"] or "").lower()]
        FAB_GAP = 16

        # 정책 분기 — _should_use_bab_normal_flow 가 표준. content + BAB 합산 (2026-05-26 fix).
        # 회귀 테스트: scripts/tests/test_root_min_height.py
        bab_total_h = sum(b["height"] for b in tabish)
        total_with_bab = int(content_bottom) + int(bab_total_h)
        content_overflows = _should_use_bab_normal_flow(
            content_bottom, [b["height"] for b in tabish], ROOT_MIN_HEIGHT,
        )

        fill_flow = _flow_fill_child_names(root_id)
        mode = _pick_root_height_mode(content_overflows, bool(tabish), bool(fill_flow))
        if mode == "A-flow":
            # A-flow 케이스 (2026-09-04) — 루트 FIXED 852 안에 세로 FILL 콘텐츠 자식이 있는 화면
            # (캡처 변환의 'Content FILL + 안내 + 하단 바' 구조). ABSOLUTE 핀은 flow 자식(안내
            # 문구)과 겹치게 하므로(스테이지참여 4순번 회귀) 바를 flow 로 두면 FILL 자식이 알아서
            # 바를 하단에 붙인다.
            desired = max(int(root_h), ROOT_MIN_HEIGHT)
            call_tool("set_layout_sizing", {"nodeId": root_id, "vertical": "FIXED"})
            if int(root_h) != desired:
                call_tool("resize_node", {"nodeId": root_id, "width": root_w, "height": desired})
            for bar in tabish:
                try:
                    call_tool("set_layout_positioning", {"nodeId": bar["id"], "layoutPositioning": "AUTO"})
                except Exception:
                    pass
            print(f"[규칙] 세로 FILL 콘텐츠({', '.join(fill_flow)}) — 루트 FIXED {desired} + 하단 바 {len(tabish)}개 flow 유지(ABSOLUTE 핀 생략)")
            bottom_anchor_y = desired - sum(b["height"] for b in tabish)
        elif content_overflows and tabish:
            # B 케이스 — 긴 콘텐츠 + 하단 바: BAB normal flow + root HUG.
            # ABSOLUTE pin 으로 두면 BAB 가 콘텐츠를 덮음(2026-05-24 v14 회귀).
            for bar in tabish:
                try:
                    call_tool("set_layout_positioning", {
                        "nodeId": bar["id"], "layoutPositioning": "AUTO",
                    })
                except Exception:
                    pass
            try:
                call_tool("set_layout_sizing", {"nodeId": root_id, "vertical": "HUG"})
            except Exception:
                pass
            print(f"[규칙] 긴 콘텐츠(content={int(content_bottom)} + BAB={int(bab_total_h)} = {total_with_bab} > {ROOT_MIN_HEIGHT}) — "
                  f"하단 바 {len(tabish)}개 normal flow + root HUG")
            # FAB 는 콘텐츠 위에 떠야 하므로 ABSOLUTE 유지 (아래에서 처리)
            # bottom_anchor_y 는 BAB 가 normal flow 라 root 의 새 height 가 됨.
            # 다시 측정 — root 이 HUG 로 늘어났을 것.
            try:
                info2 = call_tool("get_nodes_info", {"nodeIds": [root_id]})
                items2 = parse_content(info2).get("json") or []
                if items2:
                    doc2 = items2[0].get("document") or items2[0]
                    new_root_h = (doc2.get("absoluteBoundingBox") or {}).get("height") or content_bottom
                    desired = int(new_root_h)
            except Exception:
                desired = int(content_bottom) + sum(b["height"] for b in tabish)
            bottom_anchor_y = desired - sum(b["height"] for b in tabish)
        else:
            # A 케이스 — 짧은 콘텐츠: root = max(content, ROOT_MIN_HEIGHT), BAB ABSOLUTE pin.
            desired = max(int(content_bottom), ROOT_MIN_HEIGHT)
            if desired != int(root_h):
                call_tool("set_layout_sizing", {"nodeId": root_id, "vertical": "FIXED"})
                call_tool("resize_node", {"nodeId": root_id, "width": root_w, "height": desired})
                direction = "늘림" if desired > root_h else "줄임"
                print(f"[규칙] 루트 height {direction}: {int(root_h)} → {desired} (콘텐츠 extent={int(content_bottom)}, min={ROOT_MIN_HEIGHT})")
            else:
                print(f"[규칙] 루트 height 유지: {desired} (콘텐츠 extent={int(content_bottom)})")

            bottom_anchor_y = desired
            for bar in tabish:
                new_y = desired - bar["height"]
                try:
                    call_tool("set_layout_positioning", {
                        "nodeId": bar["id"], "layoutPositioning": "ABSOLUTE",
                        "constraints": {"vertical": "MAX", "horizontal": "STRETCH"},
                    })
                except Exception:
                    pass
                call_tool("move_node", {"nodeId": bar["id"], "x": bar["x"], "y": new_y})
                print(f"  하단 pin: {bar['name']} → y={new_y}")
                bottom_anchor_y = min(bottom_anchor_y, new_y)
        for fab in fabs:
            new_y = bottom_anchor_y - fab["height"] - FAB_GAP
            try:
                call_tool("set_layout_positioning", {
                    "nodeId": fab["id"], "layoutPositioning": "ABSOLUTE",
                    "constraints": {"vertical": "MAX", "horizontal": "MAX"},
                })
            except Exception:
                pass
            call_tool("move_node", {"nodeId": fab["id"], "x": fab["x"], "y": new_y})
            print(f"  FAB pin: {fab['name']} → y={new_y}")
    except Exception as e:
        print(f"  루트 minHeight 처리 실패: {e}")


def _fix_tab_bar_items(tree: dict) -> int:
    """Tab Bar 내부 아이템을 FILL로 통일하고, Tab Row에 individual stroke 적용."""
    fix_count = 0
    children = tree.get("_children_full", [])

    for child in children:
        name_lower = (child.get("name") or "").lower()

        # Tab Bar item FILL 통일
        if "tab bar" in name_lower or "tabbar" in name_lower:
            tab_items = child.get("_children_full", [])
            for item in tab_items:
                item_type = (item.get("type") or "").upper()
                item_sizing = item.get("layoutSizingHorizontal", "")
                if item_type == "FRAME" and item_sizing != "FILL":
                    try:
                        call_tool("set_layout_sizing", {
                            "nodeId": item.get("id"),
                            "horizontal": "FILL"
                        })
                        fix_count += 1
                        print(f"  Tab item FILL: {item.get('name')} ({item.get('id')})")
                    except Exception as e:
                        print(f"  Tab item FILL 실패: {item.get('name')}: {e}")

        # Tab Row (underline tab) — individual stroke bottom only
        _apply_individual_strokes(child)

    return fix_count


def _apply_individual_strokes(node: dict):
    """Tab Row 등 이름에 'Tab Row'가 포함된 노드에 bottom-only stroke 적용."""
    name = node.get("name") or ""
    if "Tab Row" in name:
        strokes = node.get("strokes", [])
        if strokes:
            stroke_color = strokes[0].get("color", {})
            try:
                call_tool("set_stroke_color", {
                    "nodeId": node.get("id"),
                    "r": stroke_color.get("r", 0.914),
                    "g": stroke_color.get("g", 0.918),
                    "b": stroke_color.get("b", 0.922),
                    "a": 1,
                    "strokeWeight": 1,
                    "strokeTopWeight": 0,
                    "strokeBottomWeight": 1,
                    "strokeLeftWeight": 0,
                    "strokeRightWeight": 0
                })
                print(f"  Individual stroke: {name} ({node.get('id')}) → bottom only")
            except Exception as e:
                print(f"  Individual stroke 실패: {name}: {e}")

    # 자식도 재귀 탐색
    for child in node.get("_children_full", []):
        _apply_individual_strokes(child)


def _fix_text_fill_in_hug_parent_live(root_id: str) -> int:
    """🔴 가로 HUG 부모 안 TEXT 의 layoutSizingHorizontal=FILL 붕괴 복구 (2026-06-12).

    batch_build(code.js)가 VERTICAL 부모의 TEXT 에 자동 FILL 을 주는데, 부모가 가로
    HUG 면 FILL-in-HUG 순환 참조로 텍스트가 최소폭으로 붕괴해 짧은 라벨('후기 공유')이
    세로로 wrap 된다. 그런 TEXT 를 HUG 로 복구. DS 인스턴스 내부(';') 제외."""
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        root = items[0].get("document") if items else None
    except Exception as e:
        print(f"  [text-fill-hug] 트리 조회 실패: {e}")
        return 0
    if not isinstance(root, dict):
        return 0
    fixed = [0]

    def walk(n, parent=None):
        if not isinstance(n, dict):
            return
        nid = n.get("id") or ""
        if (n.get("type") or "").upper() == "TEXT" and ";" not in nid and parent is not None:
            p_hug = (parent.get("layoutSizingHorizontal") or "").upper() == "HUG"
            t_fill = (n.get("layoutSizingHorizontal") or "").upper() == "FILL"
            if p_hug and t_fill and (parent.get("type") or "").upper() == "FRAME":
                try:
                    call_tool("set_layout_sizing", {"nodeId": nid, "horizontal": "HUG"})
                    fixed[0] += 1
                    print(f"  [text-fill-hug] ✓ '{n.get('name')}' FILL→HUG (부모 '{parent.get('name')}' 가로 HUG)")
                except Exception as e:
                    print(f"  [text-fill-hug] 실패(무시) {n.get('name')}: {e}")
        if (n.get("type") or "").upper() == "INSTANCE":
            return  # DS 인스턴스 내부 제외 (0-K)
        for c in n.get("_children_full") or n.get("children") or []:
            walk(c, n)

    walk(root)
    if fixed[0]:
        print(f"  [text-fill-hug] ✓ {fixed[0]}건 복구")
    return fixed[0]


def _fix_zero_width_text(tree: dict) -> int:
    """width=0인 TEXT 노드를 수정: textAutoResize → WIDTH_AND_HEIGHT, 그 후 FILL.

    Banner Card 내부 텍스트는 FILL 대신 FIXED 160px로 설정 (이미지 영역 침범 방지).
    """
    fix_count = 0

    def _walk(node: dict, inside_banner: bool = False):
        nonlocal fix_count
        node_type = (node.get("type") or "").upper()
        node_id = node.get("id")
        node_name = node.get("name", "")
        width = node.get("width", 1)

        # Banner Card 내부인지 추적
        is_banner = inside_banner or "banner card" in node_name.lower()

        if node_type == "TEXT" and width <= 1 and node_id:
            try:
                call_tool("set_text_properties", {
                    "nodeId": node_id,
                    "textAutoResize": "WIDTH_AND_HEIGHT"
                })
                if is_banner:
                    # 배너 텍스트: FIXED 160px (이미지 영역 침범 방지)
                    call_tool("set_layout_sizing", {
                        "nodeId": node_id,
                        "horizontal": "FIXED"
                    })
                    call_tool("resize_node", {
                        "nodeId": node_id,
                        "width": 160,
                        "height": 60
                    })
                    fix_count += 1
                    print(f"  텍스트 수정: {node_name} ({node_id}) [width=0 → FIXED 160px (배너)]")
                else:
                    call_tool("set_layout_sizing", {
                        "nodeId": node_id,
                        "horizontal": "FILL"
                    })
                    fix_count += 1
                    print(f"  텍스트 수정: {node_name} ({node_id}) [width=0 → FILL]")
            except Exception as e:
                print(f"  텍스트 수정 실패: {node_name} ({node_id}): {e}")

        for child in node.get("_children_full", []):
            _walk(child, inside_banner=is_banner)

    _walk(tree)
    return fix_count


# ── 2026-05-24 사용자 "다 박아" — latest 추적 + 자동 재바인딩 ─────
# 빌드/post-fix 호출마다 latest rootId + blueprint path 저장. cmd_post_fix가
# 인자 없이 호출돼도 latest 자동 lookup → 토큰 재바인딩 가능.

_LATEST_BUILD_FILE = os.path.join(os.path.dirname(__file__), ".latest_build.json")


def _save_latest_build(root_id: str, blueprint_path: str) -> None:
    try:
        with open(_LATEST_BUILD_FILE, "w") as f:
            json.dump({"rootId": root_id, "blueprintPath": blueprint_path}, f)
    except Exception:
        pass


def _load_latest_build() -> dict:
    try:
        with open(_LATEST_BUILD_FILE) as f:
            return json.load(f) or {}
    except Exception:
        return {}


def cmd_post_fix(root_node_id: str, pre_computed_layout: dict = None,
                 original_blueprint: Optional[dict] = None,
                 injected_blueprint: Optional[dict] = None):
    """빌드 후 자동 후처리: FILL 사이징, Tab Bar/FAB 배치, 섹션 갭, 텍스트 수정.

    Usage:
        python3 scripts/figma_mcp_client.py post-fix <rootNodeId>
    """
    ensure_session()

    print(f"\n{'='*50}")
    print(f"POST-FIX 자동 후처리 시작 — rootId: {root_node_id}")
    print(f"{'='*50}")
    start = time.time()

    # 1. 노드 트리 수집
    print("\n[1/5] 노드 트리 수집 중...")
    tree = _collect_tree(root_node_id)
    children_count = len(tree.get("_children_full", []))
    print(f"  루트 '{tree.get('name', '?')}' — 직계 자식 {children_count}개")

    # ★ 안전장치: 자식이 없으면 데이터 수집 실패로 판단
    if children_count == 0:
        print(f"  ⚠️ 직계 자식이 0개 — 데이터 수집 실패. post-fix 중단 (루트 보호)")
        return

    # 2. FILL 사이징 수정 (FAB/Tab Bar 제외, SPACE_BETWEEN HUG 보존)
    print("\n[2/5] FILL 사이징 검증/수정 중...")
    fill_fixes = _fix_fill_sizing(tree)
    print(f"  → {fill_fixes}건 수정")

    # 3. Tab Bar/FAB 배치 + 섹션 갭 조정
    print("\n[3/5] Tab Bar/FAB 배치 + 섹션 갭 조정 중...")
    layout_result = _fix_layout_and_positions(tree, pre_computed_layout=pre_computed_layout)
    print(f"  → content_bottom={layout_result['content_bottom']}, "
          f"fab_y={layout_result['fab_y']}, tab_y={layout_result['tab_y']}, "
          f"root_height={layout_result['root_height']}")

    # 4. Tab Bar item FILL + individual stroke
    print("\n[4/5] Tab Bar item FILL + individual stroke 수정 중...")
    tab_fixes = _fix_tab_bar_items(tree)
    print(f"  → {tab_fixes}건 수정")

    # 5. Zero-width 텍스트 수정
    print("\n[5/5] Zero-width 텍스트 수정 중...")
    text_fixes = _fix_zero_width_text(tree)
    print(f"  → {text_fixes}건 수정")

    # screen_type 을 미리 해석 (bottom-sheet 면 root 를 black 50% dim 으로 — 아래 bg 강제에 사용)
    _screen_type = _resolve_screen_type(
        root_node_id, tree, original_blueprint, injected_blueprint,
    )

    # ⚠️ 시스템 규칙: 루트 프레임 배경 = bg-primary 강제 (런타임 보장).
    # 🔴 예외: bottom-sheet 는 black 50%(dim) — 시트 radius 가시화 (2026-06-04 사용자).
    print("\n[규칙] 루트 프레임 배경 강제 적용 중...")
    _enforce_root_bg_primary_live(root_node_id, screen_type=_screen_type)

    # NavBar 스타일(절대규칙 0-O)은 cmd_build Step E.7.7(AUTO_FIX·white-card-border *이후*)에서
    # 최종 적용한다 — 여기서 적용하면 _enforce_white_card_border_live 가 NavBar(bg-primary) 위
    # back btn 에 border 를 다시 붙여 stroke 제거가 무력화됨.

    # ⚠️ 시스템 규칙 (2026-05-27): VERTICAL frame HUG 강제 — batch_build 가 카드 안
    # VERTICAL Body 를 FIXED <small> 로 박는 버그 회피. 이게 안 되면 콘텐츠가 카드
    # 밖으로 흘러나오고 root_min_height 측정이 짧게 잡혀 BAB 가 콘텐츠를 덮는다.
    print("\n[규칙] VERTICAL frame HUG 강제 (batch_build height-FIXED 버그 회피) 적용 중...")
    _enforce_vertical_hug(root_node_id)

    # ⚠️ 시스템 규칙 (2026-05-27): carousel scroll vertical HUG 강제 — 사용자 분노 fix.
    # HORIZONTAL parent (Lounge Scroll, Schedule Scroll 등) 가 vertical FILL 로 박혀
    # height=93 같은 작은 값으로 fix 되면, 자식 카드 (height 240+) 가 overflow 해서
    # 다음 섹션 (Footer 등) 을 덮어버린다. R36 _ensure_carousel_hug_v 가 있지만
    # carousel detect 조건이 까다로워 빠지는 케이스가 많음 — 이름 기반으로 unconditional.
    print("\n[규칙] carousel scroll vertical HUG 강제 (overflow → next-section 침범 방지) 적용 중...")
    _enforce_carousel_hug_v(root_node_id)

    # ⚠️ 시스템 규칙 (2026-05-27): FILL sibling 1px 버그 자동 fix — 사용자 분노 fix.
    # batch_build_screen 이 같은 부모 안 두 FILL sibling 중 한 쪽 width 를 1px 로 박는
    # 버그. Segmented Tab Active 1px / Schedule Btn 1px 케이스. 자동 균등 분배 + FILL 복원.
    print("\n[규칙] FILL sibling 1px 버그 자동 fix 적용 중...")
    _fix_fill_sibling_1px(root_node_id)

    # ⚠️ 시스템 규칙 (2026-05-27): button fill==parent fill 이면 border-secondary 자동 추가.
    # Summary Card bg-primary 강제 후 안의 outline button(bg-primary)이 안 보이는
    # 사용자 분노 fix. cornerRadius>=20 + 이름 ~ btn/button/cta 인 frame 검사.
    print("\n[규칙] button same-bg → border-secondary 자동 추가 적용 중...")
    _enforce_button_border_on_same_bg(root_node_id)

    # ⚠️ 시스템 규칙: 루트 minHeight=852 + 하단 바 bottom-pin (2026-05-24)
    # 모달/바텀시트는 HUG (2026-05-28 사용자 "또 잘려있다 ... 시스템에 박아").
    # _screen_type 은 위에서 이미 해석됨 (root bg 강제에서 사용).
    print("\n[규칙] 루트 minHeight=852 + 하단 바 bottom-pin 적용 중...")
    _enforce_root_min_height(root_node_id, screen_type=_screen_type)

    # ⚠️ 2026-05-24 사용자 분노 fix — root export clip blind spot
    # CTA overflow / icon button 시인성 / small text center 자동 검출 + fix
    print("\n[규칙] overflow detect + auto FILL 적용 중...")
    _fix_overflow_children(root_node_id)
    print("\n[규칙] icon button 시인성 보장 (bg-secondary → bg-tertiary) 적용 중...")
    _fix_icon_button_visibility(root_node_id)
    print("\n[규칙] small text FILL + LEFT → CENTER 정렬 적용 중...")
    _fix_small_text_center(root_node_id)
    print("\n[규칙] R45 섹션 clipsContent=false 강제 (carousel / rounded card 제외) 적용 중...")
    _disable_section_clipping(root_node_id)
    # 2026-05-28 사용자 명시: rounded card (cornerRadius ≥ 8) 는 clip 유지 필수
    # — 라운지 카드 같은 카드 안 image/색 영역이 라운드 모서리 밖으로 안 튀어나오게.
    try:
        _enforce_rounded_card_clip_live(root_node_id)
    except Exception as e:
        print(f"  [rounded-card-clip] 실패 (무시하고 계속): {e}")

    # 2026-05-28 사용자 분노 — Month Cell Oct → "Jct" 잘림.
    # 작은 원형 cell + 텍스트 가득 = 좌우 모서리 잘림 차단.
    try:
        _fix_text_clip_in_small_round_cells(root_node_id)
    except Exception as e:
        print(f"  [text-clip-fix] 실패 (무시하고 계속): {e}")

    # 2026-05-28 사용자 명시 — 작은 cell 안 TEXT 중앙 정렬 강제 (Month Cell Jan 좌측 정렬 분노).
    try:
        _center_text_in_small_cells_live(root_node_id)
    except Exception as e:
        print(f"  [text-center-fix] 실패 (무시하고 계속): {e}")

    # 2026-05-28 사용자 분노 — Bottom Tab Bar 라벨 wrap (커뮤니티/스테이지 두 줄).
    # Tab Bar 자식 frame HUG → FILL + 라벨 textAutoResize=HEIGHT 강제.
    try:
        _enforce_tab_bar_children_fill_live(root_node_id)
    except Exception as e:
        print(f"  [tab-bar-fill] 실패 (무시하고 계속): {e}")

    # 2026-05-28 사용자 분노 (2회) — Summary Grid 3-col 좌측 박힘 + baseline 어긋남.
    # HORIZONTAL parent + 자식이 label/value VERTICAL stack ≥2 패턴 감지 시
    # parent → MIN + CENTER, 각 col → FILL + VERTICAL + CENTER, col 안 TEXT → textAlign CENTER.
    # 컬럼 균등 분배 + 텍스트 컬럼 중앙. 새 세션 회귀 차단 absolute.
    try:
        _fix_space_between_col_baseline(root_node_id)
    except Exception as e:
        print(f"  [col-baseline] 실패 (무시하고 계속): {e}")

    # 2026-06-02 사용자: 회차 셀렉터 10~13(2자리) 만 빌드가 FIXED h=36 으로 키워
    # 숫자가 아래로 내려가 정렬 틀어짐 (1~9 는 HUG). 동질 셀 그룹 세로 사이징 통일로 차단.
    try:
        _normalize_row_cell_vertical_sizing_live(root_node_id)
    except Exception as e:
        print(f"  [row-cell-vsize] 실패 (무시하고 계속): {e}")

    # ⚠️ 2026-05-24 사용자 "다 박아" — manual fix 후 자동 재바인딩
    # 위 3개 fix가 set_fill_color/set_layout_sizing 호출 → boundVariables 끊김 가능.
    # original_blueprint가 있으면 token 재적용. 없으면 .latest_build.json에서 자동 lookup.
    bp_for_rebind = original_blueprint
    if bp_for_rebind is None:
        latest = _load_latest_build()
        bp_path = latest.get("blueprintPath")
        if bp_path and os.path.exists(bp_path):
            try:
                with open(bp_path, encoding="utf-8") as f:
                    bp_for_rebind = json.load(f)
                print(f"\n[규칙] manual fix 후 자동 재바인딩 — blueprint auto-loaded: {os.path.basename(bp_path)}")
            except Exception as e:
                print(f"\n[규칙] blueprint auto-load 실패 (재바인딩 skip): {e}")
    if bp_for_rebind is not None:
        try:
            re_ok = auto_bind_design(root_node_id, bp_for_rebind)
            print(f"  [재바인딩] 완료 — {re_ok}개 적용 (manual fix로 끊긴 token 복구)")
        except Exception as e:
            print(f"  [재바인딩] 실패: {e}")

    # ⚠️ 시스템 규칙 (2026-05-27 사용자 명시): Section Divider 라인 자동 삽입 금지.
    # post-fix 매 실행마다 빌드 트리의 모든 "Section Divider" 노드 자동 제거 — 회귀 차단.
    print("\n[규칙] Section Divider 자동 제거 (2026-05-27 절대 룰) 적용 중...")
    try:
        n_div = _strip_section_dividers(root_node_id)
        if n_div:
            print(f"  [no-divider] ✓ Section Divider 노드 {n_div}건 제거")
        else:
            print("  [no-divider] OK — Section Divider 노드 없음")
    except Exception as e:
        print(f"  [no-divider] 실패 (무시하고 계속): {e}")

    # ⚠️ 시스템 규칙 (2026-05-27 사용자 명시 — "버튼이 아니면서 면적이 큰 frame에 brand color 채우지마"):
    # 큰 면적 frame (cornerRadius>=12 + children>=2 OR children>=3, w>=100 h>=60) 에 brand
    # fill 발견 시 자동으로 bg-primary + border-secondary 로 교체. brand 는 텍스트/버튼 액센트만.
    print("\n[규칙] 큰 frame brand fill 자동 제거 (2026-05-27 절대 룰) 적용 중...")
    try:
        n_brand = _strip_large_brand_fills(root_node_id)
        if n_brand:
            print(f"  [no-large-brand] ✓ frame {n_brand}건 brand fill 제거 + border 추가")
        else:
            print("  [no-large-brand] OK — 큰 brand 카드 없음")
    except Exception as e:
        print(f"  [no-large-brand] 실패 (무시하고 계속): {e}")

    # ⚠️ 시스템 규칙 (2026-05-27 사용자 명시 — "일회성 수정은 의미없다. 다시 발생하지않게 해"):
    # clone_node 후 token rebind 실패로 흰 카드 위 흰 텍스트 박히는 회귀 차단.
    # 대비 < 1.5 인 TEXT 를 발견하면 자동으로 배경 luminance 에 맞춘 text-primary/fg-white 로 교체.
    print("\n[규칙] 안 보이는 TEXT 자동 교정 (대비 < 1.5 → text-primary/fg-white) 적용 중...")
    try:
        n_text = _auto_fix_invisible_text(root_node_id, ratio_threshold=1.5)
        if n_text:
            print(f"  [invisible-text] ✓ TEXT {n_text}건 색 자동 교정")
        else:
            print("  [invisible-text] OK — 대비 부족 TEXT 없음")
    except Exception as e:
        print(f"  [invisible-text] 실패 (무시하고 계속): {e}")

    # ⚠️ 시스템 규칙 (2026-05-27): divider 제거 부작용 — root 직계 콘텐츠 섹션의
    # paddingTop/Bottom 이 0 으로 깎여 카드가 붙어 보임. 최소 8px 복원.
    print("\n[규칙] 콘텐츠 섹션 padding 복원 (divider 제거 부작용 fix) 적용 중...")
    try:
        n_pad = _restore_content_section_padding(root_node_id, min_pad=8)
        if n_pad:
            print(f"  [section-gap] ✓ 콘텐츠 섹션 {n_pad}건 padding 복원 (min 8px)")
        else:
            print("  [section-gap] OK — padding 이미 적절")
    except Exception as e:
        print(f"  [section-gap] 실패 (무시하고 계속): {e}")

    # ⚠️ 시스템 규칙 (2026-05-27 사용자 명시): drop-shadow 절대 금지.
    # post-fix 매 실행마다 빌드 트리의 모든 frame effects 를 재제거 — 회귀 차단.
    print("\n[규칙] drop-shadow 전면 제거 (2026-05-27 절대 룰) 적용 중...")
    try:
        n_clear = _strip_all_drop_shadows(root_node_id)
        if n_clear:
            print(f"  [no-shadow] ✓ frame {n_clear}건의 drop-shadow 제거")
        else:
            print("  [no-shadow] OK — drop-shadow 가진 frame 없음")
    except Exception as e:
        print(f"  [no-shadow] 실패 (무시하고 계속): {e}")

    # ⚠️ 시스템 규칙 (2026-05-27 사용자 분노 fix): batch_build_screen 이 blueprint 의
    # strokeColor/strokeWeight 를 무시함. live 트리에 직접 박아서 회귀 차단.
    print("\n[규칙] 텍스트 크기 하한 라이브 강제 (2026-06-05, 12pt 남용 차단) 적용 중...")
    try:
        _enforce_min_text_size_live(root_node_id)
    except Exception as e:
        print(f"  [min-text-size-live] 실패 (무시하고 계속): {e}")

    print("\n[규칙] 브랜드 틴트 면 → bg-brand-primary 라이브 강제 (2026-06-05) 적용 중...")
    try:
        _enforce_brand_tint_surface_primary_live(root_node_id)
    except Exception as e:
        print(f"  [brand-tint-surface-live] 실패 (무시하고 계속): {e}")

    print("\n[규칙] 섹션 bg 색 경계 — 아래 섹션 상단 padding 증가 (2026-06-05) 적용 중...")
    try:
        _enforce_section_bg_gap_padding(root_node_id)
    except Exception as e:
        print(f"  [section-bg-gap] 실패 (무시하고 계속): {e}")

    print("\n[규칙] 월렛 바 top-left/top-right radius 16 (2026-06-05) 적용 중...")
    try:
        _enforce_wallet_bar_radius(root_node_id)
    except Exception as e:
        print(f"  [wallet-radius] 실패 (무시하고 계속): {e}")

    print("\n[규칙] Status Bar 393×62 FIXED 강제 (2026-06-12 HUG 변형 복구) 적용 중...")
    try:
        # 2026-07-10: stale 키 import 실패로 ⚠ 에러 프레임이 된 Status Bar 를 먼저 자동
        # 교체(같은 페이지 인스턴스 clone) — 그 후 size 백스톱이 FILL×FIXED 62 재단언.
        _recover_error_status_bar_live(root_node_id)
        _enforce_status_bar_size_live(root_node_id)
    except Exception as e:
        print(f"  [status-bar-size] 실패 (무시하고 계속): {e}")

    # 🔴 2026-09-04: 액션바 Action Button 이 세로 HUG 로 24px 붕괴하던 회귀 백스톱
    # (Status Bar 62→63.5 와 동일 함정 — DS 인스턴스 세로 HUG 금지). Size 별 마스터 높이 재단언.
    try:
        _enforce_action_button_height_live(root_node_id)
    except Exception as e:
        print(f"  [action-button-height] 실패 (무시하고 계속): {e}")

    # 🔴 2026-09-04: 변환 트랙은 HomeIndicator 를 자동 삽입(페이지 내 기존 인스턴스 clone).
    try:
        _st = locals().get("_screen_type")
        _ensure_home_indicator_live(root_node_id, screen_type=_st)
    except Exception as e:
        print(f"  [home-indicator-ensure] 실패 (무시하고 계속): {e}")

    # 🔴 2026-09-07 사용자 룰(0-Y-2): 키보드가 있는 화면은 최하단 HomeIndicator 불필요 — 삭제.
    try:
        _remove_home_indicator_when_keyboard_live(root_node_id)
    except Exception as e:
        print(f"  [home-indicator-keyboard] 실패 (무시하고 계속): {e}")

    try:
        _enforce_home_indicator_fill_live(root_node_id)
    except Exception as e:
        print(f"  [home-indicator-fill] 실패 (무시하고 계속): {e}")

    try:
        _enforce_tool_bar_title_style_live(root_node_id)
    except Exception as e:
        print(f"  [tool-bar-title] 실패 (무시하고 계속): {e}")

    print("\n[규칙] 인디케이터 프레임 위 gap = 아래 padding 대칭 (2026-06-05) 적용 중...")
    try:
        _enforce_indicator_symmetric_gap(root_node_id)
    except Exception as e:
        print(f"  [indicator-gap] 실패 (무시하고 계속): {e}")

    print("\n[규칙] 스테퍼 그룹 세로 2-row 스택 강제 (2026-06-08) 적용 중...")
    try:
        _enforce_stepper_two_row_live(root_node_id)
    except Exception as e:
        print(f"  [stepper-2row] 실패 (무시하고 계속): {e}")

    print("\n[규칙] 흰 카드 border 라이브 강제 (batch_build stroke 무시 버그 우회) 적용 중...")
    try:
        _enforce_white_card_border_live(root_node_id)
    except Exception as e:
        print(f"  [white-card-border-live] 실패 (무시하고 계속): {e}")

    # 🔴 2026-06-09 사용자 룰: 상단바/헤더 아이콘 버튼(back/search/nav 등)에 fill 박스·radius·
    # stroke 를 기본으로 넣지 않는다. white-card-border *직후* 실행해 enforcer 가 붙인 chrome 까지 제거.
    print("\n[규칙] 아이콘 버튼 chrome 제거 (2026-06-09 사용자: 기본 무chrome) 적용 중...")
    try:
        _strip_icon_button_chrome_live(root_node_id)
    except Exception as e:
        print(f"  [icon-button-chrome] 실패 (무시하고 계속): {e}")

    # ⚠️ 시스템 규칙 (2026-05-27 사용자 명시): 섹션 wrapper frame 에 border 박히면 안 됨.
    # _enforce_white_card_border_live 가 'section'/'wrap' 키워드 카드로 false-positive
    # 분류했던 케이스 회귀 차단. wrapper 자체에 박힌 stroke 자동 제거.
    print("\n[규칙] 섹션 wrapper frame stroke 제거 (2026-05-27 사용자 명시) 적용 중...")
    try:
        _strip_section_wrapper_borders_live(root_node_id)
    except Exception as e:
        print(f"  [strip-wrapper-border] 실패 (무시하고 계속): {e}")

    # ⚠️ 시스템 규칙 (2026-05-27 사용자 회귀 fix): batch_build_screen 이 blueprint 의
    # layoutSizingHorizontal=FILL 을 무시함. HORIZONTAL grid row 안의 카드 자식들을
    # 자동 FILL 강제 (HUG 좁아져 텍스트 줄바꿈 회귀 차단).
    print("\n[규칙] grid row 카드 FILL 강제 (HUG → FILL, 2026-05-27 회귀 fix) 적용 중...")
    try:
        _enforce_grid_row_cards_fill_live(root_node_id)
    except Exception as e:
        print(f"  [grid-row-fill] 실패 (무시하고 계속): {e}")

    # ⚠️ 시스템 규칙 (2026-05-27 사용자 회귀 fix): HORIZONTAL row 의 vertical=FIXED 회귀.
    # batch_build_screen 이 height 명시 없는 HORIZONTAL frame 도 FIXED 로 박아 row 가
    # 쓸데없이 큰 박스가 되는 버그. 자식 다 HUG 면 parent 도 HUG 강제.
    print("\n[규칙] HORIZONTAL row vertical HUG 강제 (FIXED 회귀, 2026-05-27) 적용 중...")
    try:
        _enforce_horizontal_row_hug_v_live(root_node_id)
    except Exception as e:
        print(f"  [hrow-hug-v] 실패 (무시하고 계속): {e}")

    # ⚠️ 시스템 규칙 (2026-05-27 사용자 명시): FAB 는 무조건 56×56 icon-only 원형.
    # blueprint 가 다른 크기로 작성했어도 live 에서 강제 교정.
    print("\n[규칙] FAB 56×56 크기 고정 (2026-05-27 절대 룰) 적용 중...")
    try:
        n_fab = _enforce_fab_size_live(root_node_id)
        if n_fab:
            print(f"  [fab-size] ✓ FAB {n_fab}건 56×56 + cornerRadius 28 강제")
        else:
            print("  [fab-size] OK — FAB 이미 56×56")
    except Exception as e:
        print(f"  [fab-size] 실패 (무시하고 계속): {e}")

    # 2026-05-28 사용자 명시 절대 룰: FAB 안 icon color = fg-light (#ffffff)
    # brand-solid 위 흰 아이콘이 정석. fg-white(alias) / 검정 / 임의색 회귀 차단.
    try:
        n_fab_ic = _enforce_fab_icon_color_live(root_node_id)
        if n_fab_ic:
            print(f"  [fab-icon-color] ✓ FAB 안 icon {n_fab_ic}개 → fg-light 강제 + 바인딩")
        else:
            print("  [fab-icon-color] OK — FAB icon 이미 fg-light")
    except Exception as e:
        print(f"  [fab-icon-color] 실패 (무시하고 계속): {e}")

    # 2026-05-28 사용자 명시 절대 룰: brand bg frame 안 icon 이 같은 brand 계열이면 invisible.
    # 사례: Hero Icon Box (bg-brand-solid 진한 보라) + piggy-bank Vector stroke (brand-primary 보라)
    # → 거의 안 보임. 자동 교정: 같은 brand hue 인 icon stroke/fill 을 white 로.
    print("\n[규칙] brand bg + icon contrast 자동 교정 (2026-05-28 절대 룰) 적용 중...")
    try:
        n_ic = _enforce_icon_on_brand_bg_contrast(root_node_id)
        if n_ic:
            print(f"  [icon-on-brand] ✓ brand bg 안 invisible icon {n_ic}개 → white 강제")
        else:
            print("  [icon-on-brand] OK — brand bg 안 icon 대비 충분")
    except Exception as e:
        print(f"  [icon-on-brand] 실패 (무시하고 계속): {e}")

    # 2026-06-04: blueprint instanceProperties(Hierarchy=Primary 등 variant flip) 적용.
    # create_component_instance 가 무시하므로 빌드 후 set_instance_properties 로 자동 적용.
    # ⚠️ 버튼 sizing/label 교정보다 *먼저* — variant flip 이 sizing/label 을 리셋할 수 있으니.
    print("\n[규칙] DS instance variant/prop 적용 (instanceProperties — Hierarchy/Color flip) 중...")
    try:
        _var_bp = injected_blueprint or original_blueprint
        if _var_bp is None:
            _latest_v = _load_latest_build()
            _vp = _latest_v.get("blueprintPath")
            if _vp and os.path.exists(_vp):
                with open(_vp) as _vf:
                    _var_bp = json.load(_vf)
        _variant_map = _collect_instance_variant_paths(_var_bp)
        n_var = _enforce_ds_instance_variants(root_node_id, _variant_map)
        if not n_var:
            print("  [ds-instance-variant] OK — instanceProperties 마커 없음")
        # 🧭 Tooltip arrow 가 실제 대상을 가리키도록 교정 (2026-06-04 사용자 룰).
        #    instanceProperties.Arrow 적용 직후 → _tooltipTarget 기반 방향/위치 정조준.
        _tt_targets = _collect_tooltip_targets(_var_bp)
        _enforce_tooltip_arrow_live(root_node_id, _tt_targets)
    except Exception as e:
        print(f"  [ds-instance-variant] 실패 (무시하고 계속): {e}")

    # 2026-05-28 사용자 "제일 중요한 컴포넌트는 버튼" — R23 가 버튼을 DS Action Button
    # 인스턴스로 auto-swap 하게 켰는데, DS 버튼이 공유 row 에서 1px 로 붕괴하거나
    # height 가 텍스트만큼 줄어드는 sizing 버그가 있음. 라이브에서 교정.
    print("\n[규칙] DS 버튼 sizing + icon off + label 교정 적용 중...")
    try:
        _btn_bp = original_blueprint
        if _btn_bp is None:
            _latest = _load_latest_build()
            _bp_path = _latest.get("blueprintPath")
            if _bp_path and os.path.exists(_bp_path):
                with open(_bp_path) as _f:
                    _btn_bp = json.load(_f)
        _label_map = _build_button_label_map(_btn_bp)
        n_btn = _enforce_ds_button_sizing(root_node_id, _label_map)
        if n_btn:
            print(f"  [ds-button-sizing] ✓ Action Button 인스턴스 {n_btn}건 교정 (sizing/icon/label)")
        else:
            print("  [ds-button-sizing] OK — DS 버튼 없음")
    except Exception as e:
        print(f"  [ds-button-sizing] 실패 (무시하고 계속): {e}")

    # 2026-05-28 사용자 절대 룰: "badge 에 stroke 은 없는거란다". swap 된 badge variant 가
    # outline(보더)을 들고 오거나 이전 룰이 brand 보더를 박았으면 일괄 제거. fill 은 불변.
    print("\n[규칙] DS Badge/Tag stroke 제거 (badge 는 보더 없음 — 절대 룰) 적용 중...")
    try:
        _enforce_badge_no_stroke_live(root_node_id)
    except Exception as e:
        print(f"  [badge-no-stroke] 실패 (무시하고 계속): {e}")

    # 2026-05-28 사용자 "엉망이다" — R23 가 raw frame(status-pill '진행중', round-tag
    # '1회차', link '자세히')을 DS Badge/Button/Link 인스턴스로 swap 한 뒤 원래 텍스트를
    # override 안 해 마스터 더미('Label'/'Button CTA'/'Click to Download')가 렌더됨.
    # inject 된 blueprint 의 instance 노드 _instanceText 를 경로 매칭으로 적용.
    print("\n[규칙] DS instance 텍스트 override (badge/button/link 더미 제거) 적용 중...")
    try:
        _inj_bp = injected_blueprint
        if _inj_bp is None:
            _latest = _load_latest_build()
            _bpp = _latest.get("blueprintPath")
            if _bpp and os.path.exists(_bpp):
                with open(_bpp) as _f:
                    _inj_bp = json.load(_f)
        _path_text_map = _collect_instance_text_paths(_inj_bp) if _inj_bp else {}
        n_it = _enforce_ds_instance_text(root_node_id, _path_text_map)
        if n_it:
            print(f"  [ds-instance-text] ✓ instance {n_it}건 텍스트 override (더미 제거)")
        else:
            print("  [ds-instance-text] OK — override 대상 없음")
    except Exception as e:
        print(f"  [ds-instance-text] 실패 (무시하고 계속): {e}")

    # DS "Horizontal tabs" 모드 탭 trim (2026-05-29 사용자 "Tabs 컴포넌트 써라" + "사이즈 왜케
    # 길지"). 컨테이너 인스턴스(탭 10개 고정)를 _dsModeTabs.labels 개수로 trim + 라벨 + HUG.
    # plugin set_node_visible 추가로 full 자동화. [[ds-mode-tabs-component]]
    print("\n[규칙] DS Horizontal tabs 모드 탭 trim/label 적용 중...")
    try:
        _mt_bp = injected_blueprint
        if _mt_bp is None:
            _latest = _load_latest_build()
            _bpp = _latest.get("blueprintPath")
            if _bpp and os.path.exists(_bpp):
                with open(_bpp) as _f:
                    _mt_bp = json.load(_f)
        _mt_cfg = _collect_mode_tabs_config(_mt_bp) if _mt_bp else None
        if _mt_cfg:
            _configure_ds_mode_tabs(root_node_id, _mt_cfg)
        else:
            print("  [mode-tabs] _dsModeTabs 마커 없음 — skip")
        # 절대규칙 0-P: 모든 Segmented_control 인스턴스 Size=md 무조건 강제 (마커 유무 무관).
        # _segLabels 마커 없이 hand-author 된 인스턴스도 md 가 되도록 — _configure 보다 먼저
        # 돌려 특수 size(_seg_cfg.size)가 있으면 그 뒤 _configure 가 덮어써 최종 권한을 갖게.
        _enforce_segmented_size_md_live(root_node_id)
        # Imin DS Segmented_control (_segLabels 마커) 자동 설정 — prop 기반
        _seg_cfg = _collect_seg_tabs_config(_mt_bp) if _mt_bp else None
        if _seg_cfg:
            _configure_segmented_control(root_node_id, _seg_cfg)
        # 절대 규칙 0-W (2026-06-12): DS Tool Bar 인스턴스 타이틀(_navTitle) 적용
        _tb_cfgs = _collect_tool_bar_configs(_mt_bp) if _mt_bp else []
        if _tb_cfgs:
            _configure_tool_bar(root_node_id, _tb_cfgs)
    except Exception as e:
        print(f"  [mode-tabs] 실패 (무시하고 계속): {e}")

    # ⚠️ HARD-ENFORCE (2026-05-28 사용자 명시 "룰 말고 무조건 실행 코드"):
    # cmd_post_fix 끝에 무조건 호출. 가드 최소화, 회귀 차단.
    try:
        _HARD_ENFORCE_IMIN_HOME_INVARIANTS(root_node_id)
    except Exception as e:
        print(f"  [HARD-ENFORCE] 실패 (무시): {e}")

    # ⚠️ 최종 강제 레이어 (2026-05-28 사용자 "FAB 또 찌그러져 / 회귀 누적"):
    # post-fix 의 모든 룰이 끝난 *가장 마지막* 에 고정 사이즈 invariant 를 순서 무관하게
    # 최종 보장. 중간 vertical-hug 룰이 FAB/circle 을 24px 로 되돌려도 여기서 복원.
    print("\n[최종 강제] FAB 56×56 / 원형 정원 고정 사이즈 invariant 적용 중...")
    try:
        n_inv = _enforce_fixed_size_invariants_final(root_node_id)
        print(f"  [size-invariant] ✓ 고정 사이즈 {n_inv}건 최종 강제" if n_inv
              else "  [size-invariant] OK — 찌그러진 고정 사이즈 노드 없음")
    except Exception as e:
        print(f"  [size-invariant] 실패 (무시): {e}")

    # ⚠️ 시스템 규칙 (2026-06-02 사용자 "버튼의 높이가 왜 다르지? 제일 큰거와 같아야 되"):
    # 하단 액션바의 버튼/아이콘 박스 높이를 가장 큰 것에 통일. ⚠️ size-invariant 의
    # icon-box(단일 자식) 정사각화가 한쪽 박스만 다시 키우는 충돌을 막기 위해 그 *뒤*에
    # 실행해 최종 권한을 갖는다.
    print("\n[규칙] 하단 액션바 버튼 높이 통일 (제일 큰 것에 맞춤) 적용 중...")
    try:
        _enforce_action_bar_equal_height(root_node_id)
    except Exception as e:
        print(f"  [action-bar-eq-h] 실패 (무시): {e}")

    # 🔴 FILL-in-HUG 텍스트 붕괴 복구 (2026-06-12): batch_build 의 'VERTICAL 부모 TEXT
    # 자동 FILL' 이 가로 HUG 부모 안에서는 순환 참조로 최소폭 붕괴('후기 공유' 세로
    # wrap)를 만든다. code.js 소스도 고쳤지만(플러그인 재실행 후 활성) 라이브 백스톱.
    print("\n[규칙] HUG 부모 안 TEXT FILL 붕괴 복구 적용 중...")
    try:
        _fix_text_fill_in_hug_parent_live(root_node_id)
    except Exception as e:
        print(f"  [text-fill-hug] 실패 (무시): {e}")

    # ⚠️ 시스템 규칙 (2026-06-04 사용자): 2-col FILL 붕괴 자동 복구 — HORIZONTAL row 의
    # FILL 컬럼이 1px 로 무너지고 형제가 전폭을 먹는 batch_build 버그 차단. 모든 sizing
    # 강제 *뒤*에 실행해 최종 균등 분배를 보장한다.
    print("\n[규칙] 2-col FILL 붕괴 복구 적용 중...")
    try:
        _enforce_multicol_fill_live(root_node_id)
    except Exception as e:
        print(f"  [multicol-fill] 실패 (무시): {e}")
    # 긴 텍스트가 좁은 컨테이너에 갇혀 글자단위 줄바꿈되는 붕괴 복원 (2026-06-18 — multicol 의
    # ≤3px 가드를 비껴가는 22px 대 텍스트 컨테이너 붕괴 차단. 카드 타이틀 세로 깨짐 회귀).
    try:
        _fix_collapsed_text_width_live(root_node_id)
    except Exception as e:
        print(f"  [collapsed-text] 실패 (무시): {e}")

    # 🔴 2026-06-05 사용자 룰: "CTA 버튼이 위 아래 연속적으로 있을땐 좀 더 덜 중요한 버튼의
    #    위계를 tertiary 나 outline 으로". 세로로 인접한 전폭 Primary CTA 위계 차등.
    #    ⚠️ 모든 width/sizing 강제(button-sizing·action-bar·multicol-fill) *뒤* 에 실행 —
    #    button-sizing 직후엔 set_layout_sizing(FILL) 리렌더 전이라 전폭 width 가 stale 해
    #    연속 CTA 를 못 잡는다(직접 호출은 잡힘). 트리 안정 후라야 신뢰성 있음.
    print("\n[규칙] 연속 전폭 CTA 위계 차등 (덜 중요한 Primary → Outline) 중...")
    try:
        n_cta = _enforce_consecutive_cta_hierarchy(root_node_id, injected_blueprint or original_blueprint)
        if not n_cta:
            print("  [cta-hierarchy] OK — 연속 Primary CTA 없음")
    except Exception as e:
        print(f"  [cta-hierarchy] 실패 (무시): {e}")

    # 🔴 2026-06-05 사용자 룰: "fab 버튼도 있는 화면에서 수평으로 연속된 버튼 같은 경우는
    #    성격까지 같다면 버튼 위계를 tertiary 로". 캐로셀 반복 동일 라벨 CTA → Tertiary.
    print("\n[규칙] 수평 반복 동일 성격 CTA 위계 (Tertiary) 적용 중...")
    try:
        n_ht = _enforce_horizontal_repeated_cta_tertiary(root_node_id)
        if not n_ht:
            print("  [cta-horiz-tertiary] OK — 수평 반복 동일 CTA 없음(또는 FAB 없는 화면)")
    except Exception as e:
        print(f"  [cta-horiz-tertiary] 실패 (무시): {e}")

    # ⚠️ 시스템 규칙 (2026-06-04 사용자 "프레임 안 텍스트 위아래 딱 붙으면 안 된다"):
    # 라운드 필 박스 안 라벨+값 텍스트가 세로 패딩 0 으로 모서리에 밀착하는 것 차단.
    # multicol-fill(패딩 잃는 FILL 박스 복구) *뒤*에 실행해 최종 여백을 보장.
    print("\n[규칙] 텍스트 박스 상하 여백 복원 적용 중...")
    try:
        _enforce_text_box_padding_live(root_node_id)
    except Exception as e:
        print(f"  [text-box-pad] 실패 (무시): {e}")

    # ⚠️ 시스템 규칙 (2026-05-28 사용자 "padding, gap 절대값인데 spacing- 토큰 바인딩 안돼. 박아"
    # / 2026-05-29 사용자 "primitive(Spacing/) 쓰면 안돼. 3. Spacing 의 spacing- 토큰으로 바인딩"):
    # 모든 레이아웃 강제가 끝난 *가장 마지막* 에 padding/gap 라이브 최종 값을 "3. Spacing"
    # 컬렉션의 시맨틱 spacing-* DS 변수에 바인딩. 스케일 정확 일치 값만 (시각 변화 0). 중간
    # 룰이 padding/gap 을 바꿔도 최종 값 기준이라 안전. 라이브 트리 기준.
    print("\n[규칙] padding/gap → 3. Spacing/spacing-* DS 변수 바인딩 적용 중...")
    try:
        _bind_spacing_tokens_live(root_node_id)
    except Exception as e:
        print(f"  [spacing-bind] 실패 (무시): {e}")

    # 🔴 2026-06-04 사용자: cornerRadius → radius-* DS 변수 바인딩 (개별 코너는 blueprint 값으로).
    print("\n[규칙] cornerRadius → radius-* DS 변수 바인딩 적용 중...")
    try:
        _bind_radius_tokens_live(root_node_id, injected_blueprint or original_blueprint)
    except Exception as e:
        print(f"  [radius-bind] 실패 (무시): {e}")

    # 🔴 2026-06-09 사용자: SVG 아이콘 VECTOR 의 리터럴 stroke/fill 색 → 가장 가까운 fg-* 토큰 바인딩.
    print("\n[규칙] 아이콘 stroke/fill 색 → fg-* DS 변수 바인딩 적용 중...")
    try:
        _bind_icon_color_tokens_live(root_node_id)
    except Exception as e:
        print(f"  [icon-color-bind] 실패 (무시): {e}")

    # 🔴 2026-06-09 사용자: 아이콘 프레임의 '보이지 않는 잔존 fill'(visibility off) 정리 패스.
    print("\n[규칙] 아이콘 프레임 숨은 fill 정리 적용 중...")
    try:
        _strip_icon_frame_hidden_fills_live(root_node_id)
    except Exception as e:
        print(f"  [icon-fill-strip] 실패 (무시): {e}")

    # ⚠️ 시스템 규칙 (2026-06-04): blueprint 가 명시한 FIXED 폭 + padding 을 **가장 마지막**
    # (spacing 바인더 *뒤*) 에 재단언 — enforcer/바인더가 FILL 로 늘리거나 paddingLeft 을
    # 0(spacing-none) 으로 만든 프레임(2-line Date Cell, Sched 카드)을 원래 값으로 복원.
    # 바인더 뒤라야 최종 권한을 갖는다(바인더가 다시 0 으로 만드는 회귀 차단).
    print("\n[규칙] blueprint 명시 FIXED 폭/padding 최종 복원 적용 중...")
    try:
        _fw_bp = injected_blueprint or original_blueprint
        if _fw_bp is None:
            _lt = _load_latest_build(); _fp = _lt.get("blueprintPath")
            if _fp and os.path.exists(_fp):
                with open(_fp) as _ff:
                    _fw_bp = json.load(_ff)
        _enforce_fixed_widths(root_node_id, _collect_fixed_widths(_fw_bp))
        _enforce_blueprint_padding(root_node_id, _collect_blueprint_padding(_fw_bp))
        _enforce_text_fill_live(root_node_id, _collect_text_fill_keys(_fw_bp))
    except Exception as e:
        print(f"  [fixed-width] 실패 (무시): {e}")

    # 절대규칙 0-O (2026-06-04): NavBar fill=bg-primary + 좌측 back btn stroke 제거.
    # cmd_post_fix 맨 끝(white-card-border *이후*)에서 — back btn 에 재부착된 border 를 제거.
    # (build 경로는 Step E.7.7 가 AUTO_FIX 뒤 한 번 더 적용해 최종 권한을 가짐.)
    print("\n[규칙] NavBar bg-primary + back btn stroke 제거 적용 중...")
    try:
        _enforce_navbar_style_live(root_node_id)
    except Exception as e:
        print(f"  [navbar] 실패 (무시): {e}")

    # 🔴 흰 카드 elevation — DS Shadows/shadow-basic 자동 바인딩 (2026-06-18 사용자: "표준으로
    # 박아줘, 빌드마다 자동"). drop-shadow strip *맨 뒤*에서 — 흰 면+보더 카드에 shadow-basic 적용.
    # 배너 placeholder(_noShadow/_placeholderAllowed) 제외, 월렛 등 개별코너 카드는 _cardShadow 강제.
    print("\n[규칙] 흰 카드 Shadows/shadow-basic elevation 적용 중...")
    try:
        _csf, _css = _collect_card_shadow_markers(injected_blueprint or original_blueprint or {})
        _apply_card_shadow_live(root_node_id, _csf, _css)
    except Exception as e:
        print(f"  [card-shadow] 실패 (무시): {e}")

    elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"POST-FIX 완료 — {elapsed:.1f}s")
    print(f"  FILL 수정: {fill_fixes}건")
    print(f"  Tab Bar/Stroke 수정: {tab_fixes}건")
    print(f"  텍스트 수정: {text_fixes}건")
    print(f"  루트 높이: {layout_result['root_height']}")
    _print_call_stats("post-fix")  # 2026-07-13 — 시간이 어디서 새는지 항상 로그에 남김
    print(f"{'='*50}\n")


# ── 자동 변수 바인딩 (cmd_build에 내장 — $token() blueprint → DS 변수) ──

def _token_to_figma_path(token_name: str) -> Optional[str]:
    """$token() 이름 → 변수 바인딩용 전체 figmaPath.

    ⚠️ 시스템 규칙:
    - '-alt' / '_alt' 변형 토큰은 기본 토큰으로 강제 정규화.
    - 마지막 세그먼트 '정확 일치' 우선 — bg-secondary 가 bg-secondary_alt 로
      오매칭되면 안 됨.
    """
    token_name = _strip_alt_token(token_name)
    tm = load_token_map()

    def _lookup_path(name: str) -> Optional[str]:
        info = tm.get(name)
        if info and info.get("figmaPath"):
            return info["figmaPath"]
        # Pass 1: 마지막 세그먼트 '정확 일치' 우선
        for path, info_item in tm.items():
            fp = info_item.get("figmaPath", path)
            seg = fp.rsplit("/", 1)[-1] if "/" in fp else fp
            if seg == name:
                return fp
        # Pass 2: 괄호 변형만 허용 — '_' prefix 매칭 절대 금지
        for path, info_item in tm.items():
            fp = info_item.get("figmaPath", path)
            seg = fp.rsplit("/", 1)[-1] if "/" in fp else fp
            if seg.startswith(name + " "):
                return fp
        return None

    hit = _lookup_path(token_name)
    if hit:
        return hit
    # Aqua 보조 액센트 — semantic 'Component colors/Utility/Aqua/utility-aqua-{N}' 우선
    # (VARIABLE_KEY_MAP 의 게시된 키로 K:import). TOKEN_MAP 엔 없으므로 경로를 직접 반환.
    aqua_path = _aqua_binding_path(token_name)
    if aqua_path:
        return aqua_path
    return None


_fontsize_map_cache: Optional[Dict[float, str]] = None

def _load_fontsize_map() -> Dict[float, str]:
    """fontSize 값 → figmaPath (예: 16.0 → 'fontSize/2')."""
    global _fontsize_map_cache
    if _fontsize_map_cache is not None:
        return _fontsize_map_cache
    out: Dict[float, str] = {}
    for k, v in load_token_map().items():
        if v.get("type") == "FONTSIZES":
            try:
                out[float(v["value"])] = v.get("figmaPath", k)
            except (ValueError, TypeError, KeyError):
                pass
    _fontsize_map_cache = out
    return out


_spacing_map_cache: Optional[Dict[float, str]] = None

def _load_spacing_map() -> Dict[float, str]:
    """spacing px 값 → 시맨틱 spacing 토큰 figmaPath (예: 8.0 → 'spacing-md').

    🔴 "3. Spacing" 컬렉션의 시맨틱 토큰(spacing-none/xxs/xs/sm/md/lg/xl/2xl...11xl)만
    사용한다. primitive 스케일('Spacing/5 (20px)' 등)은 **절대 금지** — 2026-05-29 사용자
    명시: "primitive 값(Spacing/) 쓰면 안돼. 3. Spacing 의 spacing- 토큰으로 바인딩해야 한다."
    figmaPath 가 소문자 'spacing-' 로 시작하는 토큰이 시맨틱(3. Spacing), 'Spacing/' 는 primitive.
    값 매핑: 0=none 2=xxs 4=xs 6=sm 8=md 12=lg 16=xl 20=2xl 24=3xl 32=4xl 40=5xl 48=6xl
            64=7xl 80=8xl 96=9xl 128=10xl 160=11xl (각 값 고유 — 충돌 없음).
    """
    global _spacing_map_cache
    if _spacing_map_cache is not None:
        return _spacing_map_cache
    out: Dict[float, str] = {}
    for k, v in load_token_map().items():
        fp = v.get("figmaPath", "")
        # 시맨틱 spacing 토큰만: figmaPath 가 소문자 'spacing-' 로 시작 (primitive 'Spacing/' 제외)
        if v.get("type") == "NUMBER" and isinstance(fp, str) and fp.startswith("spacing-"):
            try:
                out[float(v["value"])] = fp
            except (ValueError, TypeError, KeyError):
                pass
    _spacing_map_cache = out
    return out


# Figma node.setBoundVariable 가 지원하는 auto-layout spacing 필드
_SPACING_BIND_FIELDS = (
    "paddingLeft", "paddingRight", "paddingTop", "paddingBottom",
    "itemSpacing", "counterAxisSpacing",
)


def _collect_spacing_bindings(node: dict, spacing_map: Dict[float, str],
                              jobs: list, off_scale: set) -> None:
    """라이브 트리 1노드의 padding/gap 절대값 중 Spacing 토큰에 정확히 일치하는 것만 수집.

    순수 함수(네트워크 X) — 단위 테스트 가능. jobs/off_scale 를 in-place 갱신.
    - DS 인스턴스(type INSTANCE) + 인스턴스 내부 노드(id 에 ';') 는 제외 (컴포넌트가 spacing 제어).
    - layoutMode 가 HORIZONTAL/VERTICAL 인 frame 만 (auto-layout 아니면 padding/gap 무의미).
    - 스케일 밖 값(14/18/28 등)은 off_scale 에 기록 후 리터럴 유지 — 임의 snap 금지.
    """
    if not isinstance(node, dict):
        return
    nid = node.get("id") or ""
    ntype = (node.get("type") or "").upper()
    lm = (node.get("layoutMode") or "").upper()
    if ntype == "INSTANCE" or ";" in nid or lm not in ("HORIZONTAL", "VERTICAL"):
        return
    binds: Dict[str, str] = {}
    for field in _SPACING_BIND_FIELDS:
        val = node.get(field)
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            continue
        fv = round(float(val), 3)
        fp = spacing_map.get(fv)
        if fp is None and abs(fv - round(fv)) < 1e-6:
            fp = spacing_map.get(float(round(fv)))  # 20.0 vs 20 정규화
        if fp:
            binds[field] = fp
        elif fv > 0:
            off_scale.add(fv)
    if binds and nid:
        jobs.append({"nodeId": nid, "bindings": binds})


def _bind_spacing_tokens_live(root_id: str) -> int:
    """라이브 트리의 auto-layout padding/gap 절대값을 Spacing/* DS 변수에 바인딩.

    2026-05-28 사용자: "padding, gap 값이 그냥 절대값으로 들어가 있는데 spacing- 토큰이
    바인딩 되어있지않아. 바인딩 되게 시스템 수정해".

    post-fix 가 padding/gap 을 여러 단계에서 조정하므로 blueprint 값이 아닌 **라이브
    최종 값**을 읽어, 디자인 스케일에 정확히 일치하는 값만 매칭 Spacing 토큰에 바인딩한다
    (토큰 value == 현재 값 이므로 시각 변화 0). 스케일 밖 값(14/18/28 등)은 리터럴 유지 —
    임의 snap 으로 사용자가 막 승인한 레이아웃을 바꾸지 않는다.

    cmd_post_fix 끝에서 자동 호출 → 새 세션/standalone post-fix 모두 커버.
    """
    spacing_map = _load_spacing_map()
    if not spacing_map:
        print("  [spacing-bind] Spacing 토큰 없음 — skip")
        return 0
    try:
        tree = _collect_tree(root_id)
    except Exception as e:
        print(f"  [spacing-bind] 트리 수집 실패: {e}")
        return 0

    jobs: list = []
    off_scale: set = set()

    def _walk(n: dict):
        _collect_spacing_bindings(n, spacing_map, jobs, off_scale)
        for c in (n.get("_children_full") or []):
            _walk(c)
    _walk(tree)

    if not jobs:
        print("  [spacing-bind] 바인딩할 on-scale spacing 값 없음")
        return 0

    ok = 0
    field_count = 0
    for i, job in enumerate(jobs):
        try:
            call_tool("set_bound_variables",
                      {"nodeId": job["nodeId"], "bindings": job["bindings"]},
                      msg_id=i + 1)
            ok += 1
            field_count += len(job["bindings"])
        except Exception as e:
            if ok < 3:
                print(f"    [spacing-bind] FAIL {job['nodeId']}: {e}")
    print(f"  [spacing-bind] ✓ spacing 토큰 바인딩 — {ok}개 노드 / {field_count}개 필드 "
          f"(padding·gap 절대값 → 3. Spacing/spacing-*)")
    if off_scale:
        vals = ", ".join(
            str(int(v) if float(v).is_integer() else v) for v in sorted(off_scale))
        print(f"  [spacing-bind] ⚠️ 스케일 밖 값(토큰 없음, 리터럴 유지): {vals}px "
              f"— 스케일(2/4/6/8/12/16/20/24/32...)로 맞추면 바인딩됨")
    return ok


_radius_map_cache: Optional[Dict[float, str]] = None
# Figma node.setBoundVariable 가 지원하는 코너 radius 필드 (개별 코너만 바인딩 가능)
_RADIUS_BIND_FIELDS = ("topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius")


def _load_radius_map() -> Dict[float, str]:
    """radius px 값 → 시맨틱 radius 토큰 figmaPath (예: 14.0 → 'radius-xl').

    🔴 2026-06-04 사용자: "radius값 토큰 바인딩 안해? radius- 로 시작하는 토큰 있다."
    figmaPath 가 소문자 'radius-' 로 시작하는 NUMBER 토큰만 사용.
    값: 0=none 4=xxs 6=xs 8=sm 10=md 12=lg 14=xl 16=2xl 20=3xl 24=4xl 28=5xl 32=6xl 9999=full.
    """
    global _radius_map_cache
    if _radius_map_cache is not None:
        return _radius_map_cache
    out: Dict[float, str] = {}
    for _k, v in load_token_map().items():
        fp = v.get("figmaPath", "")
        if v.get("type") == "NUMBER" and isinstance(fp, str) and fp.startswith("radius-"):
            try:
                out[float(v["value"])] = fp
            except (ValueError, TypeError, KeyError):
                pass
    _radius_map_cache = out
    return out


def _radius_token_for(val: float, radius_map: Dict[float, str]) -> Optional[str]:
    """radius 값에 정확히 일치하는 radius 토큰 figmaPath. 없으면 None.

    예외: '완전 둥근'(>=100, 예 999/9999 류)은 radius-full 로 — Figma 가 절반-사이즈로
    clamp 하므로 999·9999 가 시각적으로 동일(둘 다 pill/원형). 그 외 스케일 밖은 None(리터럴 유지).
    """
    fv = round(float(val), 3)
    fp = radius_map.get(fv)
    if fp is None and abs(fv - round(fv)) < 1e-6:
        fp = radius_map.get(float(round(fv)))
    if fp:
        return fp
    if fv >= 100:  # 완전 둥근 convention → radius-full
        full = radius_map.get(9999.0)
        if full:
            return full
    return None


def _collect_radius_corners_bp(blueprint: Optional[dict]) -> dict:
    """blueprint 에서 개별 코너 radius 를 쓰는 frame 의 {이름경로: {corner_field: value}} 수집.

    get_nodes_info 가 개별 코너(topLeftRadius 등)를 None 으로 직렬화해 라이브로 못 읽으므로,
    개별 코너 binding 은 blueprint 값으로 한다(uniform cornerRadius 는 라이브로 읽음).
    """
    out = {}
    if not isinstance(blueprint, dict):
        return out
    root = blueprint.get("root") or blueprint

    def walk(n, chain):
        if not isinstance(n, dict):
            return
        cur = chain + (n.get("name") or "",)
        if (n.get("type") or "frame").lower() == "frame":
            cr = n.get("cornerRadius")
            cr = cr if isinstance(cr, (int, float)) and not isinstance(cr, bool) else None
            indiv = {f: n.get(f) for f in _RADIUS_BIND_FIELDS
                     if isinstance(n.get(f), (int, float)) and not isinstance(n.get(f), bool)}
            if indiv:
                d = {}
                for f in _RADIUS_BIND_FIELDS:
                    d[f] = indiv.get(f, cr if cr is not None else 0)
                if any(v > 0 for v in d.values()):
                    out[cur] = d
        for c in (n.get("children") or n.get("_originalChildren") or []):
            walk(c, cur)
    walk(root, ())
    return out


def _bind_radius_tokens_live(root_id: str, blueprint: Optional[dict] = None) -> int:
    """라이브 트리의 cornerRadius 를 radius-* DS 변수에 바인딩 (2026-06-04 사용자 룰).

    spacing 바인딩과 동형: 토큰 value == 현재 radius 라 시각 변화 0. uniform cornerRadius 는
    라이브 값으로, 개별 코너(시트 top 16 등)는 blueprint 값으로 매칭. 스케일 밖(999 제외)은
    리터럴 유지. DS INSTANCE·인스턴스 내부('I…;…')는 제외(컴포넌트가 radius 제어).
    """
    radius_map = _load_radius_map()
    if not radius_map:
        print("  [radius-bind] radius 토큰 없음 — skip")
        return 0
    bp_corners = _collect_radius_corners_bp(blueprint)
    try:
        tree = _collect_tree(root_id)
    except Exception as e:
        print(f"  [radius-bind] 트리 수집 실패: {e}")
        return 0

    jobs: list = []
    off_scale: set = set()

    def walk(n, chain):
        if not isinstance(n, dict):
            return
        cur = chain + (n.get("name") or "",)
        nid = n.get("id") or ""
        ntype = (n.get("type") or "").upper()
        if ntype != "INSTANCE" and ";" not in nid:
            corners = {}
            cr = n.get("cornerRadius")
            if isinstance(cr, (int, float)) and not isinstance(cr, bool) and cr > 0:
                for f in _RADIUS_BIND_FIELDS:
                    corners[f] = cr
            elif cur in bp_corners:
                corners = dict(bp_corners[cur])
            if corners:
                binds = {}
                for f, val in corners.items():
                    fp = _radius_token_for(val, radius_map)
                    if fp:
                        binds[f] = fp
                    elif val > 0:
                        off_scale.add(round(float(val), 3))
                if binds and nid:
                    jobs.append({"nodeId": nid, "bindings": binds})
        for c in (n.get("_children_full") or []):
            walk(c, cur)
    walk(tree, ())

    if not jobs:
        print("  [radius-bind] 바인딩할 on-scale radius 값 없음")
        return 0

    ok = 0
    field_count = 0
    for i, job in enumerate(jobs):
        try:
            call_tool("set_bound_variables",
                      {"nodeId": job["nodeId"], "bindings": job["bindings"]}, msg_id=i + 1)
            ok += 1
            field_count += len(job["bindings"])
        except Exception as e:
            if ok < 3:
                print(f"    [radius-bind] FAIL {job['nodeId']}: {e}")
    print(f"  [radius-bind] ✓ radius 토큰 바인딩 — {ok}개 노드 / {field_count}개 코너 "
          f"(cornerRadius → radius-*)")
    if off_scale:
        vals = ", ".join(str(int(v) if float(v).is_integer() else v) for v in sorted(off_scale))
        print(f"  [radius-bind] ⚠️ 스케일 밖 값(토큰 없음, 리터럴 유지): {vals}px "
              f"— 스케일(4/6/8/10/12/14/16/20/24/28/32)로 맞추면 바인딩됨")
    return ok


_fg_color_palette_cache: Optional[list] = None
# 아이콘 색을 fg-* 토큰으로 스냅할 최대 L1 거리 (RGB 0-1, 합산 max 3). 이내면 nearest 바인딩.
_ICON_COLOR_SNAP_THRESH = 0.30
# createNodeFromSvg 가 만드는 아이콘 path 노드 타입 (DS 인스턴스/장식 RECT·ELLIPSE 제외).
_ICON_VECTOR_TYPES = frozenset({"VECTOR", "LINE", "STAR", "POLYGON", "BOOLEAN_OPERATION"})


def _load_fg_color_palette() -> list:
    """아이콘 색 매칭용 팔레트 — Colors/Foreground/fg-* COLOR 토큰만 [(figmaPath,(r,g,b))].

    아이콘(svg_icon VECTOR)의 stroke/fill 은 fg-* 전경색이 정답이라, 전경 팔레트에서만
    nearest 매칭한다(text-/gray primitive 와 hex 가 겹쳐도 시맨틱하게 fg-* 로 바인딩).
    '-alt'(규칙 0-B)·'_hover'(정적 아이콘 무관) 변형은 제외.
    """
    global _fg_color_palette_cache
    if _fg_color_palette_cache is not None:
        return _fg_color_palette_cache
    out: list = []
    seen: set = set()
    for _k, v in load_token_map().items():
        if v.get("type") != "COLOR":
            continue
        fp = v.get("figmaPath", "")
        if not isinstance(fp, str) or not fp.startswith("Colors/Foreground/fg-"):
            continue
        low = fp.lower()
        if low.endswith("_alt") or "_hover" in low or fp in seen:
            continue
        try:
            c = hex_to_rgba(v["value"])
        except (KeyError, ValueError, TypeError):
            continue
        seen.add(fp)
        out.append((fp, (c["r"], c["g"], c["b"])))
    _fg_color_palette_cache = out
    return out


def _fg_token_rank(fp: str) -> int:
    """동일 hex fg 토큰 간 tiebreak 우선순위 (낮을수록 선호).

    fg-tertiary 와 fg-disabled 처럼 **값이 같은**(#b1b6be) 토큰이 있어, 거리가 동률일 때
    상태/엣지 토큰보다 코어 전경 tier 를 우선한다(아이콘은 상태색보다 일반 전경이 정답).
    """
    name = fp.rsplit("/", 1)[-1].lower()
    if "disabled" in name or "quaternary" in name:
        return 2  # 상태/거의-흰 엣지
    if any(s in name for s in ("brand", "success", "warning", "error")):
        return 1  # 시맨틱 액센트
    return 0      # 코어: primary/secondary/tertiary/light/dark


def _nearest_fg_token(rgb: tuple, palette: list) -> tuple:
    """rgb(0-1)에 L1 거리가 가장 가까운 fg-* 토큰 figmaPath + 거리. (None, 9.0) if 팔레트 빔.

    거리 동률(같은 hex)이면 `_fg_token_rank` 로 코어 tier 우선(disabled/quaternary 회피).
    """
    best = None
    best_key = (9.0, 9)
    for fp, prgb in palette:
        d = abs(rgb[0] - prgb[0]) + abs(rgb[1] - prgb[1]) + abs(rgb[2] - prgb[2])
        key = (round(d, 4), _fg_token_rank(fp))
        if key < best_key:
            best_key = key
            best = fp
    return best, best_key[0]


def _first_visible_solid_paint(paints: Any) -> Optional[dict]:
    """paints 배열의 첫 visible SOLID paint(color 보유). 없으면 None."""
    if not isinstance(paints, list):
        return None
    for p in paints:
        if (isinstance(p, dict) and p.get("type") == "SOLID"
                and p.get("visible", True) and isinstance(p.get("color"), dict)):
            return p
    return None


def _paint_already_bound(node: dict, paint: dict, kind: str) -> bool:
    """node/paint 의 boundVariables 로 이미 변수에 묶인 paint 인지 판정 (kind: 'fills'|'strokes')."""
    nbv = node.get("boundVariables")
    if isinstance(nbv, dict) and nbv.get(kind):
        return True
    pbv = paint.get("boundVariables") if isinstance(paint, dict) else None
    if isinstance(pbv, dict) and pbv.get("color"):
        return True
    return False


def _bind_icon_color_tokens_live(root_id: str) -> int:
    """SVG 아이콘(VECTOR) 의 리터럴 stroke/fill 색을 가장 가까운 fg-* DS 토큰에 바인딩.

    🔴 2026-06-09 사용자: "아이콘 frame 안 vector 의 stroke color 바인딩이 안 됨 → svg 삽입
    시 가장 가까운 컬러로 바인딩하는 프로세스 추가." code.js `colorizeVectors` 가 아이콘 색을
    리터럴 RGB 로 박아(예 #2c3744) 변수에 안 묶이던 회귀를 라이브에서 교정.

    - 대상: VECTOR/LINE/STAR/POLYGON/BOOLEAN_OPERATION (createNodeFromSvg 아이콘 path).
    - fg-* 전경 팔레트에서 nearest(L1) 매칭. 거리 ≤ 0.30 만 바인딩(아이콘은 DS 색이라 ≈0,
      시각 변화 0 — spacing/radius 바인더와 동형). 그보다 먼 색은 리터럴 유지.
    - 이미 바인딩된 paint·DS INSTANCE·인스턴스 내부(';') 는 skip (규칙 0-K 컴포넌트 색 보호).
    """
    palette = _load_fg_color_palette()
    if not palette:
        print("  [icon-color-bind] fg-* 토큰 없음 — skip")
        return 0
    try:
        tree = _collect_tree(root_id)
    except Exception as e:
        print(f"  [icon-color-bind] 트리 수집 실패: {e}")
        return 0

    jobs: list = []         # set_bound_variables 잡
    clear_jobs: list = []   # 🔴 stroke 아이콘의 spurious fill 제거 잡
    off_palette: list = []

    def walk(n: dict):
        if not isinstance(n, dict):
            return
        nid = n.get("id") or ""
        ntype = (n.get("type") or "").upper()
        if ntype in _ICON_VECTOR_TYPES and ";" not in nid:
            binds: Dict[str, str] = {}
            stroke_paint = _first_visible_solid_paint(n.get("strokes"))
            fill_list = n.get("fills")
            fill_paint = _first_visible_solid_paint(fill_list)
            # 🔴 2026-06-09 사용자: "월렛 아이콘은 stroke 아이콘이야" — Untitled UI 아이콘은
            # stroke 기반이고 내부는 투명이어야 한다. visible stroke 가 있으면 stroke 아이콘으로
            # 보고 stroke 만 fg-* 에 바인딩, fill(있으면 spurious 흰 내부)은 제거한다.
            # stroke 없이 fill 만 있으면 fill 아이콘으로 보고 fill 을 바인딩.
            if stroke_paint is not None:
                if not _paint_already_bound(n, stroke_paint, "strokes"):
                    c = stroke_paint["color"]
                    rgb = (c.get("r", 0), c.get("g", 0), c.get("b", 0))
                    fp, d = _nearest_fg_token(rgb, palette)
                    if fp and d <= _ICON_COLOR_SNAP_THRESH:
                        binds["strokes/0"] = fp
                    elif fp:
                        off_palette.append(round(d, 2))
                # stroke 아이콘에 fill 이 하나라도 있으면 제거 (내부 투명 — 배경이 비쳐야)
                if isinstance(fill_list, list) and fill_list and nid:
                    clear_jobs.append(nid)
            elif fill_paint is not None:
                if not _paint_already_bound(n, fill_paint, "fills"):
                    c = fill_paint["color"]
                    rgb = (c.get("r", 0), c.get("g", 0), c.get("b", 0))
                    fp, d = _nearest_fg_token(rgb, palette)
                    if fp and d <= _ICON_COLOR_SNAP_THRESH:
                        binds["fills/0"] = fp
                    elif fp:
                        off_palette.append(round(d, 2))
            if binds and nid:
                jobs.append({"nodeId": nid, "bindings": binds})
        if ntype == "INSTANCE":
            return  # DS 인스턴스 내부는 variant 가 색 제어 — 건드리지 않음
        for c in (n.get("_children_full") or []):
            walk(c)
    walk(tree)

    if not jobs and not clear_jobs:
        print("  [icon-color-bind] 바인딩/정리할 아이콘 색 없음")
        return 0

    ok = 0
    field_count = 0
    for i, job in enumerate(jobs):
        try:
            call_tool("set_bound_variables",
                      {"nodeId": job["nodeId"], "bindings": job["bindings"]},
                      msg_id=i + 1)
            ok += 1
            field_count += len(job["bindings"])
        except Exception as e:
            if ok < 3:
                print(f"    [icon-color-bind] FAIL {job['nodeId']}: {e}")
    # stroke 아이콘의 spurious fill 제거 (clear → node.fills=[])
    cleared = 0
    for i, nid in enumerate(clear_jobs):
        try:
            call_tool("set_fill_color",
                      {"nodeId": nid, "r": 0, "g": 0, "b": 0, "a": 0, "clear": True},
                      msg_id=i + 1)
            cleared += 1
        except Exception as e:
            if cleared < 3:
                print(f"    [icon-color-bind] fill clear FAIL {nid}: {e}")
    print(f"  [icon-color-bind] ✓ 아이콘 색 — 바인딩 {ok}개 노드/{field_count} paint (stroke·fill "
          f"→ fg-*) + stroke 아이콘 spurious fill 제거 {cleared}개")
    if off_palette:
        ex = ", ".join(str(v) for v in sorted(set(off_palette))[:3])
        print(f"  [icon-color-bind] ⚠️ fg 팔레트와 거리 먼 색 {len(off_palette)}건 리터럴 유지 "
              f"(L1 dist 예: {ex} > {_ICON_COLOR_SNAP_THRESH})")
    return ok


def _is_svg_icon_frame(n: dict) -> bool:
    """svg_icon wrapper FRAME 인지 판정 — 작은 정사각 + 자식이 모두 vector 계열(VECTOR 1개 이상).

    `_bind_icon_color_tokens_live` 의 VECTOR 타겟과 짝. 여기선 그 vector 들을 감싼 FRAME 을 잡아
    숨은 잔존 fill 을 정리한다. ELLIPSE/RECTANGLE 도 허용(일부 SVG 가 섞어 씀)하되 VECTOR 가
    하나는 있어야 함(순수 장식 도형 묶음 제외).
    """
    if (n.get("type") or "").upper() != "FRAME":
        return False
    kids = n.get("_children_full") or n.get("children") or []
    if not kids:
        return False
    allowed = _ICON_VECTOR_TYPES | {"ELLIPSE", "RECTANGLE"}
    if not all((c.get("type") or "").upper() in allowed for c in kids):
        return False
    if not any((c.get("type") or "").upper() in _ICON_VECTOR_TYPES for c in kids):
        return False
    bb = n.get("absoluteBoundingBox") or {}
    w = bb.get("width") or n.get("width") or 0
    h = bb.get("height") or n.get("height") or 0
    return bool(w and h and max(w, h) <= 64 and 0.6 <= (w / h) <= 1.67)


def _is_stretched_icon_frame(n: dict) -> bool:
    """아이콘 프레임이 *비정사각으로 변형*됐는지 판정 (FILL 로 늘어남 / 한 축 붕괴).

    `_is_svg_icon_frame` 과 달리 **정사각 제약을 두지 않는다** — 변형된 아이콘(예 134×28)을
    잡는 게 목적이다. 자식이 모두 vector 계열(VECTOR ≥1) + 작은 축이 아이콘 범위(≤64) +
    |w−h|>6(명백히 비정사각). `_enforce_fixed_size_invariants_final` 의 정사각 복원 대상.
    """
    if (n.get("type") or "").upper() != "FRAME":
        return False
    kids = n.get("_children_full") or n.get("children") or []
    if not kids:
        return False
    allowed = _ICON_VECTOR_TYPES | {"ELLIPSE", "RECTANGLE"}
    if not all((c.get("type") or "").upper() in allowed for c in kids):
        return False
    if not any((c.get("type") or "").upper() in _ICON_VECTOR_TYPES for c in kids):
        return False
    w, h = _node_wh(n)
    if not (isinstance(w, (int, float)) and isinstance(h, (int, float)) and w and h):
        return False
    return min(w, h) <= 64 and abs(w - h) > 6


def _strip_icon_frame_hidden_fills_live(root_id: str) -> int:
    """svg_icon 프레임에 남은 '보이지 않는 fill'(visibility off 잔존 paint)을 제거.

    🔴 2026-06-09 사용자: 아이콘 프레임 fill 이 토큰에 바인딩됐지만 visibility off 라 무의미
    (실제 색은 내부 VECTOR stroke 가 담당). 이 숨은 fill 을 비워(set_fill_color clear) 패널을
    깔끔하게 한다. **보이지 않는(visible=false) fill 만** 지우므로 시각 변화 0. 보이는 fill 은
    의도된 배경일 수 있어 손대지 않는다. DS INSTANCE·내부(';') 제외.
    """
    try:
        tree = _collect_tree(root_id)
    except Exception as e:
        print(f"  [icon-fill-strip] 트리 수집 실패: {e}")
        return 0

    targets: list = []

    def walk(n: dict):
        if not isinstance(n, dict):
            return
        nid = n.get("id") or ""
        ntype = (n.get("type") or "").upper()
        if ntype != "INSTANCE" and ";" not in nid and _is_svg_icon_frame(n):
            fills = n.get("fills")
            # 모든 fill paint 가 '보이지 않음'(visible=false) → 잔존 junk
            if (isinstance(fills, list) and fills
                    and all(isinstance(p, dict) and p.get("visible") is False for p in fills)):
                targets.append(nid)
        if ntype == "INSTANCE":
            return
        for c in (n.get("_children_full") or []):
            walk(c)
    walk(tree)

    if not targets:
        print("  [icon-fill-strip] 정리할 숨은 아이콘 fill 없음")
        return 0

    ok = 0
    for i, nid in enumerate(targets):
        try:
            call_tool("set_fill_color",
                      {"nodeId": nid, "r": 0, "g": 0, "b": 0, "a": 0, "clear": True},
                      msg_id=i + 1)
            ok += 1
        except Exception as e:
            if ok < 3:
                print(f"    [icon-fill-strip] FAIL {nid}: {e}")
    print(f"  [icon-fill-strip] ✓ 숨은 아이콘 프레임 fill 정리 — {ok}개 프레임 (보이지 않는 fill 제거)")
    return ok


def _collect_bindings(bp_node: Any, built_node: Any, out: list, by_name: bool = False):
    """원본 blueprint + 빌드된 트리를 구조로 병렬 walk하며 변수 바인딩을 수집.

    bp_node: 원본 blueprint 노드 ($token() 참조 유지본)
    built_node: get_node_info 노드 (실제 'id' 보유)
    by_name=True: 루트 직계 자식은 이름으로 매칭 (Status Bar/로고 교체로 인덱스가 밀릴 수 있음)
    """
    if not isinstance(bp_node, dict) or not isinstance(built_node, dict):
        return
    node_id = built_node.get("id")
    binds: Dict[str, str] = {}
    # 🔴 DS 인스턴스(badge/button/tag 등)는 fill/stroke 를 master/variant 가 제어한다 —
    # 절대 색을 rebind 하지 않는다 (2026-05-28 사용자 절대 규칙: "badge fill color
    # 바꾸지마! 오직 Props 에 color option 만 선택"). R23 가 swap 한 badge 노드가
    # blueprint 에 fill 필드를 남겨도 여기서 fills/0 을 덮으면 variant 색이 깨진다.
    # ⚠️ 2026-06-01: original_blueprint 는 R23 inject **전** deep-copy 라 swap 마커
    # (componentKey/_dsResolvedRole)가 없다. 그래서 bp_node 만 보면 swap 된 badge 를
    # raw frame 으로 오인해 variant fill 을 덮어쓴다(사용자: "badge color 맘대로 수정").
    # → **빌드된 노드가 INSTANCE 이면 무조건 색 rebind 금지** (원본 상태 무관).
    is_ds_instance = ((bp_node.get("type") or "").lower() == "instance"
                      or bool(bp_node.get("componentKey"))
                      or bool(bp_node.get("_dsResolvedRole"))
                      or (built_node.get("type") or "").upper() == "INSTANCE")
    # 🔴 2026-06-09 사용자: svg_icon 의 색은 **내부 VECTOR 의 stroke/fill** 에 있다(프레임 fill 아님).
    # iconColor 를 아이콘 프레임 fills/0 에 바인딩하면 '보이지 않는 프레임 fill'(visibility off)에
    # 묶여 무의미하고, 정작 보이는 vector stroke 는 리터럴로 남는다. → icon-like 노드는 iconColor
    # 의 프레임 fill 바인딩을 건너뛰고, post-fix `_bind_icon_color_tokens_live` 가 내부 VECTOR
    # stroke/fill 을 fg-* 토큰에 바인딩하게 둔다.
    _bp_type_l = (bp_node.get("type") or "").lower()
    is_icon_node = (_bp_type_l in ("icon", "svg_icon")
                    or bool(bp_node.get("iconName")) or bool(bp_node.get("svgData")))
    if not is_ds_instance:
        # 색상: fill/stroke/strokeColor/fontColor/iconColor → fills/0 · strokes/0
        # ⚠️ strokeColor 도 stroke 와 동일 처리 (blueprint 가 둘 다 사용 — 2026-05-27 사용자 분노 fix)
        for field, prop in (("fill", "fills/0"), ("stroke", "strokes/0"),
                            ("strokeColor", "strokes/0"),
                            ("fontColor", "fills/0"), ("iconColor", "fills/0")):
            if field == "iconColor" and is_icon_node:
                continue  # 아이콘 색은 vector stroke 바인더가 처리 (프레임 fill 바인딩 금지)
            val = bp_node.get(field)
            if isinstance(val, str) and val.startswith("$token(") and val.endswith(")"):
                tname = val[7:-1]
                # 텍스트 색상은 반드시 Colors/Text/text-* 토큰 — fg-* 가 오면 text-* 로 자동 교정
                if field == "fontColor" and tname.startswith("fg-"):
                    cand = "text-" + tname[3:]
                    if _token_to_figma_path(cand):
                        tname = cand
                fp = _token_to_figma_path(tname)
                if fp:
                    binds[prop] = fp  # call_tool 이 K:{key} 로 중앙 변환
        # 타이포: fontSize → fontSize/k 변수
        fs = bp_node.get("fontSize")
        if isinstance(fs, (int, float)):
            fp = _load_fontsize_map().get(float(fs))
            if fp:
                binds["fontSize"] = fp  # call_tool 이 K:{key} 로 중앙 변환
    if node_id and binds:
        out.append({"nodeId": node_id, "bindings": binds})
    # DS 인스턴스 내부(variant 가 제어)는 재귀하지 않는다 — 내부 TEXT/도형 색을
    # rebind 하면 variant 가 깨진다 (badge/button 색 보호, 2026-06-01).
    if (built_node.get("type") or "").upper() == "INSTANCE":
        return
    # 자식 재귀
    bp_children = bp_node.get("children") or []
    built_children = built_node.get("children") or []
    if by_name:
        buckets: Dict[str, list] = {}
        for bc in built_children:
            buckets.setdefault(bc.get("name"), []).append(bc)
        used: Dict[str, int] = {}
        for bpc in bp_children:
            nm = bpc.get("name")
            lst = buckets.get(nm, [])
            k = used.get(nm, 0)
            if k < len(lst):
                _collect_bindings(bpc, lst[k], out, by_name=False)
                used[nm] = k + 1
    else:
        for i, bpc in enumerate(bp_children):
            if i < len(built_children):
                _collect_bindings(bpc, built_children[i], out, by_name=False)


# ── imageQuery → 실사진 자동 적용 ────────────────────────────────
_IMG_STOPWORDS = {
    "premium", "photography", "photo", "product", "minimal", "vibrant",
    "colorful", "morning", "luxury", "professional", "quality", "high",
    "modern", "clean", "aesthetic", "background", "studio", "shot", "image",
    "the", "a", "of", "and", "with",
}


def _imagequery_to_keywords(query: str, max_kw: int = 3) -> str:
    """imageQuery 문구 → loremflickr 콤마 태그 (stopword 제거 후 앞 N 단어)."""
    toks = [t.strip().lower() for t in re.split(r"[\s,]+", query or "") if t.strip()]
    kept = [t for t in toks if t not in _IMG_STOPWORDS and len(t) > 1]
    if not kept:
        kept = toks[:max_kw] or ["product"]
    return ",".join(kept[:max_kw])


def _collect_image_queries(bp_node: Any, built_node: Any, out: list, by_name: bool = False):
    """blueprint + 빌드 트리 병렬 walk — imageQuery 있는 노드의 live id + placeholder
    icon 자식 id 수집. (이미지 frame 안 vector/icon placeholder 는 실사진 적용 후 삭제)"""
    if not isinstance(bp_node, dict) or not isinstance(built_node, dict):
        return
    q = bp_node.get("imageQuery") or bp_node.get("imageUrl") or bp_node.get("image")
    if isinstance(q, str) and q.strip():
        placeholder_ids = []
        for ch in built_node.get("children") or []:
            ct = (ch.get("type") or "").upper()
            if ct in ("VECTOR", "INSTANCE", "FRAME") and ch.get("id"):
                placeholder_ids.append(ch["id"])
        out.append({"nodeId": built_node.get("id"), "query": q.strip(),
                    "placeholders": placeholder_ids})
    bp_children = bp_node.get("children") or []
    built_children = built_node.get("children") or []
    if by_name:
        buckets: Dict[str, list] = {}
        for bc in built_children:
            buckets.setdefault(bc.get("name"), []).append(bc)
        used: Dict[str, int] = {}
        for bpc in bp_children:
            nm = bpc.get("name")
            lst = buckets.get(nm, [])
            k = used.get(nm, 0)
            if k < len(lst):
                _collect_image_queries(bpc, lst[k], out, by_name=False)
                used[nm] = k + 1
    else:
        for i, bpc in enumerate(bp_children):
            if i < len(built_children):
                _collect_image_queries(bpc, built_children[i], out, by_name=False)


def apply_image_queries(root_id: str, original_blueprint: dict) -> int:
    """imageQuery 노드에 실사진 자동 적용 (2026-05-28 사용자 "placeholder 보라 블록도 실사진으로").

    keyless 키워드 이미지 소스(loremflickr, Flickr CC)에서 imageQuery 키워드로
    사진을 받아 set_image_fill 로 적용 + placeholder icon 자식 삭제. 네트워크 실패
    시 조용히 skip(placeholder 유지). cmd_build / cmd_post_fix 에서 자동 호출.
    """
    import base64 as _b64
    import urllib.request as _ur
    try:
        content = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(content).get("json")
        built = items[0].get("document") or items[0] if isinstance(items, list) and items else None
    except Exception as e:
        print(f"  [apply-images] 빌드 트리 조회 실패: {e}")
        return 0
    if not isinstance(built, dict) or not isinstance(original_blueprint, dict):
        return 0

    jobs: list = []
    _collect_image_queries(original_blueprint, built, jobs, by_name=True)
    if not jobs:
        return 0

    applied = 0
    for job in jobs:
        nid = job.get("nodeId")
        if not nid:
            continue
        kw = _imagequery_to_keywords(job.get("query", ""))
        # loremflickr 가 콤마 다중태그 URL 에 HTTP 500 을 반환하는 회귀(2026-05-29 확인) —
        # 다중태그 → 단일태그 폴백 체인으로 graceful degrade. 마지막은 항상 단일 'product'.
        first_kw = kw.split(",")[0] if kw else "product"
        url_candidates = []
        for c in (kw, first_kw, "product"):
            u = f"https://loremflickr.com/600/600/{c}"
            if u not in url_candidates:
                url_candidates.append(u)
        data = None
        used_url = None
        for url in url_candidates:
            try:
                req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                buf = _ur.urlopen(req, timeout=25).read()
                if len(buf) < 2000:  # 에러 페이지/빈 이미지
                    continue
                data = buf
                used_url = url
                break
            except Exception as e:
                last_err = e
                continue
        if not data:
            print(f"  [apply-images] '{kw}' {nid} 실패(placeholder 유지): {last_err if 'last_err' in dir() else 'no image'}")
            continue
        try:
            b64 = _b64.b64encode(data).decode()
            call_tool("set_image_fill", {"nodeId": nid, "imageData": b64})
            # placeholder icon 자식 제거 (실사진 위 보라 gift 아이콘 등)
            for pid in job.get("placeholders") or []:
                try:
                    call_tool("delete_node", {"nodeId": pid})
                except Exception:
                    pass
            applied += 1
            print(f"  [apply-images] '{used_url.rsplit('/',1)[-1]}' → {nid} ({len(data)}b)")
        except Exception as e:
            print(f"  [apply-images] '{kw}' {nid} set_image_fill 실패(placeholder 유지): {e}")
    if applied:
        print(f"  [apply-images] ✓ 실사진 {applied}개 적용 (imageQuery)")
    return applied


def auto_bind_design(root_id: str, original_blueprint: dict) -> int:
    """빌드 직후 DS 변수(색상·타이포)를 자동 바인딩. cmd_build에서 자동 호출.

    원본 blueprint($token() 참조)와 빌드된 노드 트리(실제 ID)를 구조로 1:1 매칭하여
    set_bound_variables를 적용한다 — 별도 bindings.json 수작업 불필요.
    """
    # get_nodes_info(복수)는 전체 재귀 트리를 1콜로 반환 — get_node_info는 트리를 잘라서 반환하므로 사용 금지
    try:
        content = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(content).get("json")
        built = None
        if isinstance(items, list) and items:
            built = items[0].get("document") or items[0]
        elif isinstance(items, dict):
            built = items.get("document") or items
    except Exception as e:
        print(f"  [auto-bind] 빌드 트리 조회 실패 — 바인딩 건너뜀: {e}")
        return 0
    if not built or not built.get("id"):
        print("  [auto-bind] 빌드 트리 없음 — 바인딩 건너뜀")
        return 0

    bindings: list = []
    _collect_bindings(original_blueprint, built, bindings, by_name=True)
    if not bindings:
        print("  [auto-bind] 바인딩할 $token() 토큰 없음")
        return 0

    print(f"  [auto-bind] DS 변수 바인딩 {len(bindings)}개 노드 적용 중...")
    ok = fail = 0
    invalid_tokens: list = []  # 2026-05-26 — silent fail 검출용
    for i, item in enumerate(bindings):
        try:
            resp = call_tool("set_bound_variables",
                      {"nodeId": item["nodeId"], "bindings": item["bindings"]},
                      msg_id=i + 1)
            # 응답 본문의 errors 검사 — set_bound_variables 가 invalid 토큰을
            # 200 OK 로 반환하지만 본문에 errors[] 가 들어있는 silent fail 케이스.
            # 이전엔 그냥 ok 카운트 → blueprint 의 fake 토큰 (예: text-white-primary)
            # 이 검정 default 로 fallback 되어 텍스트 invisible 회귀(v3 s3).
            try:
                parsed = parse_content(resp).get("json") or {}
                errs = parsed.get("errors") or []
                for err in errs:
                    invalid_tokens.append({
                        "nodeId": item["nodeId"],
                        "field": err.get("field"),
                        "requested": (item["bindings"] or {}).get(err.get("field"), "?"),
                        "reason": err.get("reason") or err.get("message") or "not found in DS",
                    })
            except Exception:
                pass
            ok += 1
        except Exception as e:
            fail += 1
            if fail <= 3:
                print(f"    FAIL {item['nodeId']}: {e}")
    if invalid_tokens:
        print(f"  [auto-bind] ⚠️ Invalid 토큰 silent-skip {len(invalid_tokens)}건 — blueprint 수정 필요:")
        for it in invalid_tokens[:5]:
            print(f"    · {it['nodeId']} {it['field']} ← {it['requested']!r} ({it['reason']})")
        if len(invalid_tokens) > 5:
            print(f"    · ... +{len(invalid_tokens)-5} more")
    print(f"  [auto-bind] 완료 — {ok}개 노드 성공, {fail}개 실패")
    return ok


def _collect_blueprint_texts(blueprint: dict) -> list:
    """blueprint의 모든 type:"text" 노드의 characters 를 수집 (소문자 정규화)."""
    out = []
    def _walk(n):
        if isinstance(n, dict):
            if n.get("type") == "text":
                t = n.get("text") or n.get("characters") or ""
                if isinstance(t, str) and t.strip():
                    out.append(t.strip())
            for c in n.get("children", []) or []:
                _walk(c)
        elif isinstance(n, list):
            for x in n:
                _walk(x)
    _walk(blueprint)
    return out


def _check_wireframe_content_required(blueprint: dict) -> list:
    """⚠️ imin_* archetype 빌드 시 _wireframeContent dict 의무 (2026-05-27 절대 룰 0-E).

    archetype 화면(imin_home 등) 은 항상 와이어프레임이 source 임. blueprint root에
    _wireframeContent dict 또는 _wireframeContentSkipped: "<reason>" 둘 중 하나가
    반드시 있어야 빌드 진행. 둘 다 없으면 v13 처럼 더미 데이터로 빌드돼 사용자 격분.

    Bypass:
      root._wireframeContentSkipped: "PRD-only, no wireframe"
      root._wireframeContentSkipped: "internal screen, no wireframe"

    Returns:
        list of ERROR/WARN messages.
    """
    issues = []
    root_name = (blueprint.get("name") or "").lower().replace(" ", "_")
    archetype_prefixes = ("imin_home", "imin_account", "imin_lounge", "imin_stage",
                          "imin_my", "imin_community", "imin_calc", "imin_invite")
    is_archetype = any(p in root_name for p in archetype_prefixes)
    if not is_archetype:
        return issues

    has_content = isinstance(blueprint.get("_wireframeContent"), dict) and blueprint["_wireframeContent"]
    has_skip = bool(blueprint.get("_wireframeContentSkipped"))
    if has_content or has_skip:
        return issues

    issues.append(
        "ERROR (S23): archetype 빌드인데 root._wireframeContent dict 누락. "
        "와이어프레임에서 섹션별 텍스트/숫자/카운트를 dict 로 추출해 박을 것 — "
        "v12 더미 데이터 회귀 방지. "
        "와이어프레임 없는 케이스면 root._wireframeContentSkipped: \"<reason>\" 박기. "
        "(CLAUDE.md 절대 규칙 0-E)"
    )
    return issues


# ── S24 컨셉 선언 게이트 + novelty 시그니처 (2026-06-12 전면 개편 — 사용자: "규칙과 코드
#    강제로 수천 번 생성해도 거의 똑같아. 창의적으로 나오길 원해").
#    S22(콘텐츠 재사용 차단)의 반대 방향 장치: 콘텐츠는 같아야 하고(0-E), 비주얼은 달라야 한다.
_NOVELTY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".novelty")


# imin archetype 빌드 식별 접두사 (concept/design-direction/novelty 게이트 공용)
_ARCHETYPE_PREFIXES = ("imin_home", "imin_account", "imin_lounge", "imin_stage",
                       "imin_my", "imin_community", "imin_calc", "imin_invite",
                       "imin_signup", "imin_active", "imin_done", "imin_schedule")


def _is_archetype_build(blueprint: dict) -> bool:
    root_name = (blueprint.get("name") or "").lower().replace(" ", "_")
    return any(p in root_name for p in _ARCHETYPE_PREFIXES)


def _check_concept_required(blueprint: dict) -> list:
    """S24: imin_* archetype 빌드 시 root._concept {idea, diffs[≥3]} 선언 의무.

    매 시안이 '이번 시안의 핵심 차별 아이디어'와 '직전 버전과 달라지는 점 3가지 이상'을
    명시적으로 선언해야 빌드 통과 — 레퍼런스 Read 게이트(0-G)와 동일 철학으로, 모델이
    이전 구조를 무의식적으로 복제하는 것을 차단한다. bypass: root._conceptSkipped: "<reason>"
    (예: 사용자가 '그대로 다시' 요청한 재빌드 / 단순 수정 재빌드)."""
    issues = []
    if not _is_archetype_build(blueprint):
        return issues
    if blueprint.get("_conceptSkipped"):
        return issues
    c = blueprint.get("_concept")
    if isinstance(c, dict):
        idea = (c.get("idea") or "").strip()
        diffs = [d for d in (c.get("diffs") or []) if str(d).strip()]
        if idea and len(diffs) >= 3:
            print(f"[S24-concept] ✓ 컨셉 선언: {idea[:60]} / 차별점 {len(diffs)}개")
            return issues
    issues.append(
        "ERROR (S24): archetype 빌드인데 root._concept 누락. 이번 시안의 컨셉을 선언할 것 — "
        '{"idea": "<핵심 차별 아이디어 1줄>", "diffs": ["직전 버전과 달라지는 점 3가지 이상"]}. '
        "레퍼런스(0-G)를 보고 매 시안 새로 도출한 비주얼 가설을 적는다(형식 통과용 공허한 값 금지). "
        "단순 재빌드/수정이면 root._conceptSkipped: \"<reason>\". (2026-06-12 룰 2계층)"
    )
    return issues


# S25 — 디자인 방향 선언 (2026-06-15 사용자 룰: "콘텐츠는 1:1 이되 콘텐츠 영역 안 레이아웃·컬러·
# 간격·배치·정렬·타이포 위계는 훨씬 창의적으로. 100번 생성해도 다 똑같이 나오면 디자인이 의미 없다").
# 매 시안이 '시각 방향' 4축을 서로 다른 전략으로 선언해야 통과 → 발산 강제(천장은 enforcer
# fill-in-only 화로 제거됨). novelty 게이트와 짝.
_DESIGN_DIRECTION_AXES = ("typography", "color", "layout", "spacing")


def _check_design_direction_required(blueprint: dict) -> list:
    """S25: imin_* 빌드는 root._designDirection 선언 의무 — 이번 시안의 *시각 방향*.

    `{"id": "<짧은 고유 id>", "typography": "...", "color": "...", "layout": "...",
      "spacing": "..."}` — 4축 중 최소 3축을 *구체 전략* 으로 채운다(예 typography=
    'oversized-hero-32', color='mono-brand+1pop', layout='asymmetric-cards',
    spacing='airy-loose'). 콘텐츠(0-E)는 와이어 1:1 이되, 이 방향에 따라 콘텐츠 영역의
    디자인을 매 시안 다르게 도출한다. bypass: root._designDirectionSkipped: "<reason>"."""
    issues = []
    if not _is_archetype_build(blueprint):
        return issues
    if blueprint.get("_designDirectionSkipped"):
        return issues
    d = blueprint.get("_designDirection")
    if isinstance(d, dict):
        did = (d.get("id") or "").strip()
        axes = {a: str(d.get(a) or "").strip() for a in _DESIGN_DIRECTION_AXES}
        filled = [a for a in _DESIGN_DIRECTION_AXES if axes[a]]
        if did and len(filled) >= 3:
            print("[S25-direction] ✓ 디자인 방향 '" + did + "': "
                  + ", ".join(f"{a}={axes[a]}" for a in filled))
            return issues
    issues.append(
        "ERROR (S25): archetype 빌드인데 root._designDirection 누락/불충분. 이번 시안의 시각 "
        '방향을 선언할 것 — {"id":"<짧은 고유 id>", "typography":"...", "color":"...", '
        '"layout":"...", "spacing":"..."} (최소 3축 구체 전략). 콘텐츠는 1:1(0-E) 이되 레이아웃·'
        "컬러·간격·정렬·타이포 위계를 이 방향으로 매 시안 다르게 만든다(레퍼런스 0-G 재참조, "
        "직전 빌드와 다른 방향). 단순 재빌드면 root._designDirectionSkipped: \"<reason>\"."
    )
    return issues


# S26 — 와이어프레임/PRD 발산 선언 (2026-06-18 사용자 룰: "PRD·특히 와이어프레임 이미지를
# 그대로 똑같은 UI로 구현하는 게 문제. 그 단계에서 창의적으로 레이아웃·정렬·텍스트 위계·크기·
# 컬러를 바꿔 생성하라"). 0-C/0-N(와이어 1:1 복제 금지·창의 재해석 의무)를 advisory→하드 게이트
# 로 승격. 콘텐츠(텍스트/숫자)는 1:1(0-E) 이되, *시각 표현*은 와이어를 트레이싱하지 않았음을
# 구체적으로 선언해야 통과 — 모델이 와이어 이미지를 그대로 베끼는 것을 차단하는 forcing function.
_WIREFRAME_DIVERGENCE_AXES_HINT = "레이아웃·정렬·타이포 위계·크기·컬러"


def _check_wireframe_divergence_required(blueprint: dict) -> list:
    """S26: imin_* 빌드는 root._wireframeDivergence 선언 의무 — 와이어/PRD 대비 *시각 발산*.

    `"_wireframeDivergence": ["<와이어와 달라진 점 1>", "...", "..."]` (구체적 ≥3개).
    각 항목은 와이어의 레이아웃/정렬/타이포 위계/크기/컬러를 *어떻게 다르게* 재구성했는지
    구체적으로 적는다(예: "와이어는 좌측 정렬 라벨 나열 → 금액을 32px 센터 히어로로 재배치",
    "와이어 단일 컬럼 → 2-up 비대칭 카드 그리드"). 콘텐츠(텍스트/숫자)는 와이어 1:1(0-E)이되
    *시각 표현*은 트레이싱 금지. 형식 통과용 공허한 값("색을 바꿈" 식 추상)은 금지 — 구체적이어야.
    bypass: root._wireframeDivergenceSkipped: "<reason>" (와이어 없는 PRD 텍스트만의 빌드 /
    사용자가 '와이어 그대로' 명시한 경우 / 단순 재빌드)."""
    issues = []
    if not _is_archetype_build(blueprint):
        return issues
    if blueprint.get("_wireframeDivergenceSkipped"):
        return issues
    div = blueprint.get("_wireframeDivergence")
    items = [str(d).strip() for d in div if str(d).strip()] if isinstance(div, list) else []
    # 공허한 한두 단어 항목 방지 — 최소 길이로 구체성 약식 검증
    concrete = [d for d in items if len(d) >= 10]
    # 🔴 2026-07-14 (사용자: "와이어프레임이랑 아주 똑같다! 이러면 맡길 이유가 없지" — 코스메틱
    # 발산으로 형식만 채우고 배치를 트레이싱한 회귀): 선언 중 ≥2개는 **구조 레벨** 어휘를
    # 포함해야 통과. 코스메틱(점선→솔리드/이모지 제외/색 매핑)만으로는 발산이 아니다.
    _STRUCT_RE = re.compile(
        r"통합|그룹핑|묶|승격|역전|재배치|재배열|병합|분리|재구성|재편|무대|카드로|카드 로|"
        r"스텝|계층|위계.{0,6}(바꾸|역전|재)|섹션.{0,6}(합|통|병)|그리드로|타일로|배너로|히어로로")
    structural = [d for d in concrete if _STRUCT_RE.search(d)]
    if len(concrete) >= 3 and len(structural) >= 2:
        print(f"[S26-divergence] ✓ 와이어 발산 선언 {len(concrete)}건 (구조 레벨 {len(structural)}건) — 트레이싱 안 함")
        return issues
    if len(concrete) >= 3 and len(structural) < 2:
        issues.append(
            "ERROR (S26-structural): _wireframeDivergence 가 코스메틱 수준(스타일 치환)뿐 — 구조 레벨 "
            "발산(섹션 통합/카드 그룹핑/위계 역전/히어로 승격/그리드 재편 등) 선언이 ≥2개 필요. "
            "콘텐츠 1:1 + 메트릭 승계(2-L) 위에서 정보 구조·그룹핑·위계를 실제로 재설계할 것 "
            "(2026-07-14 사용자: '와이어와 똑같으면 맡길 이유가 없다')."
        )
        return issues
    issues.append(
        "ERROR (S26): archetype 빌드인데 root._wireframeDivergence 누락/불충분. 와이어프레임/PRD "
        f"의 {_WIREFRAME_DIVERGENCE_AXES_HINT} 를 그대로 베끼지 말고, *어떻게 다르게* 재구성했는지 "
        '구체적으로 ≥3개 선언할 것 — {"_wireframeDivergence": ["와이어는 …였는데 빌드는 …로 재배치", '
        '"…", "…"]}. 콘텐츠(텍스트/숫자)는 와이어 1:1(0-E) 이되 시각 표현은 트레이싱 금지(0-C/0-N). '
        "와이어 없는 PRD-only 빌드/단순 재빌드면 root._wireframeDivergenceSkipped: \"<reason>\"."
    )
    return issues


def _check_restructure_map_required(blueprint: dict) -> list:
    """S27: 재구성 맵 하드 게이트 (2026-07-15 사용자: "새 세션마다 와이어랑 똑같이 생성").

    선언형 게이트(S24~S26)는 새 세션이 형식적으로 채우면 뚫린다는 것이 실측으로 반복 확인됨
    → 이 게이트는 선언을 **blueprint 실물과 대조**한다.

    root `_restructureMap` 필수:
      {"wireSections": ["헤드라인", "모집현황", ...],          # 와이어의 섹션 나열 (≥3)
       "surfaces": [{"name": "Overview Card",                # 빌드의 표면(카드/무대/밴드)
                     "absorbs": ["헤드라인", "모집현황"]}, ...]}

    검증 3종 (전부 코드 대조 — 글로 못 뚫음):
      ① 커버리지 — 모든 wireSection 이 어떤 surface 에든 흡수돼야 함 (콘텐츠 누락 방지)
      ② 통합 — ≥1 surface 가 wireSection 을 2개 이상 흡수해야 함.
         와이어 섹션을 각각 카드로 1:1 래핑만 한 것("포장된 트레이싱")은 여기서 차단.
      ③ 실재 — 선언된 surface name 이 blueprint 트리에 실제로 존재하고
         표면 속성(fill/stroke 보유 frame 또는 instance)을 가져야 함.

    bypass: root._restructureMapSkipped: "<reason>" (설정/약관 등 정당한 평면 리스트 화면,
    사용자가 '와이어 그대로' 명시, 단순 재빌드)."""
    issues = []
    if not _is_archetype_build(blueprint):
        return issues
    if blueprint.get("_restructureMapSkipped"):
        return issues
    rm = blueprint.get("_restructureMap")
    if not isinstance(rm, dict):
        issues.append(
            "ERROR (S27): archetype 빌드인데 root._restructureMap 누락 — 와이어 섹션을 어떤 "
            '표면으로 재구성했는지 선언+대조하는 게이트. {"_restructureMap": {"wireSections": '
            '["섹션1", ...], "surfaces": [{"name": "<빌드 표면 노드명>", "absorbs": ["섹션1", '
            '"섹션2"]}, ...]}}. 정당한 평면 화면이면 _restructureMapSkipped: "<reason>".')
        return issues
    wire_sections = [str(s).strip() for s in (rm.get("wireSections") or []) if str(s).strip()]
    surfaces = [s for s in (rm.get("surfaces") or []) if isinstance(s, dict)]
    if len(wire_sections) < 3 or not surfaces:
        issues.append(
            "ERROR (S27): _restructureMap 불충분 — wireSections ≥3 + surfaces ≥1 필요 "
            f"(현재 {len(wire_sections)}/{len(surfaces)}).")
        return issues
    # ① 커버리지
    absorbed = set()
    for s in surfaces:
        absorbed.update(str(a).strip() for a in (s.get("absorbs") or []))
    missing = [w for w in wire_sections if w not in absorbed]
    if missing:
        issues.append(
            f"ERROR (S27-coverage): 와이어 섹션 {missing} 이(가) 어떤 surface 에도 흡수 안 됨 — "
            "콘텐츠 1:1(0-E) 위반 위험. 모든 와이어 섹션을 surfaces[].absorbs 에 배정할 것.")
    # ② 통합 — 1:1 래핑(포장된 트레이싱) 차단
    if not any(len([a for a in (s.get("absorbs") or []) if str(a).strip()]) >= 2 for s in surfaces):
        issues.append(
            "ERROR (S27-consolidation): 모든 surface 가 와이어 섹션을 1개씩만 흡수 — 이것은 "
            "섹션별 카드 래핑일 뿐 구조 재설계가 아니다. 관련 섹션을 묶어 ≥1개 surface 가 "
            "2개 이상 흡수하도록 재구성할 것 (2026-07-14 '와이어와 똑같으면 맡길 이유 없다').")
    # ③ 실재 — 선언된 surface 가 blueprint 트리에 표면으로 존재.
    # 자기 fill/stroke 가 없어도 직계 자식 절반 이상이 표면이면 그룹 래퍼로 인정 (R65 와 동일).
    def _is_surface(n):
        if not isinstance(n, dict):
            return False
        t = (n.get("type") or "frame").lower()
        if t == "instance" or n.get("fill") or n.get("stroke"):
            return True
        kids = [c for c in (n.get("children") or []) if isinstance(c, dict)]
        if kids:
            return sum(1 for c in kids if _is_surface(c)) >= max(1, len(kids) // 2)
        return False

    tree_surfaces = {}

    def _walk(n):
        if not isinstance(n, dict):
            return
        nm = (n.get("name") or "").strip()
        if nm:
            tree_surfaces[nm] = tree_surfaces.get(nm) or _is_surface(n)
        for c in n.get("children") or []:
            _walk(c)

    _walk(blueprint)
    for s in surfaces:
        nm = str(s.get("name") or "").strip()
        if nm not in tree_surfaces:
            issues.append(
                f"ERROR (S27-exists): 선언된 surface '{nm}' 가 blueprint 트리에 없음 — "
                "선언과 실물이 불일치 (이름을 트리 노드명과 정확히 일치시킬 것).")
        elif not tree_surfaces[nm]:
            issues.append(
                f"ERROR (S27-exists): surface '{nm}' 가 트리에 있으나 표면 속성(fill/stroke/"
                "instance)이 없음 — 무표면 래퍼는 그룹핑이 아니다.")
    if not issues:
        n_multi = sum(1 for s in surfaces
                      if len([a for a in (s.get("absorbs") or []) if str(a).strip()]) >= 2)
        print(f"[S27-restructure] ✓ 재구성 맵 검증 — 와이어 {len(wire_sections)}섹션 → "
              f"표면 {len(surfaces)}개 (통합 표면 {n_multi}개), 실재 확인")
    return issues


def _novelty_key(blueprint: dict) -> str:
    """root 이름에서 버전/날짜 접미사를 떼 화면(archetype) 단위 키 생성."""
    name = (blueprint.get("name") or "screen").lower().strip()
    name = re.sub(r"[_\-\s]*v\d+[a-z]?$", "", name)
    name = re.sub(r"[_\-\s]*\d{6,8}[a-z]?(_.*)?$", "", name)
    name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return name or "screen"


def _visual_signature(blueprint: dict) -> dict:
    """비주얼 시그니처 — 콘텐츠(텍스트)는 빼고 *시각 구조*만. 발산을 측정하는 차원:
    섹션 순서 / fill 토큰 분포 / radius 분포 / fontSize 분포 / itemSpacing(간격) 분포 /
    layoutMode 분포 / textAlign(정렬) 분포 / fontWeight 분포.
    (2026-06-15 확장: 간격·레이아웃·정렬·weight 추가 — 레이아웃/간격/타이포만 바꿔도
    시그니처가 달라져 novelty 게이트가 실제 디자인 발산을 측정하게.)"""
    sig = {"sections": [], "fills": {}, "radii": {}, "sizes": {},
           "gaps": {}, "modes": {}, "aligns": {}, "weights": {}}
    for c in blueprint.get("children") or []:
        if isinstance(c, dict):
            sig["sections"].append((c.get("name") or "?").strip().lower())

    def _bump(d, k):
        d[k] = d.get(k, 0) + 1

    def walk(n):
        if not isinstance(n, dict):
            return
        f = n.get("fill")
        if isinstance(f, str) and f.startswith("$token("):
            _bump(sig["fills"], f)
        r = n.get("cornerRadius")
        if not isinstance(r, (int, float)):
            r = n.get("topLeftRadius")
        if isinstance(r, (int, float)) and r > 0:
            _bump(sig["radii"], str(int(min(r, 100))))
        al = n.get("autoLayout")
        if isinstance(al, dict):
            g = al.get("itemSpacing")
            if isinstance(g, (int, float)) and not isinstance(g, bool):
                _bump(sig["gaps"], str(int(g)))
            lm = al.get("layoutMode")
            if lm:
                _bump(sig["modes"], str(lm).upper())
        if (n.get("type") or "").lower() == "text":
            fs = n.get("fontSize")
            if isinstance(fs, (int, float)):
                _bump(sig["sizes"], str(int(fs)))
            ta = n.get("textAlignHorizontal")
            if ta:
                _bump(sig["aligns"], str(ta).upper())
            st = (n.get("fontName") or {}).get("style") if isinstance(n.get("fontName"), dict) else None
            st = st or n.get("fontWeight")
            if st:
                _bump(sig["weights"], str(st))
        for ch in n.get("children") or []:
            walk(ch)
    walk(blueprint)
    return sig


def _signature_similarity(a: dict, b: dict) -> float:
    """두 시그니처의 유사도 0..1 — 섹션순서 22% + fill 18% + radius 12% + fontSize 16%
    + 간격 14% + layoutMode 8% + 정렬 6% + weight 4% (2026-06-15 확장: 간격/레이아웃/정렬/weight
    가 합쳐 32% — 레이아웃/간격/타이포만 바꿔도 유사도가 충분히 떨어지게)."""
    def multiset_sim(x, y):
        keys = set(x) | set(y)
        if not keys:
            return 1.0
        inter = sum(min(x.get(k, 0), y.get(k, 0)) for k in keys)
        union = sum(max(x.get(k, 0), y.get(k, 0)) for k in keys)
        return (inter / union) if union else 1.0
    sa, sb = a.get("sections") or [], b.get("sections") or []
    same = sum(1 for p, q in zip(sa, sb) if p == q)
    sec_sim = same / max(len(sa), len(sb), 1)
    return (0.22 * sec_sim
            + 0.18 * multiset_sim(a.get("fills") or {}, b.get("fills") or {})
            + 0.12 * multiset_sim(a.get("radii") or {}, b.get("radii") or {})
            + 0.16 * multiset_sim(a.get("sizes") or {}, b.get("sizes") or {})
            + 0.14 * multiset_sim(a.get("gaps") or {}, b.get("gaps") or {})
            + 0.08 * multiset_sim(a.get("modes") or {}, b.get("modes") or {})
            + 0.06 * multiset_sim(a.get("aligns") or {}, b.get("aligns") or {})
            + 0.04 * multiset_sim(a.get("weights") or {}, b.get("weights") or {}))


# novelty 소프트 게이트 차단선 — 직전 빌드와 이 이상 유사하면 차단(재구성 유도).
_NOVELTY_SIM_BLOCK = 0.80


def _check_novelty_gate(blueprint: dict) -> list:
    """소프트 게이트(2026-06-15 사용자 룰): 직전 빌드와 비주얼 시그니처가 너무 유사하거나
    디자인 방향 id 가 직전과 같으면 **빌드 차단**(재구성 유도). WARN-only 였던 novelty 를
    실제 게이트로 승격 — "100번 생성해도 다 똑같다"는 문제의 forcing function.

    콘텐츠(0-E)는 그대로 두되 레이아웃·컬러·간격·정렬·타이포 위계를 다른 방향으로 재구성하면
    시그니처가 떨어져 통과한다. bypass: env IMIN_SKIP_NOVELTY_GATE=1 또는 root._noveltySkipped
    (사용자가 '그대로 다시' 원하는 의도된 동일 재빌드)."""
    issues = []
    if os.environ.get("IMIN_SKIP_NOVELTY_GATE") == "1" or blueprint.get("_noveltySkipped"):
        return issues
    if not _is_archetype_build(blueprint):
        return issues
    try:
        key = _novelty_key(blueprint)
        p = os.path.join(_NOVELTY_DIR, key + ".json")
        if not os.path.exists(p):
            print(f"[novelty] '{key}' 직전 빌드 없음 — 첫 생성(게이트 통과)")
            return issues
        with open(p, encoding="utf-8") as fh:
            prev = json.load(fh)
        sim = _signature_similarity(prev.get("signature") or {}, _visual_signature(blueprint))
        pct = round(sim * 100)
        prev_did = str((prev.get("direction") or {}).get("id") or "").strip().lower()
        cur_did = str((blueprint.get("_designDirection") or {}).get("id") or "").strip().lower()
        same_dir = bool(prev_did) and prev_did == cur_did
        if sim >= _NOVELTY_SIM_BLOCK or same_dir:
            reasons = []
            if sim >= _NOVELTY_SIM_BLOCK:
                reasons.append(f"비주얼 시그니처 {pct}% 유사(차단선 {round(_NOVELTY_SIM_BLOCK*100)}%)")
            if same_dir:
                reasons.append(f"디자인 방향 id '{cur_did}' 가 직전과 동일")
            issues.append(
                "ERROR (novelty-gate): 직전 빌드와 너무 유사 — " + " / ".join(reasons) + ". "
                "콘텐츠(0-E)는 그대로 두되 콘텐츠 영역의 레이아웃·컬러·간격·정렬·타이포 위계를 "
                "**다른 디자인 방향**(_designDirection)으로 재구성하라(레퍼런스 0-G 재참조). "
                "정말 '그대로 다시'면 root._noveltySkipped:\"<reason>\" 또는 env IMIN_SKIP_NOVELTY_GATE=1."
            )
        else:
            print(f"[novelty] ✓ '{key}' 직전 대비 시그니처 {pct}% 유사 — 새로움 확보"
                  f"(차단선 {round(_NOVELTY_SIM_BLOCK*100)}%)")
    except Exception as e:
        print(f"[novelty-gate] 비교 실패(무시하고 통과): {e}")
    return issues


def _novelty_save(blueprint: dict) -> None:
    """빌드 성공 후 시그니처 + 디자인 방향 저장 — 다음 생성의 novelty 비교 기준."""
    try:
        os.makedirs(_NOVELTY_DIR, exist_ok=True)
        key = _novelty_key(blueprint)
        with open(os.path.join(_NOVELTY_DIR, key + ".json"), "w", encoding="utf-8") as fh:
            json.dump({"name": blueprint.get("name"), "signature": _visual_signature(blueprint),
                       "concept": blueprint.get("_concept"),
                       "direction": blueprint.get("_designDirection"),
                       "ts": int(time.time())},
                      fh, ensure_ascii=False)
    except Exception:
        pass


def _check_no_archetype_reuse(blueprint: dict, blueprint_path: str) -> list:
    """⚠️ 와이어 콘텐츠 1:1 추출 의무 (2026-05-27 절대 룰 0-E).

    새 세션에서 v12 같은 archetype config 를 복사해 v13 으로 reuse 시,
    더미 데이터(예: 3건의 스테이지/+14,420,320원/미납 28일)가 그대로 박혀서
    와이어 의도 무시 + 사용자 격분.

    검출 방법:
    1. scripts/blueprint_imin_home_*.json 같은 archetype 이전 빌드 파일들을 스캔
    2. 현재 blueprint 의 텍스트 노드와 70%+ 일치 시 ERROR 또는 WARN
    3. root._wireframeContent dict 가 있으면 안전 (사용자가 와이어 콘텐츠 명시 추출)

    Returns:
        list of WARN/ERROR messages.
    """
    issues = []
    cur_texts = set(_collect_blueprint_texts(blueprint))
    if len(cur_texts) < 10:
        return issues  # 너무 적으면 검증 무의미

    # root._wireframeContent dict 가 있으면 사용자가 명시 추출한 것 — 통과
    if isinstance(blueprint.get("_wireframeContent"), dict) and blueprint["_wireframeContent"]:
        return issues

    # 같은 archetype 의 이전 빌드 파일 스캔
    try:
        scripts_dir = os.path.dirname(os.path.abspath(blueprint_path)) if blueprint_path else "scripts"
        root_name = (blueprint.get("name") or "").lower()
        # archetype prefix 추출 (imin_home_2026_xxxx → imin_home)
        archetype = None
        for prefix in ("imin_home", "imin_account", "imin_lounge", "imin_stage", "imin_my"):
            if prefix in root_name.replace(" ", "_"):
                archetype = prefix
                break
        if not archetype:
            return issues

        import glob
        candidates = glob.glob(os.path.join(scripts_dir, f"blueprint_*{archetype}*.json"))
        # 현재 빌드 파일 제외
        candidates = [c for c in candidates if os.path.abspath(c) != os.path.abspath(blueprint_path or "")]

        max_overlap = 0.0
        max_match_file = None
        for cand_path in candidates:
            try:
                with open(cand_path) as f:
                    cand_bp = json.load(f)
                cand_texts = set(_collect_blueprint_texts(cand_bp))
                if not cand_texts:
                    continue
                overlap = len(cur_texts & cand_texts) / max(len(cur_texts), len(cand_texts))
                if overlap > max_overlap:
                    max_overlap = overlap
                    max_match_file = os.path.basename(cand_path)
            except Exception:
                continue

        if max_overlap >= 0.7:
            issues.append(
                f"ERROR (S22): archetype config reuse 의심 — 현재 blueprint 의 텍스트 {len(cur_texts)}개 중 "
                f"{int(max_overlap*100)}%가 '{max_match_file}' 와 일치. "
                f"v12 더미 데이터를 그대로 박은 거면 와이어 콘텐츠로 정정 필요. "
                f"이걸 의도한 빌드라면 blueprint root.\"_wireframeContent\" 에 와이어 콘텐츠 dict 추가하면 통과. "
                f"(CLAUDE.md 절대 규칙 0-E)"
            )
        elif max_overlap >= 0.5:
            issues.append(
                f"WARN (S22): 이전 빌드 '{max_match_file}' 와 텍스트 {int(max_overlap*100)}% 일치. "
                f"와이어 콘텐츠 1:1 추출됐는지 확인 필요. root._wireframeContent dict 추가 권장."
            )
    except Exception as e:
        issues.append(f"WARN (S22): archetype reuse 검증 실패 — {e}")

    return issues


def _qa_wireframe_content_match(blueprint: dict, root_id: str) -> int:
    """⚠️ QA — blueprint TEXT vs root._wireframeContent dict 매치 검증 (2026-05-27 룰 0-E).

    blueprint root._wireframeContent 가 있으면, dict 의 모든 string value 가
    빌드 결과의 TEXT characters 어딘가에 들어있는지 검증.
    미스매치 ≥ 30% 시 WARN, ≥ 50% 시 ERROR 로깅 (build 차단은 안 함 — 사용자가 fix 가능하게).
    """
    wc = blueprint.get("_wireframeContent")
    if not isinstance(wc, dict) or not wc:
        print("  [QA-wc] root._wireframeContent 없음 — 와이어 콘텐츠 매치 검증 skip")
        return 0

    # 🔴 whitespace 정규화 — 빌드 TEXT 가 줄바꿈을 넣어도(예: "Plan3님,\n첫 …") 와이어 dict 의
    # 한 줄 문자열과 매치되게 모든 공백류를 단일 space 로 collapse (2026-06-10 오탐 fix).
    import re as _re_wc
    def _norm(s):
        return _re_wc.sub(r"\s+", " ", s).strip()

    # dict 의 모든 string value 를 평탄화 추출 (정규화)
    expected = []
    def _flatten(v):
        if isinstance(v, str):
            s = _norm(v)
            if s:
                expected.append(s)
        elif isinstance(v, dict):
            for vv in v.values():
                _flatten(vv)
        elif isinstance(v, list):
            for vv in v:
                _flatten(vv)
    _flatten(wc)

    if not expected:
        return 0

    # 빌드된 트리 의 모든 TEXT characters 수집
    try:
        content = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(content).get("json")
        built = items[0].get("document") if isinstance(items, list) and items else None
    except Exception as e:
        print(f"  [QA-wc] 빌드 트리 조회 실패 — 검증 skip: {e}")
        return 0

    built_texts = []
    def _walk(n):
        if isinstance(n, dict):
            if n.get("type") == "TEXT":
                c = n.get("characters") or ""
                if isinstance(c, str) and _norm(c):
                    built_texts.append(_norm(c))
            for ch in n.get("children", []) or []:
                _walk(ch)
    _walk(built or {})

    # 🔴 DS 인스턴스 라벨(_instanceText/label/_segLabels)은 인스턴스 *내부* TEXT 라
    # get_nodes_info 트리에 안 잡힌다(예: "닫기" CTA). blueprint 가 결정적으로 적용하므로
    # 빌드 텍스트에 포함시켜 오탐(누락) 방지 (2026-06-10).
    def _walk_bp_labels(n):
        if isinstance(n, dict):
            for key in ("_instanceText", "label"):
                val = n.get(key)
                if isinstance(val, str) and _norm(val):
                    built_texts.append(_norm(val))
            props = n.get("properties")
            if isinstance(props, dict) and isinstance(props.get("label"), str):
                built_texts.append(_norm(props["label"]))
            for seg in (n.get("_segLabels") or []):
                if isinstance(seg, str) and _norm(seg):
                    built_texts.append(_norm(seg))
            for ch in n.get("children", []) or []:
                _walk_bp_labels(ch)
    _walk_bp_labels(blueprint)

    built_blob = " ".join(built_texts)

    missing = []
    for exp in expected:
        # 정확/부분 일치 — 와이어의 핵심 키워드(숫자/단위) 가 어디든 빌드에 들어있어야 함
        # 너무 짧은 (≤1자) 항목 + ASCII-only punctuation 만 있는 건 skip
        if len(exp) <= 1:
            continue
        if exp not in built_blob:
            missing.append(exp)

    total = len([e for e in expected if len(e) > 1])
    miss_ratio = len(missing) / total if total else 0
    if miss_ratio >= 0.5:
        print(f"  [QA-wc] ❌ ERROR — 와이어 콘텐츠 {total}개 중 {len(missing)}개 누락 ({int(miss_ratio*100)}%). 누락 일부:")
        for m in missing[:10]:
            print(f"     - '{m}'")
        if len(missing) > 10:
            print(f"     ... +{len(missing)-10}개")
        print(f"  [QA-wc] 와이어 콘텐츠 1:1 매치 강력 권장 — blueprint TEXT 를 와이어 그대로 정정")
    elif miss_ratio >= 0.3:
        print(f"  [QA-wc] ⚠️ WARN — 와이어 콘텐츠 {total}개 중 {len(missing)}개 누락 ({int(miss_ratio*100)}%)")
        for m in missing[:5]:
            print(f"     - '{m}'")
    else:
        print(f"  [QA-wc] ✓ 와이어 콘텐츠 매치 OK — {total}개 중 {total-len(missing)}개 빌드 트리에서 발견 ({int((1-miss_ratio)*100)}%)")
    return len(missing)


def _detect_layout_smells(root_node: dict) -> list:
    """결정적 '레이아웃 스멜' 검출 — 빌드 트리(_collect_tree 출력)의 기하/사이징만으로
    오늘 수동으로 고친 회귀 패턴을 잡는다 (2026-06-10). 순수 함수(테스트 가능).

    서브에이전트·LLM 없이, *높은 정밀도*(오탐 최소)로 3종만:
      1. SPACE_BETWEEN 행에 *콘텐츠 있는* FILL 자식 → 분배 깨짐(한쪽 뭉침). (선물 Giver Info 회귀)
      2. 짧은 텍스트(≤6자, 명시 \\n 없음)가 2줄+로 wrap → 폭 collapse. ("후기 공유"→"후/기", 탭 라벨)
      3. 프레임 폭 <4px 붕괴 → 2-col FILL collapse.
    (원형→타원은 size-invariant/_keepSizing 이 이미 막고, 검출 시 버튼 pill 오탐이 커서 제외.)
    """
    smells = []

    def _has_content(c):
        if (c.get("type") or "").upper() == "TEXT":
            return bool((c.get("characters") or "").strip())
        return bool(c.get("_children_full"))

    def walk(n):
        if not isinstance(n, dict):
            return
        ntype = (n.get("type") or "").upper()
        name = n.get("name") or "?"
        kids = n.get("_children_full") or []
        w = n.get("width") or 0
        h = n.get("height") or 0

        if ntype in ("FRAME", "COMPONENT", "INSTANCE"):
            # 1) SPACE_BETWEEN + 콘텐츠 있는 FILL 자식
            if ((n.get("layoutMode") or "").upper() == "HORIZONTAL"
                    and (n.get("primaryAxisAlignItems") or "") == "SPACE_BETWEEN"):
                real_kids = [c for c in kids if (c.get("type") or "").upper()
                             in ("FRAME", "COMPONENT", "INSTANCE", "TEXT")]
                fill_content = [c for c in real_kids
                                if (c.get("layoutSizingHorizontal") or "") == "FILL" and _has_content(c)]
                if len(real_kids) >= 2 and fill_content:
                    nm = ", ".join((c.get("name") or "?") for c in fill_content[:2])
                    smells.append(f"SPACE_BETWEEN 행 '{name}' 에 콘텐츠 든 FILL 자식({nm}) — 분배 깨짐(한쪽 뭉침). HUG + _keepSizing 권장")
            # 3) 폭 붕괴
            if 0 < w < 4 and kids:
                smells.append(f"프레임 '{name}' 폭 {round(w, 1)}px 로 붕괴 — 2-col FILL collapse 의심")

        # 2) 짧은 텍스트 wrap
        if ntype == "TEXT":
            chars = (n.get("characters") or "").strip()
            fs = n.get("fontSize")
            if chars and "\n" not in chars and len(chars) <= 6:
                wrapped = (h >= fs * 1.7) if isinstance(fs, (int, float)) and fs > 0 else (h >= 36)
                if wrapped:
                    smells.append(f"짧은 텍스트 '{chars}' 가 2줄+로 wrap (h={round(h)}) — 폭 collapse 의심(부모 HUG 붕괴 / 텍스트 FILL)")

        for c in kids:
            walk(c)

    walk(root_node)
    return smells


def _qa_layout_smells(root_id: str) -> int:
    """레이아웃 스멜 검사 (2026-06-10) — 빌드 후 자동, 스크린샷 보기 *전*에 회귀 패턴 노출.
    차단 안 함(WARN). 사람(Claude)이 스크린샷 확인할 항목을 미리 가리킨다."""
    try:
        tree = _collect_tree(root_id)
    except Exception as e:
        print(f"  [smell] 트리 수집 실패 — skip: {e}")
        return 0
    smells = _detect_layout_smells(tree)
    if smells:
        print(f"  [smell] ⚠️ 레이아웃 스멜 {len(smells)}건 — 스크린샷 확인 권장:")
        for s in smells[:12]:
            print(f"     - {s}")
        if len(smells) > 12:
            print(f"     ... +{len(smells) - 12}건")
    else:
        print("  [smell] OK — 레이아웃 스멜 없음")
    return len(smells)


def _qa_blueprint_integrity(original_blueprint: dict, root_id: str) -> int:
    """⚠️ QA — blueprint의 text 노드가 빌드 후에도 TEXT 타입인지 검증 + 자동 교정.

    enhanceBlueprint의 이모지/아이콘 자동변환이 "5" 같은 숫자 텍스트를 아이콘
    프레임으로 잘못 바꾸는 사고를 빌드 후에 잡아낸다. (예: 스테퍼 값이 별 아이콘이 됨)

    blueprint 노드가 type:"text" + text 있음인데 빌드 결과가 TEXT 가 아니면:
      같은 부모의 다른 TEXT 형제를 복제 → 텍스트 교체 → 원위치 삽입 → 잘못된 노드 삭제.
    """
    try:
        content = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(content).get("json")
        built = items[0].get("document") if isinstance(items, list) and items else None
    except Exception as e:
        print(f"  [QA] 빌드 트리 조회 실패 — 검증 건너뜀: {e}")
        return 0
    if not isinstance(built, dict):
        return 0

    issues = []  # (name, want_text, bad_node, parent_node)

    def _walk(bp, bt):
        if not isinstance(bp, dict) or not isinstance(bt, dict):
            return
        bt_children = bt.get("children") or []
        buckets: Dict[str, list] = {}
        for c in bt_children:
            buckets.setdefault(c.get("name"), []).append(c)
        used: Dict[str, int] = {}
        for bpc in bp.get("children") or []:
            if not isinstance(bpc, dict):
                continue
            nm = bpc.get("name")
            lst = buckets.get(nm, [])
            k = used.get(nm, 0)
            if k >= len(lst):
                continue
            btc = lst[k]
            used[nm] = k + 1
            if (bpc.get("type") or "").lower() == "text" and str(bpc.get("text") or "").strip():
                if (btc.get("type") or "").upper() != "TEXT":
                    issues.append((nm, str(bpc.get("text")), btc, bt))
            _walk(bpc, btc)

    _walk(original_blueprint, built)
    if not issues:
        print("  [QA] 텍스트 노드 무결성 OK — blueprint의 text 노드 전부 TEXT 유지")
        return 0

    print(f"  [QA] ⚠️ 무결성 위반 {len(issues)}건 — blueprint의 text 가 빌드 후 다른 타입이 됨:")
    fixed = 0
    for nm, want, bad, parent in issues:
        bad_id = bad.get("id")
        parent_id = parent.get("id")
        print(f"    - '{nm}': \"{want}\" (text) 여야 하는데 {bad.get('type')} 임 (id={bad_id})")
        siblings = parent.get("children") or []
        child_ids = [c.get("id") for c in siblings]
        sibling = next((c for c in siblings
                        if (c.get("type") or "").upper() == "TEXT" and c.get("id") != bad_id), None)
        if not sibling or not parent_id or bad_id not in child_ids:
            print("      교정 불가 — 복제할 TEXT 형제 없음 (수동 확인 필요)")
            continue
        try:
            clone = parse_content(call_tool("clone_node", {"nodeId": sibling["id"]})).get("json") or {}
            clone_id = clone.get("id")
            if not clone_id:
                print("      교정 실패 — clone 결과 없음")
                continue
            call_tool("set_text_content", {"nodeId": clone_id, "text": want})
            call_tool("insert_child", {"parentId": parent_id, "childId": clone_id,
                                       "index": child_ids.index(bad_id)})
            call_tool("delete_node", {"nodeId": bad_id})
            print(f"      ✅ 교정 — TEXT \"{want}\" 로 복원")
            fixed += 1
        except Exception as e:
            print(f"      교정 실패: {e}")
    print(f"  [QA] 자동 교정 {fixed}/{len(issues)}건")
    return fixed


def _qa_visual_checks(root_id: str) -> int:
    """⚠️ QA — 가시성(대비) + 레이아웃(겹침/데드밴드) 자동 검사.

    사람 눈에 의존하지 않고 빌드된 트리를 분석해 다음을 잡는다:
    - 대비 부족: 텍스트/아이콘 색이 배경과 너무 가까워 안 보임 (예: fg-quaternary on white)
    - 데드밴드: 마지막 콘텐츠와 Tab Bar 사이 빈 띠
    - 콘텐츠 가림: 콘텐츠가 Tab Bar 뒤로 넘어가 가려짐
    - Tab Bar 잘림 / 루트 하단 빈 공간

    Returns: 발견된 이슈 수.
    """
    try:
        content = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(content).get("json")
        built = items[0].get("document") if isinstance(items, list) and items else None
    except Exception as e:
        print(f"  [QA] 트리 조회 실패 — 시각 검사 건너뜀: {e}")
        return 0
    if not isinstance(built, dict):
        return 0

    issues: List[str] = []

    # ── 대비 검사 (WCAG 상대휘도 기반) ──
    CONTRAST_MIN = 1.8  # 이 비율 미만이면 "거의 안 보임" 경고 (fg-tertiary ~1.98은 통과)

    def _lin(x: float) -> float:
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    def _lum(c) -> float:
        return 0.2126 * _lin(c[0]) + 0.7152 * _lin(c[1]) + 0.0722 * _lin(c[2])

    def _ratio(c1, c2) -> float:
        l1, l2 = _lum(c1), _lum(c2)
        hi, lo = max(l1, l2), min(l1, l2)
        return (hi + 0.05) / (lo + 0.05)

    def _solid(paints):
        """paint 배열에서 첫 SOLID 색 (r,g,b,effectiveAlpha) 반환."""
        if not isinstance(paints, list):
            return None
        for p in paints:
            if not isinstance(p, dict) or p.get("visible") is False:
                continue
            if p.get("type") == "SOLID":
                col = p.get("color") or {}
                a = col.get("a", 1) * p.get("opacity", 1)
                return (col.get("r", 0), col.get("g", 0), col.get("b", 0), a)
        return None

    def _walk_contrast(node, bg, path):
        ntype = (node.get("type") or "").upper()
        name = node.get("name", "?")
        node_path = f"{path}/{name}"
        # 배경 갱신: 프레임류가 불투명 fill을 가지면 자식들의 배경이 됨
        node_bg = bg
        if ntype not in ("TEXT", "VECTOR"):
            fc = _solid(node.get("fills"))
            if fc and fc[3] >= 0.95:
                node_bg = fc[:3]
        if ntype == "TEXT":
            tc = _solid(node.get("fills"))
            chars = (node.get("characters") or "").strip()
            if tc and tc[3] >= 0.4 and chars:
                r = _ratio(tc[:3], bg)
                if r < CONTRAST_MIN:
                    issues.append(f"대비부족 TEXT '{name}' \"{chars[:14]}\" — 대비 {r:.2f} (배경과 거의 같은 색)")
        elif ntype == "VECTOR":
            ic = _solid(node.get("strokes")) or _solid(node.get("fills"))
            if ic and ic[3] >= 0.4:
                r = _ratio(ic[:3], bg)
                if r < CONTRAST_MIN:
                    issues.append(f"대비부족 ICON '{path.rsplit('/', 1)[-1]}' — 대비 {r:.2f}")
        for c in node.get("children") or []:
            _walk_contrast(c, node_bg, node_path)

    root_fill = _solid(built.get("fills"))
    base_bg = root_fill[:3] if (root_fill and root_fill[3] >= 0.95) else (0.988, 0.988, 0.992)
    _walk_contrast(built, base_bg, "")

    # ── 레이아웃 검사 (Tab Bar ↔ 콘텐츠 관계) ──
    root_bb = built.get("absoluteBoundingBox") or {}
    root_y = root_bb.get("y", 0)
    root_h = root_bb.get("height") or built.get("height") or 0
    content_bottom = 0
    tab_bar = None
    for c in built.get("children") or []:
        cname = (c.get("name") or "").lower()
        lp = c.get("layoutPositioning", "AUTO")
        bb = c.get("absoluteBoundingBox") or {}
        cy = bb.get("y", 0) - root_y
        ch = bb.get("height", 0)
        if "tab bar" in cname or "tabbar" in cname:
            tab_bar = (cy, ch)
        elif lp == "ABSOLUTE" or "fab" in cname:
            continue  # FAB 등 ABSOLUTE는 콘텐츠 바닥 계산에서 제외
        elif cy + ch > content_bottom:
            content_bottom = cy + ch
    if tab_bar:
        tab_y, tab_h = tab_bar
        gap = tab_y - content_bottom
        if gap > 24:
            issues.append(f"데드밴드 — 마지막 콘텐츠(y={round(content_bottom)})와 Tab Bar(y={round(tab_y)}) 사이 빈 띠 {round(gap)}px")
        elif gap < -8:
            issues.append(f"콘텐츠 가림 — 콘텐츠가 Tab Bar 뒤로 {round(-gap)}px 넘어가 가려짐")
        tab_bottom = tab_y + tab_h
        if root_h and root_h + 1 < tab_bottom:
            issues.append(f"Tab Bar 잘림 — 루트 높이({round(root_h)}) < Tab Bar 하단({round(tab_bottom)})")
        elif root_h and root_h - tab_bottom > 8:
            issues.append(f"루트 하단 빈 공간 {round(root_h - tab_bottom)}px — 루트 높이({round(root_h)}) > Tab Bar 하단({round(tab_bottom)})")

    # ── 2026-05-27 — Left/Right overflow detect (사용자 분노: 좌측 잘림 사각지대) ──
    # _fix_overflow_children 가 자동 fix 하지만 fix 못한 케이스 남으면 여기서 잡음.
    # carousel 자식은 의도된 overflow 이므로 제외.
    root_left = root_bb.get("x", 0)
    root_right = root_left + (root_bb.get("width", 0) or 0)
    left_off: List[tuple] = []
    right_off: List[tuple] = []

    def _is_carousel_nm(nm: str) -> bool:
        nm = (nm or "").lower()
        return any(k in nm for k in ("scroll", "carousel", "banner row", "hero row"))

    def _walk_overflow(node, depth=0, in_carousel=False):
        if not isinstance(node, dict):
            return
        if depth > 0 and not in_carousel:
            bb_ = node.get("absoluteBoundingBox") or {}
            nx_, nw_ = bb_.get("x"), bb_.get("width", 0) or 0
            if nx_ is not None:
                if nx_ < root_left - 1:
                    left_off.append((node.get("name", "?"), round(nx_), round(nw_)))
                if nx_ + nw_ > root_right + 1:
                    right_off.append((node.get("name", "?"), round(nx_ + nw_), round(nw_)))
        node_is_carousel = _is_carousel_nm(node.get("name"))
        for c_ in node.get("children") or []:
            _walk_overflow(c_, depth + 1, in_carousel or node_is_carousel)

    _walk_overflow(built)
    if left_off:
        sample = ", ".join(f"'{n}'@x={x}" for n, x, _w in left_off[:5])
        tail = f" ... +{len(left_off) - 5} more" if len(left_off) > 5 else ""
        issues.append(f"좌측 overflow {len(left_off)}건 — 자식이 root left({round(root_left)}) 밖: {sample}{tail}")
    if right_off:
        sample = ", ".join(f"'{n}'@right={x}" for n, x, _w in right_off[:5])
        tail = f" ... +{len(right_off) - 5} more" if len(right_off) > 5 else ""
        issues.append(f"우측 overflow {len(right_off)}건 — 자식이 root right({round(root_right)}) 밖: {sample}{tail}")

    if not issues:
        print("  [QA] 시각 검사 OK — 대비/레이아웃 문제 없음")
        return 0
    print(f"  [QA] ⚠️ 시각 검사 — {len(issues)}건 발견:")
    for it in issues:
        print(f"    - {it}")
    return len(issues)


# ── 2026-05-24 사용자 분노 fix (root export clip blind spot) ─────────
#
# 사용자 케이스: Primary CTA가 root width 393을 200+px overflow했는데
# root export PNG는 393으로 clip되어 잘 보였음. 사용자는 Figma canvas로
# overflow까지 봐서 즉시 발견. "이걸 왜 못 찾냐" 분노.
#
# 3개 자동 fix:
# 1) overflow detect — root width를 넘은 자식의 layoutSizingHorizontal=FILL 자동 적용
# 2) icon button 시인성 — Bookmark/Chat 같은 small icon button이 bg-secondary로
#    화이트와 거의 구분 안 될 때 보더 추가 (또는 bg-tertiary로 격상)
# 3) small text center — chat-badge 같은 짧은 텍스트가 FILL 폭에 LEFT align되어
#    부모 frame 중앙 자식과 어긋날 때 CENTER로 자동 변환

def _set_sizing_batch(items: List[dict]) -> int:
    """set_layout_sizing N건을 plugin 의 set_layout_sizing_batch 1콜로 실행.

    2026-07-13 — post-fix 471s 회귀의 주범이 사이징 개별 호출 라운드트립(1회차에만
    ~100건)이라 배칭. 플러그인/브리지에 배치 커맨드가 이미 있었는데 Python 이 안 썼음.
    items: [{"nodeId": ..., "horizontal": "FILL", "vertical": "HUG"}, ...]
    배치 실패 시 개별 호출 폴백. returns 적용 건수.
    """
    if not items:
        return 0
    try:
        res = parse_content(call_tool("set_layout_sizing_batch", {"items": items})).get("json") or {}
        ok = res.get("succeeded")
        errs = res.get("errors") or []
        for e in errs[:5]:
            print(f"    [sizing-batch] item 실패: {e}")
        return ok if isinstance(ok, int) else len(items)
    except Exception as e:
        print(f"  [sizing-batch] batch 도구 실패 → 개별 폴백: {e}")
        n = 0
        for it in items:
            try:
                call_tool("set_layout_sizing", {k: v for k, v in it.items()})
                n += 1
            except Exception:
                pass
        return n


def _fix_overflow_children(root_id: str) -> int:
    """root width를 넘어 그려진 자식을 detect → layoutSizingHorizontal=FILL 강제.

    가장 흔한 케이스: button/CTA frame이 blueprint에 layoutSizingHorizontal: FILL
    명시됐어도 batch_build_screen이 height만 명시된 자식을 FIXED parent-inner-width로
    박는 버그. 결과적으로 sibling을 밀어내고 root 밖으로 overflow.

    Returns: fix 건수.
    """
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        root = items[0].get("document") if items else None
    except Exception as e:
        print(f"  [overflow] 트리 조회 실패: {e}")
        return 0
    if not isinstance(root, dict):
        return 0
    rb = root.get("absoluteBoundingBox") or {}
    rx, rw = rb.get("x", 0), rb.get("width", 0)
    if not rw:
        return 0
    right_limit = rx + rw + 1  # 1px tolerance
    fixed = 0

    def _is_icon_like(node: dict) -> bool:
        """Icon SVG wrappers must never be FILL'd — they'd stretch the vector.
        Detect by: VECTOR type, or FRAME with a single VECTOR child (svg_icon wrapper)
        and width≈height (square), or known icon child names."""
        if not isinstance(node, dict):
            return False
        if (node.get("type") or "").upper() == "VECTOR":
            return True
        kids = node.get("children") or []
        # svg_icon wrapper: a FRAME with single VECTOR child, square-ish
        if len(kids) == 1 and (kids[0].get("type") or "").upper() == "VECTOR":
            bb = node.get("absoluteBoundingBox") or {}
            w, h = bb.get("width", 0) or 0, bb.get("height", 0) or 0
            if w and h and 0.7 <= (w / h) <= 1.43 and max(w, h) <= 64:
                return True
        return False

    def _is_small_pill(node: dict) -> bool:
        """Small status/tag pills (cornerRadius≥999, width<150) are HUG-intended.
        FILL'ing them stretches the pill across the row with empty space (2026-05-26
        m1-fail 120px bug). Detect by: fully-rounded radius + short content + width<150.
        """
        if not isinstance(node, dict):
            return False
        if (node.get("type") or "").upper() != "FRAME":
            return False
        # Full-pill radius — corner radius ≥ height/2 → effectively a pill
        cr = node.get("cornerRadius") or 0
        bb = node.get("absoluteBoundingBox") or {}
        w, h = bb.get("width", 0) or 0, bb.get("height", 0) or 0
        is_pill = (cr >= 999) or (h and cr >= h / 2 - 1)
        if not (is_pill and w and w < 150):
            return False
        # Tight content — only text/icon children, no large frames
        kids = node.get("children") or []
        if len(kids) > 4:
            return False
        for k in kids:
            kt = (k.get("type") or "").upper()
            if kt not in ("TEXT", "VECTOR", "FRAME"):
                return False
            if kt == "FRAME":
                kbb = k.get("absoluteBoundingBox") or {}
                if (kbb.get("width", 0) or 0) > 40:
                    return False
        return True

    def _is_carousel_name(nm: str) -> bool:
        nm = (nm or "").lower()
        return any(k in nm for k in ("scroll", "carousel", "banner row", "hero row"))

    def walk(node, parent_is_carousel=False):
        nonlocal fixed
        if not isinstance(node, dict):
            return
        if node.get("id") == root_id:
            for c in node.get("children") or []:
                walk(c, False)
            return
        bb = node.get("absoluteBoundingBox") or {}
        nx, nw = bb.get("x", 0), bb.get("width", 0)
        right_overflow = nx + nw > right_limit
        # 2026-05-27 — left overflow도 잡음 (사용자 분노: 좌측 잘림 사각지대)
        left_overflow = nx < (rx - 1)
        # 2026-05-27 — carousel 자식은 FIXED width 의도이므로 절대 FILL 금지.
        # 부모 frame name 에 'scroll' / 'carousel' 포함하면 그 직계 자식 skip.
        # 2026-07-13 — 짧은 텍스트(숫자 셀 라벨 등, ≤6자)는 FILL 금지: 부모 셀의 CENTER
        # 정렬이 깨져 좌측 쏠림(Turn Cell 6·7 회귀). 셀(frame) FILL 만으로 overflow 는 해소됨.
        is_short_text = ((node.get("type") or "").upper() == "TEXT"
                         and len((node.get("characters") or "").strip()) <= 8)  # '-14.33%' 류 값 포함
        if (right_overflow or left_overflow) and node.get("layoutSizingHorizontal") != "FILL":
            if _is_icon_like(node) or _is_small_pill(node) or parent_is_carousel or is_short_text:
                pass
            else:
                queue.append({"nodeId": node.get("id"), "horizontal": "FILL"})
                if left_overflow:
                    print(f"  [overflow] '{node.get('name')}' x={int(nx)} < root left {int(rx)} → FILL (좌측)")
                else:
                    print(f"  [overflow] '{node.get('name')}' x+w={int(nx+nw)} > root right {int(right_limit)} → FILL (우측)")
        # 자식 walk — 이 node가 carousel이면 자식들은 parent_is_carousel=True
        node_is_carousel = _is_carousel_name(node.get("name"))
        for c in node.get("children") or []:
            walk(c, node_is_carousel)

    queue: List[dict] = []
    walk(root)
    fixed = _set_sizing_batch(queue)
    if fixed == 0:
        print("  [overflow] OK — root width 초과 자식 없음")
    return fixed


# Bookmark/Chat 같은 small icon button (정사각 48 이하 + 아이콘 1~2개) 의 fill 이
# bg-secondary 인데 부모도 흰 배경이면 거의 invisible. 자동 fix:
# 1) bg-secondary → bg-tertiary 같은 진한 회색 (선호) — 불가능하면 border-secondary 보더 추가
# bg-secondary RGB ≈ (0.953, 0.957, 0.965); bg-tertiary RGB ≈ (0.898, 0.906, 0.922).
_BG_SECONDARY_RGB = (0.953, 0.957, 0.965)
_BG_TERTIARY_RGB = (0.898, 0.906, 0.922)

def _fix_icon_button_visibility(root_id: str) -> int:
    """small icon button (≤48px square, 1~2개 자식, name ~ /btn|button|icon/) 의
    bg-secondary fill 을 bg-tertiary 로 격상해 흰 배경 위 시인성 확보.

    Returns: fix 건수.
    """
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        root = items[0].get("document") if items else None
    except Exception as e:
        print(f"  [icon-btn] 트리 조회 실패: {e}")
        return 0
    if not isinstance(root, dict):
        return 0
    import re as _re
    BTN_RE = _re.compile(r"\b(btn|button)\b|icon$", _re.I)
    fixed = 0

    def is_bg_secondary(fills):
        if not isinstance(fills, list):
            return False
        for p in fills:
            if not isinstance(p, dict) or p.get("type") != "SOLID":
                continue
            c = p.get("color") or {}
            if (abs(c.get("r", 0) - _BG_SECONDARY_RGB[0]) < 0.01
                    and abs(c.get("g", 0) - _BG_SECONDARY_RGB[1]) < 0.01
                    and abs(c.get("b", 0) - _BG_SECONDARY_RGB[2]) < 0.01):
                return True
        return False

    def walk(node):
        nonlocal fixed
        if not isinstance(node, dict):
            return
        bb = node.get("absoluteBoundingBox") or {}
        w, h = bb.get("width", 0), bb.get("height", 0)
        name = node.get("name") or ""
        ntype = (node.get("type") or "").upper()
        # square small icon button
        if (ntype == "FRAME" and w and h
                and 32 <= w <= 56 and 32 <= h <= 56
                and abs(w - h) < 4
                and BTN_RE.search(name)
                and is_bg_secondary(node.get("fills"))):
            try:
                call_tool("set_fill_color", {
                    "nodeId": node.get("id"),
                    "r": _BG_TERTIARY_RGB[0], "g": _BG_TERTIARY_RGB[1],
                    "b": _BG_TERTIARY_RGB[2], "a": 1,
                })
                fixed += 1
                print(f"  [icon-btn] '{name}' bg-secondary → bg-tertiary (시인성)")
            except Exception:
                pass
        for c in node.get("children") or []:
            walk(c)

    walk(root)
    if fixed == 0:
        print("  [icon-btn] OK — 시인성 부족 small icon button 없음")
    return fixed


def _disable_section_clipping(root_id: str) -> int:
    """R45 — 섹션/카드 frame 의 clipsContent=false 강제 (2026-05-24).

    Figma 는 frame 생성 시 default clipsContent=true. 섹션이 clip 되면:
      - 카드 drop shadow 가 잘려보임
      - 가로 carousel 마지막 카드 peek 이 안 보임
      - tooltip 같은 ABSOLUTE 자식이 부모 밖으로 못 나옴

    사용자가 명시적으로 viewport 효과(가로 carousel 마지막 peek)를 의도한 경우만 clip 유지:
      - 이름에 'carousel' / 'banner row' / 'hero row' 등 포함된 HORIZONTAL frame

    그 외 모든 FRAME(섹션/카드/래퍼)은 clipsContent=false 로 강제.
    root frame 은 viewport 자체라 건드리지 않음(이미 plugin 이 true 강제).

    Returns: fix 건수.
    """
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        root = items[0].get("document") if items else None
    except Exception as e:
        print(f"  [no-clip] 트리 조회 실패: {e}")
        return 0
    if not isinstance(root, dict):
        return 0

    def is_carousel_wrapper(n: dict) -> bool:
        nm = (n.get("name") or "").lower()
        if not nm:
            return False
        # carousel 류 — viewport clip 의도된 frame
        keys = ("carousel", "banner row", "hero row", "scroll row", "carousel wrap")
        return any(k in nm for k in keys)

    def is_rounded_card(n: dict) -> bool:
        """cornerRadius ≥ 8 frame — 카드 안 이미지/색 영역이 라운드 모서리 밖으로
        튀어나오면 안 됨. 2026-05-28 사용자 분노 fix (라운지 카드 상단 각짐).

        cornerRadius 가 있으면 clip 유지가 시각 정석. shadow 는 _strip_all_drop_shadows
        가 다 제거하므로 shadow-clearance 룰(R42)과 충돌 없음.
        """
        cr = n.get("cornerRadius")
        if isinstance(cr, (int, float)) and cr >= 8:
            return True
        # individual corner radii — top-left 등 하나라도 ≥8
        for k in ("topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius"):
            v = n.get(k)
            if isinstance(v, (int, float)) and v >= 8:
                return True
        return False

    targets = []  # (id, layoutMode)

    def walk(node, depth):
        if not isinstance(node, dict):
            return
        # root(depth=0) 자체는 건드리지 않음 — viewport
        if depth > 0 and (node.get("type") or "").upper() == "FRAME":
            if (node.get("clipsContent") is True
                    and not is_carousel_wrapper(node)
                    and not is_rounded_card(node)):  # 2026-05-28 rounded card 보호
                # layoutMode 가 None 이면 NONE 으로 전달 — plugin 이 clipsContent 만 적용
                lm = node.get("layoutMode") or "NONE"
                targets.append((node.get("id"), lm, node.get("name") or ""))
        for c in node.get("children", []) or []:
            walk(c, depth + 1)

    walk(root, 0)

    if not targets:
        print(f"  [no-clip] OK — clipsContent=true 인 비-carousel 섹션 frame 없음")
        return 0

    # batch_execute 로 한 번에 처리 — plugin 의 set_auto_layout 이 layoutMode=NONE 케이스도
    # clipsContent 적용하도록 패치돼 있음 (2026-05-24).
    ops = [{
        "op": "set_auto_layout",
        "params": {
            "nodeId": nid,
            "layoutMode": lm,
            "clipsContent": False,
        }
    } for (nid, lm, _nm) in targets]

    try:
        call_tool("batch_execute", {"operations": ops})
        print(f"  [no-clip] {len(targets)}개 frame clipsContent=false 강제 (carousel 제외)")
        return len(targets)
    except Exception as e:
        print(f"  [no-clip] batch 실패: {e}")
        return 0


def _normalize_row_cell_vertical_sizing_live(root_id: str) -> int:
    """HORIZONTAL 행의 동질 셀 그룹(회차 셀렉터·Day strip 등)에서 세로 사이징이
    섞여(일부 HUG, 일부 FIXED/FILL) baseline 이 어긋나는 버그 차단 (2026-06-02 사용자).

    사례: 'Round Cell 1~9' 는 HUG(h=23) 인데 빌드가 'Round Cell 10~13'(2자리) 만
    FIXED h=36 으로 만들어, 더 높은 셀 안 숫자가 ~6px 아래로 내려가 정렬이 틀어짐.
    blueprint 는 13개 전부 HUG 로 올발랐음 — 빌드 단계가 일부만 키운 회귀.

    Detection (보수적 — 오탐 방지):
      - HORIZONTAL auto-layout FRAME parent
      - 직계 FRAME 자식 중, 이름의 끝 숫자를 떼면 같은 prefix 인 그룹 (예 'Round Cell')
        이 3개 이상
      - 그 그룹의 layoutSizingVertical 값이 섞여 있거나 height 가 2px 초과로 다름
    Fix:
      - 그룹 다수의 vertical 사이징으로 통일. 단 다수가 FIXED 인데 height 가 들쭉날쭉이면
        HUG 로 통일(텍스트 셀은 HUG 가 정답 — 패딩+콘텐츠로 균일 높이).
    Returns: 통일한 그룹 수.
    """
    import re as _re
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        root = items[0].get("document") if items else None
    except Exception as e:
        print(f"  [row-cell-vsize] 트리 조회 실패: {e}")
        return 0
    if not isinstance(root, dict):
        return 0

    fixed = [0]

    def _prefix(nm: str) -> str:
        # 끝의 숫자/공백/하이픈 제거 → 'Round Cell 13' → 'round cell'
        return _re.sub(r"[\s\-_]*\d+\s*$", "", (nm or "")).strip().lower()

    def _h(n: dict) -> float:
        return float((n.get("absoluteBoundingBox") or {}).get("height") or 0)

    def _walk(node):
        if not isinstance(node, dict):
            return
        if (node.get("layoutMode") or "").upper() == "HORIZONTAL":
            kids = [c for c in (node.get("children") or [])
                    if (c.get("type") or "").upper() == "FRAME"]
            # prefix 별 그룹화
            groups: Dict[str, list] = {}
            for c in kids:
                p = _prefix(c.get("name") or "")
                if p:
                    groups.setdefault(p, []).append(c)
            for p, members in groups.items():
                if len(members) < 3:
                    continue
                sizes = [(m.get("layoutSizingVertical") or "").upper() for m in members]
                heights = [_h(m) for m in members]
                mixed_size = len(set(s for s in sizes if s)) > 1
                mixed_h = (max(heights) - min(heights)) > 2 if heights else False
                if not (mixed_size or mixed_h):
                    continue
                # target = 다수 사이징. FIXED 다수인데 height 들쭉날쭉이면 HUG.
                counts: Dict[str, int] = {}
                for s in sizes:
                    if s:
                        counts[s] = counts.get(s, 0) + 1
                target = max(counts, key=counts.get) if counts else "HUG"
                if target == "FIXED" and mixed_h:
                    target = "HUG"
                changed = 0
                for m, s in zip(members, sizes):
                    if s != target:
                        try:
                            call_tool("set_layout_sizing",
                                      {"nodeId": m["id"], "vertical": target})
                            changed += 1
                        except Exception:
                            pass
                if changed:
                    fixed[0] += 1
                    print(f"  [row-cell-vsize] '{node.get('name')}' 셀 그룹 '{p}' "
                          f"{changed}개 → vertical={target} 통일")
        for c in node.get("children", []) or []:
            _walk(c)

    _walk(root)
    if not fixed[0]:
        print("  [row-cell-vsize] OK — 행 셀 세로 사이징 일관")
    return fixed[0]


def _enforce_action_bar_equal_height(root_id: str) -> int:
    """하단 액션바(Bottom Action Bar / Action Bar / CTA Bar)의 버튼/아이콘 박스 높이를
    가장 큰 것에 통일 (2026-06-02 사용자: "버튼의 높이가 왜 다르지? 제일 큰거와 같아야 되").

    원인: 아이콘 박스(Bookmark/Chat 등)는 VERTICAL HUG 라 콘텐츠 높이(아이콘 ~22 /
    아이콘+라벨 ~37)로 붕괴하는데, 옆의 DS CTA 버튼은 ~44 라 높이가 제각각이 된다.

    판정 (보수적):
      - 이름에 'action bar' / 'cta bar' / 'bottom bar' 포함된 HORIZONTAL FRAME parent
        (Tab Bar 는 _enforce_tab_bar_children_fill_live 가 따로 처리 — 제외)
      - 직계 자식 중 버튼/박스류(FRAME 또는 INSTANCE; divider/home indicator/spacer 제외)
        가 2개 이상
    Fix:
      - 그 자식들 중 최대 높이 H 계산 → H 보다 낮은 자식을 vertical FIXED + height=H 로 통일
        (DS 버튼 인스턴스 높이가 보통 최대 → 아이콘 박스가 버튼 높이에 맞춰짐)
    Returns: 통일한 액션바 수.
    """
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        root = items[0].get("document") if items else None
    except Exception as e:
        print(f"  [action-bar-eq-h] 트리 조회 실패: {e}")
        return 0
    if not isinstance(root, dict):
        return 0

    fixed = [0]
    _BAR_HINTS = ("action bar", "cta bar", "bottom bar", "bottom action")
    _SKIP_CHILD = ("divider", "separator", "home indicator", "homeindicator",
                   "spacer", "gap")

    def _is_interactive_child(c):
        t = (c.get("type") or "").upper()
        if t not in ("FRAME", "INSTANCE", "COMPONENT"):
            return False
        nm = (c.get("name") or "").lower()
        if any(k in nm for k in _SKIP_CHILD):
            return False
        return True

    def _walk(node):
        if not isinstance(node, dict):
            return
        nm = (node.get("name") or "").lower()
        is_bar = ((node.get("layoutMode") or "").upper() == "HORIZONTAL"
                  and any(h in nm for h in _BAR_HINTS)
                  and "tab bar" not in nm and "tabbar" not in nm)
        if is_bar:
            kids = [c for c in (node.get("children") or []) if _is_interactive_child(c)]
            if len(kids) >= 2:
                heights = [_node_wh(c)[1] for c in kids]
                widths = [_node_wh(c)[0] for c in kids]
                max_w = max(widths) if widths else 0

                def _is_fill_cta(c, w):
                    t = (c.get("type") or "").upper()
                    nm = (c.get("name") or "").lower()
                    if t in ("INSTANCE", "COMPONENT"):
                        return True
                    if any(k in nm for k in ("btn", "button", "cta", "submit", "참여")):
                        return True
                    # icon 박스(작은 정사각)보다 확연히 넓으면 CTA
                    return bool(w and max_w and w >= max_w - 1 and w > 100)

                # 🔴 target = CTA(전폭 버튼/INSTANCE) 높이가 기준 (2026-06-04 사용자 의도:
                # 작은 아이콘 박스를 'CTA(제일 큰 버튼) 높이에 맞춰라'). DS 버튼은 자연 높이를
                # 유지(억지로 키우면 안 붙음)하고, 나머지(아이콘 박스)가 거기 맞춘다.
                # CTA 가 없으면 max 높이로 폴백.
                cta_heights = [h for c, h, w in zip(kids, heights, widths)
                               if _is_fill_cta(c, w) and h]
                target = cta_heights[0] if cta_heights else (max(heights) if heights else 0)

                if target and target > 0:
                    changed = 0
                    for c, h, w in zip(kids, heights, widths):
                        # CTA(기준)는 높이 안 건드림 — 단, 직전 패스가 폭을 FIXED 로
                        # 깨뜨렸을 수 있으니 가로 FILL 을 항상 재단언(라벨 잘림 방지).
                        if _is_fill_cta(c, w):
                            if (c.get("layoutSizingHorizontal") or "").upper() != "FILL":
                                try:
                                    call_tool("set_layout_sizing",
                                              {"nodeId": c["id"], "horizontal": "FILL"})
                                except Exception:
                                    pass
                            continue
                        if abs(h - target) > 1.5:
                            try:
                                # ⚠️ resize_node 는 폭·높이 둘 다 FIXED 로 박는다. 전폭 CTA
                                # 버튼은 FILL 이어야 하므로(안 그러면 폭이 고정돼 라벨 잘림),
                                # height 만 맞추고 CTA 는 **무조건 horizontal=FILL 재단언**한다.
                                # (이전 '원래 모드 보존' 방식은 직전 패스에서 이미 FIXED 가
                                #  돼버린 버튼의 FIXED 를 그대로 보존하는 버그가 있었음 — 2026-06-04.)
                                call_tool("set_layout_sizing",
                                          {"nodeId": c["id"], "vertical": "FIXED"})
                                call_tool("resize_node",
                                          {"nodeId": c["id"],
                                           "width": round(w) if w else 56,
                                           "height": round(target)})
                                if _is_fill_cta(c, w):
                                    call_tool("set_layout_sizing",
                                              {"nodeId": c["id"], "horizontal": "FILL"})
                                changed += 1
                            except Exception as e:
                                print(f"  [action-bar-eq-h] '{c.get('name')}' fail: {e}")
                    if changed:
                        fixed[0] += 1
                        print(f"  [action-bar-eq-h] ✓ '{node.get('name')}' 버튼 {changed}개 "
                              f"→ height={round(target)} 통일 (제일 큰 것에 맞춤)")
        for c in node.get("children", []) or []:
            _walk(c)

    _walk(root)
    if not fixed[0]:
        print("  [action-bar-eq-h] OK — 액션바 버튼 높이 일관")
    return fixed[0]


def _enforce_tab_bar_children_fill_live(root_id: str) -> int:
    """Bottom Tab Bar 자식 tab 들 (Tab 홈/커뮤니티/스테이지/...) 이 HUG 상태로 박혀
    라벨이 width=24 처럼 좁아져 두 줄 wrap 되는 버그 fix (2026-05-28 사용자 분노).

    Detection:
      - 이름에 'tab bar'/'tabbar'/'bottom tab' 포함된 HORIZONTAL FRAME parent
      - 자식 중 2개 이상이 HUG horizontal (FILL 아님)
      - 자식 frame 안 TEXT 가 두 줄 이상 (height ≥ 32) — wrap 신호
    Fix:
      - 각 tab 자식 frame layoutSizingHorizontal=FILL (5등분 균등)
      - parent layoutMode=HORIZONTAL + primaryAxisAlignItems=MIN + counterAxisAlignItems=CENTER
        + itemSpacing=0 (FILL 자식이 width 채우므로)

    Returns: fix 건수.
    """
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        root = items[0].get("document") if items else None
    except Exception as e:
        print(f"  [tab-bar-fill] 트리 조회 실패: {e}")
        return 0
    if not isinstance(root, dict):
        return 0

    fixed = [0]

    def _is_tab_bar(n: dict) -> bool:
        nm = (n.get("name") or "").lower()
        if not any(k in nm for k in ("tab bar", "tabbar", "bottom tab", "bottom nav")):
            return False
        return (n.get("layoutMode") or "").upper() == "HORIZONTAL"

    def _walk(node):
        if not isinstance(node, dict):
            return
        if _is_tab_bar(node):
            kids = node.get("children") or []
            tab_kids = [c for c in kids if (c.get("type") or "").upper() == "FRAME"]
            if len(tab_kids) >= 3:
                # Tab Bar 자식 FILL 강제 + parent MIN
                try:
                    # parent — MIN + CENTER, itemSpacing=0
                    pads = {
                        "paddingTop": node.get("paddingTop") or 8,
                        "paddingBottom": node.get("paddingBottom") or 16,
                        "paddingLeft": node.get("paddingLeft") or 12,
                        "paddingRight": node.get("paddingRight") or 12,
                    }
                    call_tool("set_auto_layout", {
                        "nodeId": node["id"],
                        "layoutMode": "HORIZONTAL",
                        "primaryAxisAlignItems": "MIN",
                        "counterAxisAlignItems": "CENTER",
                        "itemSpacing": 0,
                        **pads,
                    })
                    for tk in tab_kids:
                        try:
                            call_tool("set_layout_sizing", {"nodeId": tk["id"], "horizontal": "FILL"})
                        except Exception:
                            pass
                        # 라벨 wrap 차단: tab 자식 안 TEXT (tab-label) → textAutoResize=HEIGHT, FILL horizontal
                        for cc in tk.get("children", []) or []:
                            if (cc.get("type") or "").upper() == "TEXT":
                                try:
                                    call_tool("set_text_properties", {
                                        "nodeId": cc["id"],
                                        "textAutoResize": "HEIGHT",
                                        "textAlignHorizontal": "CENTER",
                                    })
                                    call_tool("set_layout_sizing", {"nodeId": cc["id"], "horizontal": "FILL"})
                                except Exception:
                                    pass
                    fixed[0] += 1
                except Exception as e:
                    print(f"  [tab-bar-fill] '{node.get('name')}' fail: {e}")
            return  # Tab Bar 내부 더 walk 안 함
        for c in node.get("children", []) or []:
            _walk(c)

    _walk(root)
    if fixed[0]:
        print(f"  [tab-bar-fill] ✓ Tab Bar {fixed[0]}건 자식 FILL + 라벨 textAutoResize=HEIGHT 강제")
    else:
        print("  [tab-bar-fill] OK — Tab Bar 자식 FILL 이미 적용")
    return fixed[0]


def _center_text_in_small_cells_live(root_id: str) -> int:
    """작은 cell (width ≤ 60) 안 TEXT 는 textAlignHorizontal/Vertical=CENTER 강제
    (2026-05-28 사용자 명시 — Month Cell Jan Active 안 'Jan/1' 좌측 정렬 분노).

    Detection:
      - FRAME width ≤ 60 (작은 cell — month/day cell, badge, chip 등)
      - 자식 TEXT 의 textAlignHorizontal 이 CENTER 가 아님
    Fix: TEXT 각각에 set_text_align(CENTER, CENTER).

    Returns: fix 건수.
    """
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        root = items[0].get("document") if items else None
    except Exception as e:
        print(f"  [text-center-fix] 트리 조회 실패: {e}")
        return 0
    if not isinstance(root, dict):
        return 0

    fixed = [0]

    def _walk(node):
        if not isinstance(node, dict):
            return
        if (node.get("type") or "").upper() == "FRAME":
            w = node.get("width") or 0
            if isinstance(w, (int, float)) and 0 < w <= 60:
                for c in node.get("children", []) or []:
                    if (c.get("type") or "").upper() == "TEXT":
                        h_align = (c.get("textAlignHorizontal") or "").upper()
                        v_align = (c.get("textAlignVertical") or "").upper()
                        if h_align != "CENTER" or v_align != "CENTER":
                            try:
                                call_tool("set_text_align", {
                                    "nodeId": c["id"],
                                    "textAlignHorizontal": "CENTER",
                                    "textAlignVertical": "CENTER",
                                })
                                fixed[0] += 1
                            except Exception as e:
                                print(f"  [text-center-fix] '{c.get('name')}' fail: {e}")
        for c in node.get("children", []) or []:
            _walk(c)

    _walk(root)
    if fixed[0]:
        print(f"  [text-center-fix] ✓ 작은 cell 안 TEXT {fixed[0]}건 중앙 정렬 강제")
    else:
        print("  [text-center-fix] OK — 모든 작은 cell 안 TEXT 이미 중앙 정렬")
    return fixed[0]


def _fix_text_clip_in_small_round_cells(root_id: str) -> int:
    """작은 원형 cell (width ≤ 48 + cornerRadius ≥ width/3) 안 TEXT 가 cell 둥근
    모서리에 잘리는 버그 fix (2026-05-28 사용자 분노 — Month Cell Oct → 'Jct').

    Detection:
      - FRAME width ≤ 48
      - cornerRadius (or any individual corner) ≥ width/3 (반 원/원형 cell)
      - 자식 중 TEXT 가 width == cell.width (텍스트가 cell 가득)
    Fix: cornerRadius 를 max(8, width/5) 로 축소 (rounded square 로 변경).
         텍스트 jam 차단 — 좌우 모서리에서 텍스트 안전 거리 확보.

    Returns: fix 건수.
    """
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        root = items[0].get("document") if items else None
    except Exception as e:
        print(f"  [text-clip-fix] 트리 조회 실패: {e}")
        return 0
    if not isinstance(root, dict):
        return 0

    fixed = [0]

    def _cell_max_corner(n: dict) -> float:
        cr = n.get("cornerRadius") or 0
        if isinstance(cr, (int, float)):
            mx = float(cr)
        else:
            mx = 0.0
        for k in ("topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius"):
            v = n.get(k)
            if isinstance(v, (int, float)) and v > mx:
                mx = float(v)
        return mx

    def _walk(node):
        if not isinstance(node, dict):
            return
        if (node.get("type") or "").upper() == "FRAME":
            w = node.get("width") or 0
            if isinstance(w, (int, float)) and 0 < w <= 48:
                cr = _cell_max_corner(node)
                if cr >= w / 3.0:
                    # 자식 중 TEXT 가 cell width 가득인지 확인
                    txt_full = False
                    for c in node.get("children", []) or []:
                        if (c.get("type") or "").upper() == "TEXT":
                            tw = c.get("width") or 0
                            if isinstance(tw, (int, float)) and tw >= w - 1:
                                txt_full = True
                                break
                    if txt_full:
                        new_cr = max(8, int(w / 5))
                        try:
                            call_tool("set_corner_radius", {"nodeId": node["id"], "radius": new_cr})
                            fixed[0] += 1
                        except Exception as e:
                            print(f"  [text-clip-fix] '{node.get('name')}' fail: {e}")
        for c in node.get("children", []) or []:
            _walk(c)

    _walk(root)
    if fixed[0]:
        print(f"  [text-clip-fix] ✓ 작은 원형 cell {fixed[0]}건 cornerRadius 축소 (텍스트 잘림 차단)")
    else:
        print("  [text-clip-fix] OK — 텍스트 잘릴 만한 작은 원형 cell 없음")
    return fixed[0]


def _fix_space_between_col_baseline(root_id: str) -> int:
    """HORIZONTAL row + 자식이 VERTICAL stack (라벨/값) 패턴 일 때 균등 분포 + 중앙 정렬 강제.

    2026-05-28 사용자 분노 2회 — Summary Grid 3-col baseline 어긋남 + 좌측 박힘.

    Detection:
      - HORIZONTAL parent + primaryAxisAlignItems in (SPACE_BETWEEN, MIN)
      - 자식 ≥ 2, 각 자식이 VERTICAL frame + 자식 ≥ 2 TEXT (라벨/값 stack 패턴)
    Fix (3단):
      1. parent layoutMode HORIZONTAL + primaryAxisAlignItems=MIN (FILL 컬럼 분배 위해)
         + counterAxisAlignItems=CENTER + itemSpacing 기존 유지 (기본 12)
      2. 각 col layoutSizingHorizontal=FILL (3등분 균등)
         + col layoutMode=VERTICAL + counterAxisAlignItems=CENTER (col 안 children 가운데)
      3. 각 col 안 TEXT 자식 textAlignHorizontal=CENTER

    Returns: fix 건수.
    """
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        root = items[0].get("document") if items else None
    except Exception as e:
        print(f"  [col-baseline] 트리 조회 실패: {e}")
        return 0
    if not isinstance(root, dict):
        return 0

    fixed = [0]

    def _is_label_value_stack(n: dict) -> bool:
        if (n.get("type") or "").upper() != "FRAME":
            return False
        if (n.get("layoutMode") or "").upper() != "VERTICAL":
            return False
        kids = n.get("children") or []
        text_kids = [c for c in kids if (c.get("type") or "").upper() == "TEXT"]
        return len(text_kids) >= 2

    def _normalize_grid(parent: dict):
        """parent + 각 col + col 안 텍스트 모두 균등/중앙 정렬로 normalize."""
        kids = parent.get("children") or []
        col_kids = [c for c in kids if _is_label_value_stack(c)]
        if len(col_kids) < 2:
            return False
        # ⚠️ 2026-06-04 회귀 차단: '내 스케줄' 같은 **리스트 행**(작은 날짜셀 56 + 넓은 본문
        # 267)을 3-col stat grid 로 오인해 본문을 FILL+가운데 정렬시켜 레이아웃이 깨졌다.
        # 진짜 grid 는 컬럼 폭이 비슷하다(월입금/완료/남은 ≈ 균등). 컬럼 폭이 크게
        # 불균등(max > 2.2×min)하거나 작은 셀(≤72px)이 섞이면 list row → grid 아님, skip.
        _cw = [(_node_wh(c)[0] or 0) for c in col_kids]
        _cw = [w for w in _cw if w > 0]
        if _cw and (max(_cw) > 2.2 * min(_cw) or min(_cw) <= 72):
            return False
        spacing = parent.get("itemSpacing")
        if not isinstance(spacing, (int, float)) or spacing <= 0:
            spacing = 12
        # padding 유지 — ⚠️ get_nodes_info 가 padding 을 None 으로 누락 직렬화할 수 있어
        # `or 0` 로 읽으면 실제 16 패딩이 0 으로 파괴된다(2026-06-04 paddingLeft만 0 회귀).
        # 숫자로 확인된 값만 전달하고, 모르는 필드는 **생략**(set_auto_layout 가 기존값 보존).
        pads = {k: parent.get(k) for k in
                ("paddingTop", "paddingBottom", "paddingLeft", "paddingRight")
                if isinstance(parent.get(k), (int, float))}
        # 1) parent → HORIZONTAL + MIN + CENTER + itemSpacing
        try:
            call_tool("set_auto_layout", {
                "nodeId": parent["id"],
                "layoutMode": "HORIZONTAL",
                "primaryAxisAlignItems": "MIN",
                "counterAxisAlignItems": "CENTER",
                "itemSpacing": spacing,
                **pads,
            })
        except Exception as e:
            print(f"  [col-baseline] parent '{parent.get('name')}' fail: {e}")
            return False
        # 2) 각 col → FILL horizontal + VERTICAL + CENTER + col 안 텍스트 CENTER
        for col in col_kids:
            try:
                call_tool("set_layout_sizing", {"nodeId": col["id"], "horizontal": "FILL"})
                col_spacing = col.get("itemSpacing")
                if not isinstance(col_spacing, (int, float)):
                    col_spacing = 6
                call_tool("set_auto_layout", {
                    "nodeId": col["id"],
                    "layoutMode": "VERTICAL",
                    "primaryAxisAlignItems": "MIN",
                    "counterAxisAlignItems": "CENTER",
                    "itemSpacing": col_spacing,
                    "paddingTop": 0, "paddingBottom": 0, "paddingLeft": 0, "paddingRight": 0,
                })
                for t in col.get("children", []) or []:
                    if (t.get("type") or "").upper() == "TEXT":
                        try:
                            call_tool("set_text_align", {
                                "nodeId": t["id"],
                                "textAlignHorizontal": "CENTER",
                            })
                        except Exception:
                            pass
            except Exception as e:
                print(f"  [col-baseline] col '{col.get('name')}' fail: {e}")
        return True

    def _walk(node):
        if not isinstance(node, dict):
            return
        if (node.get("type") or "").upper() == "FRAME" \
                and (node.get("layoutMode") or "").upper() == "HORIZONTAL":
            kids = node.get("children") or []
            stack_kids = [c for c in kids if _is_label_value_stack(c)]
            if len(stack_kids) >= 2:
                if _normalize_grid(node):
                    fixed[0] += 1
        for c in node.get("children", []) or []:
            _walk(c)

    _walk(root)
    if fixed[0]:
        print(f"  [col-baseline] ✓ label/value 3-col grid {fixed[0]}건 균등 분포 + 텍스트 중앙 강제")
    else:
        print("  [col-baseline] OK — label/value stack grid 정상")
    return fixed[0]


def _enforce_rounded_card_clip_live(root_id: str) -> int:
    """🔴 절대규칙 (2026-06-04 사용자): radius 값이 있는 frame 은 **꼭** clipsContent=true.

    "frame에 radius 값을 넣으면 꼭!! Clip content 옵션 체크가 되어야 한다" — radius 가
    조금이라도(>0) 있으면 둥근 모서리가 콘텐츠를 클립하도록 clipsContent=true 강제.
    (기존 cr≥8 카드 한정 → 2026-06-04 모든 radius>0 으로 확대.)

    R45 (`_disable_section_clipping`) 가 frame clip 을 false 로 만들어도 이 enforcer 가
    R45 *직후* 돌아 radius 있는 frame 을 true 로 되돌린다. generator/manual fix 가 clip
    false 박아도 마지막에 true.

    대상: cornerRadius > 0 (또는 individual corner > 0) FRAME + 자식 ≥ 1.
    제외: root 자체(이미 plugin 이 true 강제), DS INSTANCE(master 가 제어).

    Returns: fix 건수.
    """
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        root = items[0].get("document") if items else None
    except Exception as e:
        print(f"  [rounded-card-clip] 트리 조회 실패: {e}")
        return 0
    if not isinstance(root, dict):
        return 0

    def _has_rounded_corner(n: dict) -> bool:
        cr = n.get("cornerRadius")
        if isinstance(cr, (int, float)) and cr > 0:
            return True
        for k in ("topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius"):
            v = n.get(k)
            if isinstance(v, (int, float)) and v > 0:
                return True
        return False

    targets = []

    def walk(node, depth):
        if not isinstance(node, dict):
            return
        if depth > 0 and (node.get("type") or "").upper() == "FRAME":
            kids = node.get("children") or []
            if _has_rounded_corner(node) and kids and node.get("clipsContent") is not True:
                lm = node.get("layoutMode") or "NONE"
                targets.append((node.get("id"), lm, node.get("name") or ""))
        for c in node.get("children", []) or []:
            walk(c, depth + 1)

    walk(root, 0)

    if not targets:
        print("  [rounded-card-clip] OK — rounded card 모두 clipsContent=true")
        return 0

    ops = [{
        "op": "set_auto_layout",
        "params": {
            "nodeId": nid,
            "layoutMode": lm,
            "clipsContent": True,
        }
    } for (nid, lm, _nm) in targets]
    try:
        call_tool("batch_execute", {"operations": ops})
        print(f"  [rounded-card-clip] ✓ rounded card {len(targets)}개 clipsContent=true 강제")
        return len(targets)
    except Exception as e:
        print(f"  [rounded-card-clip] batch 실패: {e}")
        return 0


def _fix_small_text_center(root_id: str) -> int:
    """짧은 TEXT 노드(≤4자) 가 FILL 폭 + LEFT 정렬이라 부모 center 자식과 어긋날 때
    textAlignHorizontal=CENTER 자동 변환. chat-badge "99+" 같은 케이스.

    Returns: fix 건수.
    """
    try:
        info = call_tool("get_nodes_info", {"nodeIds": [root_id]})
        items = parse_content(info).get("json") or []
        root = items[0].get("document") if items else None
    except Exception as e:
        print(f"  [text-center] 트리 조회 실패: {e}")
        return 0
    if not isinstance(root, dict):
        return 0
    fixed = 0

    def walk(node):
        nonlocal fixed
        if not isinstance(node, dict):
            return
        if (node.get("type") or "").upper() == "TEXT":
            chars = (node.get("characters") or "").strip()
            sz = node.get("layoutSizingHorizontal")
            align = node.get("textAlignHorizontal")
            # font size threshold: small badge/counter text only (≤11px).
            # 큰 section title 같은 게 잘못 잡히면 시각 망가짐 (empty-title "빈자리" 18px 케이스).
            tstyle = node.get("style") or {}
            fsize = tstyle.get("fontSize") if isinstance(tstyle, dict) else None
            if (len(chars) <= 4 and sz == "FILL"
                    and align in (None, "LEFT")
                    and isinstance(fsize, (int, float)) and fsize <= 11):
                try:
                    call_tool("set_text_align", {
                        "nodeId": node.get("id"), "horizontal": "CENTER",
                    })
                    fixed += 1
                    print(f"  [text-center] '{node.get('name')}' \"{chars}\" → CENTER")
                except Exception:
                    pass
        for c in node.get("children") or []:
            walk(c)

    walk(root)
    if fixed == 0:
        print("  [text-center] OK — center 필요 짧은 텍스트 없음")
    return fixed


# ── DS Text Style 자동 적용 (2026-05-12 사용자 "시스템에 박아" 지시 → 2026-05-22 머지로 소실 → 2026-05-24 복원) ──
# 빌드된 트리의 TEXT 노드 (fontSize, weight bucket) → DS textStyle key 자동 바인딩.
# ⚠️ 2026-06-12 회귀 수정: 이 스케일이 옛 DS(18/30/36 포함, 32/40 누락)로 하드코딩돼 있어
# 18px snap→18, 28px snap→30 이 됐는데 실제 맵(12/14/16/20/24/32/40/48)에 없어 타이틀이
# 조용히 미바인딩됐다. → 스케일은 TEXT_STYLE_MAP 의 실제 사이즈 집합에서 derive 한다.
# 아래 상수는 맵 로드 실패 시 폴백일 뿐이다 (실스케일과 동일하게 유지).
_DS_TEXT_SIZE_SCALE_FALLBACK = (12, 14, 16, 20, 24, 32, 40, 48)
_DS_TEXT_SIZE_TOLERANCE = 3
_TEXT_STYLE_MAP_CACHE: Optional[dict] = None

# DS Shadow fingerprint table (first DROP_SHADOW effect: offset.y, radius)
# ds/DESIGN_TOKENS.md 의 Shadows/* effect style 정의 기반
# 참고: shadow-sm·md·lg·xl·2xl 는 2개 effect 합성이지만 첫 effect 만으로 충분히 구분됨
_DS_SHADOW_FINGERPRINTS = [
    # (offset_y, radius, ds_style_name)
    (1, 2, "Shadows/shadow-xs"),
    (1, 3, "Shadows/shadow-sm"),
    (4, 6, "Shadows/shadow-md"),
    (12, 16, "Shadows/shadow-lg"),
    (20, 24, "Shadows/shadow-xl"),
    (24, 48, "Shadows/shadow-2xl"),
]
_EFFECT_STYLE_MAP_CACHE: Optional[dict] = None


def _weight_bucket(label) -> str:
    """폰트 weight 라벨을 (regular/medium/semibold/bold) 버킷으로 정규화."""
    s = str(label or "").lower()
    if "bold" in s and "semi" not in s and "demi" not in s:
        return "bold"
    if "semi" in s or "demi" in s:
        return "semibold"
    if "medium" in s:
        return "medium"
    return "regular"


def _text_style_map_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "ds", "TEXT_STYLE_MAP.json")


def _is_pretendard_text_style(name: str, family=None) -> bool:
    """빌드 텍스트는 Pretendard 라, DS text style 중 **Pretendard 패밀리만** 매칭해야 한다.
    Carmen sans 등 영문 전용 폰트 스타일을 매칭하면 plugin 이 그 폰트를 로드하려다
    hang/실패한다(22s+). family 정보가 있으면 그것으로 판별, 없으면(구 추출본) name 에
    'carmen' 등 비-Pretendard 마커가 있는지로 판별. (2026-06-01 근본 수정)"""
    if family:
        return "pretendard" in str(family).lower()
    n = (name or "").lower()
    # name 이 폰트 패밀리로 시작하는 DS 컨벤션: "Carmen sans/...", "Pretendard/..." 또는
    # "Display xl/Bold"(Pretendard 기본). 비-Pretendard 영문 폰트 마커를 제외한다.
    return "carmen" not in n


def _load_text_style_map_from_file() -> dict:
    """ds/TEXT_STYLE_MAP.json (DS 파일에서 1회 추출한 라이브러리 text style 목록)
    → {(size:int, weight_bucket:str): styleKey} 인덱스.

    `sync-text-styles` 명령으로 DS 파일(Imin Design System)에 plugin 연결된 상태에서
    한 번 추출해 생성한다. 작업 파일에는 로컬 text style 이 없어 get_styles 가 0건을
    반환하므로(=DS 를 라이브러리로 참조만 함), Figma 의 라이브러리-스타일-목록 API
    부재를 이 사전 추출본으로 우회한다. set_text_style_id 는 S:key, 형식이면
    importStyleByKeyAsync 로 라이브러리 스타일을 import 해 적용하므로 로컬 스타일이
    없어도 동작한다. (2026-06-01 재발방지 — variables 의 TOKEN_MAP.json 과 동일 패턴)"""
    path = _text_style_map_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  [text-style] TEXT_STYLE_MAP.json 로드 실패: {e}")
        return {}
    idx = {}
    for e in (data if isinstance(data, list) else []):
        size = e.get("fontSize")
        key = e.get("key")
        if not isinstance(size, (int, float)) or not key:
            continue
        name = e.get("name") or ""
        if not _is_pretendard_text_style(name, e.get("family")):
            continue
        suffix = e.get("style") or (name.split("/")[-1] if "/" in name else None)
        idx[(int(size), _weight_bucket(suffix))] = key
    return idx


def cmd_sync_text_styles() -> None:
    """DS 파일(Imin Design System)의 로컬 text style 을 추출해
    ds/TEXT_STYLE_MAP.json 에 저장한다.

    ⚠️ plugin 이 **DS 파일에 연결된 상태**에서 실행해야 한다. 작업 파일에는 로컬
    text style 이 없어 0건이 나온다. 한 번 추출해 레포에 커밋해두면 이후 모든 세션의
    빌드에서 _load_text_style_map fallback 으로 쓰여, 로컬 스타일 없이도 DS text style
    이 적용된다 (variables 의 TOKEN_MAP.json 과 동일 철학)."""
    try:
        d = parse_content(call_tool("get_styles", {})).get("json") or {}
    except Exception as e:
        print(f"❌ get_styles 실패: {e}")
        return
    texts = d.get("texts") or []
    out = []
    for t in texts:
        key = t.get("key")
        if not key:
            continue
        name = t.get("name") or ""
        out.append({
            "name": name,
            "key": key,
            "fontSize": t.get("fontSize"),
            "family": (t.get("fontName") or {}).get("family"),
            "style": (t.get("fontName") or {}).get("style")
                     or (name.split("/")[-1] if "/" in name else None),
        })
    if not out:
        print("⚠️ 로컬 text style 0건 — plugin 이 DS 파일(Imin Design System)에 "
              "연결됐는지 확인하세요.")
        print("   작업 파일에는 로컬 스타일이 없습니다. Figma 에서 DS 파일을 열고 "
              "plugin 실행 후 다시 시도하세요.")
        return
    path = _text_style_map_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"✓ DS text style {len(out)}개 추출 → {path}")
    print("  이 파일을 커밋하면 새 세션에서도 text style 이 자동 적용됩니다.")


def _effect_style_map_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "ds", "EFFECT_STYLE_MAP.json")


def cmd_sync_effect_styles() -> None:
    """DS 파일(Imin Design System)의 로컬 effect style(Shadows/* 등)을 키와 함께 추출해
    ds/EFFECT_STYLE_MAP.json 에 저장한다.

    ⚠️ plugin 이 **DS 파일(Imin Design System)에 연결된 상태**에서 실행해야 한다.
    작업 파일에는 effect style 이 라이브러리 *참조*만 있어 `getLocalEffectStylesAsync()`
    가 0건을 반환한다(Figma 는 라이브러리 스타일을 이름으로 조회하는 API 가 없음 —
    variables→VARIABLE_KEY_MAP.json, text style→TEXT_STYLE_MAP.json 과 동일 한계).
    한 번 추출해 커밋해두면 이후 모든 세션에서 `set_effect_style_id`(importStyleByKeyAsync)
    로 'Shadows/shadow-basic' 같은 DS effect style 을 키로 바인딩할 수 있다."""
    try:
        d = parse_content(call_tool("get_styles", {})).get("json") or {}
    except Exception as e:
        print(f"❌ get_styles 실패: {e}")
        return
    effects = d.get("effects") or []
    out = []
    for e in effects:
        key = e.get("key")
        if not key:
            continue
        out.append({"name": e.get("name") or "", "key": key})
    if not out:
        print("⚠️ 로컬 effect style 0건 — plugin 이 DS 파일(Imin Design System)에 "
              "연결됐는지 확인하세요.")
        print("   작업 파일에는 로컬 effect style 이 없습니다(라이브러리 참조만). "
              "Figma 에서 DS 파일을 열고 plugin 실행 후 다시 시도하세요.")
        return
    path = _effect_style_map_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    names = [o["name"] for o in out if "shadow" in (o["name"] or "").lower()]
    print(f"✓ DS effect style {len(out)}개 추출 → {path}")
    if names:
        print(f"  shadow 계열: {', '.join(names[:12])}")
    print("  이 파일을 커밋하면 새 세션에서도 effect style 키로 바인딩됩니다.")


def cmd_sync_paint_styles() -> None:
    """DS 파일(Imin Design System)의 로컬 paint(color) style — gradient 포함 — 을 키와 함께
    추출해 ds/PAINT_STYLE_MAP.json 에 저장한다 (sync-effect-styles 와 동일 패턴/한계).

    ⚠️ plugin 이 **DS 파일에 연결된 상태**에서 실행해야 한다 (작업 파일엔 라이브러리 참조만
    있어 getLocalPaintStylesAsync 가 0건). 2026-08-14 신설 — 변환본 gradient 버튼이 원본의
    'Gradient-6~5~4_h'(hover) 스타일을 물고 있어 base 스타일 키가 필요해짐."""
    try:
        d = parse_content(call_tool("get_styles", {})).get("json") or {}
    except Exception as e:
        print(f"❌ get_styles 실패: {e}")
        return
    colors = d.get("colors") or []
    out = []
    for c in colors:
        key = c.get("key")
        if not key:
            continue
        out.append({"name": c.get("name") or "", "key": key})
    if not out:
        print("⚠️ 로컬 paint style 0건 — plugin 이 DS 파일(Imin Design System)에 연결됐는지 확인.")
        return
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "ds", "PAINT_STYLE_MAP.json")
    # 🔴 병합 저장 (2026-08-14): 파일별 로컬 스타일이 흩어져 있어(예: Gradient/Brand 는
    # 다른 DS 파일 소속) 덮어쓰면 기존 채집 키가 유실된다 — key 기준 merge.
    prev = []
    try:
        with open(path, encoding="utf-8") as f:
            prev = json.load(f)
    except Exception:
        pass
    seen = {e.get("key") for e in out}
    merged = out + [e for e in prev if e.get("key") not in seen]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    out = merged
    grads = [o["name"] for o in out if "gradient" in (o["name"] or "").lower()]
    print(f"✓ DS paint style {len(out)}개 추출 → {path}")
    if grads:
        print(f"  gradient 계열: {', '.join(grads[:15])}")


def cmd_sync_components() -> None:
    """DS 파일(Imin Design System)의 로컬 COMPONENT / COMPONENT_SET 을 키와 함께
    추출해 ds/COMPONENT_KEY_MAP.json 에 저장한다 (DS v7 → Imin Design System 전수
    마이그레이션 기준 데이터).

    ⚠️ plugin 이 **Imin Design System 파일에 연결된 상태**에서 실행해야 한다. 작업
    파일에는 로컬 컴포넌트가 없어 0건이 나온다. 추출 후 ds_catalog.py 의 키를 이
    맵 기준으로 교체하면 DS v7 라이브러리 의존이 사라진다."""
    comps, sets = [], []
    try:
        comps = (parse_content(call_tool("get_local_components", {})) or {}).get("components") or []
    except Exception as e:
        print(f"❌ get_local_components 실패: {e}")
    try:
        sets = (parse_content(call_tool("get_local_component_sets", {})) or {}).get("componentSets") or []
    except Exception as e:
        print(f"❌ get_local_component_sets 실패: {e}")
    out = {
        "components": [{"name": c.get("name"), "key": c.get("key"), "id": c.get("id")}
                       for c in comps if c.get("key")],
        "componentSets": [{"name": s.get("name"), "key": s.get("key"), "id": s.get("id")}
                          for s in sets if s.get("key")],
    }
    total = len(out["components"]) + len(out["componentSets"])
    if total == 0:
        print("⚠️ 로컬 컴포넌트 0건 — plugin 이 Imin Design System 파일에 연결됐는지 확인하세요.")
        print("   Figma 에서 Imin Design System 파일을 열고 plugin 실행 후 다시 시도하세요.")
        return
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "ds", "COMPONENT_KEY_MAP.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"✓ Imin Design System 컴포넌트 {len(out['components'])}개 + "
          f"세트 {len(out['componentSets'])}개 추출 → {path}")
    print("  이 맵 기준으로 ds_catalog.py 의 DS v7 키를 교체하세요.")


def cmd_sync_variable_keys() -> None:
    """DS 변수(색·spacing·fontSize 등)의 figmaPath → key 를 추출해
    ds/VARIABLE_KEY_MAP.json 에 저장한다 (TEXT_STYLE_MAP 의 변수 판).

    ⚠️ plugin 이 **DS 변수에 접근 가능한 파일**에 연결된 상태에서 실행:
      - DS 파일(Imin Design System) 자체 → 로컬 변수로 추출, 또는
      - 팀 프로젝트의 작업 파일(라이브러리 enabled) → 라이브러리 변수로 추출.
    개인 Draft(라이브러리 끊김)에서는 0건이 나온다 — 그 상태를 구제하려고 만든 맵이므로
    반드시 라이브러리가 살아있는 위치에서 1회 추출해 레포에 커밋해둔다.

    이후 set_bound_variables 가 call_tool 중앙 변환으로 'K:{key}' 를 보내
    importVariableByKeyAsync 로 직접 import → Draft 에서도 변수 바인딩이 동작한다.
    """
    try:
        d = parse_content(call_tool("get_local_variables", {"includeLibrary": True})).get("json") or {}
    except Exception as e:
        print(f"❌ get_local_variables 실패: {e}")
        return
    out: Dict[str, str] = {}
    # 1) 로컬 변수 (DS 파일에 직접 연결했을 때)
    for v in d.get("variables") or []:
        nm, key = v.get("name"), v.get("key")
        if nm and key:
            out[nm] = key
    # 2) 라이브러리 컬렉션 변수 (작업 파일에 라이브러리 enabled 일 때)
    for col in d.get("libraryCollections") or []:
        for v in col.get("variables") or []:
            nm, key = v.get("name"), v.get("key")
            if nm and key:
                out.setdefault(nm, key)
    if not out:
        print("⚠️ DS 변수 0건 — plugin 이 라이브러리 접근 가능한 파일에 연결됐는지 확인하세요.")
        print("   개인 Draft 는 팀 라이브러리가 끊겨 변수가 안 보입니다. DS 파일(Imin Design")
        print("   System)을 열거나, 작업 파일을 팀 프로젝트로 옮긴 뒤 다시 시도하세요.")
        return
    path = os.path.normpath(VARIABLE_KEY_MAP_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
    global _variable_key_map
    _variable_key_map = None  # 캐시 무효화
    print(f"✓ DS 변수 {len(out)}개 figmaPath→key 추출 → {path}")
    print("  이 파일을 커밋하면 Draft 에서도 변수 바인딩(K:key import)이 동작합니다.")
    print("  적용: python3 scripts/figma_mcp_client.py auto-bind <rootId> <blueprint.json>")


def _load_text_style_map() -> dict:
    """DS text styles → {(size:int, weight_bucket:str): styleKey} 인덱스. 캐시.

    1순위: 현재 파일의 로컬 text style(get_styles). 2순위: 로컬이 0건이면
    ds/TEXT_STYLE_MAP.json fallback (DS 라이브러리만 참조하는 작업 파일 대응)."""
    global _TEXT_STYLE_MAP_CACHE
    if _TEXT_STYLE_MAP_CACHE is not None:
        return _TEXT_STYLE_MAP_CACHE
    try:
        d = parse_content(call_tool("get_styles", {})).get("json") or {}
    except Exception as e:
        print(f"  [text-style] get_styles 실패: {e}")
        d = {}
    idx = {}
    for t in (d.get("texts") or []):
        size = t.get("fontSize")
        if not isinstance(size, (int, float)):
            continue
        # DS style 이름 예: "Display 2xl/Bold", "Text md/Medium" — 끝의 슬래시-suffix 가 weight
        name = t.get("name") or ""
        if not _is_pretendard_text_style(name, (t.get("fontName") or {}).get("family")):
            continue  # Carmen sans 등 비-Pretendard 스타일 제외 (폰트 로드 hang 방지)
        suffix = name.split("/")[-1] if "/" in name else (t.get("fontName") or {}).get("style")
        bucket = _weight_bucket(suffix)
        idx[(int(size), bucket)] = t.get("key")
    # Fallback: 작업 파일에 로컬 text style 이 없으면(=DS 라이브러리만 참조) get_styles 가
    # 0건 → 사전 추출본 사용. 이게 없으면 text style 이 영영 적용 안 되는 회귀 발생.
    if not idx:
        idx = _load_text_style_map_from_file()
        if idx:
            print(f"  [text-style] 로컬 text style 0건 → ds/TEXT_STYLE_MAP.json fallback ({len(idx)}개)")
        else:
            print("  [text-style] ⚠️ 로컬 0건 + TEXT_STYLE_MAP.json 없음 — "
                  "DS 파일에서 `python3 scripts/figma_mcp_client.py sync-text-styles` 1회 실행 필요")
    _TEXT_STYLE_MAP_CACHE = idx
    return idx


def _ds_text_size_scale(style_map: Optional[dict] = None) -> tuple:
    """실제 DS text style 맵에 존재하는 사이즈 집합. 맵이 비면 폴백 상수.
    하드코딩 스케일이 맵과 어긋나 잘못된 사이즈로 snap → 미바인딩되는 회귀 방지 (2026-06-12)."""
    if style_map:
        sizes = sorted({s for (s, _w) in style_map.keys() if isinstance(s, int)})
        if sizes:
            return tuple(sizes)
    return _DS_TEXT_SIZE_SCALE_FALLBACK


def _snap_to_ds_size(size: int, style_map: Optional[dict] = None) -> Optional[int]:
    """off-scale 사이즈를 ±3px 안 가장 가까운 DS 스케일로 snap. 범위 밖이면 None.
    스케일은 실제 style_map 의 사이즈 집합 기준 (stale 하드코딩 금지)."""
    best, best_d = None, _DS_TEXT_SIZE_TOLERANCE + 1
    for s in _ds_text_size_scale(style_map):
        d = abs(size - s)
        if d < best_d:
            best, best_d = s, d
    return best


def _apply_ds_text_styles(root_id: str) -> None:
    """빌드된 트리의 모든 TEXT 노드에 DS Text Style 자동 바인딩.

    인스턴스 내부 노드(`I…;…`)는 건너뛴다 (인스턴스가 자기 스타일 보유).
    off-scale 사이즈는 ±3px 안 DS 스케일로 snap.
    """
    style_map = _load_text_style_map()
    if not style_map:
        print("  [text-style] DS text style 인덱스 비어있음 — 건너뜀")
        return
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
    except Exception as e:
        print(f"  [text-style] 빌드 트리 조회 실패: {e}")
        return
    if not isinstance(items, list) or not items:
        return
    built = items[0].get("document") or items[0]

    entries = []
    stats = {"applied": 0, "instance_skip": 0, "no_size": 0, "no_match": 0}
    no_match_detail = []  # (name, size, bucket) — 조용한 미바인딩 금지 (2026-06-12)

    def walk(node):
        if not isinstance(node, dict):
            return
        if node.get("type") in ("TEXT", "text"):
            nid = node.get("id") or ""
            if ";" in nid:
                stats["instance_skip"] += 1
            else:
                # get_nodes_info 는 TEXT 폰트 속성을 node.style 하위에 둔다
                tstyle = node.get("style") or {}
                size = tstyle.get("fontSize")
                bucket = _weight_bucket(tstyle.get("fontStyle"))
                if not isinstance(size, (int, float)):
                    stats["no_size"] += 1
                else:
                    si = int(round(size))
                    key = style_map.get((si, bucket))
                    if not key:
                        snapped = _snap_to_ds_size(si, style_map)
                        if snapped is not None:
                            key = style_map.get((snapped, bucket))
                    if key:
                        entries.append({"nodeId": nid, "textStyleId": f"S:{key},{root_id}"})
                        stats["applied"] += 1
                    else:
                        stats["no_match"] += 1
                        no_match_detail.append((node.get("name") or nid, si, bucket))
        for c in node.get("children", []) or []:
            walk(c)

    walk(built)
    if no_match_detail:
        scale = _ds_text_size_scale(style_map)
        print(f"  [text-style] ⚠️ DS 스타일 미매칭 {len(no_match_detail)}건 — "
              f"blueprint fontSize 를 DS 스케일 {scale} 로 맞출 것:")
        for nm, si, bucket in no_match_detail[:10]:
            print(f"    - '{nm}' {si}px {bucket} (±{_DS_TEXT_SIZE_TOLERANCE}px 안 DS 스타일 없음)")
    if not entries:
        print(f"  [text-style] 적용 0건 (스킵: instance {stats['instance_skip']} / no-size {stats['no_size']} / no-match {stats['no_match']})")
        return
    # NOTE: `batch_set_text_style_id` 는 조용히 실패하는 케이스 확인됨 → 단일 set_text_style_id 루프로 안정 적용 (2026-05-24)
    ok, fail = 0, 0
    for e in entries:
        try:
            call_tool("set_text_style_id", {"nodeId": e["nodeId"], "textStyleId": e["textStyleId"]})
            ok += 1
        except Exception:
            fail += 1
    print(f"  [text-style] ✓ DS Text Style 적용 {ok}건"
          + (f" / 실패 {fail}건" if fail else "")
          + f" (스킵: instance {stats['instance_skip']} / no-match {stats['no_match']})")

    # ⚠️ 2026-05-24 사용자 "다 박아" — set_text_style_id silent fail 검출 + 1회 재시도
    # set_text_style_id 가 ok=N 반환하지만 실제 stored 안 되는 케이스 확인 (sticky-id mismatch).
    # get_nodes_info 응답이 Figma REST API 형식이라 textStyleId는 styles.text 에 들어옴.
    def _stored_text_style_id(d: dict) -> str:
        if not isinstance(d, dict):
            return ""
        return (d.get("textStyleId")
                or (d.get("styles") or {}).get("text")
                or (d.get("boundVariables") or {}).get("textStyleId")
                or "")
    try:
        applied_ids = [e["nodeId"] for e in entries]
        verify_info = parse_content(call_tool("get_nodes_info", {"nodeIds": applied_ids})).get("json")
        if isinstance(verify_info, list):
            stored_map = {}
            for it in verify_info:
                d = it.get("document") or it
                stored_map[d.get("id")] = bool(_stored_text_style_id(d))
            unset = [e for e in entries if not stored_map.get(e["nodeId"])]
            # ⚠️ 2026-05-28 사용자 분노 fix: 빌드 직후엔 Pretendard 폰트가 cold 라
            # importStyleByKeyAsync+setTextStyleIdAsync 가 27건 전부 실패하는데, 폰트가
            # warm 해지면(=import 시도들이 폰트를 로드) 성공한다. 1회 재시도는 같은
            # tick 이라 여전히 cold → 실패. 여러 pass 로 폰트가 warm 될 때까지 반복.
            attempt = 0
            while unset and attempt < 4:
                attempt += 1
                print(f"  [text-style] ⚠️ 미적용 {len(unset)}건 — 재시도 pass {attempt}...")
                for e in unset:
                    try:
                        call_tool("set_text_style_id", {"nodeId": e["nodeId"], "textStyleId": e["textStyleId"]})
                    except Exception:
                        pass
                verify2 = parse_content(call_tool("get_nodes_info", {"nodeIds": [e["nodeId"] for e in unset]})).get("json")
                still = {}
                if isinstance(verify2, list):
                    for it in verify2:
                        d = it.get("document") or it
                        still[d.get("id")] = bool(_stored_text_style_id(d))
                unset = [e for e in unset if not still.get(e["nodeId"])]
            if unset:
                print(f"  [text-style] ❌ {len(unset)}건 끝내 미적용 (폰트 로드 실패 가능)")
            else:
                print(f"  [text-style] ✓ stored 검증 OK — {len(applied_ids)}건 모두 styles.text 에 적용 확인")
    except Exception as e:
        print(f"  [text-style] stored 검증 실패 (skip): {e}")


def _load_effect_style_map() -> dict:
    """DS effect styles → {name: styleKey} 인덱스. 캐시.

    `Shadows/*` 와 `Focus rings/*` 같은 effect style 만 포함한다 (Backdrop blur 등은 매핑 대상 아님).
    """
    global _EFFECT_STYLE_MAP_CACHE
    if _EFFECT_STYLE_MAP_CACHE is not None:
        return _EFFECT_STYLE_MAP_CACHE
    try:
        d = parse_content(call_tool("get_styles", {})).get("json") or {}
    except Exception as e:
        print(f"  [effect-style] get_styles 실패: {e}")
        _EFFECT_STYLE_MAP_CACHE = {}
        return _EFFECT_STYLE_MAP_CACHE
    idx = {}
    for e in (d.get("effects") or []):
        name = e.get("name") or ""
        key = e.get("key")
        if name and key:
            idx[name] = key
    # fallback: 작업 파일엔 로컬 effect style 이 0건(라이브러리 참조) → 사전 추출본
    # ds/EFFECT_STYLE_MAP.json(sync-effect-styles) 을 병합 (TEXT_STYLE_MAP 과 동일 패턴).
    if not idx:
        try:
            p = _effect_style_map_path()
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh:
                    for o in json.load(fh) or []:
                        if o.get("name") and o.get("key"):
                            idx[o["name"]] = o["key"]
        except Exception as e:
            print(f"  [effect-style] EFFECT_STYLE_MAP.json 로드 실패: {e}")
    _EFFECT_STYLE_MAP_CACHE = idx
    return idx


def _collect_card_shadow_markers(bp: dict) -> tuple:
    """blueprint 에서 카드 그림자 마커 수집 → (force_names, skip_names).

    `_cardShadow: true` → force(자동감지 못하는 카드도 강제: 월렛 등 개별코너 radius).
    `_noShadow: true` / `_placeholderAllowed` → skip(배너 placeholder 등 그림자 제외).
    """
    force, skip = set(), set()

    def walk(n):
        if isinstance(n, dict):
            nm = n.get("name")
            if nm:
                if n.get("_cardShadow"):
                    force.add(nm)
                if n.get("_noShadow") or n.get("_placeholderAllowed"):
                    skip.add(nm)
            for c in n.get("children") or []:
                walk(c)
    walk(bp or {})
    return force, skip


def _apply_card_shadow_live(root_id: str, force_names: set, skip_names: set) -> int:
    """흰 면+보더 카드에 DS `Shadows/shadow-basic` effect style 을 자동 바인딩 (2026-06-18 사용자 룰:
    "표준으로 박아줘 — 빌드마다 자동").

    대상: FRAME + 흰 fill(bg-primary) + 보이는 보더 + width≥80 + DS 인스턴스 아님 + 이름이 skip 아님,
    그리고 (cornerRadius 8~99 둥근 카드) **또는** 이름이 force_names. shadow-basic = innerShadow(1px)
    + dropShadow(0,10,blur24). `_strip_all_drop_shadows` *뒤*(cmd_post_fix 맨 끝)에 실행해 살아남는다.
    키는 _load_effect_style_map()(→ds/EFFECT_STYLE_MAP.json fallback)에서. 멱등.
    """
    style_map = _load_effect_style_map()
    key = style_map.get("Shadows/shadow-basic")
    if not key:
        print("  [card-shadow] shadow-basic 키 없음 — skip "
              "(DS 파일에서 sync-effect-styles 1회 필요)")
        return 0
    applied = [0]

    def _is_white_border(n):
        if (n.get("type") or "").upper() != "FRAME":
            return False
        if ";" in (n.get("id") or "") or n.get("componentKey"):
            return False
        fills = n.get("fills") or []
        if not (fills and isinstance(fills[0], dict) and fills[0].get("visible", True)
                and fills[0].get("type") == "SOLID"):
            return False
        c = fills[0].get("color") or {}
        if not (c.get("r", 0) > 0.93 and c.get("g", 0) > 0.93 and c.get("b", 0) > 0.93):
            return False
        strokes = n.get("strokes") or []
        if not (strokes and isinstance(strokes[0], dict) and strokes[0].get("visible", True)):
            return False
        bb = n.get("absoluteBoundingBox") or {}
        return (bb.get("width") or 0) >= 80

    def _is_frame_card(n):
        # forced 카드용 기본 체크(흰색 아니어도 됨): FRAME + DS 인스턴스 아님 + width≥80
        if (n.get("type") or "").upper() != "FRAME":
            return False
        if ";" in (n.get("id") or "") or n.get("componentKey"):
            return False
        bb = n.get("absoluteBoundingBox") or {}
        return (bb.get("width") or 0) >= 80

    def walk(n):
        if not isinstance(n, dict):
            return
        nm = n.get("name")
        if nm not in skip_names:
            cr = n.get("cornerRadius")
            rounded = isinstance(cr, (int, float)) and 8 <= cr < 100
            forced = nm in force_names
            # 흰+보더 둥근 카드(자동) 또는 _cardShadow 마커(흰색 아니어도 — 강조 CTA 등)
            if (_is_white_border(n) and rounded) or (forced and _is_frame_card(n)):
                try:
                    call_tool("set_effect_style_id",
                              {"nodeId": n["id"], "effectStyleId": f"S:{key},{n['id']}"})
                    applied[0] += 1
                except Exception as e:
                    print(f"  [card-shadow] '{n.get('id')}' fail: {e}")
        for c in n.get("children") or []:
            walk(c)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0])
    except Exception as e:
        print(f"  [card-shadow] root fetch fail: {e}")
    if applied[0]:
        print(f"  [card-shadow] ✓ 흰 카드 {applied[0]}개 Shadows/shadow-basic 바인딩")
    return applied[0]


def _shadow_fingerprint(effects) -> Optional[tuple]:
    """첫 DROP_SHADOW effect 의 (y, radius) 핑거프린트 추출. visible=False/INNER_SHADOW 는 무시."""
    if not isinstance(effects, list):
        return None
    for ef in effects:
        if not isinstance(ef, dict):
            continue
        if ef.get("type") != "DROP_SHADOW":
            continue
        if ef.get("visible") is False:
            continue
        off = ef.get("offset") or {}
        y = off.get("y")
        r = ef.get("radius")
        if isinstance(y, (int, float)) and isinstance(r, (int, float)):
            return (float(y), float(r))
    return None


def _match_ds_shadow(fp: tuple, style_map: dict) -> Optional[str]:
    """fingerprint → 가장 가까운 DS Shadows/* 스타일 키. tolerance 없이 nearest 매칭."""
    if not fp or not style_map:
        return None
    y, r = fp
    best_name, best_d = None, float("inf")
    for cy, cr, name in _DS_SHADOW_FINGERPRINTS:
        # 라디우스 차이가 더 무겁게 작용 (시각적 임팩트가 큼)
        d = ((y - cy) ** 2) + ((r - cr) ** 2) * 1.5
        if d < best_d and name in style_map:
            best_name, best_d = name, d
    return best_name


_NON_INTERACTIVE_NAME_RE = re.compile(
    r"\b(badge|pill|tag|chip|status|mark|progress|track|bar|divider|wrap|indicator|dot)\b",
    re.I,
)
_INTERACTIVE_NAME_RE = re.compile(
    r"\b(btn|button|cta|input|select|dropdown|toggle|switch|stepper|minus|plus)\b|^cta\b|cta$",
    re.I,
)


def _is_non_interactive_decoration(node: dict) -> bool:
    """badge / pill / progress bar 같이 interaction 없는 작은 UI 요소 detect (2026-05-27).

    Heuristic (shape + name 조합):
      - 이름이 interactive (btn/button/cta/input 등) → False (shadow 유지)
      - 이름이 non-interactive (badge/pill/progress/track 등) → True
      - shape-based fallback:
        * 작은 정사각 frame (≤50px, |w-h|<4) — icon wrap → True
        * 얇은 가로 막대 (width>=60, height<=12) — progress bar → True
        * 작은 pill (cornerRadius>=999, width<100, height<=30) — badge/pill → True
    """
    if not isinstance(node, dict):
        return False
    name = node.get("name") or ""
    if _INTERACTIVE_NAME_RE.search(name):
        return False
    if _NON_INTERACTIVE_NAME_RE.search(name):
        return True
    bb = node.get("absoluteBoundingBox") or {}
    w = bb.get("width") or node.get("width") or 0
    h = bb.get("height") or node.get("height") or 0
    cr = node.get("cornerRadius") or 0
    # 작은 정사각 icon wrap
    if 0 < w <= 50 and 0 < h <= 50 and abs(w - h) < 4:
        return True
    # 얇은 가로 막대 (progress bar)
    if w >= 60 and 0 < h <= 12:
        return True
    # 작은 pill (badge/tag)
    if cr >= 999 and 0 < w < 100 and 0 < h <= 30:
        return True
    return False


def _remove_shadow_from_non_interactive(root_id: str) -> int:
    """비-interaction UI 요소 (badge/pill/progress bar/icon wrap) 의 drop shadow 제거 (2026-05-27).

    **Why:** 사용자 명시 룰 — "badge, progress bar 등과 같이 interaction 이 없는 UI
    요소들은 drop-shadow 가 필요 없다". shadow 는 elevation/depth 단서로 interactive
    surface (카드, 버튼) 에만 의미가 있음. 작은 decoration 에 shadow 가 깔리면
    시각적 노이즈 + 부정확한 위계.

    Detection: `_is_non_interactive_decoration` (이름 + shape 휴리스틱).
    Fix: `set_effects` 로 effects = [] 적용.
    """
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
    except Exception as e:
        print(f"  [no-shadow-deco] 트리 조회 실패: {e}")
        return 0
    if not isinstance(items, list) or not items:
        return 0
    built = items[0].get("document") or items[0]

    removed = [0]

    def walk(node):
        if not isinstance(node, dict):
            return
        nid = node.get("id") or ""
        if ";" not in nid:  # 인스턴스 내부 자식 skip
            effects = node.get("effects") or []
            has_shadow = any(
                isinstance(e, dict)
                and e.get("type") in ("DROP_SHADOW", "INNER_SHADOW")
                and e.get("visible") is not False
                for e in effects
            )
            already_styled = (node.get("styles") or {}).get("effect") or node.get("effectStyleId")
            if has_shadow and _is_non_interactive_decoration(node):
                try:
                    call_tool("set_effects", {"nodeId": nid, "effects": []})
                    removed[0] += 1
                    print(f"  [no-shadow-deco] '{node.get('name')}' shadow 제거 (non-interactive)")
                except Exception as e:
                    print(f"  [no-shadow-deco] '{node.get('name')}' 제거 실패: {e}")
        for c in node.get("children") or []:
            walk(c)

    walk(built)
    if removed[0] == 0:
        print("  [no-shadow-deco] OK — non-interactive 노드에 shadow 없음")
    return removed[0]


_UTIL_SECTION_NAME_PARTS = (
    "status bar", "nav bar", "navbar", "tab bar", "tabbar",
    "bottom action bar", "action bar", "cta bar", "fab", "footer",
)


def _enforce_no_large_brand_fill(blueprint: dict) -> None:
    """버튼이 아닌 큰 면적 frame 에 bg-brand-solid fill 금지 (2026-05-27 사용자 명시).

    "추천 스테이지 섹션같이 버튼이 아니면서 면적이 큰 frame에 brand color를 채우지마!"
    brand color 는 작은 액센트(텍스트, 버튼 label, dot)에만. 큰 카드/섹션 fill 금지.

    대상: type=frame + fill=$token(bg-brand-*) + (cornerRadius >= 12 AND children >= 2)
          또는 자식 수 >= 3 (구조적으로 큰 컨테이너)
    교정: fill → $token(bg-primary), stroke → $token(border-secondary) 1px
    제외: 작은 버튼/뱃지 (cornerRadius < 12 + children < 2)
    """
    BRAND_FILL_PARTS = ("bg-brand-solid", "bg-brand-primary", "bg-brand-section")
    PILL_BUTTON_KW = ("cta", "button", "btn", "submit", "action", "fab")
    flipped = [0]

    def is_large_container(node):
        # pill 버튼/CTA exclude — cornerRadius >= 100 (pill 모양) 이면 버튼이지 큰 카드 아님 (2026-05-27)
        radius = node.get("cornerRadius") or 0
        try:
            radius = float(radius)
        except (TypeError, ValueError):
            radius = 0
        if radius >= 100:  # pill shape (cornerRadius 999 같은)
            return False
        # name 이 cta/button/btn/submit/action/fab 키워드 포함 → 버튼
        name = (node.get("name") or "").lower()
        if any(k in name for k in PILL_BUTTON_KW):
            return False
        children_count = len(node.get("children") or [])
        # cornerRadius >= 12 인 카드형 + 자식 2개 이상  또는  자식 3개 이상
        return (radius >= 12 and children_count >= 2) or children_count >= 3

    # 🔻 2026-06-12 advisory 로 강등 (전면 개편): 큰 brand 면을 강제로 흰카드+보더로 flip 하던
    # 구 동작이 히어로 컬러 모먼트를 원천 차단 → 화면 수렴의 뿌리 중 하나. 이제 author 명시
    # fill 을 존중하고 WARN 만 — 대비/가독성은 _qa_visual_checks(대비 QA)가 별도로 방어한다.
    warned = []

    def walk(node):
        if not isinstance(node, dict):
            return
        ntype = node.get("type")
        if ntype in (None, "frame", "FRAME") and node.get("_band") is not True:
            fill = node.get("fill") or ""
            if isinstance(fill, str) and any(p in fill for p in BRAND_FILL_PARTS):
                if is_large_container(node):
                    warned.append(node.get("name") or "?")
        for c in node.get("children") or []:
            walk(c)

    walk(blueprint)
    if warned:
        print(f"[스타일-기본값] 큰 brand 면 {len(warned)}건 — author 명시 존중(변경 안 함). "
              f"의도된 히어로/강조 면이면 OK, 무의식적 brand 남발이면 재고: {', '.join(warned[:5])}")


def _strip_large_brand_fills(root_id: str) -> int:
    """빌드된 트리에서 큰 면적 frame 의 brand fill 자동 교정 (2026-05-27).

    cmd_post_fix 매 실행마다 회귀 차단. 인스턴스 내부 (`I…;…`) skip.
    """
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        built = items[0].get("document") if isinstance(items, list) and items else None
    except Exception:
        return 0
    if not isinstance(built, dict):
        return 0

    # bg-brand-* tokens 의 대표 색 RGB 패턴 (DS variable rgb)
    # 정확한 매칭은 boundVariables.fills[0].id 의 token name 으로 — 못 얻으면 RGB 휴리스틱
    def is_brand_color(rgb):
        r, g, b = rgb
        # brand purple 계열: r 약 0.4~0.6, g <= 0.4, b >= 0.6
        if g < 0.4 and b > 0.5 and r > 0.2 and r < 0.7:
            return True
        return False

    def _solid_rgba(paints):
        if not isinstance(paints, list):
            return None
        for p in paints:
            if not isinstance(p, dict) or p.get("visible") is False:
                continue
            if p.get("type") == "SOLID":
                col = p.get("color") or {}
                a = col.get("a", 1) * p.get("opacity", 1)
                return (col.get("r", 0), col.get("g", 0), col.get("b", 0), a)
        return None

    targets = []

    def walk(node):
        if not isinstance(node, dict):
            return
        nid = node.get("id") or ""
        if ";" in nid:
            return
        ntype = (node.get("type") or "").upper()
        if ntype == "FRAME":
            rgba = _solid_rgba(node.get("fills"))
            radius = node.get("cornerRadius") or 0
            # pill exclude — cornerRadius >= 100 인 pill 버튼/CTA 는 strip 대상 아님 (2026-05-27)
            if isinstance(radius, (int, float)) and radius >= 100:
                for c in node.get("children") or []:
                    walk(c)
                return
            # name 이 cta/button/btn/submit/fab/action 키워드 포함 → 버튼이지 카드 아님
            name = (node.get("name") or "").lower()
            if any(k in name for k in ("cta", "button", "btn", "submit", "action", "fab")):
                for c in node.get("children") or []:
                    walk(c)
                return
            children_count = len(node.get("children") or [])
            is_large = (radius >= 12 and children_count >= 2) or children_count >= 3
            if rgba and rgba[3] >= 0.5 and is_brand_color(rgba[:3]) and is_large:
                # 보너스 가드: 작은 버튼(width/height < 100)은 제외
                box = node.get("absoluteBoundingBox") or {}
                w = box.get("width") or 0
                h = box.get("height") or 0
                if w >= 100 and h >= 60:
                    targets.append((nid, node.get("name", "?")))
        for c in node.get("children") or []:
            walk(c)

    walk(built)

    fixed = 0
    WHITE = (0.988, 0.99, 0.992)
    # 🔻 2026-06-12 advisory 로 강등 (전면 개편): 라이브에서 brand 면을 흰카드로 벗기던 동작
    # 중지 — author 의 히어로/강조 컬러 면을 존중한다. 가독성은 _auto_fix_invisible_text(대비
    # 자동교정)와 _qa_visual_checks 가 별도 방어. WHITE 상수는 구 동작 흔적(미사용).
    # (2026-07-13: 삭제된 BORDER 참조 NameError 로 이 룰 전체가 매 빌드 조용히 죽던 버그 수정)
    _ = WHITE
    for nid, name in targets:
        print(f"    [스타일-기본값] 큰 brand 면 '{name}' — author 의도 존중(변경 안 함, 의도 확인만)")
    return fixed


def _auto_fix_invisible_text(root_id: str, ratio_threshold: float = 1.5) -> int:
    """대비 부족 TEXT 자동 교정 (2026-05-27 사용자 명시 — 회귀 차단).

    clone_node 후 token rebind 실패로 흰 카드 위 흰 텍스트가 박히는 회귀 사례
    (Underline Tab swap 시 active label fill = bg-primary 박힘) 차단용.
    배경 fill 과 대비 < `ratio_threshold` 인 TEXT 노드를 발견하면 자동 교정:
    - 밝은 배경 (luminance > 0.5) → text-primary 다크 (#2c3744 approx)
    - 어두운 배경 (luminance ≤ 0.5) → fg-white 흰 (#fcfcfd approx)
    인스턴스 내부 노드 (`I…;…`) 는 마스터가 관리하므로 skip.
    """
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
        built = items[0].get("document") if isinstance(items, list) and items else None
    except Exception:
        return 0
    if not isinstance(built, dict):
        return 0

    def _lin(x):
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    def _lum(c):
        return 0.2126 * _lin(c[0]) + 0.7152 * _lin(c[1]) + 0.0722 * _lin(c[2])

    def _ratio(c1, c2):
        l1, l2 = _lum(c1), _lum(c2)
        return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)

    def _solid(paints):
        if not isinstance(paints, list):
            return None
        for p in paints:
            if not isinstance(p, dict) or p.get("visible") is False:
                continue
            if p.get("type") == "SOLID":
                col = p.get("color") or {}
                a = col.get("a", 1) * p.get("opacity", 1)
                return (col.get("r", 0), col.get("g", 0), col.get("b", 0), a)
        return None

    targets = []

    def walk(node, bg):
        if not isinstance(node, dict):
            return
        ntype = (node.get("type") or "").upper()
        nid = node.get("id") or ""
        if ";" in nid:
            return
        node_bg = bg
        if ntype not in ("TEXT", "VECTOR"):
            fc = _solid(node.get("fills"))
            if fc and fc[3] >= 0.95:
                node_bg = fc[:3]
        if ntype == "TEXT":
            tc = _solid(node.get("fills"))
            chars = (node.get("characters") or "").strip()
            if tc and tc[3] >= 0.4 and chars:
                r = _ratio(tc[:3], bg)
                if r < ratio_threshold:
                    on_dark = _lum(bg) < 0.5
                    targets.append((nid, on_dark, chars[:14]))
        for c in node.get("children") or []:
            walk(c, node_bg)

    walk(built, (1.0, 1.0, 1.0))

    DARK = (0.174, 0.215, 0.266)   # text-primary
    WHITE = (0.988, 0.988, 0.992)  # text-primary_on-brand (fg-white)
    fixed = 0
    for nid, on_dark, sample in targets:
        color = WHITE if on_dark else DARK
        try:
            call_tool("set_fill_color", {
                "nodeId": nid, "r": color[0], "g": color[1], "b": color[2], "a": 1
            })
            fixed += 1
            print(f"    [invisible-text] '{sample}' → {'WHITE' if on_dark else 'DARK'} (대비 회복)")
        except Exception:
            pass
    return fixed


def _restore_content_section_padding(root_id: str, min_pad: int = 8) -> int:
    """divider 제거 부작용으로 padding 깎인 콘텐츠 섹션의 padding 복원 (2026-05-27).

    `_enforce_section_dividers` (폐기) 가 인접 섹션의 paddingTop/Bottom 을 0 으로 깎았던 부작용
    제거기. divider 자동 삭제 후 카드들이 붙어 보이지 않게 root 직계 콘텐츠 섹션의
    paddingTop / paddingBottom 을 `min_pad` 이상으로 강제.
    utility 섹션(NavBar / Tab Bar / Footer / FAB / Action Bar 등) 은 제외.
    """
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
    except Exception:
        return 0
    if not isinstance(items, list) or not items:
        return 0
    root = items[0].get("document") or items[0]

    fixed = 0
    for child in (root.get("children") or []):
        if not isinstance(child, dict):
            continue
        name = (child.get("name") or "").lower()
        if any(p in name for p in _UTIL_SECTION_NAME_PARTS):
            continue
        # ABSOLUTE 자식(FAB 등) 도 제외
        if child.get("layoutPositioning") == "ABSOLUTE":
            continue
        if child.get("layoutMode") not in ("VERTICAL", "HORIZONTAL"):
            continue
        pt = child.get("paddingTop") or 0
        pb = child.get("paddingBottom") or 0
        if pt >= min_pad and pb >= min_pad:
            continue
        new_pt = max(pt, min_pad)
        new_pb = max(pb, min_pad)
        try:
            # ⚠️ paddingLeft/Right/itemSpacing 은 변경 대상 아님 → **생략**해 보존.
            # `... or 0` 으로 읽으면 get_nodes_info 의 None 직렬화 때문에 실제 패딩이 0 으로
            # 파괴된다(2026-06-04 paddingLeft만 0 회귀). 바꿀 top/bottom 만 전달.
            args = {"nodeId": child.get("id"), "layoutMode": child.get("layoutMode"),
                    "paddingTop": new_pt, "paddingBottom": new_pb}
            for k in ("paddingLeft", "paddingRight", "itemSpacing"):
                v = child.get(k)
                if isinstance(v, (int, float)):
                    args[k] = v
            call_tool("set_auto_layout", args)
            fixed += 1
        except Exception:
            pass
    return fixed


def _strip_section_dividers(root_id: str) -> int:
    """빌드된 트리에서 "Section Divider" 노드 자동 삭제 (2026-05-27).

    사용자 명시: 섹션 사이에 divider 라인 자동 삽입 금지. 정보 그룹 경계는 카드 border 로.
    """
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
    except Exception:
        return 0
    if not isinstance(items, list) or not items:
        return 0
    built = items[0].get("document") or items[0]

    targets = []

    def walk(node):
        if not isinstance(node, dict):
            return
        nid = node.get("id") or ""
        if ";" in nid:
            return
        name = (node.get("name") or "").lower()
        if "section divider" in name or ("divider" in name and node.get("type") == "FRAME" and not node.get("children")):
            # "Section Divider" 컨테이너 또는 단독 1px divider line frame
            targets.append(nid)
        for c in node.get("children") or []:
            walk(c)

    walk(built)

    cleared = 0
    for nid in targets:
        try:
            call_tool("delete_node", {"nodeId": nid})
            cleared += 1
        except Exception:
            pass
    return cleared


def _strip_all_drop_shadows(root_id: str) -> int:
    """빌드된 트리의 모든 frame/component/instance 노드에서 visible DROP_SHADOW effect 제거 (2026-05-27).

    사용자 명시 절대 룰: drop-shadow 적용 금지. 카드 표면은 border 로 정의.
    인스턴스 내부 노드(`I…;…`)는 마스터가 자기 effect 보유하므로 skip.
    """
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
    except Exception:
        return 0
    if not isinstance(items, list) or not items:
        return 0
    built = items[0].get("document") or items[0]

    targets = []

    # 2026-05-28 polish-aware: hero/elevation/sub-card 이름 패턴은 shadow 허용 (사용자
    # polish baseline 17389:51811 의 카드 위계 차등 표현 가능)
    POLISH_SHADOW_KEEP_RE = ("hero", "elevation", "sub-card", "sub_card",
                              "alert", "banner", "raised", "floating")

    def walk(node):
        if not isinstance(node, dict):
            return
        nid = node.get("id") or ""
        # 인스턴스 내부 노드는 skip
        if ";" in nid:
            return
        # polish exception — 위 이름 패턴 노드의 shadow 는 보존
        nm_low = (node.get("name") or "").lower()
        if any(kw in nm_low for kw in POLISH_SHADOW_KEEP_RE):
            for c in node.get("children") or []:
                walk(c)
            return
        effs = node.get("effects") or []
        has_visible_shadow = any(
            isinstance(e, dict)
            and (e.get("type") or "").startswith("DROP_SHADOW")
            and e.get("visible", True)
            for e in effs
        )
        if has_visible_shadow:
            targets.append(nid)
        for c in node.get("children") or []:
            walk(c)

    walk(built)

    cleared = 0
    for nid in targets:
        try:
            call_tool("set_effects", {"nodeId": nid, "effects": []})
            cleared += 1
        except Exception:
            pass
    return cleared


def _apply_ds_effect_styles(root_id: str) -> None:
    """빌드된 트리의 모든 frame-like 노드에 DS Effect Style 자동 바인딩.

    대상: 가시 DROP_SHADOW effect 를 가진 frame/component/instance 노드.
    인스턴스 내부 노드(`I…;…`)는 건너뜀 (마스터/인스턴스가 자기 effectStyleId 보유).
    fingerprint(첫 DROP_SHADOW 의 y_offset, radius) → 가장 가까운 Shadows/* 스타일에 매핑.
    """
    style_map = _load_effect_style_map()
    if not style_map:
        print("  [effect-style] DS effect style 인덱스 비어있음 — 건너뜀")
        return
    # Shadows/* 가 하나도 없으면 매핑 불가
    if not any(n.startswith("Shadows/") for n in style_map.keys()):
        print("  [effect-style] DS 에 Shadows/* effect style 없음 — 건너뜀")
        return
    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_id]})).get("json")
    except Exception as e:
        print(f"  [effect-style] 빌드 트리 조회 실패: {e}")
        return
    if not isinstance(items, list) or not items:
        return
    built = items[0].get("document") or items[0]

    entries = []
    stats = {"applied": 0, "instance_skip": 0, "no_effects": 0, "no_match": 0, "already_bound": 0}

    def walk(node):
        if not isinstance(node, dict):
            return
        ntype = node.get("type") or ""
        if ntype in ("FRAME", "COMPONENT", "COMPONENT_SET", "INSTANCE", "RECTANGLE"):
            nid = node.get("id") or ""
            if ";" in nid:
                stats["instance_skip"] += 1
            else:
                effects = node.get("effects")
                # styles.effect 가 이미 채워져 있으면 skip (이미 스타일 바인딩 됨)
                already = (node.get("styles") or {}).get("effect") or node.get("effectStyleId")
                if already:
                    stats["already_bound"] += 1
                else:
                    fp = _shadow_fingerprint(effects)
                    if fp is None:
                        if effects:
                            stats["no_effects"] += 1
                    else:
                        name = _match_ds_shadow(fp, style_map)
                        if name:
                            key = style_map[name]
                            entries.append({
                                "nodeId": nid,
                                "effectStyleId": f"S:{key},{root_id}",
                                "_name": name,
                            })
                            stats["applied"] += 1
                        else:
                            stats["no_match"] += 1
        for c in node.get("children", []) or []:
            walk(c)

    walk(built)
    if not entries:
        print(f"  [effect-style] 적용 0건 "
              f"(스킵: instance {stats['instance_skip']} / already-bound {stats['already_bound']} / no-match {stats['no_match']})")
        return

    ok, fail = 0, 0
    by_style = {}
    for e in entries:
        try:
            call_tool("set_effect_style_id", {"nodeId": e["nodeId"], "effectStyleId": e["effectStyleId"]})
            ok += 1
            by_style[e["_name"]] = by_style.get(e["_name"], 0) + 1
        except Exception as ex:
            fail += 1
            if fail <= 3:
                print(f"  [effect-style] FAIL {e['nodeId']} ({e['_name']}): {ex}")
    summary = ", ".join(f"{n.split('/')[-1]}×{c}" for n, c in sorted(by_style.items()))
    print(f"  [effect-style] ✓ DS Effect Style 적용 {ok}건 ({summary})"
          + (f" / 실패 {fail}건" if fail else "")
          + f" (스킵: instance {stats['instance_skip']} / already-bound {stats['already_bound']} / no-match {stats['no_match']})")


def cmd_auto_bind(root_node_id: str, blueprint_file: str):
    """기존에 빌드된 디자인에 DS 변수 자동 바인딩 (standalone — 테스트/재적용용)."""
    ensure_session()
    with open(blueprint_file, encoding="utf-8") as f:
        blueprint = json.load(f)
    auto_bind_design(root_node_id, blueprint)


def cmd_bind(bindings_file: str):
    """Apply DS variable bindings from a JSON file.

    File format:
    [
        {"nodeId": "51:33050", "bindings": {"fills/0": "Colors/Brand/brand-600"}},
        ...
    ]
    """
    ensure_session()

    with open(bindings_file) as f:
        bindings_list = json.load(f)

    print(f"Applying {len(bindings_list)} binding operations...")
    start = time.time()

    success = 0
    fail = 0
    for i, item in enumerate(bindings_list):
        node_id = item["nodeId"]
        bindings = item["bindings"]
        try:
            call_tool("set_bound_variables", {
                "nodeId": node_id,
                "bindings": bindings
            }, msg_id=i + 1)
            success += 1
        except Exception as e:
            print(f"  FAIL {node_id}: {e}")
            fail += 1

        if (i + 1) % 50 == 0:
            print(f"  Progress: {i + 1}/{len(bindings_list)}")

    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f}s — {success} success, {fail} fail")


def cmd_bind_text_styles(styles_file: str):
    """Apply text style bindings from a JSON file.

    File format:
    [
        {"nodeId": "51:33100", "textStyleId": "S:key,nodeId"},
        ...
    ]
    """
    ensure_session()

    with open(styles_file) as f:
        styles_list = json.load(f)

    print(f"Applying {len(styles_list)} text style bindings...")
    start = time.time()

    success = 0
    fail = 0
    for i, item in enumerate(styles_list):
        try:
            call_tool("set_text_style_id", {
                "nodeId": item["nodeId"],
                "textStyleId": item["textStyleId"]
            }, msg_id=i + 1)
            success += 1
        except Exception as e:
            print(f"  FAIL {item['nodeId']}: {e}")
            fail += 1

    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f}s — {success} success, {fail} fail")


def cmd_interactive():
    """Interactive REPL for MCP tool calls."""
    ensure_session()
    print("Figma MCP Interactive Mode (type 'help' or 'quit')")

    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not line:
            continue
        if line in ("quit", "exit", "q"):
            break
        if line == "help":
            print("Commands:")
            print("  <tool_name> <json_args>  — call a tool")
            print("  list                     — list available tools")
            print("  quit                     — exit")
            continue
        if line == "list":
            content = call_tool("get_document_info", {})
            result = parse_content(content)
            print("(Use 'tools/list' for full list)")
            if result["json"]:
                print(json.dumps(result["json"], indent=2, ensure_ascii=False))
            continue

        parts = line.split(None, 1)
        tool_name = parts[0]
        args_str = parts[1] if len(parts) > 1 else "{}"

        try:
            args = json.loads(args_str)
            content = call_tool(tool_name, args)
            result = parse_content(content)
            if result["json"]:
                print(json.dumps(result["json"], indent=2, ensure_ascii=False))
            else:
                for t in result["texts"]:
                    print(t)
            if result["images"]:
                print(f"[{len(result['images'])} image(s)]")
        except Exception as e:
            print(f"Error: {e}")


def cmd_cleanup_qa():
    """QA 스크린샷/체크리스트 + 레퍼런스 썸네일 즉시 전체 삭제 (2026-06-08 사용자 룰).

    작업 중 Claude 가 소비하려고 만든 임시 산출물 2종을 작업 완료 후 비운다(7일 대기하는
    cleanup_old_blueprints.py 와 별개로 즉시):
      - `scripts/qa_screenshots/<root>/` — self-verify(절대 규칙 0-F)용 PNG + self_verify_checklist.json
      - `scripts/ref_thumbnails/`        — 레퍼런스 학습(절대 규칙 0-G)용 ≤1200px 썸네일
    각 폴더 자체는 유지(다음 빌드가 재생성). self-verify/레퍼런스 Read 가 모두 끝난 뒤 호출한다."""
    # 🔴 self-verify 게이트 (2026-06-11 — 0-F): self-verify 를 안 했는데 정리(=작업 종료)
    # 하려는 것을 차단. checklist/PNG 를 지우기 전에 모델이 실제로 검증했는지 확인.
    _enforce_selfverify_gate("cleanup-qa")
    import shutil
    here = os.path.dirname(__file__)
    total = 0
    for label, folder in (("QA 스크린샷/체크리스트", "qa_screenshots"),
                          ("레퍼런스 썸네일", "ref_thumbnails")):
        root = os.path.join(here, folder)
        removed = 0
        if os.path.isdir(root):
            for entry in os.listdir(root):
                p = os.path.join(root, entry)
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p)
                    else:
                        os.remove(p)
                    removed += 1
                except Exception as e:
                    print(f"  [cleanup-qa] '{folder}/{entry}' 삭제 실패: {e}")
        total += removed
        print(f"🧹 [cleanup-qa] {label} {removed}개 항목 삭제 (scripts/{folder} 비움)")
    return total


def cmd_export(node_id: str, out_path: str = None, scale: float = 2, fmt: str = "PNG"):
    """노드를 이미지로 export 해 파일로 저장 (2026-06-10).

    `call export_node_as_image` 는 이미지를 stdout 에 못 떨궈서 매번 인라인 파이썬으로
    base64 decode → 파일 쓰기를 반복해야 했다. 이 명령이 그 보일러플레이트를 대체한다.

    Usage: figma_mcp_client.py export <nodeId> [out_path] [--scale N] [--jpg]
      out_path 미지정 시 scripts/qa_screenshots/<nodeId 안전화>.png 로 저장.
    """
    import base64
    ensure_session()
    if not out_path:
        safe = node_id.replace(":", "_").replace("/", "_")
        out_path = os.path.join(os.path.dirname(__file__), "qa_screenshots", safe + ".png")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    content = call_tool("export_node_as_image", {"nodeId": node_id, "format": fmt, "scale": scale})
    # self-verify 게이트(0-F) 추적 — hook 은 MCP 직접 호출(tool_input.nodeId)만 보므로,
    # 블레스드 CLI 경로인 cmd_export 가 직접 qa_<sid>.json 에 기록한다 (2026-06-12 갭 픽스:
    # CLI 로 export+Read 를 다 해도 게이트가 '미재export' 로 오차단하던 문제).
    sid = _current_claude_session()
    if sid:
        try:
            qp = os.path.join(_planning_gate_dir(), "qa_%s.json" % sid)
            try:
                with open(qp, encoding="utf-8") as fh:
                    cur = json.load(fh)
            except Exception:
                cur = {}
            s = set(cur.get("exported") or [])
            s.add(str(node_id))
            cur["exported"] = sorted(s)
            cur["ts"] = int(time.time())
            with open(qp, "w", encoding="utf-8") as fh:
                json.dump(cur, fh, ensure_ascii=False)
        except Exception:
            pass
    saved = False
    for item in content:
        if item.get("type") == "image":
            data = item.get("data") or (item.get("source") or {}).get("data")
            if data:
                if isinstance(data, str) and data.startswith("data:"):
                    data = data.split(",", 1)[1]
                with open(out_path, "wb") as f:
                    f.write(base64.b64decode(data))
                size = os.path.getsize(out_path)
                print(f"🖼  [export] {node_id} → {out_path} ({size:,} bytes)")
                saved = True
                break
    if not saved:
        # 이미지가 없으면 텍스트(에러 등) 출력
        for item in content:
            if item.get("type") == "text":
                print(f"[export] 이미지 없음: {item.get('text','')[:200]}")
                break
        else:
            print("[export] 이미지 없음 (응답에 image/text content 없음)")
        sys.exit(1)
    return out_path


def cmd_assemble(config_file: str):
    """섹션 템플릿을 조립하여 완전한 Blueprint JSON을 생성.

    config_file: 템플릿 조립 설정 JSON
    형식:
    {
      "rootName": "Screen Name",
      "width": 393,
      "height": 1680,
      "fill": "$token(bg-primary)",
      "sections": ["NavBar", "Ribbon", "Hero", ...custom..., "FAB", "TabBar"],
      "variables": {
        "FAB": {"label": "마이 월렛", "icon": "wallet-02"},
        "Ribbon": {"text": "누적 거래 5,000,000건"},
        "Hero": {"banners": [{"fill": "...", "tag": "...", "title": "...", ...}]}
      },
      "customSections": [ ... raw blueprint nodes ... ]
    }

    출력: scripts/blueprint_assembled_<rootName>.json → build 실행 가능
    """
    TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "blueprint_templates.json")
    if not os.path.exists(TEMPLATES_PATH):
        print(f"❌ 템플릿 파일 없음: {TEMPLATES_PATH}")
        return

    with open(TEMPLATES_PATH) as f:
        templates = json.load(f)
    sections_db = templates.get("sections", {})

    with open(config_file) as f:
        config = json.load(f)

    root_name = config.get("rootName", "Assembled Screen")
    width = config.get("width", 393)
    height = config.get("height", 1680)
    fill = config.get("fill", "$token(bg-primary)")
    section_order = config.get("sections", [])
    variables = config.get("variables", {})
    custom_sections = config.get("customSections", [])

    # alias 매핑: 짧은 이름 → 템플릿 DB 키
    SECTION_ALIASES = {
        "Ribbon": "TransactionRibbon",
        "Hero": "HeroSection",
        "Tab": "TabBar",
    }

    children = []
    custom_idx = 0
    import copy

    for section_name in section_order:
        # alias 해석
        resolved_name = SECTION_ALIASES.get(section_name, section_name)

        if section_name == "custom" or section_name.startswith("custom:"):
            # customSections 배열에서 순서대로 가져옴
            if custom_idx < len(custom_sections):
                node = custom_sections[custom_idx]
                custom_idx += 1
                children.append(node)
            else:
                print(f"  ⚠️ custom section #{custom_idx} 없음 — 건너뜀")
        elif resolved_name in sections_db:
            template_node = copy.deepcopy(sections_db[resolved_name]["template"])

            # 변수 치환 — 원본 이름과 alias 둘 다 확인
            section_vars = variables.get(section_name, variables.get(resolved_name, {}))
            template_node = _apply_template_vars(template_node, section_vars, resolved_name)

            children.append(template_node)
            print(f"  ✅ 템플릿 적용: {section_name}" + (f" → {resolved_name}" if section_name != resolved_name else ""))
        else:
            print(f"  ⚠️ 알 수 없는 섹션: {section_name} — 건너뜀")

    blueprint = {
        "rootName": root_name,
        "name": root_name,
        "type": "frame",
        "width": width,
        "height": height,
        "fill": fill,
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "itemSpacing": 0,
            "paddingTop": 0,
            "paddingBottom": 0,
            "paddingLeft": 0,
            "paddingRight": 0
        },
        "children": children,
    }

    # 미치환 placeholder 경고
    bp_str = json.dumps(blueprint, ensure_ascii=False)
    placeholder_count = bp_str.count("{{VARIABLE:")
    if placeholder_count > 0:
        print(f"\n⚠️ 미치환 placeholder {placeholder_count}개 발견 — variables에서 해당 값을 지정하세요")

    # 출력 파일명 생성
    safe_name = root_name.replace(" ", "_").replace("/", "_")[:30]
    out_path = os.path.join(os.path.dirname(__file__), f"blueprint_assembled_{safe_name}.json")
    with open(out_path, "w") as f:
        json.dump(blueprint, f, indent=2, ensure_ascii=False)

    resolved_count = len([s for s in section_order if SECTION_ALIASES.get(s, s) in sections_db])
    print(f"\n✅ Blueprint 조립 완료: {out_path}")
    print(f"  섹션 {len(children)}개, 템플릿 {resolved_count}개 사용")
    print(f"  → python3 scripts/figma_mcp_client.py build {out_path}")
    return out_path


def _apply_template_vars(node: dict, vars_dict: dict, section_name: str) -> dict:
    """템플릿 노드에 변수를 적용.

    지원 변수:
    - FAB: label, icon, fill, textColor
    - Ribbon/TransactionRibbon: text, fill, textColor
    - Hero: banners[{fill, tag, title, subText, desc}]
    - NavBar: title — 있으면 DS Tool Bar Type=Detail view(back+중앙 타이틀)로 전환
      (절대 규칙 0-W). 없으면 Type=Home(로고). 타이틀 적용은 _navTitle 마커 자동.
    - TabBar: activeTab
    """
    if not vars_dict:
        return node

    if section_name == "NavBar":
        title = vars_dict.get("title") or vars_dict.get("_navTitle")
        if title and (node.get("type") or "").lower() == "instance":
            node["componentKey"] = "SET:c9299ef0c3c7cc271850a048025a3c8d0e82b230:Type=Detail view"
            node["_navTitle"] = str(title)

    elif section_name == "FAB":
        label = vars_dict.get("label")
        # R-fix 2026-05-28: iconName/icon, iconColor/textColor alias 둘 다 인정
        icon = vars_dict.get("icon") or vars_dict.get("iconName")
        fill = vars_dict.get("fill")
        text_color = vars_dict.get("textColor") or vars_dict.get("iconColor")
        if fill:
            node["fill"] = fill
        for child in node.get("children", []):
            if child.get("type") == "icon" and icon:
                child["iconName"] = icon
                if text_color:
                    child["iconColor"] = text_color
            elif child.get("type") == "text" and label:
                child["text"] = label
                if text_color:
                    child["fontColor"] = text_color

    elif section_name in ("TransactionRibbon", "Ribbon"):
        text = vars_dict.get("text")
        fill = vars_dict.get("fill")
        text_color = vars_dict.get("textColor")
        if fill:
            node["fill"] = fill
        for child in node.get("children", []):
            if child.get("type") == "text" and text:
                child["text"] = text
                if text_color:
                    child["fontColor"] = text_color

    elif section_name in ("HeroSection", "Hero"):
        banners = vars_dict.get("banners", [])
        carousel = None
        for child in node.get("children", []):
            if "carousel" in (child.get("name") or "").lower():
                carousel = child
                break
        if carousel and banners:
            cards = [c for c in carousel.get("children", []) if "banner card" in (c.get("name") or "").lower()]
            for i, banner_vars in enumerate(banners):
                if i < len(cards):
                    card = cards[i]
                    if banner_vars.get("fill"):
                        card["fill"] = banner_vars["fill"]
                    # 카드 내부 텍스트 치환
                    for text_node in card.get("children", []):
                        children_of = text_node.get("children", [])
                        if children_of:
                            for sub in children_of:
                                if sub.get("type") == "text":
                                    name_lower = sub.get("name", "").lower()
                                    if "tag" in name_lower and banner_vars.get("tag"):
                                        sub["text"] = banner_vars["tag"]
                                    elif "title" in name_lower and banner_vars.get("title"):
                                        sub["text"] = banner_vars["title"]
                                    elif "sub" in name_lower and banner_vars.get("subText"):
                                        sub["text"] = banner_vars["subText"]
                        elif text_node.get("type") == "text":
                            name_lower = text_node.get("name", "").lower()
                            if "title" in name_lower and banner_vars.get("title"):
                                text_node["text"] = banner_vars["title"]
                            elif "sub" in name_lower and banner_vars.get("subText"):
                                text_node["text"] = banner_vars["subText"]
                            elif "desc" in name_lower and banner_vars.get("desc"):
                                text_node["text"] = banner_vars["desc"]

    elif section_name == "TabBar":
        # 2026-05-28 확장: tabLabels + tabIcons 변수 지원 (사용자 옵션 3 박힘)
        # variables.TabBar = {"activeTab":"홈", "tabLabels":["홈","라운지","스테이지","커뮤니티","전체"],
        #                     "tabIcons":["home-line","shopping-bag-01","coins-stacked-01","users-01","menu-04"]}
        active_tab = vars_dict.get("activeTab", "홈")
        tab_labels = vars_dict.get("tabLabels") or []
        tab_icons = vars_dict.get("tabIcons") or []
        tab_children_list = node.get("children", [])
        # 라벨/아이콘 override (position 기준)
        for i, tab_child in enumerate(tab_children_list):
            sub_children = tab_child.get("children", [])
            new_label = tab_labels[i] if i < len(tab_labels) else None
            new_icon = tab_icons[i] if i < len(tab_icons) else None
            for sub in sub_children:
                if sub.get("type") == "icon" and new_icon:
                    sub["iconName"] = new_icon
                elif sub.get("type") == "text" and new_label:
                    sub["text"] = new_label
        # active state 처리 (라벨 swap 후 다시 매칭)
        for tab_child in tab_children_list:
            sub_children = tab_child.get("children", [])
            is_active = False
            for sub in sub_children:
                if sub.get("type") == "text" and sub.get("text") == active_tab:
                    is_active = True
                    break
            for sub in sub_children:
                if is_active:
                    if sub.get("type") == "icon":
                        sub["iconColor"] = "$token(fg-brand-primary)"
                    elif sub.get("type") == "text":
                        sub["fontColor"] = "$token(fg-brand-primary)"
                        sub["fontName"] = {"family": "Pretendard", "style": "SemiBold"}
                else:
                    if sub.get("type") == "icon":
                        sub["iconColor"] = "$token(fg-secondary)"
                    elif sub.get("type") == "text":
                        sub["fontColor"] = "$token(fg-secondary)"
                        sub["fontName"] = {"family": "Pretendard", "style": "Medium"}

    return node


# ─── doctor — 환경/설정 진단 (Astryx CLI 패턴 차용, 2026-07-08) ─────────────────
# 새 세션/새 사용자의 "디자인 생성 준비" 검증 단계들을 한 명령으로 통합 진단한다.
# 계약 (Astryx doctor 와 동일):
#   - 항목별 PASS(✓)/WARN(⚠)/FAIL(✗)/INFO(ℹ, 선행 실패로 판정 불가) + 실행 가능한 fix 안내
#   - exit code: FAIL ≥ 1 → 1 (CI/스크립트 게이트 겸용), 아니면 0 (WARN 은 실패 아님)
#   - --json: 기계 소비용 {"type":"doctor","checks":[...],"summary":{...}} (사람용 출력 없음)
# ⚠ 진단 전용 — 상태를 바꾸지 않는다 (_ensure_bridge_server 자동 기동 호출 금지).

_DOCTOR_GLYPH = {"pass": "✓", "warn": "⚠", "fail": "✗", "info": "ℹ"}


def _doctor_checks() -> List[dict]:
    """진단 체크 실행. 각 항목 {id, label, status, message, fix?}."""
    import io
    import contextlib

    checks: List[dict] = []
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)

    def add(cid: str, label: str, status: str, message: str, fix: str = None):
        c = {"id": cid, "label": label, "status": status, "message": message}
        if fix:
            c["fix"] = fix
        checks.append(c)

    # 1. Python 패키지 (requests 는 이 스크립트 import 시점에 필수 — 여기 도달 = 있음)
    try:
        import PIL  # noqa: F401
        add("python-deps", "Python 패키지 (requests, Pillow)", "pass",
            "requests + Pillow 사용 가능")
    except Exception:
        add("python-deps", "Python 패키지 (requests, Pillow)", "warn",
            "Pillow 미설치 — 레퍼런스 썸네일/이미지 QA 기능 제한",
            "python3 -m pip install Pillow (PEP 668 환경이면 --user 폴백)")

    # 2. 브리지 빌드 산출물 존재 + src/*.ts 대비 최신성
    bridge_js = os.path.join(root, "out", "bridge", "index.js")
    if not os.path.exists(bridge_js):
        add("build", "브리지 빌드 (out/bridge/index.js)", "fail",
            "빌드 산출물 없음", "npm run build")
    else:
        built_at = os.path.getmtime(bridge_js)
        newest_src, newest_path = 0.0, ""
        for dirpath, _dirs, files in os.walk(os.path.join(root, "src")):
            for fn in files:
                if fn.endswith((".ts", ".tsx")):
                    p = os.path.join(dirpath, fn)
                    try:
                        mt = os.path.getmtime(p)
                    except OSError:
                        continue
                    if mt > newest_src:
                        newest_src, newest_path = mt, os.path.relpath(p, root)
        if newest_src > built_at:
            add("build", "브리지 빌드 (out/bridge/index.js)", "warn",
                "src/ 가 빌드보다 최신 (%s) — 브리지가 옛 코드로 동작 중일 수 있음" % newest_path,
                "npm run build 후 브리지 재시작 (플러그인도 재실행)")
        else:
            add("build", "브리지 빌드 (out/bridge/index.js)", "pass", "빌드가 src/ 보다 최신")

    # 3. 브리지 기동 (HTTP MCP 8769) — 자동 기동 없이 순수 진단
    bridge_up = False
    try:
        requests.get(MCP_URL, timeout=2)
        bridge_up = True
        add("bridge", "브리지 프로세스 (WS 8767 + HTTP MCP 8769)", "pass",
            "HTTP MCP 8769 응답 정상")
    except Exception:
        add("bridge", "브리지 프로세스 (WS 8767 + HTTP MCP 8769)", "fail",
            "8769 응답 없음 — 브리지 미기동",
            "npm run bridge (백그라운드 실행, 로그에 'Server listening on port 8767' 확인)")

    # 4. MCP 세션 초기화 (브리지 기동 시에만 판정 가능)
    session_ok = False
    if not bridge_up:
        add("mcp-session", "MCP 세션 초기화", "info", "브리지 미기동 — 판정 불가")
    else:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                sid = init_session()
            if sid:
                session_ok = True
                add("mcp-session", "MCP 세션 초기화", "pass", "세션 ID 발급 정상")
            else:
                add("mcp-session", "MCP 세션 초기화", "fail",
                    "Session initialized: None — @hono/mcp 패치 누락 의심",
                    "npm install 재실행 (postinstall 이 scripts/patch-hono-mcp.js 적용) 후 브리지 재시작")
        except Exception as e:
            add("mcp-session", "MCP 세션 초기화", "fail",
                "세션 초기화 실패: %s" % e, "브리지 로그 확인 (/tmp/bridge-server.log)")

    # 5. Figma 플러그인 연결 (get_ds_loading_status 는 플러그인 불필요 도구 — hang 없음)
    if not session_ok:
        add("plugin", "Figma 플러그인 연결", "info", "MCP 세션 없음 — 판정 불가")
    else:
        try:
            res = call_tool("get_ds_loading_status", {})
            j = _extract_tool_json(res)
            fc = j.get("figmaConnected")
            if fc is True:
                add("plugin", "Figma 플러그인 연결", "pass",
                    "플러그인 연결됨 (DS 로딩: %s)" % j.get("status"))
            elif fc is False:
                add("plugin", "Figma 플러그인 연결", "fail",
                    "플러그인 미연결",
                    "Figma 데스크톱 앱에서 'Figma Design Agent' 플러그인 실행 (유일한 수동 단계)")
            else:
                add("plugin", "Figma 플러그인 연결", "warn",
                    "구버전 브리지 — figmaConnected 필드 미지원",
                    "npm run build 후 브리지 재시작하면 정확 판정")
        except Exception as e:
            add("plugin", "Figma 플러그인 연결", "warn", "상태 조회 실패: %s" % e)

    # 6. DS 맵 4종 (토큰/텍스트스타일/이펙트/변수키 — 바인딩 파이프라인의 전제)
    token_map_path = os.path.join(root, "ds", "TOKEN_MAP.json")
    try:
        with open(token_map_path, encoding="utf-8") as fh:
            tm = json.load(fh)
        if tm:
            add("ds-token-map", "DS 토큰 맵 (ds/TOKEN_MAP.json)", "pass",
                "%d개 항목" % len(tm))
        else:
            raise ValueError("빈 맵")
    except Exception:
        add("ds-token-map", "DS 토큰 맵 (ds/TOKEN_MAP.json)", "fail",
            "없거나 손상 — 색/spacing 토큰 바인딩 불가",
            "브리지 기동 시 자동 sync (수동: bash scripts/sync-tokens-from-github.sh)")

    ts_path = os.path.join(root, "ds", "TEXT_STYLE_MAP.json")
    try:
        with open(ts_path, encoding="utf-8") as fh:
            ts = json.load(fh)
        body_sm = [e for e in ts if isinstance(e, dict)
                   and e.get("fontSize") == 14 and e.get("family") == "Pretendard"]
        if body_sm:
            add("ds-text-styles", "DS 텍스트 스타일 맵 (ds/TEXT_STYLE_MAP.json)", "pass",
                "%d개 스타일, Body sm(14px) 포함" % len(ts))
        else:
            add("ds-text-styles", "DS 텍스트 스타일 맵 (ds/TEXT_STYLE_MAP.json)", "warn",
                "Body sm(14px Pretendard) 키 없음 — stale 맵 (보조 텍스트 스타일 바인딩 실패)",
                "플러그인을 DS 파일(Imin Design System)에 연결 후 sync-text-styles 1회 실행")
    except Exception:
        add("ds-text-styles", "DS 텍스트 스타일 맵 (ds/TEXT_STYLE_MAP.json)", "warn",
            "없거나 손상 — 라이브러리 텍스트 스타일 fallback 불가",
            "플러그인을 DS 파일에 연결 후 sync-text-styles 1회 실행")

    for cid, fname, syncc, why in (
        ("ds-effect-styles", "EFFECT_STYLE_MAP.json", "sync-effect-styles",
         "카드 shadow-basic 바인딩(2-B-3) 불가"),
        ("ds-variable-keys", "VARIABLE_KEY_MAP.json", "sync-variable-keys",
         "Draft 파일에서 변수 바인딩(K:key 폴백) 불가"),
    ):
        p = os.path.join(root, "ds", fname)
        if os.path.exists(p):
            add(cid, "DS 맵 (ds/%s)" % fname, "pass", "존재")
        else:
            add(cid, "DS 맵 (ds/%s)" % fname, "warn", "없음 — %s" % why,
                "플러그인을 DS 파일에 연결 후 %s 1회 실행" % syncc)

    # 7. 기획 통독 게이트 (stale/미통독이면 cmd_build 가 차단됨 — 사전 안내)
    try:
        ok, reason = _planning_read_ok()
        if ok:
            add("planning", "기획 문서 통독 게이트", "pass", reason)
        else:
            add("planning", "기획 문서 통독 게이트", "fail",
                "%s (이 상태로는 빌드가 차단됨)" % reason,
                "learn-planning → digest 를 Read 로 끝까지 통독 → ack-planning <맨 끝 토큰>")
    except Exception as e:
        add("planning", "기획 문서 통독 게이트", "warn", "판정 실패: %s" % e)

    return checks


def cmd_doctor(json_out: bool = False) -> None:
    checks = _doctor_checks()
    summary = {s: sum(1 for c in checks if c["status"] == s)
               for s in ("pass", "warn", "fail", "info")}

    if json_out:
        print(json.dumps({"type": "doctor", "checks": checks, "summary": summary},
                         ensure_ascii=False, indent=2))
    else:
        print("figma-design-agent doctor — 환경 진단\n")
        for c in checks:
            print("  %s %s" % (_DOCTOR_GLYPH.get(c["status"], "·"), c["label"]))
            print("      %s" % c["message"])
            if c.get("fix"):
                print("      → fix: %s" % c["fix"])
        print()
        print("Summary: %d passed, %d warning(s), %d failure(s)%s" % (
            summary["pass"], summary["warn"], summary["fail"],
            (", %d skipped" % summary["info"]) if summary["info"] else ""))
        if summary["fail"]:
            print("\n✗ 실패 항목을 위 fix 안내대로 해결한 뒤 doctor 를 다시 실행하세요.")
        elif summary["warn"]:
            print("\n⚠ 실패는 없지만 경고 항목을 확인해 두세요.")
        else:
            print("\n모든 체크 통과 — 디자인 생성 준비 완료 상태입니다.")

    # exit code 계약: FAIL ≥ 1 → 1 (WARN 은 실패 아님) — CI/준비 스크립트 게이트 겸용
    if summary["fail"]:
        sys.exit(1)


# ─── component / search / manifest — DS 조회 + 자기서술 (Astryx 패턴, 2026-07-08) ────

def cmd_component(name: str = None, json_out: bool = False, full: bool = False,
                  list_all: bool = False) -> None:
    """DS 컴포넌트 가이드 조회 — ds/COMPONENT_GUIDANCE.json(do/don't) +
    ds_catalog.COMPONENT_KEYS(키) + DS_COMPONENT_DOCS(--full variants/props) 통합."""
    import ds_guidance as dg
    entries = dg.load_guidance()
    if list_all or not name:
        if json_out:
            print(json.dumps({"type": "component-list",
                              "components": [{"name": e["name"], "rule": e.get("rule"),
                                              "aliases": e.get("aliases") or []}
                                             for e in entries]}, ensure_ascii=False, indent=2))
        else:
            print("DS 컴포넌트 가이드 (%d개) — component <이름> 으로 상세 조회:" % len(entries))
            for e in entries:
                al = ", ".join(e.get("aliases") or [])
                print("  - %s%s%s" % (e["name"],
                                      " (규칙 %s)" % e.get("rule") if e.get("rule") else "",
                                      "  [%s]" % al if al else ""))
        return
    entry, candidates = dg.find(name, entries)
    if not entry:
        if json_out:
            print(json.dumps({"type": "component", "error": "not found",
                              "code": "ERR_UNKNOWN", "query": name,
                              "candidates": candidates}, ensure_ascii=False, indent=2))
        else:
            print("'%s' 컴포넌트를 찾지 못했습니다." % name)
            if candidates:
                print("후보: %s" % ", ".join(candidates))
            print("전체 목록: python3 scripts/figma_mcp_client.py component --list")
        sys.exit(1)
    if json_out:
        print(json.dumps(dg.entry_as_json(entry, full=full), ensure_ascii=False, indent=2))
    else:
        print(dg.format_entry(entry, full=full))


def cmd_search(query: str, json_out: bool = False) -> None:
    """가이드(키워드/별칭/본문) + ds_catalog 이름 통합 랭킹 검색."""
    import ds_guidance as dg
    results = dg.search(query)
    if json_out:
        print(json.dumps({"type": "search", "query": query, "results": results},
                         ensure_ascii=False, indent=2))
        return
    if not results:
        print("'%s' 검색 결과 없음 — component --list 로 가이드 목록 확인." % query)
        return
    print("'%s' 검색 결과 %d건:" % (query, len(results)))
    for r in results:
        if r["kind"] == "guidance":
            print("  [가이드] %s%s — %s" % (r["name"],
                                            " (규칙 %s)" % r.get("rule") if r.get("rule") else "",
                                            r["snippet"]))
        else:
            print("  [카탈로그] %s = %s" % (r["name"], r["snippet"]))
    print("상세: python3 scripts/figma_mcp_client.py component \"<이름>\"")


# ── rule 명령 (Phase 5 인덱스화 retrieval, 2026-07-09) ─────────────────────────
# CLAUDE.md 는 압축 인덱스만 담고, 룰 상세 원문은 docs/design-rules-detail.md 로 이관됐다.
# 이 명령이 그 문서를 룰 id 로 조회하는 retrieval 표면이다 (Astryx: "상세는 retrieval 로").

RULE_DETAIL_DOC = os.path.join(os.path.dirname(__file__), "..", "docs", "design-rules-detail.md")

# 앵커 = 룰 섹션 시작 라인. 3가지 표기 + 특수 섹션.
_RULE_RE_ABS = re.compile(r"\*\*(?:절대 )?규칙 ([0-9][0-9A-Za-z\-]*) —")  # > 🔴 **절대 규칙 0-J — … / **규칙 0-Y — … (2026-09-07: '규칙 0-Y'/'0-Y-2' 헤더가 조회 안 되던 회귀)
_RULE_RE_BQ = re.compile(r"^>\s*\S{0,4}\s*\*\*([0-9][0-9A-Za-z\-]*)\.")  # > 🔴 **2-G-2. …
_RULE_RE_HDR = re.compile(r"^###\s+([0-9A-Z][0-9A-Za-z\-]*)\.")          # ### 2-B. / ### S27. …
_RULE_SPECIAL_ALIASES = {
    "post-fix": "post-fix", "postfix": "post-fix",
    "troubleshooting": "troubleshooting", "트러블슈팅": "troubleshooting",
    # 창의 프로세스/게이트는 규칙 섹션 서두(룰 2계층 + S24~S26 + novelty)에 있다
    "creative": "creative", "창의": "creative", "two-tier": "creative",
    "s22": "creative", "s23": "creative", "s24": "creative", "s25": "creative",
    "s26": "creative", "novelty": "creative",
    # 부모 섹션에 내장된 하위 룰 (자체 앵커 없음)
    "13-b": "13",
}


def _parse_rule_sections():
    """detail 문서를 (id → (title, [lines])) 로 파싱. 섹션 = 앵커 라인 ~ 다음 앵커 직전."""
    if not os.path.exists(RULE_DETAIL_DOC):
        print("docs/design-rules-detail.md 가 없습니다 — 레포 상태 확인.")
        sys.exit(1)
    lines = open(RULE_DETAIL_DOC, encoding="utf-8").read().splitlines()
    anchors = []  # (line_idx, id, title)
    for i, ln in enumerate(lines):
        m = _RULE_RE_ABS.search(ln) or _RULE_RE_BQ.match(ln) or _RULE_RE_HDR.match(ln)
        if m:
            anchors.append((i, m.group(1).upper(), ln.strip().lstrip("> #").strip()))
            continue
        if ln.startswith("## 빌드 후 자동 후처리"):
            anchors.append((i, "POST-FIX", ln.strip("# ").strip()))
        elif ln.startswith("## 트러블슈팅"):
            anchors.append((i, "TROUBLESHOOTING", ln.strip("# ").strip()))
        elif ln.startswith("## 디자인 생성 필수 규칙"):
            anchors.append((i, "CREATIVE", "창의 프로세스 — 룰 2계층 + S22~S26/novelty 게이트"))
    sections = {}
    order = []
    for n, (start, rid, title) in enumerate(anchors):
        end = anchors[n + 1][0] if n + 1 < len(anchors) else len(lines)
        if rid not in sections:  # 같은 id 첫 앵커 우선
            sections[rid] = (title, lines[start:end])
            order.append(rid)
    return sections, order


def cmd_rule(rule_id: str = None, list_all: bool = False) -> None:
    """디자인 룰 상세 원문 조회 — CLAUDE.md 압축 인덱스의 retrieval 짝."""
    sections, order = _parse_rule_sections()
    if list_all or not rule_id:
        print("디자인 룰 %d개 — rule <id> 로 상세 원문 조회 (예: rule 0-J):" % len(order))
        for rid in order:
            print("  %-16s %s" % (rid, sections[rid][0][:88]))
        return
    key = rule_id.strip().upper()
    key = _RULE_SPECIAL_ALIASES.get(key.lower(), key)
    if key.upper() not in sections:
        cands = [r for r in order if key.upper() in r]
        print("룰 '%s' 을 찾지 못했습니다." % rule_id)
        if cands:
            print("후보: %s" % ", ".join(cands))
        print("전체 목록: python3 scripts/figma_mcp_client.py rule --list")
        sys.exit(1)
    title, body = sections[key.upper()]
    print("\n".join(body).rstrip())


# CLI 자기서술 매니페스트 (Astryx manifest 패턴) — 에이전트가 --help 스크래핑/CLAUDE.md 없이
# 명령 표면을 발견한다. ⚠️ main() 의 dispatch 분기와 이 테이블은 드리프트 가드 테스트
# (test_manifest.py)가 동기화를 강제한다 — 명령 추가 시 반드시 여기에도 등록할 것.
def _run_blueprint_lint(bp: dict):
    """cmd_build 의 design_rules LINT 와 동일한 검증을 빌드 밖에서 실행.

    2026-07-13 — validate 가 구조만 보고 룰 lint 를 안 봐서, R22.2 같은 ERROR 가
    빌드에 가서야 차단돼 왕복이 늘던 문제 해소 (validate/prebuild 공용).
    returns (violations, errors, warns). import 실패 시 ([], [], []).
    """
    try:
        import sys as _sys
        _scripts_dir = os.path.dirname(os.path.abspath(__file__))
        if _scripts_dir not in _sys.path:
            _sys.path.insert(0, _scripts_dir)
        from design_rules import REGISTRY as _REG, Severity as _Sev  # noqa: E402
        violations = _REG.run_lint(bp)
        errors = [v for v in violations if v.severity == _Sev.ERROR]
        warns = [v for v in violations if v.severity == _Sev.WARN]
        return violations, errors, warns
    except Exception as e:
        print(f"  [lint] design_rules 로드 실패 — lint 생략: {e}")
        return [], [], []


def cmd_validate_blueprint(path: str, with_refs: bool = False) -> None:
    """validate: 구조 검증 + design_rules lint (빌드와 동일 기준, 빌드 없이 수 초).

    with_refs=True (prebuild): Step A.0 레퍼런스 검색까지 미리 실행 — 빌드 전에
    썸네일을 Read 해두면 0-G 게이트에 안 걸려 빌드 왕복 1회로 끝난다 (2026-07-13,
    23분 회귀의 게이트 차단 2회 왕복 제거).
    """
    with open(path) as f:
        bp = json.load(f)
    bp = _flatten_padding_objects(bp)

    issues = validate_blueprint(bp)
    struct_errors = [i for i in issues if i.startswith("ERROR")]
    struct_warns = [i for i in issues if i.startswith("WARN")]
    if issues:
        print(f"{'✗' if struct_errors else '⚠'} 구조 검증: {len(struct_errors)} error(s), {len(struct_warns)} warning(s):")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("✓ 구조 검증 통과")

    # 창의 게이트(S24~S26)도 빌드 전에 미리 — 특히 S26 구조 발산 검사 (2026-07-14 강화)
    gate_issues = []
    for fn in (_check_wireframe_divergence_required, _check_restructure_map_required):
        try:
            gate_issues += fn(bp)
        except Exception as e:
            print(f"  [prebuild-gates] {getattr(fn, '__name__', '?')} 실패 (무시): {e}")
    for gi in gate_issues:
        print(f"  {gi}")
    gate_errors = [g for g in gate_issues if str(g).startswith("ERROR")]

    print("\n[design_rules:LINT] 룰 검증 중 (빌드와 동일 기준)...")
    violations, lint_errors, lint_warns = _run_blueprint_lint(bp)
    if violations:
        print(f"  [LINT] {len(lint_errors)} ERROR / {len(lint_warns)} WARN")
        # ERROR 를 항상 먼저 (30건 절단에 ERROR 가 묻히던 표시 버그 fix)
        ordered = lint_errors + [v for v in violations if v not in lint_errors]
        for v in ordered[:30]:
            print(f"    {v.format()}")
        if len(ordered) > 30:
            print(f"    ... +{len(ordered) - 30}개")
    else:
        print("  [LINT] ✓ 모든 룰 통과")

    if with_refs:
        # Step A.0 과 동일 검색 — 빌드가 요구할 썸네일 목록을 미리 노출
        _auto_search_uibowl_references(bp)
        if _LAST_REFERENCE_THUMBS:
            print("👉 위 썸네일들을 지금 Read 로 학습해 두면 build 의 0-G 게이트를 한 번에 통과한다.")

    if struct_errors or lint_errors or gate_errors:
        print(f"\n✗ ERROR {len(struct_errors) + len(lint_errors) + len(gate_errors)}건 — blueprint 수정 후 다시 실행 (이대로 build 하면 차단됨)")
        sys.exit(1)
    print("\n✓ build 가능 상태" + (" — 레퍼런스 Read 후 build 실행" if with_refs else ""))


CLI_COMMANDS = [
    {"name": "init", "usage": "init", "description": "MCP 세션 초기화 (브리지 자동 기동)"},
    {"name": "doctor", "usage": "doctor [--json]", "json": True,
     "description": "환경/준비 상태 통합 진단 — 브리지/세션/플러그인/DS맵/통독 게이트. FAIL≥1 → exit 1"},
    {"name": "component", "usage": "component <이름>|--list [--full] [--json]", "json": True,
     "description": "DS 컴포넌트 do/don't 가이드 + componentKey 조회 (dense 기본, --full 로 예시/props)"},
    {"name": "search", "usage": "search <쿼리> [--json]", "json": True,
     "description": "컴포넌트 가이드 + ds_catalog 통합 랭킹 검색"},
    {"name": "rule", "usage": "rule <id>|--list",
     "description": "디자인 룰 상세 원문 조회 (CLAUDE.md 압축 인덱스의 retrieval — docs/design-rules-detail.md)"},
    {"name": "manifest", "usage": "manifest [--json]", "json": True,
     "description": "이 CLI 의 명령 표면 자기서술 (OpenAPI 처럼 — 에이전트 self-discovery)"},
    {"name": "learn-planning", "usage": "learn-planning [--force]",
     "description": "src/기획 → 통독용 digest 생성 (변경 감지, ack 무효화)"},
    {"name": "ack-planning", "usage": "ack-planning <토큰>",
     "description": "digest 통독 확인 (토큰은 digest 맨 끝 — 없으면 빌드 차단)"},
    {"name": "call", "usage": "call <tool> [args_json] [--compact]",
     "description": "브리지 MCP 도구 단건 호출"},
    {"name": "export", "usage": "export <nodeId> [out] [--scale N] [--jpg]",
     "description": "노드를 이미지로 export"},
    {"name": "build", "usage": "build <blueprint.json> [--force]",
     "description": "디자인 빌드 파이프라인 — 검증·게이트·조립·post-fix·QA. 결과는 마지막 BUILD-SUMMARY-JSON 블록으로 판독"},
    {"name": "bind", "usage": "bind <bindings.json>", "description": "DS 변수 수동 바인딩"},
    {"name": "auto-bind", "usage": "auto-bind <rootId> <blueprint.json>",
     "description": "blueprint $token 참조 기반 색 변수 자동 바인딩"},
    {"name": "bind-text-styles", "usage": "bind-text-styles <styles.json>",
     "description": "텍스트 스타일 수동 바인딩"},
    {"name": "bind-effect-styles", "usage": "bind-effect-styles <rootId>",
     "description": "DS effect style (Shadows/*) 재바인딩"},
    {"name": "sync-variable-keys", "usage": "sync-variable-keys",
     "description": "ds/VARIABLE_KEY_MAP.json 추출 (DS 파일 연결 상태에서 1회)"},
    {"name": "set-badge-color", "usage": "set-badge-color <nodeId> <Color>",
     "description": "Badge 색 변경 — Color prop 만 (0-K)"},
    {"name": "sync-components", "usage": "sync-components",
     "description": "ds/COMPONENT_KEY_MAP.json 추출 (DS 파일 연결 상태에서 1회)"},
    {"name": "sync-text-styles", "usage": "sync-text-styles",
     "description": "ds/TEXT_STYLE_MAP.json 추출 (DS 파일 연결 상태에서 1회)"},
    {"name": "sync-effect-styles", "usage": "sync-effect-styles",
     "description": "ds/EFFECT_STYLE_MAP.json 추출 (DS 파일 연결 상태에서 1회)"},
    {"name": "apply-text-styles", "usage": "apply-text-styles <rootId>",
     "description": "빌드된 화면에 DS 텍스트 스타일 적용 (재빌드 없이)"},
    {"name": "apply-images", "usage": "apply-images <rootId> [blueprint.json]",
     "description": "imageQuery 기반 이미지 fill 적용"},
    {"name": "post-fix", "usage": "post-fix <rootId>",
     "description": "빌드 후처리 — FILL/위치/바인딩/enforcer 체인 재실행"},
    {"name": "validate", "usage": "validate <blueprint.json>",
     "description": "blueprint 구조 검증 + design_rules lint (빌드와 동일 기준, 빌드 없이). ERROR≥1 → exit 1"},
    {"name": "prebuild", "usage": "prebuild <blueprint.json>",
     "description": "validate(+lint) + Step A.0 레퍼런스 사전 검색 — 썸네일을 미리 Read 하면 build 0-G 게이트 1회 통과"},
    {"name": "assemble", "usage": "assemble <config.json>",
     "description": "템플릿 기반 blueprint 조립 (blueprint_templates.json)"},
    {"name": "cleanup-qa", "usage": "cleanup-qa",
     "description": "QA 스크린샷 + 레퍼런스 썸네일 삭제 (작업 종료 시 1회 — 0-F-2)"},
    {"name": "interactive", "usage": "interactive", "description": "인터랙티브 REPL 모드"},
]


def cmd_manifest(json_out: bool = False) -> None:
    if json_out:
        print(json.dumps({
            "type": "manifest",
            "name": "figma_mcp_client",
            "commands": CLI_COMMANDS,
            "responseTypes": {
                "doctor": ["doctor"],
                "build": ["build-summary"],
                "component": ["component", "component-list"],
                "search": ["search"],
                "manifest": ["manifest"],
            },
            "errorCodesModule": "scripts/error_codes.py",
        }, ensure_ascii=False, indent=2))
        return
    print("figma_mcp_client — 명령 %d개 (기계 판독: manifest --json):" % len(CLI_COMMANDS))
    for c in CLI_COMMANDS:
        print("  %-52s %s" % (c["usage"], c["description"]))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "init":
        cmd_init()
    elif cmd == "doctor":
        # 환경/설정 진단 — PASS/WARN/FAIL + fix 안내. FAIL ≥1 이면 exit 1.
        cmd_doctor(json_out="--json" in sys.argv)
    elif cmd == "component":
        _name = next((a for a in sys.argv[2:] if not a.startswith("--")), None)
        cmd_component(_name, json_out="--json" in sys.argv, full="--full" in sys.argv,
                      list_all="--list" in sys.argv)
    elif cmd == "search":
        _q = next((a for a in sys.argv[2:] if not a.startswith("--")), None)
        if not _q:
            print("Usage: figma_mcp_client.py search <쿼리> [--json]")
            sys.exit(1)
        cmd_search(_q, json_out="--json" in sys.argv)
    elif cmd == "rule":
        _rid = next((a for a in sys.argv[2:] if not a.startswith("--")), None)
        cmd_rule(_rid, list_all="--list" in sys.argv)
    elif cmd == "manifest":
        cmd_manifest(json_out="--json" in sys.argv)
    elif cmd == "learn-planning":
        _force = "--force" in sys.argv
        _out = next((a for a in sys.argv[2:] if a != "--force"), "scripts/_planning_digest.txt")
        cmd_learn_planning(_out, force=_force)
    elif cmd == "ack-planning":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py ack-planning <통독토큰>  (digest 맨 끝의 토큰)")
            sys.exit(1)
        cmd_ack_planning(sys.argv[2])
    elif cmd == "call":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py call <tool_name> [args_json] [--compact]")
            sys.exit(1)
        _compact = "--compact" in sys.argv
        _args = "{}"
        for a in sys.argv[3:]:
            if a != "--compact":
                _args = a
                break
        cmd_call(sys.argv[2], _args, compact=_compact)
    elif cmd == "export":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py export <nodeId> [out_path] [--scale N] [--jpg]")
            sys.exit(1)
        _node = sys.argv[2]
        _scale = 2
        _fmt = "PNG"
        _out = None
        _rest = sys.argv[3:]
        i = 0
        while i < len(_rest):
            a = _rest[i]
            if a == "--scale" and i + 1 < len(_rest):
                _scale = float(_rest[i + 1]); i += 2; continue
            if a == "--jpg":
                _fmt = "JPG"; i += 1; continue
            if not a.startswith("--"):
                _out = a
            i += 1
        cmd_export(_node, _out, scale=_scale, fmt=_fmt)
    elif cmd == "build":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py build <blueprint.json>")
            sys.exit(1)
        cmd_build(sys.argv[2])
    elif cmd == "bind":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py bind <bindings.json>")
            sys.exit(1)
        cmd_bind(sys.argv[2])
    elif cmd == "auto-bind":
        if len(sys.argv) < 4:
            print("Usage: figma_mcp_client.py auto-bind <rootNodeId> <blueprint.json>")
            sys.exit(1)
        cmd_auto_bind(sys.argv[2], sys.argv[3])
    elif cmd == "bind-text-styles":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py bind-text-styles <styles.json>")
            sys.exit(1)
        cmd_bind_text_styles(sys.argv[2])
    elif cmd == "bind-effect-styles":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py bind-effect-styles <rootNodeId>")
            sys.exit(1)
        ensure_session()
        _apply_ds_effect_styles(sys.argv[2])
    elif cmd == "sync-variable-keys":
        # DS 파일 또는 라이브러리 enabled 작업 파일에 plugin 연결된 상태에서 1회 실행 →
        # ds/VARIABLE_KEY_MAP.json 생성. Draft 에서도 변수 바인딩(K:key)이 동작하게 한다.
        ensure_session()
        cmd_sync_variable_keys()
    elif cmd == "set-badge-color":
        # Badge 색 변경 = Color prop (fill/stroke 직접 변경 금지 — 절대 규칙 0-K).
        if len(sys.argv) < 4:
            print("Usage: figma_mcp_client.py set-badge-color <nodeId> <Color>")
            print(f"  Color 옵션: {', '.join(BADGE_COLOR_PROP_OPTIONS)}")
            sys.exit(1)
        ensure_session()
        set_badge_color(sys.argv[2], sys.argv[3])
    elif cmd == "sync-components":
        # Imin Design System 파일에 plugin 연결된 상태에서 1회 실행 →
        # ds/COMPONENT_KEY_MAP.json 생성 (DS v7 → Imin DS 전수 마이그레이션 기준).
        ensure_session()
        cmd_sync_components()
    elif cmd == "sync-text-styles":
        # DS 파일(Imin Design System)에 plugin 연결된 상태에서 1회 실행 →
        # ds/TEXT_STYLE_MAP.json 생성. 작업 파일엔 로컬 text style 이 없으므로
        # 이 추출본이 _load_text_style_map 의 fallback 으로 쓰인다.
        ensure_session()
        cmd_sync_text_styles()
    elif cmd == "sync-effect-styles":
        # DS 파일(Imin Design System)에 plugin 연결된 상태에서 1회 실행 →
        # ds/EFFECT_STYLE_MAP.json 생성(Shadows/shadow-basic 등 키). 작업 파일엔
        # effect style 이 라이브러리 참조만 있어 0건이므로 DS 파일에서 추출해야 함.
        ensure_session()
        cmd_sync_effect_styles()
    elif cmd == "sync-paint-styles":
        # DS 파일 연결 상태에서 1회 실행 → ds/PAINT_STYLE_MAP.json (gradient color style 키)
        ensure_session()
        cmd_sync_paint_styles()
    elif cmd == "apply-text-styles":
        # 빌드된 화면에 DS text style 만 별도 적용 (재빌드 없이).
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py apply-text-styles <rootNodeId>")
            sys.exit(1)
        ensure_session()
        _apply_ds_text_styles(sys.argv[2])
    elif cmd == "apply-images":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py apply-images <rootNodeId> [blueprint.json]")
            sys.exit(1)
        ensure_session()
        _bp = None
        if len(sys.argv) >= 4 and os.path.exists(sys.argv[3]):
            with open(sys.argv[3]) as _f:
                _bp = json.load(_f)
        else:
            _latest = _load_latest_build()
            _bp_path = _latest.get("blueprintPath")
            if _bp_path and os.path.exists(_bp_path):
                with open(_bp_path) as _f:
                    _bp = json.load(_f)
        if not _bp:
            print("⚠️  blueprint 없음 — apply-images 는 imageQuery 매핑에 blueprint 필요")
            sys.exit(1)
        # thin unified spec 면 expanded blueprint 로 해석 (imageQuery 는 expanded 에만 있음)
        _bp = _maybe_resolve_unified_input(_bp)
        apply_image_queries(sys.argv[2], _bp)
    elif cmd == "post-fix":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py post-fix <rootNodeId>")
            sys.exit(1)
        cmd_post_fix(sys.argv[2])
    elif cmd == "validate":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py validate <blueprint.json>")
            sys.exit(1)
        cmd_validate_blueprint(sys.argv[2], with_refs=False)
    elif cmd == "prebuild":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py prebuild <blueprint.json>")
            sys.exit(1)
        cmd_validate_blueprint(sys.argv[2], with_refs=True)
    elif cmd == "assemble":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py assemble <config.json>")
            sys.exit(1)
        cmd_assemble(sys.argv[2])
    elif cmd == "cleanup-qa":
        cmd_cleanup_qa()
    elif cmd == "interactive":
        cmd_interactive()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
