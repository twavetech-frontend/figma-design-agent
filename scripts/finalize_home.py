"""빌드 후 마무리 후처리 — 한 방에 실행.

post-fix가 매번 망가뜨리는 항목을 노드 이름으로 찾아 교정한다:
  1. 루트 fill → bg-primary (auto-bind가 엉뚱한 변수로 바인딩하는 버그 교정)
  2. Date Card * → FIXED 72x120 (캐로셀 카드, post-fix가 FILL로 펴버림)
  3. Stage Card * → FIXED width 240 + HUG height
  4. My Stages Scroll → vertical HUG (카드가 잘리지 않도록)
  5. 레이아웃 재계산 (FAB/TabBar/루트 높이)

사용법: python finalize_home.py <rootNodeId>
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figma_mcp_client import ensure_session, call_tool, _collect_tree, _fix_layout_and_positions

root_id = sys.argv[1]
ensure_session()

# 1. 루트 fill → bg-primary
call_tool("set_fill_color", {"nodeId": root_id, "r": 0.98824, "g": 0.98824, "b": 0.99216, "a": 1})
call_tool("set_bound_variables", {"nodeId": root_id, "bindings": {"fills/0": "Colors/Background/bg-primary"}})
print(f"[1] root {root_id} fill -> bg-primary")

# 2. 트리 수집 + 이름으로 노드 인덱싱
tree = _collect_tree(root_id)
by_name = {}


def _walk(n):
    by_name.setdefault(n.get("name", ""), []).append(n)
    for c in n.get("_children_full", []):
        _walk(c)


_walk(tree)

# 3. Date Card → FIXED 72x120
date_cards = [n["id"] for nm, lst in by_name.items() if nm.startswith("Date Card") for n in lst]
for nid in date_cards:
    call_tool("set_layout_sizing", {"nodeId": nid, "horizontal": "FIXED", "vertical": "FIXED"})
    call_tool("resize_node", {"nodeId": nid, "width": 72, "height": 120})
print(f"[2] Date Card {len(date_cards)}개 -> FIXED 72x120")

# 4. Stage Card → FIXED width 240, HUG height
stage_cards = [n["id"] for nm, lst in by_name.items() if nm.startswith("Stage Card") for n in lst]
for nid in stage_cards:
    call_tool("set_layout_sizing", {"nodeId": nid, "horizontal": "FIXED"})
    call_tool("resize_node", {"nodeId": nid, "width": 240, "height": 150})
    call_tool("set_layout_sizing", {"nodeId": nid, "vertical": "HUG"})
print(f"[3] Stage Card {len(stage_cards)}개 -> FIXED w240 / HUG height")

# 5. My Stages Scroll → vertical HUG
for n in by_name.get("My Stages Scroll", []):
    call_tool("set_layout_sizing", {"nodeId": n["id"], "vertical": "HUG"})
    print(f"[4] My Stages Scroll {n['id']} -> vertical HUG")

# 6. bg-brand-solid 노드 색 교정 — auto-bind가 어두운 변수로 잘못 바인딩하는 버그
BRAND_SOLID_NAMES = ("Underline Bar", "Banner Card 1", "FAB",
                     "Day Circle Mon", "Day Circle Tue", "Day Circle Wed",
                     "Day Circle Thu", "Day Circle Fri")
brand_fixed = 0
for nm in BRAND_SOLID_NAMES:
    for n in by_name.get(nm, []):
        call_tool("set_fill_color", {"nodeId": n["id"], "r": 0.41569, "g": 0.0, "b": 0.87843, "a": 1})
        call_tool("set_bound_variables", {"nodeId": n["id"], "bindings": {"fills/0": "Colors/Background/bg-brand-solid"}})
        brand_fixed += 1
print(f"[5] bg-brand-solid 색 교정 {brand_fixed}건")

# 7. 레이아웃 재계산
tree2 = _collect_tree(root_id)
result = _fix_layout_and_positions(tree2)
print(f"[6] layout: {result}")
print("FINALIZE DONE")
