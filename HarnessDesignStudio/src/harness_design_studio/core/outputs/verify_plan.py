# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The independent check of the harness plans (`harnesses/<ID>/<ID>_plan.ods`; D-242, design of
3.0.0 section 7.5), called by `verify.verify_outputs` for each plan that `manifest.json` lists.

It imports neither the writer (`ods.py`) nor the layout (`harness_plan.py`). It reads the bytes
and works out on its own, from the project, what each plan must hold:

1. **The package** (`out_plan_package`): the entries `mimetype`, `META-INF/manifest.xml`,
   `meta.xml`, `styles.xml`, `content.xml` in that order, `mimetype` first with no extra field,
   every entry stored with the date 1980-01-01, `create_system` 3 and the mode 0o644, the
   manifest listing exactly the entries, `meta.xml` with the title and the generator.
2. **The XML** is parsed with ElementTree only after a DOCTYPE or ENTITY declaration is refused,
   as `core/kicad.py` does (`out_plan_package`).
3. **The cells** (`out_plan`): the sheets and their order, and for every cell its value type, its
   value, the text it shows and its link, against the cells derived here from the project with
   the verifier's own copies of the sides rule with splices (`plan_sides`, `spliced`), the
   Direction words (`direction_word`, `mirrored`) and the colour lookup (`lookup`);
   `tests/test_verify_plan.py` compares the copies with the core's. Every wire is in exactly one
   row (a near row, or *Further wires*, wires beyond a splice included), every pin row is there.
   The row layout of a box connector (format 4, design of 4.0.0 section 7) is read here a second
   time (`face_rows`, never imported from `core/row_layout.py`; `verify.py` uses it too): the
   column *Pin row* in F of its `CON_…` sheet, and its near block row by row in the order of the
   layout, then the pins in no row, with *Pin row* in A copying F.
4. **The formulas** (`out_plan_formula`): each formula is the text the design gives, is in the
   closed list of section 7.2 (`IF`, `ISNA`, `VLOOKUP` and `MATCH` with exact match, `SUMIF`,
   `&`, `=`, `/`, `+`, direct references only; `AND`, `OR`, `ISNUMBER` and `SEARCH` only in a
   conditional format), and gives its stored value when a small evaluator of that list computes it
   over the stored cells. A conditional format is checked by its formula text and its base cell
   only; the search boxes' formats (3.1.0, section 25) need `content.xml` to turn regular
   expressions and wildcards off (`check_settings`).
5. **The print set-up** (`out_plan`; 4.1.0, design of 4.1.0 section 5.2) of the harness sheet and
   of the sheet *Production*: the page layout is not fitted to one page (no
   `style:scale-to-pages`) and its `style:scale-to` is the scale worked out here (`_scale`) from
   the column widths as the file states them over the print range; the heading rows are rows 6 to
   9 of the harness sheet and rows 1 to 3 of *Production*; the print range is the design's; and
   every page break is before the first row of a block, where the verifier's own estimate of the
   row heights (`_heights`, `_breaks`) puts one: a block that fits on a page is not split.
   *Production* itself (part A) is worded by `verify_production.production_rows`, the verifier's
   own copy of its rows, and `H9` and row 2 of *Production* by `verify_production._length_lines`.

Not checked: the styles, the column widths, the print set-up of the other sheets and how a program
shows the file. The stamp is read from the About sheet (`plan_stamp`, for `out_stamp` in `verify.py`); a plan
changed after the export fails `out_modified` there, as every file does."""

import io
import json
import math
import re
import zipfile
import zlib
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from xml.etree import ElementTree  # noqa: S405 - DOCTYPE and entities are refused before parsing

from harness_design_studio import __version__
from harness_design_studio.core.links import effective_role
from harness_design_studio.core.model import Connector, Harness, Pin, Project, RowLayout, Wire
from harness_design_studio.core.model.physical import LOOSE_ROLE, SPLICE_ROLE
from harness_design_studio.core.verify import VerifyReport

from .stamp import Stamp, stamp_of
from .verify_labels import _label_format
from .verify_production import _length_lines, production_rows

# ---- the words of the plan, stated here a second time (never imported from the layout) --------

PLAN_SUFFIX = "_plan.ods"
MIMETYPE = "application/vnd.oasis.opendocument.spreadsheet"
ENTRIES = ("mimetype", "META-INF/manifest.xml", "meta.xml", "styles.xml", "content.xml")
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
COVER, REGISTER, NOTES, ABOUT, CON = "Cover", "Change_Register", "Notes", "About", "CON_"
PRODUCTION = "Production"
TO_FILL, OPEN_END = "to fill in", "open end"
OVERWRITE = (
    "This file is written by Harness Design Studio. An export overwrites it; work on a copy."
)
NOT_CONNECTED = "Not connected pins will be marked yellow"
NO_SGND = "[no SGND*]"
SEARCH_LABEL, SEARCH_TEXT = "Column Search String", "#"  # I2:I3 and M2:M3 (section 25)
EXAMPLE = (
    "Example colour code from the users' template: check it against the supplier's pigtail code"
)
STATUS = {"draft": "draft", "in_review": "in review", "released": "released"}
CHANGES = {
    "review": "in review",
    "release": "released",
    "new_version": "new version",
    "version_changed": "version changed",
}
ROLE_WORDS = {
    "power": "PWR",
    "return": "PWR-RET",
    "ground": "GND",
    "signal_ground": "SGND",
    "shield": "SHIELD",
    "spare": "",
}
DIRECTION_WORDS = {"in": "IN", "out": "OUT", "bidir": "IN/OUT"}
LEGEND = (
    "Direction: PWR power, PWR-RET power return, GND ground, SGND signal ground, SHIELD shield, "
    "IN input, OUT output, IN/OUT both ways; empty for a spare pin or a pin with no direction set. "
    "On the harness side IN and OUT are swapped.",
    "A yellow row is a pin of the device connector with no wire in this harness.",
    f"{NO_SGND} in the header: a pin of the role signal ground (SGND) of a device connector of this "
    "harness has no wire.",
    "Formulas: the device side and the far device side copy the CON_ sheets; Pinout, Function and "
    "Level of the harness side copy the device side; the two Direction columns mirror it; a colour "
    "by pin code is looked up in its table on this sheet; the title, the connector descriptions, "
    "the sums per cable type, the cable type lengths and Used in Row are formulas too. Every other "
    "cell is a value of the design.",
    "Search: type a text into I3 (Function) or M3 (Shielding); a cell of that column in the rows of "
    "the near connectors that contains it, without regard to case, shows in red bold. An empty box "
    "marks nothing. LibreOffice reads the text as typed; Excel reads *, ? and ~ as wildcards.",
    "The change register lists the change log of this harness (system/changelog.csv of the "
    "outputs); it is not typed into this file.",
    "This file is written by Harness Design Studio. An export overwrites it, formulas and typed "
    "changes alike; work on a copy.",
)
PIN_HEAD = ("Pinout", "Function", "Direction", "Level", "Description")
DEVICE_HEAD = ("Pin No.", "Function", "Direction", "Level", "Description")
HARNESS_HEAD = (
    "Pinout", "Function", "Direction", "Color", "Cable / Type", "Shielding / (Grouping)",
    "Length [mm] rear to rear", "Level", "Cable / Type", "Color", "Direction", "Function",
)  # fmt: skip
LENGTH = "Length [mm] rear to rear"  # every length heading of the plan (4.1.0, part D)
# the sheet Production (4.1.0, part A): its columns, with "Pigtail colour" after "Colour" while
# the plan colours by pin code
PRODUCTION_HEAD = (
    "Pin", "Signal", "Wire", "Goes to", "Wire part", "Colour", "AWG", LENGTH, "Length from",
    "Label at this end", "Shield group: here / far end",
)  # fmt: skip
PIGTAIL = "Pigtail colour"
SPLICES = "Splices: each node joins the wires listed on it"
# the print set-up (4.1.0, section 5): the width and height of the printed page in mm, a line of
# 10 pt, the width of a character and the cell's padding, all in mm; the heading rows (0-based)
PAGE_WIDTH, PAGE_HEIGHT = 276, 175
LINE, CHAR, PAD = Fraction("4.52"), Fraction("1.9"), Fraction(2)
TITLE_SIZE = Fraction(14, 10)  # a title of 14 pt is that much taller than a line of 10 pt
HARNESS_HEADING, PRODUCTION_HEADING = (5, 8), (0, 2)
# the columns of the harness sheet, 0-based: B to F the device side, H to S the harness side, one
# far pin column per far connector from T, a gap, then seven columns per far box connector
COL_A, COL_B, COL_C, COL_D, COL_E, COL_F = range(6)
PIN_ROW = "Pin row"  # F of a CON_ sheet and A of a near block, on a box connector with a layout
COL_H, COL_I, COL_J, COL_K, COL_L, COL_M, COL_N, COL_O, COL_P, COL_Q, COL_R, COL_S, COL_T = range(
    7, 20
)
GROUP = 7
# the functions of a cell formula (section 7.2); a conditional format may also use AND and OR, and
# ISNUMBER and SEARCH for the search boxes (3.1.0, D-250, section 25)
FUNCTIONS = frozenset({"IF", "ISNA", "VLOOKUP", "MATCH", "SUMIF"})
CONDITION_FUNCTIONS = FUNCTIONS | {"AND", "OR", "ISNUMBER", "SEARCH"}
ARGUMENTS = {
    "IF": (2, 3),
    "ISNA": (1, 1),
    "VLOOKUP": (4, 4),
    "MATCH": (3, 3),
    "SUMIF": (3, 3),
    "ISNUMBER": (1, 1),
    "SEARCH": (2, 2),  # no start position
}
REFUSED = ("INDIRECT", "ADDRESS", "OFFSET", "HYPERLINK")
MAX_MESSAGES = 10  # per plan and code; the rest is counted in one more message
MAX_REPEAT = 100_000  # a stored cell repeated more often than this is damage, not a plan

Value = str | int | float


# ---- the verifier's own copies of the rules of the plan ---------------------------------------


def face_rows(project: Project, c: Connector) -> tuple[tuple[str, ...], ...] | None:
    """The rows of the row layout of a connector (format 4, design of 4.0.0 section 3), read here
    a second time: a box connector (one with a device) has its own rows, else its part's; a cable
    connector its part's, else those of the box connector it plugs into (its own, else its part's).
    Only the names that are pins of the connector are kept, each row keeping its place (so its
    number); None for a connector without a layout. `verify.py` reads the Pin row columns of the
    pinout tables with it."""

    def own_or_part(x: Connector) -> RowLayout | None:
        part = project.parts.get(x.part_id)
        return x.row_layout or (part.row_layout if part is not None else None)

    if c.unit_id is not None:
        layout = own_or_part(c)
    else:
        part = project.parts.get(c.part_id)
        layout = part.row_layout if part is not None else None
        box = project.connectors.get(c.mates_with or "")
        if layout is None and box is not None and box.unit_id is not None:
            layout = own_or_part(box)
    if layout is None:
        return None
    pins = {p.id for p in c.pins}
    return tuple(tuple(name for name in row if name in pins) for row in layout.rows)


def row_numbers(rows: tuple[tuple[str, ...], ...]) -> dict[str, int]:
    """pin -> its row, counted from 1 at the top of the face."""
    return {name: n for n, row in enumerate(rows, start=1) for name in row}


def natural_key(text: str) -> tuple[list[int | str], str]:
    pieces = re.split(r"(\d+)", text)
    return [int(x) if n % 2 else x for n, x in enumerate(pieces)], text


def _is_open(c: Connector) -> bool:
    return c.role == LOOSE_ROLE


def cell_value(pin_id: str) -> Value:
    """A pin ID as the plan writes it: a number for a whole number without a leading zero."""
    return int(pin_id) if re.fullmatch(r"0|[1-9][0-9]{0,14}", pin_id) else pin_id


def direction_word(project: Project, pin: Pin, connector: Connector | None) -> str:
    """The Direction word of a pin (section 4.3): the effective role first, then the direction."""
    role = effective_role(pin, project, connector)
    if role in ROLE_WORDS:
        return ROLE_WORDS[role]
    return DIRECTION_WORDS.get(pin.direction, "")


def mirrored(word: str) -> str:
    """The word on the harness side: IN and OUT swap, every other word stays."""
    return {"IN": "OUT", "OUT": "IN"}.get(word, word)


def spliced(h: Harness) -> dict[str, list[Wire]]:
    """Wire ID -> every wire that a walk from it over splice nodes meets, itself included, in
    natural ID order. Only a pin of a connector of role `splice` passes a walk on; a pin of any
    other connector stops it."""
    splices = {c.id for c in h.connectors if c.role == SPLICE_ROLE}
    on: dict[tuple[str, str], list[Wire]] = defaultdict(list)
    for w in h.wires:
        for end in {(w.from_connector, w.from_pin), (w.to_connector, w.to_pin)}:
            if end[0] in splices:
                on[end].append(w)
    out: dict[str, list[Wire]] = {}
    for w in h.wires:
        if w.id in out:
            continue
        seen, todo = {w.id: w}, [w]
        while todo:
            here = todo.pop()
            for end in ((here.from_connector, here.from_pin), (here.to_connector, here.to_pin)):
                for there in on.get(end, []):
                    if there.id not in seen:
                        seen[there.id] = there
                        todo.append(there)
        group = sorted(seen.values(), key=lambda x: natural_key(x.id))
        for x in group:
            out[x.id] = group
    return out


def _plain_ends(wires: Sequence[Wire], h: Harness) -> list[tuple[str, str]]:
    """The pins of the wires that are not on a splice, each once."""
    splices = {c.id for c in h.connectors if c.role == SPLICE_ROLE}
    ends = [e for w in wires for e in ((w.from_connector, w.from_pin), (w.to_connector, w.to_pin))]
    return list(dict.fromkeys(e for e in ends if e[0] not in splices))


def plan_sides(h: Harness) -> tuple[tuple[Connector, ...], tuple[Connector, ...]]:
    """(near end, far end) by the sides rule of section 9: the connectors that are not splices,
    two of them joined when wires reach both through splices (`spliced`), coloured in two by walks
    in breadth in natural ID order, each walk starting in the first end; the end with more
    connectors is the near end, on a tie the end of the first connector."""
    order = sorted(
        (c for c in h.connectors if c.role != SPLICE_ROLE), key=lambda c: natural_key(c.id)
    )
    joined: dict[str, set[str]] = defaultdict(set)
    for group in spliced(h).values():
        reached = {cid for cid, _ in _plain_ends(group, h)}
        for cid in reached:
            joined[cid].update(reached - {cid})
    side: dict[str, bool] = {}
    for c in order:
        if c.id in side:
            continue
        side[c.id] = False
        walk = [c.id]
        while walk:
            here, walk = walk[0], walk[1:]
            for there in sorted(joined[here], key=natural_key):
                if there not in side:
                    side[there] = not side[here]
                    walk.append(there)
    one = tuple(c for c in order if side.get(c.id) is False)
    two = tuple(c for c in order if side.get(c.id) is True)
    return (one, two) if len(one) >= len(two) else (two, one)


def _same(a: object, b: object) -> bool:
    """An exact match of a spreadsheet: text with text without regard to case, a number with a
    number."""
    if isinstance(a, str) or isinstance(b, str):
        return isinstance(a, str) and isinstance(b, str) and a.casefold() == b.casefold()
    return a == b


def lookup(rows: Sequence[tuple[Value, str]], key: Value) -> str | None:
    """What `VLOOKUP(key; table; 2; 0)` gives over a code table, or None for #N/A."""
    for pin, colour in rows:
        if _same(pin, key):
            return colour
    return None


@dataclass(frozen=True)
class _Code:
    name: str
    parts: tuple[str, ...]
    pins: tuple[tuple[str, str], ...]
    example: bool


def _settings(project: Project) -> tuple[str, list[_Code], list[str]]:
    """The colour rule, the colour codes and the note lines of `config/harness_plan.json`; a value
    `validate` refuses counts as not set."""
    c = project.config.get("harness_plan")
    values = dict(c.values) if c is not None else {}
    rule = values.get("colour_rule")
    codes = []
    raw = values.get("colour_codes")
    for code in raw if isinstance(raw, list) else []:
        if not isinstance(code, dict) or not isinstance(code.get("name"), str):
            continue
        parts, pins = code.get("parts", []), code.get("pins", {})
        codes.append(
            _Code(
                code["name"],
                tuple(x for x in parts if isinstance(x, str)) if isinstance(parts, list) else (),
                tuple((str(k), x) for k, x in pins.items() if isinstance(x, str) and x)
                if isinstance(pins, dict)
                else (),
                code.get("example") is True,
            )
        )
    notes = values.get("notes")
    return (
        rule if rule in ("wire", "pin_code") else "wire",
        codes,
        [n for n in notes if isinstance(n, str)] if isinstance(notes, list) else [],
    )


def _length(h: Harness, w: Wire) -> float | None:
    """A wire's own length, else the sum of the segments of its one path (None for a path that is
    not unique or a segment without a length)."""
    if w.length_m is not None:
        return w.length_m
    if not h.segments:
        return None
    graph: dict[str, list[tuple[str, str, float | None]]] = defaultdict(list)
    for s in h.segments:
        graph[s.from_node].append((s.to_node, s.id, s.length_m))
        graph[s.to_node].append((s.from_node, s.id, s.length_m))

    def path(avoid: str) -> list[tuple[str, float | None]] | None:
        seen, queue = {w.from_connector}, [(w.from_connector, list[tuple[str, float | None]]())]
        while queue:
            (node, trail), queue = queue[0], queue[1:]
            if node == w.to_connector:
                return trail
            for nxt, sid, length in graph.get(node, []):
                if nxt not in seen and sid != avoid:
                    seen.add(nxt)
                    queue.append((nxt, [*trail, (sid, length)]))
        return None

    trail = path("")
    if trail is None or any(path(sid) is not None for sid, _ in trail):
        return None
    lengths = [x for _, x in trail]
    return None if any(x is None for x in lengths) else float(sum(x for x in lengths if x))


# ---- addresses and formula texts ---------------------------------------------------------------


def column(c: int) -> str:
    name, c = "", c + 1
    while c:
        c, rest = divmod(c - 1, 26)
        name = chr(65 + rest) + name
    return name


def address(row: int, col: int) -> str:
    return f"{column(col)}{row + 1}"


def _address_of(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"\$?([A-Z]{1,3})\$?([1-9][0-9]{0,6})", text)
    if m is None:
        raise ValueError(f"{text!r} is not a cell address")
    c = 0
    for ch in m.group(1):
        c = c * 26 + ord(ch) - 64
    return int(m.group(2)) - 1, c - 1


def _sheet_ref(name: str) -> str:
    return (
        name
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
        else "'" + name.replace("'", "''") + "'"
    )


def _here(row: int, col: int) -> str:
    return f"[.{address(row, col)}]"


def _there(sheet: str, row: int, col: int) -> str:
    return f"[${_sheet_ref(sheet)}.{address(row, col)}]"


def _span(col: int, first: int, last: int) -> str:
    return f"[.{address(first, col)}:.{address(last, col)}]"


def _quoted(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'


def _clean(s: str) -> str:
    """Text as an XML 1.0 file can hold it: line breaks as LF, the forbidden characters dropped."""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]", "", s)


def number_text(v: float) -> str:
    """A number as the plan shows it: no exponent, no trailing zeros."""
    s = format(Decimal(repr(v)), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


# ---- what the plan of a harness must hold, worked out from the project ------------------------


@dataclass(frozen=True)
class Want:
    value: Value
    formula: str = ""
    link: str = ""


Grid = dict[tuple[int, int], Want]


@dataclass(frozen=True)
class Printed:
    """What the print set-up of a sheet must be (4.1.0, section 5): its heading rows, its print
    range, the first and last row of each block (a page break is before a first row, where one
    is needed) and the look of the cells that are not a plain line of 10 pt (`title`: 14 pt;
    `wrap`: wrapped in its column), for the estimate of the row heights."""

    heading: tuple[int, int]
    print_range: str
    blocks: tuple[tuple[int, int], ...]
    looks: dict[tuple[int, int], str]


@dataclass
class Expected:
    """The sheets of a plan in their order, each with its cells; the conditional formats of the
    harness sheet (cell -> (formula, base cell)); the rows that each hold one pin or wire
    (row -> what it holds), for the row check; and the print set-up of the sheets that have one."""

    sheets: list[tuple[str, Grid]]
    harness_sheet: str
    conditions: dict[tuple[int, int], tuple[tuple[str, str], ...]]
    rows: dict[int, str]
    printed: dict[str, Printed] = field(default_factory=dict)


def _put(g: Grid, row: int, col: int, value: Value, formula: str = "", link: str = "") -> None:
    if value != "" or formula:
        g[row, col] = Want(_clean(value) if isinstance(value, str) else value, formula, link)
    else:
        g.pop((row, col), None)


def _fill(g: Grid, row: int, col: int, value: object) -> None:
    _put(g, row, col, TO_FILL if value is None or value == "" else value)  # type: ignore[arg-type]


def _link(g: Grid, row: int, col: int, text: str, link: str | None) -> None:
    if text or link:
        _put(g, row, col, text or link or "", link=link or "")


def plan_sheet_name(h: Harness) -> str:
    fixed = {n.casefold() for n in (COVER, REGISTER, PRODUCTION, NOTES, ABOUT)}
    clash = h.id.casefold() in fixed or h.id.casefold().startswith(CON.casefold())
    return f"Harness_{h.id}" if clash else h.id


@dataclass(frozen=True)
class _Con:
    """The CON_ sheet of a box connector: its name, cells, the row of each pin and the five values
    of each pin (A to E), the device as `B1` shows it and the description `B11`."""

    name: str
    grid: Grid
    rows: dict[str, int]
    values: dict[str, tuple[Value, str, str, str, str]]
    device: str
    description: str
    # with a row layout: pin -> its row in F (empty: in no row), and the box pins in the order of
    # a near block (row by row, then the pins in no row in pin order)
    faces: dict[str, Value] | None = None
    order: tuple[str, ...] = ()
    # B4 *Connector Name* while the label format is harness_device_connector, else None
    named: str | None = None


def _con(project: Project, box: Connector) -> _Con:
    g: Grid = {}
    part = project.parts.get(box.part_id)
    names = sorted(
        i.name
        for i in project.interfaces.values()
        if any(e.connector_id == box.id for e in i.endpoints)
    )
    ctype = (part.description if part else None) or box.part_id
    count = (part.pin_count if part else None) or len(box.pins)
    device = box.unit_id or TO_FILL
    for r, label, value in (
        (0, "Device", device),
        (1, "Connector ID", box.id),
        (2, "Interface Name", "; ".join(names)),
        (5, "Connector Type", ctype),
        (6, "Number of Pins", count),
        (7, "Gender", box.gender),
    ):
        _put(g, r, 0, label)
        _put(g, r, 1, value)
    # In the label format harness_device_connector the sheet names the connector as its device
    # does, in row 4 (empty otherwise), and the near block header reads it (design of 4.1.0, 4.5).
    named = box.name if _label_format(project) == "harness_device_connector" else None
    if named is not None:
        _put(g, 3, 0, "Connector Name")
        _put(g, 3, 1, named)
    pn = f"{ctype} {count} {box.gender}"
    description = f"{device} [{box.id}]: {'; '.join(names)}; {pn}"
    _put(g, 8, 0, "Connector Name/Part Number")
    _put(g, 8, 1, pn, '[.B6]&" "&[.B7]&" "&[.B8]')
    _put(g, 10, 0, "Connector Description")
    _put(g, 10, 1, description, '[.B1]&" ["&[.B2]&"]: "&[.B3]&"; "&[.B9]')
    for r, label in ((12, "Link to ICD"), (13, "ICD version"), (14, "CON sheet copied from")):
        _put(g, r, 0, label)
    _link(g, 12, 1, box.source_doc or "", box.source_link)
    _put(g, 13, 1, box.source_version or "")
    for n, text in enumerate(PIN_HEAD):
        _put(g, 17, n, text)
    face = face_rows(project, box)
    numbers = row_numbers(face) if face is not None else {}
    faces: dict[str, Value] | None = None
    order: tuple[str, ...] = ()
    if face is not None:
        _put(g, 17, COL_F, PIN_ROW)
        faces = {p.id: numbers.get(p.id, "") for p in box.pins}
        order = (
            *(name for row in face for name in row),
            *(p.id for p in box.pins if p.id not in numbers),
        )
    rows, values = {}, {}
    for n, pin in enumerate(box.pins):
        five = (
            cell_value(pin.id),
            pin.signal or "",
            direction_word(project, pin, box),
            pin.level or "",
            pin.function or "",
        )
        rows[pin.id], values[pin.id] = 18 + n, five
        for k, item in enumerate(five):
            _put(g, 18 + n, k, item)
        if faces is not None:
            _put(g, 18 + n, COL_F, faces[pin.id])
    return _Con(CON + box.id, g, rows, values, device, description, faces, order, named)


@dataclass
class _Line:
    """A pin row of a near block."""

    cable: Connector
    pin: Pin
    box_pin: bool
    wired: bool
    wire: Wire | None = None
    far: tuple[
        tuple[Connector, str, Wire], ...
    ] = ()  # far connector, far pin, the wire ending there


class _HarnessSheet:
    """The cells of the harness sheet (sections 3.3 to 3.5 and 18 of the design)."""

    def __init__(
        self,
        project: Project,
        h: Harness,
        name: str,
        cons: dict[str, _Con],
        tables: dict[str, tuple[int, int, tuple[tuple[Value, str], ...]]],
        rule: str,
        codes: list[_Code],
    ) -> None:
        self.project, self.h, self.name, self.cons, self.tables = project, h, name, cons, tables
        self.g: Grid = {}
        self.conditions: dict[tuple[int, int], tuple[tuple[str, str], ...]] = {}
        self.rows: dict[int, str] = {}
        self.near, self.far = plan_sides(h)
        self.spliced = spliced(h)
        self.by_part: dict[str, _Code] = {}
        if rule == "pin_code":
            for code in codes:
                for part in code.parts:
                    self.by_part.setdefault(part, code)
        self.ends: dict[tuple[str, str], list[Wire]] = defaultdict(list)
        for w in sorted(h.wires, key=lambda x: natural_key(x.id)):
            self.ends[w.from_connector, w.from_pin].append(w)
            self.ends[w.to_connector, w.to_pin].append(w)
        self.groups: dict[str, list[str]] = defaultdict(list)
        for s in sorted(h.shields, key=lambda x: natural_key(x.id)):
            for wid in s.wire_ids:
                self.groups[wid].append(s.id)
        # the far columns: (cable connector, its box when it has a CON_ sheet, pin column, group)
        self.columns: dict[str, tuple[Connector, _Con | None, int, int | None]] = {}
        group = COL_T + len(self.far) + 1
        for n, c in enumerate(self.far):
            con = self.con(c)
            self.columns[c.id] = (c, con, COL_T + n, group if con else None)
            group += GROUP if con else 0
        self.last_col = COL_T + max(len(self.far), 1) - 1
        self.types = sorted({w.part_id for w in h.wires if w.part_id}, key=natural_key)
        self.type_rows: dict[str, int] = {}
        self.per_cable: dict[str, int] = {}
        self.pin_rows: list[int] = []
        self.wire_blocks: list[tuple[int, int]] = []
        self.looks: dict[tuple[int, int], str] = {}  # a title of 14 pt, or a wrapped heading
        self.blocks: list[tuple[int, int]] = []  # the first and last row of each near block
        self.last = 0  # the last row of the print range

    def put(self, row: int, col: int, value: Value, formula: str = "", link: str = "") -> None:
        _put(self.g, row, col, value, formula, link)

    def head(self, row: int, col: int, text: str) -> None:
        """A column heading: wrapped in its column."""
        self.put(row, col, text)
        self.looks[row, col] = "wrap"

    def big(self, row: int, col: int, value: Value, formula: str = "") -> None:
        """A title of 14 pt."""
        self.put(row, col, value, formula)
        self.looks[row, col] = "title"

    def con(self, c: Connector) -> _Con | None:
        box = self.project.connectors.get(c.mates_with or "")
        return self.cons.get(CON + box.id) if box is not None else None

    def build(self, drawings: bool) -> None:
        h, doc = self.h, self.project.meta.document
        system = (doc.system if doc else "") or self.project.meta.name
        self.put(5, COL_H, system)
        self.put(5, COL_N, h.id)
        self.put(5, COL_Q, f"VERSION: v{h.version} ({STATUS.get(h.status, h.status)})")
        if self.sgnd_open():
            self.put(5, COL_T, NO_SGND)
        self.put(8, COL_H, "\n".join(_length_lines(self.project)))  # H9: the length note
        for col in (COL_I, COL_M):
            self.put(1, col, SEARCH_LABEL)
            self.put(2, col, SEARCH_TEXT)
        row = self.part_tables()
        blocks = [(c, self.lines(c)) for c in self.near]
        further = self.place(blocks)
        self.title(system)
        for n, (c, lines) in enumerate(blocks):
            row = self.block(row, c, lines, first=n == 0)
        if further:
            row = self.further(row, further)
        last = self.sums(row)
        for _, con, _, group in self.columns.values():
            if con is not None and group is not None:
                last = max(last, self.reference(row, con, group))
        if drawings:
            last += 2
            self.put(last, COL_H, f"Block diagram: harnesses/{h.id}/drawing_A3.pdf")
        self.last = last

    def sgnd_open(self) -> bool:
        for c in self.h.connectors:
            box = self.project.connectors.get(c.mates_with or "")
            for p in box.pins if box is not None else []:
                if p.role == "signal_ground" and not self.ends.get((c.id, p.id)):
                    return True
        return False

    def title(self, system: str) -> None:
        refs, texts = [], []
        for end in (self.near, self.far):
            ref, text = [], []
            for c in end:
                con = self.con(c)
                if con is not None and con.device != TO_FILL:
                    ref.append(_there(con.name, 0, 1))
                    text.append(con.device)
                else:
                    word = OPEN_END if _is_open(c) else c.id
                    ref.append(_quoted(word))
                    text.append(word)
            refs.append('&" + "&'.join(ref))
            texts.append(" + ".join(text))
        formula = f'"Harness "&{_here(5, COL_H)}&"-"&{_here(5, COL_N)}&": "'
        value = f"Harness {system}-{self.h.id}: {texts[0]}"
        if refs[0]:
            formula += f"&{refs[0]}"
        if refs[1]:
            formula += f'&" <–> "&{refs[1]}'
            value += f" <–> {texts[1]}"
        self.big(7, COL_H, value, formula)

    def part_tables(self) -> int:
        project, h = self.project, self.h
        self.put(9, COL_H, "used Connectors")
        for col, text in (
            (COL_H, "No."),
            (COL_I, "Part No."),
            (COL_M, "Quantity"),
            (COL_N, "Remark"),
        ):
            self.head(10, col, text)
        row = 11
        parts: dict[str, list[Connector]] = defaultdict(list)
        for c in h.connectors:
            parts[c.part_id].append(c)
        for n, pid in enumerate(sorted(parts, key=natural_key), start=1):
            cs = sorted(parts[pid], key=lambda c: natural_key(c.id))
            part = project.parts.get(pid)
            remark = ", ".join(c.id for c in cs)
            if part is not None and part.part_number:
                remark += f"; {part.part_number}"
            self.put(row, COL_H, n)
            self.put(row, COL_I, f"{pid} ({OPEN_END})" if all(_is_open(c) for c in cs) else pid)
            self.put(row, COL_M, len(cs))
            self.put(row, COL_N, remark)
            row += 1
        self.put(row + 1, COL_H, "used Cable Types")
        for col, text in (
            (COL_H, "No."), (COL_I, "Part No."), (COL_K, "AWG"), (COL_L, "Conductor"), (COL_O, "Colours"),
            (COL_R, "No. of wires in cable"), (COL_S, LENGTH),
        ):  # fmt: skip
            self.head(row + 2, col, text)
        row += 3
        for n, pid in enumerate(self.types, start=1):
            ws = [w for w in h.wires if w.part_id == pid]
            part = project.parts.get(pid)
            gauges = sorted({w.gauge_awg for w in ws if w.gauge_awg is not None})
            self.put(row, COL_H, n)
            self.put(row, COL_I, pid)
            self.put(row, COL_K, gauges[0] if len(gauges) == 1 else ", ".join(map(str, gauges)))
            self.put(row, COL_L, (part.specification if part else None) or "")
            self.put(
                row, COL_O, ", ".join(sorted({w.colour for w in ws if w.colour}, key=str.casefold))
            )
            self.per_cable[pid] = part.conductors if part is not None else 1
            self.put(row, COL_R, self.per_cable[pid])
            self.type_rows[pid] = row
            row += 1
        self.put(row + 1, COL_H, "used Backshells")
        for col, text in (
            (COL_H, "No."),
            (COL_I, "Part No."),
            (COL_M, "Quantity"),
            (COL_N, "Remark"),
        ):
            self.head(row + 2, col, text)
        row += 3
        shells = sorted(
            (a for a in h.accessories if a.kind == "backshell"), key=lambda a: natural_key(a.id)
        )
        if not shells:
            self.put(row, COL_I, "No backshells.")
            row += 1
        for n, a in enumerate(shells, start=1):
            self.put(row, COL_H, n)
            _fill(self.g, row, COL_I, a.part_id)
            self.put(row, COL_M, a.quantity)
            self.put(
                row,
                COL_N,
                "; ".join(x for x in (f"on {a.target}" if a.target else "", a.note) if x),
            )
            row += 1
        return row + 1

    def lines(self, c: Connector) -> list[_Line]:
        """The pins of the box connector it plugs into, then its own wired pins the box lacks;
        without a CON_ sheet, its own pins."""
        con = self.con(c)
        box = self.project.connectors.get(c.mates_with or "") if con is not None else None
        if box is None or con is None:
            return [_Line(c, p, False, bool(self.ends.get((c.id, p.id)))) for p in c.pins]
        on_box = {p.id: p for p in box.pins}
        pins = [on_box[i] for i in con.order] if con.faces is not None else box.pins
        return [_Line(c, p, True, bool(self.ends.get((c.id, p.id)))) for p in pins] + [
            _Line(c, p, False, True)
            for p in c.pins
            if p.id not in on_box and self.ends.get((c.id, p.id))
        ]

    def place(self, blocks: list[tuple[Connector, list[_Line]]]) -> list[Wire]:
        """The wire of each near row (the first by ID that reaches the far end, directly or
        through splices, and is on no row yet) with every far pin it reaches, and the wires left
        over for *Further wires*."""
        column = {c.id: n for n, c in enumerate(self.far)}
        placed: set[str] = set()
        for c, lines in blocks:
            for line in lines:
                for w in self.ends.get((c.id, line.pin.id), []):
                    if w.id in placed:
                        continue
                    group = self.spliced[w.id]
                    far = [e for e in _plain_ends(group, self.h) if e[0] in column]
                    if not far:
                        continue
                    far.sort(key=lambda e: (column[e[0]], natural_key(e[1])))
                    line.wire = w
                    line.far = tuple(
                        (
                            self.far[column[cid]],
                            pin,
                            next(
                                x
                                for x in group
                                if (cid, pin)
                                in ((x.from_connector, x.from_pin), (x.to_connector, x.to_pin))
                            ),
                        )
                        for cid, pin in far
                    )
                    placed.add(w.id)
                    break
        return [
            w for w in sorted(self.h.wires, key=lambda x: natural_key(x.id)) if w.id not in placed
        ]

    def block(self, row: int, c: Connector, lines: list[_Line], first: bool) -> int:
        project, h = self.project, self.h
        con = self.con(c)
        box = self.project.connectors.get(c.mates_with or "") if con is not None else None
        part = project.parts.get(c.part_id)
        self.big(row, COL_B, box.id if box else c.id)
        if part is not None and part.link:
            self.put(row + 1, COL_H, f"Part link: {part.link}", link=part.link)
        if box is not None and con is not None:
            _link(self.g, row + 2, COL_B, box.source_doc or "", box.source_link)
            self.put(row + 3, COL_F, "Device Side")
            self.put(row + 4, COL_B, f"Data from {con.name}")
            self.put(row + 4, COL_F, con.description, _there(con.name, 10, 1))
        self.put(row + 3, COL_H, "Harness Side")
        ctype = (part.description if part else None) or c.part_id
        if _is_open(c):
            ctype = f"{OPEN_END}, {TO_FILL}"
        if box is not None and con is not None:
            dev = _there(con.name, 0, 1) if con.device != TO_FILL else _quoted(TO_FILL)
            # the last part: B2, the connector's ID; B4, its name, in harness_device_connector
            last, cell = (box.id, 1) if con.named is None else (con.named, 3)
            formula = f'{_quoted(ctype + " [")}&{_here(5, COL_N)}&":"&{dev}&":"&{_there(con.name, cell, 1)}&"]"'
            self.put(row + 4, COL_H, f"{ctype} [{h.id}:{con.device}:{last}]", formula)
        else:
            self.put(row + 4, COL_H, f"{ctype} [{h.id}:{c.id}]")
        head = row + 5
        if box is not None:
            for n, text in enumerate(DEVICE_HEAD):
                self.head(head, COL_B + n, text)
        if con is not None and con.faces is not None:
            self.head(head, COL_A, PIN_ROW)
        for n, text in enumerate(HARNESS_HEAD):
            self.head(head, COL_H + n, text)
        for fc, fcon, pin_col, group in self.columns.values():
            if _is_open(fc):
                label = f"{OPEN_END}, {TO_FILL}"
            else:
                label = f"Pinout (of {fcon.device if fcon else fc.id})"
            self.head(head, pin_col, label)
            if first and fcon is not None and group is not None:
                self.big(head - 2, group, fcon.name.removeprefix(CON))
                self.put(head - 1, group, f"Data from {fcon.name}")
                for n, text in enumerate(PIN_HEAD):
                    self.head(head, group + n, text)
        start = head + 1
        noted = any(w.value == NOT_CONNECTED for w in self.g.values())
        for n, line in enumerate(lines):
            noted = self.line(start + n, line, con, noted)
            what = f"pin {line.cable.id}.{line.pin.id}"
            self.rows[start + n] = f"wire {line.wire.id} ({what})" if line.wire else what
        end = start + max(len(lines), 1) - 1
        self.blocks.append((row, end))
        if lines:
            self.pin_rows += range(start, end + 1)
            self.wire_blocks.append((start, end))
            gnd = (
                f'OR(AND({_here(start, COL_J)}="GND";{_here(start, COL_R)}="PWR");'
                f'AND({_here(start, COL_R)}="GND";{_here(start, COL_J)}="PWR"))'
            )
            for col in (COL_J, COL_R):
                base = f"{_sheet_ref(self.name)}.{address(start, col)}"
                for r in range(start, end + 1):
                    self.conditions[r, col] = (*self.conditions.get((r, col), ()), (gnd, base))
            for col in (COL_I, COL_M):  # the search boxes: contains the text, an empty box no
                text = f"[.${column(col)}$3]"
                found = f'IF({text}="";0;ISNUMBER(SEARCH({text};{_here(start, col)})))'
                base = f"{_sheet_ref(self.name)}.{address(start, col)}"
                for r in range(start, end + 1):
                    self.conditions[r, col] = (*self.conditions.get((r, col), ()), (found, base))
        return end + 2

    def line(self, row: int, line: _Line, con: _Con | None, noted: bool) -> bool:
        project, w = self.project, line.wire
        pid = line.pin.id
        if line.box_pin and con is not None:
            pr, five = con.rows[pid], con.values[pid]
            self.put(row, COL_B, five[0], _there(con.name, pr, 0))
            for n in range(1, 5):
                self.copy(row, COL_B + n, five[n], _there(con.name, pr, n))
            if con.faces is not None:
                self.copy(row, COL_A, con.faces[pid], _there(con.name, pr, COL_F))
            if not line.wired:
                if not noted:
                    self.put(row, COL_I, NOT_CONNECTED)
                return True
            self.put(row, COL_H, five[0], _here(row, COL_B))
            self.copy(row, COL_I, five[1], _here(row, COL_C))
            self.mirror(row, COL_J, five[2], _here(row, COL_D))
            self.copy(row, COL_O, five[3], _here(row, COL_E))
        else:
            self.put(row, COL_H, cell_value(pid))
            self.put(row, COL_I, line.pin.signal or (w.signal if w else None) or "")
            self.put(row, COL_J, mirrored(direction_word(project, line.pin, line.cable)))
        if w is None or not line.far:
            return noted
        self.colour(row, COL_K, line.cable, pid, _here(row, COL_H), w)
        kind = self.wire_cells(row, w)
        if len(line.far) == 1:
            fc, fpin, fw = line.far[0]
            _, fcon, pin_col, group = self.columns[fc.id]
            self.put(row, pin_col, cell_value(fpin))
            # a straight row copies its own Cable / Type; through a splice, the far wire's
            self.put(
                row, COL_P, *((kind, _here(row, COL_L)) if fw.id == w.id else (self.kind(fw),))
            )
            self.colour(row, COL_Q, fc, fpin, _here(row, pin_col), fw)
            if fcon is not None and fpin in fcon.rows and group is not None:
                pr, five = fcon.rows[fpin], fcon.values[fpin]
                self.mirror(row, COL_R, five[2], _there(fcon.name, pr, 2))
                self.copy(row, COL_S, five[1], _there(fcon.name, pr, 1))
                self.put(row, group, five[0])
                for n in range(1, 5):
                    self.copy(row, group + n, five[n], _there(fcon.name, pr, n))
            else:
                pin = next((p for p in fc.pins if p.id == fpin), None)
                self.put(row, COL_R, mirrored(direction_word(project, pin, fc)) if pin else "")
                self.put(row, COL_S, (pin.signal if pin else None) or fw.signal or "")
                if group is not None:
                    self.put(row, group, cell_value(fpin))
            return noted
        # two or more far pins: values, each cell the far pins' values joined by " + "
        p_, q_, r_, s_ = [], [], [], []
        for fc, fpin, fw in line.far:
            _, fcon, _, _ = self.columns[fc.id]
            p_.append(str(self.kind(fw)))
            q_.append(str(self.colour_of(fc, fpin, fw)))
            if fcon is not None and fpin in fcon.rows:
                five = fcon.values[fpin]
                r_.append(mirrored(str(five[2])))
                s_.append(str(five[1]))
            else:
                pin = next((p for p in fc.pins if p.id == fpin), None)
                r_.append(mirrored(direction_word(project, pin, fc)) if pin else "")
                s_.append((pin.signal if pin else None) or fw.signal or "")
        for col, parts in ((COL_P, p_), (COL_Q, q_), (COL_R, r_), (COL_S, s_)):
            self.joined(row, col, parts)
        for fc, fcon, pin_col, group in self.columns.values():
            pins = [fpin for c, fpin, _ in line.far if c.id == fc.id]
            if not pins:
                continue
            self.put(row, pin_col, " + ".join(pins) if len(pins) > 1 else cell_value(pins[0]))
            if group is None:
                continue
            if len(pins) == 1:
                fpin = pins[0]
                if fcon is not None and fpin in fcon.rows:
                    pr, five = fcon.rows[fpin], fcon.values[fpin]
                    self.put(row, group, five[0])
                    for n in range(1, 5):
                        self.copy(row, group + n, five[n], _there(fcon.name, pr, n))
                else:
                    self.put(row, group, cell_value(fpin))
                continue
            for n in range(5):
                self.joined(
                    row,
                    group + n,
                    [
                        str(fcon.values[x][n])
                        if fcon is not None and x in fcon.rows
                        else (x if n == 0 else "")
                        for x in pins
                    ],
                )
        return noted

    def joined(self, row: int, col: int, parts: list[str]) -> None:
        """Several far pins' values in one cell, joined by " + ", empty ones in their place; no
        cell when all are empty."""
        if any(parts):
            self.put(row, col, " + ".join(parts))

    def copy(self, row: int, col: int, value: Value, ref: str) -> None:
        if value != "":
            self.put(row, col, value, ref)

    def mirror(self, row: int, col: int, word: Value, ref: str) -> None:
        if word:
            self.put(
                row, col, mirrored(str(word)), f'IF({ref}="IN";"OUT";IF({ref}="OUT";"IN";{ref}))'
            )

    def colour_of(self, c: Connector, pin: str, w: Wire) -> Value:
        """The colour of a wire end as a value: the code's colour of the pin, else the wire's."""
        code = self.by_part.get(c.part_id)
        if code is None:
            return w.colour or TO_FILL
        if pin not in dict(code.pins):
            return TO_FILL
        return lookup(self.tables[code.name][2], cell_value(pin)) or ""

    def kind(self, w: Wire) -> Value:
        return self.types.index(w.part_id) + 1 if w.part_id else TO_FILL

    def colour(self, row: int, col: int, c: Connector, pin: str, ref: str, w: Wire) -> None:
        code = self.by_part.get(c.part_id)
        if code is None:
            _fill(self.g, row, col, w.colour)
        elif pin not in dict(code.pins):
            self.put(row, col, TO_FILL)
        else:
            first, last, table = self.tables[code.name]
            area = f"[${NOTES}.$B${first + 1}:.$C${last + 1}]"
            formula = f'IF({ref}="";"";VLOOKUP({ref};{area};2;0))'
            self.put(row, col, lookup(table, cell_value(pin)) or "", formula)

    def wire_cells(self, row: int, w: Wire) -> Value:
        """Cable / Type, Shielding and Length of a wire's row; the Cable / Type."""
        kind = self.kind(w)
        self.put(row, COL_L, kind)
        self.put(row, COL_M, ", ".join(self.groups.get(w.id, [])))
        length = _length(self.h, w)
        self.put(row, COL_N, TO_FILL if length is None else round(length * 1000, 1) + 0.0)
        return kind

    def further(self, row: int, wires: list[Wire]) -> int:
        self.put(row, COL_H, "Further wires")
        for col, text in (
            (COL_H, "Wire"), (COL_I, "From"), (COL_J, "To"), (COL_K, "Color"), (COL_L, "Cable / Type"),
            (COL_M, "Shielding / (Grouping)"), (COL_N, LENGTH),
        ):  # fmt: skip
            self.head(row + 1, col, text)
        start = row + 2
        for n, w in enumerate(wires):
            self.put(start + n, COL_H, w.id)
            self.put(start + n, COL_I, f"{w.from_connector}.{w.from_pin}")
            self.put(start + n, COL_J, f"{w.to_connector}.{w.to_pin}")
            _fill(self.g, start + n, COL_K, w.colour)
            self.wire_cells(start + n, w)
            self.rows[start + n] = f"wire {w.id}"
        self.wire_blocks.append((start, start + len(wires) - 1))
        return start + len(wires) + 1

    def sums(self, row: int) -> int:
        self.put(row, COL_H, "Sum of length of cable type [mm]")
        for col, text in ((COL_H, "No."), (COL_I, "Part No."), (COL_N, "Sum of length [mm]")):
            self.head(row + 1, col, text)
        r = row + 1
        for no, pid in enumerate(self.types, start=1):
            r += 1
            lengths, missing, terms = [], 0, []
            for first, last in self.wire_blocks:
                terms.append(
                    f"SUMIF({_span(COL_L, first, last)};{_here(r, COL_H)};{_span(COL_N, first, last)})"
                )
                for x in range(first, last + 1):
                    kind, length = self.g.get((x, COL_L)), self.g.get((x, COL_N))
                    if kind is not None and kind.value == no and length is not None:
                        if isinstance(length.value, str):
                            missing += 1
                        else:
                            lengths.append(float(length.value))
            total = round(math.fsum(lengths) / self.per_cable[pid], 9) + 0.0
            self.put(r, COL_H, no)
            self.put(r, COL_I, pid)
            self.put(r, COL_N, total, f"({'+'.join(terms)})/{_here(self.type_rows[pid], COL_R)}")
            if missing:
                self.put(r, COL_O, f"{missing} wire{'s' if missing != 1 else ''} without a length")
            self.put(self.type_rows[pid], COL_S, total, _here(r, COL_N))
        return r

    def reference(self, row: int, con: _Con, col: int) -> int:
        box = self.project.connectors[con.name.removeprefix(CON)]
        self.big(row, col, box.id)
        _link(self.g, row + 1, col, box.source_doc or "", box.source_link)
        self.put(row + 2, col, f"Data from {con.name}")
        for n, text in enumerate([*PIN_HEAD, "Used in Row"]):
            self.head(row + 3, col + n, text)
        r = row + 3
        for pin in box.pins:
            r += 1
            pr, five = con.rows[pin.id], con.values[pin.id]
            self.put(r, col, five[0], _there(con.name, pr, 0))
            for n in range(1, 5):
                self.copy(r, col + n, five[n], _there(con.name, pr, n))
            if not self.pin_rows:
                continue
            first, last = self.pin_rows[0], self.pin_rows[-1]
            used = next(
                (
                    x
                    for x in range(first, last + 1)
                    if (cell := self.g.get((x, col))) is not None and _same(cell.value, five[0])
                ),
                None,
            )
            match = f"MATCH({_here(r, col)};{_span(col, first, last)};0)"
            self.put(
                r,
                col + 5,
                "" if used is None else used + 1,
                f'IF(ISNA({match});"";{match}+{first})',
            )
        return r


def _cover(project: Project, h: Harness, stamp: Stamp) -> Grid:
    g: Grid = {}
    doc = project.meta.document
    mine = doc.plans.get(h.id) if doc else None
    for r, label, value in (
        (1, "Doc.-No.", mine.number if mine else ""),
        (2, "Version", (mine.version if mine else "") or h.version),
        (3, "Release", mine.release if mine else ""),
    ):
        _put(g, r, 4, label)
        _fill(g, r, 5, value)
    title = (mine.title if mine else "") or (doc.title if doc else "")
    _put(g, 16, 0, project.meta.name)
    _put(g, 18, 0, title or f"{project.meta.name} Harness Plan")
    _fill(g, 20, 0, doc.company if doc else "")
    _put(g, 22, 0, stamp.line)
    _put(g, 23, 0, OVERWRITE)
    _put(g, 24, 0, stamp.notice)
    _put(g, 35, 2, "Contact Information")
    lines = doc.contact if doc else []
    for n, line in enumerate(lines):
        _put(g, 36 + n, 2, line.label)
        value, link = line.value, ""
        if value and not re.search(r"\s", value):
            if value.startswith("mailto:"):
                link = value
            elif value.count("@") == 1:
                link = f"mailto:{value}"
        _put(g, 36 + n, 3, value or TO_FILL, link=link)
    if not lines:
        _put(g, 36, 3, TO_FILL)
    return g


def _register(project: Project, h: Harness, sheet: str) -> Grid:
    g: Grid = {}
    _put(g, 1, COL_B, f"Change register of {h.id}")
    for n, text in enumerate(("Version", "Sub-Version", "Date", "Name", "Sheets", "Description")):
        _put(g, 3, COL_B + n, text)
    entries = sorted(
        (e for e in project.changelog.values() if e.harness_id == h.id),
        key=lambda e: natural_key(e.id),
    )
    for n, e in enumerate(entries):
        words, comment = CHANGES.get(e.kind, e.kind), " ".join(e.comment.split())
        for k, value in enumerate(
            (
                e.version,
                e.id,
                e.when,
                " ".join(e.by.split()),
                sheet,
                f"{words}: {comment}" if comment else words,
            )
        ):
            _put(g, 4 + n, COL_B + k, value)
    if not entries:
        _put(g, 4, COL_B, "No entry in the change log of this harness yet.")
    return g


def _notes(
    rule: str, codes: list[_Code], notes: list[str], h: Harness
) -> tuple[Grid, dict[str, tuple[int, int, tuple[tuple[Value, str], ...]]]]:
    """The Notes sheet and the rows of each code table it holds (first row, last row, cells)."""
    g: Grid = {}
    _put(g, 1, COL_B, "Notes")
    used: list[_Code] = []
    if rule == "pin_code":
        first: dict[str, str] = {}
        for code in codes:
            for part in code.parts:
                first.setdefault(part, code.name)
        names = {first[c.part_id] for c in h.connectors if c.part_id in first}
        used = [code for code in codes if code.name in names]
    tables = {}
    row = 4
    for code in used:
        _put(g, row, COL_B, EXAMPLE if code.example else f"Colour code {code.name}")
        _put(g, row + 1, COL_B, f"Code {code.name}, for the parts {', '.join(code.parts)}")
        _put(g, row + 2, COL_B, "Pin")
        _put(g, row + 2, COL_C, "Color")
        cells = tuple(
            (cell_value(pin), colour)
            for pin, colour in sorted(code.pins, key=lambda x: natural_key(x[0]))
        )
        for n, (pin, colour) in enumerate(cells):
            _put(g, row + 3 + n, COL_B, pin)
            _put(g, row + 3 + n, COL_C, colour)
        tables[code.name] = (row + 3, row + 3 + max(len(cells), 1) - 1, cells)
        row += 3 + len(cells) + 1
    for line in [*notes, *([""] if notes else []), *LEGEND]:
        _put(g, row, COL_B, line)
        row += 1
    return g, tables


def _production(
    project: Project, h: Harness, rule: str, codes: list[_Code]
) -> tuple[Grid, Printed]:
    """The sheet *Production* (4.1.0, part A) from the verifier's own rows
    (`verify_production.production_rows`): the title, the length note and the headings in rows 1
    to 3, then each block's heading row, its rows (the length in mm) and an empty row, the splices
    last under their own title; while the plan colours by pin code a column *Pigtail colour* after
    *Colour*: the colour of the code at this end (*to fill in* for a pin the code does not list,
    empty for a part without a code)."""
    g: Grid = {}
    looks: dict[tuple[int, int], str] = {(0, 0): "title"}
    pigtail = rule == "pin_code"
    heads = [*PRODUCTION_HEAD[:6], *([PIGTAIL] if pigtail else []), *PRODUCTION_HEAD[6:]]
    by_part: dict[str, _Code] = {}
    for listed in codes if pigtail else []:
        for part in listed.parts:
            by_part.setdefault(part, listed)
    _put(g, 0, 0, f"Production sheet of {h.id}")
    _put(g, 1, 0, "\n".join(_length_lines(project)))
    for n, text in enumerate(heads):
        _put(g, 2, n, text)
        looks[2, n] = "wrap"
    parts = {c.id: c.part_id for c in h.connectors}
    row, blocks, titled = 3, [], False
    for block in production_rows(project, h):
        first = row
        if block.splice and not titled:
            titled = True
            _put(g, row, 0, SPLICES)
            row += 2
        _put(g, row, 0, block.heading)
        row += 1
        code = by_part.get(parts[block.connector_id])
        for line in block.rows:
            cells: list[Value] = list(line)
            if not isinstance(cells[7], str):
                cells[7] = round(float(cells[7]) * 1000, 1) + 0.0
            if pigtail:
                colour: Value = ""
                pin = str(line[0])
                if line[3] and code is not None:
                    table = tuple(
                        (cell_value(k), v)
                        for k, v in sorted(code.pins, key=lambda x: natural_key(x[0]))
                    )
                    colour = (
                        (lookup(table, cell_value(pin)) or "")
                        if pin in dict(code.pins)
                        else TO_FILL
                    )
                cells.insert(6, colour)
            for n, v in enumerate(cells):
                _put(g, row, n, v)
                looks[row, n] = "wrap"
            row += 1
        blocks.append((first, row - 1))
        row += 1
    last = max(row - 2, 2)
    return g, Printed(
        PRODUCTION_HEADING, f"A1:{address(last, len(heads) - 1)}", tuple(blocks), looks
    )


def _about(stamp: Stamp) -> Grid:
    g: Grid = {}
    for r, (label, value) in enumerate(
        (("Generated by", stamp.line), ("Model hash", stamp.model_hash), ("Notice", stamp.notice))
    ):
        _put(g, r, 0, label)
        _put(g, r, 1, value)
    return g


def expected_plan(project: Project, h: Harness, stamp: Stamp, drawings: bool) -> Expected:
    """Every sheet and cell the plan of `h` must hold, worked out from the project alone."""
    ids = {c.mates_with for c in h.connectors if c.mates_with and not _is_open(c)}
    boxes = sorted(
        (project.connectors[i] for i in ids if i in project.connectors),
        key=lambda c: natural_key(c.id),
    )
    cons = {con.name: con for con in (_con(project, b) for b in boxes)}
    rule, codes, notes = _settings(project)
    notes_grid, tables = _notes(rule, codes, notes, h)
    name = plan_sheet_name(h)
    sheet = _HarnessSheet(project, h, name, cons, tables, rule, codes)
    sheet.build(drawings)
    production, printed = _production(project, h, rule, codes)
    return Expected(
        [
            (COVER, _cover(project, h, stamp)),
            (REGISTER, _register(project, h, name)),
            (name, sheet.g),
            (PRODUCTION, production),
            (NOTES, notes_grid),
            *((n, cons[n].grid) for n in cons),
            (ABOUT, _about(stamp)),
        ],
        name,
        sheet.conditions,
        sheet.rows,
        {
            name: Printed(
                HARNESS_HEADING,
                f"H6:{address(sheet.last, sheet.last_col)}",
                tuple(sheet.blocks),
                sheet.looks,
            ),
            PRODUCTION: printed,
        },
    )


# ---- reading the package -----------------------------------------------------------------------

_NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
    "manifest": "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0",
    "meta": "urn:oasis:names:tc:opendocument:xmlns:meta:1.0",
    "dc": "http://purl.org/dc/elements/1.1/",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
}


def _q(prefix: str, name: str) -> str:
    return f"{{{_NS[prefix]}}}{name}"


class PlanUnreadable(ValueError):
    """A part of the package that cannot be read; the message says why."""


def parse_xml(name: str, data: bytes) -> ElementTree.Element:
    """An XML entry of the package, parsed only when it holds no DOCTYPE or entity declaration."""
    low = data.lower()
    if b"<!doctype" in low or b"<!entity" in low:
        raise PlanUnreadable(
            f"{name} holds a DOCTYPE or entity declaration, which a plan never has; it was not read"
        )
    try:
        return ElementTree.fromstring(data)  # noqa: S314
    except (ElementTree.ParseError, LookupError, ValueError) as exc:
        raise PlanUnreadable(f"{name} is not well-formed XML ({exc})") from exc


_DAMAGE = (
    zipfile.BadZipFile,
    zlib.error,
    OSError,
    EOFError,
    NotImplementedError,
    KeyError,
    ValueError,
)


def check_package(data: bytes) -> tuple[list[str], dict[str, bytes]]:
    """The problems of the package (section 7.3), and its entries by name (those it could read)."""
    problems: list[str] = []
    entries: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            if names[:1] != ["mimetype"]:
                problems.append("mimetype is not its first entry")
            if names != list(ENTRIES):
                problems.append(
                    f"its entries are {', '.join(names) or 'none'}, not {', '.join(ENTRIES)} in that order"
                )
            for i in infos:
                if i.compress_type != zipfile.ZIP_STORED:
                    problems.append(f"the entry {i.filename} is compressed; every entry is stored")
                if i.date_time != ZIP_DATE:
                    problems.append(
                        f"the entry {i.filename} is dated {i.date_time}, not 1980-01-01 00:00:00"
                    )
                if i.create_system != 3 or i.external_attr != 0o644 << 16:
                    problems.append(
                        f"the entry {i.filename} does not have create_system 3 and the mode 644"
                    )
                if i.filename == "mimetype" and i.extra:
                    problems.append("the entry mimetype has an extra field")
            for name in dict.fromkeys(names):
                if name in ENTRIES:
                    entries[name] = z.read(name)
    except _DAMAGE as exc:
        return [*problems, f"it cannot be read as a zip package ({type(exc).__name__})"], entries
    if "mimetype" in entries and entries["mimetype"] != MIMETYPE.encode():
        problems.append(f"its mimetype is not {MIMETYPE}")
    return problems, entries


def check_manifest(root: ElementTree.Element) -> list[str]:
    """`META-INF/manifest.xml` lists `/` and every entry but `mimetype` and itself, nothing else."""
    listed = {
        e.get(_q("manifest", "full-path"), ""): e.get(_q("manifest", "media-type"), "")
        for e in root.iter(_q("manifest", "file-entry"))
    }
    want = {"/", *ENTRIES[2:]}
    out = []
    for name in sorted(want - set(listed)):
        out.append(f"the manifest does not list {name}")
    for name in sorted(set(listed) - want):
        out.append(f"the manifest lists {name}, which the package does not hold")
    if listed.get("/", MIMETYPE) != MIMETYPE:
        out.append(f"the manifest gives / the media type {listed['/']!r}, not {MIMETYPE}")
    return out


def check_meta(root: ElementTree.Element, h: Harness) -> list[str]:
    """`meta.xml` holds the generator and the title, and nothing else."""
    meta = root.find("office:meta", _NS)
    items = list(meta) if meta is not None else []
    got = {child.tag: child.text or "" for child in items}
    want = {
        _q("meta", "generator"): f"Harness Design Studio {__version__}",
        _q("dc", "title"): f"{h.id} harness plan",
    }
    return (
        []
        if got == want and len(items) == 2
        else ["meta.xml does not hold exactly the generator and the title"]
    )


@dataclass(frozen=True)
class Got:
    """A stored cell: its value type (`float`, `string` or empty), its value (a number's
    `office:value`, a formula's `office:string-value`, else the text), the text it shows, its
    formula as written (with `of:=`), its link."""

    kind: str
    value: str | float
    shown: str
    formula: str
    link: str


@dataclass
class Read:
    """The sheets of a plan as stored: by name in their order, each cell by (row, column), and the
    conditional formats of each cell ((formula, base cell), from its style)."""

    sheets: list[tuple[str, dict[tuple[int, int], Got]]]
    conditions: dict[str, dict[tuple[int, int], tuple[tuple[str, str], ...]]]


def _shown(p: ElementTree.Element) -> str:
    out = [p.text or ""]
    for child in p:
        if child.tag == _q("text", "s"):
            out.append(" " * int(child.get(_q("text", "c"), "1")))
        elif child.tag == _q("text", "tab"):
            out.append("\t")
        elif child.tag == _q("text", "line-break"):
            out.append("\n")
        elif child.tag == _q("text", "a"):
            out.append(_shown(child))
        out.append(child.tail or "")
    return "".join(out)


def _maps(root: ElementTree.Element) -> dict[str, tuple[tuple[str, str], ...]]:
    """The conditional formats of each automatic cell style: (formula, base cell) of its maps."""
    out = {}
    for st in root.iter(_q("style", "style")):
        maps = []
        for m in st.findall("style:map", _NS):
            cond = m.get(_q("style", "condition"), "")
            if cond.startswith("is-true-formula(") and cond.endswith(")"):
                cond = cond[len("is-true-formula(") : -1]
            maps.append((cond, m.get(_q("style", "base-cell-address"), "")))
        if maps:
            out[st.get(_q("style", "name"), "")] = tuple(maps)
    return out


def _count(element: ElementTree.Element, attr: str) -> int:
    n = int(element.get(_q("table", attr), "1"))
    if not 1 <= n <= 1_048_576:
        raise PlanUnreadable(f"a {attr} of {n} is not a count a sheet can have")
    return n


def read_cells(root: ElementTree.Element) -> Read:
    maps = _maps(root)
    read = Read([], {})
    for table in root.iter(_q("table", "table")):
        name = table.get(_q("table", "name"), "")
        cells: dict[tuple[int, int], Got] = {}
        conds: dict[tuple[int, int], tuple[tuple[str, str], ...]] = {}
        r = 0
        for row in table.iter(_q("table", "table-row")):
            rows = _count(row, "number-rows-repeated")
            c = 0
            for cell in row:
                n = _count(cell, "number-columns-repeated")
                if cell.tag == _q("table", "table-cell"):
                    kind = cell.get(_q("office", "value-type"), "")
                    formula = cell.get(_q("table", "formula"), "")
                    shown = "\n".join(_shown(p) for p in cell.findall("text:p", _NS))
                    a = cell.find(".//text:a", _NS)
                    link = a.get(_q("xlink", "href"), "") if a is not None else ""
                    value: str | float = shown
                    if kind == "float":
                        value = float(cell.get(_q("office", "value"), "nan"))
                    elif (
                        formula or kind == "string" and _q("office", "string-value") in cell.attrib
                    ):
                        value = cell.get(_q("office", "string-value"), "")
                    style = maps.get(cell.get(_q("table", "style-name"), ""), ())
                    stored = value != "" or formula or kind or shown
                    if (stored or style) and rows * n > MAX_REPEAT:
                        raise PlanUnreadable(
                            f"a cell of the sheet {name!r} is repeated {rows * n} times"
                        )
                    for rr in range(r, r + rows) if stored or style else ():
                        for cc in range(c, c + n):
                            if stored:
                                cells[rr, cc] = Got(kind, value, shown, formula, link)
                            if style:
                                conds[rr, cc] = style
                c += n
            r += rows
        read.sheets.append((name, cells))
        read.conditions[name] = conds
    return read


def plan_stamp(data: bytes) -> str:
    """The short model hash on the About sheet of a plan (cell B2), or '' when it cannot be read."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = parse_xml("content.xml", z.read("content.xml"))
        about = dict(read_cells(root).sheets).get(ABOUT, {})
    except (PlanUnreadable, *_DAMAGE):
        return ""
    cell = about.get((1, 1))
    return cell.value[:12] if cell is not None and isinstance(cell.value, str) else ""


# ---- the print set-up (4.1.0, design of 4.1.0 section 5.2) -------------------------------------

MAX_COLUMNS = 16_384  # more columns than a spreadsheet program has is damage, not a plan


@dataclass
class PrintSetUp:
    """The print set-up of a sheet as stored: the width of each column in mm (None for a column
    without a width in mm), the heading rows (first and last, 0-based) inside
    `table:table-header-rows`, the rows that start a page (`fo:break-before="page"` in their row
    style), the print range without its sheet names (`H6:AB178`) and the `style:scale-to` and
    `style:scale-to-pages` of its page layout (`styles.xml`)."""

    widths: list[Fraction | None]
    heading: tuple[int, int] | None
    breaks: list[int]
    print_range: str
    scale: str | None
    fit: str | None


def read_print(content: ElementTree.Element, styles: ElementTree.Element | None) -> dict[str, PrintSetUp]:  # fmt: skip
    """The print set-up of every sheet of `content.xml`, with the page layouts of `styles.xml`."""
    widths: dict[str, Fraction | None] = {}
    breaking: set[str] = set()
    masters: dict[str, str] = {}
    auto = content.find("office:automatic-styles", _NS)
    for st in auto if auto is not None else []:
        name, family = st.get(_q("style", "name"), ""), st.get(_q("style", "family"), "")
        if family == "table-column":
            props = st.find("style:table-column-properties", _NS)
            text = props.get(_q("style", "column-width"), "") if props is not None else ""
            m = re.fullmatch(r"([0-9]{1,6}(?:\.[0-9]{1,9})?)mm", text)
            widths[name] = Fraction(m.group(1)) if m else None
        elif family == "table-row":
            props = st.find("style:table-row-properties", _NS)
            if props is not None and props.get(_q("fo", "break-before")) == "page":
                breaking.add(name)
        elif family == "table":
            masters[name] = st.get(_q("style", "master-page-name"), "")
    layouts: dict[str, ElementTree.Element] = {}
    pages: dict[str, ElementTree.Element] = {}
    for layout in styles.iter(_q("style", "page-layout")) if styles is not None else ():
        props = layout.find("style:page-layout-properties", _NS)
        if props is not None:
            layouts[layout.get(_q("style", "name"), "")] = props
    for master in styles.iter(_q("style", "master-page")) if styles is not None else ():
        props = layouts.get(master.get(_q("style", "page-layout-name"), ""))
        if props is not None:
            pages[master.get(_q("style", "name"), "")] = props
    out: dict[str, PrintSetUp] = {}
    for table in content.iter(_q("table", "table")):
        cols: list[Fraction | None] = []
        for col in table.iter(_q("table", "table-column")):
            n = _count(col, "number-columns-repeated")
            if len(cols) + n > MAX_COLUMNS:
                raise PlanUnreadable(f"a sheet has more than {MAX_COLUMNS} columns")
            cols += [widths.get(col.get(_q("table", "style-name"), ""))] * n
        heading: tuple[int, int] | None = None
        breaks: list[int] = []
        r = 0
        for child in table:
            group = child.tag == _q("table", "table-header-rows")
            if not group and child.tag != _q("table", "table-row"):
                continue
            first = r
            for row in child.iter(_q("table", "table-row")):
                if row.get(_q("table", "style-name"), "") in breaking:
                    breaks.append(r)
                r += _count(row, "number-rows-repeated")
            if group and r > first:
                heading = (first, r - 1)
        ranges = table.get(_q("table", "print-ranges"), "")
        page = pages.get(masters.get(table.get(_q("table", "style-name"), ""), ""))
        out[table.get(_q("table", "name"), "")] = PrintSetUp(
            cols,
            heading,
            breaks,
            ":".join(part.rpartition(".")[2] for part in ranges.split(":")) if ranges else "",
            page.get(_q("style", "scale-to")) if page is not None else None,
            page.get(_q("style", "scale-to-pages")) if page is not None else None,
        )
    return out


def _scale(widths: Sequence[Fraction]) -> int:
    """The largest whole percent at which columns of these widths print one page wide, from 10 to
    100 (the verifier's own copy of the rule of section 5.1)."""
    total = sum(widths, Fraction(0))
    if total <= 0:
        return 100
    return min(100, max(10, math.floor(PAGE_WIDTH * 100 / total)))


def _heights(grid: Grid, looks: dict[tuple[int, int], str], widths: Sequence[Fraction | None]) -> list[Fraction]:  # fmt: skip
    """The estimated height of each row in mm at 100 %: a line a paragraph of 10 pt (14 pt for a
    title), and a wrapped text a line for each `CHAR` mm of characters in its column's width less
    `PAD`."""
    out = [LINE] * (max((r for r, _ in grid), default=-1) + 1)
    for (r, c), want in grid.items():
        if want.value == "":
            continue
        look = looks.get((r, c), "")
        texts = want.value.split("\n") if isinstance(want.value, str) else [""]
        if look == "wrap" and isinstance(want.value, str):
            width = widths[c] if c < len(widths) else None
            room = max((width or Fraction(0)) - PAD, Fraction(1))
            lines = sum(max(1, math.ceil(len(t) * CHAR / room)) for t in texts)
        else:
            lines = len(texts)
        out[r] = max(out[r], LINE * lines * (TITLE_SIZE if look == "title" else 1))
    return out


def _breaks(heights: list[Fraction], want: Printed, scale: int) -> list[int]:
    """The rows a page must start before: the first row of a block that would not fit in what is
    left of the page (A4 landscape at `scale`, less the heading rows), unless nothing is on the
    page yet; a row the estimate cannot place on the page starts the next one."""
    top, bottom = want.heading
    room = Fraction(PAGE_HEIGHT * 100, scale) - sum(heights[top : bottom + 1], Fraction(0))
    starts = {first: sum(heights[first : last + 1], Fraction(0)) for first, last in want.blocks}
    end = min(max((last for _, last in want.blocks), default=bottom) + 1, len(heights))
    out, used = [], Fraction(0)
    for r in range(bottom + 1, end):
        if r in starts and used > 0 and used + starts[r] > room:
            out.append(r)
            used = Fraction(0)
        if used > 0 and used + heights[r] > room:
            used = Fraction(0)
        used += heights[r]
    return out


def _rows_text(rows: Sequence[int]) -> str:
    return ", ".join(str(r + 1) for r in rows) or "none"


def _printed(out: _Findings, sheet: str, got: PrintSetUp | None, want: Printed, grid: Grid) -> None:
    """The print set-up of the harness sheet or of *Production* against the design (section 5.2)."""
    where = f"sheet {sheet!r}"
    if got is None:
        return
    if got.print_range != want.print_range:
        out.add(
            "out_plan",
            f"{where} prints the range {got.print_range or 'of the whole sheet'}, the design gives {want.print_range}",
        )
    first, _, last = want.print_range.partition(":")
    c0, c1 = _address_of(first)[1], _address_of(last)[1]
    widths = got.widths[c0 : c1 + 1]
    if len(widths) != c1 - c0 + 1 or any(w is None for w in widths):
        out.add("out_plan", f"{where} does not give every column of its print range a width in mm")
        return
    scale = _scale([w for w in widths if w is not None])
    if got.fit is not None:
        out.add(
            "out_plan",
            f"{where} is fitted to {got.fit} page(s) (style:scale-to-pages), where the design prints it at {scale} %",
        )
    if got.scale != f"{scale}%":
        out.add(
            "out_plan",
            f"{where} prints at {got.scale or 'no fixed scale'}, the design gives {scale}% from the widths of its print range",
        )
    if got.heading != want.heading:
        shown = f"rows {got.heading[0] + 1} to {got.heading[1] + 1}" if got.heading else "no rows"
        out.add(
            "out_plan",
            f"{where} repeats {shown} on every page, the design gives rows {want.heading[0] + 1} to {want.heading[1] + 1}",
        )
    starts = {a for a, _ in want.blocks}
    for b in got.breaks:
        if b not in starts:
            out.add(
                "out_plan", f"{where} has a page break before row {b + 1}, which starts no block"
            )
    wanted = _breaks(_heights(grid, want.looks, got.widths), want, scale)
    if got.breaks != wanted:
        out.add(
            "out_plan",
            f"{where} has page breaks before the rows {_rows_text(got.breaks)}, the design gives {_rows_text(wanted)} (a block that fits on a page is not split)",
        )


# ---- the formulas: the closed list and a small evaluator ---------------------------------------

_SHEET = r"\$?(?:'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_]*)"
_CELL = r"\$?[A-Z]{1,3}\$?[1-9][0-9]{0,6}"
_REF = re.compile(
    rf"\[(?P<s1>{_SHEET})?\.(?P<a1>{_CELL})(?::(?P<s2>{_SHEET})?\.(?P<a2>{_CELL}))?\]"
)
_TOKEN = re.compile(
    r'\s*(?:(?P<str>"(?:[^"]|"")*")|(?P<ref>\[[^\]]*\])|(?P<num>[0-9]+(?:\.[0-9]+)?(?![0-9A-Za-z_.]))'
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_.]*)|(?P<op>[;()&=/+]))"
)


class FormulaError(ValueError):
    """A formula outside the closed list of section 7.2; the message says why."""


@dataclass(frozen=True)
class _Ref:
    sheet: str
    first: tuple[int, int]
    last: tuple[int, int]
    area: bool  # written as a range (`[.L62:.L62]` is a range of one cell)


Node = tuple[
    object, ...
]  # ("str", s) | ("num", x) | ("ref", _Ref) | ("call", name, args) | (op, a, b)


def _sheet_of(s: str | None, here: str) -> str:
    if not s:
        return here
    s = s.removeprefix("$")
    return s[1:-1].replace("''", "'") if s.startswith("'") else s


def parse_formula(
    text: str, here: str, sheets: frozenset[str], functions: frozenset[str] = FUNCTIONS
) -> Node:
    """The tree of a formula of the closed list, or `FormulaError`: a function outside `functions`
    (INDIRECT, ADDRESS, OFFSET and HYPERLINK always), a reference not in OpenFormula form or to a
    sheet the plan does not have, a name outside a reference, another operator, a number with an
    exponent, a wrong count of arguments or a lookup that is not an exact match."""
    tokens: list[tuple[str, str]] = []
    pos = 0
    while text[pos:].strip():
        m = _TOKEN.match(text, pos)
        if m is None or m.lastgroup is None:
            rest = text[pos:].lstrip()[:1]
            why = (
                "'!' is not the sheet separator of OpenFormula"
                if rest == "!"
                else f"{rest!r} is not in the closed list"
            )
            raise FormulaError(why)
        tokens.append((m.lastgroup, m.group(m.lastgroup)))
        pos = m.end()
    at = 0

    def peek() -> str:
        return tokens[at][1] if at < len(tokens) else ""

    def take(want: str = "") -> tuple[str, str]:
        nonlocal at
        if at >= len(tokens) or (want and tokens[at][1] != want):
            raise FormulaError(f"{want or 'a value'} is missing")
        at += 1
        return tokens[at - 1]

    def level(n: int) -> Node:
        ops = ("=", "&", "+", "/")
        if n == len(ops):
            return primary()
        left = level(n + 1)
        while peek() == ops[n] and tokens[at][0] == "op":
            take()
            left = (ops[n], left, level(n + 1))
        return left

    def primary() -> Node:
        kind, tok = take()
        if kind == "str":
            return ("str", tok[1:-1].replace('""', '"'))
        if kind == "num":
            return ("num", float(tok))
        if kind == "ref":
            ref = _REF.fullmatch(tok)
            if ref is None:
                raise FormulaError(
                    f"{tok} is not a reference such as [.B34] or [$Notes.$B$7:.$C$43]"
                )
            s1 = _sheet_of(ref["s1"], here)
            s2 = _sheet_of(ref["s2"], s1)
            if s1 not in sheets or s2 not in sheets or s1 != s2:
                raise FormulaError(f"{tok} refers to a sheet the plan does not have")
            first = _address_of(ref["a1"])
            last = _address_of(ref["a2"]) if ref["a2"] else first
            if last[0] < first[0] or last[1] < first[1]:
                raise FormulaError(
                    f"{tok} is not a range from its top left to its bottom right cell"
                )
            return ("ref", _Ref(s1, first, last, bool(ref["a2"])))
        if kind == "op" and tok == "(":
            inner = level(0)
            take(")")
            return inner
        if kind == "name":
            name = tok.upper()
            if name in REFUSED or name.startswith("COM.MICROSOFT."):
                raise FormulaError(f"{tok} is not allowed in a plan")
            if name not in functions:
                raise FormulaError(
                    f"{tok} is not in the closed list ({', '.join(sorted(functions))})"
                )
            take("(")
            args = [level(0)]
            while peek() == ";":
                take()
                args.append(level(0))
            take(")")
            low, high = ARGUMENTS.get(name, (1, 255))
            if not low <= len(args) <= high:
                raise FormulaError(f"{name} takes {low} to {high} arguments here, not {len(args)}")
            exact = {"VLOOKUP": 3, "MATCH": 2}.get(name)
            if exact is not None and args[exact] != ("num", 0.0):
                raise FormulaError(f"{name} must be an exact match (last argument 0)")
            return ("call", name, tuple(args))
        raise FormulaError(f"{tok!r} cannot stand here")

    tree = level(0)
    if at != len(tokens):
        raise FormulaError(f"{tokens[at][1]!r} follows a complete formula")
    return tree


class _Empty:
    pass


@dataclass(frozen=True)
class _Error:
    code: str


EMPTY, NA = _Empty(), _Error("#N/A")
Scalar = str | float | bool | _Empty | _Error


@dataclass(frozen=True)
class _Area:
    cells: tuple[tuple[Scalar, ...], ...]


def _num(v: Scalar) -> float | _Error:
    if isinstance(v, _Error):
        return v
    if isinstance(v, _Empty):
        return 0.0
    if isinstance(v, str):
        return _Error("#VALUE!")
    return float(v)


def _text(v: Scalar) -> str | _Error:
    if isinstance(v, _Error):
        return v
    if isinstance(v, _Empty):
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        return number_text(v)
    return v


def _equal(a: Scalar, b: Scalar) -> bool:
    if isinstance(a, _Empty):
        a = "" if isinstance(b, str) else 0.0
    if isinstance(b, _Empty):
        b = "" if isinstance(a, str) else 0.0
    return _same(a, b)


class Evaluator:
    """Computes a formula of the closed list over the stored cells of a plan, as a spreadsheet
    program that recalculates would (text compared without regard to case)."""

    def __init__(self, sheets: dict[str, dict[tuple[int, int], Got]]) -> None:
        self.sheets = sheets

    def cell(self, sheet: str, row: int, col: int) -> Scalar:
        c = self.sheets.get(sheet, {}).get((row, col))
        if c is None or (c.value == "" and not c.formula):
            return EMPTY
        return c.value

    def value(self, node: Node) -> Scalar:
        v = self.eval(node)
        if isinstance(v, _Area):
            if len(v.cells) == 1 and len(v.cells[0]) == 1:
                return v.cells[0][0]
            return _Error("#VALUE!")
        return v

    def eval(self, node: Node) -> Scalar | _Area:
        kind = node[0]
        if kind in ("str", "num"):
            return node[1]  # type: ignore[return-value]
        if kind == "ref":
            ref = node[1]
            assert isinstance(ref, _Ref)  # noqa: S101 (the tree is built by parse_formula)
            (r0, c0), (r1, c1) = ref.first, ref.last
            if not ref.area:
                return self.cell(ref.sheet, r0, c0)
            return _Area(
                tuple(
                    tuple(self.cell(ref.sheet, r, c) for c in range(c0, c1 + 1))
                    for r in range(r0, r1 + 1)
                )
            )
        if kind == "call":
            return self.call(str(node[1]), node[2])  # type: ignore[arg-type]
        a, b = self.value(node[1]), self.value(node[2])  # type: ignore[arg-type]
        if kind == "=":
            return next((x for x in (a, b) if isinstance(x, _Error)), None) or _equal(a, b)
        if kind == "&":
            ta, tb = _text(a), _text(b)
            return ta if isinstance(ta, _Error) else tb if isinstance(tb, _Error) else ta + tb
        x, y = _num(a), _num(b)
        if isinstance(x, _Error) or isinstance(y, _Error):
            return x if isinstance(x, _Error) else y
        if kind == "+":
            return x + y
        return _Error("#DIV/0!") if y == 0 else x / y

    def _truth(self, node: Node) -> bool | _Error:
        v = self.value(node)
        if isinstance(v, _Error):
            return v
        if isinstance(v, str):
            return _Error("#VALUE!")
        return bool(v) if isinstance(v, bool) else _num(v) != 0

    def call(self, name: str, args: tuple[Node, ...]) -> Scalar | _Area:
        if name == "IF":
            cond = self._truth(args[0])
            if isinstance(cond, _Error):
                return cond
            if cond:
                return self.value(args[1])
            return self.value(args[2]) if len(args) > 2 else False
        if name in ("AND", "OR"):
            truths = [self._truth(a) for a in args]
            error = next((t for t in truths if isinstance(t, _Error)), None)
            if error is not None:
                return error
            return all(truths) if name == "AND" else any(truths)
        if name == "ISNA":
            return self.value(args[0]) == NA
        if name == "ISNUMBER":
            v = self.value(args[0])
            return isinstance(v, float) and not isinstance(v, bool)
        if name == "SEARCH":
            # the position of the first text in the second, without regard to case and as typed (the
            # plan turns wildcards and regular expressions off); an empty text to find is #VALUE!,
            # as LibreOffice 24.2 gives it (section 25)
            find, within = _text(self.value(args[0])), _text(self.value(args[1]))
            if isinstance(find, _Error) or isinstance(within, _Error):
                return find if isinstance(find, _Error) else within
            at = within.casefold().find(find.casefold()) if find else -1
            return _Error("#VALUE!") if at < 0 else float(at + 1)
        if name == "VLOOKUP":
            key, area, col = self.value(args[0]), self.eval(args[1]), _num(self.value(args[2]))
            if (
                not isinstance(area, _Area)
                or isinstance(col, _Error)
                or not 1 <= col <= len(area.cells[0])
            ):
                return _Error("#REF!")
            if isinstance(key, _Error):
                return key
            for row in area.cells:
                if not isinstance(row[0], _Empty) and _same(row[0], key):
                    return row[int(col) - 1]
            return NA
        if name == "MATCH":
            key, area = self.value(args[0]), self.eval(args[1])
            if not isinstance(area, _Area) or (len(area.cells) > 1 and len(area.cells[0]) > 1):
                return NA
            if isinstance(key, _Error):
                return key
            flat = [v for row in area.cells for v in row]
            return next(
                (
                    float(n)
                    for n, v in enumerate(flat, 1)
                    if not isinstance(v, _Empty) and _same(v, key)
                ),
                NA,
            )
        # SUMIF: the sum of the numbers of the third range where the first matches the criterion
        area, crit, sums = self.eval(args[0]), self.value(args[1]), self.eval(args[2])
        if not isinstance(area, _Area) or not isinstance(sums, _Area) or isinstance(crit, _Error):
            return _Error("#VALUE!")
        if [len(r) for r in area.cells] != [len(r) for r in sums.cells]:
            return _Error("#VALUE!")
        total = 0.0
        for ra, rs in zip(area.cells, sums.cells, strict=True):
            for a, s in zip(ra, rs, strict=True):
                if (
                    not isinstance(a, _Empty)
                    and _same(a, crit)
                    and isinstance(s, float)
                    and not isinstance(s, bool)
                ):
                    total += s
        return total


def _gives(result: Scalar, cell: Got) -> bool:
    """True when what a formula gives is its stored value (a number within 1e-9 of it)."""
    if isinstance(result, _Empty):
        result = 0.0  # a reference to an empty cell shows 0
    if isinstance(result, (bool, _Error)):
        return False
    if isinstance(result, float):
        return isinstance(cell.value, float) and cell.kind == "float" and _near(result, cell.value)
    return cell.kind == "string" and cell.value == result


def _near(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def _shown_result(result: Scalar) -> str:
    if isinstance(result, _Error):
        return result.code
    if isinstance(result, _Empty):
        return "0"
    text = _text(result)
    return repr(text) if isinstance(text, str) else text.code


# ---- the check of one plan ---------------------------------------------------------------------


class _Findings:
    """The findings of one plan, at most MAX_MESSAGES per code and the rest counted."""

    def __init__(self, r: VerifyReport, rel: str, obj: str) -> None:
        self.r, self.rel, self.obj = r, rel, obj
        self.count: Counter[str] = Counter()

    def add(self, code: str, message: str) -> None:
        self.count[code] += 1
        if self.count[code] <= MAX_MESSAGES:
            self.r.error(code, f"{self.rel}: {message}.", self.obj)

    def close(self) -> None:
        for code, n in sorted(self.count.items()):
            if n > MAX_MESSAGES:
                self.r.error(
                    code, f"{self.rel}: {n - MAX_MESSAGES} more findings of this kind.", self.obj
                )


def _show(v: object) -> str:
    if isinstance(v, float):
        return number_text(v)
    return repr(v)


def _want_kind(w: Want) -> str:
    return "float" if not isinstance(w.value, str) else "string"


def _cells(out: _Findings, sheet: str, got: dict[tuple[int, int], Got], want: Grid) -> None:
    """Every cell of a sheet against the design: value type, value, shown text and link."""
    for key in sorted(set(got) | set(want)):
        g, w = got.get(key), want.get(key)
        where = f"sheet {sheet!r}, cell {address(*key)}"
        if w is None:
            if g is not None and (g.value != "" or g.formula or g.shown):
                out.add(
                    "out_plan",
                    f"{where} holds {_show(g.value)}, where the design has an empty cell",
                )
            continue
        if g is None:
            out.add("out_plan", f"{where} is empty, where the design has {_show(w.value)}")
            continue
        if g.kind != _want_kind(w):
            out.add(
                "out_plan",
                f"{where} holds a {g.kind or 'cell without a type'}, where the design has a {_want_kind(w)} {_show(w.value)}",
            )
            continue
        if isinstance(w.value, str):
            same, shown = g.value == w.value, w.value
        else:
            same = isinstance(g.value, float) and _near(g.value, float(w.value))
            shown = number_text(float(w.value))
        if not same:
            out.add(
                "out_plan", f"{where} holds {_show(g.value)}, the design gives {_show(w.value)}"
            )
        elif g.shown != shown and not (
            not isinstance(w.value, str) and _same_number(g.shown, float(w.value))
        ):
            out.add("out_plan", f"{where} shows {g.shown!r} but stores {_show(g.value)}")
        if g.link != w.link:
            out.add("out_plan", f"{where} links to {g.link!r}, the design gives {w.link!r}")


def _same_number(text: str, v: float) -> bool:
    try:
        return _near(float(text), v)
    except ValueError:
        return False


def _formulas(
    out: _Findings,
    sheet: str,
    got: dict[tuple[int, int], Got],
    want: Grid,
    ev: Evaluator,
    names: frozenset[str],
) -> None:
    """Every formula: the text the design gives, in the closed list, giving its stored value."""
    for key in sorted(set(got) | set(want)):
        g, w = got.get(key), want.get(key)
        if g is None:
            continue
        where = f"sheet {sheet!r}, cell {address(*key)}"
        expected = w.formula if w is not None else ""
        if not g.formula:
            if expected:
                out.add("out_plan_formula", f"{where} has no formula, the design gives ={expected}")
            continue
        if not g.formula.startswith("of:="):
            out.add(
                "out_plan_formula",
                f"{where} has a formula that is not OpenFormula (of:=): {g.formula!r}",
            )
            continue
        text = g.formula.removeprefix("of:=")
        try:
            tree = parse_formula(text, sheet, names)
        except FormulaError as exc:
            out.add(
                "out_plan_formula",
                f"{where} has the formula ={text}, which is outside the closed list: {exc}",
            )
            continue
        if text != expected:
            if expected:
                out.add(
                    "out_plan_formula",
                    f"{where} has the formula ={text}, the design gives ={expected}",
                )
            else:
                out.add(
                    "out_plan_formula",
                    f"{where} has the formula ={text}, where the design has a value",
                )
        result = ev.value(tree)
        if not _gives(result, g):
            out.add(
                "out_plan_formula",
                f"{where}: ={text} gives {_shown_result(result)}, but the cell stores {_show(g.value)}",
            )


def _conditions(
    out: _Findings, sheet: str, got: dict[tuple[int, int], tuple[tuple[str, str], ...]],
    want: dict[tuple[int, int], tuple[tuple[str, str], ...]], names: frozenset[str],
) -> None:  # fmt: skip
    """The conditional formats by their formula text and base cell (their style is not checked)."""
    for key in sorted(set(got) | set(want)):
        g, w = got.get(key, ()), want.get(key, ())
        if g == w:
            continue
        where = f"sheet {sheet!r}, cell {address(*key)}"
        for formula, _ in g:
            try:
                parse_formula(formula, sheet, names, CONDITION_FUNCTIONS)
            except FormulaError as exc:
                out.add(
                    "out_plan_formula",
                    f"{where} has a conditional format ={formula}, which is outside the closed list: {exc}",
                )
        shown = "; ".join(f"={f} from {b}" for f, b in g) or "none"
        wanted = "; ".join(f"={f} from {b}" for f, b in w) or "none"
        out.add(
            "out_plan_formula",
            f"{where} has the conditional formats {shown}, the design gives {wanted}",
        )


def _signature(cells: dict[tuple[int, int], object], row: int) -> tuple[tuple[int, object], ...]:
    def key(v: object) -> object:
        return round(float(v), 6) if isinstance(v, int | float) and not isinstance(v, bool) else v

    return tuple(sorted((c, key(v)) for (r, c), v in cells.items() if r == row and v != ""))


def _rows(
    out: _Findings, sheet: str, got: dict[tuple[int, int], Got], want: Grid, rows: dict[int, str]
) -> None:
    """Each pin row and each wire's row once: a row missing or a wire in two rows of the sheet."""
    got_values: dict[tuple[int, int], object] = {k: g.value for k, g in got.items()}
    want_values: dict[tuple[int, int], object] = {k: w.value for k, w in want.items()}
    wanted = {r: _signature(want_values, r) for r in rows}
    found = Counter(_signature(got_values, r) for r in sorted({r for r, _ in got}))
    counts = Counter(wanted.values())
    for r, what in sorted(rows.items()):
        n, k = found[wanted[r]], counts[wanted[r]]
        if n < k:
            out.add("out_plan", f"sheet {sheet!r}: the row of {what} (row {r + 1}) is missing")
        elif n > k:
            out.add("out_plan", f"sheet {sheet!r}: {what} is in {n} rows, the design has it in {k}")


def check_settings(root: ElementTree.Element) -> list[str]:
    """`content.xml` turns regular expressions and wildcards off, so that a search text, a lookup key
    and a SUMIF criterion are read as typed (section 25); without the element ODF's default turns
    regular expressions on."""
    sheet = root.find("office:body/office:spreadsheet", _NS)
    settings = sheet.find("table:calculation-settings", _NS) if sheet is not None else None
    if settings is None:
        return [
            "content.xml has no table:calculation-settings, so a reader takes a search text or a "
            "lookup key as a regular expression (the default of ODF)"
        ]
    return [
        f"content.xml sets table:{name} to {settings.get(_q('table', name), default)!r}, not "
        "'false': a reader would not take a search text or a lookup key as typed"
        for name, default in (("use-regular-expressions", "true"), ("use-wildcards", "false"))
        if settings.get(_q("table", name), default) != "false"
    ]


def check_plan(
    r: VerifyReport, project: Project, h: Harness, rel: str, data: bytes, drawings: bool
) -> None:
    """The checks of section 7.5 on the plan of one harness; findings go into `r`."""
    out = _Findings(r, rel, h.id)
    problems, entries = check_package(data)
    roots: dict[str, ElementTree.Element] = {}
    for name in ENTRIES[1:]:
        if name not in entries:
            continue
        try:
            roots[name] = parse_xml(name, entries[name])
        except PlanUnreadable as exc:
            problems.append(str(exc))
    if "META-INF/manifest.xml" in roots:
        problems += check_manifest(roots["META-INF/manifest.xml"])
    if "meta.xml" in roots:
        problems += check_meta(roots["meta.xml"], h)
    for p in problems:
        out.add("out_plan_package", p)
    if "content.xml" in roots:
        for p in check_settings(roots["content.xml"]):
            out.add("out_plan_formula", p)
        try:
            read = read_cells(roots["content.xml"])
            prints = read_print(roots["content.xml"], roots.get("styles.xml"))
        except (PlanUnreadable, ValueError) as exc:
            out.add("out_plan_package", f"content.xml cannot be read ({exc})")
        else:
            _compare(out, project, h, read, drawings, prints)
    out.close()


def _compare(
    out: _Findings,
    project: Project,
    h: Harness,
    read: Read,
    drawings: bool,
    prints: dict[str, PrintSetUp] | None = None,
) -> None:
    want = expected_plan(project, h, stamp_of(project), drawings)
    names = [n for n, _ in want.sheets]
    have = [n for n, _ in read.sheets]
    for n in names:
        if n not in have:
            out.add("out_plan", f"the sheet {n!r} is missing")
    for n in have:
        if n not in names:
            out.add("out_plan", f"the sheet {n!r} is not a sheet of the plan of {h.id}")
    if len(set(have)) != len(have):
        out.add("out_plan", "a sheet name is used twice")
    common = [n for n in have if n in names]
    if common != [n for n in names if n in have]:
        out.add(
            "out_plan", f"the sheets are in the order {', '.join(have)}, not {', '.join(names)}"
        )
    stored = dict(read.sheets)
    ev = Evaluator(stored)
    known = frozenset(have)
    for name, grid in want.sheets:
        if name not in stored:
            continue
        if name == want.harness_sheet:  # first: a row missing or twice moves every cell under it
            _rows(out, name, stored[name], grid, want.rows)
        _cells(out, name, stored[name], grid)
        _formulas(out, name, stored[name], grid, ev, known)
        wanted = want.conditions if name == want.harness_sheet else {}
        _conditions(out, name, read.conditions.get(name, {}), wanted, known)
        if prints is not None and name in want.printed:
            _printed(out, name, prints.get(name), want.printed[name], grid)


# ---- the plans of an output set ----------------------------------------------------------------

_PLAN = re.compile(r"harnesses/([^/]+)/([^/]+)_plan\.ods")


def _listed(files: dict[str, bytes]) -> list[str] | None:
    """The paths `manifest.json` lists, or None for a set without a manifest that can be read."""
    raw = files.get("manifest.json")
    if raw is None:
        return None
    try:
        return [str(f["path"]) for f in json.loads(raw)["files"]]
    except ValueError, KeyError, TypeError:
        return None


def plan_path(h: Harness) -> str:
    return f"harnesses/{h.id}/{h.id}{PLAN_SUFFIX}"


def has_drawings(files: dict[str, bytes]) -> bool:
    return any(re.fullmatch(r"harnesses/[^/]+/drawing_[^/]+\.pdf", k) for k in files)


def verify_plans(
    r: VerifyReport,
    project: Project,
    files: dict[str, bytes],
    guard: Callable[[str, Callable[[], None]], None],
) -> None:
    """Each plan the manifest lists (each plan of the set when it has no manifest) against its
    harness; a plan of a harness that is no longer in the design; and, in a set that has plans,
    a harness without its plan. `guard` turns damage into a finding (`verify._guard`)."""
    listed = _listed(files)
    paths = sorted(p for p in (listed if listed is not None else files) if _PLAN.fullmatch(p))
    drawings = has_drawings(files)
    for rel in paths:
        m = _PLAN.fullmatch(rel)
        assert m is not None  # noqa: S101 (filtered above)
        folder, stem = m.groups()
        h = project.harnesses.get(folder)
        if h is None:
            r.error(
                "out_plan", f"{rel} is the plan of {folder}, which is no longer in the design.", rel
            )
            continue
        if stem != folder:
            r.error(
                "out_plan",
                f"{rel} is not a plan the tool writes: the plan of {folder} is {plan_path(h)}.",
                rel,
            )
            continue
        if rel in files:  # a listed plan that is missing is out_missing (verify._manifest)
            guard(rel, lambda h=h, rel=rel: check_plan(r, project, h, rel, files[rel], drawings))  # type: ignore[misc]
    if paths:
        for hid in sorted(set(project.harnesses) - {_PLAN.fullmatch(p).group(1) for p in paths}):  # type: ignore[union-attr]
            r.error(
                "out_plan",
                f"{plan_path(project.harnesses[hid])} is missing: the export has harness plans, but none for {hid}.",
                hid,
            )


__all__ = [
    "Evaluator",
    "Expected",
    "FormulaError",
    "Got",
    "PlanUnreadable",
    "PrintSetUp",
    "Printed",
    "Want",
    "cell_value",
    "check_package",
    "check_plan",
    "direction_word",
    "expected_plan",
    "lookup",
    "mirrored",
    "parse_formula",
    "parse_xml",
    "plan_sheet_name",
    "plan_sides",
    "plan_stamp",
    "read_cells",
    "read_print",
    "verify_plans",
]
