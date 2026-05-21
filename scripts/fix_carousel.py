"""캐로셀 카드 FIXED 복원 — post-fix가 FILL로 강제한 가로 스크롤 카드를 되돌린다.

resize_node는 width/height 모두 필수.
- Date Card: 72x120 완전 고정
- Stage Card: width 240 고정, height는 HUG 유지
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figma_mcp_client import ensure_session, call_tool

ensure_session()

DATE_CARDS = ["1118:1082", "1118:1087", "1118:1092", "1118:1097", "1118:1102", "1118:1107"]
STAGE_CARDS = ["1118:1131", "1118:1140", "1118:1149"]

for nid in DATE_CARDS:
    call_tool("set_layout_sizing", {"nodeId": nid, "horizontal": "FIXED", "vertical": "FIXED"})
    call_tool("resize_node", {"nodeId": nid, "width": 72, "height": 120})
    print(f"date  {nid} -> 72x120")

for nid in STAGE_CARDS:
    call_tool("set_layout_sizing", {"nodeId": nid, "horizontal": "FIXED"})
    call_tool("resize_node", {"nodeId": nid, "width": 240, "height": 150})
    call_tool("set_layout_sizing", {"nodeId": nid, "vertical": "HUG"})
    print(f"stage {nid} -> w240 / HUG height")

print("DONE")
