# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The rule `signal-unshielded` (design of 4.2.0, section 4; `core/drc/electrical.py`). The rule is
not registered yet (pull request 4 of the design), so these tests call the check directly.

Interface types that agree and that disagree, the narrowing by a connector's `carries`, a type that
shields per pair with a signal of no pair, a coax; a twisted pair is no shield, a shielded pair, an
overall shield, a coax and a quad are; a generated harness is left to the verifier (one finding of
`shield_missing`, none of this rule); and the four findings of the drawn harnesses of `loose_ends`."""

from pathlib import Path

import pytest

from harness_design_studio.core import templates
from harness_design_studio.core.drc import electrical
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.model import Project, SignalDef, evolve
from harness_design_studio.core.samples import mini3
from harness_design_studio.core.verify import verify_project
from tests.electrical_support import add_type, group, hand_made, linked, titles


def hits(p: Project) -> list[str]:
    return titles(electrical._signal_unshielded(p))


def test_every_wire_of_a_harness_made_from_a_connection_asks_for_its_shield() -> None:
    p, hid = linked()
    assert hits(p) == [
        f"Wire {hid}-001 in {hid} carries TX+, which the interface type rs422 shields (per pair), but is in no shield",
        f"Wire {hid}-002 in {hid} carries TX-, which the interface type rs422 shields (per pair), but is in no shield",
        f"Wire {hid}-003 in {hid} carries RX+, which the interface type rs422 shields (per pair), but is in no shield",
        f"Wire {hid}-004 in {hid} carries RX-, which the interface type rs422 shields (per pair), but is in no shield",
    ]  # fmt: skip
    found = list(electrical._signal_unshielded(p))
    assert (found[0].object_id, found[0].key) == (f"{hid}-001", f"{hid}.{hid}-001")
    p, hid = linked(carries=False)
    assert hits(p)[0] == (
        f"Wire {hid}-001 in {hid} carries TX+, which the interface types ethernet and rs422 shield "
        "(per pair), but is in no shield"
    )


def test_types_that_disagree_ask_for_nothing_and_carries_narrows_them() -> None:
    p, hid = linked(carries=False)
    add_type(p, "own", [("TX+", "TX"), ("TX-", "TX"), ("RX+", "RX"), ("RX-", "RX")])
    assert hits(p) == []  # the project's own type has the signals and does not shield them
    explained = electrical.shield_asked(p, p.harnesses[hid], p.harnesses[hid].wires[0])
    assert explained.types == (("ethernet", "per pair"), ("own", ""), ("rs422", "per pair"))
    assert not explained.asked
    # OBC-J01 and RW1-J02 are meant for rs422 (among others): own is left out again
    p.connectors["OBC-J01"] = evolve(p.connectors["OBC-J01"], carries=["rs422"])
    p.connectors["RW1-J02"] = evolve(p.connectors["RW1-J02"], carries=["rs422"])
    assert len(hits(p)) == 4
    # and meant for the own type only: nothing is asked
    p.connectors["OBC-J01"] = evolve(p.connectors["OBC-J01"], carries=["own"])
    p.connectors["RW1-J02"] = evolve(p.connectors["RW1-J02"], carries=["own"])
    assert hits(p) == []


def test_a_signal_of_no_pair_in_a_type_that_shields_per_pair_asks_for_nothing() -> None:
    p = mini3()
    t = p.interface_types["rs422"]
    p.interface_types["rs422"] = evolve(t, signals=[*t.signals, SignalDef(name="SGND", direction="passive")])  # fmt: skip
    p, hid = hand_made(["TX+", "SGND"], ["TX+", "SGND"], [("1", "1"), ("2", "2")], project=p)
    assert hits(p) == [
        f"Wire {hid}-001 in {hid} carries TX+, which the interface types ethernet and rs422 shield (per pair), but is in no shield",
    ]  # fmt: skip


def test_an_overall_type_and_a_coax_ask_and_a_type_that_shields_nothing_does_not() -> None:
    p, hid = hand_made(["SIG+", "RF", "PWR", "HTR+"], ["SIG+", "RF", "PWR", "HTR+"], [(str(n), str(n)) for n in range(1, 5)])  # fmt: skip
    assert hits(p) == [
        f"Wire {hid}-001 in {hid} carries SIG+, which the interface type analog shields (overall), but is in no shield",
        f"Wire {hid}-002 in {hid} carries RF, which the interface type rf_coax shields (as a coax), but is in no shield",
    ]  # fmt: skip
    # a twisted shielded pair whose shielding is none asks for nothing (as Generate reads it)
    p.interface_types["analog"] = evolve(p.interface_types["analog"], shielding="none")
    assert len(hits(p)) == 1


def test_a_signal_no_type_has_and_a_wire_without_a_signal_ask_for_nothing() -> None:
    p, _hid = hand_made(["1PPS+", None], ["1PPS+", None], [("1", "1"), ("2", "2")])
    assert hits(p) == []


@pytest.mark.parametrize(
    ("kind", "found"),
    [("twisted_pair", 4), ("shielded_pair", 2), ("overall_shield", 2), ("quad", 0)],
)
def test_which_groups_are_a_shield(kind: str, found: int) -> None:
    p, hid = linked()
    wires = [f"{hid}-001", f"{hid}-002"] + ([f"{hid}-003", f"{hid}-004"] if kind == "quad" else [])
    group(p, wires, kind)
    assert len(hits(p)) == found
    if kind == "twisted_pair":
        assert hits(p)[0].endswith(f"but is in no shield (it is in twisted pair {hid}-S1)")


def test_a_coax_group_is_a_shield() -> None:
    p, hid = hand_made(["RF"], ["RF"], [("1", "1")])
    assert len(hits(p)) == 1
    group(p, [f"{hid}-001"], "coax")
    assert hits(p) == []


def test_a_generated_harness_is_left_to_the_verifier(tmp_path: Path) -> None:
    p = templates.create_project(tmp_path / "f", "first-steps")
    generate_project(p)
    h = p.harnesses["W001"]
    assert h.generated and hits(p) == []
    p.harnesses["W001"] = evolve(h, shields=[])
    assert hits(p) == []  # one fault, one finding: the verifier's
    assert any(i.code == "shield_missing" for i in verify_project(p).issues)


def test_the_drawn_harnesses_of_loose_ends(tmp_path: Path) -> None:
    from harness_design_studio.core.io.loader import load_project
    from tests.loose_support import build_loose

    p = load_project(build_loose(tmp_path / "loose")).project
    assert hits(p) == [
        "Wire W009-003 in W009 carries TX+, which the interface types ethernet and rs422 shield (per pair), but is in no shield",
        "Wire W009-004 in W009 carries TX-, which the interface types ethernet and rs422 shield (per pair), but is in no shield",
        "Wire W011-001 in W011 carries SIG+, which the interface type analog shields (overall), but is in no shield (it is in twisted pair W011-S1)",
        "Wire W011-002 in W011 carries SIG-, which the interface type analog shields (overall), but is in no shield (it is in twisted pair W011-S1)",
    ]  # fmt: skip


def test_the_rule_has_the_texts_of_the_design() -> None:
    rule = next(r for r in electrical.ELECTRICAL_RULES if r.id == "signal-unshielded")
    assert (rule.severity, rule.topic, rule.can_waive, rule.can_deviate, rule.sources) == (
        "warning", "Shielded signals", True, False, (),
    )  # fmt: skip
    assert rule.why == (
        "A signal that its interface type shields picks up and radiates noise when its wire runs "
        "without a shield."
    )
    assert rule.how == (
        "Put the wire into a shielded pair, an overall shield or a coax (Group wires; Change "
        "group... for a wire in a twisted pair)."
    )
    p, hid = linked()
    assert [f.object_id for f in rule.run(p)] == [f"{hid}-00{n}" for n in range(1, 5)]
