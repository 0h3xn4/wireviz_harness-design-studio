# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-DRC-09. The rule `wire-direction` (design of 4.2.0, section 6; `core/drc/electrical.py`). The rule is
registered since pull request 4 of the design; these tests call the check and the notes directly.

Out to out, in to in, a fan-out through a splice (no finding), two outputs through a splice, a loose
end (not judged), a pair of a connection (left to `link-direction`), `Pin.direction` over the type, a
one-directional type (silent), the note `wire-direction-unknown`; and, with Hypothesis, on a harness
made from a connection with random pin directions, the findings of `wire-direction` once the
connection is removed are the `link_direction_conflict` findings of the connection."""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from harness_design_studio.core import templates
from harness_design_studio.core.commands import apply_ops
from harness_design_studio.core.drc import electrical
from harness_design_studio.core.drc.rules import RULES
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.links import (
    _conflict,
    _direction,
    check_links,
    direction_conflict,
    pin_direction,
    plan_add_link,
    plan_create_harness,
)
from harness_design_studio.core.manual_harness import plan_cable_from_port
from harness_design_studio.core.model import Project
from tests.electrical_support import bare, hand_made, set_pin, set_signals, spliced, titles
from tests.helpers import pinout_project


def hits(p: Project) -> list[str]:
    return titles(electrical._wire_direction(p))


def note(p: Project) -> str | None:
    return next(
        (h.title for h in electrical.unchecked(p) if h.object_id == "wire-direction-unknown"), None
    )


def test_the_rule_is_registered_and_has_the_texts_of_the_design() -> None:
    assert len(RULES) == 43 and "wire-direction" in {r.id for r in RULES}
    r = next(r for r in electrical.ELECTRICAL_RULES if r.id == "wire-direction")
    assert (r.severity, r.topic, r.can_waive, r.can_deviate, r.sources) == ("error", "Directions of drawn wires", False, False, ())  # fmt: skip
    assert r.why == "Two outputs on one wire drive against each other, and two inputs have nothing to drive them."  # fmt: skip
    assert r.how == "Move the wire to a pin that fits, or correct the direction of the pin (Devices tab)."  # fmt: skip


def test_the_public_names_of_the_review_are_the_old_functions() -> None:
    assert pin_direction is _direction and direction_conflict is _conflict


def test_out_to_out_and_in_to_in() -> None:
    p, hid = hand_made(["TX+", "RX+", "TX-"], ["TX+", "RX+", "RX-"], [("1", "1"), ("2", "2"), ("3", "3")])  # fmt: skip
    found = list(electrical._wire_direction(p))
    assert [h.title for h in found] == [
        f"Wire {hid}-001 in {hid} joins pin 1 of OBC-J03 (TX+, an output) and pin 1 of RW1-J02 (TX+, an output): two outputs drive against each other",
        f"Wire {hid}-002 in {hid} joins pin 2 of OBC-J03 (RX+, an input) and pin 2 of RW1-J02 (RX+, an input): nothing drives the wire",
    ]  # fmt: skip
    assert [(h.object_id, h.key) for h in found] == [(f"{hid}-001", f"{hid}.{hid}-001"), (f"{hid}-002", f"{hid}.{hid}-002")]  # fmt: skip
    assert note(p) is None


def test_the_direction_of_the_pin_wins_over_the_type() -> None:
    p, hid = hand_made(["TX+"], ["TX+"], [("1", "1")])
    set_pin(p, "RW1-J02", "1", direction="in")  # a vendor that names the pin from its own side
    assert hits(p) == []
    set_pin(p, "OBC-J03", "1", direction="in")
    assert hits(p) == [f"Wire {hid}-001 in {hid} joins pin 1 of OBC-J03 (TX+, an input) and pin 1 of RW1-J02 (TX+, an input): nothing drives the wire"]  # fmt: skip
    set_pin(p, "OBC-J03", "1", direction="bidir")
    assert hits(p) == []


def test_a_one_directional_type_and_a_signal_no_type_has_are_not_judged() -> None:
    # SIG+ of analog lists out at both ends: not judged, and counted for the note
    p, hid = hand_made(["SIG+", "1PPS+", None], ["SIG+", "1PPS+", None], [("1", "1"), ("2", "2"), ("3", "3")])  # fmt: skip
    assert hits(p) == []
    assert note(p) == f"Directions were not checked for 3 net(s) of wires drawn by hand (first: wire {hid}-001): a pin at an end has no direction"  # fmt: skip
    for pin in ("1", "2", "3"):
        set_pin(p, "OBC-J03", pin, direction="out")
        set_pin(p, "RW1-J02", pin, direction="in")
    assert hits(p) == [] and note(p) is None


def test_a_fan_out_through_a_splice_and_two_outputs_through_a_splice() -> None:
    p, hid = spliced(None, None, None)
    for cid, d in (("PCDU-J02", "out"), ("OBC-J02", "in"), ("OBC-J03", "in")):
        set_pin(p, cid, "1", direction=d)
    assert hits(p) == []
    set_pin(p, "OBC-J03", "1", direction="out")
    assert hits(p) == [
        f"The wires {hid}-001, {hid}-002 and {hid}-003 in {hid} (through splice {hid}-X1) join 2 outputs: pin 1 of PCDU-J02 (TX+) and pin 1 of OBC-J03 (TX+)"
    ]  # fmt: skip
    for cid in ("PCDU-J02", "OBC-J02", "OBC-J03"):
        set_pin(p, cid, "1", direction="in")
    assert hits(p) == [
        f"The wires {hid}-001, {hid}-002 and {hid}-003 in {hid} (through splice {hid}-X1) join 3 inputs and no output: pin 1 of PCDU-J02 (TX+), pin 1 of OBC-J02 (TX+) and pin 1 of OBC-J03 (TX+)"
    ]  # fmt: skip


def test_a_net_with_a_loose_end_is_not_judged() -> None:
    p = bare()
    set_signals(p, "OBC-J03", ["TX+", "RX+"])
    apply_ops(p, plan_cable_from_port(p, "OBC-J03", name="Loose").ops)
    assert hits(p) == [] and note(p) is None


def test_a_pair_of_a_connection_is_left_to_the_review_of_the_connection() -> None:
    p = pinout_project()
    p.harnesses.clear()
    ops, lid = plan_add_link(p, "OBC-J01", "RW1-J02", [("1", "1"), ("3", "3")])
    apply_ops(p, ops)
    ops, hid = plan_create_harness(p, lid)
    apply_ops(p, ops)
    assert {f.code for f in check_links(p)} >= {"link_direction_conflict"}
    assert hits(p) == [] and note(p) is None
    p.links.clear()  # without the connection the drawn wires are judged
    assert len(hits(p)) == 2


def test_a_generated_harness_is_left_to_direction_conflict(tmp_path: Path) -> None:
    p = templates.create_project(tmp_path / "f", "first-steps")
    generate_project(p)
    for c in p.connectors.values():
        for pin in c.pins:
            if pin.signal:
                set_pin(p, c.id, pin.id, direction="out")
    assert hits(p) == [] and note(p) is None


def test_no_example_has_a_drawn_net(tmp_path: Path) -> None:
    for name in ("first-steps", "flatsat"):
        p = templates.create_project(tmp_path / name, name)
        if not p.harnesses:
            generate_project(p)
        assert hits(p) == [] and list(electrical.unchecked(p)) == []


def test_the_drawn_harnesses_of_loose_ends_and_of_splices(tmp_path: Path) -> None:
    from harness_design_studio.core.io.loader import load_project
    from tests.loose_support import build_loose
    from tests.splice_support import branch_leg_project

    p = load_project(build_loose(tmp_path / "loose")).project
    assert hits(p) == []
    assert note(p) == "Directions were not checked for 2 net(s) of wires drawn by hand (first: wire W010-001): a pin at an end has no direction"  # fmt: skip
    p = branch_leg_project()
    assert hits(p) == []
    assert note(p) == "Directions were not checked for 1 net(s) of wires drawn by hand (first: wire W003-004): a pin at an end has no direction"  # fmt: skip


# ---- the second statement: the review of the connection -----------------------------------------

DIRECTIONS = ("", "in", "out", "bidir")


@settings(max_examples=120, deadline=None)
@given(
    st.lists(st.sampled_from(DIRECTIONS), min_size=8, max_size=8),
    st.permutations(["1", "2", "3", "4"]),
)
def test_the_findings_are_those_of_the_review_of_the_connection(dirs, order) -> None:  # type: ignore[no-untyped-def]
    p = pinout_project()
    p.harnesses.clear()
    for k, pin in enumerate(("1", "2", "3", "4")):
        set_pin(p, "OBC-J01", pin, direction=dirs[k])
        set_pin(p, "RW1-J02", pin, direction=dirs[k + 4])
    pairs = list(zip(("1", "2", "3", "4"), order, strict=True))
    ops, lid = plan_add_link(p, "OBC-J01", "RW1-J02", pairs)
    apply_ops(p, ops)
    ops, hid = plan_create_harness(p, lid)
    apply_ops(p, ops)
    review = {
        f.pin.split(".")[1] for f in check_links(p) if f.code == "link_direction_conflict" and f.pin
    }
    assert hits(p) == []  # every net is a pair of the connection
    p.links.clear()
    wires = {w.id: w for w in p.harnesses[hid].wires}
    found = {wires[h.object_id].from_pin for h in electrical._wire_direction(p)}
    assert found == review
