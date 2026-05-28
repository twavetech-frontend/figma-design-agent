#!/usr/bin/env python3
"""
Figma MCP HTTP Client — 디자인 생성, 수정, 바인딩을 위한 Python 클라이언트

Usage:
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

# Cached token map (loaded once per process)
_token_map: Optional[Dict[str, dict]] = None


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

    # Exact match (map key)
    info = token_map.get(token_name)
    if info and info.get("type") == "COLOR":
        return hex_to_rgba(info["value"])

    # Pass 1: figmaPath 마지막 세그먼트 '정확 일치' 우선 (_alt 오매칭 방지)
    for path, info_item in token_map.items():
        if info_item.get("type") != "COLOR":
            continue
        figma_path = info_item.get("figmaPath", path)
        last_segment = figma_path.rsplit("/", 1)[-1] if "/" in figma_path else figma_path
        if last_segment == token_name:
            return hex_to_rgba(info_item["value"])

    # Pass 2: 괄호 변형 매칭만 허용 ("fg-brand-primary" → "fg-brand-primary (600)")
    # ※ '_' prefix 매칭 절대 금지 — bg-secondary 가 bg-secondary_alt 로 오매칭됨
    for path, info_item in token_map.items():
        if info_item.get("type") != "COLOR":
            continue
        figma_path = info_item.get("figmaPath", path)
        last_segment = figma_path.rsplit("/", 1)[-1] if "/" in figma_path else figma_path
        if last_segment.startswith(token_name + " "):
            return hex_to_rgba(info_item["value"])

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


def call_tool(name: str, args: dict, msg_id: int = 1) -> List[dict]:
    """Call an MCP tool and return content array."""
    # 방어: set_image_fill에 url 파라미터 사용 차단
    if name == "set_image_fill" and "url" in args:
        raise ValueError(
            "set_image_fill does NOT support 'url'. "
            "Use 'imageData' (base64-encoded PNG/JPEG). "
            "Read the file with open(path,'rb') and base64.b64encode()."
        )
    result = mcp_request("tools/call", {
        "name": name,
        "arguments": args
    }, msg_id)

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

    if not archetype:
        return

    import subprocess
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ref_script = os.path.join(project_root, "scripts", "ref_search.py")
    if not os.path.exists(ref_script):
        return

    try:
        result = subprocess.run(
            ["python3", ref_script, "--archetype", archetype,
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
            print(f"  [Step A.0] archetype '{archetype}' 매칭 reference 없음")
            return

        print(f"\n📚 [Step A.0] references/uibowl 자동 검색 — archetype '{archetype}'")
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


def _enforce_root_bg_primary_live(root_node_id: str) -> None:
    """빌드된 루트 노드의 배경을 bg-primary로 강제 (런타임 보장 — post-fix용)."""
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

    dim = {
        "name": "Dim Overlay",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "FILL",
        "fills": [_BOTTOM_SHEET_DIM_FILL],
    }
    modal = {
        "name": "Modal Sheet",
        "type": "frame",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "fill": "$token(bg-primary)",
        "topLeftRadius": 24,
        "topRightRadius": 24,
        "bottomLeftRadius": 0,
        "bottomRightRadius": 0,
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "itemSpacing": 0,
            "paddingTop": 0, "paddingBottom": 0,
            "paddingLeft": 0, "paddingRight": 0,
        },
        "children": modal_kids,
    }

    new_children = []
    if status_bar_child is not None:
        new_children.append(status_bar_child)
    new_children.extend([dim, modal])
    blueprint["children"] = new_children

    # Root 는 852 FIXED 로 (bottom sheet 위치 고정 위해)
    blueprint["height"] = 852
    blueprint["layoutSizingVertical"] = "FIXED"

    print(f"[규칙] Bottom Sheet 패턴 강제 — Dim Overlay + Modal Sheet wrap "
          f"({len(modal_kids)}개 자식을 Modal Sheet 안으로)")


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
    counts = {"brand": 0, "feedback": 0}

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
            elif "brand" in low:
                counts["brand"] += 1
        for child in node.get("children", []) or []:
            walk(child)

    walk(blueprint)
    print(f"[색상] 브랜드 액센트 {counts['brand']}곳 · 상태 컬러 {counts['feedback']}곳")
    if counts["brand"] == 0:
        print("  ⚠️  브랜드 액센트 0곳 — 완전 무채색은 와이어프레임처럼 보임. "
              "주 액션·active 등에 브랜드 컬러를 단일 액센트로 줄 것.")
    if counts["feedback"] > 8:
        print(f"  ⚠️  상태 컬러 {counts['feedback']}곳 — 진짜 상태 정보(미납·완료 등)에만 "
              "절제 사용할 것. 장식·태그·통계 전반에 색을 까는 건 금지.")


# 그레이로 채운 카드 fill — 카드 표면 규칙(2026-05-23)에서 bg-primary+보더로 교정 대상
_GREY_CARD_FILLS = ("bg-secondary", "bg-tertiary")
# 보더 관련 키 — Footer 예외 처리에서 일괄 제거
_STROKE_KEYS = ("stroke", "strokes", "strokeWeight", "strokeTopWeight",
                "strokeBottomWeight", "strokeLeftWeight", "strokeRightWeight")


def _is_footer(node: dict) -> bool:
    """맨 아래 Footer 섹션인가 — 이름에 'footer' 포함."""
    return "footer" in (node.get("name") or "").lower()


def _is_card_like(node: dict) -> bool:
    """카드형 프레임 판별 — cornerRadius ≥ 8 + fill + children."""
    if not isinstance(node, dict):
        return False
    if node.get("type") not in (None, "frame", "FRAME"):
        return False
    radius = node.get("cornerRadius") or node.get("topLeftRadius") or 0
    try:
        radius = float(radius)
    except (TypeError, ValueError):
        radius = 0
    return radius >= 8 and node.get("fill") is not None and bool(node.get("children"))


def _enforce_card_surface(blueprint: dict) -> None:
    """루트 위 최상위 카드 표면 = bg-primary fill + border-secondary 보더 (2026-05-23 룰).

    그레이(bg-secondary/tertiary)로 채운 카드 대신 흰 카드 + 보더로 표면을 정의한다.
    중첩 카드(카드 안의 인셋)·브랜드 컬러 카드는 건드리지 않는다.
    예외 — 맨 아래 Footer: bg-secondary fill + 보더 없음(카드 아닌 회색 띠).
    """
    flipped = [0]
    footer_fixed = [0]

    # 2026-05-28 polish-aware: hero/alert/participation/sub-card/attendance 이름 패턴은
    # bg-secondary 카드 그대로 보존 ([feedback_imin_home_polish_baseline] 의 17389:51811
    # 패턴 — 옅은 lavender 참여중 카드 / sub-card 포인트 카드 / alert banner 등)
    POLISH_KEEP_GREY_RE = ("hero", "alert", "banner", "participation",
                            "sub-card", "sub_card", "attendance", "dot-row", "dot_row",
                            "points", "reward")

    def walk(node, inside_card, in_footer):
        if not isinstance(node, dict):
            return
        is_footer = (not in_footer) and _is_footer(node)
        if is_footer:
            # Footer 예외 — bg-secondary 채움, 보더 제거
            node["fill"] = "$token(bg-secondary)"
            for k in _STROKE_KEYS:
                node.pop(k, None)
            footer_fixed[0] += 1
        nm_low = (node.get("name") or "").lower()
        polish_keep = any(kw in nm_low for kw in POLISH_KEEP_GREY_RE)
        is_card = (not in_footer and not is_footer) and _is_card_like(node)
        if is_card and not inside_card and not polish_keep:
            fill_name = _token_name_of(node.get("fill"))
            if fill_name and fill_name.lower() in _GREY_CARD_FILLS:
                node["fill"] = "$token(bg-primary)"
                if not node.get("stroke"):
                    node["stroke"] = "$token(border-secondary)"
                    node["strokeWeight"] = 1
                flipped[0] += 1
        for child in node.get("children", []) or []:
            walk(child, inside_card or is_card, in_footer or is_footer)

    walk(blueprint, False, False)
    if flipped[0]:
        print(f"[규칙] 카드 표면 교정 — 최상위 카드 {flipped[0]}건: bg-secondary → bg-primary + border-secondary")
    if footer_fixed[0]:
        print(f"[규칙] Footer 표면 교정 — bg-secondary 채움 + 보더 제거 ({footer_fixed[0]}건)")


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
    BG_PRIMARY = "$token(bg-primary)"
    added = [0]

    def walk(node, is_root):
        if not isinstance(node, dict):
            return
        if (not is_root) and node.get("type") in (None, "frame", "FRAME") \
                and node.get("fill") == BG_PRIMARY \
                and node.get("children") \
                and not node.get("stroke") and not node.get("strokeColor"):
            node["strokeColor"] = "$token(border-secondary)"
            node["strokeWeight"] = 1
            added[0] += 1
        for child in node.get("children", []) or []:
            walk(child, False)

    walk(blueprint, True)
    if added[0]:
        print(f"[규칙] 흰 카드 보더 자동 — fill=bg-primary frame {added[0]}건에 border-secondary 1px 추가")


def _enforce_white_card_border_live(root_node_id: str) -> int:
    """빌드 후 라이브 트리에서 fill=bg-primary frame 에 border-secondary 1px 강제 (2026-05-27 사용자 분노).

    batch_build_screen 이 blueprint 의 strokeColor/strokeWeight 를 무시하는 버그 회피.
    빌드 트리 walk + bg-primary frame 인데 stroke 없는 것 다 잡아서 박는다.
    - 대상: type=FRAME + fill=#FCFCFD (bg-primary) + children 있음
    - 제외: 루트 자체, 이미 stroke 있는 frame, 자식이 단일 텍스트인 layout group (Banner Left, Status Marks 등)
    - 색: border-secondary RGB (0.902, 0.910, 0.922) — 사용자 명시
    - weight: 1.5px (1px 은 거의 안 보임)
    """
    BORDER_R, BORDER_G, BORDER_B = 0.902, 0.910, 0.922
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

    def _has_correct_stroke(node):
        """stroke 가 있고 weight=1 이면 OK. weight != 1 이면 갱신 대상."""
        strokes = node.get("strokes") or []
        if not strokes:
            return False
        sw = node.get("strokeWeight")
        if sw != 1:
            return False  # weight 다르면 갱신
        for s in strokes:
            if s.get("visible", True) and s.get("type") == "SOLID":
                return True
        return False

    def _is_card_like(node):
        """카드 판정 — wrapper 섹션은 제외 (2026-05-27 사용자 명시).

        혼합 케이스(예: 'Attendance Banner Wrap') 처리: wrapper 키워드 + cornerRadius < 8
        이면 wrapper. cornerRadius >= 8 이면 카드 (둥근 모서리는 카드의 시각적 표식).
        """
        if not node.get("children"):
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

    def walk(node, is_root):
        if not isinstance(node, dict):
            return
        # DS 인스턴스(badge/button/tag 등) 내부는 master 가 fill/stroke 제어 —
        # 절대 손대지 않는다 (2026-05-28 사용자 "badge 에 stroke 은 없는거란다").
        if (node.get("type") or "").upper() == "INSTANCE":
            return
        if node.get("type") not in ("FRAME", "frame"):
            for ch in node.get("children", []) or []:
                walk(ch, False)
            return
        if (not is_root) and _is_bg_primary(node) and _is_card_like(node) and not _has_correct_stroke(node):
            try:
                call_tool("set_stroke_color", {
                    "nodeId": node["id"],
                    "r": BORDER_R, "g": BORDER_G, "b": BORDER_B, "a": 1,
                    "strokeWeight": 1,
                })
                # 토큰 재바인딩 — set_stroke_color 가 raw RGB 박으면 token alias 풀림
                # _token_to_figma_path 로 정확한 figmaPath 얻어서 사용 (직접 hardcode 시 not-found silent-skip)
                try:
                    fp = _token_to_figma_path("border-secondary")
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
            walk(ch, False)

    try:
        items = parse_content(call_tool("get_nodes_info", {"nodeIds": [root_node_id]})).get("json")
        if isinstance(items, list) and items:
            walk(items[0].get("document") or items[0], True)
    except Exception as e:
        print(f"  [white-card-border-live] root fetch fail: {e}")

    if fixed[0]:
        print(f"  [white-card-border-live] ✓ bg-primary frame {fixed[0]}건에 border-secondary 1px 자동 박음 (batch_build stroke 무시 버그 우회)")
    else:
        print(f"  [white-card-border-live] OK — 모든 흰 카드에 이미 보더 있음")
    return fixed[0]


# Hero 금액 텍스트 패턴 — 부호(+/−) 또는 천단위 콤마가 있는 명확한 통화 표기
# 예: "+ 0원", "- 0원", "+1,300,000원", "12,500P", "1,000만원"
_HERO_AMOUNT_RE = __import__("re").compile(
    r"^\s*[+\-−]\s*[\d,]+\s*(원|만원|P|p|포인트)\s*$"           # 부호 prefix
    r"|^\s*[\d]{1,3}(,\d{3})+\s*(원|만원|P|p|포인트)\s*$"        # 천단위 콤마
)
_HERO_TEXT_SIZE = 30


def _enforce_text_hierarchy(blueprint: dict) -> None:
    """타이포 위계 강화 — 카드 안 hero 금액 텍스트를 28px+ Bold로 자동 승격 (2026-05-23).

    컬러가 절제될수록 시각 리듬은 크기·굵기 차이로 만들어야 한다. 통화 hero
    텍스트(부호 prefix 또는 천단위 콤마가 있는 금액)가 카드 안에 있으면 본문
    수준 폰트(<28px)로 남지 않도록 30px Bold 로 끌어올린다.
    """
    bumped = [0]

    def is_hero_amount(text: str) -> bool:
        t = (text or "").strip()
        if not t or len(t) > 18:
            return False
        return bool(_HERO_AMOUNT_RE.match(t))

    def walk(node, inside_card, parent_layout, narrow_parent_width=None):
        if not isinstance(node, dict):
            return
        in_card_now = inside_card or _is_card_like(node)
        if node.get("type") in ("text", "TEXT") and inside_card:
            text = node.get("text") or node.get("characters") or ""
            # 2026-05-27 fix — HORIZONTAL row 의 인라인 텍스트는 승격 금지.
            # 인라인 hero 를 30px 로 끌어올리면 row 의 다른 자식(suffix/pill/date 등)이
            # 깨진다(stage_list 회귀: r2-amt "20,800,000원" 17px → 30px 로 폭주, 카드 밖 흘러나옴).
            # VERTICAL 부모(또는 root)의 직계 자식 hero 만 승격 의도.
            if parent_layout == "HORIZONTAL":
                pass
            elif is_hero_amount(text):
                # 2026-05-27 — 좁은 부모(<150px) 안에서는 30px hero 승격 skip.
                # Schedule cell(116px) / Lounge card(130px) 안 통화 "+130만원" / "9,800원"
                # 이 30px Bold 로 승격되면 cell padding 안에 들어가지 못해 wrap → 사용자에게
                # "잘림" 으로 보임. 좁은 cell 은 본문 폰트(14~16px) 유지.
                if narrow_parent_width is not None and narrow_parent_width < 150:
                    pass
                else:
                    # 2026-05-28 위계 fix (사용자 분노 "왜 자꾸 텍스트 막 키우냐"):
                    # fontSize 명시되어 있으면 사용자/_polish 의도 보존. promotion 은 명시
                    # 안 된 텍스트만. 17/18 등 명시 박은 amount-row value 가 30 으로 덮어
                    # 씌워지는 회귀 차단.
                    cur = node.get("fontSize")
                    if cur is not None:
                        pass  # 명시 fontSize 보존 — 사용자 의도 우선
                    else:
                        node["fontSize"] = _HERO_TEXT_SIZE
                        font = node.get("fontName") or {}
                        if (font.get("style") or "").lower() != "bold":
                            node["fontName"] = {
                                "family": font.get("family") or "Pretendard",
                                "style": "Bold",
                            }
                        bumped[0] += 1
        cur_layout = ((node.get("autoLayout") or {}).get("layoutMode")
                      or node.get("layoutMode") or "").upper()
        # narrow parent width 추적 — 자식 hero 승격 판단용
        w = node.get("width")
        node_width = w if isinstance(w, (int, float)) and w > 0 else None
        child_narrow = node_width if node_width else narrow_parent_width
        for child in node.get("children", []) or []:
            walk(child, in_card_now, cur_layout, child_narrow)

    walk(blueprint, False, "")
    if bumped[0]:
        print(f"[규칙] 타이포 위계 — hero 금액 텍스트 {bumped[0]}건 → {_HERO_TEXT_SIZE}px Bold")


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
    _auto_search_uibowl_references(blueprint)

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

    # ⚠️ 시스템 규칙: 루트 프레임 배경은 반드시 bg-primary — 다른 값이 와도 강제 교정
    _enforce_root_bg_primary(blueprint)

    # ⚠️ 시스템 규칙: modal 패턴 → 색상 advisory → 카드 표면 → elevation → 타이포 위계 → 섹션 divider → tooltip ignore auto layout → disabled slot 패턴
    _enforce_modal_pattern(blueprint)
    _enforce_bottom_sheet_pattern(blueprint)  # 2026-05-27 — bottom sheet modal 기본형
    _enforce_color_restraint(blueprint)
    _enforce_card_surface(blueprint)
    _enforce_card_elevation(blueprint)  # 2026-05-27 — shadow 자동 주입 폐기 (제거기로 작동)
    _enforce_no_large_brand_fill(blueprint)  # 2026-05-27 — 큰 면적 frame brand fill 금지
    _enforce_white_card_border(blueprint)  # 2026-05-27 — fill=bg-primary frame 자동 border
    _enforce_text_hierarchy(blueprint)
    _enforce_section_dividers(blueprint)
    _enforce_tooltip_ignore_auto_layout(blueprint)
    _enforce_disabled_slot_pattern(blueprint)

    # 자동 바인딩용 원본 보존 ($token() 참조가 살아있는 사본 — resolve 전에 떠둠)
    original_blueprint = json.loads(json.dumps(blueprint))

    # Step E.0: ⚠️ archetype config reuse 검출 + _wireframeContent 의무 (2026-05-27 절대 룰 0-E)
    archetype_issues = _check_no_archetype_reuse(blueprint, blueprint_file)
    wc_required_issues = _check_wireframe_content_required(blueprint)
    archetype_issues = archetype_issues + wc_required_issues
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
    content = call_tool("batch_build_screen", {"blueprint": blueprint})
    result = parse_content(content)
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

    # Step G: NavBar 로고 인스턴스 교체
    if node_map and "Logo Placeholder" in node_map:
        print("\n🔲 NavBar 로고 교체 중...")
        try:
            placeholder_id = node_map["Logo Placeholder"]
            navbar_id = node_map.get("NavBar")
            if navbar_id:
                # 로고 컴포넌트 인스턴스 생성
                logo_content = call_tool("create_component_instance", {
                    "componentKey": "957912b03baf924a48ef83424ed66f22a4a386a8"
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

    # ⚠️ Step F (2026-05-27 박음) — frontend spec 자동 추출 → json/<화면이름>_<날짜>_<시간>.json
    # 메모리 feedback_frontend_json_export 에 "빌드 후 자동" 박혔지만 실제 코드에 없어서
    # 2026-05-21 이후 모든 빌드에서 spec 누락. 이제 cmd_build 가 직접 호출.
    if root_id:
        try:
            print("\n[Step F] Frontend spec 추출 중...")
            _export_frontend_spec(root_id)
        except Exception as e:
            print(f"  ⚠️ Frontend spec 추출 실패 (무시): {e}")

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
    print(f"전체 완료: {total_elapsed:.1f}s (빌드 {build_elapsed:.1f}s + 후처리)")
    # ⚠️ 2026-05-24 사용자 "다 박아" — latest rootId 명시 (post-fix/screenshot/binding 재사용용)
    if root_id:
        print(f"⭐ LATEST ROOT: {root_id}  (saved → .latest_build.json)")
        print(f"   re-screenshot:  python3 scripts/figma_mcp_client.py call export_node_as_image '{{\"nodeId\":\"{root_id}\",\"format\":\"PNG\",\"scale\":1}}'")
        print(f"   re-post-fix:    python3 scripts/figma_mcp_client.py post-fix {root_id}")
    print(f"{'='*50}")


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


def _export_frontend_spec(root_id: str) -> Optional[str]:
    """Frontend spec JSON 추출 — gen_frontend_spec.py 를 subprocess 로 호출 (2026-05-27).

    cmd_build 끝의 Step F. 빌드된 root 의 flexbox 스펙 + 토큰명·hex 병기를
    json/<화면이름>_<날짜>_<시간>.json 으로 저장. gen_frontend_spec.py 내부 main 이
    sys.argv 기반이라 subprocess 로 호출하는 게 안전.

    실패하면 무시 (Step F 는 빌드 자체엔 영향 없음).
    """
    import subprocess
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gen_script = os.path.join(project_root, "scripts", "gen_frontend_spec.py")
    if not os.path.exists(gen_script):
        print(f"  ⚠️ gen_frontend_spec.py 없음 — skip")
        return None
    json_dir = os.path.join(project_root, "json")
    os.makedirs(json_dir, exist_ok=True)
    try:
        result = subprocess.run(
            ["python3", gen_script, root_id],
            cwd=project_root,
            capture_output=True, text=True,
            timeout=60,
        )
        if result.returncode == 0:
            # gen_frontend_spec 가 stdout 마지막 줄에 출력 경로 명시
            out = (result.stdout or "").strip().split("\n")
            saved_line = next((ln for ln in reversed(out) if "json/" in ln), None)
            if saved_line:
                print(f"  ✓ {saved_line}")
            else:
                print(f"  ✓ Frontend spec 추출 완료")
            return saved_line
        else:
            print(f"  ⚠️ gen_frontend_spec exit {result.returncode}: {(result.stderr or '')[:200]}")
            return None
    except subprocess.TimeoutExpired:
        print(f"  ⚠️ gen_frontend_spec timeout (60s)")
        return None


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
                try:
                    call_tool("set_layout_sizing", {
                        "nodeId": node_id,
                        "horizontal": "FILL"
                    })
                    fix_count += 1
                    print(f"  FILL 수정: {node_name} ({node_id}) [{sizing_h} → FILL]")
                except Exception as e:
                    print(f"  FILL 수정 실패: {node_name} ({node_id}): {e}")

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
                try:
                    call_tool("set_layout_sizing", {
                        "nodeId": child_id,
                        "horizontal": "FILL"
                    })
                    fix_count += 1
                    depth_label = "루트 자식" if depth == 0 else f"depth {depth + 1}"
                    print(f"  FILL 강제({depth_label}): {child.get('name', '?')} ({child_id}) [{child_sizing} → FILL]")
                except Exception as e:
                    print(f"  FILL 강제 실패: {child.get('name', '?')} ({child_id}): {e}")

            # 재귀: FRAME/COMPONENT 자식의 하위도 검사
            if child_type in ("FRAME", "COMPONENT") and depth < max_depth:
                _force_fill_recursive(child, depth + 1, max_depth)

    _force_fill_recursive(tree)

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
        try:
            if has_fills:
                call_tool("set_fill_color", {"nodeId": node_id, "r": 1, "g": 1, "b": 1, "a": 1})
                if fp:
                    try:
                        call_tool("set_bound_variables", {"nodeId": node_id, "bindings": {"fills/0": fp}})
                    except Exception:
                        pass
            if has_strokes:
                call_tool("set_stroke_color", {"nodeId": node_id, "r": 1, "g": 1, "b": 1, "a": 1})
                if fp:
                    try:
                        call_tool("set_bound_variables", {"nodeId": node_id, "bindings": {"strokes/0": fp}})
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
        try:
            if has_fills:
                call_tool("set_fill_color", {"nodeId": node_id, "r": 1, "g": 1, "b": 1, "a": 1})
                if fp:
                    try:
                        call_tool("set_bound_variables", {"nodeId": node_id, "bindings": {"fills/0": fp}})
                    except Exception:
                        pass
            if has_strokes:
                call_tool("set_stroke_color", {"nodeId": node_id, "r": 1, "g": 1, "b": 1, "a": 1})
                if fp:
                    try:
                        call_tool("set_bound_variables", {"nodeId": node_id, "bindings": {"strokes/0": fp}})
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


def _enforce_fixed_size_invariants_final(root_id: str) -> int:
    """최종 강제 레이어 (2026-05-28) — post-fix 모든 룰 끝난 뒤 순서 무관하게
    고정 사이즈 invariant 보장. vertical-hug 류 룰이 FAB/circle/icon-box 를
    24px 로 찌그러뜨리는 회귀를 마지막에 복원.

      - FAB (name 'FAB') → 56×56 FIXED, cornerRadius 28
      - 원형/icon-box (cornerRadius >= w/2, 20<=w<=80, w!=h) → max(w,h) 정사각 FIXED
    """
    fixed = [0]

    def _is_circle_iconbox(n):
        cr = n.get("cornerRadius") or 0
        w = n.get("width") or 0
        h = n.get("height") or 0
        if not (isinstance(w, (int, float)) and isinstance(h, (int, float))):
            return False
        if not (20 <= w <= 80):
            return False
        # 원형 (cornerRadius >= 절반) 또는 단일 vector/icon-frame 자식
        if cr >= (min(w, h) / 2) - 3:
            return True
        kids = n.get("children") or []
        if len(kids) == 1:
            ck = (kids[0].get("type") or "").upper()
            if ck in ("FRAME", "INSTANCE", "VECTOR"):
                return True
        return False

    def walk(node, parent_layout=""):
        if not isinstance(node, dict):
            return
        ntype = (node.get("type") or "").upper()
        name = (node.get("name") or "")
        nl = name.lower()
        nid = node.get("id")
        w = node.get("width") or 0
        h = node.get("height") or 0
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
        # 카드 padding 복원 (batch_build 가 grid row 안 카드의 padding 을 누락 →
        # 요소가 경계에 붙음). VERTICAL 카드(cornerRadius>=12 + 자식 3+)의 paddingLeft<12
        # 면 16 복원. layoutMode 동일 재설정이라 자식 sizing 영향 최소.
        elif (ntype == "FRAME" and not node.get("componentKey")
              and "card" in name.lower()
              and "carousel" not in name.lower()
              and (node.get("paddingLeft") or 0) < 8):  # padding 없는 카드만 (있으면 skip)
            try:
                call_tool("set_auto_layout", {
                    "nodeId": nid, "layoutMode": "VERTICAL",
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


def _enforce_root_min_height(root_id: str) -> None:
    """루트 height 정책 — 콘텐츠 길이에 따라 두 가지 분기 (2026-05-24):

    A) **콘텐츠 ≤ ROOT_MIN_HEIGHT (852) 인 짧은 화면**
       - root height = ROOT_MIN_HEIGHT (852)
       - 하단 바(BAB / Tab Bar / CTA Bar / FAB)를 ABSOLUTE + constraint MAX 로
         루트 하단(852 - bar_h)에 pin → 빈 공간 위에 떠 있음.

    B) **콘텐츠 > ROOT_MIN_HEIGHT 인 긴 화면**
       - 하단 바를 normal flow(AUTO)로 전환 — 콘텐츠 아래 자연스럽게 자리잡음.
       - root layoutSizingVertical = HUG → 콘텐츠 + 하단 바 모두 포함하도록 자동 확장.
       - ABSOLUTE pin 그대로 두면 BAB 가 콘텐츠를 덮어 잘려보임(2026-05-24 v14 회귀).

    FAB 는 floating button 이므로 두 케이스 모두 ABSOLUTE 유지.
    """
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

        if content_overflows and tabish:
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

    # ⚠️ 시스템 규칙: 루트 프레임 배경 = bg-primary 강제 (런타임 보장)
    print("\n[규칙] 루트 프레임 배경 bg-primary 강제 적용 중...")
    _enforce_root_bg_primary_live(root_node_id)

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
    print("\n[규칙] 루트 minHeight=852 + 하단 바 bottom-pin 적용 중...")
    _enforce_root_min_height(root_node_id)

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
    print("\n[규칙] 흰 카드 border 라이브 강제 (batch_build stroke 무시 버그 우회) 적용 중...")
    try:
        _enforce_white_card_border_live(root_node_id)
    except Exception as e:
        print(f"  [white-card-border-live] 실패 (무시하고 계속): {e}")

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

    elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"POST-FIX 완료 — {elapsed:.1f}s")
    print(f"  FILL 수정: {fill_fixes}건")
    print(f"  Tab Bar/Stroke 수정: {tab_fixes}건")
    print(f"  텍스트 수정: {text_fixes}건")
    print(f"  루트 높이: {layout_result['root_height']}")
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
    info = tm.get(token_name)
    if info and info.get("figmaPath"):
        return info["figmaPath"]
    # Pass 1: 마지막 세그먼트 '정확 일치' 우선
    for path, info_item in tm.items():
        fp = info_item.get("figmaPath", path)
        seg = fp.rsplit("/", 1)[-1] if "/" in fp else fp
        if seg == token_name:
            return fp
    # Pass 2: 괄호 변형만 허용 — '_' prefix 매칭 절대 금지
    for path, info_item in tm.items():
        fp = info_item.get("figmaPath", path)
        seg = fp.rsplit("/", 1)[-1] if "/" in fp else fp
        if seg.startswith(token_name + " "):
            return fp
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
    is_ds_instance = ((bp_node.get("type") or "").lower() == "instance"
                      or bool(bp_node.get("componentKey"))
                      or bool(bp_node.get("_dsResolvedRole")))
    if not is_ds_instance:
        # 색상: fill/stroke/strokeColor/fontColor/iconColor → fills/0 · strokes/0
        # ⚠️ strokeColor 도 stroke 와 동일 처리 (blueprint 가 둘 다 사용 — 2026-05-27 사용자 분노 fix)
        for field, prop in (("fill", "fills/0"), ("stroke", "strokes/0"),
                            ("strokeColor", "strokes/0"),
                            ("fontColor", "fills/0"), ("iconColor", "fills/0")):
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
                    binds[prop] = fp
        # 타이포: fontSize → fontSize/k 변수
        fs = bp_node.get("fontSize")
        if isinstance(fs, (int, float)):
            fp = _load_fontsize_map().get(float(fs))
            if fp:
                binds["fontSize"] = fp
    if node_id and binds:
        out.append({"nodeId": node_id, "bindings": binds})
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
        url = f"https://loremflickr.com/600/600/{kw}"
        try:
            req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = _ur.urlopen(req, timeout=25).read()
            if len(data) < 2000:  # 에러 페이지/빈 이미지
                continue
            b64 = _b64.b64encode(data).decode()
            call_tool("set_image_fill", {"nodeId": nid, "imageData": b64})
            # placeholder icon 자식 제거 (실사진 위 보라 gift 아이콘 등)
            for pid in job.get("placeholders") or []:
                try:
                    call_tool("delete_node", {"nodeId": pid})
                except Exception:
                    pass
            applied += 1
            print(f"  [apply-images] '{kw}' → {nid} ({len(data)}b)")
        except Exception as e:
            print(f"  [apply-images] '{kw}' {nid} 실패(placeholder 유지): {e}")
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

    # dict 의 모든 string value 를 평탄화 추출
    expected = []
    def _flatten(v):
        if isinstance(v, str):
            s = v.strip()
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
                if isinstance(c, str) and c.strip():
                    built_texts.append(c.strip())
            for ch in n.get("children", []) or []:
                _walk(ch)
    _walk(built or {})
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
        if (right_overflow or left_overflow) and node.get("layoutSizingHorizontal") != "FILL":
            if _is_icon_like(node) or _is_small_pill(node) or parent_is_carousel:
                pass
            else:
                try:
                    call_tool("set_layout_sizing", {
                        "nodeId": node.get("id"), "horizontal": "FILL",
                    })
                    fixed += 1
                    if left_overflow:
                        print(f"  [overflow] '{node.get('name')}' x={int(nx)} < root left {int(rx)} → FILL (좌측)")
                    else:
                        print(f"  [overflow] '{node.get('name')}' x+w={int(nx+nw)} > root right {int(right_limit)} → FILL (우측)")
                except Exception:
                    pass
        # 자식 walk — 이 node가 carousel이면 자식들은 parent_is_carousel=True
        node_is_carousel = _is_carousel_name(node.get("name"))
        for c in node.get("children") or []:
            walk(c, node_is_carousel)

    walk(root)
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
        spacing = parent.get("itemSpacing")
        if not isinstance(spacing, (int, float)) or spacing <= 0:
            spacing = 12
        # padding 유지
        pads = {
            "paddingTop": parent.get("paddingTop") or 0,
            "paddingBottom": parent.get("paddingBottom") or 0,
            "paddingLeft": parent.get("paddingLeft") or 0,
            "paddingRight": parent.get("paddingRight") or 0,
        }
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
    """cornerRadius ≥ 8 frame 은 clipsContent=true 강제 — 2026-05-28 사용자 명시.

    R45 (`_disable_section_clipping`) 가 모든 frame clip 을 false 로 강제하면서
    라운지 카드 같은 rounded card 의 내부 image/색 영역이 카드 라운드 모서리 밖으로
    튀어나와 상단이 각져 보이는 버그. R45 에 rounded card 예외를 박았지만, 라이브 강제도
    별도로 둠 — generator/manual fix 가 clip false 박아도 마지막에 true 로 되돌림.

    대상: cornerRadius ≥ 8 (또는 individual corner ≥ 8) FRAME + 자식 ≥ 1.
    root 자체는 건드리지 않음 (이미 plugin 이 true 강제).

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
        if isinstance(cr, (int, float)) and cr >= 8:
            return True
        for k in ("topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius"):
            v = n.get(k)
            if isinstance(v, (int, float)) and v >= 8:
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
_DS_TEXT_SIZE_SCALE = (12, 14, 16, 18, 20, 24, 30, 36, 48, 60, 72)
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


def _load_text_style_map() -> dict:
    """DS text styles → {(size:int, weight_bucket:str): styleKey} 인덱스. 캐시."""
    global _TEXT_STYLE_MAP_CACHE
    if _TEXT_STYLE_MAP_CACHE is not None:
        return _TEXT_STYLE_MAP_CACHE
    try:
        d = parse_content(call_tool("get_styles", {})).get("json") or {}
    except Exception as e:
        print(f"  [text-style] get_styles 실패: {e}")
        _TEXT_STYLE_MAP_CACHE = {}
        return _TEXT_STYLE_MAP_CACHE
    idx = {}
    for t in (d.get("texts") or []):
        size = t.get("fontSize")
        if not isinstance(size, (int, float)):
            continue
        # DS style 이름 예: "Display 2xl/Bold", "Text md/Medium" — 끝의 슬래시-suffix 가 weight
        name = t.get("name") or ""
        suffix = name.split("/")[-1] if "/" in name else (t.get("fontName") or {}).get("style")
        bucket = _weight_bucket(suffix)
        idx[(int(size), bucket)] = t.get("key")
    _TEXT_STYLE_MAP_CACHE = idx
    return idx


def _snap_to_ds_size(size: int) -> Optional[int]:
    """off-scale 사이즈를 ±3px 안 가장 가까운 DS 스케일로 snap. 범위 밖이면 None."""
    best, best_d = None, _DS_TEXT_SIZE_TOLERANCE + 1
    for s in _DS_TEXT_SIZE_SCALE:
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
                        snapped = _snap_to_ds_size(si)
                        if snapped is not None:
                            key = style_map.get((snapped, bucket))
                    if key:
                        entries.append({"nodeId": nid, "textStyleId": f"S:{key},{root_id}"})
                        stats["applied"] += 1
                    else:
                        stats["no_match"] += 1
        for c in node.get("children", []) or []:
            walk(c)

    walk(built)
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
            if unset:
                print(f"  [text-style] ⚠️ silent fail 검출 {len(unset)}건 — 재시도 중...")
                retry_ok = 0
                for e in unset:
                    try:
                        call_tool("set_text_style_id", {"nodeId": e["nodeId"], "textStyleId": e["textStyleId"]})
                        retry_ok += 1
                    except Exception:
                        pass
                verify2 = parse_content(call_tool("get_nodes_info", {"nodeIds": [e["nodeId"] for e in unset]})).get("json")
                still_unset = 0
                if isinstance(verify2, list):
                    for it in verify2:
                        d = it.get("document") or it
                        if not _stored_text_style_id(d):
                            still_unset += 1
                print(f"  [text-style] 재시도 결과 — {retry_ok}건 호출, {still_unset}건 여전히 미적용")
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
    _EFFECT_STYLE_MAP_CACHE = idx
    return idx


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

    def walk(node):
        if not isinstance(node, dict):
            return
        ntype = node.get("type")
        if ntype in (None, "frame", "FRAME"):
            fill = node.get("fill") or ""
            if isinstance(fill, str) and any(p in fill for p in BRAND_FILL_PARTS):
                if is_large_container(node):
                    node["fill"] = "$token(bg-primary)"
                    if not node.get("stroke") and not node.get("strokeColor"):
                        node["strokeColor"] = "$token(border-secondary)"
                        node["strokeWeight"] = 1
                    flipped[0] += 1
        for c in node.get("children") or []:
            walk(c)

    walk(blueprint)
    if flipped[0]:
        print(f"[규칙] 큰 brand 카드 fill 교정 — {flipped[0]}건 bg-brand-* → bg-primary + border (2026-05-27 사용자 명시)")


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
    BORDER = (0.894, 0.906, 0.925)
    for nid, name in targets:
        try:
            call_tool("set_fill_color", {"nodeId": nid, "r": WHITE[0], "g": WHITE[1], "b": WHITE[2], "a": 1})
            call_tool("set_stroke_color", {
                "nodeId": nid, "r": BORDER[0], "g": BORDER[1], "b": BORDER[2], "a": 1, "strokeWeight": 1
            })
            fixed += 1
            print(f"    [no-large-brand] '{name}' → bg-primary + border (brand fill 제거)")
        except Exception:
            pass
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
            call_tool("set_auto_layout", {
                "nodeId": child.get("id"),
                "layoutMode": child.get("layoutMode"),
                "paddingTop": new_pt,
                "paddingBottom": new_pb,
                "paddingLeft": child.get("paddingLeft") or 0,
                "paddingRight": child.get("paddingRight") or 0,
                "itemSpacing": child.get("itemSpacing") or 0,
            })
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
    - NavBar: (현재 변수 없음 — 로고는 빌드 후 교체)
    - TabBar: activeTab
    """
    if not vars_dict:
        return node

    if section_name == "FAB":
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


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "init":
        cmd_init()
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
        with open(sys.argv[2]) as f:
            bp = json.load(f)
        bp = _flatten_padding_objects(bp)
        issues = validate_blueprint(bp)
        if not issues:
            print("✓ Blueprint validation passed — no issues found")
        else:
            errors = [i for i in issues if i.startswith("ERROR")]
            warns = [i for i in issues if i.startswith("WARN")]
            print(f"{'✗' if errors else '⚠'} {len(errors)} error(s), {len(warns)} warning(s):")
            for issue in issues:
                print(f"  {issue}")
    elif cmd == "assemble":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py assemble <config.json>")
            sys.exit(1)
        cmd_assemble(sys.argv[2])
    elif cmd == "interactive":
        cmd_interactive()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
