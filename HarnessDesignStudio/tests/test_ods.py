# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-OUT-01: our own writer of OpenDocument spreadsheets (`core/outputs/ods.py`, design of 3.0.0
`docs/ait/DESIGN_3.0_HARNESS_PLAN.md` sections 7.2, 7.3 and 8, pull request 2): the same model gives
the same bytes (twice, in other processes, in other time zones, on a Windows `sys.platform`); the
package rules of section 7.3; what is written reads back as given; the closed formula list; the
escaping; the imports; and, when LibreOffice is installed, what a real reader shows."""

import csv
import hashlib
import io
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from harness_design_studio.core.outputs import ods
from harness_design_studio.core.outputs.ods import Cell, Condition, Page, Sheet, Style, Workbook

ROOT = Path(__file__).resolve().parents[1]
NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
    "meta": "urn:oasis:names:tc:opendocument:xmlns:meta:1.0",
    "dc": "http://purl.org/dc/elements/1.1/",
    "manifest": "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0",
}
ORDER = ["mimetype", "META-INF/manifest.xml", "meta.xml", "styles.xml", "content.xml"]
# The SHA-256 of `write_ods(sample())`. A change of any byte the writer writes changes it: make it
# again on purpose only, and say in the commit what changed in the bytes and why.
GOLDEN = "73bd22a2a939b52b9844145d66b32c155441ea4d6e5cd96e4d43783cf1a307a1"

HEAD = Style(bold=True, background="#9bc2e6", border=True, align="center")
HAND = Style(colour="#ce181e", background="#eeeeee")
YELLOW = Style(background="#ffff99")
RED_BOLD = Style(bold=True, colour="#ce181e")
TRICKY = "a < b & \"c\" 'd' >  two  spaces\tand a tab\nsecond line \x01\x0b"
CON = "CON_DEV2-J4711"


def sample() -> Workbook:
    """A small workbook with every feature of the writer, in the shapes of section 3."""
    con = Sheet(
        CON,
        rows=(
            (Cell("Device"), Cell("DEV2")),
            (Cell("Connector ID"), Cell("J4711")),
            (Cell("Link to ICD"), Cell("ICD of DEV2", link="https://example.org/icd?a=1&b=2")),
            (),
            (
                Cell("Pinout", style=HEAD),
                Cell("Function", style=HEAD),
                Cell("Direction", style=HEAD),
            ),
            (Cell(1), Cell("PWR_28V"), Cell("PWR")),
            (Cell(2), Cell("RTN"), Cell("GND")),
            (Cell("A1"), Cell("TX+"), Cell("OUT")),
        ),
        widths=(30, 40, 20),
    )
    notes = Sheet(
        "Notes",
        rows=((Cell("Pin"), Cell("Color")), (Cell(1), Cell("Black")), (Cell(2), Cell("Brown"))),
    )
    q = f"$'{CON}'"
    harness = Sheet(
        "W001",
        rows=(
            (Cell("Harness W001", style=HEAD, cols=4), None, None, None, Cell("=1+2"), Cell("+5V")),
            (
                Cell("Device side", style=HEAD, rows=2),
                Cell(TRICKY),
                None,
                None,
                Cell(0.0001),
                Cell(1e16),
            ),
            (None, Cell(-0.0), Cell(12.5), Cell(1200), Cell(-3)),
            (
                Cell(1, formula=f"[{q}.A6]"),
                Cell("PWR_28V", formula=f"[{q}.B6]"),
                Cell("PWR", formula=f"[{q}.C6]"),
                Cell("PWR", formula='IF([.C4]="IN";"OUT";IF([.C4]="OUT";"IN";[.C4]))'),
                Cell("Black", formula='IF([.A4]="";"";VLOOKUP([.A4];[$Notes.$A$2:.$B$3];2;0))'),
                Cell(250.5, style=HAND),
                Cell("S1", style=HAND),
            ),
            (
                Cell(2, formula=f"[{q}.A7]"),
                Cell("RTN", formula=f"[{q}.B7]"),
                Cell("GND", formula=f"[{q}.C7]"),
                Cell("GND", formula='IF([.C5]="IN";"OUT";IF([.C5]="OUT";"IN";[.C5]))'),
                Cell(
                    "", formula='IF(ISNA(MATCH([.A5];[.A4:.A4];0));"";MATCH([.A5];[.A4:.A4];0)+3)'
                ),
                Cell(250.5, formula="[.F4]"),
            ),
            (Cell("A1", style=YELLOW), *[Cell(style=YELLOW)] * 6),
            (Cell("Sum"), Cell(501, formula='SUMIF([.G4:.G5];"S1";[.F4:.F5])/1+[.F5]')),
            (
                Cell("Part link", link="https://example.org/part/42"),
                Cell("mail", link="mailto:a@example.org"),
            ),
            (Cell(f"{CON} [J4711]", formula=f'[{q}.A1]&" ["&[{q}.B2]&"]"'),),
        ),
        widths=(15, 25, 0, 20, 20, 20, 20),
        page=Page(
            paper="A4",
            landscape=True,
            fit=True,
            header="W001 plan",
            footer="harness-design-studio test model 0123abcd",
        ),
        print_range="A1:G9",
        conditions=(
            Condition(
                "C4:D5", 'OR(AND([.C4]="GND";[.D4]="PWR");AND([.D4]="GND";[.C4]="PWR"))', RED_BOLD
            ),
            Condition(
                "A12:B13", '[.A12]="x"', RED_BOLD
            ),  # beyond the written rows: cells are added
        ),
    )
    return Workbook(
        "W001 harness plan", (harness, notes, con), generator="Harness Design Studio test"
    )


# ---- a reader of what the writer wrote ------------------------------------------------------


def parse(data: bytes | str) -> ET.Element:
    """The writer's own XML, written by this test: not data from elsewhere."""
    return ET.fromstring(data)  # noqa: S314


def _q(tag: str) -> str:
    prefix, name = tag.split(":")
    return f"{{{NS[prefix]}}}{name}"


def _text(el: ET.Element) -> str:
    out = [el.text or ""]
    for child in el:
        if child.tag == _q("text:s"):
            out.append(" " * int(child.get(_q("text:c"), "1")))
        elif child.tag == _q("text:tab"):
            out.append("\t")
        else:
            out.append(_text(child))
        out.append(child.tail or "")
    return "".join(out)


def cell_text(el: ET.Element) -> str:
    return "\n".join(_text(p) for p in el.findall("text:p", NS))


def read(data: bytes) -> dict[str, dict[str, ET.Element]]:
    """Each sheet's cells by address, repeats expanded; covered cells are left out."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = parse(z.read("content.xml"))
    sheets: dict[str, dict[str, ET.Element]] = {}
    for table in root.iter(_q("table:table")):
        cells: dict[str, ET.Element] = {}
        r = 0
        for row in table.findall("table:table-row", NS):
            for _ in range(int(row.get(_q("table:number-rows-repeated"), "1"))):
                c = 0
                for el in row:
                    n = int(el.get(_q("table:number-columns-repeated"), "1"))
                    for _ in range(n):
                        if el.tag == _q("table:table-cell"):
                            cells[f"{ods.column(c)}{r + 1}"] = el
                        c += 1
                r += 1
        sheets[table.get(_q("table:name"), "")] = cells
    return sheets


def members(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist()}


# ---- determinism ----------------------------------------------------------------------------

_CHILD = """
import hashlib, sys
sys.path.insert(0, {tests!r})
sys.path.insert(0, {src!r})
from tests.test_ods import sample
from harness_design_studio.core.outputs.ods import write_ods
print(hashlib.sha256(write_ods(sample())).hexdigest())
"""


def test_the_same_model_gives_the_same_bytes_twice() -> None:
    assert ods.write_ods(sample()) == ods.write_ods(sample())


@pytest.mark.parametrize(
    ("tz", "seed"), [("UTC", "0"), ("Pacific/Chatham", "1"), ("America/St_Johns", "12345")]
)
def test_the_same_bytes_in_another_process_and_time_zone(tz: str, seed: str) -> None:
    code = _CHILD.format(tests=str(ROOT), src=str(ROOT / "src"))
    env = {**os.environ, "TZ": tz, "PYTHONHASHSEED": seed}
    out = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        env=env,
        check=True,
        timeout=120,
    )
    assert out.stdout.strip() == hashlib.sha256(ods.write_ods(sample())).hexdigest()


def test_the_same_bytes_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """`ZipInfo` takes `create_system` from `sys.platform` (0 on Windows); the writer sets it."""
    here = ods.write_ods(sample())
    monkeypatch.setattr(sys, "platform", "win32")
    assert zipfile.ZipInfo("x").create_system == 0
    assert ods.write_ods(sample()) == here


def test_the_golden_digest_of_the_sample() -> None:
    assert hashlib.sha256(ods.write_ods(sample())).hexdigest() == GOLDEN


# ---- the package (section 7.3) --------------------------------------------------------------


def test_the_entries_their_order_and_their_header_fields() -> None:
    data = ods.write_ods(sample())
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos = z.infolist()
        assert z.testzip() is None
    assert [i.filename for i in infos] == ORDER
    for i in infos:
        assert i.compress_type == zipfile.ZIP_STORED, i.filename
        assert i.date_time == (1980, 1, 1, 0, 0, 0), i.filename
        assert i.create_system == 3, i.filename
        assert i.external_attr == 0o644 << 16, i.filename
        assert i.extra == b"" and i.comment == b"", i.filename


def test_mimetype_comes_first_stored_with_no_extra_field() -> None:
    data = ods.write_ods(sample())
    assert data[:4] == b"PK\x03\x04"
    assert int.from_bytes(data[8:10], "little") == 0  # stored
    assert int.from_bytes(data[26:28], "little") == len("mimetype")
    assert int.from_bytes(data[28:30], "little") == 0  # no extra field
    assert data[30:38] == b"mimetype"
    assert data[38 : 38 + len(ods.MIMETYPE)] == ods.MIMETYPE.encode("ascii")


def test_the_manifest_lists_every_entry() -> None:
    files = members(ods.write_ods(sample()))
    root = parse(files["META-INF/manifest.xml"])
    entries = {
        e.get(_q("manifest:full-path")): e.get(_q("manifest:media-type"))
        for e in root.findall("manifest:file-entry", NS)
    }
    # ODF: every file but `mimetype` and the manifest itself, and "/" for the package
    assert entries == {
        "/": ods.MIMETYPE,
        "meta.xml": "text/xml",
        "styles.xml": "text/xml",
        "content.xml": "text/xml",
    }
    assert set(files) - {"mimetype", "META-INF/manifest.xml"} == set(entries) - {"/"}


def test_meta_holds_the_title_and_the_generator_only() -> None:
    root = parse(members(ods.write_ods(sample()))["meta.xml"])
    meta = root.find("office:meta", NS)
    assert meta is not None
    assert [(c.tag, c.text) for c in meta] == [
        (_q("meta:generator"), "Harness Design Studio test"),
        (_q("dc:title"), "W001 harness plan"),
    ]
    default = Workbook("t", (Sheet("A"),))
    assert default.generator.startswith("Harness Design Studio ")


def test_every_entry_is_utf8_xml_without_pretty_printing() -> None:
    for name, data in members(ods.write_ods(sample())).items():
        if name == "mimetype":
            continue
        text = data.decode("utf-8")
        assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n'), name
        body = text.split("\n", 1)[1]
        assert "\n" not in body and "  <" not in body, name
        parse(data)  # well formed


def test_automatic_styles_are_numbered_in_the_order_of_the_walk() -> None:
    content = members(ods.write_ods(sample()))["content.xml"].decode("utf-8")
    names = [s.split('"')[0] for s in content.split('<style:style style:name="')[1:]]
    for prefix in ("co", "ta", "ce"):
        got = [n for n in names if n.startswith(prefix)]
        assert got == [f"{prefix}{i}" for i in range(1, len(got) + 1)], got
    first = read(ods.write_ods(sample()))["W001"]["A1"]
    assert first.get(_q("table:style-name")) == "ce1"  # the first styled cell of the walk


# ---- reading back ---------------------------------------------------------------------------


def test_cells_read_back_as_given() -> None:
    sheets = read(ods.write_ods(sample()))
    assert list(sheets) == ["W001", "Notes", CON]
    w = sheets["W001"]

    def kind(a: str) -> tuple[str | None, str | None, str | None, str]:
        el = w[a]
        value = el.get(_q("office:value")) or el.get(_q("office:string-value"))
        return el.get(_q("office:value-type")), value, el.get(_q("table:formula")), cell_text(el)

    assert kind("E1") == ("string", None, None, "=1+2")
    assert kind("F1") == ("string", None, None, "+5V")
    assert kind("E2") == ("float", "0.0001", None, "0.0001")
    assert kind("F2") == ("float", "10000000000000000", None, "10000000000000000")
    assert kind("B3") == ("float", "0", None, "0")
    assert kind("C3") == ("float", "12.5", None, "12.5")
    assert kind("D3") == ("float", "1200", None, "1200")
    assert kind("E3") == ("float", "-3", None, "-3")
    assert kind("A4") == ("float", "1", f"of:=[$'{CON}'.A6]", "1")
    assert kind("D4") == (
        "string",
        "PWR",
        'of:=IF([.C4]="IN";"OUT";IF([.C4]="OUT";"IN";[.C4]))',
        "PWR",
    )
    assert kind("E4")[0:2] == ("string", "Black")
    assert kind("E5") == (
        "string",
        "",
        'of:=IF(ISNA(MATCH([.A5];[.A4:.A4];0));"";MATCH([.A5];[.A4:.A4];0)+3)',
        "",
    )
    assert w["E5"].get(_q("office:string-value")) == ""
    assert kind("B7") == ("float", "501", 'of:=SUMIF([.G4:.G5];"S1";[.F4:.F5])/1+[.F5]', "501")
    assert kind("A9")[3] == f"{CON} [J4711]"
    # spans: the covered cells are not cells of their own
    assert w["A1"].get(_q("table:number-columns-spanned")) == "4"
    assert w["A2"].get(_q("table:number-rows-spanned")) == "2"
    assert "B1" not in w and "D1" not in w and "A3" not in w
    assert cell_text(w["A1"]) == "Harness W001" and cell_text(w["E1"]) == "=1+2"
    # empty cells with a style (a pin with no wire) are written, with the style
    yellow = {w[f"{c}6"].get(_q("table:style-name")) for c in "ABCDEFG"}
    assert len(yellow) == 1 and None not in yellow
    assert cell_text(w["B6"]) == "" and w["B6"].get(_q("office:value-type")) is None
    assert [kind(f"{c}2")[1] for c in "A"] == [None]
    notes = sheets["Notes"]
    assert cell_text(notes["B3"]) == "Brown" and notes["A3"].get(_q("office:value")) == "2"


def test_links_are_text_a_elements() -> None:
    sheets = read(ods.write_ods(sample()))

    def link(el: ET.Element) -> tuple[str | None, str]:
        a = el.find("text:p/text:a", NS)
        assert a is not None
        return a.get(_q("xlink:href")), _text(a)

    assert link(sheets["W001"]["A8"]) == ("https://example.org/part/42", "Part link")
    assert link(sheets["W001"]["B8"]) == ("mailto:a@example.org", "mail")
    assert link(sheets[CON]["B3"]) == ("https://example.org/icd?a=1&b=2", "ICD of DEV2")
    assert sheets["W001"]["A8"].get(_q("table:formula")) is None


def test_column_widths_print_ranges_and_pages() -> None:
    files = members(ods.write_ods(sample()))
    content = parse(files["content.xml"])
    widths = {
        s.get(_q("style:name")): p.get(_q("style:column-width"))
        for s in content.iter(_q("style:style"))
        for p in s.findall("style:table-column-properties", NS)
    }
    tables = {t.get(_q("table:name")): t for t in content.iter(_q("table:table"))}

    def columns(name: str) -> list[str | None]:
        out: list[str | None] = []
        for col in tables[name].findall("table:table-column", NS):
            n = int(col.get(_q("table:number-columns-repeated"), "1"))
            out += [widths.get(col.get(_q("table:style-name"), ""))] * n
        return out

    assert columns("W001") == ["15mm", "25mm", None, "20mm", "20mm", "20mm", "20mm"]
    assert columns(CON) == ["30mm", "40mm", "20mm"]
    assert tables["W001"].get(_q("table:print-ranges")) == "W001.A1:W001.G9"
    assert tables["Notes"].get(_q("table:print-ranges")) is None
    styles = parse(files["styles.xml"])
    layouts = {
        p.get(_q("style:name")): p.find("style:page-layout-properties", NS)
        for p in styles.iter(_q("style:page-layout"))
    }
    masters = {m.get(_q("style:name")): m for m in styles.iter(_q("style:master-page"))}
    table_page = {
        s.get(_q("style:name")): s.get(_q("style:master-page-name"))
        for s in content.iter(_q("style:style"))
        if s.get(_q("style:family")) == "table"
    }
    w001 = masters[table_page[tables["W001"].get(_q("table:style-name"))]]
    props = layouts[w001.get(_q("style:page-layout-name"))]
    assert props is not None
    assert props.get(_q("fo:page-width")) == "297mm" and props.get(_q("fo:page-height")) == "210mm"
    assert props.get(_q("style:print-orientation")) == "landscape"
    assert props.get(_q("style:scale-to-pages")) == "1"
    header, footer = w001.find("style:header", NS), w001.find("style:footer", NS)
    assert header is not None and footer is not None
    assert cell_text(header) == "W001 plan"
    assert cell_text(footer) == "harness-design-studio test model 0123abcd"
    plain = masters[table_page[tables["Notes"].get(_q("table:style-name"))]]
    assert (
        plain is not w001
        and table_page[tables["Notes"].get(_q("table:style-name"))]
        == table_page[tables[CON].get(_q("table:style-name"))]
    )


def test_conditional_formats_are_style_maps_on_every_cell_of_the_range() -> None:
    files = members(ods.write_ods(sample()))
    content = parse(files["content.xml"])
    maps = {
        s.get(_q("style:name")): [
            (
                m.get(_q("style:condition")),
                m.get(_q("style:apply-style-name")),
                m.get(_q("style:base-cell-address")),
            )
            for m in s.findall("style:map", NS)
        ]
        for s in content.iter(_q("style:style"))
    }
    w = read(ods.write_ods(sample()))["W001"]
    gnd = 'is-true-formula(OR(AND([.C4]="GND";[.D4]="PWR");AND([.D4]="GND";[.C4]="PWR")))'
    for a in ("C4", "D4", "C5", "D5"):
        assert maps[w[a].get(_q("table:style-name"), "")] == [(gnd, "Condition1", "W001.C4")], a
    for a in ("A12", "B12", "A13", "B13"):
        assert maps[w[a].get(_q("table:style-name"), "")] == [
            ('is-true-formula([.A12]="x")', "Condition1", "W001.A12")
        ]
    assert not maps.get(w["E4"].get(_q("table:style-name"), ""), [])
    named = parse(files["styles.xml"]).find("office:styles", NS)
    assert named is not None
    cond = [s for s in named if s.get(_q("style:name")) == "Condition1"]
    assert len(cond) == 1
    text = cond[0].find("style:text-properties", NS)
    assert text is not None and text.get(_q("fo:color")) == "#ce181e"
    assert text.get(_q("fo:font-weight")) == "bold"


# ---- escaping -------------------------------------------------------------------------------


def test_text_is_escaped_and_reads_back() -> None:
    data = ods.write_ods(sample())
    content = members(data)["content.xml"]
    assert b"\x01" not in content and b"\x0b" not in content
    w = read(data)["W001"]
    assert cell_text(w["B2"]) == "a < b & \"c\" 'd' >  two  spaces\tand a tab\nsecond line "
    assert w["B2"].get(_q("table:formula")) is None


def test_attributes_are_escaped() -> None:
    book = Workbook(
        'T <&> "q"',
        (
            Sheet(
                "S",
                rows=(
                    (Cell('a"b<&>\n\tc', formula='IF([.B1]="";"x&amp;""<";"")'), Cell("")),
                    (Cell("q", link='https://example.org/?a="1"&b=<2>'),),
                ),
            ),
        ),
    )
    data = ods.write_ods(book)
    s = read(data)["S"]
    assert s["A1"].get(_q("office:string-value")) == 'a"b<&>\n\tc'
    assert s["A1"].get(_q("table:formula")) == 'of:=IF([.B1]="";"x&amp;""<";"")'
    a = s["A2"].find("text:p/text:a", NS)
    assert a is not None and a.get(_q("xlink:href")) == 'https://example.org/?a="1"&b=<2>'
    meta = parse(members(data)["meta.xml"]).find("office:meta/dc:title", NS)
    assert meta is not None and meta.text == 'T <&> "q"'


@pytest.mark.parametrize("text", ["=1+2", "+5V", "=SUM(A1:A3)", "-1", "@x"])
def test_a_text_that_looks_like_a_formula_stays_text(text: str) -> None:
    el = read(ods.write_ods(Workbook("t", (Sheet("S", rows=((Cell(text),),)),))))["S"]["A1"]
    assert el.get(_q("table:formula")) is None
    assert el.get(_q("office:value-type")) == "string" and cell_text(el) == text


def test_numbers_have_no_exponent() -> None:
    cases = [(0, "0"), (-0.0, "0"), (12.0, "12"), (12.5, "12.5"), (1e-05, "0.00001")]
    cases += [
        (1e16, "10000000000000000"),
        (1.5e-7, "0.00000015"),
        (-2.25e20, "-225000000000000000000"),
    ]
    cases += [(10**20, "100000000000000000000")]
    for v, s in cases:
        assert ods.number(v) == s, v
    for bad in (float("nan"), float("inf"), True):
        with pytest.raises(ValueError, match="number"):
            ods.number(bad)


# ---- the formula checker (section 7.2) ------------------------------------------------------

ALLOWED = [
    "[.B34]",
    "[$'CON_DEV2-J4711'.A19]",
    'IF([.D34]="IN";"OUT";IF([.D34]="OUT";"IN";[.D34]))',
    'IF([.H34]="";"";VLOOKUP([.H34];[$Notes.$B$7:.$C$43];2;0))',
    'IF(ISNA(MATCH([.W71];[.W34:.W63];0));"";MATCH([.W71];[.W34:.W63];0)+33)',
    "SUMIF([.L34:.L63];[.H19];[.N34:.N63])/[.R19]",
    '"Harness " & [.H6] & "-" & [.N6]',
    'if([.A1]="Hello!";1;2)',  # a "!" in a text is text
]


@pytest.mark.parametrize("formula", ALLOWED)
def test_formulas_of_the_closed_list_are_taken(formula: str) -> None:
    ods.check_formula(formula)


REFUSED = [
    ('INDIRECT("CON_"&[.B28]&"!B13")', "INDIRECT is not allowed"),
    ("ADDRESS(1;2)", "ADDRESS is not allowed"),
    ("OFFSET([.X70];[.W34];0)", "OFFSET is not allowed"),
    ('HYPERLINK("https://example.org")', "HYPERLINK is not allowed"),
    ("COM.MICROSOFT.CONCAT([.A1];[.B1])", "another program's function"),
    ("com.microsoft.ifs([.A1]=1;2)", "another program's function"),
    ("SUM([.A1:.A3])", "not in the closed list of functions"),
    ("CONCATENATE([.A1];[.B1])", "not in the closed list of functions"),
    ("[CON_X!B13]", "a reference with '!'"),
    ("CON_X!B13", "a name outside a reference"),
    ("[.A1]!B13", "'!' is the sheet separator"),
    ("B13", "a name outside a reference"),
    ("[A1]", "is not a reference such as"),
    ("[.A1]-1", "not an operator of the closed list"),
    ("[.A1]*2", "not an operator of the closed list"),
    ("[.A1]<>2", "not an operator of the closed list"),
    ("1E5", "exponent"),
    ("[.A1]=1.5E3", "exponent"),
    ("IF([.A1]=1;2", "leaves a bracket open"),
    ("[.A1])", "closes a bracket"),
    ('"abc', "no closing"),
    ("=[.A1]", "without the leading"),
    ("of:=[.A1]", "without the leading"),
    (" ", "empty"),
]


@pytest.mark.parametrize(("formula", "message"), REFUSED)
def test_formulas_outside_the_closed_list_are_refused(formula: str, message: str) -> None:
    with pytest.raises(ValueError, match=message.replace("(", r"\(")):
        ods.check_formula(formula)


def test_the_writer_refuses_a_formula_and_names_the_cell() -> None:
    book = Workbook("t", (Sheet("S", rows=((), (None, Cell(1, formula='INDIRECT("A1")')))),))
    with pytest.raises(ValueError, match=r"sheet 'S', cell B2: INDIRECT is not allowed"):
        ods.write_ods(book)
    missing = Workbook("t", (Sheet("S", rows=((Cell(1, formula="[$Other.A1]"),),)),))
    with pytest.raises(ValueError, match="the sheet 'Other', which the workbook does not have"):
        ods.write_ods(missing)


def test_conditions_take_and_or_but_not_the_refused_functions() -> None:
    def book(formula: str) -> Workbook:
        return Workbook(
            "t",
            (
                Sheet(
                    "S", rows=((Cell("x"),),), conditions=(Condition("A1:A2", formula, RED_BOLD),)
                ),
            ),
        )

    ods.write_ods(book('OR(AND([.A1]="GND";[.B1]="PWR");[.A1]="x")'))
    with pytest.raises(ValueError, match="conditional format A1:A2: OFFSET is not allowed"):
        ods.write_ods(book("OFFSET([.A1];1;0)"))
    with pytest.raises(ValueError, match="AND is not in the closed list"):
        ods.check_formula("AND([.A1];[.B1])")
    # the search boxes of the harness plan (3.1.0): ISNUMBER and SEARCH in a condition only
    ods.write_ods(book('IF([.$A$1]="";0;ISNUMBER(SEARCH([.$A$1];[.B1])))'))
    with pytest.raises(ValueError, match="FIND is not in the closed list"):
        ods.write_ods(book("ISNUMBER(FIND([.A1];[.B1]))"))
    with pytest.raises(ValueError, match="SEARCH is not in the closed list"):
        ods.check_formula("SEARCH([.A1];[.B1])")


def test_content_turns_regular_expressions_and_wildcards_off() -> None:
    """Text in a formula is read as typed: ODF's default would read a lookup key or a search text
    as a regular expression (LibreOffice does)."""
    content = members(ods.write_ods(sample()))["content.xml"].decode()
    settings = (
        '<table:calculation-settings table:use-regular-expressions="false" '
        'table:use-wildcards="false"/>'
    )
    assert settings == ods.CALCULATION_SETTINGS
    assert f"<office:spreadsheet>{settings}<table:table " in content
    assert content.count("calculation-settings") == 1


# ---- the rest of the model's checks ---------------------------------------------------------


def _one(*rows: tuple[Cell | None, ...], **sheet: object) -> Workbook:
    return Workbook("t", (Sheet("S", rows=rows, **sheet),))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("book", "message"),
    [
        (_one((Cell("a", cols=2), Cell("b"))), "lies under a spanned cell"),
        (_one((Cell("a"), None), (Cell("b", cols=2, rows=1), None), (None,)), None),
        (_one((None, Cell("a", rows=2)), (Cell("b", cols=2),)), "covers a cell that is not None"),
        (_one((Cell("a", cols=0),)), "a span is at least 1"),
        (_one((Cell("a", style=Style(colour="#ABCDEF")),)), "#rrggbb"),
        (_one((Cell("a", style=Style(align="middle")),)), "not an alignment"),
        (_one((Cell("a", style=Style(size_pt=-1)),)), "font size"),
        (_one((Cell("a", link="javascript:alert(1)"),)), "not a link that starts with"),
        (_one((Cell("a", link="file:///etc/passwd"),)), "not a link that starts with"),
        (_one((Cell("a", link="https://exa mple.org"),)), "not a link that starts with"),
        (
            _one((Cell("a", formula="[.B1]", link="https://example.org"),)),
            "a link needs a text value",
        ),
        (_one((Cell(1, link="https://example.org"),)), "a link needs a text value"),
        (_one((Cell(True),)), "is not a number"),
        (_one((Cell(float("nan")),)), "finite"),
        (_one((Cell("a"),), print_range="B2:A1"), "print range"),
        (_one((Cell("a"),), print_range="A1:B"), "print range"),
        (_one((Cell("a"),), widths=(10, -1)), "not a width"),
        (_one((Cell("a"),), page=Page(paper="Letter")), "not a paper size"),
        (
            _one((Cell("a"),), conditions=(Condition("A0:B1", "[.A1]=1", RED_BOLD),)),
            "conditional format",
        ),
        (Workbook("t", ()), "at least one sheet"),
        (Workbook("t", (Sheet("S"), Sheet("S"))), "used twice"),
        (Workbook("t", (Sheet("A:B"),)), "is not a sheet name"),
        (Workbook("t", (Sheet("'A"),)), "is not a sheet name"),
        (Workbook("t", (Sheet(" A"),)), "is not a sheet name"),
    ],
)
def test_the_writer_refuses_a_model_it_cannot_write(book: Workbook, message: str | None) -> None:
    if message is None:  # a span that covers only None cells is fine
        ods.write_ods(book)
        return
    with pytest.raises(ValueError, match=message):
        ods.write_ods(book)


def test_addresses_and_columns() -> None:
    assert [ods.column(c) for c in (0, 25, 26, 51, 52, 701, 702)] == [
        "A",
        "Z",
        "AA",
        "AZ",
        "BA",
        "ZZ",
        "AAA",
    ]
    assert ods.parse_address("B34") == (33, 1) and ods.parse_address("AA1") == (0, 26)
    assert ods.parse_range("H6:U64") == ((5, 7), (63, 20)) and ods.parse_range("C3") == (
        (2, 2),
        (2, 2),
    )
    for bad in ("b3", "B0", "B", "3", "$B$3"):
        with pytest.raises(ValueError):
            ods.parse_address(bad)
    assert ods.sheet_ref("Notes") == "Notes" and ods.sheet_ref("CON_X-1") == "'CON_X-1'"
    assert ods.sheet_ref("it's") == "'it''s'"


def test_repeated_empty_cells_and_rows() -> None:
    book = _one((Cell("a"), None, None, Cell("b")), (), (), (Cell("c"),), widths=(10, 10, 10))
    content = members(ods.write_ods(book))["content.xml"].decode("utf-8")
    assert '<table:table-cell table:number-columns-repeated="2"/>' in content
    assert (
        '<table:table-row table:number-rows-repeated="2"><table:table-cell/></table:table-row>'
        in content
    )
    assert (
        '<table:table-column table:number-columns-repeated="3" table:style-name="co1"/>' in content
    )
    s = read(ods.write_ods(book))["S"]
    assert cell_text(s["D1"]) == "b" and cell_text(s["A4"]) == "c"


# ---- imports --------------------------------------------------------------------------------


def test_importing_the_writer_loads_no_network_module() -> None:
    code = (
        f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r})\n"
        "import harness_design_studio.core.outputs.ods\n"
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in "
        "{'socket', 'ssl', 'http', 'urllib', 'xml', 'email', 'asyncio', 'PySide6', 'openpyxl'})\n"
        "print(bad)"
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True, timeout=60
    )
    assert out.stdout.strip() == "[]"


# ---- a real reader --------------------------------------------------------------------------

SOFFICE = shutil.which("soffice")


@pytest.mark.skipif(SOFFICE is None, reason="LibreOffice (soffice) is not installed")
def test_libreoffice_reads_the_values(tmp_path: Path) -> None:
    """LibreOffice converts the sample to CSV, one file per sheet, with the values it shows."""
    src = tmp_path / "sample.ods"
    src.write_bytes(ods.write_ods(sample()))
    profile = (tmp_path / "profile").as_uri()
    subprocess.run(
        [
            str(SOFFICE),
            f"-env:UserInstallation={profile}",
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

    def sheet(name: str) -> list[list[str]]:
        with (tmp_path / "out" / f"sample-{name}.csv").open(newline="", encoding="utf-8") as f:
            return list(csv.reader(f))

    w = sheet("W001")
    assert w[0][:6] == ["Harness W001", "", "", "", "=1+2", "+5V"]
    assert w[1][1] == "a < b & \"c\" 'd' >  two  spaces\tand a tab\nsecond line "
    assert w[1][4] == "0.0001" and float(w[1][5]) == 1e16  # LibreOffice shows 1E+016
    assert w[3][:5] == ["1", "PWR_28V", "PWR", "PWR", "Black"]
    assert w[4][:6] == ["2", "RTN", "GND", "GND", "", "250.5"]
    assert w[6][:2] == ["Sum", "501"]
    assert w[7][:2] == ["Part link", "mail"]
    assert w[8][0] == f"{CON} [J4711]"
    assert sheet("Notes") == [["Pin", "Color"], ["1", "Black"], ["2", "Brown"]]
    assert sheet(CON)[5] == ["1", "PWR_28V", "PWR"]
    # the conditional formats are read as conditional formats (LibreOffice's own flat file says so)
    subprocess.run(
        [
            str(SOFFICE),
            f"-env:UserInstallation={profile}",
            "--headless",
            "--convert-to",
            "fods",
            "--outdir",
            str(tmp_path / "out"),
            str(src),
        ],
        capture_output=True,
        check=True,
        timeout=180,
    )
    flat = (tmp_path / "out" / "sample.fods").read_text(encoding="utf-8")
    assert 'calcext:target-range-address="W001.C4:W001.D5"' in flat
    assert 'calcext:target-range-address="W001.A12:W001.B13"' in flat
    assert 'table:print-ranges="W001.A1:W001.G9"' in flat


def test_style_properties() -> None:
    style = Style(
        bold=True,
        italic=True,
        colour="#123456",
        background="#abcdef",
        size_pt=14,
        wrap=True,
        align="end",
        border=True,
    )
    content = parse(members(ods.write_ods(_one((Cell("x", style=style),))))["content.xml"])
    (cell,) = [
        s for s in content.iter(_q("style:style")) if s.get(_q("style:family")) == "table-cell"
    ]
    got = {f"{p.tag.split('}')[1]} {k.split('}')[1]}": v for p in cell for k, v in p.attrib.items()}
    assert got == {
        "table-cell-properties background-color": "#abcdef",
        "table-cell-properties border": "0.06pt solid #000000",
        "table-cell-properties wrap-option": "wrap",
        "table-cell-properties text-align-source": "fix",
        "paragraph-properties text-align": "end",
        "text-properties color": "#123456",
        "text-properties font-size": "14pt",
        "text-properties font-style": "italic",
        "text-properties font-weight": "bold",
        "text-properties font-weight-asian": "bold",
        "text-properties font-weight-complex": "bold",
    }
