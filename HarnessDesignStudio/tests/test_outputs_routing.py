# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The routing outputs of a harness that branches (2.3.0, D-243 owner question B7, design section 5.6):
`harnesses/<ID>/segments.csv`, the sheet *Segments* of `<ID>.xlsx` and the sheet *Routing* of the build
workbook, after *Cut list*, listed on *Start here*. Only a harness with at least one branch point has
them; a straight harness keeps its files and sheets. The mutation tests of the independent check are in
`tests/test_verify_routing.py`."""

import io

import pytest

from harness_design_studio.core.commands import Put, apply_ops
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.generate.lengths import reference_text
from harness_design_studio.core.model import BranchPoint, Project, Segment, evolve
from harness_design_studio.core.outputs import buildsheet, tables
from harness_design_studio.core.outputs.build import build_outputs
from harness_design_studio.core.outputs.stamp import parse_csv
from harness_design_studio.core.outputs.verify import _xlsx_sheets, verify_outputs
from harness_design_studio.core.outputs.xlsx_env import load_workbook
from tests.test_branch_segmentation import TWO_TWO, build

H, STRAIGHT = "W001", "W002"  # the users' harness DEV2 + DEV3 <-> DEV1 + DEV4, and a pair
LENGTHS = {"W001-L1": 0.5, "W001-L2": 0.25, "W001-L4": 1.125}  # L3 and L5 stay to fill in


def branching_project() -> Project:
    """W001 with Branch X, the trunk W001-L1 and Branch Y (three segments with a length, two
    without), and W002, a straight harness between DEV5 and DEV6."""
    p = build([*TWO_TWO, ("DEV5", "DEV6")])
    generate_project(p)
    h = p.harnesses[H]
    segs = [evolve(s, length_m=LENGTHS.get(s.id)) for s in h.segments]
    apply_ops(p, [Put("harnesses", evolve(h, segments=segs))])
    return p


@pytest.fixture(scope="module")
def project() -> Project:
    return branching_project()


@pytest.fixture(scope="module")
def files(project: Project) -> dict[str, bytes]:
    return build_outputs(project, drawings=False).files


def _values(data: bytes) -> dict[str, list[list[object]]]:
    wb = load_workbook(io.BytesIO(data), data_only=True)
    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}


def _wires(*n: int) -> list[str]:
    return [f"W001-{k:03d}" for k in n]


TRUNK = _wires(*range(1, 17))
P1, P2 = _wires(1, 2, 3, 4, 9, 10, 11, 12), _wires(5, 6, 7, 8, 13, 14, 15, 16)  # DEV1, DEV4
P3, P4 = _wires(*range(1, 9)), _wires(*range(9, 17))  # DEV2, DEV3


def test_the_project_has_one_harness_that_branches_and_one_that_does_not(project: Project) -> None:
    assert [b.name for b in project.harnesses[H].branch_points] == ["Branch X", "Branch Y"]
    assert not project.harnesses[STRAIGHT].branch_points
    assert tables.has_branches(project.harnesses[H])
    assert not tables.has_branches(project.harnesses[STRAIGHT])


def test_segments_csv_has_one_row_per_segment_with_its_ends_length_and_wires(files: dict[str, bytes]) -> None:  # fmt: skip
    rows = parse_csv(files[f"harnesses/{H}/segments.csv"])
    assert rows == [
        ["Segment", "From", "To", "Length (m)", "Number of wires", "Wires"],
        ["W001-L1", "W001-B1", "W001-B2", "0.5", "16", ";".join(TRUNK)],
        ["W001-L2", "W001-P1", "W001-B1", "0.25", "8", ";".join(P1)],
        ["W001-L3", "W001-P2", "W001-B1", "", "8", ";".join(P2)],
        ["W001-L4", "W001-P3", "W001-B2", "1.125", "8", ";".join(P3)],
        ["W001-L5", "W001-P4", "W001-B2", "", "8", ";".join(P4)],
    ]


def test_the_workbook_of_the_harness_gets_the_segments_sheet_last(files: dict[str, bytes]) -> None:
    sheets = _xlsx_sheets(files[f"harnesses/{H}/{H}.xlsx"])
    assert list(sheets)[-1] == "Segments"
    assert sheets["Segments"] == parse_csv(files[f"harnesses/{H}/segments.csv"])


def test_the_build_workbook_has_the_routing_sheet_after_the_cut_list(project: Project, files: dict[str, bytes]) -> None:  # fmt: skip
    data = files[f"harnesses/{H}/{H}_build.xlsx"]
    sheets = _values(data)
    names = buildsheet.sheet_names(project, project.harnesses[H])
    assert list(sheets) == names == [
        "Start here", "Cut list", "Routing", "Production", "Connectors", "Parts", "Accessories",
        "Labels", "Tests", "About",
    ]  # fmt: skip
    routing = [[v for v in row if v is not None] for row in sheets["Routing"]]
    assert routing == [
        ["Segment", "From", "To", "Length (m), rear or branch centre", "Number of wires", "Wires"],
        ["W001-L1", "W001-B1", "W001-B2", 0.5, 16, "; ".join(TRUNK)],
        ["W001-L2", "W001-P1", "W001-B1", 0.25, 8, "; ".join(P1)],
        ["W001-L3", "W001-P2", "W001-B1", "to fill in", 8, "; ".join(P2)],
        ["W001-L4", "W001-P3", "W001-B2", 1.125, 8, "; ".join(P3)],
        ["W001-L5", "W001-P4", "W001-B2", "to fill in", 8, "; ".join(P4)],
        [],
        ["Branch point", "Name", "Connectors beyond it, by segment"],
        ["W001-B1", "Branch X", "W001-L1: W001-P3, W001-P4; W001-L2: W001-P1; W001-L3: W001-P2"],
        ["W001-B2", "Branch Y", "W001-L1: W001-P1, W001-P2; W001-L4: W001-P3; W001-L5: W001-P4"],
        [],
        [reference_text(project)],
    ]
    assert routing == [list(r) for r in buildsheet.routing_rows(project, project.harnesses[H])]
    ws = load_workbook(io.BytesIO(data))["Routing"]
    assert ws["D4"].fill.start_color.rgb.endswith("FFE699")  # a length to fill in is amber
    assert ws["D2"].fill.fill_type is None
    assert ws.freeze_panes == "B2"


def test_start_here_lists_the_routing_sheet_after_the_cut_list(files: dict[str, bytes]) -> None:
    start = [r[0] for r in _values(files[f"harnesses/{H}/{H}_build.xlsx"])["Start here"] if r]
    assert start.index("Routing") == start.index("Cut list") + 1
    assert "Routing" not in [
        r[0] for r in _values(files[f"harnesses/{STRAIGHT}/{STRAIGHT}_build.xlsx"])["Start here"] if r
    ]  # fmt: skip


def test_a_straight_harness_has_no_routing_file_or_sheet(project: Project, files: dict[str, bytes]) -> None:  # fmt: skip
    assert f"harnesses/{STRAIGHT}/segments.csv" not in files
    assert "Segments" not in _xlsx_sheets(files[f"harnesses/{STRAIGHT}/{STRAIGHT}.xlsx"])
    build = _values(files[f"harnesses/{STRAIGHT}/{STRAIGHT}_build.xlsx"])
    assert list(build) == list(buildsheet.SHEETS)
    assert buildsheet.sheet_names(project, project.harnesses[STRAIGHT]) == list(buildsheet.SHEETS)
    assert [k for k in files if k.endswith("segments.csv")] == [f"harnesses/{H}/segments.csv"]


def test_the_outputs_verify_and_are_the_same_every_time(project: Project, files: dict[str, bytes]) -> None:  # fmt: skip
    report = verify_outputs(project, files)
    assert [i.message for i in report.issues if i.severity == "error"] == []
    again = build_outputs(project, drawings=False).files
    assert again == files


def test_rows_are_in_natural_order_and_a_side_with_no_connector_says_none() -> None:
    p = branching_project()
    h = p.harnesses[H]
    extra = [Segment(id=f"W001-L{n}", from_node="W001-B2", to_node=f"W001-B{n}") for n in range(6, 12)]  # fmt: skip
    points = [*h.branch_points, *(BranchPoint(id=f"W001-B{n}", name=f"Spare {n}") for n in range(6, 12))]  # fmt: skip
    apply_ops(
        p, [Put("harnesses", evolve(h, segments=[*h.segments, *extra], branch_points=points))]
    )
    h = p.harnesses[H]
    assert [r[0] for r in tables.segments(h)[1:]] == [f"W001-L{n}" for n in range(1, 12)]
    found_sides = tables.branch_sides(h)
    sides = {b: s for b, _name, s in found_sides}
    assert [b for b, _name, _s in found_sides][:3] == ["W001-B1", "W001-B2", "W001-B6"]
    assert sides["W001-B6"] == [("W001-L6", ["W001-P1", "W001-P2", "W001-P3", "W001-P4"])]
    assert ("W001-L6", []) in sides["W001-B2"]
    assert "W001-L6: (none)" in tables.side_text(sides["W001-B2"])
    assert tables.segments(h)[6][3:] == ["", "0", ""]  # no wire runs out to a spare branch point
    found = verify_outputs(p, build_outputs(p, drawings=False).files).issues
    assert [i.message for i in found if i.code.startswith("out_")] == []


def test_a_loop_gives_its_wires_no_route_in_the_builder_and_in_the_check() -> None:
    """With a segment that closes a loop (the rule `segment-loop` reports it) a wire whose two
    connectors the loop joins has no single route: it is counted in no segment, by the builder
    and by the independent check alike. Here every wire can go round the loop."""
    p = branching_project()
    h = p.harnesses[H]
    loop = Segment(id="W001-L6", from_node="W001-P1", to_node="W001-P3", length_m=0.1)
    apply_ops(p, [Put("harnesses", evolve(h, segments=[*h.segments, loop]))])
    h = p.harnesses[H]
    through = tables.segment_wires(h)
    assert set(through) == {f"W001-L{n}" for n in range(1, 7)}
    assert all(ids == [] for ids in through.values())
    found = verify_outputs(p, build_outputs(p, drawings=False).files).issues
    assert [i.message for i in found if i.code == "out_routing"] == []


def test_no_cell_of_a_written_workbook_holds_a_line_break() -> None:
    """The workbooks are written by openpyxl's plain writer (`xlsx_env`), which stores each sheet
    through a text-mode file: on Windows a line break in a cell becomes CR LF, so the workbook
    differs by platform (Windows CI found it in the first *Routing* sheet). Every example's
    workbooks, with the routing of flatsat, must hold no raw line break in a cell value."""
    import re
    import tempfile
    import zipfile
    from pathlib import Path

    from harness_design_studio.core import templates

    found = []
    for name in ("flatsat", "small-satellite"):
        with tempfile.TemporaryDirectory(prefix="nl-") as tmp:
            p = templates.create_project(Path(tmp) / name, name)
            if not p.harnesses:
                generate_project(p)
            files = build_outputs(p).files
        for rel, data in files.items():
            if not rel.endswith(".xlsx"):
                continue
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for member in z.namelist():
                    if member.startswith("xl/") and member.endswith(".xml"):
                        text = z.read(member)
                        for value in re.findall(rb"<t(?: [^>]*)?>(.*?)</t>", text, re.S):
                            if b"\n" in value or b"\r" in value:
                                found.append(f"{name}/{rel} {member}: {value[:60]!r}")
    assert found == [], found
