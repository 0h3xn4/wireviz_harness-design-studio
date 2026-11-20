# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Our own writer of OpenDocument spreadsheets (`.ods`, ODF 1.3; D-242, design of 3.0.0 section 8).

Callers fill a small frozen model (`Workbook` of `Sheet`s of rows of `Cell`s, styles by value) and
`write_ods` turns it into bytes; the same model always gives the same bytes (section 7.3): the
entries `mimetype`, `META-INF/manifest.xml`, `meta.xml`, `styles.xml` and `content.xml` in that
order, all stored, each with the date 1980-01-01, `create_system` 3 and `external_attr` 0o644 << 16;
`meta.xml` holds the title and the generator only; the XML is written here, UTF-8, with a fixed
attribute order and no pretty printing; automatic styles are numbered in the order of one walk of
the sheets; numbers have no exponent. Formulas are OpenFormula (`of:`) from the closed list of
section 7.2 and carry their stored value; anything outside the list is refused with `ValueError`.
`content.xml` turns regular expressions and wildcards off (`CALCULATION_SETTINGS`), so a reader
compares text as typed. Three print set-up features (design of 4.1.0 section 5.1) are off by
default and write nothing while off, so a sheet that does not use them keeps its bytes: a fixed
scale (`Page.scale`), heading rows repeated on every printed page (`Sheet.repeat_rows`) and page
breaks before rows (`Sheet.breaks`).
"""

import io
import itertools
import math
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal

from harness_design_studio import __version__
from harness_design_studio.core.outputs.canvas import escape

MIMETYPE = "application/vnd.oasis.opendocument.spreadsheet"
# Section 7.2: the functions of a cell formula, and the operators. A conditional format may also
# use AND and OR (the template's GND against PWR format, section 3.4, Q17) and ISNUMBER and SEARCH
# (the search boxes of the harness sheet, 3.1.0, D-250; section 25).
FUNCTIONS = frozenset({"IF", "ISNA", "VLOOKUP", "MATCH", "SUMIF"})
CONDITION_FUNCTIONS = FUNCTIONS | {"AND", "OR", "ISNUMBER", "SEARCH"}
# How a reader compares text (section 25): neither regular expressions nor wildcards, so a search
# text, a lookup key and a SUMIF criterion are read as typed. Without the element ODF's default
# turns regular expressions on, and LibreOffice reads `TX+` as a pattern.
CALCULATION_SETTINGS = (
    '<table:calculation-settings table:use-regular-expressions="false" '
    'table:use-wildcards="false"/>'
)
OPERATORS = "&=/+"
REFUSED = {
    "INDIRECT": "it builds a reference from text at recalculation time; write a direct reference",
    "ADDRESS": "it builds a reference from numbers at recalculation time; write a direct reference",
    "OFFSET": "it builds a reference from numbers at recalculation time; write a direct reference",
    "HYPERLINK": "a link is a text:a element of the cell (Cell.link), not a formula",
}
PAPERS = {"A4": (210, 297), "A3": (297, 420)}  # mm, portrait
# The fixed scales a reader takes, in percent: the range of LibreOffice's and Excel's page set-up.
SCALES = (10, 400)
# The row style of a row before which a page starts (ODF 1.2 section 17.17, fo:break-before); the
# row keeps the height a reader gives an unstyled row.
BREAK_ROW = (
    '<style:table-row-properties fo:break-before="page" style:use-optimal-row-height="true"/>'
)
ALIGNS = ("", "start", "center", "end")
ZIP_DATE = (1980, 1, 1, 0, 0, 0)

_NS_OFFICE = 'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
_NS = {
    "style": 'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"',
    "text": 'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"',
    "table": 'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"',
    "fo": 'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"',
    "xlink": 'xmlns:xlink="http://www.w3.org/1999/xlink"',
    "of": 'xmlns:of="urn:oasis:names:tc:opendocument:xmlns:of:1.2"',
    "meta": 'xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0"',
    "dc": 'xmlns:dc="http://purl.org/dc/elements/1.1/"',
}
_HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n'


@dataclass(frozen=True, slots=True)
class Style:
    """The look of a cell, by value: equal styles share one automatic style."""

    bold: bool = False
    italic: bool = False
    colour: str = ""  # text colour, "#rrggbb"
    background: str = ""  # "#rrggbb"
    size_pt: float = 0  # 0: the reader's default size
    wrap: bool = False
    align: str = ""  # "", "start", "center" or "end"
    border: bool = False


PLAIN = Style()


@dataclass(frozen=True, slots=True)
class Cell:
    """One cell. `value` is the text or number shown; with a `formula` (OpenFormula without the
    leading `=`, references as `[.B34]` or `[$Notes.$B$7:.$C$43]`) it is the stored result. A
    `link` (https, http or mailto) makes the text a `text:a`. `cols` and `rows` span the cell; the
    cells it covers must be None in the rows."""

    value: str | int | float = ""
    formula: str = ""
    link: str = ""
    style: Style = PLAIN
    cols: int = 1
    rows: int = 1


@dataclass(frozen=True, slots=True)
class Condition:
    """A conditional format: over `cells` ("J34:J63"), `style` applies where `formula` is true.
    References in the formula are relative to the first cell of the range."""

    cells: str
    formula: str
    style: Style


@dataclass(frozen=True, slots=True)
class Page:
    """The printed page of a sheet. `fit` prints the sheet on one page; `scale` prints it at a fixed
    scale in percent (`SCALES`, 10 to 400; 0 leaves it to the reader), written as
    `style:scale-to`; `fit` and `scale` exclude each other. Header and footer are plain text (the
    stamp)."""

    paper: str = "A4"
    landscape: bool = False
    fit: bool = False
    header: str = ""
    footer: str = ""
    scale: int = 0


@dataclass(frozen=True, slots=True)
class Sheet:
    """One sheet: `rows[0]` is row 1 and each row starts at column A; None is an empty cell.
    `widths` are column widths in mm from column A (0 leaves the width to the reader).
    `repeat_rows` (first, last), 0-based, are the rows written inside `table:table-header-rows`,
    which a reader prints at the top of every page. `breaks`, 0-based and rising, are the rows
    before which a page starts; each is written with a row style `fo:break-before="page"`. A break
    is not before row 1 and not inside the heading rows (it may be before their first row or
    right after their last). Rows are merged into a repeated run only within the heading rows,
    or within the rows between two breaks, never across."""

    name: str
    rows: tuple[tuple[Cell | None, ...], ...] = ()
    widths: tuple[float, ...] = ()
    page: Page = Page()
    print_range: str = ""  # "H6:U64"
    conditions: tuple[Condition, ...] = ()
    repeat_rows: tuple[int, int] | None = None
    breaks: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class Workbook:
    """The sheets in their order, the title and the generator of `meta.xml`."""

    title: str
    sheets: tuple[Sheet, ...]
    generator: str = f"Harness Design Studio {__version__}"


# ---- text, numbers, names -------------------------------------------------------------------

# Characters XML 1.0 does not allow; dropped, as the build workbook drops them (exports.py)
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def _clean(s: str) -> str:
    return _ILLEGAL.sub("", s.replace("\r\n", "\n").replace("\r", "\n"))


def attr(s: str) -> str:
    """Escape for an attribute value in double quotes; tab and line break stay as they are."""
    s = escape(_clean(s)).replace('"', "&quot;")
    return s.replace("\t", "&#9;").replace("\n", "&#10;")


def _spaces(m: re.Match[str]) -> str:
    n = len(m.group())
    middle = m.start() > 0 and m.end() < len(m.string)
    return (" " if middle else "") + _space_run(n - 1 if middle else n)


def _space_run(n: int) -> str:
    return "" if n == 0 else "<text:s/>" if n == 1 else f'<text:s text:c="{n}"/>'


def _inline(line: str) -> str:
    """Escaped text of one paragraph: tabs and the spaces a reader would collapse as elements."""
    parts = [re.sub(r"^ +| +$| {2,}", _spaces, escape(p)) for p in line.split("\t")]
    return "<text:tab/>".join(parts)


def paragraphs(text: str, link: str = "") -> str:
    """`text:p` elements of a text, one per line, each inside a `text:a` when there is a link."""
    out = []
    for line in _clean(text).split("\n"):
        body = _inline(line)
        if link:
            body = f'<text:a xlink:href="{attr(link)}" xlink:type="simple">{body}</text:a>'
        out.append(f"<text:p>{body}</text:p>" if body else "<text:p/>")
    return "".join(out)


def number(v: int | float) -> str:
    """A number as text without an exponent: 12, 12.5, 0.0001, 10000000000000000."""
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise ValueError(f"{v!r} is not a number")
    if isinstance(v, float) and not math.isfinite(v):
        raise ValueError(f"{v!r} is not a finite number")
    s = format(Decimal(repr(v)), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def column(c: int) -> str:
    """Column letters of a 0-based column index: 0 A, 25 Z, 26 AA."""
    name = ""
    c += 1
    while c:
        c, r = divmod(c - 1, 26)
        name = chr(65 + r) + name
    return name


_ADDR = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})")


def parse_address(a: str) -> tuple[int, int]:
    """(row, column), 0-based, of an address such as B34."""
    m = _ADDR.fullmatch(a)
    if m is None:
        raise ValueError(f"{a!r} is not a cell address such as B34")
    c = 0
    for ch in m.group(1):
        c = c * 26 + ord(ch) - 64
    return int(m.group(2)) - 1, c - 1


def parse_range(r: str) -> tuple[tuple[int, int], tuple[int, int]]:
    first, sep, last = r.partition(":")
    a, b = parse_address(first), parse_address(last if sep else first)
    if b[0] < a[0] or b[1] < a[1]:
        raise ValueError(f"{r!r} is not a range from its top left to its bottom right cell")
    return a, b


def sheet_ref(name: str) -> str:
    """A sheet name as OpenFormula and ODF addresses write it: quoted unless a plain name."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return name
    return "'" + name.replace("'", "''") + "'"


# ---- the formula checker (section 7.2) ------------------------------------------------------

_SHEET = r"\$?(?:'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_]*)"
_CELL = r"\.\$?[A-Z]{1,3}\$?[1-9][0-9]*"
_REF = re.compile(rf"\[(?P<s1>{_SHEET})?{_CELL}(?::(?P<s2>{_SHEET})?{_CELL})?\]")
_TOKEN = re.compile(
    r'(?P<ws>\s+)|(?P<str>"(?:[^"]|"")*")|(?P<ref>\[[^\]]*\])|(?P<num>[0-9]+(?:\.[0-9]+)?(?![0-9A-Za-z_.]))'
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_.]*)|(?P<op>[;()])|(?P<oper>[" + re.escape(OPERATORS) + "])"
)


def _sheet_name(s: str) -> str:
    s = s.removeprefix("$")
    return s[1:-1].replace("''", "'") if s.startswith("'") else s


def check_formula(
    formula: str, functions: frozenset[str] = FUNCTIONS, sheets: frozenset[str] | None = None
) -> None:
    """Refuse a formula outside the dialect of section 7.2 with a `ValueError` that says why:
    a function outside `functions` (and always INDIRECT, ADDRESS, OFFSET, HYPERLINK and any
    COM.MICROSOFT. function), a reference with `!`, a reference not in OpenFormula form or to a
    sheet not in `sheets`, a bare name, an operator outside &, =, /, + or unbalanced brackets."""
    if not formula.strip():
        raise ValueError("the formula is empty")
    if formula.startswith(("=", "of:")):
        raise ValueError(
            "write the formula without the leading '=' or 'of:'; the writer adds 'of:='"
        )
    pos, depth = 0, 0
    while pos < len(formula):
        m = _TOKEN.match(formula, pos)
        if m is None:
            ch = formula[pos]
            if ch == "!":
                raise ValueError(
                    "'!' is the sheet separator of another program's references; write a reference as [$Sheet.A1]"
                )
            if ch.isdigit():
                raise ValueError("write a number with digits and a point only, without an exponent")
            if ch == '"':
                raise ValueError("a text in the formula has no closing '\"'")
            raise ValueError(
                f"{ch!r} is not an operator of the closed list ({', '.join(OPERATORS)})"
            )
        kind, tok, pos = m.lastgroup, m.group(), m.end()
        if kind == "ref":
            if "!" in tok:
                raise ValueError(
                    f"{tok}: a reference with '!' is not OpenFormula; write [$Sheet.A1]"
                )
            ref = _REF.fullmatch(tok)
            if ref is None:
                raise ValueError(f"{tok} is not a reference such as [.B34] or [$Notes.$B$7:.$C$43]")
            for s in (ref["s1"], ref["s2"]):
                if s and sheets is not None and _sheet_name(s) not in sheets:
                    raise ValueError(
                        f"{tok} refers to the sheet {_sheet_name(s)!r}, which the workbook does not have"
                    )
        elif kind == "name":
            name = tok.upper()
            if not formula[pos:].lstrip().startswith("("):
                raise ValueError(
                    f"{tok!r} is a name outside a reference; write a reference as [.A1]"
                )
            if name.startswith("COM.MICROSOFT."):
                raise ValueError(
                    f"{tok} is another program's function, not OpenFormula; use & or a nested IF"
                )
            if name in REFUSED:
                raise ValueError(f"{tok} is not allowed: {REFUSED[name]}")
            if name not in functions:
                raise ValueError(
                    f"{tok} is not in the closed list of functions ({', '.join(sorted(functions))})"
                )
        elif kind == "op":
            depth += {"(": 1, ")": -1}.get(tok, 0)
            if depth < 0:
                raise ValueError("the formula closes a bracket it did not open")
    if depth:
        raise ValueError("the formula leaves a bracket open")


# ---- the style table ------------------------------------------------------------------------


class _Styles:
    """Automatic style names, numbered in the order the walk of the sheets first asks for them."""

    def __init__(self) -> None:
        self.cells: dict[tuple[Style, tuple[tuple[str, str, str], ...]], str] = {}
        self.columns: dict[float, str] = {}
        self.rows: dict[str, str] = {}
        self.pages: dict[Page, int] = {}
        self.conditions: dict[Style, str] = {}

    def page(self, p: Page) -> int:
        return self.pages.setdefault(p, len(self.pages) + 1)

    def column(self, width: float) -> str:
        return self.columns.setdefault(width, f"co{len(self.columns) + 1}")

    def row(self, properties: str) -> str:
        return self.rows.setdefault(properties, f"ro{len(self.rows) + 1}")

    def condition(self, s: Style) -> str:
        return self.conditions.setdefault(s, f"Condition{len(self.conditions) + 1}")

    def cell(self, s: Style, maps: tuple[tuple[str, str, str], ...]) -> str:
        if s == PLAIN and not maps:
            return ""
        return self.cells.setdefault((s, maps), f"ce{len(self.cells) + 1}")


def _check_style(s: Style) -> None:
    for c in (s.colour, s.background):
        if c and not re.fullmatch(r"#[0-9a-f]{6}", c):
            raise ValueError(f"{c!r} is not a colour written #rrggbb in lower case")
    if s.align not in ALIGNS:
        raise ValueError(f"{s.align!r} is not an alignment ({', '.join(repr(a) for a in ALIGNS)})")
    if not (0 <= s.size_pt <= 400):
        raise ValueError(f"{s.size_pt!r} is not a font size from 0 to 400 pt")


def _check_page(p: Page) -> None:
    if isinstance(p.scale, bool) or not isinstance(p.scale, int):
        raise ValueError(f"the scale {p.scale!r} is not a whole percent")
    if p.scale and not SCALES[0] <= p.scale <= SCALES[1]:
        raise ValueError(
            f"the scale {p.scale} % is not from {SCALES[0]} to {SCALES[1]} % (0 leaves it to the reader)"
        )
    if p.scale and p.fit:
        raise ValueError(
            "a page is either fitted to one page or printed at a fixed scale, not both"
        )


def _whole(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _print_rows(sh: Sheet, n: int, name: str) -> tuple[tuple[int, int] | None, frozenset[int]]:
    """The heading rows and the break rows of a sheet of `n` rows, checked."""
    head = sh.repeat_rows
    if head is not None and not (
        len(head) == 2 and all(_whole(r) for r in head) and 0 <= head[0] <= head[1] < n
    ):
        raise ValueError(
            f"{name}, heading rows: {head!r} is not (first, last), 0-based, of the {n} rows of the sheet"
        )
    for b in sh.breaks:
        if not _whole(b) or not 1 <= b < n:
            raise ValueError(
                f"{name}, page breaks: {b!r} is not a 0-based row from 1 to {n - 1} of the sheet"
            )
    if list(sh.breaks) != sorted(set(sh.breaks)):
        raise ValueError(f"{name}, page breaks: {sh.breaks!r} are not rising, each once")
    if head is not None:
        inside = [b for b in sh.breaks if head[0] < b <= head[1]]
        if inside:
            raise ValueError(
                f"{name}, page breaks: row {inside[0]} lies inside the heading rows {head[0]} to {head[1]}"
            )
    return head, frozenset(sh.breaks)


def _properties(s: Style) -> str:
    cell = [f'fo:background-color="{s.background}"'] if s.background else []
    if s.border:
        cell.append('fo:border="0.06pt solid #000000"')
    if s.wrap:
        cell.append('fo:wrap-option="wrap"')
    if s.align:
        cell.append('style:text-align-source="fix"')
    out = f"<style:table-cell-properties {' '.join(cell)}/>" if cell else ""
    if s.align:
        out += f'<style:paragraph-properties fo:text-align="{s.align}"/>'
    text = [f'fo:color="{s.colour}"'] if s.colour else []
    if s.size_pt:
        text.append(f'fo:font-size="{number(s.size_pt)}pt"')
    if s.italic:
        text.append('fo:font-style="italic"')
    if s.bold:
        text.append(
            'fo:font-weight="bold" style:font-weight-asian="bold" style:font-weight-complex="bold"'
        )
    return out + (f"<style:text-properties {' '.join(text)}/>" if text else "")


# ---- the sheets -----------------------------------------------------------------------------


def _cell_xml(c: Cell, style: str, sheets: frozenset[str], where: str) -> str:
    out = ["<table:table-cell"]
    if style:
        out.append(f' table:style-name="{style}"')
    if c.cols != 1:
        out.append(f' table:number-columns-spanned="{c.cols}"')
    if c.rows != 1:
        out.append(f' table:number-rows-spanned="{c.rows}"')
    if c.formula:
        try:
            check_formula(c.formula, FUNCTIONS, sheets)
        except ValueError as exc:
            raise ValueError(f"{where}: {exc}") from None
        out.append(f' table:formula="of:={attr(c.formula)}"')
    if c.link and (c.formula or not isinstance(c.value, str)):
        raise ValueError(f"{where}: a link needs a text value and no formula")
    if c.link and not re.fullmatch(r"(https?://|mailto:)[^\s\x00-\x1f\x7f]+", c.link):
        raise ValueError(
            f"{where}: {c.link!r} is not a link that starts with https://, http:// or mailto: without spaces"
        )
    if isinstance(c.value, str):
        shown = c.value
        if c.formula:
            out.append(f' office:value-type="string" office:string-value="{attr(c.value)}"')
        elif c.value:
            out.append(' office:value-type="string"')
    else:
        try:
            shown = number(c.value)
        except ValueError as exc:
            raise ValueError(f"{where}: {exc}") from None
        out.append(f' office:value-type="float" office:value="{shown}"')
    if not shown and not c.formula:
        return "".join(out) + "/>"
    return "".join(out) + ">" + paragraphs(shown, c.link) + "</table:table-cell>"


def _runs(items: list[str]) -> str:
    """Consecutive equal empty elements (cells, covered cells, columns) written once with a count."""
    out: list[str] = []
    i = 0
    while i < len(items):
        j = i
        while j + 1 < len(items) and items[j + 1] == items[i] and _repeatable(items[i]):
            j += 1
        if j > i:
            name = items[i].split(None, 1)[0].removesuffix("/>")
            out.append(
                items[i].replace(name, f'{name} table:number-columns-repeated="{j - i + 1}"', 1)
            )
        else:
            out.append(items[i])
        i = j + 1
    return "".join(out)


def _repeatable(item: str) -> bool:
    return item.endswith("/>") and "spanned" not in item


def _table_xml(sh: Sheet, styles: _Styles, sheets: frozenset[str]) -> str:
    name = f"sheet {sh.name!r}"
    cells: dict[tuple[int, int], Cell] = {}
    covered: set[tuple[int, int]] = set()
    for r, row in enumerate(sh.rows):
        for c, cell in enumerate(row):
            if cell is None:
                continue
            where = f"{name}, cell {column(c)}{r + 1}"
            if (r, c) in covered:
                raise ValueError(f"{where} lies under a spanned cell; leave it None")
            if cell.cols < 1 or cell.rows < 1:
                raise ValueError(f"{where}: a span is at least 1 column and 1 row")
            _check_style(cell.style)
            cells[r, c] = cell
            for rr in range(r, r + cell.rows):
                for cc in range(c, c + cell.cols):
                    if (rr, cc) != (r, c):
                        if (rr, cc) in cells or (rr, cc) in covered:
                            raise ValueError(f"{where}: its span covers a cell that is not None")
                        covered.add((rr, cc))
    maps: dict[tuple[int, int], tuple[tuple[str, str, str], ...]] = {}
    for cond in sh.conditions:
        _check_style(cond.style)
        try:
            (r0, c0), (r1, c1) = parse_range(cond.cells)
            check_formula(cond.formula, CONDITION_FUNCTIONS, sheets)
        except ValueError as exc:
            raise ValueError(f"{name}, conditional format {cond.cells}: {exc}") from None
        entry = (
            cond.formula,
            styles.condition(cond.style),
            f"{sheet_ref(sh.name)}.{column(c0)}{r0 + 1}",
        )
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                maps[r, c] = (*maps.get((r, c), ()), entry)
    if sh.print_range:
        try:
            parse_range(sh.print_range)
        except ValueError as exc:
            raise ValueError(f"{name}, print range: {exc}") from None
    try:
        _check_page(sh.page)
    except ValueError as exc:
        raise ValueError(f"{name}, page: {exc}") from None
    used = [*cells, *covered, *maps]
    width = max([len(sh.widths), *(c + 1 for _, c in used)], default=0)
    out = [f'<table:table table:name="{attr(sh.name)}" table:style-name="ta{styles.page(sh.page)}"']
    if sh.print_range:
        first, _, last = sh.print_range.partition(":")
        ref = attr(sheet_ref(sh.name))
        out.append(f' table:print-ranges="{ref}.{first}:{ref}.{last or first}"')
    out.append(">")
    cols = []
    for c in range(width):
        w = sh.widths[c] if c < len(sh.widths) else 0
        if w < 0 or not math.isfinite(w):
            raise ValueError(f"{name}, column {column(c)}: {w!r} is not a width in mm")
        cols.append(
            f'<table:table-column table:style-name="{styles.column(w)}"/>'
            if w
            else "<table:table-column/>"
        )
    out.append(_runs(cols))
    lengths: dict[int, int] = {}
    for r, c in used:
        lengths[r] = max(lengths.get(r, 0), c + 1)
    rows = []
    n = max([len(sh.rows), *(r + 1 for r in lengths)])
    head, breaks = _print_rows(sh, n, name)
    for r in range(n):
        items = []
        for c in range(lengths.get(r, 0)):
            if (r, c) in covered:
                items.append("<table:covered-table-cell/>")
                continue
            cell = cells.get((r, c), Cell())
            style = styles.cell(cell.style, maps.get((r, c), ()))
            items.append(_cell_xml(cell, style, sheets, f"{name}, cell {column(c)}{r + 1}"))
        if not items:
            items = ["<table:table-cell/>"]
        rows.append(_runs(items))
    if head is None and not breaks:
        out.append(_repeat_rows(rows))
        return "".join(out) + "</table:table>"
    # The heading rows and every break start a group of their own, so no run crosses them.
    cuts = sorted({0, n, *breaks, *((head[0], head[1] + 1) if head else ())})
    style = f' table:style-name="{styles.row(BREAK_ROW)}"' if breaks else ""
    for a, b in itertools.pairwise(cuts):
        group = _repeat_rows(rows[a:b], style if a in breaks else "")
        heading = head is not None and a == head[0]
        out.append(
            f"<table:table-header-rows>{group}</table:table-header-rows>" if heading else group
        )
    return "".join(out) + "</table:table>"


def _repeat_rows(rows: list[str], first: str = "") -> str:
    """Rows, with a run of equal rows written once with a repeat count; `first` (a style
    attribute) goes on the first row alone, which then joins no run."""
    out: list[str] = []
    i = 0
    if first and rows:
        out.append(f"<table:table-row{first}>{rows[0]}</table:table-row>")
        i = 1
    while i < len(rows):
        j = i
        while j + 1 < len(rows) and rows[j + 1] == rows[i]:
            j += 1
        repeat = f' table:number-rows-repeated="{j - i + 1}"' if j > i else ""
        out.append(f"<table:table-row{repeat}>{rows[i]}</table:table-row>")
        i = j + 1
    return "".join(out)


# ---- the package (section 7.3) --------------------------------------------------------------


def _content(book: Workbook, styles: _Styles) -> str:
    names = [sh.name for sh in book.sheets]
    if not names:
        raise ValueError("a workbook needs at least one sheet")
    for n in names:
        if (
            not n
            or n != n.strip()
            or re.search(r"[\[\]*?:/\\\x00-\x1f]", n)
            or n.startswith("'")
            or n.endswith("'")
        ):
            raise ValueError(
                f"{n!r} is not a sheet name (no []*?:/\\, no quote at either end, no space around it)"
            )
        if names.count(n) > 1:
            raise ValueError(f"the sheet name {n!r} is used twice")
    sheets = frozenset(names)
    body = "".join(_table_xml(sh, styles, sheets) for sh in book.sheets)
    auto = [
        f'<style:style style:name="co{i}" style:family="table-column">'
        f'<style:table-column-properties style:column-width="{number(w)}mm"/></style:style>'
        for i, w in enumerate(styles.columns, 1)
    ]
    auto += [
        f'<style:style style:name="{name}" style:family="table-row">{props}</style:style>'
        for props, name in styles.rows.items()
    ]
    auto += [
        f'<style:style style:name="ta{n}" style:family="table" style:master-page-name="mp{n}">'
        '<style:table-properties table:display="true"/></style:style>'
        for n in styles.pages.values()
    ]
    for (style, maps), name in styles.cells.items():
        conds = "".join(
            f'<style:map style:condition="is-true-formula({attr(f)})" style:apply-style-name="{target}" style:base-cell-address="{attr(base)}"/>'
            for f, target, base in maps
        )
        auto.append(
            f'<style:style style:name="{name}" style:family="table-cell" style:parent-style-name="Default">{_properties(style)}{conds}</style:style>'
        )
    ns = " ".join(
        [_NS_OFFICE, _NS["style"], _NS["text"], _NS["table"], _NS["fo"], _NS["xlink"], _NS["of"]]
    )
    return (
        f'{_HEAD}<office:document-content {ns} office:version="1.3"><office:automatic-styles>{"".join(auto)}'
        f"</office:automatic-styles><office:body><office:spreadsheet>{CALCULATION_SETTINGS}{body}</office:spreadsheet></office:body></office:document-content>"
    )


def _styles(styles: _Styles) -> str:
    named = "".join(
        f'<style:style style:name="{name}" style:family="table-cell" style:parent-style-name="Default">{_properties(s)}</style:style>'
        for s, name in styles.conditions.items()
    )
    layouts, masters = [], []
    hf = '<style:header-footer-properties fo:min-height="7.5mm" fo:margin-{}="2.5mm"/>'
    for page, n in styles.pages.items():
        if page.paper not in PAPERS:
            raise ValueError(f"{page.paper!r} is not a paper size ({', '.join(PAPERS)})")
        w, h = PAPERS[page.paper]
        if page.landscape:
            w, h = h, w
        fit = ' style:scale-to-pages="1"' if page.fit else ""
        if page.scale:
            fit = f' style:scale-to="{page.scale}%"'
        layouts.append(
            f'<style:page-layout style:name="pm{n}"><style:page-layout-properties fo:page-width="{w}mm" fo:page-height="{h}mm"'
            f' style:print-orientation="{"landscape" if page.landscape else "portrait"}" fo:margin-top="10mm" fo:margin-bottom="10mm"'
            f' fo:margin-left="10mm" fo:margin-right="10mm"{fit}/><style:header-style>{hf.format("bottom")}</style:header-style>'
            f"<style:footer-style>{hf.format('top')}</style:footer-style></style:page-layout>"
        )
        head = (
            f"<style:header>{paragraphs(page.header)}</style:header>"
            if page.header
            else '<style:header style:display="false"/>'
        )
        foot = (
            f"<style:footer>{paragraphs(page.footer)}</style:footer>"
            if page.footer
            else '<style:footer style:display="false"/>'
        )
        masters.append(
            f'<style:master-page style:name="mp{n}" style:page-layout-name="pm{n}">{head}{foot}</style:master-page>'
        )
    ns = " ".join([_NS_OFFICE, _NS["style"], _NS["text"], _NS["table"], _NS["fo"]])
    return (
        f'{_HEAD}<office:document-styles {ns} office:version="1.3"><office:styles>'
        f'<style:style style:name="Default" style:family="table-cell"/>{named}</office:styles>'
        f"<office:automatic-styles>{''.join(layouts)}</office:automatic-styles>"
        f"<office:master-styles>{''.join(masters)}</office:master-styles></office:document-styles>"
    )


def _meta(book: Workbook) -> str:
    ns = " ".join([_NS_OFFICE, _NS["meta"], _NS["dc"]])
    return (
        f'{_HEAD}<office:document-meta {ns} office:version="1.3"><office:meta>'
        f"<meta:generator>{escape(_clean(book.generator))}</meta:generator><dc:title>{escape(_clean(book.title))}</dc:title>"
        "</office:meta></office:document-meta>"
    )


def _manifest(names: list[str]) -> str:
    files = "".join(
        f'<manifest:file-entry manifest:full-path="{n}" manifest:media-type="text/xml"/>'
        for n in names
    )
    return (
        f'{_HEAD}<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">'
        f'<manifest:file-entry manifest:full-path="/" manifest:version="1.3" manifest:media-type="{MIMETYPE}"/>{files}</manifest:manifest>'
    )


def write_ods(book: Workbook) -> bytes:
    """The `.ods` package of a workbook. Raises `ValueError` for a model the writer refuses."""
    styles = _Styles()
    content = _content(book, styles)  # first: the walk of the sheets numbers the styles
    parts = {"meta.xml": _meta(book), "styles.xml": _styles(styles), "content.xml": content}
    entries = {"mimetype": MIMETYPE, "META-INF/manifest.xml": _manifest(list(parts)), **parts}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for name, text in entries.items():
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3  # set here: ZipInfo takes it from the platform (0 on Windows)
            info.external_attr = 0o644 << 16
            z.writestr(info, text.encode("utf-8"))
    return out.getvalue()
