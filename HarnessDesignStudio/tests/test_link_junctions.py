# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type,attr-defined,index"
"""REQ-HARN-05: a splice in a harness made from a connection (part C of the design of 5.0.0,
`docs/ait/DESIGN_5.0_FORMAT_5.md` sections 6, 12, 13 and 19; pull request 4).

Junctions and parallel pairs in the review of a link (`link_junction`; `link_pin_reused` for a
pin in two links and for a junction no harness can be made from); `plan_create_harness` with and
without a splice part; `verify.link_issues` by nets, and the old and the new `link_issues` equal on
random links without a junction (`tests/reference/link_issues_440.py`); the currents of the example
of section 5.2 through the made harness; no splice placed by hand in such a harness (F8) and none
made by Generate (B8); what a tool of format 4 does with a link with a junction. Every device,
part and number here is made up."""

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_design_studio.core import integrity, links, splices
from harness_design_studio.core.commands import Put, apply_ops
from harness_design_studio.core.currents import wire_currents
from harness_design_studio.core.drc import rules
from harness_design_studio.core.edit import EditError, clone_with
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.model import (
    Connector,
    Link,
    Part,
    Pin,
    PinPair,
    Project,
    Unit,
    Wire,
    evolve,
)
from harness_design_studio.core.samples import new_project
from harness_design_studio.core.verify import link_issues, verify_project
from tests.reference import integrity_181, links_430
from tests.reference import link_issues_440 as old_verify

SPLICE = "EX-SPLICE-1"
BOX = "EX-BOX-9"
A, B = "PCDU1-J01", "OBC1-J01"


def project(
    pcdu: dict[str, str | None] | None = None,
    obc: dict[str, str | None] | None = None,
    amps: dict[tuple[str, str], float] | None = None,
) -> Project:
    """Two devices, PCDU1 and OBC1, each with a connector J01 of nine pins (the signals given, by
    pin), the splice part EX-SPLICE-1 and the pin currents given."""
    p = new_project("Junctions")
    p.parts[BOX] = Part(id=BOX, category="connector", pin_count=9)
    p.parts[SPLICE] = Part(
        id=SPLICE, category="splice", manufacturer="Example Ltd", part_number=SPLICE,
        description="Crimp splice, one node (example)", pin_count=1, unverified=True,
    )  # fmt: skip
    for unit, cid, names in (("PCDU1", A, pcdu or {}), ("OBC1", B, obc or {})):
        p.units[unit] = Unit(id=unit, name=unit, subsystem="power")
        p.connectors[cid] = Connector(
            id=cid, name="J01", role="box", part_id=BOX, unit_id=unit,
            pins=[
                Pin(id=str(k), signal=names.get(str(k)), current_a=(amps or {}).get((cid, str(k))))
                for k in range(1, 10)
            ],
        )  # fmt: skip
    return p


def star(amps: dict[tuple[str, str], float] | None = None) -> Project:
    """The example of section 5.2: PCDU1-J01 pin 1 (PWR, 6 A) to OBC1-J01 pins 1, 2 and 3 (PWR,
    2 A each), and the return the same way on pin 2 and pins 4, 5 and 6 (`amps` in place of
    these currents when given)."""
    if amps is None:
        amps = {(A, "1"): 6.0, (A, "2"): 6.0} | {(B, str(k)): 2.0 for k in range(1, 7)}
    return project(
        {"1": "PWR", "2": "RTN"},
        {**{str(k): "PWR" for k in (1, 2, 3)}, **{str(k): "RTN" for k in (4, 5, 6)}},
        amps,
    )


def add_link(p: Project, pairs: list[tuple[str, str]]) -> str:
    ops, lid = links.plan_add_link(p, A, B, pairs)
    apply_ops(p, ops)
    return lid


def made(p: Project, lid: str, part: str | None = SPLICE) -> str:
    ops, hid = links.plan_create_harness(p, lid, part)
    apply_ops(p, ops)
    return hid


def findings(p: Project, lid: str) -> list[tuple[str, str, str, str | None]]:
    return [(f.code, f.severity, f.message, f.pin) for f in links.check_link(p, p.links[lid])]


def reused(p: Project, lid: str) -> list[tuple[str, str, str, str | None]]:
    return [f for f in findings(p, lid) if f[0] in ("link_pin_reused", "link_junction")]


def ends(p: Project, hid: str) -> list[tuple[str, str, str, str]]:
    """Each wire of the harness: its ID, its two ends and its signal ("" for none)."""
    return [
        (w.id, f"{w.from_connector}.{w.from_pin}", f"{w.to_connector}.{w.to_pin}", w.signal or "")
        for w in p.harnesses[hid].wires
    ]


STAR = [("1", "1"), ("1", "2"), ("1", "3")]
RETURN = [("2", "4"), ("2", "5"), ("2", "6")]


# ---- the review (section 6.1) --------------------------------------------------------------------


def test_a_junction_is_an_info_of_the_review_in_the_words_of_the_design() -> None:
    p = star()
    lid = add_link(p, STAR + RETURN)
    found = findings(p, lid)
    assert found == [
        (
            "link_junction",
            "info",
            "Pin 1 of PCDU1-J01 is joined to pins 1, 2 and 3 of OBC1-J01 (a junction); the harness made from the link joins them in a splice.",
            "PCDU1-J01.1",
        ),  # fmt: skip
        (
            "link_junction",
            "info",
            "Pin 2 of PCDU1-J01 is joined to pins 4, 5 and 6 of OBC1-J01 (a junction); the harness made from the link joins them in a splice.",
            "PCDU1-J01.2",
        ),  # fmt: skip
    ]
    assert integrity.check_integrity(p) == []
    # the design rules read the review by code: the info reaches none of the link rules
    hits = [h.title for r in rules.RULES if r.id.startswith("link-") for h in r.check(p)]
    assert not [m for m in hits if "junction" in m]


def test_a_junction_on_the_second_side_and_one_of_two_by_two() -> None:
    p = project({"1": "A", "2": "A", "3": "A"}, {"1": "A", "2": "A"})
    lid = add_link(p, [("1", "1"), ("2", "1"), ("3", "1")])
    assert (
        [m for c, _s, m, _p in findings(p, lid) if c == "link_junction"]
        == [
            "Pin 1 of OBC1-J01 is joined to pins 1, 2 and 3 of PCDU1-J01 (a junction); the harness made from the link joins them in a splice."  # fmt: skip
        ]
    )
    ops = links.plan_set_pairs(p, lid, [("1", "1"), ("1", "2"), ("2", "1"), ("2", "2")])
    apply_ops(p, ops)
    assert (
        [m for c, _s, m, _p in findings(p, lid) if c == "link_junction"]
        == [
            "Pins 1 and 2 of PCDU1-J01 are joined to pins 1 and 2 of OBC1-J01 (a junction); the harness made from the link joins them in a splice."  # fmt: skip
        ]
    )


def test_a_parallel_pair_says_nothing_and_a_pin_in_two_links_stays_an_error() -> None:
    p = project({"1": "PWR"}, {"1": "PWR", "2": "PWR"})
    lid = add_link(p, [("1", "1"), ("1", "1")])
    assert not [c for c, *_ in findings(p, lid) if c in ("link_junction", "link_pin_reused")]
    p.links["L2"] = Link(id="L2", a_connector=A, b_connector=B, pairs=[PinPair(a_pin="1", b_pin="2")])  # fmt: skip
    assert ("link_pin_reused", "error", "Pin 1 of PCDU1-J01 is paired in link L1 and in link L2. Keep it in one link.", "PCDU1-J01.1") in findings(p, "L2")  # fmt: skip
    assert [i.code for i in integrity.check_integrity(p)] == ["link_pin_reused"]


def test_a_junction_with_a_pair_missing_or_twice_is_an_error_and_makes_no_harness() -> None:
    p = project({"1": "A", "2": "A"}, {"1": "A", "2": "A"})
    lid = add_link(p, [("1", "1"), ("1", "2"), ("2", "2")])
    missing = (
        "Link L1 joins pins 1 and 2 of PCDU1-J01 and pins 1 and 2 of OBC1-J01 in one junction, but "
        "does not pair pin 2 of PCDU1-J01 with pin 1 of OBC1-J01. A junction pairs each of its pins "
        "with every pin of the other side: add that pair, or keep one pair for each pin."
    )
    assert reused(p, lid) == [("link_pin_reused", "error", missing, "PCDU1-J01.2")]
    with pytest.raises(EditError) as exc:
        links.plan_create_harness(p, lid, SPLICE)
    assert str(exc.value) == missing
    apply_ops(p, links.plan_set_pairs(p, lid, [("1", "1"), ("1", "2"), ("1", "2")]))
    twice = (
        "Link L1 pairs pin 1 of PCDU1-J01 with pin 2 of OBC1-J01 twice inside a junction, but the "
        "harness takes one wire from each pin of a junction to its splice. Keep one pair."
    )
    assert reused(p, lid) == [("link_pin_reused", "error", twice, "PCDU1-J01.1")]
    with pytest.raises(EditError, match="twice inside a junction"):
        links.plan_create_harness(p, lid, SPLICE)


def test_the_link_nets() -> None:
    nets = links.link_nets([PinPair(a_pin=a, b_pin=b) for a, b in [("1", "1"), ("2", "2"), ("1", "3"), ("2", "2")]])  # fmt: skip
    assert [(n.a_pins, n.b_pins, len(n.pairs), n.is_junction) for n in nets] == [
        (("1",), ("1", "3"), 2, True),
        (("2",), ("2",), 2, False),
    ]
    assert links.link_nets([]) == []


def test_the_proposal_still_pairs_a_pin_once() -> None:
    p = star()
    proposal = links.propose_pairs(p, A, B)
    used = [x.a_pin for x in proposal.pairs]
    assert len(used) == len(set(used)) and len({x.b_pin for x in proposal.pairs}) == len(used)


# ---- the harness made from such a link (section 6.2) ---------------------------------------------


def test_a_link_with_a_junction_needs_a_splice_part() -> None:
    p = star()
    lid = add_link(p, STAR)
    with pytest.raises(EditError) as exc:
        links.plan_create_harness(p, lid)
    assert str(exc.value) == (
        "Link L1 joins pin 1 of PCDU1-J01 to 3 pins of OBC1-J01. Choose a splice part (category "
        "splice) for the joint; the harness gets one splice for each junction."
    )
    with pytest.raises(EditError, match="is not a splice part"):
        links.plan_create_harness(p, lid, BOX)
    del p.parts[SPLICE]  # the starter library has none: a team adds its own
    with pytest.raises(EditError, match="is not a splice part"):
        links.plan_create_harness(p, lid, SPLICE)


def test_each_junction_gets_a_splice_and_each_pin_a_wire_to_its_node() -> None:
    p = star()
    lid = add_link(p, [*STAR, ("7", "7"), *RETURN])
    hid = made(p, lid)
    h = p.harnesses[hid]
    assert not h.generated and p.links[lid].harness_id == hid
    assert [
        (c.id, c.role, c.part_id, [x.id for x in c.pins])
        for c in h.connectors
        if c.role == "splice"
    ] == [  # fmt: skip
        (f"{hid}-X1", "splice", SPLICE, ["1"]),
        (f"{hid}-X2", "splice", SPLICE, ["1"]),
    ]
    p1, p2, x1, x2 = f"{hid}-P1", f"{hid}-P2", f"{hid}-X1", f"{hid}-X2"
    assert ends(p, hid) == [
        (f"{hid}-001", f"{p1}.1", f"{x1}.1", "PWR"),
        (f"{hid}-002", f"{x1}.1", f"{p2}.1", "PWR"),
        (f"{hid}-003", f"{x1}.1", f"{p2}.2", "PWR"),
        (f"{hid}-004", f"{x1}.1", f"{p2}.3", "PWR"),
        (f"{hid}-005", f"{p1}.7", f"{p2}.7", ""),
        (f"{hid}-006", f"{p1}.2", f"{x2}.1", "RTN"),
        (f"{hid}-007", f"{x2}.1", f"{p2}.4", "RTN"),
        (f"{hid}-008", f"{x2}.1", f"{p2}.5", "RTN"),
        (f"{hid}-009", f"{x2}.1", f"{p2}.6", "RTN"),
    ]
    # no length, gauge, colour or segment, as for every wire made from a link
    assert all(w.length_m is None and w.gauge_awg is None and w.colour is None for w in h.wires)
    assert not h.segments
    assert link_issues(p) == []
    assert not verify_project(p).errors
    assert [i for i in integrity.check_integrity(p) if i.severity != "info"] == []


def test_a_parallel_pair_gives_two_wires_on_the_same_two_pins_and_pin_shared_warns() -> None:
    p = project({"1": "PWR"}, {"1": "PWR"})
    lid = add_link(p, [("1", "1"), ("1", "1")])
    hid = made(p, lid, None)
    assert [e[1:3] for e in ends(p, hid)] == [(f"{hid}-P1.1", f"{hid}-P2.1")] * 2
    assert not [c for c in p.harnesses[hid].connectors if c.role == "splice"]
    assert link_issues(p) == []
    assert rules.shared_pins(p.harnesses[hid]) == {
        (f"{hid}-P1", "1"): [f"{hid}-001", f"{hid}-002"],
        (f"{hid}-P2", "1"): [f"{hid}-001", f"{hid}-002"],
    }  # the rule pin-shared warns, as for any pin with two wires


def test_a_link_without_a_junction_ignores_the_part_and_makes_the_harness_of_before() -> None:
    p = star()
    lid = add_link(p, [("1", "1"), ("2", "4")])
    q = clone_with(p, [])
    assert links.plan_create_harness(p, lid, SPLICE) == links.plan_create_harness(q, lid)
    assert links.plan_create_harness(p, lid) == links_430.plan_create_harness(p, lid)


def test_the_currents_of_the_example_of_section_5_2_through_the_made_harness() -> None:
    p = star()
    lid = add_link(p, STAR + RETURN)
    hid = made(p, lid)
    got = {k: (v.value, v.source) for k, v in wire_currents(p, p.harnesses[hid]).items()}
    assert got == {
        f"{hid}-{n:03d}": (amps, "pins")
        for n, amps in (
            (1, 6.0),
            (2, 2.0),
            (3, 2.0),
            (4, 2.0),
            (5, 6.0),
            (6, 2.0),
            (7, 2.0),
            (8, 2.0),
        )
    }


def test_no_splice_is_placed_by_hand_in_the_made_harness_and_generate_makes_none() -> None:
    p = star()
    lid = add_link(p, STAR)
    hid = made(p, lid)
    refused = f"{hid} was made from the connection {lid}, which owns its pairs of pins"
    assert refused in splices.refusal(p, hid)
    with pytest.raises(EditError, match="owns its pairs of pins"):
        splices.plan_add_splice(p, hid, SPLICE)
    with pytest.raises(EditError, match="owns its pairs of pins"):
        splices.plan_delete_splice(p, hid, f"{hid}-X1")
    before = p.harnesses[hid]
    generate_project(p)  # B8: Generate reads no link and makes no splice
    assert p.harnesses[hid] == before
    assert all(
        c.role != "splice" for h in p.harnesses.values() if h.generated for c in h.connectors
    )


# ---- the verifier by nets (section 6.3) ----------------------------------------------------------


def test_the_verifier_compares_a_link_with_its_harness_by_nets() -> None:
    p = star()
    lid = add_link(p, STAR)
    hid = made(p, lid)
    h = p.harnesses[hid]
    x1, p2 = f"{hid}-X1", f"{hid}-P2"
    extra = Wire(id=f"{hid}-009", from_connector=x1, from_pin="1", to_connector=p2, to_pin="5", manual=True)  # fmt: skip
    apply_ops(p, [Put("harnesses", evolve(h, wires=[*h.wires, extra]))])
    assert (
        [i.message for i in link_issues(p)]
        == [
            f"Harness {hid} joins pin 1 of PCDU1-J01 and pin 5 of OBC1-J01 through {x1}, which link {lid} does not pair."  # fmt: skip
        ]
    )
    apply_ops(p, [Put("harnesses", evolve(h, wires=[w for w in h.wires if w.id != f"{hid}-004"]))])
    assert (
        [i.message for i in link_issues(p)]
        == [
            f"Link {lid} pairs pin 1 of PCDU1-J01 with pin 3 of OBC1-J01, but harness {hid} has no wire between those pins. Add the wire, or change the pairing of the link."  # fmt: skip
        ]
    )
    assert all(i.code == "link_wire_mismatch" for i in link_issues(p))


def test_a_net_through_two_splices_names_both() -> None:
    p = star()
    lid = add_link(p, STAR + RETURN)
    hid = made(p, lid)
    h = p.harnesses[hid]
    bridge = Wire(id=f"{hid}-099", from_connector=f"{hid}-X1", from_pin="1", to_connector=f"{hid}-X2", to_pin="1", manual=True)  # fmt: skip
    apply_ops(p, [Put("harnesses", evolve(h, wires=[*h.wires, bridge]))])
    texts = [i.message for i in link_issues(p)]
    assert f"Harness {hid} joins pin 1 of PCDU1-J01 and pin 4 of OBC1-J01 through {hid}-X1 and {hid}-X2, which link {lid} does not pair." in texts  # fmt: skip
    assert len(texts) == 6  # pin 1 with pins 4 to 6, pin 2 with pins 1 to 3


@st.composite
def linked_projects(draw: st.DrawFn) -> Project:
    """A link without a junction (pairs of distinct pins, some given twice), its harness, and up
    to four random changes of the harness or the link afterwards (no splice)."""
    names: tuple[str | None, ...] = ("PWR", "RTN", "TX", "RX", None)
    p = project(
        {str(k): draw(st.sampled_from(names)) for k in range(1, 10)},
        {str(k): draw(st.sampled_from(names)) for k in range(1, 10)},
    )
    a_pins = draw(st.lists(st.sampled_from([str(k) for k in range(1, 10)]), min_size=1, max_size=6, unique=True))  # fmt: skip
    b_pins = draw(st.permutations([str(k) for k in range(1, 10)]))[: len(a_pins)]
    pairs = list(zip(a_pins, b_pins, strict=True))
    pairs += [pairs[k] for k in draw(st.lists(st.integers(0, len(pairs) - 1), max_size=2))]
    lid = add_link(p, pairs)
    hid = made(p, lid, None)
    rng = random.Random(draw(st.integers(0, 10**6)))
    for _ in range(draw(st.integers(0, 4))):
        h = p.harnesses[hid]
        wires = list(h.wires)
        kind = rng.choice(("delete", "add", "signal", "pin", "pairs", "reverse"))
        cables = [c.id for c in h.connectors]
        if kind == "delete" and wires:
            wires.pop(rng.randrange(len(wires)))
        elif kind == "add":
            wires.append(Wire(id=f"{hid}-{90 + len(wires)}", from_connector=rng.choice(cables), from_pin=str(rng.randint(1, 9)), to_connector=rng.choice(cables), to_pin=str(rng.randint(1, 9)), manual=True, signal=rng.choice(names)))  # fmt: skip
        elif kind == "signal" and wires:
            k = rng.randrange(len(wires))
            wires[k] = evolve(wires[k], signal=rng.choice(names))
        elif kind == "pin" and wires:
            k = rng.randrange(len(wires))
            wires[k] = evolve(wires[k], to_pin=str(rng.randint(1, 9)))
        elif kind == "reverse" and wires:
            k = rng.randrange(len(wires))
            w = wires[k]
            wires[k] = evolve(w, from_connector=w.to_connector, from_pin=w.to_pin, to_connector=w.from_connector, to_pin=w.from_pin)  # fmt: skip
        elif kind == "pairs":
            link = p.links[lid]
            p.links[lid] = evolve(link, pairs=[*link.pairs[1:], PinPair(a_pin=str(rng.randint(1, 9)), b_pin=str(rng.randint(1, 9)))])  # fmt: skip
        p.harnesses[hid] = evolve(h, wires=wires)
    return p


@settings(max_examples=150, deadline=None)
@given(linked_projects())
def test_without_a_splice_the_verifier_is_the_one_of_440(p: Project) -> None:
    """Section 6.3 and 11 (3): a harness without a splice gives the issues of 4.4.0, word for word."""
    assert link_issues(p) == old_verify.link_issues(p)


# ---- what a tool of format 4 does with such a link (sections 3.5 and 19, item 3) ----------------


def test_a_tool_of_format_4_reads_a_junction_as_a_pin_reused() -> None:
    """No key is new; the reading of the pairs is. The review and the check of 4.x (the same
    texts since 1.8.1: `tests/reference/links_430.py`, `integrity_181.py`) call a junction
    `link_pin_reused`, an error of `check`, so a 4.x tool (which opens a format 5 project
    read-only in any case) reports the project as damaged and its commands refuse it."""
    p = star()
    lid = add_link(p, STAR)
    assert "link_pin_reused" in [f.code for f in links_430.check_link(p, p.links[lid])]
    old = [i for i in integrity_181.check_integrity(p) if i.code == "link_pin_reused"]
    assert [i.severity for i in old] == ["error", "error"]
    assert old[0].message == (
        "Link 'L1' pairs pin '1' of connector 'PCDU1-J01' more than once. A pin belongs to one pair."
    )
    with pytest.raises(EditError, match="in two pairs"):
        links_430.plan_create_harness(p, lid)
    assert integrity.check_integrity(p) == []  # this tool: a junction, no error


# ---- the outputs (section 6.4): the splice outputs of 2.3.0, as for a harness drawn by hand ------


def test_the_splice_outputs_of_the_made_harness_and_their_check() -> None:
    import io

    from harness_design_studio.core.outputs.build import build_outputs
    from harness_design_studio.core.outputs.buildsheet import SPLICE_BLOCK
    from harness_design_studio.core.outputs.verify import verify_outputs
    from harness_design_studio.core.outputs.xlsx_env import load_workbook
    from tests.format5_support import format5_project

    p = format5_project()
    files = dict(build_outputs(p).files)
    report = verify_outputs(p, files)
    assert [i.message for i in report.errors] == []
    wires = files["harnesses/W003/wirelist.csv"].decode().splitlines()
    assert wires[2].endswith(",Via") and wires[3].endswith(",W003-X1")
    tests = files["harnesses/W003/tests.csv"].decode()
    assert "T001,continuity,W003-P1.1,W003-P2.1 via W003-X1," in tests
    wb = load_workbook(io.BytesIO(files["harnesses/W003/W003_build.xlsx"]), read_only=True)
    cells = [c for row in wb["Connectors"].iter_rows(values_only=True) for c in row if c]
    assert SPLICE_BLOCK in cells
    # a wrong Via cell is found by the check, which words the splice outputs on its own
    files["harnesses/W003/wirelist.csv"] = files["harnesses/W003/wirelist.csv"].replace(
        b",W003-X1\n", b",W003-X2\n", 1
    )
    assert verify_outputs(p, files).errors
