# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The harness plan of a harness with splices (REQ-OUT-01, REQ-VER-02; D-242, pull request 6 of
`docs/ait/DESIGN_3.0_HARNESS_PLAN.md`, section 9 and the "Branching" bullet of section 11): the sides
rule through splices, a Y harness through a splice, a row that reaches two far connectors and a row
that reaches two pins of one far connector, a ring of three connectors, a harness of one connector,
a splice on a branch point's leg; every wire in exactly one row, by the plan and by the verifier;
every formula's stored value against the tests' own evaluator; the verifier's findings on the plans
as written and on the mutations that matter for splices; and, with LibreOffice installed, the values
a real reader shows. All data here is fictitious."""

import re
from functools import partial
from pathlib import Path

import pytest
from hypothesis import given

from harness_design_studio.core.model import (
    Connector,
    Endpoint,
    Harness,
    InterfaceInstance,
    Pin,
    Project,
    Unit,
    Wire,
)
from harness_design_studio.core.outputs import harness_plan as hp
from harness_design_studio.core.outputs import verify_plan as vp
from harness_design_studio.core.outputs.stamp import stamp_of
from harness_design_studio.core.samples import new_project
from harness_design_studio.core.verify import VerifyReport
from tests.plan_support import (
    PlanCell,
    Sheets,
    check_values,
    golden_project,
    parse_address,
    read_plan,
)
from tests.splice_support import SPLICE_PART, splice_part
from tests.test_harness_plan import SOFFICE, f, libreoffice_check, row_of, v
from tests.test_verify_plan import _SETTINGS, has, once, projects, table, with_content

TO_FILL = "to fill in"
WIRE_PART = "EX-WIRE-SINGLE"


# ---- small projects -----------------------------------------------------------------------------


def _box(unit: str, pins: list[Pin]) -> Connector:
    return Connector(
        id=f"{unit}-J1", name="J1", role="box", part_id="EX-MICROD-9-F", unit_id=unit,
        gender="female", pins=pins,
    )  # fmt: skip


def _plug(hid: str, n: int, box: str | None, pins: int = 4, role: str = "cable") -> Connector:
    return Connector(
        id=f"{hid}-P{n}", name=f"P{n}", role=role, part_id="EX-MICROD-9-M",  # type: ignore[arg-type]
        mates_with=box, pins=[Pin(id=str(k)) for k in range(1, pins + 1)],
    )  # fmt: skip


def _splice(hid: str, n: int, nodes: int = 1) -> Connector:
    return Connector(
        id=f"{hid}-X{n}", name=f"X{n}", role="splice", part_id=SPLICE_PART,
        pins=[Pin(id=str(k), termination="crimp") for k in range(1, nodes + 1)],
    )  # fmt: skip


def _wire(hid: str, n: int, a: str, b: str, **kw: object) -> Wire:
    """A wire from `a` to `b`, each `connector.pin`."""
    (fc, fp), (tc, tp) = a.rsplit(".", 1), b.rsplit(".", 1)
    return Wire(
        id=f"{hid}-{n:03d}", from_connector=fc, from_pin=fp, to_connector=tc, to_pin=tp,
        **kw,  # type: ignore[arg-type]
    )  # fmt: skip


def _project(name: str, boxes: dict[str, list[Pin]]) -> Project:
    p = new_project(name)
    p.parts[SPLICE_PART] = splice_part()
    for unit, pins in boxes.items():
        p.units[unit] = Unit(id=unit, name=unit, subsystem="s")
        p.connectors[f"{unit}-J1"] = _box(unit, pins)
    return p


def y_project() -> Project:
    """Four devices A to D; W001 with the plugs P1 to P4 on A-J1 to D-J1 and the splices X1, X2:
    A pin 1 (power) through X1 to C pin 1 and D pin 1, a row that reaches two far connectors;
    A pin 2 (out) through X2 to C pins 3 and 4, a row that reaches two pins of one far connector;
    B pin 1 to C pin 2 and B pin 2 to D pin 2, straight. Every wire has a part and a length."""
    p = _project(
        "Splice plan test",
        {
            "A": [Pin(id="1", signal="PWR_28V", role="power"), Pin(id="2", signal="CLK", direction="out")],
            "B": [Pin(id="1", signal="TX", direction="out"), Pin(id="2", signal="RTN", role="return")],
            "C": [
                Pin(id="1", signal="PWR_28V", role="power"), Pin(id="2", signal="RX", direction="in"),
                Pin(id="3", signal="CLK_A", direction="in", level="LVDS"),
                Pin(id="4", signal="CLK_B", direction="in", function="Second clock input"),
            ],
            "D": [Pin(id="1", signal="PWR_28V", role="power"), Pin(id="2", signal="RTN", role="return")],
        },
    )  # fmt: skip
    p.interfaces["IF-1"] = InterfaceInstance(
        id="IF-1", name="Power and clock", type_id="power",
        endpoints=[Endpoint(unit_id=u, connector_id=f"{u}-J1") for u in "ABCD"],
    )  # fmt: skip
    h = "W001"
    lengths = iter((0.5, 1.0, 1.25, 0.25, 0.75, 0.8, 2.0, 2.5))
    pairs = [
        ("W001-P1.1", "W001-X1.1", "red"), ("W001-X1.1", "W001-P3.1", "red"),
        ("W001-X1.1", "W001-P4.1", "orange"), ("W001-P1.2", "W001-X2.1", "white"),
        ("W001-X2.1", "W001-P3.3", "blue"), ("W001-X2.1", "W001-P3.4", "green"),
        ("W001-P2.1", "W001-P3.2", "yellow"), ("W001-P2.2", "W001-P4.2", "black"),
    ]  # fmt: skip
    p.harnesses[h] = Harness(
        id=h, name="Y through splices",
        connectors=[*(_plug(h, n, f"{u}-J1") for n, u in enumerate("ABCD", start=1)), _splice(h, 1), _splice(h, 2)],
        wires=[
            _wire(h, n, a, b, colour=c, part_id=WIRE_PART, gauge_awg=24, length_m=next(lengths))
            for n, (a, b, c) in enumerate(pairs, start=1)
        ],
    )  # fmt: skip
    return p


def ring_project() -> Project:
    """Three inline connectors in a ring, one side through a splice: P1 pin 1 through X1 to P2
    pin 1, P2 pin 2 to P3 pin 2, P3 pin 3 to P1 pin 3."""
    p = _project("Splice ring", {})
    h = "W001"
    p.harnesses[h] = Harness(
        id=h, name="ring",
        connectors=[*(_plug(h, n, None, role="inline") for n in (1, 2, 3)), _splice(h, 1)],
        wires=[
            _wire(h, 1, "W001-P1.1", "W001-X1.1"), _wire(h, 2, "W001-X1.1", "W001-P2.1"),
            _wire(h, 3, "W001-P2.2", "W001-P3.2"), _wire(h, 4, "W001-P3.3", "W001-P1.3"),
        ],
    )  # fmt: skip
    return p


def one_connector_project() -> Project:
    """A harness of one plug on A-J1: its pin 1 through the splice X1 to its pins 2 and 3."""
    p = _project(
        "One connector",
        {"A": [Pin(id="1", signal="PWR"), Pin(id="2", signal="PWR"), Pin(id="3", signal="PWR")]},
    )
    h = "W001"
    p.harnesses[h] = Harness(
        id=h, name="jumper",
        connectors=[_plug(h, 1, "A-J1", pins=3), _splice(h, 1)],
        wires=[
            _wire(h, 1, "W001-P1.1", "W001-X1.1", length_m=0.1),
            _wire(h, 2, "W001-X1.1", "W001-P1.2", length_m=0.1),
            _wire(h, 3, "W001-X1.1", "W001-P1.3"),
        ],
    )  # fmt: skip
    return p


# ---- helpers -------------------------------------------------------------------------------------


def sheets(p: Project, hid: str = "W001") -> Sheets:
    return read_plan(hp.plan_ods(p, p.harnesses[hid], stamp_of(p)))


def harness_sheet(p: Project, hid: str = "W001") -> dict[tuple[int, int], PlanCell]:
    return sheets(p, hid)[hp.harness_sheet_name(p.harnesses[hid])]


def further(cells: dict[tuple[int, int], PlanCell], h: Harness) -> list[str]:
    """The wire IDs under *Further wires*, in their order."""
    col = parse_address("H1")[1]
    return [
        str(x.value)
        for (_r, c), x in sorted(cells.items())
        if c == col and x.value in {w.id for w in h.wires}
    ]


def wire_rows(cells: dict[tuple[int, int], PlanCell]) -> int:
    """The rows that hold a wire: every row between the part tables and the sums whose Cable /
    Type (`L`) holds a value, the headings left out."""
    col_l = parse_address("L1")[1]
    top = row_of(cells, "H", "used Backshells")
    bottom = row_of(cells, "H", "Sum of length of cable type [mm]")
    return len(
        [
            1
            for (r, c), x in cells.items()
            if c == col_l and top <= r < bottom - 1 and x.value not in ("", "Cable / Type")
        ]
    )


def verifier_rows(p: Project, hid: str = "W001") -> list[str]:
    """The wire of each row the verifier expects, by ID."""
    want = vp.expected_plan(p, p.harnesses[hid], stamp_of(p), False)
    return [what.split()[1] for what in want.rows.values() if what.startswith("wire ")]


def plan_errors(p: Project, data: bytes, hid: str = "W001") -> list[tuple[str, str]]:
    r = VerifyReport()
    vp.check_plan(r, p, p.harnesses[hid], f"harnesses/{hid}/{hid}_plan.ods", data, False)
    return [(i.code, i.message) for i in r.errors]


def each_wire_once(p: Project, hid: str = "W001") -> None:
    h = p.harnesses[hid]
    assert wire_rows(harness_sheet(p, hid)) == len(h.wires), hid
    assert sorted(verifier_rows(p, hid)) == sorted(w.id for w in h.wires), hid


# ---- the sides rule (section 9, step 1) ---------------------------------------------------------


def _sides(p: Project, hid: str = "W001") -> tuple[list[str], list[str]]:
    s = hp.plan_sides(p.harnesses[hid])
    near, far = vp.plan_sides(p.harnesses[hid])
    assert ([c.id for c in near], [c.id for c in far]) == (
        [c.id for c in s.near],
        [c.id for c in s.far],
    )
    return [c.id for c in s.near], [c.id for c in s.far]


def test_the_sides_rule_joins_two_connectors_through_splices_and_leaves_the_splices_out() -> None:
    assert _sides(y_project()) == (["W001-P1", "W001-P2"], ["W001-P3", "W001-P4"])
    # the Y of the splice fixture: one net reaches all three plugs, so the two branches are near
    assert _sides(golden_project("splices"), "W003") == (["W003-P2", "W003-P3"], ["W003-P1"])
    assert _sides(ring_project()) == (["W001-P2", "W001-P3"], ["W001-P1"])
    assert _sides(one_connector_project()) == (["W001-P1"], [])


# ---- the rows ------------------------------------------------------------------------------------


def test_a_row_that_reaches_two_far_connectors_fills_a_pin_in_each_column() -> None:
    p = y_project()
    s = sheets(p)
    cells = s["W001"]
    assert v(cells, "H8") == "Harness Splice plan test-W001: A + B <–> C + D"
    r = row_of(cells, "B", 1, after=row_of(cells, "B", "Pin No."))  # A-J1 pin 1
    assert [v(cells, f"{c}{r}") for c in "HKLN"] == [1, "red", 1, 500]
    assert (v(cells, f"T{r}"), v(cells, f"U{r}")) == (1, 1)
    # the far wires W001-002 (to C) and W001-003 (to D), in column order, as values
    assert [v(cells, f"{c}{r}") for c in "PQRS"] == [
        "1 + 1",
        "red + orange",
        "PWR + PWR",
        "PWR_28V + PWR_28V",
    ]
    assert not [c for c in "PQRS" if f(cells, f"{c}{r}")]
    # each far device side holds its one pin as the template has it
    assert v(cells, f"W{r}") == 1 and f(cells, f"X{r}") == "[$'CON_C-J1'.B19]"
    assert v(cells, f"AD{r}") == 1 and f(cells, f"AE{r}") == "[$'CON_D-J1'.B19]"
    assert check_values(s) == []


def test_two_pins_of_one_far_connector_are_joined_by_a_plus() -> None:
    p = y_project()
    cells = sheets(p)["W001"]
    r = row_of(cells, "B", 2, after=row_of(cells, "B", "Pin No."))  # A-J1 pin 2
    assert (v(cells, f"T{r}"), v(cells, f"U{r}")) == ("3 + 4", None)
    assert [v(cells, f"{c}{r}") for c in "PQRS"] == [
        "1 + 1",
        "blue + green",
        "OUT + OUT",
        "CLK_A + CLK_B",
    ]
    # the far device side of C lists both pins' values; an empty value keeps its place
    assert [v(cells, f"{c}{r}") for c in ("W", "X", "Y", "Z", "AA")] == [
        "3 + 4", "CLK_A + CLK_B", "IN + IN", "LVDS + ", " + Second clock input",
    ]  # fmt: skip
    assert not f(cells, f"W{r}") and v(cells, f"AD{r}") is None


def test_a_straight_row_beside_them_keeps_its_formulas() -> None:
    cells = sheets(y_project())["W001"]
    r = row_of(cells, "B", "Data from CON_B-J1") + 2  # B-J1 pin 1: B.1 to C.2
    assert v(cells, f"H{r}") == 1 and v(cells, f"T{r}") == 2 and v(cells, f"U{r}") is None
    assert f(cells, f"P{r}") == f"[.L{r}]"
    assert v(cells, f"R{r}") == "OUT" and f(cells, f"R{r}").startswith("IF([$'CON_C-J1'.C20]")


def test_wires_beyond_a_splice_are_further_wires_and_the_sums_count_both_blocks() -> None:
    p = y_project()
    s = sheets(p)
    cells = s["W001"]
    h = p.harnesses["W001"]
    assert further(cells, h) == ["W001-002", "W001-003", "W001-005", "W001-006"]
    top = row_of(cells, "H", "Further wires")
    assert [v(cells, f"{c}{top + 2}") for c in "HIJKLN"] == [
        "W001-002", "W001-X1.1", "W001-P3.1", "red", 1, 1000,
    ]  # fmt: skip
    total = row_of(cells, "H", "Sum of length of cable type [mm]") + 2
    assert v(cells, f"N{total}") == 9050  # every wire of the harness, both blocks
    assert f(cells, f"N{total}").count("SUMIF") == 3  # the two near blocks and the further wires
    each_wire_once(p)
    assert check_values(s) == []


def test_a_y_harness_through_a_splice_a_row_reaches_its_far_pin_through_the_splice() -> None:
    p = golden_project("splices")
    s = sheets(p, "W003")
    cells = s["W003"]
    h = p.harnesses["W003"]
    assert v(cells, "H8") == "Harness mini3 (example data)-W003: OBC + OBC <–> PCDU"
    r = row_of(cells, "B", "Data from CON_OBC-J02") + 2  # OBC-J02 pin 1: W003-002 to W003-X1
    assert [v(cells, f"{c}{r}") for c in "HKNT"] == [1, "red", 1000, 1]
    # one far pin through a splice: the far wire W003-001's values; the far pin's own cells copied
    assert (v(cells, f"P{r}"), f(cells, f"P{r}")) == (TO_FILL, "")
    assert v(cells, f"S{r}") == "PWR" and f(cells, f"S{r}") == "[$'CON_PCDU-J02'.B19]"
    assert further(cells, h) == ["W003-001", "W003-004"]
    each_wire_once(p, "W003")
    assert check_values(s) == []


def test_a_splice_on_a_branch_points_leg() -> None:
    p = golden_project("splices")
    s = sheets(p, "W004")
    cells = s["W004"]
    h = p.harnesses["W004"]
    assert _sides(p, "W004") == (["W004-P2", "W004-P3"], ["W004-P1"])
    # the inline connector's pin 1 reaches PCDU-J03 pin 1 through the splice on the leg (the far
    # wire W004-001 has no part: to fill in, as a value); its pin 2 is straight
    r = row_of(cells, "B", "W004-P2") + 6
    assert [v(cells, f"{c}{r}") for c in "HIT"] == [1, "SIG", 1]
    assert (v(cells, f"P{r}"), f(cells, f"P{r}")) == (TO_FILL, "")
    assert v(cells, f"T{r + 1}") == 2 and f(cells, f"P{r + 1}") == f"[.L{r + 1}]"
    assert further(cells, h) == ["W004-001"]
    top = row_of(cells, "H", "Further wires")
    assert [v(cells, f"{c}{top + 2}") for c in "HIJN"] == [
        "W004-001",
        "W004-P1.1",
        "W004-X1.1",
        500,
    ]
    each_wire_once(p, "W004")
    assert check_values(s) == []


def test_a_ring_of_three_connectors_through_a_splice() -> None:
    p = ring_project()
    s = sheets(p)
    cells = s["W001"]
    assert further(cells, p.harnesses["W001"]) == ["W001-001", "W001-003"]
    first = row_of(cells, "H", "Pinout") + 1  # P2 pin 1: W001-002 to X1, reaches P1 pin 1
    assert [v(cells, f"{c}{first}") for c in "HT"] == [1, 1]
    each_wire_once(p)
    assert check_values(s) == []


def test_a_harness_of_one_connector_lists_every_wire_under_further_wires() -> None:
    p = one_connector_project()
    s = sheets(p)
    cells = s["W001"]
    assert v(cells, "H8") == "Harness One connector-W001: A"
    assert further(cells, p.harnesses["W001"]) == ["W001-001", "W001-002", "W001-003"]
    total = row_of(cells, "H", "Sum of length of cable type [mm]")
    assert v(cells, f"H{total + 2}") is None  # no wire has a part
    each_wire_once(p)
    assert check_values(s) == []


@_SETTINGS
@given(projects())
def test_every_wire_is_in_exactly_one_row_of_a_random_plan(p: Project) -> None:
    each_wire_once(p)


# ---- the verifier --------------------------------------------------------------------------------

SPLICE_PLANS = [
    (y_project, "W001"),
    (ring_project, "W001"),
    (one_connector_project, "W001"),
    (partial(golden_project, "splices"), "W003"),
    (partial(golden_project, "splices"), "W004"),
]


@pytest.mark.parametrize(("make", "hid"), SPLICE_PLANS)
def test_the_verifier_finds_no_error_in_a_splice_plan_as_written(make: object, hid: str) -> None:
    p = make()  # type: ignore[operator]
    assert plan_errors(p, hp.plan_ods(p, p.harnesses[hid], stamp_of(p)), hid) == []


def _row_with(text: str, sheet: str, value: str) -> str:
    """The XML of the first row of a sheet that holds a text cell `value`."""
    for m in re.finditer(r"<table:table-row>.*?</table:table-row>", table(text, sheet).group()):
        if f"<text:p>{value}</text:p>" in m.group():
            return m.group()
    raise AssertionError(value)


def test_a_wire_beyond_a_splice_dropped_is_found() -> None:
    p = y_project()
    data = hp.plan_ods(p, p.harnesses["W001"], stamp_of(p))

    def drop(t: str) -> str:
        return t.replace(_row_with(t, "W001", "W001-005"), "", 1)

    found = plan_errors(p, with_content(data, drop))
    assert has(found, "out_plan", "the row of wire W001-005")


def test_a_far_pin_missing_is_found() -> None:
    p = y_project()
    data = hp.plan_ods(p, p.harnesses["W001"], stamp_of(p))
    found = plan_errors(p, with_content(data, once("<text:p>3 + 4</text:p>", "<text:p>3</text:p>")))
    assert has(found, "out_plan", "the design gives '3 + 4'")


# ---- a real reader -------------------------------------------------------------------------------


@pytest.mark.skipif(SOFFICE is None, reason="LibreOffice (soffice) is not installed")
def test_libreoffice_shows_the_stored_values_of_a_splice_plan(tmp_path: Path) -> None:
    p = y_project()
    assert libreoffice_check(tmp_path, hp.plan_ods(p, p.harnesses["W001"], stamp_of(p))) > 40
