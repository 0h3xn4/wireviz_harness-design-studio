# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Which connector is end A of a shield group (design of 4.1.0, section 3.5; pull request 1).

`core/shield_ends.py` names the rule the drawings have used since the shields were drawn: end A is
the `from` connector of the group's reference wire, the wire with the lowest ID in the whole
harness; end B its `to` connector; any other connector has no end (a group across a branch, which
the warning `shield_across_branch` names). The drawing takes its reference wire from here and
keeps its bytes (the drawings are in `tools.output_hashes`, checked by `tests/test_output_hashes.py`)."""

import pytest

from harness_design_studio.core.model import Connector, Harness, Pin, Project, ShieldGroup, Wire
from harness_design_studio.core.outputs import drawing
from harness_design_studio.core.shield_ends import end_at, reference_wire
from tests.plan_support import GOLDEN_PROJECTS, golden_project


def wire(n: int, a: str, b: str, pin: str = "1") -> Wire:
    return Wire(id=f"W001-{n:03d}", from_connector=a, from_pin=pin, to_connector=b, to_pin=pin)


def harness(wires: list[Wire], shields: list[ShieldGroup]) -> Harness:
    cons = [
        Connector(
            id=f"W001-P{k}",
            name=f"P{k}",
            role="cable",
            part_id="X",
            pins=[Pin(id="1"), Pin(id="2")],
        )  # fmt: skip
        for k in (1, 2, 3)
    ]
    return Harness(id="W001", name="H", connectors=cons, wires=wires, shields=shields)


def group(*ids: str, kind: str = "overall_shield") -> ShieldGroup:
    return ShieldGroup(id="W001-S1", kind=kind, wire_ids=list(ids), end_a="backshell_360", end_b="pigtail")  # type: ignore[arg-type]  # fmt: skip


def test_end_a_is_the_from_end_of_the_lowest_wire_id_in_the_harness() -> None:
    # listed in another order, and the lower wire drawn the other way round
    w2, w1 = wire(2, "W001-P1", "W001-P2"), wire(1, "W001-P2", "W001-P1", "2")
    s = group(w2.id, w1.id)
    h = harness([w2, w1], [s])
    assert reference_wire(h, s) == w1
    assert end_at(h, s, "W001-P2") == "a"
    assert end_at(h, s, "W001-P1") == "b"
    assert end_at(h, s, "W001-P3") is None


def test_a_group_across_a_branch_has_no_end_at_its_third_connector() -> None:
    w1, w2 = wire(1, "W001-P1", "W001-P2"), wire(2, "W001-P1", "W001-P3", "2")
    s = group(w1.id, w2.id)
    h = harness([w1, w2], [s])
    assert (end_at(h, s, "W001-P1"), end_at(h, s, "W001-P2")) == ("a", "b")
    assert end_at(h, s, "W001-P3") is None


def test_a_group_with_no_wire_in_the_harness_has_no_reference_and_no_end() -> None:
    w1 = wire(1, "W001-P1", "W001-P2")
    s = group("W001-099")
    h = harness([w1], [s])
    assert reference_wire(h, s) is None
    assert end_at(h, s, "W001-P1") is None
    # the drawing keeps its fallback: the first wire of the group on the sheet, else the first wire
    assert drawing._reference_wire(h, s, [w1]) == w1


def test_a_wire_from_a_connector_to_itself_is_end_a_there() -> None:
    w1 = Wire(id="W001-001", from_connector="W001-P1", from_pin="1", to_connector="W001-P1", to_pin="2")  # fmt: skip
    s = group(w1.id)
    assert end_at(harness([w1], [s]), s, "W001-P1") == "a"


@pytest.fixture(scope="module", params=GOLDEN_PROJECTS)
def golden(request: pytest.FixtureRequest) -> Project:
    return golden_project(request.param)


def test_the_rule_is_the_drawing_s_on_every_example_and_fixture(golden: Project) -> None:
    groups = 0
    for h in golden.harnesses.values():
        for s in h.shields:
            ref = reference_wire(h, s)
            assert ref is not None
            # the drawing asks with the wires of one sheet; the answer is the harness's
            assert drawing._reference_wire(h, s, list(reversed(h.wires))) == ref
            assert end_at(h, s, ref.from_connector) == "a"
            if ref.to_connector != ref.from_connector:
                assert end_at(h, s, ref.to_connector) == "b"
            members = [w for w in h.wires if w.id in s.wire_ids]
            ends = {c for w in members for c in (w.from_connector, w.to_connector)}
            if len(ends) <= 2:  # no group of the examples crosses a branch
                assert all(end_at(h, s, c) is not None for c in ends)
            groups += 1
    assert groups


def test_coax_and_nested_groups_of_flatsat() -> None:
    p = golden_project("flatsat")
    w005 = p.harnesses["W005"]
    coax = next(s for s in w005.shields if s.kind == "coax")
    ref = reference_wire(w005, coax)
    assert ref is not None and (coax.end_a, coax.end_b) == ("backshell_360", "backshell_360")
    assert {end_at(w005, coax, ref.from_connector), end_at(w005, coax, ref.to_connector)} == {"a", "b"}  # fmt: skip
    # a pair inside an overall shield: both groups have an end at each connector of the wire
    w002 = p.harnesses["W002"]
    twice = [w for w in w002.wires if sum(w.id in s.wire_ids for s in w002.shields) == 2]
    assert twice
    for w in twice:
        for s in (s for s in w002.shields if w.id in s.wire_ids):
            assert end_at(w002, s, w.from_connector) is not None
            assert end_at(w002, s, w.to_connector) is not None
