"""Seat limits for team collaboration."""

from __future__ import annotations

import sqlite3
import unittest

from billing_seats import invite_member, seat_limit_for_plan, seats_used


class BillingSeatsTests(unittest.TestCase):
    def test_team_can_invite_until_limit(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        invite_member(conn, 1, 2, plan="team")
        self.assertEqual(seats_used(conn, 1), 2)
        self.assertEqual(seat_limit_for_plan("personal"), 1)
        with self.assertRaises(ValueError):
            invite_member(conn, 1, 3, plan="personal")


if __name__ == "__main__":
    unittest.main()
