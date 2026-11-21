# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-OUT-16: the Review sheet of the build workbook (design of 4.3.0,
`docs/ait/DESIGN_4.3_REVIEW_VIEW.md`, part B, sections 4.1 to 4.5; pull request 4).

`buildsheet._review_sheet` writes the review view of `core/review.review_view` and works nothing out
again: every cell of the sheet is a cell of the view. The sheet comes before *About*, after *Tests*
and, when there is one, *As-built*; *Start here* lists it before *About*. The tests read the sheet
of `flatsat` W002 (section 4.4), the head, the six blocks and their empty sentences, the tick column
of a checklist, the release entry of `mini3-released`, and the print set-up of section 4.5 (A4
landscape, one page wide, no repeated header row, the footer, the widths, a page break before a
block that would start in the last five rows of a page)."""

import copy
import io
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.core import checks, drc, review
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.model import AsBuiltRecord, ConfigFile, Harness, Project
from harness_design_studio.core.outputs import buildsheet as bs
from harness_design_studio.core.outputs import tables
from harness_design_studio.core.outputs.build import build_outputs
from harness_design_studio.core.outputs.stamp import stamp_of
from harness_design_studio.core.outputs.xlsx_env import load_workbook
from harness_design_studio.core.samples import mini3
from tests.plan_support import golden_project
from tools.format3_record import _release_history

H = "W002"


@pytest.fixture(scope="module")
def flatsat() -> Project:
    return golden_project("flatsat")


def _found(p: Project) -> list[checks.Finding]:
    return [*checks.find(p), *drc.run(p)]


def _book(p: Project, h: Harness, found: list[checks.Finding] | None = None) -> Any:
    return load_workbook(io.BytesIO(bs.build_workbook(p, h, stamp_of(p), found)))


def _rows(ws: Any) -> list[list[Any]]:
    """The rows of a sheet, each without its empty cells at the end (an empty row is [])."""
    out = []
    for row in ws.iter_rows(values_only=True):
        cells = ["" if v is None else v for v in row]
        while cells and cells[-1] == "":
            cells.pop()
        out.append(cells)
    return out


def _view_rows(view: review.ReviewView, stamp: Any) -> list[list[Any]]:
    """The rows the sheet must hold: the head, then each block after an empty row (its heading;
    then its sentences, or its one sentence for no rows, or its columns and rows)."""
    out: list[list[Any]] = [
        [view.title],
        [f"Version {view.version}   ·   status {view.status}   ·   {stamp.line}   ·   {stamp.notice}"],
        [view.release], [review.RELEASE_HINT], [review.TICK_HINT],
    ]  # fmt: skip
    for block in view.blocks:
        out += [[], [block.heading]]
        if not block.columns:
            out += [[row.cells[0]] for row in block.rows]
        elif not block.rows:
            out.append([block.empty])
        else:
            out.append(list(block.columns))
            for row in block.rows:
                cells = list(row.cells)
                while cells and cells[-1] == "":
                    cells.pop()
                out.append(cells)
    return out


# ---- the place of the sheet (section 4.1) ------------------------------------------------------


def test_the_sheet_comes_before_about_after_tests_and_as_built(flatsat: Project) -> None:
    assert bs.SHEETS[-3:] == ("Tests", bs.REVIEW_SHEET, "About") and bs.REVIEW_SHEET == "Review"
    straight, branching = flatsat.harnesses["W003"], flatsat.harnesses["W001"]
    assert not tables.has_branches(straight) and tables.has_branches(branching)
    assert _book(flatsat, straight).sheetnames == list(bs.SHEETS)
    assert _book(flatsat, branching).sheetnames == bs.sheet_names(flatsat, branching)
    assert bs.sheet_names(flatsat, branching)[-3:] == ["Tests", "Review", "About"]
    with_records = copy.deepcopy(flatsat)
    with_records.asbuilt["R1"] = AsBuiltRecord(id="R1", kind="harness", harness_id="W003", subject="W003")  # fmt: skip
    names = bs.sheet_names(with_records, with_records.harnesses["W003"])
    assert names[-4:] == ["Tests", bs.ASBUILT_SHEET, "Review", "About"]
    assert _book(with_records, with_records.harnesses["W003"]).sheetnames == names


def test_start_here_lists_the_sheet_before_about(flatsat: Project) -> None:
    rows = _rows(_book(flatsat, flatsat.harnesses[H])["Start here"])
    named = [r[:2] for r in rows if r[:1] in (["Tests"], ["Review"], ["About"])]
    assert named == [
        ["Tests", "continuity and insulation tests; write down the result"],
        ["Review", bs.REVIEW_TEXT],
        ["About", "which version of the tool and which design this was made from"],
    ]
    assert bs.REVIEW_TEXT == (
        "for the reviewer: the project's checklist with a column to tick, every finding and open "
        "value of this harness, and the sources to look at"
    )


# ---- the head and the six blocks (sections 4.2 and 4.4) ----------------------------------------


def test_every_cell_of_flatsat_w002_is_a_cell_of_the_view(flatsat: Project) -> None:
    h = flatsat.harnesses[H]
    found = _found(flatsat)
    ws = _book(flatsat, h, found)["Review"]
    view = review.review_view(flatsat, h, found)
    assert _rows(ws) == _view_rows(view, stamp_of(flatsat))
    rows = _rows(ws)
    assert rows[0] == ["Review of W002  aocs to bus"]
    assert rows[2] == ["Release: not released yet."]
    assert rows[3] == [
        "What stops the release is marked in the column Release; a release also needs current "
        "outputs, a name and a comment."
    ]
    assert rows[4] == [
        "Tick a printout, or a copy saved outside the outputs folder: a file in outputs/ that was "
        "changed after the export stops the release (outputs_modified)."
    ]
    headings = [rows[n + 1][0] for n, r in enumerate(rows) if r == [] and n + 1 < len(rows)]
    assert headings == [
        "Checklist",
        "Findings of W002: 0 errors, 7 warnings, 11 notes open; 0 waived, 0 accepted as deviations",
        "For the whole project", "Values still open", "Sources to look at",
        "How the numbers were made",
    ]  # fmt: skip
    assert rows[7] == [review.NO_CHECKLIST]  # no list: the sentence in place of the rows
    assert (
        len(rows) == 81
    )  # the head, 6 empty rows, 6 headings, 4 column rows, 60 rows and sentences


def test_the_head_and_the_styles_of_the_cells(flatsat: Project) -> None:
    ws = _book(flatsat, flatsat.harnesses[H])["Review"]
    assert ws["A1"].font.b and ws["A1"].font.sz == 16
    assert ws["A5"].font.i
    findings = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "Severity")
    assert [ws.cell(findings, c).font.b for c in range(1, 8)] == [True] * 7  # the column row
    stops = next(
        ws.cell(r, 5) for r in range(1, ws.max_row + 1) if ws.cell(r, 5).value == review.STOPS
    )
    reason = next(
        ws.cell(r, 7) for r in range(1, ws.max_row + 1) if ws.cell(r, 7).value == review.REASON
    )
    assert stops.fill.fgColor.rgb.endswith("F8CBAD") and reason.fill.fgColor.rgb.endswith("FFE699")
    assert set(bs._RELEASE_FILLS) == {review.STOPS, review.REASON}


def test_every_harness_of_the_examples_holds_its_view() -> None:
    for name in ("first-steps", "small-satellite", "splices"):
        p = golden_project(name)
        found = _found(p)
        files = build_outputs(p, drawings=False).files
        stamp = stamp_of(p)
        for hid, h in p.harnesses.items():
            ws = load_workbook(io.BytesIO(files[f"harnesses/{hid}/{hid}_build.xlsx"]))["Review"]
            assert _rows(ws) == _view_rows(review.review_view(p, h, found), stamp), (name, hid)


def test_the_findings_are_run_when_not_given(flatsat: Project) -> None:
    h = flatsat.harnesses["W005"]
    stamp = stamp_of(flatsat)
    assert bs.build_workbook(flatsat, h, stamp) == bs.build_workbook(flatsat, h, stamp, _found(flatsat))  # fmt: skip


def test_empty_blocks_say_so_in_one_sentence() -> None:
    p = mini3()
    generate_project(p)
    bare = Harness(id="W099", name="Empty", generated=False)
    rows = _rows(_book(p, bare, [])["Review"])
    assert rows[0] == ["Review of W099  Empty"]
    after = {rows[n][0]: rows[n + 1] for n in range(len(rows) - 1) if rows[n]}
    assert after["Checklist"] == [review.NO_CHECKLIST]
    assert after[
        "Findings of W099: 0 errors, 0 warnings, 0 notes open; 0 waived, 0 accepted as deviations"
    ] == [  # fmt: skip
        "No finding of the design rules, the verifier or the logical checks is about W099 or what it carries."
    ]
    assert after["For the whole project"] == ["No finding is about the whole project."]
    assert after["Sources to look at"] == ["W099 plugs into no device connector and uses no part."]
    assert rows[-2:] == [[line] for line in review.HOW_LINES]


def test_a_checklist_has_an_empty_tick_column_with_the_tick_rules() -> None:
    p = mini3()
    generate_project(p)
    points = [f"Point {n} of the review." for n in range(1, 4)]
    naming = p.config["naming"]
    p.config["naming"] = ConfigFile(name="naming", placeholder=False, values={**naming.values, "review_checklist": points})  # fmt: skip
    ws = _book(p, p.harnesses["W001"])["Review"]
    rows = _rows(ws)
    at = next(n for n, r in enumerate(rows) if r[:1] == [f"Checklist: 3 points (config/naming.json review_checklist, list {review.list_hash(points)})"])  # fmt: skip
    assert rows[at + 1] == ["No.", "Point", "Done (x)", "Note"]
    assert rows[at + 2 : at + 5] == [[n, f"Point {n} of the review."] for n in (1, 2, 3)]
    first = at + 3  # the sheet's row of point 1
    assert [ws.cell(first + k, 3).value for k in range(3)] == [None, None, None]  # nobody ticked
    assert [str(dv.sqref) for dv in ws.data_validations.dataValidation] == [f"C{first}:C{first + 2}"]  # fmt: skip
    assert [str(cf.sqref) for cf in ws.conditional_formatting] == [f"C{first}:C{first + 2}"]


def test_a_released_harness_names_its_release_in_row_3(tmp_path: Path) -> None:
    p = _release_history(tmp_path)
    found = _found(p)
    w001 = _rows(_book(p, p.harnesses["W001"], found)["Review"])
    assert w001[1][0].startswith("Version 2.0.0   ·   status released   ·   ")
    assert w001[2] == [review.review_view(p, p.harnesses["W001"], found).release]
    assert w001[2][0].startswith("Release: version 2.0.0 released on 2026-04-02 by Ada, checked by Bob. Comment: ")  # fmt: skip
    assert _rows(_book(p, p.harnesses["W002"], found)["Review"])[2] == [
        "Release: not released yet."
    ]


# ---- the print set-up (section 4.5) -------------------------------------------------------------


def test_the_print_set_up(flatsat: Project) -> None:
    ws = _book(flatsat, flatsat.harnesses[H])["Review"]
    assert ws.page_setup.orientation == "landscape" and ws.page_setup.paperSize == 9
    assert (ws.page_setup.fitToWidth, ws.page_setup.fitToHeight) == (1, 0)
    assert ws.sheet_properties.pageSetUpPr.fitToPage
    assert ws.print_title_rows is None and ws.freeze_panes is None  # no repeated header row
    assert ws.oddFooter.right.text == "Page &P of &N" and ws.oddFooter.center.text == "&A"
    stamp = stamp_of(flatsat)
    assert ws.oddFooter.left.text == f"{stamp.line}\n{stamp.notice}"
    widths = {k: d.width for k, d in ws.column_dimensions.items()}
    assert widths["E"] == 80.0  # Finding text: up to 80, so a long text wraps on few lines
    assert all(w <= 80.0 for w in widths.values())
    assert all(widths[c] <= 46.0 for c in ("A", "C", "D", "F", "G"))
    assert list(ws.row_breaks.brk) == []  # no block starts in the last five rows of a page


@pytest.mark.parametrize("points", [27, 28, 30, 32, 33, 70])
def test_a_block_does_not_start_in_the_last_five_rows_of_a_page(points: int) -> None:
    """With a checklist of N points the heading of the findings is row N + 10 of the sheet: on rows
    38 to 42 (the last five of a page of 42 rows) a page break comes before it; on row 37 or 43
    it needs none; with 70 points the checklist runs over the first page. Every block heading of the sheet keeps out of the last five rows of its page."""
    p = mini3()
    generate_project(p)
    naming = p.config["naming"]
    listed = [f"Point {n}." for n in range(1, points + 1)]
    p.config["naming"] = ConfigFile(name="naming", placeholder=False, values={**naming.values, "review_checklist": listed})  # fmt: skip
    ws = _book(p, p.harnesses["W001"])["Review"]
    rows = _rows(ws)
    starts = [n + 2 for n, r in enumerate(rows) if r == [] and n + 1 < len(rows)]  # 1-based
    breaks = [b.id for b in ws.row_breaks.brk]
    last = 0
    for start in starts:
        if any(start - 1 == b for b in breaks):
            last = start - 1
        place = (start - 1 - last) % bs.REVIEW_PAGE_ROWS  # 0-based place on its page
        assert place < bs.REVIEW_PAGE_ROWS - bs.REVIEW_KEEP_ROWS, (start, breaks)
    findings = starts[1]
    assert findings == points + 10
    assert (breaks[:1] == [findings - 1]) == ((findings - 1) % bs.REVIEW_PAGE_ROWS >= 37)


def test_the_sheet_does_not_depend_on_the_order_of_the_wires(flatsat: Project) -> None:
    """The first items of an open check are named in natural ID order, so a harness whose wires
    and connectors are stored in another order writes the same sheet."""
    from harness_design_studio.core.model import evolve

    h = flatsat.harnesses[H]
    found = _found(flatsat)
    turned = evolve(h, wires=list(reversed(h.wires)), connectors=list(reversed(h.connectors)))
    assert _rows(_book(flatsat, turned, found)["Review"]) == _rows(_book(flatsat, h, found)["Review"])  # fmt: skip
    rows = _rows(_book(flatsat, h, found)["Review"])
    pins = next(r for r in rows if r[:1] == ["Pins in use without a termination"])
    assert pins[2] == "W002-P1.1, W002-P1.2, W002-P2.1, W002-P2.2, W002-P3.1 and 47 more"
