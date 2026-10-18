"""Meta-simulation: one-step state machine over descriptions."""

from __future__ import annotations

import unittest

from meta.description import equivalent, from_json, to_json
from meta.simulation import (
    SimulationError,
    StateMachine,
    Transition,
    events_from_state,
    machine_from_desc,
    machine_to_desc,
    step,
)


class MetaSimulationTests(unittest.TestCase):
    def _machine(self) -> StateMachine:
        return StateMachine(
            state="idle",
            transitions=(
                Transition("idle", "start", "running"),
                Transition("running", "stop", "idle"),
            ),
        )

    def test_step_advances_once(self):
        machine = self._machine()
        next_machine = step(machine, "start")
        self.assertEqual(next_machine.state, "running")
        self.assertEqual(next_machine.transitions, machine.transitions)

    def test_step_round_trip_through_description(self):
        machine = self._machine()
        desc = machine_to_desc(machine)
        restored = machine_from_desc(from_json(to_json(desc)))
        advanced = step(restored, "start")
        again = machine_from_desc(machine_to_desc(advanced))
        self.assertEqual(again.state, "running")
        self.assertTrue(equivalent(machine_to_desc(advanced), machine_to_desc(again)))

    def test_unknown_event_fails(self):
        with self.assertRaises(SimulationError):
            step(self._machine(), "nope")

    def test_rejects_non_machine_desc(self):
        from meta.description import atom, struct

        with self.assertRaises(SimulationError):
            machine_from_desc(struct(kind=atom("string", value="other", has_value=True)))

    def test_events_from_current_state(self):
        machine = self._machine()
        self.assertEqual(events_from_state(machine), ("start",))
        self.assertEqual(events_from_state(step(machine, "start")), ("stop",))


if __name__ == "__main__":
    unittest.main()
