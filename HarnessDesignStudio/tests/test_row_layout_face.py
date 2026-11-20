# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index,union-attr"
"""REQ-PIN-06: the rule `power-return-adjacent` reads the face of a connector with a row layout
(design of 4.0.0 section 8, owner answer L1; pull request 2).

Two power or ground pins of different signals that are both in rows of the layout are judged on
the face: in one row, the free contacts between them along the row (the shorter way round a
ring); in rows next to each other, neighbours on the face (rows centred on each other: x = i +
(L - n) / 2, |x - x'| <= 1) have no contact between them. A pair with a pin in no row is judged in
the list of pins, as before; pins of different rings are not judged and `unchecked-config` lists
them. A connector without a layout gives the findings of 3.0.0, word for word: a verbatim copy of
the rule of 3.0.0 below is compared with the rule on generated projects.
"""

import copy
from collections.abc import Iterator

import pytest

from harness_design_studio.core import templates
from harness_design_studio.core.derive import explain_finding
from harness_design_studio.core.drc import RULES
from harness_design_studio.core.drc import run as run_drc
from harness_design_studio.core.drc.base import Hit, cfg, number
from harness_design_studio.core.drc.by_rule import run_by_rule
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.model import ConfigFile, Connector, Pin, Project, RowLayout, evolve
from harness_design_studio.core.row_layout import parse_text
from harness_design_studio.core.samples import mini3, sat15

CID = "OBC-J09"
RULE = next(r for r in RULES if r.id == "power-return-adjacent")


def set_gap(p: Project, gap: object) -> None:
    old = p.config["generation"]
    p.config["generation"] = ConfigFile(
        name="generation",
        placeholder=old.placeholder,
        values={**old.values, "power_return_gap_pins": gap},
    )


def face(
    power: dict[str, str],
    layout: str | None,
    *,
    pins: int = 21,
    used: tuple[str, ...] = (),
    gap: int = 1,
    part: str = "EX-MICROD-21-F",
) -> Project:
    """mini3 with a box connector OBC-J09 of `pins` pins: `power` gives pins a power signal of
    the interface IF-PWR-RW1 (two signals: two pins the rule looks at), `used` gives pins a
    signal of the RS-422 interface (assigned, not free), `layout` is the connector's own rows in
    the text form."""
    p = mini3()
    set_gap(p, gap)
    out = []
    for n in range(1, pins + 1):
        pid = str(n)
        if pid in power:
            out.append(Pin(id=pid, signal=power[pid], interface_id="IF-PWR-RW1"))
        elif pid in used:
            out.append(Pin(id=pid, signal=f"TX{pid}", interface_id="IF-TM-RW1"))
        else:
            out.append(Pin(id=pid))
    p.connectors[CID] = Connector(
        id=CID, name="J09", role="box", part_id=part, unit_id="OBC", pins=out,
        row_layout=parse_text(layout) if layout else None,
    )  # fmt: skip
    return p


def hits(p: Project, cid: str = CID) -> dict[str, str]:
    return {h.object_id: h.title for h in RULE.check(p) if h.object_id.startswith(cid + ".")}


def notes(p: Project) -> list[Hit]:
    from harness_design_studio.core.drc.standard_rules import unchecked

    return [h for h in unchecked(p) if h.object_id == "power-return-rings"]


# ---- neighbours across rows ------------------------------------------------------------------


def test_the_micro_d_21_warns_for_1_and_12_and_not_for_11_and_12() -> None:
    p = face({"1": "PWR", "12": "RTN"}, "1–11 / 12–21")
    assert hits(p) == {
        f"{CID}.1+12": f"{CID}: PWR (pin 1) and RTN (pin 12) are neighbours on the face of the "
        "connector (rows 1 and 2), with no unassigned contact between them"
    }
    assert hits(face({"1": "PWR", "12": "RTN"}, None)) == {}  # ten free contacts in the list
    assert hits(face({"11": "PWR", "12": "RTN"}, "1–11 / 12–21")) == {}  # far apart on the face
    assert list(hits(face({"11": "PWR", "12": "RTN"}, None))) == [f"{CID}.11+12"]


@pytest.mark.parametrize(
    ("a", "b", "near"),
    [("12", "2", True), ("21", "10", True), ("21", "11", True), ("21", "9", False),
     ("12", "3", False), ("13", "2", True), ("13", "3", True), ("13", "4", False)],
)  # fmt: skip
def test_the_staggered_rows_of_the_micro_d_21(a: str, b: str, near: bool) -> None:
    """Pin 12 sits at x = 0.5 between pins 1 and 2; pin 21 at x = 9.5 between pins 10 and 11."""
    found = hits(face({a: "PWR", b: "RTN"}, "1–11 / 12–21"))
    assert bool(found) is near, found


@pytest.mark.parametrize(
    ("a", "b", "near"),
    [("6", "1", True), ("6", "2", True), ("6", "3", False), ("9", "4", True), ("9", "5", True),
     ("9", "3", False), ("5", "6", False)],
)  # fmt: skip
def test_the_d_sub_9(a: str, b: str, near: bool) -> None:
    found = hits(face({a: "PWR", b: "RTN"}, "1–5 / 6–9", pins=9, part="EX-MICROD-9-F"))
    assert bool(found) is near, found


@pytest.mark.parametrize(
    ("a", "b", "near"),
    [("5", "2", True), ("5", "1", True), ("5", "3", True), ("1", "6", False), ("1", "7", False),
     ("4", "8", True), ("4", "9", False)],
)  # fmt: skip
def test_three_rows_of_equal_length_take_the_pin_across_and_both_diagonals(
    a: str, b: str, near: bool
) -> None:
    found = hits(face({a: "PWR", b: "RTN"}, "1–3 / 4–6 / 7–9", pins=9, part="EX-MICROD-9-F"))
    assert bool(found) is near, found


def test_rows_two_apart_are_not_neighbours_and_the_list_is_not_read_for_them() -> None:
    p = face({"3": "PWR", "4": "RTN"}, "1 3 5 7 9 / 2 4 6 8 10 / 11–15", pins=15)  # odd and even
    assert list(hits(p)) == [f"{CID}.3+4"]  # straight across: 3 at x = 1, 4 at x = 1
    assert hits(face({"1": "PWR", "11": "RTN"}, "1–5 / 6–10 / 11–15", pins=15)) == {}
    assert hits(face({"5": "PWR", "6": "RTN"}, "1–5 / 6–10 / 11–15", pins=15)) == {}


# ---- along a row, round a ring ---------------------------------------------------------------


def test_a_gap_of_2_is_counted_along_a_row() -> None:
    layout = "1–11 / 12–21"
    found = hits(face({"1": "PWR", "3": "RTN"}, layout, gap=2))
    assert found == {
        f"{CID}.1+3": f"{CID}: PWR (pin 1) and RTN (pin 3) have 1 unassigned contact(s) between "
        "them along row 1 of the face, fewer than the 2 required"
    }
    assert hits(face({"1": "PWR", "3": "RTN"}, layout, gap=1)) == {}
    assert list(hits(face({"1": "PWR", "3": "RTN"}, layout, used=("2",), gap=1))) == [f"{CID}.1+3"]
    assert hits(face({"1": "PWR", "4": "RTN"}, layout, gap=2)) == {}  # two between: enough


def test_the_order_along_a_row_is_the_order_of_the_layout_not_of_the_list() -> None:
    p = face({"1": "PWR", "2": "RTN"}, "1 3 2 / 4–9", pins=9, part="EX-MICROD-9-F")
    assert hits(p) == {}  # pin 3 (free) is between them in the row
    q = face({"1": "PWR", "3": "RTN"}, "1 3 2 / 4–9", pins=9, part="EX-MICROD-9-F")
    assert list(hits(q)) == [f"{CID}.1+3"]


def test_the_last_pin_of_a_ring_is_next_to_its_first() -> None:
    p = face({"1": "PWR", "8": "RTN"}, "1–8 (rings)", pins=9, part="EX-MICROD-9-F")
    assert hits(p) == {
        f"{CID}.1+8": f"{CID}: PWR (pin 1) and RTN (pin 8) have 0 unassigned contact(s) between "
        "them along ring 1 of the face, fewer than the 1 required"
    }
    assert notes(p) == []  # one ring: nothing left unjudged
    rows = face({"1": "PWR", "8": "RTN"}, "1–8", pins=9, part="EX-MICROD-9-F")
    assert hits(rows) == {}  # a row is not a ring
    shorter = face({"1": "PWR", "7": "RTN"}, "1–8 (rings)", pins=9, part="EX-MICROD-9-F", gap=2)
    assert "1 unassigned contact(s)" in hits(shorter)[f"{CID}.1+7"]  # the way round by pin 8


def test_pins_of_two_rings_are_not_judged_and_unchecked_config_lists_them() -> None:
    p = face({"1": "PWR", "9": "RTN", "10": "RTN"}, "1–8 / 9–12 (rings)", pins=12)
    assert hits(p) == {}  # the list pair 9+10 is one signal, 1+9 is across the rings
    (note,) = notes(p)
    assert note.key == f"power-return-rings.{CID}"
    assert note.title == (
        f"{CID}: power and return pins of different rings of a circular insert were not checked "
        "(pins 1 and 9, 1 and 10): the row layout does not say which contacts of two rings face "
        "each other"
    )
    result = next(r for r in run_by_rule(p) if r.rule_id == "power-return-adjacent")
    assert note.title in result.notes
    unchecked = [
        f
        for f in run_drc(p)
        if f.rule == "unchecked-config" and f.object_id == "power-return-rings"
    ]
    assert [f.title for f in unchecked] == [note.title]
    set_gap(p, None)
    assert notes(p) == []  # the rule is silent: its setting is what is reported


# ---- a pin in no row, a mated cable connector ------------------------------------------------


def test_a_pin_in_no_row_is_judged_in_the_list_of_pins() -> None:
    p = face({"5": "PWR", "6": "RTN"}, "1–5", pins=9, part="EX-MICROD-9-F")
    assert hits(p) == {
        f"{CID}.5+6": f"{CID}: PWR (pin 5) and RTN (pin 6) have 0 unassigned contact(s) between "
        "them, fewer than the 1 required"
    }
    assert list(hits(face({"7": "PWR", "8": "RTN"}, "1–5", pins=9, part="EX-MICROD-9-F"))) == [
        f"{CID}.7+8"
    ]


def test_list_and_face_findings_come_in_the_order_of_the_list() -> None:
    p = face({"2": "PWR", "12": "RTN", "20": "PWR", "21": "RTN"}, "1–11 / 12–19", pins=21)
    assert list(hits(p)) == [f"{CID}.2+12", f"{CID}.20+21"]  # face, then list (20, 21 in no row)
    assert hits(face({"1": "PWR", "12": "RTN"}, "1–11 / 12–19")) == {}  # 12 at x = 1.5, 1 at 0


def test_a_cable_connector_is_judged_on_the_rows_of_the_box_connector_it_plugs_into() -> None:
    p = mini3()
    set_gap(p, 1)
    box = p.connectors["PCDU-J01"]  # pins 1 PWR, 2 RTN, 3 free; W001-P1 plugs into it
    h = p.harnesses["W001"]
    plug = next(c for c in h.connectors if c.id == "W001-P1")
    pins = [evolve(x, interface_id="IF-PWR-RW1") if x.signal else x for x in plug.pins]
    p.harnesses["W001"] = evolve(
        h, connectors=[evolve(plug, pins=pins) if c is plug else c for c in h.connectors]
    )
    assert set(hits(p, "W001-P1")) == {"W001-P1.1+2"}
    p.connectors[box.id] = evolve(box, row_layout=RowLayout(rows=[["1", "3", "2"]]))
    assert hits(p, "W001-P1") == {} and hits(p, "PCDU-J01") == {}


# ---- the derivation agrees with the rule -----------------------------------------------------


@pytest.mark.parametrize(
    ("power", "layout", "fails", "actual"),
    [({"1": "PWR", "12": "RTN"}, "1–11 / 12–21", True, 0),
     ({"1": "PWR", "3": "RTN"}, "1–11 / 12–21", False, 1),
     ({"5": "PWR", "6": "RTN"}, "1–5 / 6–10", False, None),
     ({"1": "PWR", "13": "RTN"}, "1–8 / 9–21 (rings)", False, None)],
)  # fmt: skip
def test_the_derivation_gives_the_verdict_of_the_rule(power, layout, fails, actual) -> None:
    p = face(power, layout)
    a, b = sorted(power, key=int)
    oid = f"{CID}.{a}+{b}"
    (d,) = explain_finding(p, "power-return-adjacent", oid)
    assert (oid in hits(p)) is fails
    if actual is None:
        assert d.check is None and any(s.label == "Not judged" for s in d.steps)
    else:
        assert d.check is not None and d.check.actual == actual and d.check.passes is not fails
    assert d.assumptions == ("A-RETURN-GAP",)


# ---- a project without a layout gives the findings of 3.0.0 ----------------------------------


def _rule_of_300(project: Project) -> Iterator[Hit]:
    """`_adjacent_power_return` and `_power_pairs` of 3.0.0, word for word (do not edit)."""
    gap = number(cfg(project, "generation").get("power_return_gap_pins"))
    if gap is None or not 1 <= gap <= 1000:  # also rules out nan and inf
        return
    for conn in sorted(project.connectors.values(), key=lambda x: x.id):
        yield from _pairs_of_300(project, conn, int(gap))
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        for c in h.connectors:
            yield from _pairs_of_300(project, c, int(gap))


def _pairs_of_300(project: Project, conn: Connector, gap: int) -> Iterator[Hit]:
    order = list(conn.pins)

    def is_power(k: int) -> bool:
        i = project.interfaces.get(order[k].interface_id or "")
        itype = project.interface_types.get(i.type_id) if i else None
        return itype is not None and itype.category in ("power", "ground")

    for k, p in enumerate(order):
        if not p.signal or not is_power(k):
            continue
        for m in range(k + 1, min(k + 2 + gap, len(order))):
            q = order[m]
            if not q.signal or q.signal == p.signal or not is_power(m):
                continue
            free = sum(1 for x in order[k + 1 : m] if x.interface_id is None and not x.signal)
            if free < gap:
                yield Hit(
                    f"{conn.id}.{p.id}+{q.id}",
                    f"{conn.id}: {p.signal} (pin {p.id}) and {q.signal} (pin {q.id}) have {free} unassigned contact(s) between them, fewer than the {gap} required",
                )


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> list[Project]:
    out = [mini3()]
    s = sat15()
    generate_project(s)
    out.append(s)
    for name in ("flatsat", "first-steps"):
        p = templates.create_project(tmp_path_factory.mktemp(name) / name, name)
        if not p.harnesses:
            generate_project(p)
        out.append(p)
    return out


@pytest.mark.parametrize("gap", [None, 1, 2, 3, 1.5, 0])
def test_a_project_without_a_layout_gives_the_findings_of_300(generated, gap) -> None:
    for base in generated:
        p = copy.copy(base)
        p.config = dict(base.config)
        set_gap(p, gap)
        assert list(RULE.check(p)) == list(_rule_of_300(p)), base.meta.name
        assert notes(p) == []
