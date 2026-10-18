"""Meta-description core: construct, serialize, equivalence, constraints."""

from __future__ import annotations

import unittest

from meta.description import (
    DescriptionError,
    depends_on,
    equivalent,
    from_json,
    to_json,
)
from meta.description.composite import mapping, sequence, struct
from meta.description.types import Constraint, atom


class MetaDescriptionTests(unittest.TestCase):
    def test_atom_round_trip(self):
        node = atom("string", value="hello", has_value=True, unit="text")
        restored = from_json(to_json(node))
        self.assertTrue(equivalent(node, restored))
        self.assertEqual(restored.value, "hello")
        self.assertEqual(restored.unit, "text")

    def test_struct_sequence_mapping_round_trip(self):
        node = struct(
            name=atom("string", value="pump", has_value=True),
            tags=sequence(
                atom("string", value="iot", has_value=True),
                atom("string", value="sensor", has_value=True),
            ),
            props=mapping(
                voltage=atom("float", value=3.3, has_value=True, unit="V"),
            ),
        )
        restored = from_json(to_json(node))
        self.assertTrue(equivalent(node, restored))
        self.assertEqual(to_json(node), to_json(restored))

    def test_ref_dependency_collection(self):
        node = struct(
            left=atom("int", ref="$.input.count"),
            right=atom("int", ref="system.limit"),
        )
        self.assertEqual(depends_on(node), frozenset({"$.input.count", "system.limit"}))

    def test_equivalence_detects_difference(self):
        a = atom("int", value=1, has_value=True)
        b = atom("int", value=2, has_value=True)
        self.assertTrue(equivalent(a, a))
        self.assertFalse(equivalent(a, b))

    def test_rejects_value_and_ref(self):
        with self.assertRaises(DescriptionError):
            atom("int", value=1, has_value=True, ref="$.x")

    def test_rejects_bad_constraint(self):
        with self.assertRaises(DescriptionError):
            atom(
                "bool",
                value=True,
                has_value=True,
                constraints=(Constraint("min", 0),),
            )

    def test_pattern_constraint_round_trip(self):
        node = atom(
            "string",
            value="abc",
            has_value=True,
            constraints=(Constraint("pattern", r"^[a-z]+$"),),
        )
        restored = from_json(to_json(node))
        self.assertTrue(equivalent(node, restored))

    def test_invalid_json_form(self):
        with self.assertRaises(DescriptionError):
            from_json('{"form":"nope"}')


if __name__ == "__main__":
    unittest.main()
