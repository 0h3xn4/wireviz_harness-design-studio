# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The rows of the Production sheet (`core/outputs/production.py`, design of 4.1.0, sections 3.2 to
3.5 and the edge cases of section 8 that apply to rows) and the sheet of the build workbook that
writes them (pull request 3: `buildsheet._production_sheet`, the *Start here* lines and the length
headings and sentences of *Cut list* and *Routing*).

A small drawn harness holds every case at once (`small`): natural ID order with the splices last,
the four kinds of heading, the label accessories, a pin with two wires (one row per wire), the runs
of spare pins (`3 to 4`, `8`), a pin with a signal or an interface and no wire (`(no wire)`), a wire
without part, colour, gauge or length (*to fill in*), the three origins of a length, nested groups
(both listed), a coax (backshell 360 at both ends) and a group across a branch (`here not
defined …`). Then the examples and fixtures: `flatsat` (the counts of the design), the splice, the
loose-end and the branching fixtures."""

import copy
import io
from pathlib import Path

import pytest

from harness_design_studio.core.generate.lengths import reference_lines
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import (
    Accessory,
    AsBuiltRecord,
    BranchPoint,
    Connector,
    Harness,
    Pin,
    Project,
    Segment,
    ShieldGroup,
    Unit,
    Wire,
)
from harness_design_studio.core.model.physical import LOOSE_ROLE, SPLICE_ROLE
from harness_design_studio.core.outputs import buildsheet as bs
from harness_design_studio.core.outputs import production as pr
from harness_design_studio.core.outputs import tables
from harness_design_studio.core.outputs.stamp import stamp_of
from harness_design_studio.core.outputs.xlsx_env import Workbook, load_workbook
from harness_design_studio.core.samples import new_project
from tests.loose_support import generated_loose
from tests.plan_support import golden_project

TO_FILL = "to fill in"


def small() -> Project:
    """Five connectors given out of order (W001-P10 before W001-P2), a loose end and a splice; a pin
    with two wires, a run of two spare pins and one of one, a pin with a signal and one with an
    interface but no wire; a wire without part, colour, gauge and length; a locked length, one on
    the wire and one from the segments; nested groups, a coax and a group across a branch; two
    label accessories on W001-P1 and a sleeving that is not a label."""
    p = new_project("Production")
    for u in ("D1", "D2"):
        p.units[u] = Unit(id=u, name=u, subsystem="s")
        p.connectors[f"{u}-J1"] = Connector(
            id=f"{u}-J1",
            name="J01",
            role="box",
            part_id="BOX",
            unit_id=u,
            pins=[Pin(id=str(n)) for n in range(1, 10)],
        )
    pins = [Pin(id=str(n)) for n in range(1, 10)]
    pins[6] = Pin(id="7", signal="SPARE_SIG")  # a signal and no wire
    pins[8] = Pin(id="9", interface_id="IF1")  # an interface and no wire
    cons = [
        Connector(
            id="W001-P10",
            name="P10",
            role="cable",
            part_id="PLUG",
            gender="female",
            pins=[Pin(id="1")],
        ),
        Connector(
            id="W001-P2",
            name="P2",
            role="cable",
            part_id="PLUG",
            gender="male",
            mates_with="D2-J1",
            pins=[Pin(id=str(n)) for n in range(1, 4)],
        ),
        Connector(
            id="W001-P1",
            name="P1",
            role="cable",
            part_id="PLUG",
            gender="male",
            mates_with="D1-J1",
            pins=pins,
        ),
        Connector(
            id="W001-P3", name="P3", role="loose", part_id="TBD-CONNECTOR", pins=[Pin(id="1")]
        ),
        Connector(
            id="W001-X1", name="X1", role="splice", part_id="EX-SPLICE-1", pins=[Pin(id="1")]
        ),
    ]
    wires = [
        Wire(
            id="W001-001",
            signal="PWR",
            from_connector="W001-P1",
            from_pin="1",
            to_connector="W001-P2",
            to_pin="1",
            part_id="EX-WIRE-SINGLE",
            colour="red",
            gauge_awg=24,
            length_m=1.5,
        ),
        Wire(
            id="W001-002",
            signal="RTN",
            from_connector="W001-P1",
            from_pin="2",
            to_connector="W001-P2",
            to_pin="2",
            part_id="EX-WIRE-SINGLE",
            colour="black",
            gauge_awg=24,
        ),
        Wire(
            id="W001-003",
            from_connector="W001-P1",
            from_pin="2",
            to_connector="W001-P10",
            to_pin="1",
        ),
        Wire(
            id="W001-004",
            signal="SIG",
            from_connector="W001-P3",
            from_pin="1",
            to_connector="W001-P1",
            to_pin="5",
            part_id="EX-WIRE-SINGLE",
            colour="blue",
            gauge_awg=26,
            length_m=2.0,
            locked=True,
        ),
        Wire(
            id="W001-005",
            signal="A",
            from_connector="W001-P1",
            from_pin="6",
            to_connector="W001-X1",
            to_pin="1",
            part_id="EX-WIRE-SINGLE",
            colour="white",
            gauge_awg=26,
            length_m=0.5,
        ),
        Wire(
            id="W001-006",
            signal="A",
            from_connector="W001-X1",
            from_pin="1",
            to_connector="W001-P2",
            to_pin="3",
            part_id="EX-WIRE-SINGLE",
            colour="white",
            gauge_awg=26,
            length_m=0.7,
        ),
    ]
    shields = [
        ShieldGroup(
            id="W001-S10",
            kind="coax",
            wire_ids=["W001-005"],
            end_a="backshell_360",
            end_b="backshell_360",
        ),
        ShieldGroup(id="W001-S2", kind="twisted_pair", wire_ids=["W001-001", "W001-002"]),
        ShieldGroup(
            id="W001-S1",
            kind="overall_shield",
            wire_ids=["W001-003", "W001-002", "W001-001"],
            end_a="backshell_360",
            end_b="floating",
        ),
    ]
    segments = [
        Segment(id="W001-L1", from_node="W001-P1", to_node="W001-B1", length_m=1.0),
        Segment(id="W001-L2", from_node="W001-B1", to_node="W001-P2", length_m=0.25),
        Segment(id="W001-L3", from_node="W001-B1", to_node="W001-P10"),
    ]
    accessories = [
        Accessory(id="W001-A2", kind="label", target="W001-P1"),
        Accessory(id="W001-A1", kind="label", target="W001-P1", position="50 mm from the P1 end"),
        Accessory(id="W001-A3", kind="sleeving", target="W001-P1", position="all along"),
    ]
    p.harnesses["W001"] = Harness(
        id="W001",
        name="Small",
        connectors=cons,
        wires=wires,
        shields=shields,
        branch_points=[BranchPoint(id="W001-B1", name="Branch")],
        segments=segments,
        accessories=accessories,
    )
    return p


def rows_of(p: Project, hid: str = "W001") -> dict[str, list[tuple[object, ...]]]:
    return {b.connector_id: [r.values() for r in b.rows] for b in pr.production_blocks(p, p.harnesses[hid])}  # fmt: skip


def headings(p: Project, hid: str = "W001") -> dict[str, str]:
    return {b.connector_id: b.heading for b in pr.production_blocks(p, p.harnesses[hid])}


def test_the_blocks_are_the_cable_connectors_in_natural_order_then_the_splices() -> None:
    p = small()
    blocks = pr.production_blocks(p, p.harnesses["W001"])
    assert [(b.connector_id, b.splice) for b in blocks] == [
        ("W001-P1", False), ("W001-P2", False), ("W001-P3", False), ("W001-P10", False),
        ("W001-X1", True),
    ]  # fmt: skip


def test_the_four_headings_and_the_label_accessories() -> None:
    heads = headings(small())
    assert heads == {
        "W001-P1": "W001-P1   ·   PLUG   ·   male   ·   mates D1-J1 (D1:J01)   ·   label W001-P1 mates D1-J1"
        "   ·   label at 50 mm from the P1 end; label, position to fill in",
        "W001-P2": "W001-P2   ·   PLUG   ·   male   ·   mates D2-J1 (D2:J01)   ·   label W001-P2 mates D2-J1",
        "W001-P3": "W001-P3   ·   TBD-CONNECTOR (loose end)   ·   open end, to fill in   ·   label W001-P3 open end",
        "W001-P10": "W001-P10   ·   PLUG   ·   female   ·   not plugged into a unit   ·   label W001-P10 mates -",
        "W001-X1": "W001-X1   ·   EX-SPLICE-1   ·   splice   ·   1 node",
    }  # fmt: skip


def test_a_mate_that_is_no_connector_of_the_project_and_a_gender_not_set() -> None:
    p = small()
    h = p.harnesses["W001"]
    cons = [
        c.model_copy(update={"mates_with": "GONE-J9", "gender": "unspecified"}) if c.id == "W001-P2" else c
        for c in h.connectors
    ]  # fmt: skip
    p.harnesses["W001"] = h.model_copy(update={"connectors": cons})
    assert headings(p)["W001-P2"] == (
        "W001-P2   ·   PLUG   ·   gender not set   ·   not plugged into a unit   ·   label W001-P2 mates GONE-J9"
    )  # fmt: skip
    # the far side of a wire to it has nothing in brackets
    assert rows_of(p)["W001-P1"][0][3] == "W001-P2.1"


def test_the_rows_of_a_connector_with_every_kind_of_pin() -> None:
    both = "W001-S1 overall shield: here backshell 360, far floating; W001-S2 twisted pair"
    assert rows_of(small())["W001-P1"] == [
        ("1", "PWR", "W001-001", "W001-P2.1 (D2:J01)", "EX-WIRE-SINGLE", "red (RD)", 24, 1.5,
         "on the wire", "W001-001 PWR to W001-P2.1", both),
        ("2", "RTN", "W001-002", "W001-P2.2 (D2:J01)", "EX-WIRE-SINGLE", "black (BK)", 24, 1.25,
         "segments only, no service loops", "W001-002 RTN to W001-P2.2", both),
        # the same pin again for its second wire, and a wire the design holds nothing of
        ("2", "", "W001-003", "W001-P10.1", TO_FILL, TO_FILL, TO_FILL, TO_FILL, "",
         "W001-003 to W001-P10.1", "W001-S1 overall shield: here backshell 360, far floating"),
        ("3 to 4", "", "(spare)", "", "", "", "", "", "", "", ""),
        ("5", "SIG", "W001-004", "W001-P3.1 (open end)", "EX-WIRE-SINGLE", "blue (BU)", 26, 2.0,
         "locked", "W001-004 SIG to W001-P3.1", ""),
        ("6", "A", "W001-005", "W001-X1.1 (splice)", "EX-WIRE-SINGLE", "white (WH)", 26, 0.5,
         "on the wire", "W001-005 A to W001-X1.1",
         "W001-S10 coax: here backshell 360, far backshell 360"),
        ("7", "SPARE_SIG", "(no wire)", "", "", "", "", "", "", "", ""),
        ("8", "", "(spare)", "", "", "", "", "", "", "", ""),
        ("9", "", "(no wire)", "", "", "", "", "", "", "", ""),
    ]  # fmt: skip


def test_the_far_ends_their_labels_and_the_shield_seen_from_the_other_end() -> None:
    rows = rows_of(small())
    p2 = rows["W001-P2"]
    assert [r[:4] for r in p2] == [
        ("1", "PWR", "W001-001", "W001-P1.1 (D1:J01)"),
        ("2", "RTN", "W001-002", "W001-P1.2 (D1:J01)"),
        ("3", "A", "W001-006", "W001-X1.1 (splice)"),
    ]
    assert p2[0][9] == "W001-001 PWR to W001-P1.1"  # the text of end B at the `to` end
    assert p2[0][10] == "W001-S1 overall shield: here floating, far backshell 360; W001-S2 twisted pair"  # fmt: skip
    # the loose end: its wire is the `from` end there, so it carries the text of end A
    assert rows["W001-P3"] == [
        ("1", "SIG", "W001-004", "W001-P1.5 (D1:J01)", "EX-WIRE-SINGLE", "blue (BU)", 26, 2.0,
         "locked", "W001-004 SIG to W001-P1.5", ""),
    ]  # fmt: skip
    # the third connector of a group across a branch has no end of it
    assert rows["W001-P10"][0][10] == (
        "W001-S1 overall shield: here not defined (the group ends on more than two connectors)"
    )


def test_a_splice_node_has_a_row_per_wire_and_the_labels_of_the_tables() -> None:
    p = small()
    h = p.harnesses["W001"]
    assert rows_of(p)["W001-X1"] == [
        ("1", "A", "W001-005", "W001-P1.6 (D1:J01)", "EX-WIRE-SINGLE", "white (WH)", 26, 0.5,
         "on the wire", "W001-005 A to W001-P1.6", "W001-S10 coax: here backshell 360, far backshell 360"),
        ("1", "A", "W001-006", "W001-P2.3 (D2:J01)", "EX-WIRE-SINGLE", "white (WH)", 26, 0.7,
         "on the wire", "W001-006 A to W001-P2.3", ""),
    ]  # fmt: skip
    labels = {r[0]: r[2] for r in tables.labels(p, h)[1:]}
    assert labels["W001-005-B"] == "W001-005 A to W001-P1.6"
    assert labels["W001-006-A"] == "W001-006 A to W001-P2.3"
    assert "W001-X1" not in labels  # a splice has no label, and its heading names none


def test_every_wire_is_in_two_rows_one_at_each_end() -> None:
    p = small()
    h = p.harnesses["W001"]
    seen = sorted(str(r[2]) for rows in rows_of(p).values() for r in rows if str(r[2]).startswith("W001-"))  # fmt: skip
    assert seen == sorted([w.id for w in h.wires] * 2)


def test_a_wire_from_a_pin_to_the_same_pin_is_two_rows_end_a_then_end_b() -> None:
    p = small()
    h = p.harnesses["W001"]
    loop = Wire(id="W001-007", from_connector="W001-P2", from_pin="1", to_connector="W001-P2", to_pin="1")  # fmt: skip
    p.harnesses["W001"] = h.model_copy(update={"wires": [*h.wires, loop]})
    rows = [r for r in rows_of(p)["W001-P2"] if r[2] == "W001-007"]
    assert [r[9] for r in rows] == ["W001-007 to W001-P2.1", "W001-007 to W001-P2.1"]
    assert len(rows) == 2


def test_the_label_format_in_force_is_the_label_of_the_rows_and_the_heading() -> None:
    from harness_design_studio.core.model import ConfigFile

    p = small()
    p.config["model"] = ConfigFile(name="model", placeholder=False, values={"label_format": "compact"})  # fmt: skip
    assert headings(p)["W001-P2"].endswith("label W001-P2 mates D2-J1")
    assert rows_of(p)["W001-P1"][0][9] == "W001-001 to W001-P2.1"
    assert rows_of(p)["W001-P2"][0][9] == "W001-001 to W001-P1.1"


def test_the_blocks_are_pure() -> None:
    p = small()
    before = p.harnesses["W001"].model_dump()
    assert pr.production_blocks(p, p.harnesses["W001"]) == pr.production_blocks(p, p.harnesses["W001"])  # fmt: skip
    assert p.harnesses["W001"].model_dump() == before


def test_the_headers_of_the_two_files() -> None:
    assert pr.HEADER == (
        "Pin", "Signal", "Wire", "Goes to", "Wire part", "Colour", "AWG",
        "Length (m), rear to rear", "Length from", "Label at this end",
        "Shield group: here / far end",
    )  # fmt: skip
    assert pr.PLAN_HEADER[7] == "Length [mm] rear to rear"
    assert pr.PLAN_HEADER[:7] == pr.HEADER[:7] and pr.PLAN_HEADER[8:] == pr.HEADER[8:]
    assert pr.colour_text(None) == "" and pr.colour_text("red") == "red (RD)"


# ---- the examples and the fixtures ---------------------------------------------------------------


@pytest.fixture(scope="module")
def flatsat() -> Project:
    return golden_project("flatsat")


def test_flatsat_w001_has_18_blocks_and_54_rows(flatsat: Project) -> None:
    blocks = pr.production_blocks(flatsat, flatsat.harnesses["W001"])
    assert len(blocks) == 18 and sum(len(b.rows) for b in blocks) == 54
    first = blocks[0]
    assert first.heading == (
        "W001-P1   ·   EX-MICROD-9-M   ·   male   ·   mates MTQ1-J01 (MTQ1:J01)   ·   label W001-P1 mates MTQ1-J01"
    )  # fmt: skip
    assert [r.values()[:9] for r in first.rows] == [
        ("1", "PWR", "W001-017", "W001-P10.1 (PDU2:J10)", "EX-WIRE-SINGLE", "red (RD)", 24, 2.95, "on the wire"),
        ("2", "RTN", "W001-018", "W001-P10.2 (PDU2:J10)", "EX-WIRE-SINGLE", "black (BK)", 24, 2.95, "on the wire"),
        ("3 to 9", "", "(spare)", "", "", "", "", "", ""),
    ]  # fmt: skip


def test_flatsat_row_counts_are_those_the_design_quotes(flatsat: Project) -> None:
    counts = {
        hid: sum(len(b.rows) for b in pr.production_blocks(flatsat, h))
        for hid, h in flatsat.harnesses.items()
    }
    assert {k: counts[k] for k in ("W001", "W002", "W004")} == {"W001": 54, "W002": 74, "W004": 64}


def test_flatsat_nested_groups_list_both_and_the_coax_is_bonded_at_both_ends(
    flatsat: Project,
) -> None:
    w002 = rows_of(flatsat, "W002")
    assert w002["W002-P3"][0][10] == (
        "W002-S2 twisted pair; W002-S3 overall shield: here backshell 360, far floating"
    )
    assert w002["W002-P12"][0][10] == (
        "W002-S2 twisted pair; W002-S3 overall shield: here floating, far backshell 360"
    )
    w005 = rows_of(flatsat, "W005")
    coax = [r for rows in w005.values() for r in rows if "coax" in str(r[10])]
    assert [r[10] for r in coax] == ["W005-S4 coax: here backshell 360, far backshell 360"] * 2


def test_the_splice_fixture_lists_each_node_with_its_wires() -> None:
    p = golden_project("splices")
    blocks = pr.production_blocks(p, p.harnesses["W003"])
    splices = [b for b in blocks if b.splice]
    assert [b.connector_id for b in splices] == ["W003-X1", "W003-X2"]
    assert all(not b.splice for b in blocks[: len(blocks) - 2])
    assert [r.values()[:4] for r in splices[0].rows] == [
        ("1", "PWR", "W003-001", "W003-P1.1 (PCDU:J02)"),
        ("1", "PWR", "W003-002", "W003-P2.1 (OBC:J02)"),
        ("1", "PWR", "W003-003", "W003-P3.1 (OBC:J03)"),
    ]
    assert splices[0].heading == "W003-X1   ·   EX-SPLICE-1   ·   splice   ·   1 node"
    for b in blocks:
        for r in b.rows:
            if r.wire.startswith("W003-") and b.connector_id.startswith("W003-P"):
                assert r.goes_to.endswith("(splice)"), r


def test_the_loose_end_fixture(tmp_path: Path) -> None:
    p = load_project(generated_loose(tmp_path / "loose")).project
    found = 0
    for h in p.harnesses.values():
        loose = {c.id for c in h.connectors if c.role == LOOSE_ROLE}
        for b in pr.production_blocks(p, h):
            if b.connector_id in loose:
                assert (
                    f"   ·   open end, {TO_FILL}   ·   label {b.connector_id} open end" in b.heading
                )
                found += 1
            for r in b.rows:
                far = r.goes_to.split(" ")[0].rsplit(".", 1)[0]
                if far in loose:
                    assert r.goes_to.endswith(" (open end)"), r
    assert found


def test_the_branching_fixture_needs_nothing_special() -> None:
    p = golden_project("branching")
    h = p.harnesses["W001"]
    blocks = pr.production_blocks(p, h)
    assert [b.connector_id for b in blocks] == sorted((c.id for c in h.connectors), key=tables.natural_key)  # fmt: skip
    rows = [r for b in blocks for r in b.rows if r.wire.startswith("W001-0")]
    assert len(rows) == 2 * len(h.wires)
    for r in rows:  # a length from the segments or none, and the origin to match
        assert (r.length_from == "") == (r.length == TO_FILL), r
    assert {r.length_from for r in rows} == {"", "segments only, no service loops"}
    assert not any(c.role == SPLICE_ROLE for c in h.connectors)


def test_a_wire_to_a_connector_that_is_not_in_the_harness_has_nothing_in_brackets() -> None:
    from harness_design_studio.core.outputs import verify_production as vp

    p = small()
    h = p.harnesses["W001"]
    stray = Wire(id="W001-008", from_connector="W001-P2", from_pin="2", to_connector="W001-P99", to_pin="1")  # fmt: skip
    p.harnesses["W001"] = h.model_copy(update={"wires": [*h.wires, stray]})
    row = next(r for r in rows_of(p)["W001-P2"] if r[2] == "W001-008")
    assert row[3] == "W001-P99.1"
    want = [[r.values() for r in b.rows] for b in pr.production_blocks(p, p.harnesses["W001"])]
    assert [list(b.rows) for b in vp.production_rows(p, p.harnesses["W001"])] == want
    # IDs that start with a digit sort as the core's natural order does
    ids = ["10a", "9", "a1", "1", "01", "a10", "a2"]
    assert sorted(ids, key=vp._natural) == sorted(ids, key=tables.natural_key)


# ---- the sheet of the build workbook (pull request 3) ---------------------------------------------


def _expected_sheet(p: Project, h: Harness) -> list[list[object]]:
    """The Production sheet as the rows of the core make it: the headings, the splice title above
    the first splice, each block's heading, rows and an empty row, and the length sentence last."""
    want: list[list[object]] = [list(bs.PRODUCTION_HEADER)]
    titled = False
    for b in pr.production_blocks(p, h):
        if b.splice and not titled:
            titled = True
            want += [[bs.SPLICE_BLOCK], []]
        want.append([b.heading])
        want += [list(r.values()) for r in b.rows]
        want.append([])
    want += [[line] for line in reference_lines(p)]
    return [_trim(row) for row in want]


def _trim(row: list[object]) -> list[object]:
    cells = ["" if v is None else v for v in row]
    while cells and cells[-1] == "":
        cells.pop()
    return cells


def _book(p: Project, hid: str) -> Workbook:
    return load_workbook(io.BytesIO(bs.build_workbook(p, p.harnesses[hid], stamp_of(p))))


def test_the_sheet_comes_after_the_cut_list_and_the_routing_before_connectors(
    flatsat: Project,
) -> None:
    assert bs.SHEETS == (
        "Start here", "Cut list", "Production", "Connectors", "Parts", "Accessories", "Labels",
        "Tests", "About",
    )  # fmt: skip
    straight, branching = flatsat.harnesses["W003"], flatsat.harnesses["W001"]
    assert not tables.has_branches(straight) and tables.has_branches(branching)
    assert bs.sheet_names(flatsat, straight) == list(bs.SHEETS)
    assert bs.sheet_names(flatsat, branching)[:5] == [
        "Start here", "Cut list", "Routing", "Production", "Connectors",
    ]  # fmt: skip
    assert _book(flatsat, "W003").sheetnames == list(bs.SHEETS)
    with_records = copy.deepcopy(flatsat)
    with_records.asbuilt["R1"] = AsBuiltRecord(
        id="R1", kind="harness", harness_id="W003", subject="W003"
    )
    assert bs.sheet_names(with_records, with_records.harnesses["W003"])[-3:] == [
        "Tests", bs.ASBUILT_SHEET, "About",
    ]  # fmt: skip


@pytest.mark.parametrize("hid", ["W001", "W002", "W005"])
def test_the_sheet_holds_the_rows_of_the_core_and_the_length_sentence_last(
    flatsat: Project, hid: str
) -> None:
    ws = _book(flatsat, hid)[bs.PRODUCTION_SHEET]
    got = [_trim(list(r)) for r in ws.iter_rows(values_only=True)]
    assert got == _expected_sheet(flatsat, flatsat.harnesses[hid])


def test_a_small_harness_with_a_splice_a_loose_end_and_a_wire_to_fill_in() -> None:
    p = small()
    wb = _book(p, "W001")
    ws = wb[bs.PRODUCTION_SHEET]
    got = [_trim(list(r)) for r in ws.iter_rows(values_only=True)]
    assert got == _expected_sheet(p, p.harnesses["W001"])
    assert [bs.SPLICE_BLOCK] in got  # the splices under their own title, last
    assert got.index([bs.SPLICE_BLOCK]) > max(
        n for n, r in enumerate(got) if r and str(r[0]).startswith("W001-P")
    )
    row = next(n for n, r in enumerate(ws.iter_rows(values_only=True), start=1) if r[2] == "W001-003")  # fmt: skip
    for col in (5, 6, 7, 8):  # part, colour, gauge and length to fill in: amber
        assert ws.cell(row, col).value == TO_FILL
        assert ws.cell(row, col).fill.fgColor.rgb.endswith("FFE699"), col


def test_the_print_set_up_the_colour_cells_and_the_ticks(flatsat: Project) -> None:
    wb = _book(flatsat, "W002")
    ws = wb[bs.PRODUCTION_SHEET]
    assert ws.page_setup.orientation == "landscape" and ws.page_setup.paperSize == 9
    assert ws.page_setup.fitToWidth == 1 and ws.page_setup.fitToHeight == 0
    assert ws.print_title_rows == "$1:$1" and ws.freeze_panes == "A2"
    assert stamp_of(flatsat).line in ws.oddFooter.left.text
    assert ws.cell(1, 12).value == "Done (x)"
    assert all(ws.cell(r, 12).value is None for r in range(2, ws.max_row + 1))  # nothing ticked
    ticked = {str(dv.sqref) for dv in ws.data_validations.dataValidation}
    assert ticked and all(ref.startswith("L") for ref in ticked)
    red = next(r for r in range(2, ws.max_row + 1) if ws.cell(r, 6).value == "red (RD)")
    cut = wb["Cut list"]
    in_cut = next(c for row in cut.iter_rows() for c in row if c.value == "red (RD)")
    assert ws.cell(red, 6).fill.fgColor.rgb == in_cut.fill.fgColor.rgb  # as the cut list
    assert ws.cell(red, 6).fill.fgColor.rgb not in ("00000000", None)


def test_a_page_break_comes_before_a_block_that_would_pass_42_rows(flatsat: Project) -> None:
    ws = _book(flatsat, "W002")[bs.PRODUCTION_SHEET]
    breaks = [b.id for b in ws.row_breaks.brk]
    assert breaks  # W002 has 74 rows in 22 blocks: more than one page
    heads = [
        r for r in range(2, ws.max_row + 1)
        if ws.cell(r, 1).fill.fgColor.rgb.endswith("1F3A5F")
    ]  # fmt: skip
    assert all(b + 1 in heads for b in breaks)  # never inside a block
    for start, end in zip([1, *breaks], [*breaks, ws.max_row - 1], strict=True):
        assert end - start <= 42, (start, end)


def test_start_here_lists_the_sheet_and_says_what_the_lengths_are_measured_from(
    flatsat: Project,
) -> None:
    ws = _book(flatsat, "W001")["Start here"]
    rows = [_trim(list(r)) for r in ws.iter_rows(values_only=True)]
    first = [str(r[0]) for r in rows if r]
    assert first.index("Routing") < first.index("Production") < first.index("Connectors")
    assert [bs.PRODUCTION_SHEET, bs.PRODUCTION_TEXT] in rows
    lengths = [r for r in rows if r[:1] == [bs.LENGTHS_ROW]]
    at = rows.index(lengths[0])
    lines = reference_lines(flatsat)
    assert rows[at : at + 3] == [[bs.LENGTHS_ROW, lines[0]], ["", lines[1]], ["", lines[2]]]
    assert first.index("Released on") < first.index(bs.LENGTHS_ROW) < first.index("How to use this workbook")  # fmt: skip


def test_the_cut_list_and_the_routing_say_what_their_lengths_run_between(flatsat: Project) -> None:
    wb = _book(flatsat, "W001")
    cut = [_trim(list(r)) for r in wb["Cut list"].iter_rows(values_only=True)]
    assert cut[0][5] == "Length (m), rear to rear" == bs.CUT_HEADER[5]
    lines = [[line] for line in reference_lines(flatsat)]
    assert cut[-5][1] == "18 wires" and cut[-4] == [] and cut[-3:] == lines
    routing = [_trim(list(r)) for r in wb["Routing"].iter_rows(values_only=True)]
    assert routing[0][3] == "Length (m), rear or branch centre"
    assert routing[-4:] == [[], *lines]
    assert tables.SEGMENT_HEADER[3] == "Length (m)"  # segments.csv keeps its heading
