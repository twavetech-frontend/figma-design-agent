#!/usr/bin/env python3
"""QA 스크린샷 — 노드를 PNG로 export하여 저장.

Usage:
    python scripts/qa_screenshot.py <nodeId> [out.png] [scale]
"""
import json, sys, os, base64, urllib.request

URL = "http://localhost:8769/mcp"


def main():
    if len(sys.argv) < 2:
        print("Usage: qa_screenshot.py <nodeId> [out.png] [scale]")
        sys.exit(1)
    node_id = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "qa_shot.png")
    scale = float(sys.argv[3]) if len(sys.argv) > 3 else 1

    # 1. initialize
    init = json.dumps({"jsonrpc": "2.0", "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "qa", "version": "1.0"}}, "id": 1})
    req = urllib.request.Request(URL, init.encode(), {"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=15)
    sid = resp.headers.get("Mcp-Session-Id", "") or resp.headers.get("mcp-session-id", "")

    # 2. initialized notification
    note = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
    urllib.request.urlopen(urllib.request.Request(
        URL, note.encode(), {"Content-Type": "application/json", "Mcp-Session-Id": sid}), timeout=10)

    # 3. export
    body = json.dumps({"jsonrpc": "2.0", "method": "tools/call", "params": {
        "name": "export_node_as_image",
        "arguments": {"nodeId": node_id, "format": "PNG", "scale": scale}}, "id": 2})
    req = urllib.request.Request(URL, body.encode(), {
        "Content-Type": "application/json", "Mcp-Session-Id": sid})
    data = json.loads(urllib.request.urlopen(req, timeout=60).read())

    content = data.get("result", {}).get("content", [])
    for part in content:
        if part.get("type") == "image":
            with open(out, "wb") as f:
                f.write(base64.b64decode(part["data"]))
            print(f"saved: {out}")
            return
        # 일부 응답은 text에 base64 또는 dataURL을 담음
        if part.get("type") == "text":
            txt = part.get("text", "")
            if "base64," in txt:
                txt = txt.split("base64,", 1)[1]
            try:
                raw = base64.b64decode(txt)
                if raw[:4] == b"\x89PNG":
                    with open(out, "wb") as f:
                        f.write(raw)
                    print(f"saved: {out}")
                    return
            except Exception:
                pass
    print("NO IMAGE in response:")
    print(json.dumps(data, ensure_ascii=False)[:800])
    sys.exit(2)


if __name__ == "__main__":
    main()
