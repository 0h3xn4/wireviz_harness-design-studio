# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The rows of the Production sheet of a harness (design of 4.1.0, part A, sections 3.2 to 3.5).

One block per cable connector, both ends of every wire: where each wire goes, with its part,
colour, gauge, length, where the length comes from, the label printed at this end and the shield
groups with their end here and at the far end. `production_blocks` is pure and holds plain values
only (no file, no style, no unit conversion): the build workbook writes the length in metres as it
is here, the harness plan in millimetres. The cable connectors come in natural ID order
(`tables.natural_key`), the splices last in the same order; the writer puts its splice heading
above the first splice block (`ProductionBlock.splice`).

- A run of consecutive spare pins (no wire, no signal, no interface: the *Connectors* sheet's own
  test for `(spare)`) is one row `3 to 9`; `to` and not a dash, because a pin name may hold `-`.
- A pin with a signal or an interface and no wire is a row `(no wire)` of its own.
- A pin with two or more wires has one row per wire, in wire ID order.
- A value the design does not hold reads *to fill in* (`tables.TO_FILL`); nothing is invented.

The independent verifier words every row again with its own copy of these rules
(`verify_production.production_rows`), which imports neither this module nor `tables.py`."""

from dataclasses import dataclass

from harness_design_studio.core.generate.lengths import (
    EndDepths,
    end_depths,
    length_origin,
    wire_length,
)
from harness_design_studio.core.model import Connector, Harness, Project, ShieldGroup, Wire
from harness_design_studio.core.model.physical import SPLICE_ROLE
from harness_design_studio.core.shield_ends import end_at
from harness_design_studio.core.wirecolours import resolve

from .tables import (
    OPEN_END,
    TO_FILL,
    connector_label_text,
    is_open_end,
    natural_key,
    part_text,
    wire_label_texts,
)

JOIN = "   ·   "  # between the parts of a block heading, as on the *Connectors* sheet
HEADER = (
    "Pin", "Signal", "Wire", "Goes to", "Wire part", "Colour", "AWG", "Length (m), rear to rear",
    "Length from", "Label at this end", "Shield group: here / far end",
)  # fmt: skip
PLAN_HEADER = (*HEADER[:7], "Length [mm] rear to rear", *HEADER[8:])
NO_WIRE = "(no wire)"
SPARE = "(spare)"
RUN = " to "  # between the first and the last pin of a run of spare pins
NOT_PLUGGED = "not plugged into a unit"
SPLICE_WORD = "splice"
NOT_DEFINED = "here not defined (the group ends on more than two connectors)"
END_WORDS = {"backshell_360": "backshell 360", "pigtail": "pigtail", "floating": "floating"}

Value = str | int | float


@dataclass(frozen=True)
class ProductionRow:
    """One row of a block, the columns of section 3.3 as plain values. `length` is in metres (a
    number rounded to 9 decimals) or *to fill in*; the cells of a row without a wire are empty."""

    pin: str
    signal: str
    wire: str
    goes_to: str
    part: str
    colour: str
    awg: int | str
    length: float | str
    length_from: str
    label: str
    shields: str

    def values(self) -> tuple[Value, ...]:
        return (
            self.pin, self.signal, self.wire, self.goes_to, self.part, self.colour, self.awg,
            self.length, self.length_from, self.label, self.shields,
        )  # fmt: skip


@dataclass(frozen=True)
class ProductionBlock:
    """One connector: its heading (the parts joined by `JOIN`) and its rows."""

    connector_id: str
    splice: bool
    heading: str
    rows: tuple[ProductionRow, ...]


def colour_text(name: str | None) -> str:
    """The colour in words, with its IEC 60757 code when the table knows it: "red (RD)"."""
    if not name:
        return ""
    code, _screen = resolve(name)
    return f"{name} ({code})" if code and code != name.upper() else name


def _box_text(project: Project, c: Connector) -> str | None:
    """What a cable connector plugs into, as `DEVICE:NAME` (the box connector's `unit_id` and
    `name`); None when it plugs into no connector of the project."""
    box = project.connectors.get(c.mates_with or "")
    if box is None:
        return None
    return f"{box.unit_id}:{box.name}" if box.unit_id else box.name


def _heading(project: Project, h: Harness, c: Connector) -> str:
    if c.role == SPLICE_ROLE:
        nodes = len(c.pins)
        parts = [c.id, c.part_id, SPLICE_WORD, f"{nodes} node{'s' if nodes != 1 else ''}"]
    else:
        if is_open_end(c):
            parts = [c.id, part_text(c), f"{OPEN_END}, {TO_FILL}"]
        else:
            box = _box_text(project, c)
            parts = [
                c.id, c.part_id, c.gender if c.gender != "unspecified" else "gender not set",
                f"mates {c.mates_with} ({box})" if box is not None else NOT_PLUGGED,
            ]  # fmt: skip
        parts.append(f"label {connector_label_text(project, c, h)}")
    marks = [
        f"label at {a.position}" if a.position else f"label, position {TO_FILL}"
        for a in sorted(h.accessories, key=lambda x: natural_key(x.id))
        if a.kind == "label" and a.target == c.id
    ]
    if marks:
        parts.append("; ".join(marks))
    return JOIN.join(parts)


def _goes_to(project: Project, h: Harness, cid: str, pin: str) -> str:
    """The far end of a wire, then in brackets what that connector plugs into."""
    far = next((x for x in h.connectors if x.id == cid), None)
    if far is None:
        return f"{cid}.{pin}"
    if far.role == SPLICE_ROLE:
        what: str | None = SPLICE_WORD
    elif is_open_end(far):
        what = OPEN_END
    else:
        what = _box_text(project, far)
    return f"{cid}.{pin} ({what})" if what is not None else f"{cid}.{pin}"


def _shield_text(h: Harness, s: ShieldGroup, cid: str) -> str:
    kind = s.kind.replace("_", " ")
    if s.kind == "twisted_pair":  # a pair without a shield has no ends
        return f"{s.id} {kind}"
    end = end_at(h, s, cid)
    if end is None:
        return f"{s.id} {kind}: {NOT_DEFINED}"
    here, far = (s.end_a, s.end_b) if end == "a" else (s.end_b, s.end_a)
    return f"{s.id} {kind}: here {END_WORDS.get(here, here)}, far {END_WORDS.get(far, far)}"


def _wire_row(project: Project, h: Harness, c: Connector, pin: str, signal: str | None, w: Wire, end: str, depths: EndDepths) -> ProductionRow:  # fmt: skip
    far = (w.to_connector, w.to_pin) if end == "a" else (w.from_connector, w.from_pin)
    length = wire_length(h, w, depths)
    text_a, text_b = wire_label_texts(project, w, h)
    groups = sorted((s for s in h.shields if w.id in s.wire_ids), key=lambda s: natural_key(s.id))
    return ProductionRow(
        pin=pin,
        signal=signal or w.signal or "",
        wire=w.id,
        goes_to=_goes_to(project, h, *far),
        part=w.part_id or TO_FILL,
        colour=colour_text(w.colour) or TO_FILL,
        awg=w.gauge_awg if w.gauge_awg is not None else TO_FILL,
        length=round(length, 9) + 0.0 if length is not None else TO_FILL,
        length_from=length_origin(h, w, depths),
        label=text_a if end == "a" else text_b,
        shields="; ".join(_shield_text(h, s, c.id) for s in groups),
    )


def _plain_row(pin: str, signal: str, wire: str) -> ProductionRow:
    return ProductionRow(pin, signal, wire, "", "", "", "", "", "", "", "")


def _rows(project: Project, h: Harness, c: Connector, depths: EndDepths) -> list[ProductionRow]:
    ends: dict[str, list[tuple[Wire, str]]] = {}
    for w in h.wires:
        if w.from_connector == c.id:
            ends.setdefault(w.from_pin, []).append((w, "a"))
        if w.to_connector == c.id:
            ends.setdefault(w.to_pin, []).append((w, "b"))
    rows: list[ProductionRow] = []
    run: list[str] = []

    def close_run() -> None:
        if run:
            rows.append(
                _plain_row(run[0] if len(run) == 1 else f"{run[0]}{RUN}{run[-1]}", "", SPARE)
            )
            run.clear()

    for p in c.pins:
        here = sorted(ends.get(p.id, []), key=lambda x: (x[0].id, x[1]))
        if not here and not p.signal and not p.interface_id:
            run.append(p.id)
            continue
        close_run()
        if not here:
            rows.append(_plain_row(p.id, p.signal or "", NO_WIRE))
        for w, end in here:
            rows.append(_wire_row(project, h, c, p.id, p.signal, w, end, depths))
    close_run()
    return rows


def production_blocks(project: Project, h: Harness) -> list[ProductionBlock]:
    """The blocks of the Production sheet of `h`: the cable connectors in natural ID order, then
    the splices (section 3.2), each with its heading and its rows (sections 3.3 to 3.5)."""
    ordered = sorted(h.connectors, key=lambda x: natural_key(x.id))
    plain = [c for c in ordered if c.role != SPLICE_ROLE]
    splices = [c for c in ordered if c.role == SPLICE_ROLE]
    depths = end_depths(project, h)
    return [
        ProductionBlock(
            c.id,
            c.role == SPLICE_ROLE,
            _heading(project, h, c),
            tuple(_rows(project, h, c, depths)),
        )
        for c in [*plain, *splices]
    ]


__all__ = [
    "END_WORDS",
    "HEADER",
    "JOIN",
    "NOT_DEFINED",
    "NOT_PLUGGED",
    "NO_WIRE",
    "PLAN_HEADER",
    "RUN",
    "SPARE",
    "ProductionBlock",
    "ProductionRow",
    "colour_text",
    "production_blocks",
]
