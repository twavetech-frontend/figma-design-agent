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


def cmd_call(tool_name: str, args_json: str):
    ensure_session()
    args = json.loads(args_json) if args_json else {}
    content = call_tool(tool_name, args)
    result = parse_content(content)

    if result["json"]:
        print(json.dumps(result["json"], indent=2, ensure_ascii=False))
    else:
        for t in result["texts"]:
            print(t)
    if result["images"]:
        print(f"\n[{len(result['images'])} image(s) returned]")


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
    """루트 위 **타이틀 섹션(헤딩 ≥17px 보유) 앞에만** 1px divider 자동 삽입 (2026-05-24 룰).

    너무 자주 넣으면 정보 탐색이 흐트러진다 — 타이틀이 있는 섹션 앞에만 (= 진짜 정보 그룹 경계).
    Status Bar / NavBar / Bottom Action Bar / Tab Bar / Footer 같은 utility 프레임은 제외.
    divider 삽입 시 아래 섹션의 `paddingTop` 을 0 으로 정리 — divider padding 과 섹션 padding 이
    겹쳐 불규칙 갭이 생기지 않게 (2026-05-24 추가). 재실행에도 안전.
    """
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
        is_card = (not in_footer and not is_footer) and _is_card_like(node)
        if is_card and not inside_card:
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
    """그림자 없는 카드형 프레임에 subtle drop shadow 자동 주입 (2026-05-23).

    평평한 그레이 박스만 나열하면 와이어프레임처럼 보인다 — 카드에 입체감을
    코드로 강제해 '디자인된' 느낌을 보장한다. CLAUDE.md 룰 2 폴리시 항목.
    대상: cornerRadius ≥ 8 + fill + children 을 가진 카드형 프레임(루트 제외).
    """
    shadow = {
        "type": "DROP_SHADOW",
        "color": {"r": 0, "g": 0, "b": 0, "a": 0.06},
        "offset": {"x": 0, "y": 2},
        "radius": 8,
        "spread": 0,
        "visible": True,
    }
    added = [0]

    def walk(node, is_root, in_footer):
        if not isinstance(node, dict):
            return
        # Footer 는 그림자 없는 회색 띠 — elevation 제외
        if (not in_footer) and _is_footer(node):
            in_footer = True
        if not is_root and not in_footer and _is_card_like(node) and not node.get("effects"):
            node["effects"] = [dict(shadow)]
            added[0] += 1
        for child in node.get("children", []) or []:
            walk(child, False, in_footer)

    walk(blueprint, True, False)
    if added[0]:
        print(f"[규칙] 카드 elevation 자동 주입 — 그림자 없는 카드 {added[0]}건에 subtle shadow 추가")


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
                    cur = node.get("fontSize") or 0
                    if cur < 28:
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


def cmd_build(blueprint_file: str):
    """Build a screen from a blueprint JSON file.

    Supports $token() references in color fields. Before building,
    all $token(name) values are resolved to RGBA using TOKEN_MAP.json.

    Example blueprint color:
        "fill": "$token(bg-brand-solid)"
        "fontColor": "$token(fg-brand-primary)"
    These are resolved to {"r": ..., "g": ..., "b": ..., "a": ...} at build time.
    """
    ensure_session()

    with open(blueprint_file) as f:
        blueprint = json.load(f)

    # ⚠️ 시스템 규칙: 루트 프레임 배경은 반드시 bg-primary — 다른 값이 와도 강제 교정
    _enforce_root_bg_primary(blueprint)

    # ⚠️ 시스템 규칙: modal 패턴 → 색상 advisory → 카드 표면 → elevation → 타이포 위계 → 섹션 divider → tooltip ignore auto layout → disabled slot 패턴
    _enforce_modal_pattern(blueprint)
    _enforce_bottom_sheet_pattern(blueprint)  # 2026-05-27 — bottom sheet modal 기본형
    _enforce_color_restraint(blueprint)
    _enforce_card_surface(blueprint)
    _enforce_card_elevation(blueprint)
    _enforce_text_hierarchy(blueprint)
    _enforce_section_dividers(blueprint)
    _enforce_tooltip_ignore_auto_layout(blueprint)
    _enforce_disabled_slot_pattern(blueprint)

    # 자동 바인딩용 원본 보존 ($token() 참조가 살아있는 사본 — resolve 전에 떠둠)
    original_blueprint = json.loads(json.dumps(blueprint))

    # Step 1: Validate blueprint before any processing
    issues = validate_blueprint(blueprint)
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
        cmd_post_fix(root_id, pre_computed_layout=sim_layout, original_blueprint=original_blueprint)
        print("\n🔧 후처리 2회차 (레이아웃 안정화 후 최종 배치)...")
        cmd_post_fix(root_id, original_blueprint=original_blueprint)
    else:
        print("⚠️  rootId를 찾을 수 없어 post-fix를 건너뜁니다.")

    # Step E.5: DS 변수 자동 바인딩 (색상·타이포) — $token() blueprint 기반
    if root_id:
        print("\n🔗 DS 변수 자동 바인딩 중...")
        try:
            auto_bind_design(root_id, original_blueprint)
        except Exception as e:
            print(f"  [auto-bind] 실패 (무시하고 계속): {e}")

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

        print("\n🌑 DS Effect Style (Shadows) 자동 적용 중...")
        try:
            _apply_ds_effect_styles(root_id)
        except Exception as e:
            print(f"  [effect-style] 실패 (무시하고 계속): {e}")

    # Step E.6: QA — blueprint text 노드 무결성 검증 (이모지/아이콘 오변환 사고 차단)
    if root_id:
        print("\n🔎 QA — 텍스트 노드 무결성 검증 중...")
        try:
            _qa_blueprint_integrity(original_blueprint, root_id)
        except Exception as e:
            print(f"  [QA] 실패 (무시하고 계속): {e}")

    # Step E.7: QA — 가시성(대비) + 레이아웃(겹침/데드밴드) 자동 검사
    if root_id:
        print("\n🔎 QA — 대비/레이아웃 시각 검사 중...")
        try:
            _qa_visual_checks(root_id)
        except Exception as e:
            print(f"  [QA] 시각 검사 실패 (무시하고 계속): {e}")

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

    total_elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"전체 완료: {total_elapsed:.1f}s (빌드 {build_elapsed:.1f}s + 후처리)")
    # ⚠️ 2026-05-24 사용자 "다 박아" — latest rootId 명시 (post-fix/screenshot/binding 재사용용)
    if root_id:
        print(f"⭐ LATEST ROOT: {root_id}  (saved → .latest_build.json)")
        print(f"   re-screenshot:  python3 scripts/figma_mcp_client.py call export_node_as_image '{{\"nodeId\":\"{root_id}\",\"format\":\"PNG\",\"scale\":1}}'")
        print(f"   re-post-fix:    python3 scripts/figma_mcp_client.py post-fix {root_id}")
    print(f"{'='*50}")


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

    def walk(node, depth=0):
        if depth > 0:  # root 자체는 제외 (별도 _enforce_root_min_height 가 결정)
            nm_low = (node.get("name") or "").lower()
            layout_mode = (node.get("layoutMode") or "").upper()
            sizing_v = node.get("layoutSizingVertical")
            # ABSOLUTE 배치 대상은 제외
            skip = any(kw in nm_low for kw in _VERTICAL_HUG_SKIP_KEYWORDS)
            # ABSOLUTE 노드도 제외
            if node.get("layoutPositioning") == "ABSOLUTE":
                skip = True
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
        for c in node.get("children", []) or []:
            walk(c, depth + 1)

    walk(doc)
    if fixed[0]:
        print(f"  [vertical-hug] VERTICAL FIXED → HUG 강제 {fixed[0]}건 "
              f"(batch_build height-FIXED 버그 회피)")
    else:
        print(f"  [vertical-hug] OK — VERTICAL frame 전부 HUG/FILL")
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
                 original_blueprint: Optional[dict] = None):
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
    print("\n[규칙] R45 섹션 clipsContent=false 강제 (carousel 제외) 적용 중...")
    _disable_section_clipping(root_node_id)

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
    # 색상: fill/stroke/fontColor/iconColor → fills/0 · strokes/0
    for field, prop in (("fill", "fills/0"), ("stroke", "strokes/0"),
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

    targets = []  # (id, layoutMode)

    def walk(node, depth):
        if not isinstance(node, dict):
            return
        # root(depth=0) 자체는 건드리지 않음 — viewport
        if depth > 0 and (node.get("type") or "").upper() == "FRAME":
            if node.get("clipsContent") is True and not is_carousel_wrapper(node):
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
        icon = vars_dict.get("icon")
        fill = vars_dict.get("fill")
        text_color = vars_dict.get("textColor")
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
        active_tab = vars_dict.get("activeTab", "홈")
        for tab_child in node.get("children", []):
            tab_children = tab_child.get("children", [])
            is_active = False
            for sub in tab_children:
                if sub.get("type") == "text" and sub.get("text") == active_tab:
                    is_active = True
                    break
            for sub in tab_children:
                if is_active:
                    if sub.get("type") == "icon":
                        sub["iconColor"] = "$token(fg-brand-primary)"
                    elif sub.get("type") == "text":
                        sub["fontColor"] = "$token(fg-brand-primary)"
                        sub["fontName"] = {"family": "Pretendard", "style": "SemiBold"}
                else:
                    if sub.get("type") == "icon":
                        sub["iconColor"] = "$token(fg-quaternary)"
                    elif sub.get("type") == "text":
                        sub["fontColor"] = "$token(fg-quaternary)"
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
            print("Usage: figma_mcp_client.py call <tool_name> [args_json]")
            sys.exit(1)
        cmd_call(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "{}")
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
