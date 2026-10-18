"""CRDT merge for live Desc collaboration."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from meta.collab import integrate_plain, merge, tick, to_plain
from meta.collab.daemon import tick as daemon_tick
from meta.collab.store import join_room, publish_mailbox, pull_merged, push_plain, push_replica, replica_id, room_state, sync_mailbox


def _atom(value, typ="string"):
    return {"form": "atom", "type": typ, "value": value}


def _struct(**fields):
    return {"form": "struct", "fields": fields}


class CollabCRDTTests(unittest.TestCase):
    def test_concurrent_fields_converge(self):
        base_plain = _struct(title=_atom("Hello"), n=_atom(0, "int"))
        _clock, lamport = tick({}, "aaa")
        base = integrate_plain(None, base_plain, "aaa", lamport)
        left = integrate_plain(base, _struct(title=_atom("Alpha"), n=_atom(0, "int")), "aaa", 2)
        right = integrate_plain(base, _struct(title=_atom("Hello"), n=_atom(9, "int")), "zzz", 2)
        merged = merge(left, right)
        plain = to_plain(merged)
        self.assertEqual(plain["fields"]["title"]["value"], "Alpha")
        self.assertEqual(plain["fields"]["n"]["value"], 9)

    def test_sequence_inserts_union(self):
        a = integrate_plain(None, {"form": "sequence", "items": [_atom("one")]}, "aaa", 1)
        b = integrate_plain(None, {"form": "sequence", "items": [_atom("two")]}, "zzz", 1)
        merged = to_plain(merge(a, b))
        values = [item["value"] for item in merged["items"]]
        self.assertEqual(sorted(values), ["one", "two"])

    def test_concurrent_string_inserts_keep_both_edits(self):
        base_plain = _struct(title=_atom("Hello"))
        base = integrate_plain(None, base_plain, "aaa", 1)
        left = integrate_plain(base, _struct(title=_atom("Hallo")), "aaa", 2)
        right = integrate_plain(base, _struct(title=_atom("Hello!")), "zzz", 2)
        merged = to_plain(merge(left, right))
        self.assertEqual(merged["fields"]["title"]["value"], "Hallo!")

    def test_character_ot_transform(self):
        from meta.collab.ot import apply_ops_string, diff_ops, merge_from_base

        self.assertEqual(apply_ops_string("cat", diff_ops("cat", "cart")), "cart")
        self.assertEqual(merge_from_base("cat", "cart", "cats", "aaa", "zzz"), "carts")

    def test_store_round_trip(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        ident = replica_id(root)
        self.assertTrue(ident)
        pushed = push_plain(root, "cafe", _struct(title=_atom("Cafe")))
        self.assertEqual(pushed["plain"]["fields"]["title"]["value"], "Cafe")
        pulled = pull_merged(root, "cafe")
        self.assertEqual(pulled["plain"]["fields"]["title"]["value"], "Cafe")
        tmp.cleanup()

    def test_local_room_merges_two_replicas(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        join_room(root, "stage", "alice")
        join_room(root, "stage", "bob")
        push_replica(root, "stage", "alice", _struct(title=_atom("Alpha")))
        push_replica(root, "stage", "bob", _struct(title=_atom("Alpha!")))
        room = room_state(root, "stage")
        self.assertEqual(sorted(room["replicas"]), ["alice", "bob"])
        self.assertIn("!", room["plain"]["fields"]["title"]["value"])
        tmp.cleanup()

    def test_mailbox_syncs_two_processes(self):
        import os

        shared = tempfile.TemporaryDirectory()
        left = tempfile.TemporaryDirectory()
        right = tempfile.TemporaryDirectory()
        os.environ["ZINTRIQ_COLLAB_DIR"] = shared.name
        self.addCleanup(lambda: os.environ.pop("ZINTRIQ_COLLAB_DIR", None))
        self.addCleanup(shared.cleanup)
        self.addCleanup(left.cleanup)
        self.addCleanup(right.cleanup)
        push_plain(Path(left.name), "stage", _struct(title=_atom("PeerA")))
        synced = sync_mailbox(Path(right.name), "stage")
        self.assertTrue(synced.get("peers"))
        self.assertEqual(synced["plain"]["fields"]["title"]["value"], "PeerA")

    def test_daemon_ticks_mailbox(self):
        shared = tempfile.TemporaryDirectory()
        root = tempfile.TemporaryDirectory()
        os.environ["ZINTRIQ_COLLAB_DIR"] = shared.name
        self.addCleanup(lambda: os.environ.pop("ZINTRIQ_COLLAB_DIR", None))
        self.addCleanup(shared.cleanup)
        self.addCleanup(root.cleanup)
        push_plain(Path(root.name), "stage", _struct(title=_atom("Daemon")))
        publish_mailbox(Path(root.name), "stage")
        out = daemon_tick(Path(root.name))
        self.assertTrue(out["ok"])
        self.assertIn("presence", out)
        self.assertTrue(any(row["slug"] == "stage" for row in out["synced"]))
        self.assertIn("loopback", out)

    def test_loopback_exchanges_local_peers(self):
        from meta.collab.loopback import exchange_peers, register_peer

        left = tempfile.TemporaryDirectory()
        right = tempfile.TemporaryDirectory()
        self.addCleanup(left.cleanup)
        self.addCleanup(right.cleanup)
        push_plain(Path(left.name), "stage", _struct(title=_atom("Loop")))
        publish_mailbox(Path(left.name), "stage")
        register_peer(Path(left.name), right.name)
        exchange_peers(Path(left.name))
        synced = sync_mailbox(Path(right.name), "stage")
        self.assertEqual(synced["plain"]["fields"]["title"]["value"], "Loop")
        from meta.collab.loopback import load_clocks

        self.assertTrue(load_clocks(Path(left.name)))
        from meta.collab.loopback import mailbox_merkle

        self.assertTrue(mailbox_merkle(Path(left.name)))
        self.assertFalse(exchange_peers(Path(left.name)).get("wan"))
        self.assertIn("skew", exchange_peers(Path(left.name)))


if __name__ == "__main__":
    unittest.main()
