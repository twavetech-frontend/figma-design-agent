"""레이아웃 재배치만 실행 — post-fix의 FILL 단계를 건너뛰고
Tab Bar/FAB ABSOLUTE 배치 + 루트 높이만 재계산한다.
(post-fix 전체는 캐로셀 카드를 FILL로 망가뜨리므로 layout 단계만 호출)

사용법: python fix_layout.py <rootNodeId>
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figma_mcp_client import ensure_session, _collect_tree, _fix_layout_and_positions

root_id = sys.argv[1]
ensure_session()
tree = _collect_tree(root_id)
result = _fix_layout_and_positions(tree)
print("LAYOUT RESULT:", result)
