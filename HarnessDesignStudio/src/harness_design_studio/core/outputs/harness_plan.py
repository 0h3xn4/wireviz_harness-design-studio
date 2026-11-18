# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The harness plan: one `.ods` per harness in the users' layout (D-242, design of 3.0.0 section 3).

    data = plan_ods(project, harness, stamp, drawings=False)   # harnesses/<ID>/<ID>_plan.ods

The sheets, in the order of section 3.7: *Cover*, *Change_Register*, the harness sheet (named after
the harness), *Notes*, one `CON_<box connector>` sheet per box connector the harness plugs into (in
connector ID order) and *About*. The harness sheet has the header, the part tables, one block of rows
per connector of the near end (one row per pin), the wires that do not end on a near pin, the sums
per cable type and the reference pinouts of the far box connectors.

The two ends are split by the sides rule of section 9 (`plan_sides`): a connector that is not a
splice is a node; two are joined when wires, through splices (`core/nets.py`), reach both; the graph
is coloured in two by a walk in breadth in natural ID order, and the end with more connectors is the
near end. A near row reaches every far pin that its wire reaches through splices (`joined_wires`);
a wire that ends on no near row is listed under *Further wires*, so every wire is in one row. A cell is a formula where section 7.1 says
(the copies of the `CON_…` sheets, the mirrored directions, the colours by pin code, the titles, the
descriptions, the sums and *Used in Row*), always with its stored value worked out here; everything
the model holds is a plain value. A copy of a cell that is empty is an empty cell, not a formula: a
reference to an empty cell shows 0 (section 2). The writer is `ods.py`; nothing here reads a file.
"""

import math
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from harness_design_studio.core.generate.lengths import wire_length
from harness_design_studio.core.issues import Issue
from harness_design_studio.core.links import effective_role
from harness_design_studio.core.model import Connector, Harness, Pin, Project, Wire
from harness_design_studio.core.nets import splice_ids
from harness_design_studio.core.vcs.report import one_line

from . import ods
from .ods import Cell, Condition, Page, Sheet, Style, Workbook, column, sheet_ref
from .stamp import Stamp
from .tables import OPEN_END, TO_FILL, is_open_end, natural_key

FILE_SUFFIX = "_plan.ods"
COVER, REGISTER, NOTES, ABOUT = "Cover", "Change_Register", "Notes", "About"
CON_PREFIX = "CON_"
OVERWRITE_TEXT = (
    "This file is written by Harness Design Studio. An export overwrites it; work on a copy."
)
NOT_CONNECTED_TEXT = "Not connected pins will be marked yellow"
NO_SGND = "[no SGND*]"
NO_BACKSHELLS = "No backshells."
EXAMPLE_HEADING = (
    "Example colour code from the users' template: check it against the supplier's pigtail code"
)
STATUS_WORDS = {"draft": "draft", "in_review": "in review", "released": "released"}
CHANGE_WORDS = {
    "review": "in review",
    "release": "released",
    "new_version": "new version",
    "version_changed": "version changed",
}
# Section 4.3: the Direction word of a pin, role first, then direction (Q16 for IN/OUT and SHIELD)
ROLE_WORDS = {
    "power": "PWR",
    "return": "PWR-RET",
    "ground": "GND",
    "signal_ground": "SGND",
    "shield": "SHIELD",
    "spare": "",
}
DIRECTION_WORDS = {"in": "IN", "out": "OUT", "bidir": "IN/OUT", "": ""}
MIRRORED = {"IN": "OUT", "OUT": "IN"}
COLOUR_RULES = ("wire", "pin_code")

# The template's colours (section 2)
_BLUE, _GREY, _LIGHT, _RED = "#9bc2e6", "#dddddd", "#eeeeee", "#ce181e"
_YELLOW, _AMBER, _REGISTER = "#ffff99", "#ffe699", "#83caff"
TITLE = Style(bold=True, size_pt=14)
BIG = Style(bold=True, size_pt=20, align="center")
HEAD = Style(bold=True, background=_BLUE, border=True, wrap=True)
BOLD = Style(bold=True)
GREY = Style(background=_GREY, border=True)
TYPED = Style(colour=_RED, background=_LIGHT, border=True)
FILL = Style(background=_AMBER, border=True)
YELLOW = Style(background=_YELLOW, border=True)
BOX = Style(border=True)
RED_BOLD = Style(bold=True, colour=_RED)
REGISTER_HEAD = Style(bold=True, background=_REGISTER, border=True)
WRAP = Style(wrap=True)

# The columns of the harness sheet (0-based): the device side B:F, the harness side H:S, then one
# far pin column per far connector from T, a gap, and a group of seven columns per far box connector
COL_B, COL_C, COL_D, COL_E, COL_F, COL_H = 1, 2, 3, 4, 5, 7
COL_I, COL_J, COL_K, COL_L, COL_M, COL_N, COL_O = 8, 9, 10, 11, 12, 13, 14
COL_P, COL_Q, COL_R, COL_S, COL_T = 15, 16, 17, 18, 19
GROUP_WIDTH = 7  # Pinout, Function, Direction, Level, Description, Used in Row, a gap
HARNESS_HEAD = [
    "Pinout", "Function", "Direction", "Color", "Cable / Type", "Shielding / (Grouping)",
    "Length [mm]", "Level", "Cable / Type", "Color", "Direction", "Function",
]  # fmt: skip
DEVICE_HEAD = ["Pin No.", "Function", "Direction", "Level", "Description"]
PIN_HEAD = ["Pinout", "Function", "Direction", "Level", "Description"]

Value = str | int | float


# ---- what the model gives, worked out once ----------------------------------------------------


def cell_value(pin_id: str) -> Value:
    """A pin ID as a cell: a number when it is a whole number without a leading zero, else text."""
    return int(pin_id) if re.fullmatch(r"0|[1-9][0-9]{0,14}", pin_id) else pin_id


def direction_word(project: Project, pin: Pin, connector: Connector | None) -> str:
    """The word of a pin in the Direction column (section 4.3): the effective role first (`PWR`,
    `PWR-RET`, `GND`, `SGND`, `SHIELD`, empty for a spare pin), else the direction (`IN`, `OUT`,
    `IN/OUT`), else empty."""
    role = effective_role(pin, project, connector)
    if role in ROLE_WORDS:
        return ROLE_WORDS[role]
    return DIRECTION_WORDS[pin.direction]


def mirrored(word: str) -> str:
    """The word seen from the harness side: `IN` and `OUT` swap, the others stay."""
    return MIRRORED.get(word, word)


@dataclass(frozen=True)
class Sides:
    """The cable connectors of a harness split into the near end (blocks of rows) and the far end
    (columns), each in natural ID order."""

    near: tuple[Connector, ...]
    far: tuple[Connector, ...]


def _ends(w: Wire) -> tuple[tuple[str, str], tuple[str, str]]:
    return (w.from_connector, w.from_pin), (w.to_connector, w.to_pin)


def joined_wires(h: Harness) -> dict[str, tuple[Wire, ...]]:
    """Wire ID -> the wires joined to it through splices, itself included, in natural ID order: a
    splice node (`core/nets.py`) joins every wire on it, the pin of any other connector joins none
    (two wires on one such pin are the finding `pin-shared`, and each keeps a row of its own). A
    wire with no end on a splice is alone."""
    splices = splice_ids(h)
    wires = sorted(h.wires, key=lambda x: natural_key(x.id))
    parent = {w.id: w.id for w in wires}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    first: dict[tuple[str, str], str] = {}
    for w in wires:
        for end in _ends(w):
            if end[0] in splices:
                a, b = find(first.setdefault(end, w.id)), find(w.id)
                parent[b] = a
    groups: dict[str, list[Wire]] = defaultdict(list)
    for w in wires:
        groups[find(w.id)].append(w)
    return {w.id: tuple(groups[find(w.id)]) for w in wires}


def reached_pins(group: Sequence[Wire], splices: set[str]) -> list[tuple[str, str]]:
    """The pins of a group of joined wires that are on no splice, each once, in the order met."""
    out: list[tuple[str, str]] = []
    for w in group:
        for end in _ends(w):
            if end[0] not in splices and end not in out:
                out.append(end)
    return out


def plan_sides(h: Harness) -> Sides:
    """The sides rule of section 9: a connector that is not a splice is a node, and two are joined
    when a group of wires joined through splices (`joined_wires`) reaches both; without a splice, a
    wire joins its two connectors. A walk in breadth from the first connector in natural ID order,
    neighbours in natural ID order, gives the first end the even steps and the second end the odd
    ones; a connector the walk has not reached (another part of the graph, or a connector without
    a wire) starts a new walk in the first end. The end with more connectors is the near end; on a
    tie the end of the first connector. Splices are in neither end."""
    splices = splice_ids(h)
    order = sorted(
        (c for c in h.connectors if c.id not in splices), key=lambda c: natural_key(c.id)
    )
    links: dict[str, set[str]] = defaultdict(set)
    for group in {g[0].id: g for g in joined_wires(h).values()}.values():
        connectors = {c for c, _ in reached_pins(group, splices)}
        for a in connectors:
            links[a] |= connectors - {a}
    end: dict[str, int] = {}
    for start in order:
        if start.id in end:
            continue
        end[start.id] = 0
        queue = [start.id]
        while queue:
            here = queue.pop(0)
            for nxt in sorted(links[here], key=natural_key):
                if nxt not in end:
                    end[nxt] = 1 - end[here]
                    queue.append(nxt)
    first = tuple(c for c in order if end.get(c.id) == 0)
    second = tuple(c for c in order if end.get(c.id) == 1)
    return Sides(first, second) if len(first) >= len(second) else Sides(second, first)


@dataclass(frozen=True)
class ColourCode:
    """A colour code of `config/harness_plan.json` (section 6): pins (IDs as text) to colours."""

    name: str
    parts: tuple[str, ...]
    pins: tuple[tuple[str, str], ...]
    example: bool = False


@dataclass(frozen=True)
class PlanSettings:
    colour_rule: str = "wire"
    codes: tuple[ColourCode, ...] = ()
    notes: tuple[str, ...] = ()


def plan_settings(project: Project) -> PlanSettings:
    """The settings of the plan; no file, or a value `validate` refuses, is the default."""
    c = project.config.get("harness_plan")
    values = dict(c.values) if c is not None else {}
    rule = values.get("colour_rule")
    codes = []
    raw = values.get("colour_codes")
    for code in raw if isinstance(raw, list) else []:
        if not isinstance(code, dict) or not isinstance(code.get("name"), str):
            continue
        parts = code.get("parts", [])
        pins = code.get("pins", {})
        codes.append(
            ColourCode(
                code["name"],
                tuple(x for x in parts if isinstance(x, str)) if isinstance(parts, list) else (),
                tuple((str(k), v) for k, v in pins.items() if isinstance(v, str) and v)
                if isinstance(pins, dict)
                else (),
                code.get("example") is True,
            )
        )
    notes = values.get("notes")
    return PlanSettings(
        rule if rule in COLOUR_RULES else "wire",
        tuple(codes),
        tuple(n for n in notes if isinstance(n, str)) if isinstance(notes, list) else (),
    )


def _same(a: Value, b: Value) -> bool:
    """How a spreadsheet's exact match compares two cells: a number with a number, text with text
    without regard to case."""
    if isinstance(a, str) and isinstance(b, str):
        return a.casefold() == b.casefold()
    return not isinstance(a, str) and not isinstance(b, str) and a == b


def lookup(rows: Sequence[tuple[Value, str]], key: Value) -> str | None:
    """What `VLOOKUP(key; table; 2; 0)` gives over the rows of a code table: the colour of the first
    row whose pin matches, or None (`#N/A`)."""
    return next((colour for pin, colour in rows if _same(pin, key)), None)


# ---- a grid of cells --------------------------------------------------------------------------


class _Grid:
    """Cells by (row, column), both 0-based; `rows()` gives the writer's rows."""

    def __init__(self) -> None:
        self.cells: dict[tuple[int, int], Cell] = {}

    def put(self, row: int, col: int, value: Value, style: Style = ods.PLAIN, **kw: object) -> None:
        self.cells[row, col] = Cell(value, style=style, **kw)  # type: ignore[arg-type]

    def set(self, row: int, col: int, cell: Cell | None) -> None:
        if cell is not None:
            self.cells[row, col] = cell

    def get(self, row: int, col: int) -> Cell | None:
        return self.cells.get((row, col))

    def rows(self) -> tuple[tuple[Cell | None, ...], ...]:
        if not self.cells:
            return ()
        height = max(r for r, _ in self.cells) + 1
        width: dict[int, int] = defaultdict(int)
        for r, c in self.cells:
            width[r] = max(width[r], c + 1)
        return tuple(tuple(self.cells.get((r, c)) for c in range(width[r])) for r in range(height))


def _addr(row: int, col: int) -> str:
    return f"{column(col)}{row + 1}"


def _here(row: int, col: int) -> str:
    return f"[.{_addr(row, col)}]"


def _span(col: int, first: int, last: int) -> str:
    return f"[.{_addr(first, col)}:.{_addr(last, col)}]"


def _there(sheet: str, row: int, col: int) -> str:
    return f"[${sheet_ref(sheet)}.{_addr(row, col)}]"


def _text(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'


def _copy(value: Value, ref: str, style: Style = ods.PLAIN) -> Cell | None:
    """A cell that copies `ref`, or None while the source is empty (a copy of it would show 0)."""
    return Cell(value, formula=ref, style=style) if value != "" else None


def _mirror(value: str, ref: str, style: Style = ods.PLAIN) -> Cell | None:
    formula = f'IF({ref}="IN";"OUT";IF({ref}="OUT";"IN";{ref}))'
    return Cell(mirrored(value), formula=formula, style=style) if value else None


def _filled(value: object, style: Style = BOX) -> Cell:
    """A document or design value, or *to fill in* on amber while it is empty."""
    if value is None or value == "":
        return Cell(TO_FILL, style=FILL)
    return Cell(value, style=style)  # type: ignore[arg-type]


def _joined(g: _Grid, row: int, col: int, parts: Sequence[str]) -> None:
    """The values of several far pins in one cell, joined by ` + ` in their order (an empty value
    keeps its place); no cell while every value is empty."""
    if any(parts):
        g.put(row, col, " + ".join(parts), BOX)


def _link_cell(text: str, link: str | None, style: Style = ods.PLAIN) -> Cell | None:
    if not text and not link:
        return None
    return Cell(text or link or "", link=link or "", style=style)


def _footer(stamp: Stamp) -> str:
    return f"{stamp.line}\n{stamp.notice}"


# ---- the CON_ sheets (section 3.6) ------------------------------------------------------------

CON_FIRST_PIN_ROW = 18  # 0-based: row 19, under the heading in row 18


@dataclass(frozen=True)
class ConSheet:
    """The sheet of one box connector and where each of its pins is."""

    name: str
    sheet: Sheet
    pins: dict[str, int]  # pin ID -> 0-based row
    values: dict[str, tuple[Value, str, str, str, str]]  # pin ID -> the five cells A to E
    device: str  # B1 as shown
    description: str  # B11 as shown


def con_name(box: Connector) -> str:
    return CON_PREFIX + box.id


def con_sheet(project: Project, box: Connector, stamp: Stamp) -> ConSheet:
    """The `CON_…` sheet of a box connector: the same, cell for cell, in every plan that has it
    (it reads the project only, never the harness)."""
    name = con_name(box)
    part = project.parts.get(box.part_id)
    interfaces = sorted(
        i.name
        for i in project.interfaces.values()
        if any(e.connector_id == box.id for e in i.endpoints)
    )
    ctype = (part.description if part else None) or box.part_id
    count: int = (part.pin_count if part else None) or len(box.pins)
    device = box.unit_id or ""
    g = _Grid()
    rows: list[tuple[str, Cell | None]] = [
        ("Device", _filled(device, ods.PLAIN)),
        ("Connector ID", Cell(box.id)),
        ("Interface Name", Cell("; ".join(interfaces)) if interfaces else None),
        ("", None),
        ("", None),
        ("Connector Type", Cell(ctype)),
        ("Number of Pins", Cell(count)),
        ("Gender", Cell(box.gender)),
    ]
    for r, (label, cell) in enumerate(rows):
        if label:
            g.put(r, 0, label, BOLD)
        g.set(r, 1, cell)
    device_text = device if device else TO_FILL
    pn = f"{ctype} {count} {box.gender}"
    g.put(8, 0, "Connector Name/Part Number", BOLD)
    g.put(8, 1, pn, formula='[.B6]&" "&[.B7]&" "&[.B8]')
    g.put(10, 0, "Connector Description", BOLD)
    desc = f"{device_text} [{box.id}]: {'; '.join(interfaces)}; {pn}"
    g.put(10, 1, desc, formula='[.B1]&" ["&[.B2]&"]: "&[.B3]&"; "&[.B9]')
    g.put(12, 0, "Link to ICD", BOLD)
    g.set(12, 1, _link_cell(box.source_doc or "", box.source_link))
    g.put(13, 0, "ICD version", BOLD)
    if box.source_version:
        g.put(13, 1, box.source_version)
    g.put(14, 0, "CON sheet copied from", BOLD)
    for c, head in enumerate(PIN_HEAD):
        g.put(CON_FIRST_PIN_ROW - 1, c, head, HEAD)
    pins: dict[str, int] = {}
    values: dict[str, tuple[Value, str, str, str, str]] = {}
    for n, pin in enumerate(box.pins):
        r = CON_FIRST_PIN_ROW + n
        row = (
            cell_value(pin.id),
            pin.signal or "",
            direction_word(project, pin, box),
            pin.level or "",
            pin.function or "",
        )
        pins[pin.id], values[pin.id] = r, row
        g.put(r, 0, row[0], GREY)
        for c, v in enumerate(row[1:], start=1):
            g.put(r, c, v, BOX)
    sheet = Sheet(
        name,
        g.rows(),
        widths=(48, 60, 22, 22, 60),
        page=Page("A4", landscape=False, fit=True, footer=_footer(stamp)),
    )
    return ConSheet(name, sheet, pins, values, device_text, desc)


# ---- the harness sheet (sections 3.3 to 3.5) --------------------------------------------------


@dataclass
class _Row:
    """One row of a near block: the pin and, when it has one, the wire of the row."""

    connector: Connector
    pin: Pin
    box_pin: bool  # the pin is a pin of the box connector, so it has a device side
    wired: bool  # any wire of the harness ends on it
    wire: Wire | None = None
    # (far connector, far pin, the wire that ends on that pin) of each far pin the row reaches,
    # through splices, in the order of the far columns, then of the pins
    far: tuple[tuple[Connector, str, Wire], ...] = ()


@dataclass(frozen=True)
class _Far:
    connector: Connector
    box: Connector | None
    pin_col: int
    group_col: int | None  # the first column of its device side group, for a box connector


class _HarnessSheet:
    def __init__(
        self,
        project: Project,
        h: Harness,
        stamp: Stamp,
        name: str,
        cons: dict[str, ConSheet],
        settings: PlanSettings,
        code_ranges: dict[str, tuple[int, int, tuple[tuple[Value, str], ...]]],
        drawings: bool,
    ) -> None:
        self.project, self.h, self.stamp, self.name = project, h, stamp, name
        self.cons, self.settings, self.drawings = cons, settings, drawings
        self.g = _Grid()
        self.sides = plan_sides(h)
        self.splices = splice_ids(h)
        self.joined = joined_wires(h)
        self.boxes = {c.id: project.connectors.get(c.mates_with or "") for c in h.connectors}
        self.attached: dict[tuple[str, str], list[Wire]] = defaultdict(list)
        for w in sorted(h.wires, key=lambda x: natural_key(x.id)):
            self.attached[w.from_connector, w.from_pin].append(w)
            self.attached[w.to_connector, w.to_pin].append(w)
        self.shields: dict[str, list[str]] = defaultdict(list)
        for s in sorted(h.shields, key=lambda x: natural_key(x.id)):
            for wid in s.wire_ids:
                self.shields[wid].append(s.id)
        self.codes: dict[str, ColourCode] = {}
        if settings.colour_rule == "pin_code":
            for code in settings.codes:
                for part in code.parts:
                    self.codes.setdefault(part, code)
        self.code_ranges = code_ranges
        far_count = len(self.sides.far)
        group = COL_T + far_count + 1
        self.far: list[_Far] = []
        for n, c in enumerate(self.sides.far):
            box = self.box(c)
            self.far.append(_Far(c, box, COL_T + n, group if box else None))
            group += GROUP_WIDTH if box else 0
        self.last_col = COL_T + max(far_count, 1) - 1
        self.cable_types: list[str] = []
        self.type_rows: dict[str, int] = {}  # part ID -> its row in *used Cable Types*
        self.per_cable: dict[str, int] = {}  # part ID -> No. of wires in cable
        self.block_rows: list[tuple[int, int]] = []  # (first, last) pin rows of each near block
        self.wire_rows: list[tuple[int, int]] = []  # the same, and the rows of the further wires
        self.harness_rows: list[int] = []

    def box(self, c: Connector) -> Connector | None:
        """The box connector a cable connector plugs into, when it has a `CON_…` sheet here."""
        box = self.boxes.get(c.id)
        return box if box is not None and con_name(box) in self.cons else None

    # -- the rows of the near end

    def near_rows(self, c: Connector) -> list[_Row]:
        """The pins of the box connector it plugs into, in their order, then any pin of its own with
        a wire that the box connector lacks; without a box connector, its own pins."""
        box = self.box(c)
        if box is None:
            return [_Row(c, p, False, bool(self.attached.get((c.id, p.id)))) for p in c.pins]
        rows = [_Row(c, p, True, bool(self.attached.get((c.id, p.id)))) for p in box.pins]
        on_box = {r.pin.id for r in rows}
        return rows + [
            _Row(c, p, False, True)
            for p in c.pins
            if p.id not in on_box and self.attached.get((c.id, p.id))
        ]

    def assign(self, blocks: list[tuple[Connector, list[_Row]]]) -> list[Wire]:
        """The wire of each near row: the first wire on its pin, by ID, that reaches a far pin,
        directly or through splices; the far pins it reaches, each with the wire that ends on it.
        The further wires: every wire on no row (beyond a splice, between two connectors of one
        end, the second wire of a pin; section 9)."""
        far = {c.id: (n, c) for n, c in enumerate(self.sides.far)}
        on_row: set[str] = set()
        for c, rows in blocks:
            for row in rows:
                for w in self.attached.get((c.id, row.pin.id), []):
                    if w.id in on_row:
                        continue
                    group = self.joined[w.id]
                    reached = sorted(
                        (p for p in reached_pins(group, self.splices) if p[0] in far),
                        key=lambda p: (far[p[0]][0], natural_key(p[1])),
                    )
                    if reached:
                        row.wire = w
                        row.far = tuple(
                            (far[cid][1], pin, next(x for x in group if (cid, pin) in _ends(x)))
                            for cid, pin in reached
                        )
                        on_row.add(w.id)
                        break
        return [
            w for w in sorted(self.h.wires, key=lambda x: natural_key(x.id)) if w.id not in on_row
        ]

    # -- colours

    def colour(self, c: Connector, pin: str, pin_ref: str, w: Wire) -> Cell:
        code = self.codes.get(c.part_id)
        if code is None:
            return _filled(w.colour, BOX)
        first, last, rows = self.code_ranges[code.name]
        if pin not in dict(code.pins):
            return Cell(TO_FILL, style=FILL)
        value = lookup(rows, cell_value(pin)) or ""
        table = f"[${NOTES}.$B${first + 1}:.$C${last + 1}]"
        return Cell(
            value,
            formula=f'IF({pin_ref}="";"";VLOOKUP({pin_ref};{table};2;0))',
            style=BOX,
        )

    # -- the sheet

    def build(self) -> Sheet:
        g, h, project = self.g, self.h, self.project
        doc = project.meta.document
        system = (doc.system if doc else "") or project.meta.name
        g.put(5, COL_H, system, BOLD)
        g.put(5, COL_N, h.id, BOLD)
        g.put(5, COL_Q, f"VERSION: v{h.version} ({STATUS_WORDS[h.status]})", BOLD)
        if self.signal_ground_open():
            g.put(5, COL_T, NO_SGND, RED_BOLD)
        row = self.part_tables(9)
        blocks = [(c, self.near_rows(c)) for c in self.sides.near]
        further = self.assign(blocks)
        self.title(7)
        for c, rows in blocks:
            row = self.block(row, c, rows, first=(c is blocks[0][0]))
        if further:
            row = self.further(row, further)
        sums = row
        last = self.sums(sums)
        for far in self.far:
            last = max(last, self.reference(sums, far))
        if self.drawings:
            last += 2
            g.put(last, COL_H, f"Block diagram: harnesses/{h.id}/drawing_A3.pdf")
        conditions = []
        for first, end in self.block_rows:
            gnd = (
                f'OR(AND({_here(first, COL_J)}="GND";{_here(first, COL_R)}="PWR");'
                f'AND({_here(first, COL_R)}="GND";{_here(first, COL_J)}="PWR"))'
            )
            for col in (COL_J, COL_R):
                conditions.append(
                    Condition(f"{_addr(first, col)}:{_addr(end, col)}", gnd, RED_BOLD)
                )
        widths = [6, 16, 36, 16, 16, 40, 4, 16, 36, 16, 22, 16, 22, 16, 16, 16, 22, 16, 36]
        widths += [22] * max(len(self.far), 1) + [4]
        for far in self.far:
            if far.group_col is not None:
                widths += [16, 36, 16, 16, 40, 16, 4]
        return Sheet(
            self.name,
            g.rows(),
            widths=tuple(widths),
            page=Page("A4", landscape=True, fit=True, footer=_footer(self.stamp)),
            print_range=f"H6:{_addr(last, self.last_col)}",
            conditions=tuple(conditions),
        )

    def signal_ground_open(self) -> bool:
        """True when a pin of role `signal_ground` of a box connector of this harness has no wire."""
        for c in self.h.connectors:
            box = self.boxes.get(c.id)
            for p in box.pins if box else []:
                if p.role == "signal_ground" and not self.attached.get((c.id, p.id)):
                    return True
        return False

    def title(self, row: int) -> None:
        """`H8`: Harness <system>-<number>: near devices <–> far devices, from `B1` of each sheet."""
        parts, shown = [], []
        for end in (self.sides.near, self.sides.far):
            refs, texts = [], []
            for c in end:
                box = self.box(c)
                if box is not None and self.cons[con_name(box)].device != TO_FILL:
                    refs.append(_there(con_name(box), 0, 1))
                    texts.append(self.cons[con_name(box)].device)
                else:
                    word = OPEN_END if is_open_end(c) else c.id
                    refs.append(_text(word))
                    texts.append(word)
            parts.append('&" + "&'.join(refs))
            shown.append(" + ".join(texts))
        head = f'"Harness "&{_here(5, COL_H)}&"-"&{_here(5, COL_N)}&": "'
        value = f"Harness {self.g.cells[5, COL_H].value}-{self.h.id}: {shown[0]}"
        formula = f"{head}&{parts[0]}" if parts[0] else head
        if parts[1]:
            formula += f'&" <–> "&{parts[1]}'
            value += f" <–> {shown[1]}"
        self.g.put(row, COL_H, value, TITLE, formula=formula)

    def part_tables(self, row: int) -> int:
        """*used Connectors*, *used Cable Types* and *used Backshells*; the next free row."""
        g, h, project = self.g, self.h, self.project
        by_part: dict[str, list[Connector]] = defaultdict(list)
        for c in h.connectors:
            by_part[c.part_id].append(c)
        g.put(row, COL_H, "used Connectors", BOLD)
        for col, head in (
            (COL_H, "No."),
            (COL_I, "Part No."),
            (COL_M, "Quantity"),
            (COL_N, "Remark"),
        ):
            g.put(row + 1, col, head, HEAD)
        row += 2
        for n, part_id in enumerate(sorted(by_part, key=natural_key), start=1):
            cs = sorted(by_part[part_id], key=lambda c: natural_key(c.id))
            part = project.parts.get(part_id)
            remark = ", ".join(c.id for c in cs)
            if part is not None and part.part_number:
                remark += f"; {part.part_number}"
            loose = all(is_open_end(c) for c in cs)
            g.put(row, COL_H, n, BOX)
            g.put(row, COL_I, f"{part_id} ({OPEN_END})" if loose else part_id, BOX)
            g.put(row, COL_M, len(cs), BOX)
            g.put(row, COL_N, remark, BOX)
            row += 1
        row += 1
        wires_by_part: dict[str, list[Wire]] = defaultdict(list)
        for w in h.wires:
            if w.part_id:
                wires_by_part[w.part_id].append(w)
        self.cable_types = sorted(wires_by_part, key=natural_key)
        g.put(row, COL_H, "used Cable Types", BOLD)
        heads = (
            (COL_H, "No."), (COL_I, "Part No."), (COL_K, "AWG"), (COL_L, "Conductor"), (COL_O, "Colours"),
            (COL_R, "No. of wires in cable"), (COL_S, "Length [mm]"),
        )  # fmt: skip
        for col, head in heads:
            g.put(row + 1, col, head, HEAD)
        row += 2
        for n, part_id in enumerate(self.cable_types, start=1):
            ws = wires_by_part[part_id]
            part = project.parts.get(part_id)
            gauges = sorted({w.gauge_awg for w in ws if w.gauge_awg is not None})
            colours = sorted({w.colour for w in ws if w.colour}, key=str.casefold)
            g.put(row, COL_H, n, BOX)
            g.put(row, COL_I, part_id, BOX)
            g.set(
                row,
                COL_K,
                Cell(gauges[0] if len(gauges) == 1 else ", ".join(map(str, gauges)), style=BOX),
            )
            g.put(row, COL_L, (part.specification if part else None) or "", BOX)
            g.put(row, COL_O, ", ".join(colours), BOX)
            self.per_cable[part_id] = part.conductors if part is not None else 1
            g.put(row, COL_R, self.per_cable[part_id], BOX)
            self.type_rows[part_id] = row
            row += 1
        row += 1
        g.put(row, COL_H, "used Backshells", BOLD)
        for col, head in (
            (COL_H, "No."),
            (COL_I, "Part No."),
            (COL_M, "Quantity"),
            (COL_N, "Remark"),
        ):
            g.put(row + 1, col, head, HEAD)
        row += 2
        shells = sorted(
            (a for a in h.accessories if a.kind == "backshell"), key=lambda a: natural_key(a.id)
        )
        if not shells:
            g.put(row, COL_I, NO_BACKSHELLS)
            row += 1
        for n, a in enumerate(shells, start=1):
            remark = "; ".join(x for x in (f"on {a.target}" if a.target else "", a.note) if x)
            g.put(row, COL_H, n, BOX)
            g.set(row, COL_I, _filled(a.part_id))
            g.put(row, COL_M, a.quantity, BOX)
            g.put(row, COL_N, remark, BOX)
            row += 1
        return row + 1

    def block(self, row: int, c: Connector, rows: list[_Row], first: bool) -> int:
        """One near connector: its heading rows, then one row per pin; the next free row."""
        g, project = self.g, self.project
        box = self.box(c)
        con = self.cons[con_name(box)] if box else None
        part = project.parts.get(c.part_id)
        g.put(row, COL_B, box.id if box else c.id, TITLE)
        if part is not None and part.link:
            g.put(row + 1, COL_H, f"Part link: {part.link}", link=part.link)
        if box is not None:
            g.set(row + 2, COL_B, _link_cell(box.source_doc or "", box.source_link))
        if box is not None and con is not None:
            g.put(row + 3, COL_F, "Device Side", BOLD)
            g.put(row + 4, COL_B, f"Data from {con.name}")
            g.put(row + 4, COL_F, con.description, formula=_there(con.name, 10, 1))
        g.put(row + 3, COL_H, "Harness Side", BOLD)
        ctype = (part.description if part else None) or c.part_id
        if is_open_end(c):
            ctype = f"{OPEN_END}, {TO_FILL}"
        if box is not None and con is not None:
            value = f"{ctype} [{self.h.id}:{con.device}:{box.id}]"
            dev = _there(con.name, 0, 1) if con.device != TO_FILL else _text(TO_FILL)
            formula = f'{_text(ctype + " [")}&{_here(5, COL_N)}&":"&{dev}&":"&{_there(con.name, 1, 1)}&"]"'
            g.put(row + 4, COL_H, value, BOLD, formula=formula)
        else:
            g.put(row + 4, COL_H, f"{ctype} [{self.h.id}:{c.id}]", BOLD)
        head = row + 5
        if box is not None:
            for n, text in enumerate(DEVICE_HEAD):
                g.put(head, COL_B + n, text, HEAD)
        for n, text in enumerate(HARNESS_HEAD):
            g.put(head, COL_H + n, text, HEAD)
        for far in self.far:
            box_f = far.box
            label = (
                f"{OPEN_END}, {TO_FILL}"
                if is_open_end(far.connector)
                else f"Pinout (of {self.cons[con_name(box_f)].device})"
                if box_f is not None
                else f"Pinout (of {far.connector.id})"
            )
            g.put(head, far.pin_col, label, HEAD)
            if first and box_f is not None and far.group_col is not None:
                con_f = self.cons[con_name(box_f)]
                g.put(head - 2, far.group_col, box_f.id, TITLE)
                g.put(head - 1, far.group_col, f"Data from {con_f.name}")
                for n, text in enumerate(PIN_HEAD):
                    g.put(head, far.group_col + n, text, HEAD)
        start = head + 1
        noted = any(c.value == NOT_CONNECTED_TEXT for c in g.cells.values())
        for n, r in enumerate(rows):
            noted = self.pin_row(start + n, r, con, noted)
        end = start + max(len(rows), 1) - 1
        if rows:
            self.block_rows.append((start, end))
            self.wire_rows.append((start, end))
            self.harness_rows += list(range(start, start + len(rows)))
        return end + 2

    def pin_row(self, row: int, r: _Row, con: ConSheet | None, noted: bool) -> bool:
        g, project = self.g, self.project
        pin_id, w = r.pin.id, r.wire
        if r.box_pin and con is not None:
            pr = con.pins[pin_id]
            vals = con.values[pin_id]
            g.put(row, COL_B, vals[0], GREY, formula=_there(con.name, pr, 0))
            for n in range(1, 5):
                g.set(row, COL_B + n, _copy(vals[n], _there(con.name, pr, n), BOX))
            if not r.wired:
                for col in range(COL_H, self.last_col + 1):
                    g.put(row, col, "", YELLOW)
                if not noted:
                    g.put(row, COL_I, NOT_CONNECTED_TEXT, YELLOW)
                return True
            g.put(row, COL_H, vals[0], BOX, formula=_here(row, COL_B))
            g.set(row, COL_I, _copy(vals[1], _here(row, COL_C), BOX))
            g.set(row, COL_J, _mirror(vals[2], _here(row, COL_D), BOX))
            g.set(row, COL_O, _copy(vals[3], _here(row, COL_E), BOX))
        else:
            g.put(row, COL_H, cell_value(pin_id), BOX)
            signal = r.pin.signal or (w.signal if w else None) or ""
            if signal:
                g.put(row, COL_I, signal, BOX)
            word = mirrored(direction_word(project, r.pin, r.connector))
            if word:
                g.put(row, COL_J, word, BOX)
        if w is None or not r.far:
            return noted
        g.set(row, COL_K, self.colour(r.connector, pin_id, _here(row, COL_H), w))
        kind = self.wire_cells(row, w)
        if len(r.far) > 1:
            self.far_cells(row, r.far)
            return noted
        far_c, far_pin, far_w = r.far[0]
        far = self.far_of(far_c)
        g.put(row, far.pin_col, cell_value(far_pin), BOX)
        if far_w.id == w.id:
            g.put(row, COL_P, kind, BOX, formula=_here(row, COL_L))
        else:  # through a splice: the far wire's own type, as a value (section 9)
            g.put(row, COL_P, self.wire_kind(far_w), BOX)
        g.set(row, COL_Q, self.colour(far_c, far_pin, _here(row, far.pin_col), far_w))
        con_f = self.cons[con_name(far.box)] if far.box is not None else None
        if con_f is not None and far_pin in con_f.pins and far.group_col is not None:
            pr, vals = con_f.pins[far_pin], con_f.values[far_pin]
            g.set(row, COL_R, _mirror(vals[2], _there(con_f.name, pr, 2), BOX))
            g.set(row, COL_S, _copy(vals[1], _there(con_f.name, pr, 1), BOX))
        else:
            word, signal = self.far_words(far_c, far_pin, far_w)
            if word:
                g.put(row, COL_R, word, BOX)
            if signal:
                g.put(row, COL_S, signal, BOX)
        self.group_cells(row, far, [far_pin])
        return noted

    def far_of(self, c: Connector) -> _Far:
        return next(f for f in self.far if f.connector.id == c.id)

    def far_words(self, c: Connector, pin_id: str, w: Wire) -> tuple[str, str]:
        """The mirrored Direction word and the Function of a far pin, as values: from its
        `CON_…` sheet when it has a row there, else from the cable connector's pin and the wire."""
        box = self.box(c)
        con = self.cons[con_name(box)] if box is not None else None
        if con is not None and pin_id in con.pins:
            vals = con.values[pin_id]
            return mirrored(vals[2]), vals[1]
        pin = next((p for p in c.pins if p.id == pin_id), None)
        word = mirrored(direction_word(self.project, pin, c)) if pin else ""
        return word, (pin.signal if pin else None) or w.signal or ""

    def group_cells(self, row: int, far: _Far, pins: list[str]) -> None:
        """The far device side of a row: one pin as the template has it (Pinout as a value, the
        rest copied from the far `CON_…` row); two or more pins of one far connector as values,
        each cell the pins' values joined by ` + `."""
        if far.group_col is None:
            return
        g, col = self.g, far.group_col
        con = self.cons[con_name(far.box)] if far.box is not None else None
        if len(pins) == 1:
            pin = pins[0]
            if con is not None and pin in con.pins:
                pr, vals = con.pins[pin], con.values[pin]
                g.put(row, col, vals[0], BOX)
                for n in range(1, 5):
                    g.set(row, col + n, _copy(vals[n], _there(con.name, pr, n), BOX))
            else:
                g.put(row, col, cell_value(pin), BOX)
            return
        for n in range(5):
            parts = [
                str(con.values[p][n]) if con is not None and p in con.pins else p if n == 0 else ""
                for p in pins
            ]
            _joined(g, row, col + n, parts)

    def far_cells(self, row: int, far: tuple[tuple[Connector, str, Wire], ...]) -> None:
        """A row that reaches two or more far pins (section 9): each far pin column lists its pins
        joined by ` + `; Cable / Type, Color, Direction and Function (`P` to `S`) list the values
        of each far wire in column order, joined by ` + `, as values."""
        g = self.g
        for f in self.far:
            pins = [pin for c, pin, _ in far if c.id == f.connector.id]
            if not pins:
                continue
            g.put(row, f.pin_col, cell_value(pins[0]) if len(pins) == 1 else " + ".join(pins), BOX)
            self.group_cells(row, f, pins)
        kinds, colours, words, signals = [], [], [], []
        for c, pin, w in far:
            kinds.append(str(self.wire_kind(w)))
            colours.append(str(self.colour(c, pin, "", w).value))
            word, signal = self.far_words(c, pin, w)
            words.append(word)
            signals.append(signal)
        for col, parts in ((COL_P, kinds), (COL_Q, colours), (COL_R, words), (COL_S, signals)):
            _joined(g, row, col, parts)

    def wire_kind(self, w: Wire) -> Value:
        """The Cable / Type of a wire: the No. of its part in *used Cable Types*, else to fill in."""
        return self.cable_types.index(w.part_id) + 1 if w.part_id else TO_FILL

    def wire_cells(self, row: int, w: Wire) -> Value:
        """Cable / Type (the No. of its part in *used Cable Types*), Shielding and Length of a
        wire's row; the Cable / Type as shown."""
        g = self.g
        kind = self.wire_kind(w)
        if w.part_id:
            g.put(row, COL_L, kind, TYPED)
        else:
            g.put(row, COL_L, TO_FILL, FILL)
        if self.shields.get(w.id):
            g.put(row, COL_M, ", ".join(self.shields[w.id]), TYPED)
        length = wire_length(self.h, w)
        if length is None:
            g.put(row, COL_N, TO_FILL, FILL)
        else:
            g.put(row, COL_N, round(length * 1000, 1) + 0.0, TYPED)
        return kind

    def further(self, row: int, wires: list[Wire]) -> int:
        """*Further wires*: each wire that does not end on a near pin (section 9)."""
        g = self.g
        g.put(row, COL_H, "Further wires", BOLD)
        heads = ((COL_H, "Wire"), (COL_I, "From"), (COL_J, "To"), (COL_K, "Color"), (COL_L, "Cable / Type"),
                 (COL_M, "Shielding / (Grouping)"), (COL_N, "Length [mm]"))  # fmt: skip
        for col, text in heads:
            g.put(row + 1, col, text, HEAD)
        start = row + 2
        for n, w in enumerate(wires):
            r = start + n
            g.put(r, COL_H, w.id, BOX)
            g.put(r, COL_I, f"{w.from_connector}.{w.from_pin}", BOX)
            g.put(r, COL_J, f"{w.to_connector}.{w.to_pin}", BOX)
            g.set(r, COL_K, _filled(w.colour))
            self.wire_cells(r, w)
        self.wire_rows.append((start, start + len(wires) - 1))
        return start + len(wires) + 1

    def sums(self, row: int) -> int:
        """*Sum of length of cable type [mm]*: one row per type; the last row used."""
        g = self.g
        g.put(row, COL_H, "Sum of length of cable type [mm]", BOLD)
        for col, text in ((COL_H, "No."), (COL_I, "Part No."), (COL_N, "Sum of length [mm]")):
            g.put(row + 1, col, text, HEAD)
        r = row + 1
        for no, part_id in enumerate(self.cable_types, start=1):
            r += 1
            lengths: list[float] = []
            missing = 0
            terms = []
            for first, last in self.wire_rows:
                terms.append(
                    f"SUMIF({_span(COL_L, first, last)};{_here(r, COL_H)};{_span(COL_N, first, last)})"
                )
                for x in range(first, last + 1):
                    t, length = g.get(x, COL_L), g.get(x, COL_N)
                    if t is not None and t.value == no and length is not None:
                        if isinstance(length.value, str):
                            missing += 1
                        else:
                            lengths.append(float(length.value))
            type_row, per = self.type_rows[part_id], self.per_cable[part_id]
            total = round(math.fsum(lengths) / per, 9) + 0.0
            g.put(r, COL_H, no, BOX)
            g.put(r, COL_I, part_id, BOX)
            formula = f"({'+'.join(terms)})/{_here(type_row, COL_R)}"
            g.put(r, COL_N, total, BOX, formula=formula)
            if missing:
                g.put(r, COL_O, f"{missing} wire{'s' if missing != 1 else ''} without a length")
            g.put(type_row, COL_S, total, BOX, formula=_here(r, COL_N))
        return r

    def reference(self, row: int, far: _Far) -> int:
        """The reference pinout of a far box connector under its device side group; the last row."""
        if far.box is None or far.group_col is None:
            return row
        g, col, box = self.g, far.group_col, far.box
        con = self.cons[con_name(box)]
        g.put(row, col, box.id, TITLE)
        g.set(row + 1, col, _link_cell(box.source_doc or "", box.source_link))
        g.put(row + 2, col, f"Data from {con.name}")
        for n, text in enumerate([*PIN_HEAD, "Used in Row"]):
            g.put(row + 3, col + n, text, HEAD)
        first, last = (
            (self.harness_rows[0], self.harness_rows[-1]) if self.harness_rows else (0, -1)
        )
        r = row + 3
        for pin in box.pins:
            r += 1
            pr, vals = con.pins[pin.id], con.values[pin.id]
            g.put(r, col, vals[0], GREY, formula=_there(con.name, pr, 0))
            for n in range(1, 5):
                g.set(r, col + n, _copy(vals[n], _there(con.name, pr, n), BOX))
            if last < first:
                continue
            used = next(
                (
                    x
                    for x in range(first, last + 1)
                    if (cell := g.get(x, col)) is not None
                    and cell.value != ""
                    and _same(cell.value, vals[0])
                ),
                None,
            )
            match = f"MATCH({_here(r, col)};{_span(col, first, last)};0)"
            g.put(
                r,
                col + 5,
                "" if used is None else used + 1,
                BOX,
                formula=f'IF(ISNA({match});"";{match}+{first})',
            )
        return r


# ---- Cover, Change_Register, Notes, About -----------------------------------------------------


def _cover(project: Project, h: Harness, stamp: Stamp) -> Sheet:
    doc = project.meta.document
    plan = doc.plans.get(h.id) if doc else None
    title = (
        (plan.title if plan else "")
        or (doc.title if doc else "")
        or f"{project.meta.name} Harness Plan"
    )
    g = _Grid()
    for r, (label, value) in enumerate(
        (
            ("Doc.-No.", plan.number if plan else ""),
            ("Version", (plan.version if plan else "") or h.version),
            ("Release", plan.release if plan else ""),
        ),
        start=1,
    ):
        g.put(r, 4, label, BOLD)
        g.set(r, 5, _filled(value))
    g.put(16, 0, project.meta.name, BIG, cols=6)
    g.put(18, 0, title, BIG, cols=6)
    g.set(
        20,
        0,
        Cell(doc.company, style=BIG, cols=6)
        if doc and doc.company
        else Cell(TO_FILL, style=FILL, cols=6),
    )
    g.put(22, 0, stamp.line, Style(align="center"), cols=6)
    g.put(23, 0, OVERWRITE_TEXT, Style(align="center", wrap=True), cols=6)
    g.put(24, 0, stamp.notice, Style(align="center", wrap=True), cols=6)
    g.put(35, 2, "Contact Information", BOLD)
    lines = doc.contact if doc else []
    for n, line in enumerate(lines):
        g.put(36 + n, 2, line.label, BOLD)
        g.set(36 + n, 3, _contact(line.value))
    if not lines:
        g.put(36, 3, TO_FILL, FILL)
    last = max(39, 36 + len(lines) - 1)
    return Sheet(
        COVER,
        g.rows(),
        widths=(30, 30, 30, 50, 30, 40),
        page=Page("A4", fit=True, footer=_footer(stamp)),
        print_range=f"A2:F{last + 1}",
    )


def _contact(value: str) -> Cell:
    """A contact value; an e-mail address (`mailto:` or one `@`) becomes a `mailto:` link."""
    if not value:
        return Cell(TO_FILL, style=FILL)
    link = ""
    if not re.search(r"\s", value):
        if value.startswith("mailto:"):
            link = value
        elif value.count("@") == 1:
            link = f"mailto:{value}"
    return Cell(value, link=link)


def _register(project: Project, h: Harness, stamp: Stamp, sheet_name: str) -> Sheet:
    g = _Grid()
    g.put(1, COL_B, f"Change register of {h.id}", TITLE)
    heads = ("Version", "Sub-Version", "Date", "Name", "Sheets", "Description")
    for n, text in enumerate(heads):
        g.put(3, COL_B + n, text, REGISTER_HEAD)
    entries = sorted(
        (e for e in project.changelog.values() if e.harness_id == h.id),
        key=lambda e: natural_key(e.id),
    )
    for n, e in enumerate(entries):
        words = CHANGE_WORDS[e.kind]
        comment = one_line(e.comment)
        row = (
            e.version,
            e.id,
            e.when,
            one_line(e.by),
            sheet_name,
            f"{words}: {comment}" if comment else words,
        )
        for k, v in enumerate(row):
            g.put(4 + n, COL_B + k, v, BOX)
    if not entries:
        g.put(4, COL_B, "No entry in the change log of this harness yet.")
    last = 4 + max(len(entries), 1) - 1
    return Sheet(
        REGISTER,
        g.rows(),
        widths=(6, 22, 22, 22, 30, 22, 80),
        page=Page("A4", landscape=True, fit=True, footer=_footer(stamp)),
        print_range=f"B4:G{last + 1}",
    )


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
    "The change register lists the change log of this harness (system/changelog.csv of the "
    "outputs); it is not typed into this file.",
    "This file is written by Harness Design Studio. An export overwrites it, formulas and typed "
    "changes alike; work on a copy.",
)


def _notes(
    settings: PlanSettings, codes: list[ColourCode], stamp: Stamp
) -> tuple[Sheet, dict[str, tuple[int, int, tuple[tuple[Value, str], ...]]]]:
    """The colour codes this harness uses, the project's note lines and the legend; and the rows
    of each code table (first and last 0-based row and the cells), for the lookups."""
    g = _Grid()
    g.put(1, COL_B, "Notes", TITLE)
    ranges = {}
    row = 4
    for code in codes:
        head = EXAMPLE_HEADING if code.example else f"Colour code {code.name}"
        g.put(row, COL_B, head, BOLD)
        g.put(row + 1, COL_B, f"Code {code.name}, for the parts {', '.join(code.parts)}")
        g.put(row + 2, COL_B, "Pin", HEAD)
        g.put(row + 2, COL_C, "Color", HEAD)
        start = row + 3
        cells = tuple(
            (cell_value(pin), colour)
            for pin, colour in sorted(code.pins, key=lambda x: natural_key(x[0]))
        )
        for n, (pin, colour) in enumerate(cells):
            g.put(start + n, COL_B, pin, GREY)
            g.put(start + n, COL_C, colour, BOX)
        ranges[code.name] = (start, start + max(len(cells), 1) - 1, cells)
        row = start + len(cells) + 1
    for line in settings.notes:
        g.put(row, COL_B, line, WRAP)
        row += 1
    if settings.notes:
        row += 1
    for line in LEGEND:
        g.put(row, COL_B, line, WRAP)
        row += 1
    sheet = Sheet(
        NOTES, g.rows(), widths=(6, 120, 40), page=Page("A4", fit=True, footer=_footer(stamp))
    )
    return sheet, ranges


def _about(stamp: Stamp) -> Sheet:
    rows = (
        (Cell("Generated by"), Cell(stamp.line)),
        (Cell("Model hash"), Cell(stamp.model_hash)),
        (Cell("Notice"), Cell(stamp.notice)),
    )
    return Sheet(ABOUT, rows, widths=(30, 160), page=Page("A4", footer=_footer(stamp)))


# ---- the plan ---------------------------------------------------------------------------------

_FIXED_NAMES = frozenset(n.casefold() for n in (COVER, REGISTER, NOTES, ABOUT))


def harness_sheet_name(h: Harness) -> str:
    """The harness ID, unless it reads as a fixed sheet or a `CON_…` sheet (spreadsheet programs
    compare sheet names without regard to case): then `Harness_<ID>`."""
    clash = h.id.casefold() in _FIXED_NAMES or h.id.casefold().startswith(CON_PREFIX.casefold())
    return f"Harness_{h.id}" if clash else h.id


def plan_boxes(project: Project, h: Harness) -> list[Connector]:
    """The box connectors the harness plugs into, at either end, in connector ID order."""
    ids = {c.mates_with for c in h.connectors if c.mates_with and not is_open_end(c)}
    return sorted(
        (project.connectors[i] for i in ids if i in project.connectors),
        key=lambda c: natural_key(c.id),
    )


def used_codes(settings: PlanSettings, h: Harness) -> list[ColourCode]:
    """The colour codes an end of this harness uses (rule `pin_code`), in the order of the file."""
    if settings.colour_rule != "pin_code":
        return []
    parts = {c.part_id for c in h.connectors}
    first: dict[str, str] = {}
    for code in settings.codes:
        for p in code.parts:
            first.setdefault(p, code.name)
    names = {first[p] for p in parts if p in first}
    return [code for code in settings.codes if code.name in names]


PLAN_CONFIG = "config/harness_plan.json"


def colour_notes(project: Project) -> list[Issue]:
    """The notes of `check` on the colour codes of the harness plans (section 6): `plan_colour_example`
    once for each code that still carries the example mark, and `plan_colour_missing` once for each
    harness connector whose part is in a code (rule `pin_code`) and that has a wire on a pin the code
    does not list, so that the plan reads *to fill in* for its colour. Neither stops generation or an
    export: they are not issues of `configcheck.validate`."""
    settings = plan_settings(project)
    out = [
        Issue(
            "info",
            "plan_colour_example",
            f"The colour code '{code.name}' is the example from the users' template; check it "
            'against the supplier\'s pigtail code, then take the mark off ("example": false).',
            PLAN_CONFIG,
            f"harness_plan.colour_codes.{code.name}",
        )
        for code in settings.codes
        if code.example
    ]
    if settings.colour_rule != "pin_code":
        return out
    first: dict[str, ColourCode] = {}
    for code in settings.codes:
        for part in code.parts:
            first.setdefault(part, code)
    for h in sorted(project.harnesses.values(), key=lambda x: natural_key(x.id)):
        ends: dict[str, set[str]] = defaultdict(set)
        for w in h.wires:
            ends[w.from_connector].add(w.from_pin)
            ends[w.to_connector].add(w.to_pin)
        for c in sorted(h.connectors, key=lambda x: natural_key(x.id)):
            used = first.get(c.part_id)
            if used is None:
                continue
            keys = dict(used.pins)
            missing = sorted((p for p in ends.get(c.id, ()) if p not in keys), key=natural_key)
            if missing:
                pins = ", ".join(missing[:8]) + (f" and {len(missing) - 8} more" if len(missing) > 8 else "")  # fmt: skip
                out.append(
                    Issue(
                        "warning",
                        "plan_colour_missing",
                        f"Harness {h.id}, connector {c.id} ({c.part_id}): the colour code "
                        f"'{used.name}' has no colour for pin{'s' if len(missing) > 1 else ''} "
                        f"{pins}; the harness plan reads '{TO_FILL}' there.",
                        PLAN_CONFIG,
                        f"{h.id}.{c.id}",
                    )
                )
    return out


def plan_workbook(
    project: Project, h: Harness, stamp: Stamp, *, drawings: bool = False
) -> Workbook:
    """The model of the plan of harness `h` (see the module text); `drawings` says whether the
    export has the drawings, which the harness sheet then names."""
    settings = plan_settings(project)
    cons = {con_name(b): con_sheet(project, b, stamp) for b in plan_boxes(project, h)}
    codes = used_codes(settings, h)
    notes, ranges = _notes(settings, codes, stamp)
    name = harness_sheet_name(h)
    harness = _HarnessSheet(project, h, stamp, name, cons, settings, ranges, drawings).build()
    sheets = (
        _cover(project, h, stamp),
        _register(project, h, stamp, name),
        harness,
        notes,
        *(cons[n].sheet for n in cons),
        _about(stamp),
    )
    return Workbook(f"{h.id} harness plan", sheets)


def plan_ods(project: Project, h: Harness, stamp: Stamp, *, drawings: bool = False) -> bytes:
    """The bytes of `harnesses/<ID>/<ID>_plan.ods`."""
    return ods.write_ods(plan_workbook(project, h, stamp, drawings=drawings))


def plan_path(h: Harness) -> str:
    return f"harnesses/{h.id}/{h.id}{FILE_SUFFIX}"


__all__ = [
    "FILE_SUFFIX",
    "ColourCode",
    "PlanSettings",
    "Sides",
    "cell_value",
    "colour_notes",
    "con_sheet",
    "direction_word",
    "harness_sheet_name",
    "joined_wires",
    "lookup",
    "mirrored",
    "plan_boxes",
    "plan_ods",
    "plan_path",
    "plan_settings",
    "plan_sides",
    "plan_workbook",
    "reached_pins",
    "used_codes",
]
