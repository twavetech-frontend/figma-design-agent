"""Avatar Scroller를 DS Avatar 컴포넌트 인스턴스로 재빌드."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from figma_mcp_client import ensure_session, call_tool, parse_content

WHITE = {"r": 1, "g": 1, "b": 1, "a": 1}

# DS Avatar lg variants (48px)
AVATAR_LG_PLACEHOLDER = "642f1306f91d8ffc0b614f2642bbb76584efa5f3"            # Size=lg, Placeholder=True
AVATAR_LG_VERIFIED = "722058ac875ca86b5ee8df556a3c2a3d83cb4f54"               # Size=lg, Status=Verified


def avatar_item(name, lv, component_key):
    return {
        "name": f"Avatar Item {name}-{lv}",
        "type": "frame",
        "layoutSizingHorizontal": "FIXED",
        "width": 64,
        "autoLayout": {
            "layoutMode": "VERTICAL",
            "primaryAxisAlignItems": "CENTER",
            "counterAxisAlignItems": "CENTER",
            "itemSpacing": 6,
        },
        "children": [
            {
                "name": f"DS Avatar {name}-{lv}",
                "type": "instance",
                "componentKey": component_key,
                "width": 48,
                "height": 48,
            },
            {
                "name": "Text Group",
                "type": "frame",
                "layoutSizingHorizontal": "FILL",
                "autoLayout": {
                    "layoutMode": "VERTICAL",
                    "primaryAxisAlignItems": "CENTER",
                    "counterAxisAlignItems": "CENTER",
                    "itemSpacing": 1,
                },
                "children": [
                    {
                        "name": "avatar-name",
                        "type": "text",
                        "layoutSizingHorizontal": "FILL",
                        "text": name,
                        "fontSize": 11,
                        "fontWeight": 700,
                        "fontFamily": "Pretendard",
                        "fontColor": {"r": 0.094, "g": 0.102, "b": 0.122, "a": 1},
                        "textAlignHorizontal": "CENTER",
                        "textAutoResize": "TRUNCATE",
                    },
                    {
                        "name": "avatar-lv",
                        "type": "text",
                        "text": f"lv.{lv}",
                        "fontSize": 10,
                        "fontWeight": 500,
                        "fontFamily": "Pretendard",
                        "fontColor": {"r": 0.58, "g": 0.6, "b": 0.62, "a": 1},
                        "textAlignHorizontal": "CENTER",
                    },
                ],
            },
        ],
    }


avatar_section = {
    "name": "Avatar Scroller",
    "type": "frame",
    "width": 393,
    "fill": WHITE,
    "autoLayout": {
        "layoutMode": "HORIZONTAL",
        "counterAxisAlignItems": "CENTER",
        "itemSpacing": 12,
        "paddingTop": 8,
        "paddingBottom": 18,
        "paddingLeft": 20,
        "paddingRight": 20,
        "clipsContent": True,
    },
    "children": [
        # Add Button
        {
            "name": "Add Avatar Button",
            "type": "frame",
            "width": 64,
            "autoLayout": {
                "layoutMode": "VERTICAL",
                "primaryAxisAlignItems": "CENTER",
                "counterAxisAlignItems": "CENTER",
                "itemSpacing": 6,
            },
            "children": [
                {
                    "name": "Add Circle",
                    "type": "frame",
                    "width": 48, "height": 48,
                    "autoLayout": {
                        "layoutMode": "HORIZONTAL",
                        "primaryAxisAlignItems": "CENTER",
                        "counterAxisAlignItems": "CENTER",
                    },
                    "fill": WHITE,
                    "stroke": {"r": 0.835, "g": 0.843, "b": 0.855, "a": 1},
                    "strokeWeight": 1.5,
                    "dashPattern": [4, 4],
                    "cornerRadius": 999,
                    "children": [
                        {"name": "plus-icon", "type": "icon", "iconName": "plus",
                         "size": 22, "iconColor": {"r": 0.58, "g": 0.6, "b": 0.62, "a": 1}}
                    ],
                },
                {
                    "name": "add-label", "type": "text",
                    "text": "추가",
                    "fontSize": 11, "fontWeight": 500,
                    "fontFamily": "Pretendard",
                    "fontColor": {"r": 0.58, "g": 0.6, "b": 0.62, "a": 1},
                    "textAlignHorizontal": "CENTER",
                },
            ],
        },
        # Divider
        {
            "name": "Avatar Divider",
            "type": "rectangle",
            "width": 1, "height": 56,
            "fill": {"r": 0.925, "g": 0.929, "b": 0.929, "a": 1},
        },
        avatar_item("닉네임여덟자까지", 1202, AVATAR_LG_PLACEHOLDER),
        avatar_item("닉네임여덟자까지", 39, AVATAR_LG_VERIFIED),
        avatar_item("닉네임여덟자까지", 492, AVATAR_LG_PLACEHOLDER),
        avatar_item("닉네임여덟자까지", 77, AVATAR_LG_PLACEHOLDER),
    ],
}


def main():
    ensure_session()

    ROOT_ID = "16805:71838"
    OLD_AVATAR_ID = "16805:71894"

    # 1. Delete old Avatar Scroller
    print("[1/3] Deleting old Avatar Scroller…")
    content = call_tool("delete_node", {"nodeId": OLD_AVATAR_ID})
    print("  ", parse_content(content).get("texts") or "deleted")

    # 2. Build new Avatar Scroller as standalone root (no parentId — bug workaround)
    print("\n[2/3] Building new Avatar Scroller with DS Avatar instances…")
    avatar_section["x"] = 1500
    avatar_section["y"] = 0
    content = call_tool("batch_build_screen", {"blueprint": avatar_section})
    result = parse_content(content)
    j = result.get("json") or {}
    new_id = j.get("rootId") or j.get("nodeId")
    print(f"  new Avatar Scroller: {new_id}")
    if not new_id:
        print("  RAW:", result.get("texts")[:1])
        return

    # Save new nodeMap
    if j.get("nodeMap"):
        with open("/tmp/node_map_avatar.json", "w") as f:
            json.dump(j["nodeMap"], f, indent=2, ensure_ascii=False)

    # 3. Move new Avatar Scroller to index 4 in root (Status Bar 0, NavBar 1, Category 2, Stepper 3, Avatar 4)
    print("\n[3/3] Reordering to index 4 in root…")
    content = call_tool("insert_child", {
        "parentId": ROOT_ID,
        "childId": new_id,
        "index": 4,
    })
    print("  ", parse_content(content).get("json"))

    # Set FILL horizontal
    call_tool("set_layout_sizing", {"nodeId": new_id, "horizontal": "FILL"})

    print("\n✅ Avatar Scroller 재빌드 완료")


if __name__ == "__main__":
    main()
