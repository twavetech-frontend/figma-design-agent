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
import base64
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional, List, Dict

MCP_URL = "http://localhost:8769/mcp"
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


def resolve_token_ref(value: str) -> Optional[Dict[str, float]]:
    """Resolve a $token(name) reference to RGBA.

    Supported formats:
        "$token(bg-brand-solid)"
        "$token(Colors/Background/bg-brand-solid)"
        "$token(fg-brand-primary)" — matches "fg-brand-primary (600)" etc.
    """
    if not isinstance(value, str) or not value.startswith("$token("):
        return None
    token_name = value[7:-1]  # strip "$token(" and ")"
    token_map = load_token_map()

    # Exact match
    info = token_map.get(token_name)
    if info and info.get("type") == "COLOR":
        return hex_to_rgba(info["value"])

    # Partial match — search for token name in figmaPath endings
    for path, info_item in token_map.items():
        figma_path = info_item.get("figmaPath", path)
        last_segment = figma_path.rsplit("/", 1)[-1] if "/" in figma_path else figma_path
        # Match: exact segment, or segment starts with token_name + space/underscore
        # e.g. "fg-brand-primary" matches "fg-brand-primary (600)"
        if last_segment == token_name or last_segment.startswith(token_name + " ") or last_segment.startswith(token_name + "_"):
            if info_item.get("type") == "COLOR":
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

    resp = requests.post(MCP_URL, json=payload, headers=headers, timeout=300)

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
    requests.post(MCP_URL, json=payload, headers=headers, timeout=10)

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
        yoga_src = os.path.join(project_root, "src", "yoga-cli.ts")
        proc = subprocess.run(
            ["npx", "tsx", yoga_src],
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

    # ──── 병렬 실행: 이미지 사전 생성 + 빌드 동시 시작 ────
    # Step A: Blueprint에서 imageGen 스펙을 빌드 전에 추출 (nodeId 불필요)
    image_specs_raw = []

    def _walk_for_image_specs(node: dict):
        image_gen = node.get("imageGen")
        if image_gen and isinstance(image_gen, dict):
            image_specs_raw.append({
                "nodeName": node.get("name", ""),
                "prompt": image_gen.get("prompt", ""),
                "isHero": image_gen.get("isHero", False),
                "width": image_gen.get("width"),
                "height": image_gen.get("height"),
                "style": image_gen.get("style"),
            })
        for child in node.get("children", []):
            _walk_for_image_specs(child)

    _walk_for_image_specs(blueprint)

    # Step B: 이미지 사전 생성을 백그라운드 스레드로 시작
    pre_gen_future = None
    if image_specs_raw:
        print(f"\n🎨 이미지 사전 생성 시작 ({len(image_specs_raw)}건 — 빌드와 병렬 실행)")
        executor = ThreadPoolExecutor(max_workers=1)
        pre_gen_future = executor.submit(_pre_generate_images_parallel, image_specs_raw)

    # Step C: 빌드 실행 (이미지 생성과 동시)
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

    # Step E: post-fix
    if root_id:
        print("\n🔧 자동 후처리 실행 중...")
        sim_layout = sim_result.get("layout") if sim_result else None
        cmd_post_fix(root_id, pre_computed_layout=sim_layout)
    else:
        print("⚠️  rootId를 찾을 수 없어 post-fix를 건너뜁니다.")

    # Step F: 이미지 사전 생성 완료 대기 + Figma 적용
    if pre_gen_future and node_map is not None:
        print("\n⏳ 이미지 사전 생성 완료 대기 중...")
        pre_results = pre_gen_future.result()  # 이미 완료됐으면 즉시 반환
        executor.shutdown(wait=False)

        ok_results = [r for r in pre_results if "imagePath" in r]
        if ok_results:
            print(f"\n🖼️  이미지 Figma 적용 ({len(ok_results)}건)...")
            _apply_pre_generated_images(pre_results, node_map)
        else:
            print("\n  이미지 사전 생성 결과 없음")
    elif pre_gen_future:
        # node_map이 None (빌드 실패)이어서 적용 불가
        pre_gen_future.cancel()
        executor.shutdown(wait=False)
        print("\n⚠️  nodeMap이 None — 빌드 실패로 사전 생성 이미지 적용 불가")
    elif not image_specs_raw:
        print("\n(imageGen 스펙 없음 — 이미지 생성 건너뜀)")

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

    total_elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"전체 완료: {total_elapsed:.1f}s (빌드 {build_elapsed:.1f}s + 후처리 + 이미지)")
    print(f"{'='*50}")


def _extract_image_specs(blueprint: dict, node_map: dict) -> list:
    """Blueprint에서 imageGen 스펙을 추출하고, nodeMap으로 실제 nodeId를 매핑.

    Blueprint 노드에 imageGen 필드가 있으면:
    {
        "name": "Banner Card 1",
        "imageGen": {
            "prompt": "3D coins floating...",
            "isHero": true,
            "style": "yanolja-3d"  // optional
        }
    }

    Returns: [{"nodeId": "85:1502", "prompt": "...", "isHero": true, "style": "..."}, ...]
    """
    specs = []

    def _walk(node: dict):
        name = node.get("name", "")
        image_gen = node.get("imageGen")
        if image_gen and isinstance(image_gen, dict):
            # nodeMap에서 실제 nodeId 찾기
            node_id = node_map.get(name)
            if node_id:
                spec = {
                    "nodeId": node_id,
                    "nodeName": name,
                    "prompt": image_gen.get("prompt", ""),
                    "isHero": image_gen.get("isHero", False),
                    "width": image_gen.get("width"),
                    "height": image_gen.get("height"),
                    "style": image_gen.get("style"),
                }
                specs.append(spec)
            else:
                print(f"  ⚠️ imageGen 노드 '{name}'의 nodeId를 nodeMap에서 찾을 수 없음")

        for child in node.get("children", []):
            _walk(child)

    _walk(blueprint)
    return specs


def _generate_images(specs: list):
    """generate_image MCP 도구로 이미지 생성 + Figma 노드에 적용. (기존 순차 방식)"""
    start = time.time()
    success = 0
    fail = 0

    for i, spec in enumerate(specs):
        node_name = spec["nodeName"]
        node_id = spec["nodeId"]
        prompt = spec["prompt"]
        is_hero = spec.get("isHero", False)

        print(f"  [{i+1}/{len(specs)}] {node_name} ({'hero' if is_hero else 'icon'})...")

        params = {
            "prompt": prompt,
            "nodeId": node_id,
            "isHero": is_hero,
        }
        if spec.get("width"):
            params["width"] = spec["width"]
        if spec.get("height"):
            params["height"] = spec["height"]
        if spec.get("style"):
            params["style"] = spec["style"]

        try:
            content = call_tool("generate_image", params)
            result = parse_content(content)
            if result["json"] and result["json"].get("success"):
                print(f"    ✅ 완료 ({result['json'].get('width')}x{result['json'].get('height')})")
                success += 1
            else:
                print(f"    ❌ 실패: {result.get('texts', ['unknown error'])}")
                fail += 1
        except Exception as e:
            print(f"    ❌ 에러: {e}")
            fail += 1

    elapsed = time.time() - start
    print(f"\n  이미지 생성 완료 — {success} 성공, {fail} 실패 ({elapsed:.1f}s)")


# ─── 병렬 이미지 사전 생성 (빌드와 동시 실행) ───────────────────────────

GEMINI_MODEL = "gemini-3-pro-image-preview"
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

DEFAULT_3D_STYLE = "Cinema4D, Octane render, soft diffused studio lighting, front view, orthographic projection, matte clay-like material with subtle specular, warm gentle shadows, simple symbolic forms, rounded friendly shapes, transparent background, clean minimal, high quality"
TOSSFACE_2D_STYLE = "Tossface emoji style: completely flat 2D, NO gradients, NO shadows, NO outlines, NO 3D effects, NO perspective, simple geometric rounded shapes, 2-3 solid bright colors only, minimal detail, like a simplified emoji icon, clean vector look, transparent background"

def _get_gemini_api_key() -> str:
    """Electron 앱 설정에서 Gemini API 키를 로드."""
    settings_path = os.path.expanduser(
        "~/Library/Application Support/figma-design-agent/settings.json"
    )
    try:
        with open(settings_path) as f:
            return json.load(f).get("geminiApiKey", "")
    except FileNotFoundError:
        return ""


def _find_reference_images(prompt: str, is_2d: bool) -> list:
    """프롬프트와 스타일에 맞는 레퍼런스 이미지를 자동 탐색."""
    ref_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "reference-images")
    refs = []
    subdir = "2d" if is_2d else "icon"
    target_dir = os.path.join(ref_dir, subdir)
    if os.path.isdir(target_dir):
        for fname in os.listdir(target_dir):
            if fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                refs.append(os.path.join(target_dir, fname))
                if len(refs) >= 2:
                    break
    return refs


def _pre_generate_single(spec: dict, api_key: str, output_dir: str) -> dict:
    """단일 이미지를 Gemini API로 사전 생성 (nodeId 불필요).

    Returns: {"nodeName": str, "imagePath": str, "isHero": bool} or {"nodeName": str, "error": str}
    """
    node_name = spec["nodeName"]
    prompt = spec["prompt"]
    is_hero = spec.get("isHero", False)
    is_2d = (spec.get("style") or "").lower() in ("2d", "tossface")
    style = TOSSFACE_2D_STYLE if is_2d else (spec.get("style") or DEFAULT_3D_STYLE)

    # 프롬프트 구성
    if is_hero:
        mode_instructions = (
            "IMPORTANT: Keep the background. "
            "All graphic elements MUST be on the RIGHT SIDE. "
            "The LEFT 60% must be empty for text overlay. "
            "NO MORE THAN 2-3 simple objects total."
        )
    else:
        mode_instructions = "IMPORTANT: transparent background (PNG with alpha)."

    full_prompt = f"{prompt}. Style: {style}. {mode_instructions} High quality."

    # 레퍼런스 이미지
    parts = []
    for ref_path in _find_reference_images(prompt, is_2d):
        try:
            with open(ref_path, "rb") as f:
                ref_b64 = base64.b64encode(f.read()).decode()
            parts.append({"inlineData": {"mimeType": "image/png", "data": ref_b64}})
        except Exception:
            pass

    parts.append({"text": full_prompt})

    # Gemini API 호출
    try:
        resp = requests.post(
            f"{GEMINI_ENDPOINT}?key={api_key}",
            json={
                "contents": [{"parts": parts}],
                "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
            },
            timeout=180,
        )
        data = resp.json()

        if "candidates" not in data:
            return {"nodeName": node_name, "error": f"Gemini 응답 없음: {str(data)[:200]}"}

        # 이미지 추출
        img_b64 = None
        for part in data["candidates"][0]["content"]["parts"]:
            if "inlineData" in part:
                img_b64 = part["inlineData"]["data"]
                break

        if not img_b64:
            return {"nodeName": node_name, "error": "응답에 이미지 없음"}

        raw_data = base64.b64decode(img_b64)
        safe_name = node_name.replace(" ", "_").replace("/", "_")
        raw_path = os.path.join(output_dir, f"{safe_name}_raw.png")
        with open(raw_path, "wb") as f:
            f.write(raw_data)

        if is_hero:
            # 히어로: 배경 유지, 리사이즈만
            final_path = os.path.join(output_dir, f"{safe_name}.png")
            from PIL import Image as PILImage
            img = PILImage.open(io.BytesIO(raw_data))
            img.save(final_path)
            return {"nodeName": node_name, "imagePath": final_path, "isHero": True}
        else:
            # 아이콘: rembg 배경 제거 + 정사각형 크롭
            from rembg import remove
            from PIL import Image as PILImage
            input_img = PILImage.open(io.BytesIO(raw_data))
            output_img = remove(input_img)

            # 정사각형 중앙 크롭
            w, h = output_img.size
            s = min(w, h)
            left = (w - s) // 2
            top = (h - s) // 2
            output_img = output_img.crop((left, top, left + s, top + s))
            output_img = output_img.resize((120, 120), PILImage.LANCZOS)

            final_path = os.path.join(output_dir, f"{safe_name}.png")
            output_img.save(final_path)
            return {"nodeName": node_name, "imagePath": final_path, "isHero": False}

    except Exception as e:
        return {"nodeName": node_name, "error": str(e)}


def _pre_generate_images_parallel(specs: list) -> list:
    """Blueprint의 imageGen 스펙들을 병렬로 사전 생성.

    빌드 전에 호출되어 빌드와 동시에 실행됨.
    nodeId 없이 이미지만 생성하여 로컬 파일로 저장.

    Returns: [{"nodeName": str, "imagePath": str, "isHero": bool}, ...]
    """
    api_key = _get_gemini_api_key()
    if not api_key:
        print("  ⚠️ Gemini API 키 미설정 — 이미지 사전 생성 건너뜀")
        return []

    output_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "generated")
    os.makedirs(output_dir, exist_ok=True)

    results = []
    start = time.time()

    # 최대 3개 병렬 (Gemini API rate limit 고려)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_pre_generate_single, spec, api_key, output_dir): spec
            for spec in specs
        }
        for future in as_completed(futures):
            spec = futures[future]
            result = future.result()
            if "error" in result:
                print(f"  ❌ {result['nodeName']}: {result['error'][:100]}")
            else:
                print(f"  ✅ {result['nodeName']}: {result['imagePath']}")
            results.append(result)

    elapsed = time.time() - start
    ok = sum(1 for r in results if "imagePath" in r)
    fail = sum(1 for r in results if "error" in r)
    print(f"  이미지 사전 생성 — {ok} 성공, {fail} 실패 ({elapsed:.1f}s)")
    return results


def _apply_pre_generated_images(pre_results: list, node_map: dict):
    """사전 생성된 이미지를 nodeMap 기반으로 Figma에 적용.

    pre_results: _pre_generate_images_parallel의 결과
    node_map: batch_build_screen이 반환한 {name: nodeId} 매핑
    """
    success = 0
    fail = 0

    for result in pre_results:
        if "error" in result:
            continue

        node_name = result["nodeName"]
        image_path = result["imagePath"]
        is_hero = result.get("isHero", False)
        node_id = node_map.get(node_name)

        if not node_id:
            print(f"  ⚠️ '{node_name}' nodeMap에 없음 — 적용 건너뜀")
            fail += 1
            continue

        try:
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()

            scale_mode = "FILL" if is_hero else "FIT"
            content = call_tool("set_image_fill", {
                "nodeId": node_id,
                "imageData": img_b64,
                "scaleMode": scale_mode,
            })
            result_parsed = parse_content(content)
            if result_parsed.get("json"):
                print(f"  ✅ {node_name} → {node_id} ({scale_mode})")
                success += 1
            else:
                print(f"  ❌ {node_name} 적용 실패: {result_parsed.get('texts', [])}")
                fail += 1
        except Exception as e:
            print(f"  ❌ {node_name} 에러: {e}")
            fail += 1

    print(f"  이미지 적용 — {success} 성공, {fail} 실패")


def _collect_tree(node_id: str, depth: int = 0, max_depth: int = 6) -> dict:
    """노드 트리를 재귀적으로 수집 (최대 depth 6).

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
                child_node = _collect_tree(str(child_id), depth + 1, max_depth)
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
            # HORIZONTAL 부모 안의 Banner Card (캐로셀)
            if parent_layout_mode == "HORIZONTAL" and "banner" in name_lower:
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

    # FAB 배치
    fab_y = content_bottom + 16
    if fab:
        try:
            call_tool("set_layout_positioning", {
                "nodeId": fab.get("id"),
                "layoutPositioning": "ABSOLUTE"
            })
        except Exception as e:
            print(f"  FAB ABSOLUTE 설정 실패 (무시): {e}")
        # FAB 크기 복원 (pill 형태 120×44) — FILL 변환으로 width가 늘어났을 수 있음
        fab_width = fab.get("width", 120)
        if fab_width > 200:  # FILL로 늘어난 경우
            try:
                call_tool("set_layout_sizing", {
                    "nodeId": fab.get("id"),
                    "horizontal": "HUG"
                })
                print(f"  FAB 크기 복원: width {fab_width} → HUG")
            except Exception as e:
                print(f"  FAB 크기 복원 실패: {e}")
        try:
            call_tool("move_node", {
                "nodeId": fab.get("id"),
                "x": 253,
                "y": fab_y
            })
            print(f"  FAB 배치: y={fab_y}, x=253")
            result["fab_y"] = fab_y
        except Exception as e:
            print(f"  FAB 이동 실패: {e}")

    # Tab Bar 배치
    if fab:
        tab_y = fab_y + 44 + 16
    else:
        tab_y = content_bottom + 24

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

    # 루트 프레임 높이 조정
    if tab_bar:
        root_height = tab_y + 73
    elif fab:
        root_height = fab_y + 44 + 24
    else:
        root_height = content_bottom + 24

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


def cmd_post_fix(root_node_id: str, pre_computed_layout: dict = None):
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

    elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"POST-FIX 완료 — {elapsed:.1f}s")
    print(f"  FILL 수정: {fill_fixes}건")
    print(f"  Tab Bar/Stroke 수정: {tab_fixes}건")
    print(f"  텍스트 수정: {text_fixes}건")
    print(f"  루트 높이: {layout_result['root_height']}")
    print(f"{'='*50}\n")


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
        "Hero": {"banners": [{"fill": "...", "imagePrompt": "...", ...}]}
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
    - Hero: banners[{fill, tag, title, subText, desc, imagePrompt}]
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
                    if banner_vars.get("imagePrompt"):
                        card["imageGen"] = {
                            "prompt": banner_vars["imagePrompt"],
                            "isHero": True
                        }
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
    elif cmd == "bind-text-styles":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py bind-text-styles <styles.json>")
            sys.exit(1)
        cmd_bind_text_styles(sys.argv[2])
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
