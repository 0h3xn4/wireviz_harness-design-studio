# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-PIN-09. With `naming.far_device_names` on, the pairing proposal of a connection reads the
other device's name off a pin name and leaves out the pins that name a third device, with a note,
and the link review reads the names the same way (design of 4.4.0,
`docs/ait/DESIGN_4.4_NAMES_PORTS.md`, sections 2.3 and 4; owner questions N1, N9 and N10). With the
setting off (the default) the proposal and the review are those of 4.3.0: `tests/reference/
links_430.py` is that module, verbatim, and the property tests compare the two on random
connectors whose pins also name devices. Device and signal names are made up (`OBC1`, `TTC1`)."""

import dataclasses
from collections.abc import Sequence

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_design_studio.core import configcheck, links
from harness_design_studio.core.commands import apply_ops
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.model import (
    ConfigFile,
    Connector,
    Link,
    Part,
    Pin,
    PinPair,
    Project,
    Unit,
    evolve,
)
from harness_design_studio.core.samples import mini3
from tests.reference import links_430 as old

OBC = ["TTC1_TX", "TTC1_RX", "TTC1_PPS", "TTC2_TX", "TTC2_RX", "TTC2_PPS"]
BARE = ["TX", "RX", "PPS"]
NOTE_TTC1 = (
    "Pins 1, 2 and 3 of OBC1-J01 name device TTC1, so they are not offered in a link to TTC2 "
    "(Settings > Project: Signal names name the far device)."
)
NOTE_TTC2 = (
    "Pins 4, 5 and 6 of OBC1-J01 name device TTC2, so they are not offered in a link to TTC1 "
    "(Settings > Project: Signal names name the far device)."
)


def empty() -> Project:
    p = mini3()
    for objects in (p.harnesses, p.interfaces, p.links, p.connectors, p.units, p.placements):
        objects.clear()  # type: ignore[attr-defined]
    part = Part(id="GEN-12", category="connector", pin_count=12, description="generated")
    p.parts[part.id] = part
    return p


def add(p: Project, cid: str, unit: str, names: Sequence[str | None]) -> None:
    if unit not in p.units:
        p.units[unit] = Unit(id=unit, name=f"Device {unit}", subsystem="example")
    pins = [Pin(id=str(n + 1), signal=s) for n, s in enumerate(names)]
    p.connectors[cid] = Connector(
        id=cid, name=cid.split("-")[-1], role="box", part_id="GEN-12", unit_id=unit,
        gender="female", pins=pins,
    )  # fmt: skip


def turn_on(p: Project) -> Project:
    plan = configcheck.plan_set_far_device_names(p, True)
    assert plan.ok
    apply_ops(p, plan.ops)
    return p


def two_transceivers(obc: Sequence[str | None], ttc: Sequence[str | None], *, on: bool) -> Project:
    """The run of section 2.3: OBC1 with one connector of the pins of both transceivers, TTC1 and
    TTC2 each with one connector of the names `ttc`."""
    p = empty()
    add(p, "OBC1-J01", "OBC1", obc)
    add(p, "TTC1-J01", "TTC1", ttc)
    add(p, "TTC2-J01", "TTC2", ttc)
    return turn_on(p) if on else p


def pairs_by_name(p: Project, a: str, b: str) -> list[str]:
    prop = links.propose_pairs(p, a, b)
    na = {x.id: x.signal for x in p.connectors[a].pins}
    nb = {x.id: x.signal for x in p.connectors[b].pins}
    return [f"{na[x.a_pin]}={nb[x.b_pin]}" for x in prop.pairs]


def link(p: Project, a: str, b: str, pairs: list[tuple[str, str]], lid: str = "L1") -> Link:
    made = Link(
        id=lid, name="", a_connector=a, b_connector=b,
        pairs=[PinPair(a_pin=x, b_pin=y) for x, y in pairs],
    )  # fmt: skip
    p.links[lid] = made
    return made


# ---- the setting ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("values", "on"),
    [({}, False), ({"far_device_names": False}, False), ({"far_device_names": "yes"}, False),
     ({"far_device_names": 1}, False), ({"far_device_names": True}, True)],
    ids=["unset", "false", "text", "one", "true"],
)  # fmt: skip
def test_only_true_turns_the_reading_on(values: dict[str, object], on: bool) -> None:
    p = empty()
    base = p.config.get("naming")
    kept = dict(base.values) if base is not None else {}
    p.config["naming"] = ConfigFile(name="naming", placeholder=False, values={**kept, **values})
    assert links.far_device_names_on(p) is on


# ---- section 2.3 with the setting off: 4.3.0 -----------------------------------------------------


def test_off_the_proposal_for_ttc2_pairs_the_ttc1_pins_as_in_430() -> None:
    p = two_transceivers(OBC, BARE, on=False)
    for far in ("TTC1-J01", "TTC2-J01"):
        assert pairs_by_name(p, "OBC1-J01", far) == ["TTC1_TX=RX", "TTC1_RX=TX"]
        prop = links.propose_pairs(p, "OBC1-J01", far)
        assert prop.unpaired_a == ("3", "4", "5", "6") and prop.unpaired_b == ("3",)
        assert prop.notes == ()


# ---- section 4.1 with the setting on -------------------------------------------------------------


def test_on_each_transceiver_gets_its_own_pins_with_the_note() -> None:
    p = two_transceivers(OBC, BARE, on=True)
    assert pairs_by_name(p, "OBC1-J01", "TTC1-J01") == ["TTC1_TX=RX", "TTC1_RX=TX", "TTC1_PPS=PPS"]
    assert pairs_by_name(p, "OBC1-J01", "TTC2-J01") == ["TTC2_TX=RX", "TTC2_RX=TX", "TTC2_PPS=PPS"]
    to_ttc1 = links.propose_pairs(p, "OBC1-J01", "TTC1-J01")
    to_ttc2 = links.propose_pairs(p, "OBC1-J01", "TTC2-J01")
    assert to_ttc1.notes == (NOTE_TTC2,)
    assert to_ttc2.notes == (NOTE_TTC1,)
    # the left-out pins are not offered, so they are not in the unpaired lists either
    assert to_ttc2.unpaired_a == () and to_ttc2.unpaired_b == ()


def test_on_a_prefix_on_both_sides_pairs() -> None:
    p = two_transceivers(OBC, ["OBC1_RX", "OBC1_TX"], on=True)
    assert pairs_by_name(p, "OBC1-J01", "TTC1-J01") == ["TTC1_TX=OBC1_RX", "TTC1_RX=OBC1_TX"]
    assert pairs_by_name(p, "OBC1-J01", "TTC2-J01") == ["TTC2_TX=OBC1_RX", "TTC2_RX=OBC1_TX"]
    q = two_transceivers(OBC, ["OBC1_RX", "OBC1_TX"], on=False)
    assert pairs_by_name(q, "OBC1-J01", "TTC2-J01") == []  # 4.3.0 pairs nothing


@pytest.mark.parametrize("first", ["TTC1-J01", "TTC2-J01"], ids=["ttc1", "ttc2"])
def test_on_the_order_of_the_links_no_longer_matters(first: str) -> None:
    p = two_transceivers(OBC, BARE, on=True)
    ops, _lid = links.plan_add_link(p, "OBC1-J01", first)
    apply_ops(p, ops)
    second = "TTC2-J01" if first == "TTC1-J01" else "TTC1-J01"
    unit = second.split("-")[0]
    assert pairs_by_name(p, "OBC1-J01", second) == [f"{unit}_TX=RX", f"{unit}_RX=TX", f"{unit}_PPS=PPS"]  # fmt: skip
    notes = links.propose_pairs(p, "OBC1-J01", second).notes
    assert any("already paired in link L1" in n for n in notes)


def test_on_the_far_side_also_leaves_out_a_third_device() -> None:
    p = two_transceivers(OBC, BARE, on=True)
    add(p, "TTC2-J02", "TTC2", ["RX", "TTC1_PPS", "PPS"])
    prop = links.propose_pairs(p, "OBC1-J01", "TTC2-J02")
    assert [(x.a_pin, x.b_pin) for x in prop.pairs] == [("4", "1"), ("6", "3")]
    assert prop.notes == (
        NOTE_TTC1,
        "Pin 2 of TTC2-J02 names device TTC1, so it is not offered in a link to OBC1 "
        "(Settings > Project: Signal names name the far device).",
    )


def test_on_a_name_of_two_devices_is_read_whole_with_its_note() -> None:
    p = two_transceivers(["TTC1_TX_TTC2", "PPS"], BARE, on=True)
    prop = links.propose_pairs(p, "OBC1-J01", "TTC2-J01")
    assert pairs_by_name(p, "OBC1-J01", "TTC2-J01") == ["PPS=PPS"]
    assert prop.unpaired_a == ("1",)  # offered, and read whole: it meets no name of TTC2
    assert prop.notes == (
        "Pin 1 of OBC1-J01: TTC1_TX_TTC2 can be read as a name of TTC1 or of TTC2, so it names "
        "neither. Rename the pin.",
    )


def test_on_a_pin_that_names_its_own_device_is_read_whole() -> None:
    """N10: `TTC2_TX` on TTC2 is not read as `TX`; a prefix missing on one side still meets its
    counterpart, as in 4.3.0, and whole names that are equal still pair (`TTC2_PPS` on both)."""
    p = two_transceivers(["RX", "TTC2_PPS", "PPS"], ["TTC2_TX", "TTC2_PPS", "TTC2_CLK"], on=True)
    assert pairs_by_name(p, "OBC1-J01", "TTC2-J01") == ["RX=TTC2_TX", "TTC2_PPS=TTC2_PPS"]
    prop = links.propose_pairs(p, "OBC1-J01", "TTC2-J01")
    assert prop.unpaired_a == ("3",) and prop.unpaired_b == ("3",)  # PPS and TTC2_CLK
    off = two_transceivers(["RX", "TTC2_PPS", "PPS"], ["TTC2_TX", "TTC2_PPS", "TTC2_CLK"], on=False)
    assert pairs_by_name(off, "OBC1-J01", "TTC2-J01") == ["RX=TTC2_TX", "TTC2_PPS=TTC2_PPS"]


def test_on_two_transmit_names_are_not_paired_and_the_note_says_why() -> None:
    p = two_transceivers(["TTC2_TX", "TTC2_TX"], ["TX", "TTC2_TX"], on=True)
    prop = links.propose_pairs(p, "OBC1-J01", "TTC2-J01")
    assert prop.pairs == ()
    assert prop.notes == (
        "TTC2_TX on pin 1 of OBC1-J01 and TX on pin 1 of TTC2-J01 were not paired: they look like "
        "transmit to transmit. If one device names its pins from the other's point of view, pair "
        "them yourself.",
        "TTC2_TX on pin 1 of OBC1-J01 and TTC2_TX on pin 2 of TTC2-J01 were not paired: they look "
        "like transmit to transmit. If one device names its pins from the other's point of view, "
        "pair them yourself.",
        "TTC2_TX on pin 2 of OBC1-J01 and TX on pin 1 of TTC2-J01 were not paired: they look like "
        "transmit to transmit. If one device names its pins from the other's point of view, pair "
        "them yourself.",
        "TTC2_TX on pin 2 of OBC1-J01 and TTC2_TX on pin 2 of TTC2-J01 were not paired: they look "
        "like transmit to transmit. If one device names its pins from the other's point of view, "
        "pair them yourself.",
    )


def test_on_the_longest_id_wins() -> None:
    p = empty()
    add(p, "OBC1-J01", "OBC1", ["OBC1-R_TX", "OBC1_TX"])
    add(p, "TTC1-J01", "TTC1", ["RX"])
    p.units["OBC1-R"] = Unit(id="OBC1-R", name="Device OBC1-R", subsystem="example")
    turn_on(p)
    # on OBC1, OBC1-R_TX names the redundant computer, OBC1_TX names OBC1 itself
    prop = links.propose_pairs(p, "OBC1-J01", "TTC1-J01")
    assert pairs_by_name(p, "OBC1-J01", "TTC1-J01") == ["OBC1_TX=RX"]
    assert prop.notes == (
        "Pin 1 of OBC1-J01 names device OBC1-R, so it is not offered in a link to TTC1 "
        "(Settings > Project: Signal names name the far device).",
    )


def test_on_a_loose_cable_end_reads_names_as_in_430() -> None:
    p = two_transceivers(OBC, BARE, on=True)
    loose = evolve(p.connectors["TTC2-J01"], unit_id=None)
    new = links.propose_pairs_between(p, p.connectors["OBC1-J01"], loose)
    was = old.propose_pairs_between(p, p.connectors["OBC1-J01"], loose)
    assert dataclasses.astuple(new) == dataclasses.astuple(was)


def test_on_the_one_click_connection_starts_with_the_connector_of_the_far_device() -> None:
    def made(on: bool) -> Project:
        p = empty()
        add(p, "OBC1-J01", "OBC1", ["TTC1_TX", "TTC1_RX"])
        add(p, "OBC1-J02", "OBC1", ["TTC2_TX", "TTC2_RX", "TTC2_PPS"])
        add(p, "TTC2-J01", "TTC2", BARE)
        p.units["TTC1"] = Unit(id="TTC1", name="Device TTC1", subsystem="example")
        return turn_on(p) if on else p

    off, on = made(False), made(True)
    assert links.best_connectors(off, "OBC1", "", "TTC2", "") == ("OBC1-J01", "TTC2-J01")
    assert links.best_connectors(on, "OBC1", "", "TTC2", "") == ("OBC1-J02", "TTC2-J01")
    quick = links.plan_quick_link(on, "OBC1", "TTC2")
    assert (quick.a_connector, quick.pairs, quick.by) == ("OBC1-J02", 3, "signals")


# ---- section 4.2: the review -------------------------------------------------------------------


def messages(p: Project) -> list[tuple[str, str, str | None]]:
    return [(f.code, f.message, f.pin) for f in links.check_links(p)]


def test_review_names_a_pair_of_a_third_device() -> None:
    p = two_transceivers(OBC, BARE, on=True)
    link(p, "OBC1-J01", "TTC2-J01", [("1", "2"), ("4", "2"), ("6", "3")])
    found = messages(p)
    assert (
        "link_signal_mismatch",
        "Link L1 pairs pin 1 of OBC1-J01 with pin 2 of TTC2-J01, but TTC1_TX names unit TTC1, not "
        "TTC2. Pair it in a link to TTC1, or rename the pin.",
        "OBC1-J01.1",
    ) in found
    # TTC2_PPS and PPS match in a link to TTC2: no finding for that pair
    assert not [m for m in found if "pin 6 of OBC1-J01" in m[1]]
    off = two_transceivers(OBC, BARE, on=False)
    link(off, "OBC1-J01", "TTC2-J01", [("1", "2"), ("4", "2"), ("6", "3")])
    found_off = messages(off)
    assert not [m for m in found_off if "names unit" in m[1]]
    assert any("signals differ (TTC2_PPS and PPS)" in m[1] for m in found_off)


def test_review_points_an_unpaired_pin_of_a_third_device_to_that_device() -> None:
    p = two_transceivers(OBC, BARE, on=True)
    ops, _lid = links.plan_add_link(p, "OBC1-J01", "TTC2-J01")
    apply_ops(p, ops)
    found = messages(p)
    assert [m for m in found if m[0] == "link_pin_unpaired"] == [
        (
            "link_pin_unpaired",
            f"Pin {n} of OBC1-J01 is named {s} (unit TTC1) but no link pairs it. Link OBC1-J01 "
            "to a connector of TTC1, or set its role to Spare if it is not used.",
            f"OBC1-J01.{n}",
        )
        for n, s in (("1", "TTC1_TX"), ("2", "TTC1_RX"), ("3", "TTC1_PPS"))
    ]
    assert len(found) == 3  # the pairs the proposal made are not reported
    ops, _lid = links.plan_add_link(p, "OBC1-J01", "TTC1-J01")  # a link to TTC1 pairs them
    apply_ops(p, ops)
    assert messages(p) == []
    off = two_transceivers(OBC, BARE, on=False)
    link(off, "OBC1-J01", "TTC2-J01", [("4", "2"), ("5", "1"), ("6", "3")])
    unpaired_off = [m[1] for m in messages(off) if m[0] == "link_pin_unpaired"]
    assert unpaired_off[0] == (
        "Pin 1 of OBC1-J01 is named TTC1_TX but is not paired in link L1. Pair it with a pin of "
        "TTC2-J01, or set its role to Spare if it is not used."
    )


def test_review_reads_a_third_device_on_the_far_side_too() -> None:
    p = two_transceivers(OBC, BARE, on=True)
    add(p, "TTC2-J02", "TTC2", ["RX", "TTC1_PPS"])
    link(p, "OBC1-J01", "TTC2-J02", [("4", "1"), ("6", "2")])
    found = links.check_link(p, p.links["L1"])
    assert (
        "Link L1 pairs pin 6 of OBC1-J01 with pin 2 of TTC2-J02, but TTC1_PPS names unit TTC1, "
        "not OBC1. Pair it in a link to TTC1, or rename the pin."
    ) in [f.message for f in found]
    assert [f.pin for f in found if "names unit TTC1, not OBC1" in f.message] == ["TTC2-J02.2"]


def test_review_two_transmit_names_after_the_reading() -> None:
    p = two_transceivers(["TTC2_TX"], ["TX"], on=True)
    link(p, "OBC1-J01", "TTC2-J01", [("1", "1")])
    assert [m[1] for m in messages(p)] == [
        "Link L1 pairs pin 1 of OBC1-J01 with pin 1 of TTC2-J01, and TTC2_TX and TX both read as "
        "TX, which looks like transmit to transmit. A transmit pin should meet a receive pin. "
        "Check the pairing, or the names."
    ]


def test_the_proposal_is_never_refused_by_the_review() -> None:
    """A link made from the proposal has no `link_signal_mismatch` (the review reads as the
    proposal does)."""
    for ttc in (BARE, ["OBC1_RX", "OBC1_TX", "PPS"], ["TTC2_TX", "TTC2_PPS", "RX"]):
        p = two_transceivers(OBC, ttc, on=True)
        for far in ("TTC1-J01", "TTC2-J01"):
            ops, lid = links.plan_add_link(p, "OBC1-J01", far, link_id=f"L{far[3]}")
            apply_ops(p, ops)
            codes = {f.code for f in links.check_link(p, p.links[lid])}
            assert "link_signal_mismatch" not in codes, (ttc, far)


# ---- with the setting off: the functions of 4.3.0 (Hypothesis) ---------------------------------

UNITS = ("OBC1", "OBC1-R", "TTC1", "TTC2", "D1")
_WORDS = ("TX", "RX", "TXD", "RXD", "PPS", "PWR", "RTN", "GND", "CANH", "TX+", "RX-", "MOSI",
          "MISO", "CLK", "SIG")  # fmt: skip
_PART = st.sampled_from(("", *UNITS, "UART", "A"))
_SEP = st.sampled_from(("_", ".", "-"))


@st.composite
def pin_names(draw: st.DrawFn) -> str | None:
    """Signal names, many of which name a device of the project as a prefix or a suffix."""
    if draw(st.integers(0, 9)) == 0:
        return None
    word = draw(st.sampled_from(_WORDS))
    head, tail = draw(_PART), draw(_PART)
    name = word
    if head:
        name = f"{head}{draw(_SEP)}{name}"
    if tail and draw(st.booleans()):
        name = f"{name}{draw(_SEP)}{tail}"
    return name.lower() if draw(st.integers(0, 9)) == 0 else name


@st.composite
def projects(draw: st.DrawFn, *, flag: object = None) -> Project:
    """A project of the five devices with up to two connectors each, named at random, a few
    links paired at random (pins that do not exist and pins used twice included), and the
    setting `far_device_names` set to `flag` (None: not set)."""
    p = empty()
    for unit in UNITS:
        p.units[unit] = Unit(id=unit, name=f"Device {unit}", subsystem="example")
        for k in range(draw(st.integers(0, 2))):
            names = draw(st.lists(pin_names(), min_size=1, max_size=7))
            add(p, f"{unit}-J{k + 1:02d}", unit, names)
    ids = sorted(p.connectors)
    if len(ids) >= 2:
        for n in range(draw(st.integers(0, 3))):
            a, b = draw(st.sampled_from(ids)), draw(st.sampled_from(ids))
            if p.connectors[a].unit_id == p.connectors[b].unit_id:
                continue
            pins_a = [x.id for x in p.connectors[a].pins] + ["99"]
            pins_b = [x.id for x in p.connectors[b].pins] + ["98"]
            pairs = draw(st.lists(st.tuples(st.sampled_from(pins_a), st.sampled_from(pins_b)), max_size=6))  # fmt: skip
            link(p, a, b, pairs, f"L{n + 1}")
    if flag is not None:
        base = p.config.get("naming")
        kept = dict(base.values) if base is not None else {}
        p.config["naming"] = ConfigFile(
            name="naming", placeholder=False, values={**kept, "far_device_names": flag}
        )
    return p


def _proposal(module: object, p: Project, a: str, b: str) -> tuple[object, ...]:
    try:
        return dataclasses.astuple(module.propose_pairs(p, a, b))  # type: ignore[attr-defined]
    except EditError as exc:
        return ("refused", str(exc))


@settings(max_examples=150, deadline=None)
@given(st.data())
def test_off_the_proposal_is_the_430_one(data: st.DataObject) -> None:
    flag = data.draw(st.sampled_from((None, False)))
    p = data.draw(projects(flag=flag))
    ids = sorted(p.connectors)
    for a in ids:
        for b in ids:
            if a != b:
                assert _proposal(links, p, a, b) == _proposal(old, p, a, b), (a, b)


@settings(max_examples=150, deadline=None)
@given(st.data())
def test_off_the_review_is_the_430_one(data: st.DataObject) -> None:
    flag = data.draw(st.sampled_from((None, False)))
    p = data.draw(projects(flag=flag))
    assert [dataclasses.astuple(f) for f in links.check_links(p)] == [
        dataclasses.astuple(f) for f in old.check_links(p)
    ]
    for x in p.links.values():
        assert [dataclasses.astuple(f) for f in links.check_link(p, x)] == [
            dataclasses.astuple(f) for f in old.check_link(p, x)
        ]


@settings(max_examples=100, deadline=None)
@given(projects(flag=True))
def test_on_no_proposed_pair_has_a_pin_of_a_third_device(p: Project) -> None:
    from harness_design_studio.core.device_names import link_reading, unit_ids

    units = unit_ids(p)
    ids = sorted(p.connectors)
    assert all(
        f.code.startswith("link_") for f in links.check_links(p)
    )  # the review reads them too
    for a in ids:
        for b in ids:
            ca, cb = p.connectors[a], p.connectors[b]
            if ca.unit_id == cb.unit_id:
                continue
            prop = links.propose_pairs(p, a, b)
            sa = {x.id: x.signal or "" for x in ca.pins}
            sb = {x.id: x.signal or "" for x in cb.pins}
            for pair in prop.pairs:
                assert link_reading(sa[pair.a_pin], ca.unit_id or "", cb.unit_id or "", units).offered  # fmt: skip
                assert link_reading(sb[pair.b_pin], cb.unit_id or "", ca.unit_id or "", units).offered  # fmt: skip
