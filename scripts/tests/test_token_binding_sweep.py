import json
import os
import sys
import unittest

# Add scripts dir to path so we can import figma_mcp_client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as fmc

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_token_map.json")


def load_fixture():
    with open(FIXTURE_PATH) as f:
        return json.load(f)


class TestLoadTokenIndex(unittest.TestCase):
    def test_color_index_groups_same_value(self):
        idx = fmc._load_token_index(load_fixture())
        # Both grayLightMode-900 and text-textPrimary share #181d27
        key = (24, 29, 39, 1.0)  # rgba normalized to 0-255 ints + alpha float
        self.assertIn(key, idx["color_index"])
        names = [t[0] for t in idx["color_index"][key]]
        self.assertIn("--colors-text-textPrimary", names)
        self.assertIn("--colors-grayLightMode-900", names)

    def test_color_index_marks_semantic_first(self):
        idx = fmc._load_token_index(load_fixture())
        key = (24, 29, 39, 1.0)
        # semantic (text-*) should come before primitive (gray*)
        first_token, first_is_semantic = idx["color_index"][key][0]
        self.assertEqual(first_token, "--colors-text-textPrimary")
        self.assertTrue(first_is_semantic)

    def test_number_index_groups_value(self):
        idx = fmc._load_token_index(load_fixture())
        self.assertIn(8, idx["number_index"])
        self.assertIn(("--spacing-2-8px", False), idx["number_index"][8])

    def test_typography_list_resolves_references(self):
        idx = fmc._load_token_index(load_fixture())
        self.assertEqual(len(idx["typography_list"]), 1)
        ts = idx["typography_list"][0]
        self.assertEqual(ts["name"], "--display2xl-semibold")
        # Resolution succeeds when fixture has the referenced token (fontSize/10 → 72)
        self.assertEqual(ts["fontSize"], 72)
        # Unresolved reference is preserved as raw string
        self.assertEqual(ts["fontFamily"], "{Font family.font-family-display}")


class TestMatchColor(unittest.TestCase):
    def setUp(self):
        self.idx = fmc._load_token_index(load_fixture())

    def test_exact_match_picks_semantic(self):
        # #181d27 maps to text-textPrimary AND grayLightMode-900; semantic wins
        result = fmc._match_color((24, 29, 39, 1.0), self.idx["color_index"])
        self.assertEqual(result, "--colors-text-textPrimary")

    def test_near_match_outside_threshold(self):
        # Off by 5 in each channel = ΔRGB 15, outside threshold of 12 → None
        result = fmc._match_color((29, 34, 44, 1.0), self.idx["color_index"])
        self.assertIsNone(result)

    def test_near_match_at_threshold_boundary(self):
        # ΔRGB exactly 12 (12+0+0) → still matches per `dist > _COLOR_THRESHOLD`
        result = fmc._match_color((36, 29, 39, 1.0), self.idx["color_index"])
        self.assertEqual(result, "--colors-text-textPrimary")

    def test_alpha_mismatch_rejects_match(self):
        # Same RGB as text-textPrimary but very different alpha → no match
        result = fmc._match_color((24, 29, 39, 0.5), self.idx["color_index"])
        self.assertIsNone(result)

    def test_near_match_inside_threshold(self):
        # Off by 3+3+3 = ΔRGB 9 → matches
        result = fmc._match_color((27, 32, 42, 1.0), self.idx["color_index"])
        self.assertEqual(result, "--colors-text-textPrimary")

    def test_returns_none_when_no_candidates(self):
        result = fmc._match_color((250, 250, 250, 1.0), self.idx["color_index"])
        self.assertIsNone(result)


class TestMatchNumber(unittest.TestCase):
    def setUp(self):
        self.idx = fmc._load_token_index(load_fixture())

    def test_exact_match(self):
        self.assertEqual(fmc._match_number(8, self.idx["number_index"]), "--spacing-2-8px")

    def test_within_threshold(self):
        # 9 is within ±2 of 8 (closest: 8 over 12)
        self.assertEqual(fmc._match_number(9, self.idx["number_index"]), "--spacing-2-8px")

    def test_outside_threshold(self):
        # 5 is 3 away from 8, outside ±2
        self.assertIsNone(fmc._match_number(5, self.idx["number_index"]))

    def test_zero_returns_none(self):
        self.assertIsNone(fmc._match_number(0, self.idx["number_index"]))

    def test_none_returns_none(self):
        self.assertIsNone(fmc._match_number(None, self.idx["number_index"]))

    def test_at_threshold_boundary_matches(self):
        # dist == 2 should still match (strict `>` comparison)
        self.assertEqual(fmc._match_number(6, self.idx["number_index"]), "--spacing-2-8px")


class TestMatchTextstyle(unittest.TestCase):
    def setUp(self):
        # Build a richer fixture so fontSize.10 (=72) resolves
        self.token_map = load_fixture()
        # Add Font family / weight / lineHeight / letterSpacing primitives
        self.token_map["--fontFamily-fontFamilyDisplay"] = {
            "figmaPath": "Font family/font-family-display",
            "value": "Pretendard", "type": "TEXT"
        }
        self.token_map["--fontWeight-semibold"] = {
            "figmaPath": "Font weight/semibold", "value": "Semibold", "type": "TEXT"
        }
        self.token_map["--lineHeight-display2xl"] = {
            "figmaPath": "Line height/display-2xl", "value": 90, "type": "NUMBER"
        }
        self.token_map["--letterSpacing-0"] = {
            "figmaPath": "letterSpacing/0", "value": 0, "type": "NUMBER"
        }
        self.idx = fmc._load_token_index(self.token_map)

    def test_exact_typography_match(self):
        text_props = {
            "fontFamily": "Pretendard",
            "fontWeight": "Semibold",
            "fontSize": 72,
            "lineHeight": 90,
            "letterSpacing": 0,
        }
        self.assertEqual(
            fmc._match_textstyle(text_props, self.idx["typography_list"]),
            "--display2xl-semibold",
        )

    def test_near_size_within_threshold(self):
        text_props = {
            "fontFamily": "Pretendard", "fontWeight": "Semibold",
            "fontSize": 73,  # ±1 OK
            "lineHeight": 90, "letterSpacing": 0,
        }
        self.assertEqual(
            fmc._match_textstyle(text_props, self.idx["typography_list"]),
            "--display2xl-semibold",
        )

    def test_family_mismatch_rejects(self):
        text_props = {
            "fontFamily": "Roboto",  # different family
            "fontWeight": "Semibold", "fontSize": 72,
            "lineHeight": 90, "letterSpacing": 0,
        }
        self.assertIsNone(
            fmc._match_textstyle(text_props, self.idx["typography_list"])
        )

    def test_weight_mismatch_rejects(self):
        text_props = {
            "fontFamily": "Pretendard",
            "fontWeight": "Bold",  # different weight
            "fontSize": 72, "lineHeight": 90, "letterSpacing": 0,
        }
        self.assertIsNone(
            fmc._match_textstyle(text_props, self.idx["typography_list"])
        )

    def test_none_text_props_returns_none(self):
        self.assertIsNone(
            fmc._match_textstyle(None, self.idx["typography_list"])
        )

    def test_lineheight_outside_tolerance_rejects(self):
        # lineHeight 94 against candidate ts_lh=90 → diff 4 > tol 2.7 → reject
        text_props = {
            "fontFamily": "Pretendard", "fontWeight": "Semibold",
            "fontSize": 72,
            "lineHeight": 94,
            "letterSpacing": 0,
        }
        self.assertIsNone(
            fmc._match_textstyle(text_props, self.idx["typography_list"])
        )


class TestMatchShadow(unittest.TestCase):
    def setUp(self):
        token_map = load_fixture()
        # Real-shape BOXSHADOW: 8-char hex color (last 2 = alpha 0x14 ≈ 0.078),
        # x/y/blur instead of offsetX/offsetY/radius.
        token_map["--shadow-md"] = {
            "figmaPath": "Shadows/shadow-md",
            "value": {
                "color": "#0a0d1214",
                "type": "dropShadow",
                "x": 0, "y": 4, "blur": 6, "spread": -2
            },
            "type": "BOXSHADOW"
        }
        self.idx = fmc._load_token_index(token_map)

    def test_exact_shadow_match(self):
        effect = {
            "type": "DROP_SHADOW",
            "color": {"r": 0.039, "g": 0.051, "b": 0.071, "a": 0.08},
            "offset": {"x": 0, "y": 4},
            "radius": 6, "spread": -2,
        }
        self.assertEqual(
            fmc._match_shadow(effect, self.idx["shadow_list"]),
            "--shadow-md",
        )

    def test_near_shadow_within_tolerance(self):
        effect = {
            "type": "DROP_SHADOW",
            "color": {"r": 0.039, "g": 0.051, "b": 0.071, "a": 0.08},
            "offset": {"x": 0, "y": 5},  # off by 1
            "radius": 7,                   # off by 1
            "spread": -2,
        }
        self.assertEqual(
            fmc._match_shadow(effect, self.idx["shadow_list"]),
            "--shadow-md",
        )

    def test_color_mismatch_rejects(self):
        effect = {
            "type": "DROP_SHADOW",
            "color": {"r": 1.0, "g": 0, "b": 0, "a": 0.08},  # red shadow
            "offset": {"x": 0, "y": 4},
            "radius": 6, "spread": -2,
        }
        self.assertIsNone(
            fmc._match_shadow(effect, self.idx["shadow_list"])
        )

    def test_multilayer_token_skipped_at_load(self):
        token_map = load_fixture()
        token_map["--shadow-multilayer"] = {
            "figmaPath": "Shadows/shadow-lg",
            "value": [
                {"color": "#0a0d1214", "type": "dropShadow", "x": 0, "y": 12, "blur": 16, "spread": -4},
                {"color": "#0a0d1208", "type": "dropShadow", "x": 0, "y": 4, "blur": 6, "spread": -2},
            ],
            "type": "BOXSHADOW"
        }
        idx = fmc._load_token_index(token_map)
        names = [s["name"] for s in idx["shadow_list"]]
        self.assertNotIn("--shadow-multilayer", names)

    def test_none_effect_returns_none(self):
        self.assertIsNone(fmc._match_shadow(None, self.idx["shadow_list"]))


class TestWalkNodeTree(unittest.TestCase):
    def test_flatten_recursive_tree(self):
        tree = {
            "id": "1:1", "type": "FRAME",
            "children": [
                {"id": "1:2", "type": "TEXT"},
                {"id": "1:3", "type": "FRAME",
                 "children": [{"id": "1:4", "type": "TEXT"}]},
            ],
        }
        flat = fmc._flatten_node_tree(tree)
        ids = [n["id"] for n in flat]
        self.assertEqual(ids, ["1:1", "1:2", "1:3", "1:4"])

    def test_no_children_handles_gracefully(self):
        tree = {"id": "1:1", "type": "RECTANGLE"}
        flat = fmc._flatten_node_tree(tree)
        self.assertEqual([n["id"] for n in flat], ["1:1"])

    def test_empty_children_list(self):
        tree = {"id": "1:1", "type": "FRAME", "children": []}
        flat = fmc._flatten_node_tree(tree)
        self.assertEqual([n["id"] for n in flat], ["1:1"])

    def test_deep_nesting_three_levels(self):
        tree = {"id": "1:1", "type": "FRAME", "children": [
            {"id": "1:2", "type": "FRAME", "children": [
                {"id": "1:3", "type": "FRAME", "children": [
                    {"id": "1:4", "type": "TEXT"}]}]}]}
        flat = fmc._flatten_node_tree(tree)
        self.assertEqual([n["id"] for n in flat], ["1:1", "1:2", "1:3", "1:4"])

    def test_non_list_children_treated_as_leaf(self):
        tree = {"id": "1:1", "type": "FRAME", "children": "malformed"}
        flat = fmc._flatten_node_tree(tree)
        self.assertEqual([n["id"] for n in flat], ["1:1"])
        self.assertNotIn("children", flat[0])


class TestCollectBindings(unittest.TestCase):
    def setUp(self):
        # Extend fixture so typography + shadow paths can match
        token_map = load_fixture()
        token_map["--fontFamily-fontFamilyDisplay"] = {
            "figmaPath": "Font family/font-family-display",
            "value": "Pretendard", "type": "TEXT"
        }
        token_map["--fontWeight-semibold"] = {
            "figmaPath": "Font weight/semibold", "value": "Semibold", "type": "TEXT"
        }
        token_map["--lineHeight-display2xl"] = {
            "figmaPath": "Line height/display-2xl", "value": 90, "type": "NUMBER"
        }
        token_map["--letterSpacing-0"] = {
            "figmaPath": "letterSpacing/0", "value": 0, "type": "NUMBER"
        }
        token_map["--shadow-md"] = {
            "figmaPath": "Shadows/shadow-md",
            "value": {
                "color": "#0a0d1214",
                "type": "dropShadow",
                "x": 0, "y": 4, "blur": 6, "spread": -2
            },
            "type": "BOXSHADOW"
        }
        self.idx = fmc._load_token_index(token_map)

    def test_collect_color_fill(self):
        nodes = [{
            "id": "1:1", "type": "FRAME",
            "fills": [{"type": "SOLID", "color": {"r": 24/255, "g": 29/255, "b": 39/255, "a": 1}}],
        }]
        q = fmc._collect_bindings(nodes, self.idx)
        self.assertEqual(len(q["color_bindings"]), 1)
        b = q["color_bindings"][0]
        self.assertEqual(b["nodeId"], "1:1")
        self.assertEqual(b["field"], "fills")
        self.assertEqual(b["index"], 0)
        self.assertEqual(b["token_name"], "--colors-text-textPrimary")

    def test_collect_padding_and_radius(self):
        nodes = [{
            "id": "1:1", "type": "FRAME",
            "paddingTop": 8, "paddingLeft": 12, "paddingBottom": 0,  # 0 skipped
            "itemSpacing": 8,
            "cornerRadius": 12,
        }]
        q = fmc._collect_bindings(nodes, self.idx)
        fields = sorted(b["field"] for b in q["number_bindings"])
        self.assertEqual(fields, ["cornerRadius", "itemSpacing", "paddingLeft", "paddingTop"])

    def test_skip_image_fill(self):
        nodes = [{
            "id": "1:1", "type": "FRAME",
            "fills": [{"type": "IMAGE", "imageHash": "abc"}],
        }]
        q = fmc._collect_bindings(nodes, self.idx)
        self.assertEqual(q["color_bindings"], [])

    def test_unmapped_color_recorded(self):
        nodes = [{
            "id": "1:1", "type": "FRAME",
            "fills": [{"type": "SOLID", "color": {"r": 0.1, "g": 0.5, "b": 0.9, "a": 1}}],
        }]
        q = fmc._collect_bindings(nodes, self.idx)
        self.assertEqual(q["color_bindings"], [])
        self.assertEqual(len(q["unmapped"]["colors"]), 1)

    def test_collect_stroke(self):
        nodes = [{
            "id": "1:1", "type": "FRAME",
            "strokes": [{"type": "SOLID", "color": {"r": 24/255, "g": 29/255, "b": 39/255, "a": 1}}],
        }]
        q = fmc._collect_bindings(nodes, self.idx)
        self.assertEqual(len(q["color_bindings"]), 1)
        b = q["color_bindings"][0]
        self.assertEqual(b["field"], "strokes")
        self.assertEqual(b["index"], 0)
        self.assertEqual(b["token_name"], "--colors-text-textPrimary")

    def test_collect_typography_happy_path(self):
        nodes = [{
            "id": "1:T", "type": "TEXT",
            "fontFamily": "Pretendard",
            "fontWeight": "Semibold",
            "fontSize": 72,
            "lineHeight": 90,
            "letterSpacing": 0,
        }]
        q = fmc._collect_bindings(nodes, self.idx)
        self.assertEqual(len(q["textstyle_bindings"]), 1)
        self.assertEqual(q["textstyle_bindings"][0]["nodeId"], "1:T")
        self.assertEqual(q["textstyle_bindings"][0]["token_name"], "--display2xl-semibold")

    def test_collect_effect_happy_path(self):
        nodes = [{
            "id": "1:E", "type": "FRAME",
            "effects": [{
                "type": "DROP_SHADOW",
                "color": {"r": 0.039, "g": 0.051, "b": 0.071, "a": 0.078},
                "offset": {"x": 0, "y": 4},
                "radius": 6, "spread": -2,
            }],
        }]
        q = fmc._collect_bindings(nodes, self.idx)
        self.assertEqual(len(q["effect_bindings"]), 1)
        self.assertEqual(q["effect_bindings"][0]["nodeId"], "1:E")
        self.assertEqual(q["effect_bindings"][0]["index"], 0)
        self.assertEqual(q["effect_bindings"][0]["token_name"], "--shadow-md")

    def test_collect_mixed_style_text_unmapped(self):
        nodes = [{
            "id": "1:M", "type": "TEXT",
            "hasMixedStyle": True,
            "fontFamily": "Pretendard", "fontWeight": "Semibold",
        }]
        q = fmc._collect_bindings(nodes, self.idx)
        self.assertEqual(q["textstyle_bindings"], [])
        self.assertEqual(len(q["unmapped"]["typography"]), 1)
        self.assertEqual(q["unmapped"]["typography"][0]["reason"], "mixed_or_missing")


if __name__ == "__main__":
    unittest.main()
