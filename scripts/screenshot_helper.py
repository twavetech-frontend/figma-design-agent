"""QA 스크린샷 헬퍼 — export_node_as_image 결과를 PNG 파일로 저장.

사용법: python screenshot_helper.py <nodeId> <outPath> [scale]
"""
import sys
import os
import base64

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figma_mcp_client import ensure_session, call_tool

node_id = sys.argv[1]
out_path = sys.argv[2]
scale = float(sys.argv[3]) if len(sys.argv) > 3 else 1

ensure_session()
content = call_tool("export_node_as_image", {"nodeId": node_id, "format": "PNG", "scale": scale})

img_data = None
for item in content:
    if item.get("type") == "image":
        img_data = item.get("data")
        break

if not img_data:
    texts = [i.get("text", "") for i in content if i.get("type") == "text"]
    print("NO IMAGE:", texts[:3])
    sys.exit(1)

with open(out_path, "wb") as f:
    f.write(base64.b64decode(img_data))
print(f"SAVED {out_path} ({len(img_data)} b64 chars)")
