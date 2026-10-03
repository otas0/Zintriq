"""S2 tracker and S4 personal-tool paths. Cases turn green in K2–K6."""

from __future__ import annotations

import unittest


class TrackerScenarioTests(unittest.TestCase):
    @unittest.expectedFailure
    def test_s2_blank_project_form_writes_validated_record(self):
        self.fail("needs K2 schema validation and K3 public invoke")

    @unittest.expectedFailure
    def test_s2_public_detail_and_live_list(self):
        self.fail("needs K4 /build/<slug>/records/<model>/<record> and live repeater")

    @unittest.expectedFailure
    def test_s2_anonymous_limits_and_csp(self):
        self.fail("needs K4 rate limit, body cap, and published CSP")


class PersonalToolScenarioTests(unittest.TestCase):
    @unittest.expectedFailure
    def test_s4_personal_workspace_has_no_store(self):
        self.fail("needs K5 workspaces.type=personal without ensure_workspace_store")

    @unittest.expectedFailure
    def test_s4_publish_is_build_url_not_hybrid_home(self):
        self.fail("needs K5 publish assertions for blank personal projects")


if __name__ == "__main__":
    unittest.main()
