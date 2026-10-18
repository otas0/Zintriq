"""Decisions: visual query, connectors, compile kernels, plugin catalog."""

from __future__ import annotations

import json
import unittest

from meta.boundary import reset_for_tests
from meta.description import atom, struct
from meta.instantiation import instantiate
from meta.query import QueryError, visual_query
from meta.runtime.connectors import ConnectorError, allow
from meta.runtime.kernels import manhattan_route, route_drc
from plugin_catalog import PluginError, catalog, fetch_store, hosted_catalog, load_remote, reset_reviews, review, sign_pack, submit, validate_manifest


class DecisionTests(unittest.TestCase):
    def setUp(self):
        reset_for_tests()

    def tearDown(self):
        reset_for_tests()

    def test_visual_query_rejects_sql_ops(self):
        rows = [{"name": "a", "n": 1}, {"name": "b", "n": 2}]
        self.assertEqual(len(visual_query(rows, {"op": "eq", "field": "name", "value": "a"})), 1)
        with self.assertRaises(QueryError):
            visual_query(rows, {"op": "raw", "field": "name"})
        with self.assertRaises(QueryError):
            visual_query(rows, {"op": "eq", "field": "a;drop"})

    def test_connector_whitelist(self):
        self.assertTrue(allow("https://example.com/x").startswith("https://"))
        with self.assertRaises(ConnectorError):
            allow("mongodb://localhost")
        with self.assertRaises(ConnectorError):
            allow("redis://x")

    def test_instantiate_compiles_domain_and_device_jobs(self):
        scene = struct(kind=atom("string", value="vr.space", has_value=True), ipd=atom("float", value=64, has_value=True))
        art = instantiate(scene, slug="vr-room")
        body = json.loads(art.payload)
        self.assertIn("compiled", body)
        self.assertEqual(body["compiled"]["kind"], "vr.space")
        job = struct(kind=atom("string", value="print3d.job", has_value=True), layer=atom("float", value=0.2, has_value=True))
        device = instantiate(job, slug="print-job")
        dbody = json.loads(device.payload)
        self.assertIn("gcode", dbody["compiled"])

    def test_route_same_layer_drc_and_film_edl(self):
        traces = [manhattan_route(0, 0, 10, 0, layer=0), manhattan_route(0, 1, 10, 1, layer=0)]
        self.assertTrue(route_drc(traces, min_gap=4))
        traces_ok = [manhattan_route(0, 0, 10, 0, layer=0), manhattan_route(0, 1, 10, 1, layer=1)]
        self.assertFalse(route_drc(traces_ok, min_gap=4))

    def test_plugin_catalog(self):
        rows = catalog()
        ids = {row["id"] for row in rows}
        self.assertIn("official-scene", ids)
        self.assertIn("official-film", ids)
        self.assertIn("official-circuit", ids)
        self.assertIn("community-marks", ids)
        self.assertNotIn("community-pending", ids)
        pending = {row["id"] for row in catalog(include_pending=True)}
        self.assertIn("community-pending", pending)
        self.assertGreaterEqual(len(rows), 28)

    def test_third_party_review_and_sandbox(self):
        reset_reviews()
        self.addCleanup(reset_reviews)
        with self.assertRaises(PluginError):
            validate_manifest({"id": "community-bad", "name": "x", "origin": "third", "code": "eval(1)"})
        submitted = submit({"id": "community-extra", "name": "Extra"})
        self.assertEqual(submitted["status"], "pending")
        ids = {row["id"] for row in catalog()}
        self.assertNotIn("community-extra", ids)
        review("community-extra", "approved")
        self.assertIn("community-extra", {row["id"] for row in catalog()})

    def test_signed_remote_catalog(self):
        import tempfile
        from pathlib import Path

        reset_reviews()
        self.addCleanup(reset_reviews)
        pack = sign_pack({"id": "remote-one", "name": "Remote", "origin": "third", "status": "approved", "file": "remote-one.json"})
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "catalog.json"
        path.write_text(json.dumps({"packs": [pack]}), encoding="utf-8")
        ids = {row["id"] for row in catalog(remote_path=str(path))}
        self.assertIn("remote-one", ids)
        with self.assertRaises(PluginError):
            load_remote(str(path.with_name("missing.json")))
        store = hosted_catalog()
        self.assertEqual(store["kind"], "store")
        self.assertEqual(store["protocol"], 7)
        self.assertTrue(store.get("digest"))
        self.assertTrue(store.get("etag"))
        self.assertTrue(store.get("signed"))
        self.assertTrue(store.get("mirror"))
        from plugin_catalog import load_mirror, mirror_catalog

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        mirror_catalog(Path(tmp.name), store)
        self.assertEqual(load_mirror(Path(tmp.name))["protocol"], 7)
        from plugin_catalog import catalog_delta, queue_pack, record_install, installed_index, revoke_pack, signed_index, stamp_plugin, uninstall_plugin, unlocked_installs, view_unlocked

        record_install(Path(tmp.name), "official-scene")
        self.assertIn("official-scene", installed_index(Path(tmp.name)))
        delta = catalog_delta(store, hosted_catalog())
        self.assertEqual(delta["protocol"], 7)
        self.assertIn("official-scene", queue_pack(Path(tmp.name), "official-scene"))
        self.assertEqual(signed_index(Path(tmp.name))["protocol"], 7)
        self.assertIn("official-scene", revoke_pack(Path(tmp.name), "official-scene"))
        uninstall_plugin(Path(tmp.name), "official-scene", delete=False)
        stamped = stamp_plugin(name="Local Scene", form="Scene", data_root=Path(tmp.name))
        ident = stamped["pack"]["id"]
        self.assertFalse(stamped.get("replaced"))
        self.assertIn(ident, installed_index(Path(tmp.name)))
        self.assertTrue(view_unlocked("scene", unlocked_installs(Path(tmp.name))))
        again = stamp_plugin(
            name="Local Scene",
            form="Scene",
            document={"form": "atom", "type": "string", "value": "v2", "has_value": True},
            data_root=Path(tmp.name),
        )
        self.assertTrue(again["replaced"])
        self.assertEqual(again["pack"]["id"], ident)
        self.assertEqual((again["pack"].get("document") or {}).get("value"), "v2")
        keep = stamp_plugin(name="Local Scene", form="AI", data_root=Path(tmp.name))
        self.assertTrue(keep["replaced"])
        self.assertEqual(keep["pack"]["id"], ident)
        self.assertEqual(keep["pack"]["form"], "AI")
        self.assertEqual((keep["pack"].get("document") or {}).get("value"), "v2")
        disabled = uninstall_plugin(Path(tmp.name), ident, delete=False)
        self.assertTrue(disabled["disabled"])
        self.assertFalse(disabled["deleted"])
        self.assertNotIn(ident, installed_index(Path(tmp.name)))
        self.assertFalse(view_unlocked("scene", unlocked_installs(Path(tmp.name))))
        self.assertFalse(view_unlocked("code", []))
        self.assertFalse(view_unlocked("visual", []))
        self.assertTrue((Path(tmp.name) / "plugins" / stamped["pack"]["file"]).is_file())
        record_install(Path(tmp.name), ident)
        removed = uninstall_plugin(Path(tmp.name), ident, delete=True)
        self.assertTrue(removed["deleted"])
        self.assertFalse((Path(tmp.name) / "plugins" / stamped["pack"]["file"]).is_file())
        other = stamp_plugin(name="Other Scene", form="Scene", data_root=Path(tmp.name))
        self.assertFalse(other.get("replaced"))
        self.assertNotEqual(other["pack"]["id"], ident)
        ids = {row["id"] for row in fetch_store(str(path))}
        self.assertIn("remote-one", ids)
        with self.assertRaises(PluginError):
            fetch_store("https://example.com/catalog.json")


if __name__ == "__main__":
    unittest.main()
