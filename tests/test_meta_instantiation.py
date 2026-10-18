"""Meta-instantiation and the software.page boundary."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from meta.boundary import (
    SOFTWARE_PAGE,
    SOFTWARE_PAGE_ID,
    Boundary,
    BoundaryError,
    boundary_from_desc,
    boundary_to_desc,
    get,
    list_boundaries,
    register,
    reset_for_tests,
)
from meta.description import atom, equivalent, from_json, sequence, struct, to_json
from meta.instantiation import (
    TARGET_DESC,
    TARGET_DESKTOP_HOST,
    TARGET_DEVICE,
    TARGET_OS_HOST,
    TARGET_UIR,
    TARGET_VISUAL,
    TARGET_WEB_BUILD,
    Artifact,
    InstantiationError,
    add_site_page,
    apply_events,
    description_from_artifact,
    instantiate,
    public_url_for_slug,
    remove_site_page,
    render_software_page,
    rendered_site_files,
    site_pages,
    software_page,
    software_site,
    software_system,
    flatten_system_pages,
    system_built_parts,
    validate_asset_name,
    validate_slug,
    zintriq_system_desc,
)
from meta.instantiation.page import HREF_PREVIEW
from meta.simulation import StateMachine, Transition, machine_from_desc, machine_to_desc, step
from meta.uir import visual_to_desc


class MetaInstantiationTests(unittest.TestCase):
    def setUp(self):
        reset_for_tests()

    def tearDown(self):
        reset_for_tests()

    def _machine(self) -> StateMachine:
        return StateMachine(
            state="idle",
            transitions=(
                Transition("idle", "start", "running"),
                Transition("running", "stop", "idle"),
            ),
        )

    def test_software_page_is_builtin(self):
        listed = list_boundaries()
        self.assertIn(SOFTWARE_PAGE, listed)
        self.assertEqual(get(SOFTWARE_PAGE_ID).instantiation_target, TARGET_WEB_BUILD)

    def test_hardware_and_os_boundaries_are_builtins(self):
        from meta.boundary import HARDWARE_MODULE_ID, OS_SURFACE_ID

        ids = {item.id for item in list_boundaries()}
        self.assertIn(HARDWARE_MODULE_ID, ids)
        self.assertIn(OS_SURFACE_ID, ids)
        self.assertEqual(get(HARDWARE_MODULE_ID).kind, "hardware")
        self.assertEqual(get(OS_SURFACE_ID).kind, "os")
        self.assertEqual(get(HARDWARE_MODULE_ID).instantiation_target, TARGET_DEVICE)
        module = struct(
            kind=atom("string", value=HARDWARE_MODULE_ID, has_value=True),
            sense=atom("string", value="presence", has_value=True),
            title=atom("string", value="Sense", has_value=True),
        )
        artifact = instantiate(module, slug="sense-mod")
        self.assertEqual(artifact.target, TARGET_DEVICE)
        self.assertEqual(artifact.boundary_id, HARDWARE_MODULE_ID)
        self.assertTrue(equivalent(module, description_from_artifact(artifact)))
        self.assertIn("esphome:", artifact.payload_object()["esphome"])
        host = struct(
            kind=atom("string", value=OS_SURFACE_ID, has_value=True),
            title=atom("string", value="Host", has_value=True),
        )
        os_art = instantiate(host, slug="host-os")
        self.assertEqual(os_art.boundary_id, OS_SURFACE_ID)
        self.assertEqual(os_art.target, TARGET_OS_HOST)
        plant = software_system(
            title="Plant",
            parts=(
                ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                ("cell", "Cell", module),
            ),
        )
        sys_art = instantiate(plant, slug="plant-hw")
        by_key = {item["key"]: item["artifact"] for item in sys_art.payload_object()["parts"]}
        self.assertEqual(by_key["home"]["target"], TARGET_WEB_BUILD)
        self.assertEqual(by_key["cell"]["target"], TARGET_DEVICE)
        self.assertEqual(by_key["cell"]["boundary_id"], HARDWARE_MODULE_ID)
        names = {name for name, _html in rendered_site_files(sys_art)}
        self.assertIn("home.html", names)
        self.assertIn("cell.json", names)
        with self.assertRaises(BoundaryError):
            register(get(HARDWARE_MODULE_ID))

    def test_boundaries_live_in_meta_space(self):
        from meta.boundary import META_SPACE_ID, space_boundary_ids, space_desc

        ids = set(space_boundary_ids())
        self.assertIn("hardware.module", ids)
        self.assertIn("os.surface", ids)
        self.assertIn("software.page", ids)
        self.assertIn("scene", ids)
        self.assertIn("cad.solid", ids)
        self.assertIn("commerce.checkout", ids)
        self.assertIn("social.channel", ids)
        self.assertIn("ai", ids)
        self.assertNotIn(META_SPACE_ID, ids)
        self.assertEqual(get(META_SPACE_ID).kind, "meta")
        extra = Boundary(
            id="lab.gate",
            name="Lab",
            kind="software",
            instantiation_target=TARGET_WEB_BUILD,
            meta_level=0,
        )
        register(extra)
        self.assertIn("lab.gate", space_boundary_ids())
        artifact = instantiate(space_desc(), slug="meta-space")
        self.assertEqual(artifact.boundary_id, META_SPACE_ID)
        self.assertEqual(artifact.target, TARGET_WEB_BUILD)
        by_key = {item["key"]: item["artifact"] for item in artifact.payload_object()["parts"]}
        self.assertEqual(by_key["software-page"]["target"], TARGET_WEB_BUILD)
        self.assertEqual(by_key["hardware-module"]["target"], TARGET_DEVICE)
        self.assertEqual(by_key["os-surface"]["boundary_id"], "os.surface")
        self.assertEqual(by_key["lab-gate"]["boundary_id"], "lab.gate")

    def test_add_part_kind_registers_boundary_in_space(self):
        from meta.boundary import space_boundary_ids, space_desc
        from meta.instantiation import add_system_part, child_for_part_kind, system_parts

        def kind_of(node):
            kind = dict(node.fields).get("kind")
            return kind.value if getattr(kind, "has_value", False) else ""

        space = space_desc()
        grown = add_system_part(space, part_kind="boundary", title="Custom")
        kinds = [kind_of(child) for _key, _title, child in system_parts(grown)]
        self.assertIn("meta.boundary", kinds)
        self.assertIn("software.part", space_boundary_ids())
        self.assertEqual(kind_of(child_for_part_kind("hardware", title="Sense")), "hardware.module")
        self.assertEqual(kind_of(child_for_part_kind("os", title="Host")), "os.surface")

    def test_install_all_boundaries_walks_nested_structs(self):
        from meta.instantiation import child_for_part_kind
        from meta.instantiation.system import install_all_boundaries

        wrapped = struct(
            kind=atom("string", value="scene", has_value=True),
            title=atom("string", value="Wrap", has_value=True),
            inner=child_for_part_kind("boundary", title="Portal"),
        )
        before = {item.id for item in list_boundaries()}
        install_all_boundaries(wrapped)
        self.assertTrue({item.id for item in list_boundaries()} - before)
        artifact = instantiate(wrapped, slug="wrap-scene")
        self.assertTrue(artifact.checksum)

    def test_search_filters_meta_level(self):
        from desktop.meta_store import rebuild_search_index, save_draft, search_all

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        save_draft(
            "level-two",
            code='{"form":"struct","fields":{"kind":{"form":"atom","type":"string","value":"scene"},"meta_level":{"form":"atom","type":"int","value":2}}}',
            base=root,
        )
        rebuild_search_index(base=root)
        hits = search_all("", meta_level="2", base=root)
        self.assertTrue(any(hit.get("slug") == "level-two" and hit.get("meta_level") == 2 for hit in hits))
        self.assertFalse(any(hit.get("slug") == "level-two" for hit in search_all("", meta_level="9", base=root)))
        ranged = search_all("", meta_level_min="1", meta_level_max="3", base=root)
        self.assertTrue(any(hit.get("slug") == "level-two" for hit in ranged))
        self.assertFalse(any(hit.get("slug") == "level-two" for hit in search_all("", meta_level_min="5", meta_level_max="9", base=root)))

    def test_register_rejects_duplicate(self):
        with self.assertRaises(BoundaryError):
            register(SOFTWARE_PAGE)

    def test_register_custom_boundary(self):
        extra = Boundary(
            id="hardware.chip",
            name="Chip",
            kind="hardware",
            instantiation_target=TARGET_DESC,
            meta_level=0,
        )
        register(extra)
        self.assertEqual(get("hardware.chip").name, "Chip")

    def test_boundary_description_builds_and_registers(self):
        node = boundary_to_desc(
            Boundary(
                id="lab.gate",
                name="Lab gate",
                kind="software",
                instantiation_target=TARGET_WEB_BUILD,
                meta_level=0,
            )
        )
        self.assertEqual(boundary_from_desc(node).id, "lab.gate")
        artifact = instantiate(node, target=TARGET_WEB_BUILD, slug="lab-gate")
        self.assertEqual(artifact.boundary_id, "lab.gate")
        self.assertEqual(get("lab.gate").name, "Lab gate")
        html = render_software_page(artifact)
        self.assertIn('data-page-kind="meta.boundary"', html)
        self.assertIn('data-boundary="lab.gate"', html)
        self.assertIn("<dd>lab.gate</dd>", html)
        self.assertIn("web_build", html)
        again = instantiate(node, target=TARGET_WEB_BUILD, slug="lab-gate")
        self.assertEqual(again.boundary_id, "lab.gate")
        own = instantiate(node, slug="lab-gate-own")
        self.assertEqual(own.target, TARGET_WEB_BUILD)
        self.assertEqual(own.boundary_id, "lab.gate")
        spec = boundary_to_desc(
            Boundary(
                id="lab.spec",
                name="Lab spec",
                kind="software",
                instantiation_target=TARGET_DESC,
                meta_level=0,
            )
        )
        compiled = instantiate(spec)
        self.assertEqual(compiled.target, TARGET_DESC)
        self.assertEqual(compiled.boundary_id, "lab.spec")
        named = instantiate(spec, slug="lab-spec")
        self.assertEqual(named.slug, "lab-spec")
        self.assertEqual(named.public_url, "/build/lab-spec")
        clash = boundary_to_desc(
            Boundary(
                id="lab.gate",
                name="Other",
                kind="software",
                instantiation_target=TARGET_DESC,
                meta_level=0,
            )
        )
        with self.assertRaises(InstantiationError):
            instantiate(clash, target=TARGET_DESC)

    def test_system_description_builds_nested_parts(self):
        gate = boundary_to_desc(
            Boundary(
                id="plant.gate",
                name="Plant gate",
                kind="software",
                instantiation_target=TARGET_WEB_BUILD,
                meta_level=0,
            )
        )
        inner = software_system(
            title="Cell",
            parts=(("note", "Note", software_page(title="Note", body=("Nested.",))),),
        )
        node = software_system(
            title="Plant",
            parts=(
                ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                ("gate", "Gate", gate),
                ("cell", "Cell", inner),
            ),
        )
        artifact = instantiate(node, target=TARGET_WEB_BUILD, slug="plant-sys")
        self.assertEqual(get("plant.gate").name, "Plant gate")
        payload = artifact.payload_object()
        by_key = {item["key"]: item["artifact"] for item in payload["parts"]}
        self.assertEqual(by_key["home"]["target"], TARGET_WEB_BUILD)
        self.assertEqual(by_key["gate"]["target"], TARGET_WEB_BUILD)
        self.assertEqual(by_key["gate"]["boundary_id"], "plant.gate")
        self.assertEqual(by_key["cell"]["target"], TARGET_WEB_BUILD)
        cell = Artifact.from_data(by_key["cell"])
        nested = {item["key"]: item["artifact"] for item in cell.payload_object()["parts"]}
        self.assertEqual(nested["note"]["target"], TARGET_WEB_BUILD)
        names = {name for name, _html in rendered_site_files(artifact)}
        self.assertIn("home.html", names)
        self.assertIn("gate.html", names)
        self.assertIn("cell.html", names)
        self.assertIn("cell-note.html", names)
        built = {key: child.target for key, _title, child in system_built_parts(artifact)}
        self.assertEqual(built["home"], TARGET_WEB_BUILD)
        self.assertEqual(built["cell-note"], TARGET_WEB_BUILD)
        home = render_software_page(artifact)
        self.assertIn('data-page-kind="meta.system"', home)
        self.assertIn('data-part-kind="software.page"', home)
        self.assertIn("Plant home.", home)
        self.assertIn("/build/plant-sys/gate", home)
        gate_html = render_software_page(artifact, page_key="gate")
        self.assertIn('data-part-kind="meta.boundary"', gate_html)
        self.assertIn('data-boundary="plant.gate"', gate_html)
        self.assertIn("plant.gate", gate_html)
        cell = render_software_page(artifact, page_key="cell")
        self.assertIn('data-part-kind="meta.system"', cell)
        self.assertIn("cell-note", cell)
        note = render_software_page(artifact, page_key="cell-note")
        self.assertIn("Nested.", note)

    def test_system_part_follows_boundary_target(self):
        spec = boundary_to_desc(
            Boundary(
                id="plant.spec",
                name="Plant spec",
                kind="software",
                instantiation_target=TARGET_DESC,
                meta_level=0,
            )
        )
        node = software_system(
            title="Plant",
            parts=(
                ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                ("spec", "Spec", spec),
            ),
        )
        artifact = instantiate(node, target=TARGET_WEB_BUILD, slug="plant-mix")
        built = {key: child for key, _title, child in system_built_parts(artifact)}
        self.assertEqual(built["spec"].target, TARGET_DESC)
        self.assertEqual(built["spec"].boundary_id, "plant.spec")
        names = {name for name, _body in rendered_site_files(artifact)}
        self.assertIn("spec.json", names)
        self.assertIn("home.html", names)
        self.assertNotIn("spec.html", names)

    def test_system_site_part_builds_all_pages(self):
        node = software_system(
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
        )
        artifact = instantiate(node, target=TARGET_WEB_BUILD, slug="plant-guide")
        names = {name for name, _html in rendered_site_files(artifact)}
        self.assertIn("guide.html", names)
        self.assertIn("guide-about.html", names)
        overview = render_software_page(artifact, page_key="guide")
        self.assertIn("Wear gloves.", overview)
        self.assertIn("/build/plant-guide/guide-about", overview)
        about = render_software_page(artifact, page_key="guide-about")
        self.assertIn("Station history.", about)
        self.assertIn('data-part-kind="software.page"', about)

    def test_system_nesting_limit(self):
        node = software_page(title="Leaf", body=("x",))
        for _ in range(5):
            node = software_system(title="Wrap", parts=(("n", "N", node),))
        rows = flatten_system_pages(node)
        self.assertGreaterEqual(len(rows), 1)

    def test_desc_target_round_trip(self):
        node = struct(label=atom("string", value="pump", has_value=True))
        artifact = instantiate(node, target=TARGET_DESC)
        self.assertEqual(artifact.boundary_id, "meta.core")
        self.assertEqual(artifact.checksum, artifact.to_data()["checksum"])
        restored = description_from_artifact(artifact)
        self.assertTrue(equivalent(node, restored))

    def test_web_build_maps_to_build_slug(self):
        machine = self._machine()
        artifact = instantiate(
            machine,
            boundary_id=SOFTWARE_PAGE_ID,
            slug="demo-page",
            events=("start",),
        )
        self.assertEqual(artifact.target, TARGET_WEB_BUILD)
        self.assertEqual(artifact.public_url, "/build/demo-page")
        self.assertEqual(artifact.slug, "demo-page")
        body = artifact.payload_object()
        self.assertEqual(body["machine_state"], "running")
        self.assertEqual(body["public_url"], "/build/demo-page")
        recovered = description_from_artifact(artifact)
        self.assertEqual(machine_from_desc(recovered).state, "running")
        self.assertTrue(
            equivalent(recovered, machine_to_desc(step(self._machine(), "start")))
        )

    def test_software_page_html_escapes_and_shows_state(self):
        dirty = struct(label=atom("string", value="<script>x</script>", has_value=True))
        page = render_software_page(instantiate(dirty, target=TARGET_WEB_BUILD, slug="safe-page"))
        self.assertIn('data-boundary="software.page"', page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>x</script>", page)
        machine_html = render_software_page(
            instantiate(self._machine(), target=TARGET_WEB_BUILD, slug="demo-page"),
            step_action="/api/builder-core/meta/page/demo-page/step",
            csrf_token="tok",
        )
        self.assertIn('data-machine-state="idle"', machine_html)
        self.assertIn('name="event" value="start"', machine_html)
        self.assertIn("csrf_token", machine_html)

    def test_document_page_uses_title_and_body(self):
        node = software_page(title="Pump station", body=("Keep guards on.", "<script>x</script>"))
        html = render_software_page(instantiate(node, target=TARGET_WEB_BUILD, slug="pump-doc"))
        self.assertIn('data-page-kind="software.page"', html)
        self.assertIn("<title>Pump station</title>", html)
        self.assertIn("<h1>Pump station</h1>", html)
        self.assertIn("<p>Keep guards on.</p>", html)
        self.assertIn("<p>&lt;script&gt;x&lt;/script&gt;</p>", html)
        self.assertNotIn("<script>x</script>", html)
        heading = struct(
            kind=atom("string", value="software.page", has_value=True),
            title=atom("string", value="Guide", has_value=True),
            body=sequence(
                struct(
                    heading=atom("string", value="Safety", has_value=True),
                    text=atom("string", value="Stop first.", has_value=True),
                )
            ),
        )
        block = render_software_page(instantiate(heading, target=TARGET_WEB_BUILD, slug="guide"))
        self.assertIn("<h2>Safety</h2>", block)
        self.assertIn("<p>Stop first.</p>", block)

    def test_theme_allows_hex_only(self):
        node = software_page(
            title="Night",
            body=("Quiet.",),
            theme={"background": "#0b1020", "color": "#e8eef8", "accent": "#6ea8fe"},
        )
        html = render_software_page(instantiate(node, target=TARGET_WEB_BUILD, slug="night"))
        self.assertIn('data-theme="1"', html)
        self.assertIn("--mp-bg:#0b1020", html)
        self.assertIn("--mp-fg:#e8eef8", html)
        self.assertIn("--mp-accent:#6ea8fe", html)
        dirty = software_page(
            title="Bad",
            body=("x",),
            theme={"background": "url(javascript:alert(1))", "color": "#fff;x", "accent": "red"},
        )
        skipped = render_software_page(instantiate(dirty, target=TARGET_WEB_BUILD, slug="bad-theme"))
        self.assertNotIn("data-theme", skipped)
        self.assertNotIn("javascript", skipped)
        self.assertNotIn("url(", skipped)

    def test_theme_layout_ints_only(self):
        node = software_page(
            title="Wide",
            body=("Room.",),
            theme={"measure": 56, "space": 32, "background": "#fff"},
        )
        html = render_software_page(instantiate(node, target=TARGET_WEB_BUILD, slug="wide"))
        self.assertIn("--mp-measure:56rem", html)
        self.assertIn("--mp-space:32px", html)
        skipped = software_page(
            title="Tight",
            body=("x",),
            theme={"measure": 8, "space": 400, "background": "#fff"},
        )
        skipped_html = render_software_page(instantiate(skipped, target=TARGET_WEB_BUILD, slug="tight"))
        self.assertNotIn("--mp-measure:", skipped_html)
        self.assertNotIn("--mp-space:", skipped_html)
        out_of_range = struct(
            kind=atom("string", value="software.page", has_value=True),
            title=atom("string", value="Range", has_value=True),
            body=sequence(atom("string", value="x", has_value=True)),
            theme=struct(
                measure=atom("int", value=8, has_value=True),
                space=atom("int", value=400, has_value=True),
            ),
        )
        ranged = render_software_page(instantiate(out_of_range, target=TARGET_WEB_BUILD, slug="range"))
        self.assertNotIn("--mp-measure:", ranged)
        self.assertNotIn("--mp-space:", ranged)
        dirty = struct(
            kind=atom("string", value="software.page", has_value=True),
            title=atom("string", value="Hack", has_value=True),
            body=sequence(atom("string", value="x", has_value=True)),
            theme=struct(
                measure=atom("string", value="40rem;background:url(x)", has_value=True),
                space=atom("string", value="24px", has_value=True),
            ),
        )
        dirty_html = render_software_page(instantiate(dirty, target=TARGET_WEB_BUILD, slug="hack-layout"))
        self.assertNotIn("--mp-measure:", dirty_html)
        self.assertNotIn("--mp-space:", dirty_html)
        self.assertNotIn("url(", dirty_html)

    def test_site_routes_pages_and_nav(self):
        site = software_site(
            title="Plant",
            pages=(
                ("home", "Home", ("Welcome.",)),
                ("about", "About", ("About the plant.",)),
            ),
        )
        artifact = instantiate(site, target=TARGET_WEB_BUILD, slug="plant")
        home = render_software_page(artifact, page_key="home")
        about = render_software_page(artifact, page_key="about")
        self.assertIn('data-page-kind="software.site"', home)
        self.assertIn('data-page-key="home"', home)
        self.assertIn("<h1>Home</h1>", home)
        self.assertIn("<p>Welcome.</p>", home)
        self.assertIn('href="/build/plant/about"', home)
        self.assertIn('aria-current="page"', home)
        self.assertIn("<h1>About</h1>", about)
        self.assertIn("<p>About the plant.</p>", about)
        with self.assertRaises(InstantiationError):
            render_software_page(artifact, page_key="missing")
        with self.assertRaises(InstantiationError):
            software_site(title="Empty", pages=())

    def test_static_site_files_use_relative_links(self):
        site = software_site(
            title="Plant",
            pages=(
                ("home", "Home", ("Welcome.",)),
                ("about", "About", ("About the plant.",)),
            ),
        )
        artifact = instantiate(site, target=TARGET_WEB_BUILD, slug="plant")
        files = dict(rendered_site_files(artifact))
        self.assertIn("home.html", files)
        self.assertIn("about.html", files)
        self.assertIn("index.html", files)
        self.assertIn('href="about.html"', files["home.html"])
        self.assertNotIn("/build/plant/about", files["home.html"])
        self.assertNotIn("csrf_token", files["about.html"])
        self.assertNotIn("zintriq-meta", files["home.html"])
        self.assertNotIn("data-mp-page", files["home.html"])
        self.assertEqual(files["index.html"], files["home.html"])

    def test_preview_hrefs_signal_page_keys(self):
        site = software_site(
            title="Plant",
            pages=(
                ("home", "Home", ("Welcome.",)),
                ("about", "About", ("About the plant.",)),
            ),
        )
        artifact = instantiate(site, target=TARGET_WEB_BUILD, slug="plant")
        preview = render_software_page(artifact, page_key="home", href_style=HREF_PREVIEW)
        self.assertIn('data-mp-page="about"', preview)
        self.assertIn('href="#mp-about"', preview)
        self.assertIn("source:'zintriq-meta'", preview)
        self.assertNotIn("/build/plant/about", preview)
        self.assertNotIn("csrf_token", preview)

    def test_add_and_remove_site_page(self):
        site = software_site(
            title="Plant",
            pages=(
                ("home", "Home", ("Welcome.",)),
                ("about", "About", ("About the plant.",)),
            ),
        )
        grown = add_site_page(site)
        keys = [key for key, _title, _page in site_pages(grown)]
        self.assertEqual(keys, ["home", "about", "page"])
        named = add_site_page(grown, key="contact", title="Contact", body=("Write us.",))
        self.assertEqual(
            [key for key, _title, _page in site_pages(named)],
            ["home", "about", "page", "contact"],
        )
        trimmed = remove_site_page(named, "page")
        self.assertEqual(
            [key for key, _title, _page in site_pages(trimmed)],
            ["home", "about", "contact"],
        )
        with self.assertRaises(InstantiationError):
            add_site_page(named, key="home")
        only = software_site(title="One", pages=(("home", "Home", ("Hi.",)),))
        with self.assertRaises(InstantiationError):
            remove_site_page(only, "home")
        with self.assertRaises(InstantiationError):
            add_site_page(software_page(title="Lone", body=("x",)))

    def test_system_nested_site_page_ops(self):
        from meta.instantiation import apply_site_op, duplicate_site_page, flatten_system_pages, software_system

        node = software_system(
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
        )

        def grow(site, _local, _prefix):
            updated = add_site_page(site)
            return updated, site_pages(updated)[-1][0]

        grown, page_key = apply_site_op(node, "guide-about", grow)
        self.assertEqual(page_key, "guide-page")
        self.assertEqual(
            [key for key, _title, _page in flatten_system_pages(grown)],
            ["home", "guide", "guide-about", "guide-page"],
        )

        def trim(site, local, _prefix):
            updated = remove_site_page(site, local)
            return updated, site_pages(updated)[0][0]

        trimmed, next_key = apply_site_op(grown, "guide-page", trim)
        self.assertEqual(next_key, "guide")
        self.assertEqual(
            [key for key, _title, _page in flatten_system_pages(trimmed)],
            ["home", "guide", "guide-about"],
        )
        promoted, added_key = apply_site_op(node, "home", grow, promote=True)
        self.assertEqual(added_key, "home-page")
        self.assertEqual(
            [key for key, _title, _page in flatten_system_pages(promoted)],
            ["home", "home-page", "guide", "guide-about"],
        )
        lone, lone_key = apply_site_op(
            software_page(title="Lone", body=("x",)),
            "home",
            grow,
            promote=True,
        )
        self.assertEqual(lone_key, "page")
        self.assertEqual([key for key, _title, _page in site_pages(lone)], ["home", "page"])

        def copy_page(site, local, _prefix):
            updated = duplicate_site_page(site, local)
            keys = [item[0] for item in site_pages(updated)]
            next_local = keys[-1]
            try:
                next_local = keys[keys.index(local) + 1]
            except (ValueError, IndexError):
                pass
            return updated, next_local

        copied, copy_key = apply_site_op(node, "home", copy_page, promote=True)
        self.assertEqual(copy_key, "home-home-2")
        self.assertEqual(
            [key for key, _title, _page in flatten_system_pages(copied)],
            ["home", "home-home-2", "guide", "guide-about"],
        )
        lone_copy, lone_copy_key = apply_site_op(
            software_page(title="Lone", body=("x",)),
            "home",
            copy_page,
            promote=True,
        )
        self.assertEqual(lone_copy_key, "home-2")
        self.assertEqual([key for key, _title, _page in site_pages(lone_copy)], ["home", "home-2"])

        def shift_page(site, local, _prefix):
            from meta.instantiation import move_site_page

            return move_site_page(site, local, delta=1), local

        shifted, shifted_key = apply_site_op(promoted, "home", shift_page, promote=True)
        self.assertEqual(shifted_key, "home")
        self.assertEqual(
            [key for key, _title, _page in flatten_system_pages(shifted)],
            ["home-page", "home", "guide", "guide-about"],
        )
        lone_moved, lone_moved_key = apply_site_op(lone, "home", shift_page, promote=True)
        self.assertEqual(lone_moved_key, "home")
        self.assertEqual([key for key, _title, _page in site_pages(lone_moved)], ["page", "home"])

    def test_system_add_remove_part(self):
        from meta.instantiation import (
            add_system_part,
            apply_system_part_op,
            duplicate_system_part,
            flatten_system_pages,
            move_system_part,
            remove_system_part,
            software_system,
            system_parts,
        )

        node = software_system(
            title="Plant",
            parts=(
                ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                ("gate", "Gate", software_page(title="Gate", body=("Closed.",))),
            ),
        )

        def grow(system, _part_key):
            updated = add_system_part(system)
            return updated, system_parts(updated)[-1][0]

        grown, page_key = apply_system_part_op(node, "home", grow)
        self.assertEqual(page_key, "part")
        self.assertEqual(
            [key for key, _title, _page in flatten_system_pages(grown)],
            ["home", "gate", "part"],
        )
        inner = software_system(
            title="Cell",
            parts=(("note", "Note", software_page(title="Note", body=("Keep dry.",))),),
        )
        nested = software_system(
            title="Plant",
            parts=(
                ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                ("cell", "Cell", inner),
            ),
        )
        nested_grown, nested_key = apply_system_part_op(nested, "cell-note", grow)
        self.assertEqual(nested_key, "cell-part")
        self.assertEqual(
            [key for key, _title, _page in flatten_system_pages(nested_grown)],
            ["home", "cell", "cell-note", "cell-part"],
        )

        def trim(system, part_key):
            updated = remove_system_part(system, part_key)
            return updated, system_parts(updated)[0][0]

        trimmed, next_key = apply_system_part_op(grown, "part", trim)
        self.assertEqual(next_key, "home")
        self.assertEqual(
            [key for key, _title, _page in flatten_system_pages(trimmed)],
            ["home", "gate"],
        )

        def shift(system, part_key):
            updated = move_system_part(system, part_key, delta=1)
            return updated, part_key

        moved, moved_key = apply_system_part_op(node, "home", shift)
        self.assertEqual(moved_key, "home")
        self.assertEqual(
            [key for key, _title, _page in flatten_system_pages(moved)],
            ["gate", "home"],
        )

        def copy_part(system, part_key):
            updated = duplicate_system_part(system, part_key)
            keys = [item[0] for item in system_parts(updated)]
            return updated, keys[keys.index(part_key) + 1]

        copied, copy_key = apply_system_part_op(node, "home", copy_part)
        self.assertEqual(copy_key, "home-2")
        self.assertEqual(
            [key for key, _title, _page in flatten_system_pages(copied)],
            ["home", "home-2", "gate"],
        )
        with self.assertRaises(InstantiationError):
            apply_system_part_op(
                software_site(title="Site", pages=(("home", "Home", ("Hi.",)),)),
                "home",
                grow,
            )

    def test_system_page_part_copy_and_rename(self):
        from meta.instantiation import apply_page_part_update, document_copy, flatten_system_pages, software_system

        node = software_system(
            title="Plant",
            parts=(
                ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                ("gate", "Gate", software_page(title="Gate", body=("Closed.",))),
            ),
        )
        rewritten, key = apply_page_part_update(
            node,
            "home",
            title="Overview",
            blocks=[{"kind": "paragraph", "text": "Rewritten home."}],
            new_key="intro",
        )
        self.assertEqual(key, "intro")
        self.assertEqual(
            [item[0] for item in flatten_system_pages(rewritten)],
            ["intro", "gate"],
        )
        lone, _page_key = apply_page_part_update(
            software_page(title="Lone", body=("x",)),
            "",
            title="Named",
            blocks=[{"kind": "paragraph", "text": "One."}],
        )
        self.assertEqual(document_copy(lone), ("Named", ("One.",)))

    def test_system_boundary_part_copy_and_rename(self):
        from meta.instantiation import apply_boundary_part_update, document_copy, flatten_system_pages, software_system

        gate = boundary_to_desc(
            Boundary(
                id="plant.gate",
                name="Plant gate",
                kind="software",
                instantiation_target=TARGET_WEB_BUILD,
                meta_level=0,
            )
        )
        node = software_system(
            title="Plant",
            parts=(
                ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                ("gate", "Gate", gate),
            ),
        )
        rewritten, key = apply_boundary_part_update(
            node,
            "gate",
            title="Portal",
            new_key="portal",
            bound_id="plant.portal",
            surface_kind="meta",
            target=TARGET_DESC,
            meta_level=2,
        )
        self.assertEqual(key, "portal")
        self.assertEqual(
            [item[0] for item in flatten_system_pages(rewritten)],
            ["home", "portal"],
        )
        self.assertEqual(document_copy(rewritten, "portal"), ("Portal", ()))
        described = boundary_from_desc(flatten_system_pages(rewritten)[1][2])
        self.assertEqual(described.id, "plant.portal")
        self.assertEqual(described.name, "Portal")
        self.assertEqual(described.kind, "meta")
        self.assertEqual(described.instantiation_target, TARGET_DESC)
        self.assertEqual(described.meta_level, 2)
        from meta.instantiation import boundary_copy

        self.assertEqual(
            boundary_copy(rewritten, "portal"),
            {
                "id": "plant.portal",
                "meta_level": 2,
                "name": "Portal",
                "surface": "meta",
                "target": TARGET_DESC,
            },
        )
        with self.assertRaises(InstantiationError):
            apply_boundary_part_update(rewritten, "portal", title="Portal", target="nope")
        with self.assertRaises(InstantiationError):
            apply_boundary_part_update(rewritten, "portal", title="Portal", meta_level=-1)
        lone, _page_key = apply_boundary_part_update(
            boundary_to_desc(
                Boundary(
                    id="lab.gate",
                    name="Lab gate",
                    kind="software",
                    instantiation_target=TARGET_WEB_BUILD,
                    meta_level=0,
                )
            ),
            "",
            title="Named gate",
            bound_id="lab.named",
            surface_kind="software",
            target=TARGET_WEB_BUILD,
        )
        self.assertEqual(document_copy(lone), ("Named gate", ()))
        self.assertEqual(boundary_from_desc(lone).id, "lab.named")

    def test_system_surface_ops_and_nested_title(self):
        from meta.instantiation import (
            apply_system_node_update,
            copy_surface,
            flatten_system_pages,
            software_system,
            theme_copy,
        )

        inner = software_system(
            title="Cell",
            parts=(("note", "Note", software_page(title="Note", body=("Nested.",))),),
        )
        node = software_system(
            title="Plant",
            parts=(
                ("home", "Home", software_page(title="Home", body=("Plant home.",))),
                ("gate", "Gate", boundary_to_desc(Boundary(
                    id="plant.gate",
                    name="Plant gate",
                    kind="software",
                    instantiation_target=TARGET_WEB_BUILD,
                    meta_level=0,
                ))),
                ("cell", "Cell", inner),
            ),
        )
        self.assertEqual(copy_surface(node, "home"), "page")
        self.assertEqual(copy_surface(node, "gate"), "boundary")
        self.assertEqual(copy_surface(node, "cell"), "system")
        self.assertIsNone(theme_copy(node, "gate"))
        self.assertIsNone(theme_copy(node, "cell"))
        self.assertIsNotNone(theme_copy(node, "home"))
        rewritten, key = apply_system_node_update(
            node,
            "cell",
            title="Module",
            new_key="module",
        )
        self.assertEqual(key, "module")
        self.assertEqual(
            [item[0] for item in flatten_system_pages(rewritten)],
            ["home", "gate", "module", "module-note"],
        )
        self.assertEqual(copy_surface(rewritten, "module"), "system")

    def test_step_at_system_part_and_root_title(self):
        from meta.instantiation import apply_step_at_key, root_system_title, set_system_title, software_system
        from meta.simulation import StateMachine, Transition, machine_from_desc, machine_to_desc

        node = software_system(
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
        )
        stepped, key = apply_step_at_key(node, "flow", "start")
        self.assertEqual(key, "flow")
        self.assertEqual(machine_from_desc(flatten_system_pages(stepped)[1][2]).state, "running")
        self.assertEqual(machine_from_desc(flatten_system_pages(node)[1][2]).state, "idle")
        named = set_system_title(stepped, "Garden")
        self.assertEqual(root_system_title(named), "Garden")
        lone, _key = apply_step_at_key(
            machine_to_desc(StateMachine(
                state="idle",
                transitions=(Transition("idle", "start", "running"),),
            )),
            "",
            "start",
        )
        self.assertEqual(machine_from_desc(lone).state, "running")

    def test_update_page_copy(self):
        site = software_site(
            title="Plant",
            pages=(
                ("home", "Home", ("Welcome.",)),
                ("about", "About", ("About the plant.",)),
            ),
        )
        from meta.instantiation import document_copy, update_page_copy

        rewritten = update_page_copy(
            site,
            key="about",
            title="History",
            body="First.\n\nSecond.",
        )
        self.assertEqual(document_copy(rewritten, "about"), ("History", ("First.", "Second.")))
        self.assertEqual(document_copy(rewritten, "home")[0], "Home")
        lone = update_page_copy(
            software_page(title="Lone", body=("x",)),
            title="Named",
            body=("One.", "Two."),
        )
        self.assertEqual(document_copy(lone), ("Named", ("One.", "Two.")))
        with self.assertRaises(InstantiationError):
            update_page_copy(site, key="about", title="  ")

        from meta.instantiation import move_site_page, page_blocks

        structured = update_page_copy(
            site,
            key="home",
            title="Home",
            blocks=(
                {"kind": "paragraph", "text": "Welcome."},
                {"kind": "heading", "text": "Next"},
                {"kind": "link", "text": "About", "to": "about"},
            ),
        )
        self.assertEqual(
            page_blocks(structured, "home"),
            [
                {"kind": "paragraph", "text": "Welcome."},
                {"kind": "heading", "text": "Next"},
                {"kind": "link", "text": "About", "to": "about"},
            ],
        )
        html = render_software_page(instantiate(structured, target=TARGET_WEB_BUILD, slug="plant"))
        self.assertIn("<h2>Next</h2>", html)
        self.assertIn('href="/build/plant/about"', html)
        moved = move_site_page(structured, "home", delta=1)
        self.assertEqual([key for key, _title, _page in site_pages(moved)], ["about", "home"])
        self.assertEqual(move_site_page(moved, "home", delta=1), moved)
        from meta.instantiation import rename_site_page, update_site_title

        renamed = rename_site_page(structured, "about", "history")
        self.assertEqual([key for key, _title, _page in site_pages(renamed)], ["home", "history"])
        self.assertEqual(page_blocks(renamed, "home")[2]["to"], "history")
        named = update_site_title(renamed, "Garden")
        from meta.instantiation import site_title as read_site_title
        self.assertEqual(read_site_title(named), "Garden")
        with self.assertRaises(InstantiationError):
            rename_site_page(named, "home", "history")
        from meta.instantiation import duplicate_site_page

        cloned = duplicate_site_page(structured, "about")
        self.assertEqual(
            [key for key, _title, _page in site_pages(cloned)],
            ["home", "about", "about-2"],
        )
        self.assertEqual(page_blocks(cloned, "about-2"), page_blocks(cloned, "about"))

        pictured = update_page_copy(
            site,
            key="home",
            title="Home",
            blocks=(
                {"kind": "paragraph", "text": "Look."},
                {"kind": "image", "src": "hero.png", "text": "Hero"},
            ),
        )
        self.assertEqual(
            page_blocks(pictured, "home"),
            [
                {"kind": "paragraph", "text": "Look."},
                {"kind": "image", "src": "hero.png", "text": "Hero"},
            ],
        )
        host = render_software_page(instantiate(pictured, target=TARGET_WEB_BUILD, slug="plant"))
        self.assertIn('src="/build/plant/assets/hero.png"', host)
        self.assertIn('alt="Hero"', host)
        files = dict(rendered_site_files(instantiate(pictured, target=TARGET_WEB_BUILD, slug="plant")))
        self.assertIn('src="hero.png"', files["home.html"])
        with self.assertRaises(InstantiationError):
            validate_asset_name("https://evil.example/x.png")
        with self.assertRaises(InstantiationError):
            validate_asset_name("../hero.png")
        with self.assertRaises(InstantiationError):
            validate_asset_name("hero.svg")
        with self.assertRaises(InstantiationError):
            update_page_copy(
                site,
                key="home",
                blocks=({"kind": "image", "src": "https://evil.example/x.png"},),
            )
        listed = update_page_copy(
            site,
            key="home",
            title="Home",
            blocks=(
                {"kind": "paragraph", "text": "Pack."},
                {"kind": "list", "items": ("One", "Two")},
            ),
        )
        self.assertEqual(
            page_blocks(listed, "home"),
            [
                {"kind": "paragraph", "text": "Pack."},
                {"kind": "list", "items": ["One", "Two"]},
            ],
        )
        html = render_software_page(instantiate(listed, target=TARGET_WEB_BUILD, slug="plant"))
        self.assertIn("<ul class=\"mp-list\">", html)
        self.assertIn("<li>One</li>", html)
        self.assertIn("<li>Two</li>", html)
        quoted = update_page_copy(
            site,
            key="home",
            title="Home",
            blocks=(
                {"kind": "heading", "text": "Said"},
                {"kind": "quote", "text": "Keep it local."},
            ),
        )
        self.assertEqual(
            page_blocks(quoted, "home"),
            [
                {"kind": "heading", "text": "Said"},
                {"kind": "quote", "text": "Keep it local."},
            ],
        )
        qhtml = render_software_page(instantiate(quoted, target=TARGET_WEB_BUILD, slug="plant"))
        self.assertIn("<blockquote>Keep it local.</blockquote>", qhtml)
        ranked = update_page_copy(
            site,
            key="home",
            title="Home",
            blocks=(
                {"kind": "heading", "text": "Section", "level": 3},
                {"kind": "code", "text": "<script>x</script>"},
            ),
        )
        self.assertEqual(
            page_blocks(ranked, "home"),
            [
                {"kind": "heading", "text": "Section", "level": 3},
                {"kind": "code", "text": "<script>x</script>"},
            ],
        )
        ranked_html = render_software_page(instantiate(ranked, target=TARGET_WEB_BUILD, slug="plant"))
        self.assertIn("<h3>Section</h3>", ranked_html)
        self.assertIn("<pre class=\"mp-code\"><code>&lt;script&gt;x&lt;/script&gt;</code></pre>", ranked_html)
        self.assertNotIn("<script>x</script>", ranked_html)
        with self.assertRaises(InstantiationError):
            update_page_copy(
                site,
                key="home",
                title="Home",
                blocks=({"kind": "heading", "text": "No", "level": 1},),
            )

    def test_update_page_theme(self):
        from meta.instantiation import theme_copy, update_page_theme

        site = software_site(
            title="Plant",
            pages=(("home", "Home", ("Welcome.",)),),
            theme={"accent": "#06c", "background": "#fff", "color": "#111"},
        )
        painted = update_page_theme(
            site,
            {"accent": "#6ea8fe", "background": "#0b1020", "color": "#e8eef8", "measure": 56, "space": 32},
        )
        self.assertEqual(
            theme_copy(painted),
            {
                "accent": "#6ea8fe",
                "background": "#0b1020",
                "color": "#e8eef8",
                "measure": 56,
                "space": 32,
            },
        )
        html = render_software_page(instantiate(painted, target=TARGET_WEB_BUILD, slug="night-plant"))
        self.assertIn("--mp-bg:#0b1020", html)
        self.assertIn("--mp-measure:56rem", html)
        with self.assertRaises(InstantiationError):
            update_page_theme(site, {"accent": "red"})
        with self.assertRaises(InstantiationError):
            update_page_theme(site, {"measure": 8})
        local = update_page_theme(painted, {"accent": "#c00"}, key="home", scope="page")
        self.assertEqual(theme_copy(local)["accent"], "#6ea8fe")
        self.assertEqual(theme_copy(local, "home", scope="page")["accent"], "#c00")
        local_html = render_software_page(instantiate(local, target=TARGET_WEB_BUILD, slug="tint"))
        self.assertIn("--mp-accent:#c00", local_html)
        self.assertIn("--mp-bg:#0b1020", local_html)

    def test_web_build_rejects_path_separators_in_slug(self):
        node = atom("string", value="x", has_value=True)
        with self.assertRaises(InstantiationError):
            instantiate(node, target=TARGET_WEB_BUILD, slug="../etc")
        with self.assertRaises(InstantiationError):
            instantiate(node, target=TARGET_WEB_BUILD, slug="a/b")
        with self.assertRaises(InstantiationError):
            validate_slug("A_B")

    def test_public_url_helper(self):
        self.assertEqual(public_url_for_slug("abc"), "/build/abc")

    def test_uir_and_visual_targets_preserve_desc(self):
        node = struct(
            a=atom("int", value=1, has_value=True),
            b=atom("int", value=2, has_value=True),
        )
        uir_art = instantiate(node, target=TARGET_UIR)
        vis_art = instantiate(node, target=TARGET_VISUAL)
        self.assertTrue(equivalent(node, from_json(uir_art.payload)))
        self.assertTrue(equivalent(node, visual_to_desc(json.loads(vis_art.payload))))
        self.assertTrue(equivalent(node, description_from_artifact(uir_art)))
        self.assertTrue(equivalent(node, description_from_artifact(vis_art)))

    def test_apply_events_then_instantiate(self):
        advanced = apply_events(self._machine(), ["start", "stop"])
        self.assertEqual(advanced.state, "idle")
        artifact = instantiate(advanced, target=TARGET_DESC)
        self.assertEqual(machine_from_desc(description_from_artifact(artifact)).state, "idle")

    def test_boundary_target_mismatch(self):
        node = atom("string", value="x", has_value=True)
        with self.assertRaises(InstantiationError):
            instantiate(node, target=TARGET_DESC, boundary_id=SOFTWARE_PAGE_ID)

    def test_unknown_target(self):
        with self.assertRaises(InstantiationError):
            instantiate(atom("null", value=None, has_value=True), target="chip-gds")

    def test_bad_events_surface_as_instantiation_error(self):
        with self.assertRaises(InstantiationError):
            instantiate(self._machine(), target=TARGET_DESC, events=("nope",))

    def test_checksum_stable_for_canonical_json(self):
        node = struct(z=atom("int", value=1, has_value=True), a=atom("int", value=2, has_value=True))
        first = instantiate(node, target=TARGET_DESC)
        second = instantiate(node, target=TARGET_DESC)
        self.assertEqual(first.payload, to_json(node))
        self.assertEqual(first.checksum, second.checksum)

    def test_artifact_from_data_rejects_bad_checksum(self):
        from meta.instantiation import Artifact

        node = atom("int", value=1, has_value=True)
        artifact = instantiate(node, target=TARGET_DESC)
        data = artifact.to_data()
        data["checksum"] = "0" * 64
        with self.assertRaises(InstantiationError):
            Artifact.from_data(data)
        again = Artifact.from_data(artifact.to_data())
        self.assertEqual(again.payload, artifact.payload)

    def test_domain_worlds_instantiate_to_playable_web_build(self):
        from meta.instantiation import add_system_part, child_for_part_kind
        from meta.runtime.world import complete_local, world_spec

        scene = struct(
            kind=atom("string", value="scene", has_value=True),
            mesh=atom("string", value="cube", has_value=True),
            title=atom("string", value="Room", has_value=True),
        )
        artifact = instantiate(scene, slug="play-room")
        self.assertEqual(artifact.target, TARGET_WEB_BUILD)
        self.assertEqual(artifact.boundary_id, "scene")
        html_doc = render_software_page(artifact)
        self.assertIn('data-world="scene"', html_doc)
        self.assertIn("zw-spec", html_doc)
        self.assertEqual(world_spec(scene)["family"], "game")
        cad = instantiate(child_for_part_kind("cad", title="Block"), slug="cad-block")
        self.assertEqual(cad.boundary_id, "cad.solid")
        self.assertIn("cad.solid", render_software_page(cad))
        pay = instantiate(child_for_part_kind("checkout"), slug="shop-pay")
        self.assertIn("commerce.checkout", render_software_page(pay))
        chat = instantiate(child_for_part_kind("channel"), slug="chat-room")
        self.assertIn("social.channel", render_software_page(chat))
        brain = instantiate(child_for_part_kind("ai"), slug="ask-local")
        self.assertIn("data-world=\"ai\"", render_software_page(brain))
        self.assertIn("local · Hello", complete_local("Hello", "local"))
        plant = software_system(title="Studio", parts=(("home", "Home", software_page(title="Home", body=("Hi.",))),))
        grown = add_system_part(plant, part_kind="scene", title="Stage")
        sys_art = instantiate(grown, slug="studio-world")
        keys = {item["key"] for item in sys_art.payload_object()["parts"]}
        self.assertIn("home", keys)
        self.assertTrue(any(item["artifact"]["boundary_id"] == "scene" for item in sys_art.payload_object()["parts"]))

    def test_system_desc_compiles_to_desktop_host(self):
        from meta.boundary import META_DESKTOP_ID

        plant = software_system(
            title="Plant",
            parts=(("home", "Home", software_page(title="Home", body=("Hi.",))),),
        )
        web = instantiate(plant, slug="plant-web")
        self.assertEqual(web.target, TARGET_WEB_BUILD)
        host = instantiate(plant, target=TARGET_DESKTOP_HOST, slug="plant-desk")
        self.assertEqual(host.target, TARGET_DESKTOP_HOST)
        self.assertEqual(host.boundary_id, META_DESKTOP_ID)
        self.assertEqual(host.public_url, "/studio")
        body = host.payload_object()
        self.assertEqual(body["host"]["bind"], "127.0.0.1")
        self.assertEqual(body["host"]["stack"], ["electron", "flask"])
        self.assertFalse(body["unity"])
        self.assertFalse(body["wan"])
        self.assertFalse(body["cdn"])
        self.assertEqual(body["loop"], "plugin-project-plugin")
        self.assertFalse(body["self"])
        self.assertTrue(equivalent(plant, description_from_artifact(host)))
        zin = instantiate(zintriq_system_desc(), target=TARGET_DESKTOP_HOST, slug="zintriq")
        data = zin.payload_object()
        self.assertTrue(data["self"])
        self.assertIn("scene", data["host"]["editors"])
        self.assertIn("ai", data["host"]["editors"])
        keys = {item["key"] for item in data["parts"]}
        self.assertIn("workbench", keys)
        self.assertIn("flask", keys)
        self.assertIn("scene", keys)
        self.assertGreaterEqual(len(data["parts"]), 28)
        self.assertFalse(data["binary"])
        self.assertFalse(data["installer"])
        self.assertFalse(data["signed"])
        self.assertEqual(data["pack"]["appId"], "com.zintriq.studio")
        self.assertEqual(data["pack"]["command"], ["npm", "run", "pack"])
        self.assertTrue(data["pack"]["dir"])
        self.assertEqual(data["pack"]["publish"], "never")
        self.assertEqual(data["launch"]["bind"], "127.0.0.1")
        self.assertEqual(data["launch"]["studio"], "/studio")
        self.assertTrue(data["launch"]["loopback_only"])
        self.assertIn("scene", data["launch"]["editors"])
        self.assertEqual(data["launch"]["env"]["ZINTRIQ_DESKTOP"], "1")
        from meta.runtime.desktop_host import editor_plugin_ids

        editor_keys = [item["key"] for item in data["parts"] if item["key"] not in {"workbench", "flask"}]
        self.assertEqual(editor_keys, editor_plugin_ids())
        again = instantiate(zintriq_system_desc(), target=TARGET_DESKTOP_HOST, slug="zintriq")
        self.assertEqual(zin.checksum, again.checksum)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        from meta.runtime.desktop_host import apply_desktop_host

        stored = apply_desktop_host(zintriq_system_desc(), slug="zintriq", data_root=Path(tmp.name), parts=data["parts"])
        root = Path(tmp.name) / "desktop" / "zintriq"
        self.assertTrue((root / "host.json").is_file())
        self.assertTrue((root / "pack.json").is_file())
        self.assertTrue((root / "launch.json").is_file())
        self.assertTrue((root / "checksum.txt").is_file())
        launch = json.loads((root / "launch.json").read_text(encoding="utf-8"))
        self.assertEqual(launch["studio"], "/studio")
        self.assertTrue(launch["loopback_only"])
        self.assertTrue(launch["data_dir"])
        self.assertIn("scene", launch["editors"])
        self.assertIn("ZINTRIQ_DESKTOP=1", (root / "env.desktop").read_text(encoding="utf-8"))
        self.assertFalse(stored["pack"]["installer"])
        stored2 = apply_desktop_host(zintriq_system_desc(), slug="zintriq", data_root=Path(tmp.name), parts=data["parts"])
        self.assertEqual(stored["checksum"], stored2["checksum"])


if __name__ == "__main__":
    unittest.main()
