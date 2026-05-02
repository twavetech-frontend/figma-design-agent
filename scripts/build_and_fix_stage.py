"""Stage Tab 전체 빌드 + 후처리 (1-shot)."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def main():
    OLD_ROOT = "16805:71838"
    LOGO_KEY = "81efeddd245e95f31a2724aa370ee54d3caf93d0"

    from figma_mcp_client import ensure_session, call_tool, parse_content, cmd_post_fix
    ensure_session()

    # 1. 기존 root 삭제 (있으면)
    print("[1/6] 기존 root 삭제…")
    try:
        content = call_tool("delete_node", {"nodeId": OLD_ROOT})
        print("  ", parse_content(content).get("texts") or "deleted")
    except Exception as e:
        print(f"  (skip) {e}")

    # 2. Blueprint 재생성
    print("\n[2/6] Blueprint 재생성…")
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts/build_stage_tab.py")], check=True)
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts/resolve_stage_light.py")], check=True)

    # 3. 빌드
    print("\n[3/6] batch_build_screen…")
    with open(os.path.join(ROOT, "scripts/blueprint_stage_tab_light.json")) as f:
        bp = json.load(f)
    bp["x"] = 1000
    bp["y"] = 0
    content = call_tool("batch_build_screen", {"blueprint": bp})
    result = parse_content(content)
    j = result.get("json") or {}
    root_id = j.get("rootId") or j.get("nodeId")
    nm = j.get("nodeMap", {})
    print(f"  rootId: {root_id}, totalNodes: {j.get('totalNodes')}, nodeMap: {len(nm)}")
    if not root_id:
        print("  ❌ 빌드 실패")
        print(result.get("texts", [])[:1])
        return

    with open("/tmp/node_map.json", "w") as f:
        json.dump(nm, f, indent=2, ensure_ascii=False)

    # 4. NavBar 로고 컴포넌트 인스턴스 교체
    print("\n[4/6] NavBar 로고 교체…")
    logo_ph_id = nm.get("Logo Placeholder")
    navbar_id = nm.get("NavBar")
    if logo_ph_id and navbar_id:
        try:
            call_tool("delete_node", {"nodeId": logo_ph_id})
            content = call_tool("create_component_instance", {"componentKey": LOGO_KEY, "x": 0, "y": 0})
            logo_id = parse_content(content).get("json", {}).get("id")
            if logo_id:
                call_tool("insert_child", {"parentId": navbar_id, "childId": logo_id, "index": 0})
                print(f"  ✅ 로고 인스턴스 {logo_id} 삽입")
        except Exception as e:
            print(f"  ⚠️ 로고 교체 실패: {e}")

    # 5. Status Bar를 root index 0으로 (자동 주입된 게 root에 안 붙은 케이스 방어)
    print("\n[5/6] Status Bar 위치 보정…")
    sb_id = nm.get("Status Bar")
    if sb_id:
        try:
            call_tool("insert_child", {"parentId": root_id, "childId": sb_id, "index": 0})
            call_tool("set_layout_positioning", {"nodeId": sb_id, "layoutPositioning": "AUTO"})
            call_tool("set_layout_sizing", {"nodeId": sb_id, "horizontal": "FILL"})
            print(f"  ✅ Status Bar {sb_id} → root[0]")
        except Exception as e:
            print(f"  ⚠️ Status Bar 보정 실패: {e}")

    # 6. post-fix (FAB/Tab Bar 자동 배치 + FILL 보정 + Status Bar bg 매칭)
    print("\n[6/6] post-fix…")
    cmd_post_fix(root_id)
    print("\n  → 추가 FAB 보정 (post-fix가 pill로 만들었을 가능성)")
    fab_id = nm.get("FAB")
    if fab_id:
        try:
            call_tool("set_layout_sizing", {"nodeId": fab_id, "horizontal": "FIXED", "vertical": "FIXED"})
            call_tool("resize_node", {"nodeId": fab_id, "width": 52, "height": 52})
        except Exception as e:
            print(f"  ⚠️ FAB resize 실패: {e}")

    print(f"\n✅ 완료. rootId={root_id}")


if __name__ == "__main__":
    main()
