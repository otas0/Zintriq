"""Physics, B-rep, settlement, federation, and local weight kernels."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from meta.boundary import reset_for_tests
from meta.description import atom, sequence, struct
from meta.instantiation import instantiate, render_software_page
from meta.runtime.kernels import (
    assemble_film,
    bind_pose,
    brep_solid,
    ccd_ik,
    centroid_xy,
    complete_session,
    complete_weights,
    aces_curve,
    apply_cdl,
    copper_balance,
    copper_pour,
    copper_thieve,
    dcode_table,
    dual_quat_blend,
    excellon_text,
    factory_deck,
    false_color,
    federate_messages,
    flood_weights,
    gerber_map,
    highlight_roll,
    keepout_hits,
    rec709_encode,
    rec709_decode,
    skin_cluster,
    stencil_openings,
    stretch_correct,
    vectorscope_polar,
    grade_dag,
    grade_frame,
    grade_graph,
    hammer_weights,
    heat_bind,
    histogram,
    joint_limits,
    kernel_spec,
    lut_1d,
    lut_rgb,
    manhattan_route,
    mix_audio,
    nc_drill,
    padstack,
    paint_weights,
    pick_place,
    process_card,
    prune_influences,
    razor_shot,
    rgb_parade,
    route_drc,
    scene_compile,
    settle_charge,
    tokenize_local,
    skin_deform,
    skin_deform_dq,
    skin_error,
    skin_deform3d,
    skin_mesh,
    skin_mesh3d,
    step_physics,
    step_skeleton,
    tapeout_pack,
    volume_preserve,
    vectorscope,
    waveform,
)


class KernelTests(unittest.TestCase):
    def setUp(self):
        reset_for_tests()

    def tearDown(self):
        reset_for_tests()

    def test_physics_falls(self):
        body = struct(
            gravity=atom("float", value=-9.8, has_value=True),
            kind=atom("string", value="physics.body", has_value=True),
            mass=atom("float", value=1, has_value=True),
            vy=atom("float", value=0, has_value=True),
            y=atom("float", value=10, has_value=True),
        )
        stepped = step_physics(body, dt=0.1)
        self.assertLess(stepped["y"], 10)
        self.assertLess(stepped["vy"], 0)
        html = render_software_page(instantiate(body, slug="fall-body"))
        self.assertIn("physics.body", html)

    def test_skeleton_and_brep_and_film(self):
        rig = struct(
            bones=sequence(
                struct(id=atom("string", value="a", has_value=True), length=atom("float", value=1, has_value=True)),
                struct(id=atom("string", value="b", has_value=True), length=atom("float", value=1, has_value=True)),
            ),
            kind=atom("string", value="skeleton.rig", has_value=True),
            reach=atom("float", value=1, has_value=True),
        )
        self.assertEqual(len(step_skeleton(rig)["bones"]), 2)
        solid = struct(
            depth=atom("float", value=2, has_value=True),
            height=atom("float", value=3, has_value=True),
            kind=atom("string", value="cad.brep", has_value=True),
            width=atom("float", value=4, has_value=True),
        )
        mesh = brep_solid(solid)
        self.assertEqual(len(mesh["vertices"]), 8)
        self.assertEqual(mesh["volume"], 24)
        cut = struct(
            kind=atom("string", value="film.cut", has_value=True),
            shots=sequence(
                struct(clip=atom("string", value="a", has_value=True), duration=atom("float", value=1, has_value=True)),
                struct(clip=atom("string", value="b", has_value=True), duration=atom("float", value=2, has_value=True)),
            ),
        )
        self.assertEqual(assemble_film(cut)["duration"], 3)

    def test_settlement_federation_weights(self):
        charge = struct(
            amount=atom("float", value=12.5, has_value=True),
            currency=atom("string", value="usd", has_value=True),
            kind=atom("string", value="commerce.settle", has_value=True),
        )
        self.assertEqual(settle_charge(charge, op="capture")["op"], "captured")
        self.assertEqual(federate_messages(["a", "b"], ["b", "c"]), ["a", "b", "c"])
        tmp = tempfile.TemporaryDirectory()
        from meta.runtime.local_infer import write_fixture_weights

        write_fixture_weights(Path(tmp.name))
        out = complete_weights("Hello world", data_root=Path(tmp.name))
        self.assertTrue(out)
        self.assertNotIn("weights:", out)
        tmp.cleanup()

    def test_ik_skin_route_nle(self):
        joints = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
        posed = ccd_ik(joints, (1.0, 1.0), iterations=16)
        self.assertEqual(len(posed), 3)
        self.assertLess(abs(posed[-1][0] - 1.0) + abs(posed[-1][1] - 1.0), 0.35)
        skinned = skin_deform(
            [(0.0, 0.0), (0.0, 1.0)],
            [(0.0, 0.0), (0.0, 1.0)],
            [(1.0, 0.0), (1.0, 1.0)],
            [[(0, 1.0)], [(0, 1.0)]],
        )
        self.assertAlmostEqual(skinned[0][0], 1.0)
        path = manhattan_route(0, 0, 10, 10)
        self.assertEqual(path["path"][0], (0, 0))
        self.assertEqual(path["path"][-1], (10, 10))
        hits = route_drc([path, manhattan_route(0, 1, 10, 1, layer=0)], min_gap=4)
        self.assertTrue(hits)
        cut = assemble_film(
            struct(
                kind=atom("string", value="film.cut", has_value=True),
                playhead=atom("float", value=1.5, has_value=True),
                shots=sequence(
                    struct(
                        clip=atom("string", value="a", has_value=True),
                        duration=atom("float", value=1, has_value=True),
                        **{"in": atom("float", value=0, has_value=True)},
                        track=atom("int", value=1, has_value=True),
                    ),
                    struct(
                        clip=atom("string", value="b", has_value=True),
                        duration=atom("float", value=2, has_value=True),
                        **{"in": atom("float", value=1, has_value=True)},
                        track=atom("int", value=1, has_value=True),
                    ),
                ),
            )
        )
        self.assertEqual(cut["active"], "b")
        split = razor_shot(cut["shots"], 2.0)
        self.assertGreater(len(split), len(cut["shots"]))
        shader = kernel_spec(struct(kind=atom("string", value="shader", has_value=True)))
        self.assertEqual(shader["blend"], "opaque")
        audio = kernel_spec(
            struct(
                duration=atom("float", value=2.5, has_value=True),
                kind=atom("string", value="audio", has_value=True),
            )
        )
        self.assertEqual(audio["duration"], 2.5)
        painted = paint_weights([[(0, 1.0)], [(0, 1.0)]], [(0.0, 0.0), (0.2, 0.0)], (0.0, 0.0), bone=1, radius=1.0, strength=1.0)
        self.assertEqual(len(painted[0]), 2)
        mix = mix_audio([{"clip": "vo", "in": 0, "duration": 2, "gain": 0.5, "pan": -0.2}], 0.5)
        self.assertAlmostEqual(mix["level"], 0.5)
        rgb = grade_frame((0.5, 0.4, 0.3), lift=0.0, gamma=1.0, gain=1.2, sat=1.0)
        self.assertGreater(rgb[0], 0.4)
        vias = [{"x": 0, "y": 0, "net": "a", "from": 0, "to": 1}, {"x": 0.1, "y": 0.1, "net": "b", "from": 0, "to": 1}]
        self.assertTrue(route_drc([], min_gap=4, vias=vias))
        card_hits = route_drc(
            [],
            vias=[{"net": "v", "drill": 0.1, "size": 0.2, "x": 0, "y": 0, "from": 0, "to": 1}],
            card=process_card(),
        )
        self.assertTrue(card_hits)
        mesh = skin_mesh([(0.0, 0.0), (10.0, 0.0), (20.0, 4.0)])
        self.assertTrue(mesh["faces"])
        limited = mix_audio([{"clip": "vo", "in": 0, "duration": 2, "gain": 4.0}], 0.5, limiter=1.0)
        self.assertTrue(limited["limited"])
        shifted = grade_frame((0.5, 0.4, 0.3), hue=30, contrast=1.1, temp=2)
        self.assertEqual(len(shifted), 3)
        tube = skin_mesh3d([(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (20.0, 4.0, 2.0)])
        self.assertTrue(tube["faces"])
        self.assertEqual(len(tube["vertices"][0]), 3)
        posed3 = skin_deform3d(tube["vertices"], [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)], [(0.0, 0.0, 0.0), (10.0, 2.0, 0.0)], tube["weights"])
        self.assertEqual(len(posed3[0]), 3)
        far = paint_weights([[(0, 1.0)], [(0, 1.0)]], [(0.0, 0.0, 8.0), (0.2, 0.0, 0.0)], (0.0, 0.0, 0.0), bone=1, radius=1.0, strength=1.0)
        self.assertEqual(len(far[0]), 1)
        deck = factory_deck("4L-FR4")
        self.assertEqual(len(deck["layers"]), 4)
        holes = route_drc(
            [],
            vias=[{"net": "a", "drill": 0.3, "x": 0, "y": 0}, {"net": "a", "drill": 0.3, "x": 0.2, "y": 0}],
            card=deck,
        )
        self.assertTrue(any("hole-to-hole" in item for item in holes))
        edge_hits = route_drc(
            [{"net": "n", "layer": 0, "path": [(0.0, 0.0), (1.0, 0.0)], "width": 0.2}],
            card=deck,
        )
        self.assertTrue(any("copper-to-edge" in item for item in edge_hits))
        graph = grade_graph((0.4, 0.4, 0.4), [{"op": "gain", "value": 1.2}])
        self.assertGreater(graph[0], 0.4)
        self.assertTrue(waveform([(0.2, 0.3, 0.4)]))
        self.assertIn("u", vectorscope((0.8, 0.2, 0.1)))
        flooded = flood_weights([[(0, 1.0), (1, 1.0)]], bone=1)
        self.assertEqual(flooded[0][0][0], 1)
        heated = heat_bind([(0.0, 0.0, 0.0), (5.0, 0.0, 0.0)], [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)])
        self.assertTrue(heated[0])
        pruned = prune_influences([[(0, 0.1), (1, 0.8), (2, 0.7), (3, 0.2), (4, 0.9)]], max_influences=2)
        self.assertEqual(len(pruned[0]), 2)
        cdl = apply_cdl((0.4, 0.4, 0.4), slope=1.2, offset=0.0, power=1.0)
        self.assertGreater(cdl[0], 0.4)
        mixed = grade_graph((0.5, 0.5, 0.5), [{"op": "cdl", "slope": 1.1}, {"op": "mix", "value": 0.25}])
        self.assertEqual(len(mixed), 3)
        self.assertTrue(gerber_map(deck))
        job = tapeout_pack([{"net": "n", "layer": 0, "path": [(10.0, 10.0), (20.0, 10.0)], "width": 0.2}], card=deck)
        self.assertIn("gerber", job)
        self.assertTrue(histogram([(0.1, 0.2, 0.3)]))
        self.assertTrue(rgb_parade([(0.1, 0.2, 0.3)])["r"])
        film = assemble_film(
            struct(
                kind=atom("string", value="film.cut", has_value=True),
                shots=sequence(struct(clip=atom("string", value="a", has_value=True), duration=atom("float", value=1, has_value=True))),
            )
        )
        self.assertIn("histogram", film)
        self.assertIn("parade", film)
        self.assertIn("dag", film)
        self.assertTrue(job.get("bom"))
        self.assertTrue(job.get("pour"))
        self.assertTrue(padstack({"drill": 0.3, "size": 0.6})["annular"] > 0)
        self.assertGreater(copper_pour([(0, 0), (10, 0), (10, 8), (0, 8)], [])["area"], 0)
        dag = grade_dag((0.4, 0.4, 0.4), [{"id": "a", "op": "gain", "value": 1.1}, {"id": "b", "op": "sat", "input": "a", "value": 1.0}])
        self.assertEqual(len(dag), 3)
        dq = skin_deform_dq([(0.0, 0.0, 0.0)], [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [(0.0, 0.0, 0.0), (1.0, 1.0, 0.0)], [[(0, 1.0)]], dual=0.4)
        self.assertEqual(len(dq[0]), 3)
        self.assertTrue(job.get("drill"))
        self.assertTrue(job.get("netlist"))
        self.assertTrue(nc_drill([{"x": 1, "y": 2, "drill": 0.3}])["hits"])
        self.assertTrue(bind_pose([(0, 0, 0), (1, 0, 0)]))
        muted = grade_graph((0.4, 0.4, 0.4), [{"op": "gain", "value": 2.0, "mute": True}])
        self.assertAlmostEqual(muted[0], 0.4, places=3)
        self.assertGreater(lut_1d((0.5, 0.5, 0.5), [(0, 0), (1, 1)])[0], 0.4)
        vol = volume_preserve([(2.0, 0.0, 0.0)], [(1.0, 0.0, 0.0)], amount=0.5)
        self.assertEqual(len(vol[0]), 3)
        self.assertIn("lut", film)
        self.assertIn("wipe", film)
        self.assertIn("M30", excellon_text([{"x": 1, "y": 2}]))
        self.assertTrue(job.get("odb"))
        self.assertEqual(hammer_weights([[(0, 0.2), (1, 0.8)]], bone=1)[0][0][0], 1)
        self.assertEqual(len(lut_rgb((0.4, 0.5, 0.6))), 3)
        self.assertTrue(job.get("panel"))
        self.assertTrue(job.get("ipc2581"))
        self.assertGreater(aces_curve((0.5, 0.5, 0.5))[0], 0.0)
        self.assertTrue(joint_limits([{"angle": 200}])[0]["clamped"])
        self.assertIn("aces", film)
        self.assertTrue(copper_balance([{"path": [(0, 0), (10, 0)], "width": 1.0}]))
        self.assertTrue(job.get("pick"))
        self.assertIn("x", centroid_xy([{"path": [(0, 0), (2, 2)]}]))
        self.assertEqual(len(false_color((0.2, 0.4, 0.8))), 3)
        self.assertGreaterEqual(skin_error([(0, 0, 0)], [(0, 0, 0)]), 0.0)
        self.assertIn("false", film)
        self.assertTrue(pick_place([{"net": "n", "path": [(1, 1)]}]))
        self.assertEqual(skin_cluster([[(0, 0.2), (1, 0.9)]])[0], 1)
        blended = dual_quat_blend([(0.0, 0.0, 0.0)], [(2.0, 0.0, 0.0)], dual=0.5)
        self.assertAlmostEqual(blended[0][0], 1.0)
        stretched = stretch_correct([(2.0, 0.0, 0.0)], [(0.0, 0.0, 0.0)], amount=0.5)
        self.assertAlmostEqual(stretched[0][0], 1.0)
        self.assertTrue(dcode_table([{"width": 0.2}, {"width": 0.4}]))
        self.assertTrue(stencil_openings([{"x": 1, "y": 1, "size": 0.6}]))
        self.assertTrue((job.get("plated") or {}).get("plated") is not None)
        self.assertGreater(copper_thieve(deck)["fill"], 0)
        self.assertTrue(keepout_hits([{"path": [(0.0, 0.0)]}], {"x": 0, "y": 0, "w": 1, "h": 1}))
        encoded = rec709_encode((0.5, 0.5, 0.5))
        self.assertEqual(len(encoded), 3)
        self.assertGreater(rec709_decode(encoded)[0], 0.3)
        self.assertLess(highlight_roll((0.95, 0.95, 0.95), knee=0.8, amount=0.5)[0], 0.95)
        self.assertIn("theta", vectorscope_polar((0.8, 0.2, 0.1)))
        self.assertIn("rec709", film)
        self.assertIn("polar", film)
        rolled = grade_graph((0.9, 0.9, 0.9), [{"op": "roll", "value": 0.5, "knee": 0.7}])
        self.assertEqual(len(rolled), 3)
        graph = scene_compile(
            struct(
                kind=atom("string", value="scene", has_value=True),
                mesh=atom("string", value="cube", has_value=True),
                objects=sequence(
                    struct(
                        name=atom("string", value="Cube", has_value=True),
                        x=atom("float", value=1, has_value=True),
                    )
                ),
            )
        )
        self.assertTrue(graph["hierarchy"])
        self.assertTrue(graph["frustum"]["matrix"])
        self.assertFalse(graph["unity"])
        self.assertIn("world_matrix", graph["hierarchy"][0])
        played = scene_compile(
            struct(
                kind=atom("string", value="scene", has_value=True),
                time=atom("float", value=0.5, has_value=True),
                instances=sequence(
                    struct(
                        name=atom("string", value="Dup", has_value=True),
                        mesh=atom("string", value="cube", has_value=True),
                        x=atom("float", value=2, has_value=True),
                    )
                ),
                keys=sequence(
                    struct(t=atom("float", value=0, has_value=True), px=atom("float", value=0, has_value=True)),
                    struct(t=atom("float", value=1, has_value=True), px=atom("float", value=10, has_value=True)),
                ),
            )
        )
        self.assertEqual(len(played["instances"]), 1)
        self.assertAlmostEqual(played["play"]["px"], 5.0)
        self.assertTrue(played["playing"])
        cam_job = kernel_spec(
            struct(
                kind=atom("string", value="circuit", has_value=True),
                nets=sequence(struct(name=atom("string", value="n1", has_value=True))),
                vias=sequence(
                    struct(
                        x=atom("float", value=1, has_value=True),
                        y=atom("float", value=1, has_value=True),
                        plated=atom("bool", value=True, has_value=True),
                    )
                ),
            )
        )
        self.assertIn("netlist", cam_job)
        self.assertIn("apertures", cam_job)
        self.assertIn("stencil", cam_job)
        self.assertIn("plated", cam_job)
        self.assertIn("keepout", cam_job)
        film_cut = assemble_film(
            struct(
                kind=atom("string", value="film.cut", has_value=True),
                playhead=atom("float", value=0.5, has_value=True),
                razor_at=atom("float", value=0.5, has_value=True),
                shots=sequence(
                    struct(
                        clip=atom("string", value="a", has_value=True),
                        duration=atom("float", value=1, has_value=True),
                        **{"in": atom("float", value=0, has_value=True)},
                    )
                ),
            )
        )
        self.assertGreaterEqual(len(film_cut["razored"]), 2)
        self.assertTrue(film_cut["cache_hit"])
        self.assertTrue(film_cut["playhead_cache"]["hash"])
        self.assertTrue(tokenize_local("Hello 世界"))
        tmp_ai = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_ai.cleanup)
        from meta.runtime.kernels import WeightsError
        from meta.runtime.local_infer import write_fixture_weights

        with self.assertRaises(WeightsError):
            complete_session(prompt="Hello", data_root=Path(tmp_ai.name), temperature=0.2, max_tokens=8)
        write_fixture_weights(Path(tmp_ai.name), "local.json")
        session = complete_session(prompt="Hello", data_root=Path(tmp_ai.name), temperature=0.2, max_tokens=8)
        self.assertTrue(session["local"])
        self.assertFalse(session["hosted"])
        self.assertTrue(session["output"])

    def test_all_kernel_kinds_emit(self):
        from meta.runtime.kernels import KERNEL_KINDS

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for kind in sorted(KERNEL_KINDS):
            desc = struct(kind=atom("string", value=kind, has_value=True))
            out = kernel_spec(desc, data_root=root)
            self.assertEqual(out.get("kind"), kind, msg=kind)


if __name__ == "__main__":
    unittest.main()
