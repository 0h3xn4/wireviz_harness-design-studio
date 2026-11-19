# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The row layout of a connector (format 4, D-250, D-251; design of 4.0.0,
`docs/ait/DESIGN_4.0_ROW_LAYOUT.md` sections 3 and 6.1).

    rows = layout_of(project, connector)         # the rows section 3 gives it, or None
    rows.row_of("12")                            # 2: the row of a pin, None for a pin in no row
    layout = parse_text("1–11 / 12–21")          # the short text form, None for an empty text
    layout_text(layout)                          # "1–11 / 12–21"
    layout = from_lengths([11, 10])              # rows numbered one after the other: 1–11 / 12–21
    layout = from_lengths([11, 10], pins)        # the connector's pins in pin order, 11 then 10
    kept = follow_pins(c.row_layout, pins, {"3": "A3"})   # a connector's own rows after a pin edit

**Where a layout comes from** (section 3). A box connector (one with `unit_id`) has its own layout
(`Connector.row_layout`) when it has one, else the layout of its part, else none. A cable
connector has the layout of its part, else the layout of the box connector it plugs into
(`mates_with`, by the rule of a box connector: pins mate by ID), else none. A name of the layout
that is not a pin of the connector is left out (`left_out`); a row keeps its number when names of
it are left out, so the rows still say where a contact sits on the face; a pin that is in no row
is listed after the rows, in pin order, without a row (`outside`).

**The text form** (section 6.1): rows separated by `/`, the pins of a row by spaces or commas, a
run of whole-number pins written `1–11` (an en dash) or `1:11`, counting up or down (`11–1`), and
the mark `(rings)` at the end for `rings: true`. Neither `/`, `–` nor `:` can be part of a pin ID
(`core/ids.py`), so the form is never ambiguous; `-` and `..` can, so they are part of a name and
never a range mark (`1-11` is the pin named `1-11`). The writer uses `–` and a run wherever three
or more whole-number pins follow each other; `parse_text(layout_text(x)) == x` for every layout.

Nothing here changes a project: the functions are pure, and every message is a plain sentence
(`ValueError`, for the editor's line under a field and for the command line).
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from .ids import check_pin_id
from .model import Connector, Pin, Project, RowLayout
from .model.base import MAX_PIN_COUNT
from .model.physical import MAX_ROWS

__all__ = [
    "RANGE_MARKS",
    "RINGS_MARK",
    "PinRows",
    "Source",
    "follow_pins",
    "from_lengths",
    "layout_of",
    "layout_text",
    "parse_lengths",
    "parse_text",
]

Source = Literal["own", "part", "mated"]
EN_DASH = "–"
RANGE_MARKS = (EN_DASH, ":")  # `1–11` or `1:11`; never `-` or `..`, which a pin ID may hold
RINGS_MARK = "(rings)"
_WHOLE = re.compile(r"0|[1-9][0-9]*")  # a whole-number pin as the writer writes it
_RANGE = re.compile(rf"\s*[{EN_DASH}:]\s*")
_SEPARATOR = re.compile(r"[\s,]+")


@dataclass(frozen=True)
class PinRows:
    """The layout of one connector as section 3 resolves it. `rows` are the rows of the layout in
    their order with only the names that are pins of the connector (a row may be empty when none
    of its names is); `source` says whose layout it is (`own`: the connector's own; `part`: its
    part's; `mated`: the box connector it plugs into) and `source_id` names that connector or
    part; `left_out` are the names of the layout that are not pins of the connector (`check`
    warns about them), `outside` the pins of the connector in no row, in pin order."""

    connector_id: str
    rows: tuple[tuple[str, ...], ...]
    rings: bool
    source: Source
    source_id: str
    left_out: tuple[str, ...] = ()
    outside: tuple[str, ...] = ()

    def row_of(self, pin_id: str) -> int | None:
        """The row of a pin, counted from 1 at the top of the face (or the outer ring); None for a
        pin in no row."""
        for number, row in enumerate(self.rows, start=1):
            if pin_id in row:
                return number
        return None

    def order(self) -> tuple[str, ...]:
        """The pins row by row in the order of the layout, then the pins in no row."""
        return (*(p for row in self.rows for p in row), *self.outside)


def _resolved(connector: Connector, layout: RowLayout, source: Source, source_id: str) -> PinRows:
    pins = [p.id for p in connector.pins]
    have = set(pins)
    rows = tuple(tuple(n for n in row if n in have) for row in layout.rows)
    in_rows = {n for row in rows for n in row}
    return PinRows(
        connector.id,
        rows,
        layout.rings,
        source,
        source_id,
        tuple(n for n in layout.names() if n not in have),
        tuple(p for p in pins if p not in in_rows),
    )


def _box_layout(project: Project, box: Connector) -> tuple[RowLayout, Source, str] | None:
    if box.row_layout is not None:
        return box.row_layout, "own", box.id
    part = project.parts.get(box.part_id)
    if part is not None and part.row_layout is not None:
        return part.row_layout, "part", part.id
    return None


def layout_of(project: Project, connector: Connector) -> PinRows | None:
    """The row layout of `connector` (a box connector of the project or a connector of a harness)
    by the rules of section 3, or None when it has none."""
    if connector.unit_id is not None:
        found = _box_layout(project, connector)
        return None if found is None else _resolved(connector, *found)
    part = project.parts.get(connector.part_id)
    if part is not None and part.row_layout is not None:
        return _resolved(connector, part.row_layout, "part", part.id)
    box = project.connectors.get(connector.mates_with or "")
    if box is not None and box.unit_id is not None:
        found = _box_layout(project, box)
        if found is not None:
            return _resolved(connector, found[0], "mated", box.id)
    return None


# ---- keeping a connector's own rows in step with its pins ------------------------------------


def follow_pins(
    layout: RowLayout | None, pins: Iterable[Pin], renamed: Mapping[str, str] | None = None
) -> RowLayout | None:
    """A box connector's own layout after its pins changed (design of 4.0.0 section 13, *The
    edits*): a renamed pin (`renamed`: old ID -> new ID) keeps its place under its new name, a pin
    that is gone leaves its row, a row left empty goes, and a layout left with no row is None (no
    key). The layout is returned as it is when nothing of it changes."""
    if layout is None:
        return None
    have = {p.id for p in pins}
    names = renamed or {}
    rows = [[names.get(n, n) for n in row] for row in layout.rows]
    rows = [[n for n in row if n in have] for row in rows]
    rows = [row for row in rows if row]
    if rows == layout.rows:
        return layout
    return RowLayout(rows=rows, rings=layout.rings) if rows else None


# ---- the text form (section 6.1) -------------------------------------------------------------


def _whole(name: str) -> int | None:
    return int(name) if _WHOLE.fullmatch(name) else None


def _run(text: str, row: int) -> list[str]:
    first, last = _RANGE.split(text)
    a, b = _whole(first), _whole(last)
    if a is None or b is None:
        raise ValueError(
            f"row {row}: '{text}' is not a run of pins; a run is two whole numbers without a "
            f"leading zero, such as 1{EN_DASH}11 or 1:11"
        )
    if abs(b - a) + 1 > MAX_PIN_COUNT:
        raise ValueError(f"row {row}: the run '{text}' has more than {MAX_PIN_COUNT} pins")
    step = 1 if b >= a else -1
    return [str(n) for n in range(a, b + step, step)]


def _row(text: str, row: int) -> list[str]:
    joined = _RANGE.sub(lambda m: m.group(0).strip(), text.strip())
    out: list[str] = []
    for token in (t for t in _SEPARATOR.split(joined) if t):
        if any(mark in token for mark in RANGE_MARKS):
            if sum(token.count(mark) for mark in RANGE_MARKS) != 1:
                raise ValueError(f"row {row}: '{token}' has more than one range mark")
            out += _run(token, row)
            continue
        try:
            out.append(check_pin_id(token))
        except ValueError as exc:
            raise ValueError(f"row {row}: '{token}' is not a pin name: {exc}") from None
    if not out:
        raise ValueError(f"row {row} is empty; leave it out")
    return out


def _layout(rows: list[list[str]], rings: bool) -> RowLayout:
    try:
        return RowLayout(rows=rows, rings=rings)
    except ValidationError as exc:
        raise ValueError(_first_message(exc)) from None


def _first_message(exc: ValidationError) -> str:
    message = str(exc.errors()[0].get("msg", ""))
    return message.removeprefix("Value error, ")


def parse_text(text: str) -> RowLayout | None:
    """The layout a line of the text form gives (section 6.1); None for an empty line (no
    layout). Raises `ValueError` with a plain sentence for a line that is not a layout."""
    body = text.strip()
    rings = False
    if body.endswith(RINGS_MARK):
        rings = True
        body = body.removesuffix(RINGS_MARK).strip()
    if RINGS_MARK in body:
        raise ValueError(f"the mark {RINGS_MARK} goes at the end of the rows")
    if not body:
        if rings:
            raise ValueError(f"the mark {RINGS_MARK} needs rows before it")
        return None
    parts = body.split("/")
    if len(parts) > MAX_ROWS:
        raise ValueError(f"a row layout has at most {MAX_ROWS} rows; this one has {len(parts)}")
    return _layout([_row(part, k) for k, part in enumerate(parts, start=1)], rings)


def _row_text(row: Sequence[str]) -> str:
    out: list[str] = []
    k = 0
    while k < len(row):
        start = _whole(row[k])
        end = k
        if start is not None:
            for step in (1, -1):
                j = k
                while j + 1 < len(row) and _whole(row[j + 1]) == (_whole(row[j]) or 0) + step:
                    j += 1
                if j - k >= 2:
                    end = j
                    break
        if end - k >= 2:
            out.append(f"{row[k]}{EN_DASH}{row[end]}")
            k = end + 1
        else:
            out.append(row[k])
            k += 1
    return " ".join(out)


def layout_text(layout: RowLayout | None) -> str:
    """The layout in the text form (section 6.1): `1–11 / 12–21`, `1–8 / 9–12 (rings)`; an empty
    text for no layout."""
    if layout is None:
        return ""
    text = " / ".join(_row_text(row) for row in layout.rows)
    return f"{text} {RINGS_MARK}" if layout.rings else text


# ---- from row lengths (section 6.1) ----------------------------------------------------------


def parse_lengths(text: str) -> list[int]:
    """The row lengths of a line such as `11, 10` (commas or spaces between them). Raises
    `ValueError` for anything that is not a list of whole numbers from 1."""
    tokens = [t for t in _SEPARATOR.split(text.strip()) if t]
    if not tokens:
        raise ValueError("give the length of each row, such as 11, 10")
    out = []
    for token in tokens:
        number = _whole(token)
        if number is None or number < 1:
            raise ValueError(f"'{token}' is not a row length (a whole number from 1)")
        out.append(number)
    return out


def from_lengths(lengths: Sequence[int], pins: Sequence[Pin] | None = None) -> RowLayout:
    """The layout of rows numbered one after the other: on a part (`pins` None) the names 1 to N,
    `11, 10` giving `1–11 / 12–21`; on a connector its pins in pin order, eleven then ten. Raises
    `ValueError` when the lengths ask for more pins than the connector has."""
    if not lengths or any(n < 1 for n in lengths):
        raise ValueError("every row has at least one pin")
    if len(lengths) > MAX_ROWS:
        raise ValueError(f"a row layout has at most {MAX_ROWS} rows; {len(lengths)} were given")
    total = sum(lengths)
    if total > MAX_PIN_COUNT:
        raise ValueError(f"a row layout names at most {MAX_PIN_COUNT} pins; {total} were given")
    names = [str(n) for n in range(1, total + 1)] if pins is None else [p.id for p in pins]
    if total > len(names):
        raise ValueError(f"the rows hold {total} pins; the connector has {len(names)}")
    rows, at = [], 0
    for n in lengths:
        rows.append(names[at : at + n])
        at += n
    return _layout(rows, False)
