"""Stage Tab Blueprint의 $token() 참조를 라이트 모드 RGB로 변환."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "scripts/blueprint_stage_tab.json")
OUT = os.path.join(ROOT, "scripts/blueprint_stage_tab_light.json")


def hex_to_rgb(h):
    h = h.lstrip("#")
    return {"r": int(h[0:2], 16) / 255, "g": int(h[2:4], 16) / 255, "b": int(h[4:6], 16) / 255, "a": 1}


# Untitled UI 라이트 모드 imin 토큰 매핑 (imin-home/blueprint.json과 일치)
LIGHT = {
    "bg-primary": "#ffffff",
    "bg-secondary": "#fafafa",
    "bg-tertiary": "#f5f5f6",
    "bg-quaternary": "#e9eaeb",
    "bg-brand-primary": "#f4ebff",
    "bg-brand-secondary": "#e9d7fe",
    "bg-brand-solid": "#7700ff",
    "bg-brand-solid_hover": "#6938ef",
    "bg-success-primary": "#dcfae6",
    "bg-warning-primary": "#fef6e0",
    "bg-error-primary": "#fee4e2",
    "fg-primary": "#181a1f",
    "fg-secondary": "#414756",
    "fg-tertiary": "#717680",
    "fg-quaternary": "#94989e",
    "fg-brand-primary": "#6938ef",
    "fg-brand-secondary": "#5200b0",
    "fg-error-primary": "#d92d20",
    "fg-success-primary": "#079455",
    "fg-warning-primary": "#dc6803",
    "fg-white": "#ffffff",
    "border-primary": "#d5d7da",
    "border-secondary": "#ececed",
    "border-tertiary": "#f5f5f6",
    "border-brand": "#9b55ff",
    "border-brand-solid": "#7700ff",
}


def resolve(node):
    if isinstance(node, str):
        if node.startswith("$token(") and node.endswith(")"):
            tok = node[7:-1]
            if tok in LIGHT:
                return hex_to_rgb(LIGHT[tok])
            else:
                print(f"⚠️ 미매핑 토큰: {tok}")
                return hex_to_rgb("#ff00ff")
        return node
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            # letterSpacing: plugin expects number (PIXELS). object {value, unit} 변환
            if k == "letterSpacing" and isinstance(v, dict):
                # PERCENT → 작은 픽셀 값으로 변환 (font_size * pct/100, default font 14)
                val = v.get("value", 0)
                unit = v.get("unit", "PIXELS")
                if unit == "PERCENT":
                    out[k] = round(val * 0.14, 2)  # 14sp 기준 -2% ≈ -0.28
                else:
                    out[k] = val
            # lineHeight: plugin expects number or {value, unit} — keep as-is
            else:
                out[k] = resolve(v)
        return out
    if isinstance(node, list):
        return [resolve(x) for x in node]
    return node


with open(SRC) as f:
    bp = json.load(f)

bp = resolve(bp)

with open(OUT, "w") as f:
    json.dump(bp, f, indent=2, ensure_ascii=False)

print(f"✅ Saved {OUT}")
