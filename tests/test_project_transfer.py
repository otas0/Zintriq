"""Desktop project packages are untrusted input."""

from __future__ import annotations

import hashlib
import io
import json
import os
import struct
import tempfile
import unittest
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from desktop.sqlite_io import open_connection
from desktop.transfer import (
    LIMITS,
    Limits,
    TransferError,
    export_project,
    import_project,
    preview_package,
)
from universal_builder_core import init_universal_builder_tables
from universal_builder_runtime import render_document
from universal_builder_core import capture_project_snapshot


ROOT = Path(__file__).resolve().parents[1]
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)
JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.signaturevalue1"
LONG_RANDOM = "Aa1Bb2Cc3Dd4Ee5Ff6Gg7Hh8Ii9Jj0Kk1Ll2Mm3N"


def _dumps(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _pack(files: dict, *, stored: bool = False) -> bytes:
    payload = {name: blob if isinstance(blob, bytes) else blob.encode("utf-8") for name, blob in files.items()}
    checksums = {name: hashlib.sha256(blob).hexdigest() for name, blob in payload.items()}
    payload["checksums.json"] = json.dumps(checksums).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, blob in payload.items():
            info = zipfile.ZipInfo(filename=name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            info.flag_bits |= 0x800
            archive.writestr(info, blob)
    return buffer.getvalue()


def _minimal_files(name: str = "Demo", **overrides) -> dict:
    files = {
        "manifest.json": _dumps({
            "schema_version": 1,
            "exported_at": "2026-01-01T00:00:00Z",
            "app_version": "0.0.0",
            "project_id": "424242",
            "project_name": name,
            "requires": [],
            "migrations": [],
        }),
        "content/project.json": _dumps({
            "name": name,
            "kind": "composition",
            "description": "",
            "settings": {},
            "enabled_capabilities": [],
            "theme_reference": "",
        }),
        "content/pages.json": _dumps({"surfaces": [], "documents": [], "routes": [], "entries": [], "bindings": []}),
        "content/components.json": _dumps({"definitions": [], "instances": []}),
        "content/collections.json": _dumps([]),
        "content/workflows.json": _dumps({"documents": [], "actions": [], "interactions": [], "conditions": []}),
        "content/design.json": _dumps({"tokens": [], "variables": []}),
        "content/redactions.json": _dumps([]),
        "content/omitted.json": _dumps({}),
        "content/external_urls.json": _dumps([]),
    }
    files.update(overrides)
    return files


def _patch_uncompressed_size(blob: bytes, new_size: int) -> bytes:
    data = bytearray(blob)
    encoded = int(new_size).to_bytes(4, "little")
    start = 0
    while True:
        index = data.find(b"PK\x03\x04", start)
        if index < 0:
            break
        data[index + 22 : index + 26] = encoded
        start = index + 4
    start = 0
    while True:
        index = data.find(b"PK\x01\x02", start)
        if index < 0:
            break
        data[index + 24 : index + 28] = encoded
        start = index + 4
    return bytes(data)


class _ScriptHunter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bad = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script":
            self.bad.append(tag)
        for name, _value in attrs:
            if name.lower().startswith("on"):
                self.bad.append(name)

    def handle_data(self, data):
        self.text.append(data)


class TransferFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def new_db(self):
        path = self.root / f"db-{len(list(self.root.glob('*.db')))}.db"
        conn = open_connection(path)
        init_universal_builder_tables(conn)
        conn.commit()
        return path, conn

    def uploads(self):
        path = self.root / f"uploads-{len(list(self.root.glob('uploads-*')))}"
        path.mkdir()
        return path

    def import_bytes(self, blob, *, enable_keys=None, fail_after=None, limits=None):
        _path, conn = self.new_db()
        uploads = self.uploads()
        try:
            result = import_project(
                conn,
                blob,
                upload_dir=uploads,
                workspace_id=1,
                user_id=1,
                enable_keys=set(enable_keys or ()),
                fail_after=fail_after,
                limits=limits,
            )
        except Exception:
            conn.close()
            raise
        return conn, uploads, result


class RoundTripTests(TransferFixture):
    def _seed(self, conn, uploads: Path):
        (uploads / "pic.png").write_bytes(PNG)
        now = "2026-01-01 00:00:00"
        settings = {
            "api_key": "hunter2-secret",
            "note": LONG_RANDOM,
            "theme": "plain",
        }
        cursor = conn.execute(
            """INSERT INTO builder_projects
               (workspace_id, name, slug, kind, status, description, settings, schema_version,
                enabled_capabilities, theme_reference, created_by, updated_at)
               VALUES (1, 'My Work', 'my-work', 'composition', 'draft', ?, ?, 1, '[]', '', 1, ?)""",
            (f"Hello {JWT}", json.dumps(settings), now),
        )
        project_id = int(cursor.lastrowid)
        surface = conn.execute(
            """INSERT INTO builder_surfaces
               (project_id, surface_key, name, type, audience, base_path, settings, sort_order, updated_at)
               VALUES (?, 'web', 'Web', 'public_web', 'public', '', '{}', 0, ?)""",
            (project_id, now),
        )
        surface_id = int(surface.lastrowid)
        document = conn.execute(
            """INSERT INTO builder_documents
               (project_id, surface_id, document_key, name, type, route, status, schema, sort_order, updated_at)
               VALUES (?, ?, 'page_home', 'Home', 'page', '/home', 'active', '{}', 0, ?)""",
            (project_id, surface_id, now),
        )
        document_id = int(document.lastrowid)
        conn.execute(
            """INSERT INTO builder_nodes
               (document_id, node_key, parent_key, component_type, props, styles, sort_order, updated_at)
               VALUES (?, 'node_main', NULL, 'text', ?, '{}', 0, ?)""",
            (document_id, json.dumps({"body": "Hello page", "src": "/uploads/pic.png"}), now),
        )
        conn.execute(
            """INSERT INTO builder_data_models (project_id, model_key, name, schema, adapter, updated_at)
               VALUES (?, 'model_notes', 'Notes', '{}', 'native', ?)""",
            (project_id, now),
        )
        conn.execute(
            """INSERT INTO builder_data_records (project_id, model_key, record_key, data, status)
               VALUES (?, 'model_notes', 'row1', '{"marker":"record-marker-secret"}', 'active')""",
            (project_id,),
        )
        conn.execute(
            """INSERT INTO builder_deployments
               (project_id, environment, channel, status, public_url, configuration, updated_at)
               VALUES (?, 'production', 'web', 'active', 'https://deploy-marker.example/secret', '{}', ?)""",
            (project_id, now),
        )
        conn.execute(
            """INSERT INTO builder_actions
               (project_id, document_id, node_key, action_key, event_type, action_type, configuration, sort_order, updated_at)
               VALUES (?, ?, 'node_main', 'action_hook', 'click', 'open_page', ?, 0, ?)""",
            (
                project_id,
                document_id,
                json.dumps({
                    "url": "https://example.com/hook",
                    "callback": "https://example.com/cb?token=abcdef",
                    "webhook": "https://hooks.slack.com/services/TAAA/BBBB/CCCCSECRET",
                    "enabled": True,
                }),
                now,
            ),
        )
        conn.execute(
            """INSERT INTO builder_design_tokens
               (project_id, token_key, name, category, group_name, values_json, description, updated_at)
               VALUES (?, 'color.brand', 'Brand', 'color', '', '{"light":"#112233"}', '', ?)""",
            (project_id, now),
        )
        conn.execute(
            """INSERT INTO builder_component_definitions
               (project_id, component_key, name, root_structure, property_schema, token_dependencies, updated_at)
               VALUES (?, 'card_main', 'Card', '[]', '{}', '["color.brand"]', ?)""",
            (project_id, now),
        )
        definition_id = int(conn.execute("SELECT id FROM builder_component_definitions WHERE project_id=?", (project_id,)).fetchone()["id"])
        conn.execute(
            """INSERT INTO builder_component_instances
               (project_id, document_id, node_key, component_definition_id, overrides, updated_at)
               VALUES (?, ?, 'node_main', ?, '{}', ?)""",
            (project_id, document_id, definition_id, now),
        )
        conn.execute(
            """INSERT INTO builder_project_variables
               (project_id, variable_key, name, value_json, value_type, updated_at)
               VALUES (?, 'headline', 'Headline', ?, 'string', ?)""",
            (project_id, json.dumps("Bearer super-secret-token"), now),
        )
        conn.commit()
        return project_id

    def test_round_trip_strips_secrets_and_keeps_content(self):
        _path, conn = self.new_db()
        uploads = self.uploads()
        project_id = self._seed(conn, uploads)
        before = conn.execute("SELECT name, updated_at FROM builder_projects WHERE id=?", (project_id,)).fetchone()
        blob = export_project(conn, project_id, 1, uploads, app_version="0.1.0")
        after = conn.execute("SELECT name, updated_at FROM builder_projects WHERE id=?", (project_id,)).fetchone()
        self.assertEqual(tuple(before), tuple(after))
        from desktop.transfer import _read_zip

        unpacked = b"".join(_read_zip(blob, LIMITS).values())
        self.assertNotIn(b"hunter2-secret", unpacked)
        self.assertNotIn(b"sk_live_", unpacked)
        self.assertNotIn(JWT.encode(), unpacked)
        self.assertNotIn(b"Bearer super-secret-token", unpacked)
        self.assertNotIn(b"CCCCSECRET", unpacked)
        self.assertNotIn(b"token=abcdef", unpacked)
        self.assertNotIn(LONG_RANDOM.encode(), unpacked)
        self.assertNotIn(b"record-marker-secret", unpacked)
        self.assertNotIn(b"deploy-marker", unpacked)
        self.assertIn(b"color.brand", unpacked)
        self.assertIn("需要重新配置".encode(), unpacked)
        with self.assertRaises(TransferError) as mismatch:
            export_project(conn, project_id, 99, uploads)
        self.assertEqual(mismatch.exception.code, "not_found")
        preview = preview_package(blob)
        self.assertEqual(preview["warning"], "包内可能含个人信息")
        self.assertEqual(preview["project_name"], "My Work")
        self.assertEqual(preview["page_count"], 1)
        self.assertEqual(preview["collection_count"], 1)
        self.assertTrue(any("数据记录" in item for item in preview["ignored"]))
        urls = [url for item in preview["automations"] for url in item["external_urls"]]
        urls.extend(preview["external_urls"])
        self.assertIn("https://example.com/hook", urls)
        self.assertIn("https://hooks.slack.com", urls)
        self.assertNotIn("CCCCSECRET", " ".join(urls))
        self.assertTrue(preview["needs_reconfiguration"])
        conn.close()

        imported, imported_uploads, result = self.import_bytes(blob)
        self.assertNotEqual(result["project_id"], 424242)
        row = imported.execute("SELECT * FROM builder_projects WHERE id=?", (result["project_id"],)).fetchone()
        settings = json.loads(row["settings"])
        self.assertEqual(settings["imported_from"]["package_sha256"], hashlib.sha256(blob).hexdigest())
        self.assertIn("imported_at", settings["imported_from"])
        self.assertNotIn("424242", json.dumps(settings))
        self.assertNotIn("project_id", settings["imported_from"])
        self.assertEqual(row["status"], "draft")
        node = imported.execute(
            """SELECT props FROM builder_nodes n
               JOIN builder_documents d ON d.id=n.document_id
               WHERE d.project_id=?""",
            (result["project_id"],),
        ).fetchone()
        props = json.loads(node["props"])
        self.assertEqual(props["body"], "Hello page")
        self.assertTrue(props["src"].startswith("/uploads/"))
        self.assertNotIn("pic.png", props["src"])
        stored = imported_uploads / props["src"].rsplit("/", 1)[-1]
        self.assertEqual(stored.read_bytes(), PNG)
        action = imported.execute(
            "SELECT configuration FROM builder_actions WHERE project_id=?",
            (result["project_id"],),
        ).fetchone()
        configuration = json.loads(action["configuration"])
        self.assertIs(configuration["enabled"], False)
        self.assertEqual(imported.execute("SELECT COUNT(*) AS c FROM builder_data_records WHERE project_id=?", (result["project_id"],)).fetchone()["c"], 0)
        token = imported.execute("SELECT token_key FROM builder_design_tokens WHERE project_id=?", (result["project_id"],)).fetchone()
        self.assertEqual(token["token_key"], "color.brand")
        enabled, _uploads, enabled_result = self.import_bytes(blob, enable_keys={"action:action_hook"})
        enabled_action = json.loads(enabled.execute(
            "SELECT configuration FROM builder_actions WHERE project_id=?",
            (enabled_result["project_id"],),
        ).fetchone()["configuration"])
        self.assertIs(enabled_action["enabled"], True)
        imported.close()
        enabled.close()

    def test_same_package_twice_is_independent(self):
        _path, conn = self.new_db()
        uploads = self.uploads()
        project_id = self._seed(conn, uploads)
        blob = export_project(conn, project_id, 1, uploads, app_version="0.1.0")
        conn.close()
        empty, empty_conn = self.new_db()
        target = self.uploads()
        first = import_project(empty_conn, blob, upload_dir=target, workspace_id=1, user_id=1)
        second = import_project(empty_conn, blob, upload_dir=target, workspace_id=1, user_id=1)
        self.assertNotEqual(first["project_id"], second["project_id"])
        self.assertEqual(first["slug"], "my-work")
        self.assertEqual(second["slug"], "my-work-2")
        empty_conn.execute("UPDATE builder_projects SET name='Changed' WHERE id=?", (first["project_id"],))
        empty_conn.execute(
            """UPDATE builder_nodes SET props='{"body":"only-first"}'
               WHERE document_id IN (SELECT id FROM builder_documents WHERE project_id=?)""",
            (first["project_id"],),
        )
        empty_conn.commit()
        other = empty_conn.execute("SELECT name FROM builder_projects WHERE id=?", (second["project_id"],)).fetchone()
        other_props = json.loads(empty_conn.execute(
            """SELECT props FROM builder_nodes
               WHERE document_id IN (SELECT id FROM builder_documents WHERE project_id=?)""",
            (second["project_id"],),
        ).fetchone()["props"])
        self.assertEqual(other["name"], "My Work")
        self.assertEqual(other_props["body"], "Hello page")
        names = sorted(path.name for path in target.iterdir() if path.is_file())
        self.assertEqual(len(names), 2)
        self.assertNotEqual(names[0], names[1])
        (target / names[0]).write_bytes(b"changed-file")
        self.assertEqual((target / names[1]).read_bytes(), PNG)
        empty_conn.close()
        self.assertTrue(empty)

    def test_script_and_event_handler_do_not_execute(self):
        _path, conn = self.new_db()
        uploads = self.uploads()
        now = "2026-01-01 00:00:00"
        cursor = conn.execute(
            """INSERT INTO builder_projects
               (workspace_id, name, slug, kind, status, description, settings, schema_version, enabled_capabilities, created_by, updated_at)
               VALUES (1, 'Scripty', 'scripty', 'composition', 'draft', '', '{}', 1, '[]', 1, ?)""",
            (now,),
        )
        project_id = int(cursor.lastrowid)
        surface = conn.execute(
            """INSERT INTO builder_surfaces (project_id, surface_key, name, type, updated_at)
               VALUES (?, 'web', 'Web', 'public_web', ?)""",
            (project_id, now),
        )
        document = conn.execute(
            """INSERT INTO builder_documents
               (project_id, surface_id, document_key, name, type, route, status, updated_at)
               VALUES (?, ?, 'page_home', 'Home', 'page', '/', 'active', ?)""",
            (project_id, int(surface.lastrowid), now),
        )
        conn.execute(
            """INSERT INTO builder_nodes
               (document_id, node_key, component_type, props, styles, updated_at)
               VALUES (?, 'node_main', 'text', ?, ?, ?)""",
            (
                int(document.lastrowid),
                json.dumps({"body": "<script>alert(1)</script><img src=x onerror=alert(1)>"}),
                json.dumps({"onclick": "alert(1)", "color": "red"}),
                now,
            ),
        )
        conn.commit()
        blob = export_project(conn, project_id, 1, uploads)
        conn.close()
        imported, _uploads, result = self.import_bytes(blob)
        snapshot = capture_project_snapshot(imported, result["project_id"])
        html = render_document(snapshot, "page_home")
        self.assertIsNotNone(html)
        self.assertNotIn("<script", html.lower())
        hunter = _ScriptHunter()
        hunter.feed(html)
        self.assertEqual(hunter.bad, [])
        self.assertIn("alert(1)", "".join(hunter.text))
        stored = imported.execute("SELECT props FROM builder_nodes").fetchone()
        self.assertIn("<script>alert(1)</script>", stored["props"])
        imported.close()

    def test_chinese_path_round_trip(self):
        blob = _pack(_minimal_files("我的作品"))
        folder = self.root / "工作室 导出"
        folder.mkdir()
        target = folder / "我的作品.zintriq"
        target.write_bytes(blob)
        preview = preview_package(target.read_bytes())
        self.assertEqual(preview["project_name"], "我的作品")
        _conn, _uploads, result = self.import_bytes(target.read_bytes())
        self.assertEqual(result["name"], "我的作品")
        _conn.close()

    def test_x_access_schema_survives_round_trip(self):
        _path, conn = self.new_db()
        uploads = self.uploads()
        project_id = self._seed(conn, uploads)
        schema = {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
            "additionalProperties": False,
            "x-access": {"public_create": True, "public_read": True, "public_update": False},
        }
        conn.execute(
            "UPDATE builder_data_models SET schema=? WHERE project_id=? AND model_key=?",
            (json.dumps(schema), project_id, "model_notes"),
        )
        conn.commit()
        blob = export_project(conn, project_id, 1, uploads, app_version="0.1.0")
        conn.close()
        imported, _uploads, result = self.import_bytes(blob)
        row = imported.execute(
            "SELECT schema FROM builder_data_models WHERE project_id=? AND model_key=?",
            (result["project_id"], "model_notes"),
        ).fetchone()
        stored = json.loads(row["schema"])
        self.assertEqual(stored["x-access"]["public_create"], True)
        self.assertEqual(stored["additionalProperties"], False)
        imported.close()

    def test_failure_leaves_no_rows_or_files(self):
        blob = _pack(_minimal_files())
        _path, conn = self.new_db()
        uploads = self.uploads()
        with self.assertRaises(TransferError):
            import_project(
                conn, blob, upload_dir=uploads, workspace_id=1, user_id=1, fail_after="project",
            )
        self.assertEqual(conn.execute("SELECT COUNT(*) AS c FROM builder_projects").fetchone()["c"], 0)
        self.assertEqual(list(uploads.iterdir()), [])
        conn.close()

    def test_dangling_reference_rolls_back(self):
        files = _minimal_files()
        files["content/workflows.json"] = _dumps({
            "documents": [],
            "actions": [{
                "action_key": "action_missing",
                "document_key": "missing_doc",
                "node_key": "",
                "event_type": "click",
                "action_type": "open_page",
                "configuration": {},
                "sort_order": 0,
            }],
            "interactions": [],
            "conditions": [],
        })
        blob = _pack(files)
        _path, conn = self.new_db()
        uploads = self.uploads()
        with self.assertRaises(TransferError) as caught:
            import_project(conn, blob, upload_dir=uploads, workspace_id=1, user_id=1)
        self.assertEqual(caught.exception.code, "dangling")
        self.assertEqual(conn.execute("SELECT COUNT(*) AS c FROM builder_projects").fetchone()["c"], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) AS c FROM builder_actions").fetchone()["c"], 0)
        self.assertEqual(list(uploads.iterdir()), [])
        conn.close()

    def test_control_characters_are_removed_from_the_name(self):
        files = _minimal_files("A\x00B\nC" + ("x" * 200))
        project = json.loads(files["content/project.json"])
        project["name"] = "A\x00B\nC" + ("x" * 200)
        files["content/project.json"] = _dumps(project)
        _conn, _uploads, result = self.import_bytes(_pack(files))
        self.assertEqual(result["name"], ("ABCxxx" + ("x" * 114))[:120])
        self.assertNotIn("\n", result["name"])
        self.assertNotIn("\x00", result["name"])
        _conn.close()


class HostilePackageTests(TransferFixture):
    def assert_rejected(self, blob, code, limits=None):
        with self.assertRaises(TransferError) as caught:
            preview_package(blob, limits=limits)
        self.assertEqual(caught.exception.code, code, caught.exception.message)

    def test_duplicate_symlink_case_and_reserved_names(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("content/pages.json", b"{}")
            archive.writestr("content/pages.json", b"{}")
        self.assert_rejected(buffer.getvalue(), "duplicate_name")

        info = zipfile.ZipInfo("content/project.json")
        info.flag_bits |= 0x800
        info.external_attr = (0o120777) << 16
        info.compress_type = zipfile.ZIP_STORED
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(info, b"{}")
        self.assert_rejected(buffer.getvalue(), "symlink")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("content/pages.json", b"{}")
            archive.writestr("content/Pages.json", b"{}")
        self.assert_rejected(buffer.getvalue(), "case_conflict")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("content/CON.json", b"{}")
        self.assert_rejected(buffer.getvalue(), "reserved_name")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("content/pages.json.", b"{}")
        self.assert_rejected(buffer.getvalue(), "bad_name")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            info = zipfile.ZipInfo("content/pages.json ")
            info.flag_bits |= 0x800
            archive.writestr(info, b"{}")
        self.assert_rejected(buffer.getvalue(), "bad_name")

    def test_non_utf8_name_and_nested_archive(self):
        info = zipfile.ZipInfo("content/pages.json")
        info.compress_type = zipfile.ZIP_STORED
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(info, b"{}")
        blob = buffer.getvalue().replace(b"content/pages.json", b"content/pages.jso\xff")
        self.assert_rejected(blob, "encoding")

        nested = io.BytesIO()
        with zipfile.ZipFile(nested, "w") as archive:
            archive.writestr("inner.txt", b"hello")
        files = _minimal_files()
        files["content/pages.json"] = nested.getvalue()
        self.assert_rejected(_pack(files, stored=True), "nested_archive")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("content/extra.zip", b"hello")
        self.assert_rejected(buffer.getvalue(), "nested_archive")

    def test_declared_size_is_not_trusted(self):
        files = _minimal_files()
        blob = _pack(files, stored=True)
        lied_small = _patch_uncompressed_size(blob, 10)
        preview = preview_package(lied_small)
        self.assertEqual(preview["project_name"], "Demo")
        huge = _patch_uncompressed_size(blob, 0x7FFFFFFF)
        preview = preview_package(huge)
        self.assertEqual(preview["project_name"], "Demo")

        payload = b"{" + (b"x" * 180) + b"}"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            info = zipfile.ZipInfo("content/project.json")
            info.compress_type = zipfile.ZIP_STORED
            info.flag_bits |= 0x800
            archive.writestr(info, payload)
        declared = _patch_uncompressed_size(buffer.getvalue(), 10)
        self.assert_rejected(declared, "too_large", Limits(max_file=50, max_uncompressed=1000))

    def test_deep_json_checksum_schema_and_path(self):
        files = _minimal_files()
        deep = "1"
        for _index in range(40):
            deep = '{"a":' + deep + "}"
        files["content/pages.json"] = deep.encode("utf-8")
        self.assert_rejected(_pack(files), "json_limit")

        files = _minimal_files()
        manifest = json.loads(files["manifest.json"])
        manifest["schema_version"] = 2
        files["manifest.json"] = _dumps(manifest)
        with self.assertRaises(TransferError) as caught:
            preview_package(_pack(files))
        self.assertEqual(caught.exception.code, "schema_version")
        self.assertIn("升级", caught.exception.message)

        files = _minimal_files()
        payload = {name: blob if isinstance(blob, bytes) else blob for name, blob in files.items()}
        checksums = {name: hashlib.sha256(blob).hexdigest() for name, blob in payload.items()}
        checksums["manifest.json"] = "0" * 64
        payload["checksums.json"] = json.dumps(checksums).encode("utf-8")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, item in payload.items():
                archive.writestr(name, item)
        self.assert_rejected(buffer.getvalue(), "checksum")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../secret.json", b"{}")
        self.assert_rejected(buffer.getvalue(), "bad_path")

        info = zipfile.ZipInfo("content/project.json")
        info.flag_bits |= 0x1 | 0x800
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(info, b"{}")
        encrypted = bytearray(buffer.getvalue())
        local = encrypted.find(b"PK\x03\x04")
        self.assertGreaterEqual(local, 0)
        flag = int.from_bytes(encrypted[local + 6 : local + 8], "little") | 0x1
        encrypted[local + 6 : local + 8] = flag.to_bytes(2, "little")
        central = encrypted.find(b"PK\x01\x02")
        if central >= 0:
            flag = int.from_bytes(encrypted[central + 8 : central + 10], "little") | 0x1
            encrypted[central + 8 : central + 10] = flag.to_bytes(2, "little")
        self.assert_rejected(bytes(encrypted), "encrypted")

    def test_svg_is_rejected_and_font_is_kept(self):
        files = _minimal_files()
        files["assets/" + ("ab" * 8) + ".png"] = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
        self.assert_rejected(_pack(files, stored=True), "svg")
        files = _minimal_files()
        files["assets/" + ("cd" * 8) + ".woff"] = b"wOFF" + b"\x00" * 16
        preview = preview_package(_pack(files, stored=True))
        self.assertEqual(preview["project_name"], "Demo")

    def test_helpers_do_not_commit(self):
        for name in ("universal_builder_core.py", "universal_builder_creator.py"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn(".commit(", text)
        source = (ROOT / "desktop" / "transfer.py").read_text(encoding="utf-8")
        self.assertIn("BEGIN IMMEDIATE", source)
        self.assertIn("PRAGMA query_only=ON", source)

    def test_preview_accepts_official_dotted_keys_and_skips_empty_bindings(self):
        from universal_builder_core import create_blank_project

        _path, conn = self.new_db()
        uploads = self.uploads()
        project_id = create_blank_project(conn, 1, "Blank Work", 1)
        conn.execute(
            """INSERT INTO builder_bindings
               (project_id, document_id, node_key, binding_key, source_type, source_config, transform, updated_at)
               VALUES (?, NULL, 'missing', '', 'literal', '{}', '{}', '2026-01-01 00:00:00')""",
            (project_id,),
        )
        conn.commit()
        blob = export_project(conn, project_id, 1, uploads, app_version="0.1.0")
        preview = preview_package(blob)
        self.assertEqual(preview["project_name"], "Blank Work")
        conn.close()

    def test_reserved_document_key_records_is_rejected(self):
        files = _minimal_files()
        files["content/pages.json"] = _dumps({
            "surfaces": [],
            "documents": [{
                "document_key": "records",
                "name": "Records",
                "type": "page",
                "route": "/records",
                "nodes": [],
            }],
            "routes": [],
            "entries": [],
            "bindings": [],
        })
        with self.assertRaises(TransferError) as caught:
            preview_package(_pack(files))
        self.assertEqual(caught.exception.code, "bad_key")

    def test_unknown_action_type_is_rejected(self):
        files = _minimal_files()
        files["content/workflows.json"] = _dumps({
            "documents": [],
            "actions": [{
                "action_key": "action_hook",
                "document_key": "",
                "node_key": "",
                "event_type": "click",
                "action_type": "not_a_real_action",
                "configuration": {},
                "sort_order": 0,
            }],
            "interactions": [],
            "conditions": [],
        })
        with self.assertRaises(TransferError) as caught:
            preview_package(_pack(files))
        self.assertEqual(caught.exception.code, "bad_key")


class WebModeRouteTests(unittest.TestCase):
    def test_transfer_routes_are_404_on_the_web(self):
        if os.environ.get("ZINTRIQ_DESKTOP") == "1":
            self.skipTest("parent environment enables desktop mode")
        import app as app_module

        client = app_module.app.test_client()
        with client.session_transaction() as sess:
            sess["csrf_token"] = "csrf-transfer"
        headers = {"X-CSRF-Token": "csrf-transfer"}
        for path in (
            "/api/builder-core/transfer/export/1",
            "/api/builder-core/transfer/preview",
            "/api/builder-core/transfer/commit",
        ):
            response = client.post(path, data=b"x", headers=headers)
            self.assertEqual(response.status_code, 404, path)
        upload = client.get("/uploads/" + ("ab" * 8) + ".png")
        self.assertEqual(upload.status_code, 404)


if __name__ == "__main__":
    unittest.main()
