"""Published runtime style sanitization: only token CSS keys, no raw injection."""

from __future__ import annotations

import unittest

from universal_builder_runtime import STYLE_KEYS, _safe_style


class SafeStyleTests(unittest.TestCase):
    def test_token_and_variable_values_map_to_css_vars(self):
        css = _safe_style({
            "color": "token:brand",
            "background": "variable:surface",
            "fontSize": 16,
        })
        self.assertIn("color:var(--ub-token-brand)", css)
        self.assertIn("background:var(--ub-var-surface)", css)
        self.assertIn("font-size:16", css)

    def test_unknown_keys_and_injection_are_dropped(self):
        css = _safe_style({
            "color": "red; background:url(javascript:alert(1))",
            "onclick": "alert(1)",
            "backgroundImage": "url(https://evil.example/x)",
            "customProp": "token:brand",
            "filter": "blur(2px)",
        })
        # Semicolon in value rejects the whole declaration.
        self.assertNotIn("javascript", css)
        self.assertNotIn("onclick", css)
        self.assertNotIn("background-image", css)
        self.assertNotIn("customProp", css)
        self.assertNotIn("--ub-token-brand", css)
        self.assertIn("filter:blur(2px)", css)
        for key in STYLE_KEYS:
            self.assertNotEqual(key.lower(), "onclick")


if __name__ == "__main__":
    unittest.main()
