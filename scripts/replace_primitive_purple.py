"""Replace _Primitives Purple 2 / Gray scale raw colors with DS semantic
brand/fg equivalents. Reads unmapped-tokens-{root}.json (output of
post-fix step 9) and rewrites each unmapped fill/stroke to its semantic raw
value, then re-runs token-bind.
"""
import json
import sys
import subprocess

# raw RGB (0-255) → semantic raw RGB (0-255)
# Each entry: source primitive → target semantic token raw
COLOR_REMAP = {
    # Brand purple (_Primitives Purple 2 → Color modes brand semantics)
    (89, 37, 220):  ((82, 0, 176),    "text-brand-secondary    #5200b0"),
    (105, 56, 239): ((119, 0, 255),   "bg-brand-solid          #7700ff"),
    (122, 90, 248): ((155, 85, 255),  "fg-brand-secondary      #9b55ff"),
    (62, 28, 150):  ((52, 0, 120),    "bg-brand-section        #340078"),
    (235, 233, 254):((244, 236, 255), "bg-brand-primary        #f4ecff"),
    (217, 214, 254):((230, 212, 255), "bg-brand-secondary      #e6d4ff"),
    (74, 31, 184):  ((82, 0, 176),    "bg-brand-section_subtle #5200b0"),
    # Gray light-mode → fg/text semantics
    (24, 29, 39):   ((44, 55, 68),    "fg-primary              #2c3744"),  # #181d27 → fg-primary
    (65, 70, 81):   ((44, 55, 68),    "fg-primary              #2c3744"),  # #414651 → fg-primary
    (83, 88, 98):   ((89, 96, 105),   "fg-secondary_hover      #596069"),  # #535862 → fg-secondary_hover
    (113, 118, 128):((104, 112, 121), "fg-secondary            #687079"),  # #717680 → fg-secondary
    # Error red
    (240, 68, 56):  ((217, 45, 32),   "bg-error-solid_hover    #d92d20"),  # #f04438 → bg-error-solid_hover (also text-error)
    (217, 45, 32):  ((217, 45, 32),   "text-error-primary      #d92d20"),  # #d92d20 stays
    # Warning orange/yellow
    (181, 71, 8):   ((181, 71, 8),    "utility-warning-700     #b54708"),  # already semantic in Component colors
    (247, 144, 9):  ((247, 144, 9),   "fg-warning-secondary    #f79009"),
    (220, 104, 3):  ((220, 104, 3),   "fg-warning-primary      #dc6803"),
    (254, 200, 75): ((254, 200, 75),  "utility-warning-300     #fec84b"),
}


def call_tool(name, params):
    """Invoke an MCP tool via the figma_mcp_client.py CLI and return stdout."""
    res = subprocess.run(
        ["python3", "scripts/figma_mcp_client.py", "call", name, json.dumps(params)],
        capture_output=True, text=True, cwd="/Users/julee/imin/figma-design-agent",
    )
    return res.stdout, res.stderr


def main():
    if len(sys.argv) < 2:
        print("usage: replace_primitive_purple.py <root_node_id>")
        sys.exit(1)
    root_id = sys.argv[1]
    safe_root = root_id.replace(":", "_").replace("/", "_")
    report_path = f"/tmp/unmapped-tokens-{safe_root}.json"
    rep = json.load(open(report_path))
    colors = rep.get("colors", [])
    if not colors:
        print(f"no unmapped colors in {report_path}")
        return

    # Group by node so we can fetch its strokeWeight once
    nodes = {}
    for entry in colors:
        nid = entry.get("nodeId")
        field = entry.get("field")
        rgba = tuple(entry.get("rgba", [])[:3])
        if not nid or not field or len(rgba) != 3:
            continue
        nodes.setdefault(nid, {"fills": [], "strokes": []})[field].append((entry.get("index", 0), rgba))

    print(f"=== {len(colors)} unmapped colors across {len(nodes)} nodes ===")

    fixed_fills = 0
    fixed_strokes = 0
    skipped = 0
    unknown_colors = set()

    for nid, fields in nodes.items():
        # Fetch node info once for strokeWeight
        weight = None
        if fields["strokes"]:
            out, _ = call_tool("get_node_info", {"nodeId": nid, "depth": 0})
            try:
                # Strip warnings, find first JSON
                lines = [l for l in out.splitlines() if not l.startswith("/Users") and "warnings" not in l.lower()]
                joined = "\n".join(lines)
                idx = joined.find("{")
                if idx >= 0:
                    info = json.loads(joined[idx:])
                    weight = info.get("strokeWeight", 1)
                    if not isinstance(weight, (int, float)):
                        weight = 1
            except Exception:
                weight = 1

        for field, items in fields.items():
            for idx, rgba in items:
                if rgba not in COLOR_REMAP:
                    unknown_colors.add(rgba)
                    skipped += 1
                    continue
                new_rgb, label = COLOR_REMAP[rgba]
                r, g, b = (v / 255.0 for v in new_rgb)
                if field == "fills":
                    out, err = call_tool("set_fill_color", {"nodeId": nid, "r": r, "g": g, "b": b, "a": 1})
                    fixed_fills += 1
                elif field == "strokes":
                    params = {"nodeId": nid, "r": r, "g": g, "b": b, "a": 1, "strokeWeight": weight or 1}
                    out, err = call_tool("set_stroke_color", params)
                    fixed_strokes += 1
                if "Error" in (out or "") or "Error" in (err or ""):
                    print(f"  ⚠️ {nid} {field}: {(err or out).strip()[:100]}")

    print(f"\n=== applied: fills={fixed_fills}, strokes={fixed_strokes}, skipped={skipped} ===")
    if unknown_colors:
        print("unknown raw colors (no mapping):")
        for c in unknown_colors:
            print(f"  rgba={c}")


if __name__ == "__main__":
    main()
