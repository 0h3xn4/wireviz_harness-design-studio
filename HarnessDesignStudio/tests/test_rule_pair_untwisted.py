# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-DRC-06. The rule `pair-untwisted` (design of 4.2.0, section 3; `core/drc/electrical.py`). The rule is
registered since pull request 4 of the design; these tests call the check directly.

Pairs from the interface type of the wires, from the types of the signals at the ends, from the names
(`+ -`, `P N`, `H L` and a project's own table) and from port names; twisted by a twisted pair, a
shielded pair and a quad, not by an overall shield or a part with two conductors; silent for three
wires of one name, a split pair and a wire with no signal; a generated harness of a type of
construction `single` with pairs; and, on every example, the pairs it finds are the twisted and
shielded pairs that `generate/shields.plan` makes, a second statement of the question that shares no
code with it."""

from pathlib import Path

import pytest

from harness_design_studio.core import templates
from harness_design_studio.core.commands import Put, apply_ops
from harness_design_studio.core.drc import electrical
from harness_design_studio.core.drc.rules import RULES
from harness_design_studio.core.generate import shields
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.manual_harness import plan_add_connector
from harness_design_studio.core.model import ConfigFile, Project, evolve
from harness_design_studio.core.wires import plan_add_wire, plan_wire_edit
from tests.electrical_support import add_type, group, hand_made, linked, titles

EXAMPLES = ("blank", "first-steps", "minimal-satellite", "small-satellite", "flatsat")
# the pairs of section 2.7 of the design: the twisted and shielded pairs Generate makes
EXAMPLE_PAIRS = {"blank": 0, "first-steps": 2, "minimal-satellite": 6, "small-satellite": 15, "flatsat": 31}  # fmt: skip


def hits(p: Project) -> list[str]:
    return titles(electrical._pair_untwisted(p))


def test_the_rules_are_registered_after_direction_conflict() -> None:
    ids = [r.id for r in RULES]
    at = ids.index("direction-conflict")
    assert len(RULES) == 43 and ids[at + 1 : at + 3] == ["pair-untwisted", "signal-unshielded"]


# ---- where a pair comes from --------------------------------------------------------------------


def test_a_harness_made_from_a_connection_pairs_by_the_types_of_the_signals() -> None:
    p, hid = linked()
    assert hits(p) == [
        f"Wires {hid}-001 (TX+) and {hid}-002 (TX-) in {hid} are pair TX of the interface type rs422 but are not twisted together",
        f"Wires {hid}-003 (RX+) and {hid}-004 (RX-) in {hid} are pair RX of the interface type rs422 but are not twisted together",
    ]  # fmt: skip
    # the connector carries rs422 (and rs485, can, discrete): ethernet, which has TX+ too, is left out
    p, hid = linked(carries=False)
    assert hits(p)[0] == (
        f"Wires {hid}-001 (TX+) and {hid}-002 (TX-) in {hid} are pair TX of the interface types "
        "ethernet and rs422 but are not twisted together"
    )
    found = list(electrical._pair_untwisted(p))
    assert [(h.object_id, h.key) for h in found] == [
        (f"{hid}-001", f"{hid}.{hid}-001+{hid}-002"),
        (f"{hid}-003", f"{hid}.{hid}-003+{hid}-004"),
    ]


def test_the_wires_of_a_generated_harness_pair_by_their_interface_type(tmp_path: Path) -> None:
    p = templates.create_project(tmp_path / "f", "first-steps")
    generate_project(p)
    assert hits(p) == []  # Generate twists every pair
    h = p.harnesses["W001"]
    p.harnesses["W001"] = evolve(h, shields=[])
    assert hits(p) == [
        "Wires W001-001 (TX+) and W001-003 (TX-) in W001 are pair TX of the interface type rs422 but are not twisted together",
        "Wires W001-002 (TX+) and W001-004 (TX-) in W001 are pair TX of the interface type rs422 but are not twisted together",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("a", "b"),
    [("1PPS+", "1PPS-"), ("TX_P", "TX_N"), ("CLKH", "CLKL"), ("SYNC-", "SYNC+"), ("REFN", "REFP")],
)
def test_names_that_differ_only_by_the_endings_of_a_row_are_a_pair(a: str, b: str) -> None:
    p, hid = hand_made([a, b], [a, b], [("1", "1"), ("2", "2")])
    assert hits(p) == [
        f"Wires {hid}-001 ({a}) and {hid}-002 ({b}) in {hid} are a pair by their names but are not twisted together"
    ]


@pytest.mark.parametrize(
    ("a", "b"),
    [("+", "-"), ("1pps+", "1PPS-"), ("SIGA", "SIGB"), ("TXH", "RXL"), ("CLKP", "CLKL")],
)
def test_names_compared_exactly_and_with_something_in_front(a: str, b: str) -> None:
    p, _hid = hand_made([a, b], [a, b], [("1", "1"), ("2", "2")])
    assert hits(p) == []


def test_a_project_table_of_endings_replaces_the_default() -> None:
    p, hid = hand_made(["SIGA", "SIGB", "CLKH", "CLKL"], ["SIGA", "SIGB", "CLKH", "CLKL"], [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4")])  # fmt: skip
    assert hits(p) == [f"Wires {hid}-003 (CLKH) and {hid}-004 (CLKL) in {hid} are a pair by their names but are not twisted together"]  # fmt: skip
    p.config["naming"] = ConfigFile(name="naming", placeholder=False, values={"pair_suffixes": [["A", "B"]]})  # fmt: skip
    assert hits(p) == [f"Wires {hid}-001 (SIGA) and {hid}-002 (SIGB) in {hid} are a pair by their names but are not twisted together"]  # fmt: skip
    p.config["naming"] = ConfigFile(name="naming", placeholder=False, values={"pair_suffixes": []})
    assert hits(p) == []
    # a refused table is not used, and no table is guessed in its place
    p.config["naming"] = ConfigFile(name="naming", placeholder=False, values={"pair_suffixes": [["A", "A"]]})  # fmt: skip
    assert electrical.pair_suffixes(p) == () and hits(p) == []


def test_a_type_that_has_both_signals_decides_before_the_names() -> None:
    # HTR+ and HTR- of the type heater are its pair H; TX+ and RX- of rs422 are two pairs: no pair
    p, hid = hand_made(["HTR+", "HTR-", "TX+", "RX-"], ["HTR+", "HTR-", "TX+", "RX-"], [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4")])  # fmt: skip
    assert hits(p) == [f"Wires {hid}-001 (HTR+) and {hid}-002 (HTR-) in {hid} are pair H of the interface type heater but are not twisted together"]  # fmt: skip
    # a type of the project that has both names but no pair for them: not a pair, even by the names
    add_type(p, "own", [("HTR+", None), ("HTR-", None)])
    assert hits(p) == []


def test_a_fixed_pin_named_for_a_port_reads_as_the_signal_of_the_type() -> None:
    names = ["RS422_2_TX+", "RS422_2_TX-"]
    p, hid = hand_made(names, names, [("1", "1"), ("2", "2")], fixed=True)
    assert hits(p) == [
        f"Wires {hid}-001 (RS422_2_TX+) and {hid}-002 (RS422_2_TX-) in {hid} are pair TX of the "
        "interface types ethernet and rs422 but are not twisted together"
    ]
    # not fixed: no port is read, and the names still differ only by + and -
    p, hid = hand_made(names, names, [("1", "1"), ("2", "2")])
    assert hits(p) == [f"Wires {hid}-001 (RS422_2_TX+) and {hid}-002 (RS422_2_TX-) in {hid} are a pair by their names but are not twisted together"]  # fmt: skip


def test_a_crossed_pair_is_named_at_its_first_connector() -> None:
    p, hid = hand_made(["TX+", "TX-", None], [None, "RX+", "RX-"], [("1", "2"), ("2", "3")])
    assert hits(p) == [f"Wires {hid}-001 (TX+) and {hid}-002 (TX-) in {hid} are pair TX of the interface types ethernet and rs422 but are not twisted together"]  # fmt: skip


# ---- twisted or not ---------------------------------------------------------------------------


@pytest.mark.parametrize(("kind", "twisted"), [("twisted_pair", True), ("shielded_pair", True), ("overall_shield", False)])  # fmt: skip
def test_a_twisted_or_shielded_pair_twists_and_an_overall_shield_does_not(kind: str, twisted: bool) -> None:  # fmt: skip
    p, hid = linked()
    group(p, [f"{hid}-001", f"{hid}-002"], kind)
    assert len(hits(p)) == (1 if twisted else 2)


def test_a_quad_twists_and_a_coax_does_not() -> None:
    p, hid = linked()
    group(p, [f"{hid}-001", f"{hid}-002", f"{hid}-003", f"{hid}-004"], "quad")
    assert hits(p) == []
    p, hid = linked()
    group(p, [f"{hid}-001"], "coax")
    group(p, [f"{hid}-002"], "coax")
    assert len(hits(p)) == 2


def test_a_wire_part_with_two_conductors_does_not_make_a_twisted_pair() -> None:
    p, hid = linked()
    part = next(x for x in p.parts.values() if x.category == "wire")
    apply_ops(p, [Put("parts", evolve(part, conductors=2))])
    apply_ops(p, plan_wire_edit(p, [f"{hid}-001", f"{hid}-002"], {"part_id": part.id}))
    assert len(hits(p)) == 2


# ---- silent -------------------------------------------------------------------------------------


def test_three_wires_of_one_name_make_no_pair() -> None:
    p, _hid = hand_made(["TX+", "TX-", "TX+"], ["TX+", "TX-", "TX+"], [("1", "1"), ("2", "2"), ("3", "3")])  # fmt: skip
    assert hits(p) == []
    p, _hid = hand_made(["1PPS+", "1PPS-", "1PPS-"], ["1PPS+", "1PPS-", "1PPS-"], [("1", "1"), ("2", "2"), ("3", "3")])  # fmt: skip
    assert hits(p) == []


def test_a_split_pair_and_a_wire_with_no_signal_are_silent() -> None:
    p, hid = hand_made(["TX+", "TX-"], ["TX+", "TX-"], [("1", "1")])
    # the second wire of the pair runs to another connector: the two are not on the same two
    ops, far = plan_add_connector(p, hid, mates_with="PCDU-J03")
    apply_ops(p, ops)
    pin = next(c for c in p.harnesses[hid].connectors if c.id == far).pins[0].id
    apply_ops(p, plan_add_wire(p, hid, f"{hid}-P1", "2", far, pin))
    assert hits(p) == []
    p, _hid = hand_made([None, None], [None, None], [("1", "1"), ("2", "2")])
    assert hits(p) == []
    p, _hid = hand_made(["TX+", None], ["TX+", None], [("1", "1"), ("2", "2")])
    assert hits(p) == []


# ---- a type of construction single with pairs -----------------------------------------------


def test_a_generated_harness_of_a_single_type_with_pairs_is_found(tmp_path: Path) -> None:
    p = templates.create_project(tmp_path / "f", "first-steps")
    p.interface_types["rs422"] = evolve(p.interface_types["rs422"], construction="single", shielding="none")  # fmt: skip
    generate_project(p)
    assert not any(g.kind in electrical.TWISTING_KINDS for g in p.harnesses["W001"].shields)
    assert len(hits(p)) == 2 and all("of the interface type rs422" in t for t in hits(p))


# ---- the second statement: the pairs Generate makes ----------------------------------------


def _plan_pairs(p: Project) -> set[frozenset[str]]:
    """The twisted and shielded pairs `shields.plan` makes of the signal pairs of the types (the way
    out and back of a power type, which it twists too, is no signal pair)."""
    out: set[frozenset[str]] = set()
    for h in p.harnesses.values():
        ifaces = [p.interfaces[i] for i in sorted({w.interface_id for w in h.wires if w.interface_id})]  # fmt: skip
        for g in shields.plan(p, ifaces, list(h.wires)):
            t = p.interface_types[p.interfaces[g.interface_id].type_id]
            paired = {s.name for s in t.signals if s.pair}
            if g.kind in ("twisted_pair", "shielded_pair") and all(
                (w.signal or "").split("/")[0] in paired for w in g.wires
            ):
                out.add(frozenset(w.id for w in g.wires))
    return out


@pytest.mark.parametrize("name", EXAMPLES)
def test_on_every_example_the_pairs_are_those_generate_twists(tmp_path: Path, name: str) -> None:
    p = templates.create_project(tmp_path / name, name)
    if not p.harnesses:
        generate_project(p)
    assert hits(p) == []  # no example fires (section 2.7)
    found = {frozenset((x.a.id, x.b.id)) for h in p.harnesses.values() for x in electrical.signal_pairs(p, h)}  # fmt: skip
    assert found == _plan_pairs(p) and len(found) == EXAMPLE_PAIRS[name]
    for hid in list(p.harnesses):
        p.harnesses[hid] = evolve(p.harnesses[hid], shields=[])
    assert len(hits(p)) == EXAMPLE_PAIRS[name]


def test_the_drawn_harnesses_of_loose_ends(tmp_path: Path) -> None:
    from harness_design_studio.core.io.loader import load_project
    from tests.loose_support import build_loose

    p = load_project(build_loose(tmp_path / "loose")).project
    assert hits(p) == [
        "Wires W009-003 (TX+) and W009-004 (TX-) in W009 are pair TX of the interface types ethernet and rs422 but are not twisted together",
        "Wires W010-001 (1PPS+) and W010-002 (1PPS-) in W010 are a pair by their names but are not twisted together",
        "Wires W013-001 (1PPS+) and W013-002 (1PPS-) in W013 are a pair by their names but are not twisted together",
    ]  # fmt: skip


def test_the_rule_has_the_texts_of_the_design() -> None:
    rule = next(r for r in electrical.ELECTRICAL_RULES if r.id == "pair-untwisted")
    assert (rule.severity, rule.topic, rule.can_waive, rule.can_deviate, rule.sources) == (
        "warning", "Twisted pairs", True, False, (),
    )  # fmt: skip
    assert rule.why == "Two wires of a signal pair that are not twisted together pick up noise and radiate it."  # fmt: skip
    assert rule.how == (
        "Select the two wires and use Group wires (twisted pair, or shielded pair if the signal "
        "needs a shield); for a harness Generate made, give the interface type a twisted "
        "construction and generate again."
    )
    p, hid = linked()
    findings = rule.run(p)
    assert [f.object_id for f in findings] == [f"{hid}-001", f"{hid}-003"]
    assert findings[0].why == f"{rule.why} To fix it: {rule.how}" and findings[0].fix_label is None
