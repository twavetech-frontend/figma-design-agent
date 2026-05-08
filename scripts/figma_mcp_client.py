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

    # 3a. Blueprint lint (registry 기반 룰)
    python3 scripts/figma_mcp_client.py lint blueprint.json

    # 3b. 빌드 후 verify (실제 Figma 트리 vs 룰)
    python3 scripts/figma_mcp_client.py verify <rootNodeId> [blueprint.json]

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

# Make sibling design_rules package importable (scripts/ on path)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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


# NOTE: validate_blueprint was removed 2026-05-04 — all checks ported into
# scripts/design_rules/ (S00 schema, R10 layout, R11 typography, R12 imageGen,
# R13 autoLayout, R20 semantic-only, R21 bg-hierarchy, R22 brand-text,
# R23 ds-first, R24 status-bar, R25 tab-bar-stroke). Use REGISTRY.run_lint().


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


_BUILT_BLUEPRINTS_LEDGER = os.path.join(os.path.dirname(__file__), ".built_blueprints.json")


def _ledger_load() -> dict:
    if not os.path.exists(_BUILT_BLUEPRINTS_LEDGER):
        return {}
    try:
        with open(_BUILT_BLUEPRINTS_LEDGER) as f:
            return json.load(f)
    except Exception:
        return {}


def _ledger_save(d: dict):
    try:
        with open(_BUILT_BLUEPRINTS_LEDGER, "w") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass


def _ledger_check_reuse(blueprint_file: str) -> Optional[str]:
    """Return error message if blueprint_file path was already used for a successful build."""
    abs_path = os.path.abspath(blueprint_file)
    ledger = _ledger_load()
    entry = ledger.get(abs_path)
    if entry:
        return (f"BLUEPRINT REUSE BLOCKED: '{abs_path}' was already used for build "
                f"on {entry.get('builtAt','?')} (rootId={entry.get('rootId','?')}). "
                f"Per project rule: blueprints must be authored fresh for every build. "
                f"Write a new file with a different name.")
    return None


def _ledger_record(blueprint_file: str, root_id: str):
    abs_path = os.path.abspath(blueprint_file)
    ledger = _ledger_load()
    ledger[abs_path] = {
        "builtAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rootId": root_id,
    }
    _ledger_save(ledger)


# ── Canonical in-file references (D — pre-build hook) ──────────────────
# Maps blueprint name keyword → user-approved canonical frame in same Figma file.
# When a build matches a known screen, the agent + lint are forced to align
# with the actual user-polished design rather than stale archived blueprints.
CANONICAL_IN_FILE_REFS = {
    "imin_home": {
        "fileKey": "SsgiLsXVMkf0wv8OhRGwks",
        "nodeId": "17037:3628",
        "name": "imin_home_v17",
        "rule": "R31-imin-home-canonical",
        "template": "blueprint_templates.json → sections.RecommendSectionV17",
        "note": (
            "User-approved canonical home design. Recommend Section uses "
            "bg-secondary card + 161×68 pill progress widget + 3 stepper "
            "pills + full-width '스테이지 참여하기' brand CTA + "
            "이율순·금액순·기간순 view-all hint. Brand-purple recommend "
            "containers from earlier v12 builds are deprecated."
        ),
    },
}


def _inject_canonical_reference(blueprint: dict) -> dict:
    """If blueprint name matches a known canonical screen, attach a
    `_canonicalReference` marker so downstream rules (R31 etc.) and the
    agent are aware of the in-file authoritative design. This is a
    decision-aid — actual structural enforcement still goes through R*
    design rules in design_rules/.
    """
    name = (blueprint.get("rootName") or blueprint.get("name") or "").lower()
    for key, ref in CANONICAL_IN_FILE_REFS.items():
        if key in name:
            blueprint["_canonicalReference"] = ref
            print(f"\n[canonical-ref] '{key}' detected → {ref['name']} ({ref['nodeId']})")
            print(f"  Template: {ref['template']}")
            print(f"  Enforced by: {ref['rule']}")
            print(f"  Note: {ref['note'][:120]}...")

            # Also auto-augment references[] so S20 sees an in-file ref entry
            refs = blueprint.setdefault("references", [])
            already = any(
                isinstance(r, dict) and r.get("ref", "").startswith(f"figma://{ref['fileKey']}")
                for r in refs
            )
            if not already:
                in_file_ref = f"figma://{ref['fileKey']}/{ref['nodeId']}"
                refs.insert(0, {
                    "section": "(canonical full-screen)",
                    "ref": in_file_ref,
                    "app": "imin (user-modified)",
                    "extract": ref["note"],
                    # Auto-fill _searchLog so S21 doesn't ERROR on this
                    # auto-injected entry (it is by definition the most
                    # authoritative reference — the user's own design)
                    "_searchLog": {
                        "queries": ["canonical in-file design", key],
                        "candidates": [
                            in_file_ref,
                            f"blueprint_templates.json sections.{ref.get('template', '?')}",
                            "fallback: uibowl/toss/* + uibowl/kakaopay/*",
                        ],
                        "chosen": in_file_ref,
                        "copyNotes": (f"Auto-attached canonical reference: "
                                      f"{ref['name']} (node {ref['nodeId']}) "
                                      f"in file {ref['fileKey']}. Template: "
                                      f"{ref.get('template', '?')}. "
                                      f"Enforced by: {ref.get('rule', '?')}. "
                                      f"This entry is auto-injected by "
                                      f"_inject_canonical_reference for "
                                      f"any blueprint matching '{key}'."),
                    },
                })
                print(f"  → auto-inserted as references[0]")
            break
    return blueprint


def cmd_build(blueprint_file: str):
    """Build a screen from a blueprint JSON file.

    Supports $token() references in color fields. Before building,
    all $token(name) values are resolved to RGBA using TOKEN_MAP.json.

    Project rules enforced:
      • Blueprint files cannot be reused — once a file path is built, ledger
        blocks subsequent builds from the same path.
      • On successful build the blueprint file is auto-deleted to prevent
        reuse and force fresh authoring next time.

    Example blueprint color:
        "fill": "$token(bg-brand-solid)"
        "fontColor": "$token(fg-brand-primary)"
    These are resolved to {"r": ..., "g": ..., "b": ..., "a": ...} at build time.
    """
    ensure_session()

    # Reuse-guard: block known-built paths
    reuse_err = _ledger_check_reuse(blueprint_file)
    if reuse_err and "--force" not in sys.argv:
        print(f"\n{'='*50}\n{reuse_err}\n{'='*50}\n")
        return

    with open(blueprint_file) as f:
        blueprint = json.load(f)

    # Step 0: D — auto-inject canonical in-file reference for known screens
    blueprint = _inject_canonical_reference(blueprint)

    # Step 1: L1 schema + L2 lint via registry hard-gate
    from design_rules import REGISTRY as _RULES, Severity as _Sev
    blueprint = _RULES.run_inject(blueprint)  # L3 — Status Bar etc.
    violations = _RULES.run_lint(blueprint)
    errors = [v for v in violations if v.severity == _Sev.ERROR]
    warns  = [v for v in violations if v.severity == _Sev.WARN]
    infos  = [v for v in violations if v.severity == _Sev.INFO]
    if errors:
        print(f"\n{'='*50}")
        print(f"LINT FAILED — {len(errors)} error(s), {len(warns)} warning(s):")
        for v in violations:
            if v.severity in (_Sev.ERROR, _Sev.WARN):
                print(f"  {v.format()}")
        print(f"{'='*50}\n")
        print("Fix errors before building. Use --force to skip lint.")
        if "--force" not in sys.argv:
            return
    elif warns or infos:
        print(f"Lint: {len(warns)} warning(s), {len(infos)} info")
        for v in warns[:20]:
            print(f"  {v.format()}")
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
    pexels_specs_raw = []

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
        # New: imageQuery for real-photo via Pexels
        image_query = node.get("imageQuery")
        if image_query:
            pexels_specs_raw.append({
                "nodeName": node.get("name", ""),
                "query": image_query if isinstance(image_query, str) else image_query.get("q", ""),
                "orientation": (image_query.get("orientation") if isinstance(image_query, dict) else None),
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

    # Step B.2: Pexels 사진 검색을 백그라운드 스레드로 시작
    pexels_future = None
    if pexels_specs_raw:
        print(f"\n📸 Pexels 사진 검색 시작 ({len(pexels_specs_raw)}건)")
        pexels_executor = ThreadPoolExecutor(max_workers=4)
        pexels_future = pexels_executor.submit(_fetch_pexels_images_parallel, pexels_specs_raw)

    # Step C: 빌드 실행 (이미지 생성과 동시)
    start = time.time()
    # Clone & Bind 파이프라인: sanitizer가 이미 blueprint를 안전화했으므로
    # TS 레이어의 enhanceBlueprint(자동 enforce)를 스킵 — star-01 fallback 우회 (S2.5)
    skip_enhance = os.environ.get("FIGMA_MCP_SKIP_ENHANCE", "1") != "0"

    # Sanitize letterSpacing/lineHeight: plugin's batch_build_screen accepts only
    # numbers (sets unit=PIXELS); object form {value, unit:PERCENT} fails Figma
    # schema validation ("Expected number, received object"). Flatten in-place
    # right before send (2026-05-05 regression fix).
    def _flatten_typo(n):
        if not isinstance(n, dict): return
        for k in ("letterSpacing", "lineHeight"):
            v = n.get(k)
            if isinstance(v, dict) and "value" in v:
                unit = (v.get("unit") or "PIXELS").upper()
                val = v.get("value", 0)
                if unit == "PERCENT":
                    fs = n.get("fontSize")
                    n[k] = (float(fs) * float(val) / 100.0) if isinstance(fs, (int, float)) else 0
                else:
                    n[k] = float(val)
        for c in (n.get("children") or []):
            _flatten_typo(c)
    _flatten_typo(blueprint)

    # Guard against TS-layer enhanceBlueprint mis-detecting numeric/Korean
    # texts as emoji-only and converting them to star-01 placeholders. The
    # bug is in src/main/figma-mcp-embedded.ts isEmojiOnlyText (\p{Emoji}
    # matches digits 0-9, '#', '*'). Even with skipEnhance=true, the MCP
    # server may not reload after a build, so guard client-side: prefix any
    # purely-non-emoji text with U+2060 WORD JOINER (invisible, doesn't
    # affect rendering). The emoji-strip regex won't match this so the
    # text is no longer "emoji-only".
    import re as _re_guard
    _SAFE_TEXT_RE = _re_guard.compile(
        r'^[\sA-Za-z0-9가-힯ㄱ-ㅎㅏ-ㅣ.,!?+\-*/#:;()%원만개월뒤내년일주차회·]+$'
    )
    _WORD_JOINER = "⁠"
    def _guard_numeric_text(n):
        if not isinstance(n, dict): return
        if (n.get("type") or "").lower() == "text":
            t = n.get("text") or n.get("characters")
            if isinstance(t, str) and t.strip() and _SAFE_TEXT_RE.match(t.strip()):
                if not t.startswith(_WORD_JOINER):
                    if "text" in n:
                        n["text"] = _WORD_JOINER + t
                    if "characters" in n:
                        n["characters"] = _WORD_JOINER + t
        for c in (n.get("children") or []):
            _guard_numeric_text(c)
    _guard_numeric_text(blueprint)

    content = call_tool("batch_build_screen", {"blueprint": blueprint, "skipEnhance": skip_enhance})
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

    # Step E.0: Instance properties / Label text overrides (Rule 2 from invariants 2026-05-04)
    # Pill / Badge / Button DS 컴포넌트는 텍스트 property가 없어서
    # `instanceProperties: { Label: "..." }`를 지정해도 적용되지 않음. 빌드 후
    # 인스턴스 안 첫 TEXT 자식을 찾아 set_text_content로 직접 갱신.
    # 또한 Boolean/VARIANT/INSTANCE_SWAP 속성은 set_instance_properties로 전달.
    if root_id and node_map:
        print("\n🏷️  Instance properties / Label 자동 override 중...")
        applied = _apply_instance_overrides(blueprint, node_map)
        if applied:
            print(f"  → {applied}건 적용")

    # Step E: post-fix (2회 실행 — 1회차: FILL 수정 + 배치, 2회차: 레이아웃 안정화 후 최종 배치)
    if root_id:
        print("\n🔧 자동 후처리 실행 중...")
        sim_layout = sim_result.get("layout") if sim_result else None
        cmd_post_fix(root_id, pre_computed_layout=sim_layout)
        print("\n🔧 후처리 2회차 (레이아웃 안정화 후 최종 배치)...")
        cmd_post_fix(root_id)

        # Step E.LAST: blueprint layoutMode integrity enforcement.
        if node_map:
            print("\n🛡️  Blueprint layoutMode 무결성 검증 중...")
            layout_fixes = _enforce_blueprint_layout(blueprint, node_map)
            print(f"  → {layout_fixes}건 layout 복원")

            # Step E.LAST2: re-apply instance text overrides after post-fix.
            # post-fix's binding sweep + layout enforcement can silently
            # reset some instance text overrides (observed: pill 10만원/13개월
            # reverted to master "Label" for some pills). Run again as
            # final-pass to guarantee text persists.
            print("\n🏷️  Instance text 재적용 (post-fix 후 final pass)...")
            final_applied = _apply_instance_overrides(blueprint, node_map)
            print(f"  → {final_applied}건 재적용")
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

    # Step F.2: Pexels 사진 검색 완료 대기 + Figma 적용
    if pexels_future and node_map is not None:
        print("\n⏳ Pexels 사진 다운로드 완료 대기 중...")
        pexels_results = pexels_future.result()
        pexels_executor.shutdown(wait=False)
        ok = [r for r in pexels_results if "imagePath" in r]
        if ok:
            print(f"\n🖼️  Pexels 사진 Figma 적용 ({len(ok)}건)...")
            _apply_pre_generated_images(pexels_results, node_map)
    elif pexels_future:
        pexels_future.cancel()
        pexels_executor.shutdown(wait=False)
        print("\n⚠️  nodeMap이 None — Pexels 적용 불가")

    # Step G: NavBar 로고 인스턴스 교체
    if node_map and "Logo Placeholder" in node_map:
        print("\n🔲 NavBar 로고 교체 중...")
        try:
            placeholder_id = node_map["Logo Placeholder"]
            navbar_id = node_map.get("NavBar")
            if navbar_id:
                # 로고 컴포넌트 인스턴스 생성
                logo_content = call_tool("create_component_instance", {
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

    total_elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"전체 완료: {total_elapsed:.1f}s (빌드 {build_elapsed:.1f}s + 후처리 + 이미지)")
    print(f"{'='*50}")

    # Project rule: blueprint files must be authored fresh per build.
    # Record + auto-delete the source file so reuse is physically prevented.
    if root_id:
        try:
            _ledger_record(blueprint_file, root_id)
            if os.path.exists(blueprint_file) and "--keep-blueprint" not in sys.argv:
                os.unlink(blueprint_file)
                print(f"\n🗑️  Blueprint auto-deleted: {blueprint_file}")
                print("    (project rule: write a fresh blueprint for each build)")
        except Exception as e:
            print(f"\n⚠️  Blueprint cleanup failed: {e}")


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
    explicit_2d = (spec.get("style") or "").lower() in ("2d", "tossface")
    # 소형 아이콘(≤32px)은 자동으로 2D — style 누락해도 안전
    size = max(spec.get("width") or 120, spec.get("height") or 120)
    is_2d = explicit_2d or (not is_hero and size <= 32)
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


_WIKIMEDIA_UA = "figma-design-agent/1.0 (https://github.com/twavetech-frontend/figma-design-agent)"


def _fetch_pexels_single(spec: dict, output_dir: str) -> dict:
    """Search Wikimedia Commons for a single query, download first matching photo.

    Note: function name kept as `_fetch_pexels_*` for compat — actually uses
    Wikimedia Commons API since Pexels requires auth (401) and Unsplash blocks
    scraping. Wikimedia is free, no auth, just needs proper User-Agent.

    spec: {nodeName, query}
    Returns: {nodeName, imagePath, isHero=True} or {nodeName, error}
    """
    import urllib.request, urllib.parse
    name = spec.get("nodeName", "")
    query = spec.get("query", "")
    if not query:
        return {"nodeName": name, "error": "empty query"}
    api_url = (
        "https://commons.wikimedia.org/w/api.php?"
        f"action=query&format=json&generator=search&"
        f"gsrsearch={urllib.parse.quote(query)}+filetype:bitmap&"
        f"gsrnamespace=6&gsrlimit=5&"
        f"prop=imageinfo&iiprop=url&iiurlwidth=600"
    )
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": _WIKIMEDIA_UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        pages = (data.get("query", {}) or {}).get("pages", {}) or {}
        # Sort by index to get top match
        sorted_pages = sorted(pages.values(),
                              key=lambda p: p.get("index", 999))
        image_url = None
        for p in sorted_pages:
            infos = p.get("imageinfo") or []
            if not infos: continue
            url = infos[0].get("thumburl") or infos[0].get("url")
            if url:
                image_url = url
                break
        if not image_url:
            return {"nodeName": name, "error": f"no results for '{query}'"}
        safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
        ext = ".jpg"
        if ".png" in image_url.lower(): ext = ".png"
        local = os.path.join(output_dir, f"wm_{safe}{ext}")
        req2 = urllib.request.Request(image_url, headers={"User-Agent": _WIKIMEDIA_UA})
        with urllib.request.urlopen(req2, timeout=30) as r:
            with open(local, "wb") as f:
                f.write(r.read())
        return {"nodeName": name, "imagePath": local, "isHero": True}
    except Exception as e:
        return {"nodeName": name, "error": str(e)}


def _fetch_pexels_images_parallel(specs: list) -> list:
    """Fetch all Pexels image queries in parallel."""
    output_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "pexels")
    os.makedirs(output_dir, exist_ok=True)
    results = []
    start = time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(_fetch_pexels_single, spec, output_dir): spec
                   for spec in specs}
        for future in as_completed(futures):
            res = future.result()
            if "error" in res:
                print(f"  ❌ Pexels {res['nodeName']}: {res['error'][:80]}")
            else:
                print(f"  ✅ Pexels {res['nodeName']}: {os.path.basename(res['imagePath'])}")
            results.append(res)
    elapsed = time.time() - start
    ok = sum(1 for r in results if "imagePath" in r)
    print(f"  Pexels — {ok}/{len(specs)} ({elapsed:.1f}s)")
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
                     "Nav Right", "Vector", "Icon", "Chevron", "Dot",
                     # Slider 컴포넌트 (규칙 #24): Fill/Thumb은 progress 비율 × track_width로
                     # 계산된 FIXED width여야 함. FILL 강제되면 Thumb이 Track 끝으로 밀려
                     # progress 표시 불가. "slider"로 시작하는 모든 이름 skip (Slider Fill/
                     # Slider Thumb/Slider Track/Slider Bar 등).
                     "slider")
    # 단어 경계 매칭용 정규식 — substring 매칭("tag" ⊂ "stage") 버그 방지
    _SKIP_RE = re.compile(
        r'\b(?:' + '|'.join(re.escape(kw.lower()) for kw in SKIP_KEYWORDS) + r')\b'
    )
    # FAB/Tab Bar는 ABSOLUTE로 배치되므로 FILL 변환하면 안 됨
    ABSOLUTE_NAME_KEYWORDS = ("fab", "tab bar", "tabbar", "bottom nav", "bottomnav")
    fix_count = 0

    def _walk(node: dict, parent_layout_mode: str = "",
              parent_align: str = "", parent_name: str = "",
              is_last_child: bool = False):
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
            # 가로 스크롤 섹션 카드 보호 (VS32): 부모 이름에 "scroll"/"carousel" 포함 +
            # 자식이 FIXED 명시된 경우만 skip — 일반 HORIZONTAL 섹션(Summary Grid,
            # Onboarding Alert 등)에는 영향 없음
            parent_lower = (parent_name or "").lower()
            if (parent_layout_mode == "HORIZONTAL"
                    and sizing_h == "FIXED"
                    and ("scroll" in parent_lower or "carousel" in parent_lower)):
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
        current_name = node.get("name") or ""
        children = node.get("_children_full", [])
        for i, child in enumerate(children):
            _walk(child, current_layout, current_align, current_name,
                  is_last_child=(i == len(children) - 1))

    _walk(tree)

    # ★ 안전장치: 루트부터 재귀적으로 FRAME 자식을 FILL 강제 (FAB/Tab Bar 제외)
    # _walk에서 데이터 누락이나 조건 스킵으로 빠져나갈 수 있으므로,
    # VERTICAL 부모의 모든 FRAME 자식을 재귀적으로 검증/수정
    ABSOLUTE_NAME_KEYWORDS_LOWER = ("fab", "tab bar", "tabbar", "bottom nav", "bottomnav")

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
        if "tab bar" in name or "tabbar" in name or "bottom nav" in name or "bottomnav" in name:
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
                if c_lp == "ABSOLUTE" or "fab" in c_name or "tab bar" in c_name or "tab_bar" in c_name or "bottom nav" in c_name or "bottomnav" in c_name:
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
    """Tab Bar / Bottom Nav 내부 아이템을 FILL로 통일하고 label 텍스트를 CENTER 정렬.

    감지 키워드: "tab bar", "tabbar", "bottom nav", "bottomnav"
    처리:
      1. Tab item FRAME → layoutSizingHorizontal: FILL (폭 균등 분배)
      2. Tab item 내부 TEXT (label) → textAlignHorizontal: CENTER (아이콘 하단 중앙 정렬)
         ※ FILL 텍스트는 alignment가 LEFT면 왼쪽으로 밀려나 아이콘과 어긋남 (CLAUDE.md 규칙 7)
    """
    NAV_KEYWORDS = ("tab bar", "tabbar", "bottom nav", "bottomnav")
    fix_count = 0
    children = tree.get("_children_full", [])

    for child in children:
        name_lower = (child.get("name") or "").lower()

        if any(kw in name_lower for kw in NAV_KEYWORDS):
            tab_items = child.get("_children_full", [])
            for item in tab_items:
                item_type = (item.get("type") or "").upper()
                item_sizing = item.get("layoutSizingHorizontal", "")
                item_id = item.get("id")
                if item_type == "FRAME" and item_sizing != "FILL":
                    try:
                        call_tool("set_layout_sizing", {
                            "nodeId": item_id,
                            "horizontal": "FILL"
                        })
                        fix_count += 1
                        print(f"  Tab item FILL: {item.get('name')} ({item_id})")
                    except Exception as e:
                        print(f"  Tab item FILL 실패: {item.get('name')}: {e}")

                # Tab item 내부 TEXT(label)를 CENTER 정렬로 강제
                for sub in item.get("_children_full", []):
                    sub_type = (sub.get("type") or "").upper()
                    sub_id = sub.get("id")
                    if sub_type == "TEXT" and sub_id:
                        align = sub.get("textAlignHorizontal")
                        if align != "CENTER":
                            try:
                                call_tool("set_text_align", {
                                    "nodeId": sub_id,
                                    "textAlignHorizontal": "CENTER"
                                })
                                fix_count += 1
                                print(f"  Tab label CENTER: {sub.get('name')} ({sub_id}) [{align} → CENTER]")
                            except Exception as e:
                                print(f"  Tab label CENTER 실패: {sub.get('name')}: {e}")

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


def _fix_stroke_alignment(tree: dict) -> int:
    """strokeAlign INSIDE 강제 — OUTSIDE/CENTER 전면 금지.

    배경: OUTSIDE/CENTER stroke는 부모 프레임이 clipsContent=True이면 잘려보인다.
    실전 사례(2026-04-22): Schedule Today Card(strokeAlign=OUTSIDE, 2px)가
    Day Card Row(clipsContent=True)에 의해 상단 stroke가 잘림.

    정책: stroke가 있는 모든 노드를 강제로 strokeAlign=INSIDE로 재설정.
      - strokeAlign 정보를 plugin이 리턴 안 할 수 있어 "무조건 INSIDE로 set"이 안전
      - 이미 INSIDE인 노드에 재설정해도 무해 (idempotent)
      - 시각적 크기(bbox) 변동 없음, 부모 clip과 무관하게 항상 렌더
    """
    fix_count = 0

    # Frame-like 타입만 대상 — Vector/path 노드의 CENTER stroke는 path 렌더 기본값이라 건드리면 안 됨
    FRAME_TYPES = {"FRAME", "RECTANGLE", "COMPONENT", "COMPONENT_SET", "INSTANCE"}

    def _walk(node: dict):
        nonlocal fix_count
        node_id = node.get("id")
        node_name = node.get("name", "")
        node_type = (node.get("type") or "").upper()
        strokes = node.get("strokes") or []
        stroke_weight = node.get("strokeWeight") or 0
        stroke_align = node.get("strokeAlign")  # plugin이 미제공 시 None

        # stroke가 visible=True이고 weight>0인 노드만 대상
        visible_strokes = [s for s in strokes if s.get("visible", True)]
        has_stroke = bool(visible_strokes) and stroke_weight > 0

        # Frame-like이면서, 이미 INSIDE로 확인되지 않은 노드만 대상
        is_frame_like = node_type in FRAME_TYPES
        if has_stroke and is_frame_like and stroke_align != "INSIDE" and node_id:
            try:
                first = visible_strokes[0]
                color = first.get("color", {})
                r = color.get("r", 0)
                g = color.get("g", 0)
                b = color.get("b", 0)
                a = first.get("opacity", color.get("a", 1))
                call_tool("set_stroke_color", {
                    "nodeId": node_id,
                    "r": r, "g": g, "b": b, "a": a,
                    "strokeWeight": stroke_weight,
                    "strokeAlign": "INSIDE",
                })
                fix_count += 1
                align_note = f"{stroke_align or 'unknown'} → INSIDE"
                print(f"  stroke INSIDE 강제: {node_name} ({node_id}) [{stroke_weight}px, {align_note}]")
            except Exception as e:
                print(f"  stroke 수정 실패: {node_name} ({node_id}): {e}")

        for child in node.get("_children_full", []):
            _walk(child)

    _walk(tree)
    return fix_count


def _check_horizontal_scroll_peek(tree: dict) -> int:
    """가로 스크롤 섹션의 카드 너비가 뷰포트 40% 이하인지 검증 (VS32).

    가로 스크롤 섹션 감지 기준 (모두 충족):
      1. HORIZONTAL autoLayout + clipsContent:true
      2. 자식 총 너비(카드 합 + gap) > 부모 width  → 실제로 스크롤 의도됐음
      3. 자식이 2개 이상
    위 조건을 만족하는 섹션에서 최대 카드 width > 165px이면 경고.

    예외:
      - 히어로 배너 캐로셀 (name에 "banner" / "carousel" / "hero" 포함)
      - Bottom Nav, Tab Bar, Day Row 등 고정 배치 (자식 총 너비가 부모 이하면 스크롤 아님)
    """
    VIEWPORT_W = 393
    MAX_CARD_W = 165   # 40% threshold
    warn_count = 0

    def _walk(node: dict):
        nonlocal warn_count
        node_type = (node.get("type") or "").upper()
        node_name = (node.get("name") or "").lower()
        layout_mode = node.get("layoutMode")
        clips = node.get("clipsContent", False)
        parent_w = node.get("width") or 0
        item_spacing = node.get("itemSpacing") or 0
        padding_l = node.get("paddingLeft") or 0
        padding_r = node.get("paddingRight") or 0

        is_banner = "banner" in node_name or "carousel" in node_name or "hero" in node_name
        # 가로 스크롤 섹션은 이름에 "scroll" 포함 강제 (Stage Card Scroll, Product Scroll 등)
        # → MissedAlert, Summary Grid, Days Row, Bottom Nav 등 오탐 제거
        is_scroll_section = "scroll" in node_name

        if (node_type in ("FRAME", "COMPONENT", "INSTANCE")
                and layout_mode == "HORIZONTAL"
                and clips
                and is_scroll_section
                and not is_banner
                and parent_w > 0):
            children = node.get("_children_full", [])
            frame_children = [c for c in children
                              if (c.get("type") or "").upper() in ("FRAME", "COMPONENT", "INSTANCE", "RECTANGLE")
                              and (c.get("width") or 0) > 0]
            if len(frame_children) >= 2:
                widths = [c.get("width") for c in frame_children]
                # 가로 스크롤 섹션 조건:
                #   (1) 모든 자식이 FIXED 너비 (FILL이면 grid 분할이지 스크롤 아님)
                #   (2) 자식 총 너비 > 부모 width (실제 스크롤 필요)
                all_fixed = all(
                    c.get("layoutSizingHorizontal") == "FIXED"
                    for c in frame_children
                )
                total_content_w = sum(widths) + item_spacing * (len(widths) - 1) + padding_l + padding_r
                is_scrollable = all_fixed and total_content_w > parent_w + 8

                if is_scrollable:
                    max_w = max(widths)
                    if max_w > MAX_CARD_W:
                        pct = int(max_w / VIEWPORT_W * 100)
                        print(f"  ⚠️ peek 위반: '{node.get('name')}' 카드 최대 width {round(max_w)}px ({pct}% > 40%) — 3번째 카드 peek 불가")
                        print(f"     권장: 카드 width ≤ {MAX_CARD_W}px (뷰포트 40%) — VS32 참조")
                        warn_count += 1

        for child in node.get("_children_full", []):
            _walk(child)

    _walk(tree)
    return warn_count


def _match_status_bar_bg_to_nav(tree: dict) -> bool:
    """Status Bar(children[0])의 fill을 NavBar(children[1])의 fill과 일치시킴.
    CLAUDE.md 규칙 #25 — 상단 시스템 UI와 앱 헤더의 시각적 연결.

    NavBar fill이 변수에 바인딩돼 있으면 Status Bar에도 같은 변수를 바인딩
    (raw rgba만 복사하면 Step 9 token-binding sweep이 근사 매칭으로 다른
    토큰을 다시 붙여 색이 어긋남 — 2026-05-05 R30 패치).

    반환: True면 매칭 적용됨, False면 skip (대상 없음 or fill 미지정).
    """
    children = tree.get("_children_full", [])
    if len(children) < 2:
        return False
    sb = children[0]
    nav = children[1]
    sb_id = sb.get("id")
    sb_name = (sb.get("name") or "").lower()
    if "status" not in sb_name or not sb_id:
        return False
    # NavBar의 첫 SOLID fill 추출
    nav_fills = nav.get("fills") or []
    solid = None
    for f in nav_fills:
        if isinstance(f, dict) and f.get("type") == "SOLID":
            solid = f
            break
    if not solid:
        return False
    color = solid.get("color") or {}
    r = color.get("r")
    g = color.get("g")
    b = color.get("b")
    if r is None or g is None or b is None:
        return False
    opacity = solid.get("opacity", 1)

    # ── 1단계: raw rgba로 fill 슬롯 보장 (binding은 fills[0] 존재 전제) ──
    try:
        call_tool("set_fill_color", {
            "nodeId": sb_id,
            "r": r, "g": g, "b": b, "a": opacity,
        })
    except Exception as e:
        print(f"  ⚠️ Status Bar bg 매칭 실패: {e}")
        return False

    # ── 2단계: NavBar fill이 변수 바인딩이면 같은 변수로 Status Bar도 바인딩 ──
    bv = solid.get("boundVariables") or {}
    var_ref = bv.get("color") if isinstance(bv, dict) else None
    var_id = var_ref.get("id") if isinstance(var_ref, dict) else None
    bound_name = None
    if var_id:
        try:
            rv = call_tool("get_local_variables", {})
            if isinstance(rv, list) and rv:
                vars_list = (json.loads(rv[0].get("text") or "{}").get("variables") or [])
                for v in vars_list:
                    if v.get("id") == var_id:
                        bound_name = v.get("name")
                        break
            if bound_name:
                rb = call_tool("batch_bind_variables", {
                    "items": [{
                        "nodeId": sb_id,
                        "bindings": {"fills/0": bound_name},
                    }]
                })
                ok = False
                if isinstance(rb, list) and rb:
                    try:
                        d = json.loads(rb[0].get("text") or "{}")
                        ok = d.get("succeeded", 0) > 0
                    except Exception:
                        pass
                if ok:
                    print(f"  Status Bar bg → NavBar token: {bound_name}")
                    return True
                else:
                    print(f"  ⚠️ Status Bar token bind 0/1 — raw rgba 유지 ({bound_name})")
        except Exception as e:
            print(f"  ⚠️ Status Bar token bind 예외 (raw rgba 유지): {e}")

    print(f"  Status Bar bg → NavBar fill (raw): rgba({r:.3f},{g:.3f},{b:.3f},{opacity:.2f})")
    return True


def _enforce_blueprint_layout(blueprint, node_map):
    """Defensive: post-fix or yoga sim may mutate layoutMode silently.
    Walk blueprint by name, look up built node via node_map, and force
    layoutMode/primaryAxis/counterAxis back to what the blueprint declared.

    Returns count of fixes applied.
    """
    fixes = 0

    def walk(node):
        nonlocal fixes
        if isinstance(node, dict):
            name = node.get("name")
            al = node.get("autoLayout")
            ntype = node.get("type", "frame")
            if name and ntype in ("frame", "FRAME") and al and name in node_map:
                want_mode = al.get("layoutMode") or al.get("direction")
                if want_mode in ("HORIZONTAL", "VERTICAL"):
                    nid = node_map[name]
                    try:
                        r = call_tool("get_node_info", {"nodeId": nid})
                        if isinstance(r, list) and r:
                            try:
                                info = json.loads(r[0].get("text", ""))
                                actual_mode = info.get("layoutMode")
                                if actual_mode and actual_mode != want_mode:
                                    # Mismatch — force back
                                    payload = {
                                        "nodeId": nid,
                                        "layoutMode": want_mode,
                                        "itemSpacing": al.get("itemSpacing", 0),
                                    }
                                    if "primaryAxisAlignItems" in al:
                                        payload["primaryAxisAlignItems"] = al["primaryAxisAlignItems"]
                                    if "counterAxisAlignItems" in al:
                                        payload["counterAxisAlignItems"] = al["counterAxisAlignItems"]
                                    for k in ("paddingTop", "paddingBottom", "paddingLeft", "paddingRight"):
                                        if k in al:
                                            payload[k] = al[k]
                                    call_tool("set_auto_layout", payload)
                                    fixes += 1
                                    print(f"  ↩️  layout restore '{name}': {actual_mode} → {want_mode}")
                            except Exception:
                                pass
                    except Exception:
                        pass
            for c in node.get("children") or []:
                walk(c)
            for c in node.get("_originalChildren") or []:
                walk(c)
        elif isinstance(node, list):
            for c in node:
                walk(c)

    walk(blueprint)
    return fixes


def _apply_instance_overrides(blueprint, node_map):
    """Walk blueprint for any node with type=='instance' + instanceProperties.
    Two paths:
      1. `Label` key  → set_text_content on instance's first TEXT descendant
      2. other keys (Boolean/VARIANT/INSTANCE_SWAP) → set_instance_properties pass-through
    Resolves nodeId via node_map (build's name→id mapping).
    Returns count of overrides successfully applied.
    """
    overrides = []  # [(nodeId, kind, payload)]

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "instance":
                name = node.get("name")
                # Source 1: explicit instanceProperties from blueprint
                ip = node.get("instanceProperties") or {}
                # Source 2: R23 inject's _instanceText (auto-extracted from name)
                inj_text = node.get("_instanceText")
                if name and name in node_map:
                    nid = node_map[name]
                    label = ip.get("Label") or inj_text
                    if label:
                        overrides.append((nid, "text", str(label)))
                    other = {k: v for k, v in ip.items() if k != "Label"}
                    if other:
                        overrides.append((nid, "props", other))
            for c in node.get("children") or []:
                walk(c)
            # Also walk _originalChildren (R23 stripped them but they're still data)
            for c in node.get("_originalChildren") or []:
                walk(c)
        elif isinstance(node, list):
            for c in node:
                walk(c)

    walk(blueprint)
    if not overrides:
        return 0

    succeeded = 0
    for nid, kind, payload in overrides:
        try:
            if kind == "text":
                # Fetch instance subtree, find first TEXT descendant
                r = call_tool("get_node_info", {"nodeId": nid})
                if not isinstance(r, list) or not r or "Error" in r[0].get("text", "")[:50]:
                    continue
                inst = json.loads(r[0]["text"])
                # Recurse for first TEXT
                def first_text(n):
                    if isinstance(n, dict):
                        if n.get("type") == "TEXT":
                            return n.get("id")
                        for c in n.get("children") or []:
                            t = first_text(c)
                            if t:
                                return t
                    return None
                tid = first_text(inst)
                if tid:
                    call_tool("set_text_content", {"nodeId": tid, "text": payload})
                    succeeded += 1
            elif kind == "props":
                # Pass-through for Boolean / VARIANT / INSTANCE_SWAP
                call_tool("set_instance_properties", {"nodeId": nid, "properties": payload})
                succeeded += 1
        except Exception:
            pass
    return succeeded


def _auto_bind_semantic_tokens(root_node_id):
    """Run semantic-token binding sweep on the rendered tree.
    Wraps _collect_bindings + _apply_bindings into a single auto-step.
    Honors invariants 4 (semantic only) + 5 (state excluded) — both
    enforced in _load_token_index, no per-call config needed.
    """
    try:
        token_map = load_token_map()
        if not token_map:
            return {"colors_succeeded": 0, "colors_total": 0}
        indexes = _load_token_index(token_map)
        r = call_tool("get_nodes_info", {"nodeIds": [root_node_id]})
        if not isinstance(r, list) or not r or "Error" in r[0].get("text", "")[:50]:
            return {"colors_succeeded": 0, "colors_total": 0}
        tree = json.loads(r[0]["text"])[0].get("document") or {}
        nodes = _flatten_node_tree(tree)
        queues = _collect_bindings(nodes, indexes)
        return _apply_bindings(queues)
    except Exception as e:
        print(f"  ⚠️ token-bind sweep error (continuing): {e}")
        return {"colors_succeeded": 0, "colors_total": 0}


def _auto_classify_black_texts(root_node_id):
    """Find TEXT nodes with default-black fill (#000000) AND no bound variable,
    classify them by ancestor context, and bind to an appropriate semantic
    token. Workaround for build pipeline bug where $token() in TEXT 'color'
    field isn't applied.

    Classification rules (priority top-down):
      • Inside bg-brand-solid ancestor → bg-primary (white)
      • Inside bg-error-* / bg-warning-* / bg-success-* → matching fg-*
      • By Korean content patterns → fg-tertiary (메타) / fg-secondary (라벨)
      • Default → fg-primary
    """
    try:
        # Build var-id → name map
        rv = call_tool("get_local_variables", {})
        if not isinstance(rv, list) or not rv:
            return 0
        var_id_to_name = {
            v.get("id"): v.get("name", "")
            for v in (json.loads(rv[0]["text"]).get("variables") or [])
        }

        rt = call_tool("get_nodes_info", {"nodeIds": [root_node_id]})
        if not isinstance(rt, list) or not rt or "Error" in rt[0].get("text", "")[:50]:
            return 0
        tree = json.loads(rt[0]["text"])[0].get("document") or {}

        to_bind = []

        def get_bg(node):
            fills = node.get("fills") or []
            if not fills or not isinstance(fills[0], dict):
                return None
            bv = fills[0].get("boundVariables") or {}
            cb = bv.get("color") if isinstance(bv, dict) else None
            if isinstance(cb, dict) and cb.get("id"):
                return var_id_to_name.get(cb["id"], "")
            return None

        def classify(text_node, bg_chain):
            chars = text_node.get("characters", "") or ""
            # Innermost ancestor bg with content
            parent_bg = next((b for b in reversed(bg_chain) if b), "") or ""
            pl = parent_bg.lower()
            # On brand bg → white
            if "bg-brand-solid" in pl:
                return "Colors/Background/bg-primary"
            if "bg-error-solid" in pl or "fg-error" in pl:
                return "Colors/Background/bg-primary"
            if "bg-success-solid" in pl:
                return "Colors/Background/bg-primary"
            if "bg-warning-solid" in pl:
                return "Colors/Background/bg-primary"
            # On error-secondary (light red) → fg-error-primary text
            if "bg-error-secondary" in pl or "bg-error-primary" in pl:
                return "Colors/Foreground/fg-error-primary"
            if "bg-warning-secondary" in pl or "bg-warning-primary" in pl:
                return "Colors/Foreground/fg-warning-primary"
            if "bg-success-secondary" in pl or "bg-success-primary" in pl:
                return "Colors/Foreground/fg-success-primary"
            if "bg-brand-primary" in pl or "bg-brand-secondary" in pl:
                return "Colors/Foreground/fg-brand-primary"
            # Specific symbols
            if chars in ("+",):
                return "Colors/Foreground/fg-success-primary"
            if chars in ("−", "-"):
                return "Colors/Foreground/fg-error-primary"
            # Heuristic by content: short tertiary captions
            tertiary_hints = (
                "총 ", "에 보여요", "사용자에게", "전체 보기", "이번 달",
                "매일매일", "방금 전", "분 전", "시간 전", "어제", "일 전", "주 전",
            )
            if any(hint in chars for hint in tertiary_hints):
                return "Colors/Foreground/fg-tertiary"
            secondary_hints = ("모은 금액", "납입 예정액", "월 납입", "납입 완료", "남은 납입", "수령 회차", "기간")
            if any(hint in chars for hint in secondary_hints):
                return "Colors/Foreground/fg-secondary"
            # Default
            return "Colors/Foreground/fg-primary"

        def walk(n, bg_chain):
            if (n.get("id") or "").startswith("I"):
                return  # don't touch instance internals
            own_bg = get_bg(n)
            new_chain = bg_chain + [own_bg] if own_bg else bg_chain
            if n.get("type") == "TEXT":
                fills = n.get("fills") or []
                if isinstance(fills, list) and fills:
                    f = fills[0]
                    if isinstance(f, dict):
                        color = f.get("color") or {}
                        bv = f.get("boundVariables") or {}
                        cb = bv.get("color") if isinstance(bv, dict) else None
                        bound = isinstance(cb, dict) and cb.get("id")
                        is_black = (
                            color.get("r", 1) == 0
                            and color.get("g", 1) == 0
                            and color.get("b", 1) == 0
                        )
                        if is_black and not bound:
                            target = classify(n, new_chain)
                            if target:
                                to_bind.append({
                                    "nodeId": n.get("id"),
                                    "bindings": {"fills/0": target},
                                })
            for c in n.get("children") or []:
                walk(c, new_chain)

        walk(tree, [])
        if not to_bind:
            return 0

        succeeded = 0
        chunk = 50
        for i in range(0, len(to_bind), chunk):
            batch = to_bind[i : i + chunk]
            try:
                r = call_tool("batch_bind_variables", {"items": batch})
                d = json.loads(r[0]["text"]) if isinstance(r, list) and r else {}
                succeeded += d.get("succeeded", 0)
            except Exception:
                pass
        return succeeded
    except Exception as e:
        print(f"  ⚠️ black-text classify error (continuing): {e}")
        return 0


def cmd_post_fix(root_node_id: str, pre_computed_layout: dict = None):
    """빌드 후 자동 후처리: FILL 사이징, Tab Bar/FAB 배치, 섹션 갭, 텍스트 수정, stroke 정렬.

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
    print("\n[5/6] Zero-width 텍스트 수정 중...")
    text_fixes = _fix_zero_width_text(tree)
    print(f"  → {text_fixes}건 수정")

    # 6. Stroke 정렬 강제 (OUTSIDE → INSIDE) — clipsContent 부모에 잘리는 현상 방지
    print("\n[6/7] Stroke INSIDE 정렬 강제 중...")
    stroke_fixes = _fix_stroke_alignment(tree)
    print(f"  → {stroke_fixes}건 수정")

    # 7. 가로 스크롤 peek 검증 (VS32) — 카드 width > 165px이면 경고
    print("\n[7/8] 가로 스크롤 Peek 검증 중...")
    peek_warns = _check_horizontal_scroll_peek(tree)
    if peek_warns == 0:
        print(f"  → 모든 가로 스크롤 섹션이 peek 패턴 준수")
    else:
        print(f"  → ⚠️ {peek_warns}개 섹션에서 peek 패턴 위반 (카드가 너무 큼 — Blueprint 수정 필요)")

    # 8. Status Bar bg 매칭 (CLAUDE.md 규칙 #25)
    print("\n[8/10] Status Bar bg를 NavBar fill과 매칭 중...")
    sb_matched = _match_status_bar_bg_to_nav(tree)
    if not sb_matched:
        print(f"  → skip (Status Bar 자식 없음 또는 NavBar fill 미지정)")

    # 8.5. R28 carousel-align: 가로 스크롤 carousel 첫 카드 x = 형제 타이틀 x
    # (사용자 정책 2026-05-05)
    print("\n[8.5] R28 가로 carousel ↔ 타이틀 좌측 정렬 보정 중...")
    try:
        from design_rules import REGISTRY as _R28
        # 최신 트리 다시 수집 — 위에서 위치 변경 발생했을 수 있음
        _r28_tree = _collect_tree(root_node_id)
        rule = next((r for r in _R28._rules.values()
                     if r.rule_id == "R28-carousel-align"), None)
        if rule and rule.auto_fix_built_fn:
            r28_fixes = rule.auto_fix_built_fn(_r28_tree, {}) or 0
            print(f"  → {r28_fixes}건 정렬")
    except Exception as e:
        print(f"  ⚠️ R28 carousel-align 실패 (무시): {e}")

    # 8.6. R35 underline-tab-active: active tab에 brand bottom stroke 강제
    # (사용자 정책 2026-05-06)
    print("\n[8.6] R35 underline tab nav active 강제 중...")
    try:
        from design_rules import REGISTRY as _R35
        _r35_tree = _collect_tree(root_node_id)
        rule = next((r for r in _R35._rules.values()
                     if r.rule_id == "R35-underline-tab-active"), None)
        if rule and rule.auto_fix_built_fn:
            r35_fixes = rule.auto_fix_built_fn(_r35_tree, {}) or 0
            print(f"  → {r35_fixes}건 underline 적용")
    except Exception as e:
        print(f"  ⚠️ R35 underline-tab-active 실패 (무시): {e}")

    # 8.7. R36 carousel-peek: horizontal carousel 마지막 카드 25%+ peek 강제
    # (사용자 정책 2026-05-06 — v25 stage card scroll 잘림 회귀 fix)
    print("\n[8.7] R36 carousel last-card peek 강제 중...")
    try:
        from design_rules import REGISTRY as _R36
        _r36_tree = _collect_tree(root_node_id)
        rule = next((r for r in _R36._rules.values()
                     if r.rule_id == "R36-carousel-peek"), None)
        if rule and rule.auto_fix_built_fn:
            r36_fixes = rule.auto_fix_built_fn(_r36_tree, {}) or 0
            print(f"  → {r36_fixes}건 카드 폭 조정")
    except Exception as e:
        print(f"  ⚠️ R36 carousel-peek 실패 (무시): {e}")

    # 9. Semantic Token Binding sweep (Rule 4/5 from invariants 2026-05-04)
    print("\n[9/10] Semantic Token Binding sweep 중...")
    bind_counts = _auto_bind_semantic_tokens(root_node_id)
    print(f"  → colors {bind_counts.get('colors_succeeded',0)}/{bind_counts.get('colors_total',0)} bound")

    # 10. Auto-fix black default text colors (Rule 6 from invariants)
    # build pipeline의 resolve_tokens_in_blueprint가 TEXT 'color'에 있는
    # $token()을 적용 안 하는 버그 우회. 검정(0,0,0)이고 not-bound인 텍스트를
    # 부모 컨텍스트에 따라 분류해서 바인딩.
    print("\n[10/10] 검정 default 텍스트 자동 분류 + binding 중...")
    text_fixed = _auto_classify_black_texts(root_node_id)
    print(f"  → {text_fixed} 텍스트 자동 컬러 binding")

    elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"POST-FIX 완료 — {elapsed:.1f}s")
    print(f"  FILL 수정: {fill_fixes}건")
    print(f"  Tab Bar/Stroke 수정: {tab_fixes}건")
    print(f"  텍스트 수정: {text_fixes}건")
    print(f"  Stroke INSIDE 수정: {stroke_fixes}건")
    print(f"  Peek 위반 경고: {peek_warns}건")
    print(f"  Status Bar bg 매칭: {'OK' if sb_matched else 'skip'}")
    print(f"  Semantic bind: {bind_counts.get('colors_succeeded',0)}/{bind_counts.get('colors_total',0)}")
    print(f"  텍스트 컨텍스트 binding: {text_fixed}건")
    print(f"  루트 높이: {layout_result['root_height']}")
    print(f"{'='*50}\n")

    # ── L5 verify — registry-based post-build assertions ──
    try:
        from design_rules import REGISTRY as _R, Severity as _S
        verify_tree = _collect_tree(root_node_id)
        violations = _R.run_verify(verify_tree, ctx={"blueprint": pre_computed_layout})
        errs = [v for v in violations if v.severity == _S.ERROR]
        warns = [v for v in violations if v.severity == _S.WARN]
        if errs or warns:
            print(f"VERIFY — {len(errs)} error(s), {len(warns)} warning(s):")
            for v in violations:
                print(f"  {v.format()}")
        else:
            print(f"VERIFY ✓ all {len([r for r in _R.all() if 'verify' in [p.value for p in r.phases()]])} verify rule(s) passed")
    except Exception as _ve:
        print(f"VERIFY skipped (error): {_ve}")


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
        # Backward-compat alias — forwards to lint
        print("[deprecated] 'validate' subcommand → forwarding to 'lint'")
        sys.argv[1] = "lint"
        return main()
    elif cmd == "lint":
        # New registry-based lint — use this preferentially over `validate`
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py lint <blueprint.json>")
            sys.exit(1)
        from design_rules import REGISTRY as _R, Severity as _S
        with open(sys.argv[2]) as f:
            bp = json.load(f)
        bp = _flatten_padding_objects(bp)
        bp = _R.run_inject(bp)  # show post-inject state
        violations = _R.run_lint(bp)
        errs = [v for v in violations if v.severity == _S.ERROR]
        warns = [v for v in violations if v.severity == _S.WARN]
        infos = [v for v in violations if v.severity == _S.INFO]
        print(f"Loaded rules: {len(_R.all())}")
        print(f"{'✗' if errs else '✓'} {len(errs)} error(s), {len(warns)} warning(s), {len(infos)} info")
        for v in violations:
            print(f"  {v.format()}")
        sys.exit(1 if errs else 0)
    elif cmd == "verify":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py verify <rootNodeId> [blueprint.json]")
            sys.exit(1)
        from design_rules import REGISTRY as _R, Severity as _S
        ensure_session()
        root_id = sys.argv[2]
        tree = _collect_tree(root_id)
        ctx = {}
        if len(sys.argv) > 3:
            with open(sys.argv[3]) as f:
                ctx["blueprint"] = json.load(f)
        violations = _R.run_verify(tree, ctx)
        errs = [v for v in violations if v.severity == _S.ERROR]
        warns = [v for v in violations if v.severity == _S.WARN]
        print(f"Verify: {len(errs)} error(s), {len(warns)} warning(s)")
        for v in violations:
            print(f"  {v.format()}")
        sys.exit(1 if errs else 0)
    elif cmd == "assemble":
        if len(sys.argv) < 3:
            print("Usage: figma_mcp_client.py assemble <config.json>")
            sys.exit(1)
        cmd_assemble(sys.argv[2])
    elif cmd == "reference":
        from reference_lib import cli as _ref_cli
        sys.exit(_ref_cli(sys.argv[2:]))
    elif cmd == "interactive":
        cmd_interactive()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


# ============================================================
# Semantic Token Binding Sweep (post-fix step 6)
# ============================================================

_SEMANTIC_PREFIXES = ("fg-", "bg-", "border-", "text-")
_SEMANTIC_PATH_PARTS = ("/Fg/", "/Bg/", "/Border/", "/Text/", "/Background/", "/Foreground/")


def _is_semantic_token(name, figma_path):
    """Heuristic: token is semantic if name contains fg-/bg-/border-/text- after
    the type prefix, or if figmaPath has those segments.

    NOTE 2026-05-05: utility-blue-light carve-out REMOVED. User rejected
    aqua/second-accent. Only true semantic tokens (bg-/fg-/border-/text-)
    are eligible for binding.
    """
    lower_name = name.lower()
    for p in _SEMANTIC_PREFIXES:
        if p in lower_name:
            return True
    for p in _SEMANTIC_PATH_PARTS:
        if p in figma_path:
            return True
    return False


def _hex_to_rgba_ints(hex_str):
    """'#181d27' or '#181d27ff' -> (24, 29, 39, 1.0). None if not parseable."""
    if not isinstance(hex_str, str) or not hex_str.startswith("#"):
        return None
    h = hex_str[1:]
    try:
        if len(h) == 6:
            r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16); a = 1.0
        elif len(h) == 8:
            r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
            a = round(int(h[6:8], 16) / 255.0, 3)
        else:
            return None
        return (r, g, b, a)
    except ValueError:
        return None


def _resolve_typography_value(value, token_map):
    """TYPOGRAPHY value uses {Font family.x} / {fontSize.N} reference syntax.
    Return a dict where references are replaced by their resolved primitive
    value if found in token_map; otherwise keep the original reference string
    so we can debug later."""
    resolved = {}
    for k, v in value.items():
        if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
            ref = v[1:-1]  # 'Font family.font-family-display' or 'fontSize.10'
            # Convert reference path 'fontSize.10' -> figmaPath 'fontSize/10'
            ref_path = ref.replace(".", "/")
            found = None
            for tkn in token_map.values():
                if tkn.get("figmaPath") == ref_path:
                    found = tkn.get("value")
                    break
            resolved[k] = found if found is not None else v
        else:
            resolved[k] = v
    return resolved


def _load_token_index(token_map):
    """Build reverse indexes from TOKEN_MAP.json contents.

    Returns:
        {
          "color_index":  {(r,g,b,a): [(token_name, is_semantic)]},
          "number_index": {value: [(token_name, is_semantic)]},
          "typography_list": [{name, fontFamily, fontWeight, fontSize,
                               lineHeight, letterSpacing}],
          "shadow_list":     [{name, color, offsetX, offsetY, radius, spread}]
        }
    Each color_index / number_index list is sorted with semantic tokens first.
    """
    color_index = {}
    number_index = {}
    typography_list = []
    shadow_list = []

    for name, entry in token_map.items():
        ttype = entry.get("type")
        figma_path = entry.get("figmaPath", "")
        is_semantic = _is_semantic_token(name, figma_path)
        value = entry.get("value")

        if ttype == "COLOR":
            rgba = _hex_to_rgba_ints(value)
            if rgba is None:
                continue
            # User policy 2026-05-03: bind ONLY to semantic tokens.
            # Primitives (Base/*, Brand/600, Gray .../900, Component colors/*)
            # are excluded from binding candidates entirely. Designer must use
            # semantic-named tokens (bg-*, fg-*, border-*, text-*).
            if not is_semantic:
                continue
            # User policy 2026-05-03/04: in DEFAULT state, never bind to
            # state-specific OR modifier-variant tokens. These share hex with
            # plain hierarchy tokens (e.g. bg-secondary_subtle = #fcfcfd =
            # bg-secondary) but encode "subtle / hover / disabled" semantics
            # which are wrong for a normal-state fill.
            #   plain only: bg-primary/secondary/tertiary/quaternary
            #   excluded: any token with state/modifier suffix or special-purpose name
            lower = (figma_path or name).lower()
            if any(state in lower for state in (
                # state names
                "/bg-disabled", "/bg-active",
                # modifier suffixes (apply to bg-* / fg-* / border-* / text-*)
                "_hover", "_pressed", "_focused", "_focus", "_visited",
                "_subtle", "_alt", "_on-brand",
                # inverse / solid (special purpose, never normal default)
                "/bg-primary-solid", "/bg-secondary-solid",
            )):
                continue
            color_index.setdefault(rgba, []).append((name, is_semantic))
        elif ttype == "NUMBER":
            if isinstance(value, (int, float)):
                number_index.setdefault(value, []).append((name, is_semantic))
        elif ttype == "TYPOGRAPHY" and isinstance(value, dict):
            resolved = _resolve_typography_value(value, token_map)
            typography_list.append({"name": name, **resolved})
        elif ttype == "BOXSHADOW" and isinstance(value, dict):
            # Normalize field names — upstream sync may use either {x,y,blur}
            # (current sync-to-agent.js output) or {offsetX,offsetY,radius}.
            # Alpha is encoded in the last 2 chars of an 8-char hex color.
            color_hex = value.get("color")
            rgba_ints = _hex_to_rgba_ints(color_hex) if isinstance(color_hex, str) else None
            extracted_alpha = rgba_ints[3] if rgba_ints is not None else value.get("alpha", 1)
            shadow_list.append({
                "name": name,
                "color":   color_hex,
                "alpha":   extracted_alpha,
                "offsetX": value.get("offsetX", value.get("x", 0)),
                "offsetY": value.get("offsetY", value.get("y", 0)),
                "radius":  value.get("radius",  value.get("blur", 0)),
                "spread":  value.get("spread", 0),
            })
        # else: list-shaped multi-layer BOXSHADOW values are not yet handled (future)

    # Sort each bucket: semantic first, plain hierarchy ahead of special-purpose,
    # then alphabetical. This ensures bg-secondary wins over bg-brand-section /
    # bg-field when they collide on the same RGB. (User policy 2026-05-08:
    # plain semantic-hierarchy tokens are the canonical default in any new build.)
    _PLAIN_HIERARCHY = (
        # background plain
        "bg-primary", "bg-secondary", "bg-tertiary", "bg-quaternary",
        # foreground plain
        "fg-primary", "fg-secondary", "fg-tertiary", "fg-quaternary",
        # text plain
        "text-primary", "text-secondary", "text-tertiary", "text-quaternary",
        # border plain
        "border-primary", "border-secondary", "border-tertiary",
    )
    def _is_plain(name):
        last = name.rsplit("/", 1)[-1].lower()
        return last in _PLAIN_HIERARCHY
    def _sort_bucket(bucket):
        return sorted(bucket, key=lambda t: (not t[1], not _is_plain(t[0]), t[0]))

    for k in list(color_index.keys()):
        color_index[k] = _sort_bucket(color_index[k])
    for k in list(number_index.keys()):
        number_index[k] = _sort_bucket(number_index[k])

    return {
        "color_index": color_index,
        "number_index": number_index,
        "typography_list": typography_list,
        "shadow_list": shadow_list,
    }


_COLOR_THRESHOLD = 12  # ΔRGB sum, RGB 0-255


def _token_class(name: str) -> str:
    """Classify a TOKEN_MAP entry name into 'background' / 'foreground' /
    'text' / 'border' / 'other'. Used to prefer same-class candidates when
    binding by RGB (a TEXT fill must never bind to a Colors/Background/* var,
    and a FRAME bg must never bind to a Colors/Foreground/* var)."""
    n = (name or "").lower()
    if "/background/" in n or n.startswith("colors/background"):
        return "background"
    if "/foreground/" in n or n.startswith("colors/foreground"):
        return "foreground"
    if "/text/" in n or n.startswith("colors/text"):
        return "text"
    if "/border/" in n or n.startswith("colors/border"):
        return "border"
    return "other"


def _match_color(rgba_tuple, color_index, prefer_class: str = None):
    """Return the best-matching token name for an (r,g,b,a) tuple, or None.

    `prefer_class`:
        "background" — caller is a FRAME fill / RECTANGLE bg → require
                       Colors/Background/* tokens; reject foreground/text.
        "foreground" — caller is a TEXT fill or icon vector fill → require
                       Colors/Foreground/* or Colors/Text/* tokens.
        "border"     — caller is a stroke → prefer Colors/Border/* then
                       Colors/Foreground/* (border style line).
        None         — no class restriction (legacy behavior).

    This prevents the v27 regression where the post-fix sweep bound the
    "이번 달 스케줄" TEXT to Colors/Background/bg-field (because the same
    RGB collided with fg-quaternary in TOKEN_MAP), making the title invisible.

    Strategy:
        1. Exact (r,g,b,a) hit → first compatible token in pre-sorted bucket.
        2. Otherwise scan all entries with same alpha (±0.05), find lowest
           ΔRGB that is ≤ _COLOR_THRESHOLD. Tie-break by class-match >
           semantic > plain-hierarchy > alphabetical.
    """
    def _accepts(name: str) -> bool:
        if not prefer_class:
            return True
        c = _token_class(name)
        if prefer_class == "background":
            return c == "background"
        if prefer_class == "foreground":
            return c in ("foreground", "text")
        if prefer_class == "border":
            return c in ("border", "foreground")
        return True

    # Exact hit — pick first compatible token
    if rgba_tuple in color_index:
        for tok_name, _ in color_index[rgba_tuple]:
            if _accepts(tok_name):
                return tok_name
        # No class match on exact RGB? fall through to fuzzy search

    r, g, b, a = rgba_tuple
    best_dist = _COLOR_THRESHOLD + 1
    best_token = None
    best_is_semantic = False
    for (cr, cg, cb, ca), bucket in color_index.items():
        if abs(ca - a) > 0.05:
            continue
        dist = abs(cr - r) + abs(cg - g) + abs(cb - b)
        if dist > _COLOR_THRESHOLD:
            continue
        # Pick first class-compatible candidate from bucket
        cand_name, cand_semantic = (None, False)
        for tn, sem in bucket:
            if _accepts(tn):
                cand_name, cand_semantic = tn, sem
                break
        if not cand_name:
            continue
        better = (
            dist < best_dist
            or (dist == best_dist and cand_semantic and not best_is_semantic)
        )
        if better:
            best_dist = dist
            best_token = cand_name
            best_is_semantic = cand_semantic
    return best_token


_NUMBER_THRESHOLD = 2  # ±px


def _match_number(value, number_index):
    """Return best NUMBER token within ±_NUMBER_THRESHOLD of value, or None.
    value=0 is treated as 'no semantic meaning' and skipped."""
    if value == 0 or value is None:
        return None
    if value in number_index:
        return number_index[value][0][0]
    best_dist = _NUMBER_THRESHOLD + 1
    best_token = None
    best_is_semantic = False
    for cand_value, bucket in number_index.items():
        dist = abs(cand_value - value)
        if dist > _NUMBER_THRESHOLD:
            continue
        cand_name, cand_semantic = bucket[0]
        better = (
            dist < best_dist
            or (dist == best_dist and cand_semantic and not best_is_semantic)
        )
        if better:
            best_dist = dist
            best_token = cand_name
            best_is_semantic = cand_semantic
    return best_token


_FONT_SIZE_THRESHOLD = 1     # ±px
_LINE_HEIGHT_PCT = 0.03      # ±3%
_LETTER_SPACING_PCT = 0.03   # ±3% relative to fontSize, fallback ±0.1


def _match_textstyle(text_props, typography_list):
    """Find a TYPOGRAPHY token whose family/weight match exactly and whose
    size/lineHeight/letterSpacing are within tolerance. Returns the token name
    (caller maps name → text style id elsewhere)."""
    if not isinstance(text_props, dict):
        return None
    pf = text_props.get("fontFamily")
    pw = text_props.get("fontWeight")
    ps = text_props.get("fontSize")
    plh = text_props.get("lineHeight")
    pls = text_props.get("letterSpacing")
    if pf is None or pw is None or ps is None:
        return None

    best_dist = float("inf")
    best_name = None
    for ts in typography_list:
        if ts.get("fontFamily") != pf:
            continue
        if ts.get("fontWeight") != pw:
            continue
        ts_size = ts.get("fontSize")
        if not isinstance(ts_size, (int, float)):
            continue
        if abs(ts_size - ps) > _FONT_SIZE_THRESHOLD:
            continue
        ts_lh = ts.get("lineHeight")
        if isinstance(ts_lh, (int, float)) and isinstance(plh, (int, float)):
            tol = max(ts_lh * _LINE_HEIGHT_PCT, 1.0)
            if abs(ts_lh - plh) > tol:
                continue
        ts_ls = ts.get("letterSpacing")
        if isinstance(ts_ls, (int, float)) and isinstance(pls, (int, float)):
            tol = max(abs(ts_size) * _LETTER_SPACING_PCT, 0.1)
            if abs(ts_ls - pls) > tol:
                continue
        # distance: sum of normalized deltas
        dist = abs(ts_size - ps)
        if dist < best_dist:
            best_dist = dist
            best_name = ts["name"]
    return best_name


_SHADOW_OFFSET_TOL = 1   # ±px
_SHADOW_RADIUS_TOL = 2   # ±px
_SHADOW_SPREAD_TOL = 1   # ±px
_SHADOW_ALPHA_TOL = 0.1


def _figma_color_to_rgba_ints(c):
    """{r:0..1, g:0..1, b:0..1, a:0..1} -> (r,g,b,a) with ints + alpha float."""
    if not isinstance(c, dict):
        return None
    try:
        r = int(round(c.get("r", 0) * 255))
        g = int(round(c.get("g", 0) * 255))
        b = int(round(c.get("b", 0) * 255))
        a = round(c.get("a", 1.0), 3)
        return (r, g, b, a)
    except (TypeError, ValueError):
        return None


def _match_shadow(effect, shadow_list):
    """Match a Figma effect (DROP_SHADOW) to a BOXSHADOW token."""
    if not isinstance(effect, dict):
        return None
    if effect.get("type") not in ("DROP_SHADOW", "INNER_SHADOW"):
        return None
    e_rgba = _figma_color_to_rgba_ints(effect.get("color"))
    if e_rgba is None:
        return None
    er, eg, eb, ea = e_rgba
    e_off = effect.get("offset") or {}
    eox = e_off.get("x", 0)
    eoy = e_off.get("y", 0)
    erad = effect.get("radius", 0)
    espread = effect.get("spread", 0)

    best_dist = float("inf")
    best_name = None
    for sh in shadow_list:
        sh_color = sh.get("color")
        s_rgba = _hex_to_rgba_ints(sh_color) if isinstance(sh_color, str) else None
        if s_rgba is None:
            continue
        sr, sg, sb, _ = s_rgba
        sa = sh.get("alpha", 1)
        if abs(sr - er) + abs(sg - eg) + abs(sb - eb) > _COLOR_THRESHOLD:
            continue
        if abs(sa - ea) > _SHADOW_ALPHA_TOL:
            continue
        if abs(sh.get("offsetX", 0) - eox) > _SHADOW_OFFSET_TOL:
            continue
        if abs(sh.get("offsetY", 0) - eoy) > _SHADOW_OFFSET_TOL:
            continue
        if abs(sh.get("radius", 0) - erad) > _SHADOW_RADIUS_TOL:
            continue
        if abs(sh.get("spread", 0) - espread) > _SHADOW_SPREAD_TOL:
            continue
        dist = (
            abs(sh.get("offsetX", 0) - eox)
            + abs(sh.get("offsetY", 0) - eoy)
            + abs(sh.get("radius", 0) - erad)
            + abs(sh.get("spread", 0) - espread)
        )
        if dist < best_dist:
            best_dist = dist
            best_name = sh["name"]
    return best_name


def _flatten_node_tree(node):
    """DFS pre-order flatten a recursive node-info dict into a list of node
    dicts. Each returned node retains its original keys (without 'children').
    Resilient to missing 'children' or non-list 'children'."""
    if not isinstance(node, dict):
        return []
    out = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if not isinstance(cur, dict):
            continue
        copy = {k: v for k, v in cur.items() if k != "children"}
        out.append(copy)
        children = cur.get("children")
        if isinstance(children, list):
            for child in reversed(children):
                stack.append(child)
    return out


_NUMBER_FIELDS = (
    "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
    "itemSpacing",
    "cornerRadius",
    "topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius",
    "strokeWeight",
    "strokeTopWeight", "strokeRightWeight",
    "strokeBottomWeight", "strokeLeftWeight",
)


def _collect_bindings(nodes, indexes):
    """Walk flattened nodes and produce binding queues + unmapped report.

    Returns:
        {
          "color_bindings":     [{nodeId, field: "fills"|"strokes", index, token_name}],
          "number_bindings":    [{nodeId, field, token_name}],
          "textstyle_bindings": [{nodeId, token_name}],
          "effect_bindings":    [{nodeId, index, token_name}],
          "unmapped": {colors:[], numbers:[], typography:[], shadows:[]}
        }
    """
    out = {
        "color_bindings": [],
        "number_bindings": [],
        "textstyle_bindings": [],
        "effect_bindings": [],
        "unmapped": {"colors": [], "numbers": [], "typography": [], "shadows": []},
    }
    color_idx = indexes["color_index"]
    number_idx = indexes["number_index"]
    typo_list = indexes["typography_list"]
    shadow_list = indexes["shadow_list"]

    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        if not nid:
            continue

        # Node-type → token-class hint. TEXT fills must bind to fg-* / text-*,
        # FRAME/RECT fills to bg-*. This blocks the cross-class regressions
        # where same-RGB collisions matched the wrong family (v27, 2026-05-08).
        node_type = (n.get("type") or "").upper()
        is_text_node = node_type in ("TEXT",)
        # Vector children of icon frames also paint with foreground colors
        is_icon_vector = node_type in ("VECTOR", "INSTANCE") and (
            "icon" in (n.get("name") or "").lower()
        )
        fill_class = "foreground" if (is_text_node or is_icon_vector) else "background"
        stroke_class = "foreground" if is_text_node else "border"

        # fills — skip if already bound to a variable (Figma's variable
        # resolution returns the file's current value, which can differ from
        # TOKEN_MAP's hex; rebinding based on the displayed hex breaks the
        # original correct binding). User policy 2026-05-04: never override
        # an existing valid binding on second-pass sweeps.
        for i, fill in enumerate(n.get("fills") or []):
            if not isinstance(fill, dict):
                continue
            if fill.get("type") != "SOLID":
                continue
            # Already bound? Don't touch.
            bv = fill.get("boundVariables") or {}
            if isinstance(bv, dict) and bv.get("color"):
                continue
            rgba = _figma_color_to_rgba_ints(fill.get("color"))
            if rgba is None:
                continue
            tok = _match_color(rgba, color_idx, prefer_class=fill_class)
            if tok:
                out["color_bindings"].append(
                    {"nodeId": nid, "field": "fills", "index": i, "token_name": tok}
                )
            else:
                out["unmapped"]["colors"].append(
                    {"nodeId": nid, "field": "fills", "index": i, "rgba": rgba,
                     "class": fill_class}
                )

        # strokes — same skip-if-bound logic
        for i, stroke in enumerate(n.get("strokes") or []):
            if not isinstance(stroke, dict):
                continue
            if stroke.get("type") != "SOLID":
                continue
            bv = stroke.get("boundVariables") or {}
            if isinstance(bv, dict) and bv.get("color"):
                continue
            rgba = _figma_color_to_rgba_ints(stroke.get("color"))
            if rgba is None:
                continue
            tok = _match_color(rgba, color_idx, prefer_class=stroke_class)
            if tok:
                out["color_bindings"].append(
                    {"nodeId": nid, "field": "strokes", "index": i, "token_name": tok}
                )
            else:
                out["unmapped"]["colors"].append(
                    {"nodeId": nid, "field": "strokes", "index": i, "rgba": rgba,
                     "class": stroke_class}
                )

        # numbers
        for f in _NUMBER_FIELDS:
            if f not in n:
                continue
            v = n[f]
            if not isinstance(v, (int, float)) or v == 0:
                continue
            tok = _match_number(v, number_idx)
            if tok:
                out["number_bindings"].append(
                    {"nodeId": nid, "field": f, "token_name": tok}
                )
            else:
                out["unmapped"]["numbers"].append(
                    {"nodeId": nid, "field": f, "value": v}
                )

        # typography (TEXT nodes only)
        if n.get("type") == "TEXT":
            # mixed style detection: 'fontSize' missing or marked mixed
            if n.get("hasMixedStyle") or n.get("fontSize") is None:
                out["unmapped"]["typography"].append(
                    {"nodeId": nid, "reason": "mixed_or_missing"}
                )
            else:
                # Note: Figma may return fontWeight as int (e.g. 600) or as a display string
                # ("Semibold"). _match_textstyle currently expects string; int→string mapping is a
                # known open item (see plan Risk #3). The fontName.style fallback covers most cases.
                text_props = {
                    "fontFamily": n.get("fontFamily") or (n.get("fontName") or {}).get("family"),
                    "fontWeight": (
                        n.get("fontWeight")
                        or (n.get("fontName") or {}).get("style")
                    ),
                    "fontSize": n.get("fontSize"),
                    "lineHeight": (n.get("lineHeight") or {}).get("value")
                                  if isinstance(n.get("lineHeight"), dict)
                                  else n.get("lineHeight"),
                    "letterSpacing": (n.get("letterSpacing") or {}).get("value")
                                     if isinstance(n.get("letterSpacing"), dict)
                                     else n.get("letterSpacing"),
                }
                tok = _match_textstyle(text_props, typo_list)
                if tok:
                    out["textstyle_bindings"].append(
                        {"nodeId": nid, "token_name": tok}
                    )
                else:
                    out["unmapped"]["typography"].append(
                        {"nodeId": nid, "props": text_props}
                    )

        # effects
        for i, eff in enumerate(n.get("effects") or []):
            if not isinstance(eff, dict):
                continue
            if eff.get("type") not in ("DROP_SHADOW", "INNER_SHADOW"):
                continue
            tok = _match_shadow(eff, shadow_list)
            if tok:
                out["effect_bindings"].append(
                    {"nodeId": nid, "index": i, "token_name": tok}
                )
            else:
                out["unmapped"]["shadows"].append(
                    {"nodeId": nid, "index": i, "effect": eff}
                )

    return out


_BIND_CHUNK = 100


def _apply_bindings(queues):
    """Issue MCP calls for collected bindings. Returns counts.

    Plugin's `batch_bind_variables` expects:
        items: [{ nodeId, bindings: { "fills.0": "varName", "paddingTop": "varName" } }]
    where `bindings` is a property→variableName MAP. Group all bindings for a
    single node into one item to match this shape (was previously sent as flat
    list which the plugin silently rejected — succeeded=0 on every call).
    """
    from collections import defaultdict
    counts = {"colors": 0, "numbers": 0, "textstyles": 0, "effects": 0}

    import re as _re
    def _clean_token_name(n):
        # Strip trailing ' (NNN)' — figmaPath includes tier numbers
        # ('fg-primary (900)') but Figma local variable name doesn't.
        return _re.sub(r"\s*\(\d+\)\s*$", "", n)

    by_node = defaultdict(dict)
    for b in queues["color_bindings"]:
        # Plugin expects 'fills/0' / 'strokes/0' (slash separator), not 'fills.0'
        by_node[b["nodeId"]][f"{b['field']}/{b['index']}"] = _clean_token_name(b["token_name"])
        counts["colors"] += 1
    for b in queues["number_bindings"]:
        by_node[b["nodeId"]][b["field"]] = _clean_token_name(b["token_name"])
        counts["numbers"] += 1

    items = [{"nodeId": nid, "bindings": props} for nid, props in by_node.items()]
    succeeded = 0
    total = 0
    for i in range(0, len(items), _BIND_CHUNK):
        chunk = items[i:i + _BIND_CHUNK]
        if not chunk:
            continue
        try:
            r = call_tool("batch_bind_variables", {"items": chunk}, msg_id=10000 + i)
            txt = r[0].get("text", "") if isinstance(r, list) and r else ""
            try:
                d = json.loads(txt)
                succeeded += d.get("succeeded", 0)
                total += d.get("total", 0)
            except Exception:
                pass
        except Exception:
            pass
    counts["colors_succeeded"] = succeeded
    counts["colors_total"] = total

    if queues["textstyle_bindings"]:
        ts_payload = [
            {"nodeId": b["nodeId"], "textStyleName": b["token_name"]}
            for b in queues["textstyle_bindings"]
        ]
        call_tool("batch_set_text_style_id", {"items": ts_payload}, msg_id=20000)
        counts["textstyles"] = len(ts_payload)

    for b in queues["effect_bindings"]:
        call_tool(
            "set_effect_style_id",
            {"nodeId": b["nodeId"], "effectStyleName": b["token_name"]},
            msg_id=30000,
        )
        counts["effects"] += 1

    return counts


if __name__ == "__main__":
    main()
