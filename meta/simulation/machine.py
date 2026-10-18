"""One-step discrete state-machine simulation over meta descriptions."""

from __future__ import annotations

from dataclasses import dataclass

from meta.description.composite import StructDesc, sequence, struct
from meta.description.types import AtomDesc, Desc, atom
from meta.simulation.errors import SimulationError

MACHINE_KIND = "state_machine"


@dataclass(frozen=True)
class Transition:
    source: str
    event: str
    target: str


@dataclass(frozen=True)
class StateMachine:
    state: str
    transitions: tuple[Transition, ...] = ()


def step(machine: StateMachine, event: str) -> StateMachine:
    """Advance exactly one transition for ``event``, or raise."""
    event_key = str(event or "").strip()
    if not event_key:
        raise SimulationError("event required")
    if not machine.state:
        raise SimulationError("machine has no current state")
    for transition in machine.transitions:
        if transition.source == machine.state and transition.event == event_key:
            return StateMachine(state=transition.target, transitions=machine.transitions)
    raise SimulationError(
        f"no transition for state={machine.state!r} event={event_key!r}"
    )


def events_from_state(machine: StateMachine) -> tuple[str, ...]:
    """Events that have a transition from the current state, in definition order."""
    seen: list[str] = []
    for item in machine.transitions:
        if item.source == machine.state and item.event not in seen:
            seen.append(item.event)
    return tuple(seen)


def machine_to_desc(machine: StateMachine) -> StructDesc:
    transitions = sequence(
        *(
            struct(
                source=atom("string", value=item.source, has_value=True),
                event=atom("string", value=item.event, has_value=True),
                target=atom("string", value=item.target, has_value=True),
            )
            for item in machine.transitions
        )
    )
    return struct(
        kind=atom("string", value=MACHINE_KIND, has_value=True),
        state=atom("string", value=machine.state, has_value=True),
        transitions=transitions,
    )


def machine_from_desc(node: Desc) -> StateMachine:
    if not isinstance(node, StructDesc):
        raise SimulationError("state machine must be a struct description")
    fields = {name: child for name, child in node.fields}
    kind = fields.get("kind")
    if not isinstance(kind, AtomDesc) or not kind.has_value or kind.value != MACHINE_KIND:
        raise SimulationError("struct kind must be state_machine")
    state_node = fields.get("state")
    if not isinstance(state_node, AtomDesc) or not state_node.has_value:
        raise SimulationError("state machine requires string state value")
    if state_node.type_name != "string" or not isinstance(state_node.value, str) or not state_node.value:
        raise SimulationError("invalid state value")
    transitions_node = fields.get("transitions")
    transitions: list[Transition] = []
    if transitions_node is not None:
        from meta.description.composite import SequenceDesc

        if not isinstance(transitions_node, SequenceDesc):
            raise SimulationError("transitions must be a sequence")
        for item in transitions_node.items:
            transitions.append(_transition_from_desc(item))
    return StateMachine(state=state_node.value, transitions=tuple(transitions))


def _transition_from_desc(node: Desc) -> Transition:
    if not isinstance(node, StructDesc):
        raise SimulationError("transition must be a struct")
    fields = {name: child for name, child in node.fields}
    return Transition(
        source=_string_field(fields, "source"),
        event=_string_field(fields, "event"),
        target=_string_field(fields, "target"),
    )


def _string_field(fields: dict, name: str) -> str:
    node = fields.get(name)
    if not isinstance(node, AtomDesc) or not node.has_value:
        raise SimulationError(f"transition.{name} required")
    if node.type_name != "string" or not isinstance(node.value, str) or not node.value.strip():
        raise SimulationError(f"transition.{name} must be a non-empty string")
    return node.value.strip()
