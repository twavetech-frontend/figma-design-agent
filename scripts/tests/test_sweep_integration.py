import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as fmc


class TestBindSemanticTokensSmoke(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def fake_call_tool(name, args, msg_id=1):
            self.calls.append((name, args))
            if name == "get_node_info":
                # Minimal rendered tree — one frame with a fill that should
                # match a real token (#181d27 → text-textPrimary)
                return [{"text": '{"id": "1:1", "type": "FRAME", '
                                  '"paddingTop": 8, '
                                  '"fills": [{"type":"SOLID","color":{"r":0.094,"g":0.114,"b":0.153,"a":1}}], '
                                  '"children": []}'}]
            return [{"text": '{"success": true}'}]
        self._orig = fmc.call_tool
        fmc.call_tool = fake_call_tool

    def tearDown(self):
        fmc.call_tool = self._orig

    def test_end_to_end_pass(self):
        counts = fmc._bind_semantic_tokens("1:1")
        # Should issue at least one batch_bind_variables call
        bind_calls = [c for c in self.calls if c[0] == "batch_bind_variables"]
        self.assertTrue(len(bind_calls) >= 1, f"calls so far: {self.calls}")
        self.assertNotIn("skipped", counts)
        # Numbers count should pick up paddingTop=8 (matches --spacing-2-8px)
        self.assertGreaterEqual(counts.get("numbers", 0), 1)


if __name__ == "__main__":
    unittest.main()
