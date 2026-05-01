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

    def test_near_match_within_threshold(self):
        # Off by 5 in each channel = ΔRGB 15... outside 12 → None
        result = fmc._match_color((29, 34, 44, 1.0), self.idx["color_index"])
        self.assertIsNone(result)

    def test_near_match_inside_threshold(self):
        # Off by 3+3+3 = ΔRGB 9 → matches
        result = fmc._match_color((27, 32, 42, 1.0), self.idx["color_index"])
        self.assertEqual(result, "--colors-text-textPrimary")

    def test_returns_none_when_no_candidates(self):
        result = fmc._match_color((250, 250, 250, 1.0), self.idx["color_index"])
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
