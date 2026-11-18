# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The independent output check of the routing (2.3.0, D-243 B7, design section 5.6): `verify.py` works
out the rows of `segments.csv`, of the sheet *Segments* of `<ID>.xlsx` and of the sheet *Routing* of the
build workbook from the project alone (its own route of each wire, its own count of the wires per
segment, its own walk to the connectors beyond a branch point) and reports `out_routing` when a cell
differs, a row is missing or out of order, or a file or sheet is missing for a harness with a branch
point or present for one without. One mutation per check, in the style of
`tests/test_build_data_outputs.py`."""

import io
from collections.abc import Callable
from typing import Any

import pytest

from harness_design_studio.core.model import Project
from harness_design_studio.core.outputs import exports
from harness_design_studio.core.outputs.build import build_outputs
from harness_design_studio.core.outputs.stamp import csv_bytes, parse_csv, stamp_of
from harness_design_studio.core.outputs.verify import _xlsx_sheets, verify_outputs
from harness_design_studio.core.outputs.xlsx_env import load_workbook
from tests.test_outputs_routing import STRAIGHT, H, branching_project

CSV = f"harnesses/{H}/segments.csv"
BOOK = f"harnesses/{H}/{H}.xlsx"
BUILD = f"harnesses/{H}/{H}_build.xlsx"


@pytest.fixture(scope="module")
def project() -> Project:
    return branching_project()


@pytest.fixture(scope="module")
def built(project: Project) -> dict[str, bytes]:
    return build_outputs(project, drawings=False).files


def _codes(project: Project, files: dict[str, bytes]) -> set[str]:
    return {i.code for i in verify_outputs(project, files).issues}


def test_the_untouched_files_pass(project: Project, built: dict[str, bytes]) -> None:
    assert not {c for c in _codes(project, built) if c.startswith("out_")}


# ---- segments.csv ---------------------------------------------------------------------------------


def _csv_changed(project: Project, built: dict[str, bytes], change: Callable[[list[list[str]]], None]) -> set[str]:  # fmt: skip
    rows = parse_csv(built[CSV])
    change(rows)
    return _codes(project, {**built, CSV: csv_bytes(rows, stamp_of(project))})


def _set(row: int, col: int, value: str) -> Callable[[list[list[str]]], None]:
    def change(rows: list[list[str]]) -> None:
        rows[row][col] = value

    return change


def _move_wire(rows: list[list[str]]) -> None:
    """W001-001 moved from W001-L2 (DEV1's leg) to W001-L3 (DEV4's leg); the counts stay right."""
    leg1, leg2 = rows[2][5].split(";"), rows[3][5].split(";")
    rows[2][5] = ";".join([*leg1[1:], leg2[0]])
    rows[3][5] = ";".join(sorted([*leg2[1:], leg1[0]]))


def _swap(rows: list[list[str]]) -> None:
    rows[1], rows[2] = rows[2], rows[1]


@pytest.mark.parametrize(
    ("name", "change"),
    [
        ("a changed length", _set(1, 3, "0.55")),
        ("a length where none is entered", _set(3, 3, "1")),
        ("no length where one is entered", _set(2, 3, "")),
        ("a wrong count", _set(1, 4, "15")),
        ("a wire moved to another segment", _move_wire),
        ("a wrong end", _set(2, 1, "W001-P2")),
        ("a missing row", lambda rows: rows.pop(3)),
        ("an extra row", lambda rows: rows.append(["W001-L9", "W001-B1", "W001-P1", "", "0", ""])),
        ("rows out of order", _swap),
        ("a wrong heading", _set(0, 4, "Wires (count)")),
    ],
)
def test_a_changed_segments_csv_is_out_routing(project: Project, built: dict[str, bytes], name: str, change: Callable[[list[list[str]]], None]) -> None:  # fmt: skip
    assert "out_routing" in _csv_changed(project, built, change), name


def test_segments_csv_exists_exactly_for_a_harness_with_a_branch_point(project: Project, built: dict[str, bytes]) -> None:  # fmt: skip
    missing = {k: v for k, v in built.items() if k != CSV}
    assert "out_missing" in _codes(project, missing)
    extra = {**built, f"harnesses/{STRAIGHT}/segments.csv": built[CSV]}
    assert "out_routing" in _codes(project, extra)


# ---- the Segments sheet of <ID>.xlsx --------------------------------------------------------------


def _book(project: Project, built: dict[str, bytes], hid: str, segments: list[list[str]] | None) -> bytes:  # fmt: skip
    """The workbook of `hid` again, with `segments` as its Segments sheet (none for None)."""
    sheets = {k: v for k, v in _xlsx_sheets(built[f"harnesses/{hid}/{hid}.xlsx"]).items() if k not in ("About", "Segments")}  # fmt: skip
    if segments is not None:
        sheets["Segments"] = segments
    return exports.xlsx_bytes(sheets, stamp_of(project))


def test_the_rebuilt_workbook_passes(project: Project, built: dict[str, bytes]) -> None:
    same = _book(project, built, H, parse_csv(built[CSV]))
    assert same == built[BOOK]


def test_a_changed_segments_sheet_is_out_routing(project: Project, built: dict[str, bytes]) -> None:
    rows = parse_csv(built[CSV])
    rows[4][3] = "2"
    assert "out_routing" in _codes(project, {**built, BOOK: _book(project, built, H, rows)})
    rows = parse_csv(built[CSV])
    _move_wire(rows)
    assert "out_routing" in _codes(project, {**built, BOOK: _book(project, built, H, rows)})


def test_the_segments_sheet_exists_exactly_for_a_harness_with_a_branch_point(project: Project, built: dict[str, bytes]) -> None:  # fmt: skip
    assert "out_routing" in _codes(project, {**built, BOOK: _book(project, built, H, None)})
    other = f"harnesses/{STRAIGHT}/{STRAIGHT}.xlsx"
    wrong = _book(project, built, STRAIGHT, parse_csv(built[CSV]))
    assert "out_routing" in _codes(project, {**built, other: wrong})


# ---- the Routing sheet of the build workbook ------------------------------------------------------


def _build_changed(project: Project, built: dict[str, bytes], change: Callable[[Any], None], rel: str = BUILD) -> set[str]:  # fmt: skip
    wb = load_workbook(io.BytesIO(built[rel]))
    change(wb)
    out = io.BytesIO()
    wb.save(out)
    return _codes(project, {**built, rel: out.getvalue()})


def _cell(sheet: str, ref: str, value: object) -> Callable[[Any], None]:
    def change(wb: Any) -> None:
        wb[sheet][ref].value = value

    return change


def _move_in_sheet(wb: Any) -> None:
    ws = wb["Routing"]
    leg1, leg2 = str(ws["F3"].value).split("; "), str(ws["F4"].value).split("; ")
    ws["F3"].value = "; ".join([*leg1[1:], leg2[0]])
    ws["F4"].value = "; ".join(sorted([*leg2[1:], leg1[0]]))


def _unlist(wb: Any) -> None:
    """The line *Routing* of *How to use this workbook* taken out of *Start here*."""
    for row in wb["Start here"].iter_rows():
        for c in row:
            if c.value == "Routing":
                c.value = None


WRONG_SIDES = "W001-L1: W001-P3; W001-L2: W001-P1, W001-P4; W001-L3: W001-P2"


@pytest.mark.parametrize(
    ("name", "change"),
    [
        ("a changed length", _cell("Routing", "D2", 0.75)),
        ("a number where the length is to fill in", _cell("Routing", "D4", 1.0)),
        ("to fill in where a length is entered", _cell("Routing", "D3", "to fill in")),
        ("a wrong count", _cell("Routing", "E2", 17)),
        ("a wire moved to another segment", _move_in_sheet),
        ("a missing segment row", lambda wb: wb["Routing"].delete_rows(4)),
        ("a wrong side of a branch point", _cell("Routing", "C9", WRONG_SIDES)),
        ("a renamed branch point", _cell("Routing", "B10", "Branch Z")),
        ("a missing branch point row", lambda wb: wb["Routing"].delete_rows(10)),
        ("no branch point block", lambda wb: wb["Routing"].delete_rows(7, 4)),
        ("the sheet removed", lambda wb: wb.remove(wb["Routing"])),
        ("the line of Start here removed", _unlist),
    ],
)
def test_a_changed_routing_sheet_is_out_routing(project: Project, built: dict[str, bytes], name: str, change: Callable[[Any], None]) -> None:  # fmt: skip
    assert "out_routing" in _build_changed(project, built, change), name


def test_a_routing_sheet_in_the_build_workbook_of_a_straight_harness_is_out_routing(project: Project, built: dict[str, bytes]) -> None:  # fmt: skip
    rel = f"harnesses/{STRAIGHT}/{STRAIGHT}_build.xlsx"

    def add(wb: Any) -> None:
        wb.create_sheet("Routing", 2).append(["Segment", "From", "To", "Length (m)", "Number of wires", "Wires"])  # fmt: skip

    assert "out_routing" in _build_changed(project, built, add, rel)
