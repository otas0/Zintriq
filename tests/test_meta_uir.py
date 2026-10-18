"""UIR dual-expression bridge over meta descriptions."""

from __future__ import annotations

import unittest

from meta.description import atom, equivalent, from_json, mapping, sequence, struct, to_json
from meta.simulation import StateMachine, Transition, machine_from_desc, machine_to_desc, step
from meta.uir import (
    UIRError,
    code_to_desc,
    desc_to_visual,
    from_code,
    from_desc,
    to_code,
    to_desc,
    visual_to_desc,
)


class MetaUIRTests(unittest.TestCase):
    def test_atom_and_composite_round_trip(self):
        node = struct(
            name=atom("string", value="pump", has_value=True),
            tags=sequence(
                atom("string", value="iot", has_value=True),
                atom("string", ref="$.tag"),
            ),
            props=mapping(voltage=atom("float", value=3.3, has_value=True, unit="V")),
        )
        uir = from_desc(node)
        restored = to_desc(uir)
        self.assertTrue(equivalent(node, restored))
        self.assertEqual(to_json(node), to_json(restored))

    def test_visual_round_trip(self):
        node = struct(
            a=atom("int", value=1, has_value=True),
            b=atom("int", value=2, has_value=True),
        )
        visual = desc_to_visual(node)
        self.assertEqual(visual["form"], "visual")
        self.assertTrue(isinstance(visual["nodes"], list))
        restored = visual_to_desc(visual)
        self.assertTrue(equivalent(node, restored))

    def test_code_json_round_trip(self):
        node = atom("string", value="hello", has_value=True, unit="text")
        uir = from_desc(node, source="code")
        code = to_code(uir, language="json")
        self.assertEqual(code, to_json(node))
        restored = code_to_desc(code, language="json")
        self.assertTrue(equivalent(node, restored))
        again = to_desc(from_code(code))
        self.assertTrue(equivalent(node, again))

    def test_visual_code_equivalence(self):
        node = struct(
            left=atom("bool", value=True, has_value=True),
            right=atom("null", value=None, has_value=True),
        )
        via_visual = visual_to_desc(desc_to_visual(node))
        via_code = code_to_desc(to_code(from_desc(node)))
        self.assertTrue(equivalent(via_visual, via_code))
        self.assertTrue(equivalent(node, via_visual))

    def test_code_yaml_round_trip(self):
        node = atom("string", value="hello", has_value=True, unit="text")
        code = to_code(from_desc(node), language="yaml")
        restored = code_to_desc(code, language="yaml")
        self.assertTrue(equivalent(node, restored))

    def test_unsupported_code_language(self):
        with self.assertRaises(UIRError):
            to_code(from_desc(atom("int", value=1, has_value=True)), language="python")

    def test_unsupported_uir_kind(self):
        from meta.uir.graph import uir_from_data

        with self.assertRaises(UIRError):
            uir_from_data(
                {
                    "root": "n1",
                    "nodes": {"n1": {"id": "n1", "kind": "qubit", "properties": {}}},
                    "edges": {},
                }
            )

    def test_state_machine_survives_uir(self):
        machine = StateMachine(
            state="idle",
            transitions=(
                Transition("idle", "start", "running"),
                Transition("running", "stop", "idle"),
            ),
        )
        desc = machine_to_desc(machine)
        restored_desc = to_desc(from_desc(from_json(to_json(desc))))
        # Also through visual + code
        restored_desc = visual_to_desc(desc_to_visual(desc))
        restored_desc = code_to_desc(to_code(from_desc(restored_desc)))
        restored = machine_from_desc(restored_desc)
        advanced = step(restored, "start")
        self.assertEqual(advanced.state, "running")


if __name__ == "__main__":
    unittest.main()
