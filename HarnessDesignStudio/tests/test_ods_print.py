# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-OUT-01: the print set-up of the `.ods` writer (`core/outputs/ods.py`, design of 4.1.0
`docs/ait/DESIGN_4.1_PRODUCTION_SHEET.md` section 5.1, pull request 4): a fixed scale
(`Page.scale`), heading rows repeated on every printed page (`Sheet.repeat_rows`) and page breaks
(`Sheet.breaks`). Each is off by default and writes nothing while off (the golden digest of
`tests/test_ods.py` stays); this file has a sample of its own that uses all three, its digest, and
reads what is written back with an XML parser. When LibreOffice is installed, it reads the sample
too."""

import hashlib
import io
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from harness_design_studio.core.outputs import ods, verify_plan
from harness_design_studio.core.outputs.ods import Cell, Page, Sheet, Style, Workbook
from tests.test_ods import NS, _q, cell_text, members, parse, sample

# The SHA-256 of `write_ods(print_sample())`. Make it again on purpose only, and say in the commit
# what changed in the bytes and why.
GOLDEN = "77fb5fd8b8003bf4923ea737b4abc73dc4893fdfcee1e2658b5e86f869942810"

HEAD = Style(bold=True, background="#9bc2e6", border=True)
# 0-based rows of the sheet "Print": the heading rows, the breaks, the run of equal rows around
# the break at 65 (rows 60 to 69 hold the same cells)
HEADING = (1, 3)
BREAKS = (4, 40, 65, 100)
SAME = range(60, 70)
ROWS = 140


def _body(r: int) -> tuple[Cell | None, ...]:
    if r in SAME:
        return (Cell("same"), Cell("row"))
    return (Cell(r - 3), Cell(f"signal {r - 3}"), Cell(0.5 + r))


def print_sample() -> Workbook:
    """Four sheets: "Print" with a fixed scale, heading rows and breaks (one right after the
    heading rows, one inside a run of equal rows); "Top" with equal rows before, inside and after
    its heading rows and equal empty rows on both sides of its break; "Edge" with a break before
    its first heading row and one right after its last; "Fit" fitted to one page, as before."""
    rows: list[tuple[Cell | None, ...]] = [
        (Cell("Print sample", style=HEAD, cols=3), None, None),
        (Cell("System"), Cell("SYS")),
        (Cell("Harness"), Cell("W001")),
        (Cell("Pin", style=HEAD), Cell("Signal", style=HEAD), Cell("Length", style=HEAD)),
    ]
    rows += [_body(r) for r in range(4, ROWS)]
    printed = Sheet(
        "Print",
        rows=tuple(rows),
        widths=(20, 60, 25),
        page=Page("A4", landscape=True, scale=61, header="print sample", footer="stamp 0123abcd"),
        print_range=f"A1:C{ROWS}",
        repeat_rows=HEADING,
        breaks=BREAKS,
    )
    h = (Cell("h"),)
    top = Sheet(
        "Top",
        rows=((Cell("a"),), h, h, h, h, (), (), (), (), (Cell("z"),)),
        page=Page("A4", scale=100),
        repeat_rows=(2, 3),
        breaks=(7,),
    )
    edge = Sheet("Edge", rows=((Cell("a"),), h, h, (Cell("b"),)), repeat_rows=(1, 2), breaks=(1, 3))
    fit = Sheet("Fit", rows=((Cell("x"),), (Cell("y"),)), page=Page("A4", fit=True))
    return Workbook(
        "print sample", (printed, top, edge, fit), generator="Harness Design Studio test"
    )


# ---- a reader of the rows -------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    """One row of a sheet as written, repeats expanded: whether it is inside
    `table:table-header-rows`, its row style's name, the texts of its cells, and the index of the
    `table:table-row` element it was written in (equal for rows of one repeated run)."""

    header: bool
    style: str
    texts: tuple[str, ...]
    element: int


def rows_of(content: ET.Element, sheet: str) -> list[Row]:
    (table,) = [t for t in content.iter(_q("table:table")) if t.get(_q("table:name")) == sheet]
    out: list[Row] = []
    elements = 0
    for child in table:
        if child.tag == _q("table:table-header-rows"):
            group, header = list(child), True
        elif child.tag == _q("table:table-row"):
            group, header = [child], False
        else:
            continue
        for row in group:
            assert row.tag == _q("table:table-row")
            texts = tuple(cell_text(c) for c in row)
            for _ in range(int(row.get(_q("table:number-rows-repeated"), "1"))):
                out.append(Row(header, row.get(_q("table:style-name"), ""), texts, elements))
            elements += 1
    return out


def row_styles(content: ET.Element) -> dict[str, dict[str, str]]:
    """The automatic row styles: their name and the attributes of their row properties."""
    out = {}
    for s in content.iter(_q("style:style")):
        if s.get(_q("style:family")) == "table-row":
            (props,) = s.findall("style:table-row-properties", NS)
            out[s.get(_q("style:name"), "")] = {k.split("}")[1]: v for k, v in props.attrib.items()}
    return out


def page_of(files: dict[str, bytes], sheet: str) -> ET.Element:
    """The page layout properties of a sheet: table style, master page, page layout."""
    content, styles = parse(files["content.xml"]), parse(files["styles.xml"])
    (table,) = [t for t in content.iter(_q("table:table")) if t.get(_q("table:name")) == sheet]
    master = {
        s.get(_q("style:name")): s.get(_q("style:master-page-name"))
        for s in content.iter(_q("style:style"))
        if s.get(_q("style:family")) == "table"
    }[table.get(_q("table:style-name"))]
    layout = {
        m.get(_q("style:name")): m.get(_q("style:page-layout-name"))
        for m in styles.iter(_q("style:master-page"))
    }[master]
    (props,) = [
        p.find("style:page-layout-properties", NS)
        for p in styles.iter(_q("style:page-layout"))
        if p.get(_q("style:name")) == layout
    ]
    assert props is not None
    return props


def broken(rows: list[Row], styles: dict[str, dict[str, str]]) -> list[int]:
    return [i for i, r in enumerate(rows) if styles.get(r.style, {}).get("break-before") == "page"]


# ---- the bytes ------------------------------------------------------------------------------


def test_the_golden_digest_of_the_print_sample() -> None:
    data = ods.write_ods(print_sample())
    assert data == ods.write_ods(print_sample())
    assert hashlib.sha256(data).hexdigest() == GOLDEN


def test_a_sheet_without_them_writes_none_of_them() -> None:
    files = members(ods.write_ods(sample()))
    content, styles = files["content.xml"].decode(), files["styles.xml"].decode()
    assert "table-header-rows" not in content and 'style:family="table-row"' not in content
    assert "table:style-name" not in "".join(re.findall(r"<table:table-row[^>]*>", content))
    assert "style:scale-to=" not in styles


# ---- the heading rows -----------------------------------------------------------------------


def test_the_heading_rows_hold_exactly_the_rows_asked() -> None:
    content = parse(members(ods.write_ods(print_sample()))["content.xml"])
    rows = rows_of(content, "Print")
    assert len(rows) == ROWS
    assert [i for i, r in enumerate(rows) if r.header] == list(range(HEADING[0], HEADING[1] + 1))
    assert [r.texts for r in rows[1:4]] == [
        ("System", "SYS"),
        ("Harness", "W001"),
        ("Pin", "Signal", "Length"),
    ]
    assert rows[0].texts[0] == "Print sample" and rows[4].texts == ("1", "signal 1", "4.5")
    group = next(content.iter(_q("table:table-header-rows")))
    assert [cell_text(r[0]) for r in group] == ["System", "Harness", "Pin"]
    assert [i for i, r in enumerate(rows_of(content, "Top")) if r.header] == [2, 3]
    assert [i for i, r in enumerate(rows_of(content, "Edge")) if r.header] == [1, 2]


def test_equal_rows_are_merged_inside_the_heading_rows_and_not_across_them() -> None:
    content = parse(members(ods.write_ods(print_sample()))["content.xml"])
    top = rows_of(content, "Top")
    assert [r.texts for r in top] == [("a",), *[("h",)] * 4, *[("",)] * 4, ("z",)]
    # rows 3 and 4 are equal and inside the heading rows: one run of 2, within the group
    assert top[2].element == top[3].element and top[2].header and top[3].header
    # the equal row 2 before the heading rows and row 5 after them stay apart
    assert len({top[1].element, top[2].element, top[4].element}) == 3
    (table,) = [t for t in content.iter(_q("table:table")) if t.get(_q("table:name")) == "Top"]
    (group,) = table.iter(_q("table:table-header-rows"))
    assert [r.get(_q("table:number-rows-repeated")) for r in group] == ["2"]


# ---- the breaks -----------------------------------------------------------------------------


def test_the_break_rows_carry_a_style_that_starts_a_page() -> None:
    content = parse(members(ods.write_ods(print_sample()))["content.xml"])
    styles = row_styles(content)
    assert styles == {
        "ro1": {"break-before": "page", "use-optimal-row-height": "true"},
    }
    rows = rows_of(content, "Print")
    assert broken(rows, styles) == list(BREAKS)
    assert {r.style for i, r in enumerate(rows) if i not in BREAKS} == {""}
    assert broken(rows_of(content, "Top"), styles) == [7]
    assert broken(rows_of(content, "Edge"), styles) == [1, 3]


def test_a_break_right_after_the_heading_rows_and_before_the_first() -> None:
    content = parse(members(ods.write_ods(print_sample()))["content.xml"])
    styles = row_styles(content)
    rows = rows_of(content, "Print")
    # row 5 (0-based 4) starts a page and is not inside the heading rows
    assert rows[4].style == "ro1" and not rows[4].header and rows[3].header
    edge = rows_of(content, "Edge")
    # a break before the first heading row is written on that row, inside the group
    assert edge[1].header and edge[1].style == "ro1" and not edge[0].header
    # the break row does not join the equal row after it, which stays in the heading rows
    assert edge[1].texts == edge[2].texts and edge[1].element != edge[2].element
    assert edge[2].header and edge[2].style == ""
    # a break right after the last heading row is outside the group
    assert edge[3].style == "ro1" and not edge[3].header
    assert broken(edge, styles) == [1, 3]


def test_equal_rows_around_a_break_are_not_merged_across_it() -> None:
    content = parse(members(ods.write_ods(print_sample()))["content.xml"])
    rows = rows_of(content, "Print")
    assert {rows[i].texts for i in SAME} == {("same", "row")}
    runs = [rows[i].element for i in SAME]
    # 60 to 64 one run of 5, 65 a row of its own (the break), 66 to 69 a run of 4
    assert runs[:5] == [runs[0]] * 5 and runs[6:] == [runs[6]] * 4
    assert len({runs[0], runs[5], runs[6]}) == 3
    assert rows[65].style == "ro1" and rows[64].style == "" and rows[66].style == ""
    top = rows_of(content, "Top")
    # empty rows 6 and 7 one run, the break at 8 a row of its own, the empty row 9 apart again
    assert top[5].element == top[6].element
    assert len({top[6].element, top[7].element, top[8].element}) == 3
    assert top[7].style == "ro1" and top[8].style == ""


# ---- the scale ------------------------------------------------------------------------------


def test_a_fixed_scale_is_written_as_scale_to() -> None:
    files = members(ods.write_ods(print_sample()))
    props = page_of(files, "Print")
    assert props.get(_q("style:scale-to")) == "61%"
    assert props.get(_q("style:scale-to-pages")) is None
    assert props.get(_q("style:print-orientation")) == "landscape"
    assert page_of(files, "Top").get(_q("style:scale-to")) == "100%"
    fit = page_of(files, "Fit")
    assert fit.get(_q("style:scale-to-pages")) == "1" and fit.get(_q("style:scale-to")) is None


@pytest.mark.parametrize("scale", [10, 61, 100, 400])
def test_the_scales_a_reader_takes(scale: int) -> None:
    book = Workbook("t", (Sheet("S", rows=((Cell("a"),),), page=Page(scale=scale)),))
    assert f'style:scale-to="{scale}%"' in members(ods.write_ods(book))["styles.xml"].decode()


# ---- what the writer refuses ----------------------------------------------------------------


def _sheet(**kw: object) -> Workbook:
    rows = tuple((Cell(f"r{r}"),) for r in range(10))
    return Workbook("t", (Sheet("S", rows=rows, **kw),))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("book", "message"),
    [
        (_sheet(page=Page(fit=True, scale=61)), "either fitted to one page or .* fixed scale"),
        (_sheet(page=Page(scale=9)), "not from 10 to 400"),
        (_sheet(page=Page(scale=401)), "not from 10 to 400"),
        (_sheet(page=Page(scale=-5)), "not from 10 to 400"),
        (_sheet(page=Page(scale=61.5)), "not a whole percent"),  # type: ignore[arg-type]
        (_sheet(page=Page(scale=True)), "not a whole percent"),
        (_sheet(repeat_rows=(3, 2)), "heading rows"),
        (_sheet(repeat_rows=(-1, 2)), "heading rows"),
        (_sheet(repeat_rows=(8, 10)), "heading rows"),
        (_sheet(repeat_rows=(1,)), "heading rows"),  # type: ignore[arg-type]
        (_sheet(breaks=(0,)), "page breaks"),
        (_sheet(breaks=(10,)), "page breaks"),
        (_sheet(breaks=(5, 3)), "not rising"),
        (_sheet(breaks=(3, 3)), "not rising"),
        (_sheet(breaks=(True,)), "page breaks"),
        (_sheet(repeat_rows=(1, 3), breaks=(2,)), "row 2 lies inside the heading rows 1 to 3"),
        (_sheet(repeat_rows=(1, 3), breaks=(3,)), "row 3 lies inside the heading rows 1 to 3"),
    ],
)
def test_the_writer_refuses_a_print_set_up_it_cannot_write(book: Workbook, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ods.write_ods(book)


@pytest.mark.parametrize(("head", "breaks"), [((1, 3), (1,)), ((1, 3), (4,)), ((0, 9), ())])
def test_breaks_at_the_edges_of_the_heading_rows_are_taken(
    head: tuple[int, int], breaks: tuple[int, ...]
) -> None:
    content = parse(members(ods.write_ods(_sheet(repeat_rows=head, breaks=breaks)))["content.xml"])
    rows = rows_of(content, "S")
    assert [r.texts for r in rows] == [(f"r{r}",) for r in range(10)]
    assert [i for i, r in enumerate(rows) if r.header] == list(range(head[0], head[1] + 1))
    assert broken(rows, row_styles(content)) == list(breaks)


# ---- the readers of the outputs -------------------------------------------------------------


def test_the_verifiers_reader_reads_the_cells_through_the_new_elements() -> None:
    """`verify_plan.read_cells` (the check of the harness plan) reads a cell in the heading rows
    and after a break at its row."""
    data = members(ods.write_ods(print_sample()))["content.xml"]
    got = dict(verify_plan.read_cells(verify_plan.parse_xml("content.xml", data)).sheets)
    printed = got["Print"]
    assert printed[1, 0].shown == "System" and printed[3, 2].shown == "Length"
    assert printed[4, 1].shown == "signal 1" and printed[65, 0].shown == "same"
    assert printed[ROWS - 1, 1].shown == f"signal {ROWS - 4}"
    assert got["Top"][9, 0].shown == "z" and got["Edge"][3, 0].shown == "b"


# ---- a real reader --------------------------------------------------------------------------

SOFFICE = shutil.which("soffice")


def _convert(src: Path, to: str, out: Path) -> Path:
    assert SOFFICE is not None
    subprocess.run(
        [
            SOFFICE,
            f"-env:UserInstallation={(out / 'profile').as_uri()}",
            "--headless",
            "--convert-to",
            to,
            "--outdir",
            str(out),
            str(src),
        ],
        capture_output=True,
        check=True,
        timeout=180,
    )
    return out / f"{src.stem}.{to}"


@pytest.mark.skipif(SOFFICE is None, reason="LibreOffice (soffice) is not installed")
def test_libreoffice_keeps_the_print_set_up(tmp_path: Path) -> None:
    """LibreOffice's own flat file of the sample keeps the scale, the heading rows and the breaks;
    its PDF has a page for each part between two breaks."""
    src = tmp_path / "print.ods"
    src.write_bytes(ods.write_ods(print_sample()))
    flat = _convert(src, "fods", tmp_path).read_text(encoding="utf-8")
    assert 'style:scale-to="61%"' in flat
    assert flat.count("<table:table-header-rows>") == 3
    breaks = {
        m.group(1)
        for m in re.finditer(
            r'<style:style style:name="([^"]+)" style:family="table-row">'
            r'\s*<style:table-row-properties[^>]*fo:break-before="page"',
            flat,
        )
    }
    assert breaks
    written = sum(
        len(re.findall(rf'<table:table-row table:style-name="{name}"', flat)) for name in breaks
    )
    assert written == len(BREAKS) + 3
    pdf = _convert(src, "pdf", tmp_path).read_bytes()
    # every part between two breaks fits on a page: Print 5 pages, Top 2, Edge 3, Fit 1
    assert len(re.findall(rb"/Type\s*/Page(?![a-z])", pdf)) == 11


def test_the_sample_reads_with_the_xml_parser_of_the_standard_library() -> None:
    with zipfile.ZipFile(io.BytesIO(ods.write_ods(print_sample()))) as z:
        for name in ("content.xml", "styles.xml"):
            ET.fromstring(z.read(name))  # noqa: S314
