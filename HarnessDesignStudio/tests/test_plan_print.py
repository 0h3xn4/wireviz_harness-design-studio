# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-OUT-15: the harness plan prints over several pages (design of 4.1.0
`docs/ait/DESIGN_4.1_PRODUCTION_SHEET.md`, sections 5, 6.2 and 3.1; pull request 5).

The harness sheet prints at a fixed scale, the largest whole percent at which its print range is
one A4 landscape page wide, with rows 6 to 9 (the header line, the title and the length note `H9`)
at the top of every page, and a page break before a near block that would not fit in what is
left of the page; its print range is as before. The sheet *Production* (part A) follows it: the
blocks of `production.production_blocks` with the lengths in mm, rows 1 to 3 repeated, printed at
100 %. Every length heading says *rear to rear*, and `H9` and row 2 of *Production* say what the
lengths are measured from. *Cover*, *Change_Register*, *Notes* and the `CON_…` sheets keep their one
page. The independent verifier (`verify_plan.py`) states all of it again and refuses a plan whose
harness sheet is fitted to one page, prints at another scale, repeats other rows, breaks a page
elsewhere or holds another Production cell. With LibreOffice installed, the PDF of a plan is read
back."""

import io
import re
import shutil
import subprocess
import zipfile
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

import pytest

from harness_design_studio.core.generate.lengths import reference_lines
from harness_design_studio.core.model import Harness, Project
from harness_design_studio.core.outputs import harness_plan as hp
from harness_design_studio.core.outputs import verify_plan as vp
from harness_design_studio.core.outputs.ods import Cell
from harness_design_studio.core.outputs.production import PLAN_HEADER, production_blocks
from harness_design_studio.core.outputs.stamp import stamp_of
from harness_design_studio.core.verify import VerifyReport
from tests.plan_support import golden_project, read_plan
from tests.test_harness_plan import _code, plan, straight
from tests.test_verify_plan import has, plan_errors, table, with_content, with_entry

FLATSAT_W001 = "W001"


@pytest.fixture(scope="module")
def flatsat() -> Project:
    return golden_project("flatsat")


@pytest.fixture(scope="module")
def w001(flatsat: Project) -> bytes:
    return plan(flatsat, FLATSAT_W001)


def setups(data: bytes) -> dict[str, vp.PrintSetUp]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        content = vp.parse_xml("content.xml", z.read("content.xml"))
        styles = vp.parse_xml("styles.xml", z.read("styles.xml"))
    return vp.read_print(content, styles)


# ---- the scale -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("widths", "scale"),
    [
        ((448,), 61),  # W001 of flatsat: 276 / 448
        ((250, 22), 100),  # one far connector: narrower than the page
        ((276,), 100),
        ((277,), 99),  # LibreOffice prints 277 mm on two pages
        ((22,) * 200, 10),  # the smallest scale a reader takes
    ],
)
def test_the_scale_is_the_largest_whole_percent_one_page_wide(
    widths: tuple[int, ...], scale: int
) -> None:
    assert hp.print_scale(widths) == scale
    assert vp._scale([Fraction(w) for w in widths]) == scale


def test_the_harness_sheet_prints_at_a_fixed_scale_with_rows_6_to_9_repeated(w001: bytes) -> None:
    got = setups(w001)[FLATSAT_W001]
    assert got.fit is None and got.scale == "61%"
    assert got.heading == (5, 8)
    assert got.print_range == "H6:AB178"  # as before 4.1.0: H6 to the last far pin column
    assert sum(w for w in got.widths[7:28] if w is not None) == 448
    assert got.breaks  # 178 rows do not fit on one page at 61 %


def test_the_production_sheet_prints_at_100_with_rows_1_to_3_repeated(w001: bytes) -> None:
    got = setups(w001)[hp.PRODUCTION]
    assert got.fit is None and got.scale == "100%"
    assert got.heading == (0, 2)
    assert got.print_range.startswith("A1:K")
    assert sum(w for w in got.widths[:11] if w is not None) <= hp.PAGE_WIDTH_MM


def test_the_other_sheets_keep_their_one_page(w001: bytes) -> None:
    for name, got in setups(w001).items():
        if name in (FLATSAT_W001, hp.PRODUCTION):
            continue
        assert (got.heading, got.breaks, got.scale) == (None, [], None), name
        assert got.fit == (None if name == hp.ABOUT else "1"), name


# ---- the page breaks -----------------------------------------------------------------------------


def _pages(
    heights: list[Fraction], heading: tuple[int, int], breaks: tuple[int, ...], scale: int, end: int
) -> dict[int, int]:
    """The page of each row after the heading rows, as a reader paginates: a new page at a break
    and when a row does not fit any more."""
    room = Fraction(hp.PAGE_HEIGHT_MM * 100, scale) - sum(heights[heading[0] : heading[1] + 1])
    page, used, out = 0, Fraction(0), {}
    for r in range(heading[1] + 1, end + 1):
        if r in breaks or (used and used + heights[r] > room):
            page, used = page + 1, Fraction(0)
        used += heights[r]
        out[r] = page
    return out


@pytest.mark.parametrize("hid", ["W001", "W002", "W004", "W006"])
def test_breaks_only_before_blocks_and_no_block_that_fits_is_split(
    flatsat: Project, hid: str
) -> None:
    h = flatsat.harnesses[hid]
    book = hp.plan_workbook(flatsat, h, stamp_of(flatsat))
    want = vp.expected_plan(flatsat, h, stamp_of(flatsat), False).printed
    for sheet in book.sheets:
        if sheet.name not in want:
            continue
        blocks = want[sheet.name].blocks
        heading = sheet.repeat_rows
        assert heading is not None and sheet.breaks
        assert set(sheet.breaks) <= {first for first, _ in blocks}, sheet.name
        heights = hp.row_heights(sheet.rows, sheet.widths)
        room = Fraction(hp.PAGE_HEIGHT_MM * 100, sheet.page.scale) - sum(
            heights[heading[0] : heading[1] + 1]
        )
        pages = _pages(heights, heading, sheet.breaks, sheet.page.scale, blocks[-1][1])
        for first, last in blocks:
            if sum(heights[first : last + 1]) <= room:
                assert pages[first] == pages[last], (sheet.name, first, last)


def test_a_title_and_a_wrapped_heading_are_taller_than_a_line() -> None:
    title = Cell("W001-P1", style=hp.TITLE)
    head = Cell("Length [mm] rear to rear", style=hp.HEAD)
    note = Cell("one\ntwo\nthree", style=hp.NOTE)
    heights = hp.row_heights([(title,), (None, head), (note,), ()], [30, 16])
    assert heights == [hp.ROW_MM * Fraction(14, 10), hp.ROW_MM * 4, hp.ROW_MM * 3, hp.ROW_MM]


def test_a_block_that_does_not_fit_starts_a_page_and_a_page_with_nothing_on_it_takes_any() -> None:
    line = hp.ROW_MM
    heights = [line] * 200
    room_rows = int(Fraction(hp.PAGE_HEIGHT_MM) / line) - 2  # rows 0 and 1 repeat
    blocks = [(2, room_rows - 3), (room_rows - 2, room_rows + 10), (room_rows + 11, 199)]
    assert hp.page_breaks(heights, (0, 1), blocks, 100) == (room_rows - 2, room_rows + 11)
    assert hp.page_breaks(heights, (0, 1), [(2, 199)], 100) == ()  # longer than a page: no break


# ---- the length note and the headings (section 6.2) ----------------------------------------------


def test_the_length_note_and_every_length_heading_say_rear_to_rear(
    flatsat: Project, w001: bytes
) -> None:
    s = read_plan(w001)
    harness, production = s[FLATSAT_W001], s[hp.PRODUCTION]
    note = "\n".join(reference_lines(flatsat))
    assert harness[8, hp.COL_H].value == note  # H9
    assert production[1, 0].value == note  # A2
    heads = [(r, c) for (r, c), x in harness.items() if x.value == "Length [mm] rear to rear"]
    assert len({c for _, c in heads}) == 2  # column N of the blocks and S of the cable types
    assert not [x for x in harness.values() if x.value == "Length [mm]"]
    assert production[2, 7].value == "Length [mm] rear to rear"


# ---- the sheet Production (part A) --------------------------------------------------------------


def test_the_production_sheet_follows_the_harness_sheet(flatsat: Project, w001: bytes) -> None:
    s = read_plan(w001)
    names = list(s)
    assert names[names.index(FLATSAT_W001) + 1 : names.index(FLATSAT_W001) + 3] == [
        hp.PRODUCTION,
        hp.NOTES,
    ]
    cells = s[hp.PRODUCTION]
    assert cells[0, 0].value == "Production sheet of W001"
    assert [cells[2, c].value for c in range(11)] == list(PLAN_HEADER)
    blocks = production_blocks(flatsat, flatsat.harnesses[FLATSAT_W001])
    assert len(blocks) == 18 and sum(len(b.rows) for b in blocks) == 54
    row = 3
    for b in blocks:
        assert cells[row, 0].value == b.heading
        for r in b.rows:
            row += 1
            got = [cells[row, c].value if (row, c) in cells else "" for c in range(11)]
            want = [*r.values()]
            want[7] = round(want[7] * 1000, 1) if isinstance(want[7], float) else want[7]
            want[6] = float(want[6]) if isinstance(want[6], int) else want[6]
            assert got == want, (b.connector_id, r.pin)
            assert not any(cells[row, c].formula for c in range(11) if (row, c) in cells)
        row += 2


def test_the_splices_come_last_under_their_own_title() -> None:
    p = golden_project("splices")
    h = next(h for h in p.harnesses.values() if any(c.role == "splice" for c in h.connectors))
    cells = read_plan(plan(p, h.id))[hp.PRODUCTION]
    column_a = [x.value for (r, c), x in sorted(cells.items()) if c == 0 and x.value != ""]
    assert hp.SPLICE_BLOCK in column_a
    after = column_a[column_a.index(hp.SPLICE_BLOCK) + 1 :]
    splices = [b.heading for b in production_blocks(p, h) if b.splice]
    assert [x for x in after if x in splices] == splices
    assert vp.SPLICES == hp.SPLICE_BLOCK


def test_a_harness_named_production_gets_a_prefix() -> None:
    for hid in ("Production", "production"):
        assert hp.harness_sheet_name(Harness(id=hid, name="n")) == f"Harness_{hid}"
        assert vp.plan_sheet_name(Harness(id=hid, name="n")) == f"Harness_{hid}"
    p = straight()
    h = p.harnesses.pop("W001")
    p.harnesses["Production"] = h.model_copy(update={"id": "Production"})
    data = plan(p, "Production")
    assert {"Harness_Production", hp.PRODUCTION} <= set(read_plan(data))
    assert plan_errors(p, data, "Production") == []


def test_the_pigtail_colour_while_the_plan_colours_by_pin_code() -> None:
    p = _code(straight(), {"1": "Black", "2": "Brown"}, ["EX-MICROD-9-M"])
    data = plan(p)
    cells = read_plan(data)[hp.PRODUCTION]
    heads = [cells[2, c].value for c in range(12)]
    assert heads[5:8] == ["Colour", hp.PIGTAIL_HEAD, "AWG"]
    rows = {(cells[r, 0].value, cells[r, 2].value): r for (r, c) in cells if c == 2 and r > 2}
    assert cells[rows["1", "W001-001"], 6].value == "Black"  # W001-P1 pin 1, from the code
    assert cells[rows["3", "W001-003"], 6].value == "to fill in"  # pin 3 is not in the code
    assert plan_errors(p, data) == []
    assert hp.PIGTAIL_HEAD not in [
        x.value for x in read_plan(plan(straight()))[hp.PRODUCTION].values()
    ]


# ---- the verifier --------------------------------------------------------------------------------


def _with_styles(data: bytes, fn: Callable[[str], str]) -> bytes:
    return with_entry(data, "styles.xml", fn)


def _in_table(name: str, fn: Callable[[str], str]) -> Callable[[str], str]:
    def edit(text: str) -> str:
        m = table(text, name)
        return text[: m.start()] + fn(m.group()) + text[m.end() :]

    return edit


def _break_style(text: str) -> str:
    m = re.search(
        r'<style:style style:name="([^"]+)" style:family="table-row">'
        r'<style:table-row-properties fo:break-before="page"',
        text,
    )
    assert m is not None
    return m.group(1)


def test_a_plan_as_written_has_no_print_finding(flatsat: Project, w001: bytes) -> None:
    assert plan_errors(flatsat, w001) == []


def test_the_verifier_refuses_a_harness_sheet_fitted_to_one_page(
    flatsat: Project, w001: bytes
) -> None:
    bad = _with_styles(
        w001, lambda t: t.replace('style:scale-to="61%"', 'style:scale-to-pages="1"')
    )
    found = plan_errors(flatsat, bad)
    assert has(found, "out_plan", "is fitted to 1 page(s)")
    assert has(found, "out_plan", "prints at no fixed scale, the design gives 61%")


def test_the_verifier_refuses_another_scale(flatsat: Project, w001: bytes) -> None:
    bad = _with_styles(w001, lambda t: t.replace('style:scale-to="61%"', 'style:scale-to="70%"'))
    assert has(plan_errors(flatsat, bad), "out_plan", "prints at 70%, the design gives 61%")


def test_the_verifier_refuses_heading_rows_that_are_not_repeated(
    flatsat: Project, w001: bytes
) -> None:
    def unwrap(sheet: str) -> str:
        return sheet.replace("<table:table-header-rows>", "").replace(
            "</table:table-header-rows>", ""
        )

    bad = with_content(w001, _in_table(FLATSAT_W001, unwrap))
    assert has(
        plan_errors(flatsat, bad),
        "out_plan",
        "repeats no rows on every page, the design gives rows 6 to 9",
    )
    bad = with_content(w001, _in_table(hp.PRODUCTION, unwrap))
    assert has(plan_errors(flatsat, bad), "out_plan", "the design gives rows 1 to 3")


def test_the_verifier_refuses_a_missing_or_a_moved_break(flatsat: Project, w001: bytes) -> None:
    def drop(text: str) -> str:
        name = _break_style(text)
        return _in_table(FLATSAT_W001, lambda s: s.replace(f' table:style-name="{name}"', "", 1))(
            text
        )

    found = plan_errors(flatsat, with_content(w001, drop))
    assert has(found, "out_plan", f"sheet '{FLATSAT_W001}' has page breaks before the rows")

    def add(text: str) -> str:  # a break before the row "Harness Side" of the first block
        name = _break_style(text)

        def edit(sheet: str) -> str:
            m = re.search(r"<table:table-row>(?=(?:(?!</table:table-row>).)*Harness Side)", sheet)
            assert m is not None
            return (
                sheet[: m.start()]
                + f'<table:table-row table:style-name="{name}">'
                + sheet[m.end() :]
            )

        return _in_table(FLATSAT_W001, edit)(text)

    assert has(plan_errors(flatsat, with_content(w001, add)), "out_plan", "which starts no block")


def test_the_verifier_refuses_another_print_range(flatsat: Project, w001: bytes) -> None:
    bad = with_content(w001, lambda t: t.replace("W001.H6:W001.AB178", "W001.A1:W001.AB178", 1))
    assert has(
        plan_errors(flatsat, bad),
        "out_plan",
        "prints the range A1:AB178, the design gives H6:AB178",
    )


def test_the_verifier_refuses_another_production_cell_or_none(
    flatsat: Project, w001: bytes
) -> None:
    blocks = production_blocks(flatsat, flatsat.harnesses[FLATSAT_W001])
    label = blocks[0].rows[0].label
    bad = with_content(
        w001,
        _in_table(
            hp.PRODUCTION,
            lambda s: s.replace(f"<text:p>{label}</text:p>", "<text:p>W001-999</text:p>", 1),
        ),
    )
    assert has(
        plan_errors(flatsat, bad), "out_plan", f"sheet '{hp.PRODUCTION}', cell J5 holds 'W001-999'"
    )
    gone = with_content(w001, lambda t: t.replace(table(t, hp.PRODUCTION).group(), "", 1))
    assert has(plan_errors(flatsat, gone), "out_plan", f"the sheet '{hp.PRODUCTION}' is missing")


def test_the_verifier_s_estimate_is_the_builder_s(flatsat: Project) -> None:
    """The verifier's own copy of the row heights and the breaks gives the builder's breaks on
    every harness of flatsat."""
    for h in flatsat.harnesses.values():
        book = hp.plan_workbook(flatsat, h, stamp_of(flatsat))
        expected = vp.expected_plan(flatsat, h, stamp_of(flatsat), False)
        grids = dict(expected.sheets)
        for sheet in book.sheets:
            if sheet.name not in expected.printed:
                continue
            want = expected.printed[sheet.name]
            widths = [Fraction(w) for w in sheet.widths]
            assert vp._heights(grids[sheet.name], want.looks, widths)[: len(sheet.rows)] == (
                hp.row_heights(sheet.rows, sheet.widths)
            ), (h.id, sheet.name)
            assert vp._breaks(
                vp._heights(grids[sheet.name], want.looks, widths), want, sheet.page.scale
            ) == list(sheet.breaks), (h.id, sheet.name)


def test_the_plan_check_reads_the_print_set_up_only_from_the_plan(
    flatsat: Project, w001: bytes
) -> None:
    r = VerifyReport()
    vp.check_plan(r, flatsat, flatsat.harnesses[FLATSAT_W001], "x_plan.ods", w001, False)
    assert r.errors == []


# ---- a real reader --------------------------------------------------------------------------------

SOFFICE, PDFTOTEXT = shutil.which("soffice"), shutil.which("pdftotext")


@pytest.mark.skipif(
    SOFFICE is None or PDFTOTEXT is None, reason="LibreOffice or pdftotext is not installed"
)
def test_libreoffice_prints_both_sheets_one_page_wide_with_their_headings(
    tmp_path: Path, w001: bytes
) -> None:
    assert SOFFICE is not None and PDFTOTEXT is not None
    src = tmp_path / "W001_plan.ods"
    src.write_bytes(w001)
    subprocess.run(
        [SOFFICE, f"-env:UserInstallation={(tmp_path / 'profile').as_uri()}", "--headless",
         "--convert-to", "pdf", "--outdir", str(tmp_path), str(src)],
        capture_output=True, check=True, timeout=180,
    )  # fmt: skip
    text = subprocess.run(
        [PDFTOTEXT, "-layout", str(tmp_path / "W001_plan.pdf"), "-"],
        capture_output=True, check=True, timeout=60, text=True,
    ).stdout  # fmt: skip
    pages = text.split("\f")
    harness = [p for p in pages if "Harness Side" in p or "Further wires" in p]
    production = [p for p in pages if "Production sheet of W001" in p]
    assert len(harness) >= 2 and len(production) >= 2
    assert all("VERSION: v" in p for p in harness)  # row 6 on every page
    assert all("Shield group" in p and "Pin" in p for p in production)  # one page wide
    assert all("Lengths run from the rear of a connector" in p for p in production)
