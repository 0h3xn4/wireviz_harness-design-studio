# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-DRC-08. The rule `level-conflict` (design of 4.2.0, section 5; `core/drc/electrical.py`). The rule is
registered since pull request 4 of the design; these tests call the check and the notes directly, and
`tests/test_electrical_registered.py` has the deviation through `drc`, the line of *Start here* and
the release.

Silent while the table is not set (the tool ships no level word, D-11), with the note `levels` only
where a pin has a level; a wire, a net through a splice, a pair of a connection without a harness and
a connection with a harness (judged once, through the harness); case and outer spaces; `3V3` is not
`RS422-3V3`; the notes `no-level` and `level-unknown`; a refused table; a loose end; and the nets the
rule judges compared with `verify.splice_nets`, the verifier's own copy of the nets."""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from harness_design_studio.core import templates
from harness_design_studio.core.commands import apply_ops
from harness_design_studio.core.drc import electrical
from harness_design_studio.core.drc.base import Rule
from harness_design_studio.core.drc.rules import RULES
from harness_design_studio.core.links import plan_add_link
from harness_design_studio.core.manual_harness import plan_cable_from_port
from harness_design_studio.core.model import ConfigFile, Connector, Harness, Pin, Project, Wire
from harness_design_studio.core.verify import splice_nets
from tests.electrical_support import bare, hand_made, linked, set_pin, set_signals, spliced, titles
from tests.helpers import pinout_project


def table(p: Project, pairs: object) -> Project:
    old = p.config.get("segregation")
    values = dict(old.values) if old is not None else {}
    values["level_pairs_to_separate"] = pairs
    p.config["segregation"] = ConfigFile(name="segregation", placeholder=True, values=values)
    return p


def hits(p: Project) -> list[str]:
    return titles(electrical._level_conflict(p))


def notes(p: Project) -> dict[str, str]:
    return {h.object_id: h.title for h in electrical.unchecked(p) if not h.object_id.startswith("wire-")}  # fmt: skip


def rule() -> Rule:
    return next(r for r in electrical.ELECTRICAL_RULES if r.id == "level-conflict")


def leveled() -> tuple[Project, str]:
    """A wire from an 18V pin to an RS422-3V3 pin, and one between two RS422-3V3 pins."""
    return hand_made(
        ["RTN", "TX+"], ["TX-", "RX+"], [("1", "1"), ("2", "2")],
    )  # fmt: skip


def with_levels(p: Project) -> Project:
    set_pin(p, "OBC-J03", "1", level="18V")
    set_pin(p, "OBC-J03", "2", level="RS422-3V3")
    set_pin(p, "RW1-J02", "1", level="RS422-3V3")
    set_pin(p, "RW1-J02", "2", level="RS422-3V3")
    return p


def test_the_rule_is_registered_and_has_the_texts_of_the_design() -> None:
    assert len(RULES) == 43 and "level-conflict" in {r.id for r in RULES}
    r = rule()
    assert (r.severity, r.topic, r.can_waive, r.can_deviate, r.sources) == ("error", "Signal levels", False, True, ())  # fmt: skip
    assert r.why == "A wire that joins two signal levels the project keeps apart can damage the device on the lower level."  # fmt: skip
    assert r.how == (
        "Move the wire to a pin of a level that fits, or correct the level of the pin (Devices tab). "
        "The pairs kept apart are config/segregation.json level_pairs_to_separate."
    )


def test_silent_while_the_table_is_not_set_and_the_note_names_the_levels() -> None:
    p, _hid = leveled()
    assert hits(p) == [] and notes(p) == {}  # no level, no table: nothing to say
    with_levels(p)
    assert hits(p) == []
    assert notes(p) == {
        "levels": "Signal levels were not checked: 4 pin(s) have a level (18V, RS422-3V3), but no pairs of levels to keep apart are set (config/segregation.json: level_pairs_to_separate)"
    }  # fmt: skip
    empties: tuple[object, ...] = (None, [])
    for empty in empties:
        assert hits(table(p, empty)) == [] and set(notes(p)) == {"levels"}


def test_at_most_five_words_are_named() -> None:
    p, _hid = hand_made(["A"] * 7, [None], [("1", "1")])
    for n, word in enumerate(("5V", "3V3", "12V", "28V", "1V8", "TTL", "3v3"), start=1):
        set_pin(p, "OBC-J03", str(n), level=word)
    assert notes(p)["levels"].startswith(
        "Signal levels were not checked: 7 pin(s) have a level (12V, 1V8, 28V, 3V3, 5V and 1 more)"
    )


def test_a_wire_that_joins_two_levels_kept_apart() -> None:
    p, hid = leveled()
    table(with_levels(p), [["18V", "RS422-3V3"]])
    found = list(electrical._level_conflict(p))
    assert [h.title for h in found] == [
        f"Wire {hid}-001 in {hid} joins pin 1 of OBC-J03 (level 18V) and pin 1 of RW1-J02 (level RS422-3V3), two levels the project keeps apart"
    ]  # fmt: skip
    assert (found[0].object_id, found[0].key) == (f"{hid}-001", f"{hid}.{hid}-001.OBC-J03.1+RW1-J02.1")  # fmt: skip
    assert notes(p) == {}
    assert [f.can_deviate for f in rule().run(p)] == [True]


def test_words_are_compared_without_case_and_outer_spaces_and_no_number_is_read() -> None:
    p, hid = leveled()
    with_levels(p)
    set_pin(p, "OBC-J03", "1", level=" 18v ")
    table(p, [["18V", " rs422-3v3"]])
    assert hits(p) == [
        f"Wire {hid}-001 in {hid} joins pin 1 of OBC-J03 (level 18v) and pin 1 of RW1-J02 (level RS422-3V3), two levels the project keeps apart"
    ]  # fmt: skip
    table(p, [["18V", "3V3"]])
    assert hits(p) == []  # RS422-3V3 is not 3V3
    table(p, [["18 V", "RS422-3V3"]])
    assert hits(p) == []  # 18 V is not 18V


def test_a_net_through_a_splice_names_its_path() -> None:
    p, hid = spliced("28V", "3V3", "28V")
    table(p, [["28V", "3V3"]])
    assert hits(p) == [
        f"The wires {hid}-001 and {hid}-002 in {hid} (through splice {hid}-X1) join pin 1 of PCDU-J02 (level 28V) and pin 1 of OBC-J02 (level 3V3), two levels the project keeps apart",
        f"The wires {hid}-002 and {hid}-003 in {hid} (through splice {hid}-X1) join pin 1 of OBC-J02 (level 3V3) and pin 1 of OBC-J03 (level 28V), two levels the project keeps apart",
    ]  # fmt: skip
    found = list(electrical._level_conflict(p))
    assert {h.object_id for h in found} == {f"{hid}-001"} and len({h.key for h in found}) == 2


def test_a_connection_without_a_harness_and_one_with_a_harness_are_judged_once() -> None:
    p = pinout_project()
    for cid in ("OBC-J01", "RW1-J02"):
        p.connectors[cid] = p.connectors[cid].model_copy(update={"carries": []})
    set_pin(p, "OBC-J01", "1", level="18V")
    set_pin(p, "RW1-J02", "3", level="RS422-3V3")
    ops, lid = plan_add_link(p, "OBC-J01", "RW1-J02")
    apply_ops(p, ops)
    table(p, [["18V", "RS422-3V3"]])
    found = list(electrical._level_conflict(p))
    assert [h.title for h in found] == [
        f"Link {lid} pairs pin 1 of OBC-J01 (level 18V) with pin 3 of RW1-J02 (level RS422-3V3), two levels the project keeps apart"
    ]  # fmt: skip
    assert (found[0].object_id, found[0].key) == (lid, f"{lid}.1+3")
    p, hid = linked()
    set_pin(p, "OBC-J01", "1", level="18V")
    set_pin(p, "RW1-J02", "3", level="RS422-3V3")
    table(p, [["18V", "RS422-3V3"]])
    assert hits(p) == [
        f"Wire {hid}-001 in {hid} joins pin 1 of OBC-J01 (level 18V) and pin 3 of RW1-J02 (level RS422-3V3), two levels the project keeps apart"
    ]  # fmt: skip


def test_the_notes_with_a_table() -> None:
    p, hid = leveled()
    table(p, [["18V", "RS422-3V3"]])
    assert notes(p) == {"no-level": "No pin has a level yet, so the signal level check did not run"}
    set_pin(p, "OBC-J03", "1", level="18V")
    assert notes(p) == {
        "level-unknown": f"Signal levels were not checked for 2 net(s) (first: wire {hid}-001): a pin at an end has no level"
    }  # fmt: skip
    with_levels(p)
    assert notes(p) == {}
    q = pinout_project()
    q.harnesses.clear()
    set_pin(q, "OBC-J01", "1", level="18V")
    ops, lid = plan_add_link(q, "OBC-J01", "RW1-J02")
    apply_ops(q, ops)
    table(q, [["18V", "3V3"]])
    assert notes(q) == {
        "level-unknown": f"Signal levels were not checked for 4 pair(s) of connections (first: link {lid}): a pin at an end has no level"
    }  # fmt: skip


def test_a_refused_table_keeps_the_rule_and_its_notes_silent() -> None:
    p, _hid = leveled()
    table(with_levels(p), [["18V", "18v"]])
    assert hits(p) == [] and notes(p) == {}
    assert electrical.level_pairs(p) is None


def test_a_loose_end_is_no_device_end() -> None:
    p = bare()
    set_signals(p, "OBC-J03", ["TX+", "TX-"], levels=["28V", "3V3"])
    a = plan_cable_from_port(p, "OBC-J03", name="Loose")
    apply_ops(p, a.ops)
    table(p, [["28V", "3V3"]])
    assert hits(p) == [] and notes(p) == {}


def test_no_example_has_a_level_or_a_note(tmp_path: Path) -> None:
    for name in ("first-steps", "flatsat"):
        p = templates.create_project(tmp_path / name, name)
        assert hits(p) == [] and list(electrical.unchecked(p)) == []
        assert electrical.level_pairs(p) is None
        assert "level_pairs_to_separate" not in p.config["segregation"].values


# ---- the second statement: the nets of the verifier ---------------------------------------------

CONNECTORS = ("W9-P1", "W9-P2", "W9-P3", "W9-X1", "W9-X2")
BOXES = {"W9-P1": "D1-J1", "W9-P2": "D2-J1", "W9-P3": "D3-J1"}
PINS = ("1", "2", "3")
LEVELS = ("A", "B", "C", None)


def random_project(wires: list[tuple[int, int, int, int]], levels: list[int]) -> Project:
    p = bare()
    n = 0
    for box in BOXES.values():
        pins = []
        for pid in PINS:
            pins.append(
                Pin(id=pid, signal="S", level=LEVELS[levels[n % len(levels)] if levels else 3])
            )
            n += 1
        p.connectors[box] = Connector(id=box, name="J1", role="box", part_id="P", unit_id="OBC", pins=pins)  # fmt: skip
    conns = [
        Connector(
            id=cid, name=cid, role="splice" if "-X" in cid else "cable", part_id="P",
            mates_with=BOXES.get(cid), pins=[Pin(id=k) for k in PINS],
        )
        for cid in CONNECTORS
    ]  # fmt: skip
    out = [
        Wire(
            id=f"W9-{k:03d}",
            from_connector=CONNECTORS[a],
            from_pin=PINS[pa],
            to_connector=CONNECTORS[b],
            to_pin=PINS[pb],
        )  # fmt: skip
        for k, (a, pa, b, pb) in enumerate(wires, start=1)
        if (a, pa) != (b, pb)
    ]
    p.harnesses["W9"] = Harness(id="W9", name="random", connectors=conns, wires=out)
    return table(p, [["A", "B"]])


def expected(p: Project) -> set[frozenset[str]]:
    """The pairs of device pins with the levels A and B that one net joins, from the verifier's own
    nets (`verify.splice_nets`): its pins not on a splice, each read through the connector it is on."""
    h = p.harnesses["W9"]
    out: set[frozenset[str]] = set()
    for pins, _wires in splice_nets(h):
        ends = sorted(f"{BOXES[c]}.{pin}" for c, pin in pins if c in BOXES)
        for i, x in enumerate(ends):
            for y in ends[i + 1 :]:
                lx = p.connectors[x.split(".")[0]].pins[PINS.index(x.split(".")[1])].level
                ly = p.connectors[y.split(".")[0]].pins[PINS.index(y.split(".")[1])].level
                if {lx, ly} == {"A", "B"}:
                    out.add(frozenset((x, y)))
    return out


_WIRE = st.tuples(st.integers(0, 4), st.integers(0, 2), st.integers(0, 4), st.integers(0, 2))


@settings(max_examples=120, deadline=None)
@given(st.lists(_WIRE, max_size=12), st.lists(st.integers(0, 3), min_size=1, max_size=9))
def test_the_pairs_found_are_those_of_the_nets_of_the_verifier(wires, levels) -> None:  # type: ignore[no-untyped-def]
    p = random_project(wires, levels)
    found = {frozenset(h.key.split(".", 2)[2].split("+")) for h in electrical._level_conflict(p)}  # type: ignore[union-attr]
    assert found == expected(p)
