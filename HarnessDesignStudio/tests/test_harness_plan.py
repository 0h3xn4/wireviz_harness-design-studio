# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The harness plan, one `.ods` per harness in the users' layout (REQ-OUT-01; D-242, pull request 3
of `docs/ait/DESIGN_3.0_HARNESS_PLAN.md`, sections 3, 6, 7, 9 and 10; the "Layout" bullet of
section 11). Each region of section 3 on small projects; the Direction words and the mirrored
directions; the colour rule both ways; the yellow rows and `[no SGND*]`; the sums; the register;
a released harness, a loose end, an empty document; the `CON_…` sheet of a box connector the same
in two plans; the example colour code; every formula's stored value against the tests' own
evaluator (`tests/plan_support.py`); the bytes; the goldens; and, with LibreOffice installed, the
values a real reader shows. Document data here is placeholder text only."""

import csv
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from harness_design_studio.core import configcheck, templates
from harness_design_studio.core.generation_status import input_hash
from harness_design_studio.core.model import (
    Accessory,
    ChangeEntry,
    ConfigFile,
    Connector,
    ContactLine,
    DocumentInfo,
    Endpoint,
    Harness,
    InterfaceInstance,
    Pin,
    PlanDocument,
    Project,
    ShieldGroup,
    Unit,
    Wire,
    evolve,
)
from harness_design_studio.core.outputs import harness_plan as hp
from harness_design_studio.core.outputs.build import build_outputs
from harness_design_studio.core.outputs.ods import check_formula
from harness_design_studio.core.outputs.stamp import stamp_of
from harness_design_studio.core.samples import new_project, start_project
from tests.helpers import FIXTURES
from tests.plan_support import (
    GOLDEN_PROJECTS,
    READABLE,
    Evaluator,
    PlanCell,
    Sheets,
    address,
    check_values,
    find,
    golden_files,
    golden_project,
    parse_address,
    read_plan,
    shown_texts,
)

GOLDEN = FIXTURES / "outputs" / "harness_plan"
TO_FILL = "to fill in"


# ---- small projects ---------------------------------------------------------------------------


def _box(unit: str, pins: list[Pin], part: str = "EX-MICROD-9-F") -> Connector:
    return Connector(
        id=f"{unit}-J1", name="J1", role="box", part_id=part, unit_id=unit, gender="female",
        pins=pins,
    )  # fmt: skip


def _plug(hid: str, n: int, box: str | None, pins: int = 9, **kw: object) -> Connector:
    return Connector(
        id=f"{hid}-P{n}", name=f"P{n}", role=kw.pop("role", "cable"),  # type: ignore[arg-type]
        part_id=kw.pop("part_id", "EX-MICROD-9-M"),  # type: ignore[arg-type]
        mates_with=box, pins=[Pin(id=str(k)) for k in range(1, pins + 1)], **kw,  # type: ignore[arg-type]
    )  # fmt: skip


def _wire(hid: str, n: int, a: tuple[str, str], b: tuple[str, str], **kw: object) -> Wire:
    return Wire(
        id=f"{hid}-{n:03d}", from_connector=a[0], from_pin=a[1], to_connector=b[0], to_pin=b[1],
        **kw,  # type: ignore[arg-type]
    )  # fmt: skip


def straight() -> Project:
    """Two devices A and B; W001 from A-J1 to B-J1 with three wires: A pin 1 (PWR, a level, a
    description) to B pin 1, A pin 2 (out) to B pin 3 (in), A pin 3 (SGND) to B pin 2 (in); A pins
    4 and 5 have no wire. One pair part (two wires), one single wire without a length."""
    p = new_project("Plan test")
    for u in ("A", "B"):
        p.units[u] = Unit(id=u, name=u, subsystem="s")
    p.connectors["A-J1"] = _box("A", [
        Pin(id="1", signal="PWR_28V", role="power", level="28V", function="Supply"),
        Pin(id="2", signal="TX", direction="out", level="RS422-3V3"),
        Pin(id="3", signal="SGND", role="signal_ground"),
        Pin(id="4", signal="SPARE1", role="spare"),
        Pin(id="5"),
    ])  # fmt: skip
    p.connectors["B-J1"] = _box("B", [
        Pin(id="1", signal="PWR_28V", role="power"),
        Pin(id="2", signal="SGND_IN", direction="in"),
        Pin(id="3", signal="RX", direction="in"),
    ])  # fmt: skip
    p.interfaces["IF-1"] = InterfaceInstance(
        id="IF-1", name="Data A to B", type_id="rs422",
        endpoints=[Endpoint(unit_id="A", connector_id="A-J1"), Endpoint(unit_id="B", connector_id="B-J1")],
    )  # fmt: skip
    h = "W001"
    p.harnesses[h] = Harness(
        id=h, name="A to B",
        connectors=[_plug(h, 1, "A-J1"), _plug(h, 2, "B-J1")],
        wires=[
            _wire(h, 1, ("W001-P1", "1"), ("W001-P2", "1"), part_id="EX-WIRE-TWISTED-SHIELDED",
                  length_m=1.25, colour="red", gauge_awg=24),
            _wire(h, 2, ("W001-P1", "2"), ("W001-P2", "3"), part_id="EX-WIRE-TWISTED-SHIELDED",
                  length_m=1.5, colour="white", gauge_awg=24),
            _wire(h, 3, ("W001-P2", "2"), ("W001-P1", "3"), part_id="EX-WIRE-SINGLE", colour="black"),
        ],
        shields=[ShieldGroup(id="W001-S1", kind="twisted_pair", wire_ids=["W001-001", "W001-002"])],
    )  # fmt: skip
    return p


def plan(p: Project, hid: str = "W001", drawings: bool = False) -> bytes:
    return hp.plan_ods(p, p.harnesses[hid], stamp_of(p), drawings=drawings)


def sheets(p: Project, hid: str = "W001") -> Sheets:
    return read_plan(plan(p, hid))


def v(cells: dict[tuple[int, int], PlanCell], a: str) -> object:
    c = cells.get(parse_address(a))
    return None if c is None else c.value


def f(cells: dict[tuple[int, int], PlanCell], a: str) -> str:
    c = cells.get(parse_address(a))
    return "" if c is None else c.formula


def row_of(cells: dict[tuple[int, int], PlanCell], col: str, value: object, after: int = 0) -> int:
    """The 1-based row of the first cell in `col` with `value` below row `after`."""
    c = parse_address(f"{col}1")[1]
    return next(
        r + 1 for (r, cc), x in sorted(cells.items()) if cc == c and r >= after and x.value == value
    )


def with_plan_config(p: Project, **values: object) -> Project:
    p.config["harness_plan"] = ConfigFile(name="harness_plan", placeholder=False, values=values)
    return p


# ---- the sheets and their order (section 3.7) -------------------------------------------------


def test_the_sheets_are_in_the_order_of_section_3_7() -> None:
    p = straight()
    assert list(sheets(p)) == [
        "Cover",
        "Change_Register",
        "W001",
        "Notes",
        "CON_A-J1",
        "CON_B-J1",
        "About",
    ]


def test_a_harness_id_that_reads_as_a_fixed_sheet_gets_a_prefix() -> None:
    assert hp.harness_sheet_name(Harness(id="Notes", name="n")) == "Harness_Notes"
    assert hp.harness_sheet_name(Harness(id="con_X", name="n")) == "Harness_con_X"
    assert hp.harness_sheet_name(Harness(id="W001", name="n")) == "W001"


# ---- Cover (section 3.1) ----------------------------------------------------------------------


def test_an_empty_document_reads_to_fill_in_and_the_version_is_the_harness_version() -> None:
    p = straight()
    cover = sheets(p)["Cover"]
    assert (v(cover, "E2"), v(cover, "F2")) == ("Doc.-No.", TO_FILL)
    assert (v(cover, "E3"), v(cover, "F3")) == ("Version", "1.0.0")
    assert (v(cover, "E4"), v(cover, "F4")) == ("Release", TO_FILL)
    assert v(cover, "A17") == "Plan test"
    assert v(cover, "A19") == "Plan test Harness Plan"
    assert v(cover, "A21") == TO_FILL
    assert v(cover, "C36") == "Contact Information" and v(cover, "D37") == TO_FILL
    stamp = stamp_of(p)
    assert v(cover, "A23") == stamp.line and v(cover, "A25") == stamp.notice
    assert v(cover, "A24") == hp.OVERWRITE_TEXT


def test_the_cover_takes_the_document_data_and_a_persons_version() -> None:
    p = straight()
    p.meta = evolve(p.meta, document=DocumentInfo(
        system="SYS", title="Project plans", company="Example Ltd",
        contact=[ContactLine(label="Name", value="to fill in later"),
                 ContactLine(label="E-mail", value="plans@example.org")],
        plans={"W001": PlanDocument(number="DOC-0001", version="2.1", release="2026-01-01", title="")},
    ))  # fmt: skip
    cover = sheets(p)["Cover"]
    assert [v(cover, a) for a in ("F2", "F3", "F4", "A19", "A21")] == [
        "DOC-0001",
        "2.1",
        "2026-01-01",
        "Project plans",
        "Example Ltd",
    ]
    assert [v(cover, a) for a in ("C37", "D37", "C38", "D38")] == [
        "Name",
        "to fill in later",
        "E-mail",
        "plans@example.org",
    ]
    assert cover[parse_address("D38")].link == "mailto:plans@example.org"
    assert cover[parse_address("D37")].link == ""
    p.meta.document.plans["W001"] = PlanDocument(title="Plan of W001")  # type: ignore[union-attr]
    cover = sheets(p)["Cover"]
    assert v(cover, "F3") == "1.0.0" and v(cover, "A19") == "Plan of W001"
    harness = sheets(p)["W001"]
    assert v(harness, "H6") == "SYS" and str(v(harness, "H8")).startswith("Harness SYS-W001: ")


# ---- Change_Register (section 3.2) ------------------------------------------------------------


def test_the_register_holds_the_change_log_of_that_harness_only() -> None:
    p = straight()
    p.harnesses["W002"] = Harness(id="W002", name="other")
    entries = [
        ChangeEntry(id="C0001", harness_id="W001", version="1.0.0", kind="review", by="Reviewer one", when="2026-01-02"),
        ChangeEntry(id="C0002", harness_id="W002", version="1.0.0", kind="release", by="x", when="2026-01-03"),
        ChangeEntry(id="C0003", harness_id="W001", version="1.0.0", kind="release", by="Approver", when="2026-01-04",
                    comment="first\nrelease"),
        ChangeEntry(id="C0004", harness_id="W001", version="1.1.0", kind="new_version", by="Author", when="2026-01-05"),
    ]  # fmt: skip
    p.changelog = {e.id: e for e in entries}
    reg = sheets(p)["Change_Register"]
    assert [v(reg, f"{c}4") for c in "BCDEFG"] == [
        "Version",
        "Sub-Version",
        "Date",
        "Name",
        "Sheets",
        "Description",
    ]
    rows = [[v(reg, f"{c}{r}") for c in "BCDEFG"] for r in (5, 6, 7)]
    assert rows == [
        ["1.0.0", "C0001", "2026-01-02", "Reviewer one", "W001", "in review"],
        ["1.0.0", "C0003", "2026-01-04", "Approver", "W001", "released: first release"],
        ["1.1.0", "C0004", "2026-01-05", "Author", "W001", "new version"],
    ]
    assert v(reg, "B8") is None
    assert (
        v(sheets(straight())["Change_Register"], "B5")
        == "No entry in the change log of this harness yet."
    )


def test_a_released_harness_says_so_in_its_header() -> None:
    p = straight()
    p.harnesses["W001"] = evolve(p.harnesses["W001"], status="released", version="2.0.0")
    harness = sheets(p)["W001"]
    assert v(harness, "Q6") == "VERSION: v2.0.0 (released)"
    assert v(sheets(p)["Cover"], "F3") == "2.0.0"
    assert v(sheets(straight())["W001"], "Q6") == "VERSION: v1.0.0 (draft)"


# ---- the harness sheet (sections 3.3 to 3.5) --------------------------------------------------


def test_the_header_and_the_title() -> None:
    harness = sheets(straight())["W001"]
    assert (v(harness, "H6"), v(harness, "N6")) == ("Plan test", "W001")
    assert v(harness, "H8") == "Harness Plan test-W001: A <–> B"
    assert f(harness, "H8") == (
        '"Harness "&[.H6]&"-"&[.N6]&": "&[$\'CON_A-J1\'.B1]&" <–> "&[$\'CON_B-J1\'.B1]'
    )


def test_the_part_tables() -> None:
    p = straight()
    p.harnesses["W001"] = evolve(p.harnesses["W001"], accessories=[
        Accessory(id="A1", kind="backshell", part_id="EX-BACKSHELL", target="W001-P1", quantity=2, note="tight"),
        Accessory(id="A2", kind="label"),
    ])  # fmt: skip
    harness = sheets(p)["W001"]
    top = row_of(harness, "H", "used Connectors")
    assert [v(harness, f"{c}{top + 1}") for c in "HIMN"] == [
        "No.",
        "Part No.",
        "Quantity",
        "Remark",
    ]
    assert [v(harness, f"{c}{top + 2}") for c in "HIMN"] == [
        1,
        "EX-MICROD-9-M",
        2,
        "W001-P1, W001-P2",
    ]
    types = row_of(harness, "H", "used Cable Types")
    assert [v(harness, f"{c}{types + 1}") for c in "HIKLORS"] == [
        "No.",
        "Part No.",
        "AWG",
        "Conductor",
        "Colours",
        "No. of wires in cable",
        "Length [mm]",
    ]
    assert [v(harness, f"{c}{types + 2}") for c in "HIKOR"] == [1, "EX-WIRE-SINGLE", "", "black", 1]
    assert [v(harness, f"{c}{types + 3}") for c in "HIKOR"] == [
        2,
        "EX-WIRE-TWISTED-SHIELDED",
        24,
        "red, white",
        2,
    ]
    shells = row_of(harness, "H", "used Backshells")
    assert [v(harness, f"{c}{shells + 2}") for c in "HIMN"] == [
        1,
        "EX-BACKSHELL",
        2,
        "on W001-P1; tight",
    ]
    assert v(sheets(straight())["W001"], f"I{shells + 2}") == hp.NO_BACKSHELLS


def _near_rows(harness: dict[tuple[int, int], PlanCell]) -> dict[object, int]:
    """Pin -> 1-based row of the near block of A-J1."""
    head = row_of(harness, "B", "Pin No.")
    out = {}
    r = head + 1
    while (x := v(harness, f"B{r}")) is not None:
        out[x] = r
        r += 1
    return out


def test_the_device_side_copies_the_con_sheet_and_the_harness_side_copies_and_mirrors() -> None:
    harness = sheets(straight())["W001"]
    rows = _near_rows(harness)
    assert list(rows) == [1, 2, 3, 4, 5]
    r = rows[1]
    assert [v(harness, f"{c}{r}") for c in "BCDEF"] == [1, "PWR_28V", "PWR", "28V", "Supply"]
    assert [f(harness, f"{c}{r}") for c in "BCDEF"] == [f"[$'CON_A-J1'.{c}19]" for c in "ABCDE"]
    assert [f(harness, f"{c}{r}") for c in "HIO"] == [f"[.B{r}]", f"[.C{r}]", f"[.E{r}]"]
    assert v(harness, f"J{r}") == "PWR" and f(harness, f"J{r}") == (
        f'IF([.D{r}]="IN";"OUT";IF([.D{r}]="OUT";"IN";[.D{r}]))'
    )
    r2 = rows[2]  # TX, out at A: IN on the harness side; RX, in at B: OUT mirrored
    assert (v(harness, f"D{r2}"), v(harness, f"J{r2}")) == ("OUT", "IN")
    assert (v(harness, f"R{r2}"), v(harness, f"S{r2}"), v(harness, f"T{r2}")) == ("OUT", "RX", 3)
    assert f(harness, f"R{r2}") == (
        'IF([$\'CON_B-J1\'.C21]="IN";"OUT";IF([$\'CON_B-J1\'.C21]="OUT";"IN";[$\'CON_B-J1\'.C21]))'
    )
    assert f(harness, f"S{r2}") == "[$'CON_B-J1'.B21]"
    # an empty source is an empty cell, not a copy that would show 0
    assert v(harness, f"F{r2}") is None and v(harness, f"E{rows[3]}") is None
    assert v(harness, f"D{rows[3]}") == "SGND" and v(harness, f"J{rows[3]}") == "SGND"


def test_the_wire_cells_of_a_row() -> None:
    harness = sheets(straight())["W001"]
    rows = _near_rows(harness)
    r1, r3 = rows[1], rows[3]
    assert [v(harness, f"{c}{r1}") for c in "KLMNPQ"] == ["red", 2, "W001-S1", 1250, 2, "red"]
    assert f(harness, f"P{r1}") == f"[.L{r1}]" and f(harness, f"K{r1}") == ""
    # M is empty; it is listed because the search format of section 25 gives it a style
    assert [v(harness, f"{c}{r3}") for c in "KLMN"] == ["black", 1, "", TO_FILL]
    assert v(harness, f"T{r3}") == 2


def test_the_far_device_side_and_the_reference_pinout() -> None:
    harness = sheets(straight())["W001"]
    rows = _near_rows(harness)
    head = row_of(harness, "B", "Pin No.")
    # one far connector: its pin column T, a gap U, its group from V
    assert v(harness, f"T{head}") == "Pinout (of B)"
    assert [v(harness, f"{c}{head}") for c in ("V", "W", "X", "Y", "Z")] == hp.PIN_HEAD
    assert (
        v(harness, f"V{head - 2}") == "B-J1" and v(harness, f"V{head - 1}") == "Data from CON_B-J1"
    )
    r2 = rows[2]
    assert (v(harness, f"V{r2}"), f(harness, f"V{r2}")) == (3, "")
    assert (v(harness, f"W{r2}"), f(harness, f"W{r2}")) == ("RX", "[$'CON_B-J1'.B21]")
    ref = row_of(harness, "V", "Pinout", after=head)
    assert v(harness, f"AA{ref}") == "Used in Row"
    pins = {v(harness, f"V{r}"): r for r in range(ref + 1, ref + 4)}
    assert list(pins) == [1, 2, 3]
    assert f(harness, f"V{pins[1]}") == "[$'CON_B-J1'.A19]"
    first = min(rows.values())
    match = f"MATCH([.V{pins[3]}];[.V{first}:.V{max(rows.values())}];0)"
    assert f(harness, f"AA{pins[3]}") == f'IF(ISNA({match});"";{match}+{first - 1})'
    assert v(harness, f"AA{pins[3]}") == r2 and v(harness, f"AA{pins[1]}") == rows[1]


def test_a_pin_without_a_wire_is_a_yellow_row_with_the_sentence_once() -> None:
    harness = sheets(straight())["W001"]
    rows = _near_rows(harness)
    # H to T, but J and R, which also carry the conditional format of GND against PWR, and I and
    # M, which carry the search format (section 25)
    cols = {parse_address(f"{c}1")[1] for c in "HKLNOPQST"}
    yellow = {c.style for (r, cc), c in harness.items() if r + 1 == rows[4] and cc in cols}
    assert len(yellow) == 1 and yellow != {""}
    assert {(r, cc) for (r, cc) in harness if r + 1 == rows[4] and cc in cols} == {
        (rows[4] - 1, cc) for cc in cols
    }
    assert v(harness, f"I{rows[4]}") == hp.NOT_CONNECTED_TEXT
    assert v(harness, f"I{rows[5]}") == ""  # yellow, empty: the sentence is there once
    assert (
        harness[parse_address(f"H{rows[5]}")].style == harness[parse_address(f"H{rows[4]}")].style
    )
    assert len(find(harness, hp.NOT_CONNECTED_TEXT)) == 1
    assert (
        harness[parse_address(f"H{rows[1]}")].style != harness[parse_address(f"H{rows[4]}")].style
    )


def test_no_sgnd_shows_while_a_signal_ground_pin_has_no_wire() -> None:
    p = straight()
    assert v(sheets(p)["W001"], "T6") is None  # A pin 3 (SGND) has a wire
    h = p.harnesses["W001"]
    p.harnesses["W001"] = evolve(h, wires=[w for w in h.wires if w.id != "W001-003"])
    assert v(sheets(p)["W001"], "T6") == hp.NO_SGND


def test_the_sums_per_cable_type_with_pair_parts_and_wires_without_a_length() -> None:
    harness = sheets(straight())["W001"]
    rows = _near_rows(harness)
    top = row_of(harness, "H", "Sum of length of cable type [mm]")
    first, last = min(rows.values()), max(rows.values())
    single, pair = top + 2, top + 3
    assert [v(harness, f"{c}{single}") for c in "HIN"] == [1, "EX-WIRE-SINGLE", 0]
    assert v(harness, f"O{single}") == "1 wire without a length"
    types = row_of(harness, "H", "used Cable Types")
    assert f(harness, f"N{pair}") == (
        f"(SUMIF([.L{first}:.L{last}];[.H{pair}];[.N{first}:.N{last}]))/[.R{types + 3}]"
    )
    assert v(harness, f"N{pair}") == (1250 + 1500) / 2  # a pair part counts the metres of cable
    assert v(harness, f"O{pair}") is None
    assert (v(harness, f"S{types + 3}"), f(harness, f"S{types + 3}")) == (1375, f"[.N{pair}]")


def test_the_conditional_format_of_gnd_against_pwr_is_over_both_direction_columns() -> None:
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(plan(straight()))) as z:
        content = z.read("content.xml").decode()
    assert content.count("is-true-formula(OR(AND([.J") > 0
    assert "&quot;GND&quot;" in content and "&quot;PWR&quot;" in content


def test_a_drawing_is_named_when_the_export_has_the_drawings() -> None:
    p = straight()
    assert find(
        read_plan(plan(p, drawings=True))["W001"], "Block diagram: harnesses/W001/drawing_A3.pdf"
    )
    assert not [c for c in sheets(p)["W001"].values() if str(c.value).startswith("Block diagram")]


# ---- the Direction words (section 4.3) --------------------------------------------------------


@pytest.mark.parametrize(
    ("pin", "word"),
    [
        (Pin(id="1", role="power"), "PWR"),
        (Pin(id="1", role="return"), "PWR-RET"),
        (Pin(id="1", role="ground"), "GND"),
        (Pin(id="1", role="signal_ground"), "SGND"),
        (Pin(id="1", role="shield"), "SHIELD"),
        (Pin(id="1", role="spare", direction="out"), ""),
        (Pin(id="1", signal="DATA", direction="in"), "IN"),
        (Pin(id="1", signal="DATA", direction="out"), "OUT"),
        (Pin(id="1", signal="DATA", direction="bidir"), "IN/OUT"),
        (Pin(id="1", signal="DATA"), ""),
        (Pin(id="1"), ""),
        (Pin(id="1", signal="GND"), "GND"),  # a derived role reads as a set one
        (Pin(id="1", signal="RTN"), "PWR-RET"),
    ],
)
def test_the_direction_word_of_a_pin(pin: Pin, word: str) -> None:
    assert hp.direction_word(new_project(), pin, None) == word
    assert hp.mirrored(word) == {"IN": "OUT", "OUT": "IN"}.get(word, word)


# ---- the colour rule (section 6) --------------------------------------------------------------


def _code(p: Project, pins: dict[str, str], parts: list[str], example: bool = False) -> Project:
    code: dict[str, object] = {"name": "pigtail", "parts": parts, "pins": pins}
    if example:
        code["example"] = True
    return with_plan_config(p, colour_rule="pin_code", colour_codes=[code])


def test_the_wire_rule_writes_the_wire_colour_as_a_value() -> None:
    p = _code(straight(), {"1": "Black", "2": "Brown", "3": "Red"}, ["EX-MICROD-9-M"])
    p.config["harness_plan"] = evolve(
        p.config["harness_plan"], values={**p.config["harness_plan"].values, "colour_rule": "wire"}
    )
    s = sheets(p)
    rows = _near_rows(s["W001"])
    assert (v(s["W001"], f"K{rows[1]}"), f(s["W001"], f"K{rows[1]}")) == ("red", "")
    assert not find(s["Notes"], "Pin")  # the rule is off: no table


def test_the_pin_code_rule_looks_each_end_up_by_its_pin() -> None:
    p = _code(straight(), {"1": "Black", "2": "Brown", "3": "Red"}, ["EX-MICROD-9-M"])
    s = sheets(p)
    harness, notes = s["W001"], s["Notes"]
    head = row_of(notes, "B", "Pin")
    assert v(notes, f"B{head - 2}") == "Colour code pigtail"
    assert [(v(notes, f"B{r}"), v(notes, f"C{r}")) for r in range(head + 1, head + 4)] == [
        (1, "Black"),
        (2, "Brown"),
        (3, "Red"),
    ]
    table = f"[$Notes.$B${head + 1}:.$C${head + 3}]"
    rows = _near_rows(harness)
    r1, r2 = rows[1], rows[2]
    assert v(harness, f"K{r1}") == "Black"
    assert f(harness, f"K{r1}") == f'IF([.H{r1}]="";"";VLOOKUP([.H{r1}];{table};2;0))'
    assert (v(harness, f"K{r2}"), v(harness, f"Q{r2}")) == ("Brown", "Red")  # far end: its pin 3
    assert f(harness, f"Q{r2}") == f'IF([.T{r2}]="";"";VLOOKUP([.T{r2}];{table};2;0))'


def test_an_unlisted_pin_reads_to_fill_in_and_a_part_not_in_a_code_keeps_the_wire_colour() -> None:
    p = _code(straight(), {"1": "Black"}, ["EX-MICROD-9-M"])
    harness = sheets(p)["W001"]
    rows = _near_rows(harness)
    assert (v(harness, f"K{rows[2]}"), f(harness, f"K{rows[2]}")) == (TO_FILL, "")
    p = _code(straight(), {"1": "Black"}, ["EX-OTHER"])
    harness = sheets(p)["W001"]
    assert v(harness, f"K{_near_rows(harness)[1]}") == "red"


def test_a_pin_01_matches_only_the_key_01() -> None:
    p = straight()
    h = p.harnesses["W001"]
    plug = evolve(h.connectors[0], mates_with=None, pins=[Pin(id="01"), Pin(id="2"), Pin(id="3")])
    wires = [evolve(h.wires[0], from_pin="01"), *h.wires[1:]]
    p.harnesses["W001"] = evolve(h, connectors=[plug, h.connectors[1]], wires=wires)
    harness = sheets(_code(p, {"1": "Black"}, ["EX-MICROD-9-M"]))["W001"]
    r = row_of(harness, "H", "01")
    assert v(harness, f"K{r}") == TO_FILL
    s = sheets(_code(p, {"01": "Black", "1": "Grey"}, ["EX-MICROD-9-M"]))
    harness = s["W001"]
    assert v(harness, f"K{r}") == "Black" and f(harness, f"K{r}").startswith("IF(")
    assert find(s["Notes"], "01") and find(s["Notes"], 1.0)  # text 01 and number 1 are two keys


def test_the_example_colour_code_is_taken_on_purpose_and_stays_marked() -> None:
    code = templates.example_colour_code(["EX-MICROD-9-M"])
    assert code["example"] is True and code["parts"] == ["EX-MICROD-9-M"]
    pins = code["pins"]
    assert isinstance(pins, dict) and len(pins) == 37
    assert (pins["1"], pins["10"], pins["20"], pins["37"]) == (
        "Black",
        "White",
        "Wh / Bl / Brown",
        "Wh / Red / Green",
    )
    p = with_plan_config(straight(), colour_rule="pin_code", colour_codes=[code])
    assert configcheck.validate_harness_plan(p) == []
    s = sheets(p)
    assert find(s["Notes"], hp.EXAMPLE_HEADING)
    harness = s["W001"]
    assert v(harness, f"K{_near_rows(harness)[2]}") == "Brown"
    assert check_values(s) == []


def test_a_new_project_has_no_colour_code() -> None:
    p = start_project("New")
    assert "harness_plan" not in p.config
    assert hp.plan_settings(p) == hp.PlanSettings()
    with open(
        templates._root() / "templates" / templates.EXAMPLE_COLOUR_CODE,
        newline="",
        encoding="utf-8",
    ) as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["Pin", "Colour"] and len(rows) == 38


def test_a_part_in_two_codes_is_refused() -> None:
    p = with_plan_config(straight(), colour_rule="pin_code", colour_codes=[
        {"name": "one", "parts": ["EX-MICROD-9-M"], "pins": {"1": "Black"}},
        {"name": "two", "parts": ["EX-MICROD-9-M", "EX-OTHER"], "pins": {"1": "Grey"}},
    ])  # fmt: skip
    issues = configcheck.validate_harness_plan(p)
    assert [i.code for i in issues] == ["config_invalid"]
    assert "names the part 'EX-MICROD-9-M' in more than one code" in issues[0].message


def test_the_plan_settings_do_not_make_the_harnesses_look_out_of_date() -> None:
    p = straight()
    before = input_hash(p)
    _code(p, {"1": "Black"}, ["EX-MICROD-9-M"])
    assert input_hash(p) == before


# ---- the CON_ sheets (section 3.6) ------------------------------------------------------------


def test_the_con_sheet_of_a_box_connector() -> None:
    p = straight()
    p.connectors["A-J1"] = evolve(
        p.connectors["A-J1"],
        source_doc="ICD-A",
        source_version="v0.5.0",
        source_link="https://example.org/icd-a",
    )
    con = sheets(p)["CON_A-J1"]
    assert [(v(con, f"A{r}"), v(con, f"B{r}")) for r in (1, 2, 3, 6, 7, 8)] == [
        ("Device", "A"), ("Connector ID", "A-J1"), ("Interface Name", "Data A to B"),
        ("Connector Type", "Micro-D 9-pin, female (example, baseline power and data)"),
        ("Number of Pins", 9), ("Gender", "female"),
    ]  # fmt: skip
    assert f(con, "B9") == '[.B6]&" "&[.B7]&" "&[.B8]'
    assert v(con, "B9") == "Micro-D 9-pin, female (example, baseline power and data) 9 female"
    assert f(con, "B11") == '[.B1]&" ["&[.B2]&"]: "&[.B3]&"; "&[.B9]'
    assert v(con, "B11") == "A [A-J1]: Data A to B; " + str(v(con, "B9"))
    assert (v(con, "B13"), con[parse_address("B13")].link, v(con, "B14")) == (
        "ICD-A",
        "https://example.org/icd-a",
        "v0.5.0",
    )
    assert v(con, "A15") == "CON sheet copied from" and v(con, "B15") is None
    assert v(con, "A16") is None  # the last update is not written
    assert [v(con, f"{c}18") for c in "ABCDE"] == hp.PIN_HEAD
    assert [v(con, f"{c}19") for c in "ABCDE"] == [1, "PWR_28V", "PWR", "28V", "Supply"]
    assert [v(con, f"{c}20") for c in "ABCDE"] == [2, "TX", "OUT", "RS422-3V3", ""]


def test_a_box_connector_used_by_two_harnesses_gives_the_same_con_sheet() -> None:
    p = straight()
    p.connectors["C-J1"] = _box("C", [Pin(id="1"), Pin(id="2")])
    p.units["C"] = Unit(id="C", name="C", subsystem="s")
    h = "W002"
    p.harnesses[h] = Harness(
        id=h, name="A to C", connectors=[_plug(h, 1, "A-J1"), _plug(h, 2, "C-J1")],
        wires=[_wire(h, 1, ("W002-P1", "4"), ("W002-P2", "1"))],
    )  # fmt: skip
    one, two = sheets(p, "W001"), sheets(p, "W002")
    assert "CON_A-J1" in one and "CON_A-J1" in two

    def plain(
        cells: dict[tuple[int, int], PlanCell],
    ) -> dict[tuple[int, int], tuple[object, str, str]]:
        return {k: (c.value, c.formula, c.link) for k, c in cells.items()}

    assert plain(one["CON_A-J1"]) == plain(two["CON_A-J1"])


# ---- the sides rule (section 9, without splices) ----------------------------------------------


def _sides(connectors: list[str], wires: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    h = Harness(
        id="W", name="w",
        connectors=[Connector(id=c, name=c, role="cable", part_id="X", pins=[Pin(id=str(k)) for k in range(1, 9)]) for c in connectors],
        wires=[Wire(id=f"W-{n}", from_connector=a, from_pin=str(n), to_connector=b, to_pin=str(n)) for n, (a, b) in enumerate(wires, start=1)],
    )  # fmt: skip
    s = hp.plan_sides(h)
    return [c.id for c in s.near], [c.id for c in s.far]


def test_the_sides_rule() -> None:
    assert _sides(["P1", "P2"], [("P1", "P2")]) == (
        ["P1"],
        ["P2"],
    )  # a tie: the first connector's end
    assert _sides(["P1", "P2", "P3"], [("P1", "P2"), ("P1", "P3")]) == (["P2", "P3"], ["P1"])
    assert _sides(["P10", "P2", "P1"], [("P1", "P10"), ("P2", "P10")]) == (["P1", "P2"], ["P10"])
    # two parts of the graph: each walk starts in the first end; a connector without a wire too
    assert _sides(["P1", "P2", "P3", "P4", "P5"], [("P1", "P2"), ("P3", "P4")]) == (
        ["P1", "P3", "P5"],
        ["P2", "P4"],
    )
    assert _sides(["P1"], []) == (["P1"], [])


def test_a_ring_of_three_connectors_lists_the_wire_inside_one_end_under_further_wires() -> None:
    p = new_project("Ring")
    h = "W001"
    p.harnesses[h] = Harness(
        id=h, name="ring", connectors=[_plug(h, n, None, role="inline") for n in (1, 2, 3)],
        wires=[
            _wire(h, 1, ("W001-P1", "1"), ("W001-P2", "1")),
            _wire(h, 2, ("W001-P2", "2"), ("W001-P3", "2")),
            _wire(h, 3, ("W001-P1", "3"), ("W001-P3", "3")),
        ],
    )  # fmt: skip
    s = sheets(p)
    harness = s["W001"]
    top = row_of(harness, "H", "Further wires")
    assert [v(harness, f"{c}{top + 2}") for c in "HIJ"] == ["W001-002", "W001-P2.2", "W001-P3.2"]
    assert v(harness, f"H{top + 3}") is None
    assert "CON_" not in "".join(s) and check_values(s) == []
    assert _wires_in_rows(harness, p.harnesses["W001"]) == 3


def _wires_in_rows(harness: dict[tuple[int, int], PlanCell], h: Harness) -> int:
    """The rows with a wire: a near row copies its Cable / Type into P; a further wire has its ID
    in H."""
    ids = {w.id for w in h.wires}
    p, col_h = parse_address("P1")[1], parse_address("H1")[1]
    near = [1 for (_r, c), x in harness.items() if c == p and x.formula.startswith("[.L")]
    return len(near) + len([1 for (_r, c), x in harness.items() if c == col_h and x.value in ids])


def test_every_wire_of_a_harness_is_in_exactly_one_row() -> None:
    p = golden_project("branching")
    for h in p.harnesses.values():
        assert _wires_in_rows(sheets(p, h.id)[h.id], h) == len(h.wires), h.id


# ---- a loose end (section 9) ------------------------------------------------------------------


def test_a_loose_end_is_a_far_column_with_no_con_sheet() -> None:
    p = straight()
    h = p.harnesses["W001"]
    loose = evolve(h.connectors[1], role="loose", mates_with=None, part_id="TBD-CONNECTOR")
    p.harnesses["W001"] = evolve(h, connectors=[h.connectors[0], loose])
    s = sheets(p)
    assert list(s) == ["Cover", "Change_Register", "W001", "Notes", "CON_A-J1", "About"]
    harness = s["W001"]
    head = row_of(harness, "B", "Pin No.")
    assert v(harness, f"T{head}") == "open end, to fill in"
    assert v(harness, "H8") == "Harness Plan test-W001: A <–> open end"
    r = _near_rows(harness)[2]
    # no CON_ sheet at the far end: its pin as a value, and no far direction or function to copy
    assert v(harness, f"T{r}") == 3 and not v(harness, f"R{r}") and not v(harness, f"S{r}")
    assert find(harness, "TBD-CONNECTOR (open end)")
    assert check_values(s) == []


# ---- the whole: formulas, the stamp, the bytes, build_outputs ---------------------------------


@pytest.mark.parametrize("name", GOLDEN_PROJECTS)
def test_every_formula_gives_its_stored_value_and_is_in_the_closed_list(name: str) -> None:
    p = golden_project(name)
    for h in p.harnesses.values():
        s = sheets(p, h.id)
        assert check_values(s) == [], h.id
        for cells in s.values():
            for cell in cells.values():
                if cell.formula:
                    check_formula(cell.formula, sheets=frozenset(s))


def test_the_evaluator_finds_a_stored_value_the_formula_does_not_give() -> None:
    s = sheets(straight())
    harness = s["W001"]
    r = _near_rows(harness)[2]
    key = parse_address(f"J{r}")
    harness[key] = PlanCell("OUT", harness[key].formula)
    assert check_values(s) == [f"W001!J{r}: 'IN' != stored 'OUT'"]
    ev = Evaluator(s)
    assert ev.evaluate('IF(ISNA(MATCH(7;[.H1:.H3];0));"no";"yes")&"!"', "W001") == "no!"
    assert address(*parse_address("AD100")) == "AD100"


def test_the_stamp_and_the_notice_are_on_the_about_sheet_the_cover_and_every_footer() -> None:
    import io
    import zipfile

    p = straight()
    stamp = stamp_of(p)
    data = plan(p)
    about = read_plan(data)["About"]
    assert [v(about, a) for a in ("A1", "B1", "A2", "B2", "A3", "B3")] == [
        "Generated by",
        stamp.line,
        "Model hash",
        stamp.model_hash,
        "Notice",
        stamp.notice,
    ]
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        styles = z.read("styles.xml").decode()
        sheets_in_file = z.read("content.xml").decode().count("<table:table ")
    # every sheet's page style has the stamp and the notice in its footer
    footer = (
        f"<style:footer><text:p>{stamp.line}</text:p><text:p>{stamp.notice}</text:p></style:footer>"
    )
    assert styles.count(footer) == styles.count("<style:master-page ") >= 1
    assert sheets_in_file == 7 and "<style:footer style:display" not in styles


def test_a_plan_is_the_same_bytes_every_time() -> None:
    p = golden_project("branching")
    assert plan(p) == plan(p)
    assert plan(golden_project("branching")) == plan(p)


def test_build_outputs_writes_the_plans_only_when_asked_and_lists_them_in_the_manifest() -> None:
    p = straight()
    off = build_outputs(p, drawings=False)
    assert not [k for k in off.files if k.endswith(".ods")]
    on = build_outputs(p, drawings=False, harness_plan=True)
    assert set(on.files) - set(off.files) == {"harnesses/W001/W001_plan.ods"}
    assert all(on.files[k] == off.files[k] for k in off.files)
    manifest = json.loads(on.manifest(p))
    listed = {e["path"]: e for e in manifest["files"]}
    import hashlib

    data = on.files["harnesses/W001/W001_plan.ods"]
    assert listed["harnesses/W001/W001_plan.ods"]["sha256"] == hashlib.sha256(data).hexdigest()
    assert data == plan(p)


# ---- the goldens --------------------------------------------------------------------------------


@pytest.mark.parametrize("name", GOLDEN_PROJECTS)
def test_the_plans_match_the_goldens(name: str) -> None:
    p = golden_project(name)
    stamp = stamp_of(p)
    files = {hp.plan_path(h): hp.plan_ods(p, h, stamp, drawings=True) for h in p.harnesses.values()}
    digests, texts = golden_files(files)
    assert digests == json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    if name in READABLE:
        for rel, body in texts.items():
            assert (GOLDEN / name / rel).read_text(encoding="utf-8") == body, rel


# ---- a real reader ----------------------------------------------------------------------------

SOFFICE = shutil.which("soffice")


@pytest.mark.skipif(SOFFICE is None, reason="LibreOffice (soffice) is not installed")
def test_libreoffice_shows_the_stored_values(tmp_path: Path) -> None:
    """LibreOffice converts one plan to CSV, one file per sheet; every cell it shows reads as the
    cell's stored text (a recalculated formula included)."""
    assert libreoffice_check(tmp_path, plan(golden_project("branching"))) > 100


def libreoffice_check(tmp_path: Path, data: bytes) -> int:
    """Convert a plan to CSV with LibreOffice and compare every shown cell with the stored text
    (both ways); the number of formula cells compared."""
    src = tmp_path / "plan.ods"
    src.write_bytes(data)
    subprocess.run(
        [
            str(SOFFICE),
            f"-env:UserInstallation={(tmp_path / 'profile').as_uri()}",
            "--headless",
            "--convert-to",
            "csv:Text - txt - csv (StarCalc):44,34,76,1,,0,false,true,false,false,false,-1",
            "--outdir",
            str(tmp_path / "out"),
            str(src),
        ],
        capture_output=True,
        check=True,
        timeout=180,
    )
    stored = shown_texts(data)
    formulas = 0
    for name, cells in read_plan(data).items():
        with (tmp_path / "out" / f"plan-{name}.csv").open(newline="", encoding="utf-8") as fh:
            shown = list(csv.reader(fh))
        for (r, c), text in stored[name].items():
            got = shown[r][c] if r < len(shown) and c < len(shown[r]) else ""
            assert got == text, (
                f"{name}!{address(r, c)}: LibreOffice shows {got!r}, stored {text!r}"
            )
            formulas += bool(cells.get((r, c), PlanCell("")).formula)
        for r, row in enumerate(shown):  # and it shows nothing the file does not hold
            for c, text in enumerate(row):
                assert not text or (r, c) in stored[name], f"{name}!{address(r, c)}: {text!r}"
    return formulas
