# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The tests' own reader of a harness plan (`.ods`) and their own evaluator of the closed formula
list of section 7.2 of `docs/ait/DESIGN_3.0_HARNESS_PLAN.md`: `IF`, `ISNA`, `VLOOKUP` and `MATCH`
(exact match), `SUMIF`, and `&`, `=`, `/`, `+`; in a conditional format also `AND`, `OR`,
`ISNUMBER` and `SEARCH` (section 25: the search boxes). Neither imports the plan's layout module
or the writer: the reader parses `content.xml` with ElementTree and the evaluator computes a
formula over the stored cells, as a spreadsheet program that recalculates would, text compared
without regard to case. `SEARCH` reads its text as typed, since the plan turns regular expressions
and wildcards off (no `*`, `?` or `~` of a pattern), and an empty text to find gives `#VALUE!`, as
LibreOffice 24.2 does (Excel gives 1; the plan's format does not search for an empty text).
`read_conditions` and `marked` read the conditional formats and evaluate them at a cell. `dump`
writes the cells as lines of text, for the readable goldens."""

import hashlib
import io
import re
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from harness_design_studio.core.model import Project

NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
}


def _q(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


@dataclass(frozen=True)
class PlanCell:
    value: str | float  # a number cell's office:value, else the text (office:string-value)
    formula: str = ""  # without the `of:=` prefix
    link: str = ""
    style: str = ""


Sheets = dict[str, dict[tuple[int, int], PlanCell]]


def _text(p: ET.Element) -> str:
    out = [p.text or ""]
    for child in p:
        if child.tag == _q("text", "s"):
            out.append(" " * int(child.get(_q("text", "c"), "1")))
        elif child.tag == _q("text", "tab"):
            out.append("\t")
        elif child.tag == _q("text", "a"):
            out.append(_text(child))
        out.append(child.tail or "")
    return "".join(out)


def _link(cell: ET.Element) -> str:
    a = cell.find(".//text:a", NS)
    return a.get(_q("xlink", "href"), "") if a is not None else ""


def read_plan(data: bytes) -> Sheets:
    """sheet name -> (row, column), both 0-based -> the cell, for every cell with a value, a
    formula or a style; the empty cells of a repeat are not listed."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("content.xml"))  # noqa: S314 (the tool's own file)
    out: Sheets = {}
    for table in root.iter(_q("table", "table")):
        cells: dict[tuple[int, int], PlanCell] = {}
        r = 0
        for row in table.iter(_q("table", "table-row")):
            repeat = int(row.get(_q("table", "number-rows-repeated"), "1"))
            c = 0
            for cell in row:
                n = int(cell.get(_q("table", "number-columns-repeated"), "1"))
                if cell.tag == _q("table", "table-cell"):
                    kind = cell.get(_q("office", "value-type"))
                    formula = cell.get(_q("table", "formula"), "").removeprefix("of:=")
                    style = cell.get(_q("table", "style-name"), "")
                    shown = "\n".join(_text(p) for p in cell.findall("text:p", NS))
                    value: str | float
                    if kind == "float":
                        value = float(cell.get(_q("office", "value"), "nan"))
                    elif kind == "string" and formula:
                        value = cell.get(_q("office", "string-value"), "")
                    else:
                        value = shown
                    if value != "" or formula or style:
                        for rr in range(r, r + repeat):
                            for cc in range(c, c + n):
                                cells[rr, cc] = PlanCell(value, formula, _link(cell), style)
                c += n
            r += repeat
        out[table.get(_q("table", "name"), "")] = cells
    return out


Conditions = dict[str, dict[tuple[int, int], tuple[tuple[str, str], ...]]]


def read_conditions(data: bytes) -> Conditions:
    """sheet name -> (row, column) -> the conditional formats of the cell, each (formula, base cell
    such as `W001.I34`), from the `style:map`s of the cell's automatic style."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("content.xml"))  # noqa: S314 (the tool's own file)
    maps: dict[str, tuple[tuple[str, str], ...]] = {}
    for st in root.iter(_q("style", "style")):
        found = []
        for m in st.findall("style:map", NS):
            cond = m.get(_q("style", "condition"), "")
            assert cond.startswith("is-true-formula(") and cond.endswith(")"), cond
            found.append(
                (cond[len("is-true-formula(") : -1], m.get(_q("style", "base-cell-address"), ""))
            )
        if found:
            maps[st.get(_q("style", "name"), "")] = tuple(found)
    return {
        name: {k: maps[c.style] for k, c in cells.items() if c.style in maps}
        for name, cells in read_plan(data).items()
    }


def shown_texts(data: bytes) -> dict[str, dict[tuple[int, int], str]]:
    """The text each cell shows (its `text:p`), as a reader that does not recalculate shows it."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("content.xml"))  # noqa: S314 (the tool's own file)
    out: dict[str, dict[tuple[int, int], str]] = {}
    for table in root.iter(_q("table", "table")):
        cells: dict[tuple[int, int], str] = {}
        r = 0
        for row in table.iter(_q("table", "table-row")):
            repeat = int(row.get(_q("table", "number-rows-repeated"), "1"))
            c = 0
            for cell in row:
                n = int(cell.get(_q("table", "number-columns-repeated"), "1"))
                shown = "\n".join(_text(p) for p in cell.findall("text:p", NS))
                if shown:
                    for rr in range(r, r + repeat):
                        for cc in range(c, c + n):
                            cells[rr, cc] = shown
                c += n
            r += repeat
        out[table.get(_q("table", "name"), "")] = cells
    return out


# ---- addresses ----------------------------------------------------------------------------------


def address(row: int, col: int) -> str:
    name, c = "", col + 1
    while c:
        c, rem = divmod(c - 1, 26)
        name = chr(65 + rem) + name
    return f"{name}{row + 1}"


def parse_address(a: str) -> tuple[int, int]:
    m = re.fullmatch(r"\$?([A-Z]+)\$?([0-9]+)", a)
    if m is None:
        raise ValueError(a)
    c = 0
    for ch in m.group(1):
        c = c * 26 + ord(ch) - 64
    return int(m.group(2)) - 1, c - 1


def find(cells: dict[tuple[int, int], PlanCell], value: object) -> list[tuple[int, int]]:
    """The places of the cells with this value, in row then column order."""
    return sorted(k for k, v in cells.items() if v.value == value)


# ---- the evaluator --------------------------------------------------------------------------------


class _Empty:
    def __repr__(self) -> str:
        return "EMPTY"


class _NA:
    def __repr__(self) -> str:
        return "#N/A"


class _ValueError(_NA):
    """#VALUE!: what SEARCH gives when it does not find the text; it passes through like #N/A."""

    def __repr__(self) -> str:
        return "#VALUE!"


EMPTY, NA, VALUE = _Empty(), _NA(), _ValueError()
Scalar = str | float | bool | _Empty | _NA


@dataclass
class _Range:
    rows: list[list[Scalar]]


_TOKEN = re.compile(
    r'\s*(?:(?P<str>"(?:[^"]|"")*")|(?P<ref>\[[^\]]*\])|(?P<num>[0-9]+(?:\.[0-9]+)?)'
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_.]*)|(?P<op>[;()&=/+]))"
)
FUNCTIONS = ("IF", "ISNA", "VLOOKUP", "MATCH", "SUMIF")
CONDITION_FUNCTIONS = (*FUNCTIONS, "AND", "OR", "ISNUMBER", "SEARCH")


def _tokens(formula: str) -> list[tuple[str, str]]:
    out, pos = [], 0
    while pos < len(formula):
        if formula[pos:].strip() == "":
            break
        m = _TOKEN.match(formula, pos)
        if m is None or m.lastgroup is None:
            raise ValueError(f"cannot read {formula[pos:]!r}")
        out.append((m.lastgroup, m.group(m.lastgroup)))
        pos = m.end()
    return out


def _same(a: Scalar, b: Scalar) -> bool:
    if isinstance(a, _Empty):
        a = ""
    if isinstance(b, _Empty):
        b = ""
    if isinstance(a, str) and isinstance(b, str):
        return a.casefold() == b.casefold()
    if isinstance(a, str) or isinstance(b, str):
        return False
    return float(a) == float(b)  # type: ignore[arg-type]


def _number(v: Scalar) -> float | _NA:
    if isinstance(v, _NA):
        return NA
    if isinstance(v, _Empty):
        return 0.0
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, str):
        raise ValueError(f"{v!r} is text where a number is needed (#VALUE!)")
    return float(v)


def _as_text(v: Scalar) -> str:
    if isinstance(v, _Empty):
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        return str(int(v)) if v == int(v) and abs(v) < 1e15 else repr(v)
    return str(v)


class Evaluator:
    """Computes the formulas of a plan over its stored cells."""

    def __init__(self, sheets: Sheets) -> None:
        self.sheets = sheets

    def cell(self, sheet: str, row: int, col: int) -> Scalar:
        c = self.sheets[sheet].get((row, col))
        if c is None or (c.value == "" and not c.formula):
            return EMPTY
        return c.value

    def _ref(self, text: str, here: str) -> Scalar | _Range:
        body = text[1:-1]
        first, _, last = body.partition(":")

        def split(part: str, sheet: str) -> tuple[str, str]:
            name, _, addr = part.rpartition(".")
            name = name.removeprefix("$")
            if name.startswith("'"):
                name = name[1:-1].replace("''", "'")
            return (name or sheet), addr

        s1, a1 = split(first, here)
        if not last:
            r, c = parse_address(a1)
            return self.cell(s1, r, c)
        s2, a2 = split(last, s1)
        (r0, c0), (r1, c1) = parse_address(a1), parse_address(a2)
        return _Range([[self.cell(s2, r, c) for c in range(c0, c1 + 1)] for r in range(r0, r1 + 1)])

    def evaluate(self, formula: str, sheet: str, condition: bool = False) -> Scalar:
        """The value of a cell formula; with `condition`, of a conditional format's formula, which
        may also use AND, OR, ISNUMBER and SEARCH."""
        functions = CONDITION_FUNCTIONS if condition else FUNCTIONS
        toks = _tokens(formula)
        pos = 0

        def peek() -> tuple[str, str] | None:
            return toks[pos] if pos < len(toks) else None

        def take(expected: str | None = None) -> tuple[str, str]:
            nonlocal pos
            tok = toks[pos]
            if expected is not None and tok[1] != expected:
                raise ValueError(f"expected {expected!r}, read {tok[1]!r}")
            pos += 1
            return tok

        def binary(
            sub: Callable[[], Scalar | _Range], op: str, fn: Callable[[Scalar, Scalar], Scalar]
        ) -> Callable[[], Scalar | _Range]:
            def parse() -> Scalar | _Range:
                left = sub()
                while peek() == ("op", op):
                    take()
                    right = sub()
                    a, b = _scalar(left), _scalar(right)
                    left = NA if isinstance(a, _NA) or isinstance(b, _NA) else fn(a, b)
                return left

            return parse

        def primary() -> Scalar | _Range:
            nonlocal pos
            kind, text = take()
            if kind == "str":
                return text[1:-1].replace('""', '"')
            if kind == "num":
                return float(text)
            if kind == "ref":
                return self._ref(text, sheet)
            if kind == "op" and text == "(":
                value = comparison()
                take(")")
                return value
            if kind == "name":
                name = text.upper()
                if name not in functions:
                    raise ValueError(f"{text} is not in the closed list")
                take("(")
                # the token spans of the arguments, so that IF evaluates only the branch it takes
                starts: list[tuple[int, int]] = []
                depth, start, i = 0, pos, pos
                while True:
                    t = toks[i][1]
                    if t == "(":
                        depth += 1
                    elif t == ")":
                        if depth == 0:
                            starts.append((start, i))
                            break
                        depth -= 1
                    elif t == ";" and depth == 0:
                        starts.append((start, i))
                        start = i + 1
                    i += 1
                end = i
                spans = list(starts)

                def arg(n: int) -> Scalar | _Range:
                    nonlocal pos
                    saved = pos
                    pos = spans[n][0]
                    value = comparison()
                    if pos != spans[n][1]:
                        raise ValueError(f"argument {n + 1} of {name} is not one expression")
                    pos = saved
                    return value

                result = self._call(name, arg, len(spans))
                pos = end + 1
                return result
            raise ValueError(f"unexpected {text!r}")

        mul = binary(primary, "/", _divide)
        add = binary(mul, "+", _plus)
        concat = binary(add, "&", lambda a, b: _as_text(a) + _as_text(b))
        comparison = binary(concat, "=", _same)
        value = comparison()
        if pos != len(toks):
            raise ValueError(f"{formula!r}: tokens left after the expression")
        return _scalar(value)

    def _call(self, name: str, arg: Callable[[int], Scalar | _Range], count: int) -> Scalar:
        if name == "IF":
            cond = _scalar(arg(0))
            if isinstance(cond, _NA):
                return NA
            truth = cond if isinstance(cond, bool) else _number(cond) != 0
            if truth:
                return _scalar(arg(1))
            return _scalar(arg(2)) if count > 2 else False
        if name == "ISNA":
            return type(_scalar(arg(0))) is _NA
        if name in ("AND", "OR"):
            truths = [_truth(_scalar(arg(n))) for n in range(count)]
            return all(truths) if name == "AND" else any(truths)
        if name == "ISNUMBER":
            v = _scalar(arg(0))
            return isinstance(v, float)
        if name == "SEARCH":
            if count != 2:
                raise ValueError("SEARCH takes the text to find and the text to look in")
            find, within = _scalar(arg(0)), _scalar(arg(1))
            if isinstance(find, _NA) or isinstance(within, _NA):
                return find if isinstance(find, _NA) else within
            needle, text = _as_text(find).casefold(), _as_text(within).casefold()
            at = text.find(needle) if needle else -1
            return VALUE if at < 0 else float(at + 1)
        if name == "VLOOKUP":
            key, table, col, exact = _scalar(arg(0)), arg(1), _scalar(arg(2)), _scalar(arg(3))
            if not isinstance(table, _Range) or count != 4 or _number(exact) != 0:
                raise ValueError("VLOOKUP needs a range and the fourth argument 0")
            for row in table.rows:
                if _same(row[0], key):
                    return row[int(_number(col)) - 1]  # type: ignore[arg-type]
            return NA
        if name == "MATCH":
            key, area, exact = _scalar(arg(0)), arg(1), _scalar(arg(2))
            if not isinstance(area, _Range) or count != 3 or _number(exact) != 0:
                raise ValueError("MATCH needs a range and the third argument 0")
            flat = [v for row in area.rows for v in row]
            for n, v in enumerate(flat, start=1):
                if not isinstance(v, _Empty) and _same(v, key):
                    return float(n)
            return NA
        if name == "SUMIF":
            area, crit, sums = arg(0), _scalar(arg(1)), arg(2)
            if not isinstance(area, _Range) or not isinstance(sums, _Range):
                raise ValueError("SUMIF needs two ranges")
            total = 0.0
            for ra, rs in zip(area.rows, sums.rows, strict=True):
                for a, s in zip(ra, rs, strict=True):
                    if _same(a, crit) and isinstance(s, float):
                        total += s
            return total
        raise ValueError(name)


def _truth(v: Scalar) -> bool:
    if isinstance(v, _NA):
        raise ValueError(f"{v!r} where a truth value is needed")
    return v if isinstance(v, bool) else _number(v) != 0


def _scalar(v: Scalar | _Range) -> Scalar:
    if isinstance(v, _Range):
        if len(v.rows) == 1 and len(v.rows[0]) == 1:
            return v.rows[0][0]
        raise ValueError("a range where one value is needed")
    return v


def _divide(a: Scalar, b: Scalar) -> Scalar:
    x, y = _number(a), _number(b)
    if isinstance(x, _NA) or isinstance(y, _NA):
        return NA
    if y == 0:
        raise ValueError("#DIV/0!")
    return x / y


def _plus(a: Scalar, b: Scalar) -> Scalar:
    x, y = _number(a), _number(b)
    if isinstance(x, _NA) or isinstance(y, _NA):
        return NA
    return x + y


_REL = re.compile(r"\.(\$?)([A-Z]+)(\$?)([0-9]+)")


def moved(formula: str, rows: int, cols: int) -> str:
    """The formula with its relative references moved by `rows` and `cols` (a `$` part stays), as
    a conditional format is read at a cell other than its base cell."""

    def one(ref: re.Match[str]) -> str:
        def move(m: re.Match[str]) -> str:
            r, c = parse_address(f"{m.group(2)}{m.group(4)}")
            col = address(0, c + (0 if m.group(1) else cols))[:-1]
            row = r + (0 if m.group(3) else rows) + 1
            return f".{m.group(1)}{col}{m.group(3)}{row}"

        return _REL.sub(move, ref.group())

    return re.sub(
        r'"(?:[^"]|"")*"|\[[^\]]*\]',
        lambda m: m.group() if m.group().startswith('"') else one(m),
        formula,
    )


def marked(sheets: Sheets, conditions: Conditions, sheet: str, row: int, col: int) -> list[str]:
    """The formulas of the conditional formats of a cell that are true there, each read at the
    cell (its references moved from the base cell)."""
    out = []
    for formula, base in conditions.get(sheet, {}).get((row, col), ()):
        r0, c0 = parse_address(base.rpartition(".")[2])
        here = moved(formula, row - r0, col - c0)
        value = Evaluator(sheets).evaluate(here, sheet, condition=True)
        if _truth(value):
            out.append(here)
    return out


def check_values(sheets: Sheets) -> list[str]:
    """Every formula cell whose stored value is not what its formula gives (empty: all agree)."""
    ev = Evaluator(sheets)
    bad = []
    for name, cells in sheets.items():
        for (r, c), cell in sorted(cells.items()):
            if not cell.formula:
                continue
            got = ev.evaluate(cell.formula, name)
            if isinstance(got, (bool, _NA, _Empty)):
                bad.append(f"{name}!{address(r, c)}: {cell.formula} gives {got!r}")
            elif isinstance(cell.value, float) != isinstance(got, float):
                bad.append(
                    f"{name}!{address(r, c)}: {cell.formula} gives {got!r}, stored {cell.value!r}"
                )
            elif isinstance(got, float):
                if abs(got - float(cell.value)) > 1e-9 * max(1.0, abs(got)):
                    bad.append(f"{name}!{address(r, c)}: {got!r} != stored {cell.value!r}")
            elif got != cell.value:
                bad.append(f"{name}!{address(r, c)}: {got!r} != stored {cell.value!r}")
    return bad


def dump(data: bytes) -> str:
    """The cells of a plan as lines `Sheet!A1<tab>value[<tab>=formula][<tab>link]`, sheet by
    sheet in the order of the file, row by row: what a reviewer reads in a golden diff."""
    lines = []
    for name, cells in read_plan(data).items():
        lines.append(f"== {name}")
        for (r, c), cell in sorted(cells.items()):
            if cell.value == "" and not cell.formula:
                continue
            value = cell.value if isinstance(cell.value, str) else _as_text(cell.value)
            line = f"{address(r, c)}\t{value!s}".replace("\n", "\\n")
            if cell.formula:
                line += f"\t={cell.formula}"
            if cell.link:
                line += f"\t<{cell.link}>"
            lines.append(line)
    return "\n".join(lines) + "\n"


# ---- the golden projects --------------------------------------------------------------------------

EXAMPLES = ("first-steps", "minimal-satellite", "small-satellite", "flatsat")
GOLDEN_PROJECTS = (*EXAMPLES, "branching", "splices", "row_layout", "format5")
# the projects whose plans are kept as text to read
READABLE = ("first-steps", "branching", "splices", "row_layout")


def golden_project(name: str) -> Project:
    """An example generated the way a user does (as `tools.output_hashes` makes it), or the
    branching fixture of `tests/test_outputs_routing.py` (the users' harness DEV2 + DEV3 <-> DEV1 +
    DEV4 and a straight one), or the splice fixture of `tests/splice_support.py` (`splices`: mini3
    with the Y harness W003 through two splices and W004 with a splice on a branch point's leg),
    or the row layout fixture of `tests/row_layout_support.py` (`row_layout`: mini3 with the rows
    of a part and the own rows of a box connector, format 4), or the fixture of format 5 of
    `tests/format5_support.py` (`format5`: face ends and depths)."""
    if name == "branching":
        from tests.test_outputs_routing import branching_project

        return branching_project()
    if name == "splices":
        from tests.splice_support import branch_leg_project

        return branch_leg_project()
    if name == "format5":
        from tests.format5_support import format5_project

        return format5_project()
    if name == "row_layout":
        from tests.row_layout_support import row_layout_project

        return row_layout_project()
    from harness_design_studio.core import templates
    from harness_design_studio.core.generate.engine import generate_project

    with tempfile.TemporaryDirectory(prefix="plan-") as tmp:
        project = templates.create_project(Path(tmp) / name, name)
    if not project.harnesses:
        generate_project(project)
    return project


def golden_files(files: dict[str, bytes]) -> tuple[dict[str, str], dict[str, str]]:
    """The plans of an output set: their SHA-256 by path, and their readable dumps by path."""
    plans = {k: v for k, v in sorted(files.items()) if k.endswith("_plan.ods")}
    digests = {k: hashlib.sha256(v).hexdigest() for k, v in plans.items()}
    texts = {k.removesuffix(".ods") + ".txt": dump(v) for k, v in plans.items()}
    return digests, texts
