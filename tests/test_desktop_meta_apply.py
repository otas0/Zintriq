"""Desktop host applies web_build artifacts to local /build/<slug>."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("SECRET_KEY", "test-desktop-meta")

from meta.boundary import Boundary, boundary_to_desc
from meta.description import atom, struct, to_json
from meta.instantiation import software_page, software_site, software_system
from meta.simulation import StateMachine, Transition, machine_to_desc


class DesktopMetaApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module

        cls.app_module = app_module
        cls.app = app_module.app
        cls.app.config["TESTING"] = True
        with cls.app.app_context():
            app_module.init_db()

    def setUp(self):
        from builder_http_support import application_client, auth_headers, login_editor

        self.data_dir = Path(tempfile.mkdtemp(prefix="zintriq-meta-art-"))
        os.environ["ZINTRIQ_DATA_DIR"] = str(self.data_dir)
        self.client = application_client(self.app)
        self.user_id, self.workspace_id, self.csrf = login_editor(self.client, self.app_module)
        self.headers = auth_headers(self.csrf)

    def tearDown(self):
        from builder_http_support import disable_application_host
        from plugin_catalog import reset_reviews

        disable_application_host()
        os.environ.pop("ZINTRIQ_DATA_DIR", None)
        reset_reviews()

    def test_instantiate_writes_local_artifact_and_build_page(self):
        machine = StateMachine(
            state="idle",
            transitions=(Transition("idle", "start", "running"),),
        )
        created = self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "pump-page",
                "events": ["start"],
                "description": json.loads(to_json(machine_to_desc(machine))),
            }),
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True)[:400])
        body = created.get_json()
        self.assertEqual(body["public_url"], "/build/pump-page")
        stored = self.data_dir / "artifacts" / "pump-page.json"
        self.assertTrue(stored.is_file())
        listed = self.client.get("/api/builder-core/meta/artifacts", headers=self.headers)
        self.assertEqual(listed.status_code, 200)
        slugs = {item["slug"] for item in listed.get_json()["artifacts"]}
        self.assertIn("pump-page", slugs)
        page = self.client.get("/build/pump-page/home")
        self.assertEqual(page.status_code, 200, page.get_data(as_text=True)[:300])
        html = page.get_data(as_text=True)
        self.assertIn("running", html)
        self.assertIn('data-boundary="software.page"', html)
        self.assertIn('data-machine-state="running"', html)
        self.assertNotIn('"public_url": "/build/pump-page"', html)
        self.assertIn("text/html", page.headers.get("Content-Type", ""))
        self.assertIn("script-src 'self'", page.headers.get("Content-Security-Policy", ""))

    def test_document_page_renders_on_build(self):
        created = self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "station-guide",
                "description": json.loads(to_json(software_page(
                    title="Station guide",
                    body=("Wear gloves.",),
                ))),
            }),
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True)[:400])
        page = self.client.get("/build/station-guide/home")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200, html[:300])
        self.assertIn("<h1>Station guide</h1>", html)
        self.assertIn("<p>Wear gloves.</p>", html)
        self.assertIn('data-page-kind="software.page"', html)

    def test_boundary_description_builds_on_desktop(self):
        created = self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "lab-gate",
                "description": json.loads(to_json(boundary_to_desc(Boundary(
                    id="lab.gate",
                    name="Lab gate",
                    kind="software",
                    instantiation_target="web_build",
                    meta_level=0,
                )))),
            }),
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True)[:400])
        page = self.client.get("/build/lab-gate/home")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200, html[:400])
        self.assertIn('data-page-kind="meta.boundary"', html)
        self.assertIn('data-boundary="lab.gate"', html)
        self.assertIn("Lab gate", html)
        self.assertIn("web_build", html)

    def test_instantiate_follows_boundary_target(self):
        created = self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "lab-spec",
                "description": json.loads(to_json(boundary_to_desc(Boundary(
                    id="lab.spec",
                    name="Lab spec",
                    kind="software",
                    instantiation_target="desc",
                    meta_level=0,
                )))),
            }),
        )
        body = created.get_json()
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True)[:400])
        self.assertEqual(body["target"], "desc")
        self.assertNotIn("zip_url", body)
        page = self.client.get("/build/lab-spec/home")
        text = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200, text[:400])
        self.assertIn("application/json", page.content_type)
        data = json.loads(text)
        self.assertEqual(data["fields"]["id"]["value"], "lab.spec")
        listing = self.client.get("/studio")
        html = listing.get_data(as_text=True)
        self.assertIn("lab-spec", html)
        self.assertIn("<span>desc</span>", html)

    def test_preview_follows_boundary_target(self):
        preview = self.client.post(
            "/api/builder-core/meta/preview",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "lab-spec-preview",
                "description": json.loads(to_json(boundary_to_desc(Boundary(
                    id="lab.spec",
                    name="Lab spec",
                    kind="software",
                    instantiation_target="desc",
                    meta_level=0,
                )))),
            }),
        )
        payload = preview.get_json()
        self.assertEqual(preview.status_code, 200, preview.get_data(as_text=True)[:400])
        self.assertEqual(payload["target"], "desc")
        self.assertIn('data-page-kind="desc"', payload["page_html"])
        self.assertIn("lab.spec", payload["page_html"])
        self.assertNotIn('data-page-kind="meta.boundary"', payload["page_html"])
        self.assertFalse((self.data_dir / "artifacts" / "lab-spec-preview.json").exists())

    def test_system_description_builds_on_desktop(self):
        created = self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-sys",
                "description": json.loads(to_json(software_system(
                    title="Plant",
                    parts=(
                        ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                        ("gate", "Gate", boundary_to_desc(Boundary(
                            id="plant.gate",
                            name="Plant gate",
                            kind="software",
                            instantiation_target="web_build",
                            meta_level=0,
                        ))),
                    ),
                ))),
            }),
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True)[:400])
        home = self.client.get("/build/plant-sys/home")
        html = home.get_data(as_text=True)
        self.assertEqual(home.status_code, 200, html[:400])
        self.assertIn('data-page-kind="meta.system"', html)
        self.assertIn("Plant home.", html)
        gate = self.client.get("/build/plant-sys/gate")
        gate_html = gate.get_data(as_text=True)
        self.assertEqual(gate.status_code, 200, gate_html[:400])
        self.assertIn('data-part-kind="meta.boundary"', gate_html)
        self.assertIn('data-boundary="plant.gate"', gate_html)

    def test_system_desc_part_served_as_json(self):
        created = self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-mix",
                "description": json.loads(to_json(software_system(
                    title="Plant",
                    parts=(
                        ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                        ("spec", "Spec", boundary_to_desc(Boundary(
                            id="plant.spec",
                            name="Plant spec",
                            kind="software",
                            instantiation_target="desc",
                            meta_level=0,
                        ))),
                    ),
                ))),
            }),
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True)[:400])
        spec = self.client.get("/build/plant-mix/spec")
        body = spec.get_data(as_text=True)
        self.assertEqual(spec.status_code, 200, body[:400])
        self.assertIn("application/json", spec.content_type)
        data = json.loads(body)
        self.assertEqual(data["fields"]["kind"]["value"], "meta.boundary")
        self.assertEqual(data["fields"]["id"]["value"], "plant.spec")
        home = self.client.get("/build/plant-mix/home")
        self.assertEqual(home.status_code, 200)
        self.assertIn("text/html", home.content_type)

    def test_system_site_part_serves_all_pages(self):
        created = self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-guide",
                "description": json.loads(to_json(software_system(
                    title="Plant",
                    parts=(
                        ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                        (
                            "guide",
                            "Guide",
                            software_site(
                                title="Guide",
                                pages=(
                                    ("home", "Overview", ("Wear gloves.",)),
                                    ("about", "About", ("Station history.",)),
                                ),
                            ),
                        ),
                    ),
                ))),
            }),
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True)[:400])
        overview = self.client.get("/build/plant-guide/guide")
        html = overview.get_data(as_text=True)
        self.assertEqual(overview.status_code, 200, html[:400])
        self.assertIn("Wear gloves.", html)
        about = self.client.get("/build/plant-guide/guide-about")
        about_html = about.get_data(as_text=True)
        self.assertEqual(about.status_code, 200, about_html[:400])
        self.assertIn("Station history.", about_html)

    def test_system_nested_site_page_add_remove_via_api(self):
        code = to_json(software_system(
            title="Plant",
            parts=(
                ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                (
                    "guide",
                    "Guide",
                    software_site(
                        title="Guide",
                        pages=(
                            ("home", "Overview", ("Wear gloves.",)),
                            ("about", "About", ("Station history.",)),
                        ),
                    ),
                ),
            ),
        ))
        added = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-guide",
                "op": "add",
                "page_key": "guide-about",
                "code": code,
            }),
        )
        self.assertEqual(added.status_code, 200, added.get_data(as_text=True)[:400])
        payload = added.get_json()
        self.assertEqual(
            [item["key"] for item in payload["pages"]],
            ["home", "guide", "guide-about", "guide-page"],
        )
        self.assertEqual(payload["page_key"], "guide-page")
        self.assertIn("New page.", payload["page_html"])
        self.assertEqual(payload["site_title"], "Guide")
        updated = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-guide",
                "op": "update",
                "page_key": "guide-about",
                "new_key": "guide-about",
                "title": "About",
                "site_title": "Guide",
                "blocks": [{"kind": "paragraph", "text": "Rewritten history."}],
                "code": payload["code"],
            }),
        )
        copy = updated.get_json()
        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True)[:400])
        self.assertEqual(copy["page_key"], "guide-about")
        self.assertIn("Rewritten history.", copy["page_html"])
        self.assertEqual(
            [item["key"] for item in copy["pages"]],
            ["home", "guide", "guide-about", "guide-page"],
        )
        removed = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-guide",
                "op": "remove",
                "key": "guide-page",
                "page_key": "guide-about",
                "code": copy["code"],
            }),
        )
        gone = removed.get_json()
        self.assertEqual(removed.status_code, 200, removed.get_data(as_text=True)[:400])
        self.assertEqual([item["key"] for item in gone["pages"]], ["home", "guide", "guide-about"])
        self.assertEqual(gone["page_key"], "guide-about")
        grown = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "op": "add",
                "page_key": "home",
                "code": code,
            }),
        )
        promoted = grown.get_json()
        self.assertEqual(grown.status_code, 200, grown.get_data(as_text=True)[:400])
        self.assertEqual(
            [item["key"] for item in promoted["pages"]],
            ["home", "home-page", "guide", "guide-about"],
        )
        self.assertEqual(promoted["page_key"], "home-page")
        self.assertIn("New page.", promoted["page_html"])
        self.assertIn("Plant home.", json.dumps(json.loads(promoted["code"])))
        duplicated = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "op": "duplicate",
                "page_key": "home",
                "code": code,
            }),
        )
        clone = duplicated.get_json()
        self.assertEqual(duplicated.status_code, 200, duplicated.get_data(as_text=True)[:400])
        self.assertEqual(clone["page_key"], "home-home-2")
        self.assertEqual(
            [item["key"] for item in clone["pages"]],
            ["home", "home-home-2", "guide", "guide-about"],
        )
        self.assertIn("Plant home.", clone["page_html"])
        moved = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "op": "move",
                "page_key": "home",
                "delta": 1,
                "code": promoted["code"],
            }),
        )
        shifted = moved.get_json()
        self.assertEqual(moved.status_code, 200, moved.get_data(as_text=True)[:400])
        self.assertEqual(shifted["page_key"], "home")
        self.assertEqual(
            [item["key"] for item in shifted["pages"]],
            ["home-page", "home", "guide", "guide-about"],
        )

    def test_system_part_add_remove_via_api(self):
        code = to_json(software_system(
            title="Plant",
            parts=(
                ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                ("gate", "Gate", software_page(title="Gate", body=("Closed.",))),
            ),
        ))
        preview = self.client.post(
            "/api/builder-core/meta/preview",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-sys",
                "page_key": "home",
                "code": code,
            }),
        )
        shown = preview.get_json()
        self.assertEqual(preview.status_code, 200, preview.get_data(as_text=True)[:400])
        self.assertEqual(shown["kind"], "meta.system")
        self.assertEqual(shown["part_key"], "home")
        self.assertTrue(shown["can_remove_part"])
        self.assertTrue(shown["can_move_part"])
        moved = self.client.post(
            "/api/builder-core/meta/system-part",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-sys",
                "op": "move",
                "delta": 1,
                "page_key": "home",
                "code": code,
            }),
        )
        shifted = moved.get_json()
        self.assertEqual(moved.status_code, 200, moved.get_data(as_text=True)[:400])
        self.assertEqual([item["key"] for item in shifted["pages"]], ["gate", "home"])
        copied = self.client.post(
            "/api/builder-core/meta/system-part",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-sys",
                "op": "duplicate",
                "page_key": "home",
                "code": code,
            }),
        )
        clone = copied.get_json()
        self.assertEqual(copied.status_code, 200, copied.get_data(as_text=True)[:400])
        self.assertEqual(clone["page_key"], "home-2")
        self.assertEqual([item["key"] for item in clone["pages"]], ["home", "home-2", "gate"])
        added = self.client.post(
            "/api/builder-core/meta/system-part",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-sys",
                "op": "add",
                "page_key": "home",
                "code": code,
            }),
        )
        payload = added.get_json()
        self.assertEqual(added.status_code, 200, added.get_data(as_text=True)[:400])
        self.assertEqual(payload["page_key"], "part")
        self.assertEqual([item["key"] for item in payload["pages"]], ["home", "gate", "part"])
        self.assertIn("New part.", payload["page_html"])
        blocked = self.client.post(
            "/api/builder-core/meta/system-part",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "op": "remove",
                "page_key": "guide-about",
                "code": to_json(software_system(
                    title="Plant",
                    parts=(
                        (
                            "guide",
                            "Guide",
                            software_site(
                                title="Guide",
                                pages=(
                                    ("home", "Overview", ("Wear gloves.",)),
                                    ("about", "About", ("Station history.",)),
                                ),
                            ),
                        ),
                        ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                    ),
                )),
            }),
        )
        self.assertEqual(blocked.status_code, 400)
        removed = self.client.post(
            "/api/builder-core/meta/system-part",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-sys",
                "op": "remove",
                "page_key": "part",
                "code": payload["code"],
            }),
        )
        gone = removed.get_json()
        self.assertEqual(removed.status_code, 200, removed.get_data(as_text=True)[:400])
        self.assertEqual([item["key"] for item in gone["pages"]], ["home", "gate"])
        self.assertEqual(gone["page_key"], "home")

    def test_system_page_part_update_via_api(self):
        code = to_json(software_system(
            title="Plant",
            parts=(
                ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                ("gate", "Gate", software_page(title="Gate", body=("Closed.",))),
            ),
        ))
        updated = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-sys",
                "op": "update",
                "page_key": "home",
                "new_key": "intro",
                "title": "Overview",
                "blocks": [{"kind": "paragraph", "text": "Rewritten home."}],
                "code": code,
            }),
        )
        payload = updated.get_json()
        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True)[:400])
        self.assertEqual(payload["page_key"], "intro")
        self.assertEqual(payload["page_title"], "Overview")
        self.assertIn("Rewritten home.", payload["page_html"])
        self.assertEqual([item["key"] for item in payload["pages"]], ["intro", "gate"])
        themed = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "op": "theme",
                "page_key": "intro",
                "theme": {"accent": "#c00"},
                "code": payload["code"],
            }),
        )
        self.assertEqual(themed.status_code, 200, themed.get_data(as_text=True)[:400])
        self.assertEqual(themed.get_json()["page_theme"]["accent"], "#c00")
        lone = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "op": "update",
                "title": "Named",
                "blocks": [{"kind": "paragraph", "text": "One."}],
                "code": to_json(software_page(title="Lone", body=("x",))),
            }),
        )
        self.assertEqual(lone.status_code, 200, lone.get_data(as_text=True)[:400])
        self.assertEqual(lone.get_json()["page_title"], "Named")
        self.assertIn("One.", lone.get_json()["page_html"])

    def test_system_boundary_part_update_via_api(self):
        code = to_json(software_system(
            title="Plant",
            parts=(
                ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                ("gate", "Gate", boundary_to_desc(Boundary(
                    id="plant.gate",
                    name="Plant gate",
                    kind="software",
                    instantiation_target="web_build",
                    meta_level=0,
                ))),
            ),
        ))
        updated = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-sys",
                "op": "update",
                "page_key": "gate",
                "new_key": "portal",
                "title": "Portal",
                "boundary_id": "plant.portal",
                "surface": "meta",
                "target": "desc",
                "meta_level": 2,
                "blocks": [{"kind": "paragraph", "text": "ignored."}],
                "code": code,
            }),
        )
        payload = updated.get_json()
        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True)[:400])
        self.assertEqual(payload["page_key"], "portal")
        self.assertEqual(payload["page_title"], "Portal")
        self.assertEqual(payload["boundary"]["id"], "plant.portal")
        self.assertEqual(payload["boundary"]["surface"], "meta")
        self.assertEqual(payload["boundary"]["target"], "desc")
        self.assertEqual(payload["boundary"]["meta_level"], 2)
        self.assertEqual(payload["target"], "desc")
        self.assertEqual([item["key"] for item in payload["pages"]], ["home", "portal"])
        self.assertIn("plant.portal", payload["page_html"])
        self.assertNotIn("ignored.", payload["page_html"])
        lone = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "op": "update",
                "title": "Named gate",
                "boundary_id": "lab.named",
                "surface": "software",
                "target": "web_build",
                "code": to_json(boundary_to_desc(Boundary(
                    id="lab.gate",
                    name="Lab gate",
                    kind="software",
                    instantiation_target="web_build",
                    meta_level=0,
                ))),
            }),
        )
        self.assertEqual(lone.status_code, 200, lone.get_data(as_text=True)[:400])
        self.assertEqual(lone.get_json()["page_title"], "Named gate")
        self.assertEqual(lone.get_json()["boundary"]["id"], "lab.named")
        self.assertIn("lab.named", lone.get_json()["page_html"])

    def test_preview_flags_and_nested_system_update_via_api(self):
        code = to_json(software_system(
            title="Plant",
            parts=(
                ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                ("gate", "Gate", boundary_to_desc(Boundary(
                    id="plant.gate",
                    name="Plant gate",
                    kind="software",
                    instantiation_target="web_build",
                    meta_level=0,
                ))),
                ("cell", "Cell", software_system(
                    title="Cell",
                    parts=(("note", "Note", software_page(title="Note", body=("Nested.",))),),
                )),
            ),
        ))
        home = self.client.post(
            "/api/builder-core/meta/preview",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "page_key": "home", "code": code}),
        )
        home_data = home.get_json()
        self.assertEqual(home.status_code, 200, home.get_data(as_text=True)[:400])
        self.assertEqual(home_data["copy_surface"], "page")
        self.assertTrue(home_data["can_page_ops"])
        self.assertTrue(home_data["can_theme"])
        gate = self.client.post(
            "/api/builder-core/meta/preview",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "page_key": "gate", "code": code}),
        )
        gate_data = gate.get_json()
        self.assertEqual(gate.status_code, 200, gate.get_data(as_text=True)[:400])
        self.assertEqual(gate_data["copy_surface"], "boundary")
        self.assertFalse(gate_data["can_page_ops"])
        self.assertFalse(gate_data["can_theme"])
        cell = self.client.post(
            "/api/builder-core/meta/preview",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "page_key": "cell", "code": code}),
        )
        cell_data = cell.get_json()
        self.assertEqual(cell.status_code, 200, cell.get_data(as_text=True)[:400])
        self.assertEqual(cell_data["copy_surface"], "system")
        self.assertFalse(cell_data["can_page_ops"])
        self.assertFalse(cell_data["can_theme"])
        updated = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "op": "update",
                "page_key": "cell",
                "new_key": "module",
                "title": "Module",
                "code": code,
            }),
        )
        payload = updated.get_json()
        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True)[:400])
        self.assertEqual(payload["page_key"], "module")
        self.assertEqual(payload["page_title"], "Module")
        self.assertEqual(payload["copy_surface"], "system")
        self.assertEqual(
            [item["key"] for item in payload["pages"]],
            ["home", "gate", "module", "module-note"],
        )

    def test_step_selected_part_and_system_title_via_api(self):
        code = to_json(software_system(
            title="Plant",
            parts=(
                ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                (
                    "flow",
                    "Flow",
                    machine_to_desc(StateMachine(
                        state="idle",
                        transitions=(Transition("idle", "start", "running"),),
                    )),
                ),
            ),
        ))
        previewed = self.client.post(
            "/api/builder-core/meta/preview",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "page_key": "flow", "code": code}),
        )
        shown = previewed.get_json()
        self.assertEqual(previewed.status_code, 200, previewed.get_data(as_text=True)[:400])
        self.assertEqual(shown["system_title"], "Plant")
        self.assertEqual(shown["simulation"]["state"], "idle")
        stepped = self.client.post(
            "/api/builder-core/meta/step",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "page_key": "flow",
                "event": "start",
                "code": code,
            }),
        )
        payload = stepped.get_json()
        self.assertEqual(stepped.status_code, 200, stepped.get_data(as_text=True)[:400])
        self.assertEqual(payload["page_key"], "flow")
        self.assertEqual(payload["simulation"]["state"], "running")
        self.assertEqual(payload["system_title"], "Plant")
        renamed = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "op": "update",
                "page_key": "home",
                "title": "Home",
                "system_title": "Garden",
                "blocks": [{"kind": "paragraph", "text": "Plant home."}],
                "code": code,
            }),
        )
        garden = renamed.get_json()
        self.assertEqual(renamed.status_code, 200, renamed.get_data(as_text=True)[:400])
        self.assertEqual(garden["system_title"], "Garden")
        self.assertEqual(garden["page_title"], "Home")

    def test_site_serves_named_pages(self):
        created = self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-site",
                "description": json.loads(to_json(software_site(
                    title="Plant",
                    pages=(
                        ("home", "Home", ("Hello plant.",)),
                        ("about", "About", ("History.",)),
                    ),
                ))),
            }),
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True)[:400])
        home = self.client.get("/build/plant-site/home")
        about = self.client.get("/build/plant-site/about")
        missing = self.client.get("/build/plant-site/nope")
        self.assertEqual(home.status_code, 200)
        self.assertIn("<h1>Home</h1>", home.get_data(as_text=True))
        self.assertIn('href="/build/plant-site/about"', home.get_data(as_text=True))
        exported = self.data_dir / "sites" / "plant-site"
        self.assertTrue((exported / "home.html").is_file())
        self.assertTrue((exported / "about.html").is_file())
        self.assertTrue((exported / "index.html").is_file())
        disk_home = (exported / "home.html").read_text(encoding="utf-8")
        self.assertIn('href="about.html"', disk_home)
        self.assertNotIn("/build/plant-site/about", disk_home)
        self.assertEqual(created.get_json()["zip_url"], "/api/builder-core/meta/sites/plant-site/zip")
        self.assertEqual(created.get_json()["studio"], "/studio/meta/plant-site")
        zipped = self.client.get("/api/builder-core/meta/sites/plant-site/zip", headers=self.headers)
        self.assertEqual(zipped.status_code, 200)
        self.assertIn("zip", zipped.headers.get("Content-Type", ""))
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(zipped.get_data())) as archive:
            names = set(archive.namelist())
            self.assertIn("plant-site/home.html", names)
            self.assertIn("plant-site/about.html", names)
            self.assertIn("plant-site/meta.json", names)
            meta = json.loads(archive.read("plant-site/meta.json").decode("utf-8"))
            self.assertEqual(meta["slug"], "plant-site")
            self.assertIn("description", meta)
            self.assertIn("href=\"about.html\"", archive.read("plant-site/home.html").decode("utf-8"))
        copied = self.client.post(
            "/api/builder-core/meta/sites/import",
            headers={"X-CSRF-Token": self.csrf},
            data={
                "csrf_token": self.csrf,
                "slug": "plant-copy",
                "site": (io.BytesIO(zipped.get_data()), "plant-site.zip"),
            },
        )
        self.assertEqual(copied.status_code, 201, copied.get_data(as_text=True)[:400])
        self.assertEqual(copied.get_json()["slug"], "plant-copy")
        self.assertEqual(copied.get_json()["studio"], "/studio/meta/plant-copy")
        self.assertIn("software.site", copied.get_json()["code"])
        copy_editor = self.client.get("/studio/meta/plant-copy")
        self.assertEqual(copy_editor.status_code, 200)
        self.assertIn("plant-copy", copy_editor.get_data(as_text=True))
        copy_page = self.client.get("/build/plant-copy/about")
        self.assertEqual(copy_page.status_code, 200)
        self.assertIn("<h1>About</h1>", copy_page.get_data(as_text=True))
        slip = io.BytesIO()
        with zipfile.ZipFile(slip, "w") as archive:
            archive.writestr("../etc/passwd", "nope")
        bad = self.client.post(
            "/api/builder-core/meta/sites/import",
            headers={"X-CSRF-Token": self.csrf},
            data={
                "csrf_token": self.csrf,
                "site": (io.BytesIO(slip.getvalue()), "slip.zip"),
            },
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(about.status_code, 200)
        self.assertIn("<h1>About</h1>", about.get_data(as_text=True))
        self.assertEqual(missing.status_code, 404)
        root = self.client.get("/build/plant-site", follow_redirects=False)
        self.assertEqual(root.status_code, 302)
        self.assertTrue(root.headers.get("Location", "").endswith("/build/plant-site/home"))
        about_preview = self.client.post(
            "/api/builder-core/meta/preview",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-site",
                "page_key": "about",
                "code": to_json(software_site(
                    title="Plant",
                    pages=(
                        ("home", "Home", ("Hello plant.",)),
                        ("about", "About", ("History.",)),
                    ),
                )),
            }),
        )
        self.assertEqual(about_preview.status_code, 200, about_preview.get_data(as_text=True)[:400])
        preview_body = about_preview.get_json()
        self.assertEqual(preview_body["page_key"], "about")
        self.assertEqual([item["key"] for item in preview_body["pages"]], ["home", "about"])
        self.assertIn("<h1>About</h1>", preview_body["page_html"])
        self.assertIn('data-mp-page="home"', preview_body["page_html"])
        self.assertIn("zintriq-meta", preview_body["page_html"])
        self.assertNotIn("/build/plant-site/", preview_body["page_html"])

    def test_site_page_add_remove_via_api(self):
        code = to_json(software_site(
            title="Plant",
            pages=(
                ("home", "Home", ("Hello plant.",)),
                ("about", "About", ("History.",)),
            ),
        ))
        added = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-site",
                "op": "add",
                "code": code,
            }),
        )
        self.assertEqual(added.status_code, 200, added.get_data(as_text=True)[:400])
        payload = added.get_json()
        self.assertEqual([item["key"] for item in payload["pages"]], ["home", "about", "page"])
        self.assertEqual(payload["page_key"], "page")
        self.assertIn("New page.", payload["page_html"])
        removed = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-site",
                "op": "remove",
                "key": "page",
                "page_key": "home",
                "code": payload["code"],
            }),
        )
        self.assertEqual(removed.status_code, 200, removed.get_data(as_text=True)[:400])
        self.assertEqual([item["key"] for item in removed.get_json()["pages"]], ["home", "about"])
        self.assertEqual(removed.get_json()["page_key"], "home")
        last = to_json(software_site(title="One", pages=(("home", "Home", ("Hi.",)),)))
        blocked = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "op": "remove",
                "key": "home",
                "code": last,
            }),
        )
        self.assertEqual(blocked.status_code, 400)
        updated = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-site",
                "op": "update",
                "key": "about",
                "title": "History",
                "body": "Founded here.\nStill open.",
                "code": removed.get_json()["code"],
            }),
        )
        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True)[:400])
        copy = updated.get_json()
        self.assertEqual(copy["page_key"], "about")
        self.assertEqual(copy["page_title"], "History")
        self.assertEqual(copy["page_body"], ["Founded here.", "Still open."])
        self.assertIn("<h1>History</h1>", copy["page_html"])
        self.assertIn("<p>Founded here.</p>", copy["page_html"])
        painted = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-site",
                "op": "theme",
                "page_key": "about",
                "theme": {
                    "accent": "#6ea8fe",
                    "background": "#0b1020",
                    "color": "#e8eef8",
                    "measure": 56,
                    "space": 32,
                },
                "code": copy["code"],
            }),
        )
        self.assertEqual(painted.status_code, 200, painted.get_data(as_text=True)[:400])
        theme = painted.get_json()
        self.assertEqual(theme["page_theme"]["accent"], "#6ea8fe")
        self.assertEqual(theme["page_theme"]["measure"], 56)
        self.assertIn("--mp-bg:#0b1020", theme["page_html"])
        rejected = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "op": "theme",
                "theme": {"accent": "red"},
                "code": copy["code"],
            }),
        )
        self.assertEqual(rejected.status_code, 400)
        blocked_blocks = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-site",
                "op": "update",
                "key": "home",
                "title": "Home",
                "blocks": [
                    {"kind": "paragraph", "text": "Hello plant."},
                    {"kind": "heading", "text": "Next"},
                    {"kind": "link", "text": "History", "to": "about"},
                ],
                "code": painted.get_json()["code"],
            }),
        )
        self.assertEqual(blocked_blocks.status_code, 200, blocked_blocks.get_data(as_text=True)[:400])
        home_copy = blocked_blocks.get_json()
        self.assertEqual(
            home_copy["page_blocks"],
            [
                {"kind": "paragraph", "text": "Hello plant."},
                {"kind": "heading", "text": "Next"},
                {"kind": "link", "text": "History", "to": "about"},
            ],
        )
        self.assertIn("<h2>Next</h2>", home_copy["page_html"])
        moved = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-site",
                "op": "move",
                "key": "home",
                "delta": 1,
                "code": home_copy["code"],
            }),
        )
        self.assertEqual(moved.status_code, 200, moved.get_data(as_text=True)[:400])
        self.assertEqual([item["key"] for item in moved.get_json()["pages"]], ["about", "home"])
        page_theme = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-site",
                "op": "theme",
                "scope": "page",
                "key": "about",
                "theme": {"accent": "#c00"},
                "code": moved.get_json()["code"],
            }),
        )
        self.assertEqual(page_theme.status_code, 200, page_theme.get_data(as_text=True)[:400])
        self.assertEqual(page_theme.get_json()["page_theme"]["accent"], "#6ea8fe")
        self.assertEqual(page_theme.get_json()["page_theme_local"]["accent"], "#c00")
        renamed = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-site",
                "op": "update",
                "key": "home",
                "new_key": "lore",
                "site_title": "Garden",
                "title": "Home",
                "blocks": [{"kind": "paragraph", "text": "Hello plant."}],
                "code": page_theme.get_json()["code"],
            }),
        )
        self.assertEqual(renamed.status_code, 200, renamed.get_data(as_text=True)[:400])
        renamed_body = renamed.get_json()
        self.assertEqual([item["key"] for item in renamed_body["pages"]], ["about", "lore"])
        self.assertEqual(renamed_body["page_key"], "lore")
        self.assertEqual(renamed_body["site_title"], "Garden")
        cloned = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "plant-site",
                "op": "duplicate",
                "key": "about",
                "code": renamed_body["code"],
            }),
        )
        self.assertEqual(cloned.status_code, 200, cloned.get_data(as_text=True)[:400])
        self.assertEqual(
            [item["key"] for item in cloned.get_json()["pages"]],
            ["about", "about-2", "lore"],
        )
        self.assertEqual(cloned.get_json()["page_key"], "about-2")

    def test_local_image_upload_serves_and_zips(self):
        import io
        import zipfile

        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
            "0000000c4944415408d763f80f00000101000518d84e0000000049454e44ae426082"
        )
        created = self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "photo-site",
                "description": json.loads(to_json(software_site(
                    title="Photos",
                    pages=(("home", "Home", ("Look.",)),),
                ))),
            }),
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True)[:400])
        uploaded = self.client.post(
            "/api/builder-core/meta/sites/photo-site/assets",
            headers={"X-CSRF-Token": self.csrf},
            data={"csrf_token": self.csrf, "file": (io.BytesIO(png), "hero.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.get_data(as_text=True)[:400])
        self.assertEqual(uploaded.get_json()["name"], "hero.png")
        self.assertEqual(uploaded.get_json()["assets"], ["hero.png"])
        listed = self.client.get("/api/builder-core/meta/sites/photo-site/assets", headers=self.headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.get_json()["assets"], ["hero.png"])
        asset = self.client.get("/build/photo-site/assets/hero.png")
        self.assertEqual(asset.status_code, 200)
        self.assertEqual(asset.get_data(), png)
        self.assertIn("image/png", asset.headers.get("Content-Type", ""))
        code = to_json(software_site(
            title="Photos",
            pages=(("home", "Home", ("Look.",)),),
        ))
        updated = self.client.post(
            "/api/builder-core/meta/site-page",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "photo-site",
                "op": "update",
                "page_key": "home",
                "title": "Home",
                "code": code,
                "blocks": [
                    {"kind": "paragraph", "text": "Look."},
                    {"kind": "image", "src": "hero.png", "text": "Hero"},
                ],
            }),
        )
        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True)[:400])
        self.assertIn("data:image/png", updated.get_json().get("page_html") or "")
        saved = self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "photo-site",
                "description": json.loads(updated.get_json()["code"]),
            }),
        )
        self.assertEqual(saved.status_code, 201, saved.get_data(as_text=True)[:400])
        home = self.client.get("/build/photo-site/home")
        self.assertIn('src="/build/photo-site/assets/hero.png"', home.get_data(as_text=True))
        disk = (self.data_dir / "sites" / "photo-site" / "home.html").read_text(encoding="utf-8")
        self.assertIn('src="hero.png"', disk)
        self.assertTrue((self.data_dir / "sites" / "photo-site" / "hero.png").is_file())
        zipped = self.client.get("/api/builder-core/meta/sites/photo-site/zip", headers=self.headers)
        with zipfile.ZipFile(io.BytesIO(zipped.get_data())) as archive:
            self.assertIn("photo-site/hero.png", archive.namelist())
            self.assertEqual(archive.read("photo-site/hero.png"), png)
        copied = self.client.post(
            "/api/builder-core/meta/sites/import",
            headers={"X-CSRF-Token": self.csrf},
            data={
                "csrf_token": self.csrf,
                "slug": "photo-copy",
                "site": (io.BytesIO(zipped.get_data()), "photo-site.zip"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(copied.status_code, 201, copied.get_data(as_text=True)[:400])
        again = self.client.get("/build/photo-copy/assets/hero.png")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.get_data(), png)
        svg = self.client.post(
            "/api/builder-core/meta/sites/photo-site/assets",
            headers={"X-CSRF-Token": self.csrf},
            data={"csrf_token": self.csrf, "file": (io.BytesIO(b"<svg></svg>"), "hero.svg")},
            content_type="multipart/form-data",
        )
        self.assertEqual(svg.status_code, 400)
        gone = self.client.post(
            "/api/builder-core/meta/sites/photo-site/assets/remove",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "name": "hero.png"}),
        )
        self.assertEqual(gone.status_code, 200, gone.get_data(as_text=True)[:400])
        self.assertEqual(gone.get_json()["assets"], [])
        self.assertEqual(self.client.get("/build/photo-site/assets/hero.png").status_code, 404)
        self.assertFalse((self.data_dir / "assets" / "photo-site" / "hero.png").is_file())
        self.assertFalse((self.data_dir / "sites" / "photo-site" / "hero.png").is_file())

    def test_local_page_step_rewrites_artifact(self):
        machine = StateMachine(
            state="idle",
            transitions=(
                Transition("idle", "start", "running"),
                Transition("running", "stop", "idle"),
            ),
        )
        created = self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "live-page",
                "description": json.loads(to_json(machine_to_desc(machine))),
            }),
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True)[:400])
        idle = self.client.get("/build/live-page/home")
        self.assertIn('data-machine-state="idle"', idle.get_data(as_text=True))
        self.assertIn('name="event" value="start"', idle.get_data(as_text=True))
        stepped = self.client.post(
            "/api/builder-core/meta/page/live-page/step",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "event": "start"}),
        )
        self.assertEqual(stepped.status_code, 200, stepped.get_data(as_text=True)[:400])
        self.assertEqual(stepped.get_json()["state"], "running")
        self.assertEqual(stepped.get_json()["target"], "web_build")
        again = self.client.get("/build/live-page/home")
        self.assertIn('data-machine-state="running"', again.get_data(as_text=True))

    def test_page_step_keeps_artifact_target(self):
        machine = StateMachine(
            state="idle",
            transitions=(
                Transition("idle", "start", "running"),
                Transition("running", "stop", "idle"),
            ),
        )
        created = self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "spec-live",
                "target": "desc",
                "description": json.loads(to_json(machine_to_desc(machine))),
            }),
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True)[:400])
        self.assertEqual(created.get_json()["target"], "desc")
        idle = self.client.get("/build/spec-live/home")
        self.assertIn("application/json", idle.content_type)
        idle_body = json.loads(idle.get_data(as_text=True))
        self.assertEqual(idle_body["fields"]["state"]["value"], "idle")
        stepped = self.client.post(
            "/api/builder-core/meta/page/spec-live/step",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "event": "start"}),
        )
        payload = stepped.get_json()
        self.assertEqual(stepped.status_code, 200, stepped.get_data(as_text=True)[:400])
        self.assertEqual(payload["state"], "running")
        self.assertEqual(payload["target"], "desc")
        self.assertNotIn("zip_url", payload)
        again = self.client.get("/build/spec-live/home")
        self.assertIn("application/json", again.content_type)
        data = json.loads(again.get_data(as_text=True))
        self.assertEqual(data["fields"]["kind"]["value"], "state_machine")
        self.assertEqual(data["fields"]["state"]["value"], "running")
        listing = self.client.get("/studio")
        self.assertIn("<span>desc</span>", listing.get_data(as_text=True))

    def test_rejects_path_slug(self):
        node = struct(label=atom("string", value="x", has_value=True))
        bad = self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "../etc",
                "description": json.loads(to_json(node)),
            }),
        )
        self.assertEqual(bad.status_code, 400)

    def test_web_mode_does_not_instantiate(self):
        from builder_http_support import disable_application_host

        disable_application_host()
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["csrf_token"] = "csrf-web"
        resp = client.post(
            "/api/builder-core/meta/instantiate",
            headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf-web"},
            data=json.dumps({"csrf_token": "csrf-web", "slug": "x"}),
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(
            client.post(
                "/api/builder-core/meta/system-part",
                headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf-web"},
                data=json.dumps({"csrf_token": "csrf-web", "op": "add"}),
            ).status_code,
            404,
        )
        listed = client.get("/api/builder-core/meta/artifacts")
        self.assertEqual(listed.status_code, 404)
        page = client.get("/build/pump-page/home")
        self.assertEqual(page.status_code, 404)
        self.assertEqual(client.get("/build/pump-page").status_code, 404)
        with client.session_transaction() as sess:
            sess["csrf_token"] = "csrf-web"
        stepped = client.post(
            "/api/builder-core/meta/page/live-page/step",
            headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf-web"},
            data=json.dumps({"csrf_token": "csrf-web", "event": "start"}),
        )
        self.assertEqual(stepped.status_code, 404)
        self.assertEqual(client.get("/api/builder-core/meta/sites/x/zip").status_code, 404)
        imported = client.post(
            "/api/builder-core/meta/sites/import",
            headers={"X-CSRF-Token": "csrf-web"},
            data={"csrf_token": "csrf-web"},
        )
        self.assertEqual(imported.status_code, 404)
        gone = client.post(
            "/api/builder-core/meta/sites/x/remove",
            headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf-web"},
            data=json.dumps({"csrf_token": "csrf-web"}),
        )
        self.assertEqual(gone.status_code, 404)
        draft_gone = client.post(
            "/api/builder-core/meta/drafts/remove",
            headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf-web"},
            data=json.dumps({"csrf_token": "csrf-web", "slug": "x"}),
        )
        self.assertEqual(draft_gone.status_code, 404)
        self.assertEqual(client.get("/build/x/assets/hero.png").status_code, 404)
        posted = client.post(
            "/api/builder-core/meta/sites/x/assets",
            headers={"X-CSRF-Token": "csrf-web"},
            data={"csrf_token": "csrf-web"},
        )
        self.assertEqual(posted.status_code, 404)
        self.assertEqual(client.get("/api/builder-core/meta/sites/x/assets").status_code, 404)
        removed = client.post(
            "/api/builder-core/meta/sites/x/assets/remove",
            headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf-web"},
            data=json.dumps({"csrf_token": "csrf-web", "name": "hero.png"}),
        )
        self.assertEqual(removed.status_code, 404)

    def test_meta_editor_and_preview_round_trip(self):
        page = self.client.get("/studio/meta")
        self.assertEqual(page.status_code, 200, page.get_data(as_text=True)[:400])
        html = page.get_data(as_text=True)
        self.assertIn("studio/meta-editor.js", html)
        self.assertIn("studio/editor-views.js", html)
        self.assertIn("studio/workbench.js", html)
        self.assertIn("studio/zintriq.js", html)
        self.assertIn('data-workbench="1"', html)
        self.assertIn('data-view="meta"', html)
        self.assertIn('data-meta-view="describe"', html)
        self.assertIn("me-host-empty", html)
        self.assertIn('class="me-host-tools" hidden', html)
        self.assertIn("id=\"me-graph\"", html)
        self.assertIn("id=\"me-diagram\"", html)
        self.assertIn("studio/editors/diagram.js", html)
        self.assertIn("studio/editors/plugin-kit.js", html)
        self.assertIn("studio/editors/pack.js", html)
        self.assertIn("id=\"me-plugin-host\"", html)
        self.assertIn("id=\"me-uir\"", html)
        self.assertIn("me-uir-apply", html)
        listed = self.client.get("/api/builder-core/meta/views", headers=self.headers)
        self.assertEqual(listed.status_code, 200)
        ids = {item["id"] for item in listed.get_json()["views"]}
        self.assertFalse({"code", "visual", "graph", "diagram", "uir", "page"} & ids)
        describe = self.client.get("/api/builder-core/meta/views?surface=describe", headers=self.headers)
        describe_views = describe.get_json()["views"]
        describe_ids = {item["id"] for item in describe_views}
        self.assertNotIn("code", describe_ids)
        self.assertNotIn("scene", describe_ids)
        installed_scene = self.client.post(
            "/api/plugin/install",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": "official-scene"}),
        )
        self.assertEqual(installed_scene.status_code, 200, installed_scene.get_data(as_text=True)[:400])
        scene_html = self.client.get("/studio/meta").get_data(as_text=True)
        self.assertRegex(scene_html, r'data-editor-view="scene"')
        self.assertRegex(scene_html, r'data-editor-pane="code"[^>]*hidden')
        self.assertRegex(scene_html, r'data-editor-pane="visual"[^>]*hidden')
        self.assertNotRegex(scene_html, r'id="me-plugin-host"[^>]*hidden')
        self.assertNotIn('class="me-host-tools" hidden', scene_html)
        home_after = self.client.get("/studio").get_data(as_text=True)
        self.assertIn("official-scene", home_after)
        self.assertIn(">Scene</a>", home_after)
        describe_after = self.client.get("/api/builder-core/meta/views?surface=describe", headers=self.headers)
        describe_ids = {item["id"] for item in describe_after.get_json()["views"]}
        self.assertIn("scene", describe_ids)
        self.assertNotIn("code", describe_ids)
        scene = next(item for item in describe_after.get_json()["views"] if item["id"] == "scene")
        self.assertEqual(scene["contract"], ["render", "hitTest", "edit"])
        self.assertEqual(scene["pane"], "plugin")
        installed_meta = self.client.post(
            "/api/plugin/install",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": "official-meta"}),
        )
        self.assertEqual(installed_meta.status_code, 200, installed_meta.get_data(as_text=True)[:400])
        describe_meta = self.client.get("/api/builder-core/meta/views?surface=describe", headers=self.headers)
        describe_meta_ids = {item["id"] for item in describe_meta.get_json()["views"]}
        self.assertTrue({"code", "visual", "graph", "diagram", "uir", "page"}.issubset(describe_meta_ids))
        diagram = next(item for item in describe_meta.get_json()["views"] if item["id"] == "diagram")
        self.assertEqual(diagram["contract"], ["render", "hitTest", "edit"])
        space_views = self.client.get("/api/builder-core/meta/views?surface=space", headers=self.headers)
        self.assertEqual({item["id"] for item in space_views.get_json()["views"]}, {"space", "code", "graph", "uir"})
        visual_page = self.client.get("/studio/meta?pane=visual")
        self.assertEqual(visual_page.status_code, 200)
        self.assertRegex(visual_page.get_data(as_text=True), r"<body[^>]*data-editor-view=\"visual\"")
        sim_html = self.client.get("/studio/simulate").get_data(as_text=True)
        self.assertRegex(sim_html, r"<body[^>]*data-editor-view=\"simulation\"")
        self.assertIn("/app/community", html)
        self.assertIn("me-host-empty", html)
        sim_page = self.client.get("/studio/simulate")
        self.assertEqual(sim_page.status_code, 200, sim_page.get_data(as_text=True)[:400])
        self.assertIn('data-meta-view="simulate"', sim_page.get_data(as_text=True))
        inst_page = self.client.get("/studio/instantiate")
        self.assertEqual(inst_page.status_code, 200, inst_page.get_data(as_text=True)[:400])
        self.assertIn('data-meta-view="instantiate"', inst_page.get_data(as_text=True))
        self.assertNotIn("universal-builder.js", html)
        self.assertIn("me-code", html)
        self.assertIn('id="me-produce"', html)
        self.assertIn("me-sim", html)
        self.assertIn("me-sim-empty", html)
        self.assertIn("id=\"me-artifact\"", html)
        self.assertIn("me-artifact-empty", html)
        self.assertIn("data-insert", html)
        self.assertIn("data-insert=\"boundary\"", html)
        self.assertIn("data-insert=\"hardware\"", html)
        self.assertIn("data-insert=\"os\"", html)
        self.assertIn("data-insert=\"space\"", html)
        bounds = self.client.get("/api/builder-core/meta/boundaries", headers=self.headers)
        self.assertEqual(bounds.status_code, 200)
        bound_ids = {item["id"] for item in bounds.get_json()["boundaries"]}
        self.assertLessEqual({"software.page", "hardware.module", "os.surface", "meta.space"}, bound_ids)
        space = self.client.get("/api/builder-core/meta/space", headers=self.headers)
        self.assertEqual(space.status_code, 200)
        self.assertEqual(space.get_json()["id"], "meta.space")
        self.assertIn("software.page", space.get_json()["boundaries"])
        self.assertNotIn("meta.space", space.get_json()["boundaries"])
        self.assertIn("meta.system", space.get_json()["code"])
        opened = self.client.get("/studio/meta?space=1", follow_redirects=False)
        self.assertIn(opened.status_code, (301, 302, 303))
        self.assertTrue((opened.headers.get("Location") or "").endswith("/studio/space"))
        space_page = self.client.get("/studio/space")
        self.assertEqual(space_page.status_code, 200, space_page.get_data(as_text=True)[:400])
        opened_html = space_page.get_data(as_text=True)
        self.assertIn('data-meta-view="space"', opened_html)
        self.assertIn("id=\"me-space-doc\"", opened_html)
        self.assertIn("meta.space", opened_html)
        self.assertIn("software.page", opened_html)
        self.assertIn('value="meta-space"', opened_html)
        space_preview = self.client.post(
            "/api/builder-core/meta/preview",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "code": space.get_json()["code"],
                "slug": "meta-space",
            }),
        )
        self.assertEqual(space_preview.status_code, 200, space_preview.get_data(as_text=True)[:400])
        self.assertTrue(space_preview.get_json().get("space"))
        self.assertTrue(space_preview.get_json().get("space_parts"))
        added_bound = self.client.post(
            "/api/builder-core/meta/system-part",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "op": "add",
                "kind": "boundary",
                "code": space.get_json()["code"],
                "slug": "meta-space",
            }),
        )
        self.assertEqual(added_bound.status_code, 200, added_bound.get_data(as_text=True)[:400])
        self.assertIn("software.part", added_bound.get_json().get("boundaries") or [])
        self.assertIn("me-host-empty", html)
        self.assertIn("me-page", html)
        self.assertIn("me-pages", html)
        self.assertIn("me-copy", html)
        self.assertIn("me-page-title", html)
        self.assertIn("me-bound-id", html)
        self.assertIn("me-bound-surface", html)
        self.assertIn("me-bound-target", html)
        self.assertIn("me-bound-level", html)
        self.assertIn("me-blocks", html)
        self.assertIn("me-site-title", html)
        self.assertIn("me-system-title", html)
        self.assertIn("me-page-key", html)
        self.assertIn("me-zip", html)
        self.assertIn("me-undo", html)
        css = (Path(__file__).resolve().parents[1] / "static" / "studio" / "meta-editor.css").read_text()
        self.assertIn(".me-btn {", css)
        self.assertIn(".me-btn--tiny {", css)
        self.assertNotIn("height: 28px", css)
        self.assertNotIn("height: 36px", css)
        self.assertIn("height: 32px", css)
        self.assertIn("data-block-add=\"list\"", html)
        self.assertIn("data-block-add=\"quote\"", html)
        self.assertIn("data-block-add=\"code\"", html)
        self.assertNotIn("zw-primitive-strip", html)
        self.assertIn("me-image-upload", html)
        self.assertIn("me-assets", html)
        self.assertIn("me-theme", html)
        self.assertIn("me-theme-accent", html)
        self.assertIn("me-theme-scope", html)
        self.assertIn("sandbox=\"allow-scripts\"", html)
        code = self.client.get("/studio/meta").get_data(as_text=True)
        self.assertIn("software.site", code)
        self.assertIn("Welcome.", code)
        self.assertIn("Next", code)
        self.assertIn('value="site"', code)
        self.assertIn("&#34;measure&#34;", code)
        preview = self.client.post(
            "/api/builder-core/meta/preview",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "code": to_json(machine_to_desc(StateMachine(
                    state="idle",
                    transitions=(Transition("idle", "start", "running"),),
                ))),
                "slug": "preview-live",
            }),
        )
        self.assertEqual(preview.status_code, 200, preview.get_data(as_text=True)[:400])
        payload = preview.get_json()
        self.assertTrue(payload["equivalent"])
        self.assertTrue(payload["equivalent_uir"])
        self.assertEqual(payload["visual"]["form"], "visual")
        self.assertTrue(payload["visual"]["nodes"])
        self.assertIn("nodes", payload["uir"])
        self.assertIn("edges", payload["uir"])
        uir_only = self.client.post(
            "/api/builder-core/meta/preview",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "uir": payload["uir"],
                "slug": "preview-live",
            }),
        )
        self.assertEqual(uir_only.status_code, 200, uir_only.get_data(as_text=True)[:400])
        self.assertTrue(uir_only.get_json()["equivalent"])
        self.assertTrue(uir_only.get_json()["equivalent_uir"])
        self.assertEqual(payload["simulation"]["state"], "idle")
        self.assertEqual(payload["simulation"]["events"], ["start"])
        self.assertIn('data-boundary="software.page"', payload["page_html"])
        self.assertIn('data-machine-state="idle"', payload["page_html"])
        self.assertEqual(payload["page_slug"], "preview-live")
        self.assertFalse((self.data_dir / "artifacts" / "preview-live.json").exists())
        visual_only = self.client.post(
            "/api/builder-core/meta/preview",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "visual": payload["visual"],
                "slug": "preview-live",
            }),
        )
        self.assertEqual(visual_only.status_code, 200, visual_only.get_data(as_text=True)[:400])
        self.assertTrue(visual_only.get_json()["equivalent"])
        self.assertIn("idle", visual_only.get_json()["code"])

    def test_step_advances_machine_in_editor(self):
        code = to_json(machine_to_desc(StateMachine(
            state="idle",
            transitions=(Transition("idle", "start", "running"),),
        )))
        stepped = self.client.post(
            "/api/builder-core/meta/step",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "code": code,
                "event": "start",
            }),
        )
        self.assertEqual(stepped.status_code, 200, stepped.get_data(as_text=True)[:400])
        payload = stepped.get_json()
        self.assertEqual(payload["simulation"]["state"], "running")
        self.assertEqual(payload["simulation"]["events"], [])
        unknown = self.client.post(
            "/api/builder-core/meta/step",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "code": code,
                "event": "nope",
            }),
        )
        self.assertEqual(unknown.status_code, 400)

    def test_web_has_no_meta_editor(self):
        from builder_http_support import disable_application_host

        disable_application_host()
        client = self.app.test_client()
        self.assertEqual(client.get("/studio/meta").status_code, 404)
        self.assertEqual(client.get("/studio/simulate").status_code, 404)
        self.assertEqual(client.get("/studio/instantiate").status_code, 404)
        self.assertEqual(client.get("/studio/space").status_code, 404)
        self.assertEqual(client.get("/static/studio/meta-editor.js").status_code, 404)
        self.assertEqual(client.get("/static/studio/workbench.js").status_code, 404)
        self.assertEqual(client.get("/static/studio/zintriq.js").status_code, 404)
        self.assertEqual(client.get("/static/studio/editors/diagram.js").status_code, 404)
        self.assertEqual(client.get("/static/studio/editors/pack.js").status_code, 404)
        with client.session_transaction() as sess:
            sess["csrf_token"] = "csrf-web"
        stepped = client.post(
            "/api/builder-core/meta/step",
            headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf-web"},
            data=json.dumps({"csrf_token": "csrf-web", "code": "{}", "event": "start"}),
        )
        self.assertEqual(stepped.status_code, 404)
        site_page = client.post(
            "/api/builder-core/meta/site-page",
            headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf-web"},
            data=json.dumps({"csrf_token": "csrf-web", "code": "{}", "op": "add"}),
        )
        self.assertEqual(site_page.status_code, 404)
        self.assertEqual(client.get("/api/plugin").status_code, 404)
        self.assertEqual(client.get("/api/plugin/store").status_code, 404)
        ai = client.post(
            "/api/ai",
            headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf-web"},
            data=json.dumps({"csrf_token": "csrf-web", "prompt": "hi"}),
        )
        self.assertEqual(ai.status_code, 404)
        chat = client.post(
            "/api/ai/chat",
            headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf-web"},
            data=json.dumps({"csrf_token": "csrf-web", "prompt": "hi"}),
        )
        self.assertEqual(chat.status_code, 404)
        produce = client.post(
            "/api/builder-core/meta/produce",
            headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf-web"},
            data=json.dumps({"csrf_token": "csrf-web", "prompt": "cube"}),
        )
        self.assertEqual(produce.status_code, 404)
        deploy = client.post(
            "/api/deploy",
            headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf-web"},
            data=json.dumps({"csrf_token": "csrf-web"}),
        )
        self.assertEqual(deploy.status_code, 404)
        self.assertEqual(client.get("/api/hardware").status_code, 404)
        plugins = client.get("/plugins")
        self.assertEqual(plugins.status_code, 200)
        self.assertIn("empty", plugins.get_data(as_text=True).lower())
        self.assertIn("not an editor", plugins.get_data(as_text=True))
        plugin_html = plugins.get_data(as_text=True)
        self.assertIn("Circuit", plugin_html)
        self.assertIn("Film", plugin_html)
        self.assertNotIn("Pending pack", plugin_html)
        self.assertIn("sandbox", plugin_html)
        self.assertIn("/plugins/files/scene.zintriq-plugin.json", plugin_html)
        self.assertIn('data-pack-id="official-scene"', plugin_html)
        self.assertNotIn("/api/plugin/install", plugin_html)
        scene = self.client.get("/plugins/files/scene.zintriq-plugin.json")
        self.assertEqual(scene.status_code, 200)
        pack = scene.get_json()
        self.assertEqual(pack["origin"], "official")
        self.assertFalse(pack.get("js"))
        self.assertIn("document", pack)

    def test_draft_saves_locally_and_reopens(self):
        from desktop.meta_store import load_draft

        dirty = "{ not json yet"
        saved = self.client.post(
            "/api/builder-core/meta/drafts",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "offline-note",
                "code": dirty,
                "events": "start",
            }),
        )
        self.assertEqual(saved.status_code, 200, saved.get_data(as_text=True)[:400])
        disk = self.data_dir / "drafts" / "offline-note.json"
        self.assertTrue(disk.is_file())
        self.assertEqual(load_draft("offline-note", base=self.data_dir)["code"], dirty)
        self.assertTrue((self.data_dir / "search-index.json").is_file())
        found = self.client.get("/api/builder-core/meta/search?q=not+json+yet", headers=self.headers)
        self.assertEqual(found.status_code, 200)
        self.assertTrue(any(hit.get("slug") == "offline-note" for hit in found.get_json().get("hits") or []))
        blocked = self.client.get("/api/builder-core/meta/search?q=x&sql=SELECT+1", headers=self.headers)
        self.assertEqual(blocked.status_code, 400)
        filtered = self.client.get("/api/builder-core/meta/search?stamped=0", headers=self.headers)
        self.assertEqual(filtered.status_code, 200)
        self.assertTrue(any(hit.get("slug") == "offline-note" for hit in filtered.get_json().get("hits") or []))
        os.environ["ZINTRIQ_FAKE_USB"] = "usb-test-0"
        self.addCleanup(lambda: os.environ.pop("ZINTRIQ_FAKE_USB", None))
        buses = self.client.get("/api/builder-core/meta/hardware/buses", headers=self.headers)
        self.assertEqual(buses.status_code, 200)
        self.assertIn("usb-test-0", json.dumps(buses.get_json()))
        ping = self.client.post(
            "/api/builder-core/meta/hardware/buses/transfer",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "kind": "usb", "device": "usb-test-0", "payload": "ping"}),
        )
        self.assertEqual(ping.status_code, 200, ping.get_data(as_text=True)[:300])
        self.assertTrue(ping.get_json().get("ok"))
        layout = self.client.post(
            "/api/builder-core/meta/layout",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "tree": {"type": "leaf", "id": "code"}, "max": ""}),
        )
        self.assertEqual(layout.status_code, 200, layout.get_data(as_text=True)[:300])
        loaded = self.client.get("/api/builder-core/meta/layout", headers=self.headers)
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.get_json().get("tree", {}).get("id"), "code")
        grouped = self.client.post(
            "/api/builder-core/meta/layout",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "activeGroup": 0,
                "groups": [{"max": "", "tree": {"id": "code", "type": "leaf"}}],
                "tree": {"id": "code", "type": "leaf"},
            }),
        )
        self.assertEqual(grouped.status_code, 200)
        self.assertEqual(len(grouped.get_json().get("groups") or []), 1)
        store = self.client.get("/api/plugin/store", headers=self.headers)
        self.assertEqual(store.status_code, 200)
        self.assertEqual(store.get_json().get("kind"), "store")
        session = self.client.post(
            "/api/builder-core/meta/hardware/buses/session",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "kind": "usb", "device": "usb-test-0"}),
        )
        self.assertEqual(session.status_code, 200, session.get_data(as_text=True)[:300])
        sid = session.get_json().get("session")
        self.assertTrue(sid)
        written = self.client.post(
            "/api/builder-core/meta/hardware/buses/session/write",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "session": sid, "payload": "hi"}),
        )
        self.assertEqual(written.status_code, 200)
        blocked = self.client.post(
            "/api/plugin/install",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": "community-pending"}),
        )
        self.assertEqual(blocked.status_code, 403)
        stamped = self.client.post(
            "/api/plugin/stamp",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "name": "Hello AI", "form": "AI"}),
        )
        self.assertEqual(stamped.status_code, 201, stamped.get_data(as_text=True)[:400])
        self.assertEqual(stamped.get_json()["pack"]["form"], "AI")
        self.assertTrue(stamped.get_json()["pack"]["stamp"])
        packs = self.client.get("/api/plugin", headers=self.headers).get_json()["packs"]
        pack_ids = {row["id"] for row in packs}
        self.assertIn("official-scene", pack_ids)
        self.assertIn(stamped.get_json()["pack"]["id"], pack_ids)
        used = self.client.post(
            "/api/plugin/project",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "ids": [stamped.get_json()["pack"]["id"]], "title": "Hello AI"}),
        )
        self.assertEqual(used.status_code, 201, used.get_data(as_text=True)[:400])
        used_body = used.get_json()
        self.assertIn("/studio/meta/", used_body["studio"])
        draft = self.client.get("/studio/meta/" + used_body["slug"])
        self.assertEqual(draft.status_code, 200)
        self.assertIn(used_body["slug"], draft.get_data(as_text=True))
        scene_stamp = self.client.post(
            "/api/plugin/stamp",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "name": "My Scene", "form": "Scene"}),
        )
        self.assertEqual(scene_stamp.status_code, 201, scene_stamp.get_data(as_text=True)[:400])
        views = self.client.get("/api/builder-core/meta/views?surface=describe", headers=self.headers)
        self.assertIn("scene", {item["id"] for item in views.get_json()["views"]})
        app_out = self.client.post(
            "/api/builder-core/meta/produce",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "kind": "app", "title": "Host app", "slug": "export-app"}),
        )
        self.assertEqual(app_out.status_code, 201, app_out.get_data(as_text=True)[:400])
        self.assertIn("/api/builder-core/meta/apps/export-app/zip", app_out.get_json().get("zip_url") or "")
        zipped = self.client.get("/api/builder-core/meta/apps/export-app/zip", headers=self.headers)
        self.assertEqual(zipped.status_code, 200)
        self.assertEqual(zipped.mimetype, "application/zip")
        import io

        opened = self.client.post(
            "/api/builder-core/meta/sites/import",
            headers={"X-CSRF-Token": self.csrf},
            data={
                "csrf_token": self.csrf,
                "slug": "reopen-app",
                "site": (io.BytesIO(zipped.get_data()), "export-app.zintriq-app.zip"),
            },
        )
        self.assertEqual(opened.status_code, 201, opened.get_data(as_text=True)[:400])
        opened_body = opened.get_json()
        self.assertEqual(opened_body["slug"], "reopen-app")
        self.assertEqual(opened_body["target"], "desktop_host")
        self.assertFalse(opened_body.get("installer"))
        self.assertFalse(opened_body.get("store"))
        self.assertFalse(opened_body.get("binary"))
        self.assertEqual(opened_body["studio"], "/studio/meta/reopen-app")
        editor = self.client.get("/studio/meta/reopen-app")
        self.assertEqual(editor.status_code, 200)
        self.assertIn("reopen-app", editor.get_data(as_text=True))
        restamp = self.client.post(
            "/api/plugin/stamp",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "name": "From app zip",
                "form": "App",
                "code": opened_body["code"],
            }),
        )
        self.assertEqual(restamp.status_code, 201, restamp.get_data(as_text=True)[:400])
        import zipfile

        fake = io.BytesIO()
        with zipfile.ZipFile(fake, "w") as archive:
            archive.writestr(
                "store-app/host.json",
                json.dumps({"description": {"form": "atom", "type": "string", "value": "x"}, "installer": True, "slug": "store-app"}),
            )
        refused = self.client.post(
            "/api/builder-core/meta/sites/import",
            headers={"X-CSRF-Token": self.csrf},
            data={
                "csrf_token": self.csrf,
                "site": (io.BytesIO(fake.getvalue()), "store.zintriq-app.zip"),
            },
        )
        self.assertEqual(refused.status_code, 400)
        listed = self.client.get("/api/builder-core/meta/drafts", headers=self.headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.get_json()["current"], "reopen-app")
        page = self.client.get("/studio/meta")
        html = page.get_data(as_text=True)
        self.assertIn("reopen-app", html)
        self.assertIn("/app/community", html)
        note = self.client.get("/studio/meta/offline-note")
        self.assertIn("not json yet", note.get_data(as_text=True))
        fresh = self.client.get("/studio/meta?new=1")
        self.assertEqual(fresh.status_code, 200, fresh.get_data(as_text=True)[:400])
        fresh_html = fresh.get_data(as_text=True)
        self.assertNotIn("Welcome.", fresh_html)
        self.assertIn("{}", fresh_html)
        self.assertNotIn("not json yet", fresh_html)
        self.assertIn('id="me-slug"', fresh_html)
        self.assertIn('value="site"', fresh_html)
        self.assertNotIn("offline-note", fresh_html.split("me-slug", 1)[-1][:400])
        removed = self.client.post(
            "/api/builder-core/meta/drafts/remove",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "slug": "offline-note"}),
        )
        self.assertEqual(removed.status_code, 200, removed.get_data(as_text=True)[:400])
        self.assertFalse(disk.is_file())
        listed_after = self.client.get("/api/builder-core/meta/drafts", headers=self.headers)
        slugs = {item["slug"] for item in listed_after.get_json()["drafts"]}
        self.assertNotIn("offline-note", slugs)

    def test_new_description_skips_taken_slug(self):
        self.client.post(
            "/api/builder-core/meta/drafts",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "slug": "site", "code": '{"taken":true}'}),
        )
        fresh = self.client.get("/studio/meta?new=1")
        html = fresh.get_data(as_text=True)
        self.assertEqual(fresh.status_code, 200, html[:400])
        self.assertIn('value="site-2"', html)
        self.assertNotIn('{"taken":true}', html)

    def test_remove_site_deletes_local_files(self):
        from meta.instantiation import default_site_desc

        created = self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "drop-site",
                "description": json.loads(to_json(default_site_desc())),
            }),
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True)[:400])
        artifact = self.data_dir / "artifacts" / "drop-site.json"
        home = self.data_dir / "sites" / "drop-site" / "home.html"
        self.assertTrue(artifact.is_file())
        self.assertTrue(home.is_file())
        removed = self.client.post(
            "/api/builder-core/meta/sites/drop-site/remove",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf}),
        )
        self.assertEqual(removed.status_code, 200, removed.get_data(as_text=True)[:400])
        self.assertFalse(artifact.is_file())
        self.assertFalse(home.is_file())
        self.assertEqual(self.client.get("/build/drop-site/home").status_code, 404)

    def test_studio_home_lists_local_drafts_and_artifacts(self):
        self.client.post(
            "/api/builder-core/meta/drafts",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "shelf-draft",
                "code": "{}",
            }),
        )
        machine = StateMachine(
            state="idle",
            transitions=(Transition("idle", "start", "running"),),
        )
        self.client.post(
            "/api/builder-core/meta/instantiate",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "slug": "shelf-page",
                "events": ["start"],
                "description": json.loads(to_json(machine_to_desc(machine))),
            }),
        )
        home = self.client.get("/studio")
        self.assertEqual(home.status_code, 200, home.get_data(as_text=True)[:400])
        html = home.get_data(as_text=True)
        self.assertIn("id=\"da-cloud-drafts\"", html)
        self.assertIn("id=\"da-sync\"", html)
        self.assertIn("da-welcome", html)
        self.assertIn("Empty Space", html)
        self.assertIn("On this machine", html)
        self.assertIn(">New</a>", html)
        self.assertIn("Add plugin", html)
        self.assertIn('data-workbench="1"', html)
        self.assertIn('data-view="meta"', html)
        self.assertIn('data-document="description"', html)
        self.assertIn("Zintriq", html)
        self.assertNotIn("Library", html)
        self.assertNotIn("Cloud drafts", html)
        self.assertIn("studio/zintriq.js", html)
        root = Path(__file__).resolve().parents[1]
        self.assertNotIn("fetch(", (root / "static/studio/factory.js").read_text())
        self.assertNotIn("fetch(", (root / "static/studio/meta-editor.js").read_text())
        self.assertIn("window.zintriq.http", (root / "static/studio/factory.js").read_text())
        self.assertIn("dragover", (root / "static/studio/factory.js").read_text())
        factory_js = (root / "static/studio/factory.js").read_text()
        self.assertIn("refreshInstalledPacks", factory_js)
        self.assertIn("isPluginFile", factory_js)
        self.assertIn("looksLikePluginPack", factory_js)
        self.assertIn("data-pack-disable", factory_js)
        self.assertIn("refreshCurrentDrafts", factory_js)
        self.assertIn("data-pack-disable", (root / "templates" / "studio" / "factory.html").read_text())
        self.assertIn("wb-host", (root / "templates" / "studio" / "_workbench_bar.html").read_text())
        self.assertIn("overflow-x: auto", (root / "static" / "studio" / "workbench.css").read_text())
        community_js = (root / "static/studio/community.js").read_text()
        self.assertIn('window.location.href = "/studio"', community_js)
        self.assertIn("/api/plugin/use", community_js)
        self.assertIn("applyPackFocus", community_js)
        self.assertIn("da-stamp-id", (root / "templates" / "studio" / "community.html").read_text())
        self.assertIn("me-host-tools", (root / "templates" / "studio" / "meta_editor.html").read_text())
        self.assertIn("hardware_host_unlocked", (root / "plugin_catalog.py").read_text())
        self.assertIn("verify_pack_digest", (root / "plugin_catalog.py").read_text())
        self.assertIn("pack_document_code", (root / "plugin_catalog.py").read_text())
        self.assertNotIn('class="da-welcome"', (root / "templates" / "studio" / "settings.html").read_text())
        workbench_js = (root / "static/studio/workbench.js").read_text()
        self.assertIn("switchSurface", workbench_js)
        self.assertIn("zintriq-draft-slug", workbench_js)
        self.assertIn("BroadcastChannel", (root / "static/studio/editor-views.js").read_text())
        self.assertIn("stamp-target", (root / "static/studio/meta-editor.js").read_text())
        zintriq = (root / "static/studio/zintriq.js").read_text()
        self.assertIn("zintriqInvokeHttp", zintriq)
        self.assertIn("kind: \"form\"", zintriq)
        self.assertIn("dragover", zintriq)
        self.assertIn("openPack", zintriq)
        self.assertIn("data-part-add", (root / "static/studio/meta-editor.js").read_text())
        self.assertIn("data-part-kind", (root / "static/studio/meta-editor.js").read_text())
        self.assertIn("data-part-duplicate", (root / "static/studio/meta-editor.js").read_text())
        self.assertIn("data-part-move", (root / "static/studio/meta-editor.js").read_text())
        self.assertIn("/api/builder-core/meta/system-part", (root / "static/studio/meta-editor.js").read_text())
        editor_js = (root / "static/studio/meta-editor.js").read_text()
        self.assertIn("me-graph-canvas", editor_js)
        self.assertIn("source !== \"code\"", editor_js)
        self.assertIn("renderSpaceDoc", editor_js)
        diagram_js = (root / "static" / "studio" / "editors" / "diagram.js").read_text()
        self.assertIn("hitTest", diagram_js)
        self.assertIn("applyVisual", diagram_js)
        self.assertNotIn("fetch(", diagram_js)
        engine_js = (root / "static" / "studio" / "editor-views.js").read_text()
        self.assertIn("bindDocument", engine_js)
        self.assertIn("hitTest", engine_js)
        self.assertIn("getPropertyPanel", engine_js)
        core_js = (root / "static" / "studio" / "engine.js").read_text()
        self.assertIn("history", core_js)
        self.assertIn("selection", core_js)
        self.assertIn("command", core_js)
        self.assertIn("ZintriqEngine", core_js)
        self.assertIn("meta.instantiate", editor_js)
        self.assertIn("applyCode", engine_js)
        pack_js = (root / "static" / "studio" / "editors" / "pack.js").read_text()
        self.assertNotIn("fetch(", pack_js)
        self.assertIn("data-plugin-merge", (root / "static" / "studio" / "editors" / "plugin-kit.js").read_text())
        self.assertIn("data-plugin-replace", (root / "static" / "studio" / "editors" / "plugin-kit.js").read_text())
        self.assertIn("runtime: \"shader\"", pack_js)
        self.assertIn("/api/builder-core/meta/collab", editor_js)
        self.assertIn("/api/builder-core/meta/hardware/ports", editor_js)
        meta_html = self.client.get("/studio/meta").get_data(as_text=True)
        self.assertIn("studio/engine.js", meta_html)
        self.assertIn('id="me-props"', meta_html)
        self.assertIn("studio/editors/runtimes.js", meta_html)
        self.assertIn("studio/editors/solvers.js", meta_html)
        self.assertIn('id="me-statusbar"', meta_html)
        self.assertIn("me-hw-flash", meta_html)
        self.assertIn("me-hw-ssid", meta_html)
        self.assertIn("me-hw-bus", meta_html)
        self.assertIn("me-hw-bus-open", meta_html)
        self.assertIn("/api/builder-core/meta/hardware/buses", editor_js)
        self.assertIn("/api/builder-core/meta/hardware/buses/session", editor_js)
        self.assertIn("bindDock", (root / "static" / "studio" / "workbench.js").read_text())
        self.assertIn('name="me-code-lang"', meta_html)
        self.assertIn("me-canvas-tree", meta_html)
        self.assertIn("/api/builder-core/meta/hardware/flash", editor_js)
        self.assertIn("kindValue: \"scene\"", pack_js)
        self.assertIn("sheet:", pack_js)
        for plugin_id in ("scene", "text", "spreadsheet", "quantum", "meta-meta"):
            self.assertIn('id: "' + plugin_id + '"', pack_js)
        kit_js = (root / "static" / "studio" / "editors" / "plugin-kit.js").read_text()
        self.assertIn("makePlugin", kit_js)
        self.assertIn("domainRoot", kit_js)
        self.assertIn("data-field-id", kit_js)
        self.assertIn("{ merge: true, field: spec.id }", kit_js)
        self.assertIn("opts.merge && opts.field", editor_js)
        self.assertNotIn("fetch(", kit_js)
        self.assertIn("/studio/meta?new=1", html)
        self.assertIn("Add plugin", html)
        self.assertIn('id="da-probe"', html)
        self.assertIn("/app/community", html)
        self.assertIn(">New</a>", html)
        self.assertIn("Add plugin", html)
        self.assertIn("Save as plugin", meta_html)
        self.assertIn("Export webpage", meta_html)
        self.assertIn("Export app", meta_html)
        self.assertIn("Export plugin pack", meta_html)
        self.assertNotIn("New description", html)
        self.assertNotIn("follows the description", html)
        self.assertNotIn("Meta space", html)
        self.assertNotIn("da-layers", html)
        self.assertIn("/studio/meta/shelf-draft", html)
        self.assertNotIn("/studio/simulate/shelf-draft", html)
        self.assertNotIn("/studio/instantiate/shelf-draft", html)
        self.assertIn("/build/shelf-page/home", html)
        self.assertIn("/api/builder-core/meta/sites/shelf-page/zip", html)
        self.assertIn('data-draft-row="shelf-draft"', html)
        self.assertIn("Right-click for Fill / Rename / Remove", html)
        self.assertIn('data-remove-site="shelf-page"', html)
        self.assertNotIn("zw-primitive-strip", html)
        self.assertNotIn("zw-project-grid", html)
        self.assertNotIn("workspace-dashboard.js", html)
        self.assertNotIn("new-composition", html)
        retired = self.client.get("/studio/p/1", follow_redirects=False)
        self.assertIn(retired.status_code, (301, 302, 303))
        self.assertTrue((retired.headers.get("Location") or "").endswith("/studio"))
        editor_js = self.client.get("/static/builder/universal-builder.js")
        self.assertEqual(editor_js.status_code, 404)
        transfer_js = self.client.get("/static/builder/project-transfer.js")
        self.assertEqual(transfer_js.status_code, 404)
        packed = self.client.post(
            "/api/builder-core/transfer/export/1",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf}),
        )
        self.assertEqual(packed.status_code, 404)
        self.assertNotIn(">Data</strong>", html)
        index = self.client.get("/api/builder-core/meta/index", headers=self.headers)
        self.assertEqual(index.status_code, 200)
        body = index.get_json()
        slugs = {item["slug"] for item in body["drafts"]}
        self.assertIn("shelf-draft", slugs)
        arts = {item["slug"] for item in body["artifacts"]}
        self.assertIn("shelf-page", arts)
        built = next(item for item in body["artifacts"] if item["slug"] == "shelf-page")
        self.assertIn("home.html", built["files"])
        self.assertEqual(built["zip_url"], "/api/builder-core/meta/sites/shelf-page/zip")
        from builder_http_support import disable_application_host

        disable_application_host()
        client = self.app.test_client()
        self.assertEqual(client.get("/api/builder-core/meta/index").status_code, 404)

    def test_web_cannot_save_drafts(self):
        from builder_http_support import disable_application_host

        disable_application_host()
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["csrf_token"] = "csrf-web"
        resp = client.post(
            "/api/builder-core/meta/drafts",
            headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf-web"},
            data=json.dumps({"csrf_token": "csrf-web", "slug": "x", "code": "{}"}),
        )
        self.assertEqual(resp.status_code, 404)

    def test_desktop_missing_page_stays_in_studio(self):
        missing = self.client.get("/this-is-not-a-studio-page")
        self.assertEqual(missing.status_code, 404)
        html = missing.get_data(as_text=True)
        self.assertIn("Back to Studio", html)
        self.assertIn('href="/studio"', html)
        self.assertNotIn("mq-public-header", html)
        self.assertNotIn("Go home", html)
        self.assertNotIn("/product", html)
        self.assertNotIn("marketing.css", html)
        home = self.client.get("/", follow_redirects=False)
        self.assertIn(home.status_code, (301, 302, 303))
        self.assertTrue((home.headers.get("Location") or "").endswith("/studio"))

    def test_web_missing_page_keeps_site_home(self):
        from builder_http_support import disable_application_host

        disable_application_host()
        client = self.app.test_client()
        missing = client.get("/this-is-not-a-studio-page")
        self.assertEqual(missing.status_code, 404)
        html = missing.get_data(as_text=True)
        self.assertIn("mq-error-state", html)
        self.assertIn("Go home", html)

    def test_api_ai_requires_local_weights(self):
        missing = self.client.post(
            "/api/ai",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "prompt": "hi", "model": "local.json"}),
        )
        self.assertEqual(missing.status_code, 404)
        body = missing.get_json()
        self.assertFalse(body.get("hosted"))
        from meta.runtime.local_infer import write_fixture_weights

        write_fixture_weights(self.data_dir, "local.json")
        ok = self.client.post(
            "/api/ai",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "prompt": "hello",
                "model": "local.json",
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 4,
            }),
        )
        self.assertEqual(ok.status_code, 200, ok.get_data(as_text=True)[:400])
        session = ok.get_json()
        self.assertFalse(session["hosted"])
        self.assertTrue(session["local"])
        self.assertTrue(session["output"])
        streamed = self.client.post(
            "/api/ai",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "prompt": "hello",
                "model": "local.json",
                "stream": True,
                "max_tokens": 4,
            }),
        )
        self.assertEqual(streamed.status_code, 200)
        self.assertIn("application/x-ndjson", streamed.headers.get("Content-Type", ""))
        self.assertIn("hosted", streamed.get_data(as_text=True))
        embed = self.client.post(
            "/api/ai/embed",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "text": "hello", "model": "local.json"}),
        )
        self.assertEqual(embed.status_code, 200, embed.get_data(as_text=True)[:400])
        self.assertFalse(embed.get_json()["openai"])
        tools = self.client.post(
            "/api/builder-core/meta/ai/tools",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "tool": "explain", "args": {"prompt": "err"}, "model": "local.json"}),
        )
        self.assertEqual(tools.status_code, 200, tools.get_data(as_text=True)[:400])
        play = self.client.post(
            "/api/builder-core/meta/engine/play",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "code": json.dumps({
                    "form": "struct",
                    "fields": {"kind": {"form": "atom", "type": "string", "value": "scene"}},
                }),
                "frames": 2,
            }),
        )
        self.assertEqual(play.status_code, 200, play.get_data(as_text=True)[:400])
        self.assertFalse(play.get_json()["unity"])

    def test_produce_makes_artifact_without_weights(self):
        made = self.client.post(
            "/api/builder-core/meta/produce",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "prompt": "cube", "slug": "made-cube"}),
        )
        self.assertEqual(made.status_code, 201, made.get_data(as_text=True)[:500])
        body = made.get_json()
        self.assertFalse(body["model"])
        self.assertEqual(body["kind"], "scene")
        self.assertTrue(body["code"])
        self.assertTrue(body.get("public_url") or body.get("slug"))
        page = self.client.post(
            "/api/builder-core/meta/produce",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "kind": "page", "title": "Host page", "slug": "export-page"}),
        )
        self.assertEqual(page.status_code, 201, page.get_data(as_text=True)[:400])
        self.assertEqual(page.get_json()["studio"], "/studio/meta/export-page")
        editor = self.client.get("/studio/meta/export-page")
        self.assertEqual(editor.status_code, 200)
        self.assertIn("export-page", editor.get_data(as_text=True))

    def test_plugin_disable_remove_reclaims_official_tools(self):
        first = self.client.post(
            "/api/plugin/stamp",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "name": "Scene A", "form": "Scene"}),
        )
        self.assertEqual(first.status_code, 201, first.get_data(as_text=True)[:400])
        ident = first.get_json()["pack"]["id"]
        listed = self.client.get("/api/plugin", headers=self.headers).get_json()
        row = next(item for item in listed["packs"] if item["id"] == ident)
        self.assertTrue(row["installed"])
        self.assertTrue(row["stamp"])
        views = self.client.get("/api/builder-core/meta/views?surface=describe", headers=self.headers)
        self.assertIn("scene", {item["id"] for item in views.get_json()["views"]})
        second = self.client.post(
            "/api/plugin/stamp",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "name": "Scene B", "form": "Scene"}),
        )
        self.assertEqual(second.status_code, 201, second.get_data(as_text=True)[:400])
        other = second.get_json()["pack"]["id"]
        disabled = self.client.post(
            "/api/plugin/disable",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": ident}),
        )
        self.assertEqual(disabled.status_code, 200, disabled.get_data(as_text=True)[:400])
        self.assertTrue(disabled.get_json()["disabled"])
        self.assertFalse(disabled.get_json()["deleted"])
        still = self.client.get("/api/builder-core/meta/views?surface=describe", headers=self.headers)
        self.assertIn("scene", {item["id"] for item in still.get_json()["views"]})
        removed = self.client.post(
            "/api/plugin/remove",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": other}),
        )
        self.assertEqual(removed.status_code, 200, removed.get_data(as_text=True)[:400])
        self.assertTrue(removed.get_json()["deleted"])
        gone = self.client.get("/api/builder-core/meta/views?surface=describe", headers=self.headers)
        self.assertNotIn("scene", {item["id"] for item in gone.get_json()["views"]})
        packs = {item["id"] for item in self.client.get("/api/plugin", headers=self.headers).get_json()["packs"]}
        self.assertIn(ident, packs)
        self.assertNotIn(other, packs)
        official = self.client.post(
            "/api/plugin/install",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": "official-scene"}),
        )
        self.assertEqual(official.status_code, 200)
        back = self.client.get("/api/builder-core/meta/views?surface=describe", headers=self.headers)
        self.assertIn("scene", {item["id"] for item in back.get_json()["views"]})
        drop_official = self.client.post(
            "/api/plugin/disable",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": "official-scene"}),
        )
        self.assertEqual(drop_official.status_code, 200)
        locked = self.client.get("/api/builder-core/meta/views?surface=describe", headers=self.headers)
        self.assertNotIn("scene", {item["id"] for item in locked.get_json()["views"]})

    def test_stamp_overwrites_same_name_then_install(self):
        first = self.client.post(
            "/api/plugin/stamp",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "name": "Rewrite Me", "form": "Scene"}),
        )
        self.assertEqual(first.status_code, 201, first.get_data(as_text=True)[:400])
        ident = first.get_json()["pack"]["id"]
        self.assertFalse(first.get_json().get("replaced"))
        second = self.client.post(
            "/api/plugin/stamp",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "name": "Rewrite Me",
                "form": "Scene",
                "document": {"form": "atom", "type": "string", "value": "next", "has_value": True},
            }),
        )
        self.assertEqual(second.status_code, 201, second.get_data(as_text=True)[:400])
        body = second.get_json()
        self.assertTrue(body["replaced"])
        self.assertEqual(body["pack"]["id"], ident)
        self.assertEqual((body["pack"].get("document") or {}).get("value"), "next")
        listed = self.client.get("/api/plugin", headers=self.headers).get_json()["packs"]
        matches = [row for row in listed if row.get("name") == "Rewrite Me"]
        self.assertEqual(len(matches), 1)
        installed = self.client.post(
            "/api/plugin/install",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": ident}),
        )
        self.assertEqual(installed.status_code, 200, installed.get_data(as_text=True)[:400])
        installed_body = installed.get_json()
        self.assertTrue(installed_body.get("refreshed"))
        self.assertTrue(installed_body.get("studio"))
        self.assertIn("/studio/meta/", installed_body["studio"])
        from desktop.meta_store import current_draft_slug, load_draft

        slug = installed_body["slug"]
        self.assertEqual(current_draft_slug(), slug)
        draft = load_draft(slug)
        self.assertIn("next", draft["code"])
        editor = self.client.get("/studio/meta/" + slug)
        self.assertEqual(editor.status_code, 200)
        views = self.client.get("/api/builder-core/meta/views?surface=describe", headers=self.headers)
        self.assertIn("scene", {item["id"] for item in views.get_json()["views"]})
        used = self.client.post(
            "/api/plugin/project",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "ids": [ident], "title": "Rewrite Me"}),
        )
        self.assertEqual(used.status_code, 201, used.get_data(as_text=True)[:400])
        used_slug = used.get_json()["slug"]
        third = self.client.post(
            "/api/plugin/stamp",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "name": "Rewrite Me",
                "form": "Scene",
                "document": {"form": "atom", "type": "string", "value": "after-use", "has_value": True},
            }),
        )
        self.assertEqual(third.status_code, 201, third.get_data(as_text=True)[:400])
        again = self.client.post(
            "/api/plugin/install",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": ident}),
        )
        self.assertEqual(again.status_code, 200, again.get_data(as_text=True)[:400])
        self.assertEqual(again.get_json()["slug"], used_slug)
        self.assertIn("after-use", load_draft(used_slug)["code"])
        self.assertEqual(current_draft_slug(), used_slug)
        again_use = self.client.post(
            "/api/plugin/project",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "ids": [ident], "title": "Rewrite Me"}),
        )
        self.assertEqual(again_use.status_code, 201)
        self.assertEqual(again_use.get_json()["slug"], used_slug)

    def test_install_keeps_current_draft_and_new_uses_scene(self):
        from desktop.meta_store import current_draft_slug, load_draft

        saved = self.client.post(
            "/api/builder-core/meta/drafts",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "slug": "keep-me", "code": "{}"}),
        )
        self.assertEqual(saved.status_code, 200, saved.get_data(as_text=True)[:400])
        self.assertEqual(current_draft_slug(), "keep-me")
        installed = self.client.post(
            "/api/plugin/install",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": "official-scene"}),
        )
        self.assertEqual(installed.status_code, 200, installed.get_data(as_text=True)[:400])
        body = installed.get_json()
        self.assertEqual(body.get("draft"), "keep-me")
        self.assertEqual(body.get("home"), "/studio")
        self.assertEqual(current_draft_slug(), "keep-me")
        self.assertEqual(load_draft("keep-me")["code"], "{}")
        home = self.client.get("/studio?draft=keep-me&pane=scene")
        home_html = home.get_data(as_text=True)
        self.assertIn("keep-me", home_html)
        self.assertIn('data-editor-view="scene"', home_html)
        self.assertIn("data-pack-id=\"official-scene\"", home_html)
        fresh = self.client.get("/studio/meta?new=1")
        fresh_html = fresh.get_data(as_text=True)
        self.assertIn("cube", fresh_html)
        self.assertNotIn("Welcome.", fresh_html)

    def test_hardware_bar_only_on_instantiate(self):
        installed = self.client.post(
            "/api/plugin/install",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": "official-robotics"}),
        )
        self.assertEqual(installed.status_code, 200, installed.get_data(as_text=True)[:400])
        describe = self.client.get("/studio/meta").get_data(as_text=True)
        self.assertRegex(describe, r'id="me-hw"[^>]*hidden')
        inst = self.client.get("/studio/instantiate").get_data(as_text=True)
        self.assertIn('id="me-hw"', inst)
        self.assertNotRegex(inst, r'id="me-hw"[^>]*hidden')

    def test_stamp_same_id_overwrites_pack(self):
        first = self.client.post(
            "/api/plugin/stamp",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "name": "Same Pack", "form": "Scene"}),
        )
        self.assertEqual(first.status_code, 201, first.get_data(as_text=True)[:400])
        ident = first.get_json()["pack"]["id"]
        second = self.client.post(
            "/api/plugin/stamp",
            headers=self.headers,
            data=json.dumps({
                "csrf_token": self.csrf,
                "id": ident,
                "name": "Same Pack v2",
                "form": "Scene",
                "document": {"form": "atom", "type": "string", "value": "overwritten", "has_value": True},
            }),
        )
        self.assertEqual(second.status_code, 201, second.get_data(as_text=True)[:400])
        self.assertTrue(second.get_json()["replaced"])
        self.assertEqual(second.get_json()["pack"]["id"], ident)
        listed = self.client.get("/api/plugin", headers=self.headers).get_json()["packs"]
        self.assertEqual(len([row for row in listed if row.get("id") == ident]), 1)

    def test_use_without_draft_opens_pack_skeleton(self):
        from desktop.meta_store import current_draft_slug, load_draft

        installed = self.client.post(
            "/api/plugin/install",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": "official-scene"}),
        )
        self.assertEqual(installed.status_code, 200, installed.get_data(as_text=True)[:400])
        used = self.client.post(
            "/api/plugin/use",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": "official-scene"}),
        )
        self.assertEqual(used.status_code, 200, used.get_data(as_text=True)[:400])
        body = used.get_json()
        self.assertTrue(body.get("slug"))
        self.assertIn("/studio/meta/", body.get("studio") or "")
        self.assertEqual(body.get("pane"), "scene")
        self.assertEqual(current_draft_slug(), body["slug"])
        self.assertIn("cube", load_draft(body["slug"])["code"])

    def test_desc_json_opens_not_install(self):
        from desktop.meta_store import import_stamp_bytes, load_draft

        raw = json.dumps({"form": "atom", "type": "string", "value": "site-desc", "has_value": True}).encode("utf-8")
        out = import_stamp_bytes(raw, slug="open-desc")
        self.assertEqual(out.get("kind"), "desc")
        self.assertIn("/studio/meta/open-desc", out.get("studio") or "")
        self.assertIn("site-desc", load_draft("open-desc")["code"])

    def test_new_picks_single_primary_skeleton(self):
        from plugin_catalog import default_new_code
        from desktop.meta_store import data_dir

        for ident in ("official-scene", "official-ui"):
            res = self.client.post(
                "/api/plugin/install",
                headers=self.headers,
                data=json.dumps({"csrf_token": self.csrf, "id": ident}),
            )
            self.assertEqual(res.status_code, 200, res.get_data(as_text=True)[:400])
        code = default_new_code(data_dir())
        self.assertIn("cube", code)
        self.assertNotIn('"parts"', code)

    def test_stamp_target_preview_and_portal_sha256(self):
        from plugin_catalog import official_pack_file, pack_sha256, verify_pack_digest

        tip = self.client.get("/api/plugin/stamp-target?name=Preview%20Pack", headers=self.headers)
        self.assertEqual(tip.status_code, 200)
        self.assertTrue(str(tip.get_json().get("id") or "").startswith("community-"))
        pack = official_pack_file("scene.zintriq-plugin.json")
        self.assertEqual(pack["sha256"], pack_sha256(pack))
        verify_pack_digest(pack, required=True)
        portal = self.client.get("/plugins/files/scene.zintriq-plugin.json")
        self.assertEqual(portal.status_code, 200)
        downloaded = portal.get_json()
        self.assertEqual(downloaded.get("sha256"), pack["sha256"])
        verify_pack_digest(downloaded, required=True)

    def test_cold_start_keeps_current_draft_pointer(self):
        from desktop.meta_store import current_draft_slug

        fresh = self.client.get("/studio/meta?new=1")
        self.assertEqual(fresh.status_code, 200)
        slug = current_draft_slug()
        self.assertTrue(slug)
        home = self.client.get("/studio")
        html = home.get_data(as_text=True)
        self.assertIn(f'data-draft-slug="{slug}"', html)
        self.assertIn(f'data-draft-row="{slug}"', html)
        self.assertIn("is-current", html)
        self.assertIn("da-draft-empty", html)
        self.assertIn("Current · Empty", html)
        self.assertIn("is-current-empty", html)
        self.assertIn("Right-click for Fill", html)
        self.assertNotIn(f'data-fill-draft="{slug}"', html)

    def test_rename_draft_and_empty_flag(self):
        from desktop.meta_store import current_draft_slug, draft_is_empty, load_draft

        self.assertTrue(draft_is_empty("{}"))
        self.assertFalse(draft_is_empty('{"form":"atom"}'))
        saved = self.client.post(
            "/api/builder-core/meta/drafts",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "slug": "rename-me", "code": "{}"}),
        )
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.get_json().get("empty") or load_draft("rename-me")["empty"])
        renamed = self.client.post(
            "/api/builder-core/meta/drafts/rename",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "slug": "rename-me", "to": "renamed-doc"}),
        )
        self.assertEqual(renamed.status_code, 200, renamed.get_data(as_text=True)[:400])
        self.assertEqual(renamed.get_json()["slug"], "renamed-doc")
        self.assertEqual(current_draft_slug(), "renamed-doc")
        self.assertTrue(load_draft("renamed-doc")["empty"])

    def test_portal_copy_sha256_and_modes_scroll(self):
        from desktop.layout import normalize_layout
        from desktop.meta_store import load_layout, save_layout

        layout = normalize_layout({"modesScroll": 240, "pane": "scene"})
        self.assertEqual(layout["modesScroll"], 240)
        self.assertEqual(layout["pane"], "scene")
        saved = save_layout({"modesScroll": 320, "pane": "ui", "groups": layout.get("groups") or []})
        self.assertEqual(saved["modesScroll"], 320)
        self.assertEqual(saved["pane"], "ui")
        disk = (Path(self.data_dir) / "workbench-layout.json").read_text(encoding="utf-8")
        self.assertIn('"modesScroll": 320', disk)
        self.assertIn('"pane": "ui"', disk)
        loaded = load_layout()
        self.assertEqual(loaded["modesScroll"], 320)
        self.assertEqual(loaded["pane"], "ui")
        plugins = self.client.get("/plugins").get_data(as_text=True)
        self.assertIn("data-copy-sha256", plugins)
        self.assertIn("page.plugins.copy_sha256", (Path(__file__).resolve().parents[1] / "templates/marketing/plugins.html").read_text())
        site_chrome = (Path(__file__).resolve().parents[1] / "static/js/site-chrome.js").read_text()
        self.assertIn("data-copy-sha256", site_chrome)
        self.assertIn("showCopyToast", site_chrome)
        self.assertIn("mq-toast", site_chrome)
        factory_js = (Path(__file__).resolve().parents[1] / "static/studio/factory.js").read_text()
        self.assertIn("openLocalFiles", factory_js)
        self.assertIn("skippedQueue", factory_js)
        self.assertIn("Retry ", factory_js)
        self.assertIn("Retry all", factory_js)
        self.assertIn("Retrying ", factory_js)
        self.assertIn("data-retry-cancel", factory_js)
        self.assertIn("Confirm cancel?", factory_js)
        self.assertIn("da-skipped-lead", factory_js)
        self.assertIn("Install UI & Fill", factory_js)
        self.assertIn("Install Scene & Fill", factory_js)
        self.assertIn("Retry install & Fill", factory_js)
        self.assertIn("paintFillInstallFail", factory_js)
        self.assertIn("data-fill-draft-link", factory_js)
        self.assertIn("Open Community", factory_js)
        self.assertIn("Occupied:", factory_js)
        self.assertIn("free_slots", factory_js)
        self.assertIn("data-rename-slot", factory_js)
        self.assertIn("Other name", factory_js)
        self.assertIn("data-rename-custom", factory_js)
        self.assertIn("is-occupied", factory_js)
        self.assertIn("loadTakenSlugSet", factory_js)
        self.assertIn("pointerdown", factory_js)
        self.assertIn("navigator.vibrate", factory_js)
        self.assertIn("is-hold", factory_js)
        self.assertIn("holdMs", factory_js)
        self.assertIn("zintriq-hold-touch-ms", factory_js)
        self.assertIn("zintriq-binding-cleared", factory_js)
        self.assertIn("zintriq-binding", factory_js)
        self.assertIn("__from", factory_js)
        self.assertIn("Bound draft:", factory_js)
        self.assertIn("fillDraftSlug", factory_js)
        self.assertIn("Rename to ", factory_js)
        self.assertIn("da-draft-menu", factory_js)
        community_js = (Path(__file__).resolve().parents[1] / "static/studio/community.js").read_text()
        self.assertIn("da-reload", (Path(__file__).resolve().parents[1] / "templates/studio/community.html").read_text())
        self.assertIn("zintriq-community-kind", community_js)
        self.assertIn("zintriq-community-q", community_js)
        self.assertIn("syncCommunityUrl", community_js)
        self.assertIn('syncCommunityUrl("push")', community_js)
        self.assertIn("communityPushMax", community_js)
        self.assertIn("zintriq-community-push-max", community_js)
        self.assertIn("popstate", community_js)
        self.assertIn("params.set(\"q\"", community_js)
        self.assertIn("bound to draft", community_js)
        self.assertIn("rebind: true", community_js)
        self.assertIn("binding_cleared", community_js)
        self.assertIn("zintriq-binding-cleared", community_js)
        self.assertIn("zintriq-binding", community_js)
        self.assertIn("prefillStampName", community_js)
        workbench_js = (Path(__file__).resolve().parents[1] / "static/studio/workbench.js").read_text()
        self.assertIn("modesScroll", workbench_js)
        self.assertIn("rebind-timeline", workbench_js)
        self.assertIn("openRebindDrawer", workbench_js)
        self.assertIn("wb-rebind-group", workbench_js)
        self.assertIn("zintriq-rebind-open-pack", workbench_js)
        self.assertIn("refreshRebinds", workbench_js)
        self.assertIn("__zintriqLayoutTimer", workbench_js)
        self.assertIn("layoutDebounceMs", workbench_js)
        self.assertIn("zintriq-layout-debounce", workbench_js)
        self.assertIn("zintriq-focus-hw", workbench_js)
        self.assertIn("zintriq-layout", workbench_js)
        self.assertIn("zintriq-binding", workbench_js)
        self.assertIn("__zintriqWindowId", workbench_js)
        editor_views = (Path(__file__).resolve().parents[1] / "static/studio/editor-views.js").read_text()
        self.assertIn("ESP32 hidden", editor_views)
        self.assertIn("Reinstall Robotics", editor_views)
        self.assertIn("scrollIntoView", editor_views)
        self.assertIn("#me-hw missing", editor_views)
        self.assertIn("Open Instantiate", editor_views)
        self.assertIn("data-hw-open-instantiate", editor_views)
        self.assertIn("zintriq-focus-hw", editor_views)
        self.assertIn("paintFocusFail", editor_views)
        self.assertIn("is-current-empty", (Path(__file__).resolve().parents[1] / "static/desktop-app.css").read_text())
        self.assertIn("is-hold", (Path(__file__).resolve().parents[1] / "static/desktop-app.css").read_text())
        self.assertIn("Right-click for Fill", (Path(__file__).resolve().parents[1] / "templates/studio/factory.html").read_text())
        settings_html = (Path(__file__).resolve().parents[1] / "templates/studio/settings.html").read_text()
        self.assertIn("da-settings-push-max", settings_html)
        self.assertIn("da-settings-layout-debounce", settings_html)
        self.assertIn("da-settings-hold-touch", settings_html)
        self.assertIn("da-settings-prefs-export", settings_html)
        settings_js = (Path(__file__).resolve().parents[1] / "static/studio/workbench-settings.js").read_text()
        self.assertIn("zintriq-community-push-max", settings_js)
        self.assertIn("zintriq-layout-debounce", settings_js)
        self.assertIn("zintriq-hold-touch-ms", settings_js)
        self.assertIn("collectLocalPrefs", settings_js)
        self.assertIn("zintriq-local-prefs", settings_js)
        site_chrome = (Path(__file__).resolve().parents[1] / "static/js/site-chrome.js").read_text()
        self.assertIn("prefersReducedMotion", site_chrome)
        self.assertIn('Escape', site_chrome)
        self.assertIn("dismissCopyToast", site_chrome)
        self.assertIn("pointerup", site_chrome)
        self.assertIn("mq-toast__secs", site_chrome)
        self.assertIn("TOAST_MS", site_chrome)
        self.assertIn("assertModesScrollLayout", (Path(__file__).resolve().parents[1] / "desktop/scripts/smoke.js").read_text())

    def test_fill_empty_rename_suggestion_and_use_rebind(self):
        from desktop.meta_store import current_draft_slug, load_draft
        from plugin_catalog import plugin_drafts, rebind_timeline

        bare = self.client.post(
            "/api/builder-core/meta/drafts",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "slug": "need-pack", "code": "{}"}),
        )
        self.assertEqual(bare.status_code, 200)
        no_pack = self.client.post(
            "/api/builder-core/meta/drafts/fill",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "slug": "need-pack", "id": "auto"}),
        )
        self.assertEqual(no_pack.status_code, 400)
        no_body = no_pack.get_json()
        self.assertEqual(no_body.get("community"), "/app/community")
        self.assertIn("suggest_pack", no_body)
        self.client.post(
            "/api/plugin/install",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": "official-ui"}),
        )
        saved = self.client.post(
            "/api/builder-core/meta/drafts",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "slug": "empty-fill", "code": "{}"}),
        )
        self.assertEqual(saved.status_code, 200)
        filled = self.client.post(
            "/api/builder-core/meta/drafts/fill",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "slug": "empty-fill", "id": "auto"}),
        )
        self.assertEqual(filled.status_code, 200, filled.get_data(as_text=True)[:400])
        body = filled.get_json()
        self.assertEqual(body.get("pack_id"), "official-ui")
        self.assertEqual(body.get("pane"), "ui")
        self.assertFalse(load_draft("empty-fill")["empty"])
        self.client.post(
            "/api/builder-core/meta/drafts",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "slug": "taken-name", "code": "{}"}),
        )
        self.client.post(
            "/api/builder-core/meta/drafts",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "slug": "taken-name-2", "code": "{}"}),
        )
        clash = self.client.post(
            "/api/builder-core/meta/drafts/rename",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "slug": "empty-fill", "to": "taken-name"}),
        )
        self.assertEqual(clash.status_code, 409)
        clash_body = clash.get_json()
        self.assertEqual(clash_body.get("suggestion"), "taken-name-3")
        self.assertEqual(clash_body.get("conflict_chain"), ["taken-name", "taken-name-2"])
        self.assertIn("taken-name-3", clash_body.get("free_slots") or [])
        self.assertIn("taken-name-4", clash_body.get("free_slots") or [])
        self.client.post(
            "/api/plugin/install",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": "official-scene"}),
        )
        first = self.client.post(
            "/api/plugin/use",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": "official-scene"}),
        )
        self.assertEqual(first.status_code, 200)
        first_slug = first.get_json()["slug"]
        self.assertTrue(first.get_json().get("rebound"))
        self.assertEqual(plugin_drafts(Path(self.data_dir)).get("official-scene"), first_slug)
        second = self.client.post(
            "/api/plugin/use",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": "official-scene", "rebind": True}),
        )
        self.assertEqual(second.status_code, 200)
        second_slug = second.get_json()["slug"]
        self.assertNotEqual(first_slug, second_slug)
        self.assertEqual(second.get_json().get("from"), first_slug)
        self.assertEqual(plugin_drafts(Path(self.data_dir)).get("official-scene"), second_slug)
        self.assertEqual(current_draft_slug(), second_slug)
        timeline = rebind_timeline(Path(self.data_dir))
        self.assertTrue(any(row.get("from") == first_slug and row.get("to") == second_slug for row in timeline))
        pack_path = Path(self.data_dir) / "plugins" / "scene.zintriq-plugin.json"
        self.assertTrue(pack_path.is_file())
        removed = self.client.post(
            "/api/plugin/remove",
            headers=self.headers,
            data=json.dumps({"csrf_token": self.csrf, "id": "official-scene", "delete_draft": False}),
        )
        self.assertEqual(removed.status_code, 200, removed.get_data(as_text=True)[:400])
        removed_body = removed.get_json()
        self.assertTrue(removed_body.get("cleared") or removed_body.get("deleted"))
        self.assertEqual(removed_body.get("binding_cleared"), second_slug)
        self.assertNotIn("official-scene", plugin_drafts(Path(self.data_dir)))
        self.assertFalse(pack_path.is_file())


if __name__ == "__main__":
    unittest.main()
