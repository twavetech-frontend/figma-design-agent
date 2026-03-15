#!/usr/bin/env python3
"""이미지 재생성 + 레이아웃 수정 — 올바른 MCP 프로토콜 사용"""
import json, os, base64, requests, glob, random, time, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from io import BytesIO

# --- Config ---
SETTINGS_PATH = os.path.expanduser("~/Library/Application Support/figma-design-agent/settings.json")
with open(SETTINGS_PATH) as f:
    API_KEY = json.load(f).get("geminiApiKey", "")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image-preview:generateContent?key={API_KEY}"
MCP_URL = "http://localhost:8769/mcp"
ASSETS_DIR = "assets/generated"

# Load MCP session
SESSION_FILE = "scripts/.mcp_session"
with open(SESSION_FILE) as f:
    MCP_SESSION_ID = f.read().strip()

ICON_REFS = glob.glob("assets/reference-images/icon/*.png") + glob.glob("assets/reference-images/icon/*.jpg")
HERO_REFS = glob.glob("assets/reference-images/hero/*.png") + glob.glob("assets/reference-images/hero/*.jpg")
TWOD_REFS = glob.glob("assets/reference-images/2d/*.png") + glob.glob("assets/reference-images/2d/*.jpg")

_msg_id = 0

def call_mcp(tool_name, args):
    """올바른 MCP JSON-RPC 프로토콜로 도구 호출"""
    global _msg_id
    _msg_id += 1
    payload = {
        "jsonrpc": "2.0",
        "id": _msg_id,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": args}
    }
    headers = {
        "Content-Type": "application/json",
        "mcp-session-id": MCP_SESSION_ID
    }
    resp = requests.post(MCP_URL, json=payload, headers=headers, timeout=300)
    data = resp.json()
    if "error" in data:
        print(f"    MCP Error: {data['error']}")
        return None
    content = data.get("result", {}).get("content", [])
    for c in content:
        if c.get("type") == "text":
            try:
                return json.loads(c["text"])
            except:
                return c["text"]
    return content

def get_ref_images(refs, count=2):
    if not refs: return []
    chosen = random.sample(refs, min(count, len(refs)))
    parts = []
    for p in chosen:
        with open(p, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        ext = p.rsplit(".", 1)[-1].lower()
        mime = "image/png" if ext == "png" else "image/jpeg"
        parts.append({"inlineData": {"mimeType": mime, "data": data}})
    return parts

def call_gemini(prompt, ref_parts=None):
    parts = []
    if ref_parts:
        parts.extend(ref_parts)
        parts.append({"text": "Use the style of these reference images. " + prompt})
    else:
        parts.append({"text": prompt})
    resp = requests.post(GEMINI_URL, json={
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}
    }, timeout=180)
    data = resp.json()
    if "candidates" not in data:
        raise Exception(f"No candidates: {str(data)[:300]}")
    for part in data["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            return base64.b64decode(part["inlineData"]["data"])
    raise Exception("No image in response")

def process_icon(img_bytes, size, use_rembg=True):
    if use_rembg:
        from rembg import remove
        img_bytes = remove(img_bytes)
    img = Image.open(BytesIO(img_bytes)).convert("RGBA")
    w, h = img.size
    s = min(w, h)
    left = (w - s) // 2
    top = (h - s) // 2
    img = img.crop((left, top, left + s, top + s))
    img = img.resize((size * 3, size * 3), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def process_hero(img_bytes, w, h):
    img = Image.open(BytesIO(img_bytes)).convert("RGBA")
    iw, ih = img.size
    target_ratio = w / h
    current_ratio = iw / ih
    if current_ratio > target_ratio:
        new_w = int(ih * target_ratio)
        left = (iw - new_w) // 2
        img = img.crop((left, 0, left + new_w, ih))
    else:
        new_h = int(iw / target_ratio)
        top = (ih - new_h) // 2
        img = img.crop((0, top, iw, top + new_h))
    img = img.resize((w * 3, h * 3), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

IMAGES = [
    {"name": "banner1", "nodeId": "111:26", "isHero": True, "w": 353, "h": 180,
     "prompt": "3D soft matte gold coins and invitation envelope floating, right side composition, left half completely empty solid purple background. Soft matte clay texture, NOT glossy. Cinema4D Octane render, soft diffused lighting. Max 2 objects. No text. No shadow."},
    {"name": "banner2", "nodeId": "111:31", "isHero": True, "w": 353, "h": 180,
     "prompt": "3D soft matte cosmetics lipstick and cream jar, right side composition, left half completely empty solid green background. Soft matte clay texture, NOT glossy. Cinema4D Octane render, soft diffused lighting. Max 2 objects. No text. No shadow."},
    {"name": "banner3", "nodeId": "111:36", "isHero": True, "w": 353, "h": 180,
     "prompt": "3D soft matte gift box with ribbon, right side composition, left half completely empty solid orange background. Soft matte clay texture, NOT glossy. Cinema4D Octane render, soft diffused lighting. ONLY ONE gift box. No text. No shadow."},
    {"name": "fun_random", "nodeId": "111:91", "isHero": False, "size": 32, "style": "3d",
     "prompt": "3D rendered icon of a mystery gift box with question mark, Korean app style like KakaoTalk. Soft matte finish, NOT glossy, rounded clay-like. Chunky compact, square proportions. ONLY ONE object. Pure white background. No text. No shadow."},
    {"name": "fun_gift", "nodeId": "111:95", "isHero": False, "size": 32, "style": "3d",
     "prompt": "3D rendered icon of a shopping bag with ribbon bow, Korean app style like KakaoTalk. Soft matte finish, NOT glossy, rounded clay-like. Chunky compact, square proportions. ONLY ONE object. Pure white background. No text. No shadow."},
    {"name": "daily_rescue", "nodeId": "111:101", "isHero": False, "size": 24, "style": "2d",
     "prompt": "2D flat emoji icon of a life ring rescue float, Tossface style. Simple geometric shapes, bold flat colors, no gradients, no shadows. Single centered object. Pure white background. No text."},
    {"name": "daily_check", "nodeId": "111:107", "isHero": False, "size": 24, "style": "2d",
     "prompt": "2D flat emoji icon of a calendar with checkmark, Tossface style. Simple geometric shapes, bold flat colors, no gradients, no shadows. Single centered object. Pure white background. No text."},
    {"name": "daily_point", "nodeId": "111:113", "isHero": False, "size": 24, "style": "2d",
     "prompt": "2D flat emoji icon of lightning bolt with coin, Tossface style. Simple geometric shapes, bold flat colors, no gradients, no shadows. Single centered object. Pure white background. No text."},
]

def generate_one(spec):
    name = spec["name"]
    print(f"  🎨 {name}...")
    try:
        refs = get_ref_images(
            HERO_REFS if spec.get("isHero") else
            (TWOD_REFS if spec.get("style") == "2d" else ICON_REFS)
        )
        raw = call_gemini(spec["prompt"], refs)
        if spec.get("isHero"):
            processed = process_hero(raw, spec["w"], spec["h"])
            mode = "FILL"
        else:
            processed = process_icon(raw, spec["size"], use_rembg=True)
            mode = "FIT"
        filename = f"{name}.png"
        with open(f"{ASSETS_DIR}/{filename}", "wb") as f:
            f.write(processed)
        print(f"  ✅ {name}: {len(processed)} bytes")
        return {"name": name, "nodeId": spec["nodeId"], "filename": filename, "mode": mode, "ok": True}
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        return {"name": name, "nodeId": spec["nodeId"], "ok": False, "error": str(e)}


if __name__ == "__main__":
    print("=" * 60)
    print("STEP 1: 레이아웃 수정")
    print("=" * 60)

    # Fix banner text widths to 160px (post-fix가 FILL로 변경한 것 복원)
    print("\n  [배너 텍스트 너비 160px 복원]")
    for nid, name in [("111:29", "b1-sub"), ("111:30", "b1-title"),
                       ("111:34", "b2-sub"), ("111:35", "b2-title"),
                       ("111:39", "b3-sub"), ("111:40", "b3-title")]:
        call_mcp("set_layout_sizing", {"nodeId": nid, "horizontal": "FIXED"})
        call_mcp("resize_node", {"nodeId": nid, "width": 160, "height": 60})
        print(f"    ✅ {name} → FIXED 160px")

    print("\n" + "=" * 60)
    print("STEP 2: 이미지 생성 (8건)")
    print("=" * 60 + "\n")

    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(generate_one, s): s for s in IMAGES}
        for f in as_completed(futures):
            results.append(f.result())

    ok_results = [r for r in results if r.get("ok")]
    fail_results = [r for r in results if not r.get("ok")]
    print(f"\n  생성: {len(ok_results)} 성공, {len(fail_results)} 실패")

    if not ok_results:
        print("이미지 없음, 종료")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("STEP 3: 이미지 적용 (올바른 MCP 프로토콜)")
    print("=" * 60 + "\n")

    for r in ok_results:
        img_path = f"{ASSETS_DIR}/{r['filename']}"
        if not os.path.exists(img_path):
            print(f"  ⚠️ {r['name']}: 파일 없음 ({img_path})")
            continue

        with open(img_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        result = call_mcp("set_image_fill", {
            "nodeId": r["nodeId"],
            "imageData": img_b64,
            "scaleMode": r["mode"]
        })
        print(f"  ✅ {r['name']} → {r['nodeId']} ({r['mode']})")
        time.sleep(0.5)

    print("\n✅ 모든 수정 완료!")
