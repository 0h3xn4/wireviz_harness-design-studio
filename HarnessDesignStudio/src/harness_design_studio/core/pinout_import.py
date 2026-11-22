# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Import a device's pinout from a spreadsheet (CSV or XLSX) as a plan: nothing changes until the
person confirms. One row of the sheet is one pin: the connector it belongs to, its name or number,
the signal on it, whether the device fixes it, a contact size, a termination, a function (free text;
a sheet with only a Function column and no Signal column reads it as the signal, as before) and the
contact part the cable side uses (a part of category contact; the heading `Cable contact`, or
`Contact` next to a Pin heading) and a direction (`Direction`: in, out or bidirectional; empty
leaves it unset, 1.9.0). An optional Port column (2.1.0, D-237) names the port of the pin; the
import writes it into the signal name (`RS422_2` and `TX+` give `RS422_2_TX+`), because a port is a
naming convention on the signal, not a field (`core/ports.py`, `docs/IMPORTS.md`). The project's
signal map (`naming.signal_map`, 4.4.0, `core/signal_map.py`) renames a team's name in the Signal
(or Function) cell before the port is written into it, also inside a port (`TTC1_TXP` becomes
`TTC1_TX+`; signal `TXP` with port `TTC1` gives `TTC1_TX+`); each rename is listed
(`PinoutPlan.renamed`) and kept in the import record.

The users' sheets of the harness plan (3.0.0, design section 4.3) are read as well: *Description*
is the pin's function (a sheet with Function and Description reads Function as the signal), *Level*
the pin's level, and the Direction words `PWR`, `PWR-RET`, `GND`, `SGND`, `SHIELD` and `SPARE` the
pin's role (`IN`, `OUT` and `IN/OUT` its direction). Any other word, such as `TEST`, sets neither:
the row is imported, and the import record lists the word under the converted values. The columns
*Source* (also *ICD*), *Source version* and *Source link* say where the pinout of a connector comes
from; the rows of one connector give one value.

An optional *Pin row* column (4.0.0, format 4, design of 4.0.0 section 6.2; also *Row* or *Contact
row*) gives the row of the pin on the face of its connector, a whole number from 1; the pins of a
row are in the order of the lines, and an empty cell leaves the pin out of the rows. For each
connector the rows are compared with the layout it has now (`core/row_layout.layout_of`), row by
row as sets of pins: equal, nothing changes (so a file `export-pinout` wrote reads back as no
change); else they become the connector's own rows (`row_layout_edit.plan_set_row_layout`),
keeping the ring mark of the layout it had, and the import names the connector under *row layouts
set*, with a note when its part has no rows of its own. Rows that leave a gap (1 and 3) are closed
up and noted. A sheet without the column leaves every layout as it is.

The tool knows no program's table format: columns are matched by their headings (with common
aliases), the way the parts import does. Columns it cannot store (remarks,
a voltage) are named in a warning and left out; the file format has no field for them.
Every row gets a result with its exact reason, a sheet with a bad row is not imported at all, and
what is imported is one `History` step ("Import pinout (2 connectors, 36 pins)").
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import devices, edit
from .commands import Op
from .edit import EditError
from .errors import HarnessError
from .imports import (
    MAX_BYTES,
    STAMP_LINE,
    ImportError_,
    parse_csv,
    parse_csv_file,
    read_table_sheet,
)
from .model import Connector, InterfaceType, Project, RowLayout
from .ports import (
    SEPARATORS,
    Port,
    compose,
    is_signal_of,
    natural_key,
    port_name_problem,
    ports_of,
    read_signal,
)
from .row_layout import layout_of, layout_text
from .row_layout_edit import plan_set_row_layout
from .signal_map import Renamed
from .signal_map import apply as apply_signal_map
from .signal_map import table as project_signal_map

Table = list[list[str]]

FIELDS: tuple[tuple[str, str], ...] = (
    ("connector", "Connector"),
    ("pin", "Pin"),
    ("signal", "Signal"),
    ("mode", "Mode"),
    ("contact_size", "Contact size"),
    ("termination", "Termination"),
    ("function", "Function"),
    ("contact_part", "Cable contact"),
    ("direction", "Direction"),
    ("part", "Part"),
    ("gender", "Gender"),
    ("port", "Port"),
    ("level", "Level"),
    ("source_doc", "Source"),
    ("source_version", "Source version"),
    ("source_link", "Source link"),
    ("pin_row", "Pin row"),
)
_ALIASES = {
    "connector": ("connector", "conn", "connectorid", "connectorname", "ref", "reference"),
    "pin": ("pin", "pinid", "pinnumber", "pinno", "pinname", "contact", "number"),
    "signal": ("signal", "signalname", "net", "netname", "function"),
    "mode": ("mode", "allocation", "fixed"),
    "contact_size": ("contactsize", "size", "gauge", "contactgauge"),
    "termination": ("termination", "term", "terminationtype"),
    "function": (
        "function",
        "pinfunction",
        "functiondescription",
        "description",
    ),  # "function" alone means the signal; "description" is the users' word for it (3.0.0)
    # "contact" alone is the pin when the sheet has no other pin heading (as it always was)
    "contact_part": ("cablecontact", "contactpart", "cablecontactpart", "contact"),
    "direction": ("direction", "pindirection", "dir", "iomode"),
    "part": ("part", "partid", "partnumber", "connectorpart"),
    "gender": ("gender", "sex"),
    "port": ("port", "portname", "portid"),
    "level": ("level", "signallevel", "pinlevel"),
    "source_doc": ("source", "icd", "sourcedocument", "sourcedoc"),
    "source_version": ("sourceversion", "icdversion", "sourcedocumentversion"),
    "source_link": ("sourcelink", "icdlink", "sourceurl", "icdurl"),
    "pin_row": ("pinrow", "row", "contactrow"),  # 4.0.0: the row of the pin on the face
}
# the fields that belong to a connector, not to a pin: the rows of one connector give one value
CONNECTOR_COLUMNS = ("source_doc", "source_version", "source_link")
DIRECTION_UNIT = "Direction word"
NOT_SET = "not set"
WORDS = "PWR, PWR-RET, GND, SGND, SHIELD, SPARE, IN, OUT, IN/OUT"
# headings the file format has no field for: named in a warning, never written
_UNSTORED = frozenset(
    {
        "remarks", "remark", "notes", "note", "comment",
        "comments", "voltage", "current", "class",
    }
)  # fmt: skip
_YES = frozenset({"yes", "y", "true", "x", "1", "fixed"})
_GENDER_WORDS = {
    "male": "male", "m": "male", "plug": "male", "pin": "male", "pins": "male",
    "female": "female", "f": "female", "socket": "female", "receptacle": "female",
}  # fmt: skip


def read_pinout_table(path: Path | str) -> tuple[Table, str | None]:
    """Read a pinout sheet. A CSV file written by this tool starts with a comment line (`# ...`,
    docs/OUTPUTS.md); it is skipped. In a workbook written by this tool the first sheet is the
    "About" sheet; it is passed over, so what `export-pinout` writes can be read back."""
    p = Path(path)
    if p.suffix.lower() in (".csv", ".tsv"):
        try:
            raw = p.read_bytes()[: MAX_BYTES + 1]
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ImportError_(
                "The file is not UTF-8 text. Save it as CSV UTF-8 and try again."
            ) from exc
        except OSError as exc:
            raise ImportError_(f"The file could not be read ({exc.strerror}).") from exc
        if STAMP_LINE.match(
            text
        ):  # the tool's own file: the stamp line goes, so do the apostrophes
            return parse_csv_file(text), None
        if text.startswith("# "):
            text = text.partition("\n")[2]
        return parse_csv(text), None
    return read_table_sheet(p, skip_sheets=("About",))


def _norm(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def guess_mapping(header: list[str]) -> dict[str, int]:
    """Which column is which field, by heading (the first column that matches wins; a column is
    used once)."""
    norm = [_norm(h) for h in header]
    out: dict[str, int] = {}
    used: set[int] = set()
    for key, _label in FIELDS:
        for alias in _ALIASES[key]:
            hit = next((i for i, h in enumerate(norm) if h == alias and i not in used), None)
            if hit is not None:
                out[key] = hit
                used.add(hit)
                break
    return out


def unstored_columns(header: list[str], mapping: dict[str, int]) -> list[str]:
    """Headings of columns that carry something the project file cannot hold."""
    mapped = set(mapping.values())
    return [h for i, h in enumerate(header) if i not in mapped and _norm(h) in _UNSTORED]


@dataclass
class PinoutRow:
    row_number: int
    ok: bool
    message: str
    connector: str = ""  # the connector ID the row goes to
    pin: str = ""
    signal: str = ""  # the signal the pin gets: with the port of a Port column written into it


@dataclass(frozen=True)
class WordConversion:
    """A Direction word the import does not know (`TEST`): the row is imported, and the pin's role
    and direction are not set from it (design of 3.0.0 section 4.3)."""

    row: int
    connector: str
    pin: str
    word: str


# the longest signal name the file format takes (`Pin.signal` is a `Name`)
MAX_SIGNAL = 200


@dataclass(frozen=True)
class PortReport:
    """The named ports of one imported connector for one interface type it can carry."""

    connector: str
    type_id: str
    type_name: str
    ports: tuple[Port, ...]  # natural order of the names; ports that cannot be used included
    notes: tuple[str, ...]  # incomplete or doubled ports and ambiguous pins, in plain words

    def as_dict(self) -> dict[str, object]:
        """The report as `--json` writes it."""
        return {
            "connector": self.connector,
            "type": self.type_id,
            "type_name": self.type_name,
            "ports": [
                {
                    "name": p.name,
                    "usable": p.usable,
                    "pins": [{"signal": pp.signal, "pin": pp.pin_id} for pp in p.pins],
                    "missing": list(p.missing),
                    "doubled": list(p.doubled),
                }
                for p in self.ports
            ],
            "notes": list(self.notes),
        }


@dataclass
class PinoutPlan:
    rows: list[PinoutRow] = field(default_factory=list)
    ops: list[Op] = field(default_factory=list)
    connectors: list[str] = field(default_factory=list)  # connector IDs that are added or changed
    added: list[str] = field(default_factory=list)  # ... of which new
    unchanged: list[str] = field(default_factory=list)  # connectors the table leaves as they are
    pins: int = 0
    unmatched_signals: dict[str, list[str]] = field(default_factory=dict)  # signal -> "J01.A1"
    warnings: list[str] = field(default_factory=list)
    unit_id: str = ""
    new_unit: bool = False
    ports: list[PortReport] = field(default_factory=list)  # per connector, then per type ID
    words: list[WordConversion] = field(default_factory=list)  # unknown Direction words
    row_layouts: list[str] = field(default_factory=list)  # connectors given own rows (4.0.0)
    row_notes: list[str] = field(default_factory=list)  # a gap closed up, rows on one connector
    renamed: list[Renamed] = field(default_factory=list)  # pins the project's signal map renamed

    @property
    def port_lines(self) -> list[str]:
        """One line per connector and port list: `J01: RS-422 ports: RS422_1 (pins 1-4), RS422_2
        (5-8)`. Types with the same ports on a connector share a line (`Ethernet or RS-422`)."""
        lines: list[str] = []
        groups: dict[tuple[str, str, int], list[str]] = {}
        for r in self.ports:
            key = (r.connector, _ports_text(r.ports), len(r.ports))
            groups.setdefault(key, []).append(r.type_name)
        for (cid, text, count), names in groups.items():
            word = "ports" if count > 1 else "port"
            lines.append(f"{cid}: {' or '.join(names)} {word}: {text}")
        return lines

    @property
    def ok_count(self) -> int:
        return sum(r.ok for r in self.rows)

    @property
    def bad_count(self) -> int:
        return sum(not r.ok for r in self.rows)

    @property
    def importable(self) -> bool:
        return bool(self.ops) and self.bad_count == 0

    @property
    def label(self) -> str:
        n, p = len(self.connectors), self.pins
        return (
            f"Import pinout ({n} connector{'s' if n != 1 else ''}, {p} pin{'s' if p != 1 else ''})"
        )


def plan_pinout_import(
    project: Project,
    table: Table,
    mapping: dict[str, int],
    *,
    unit_id: str,
    new_unit_name: str | None = None,
    subsystem: str | None = None,
    parts: dict[str, str] | None = None,
    default_part: str | None = None,
    gender: str | None = None,
    connector: str | None = None,
    replace: bool = False,
) -> PinoutPlan:
    """One result per data row of `table` (the first row is the header). `unit_id` is an existing
    unit, or a new device when `new_unit_name` is given. `parts` maps a connector as the sheet
    names it (`J1`) to a library part for a connector that does not exist yet; `default_part` is
    used for the others; a `Part` column of the sheet does the same per row. Without a Connector
    column every row goes to `connector` (default `J01`). With `replace` the pins the sheet does
    not name are dropped from a connector that already exists. Nothing is invented: a missing part
    or a bad value is a refused row, never a guess."""
    plan = PinoutPlan(unit_id=unit_id)
    if "pin" not in mapping:
        raise ImportError_("The file needs a Pin column (a heading such as Pin or Pin number).")
    header = table[0] if table else []
    plan.warnings += [
        f"Column '{h}' is not imported: a pin has no field for it."
        for h in unstored_columns(header, mapping)
    ]
    work = edit.clone_with(project, [])  # the plan is built step by step on a copy
    if unit_id not in work.units:
        if not new_unit_name:
            raise ImportError_(
                f"Device '{unit_id}' does not exist. Name the new device to create it."
            )
        unit_ops, _ = devices.ops_add_device(
            work, unit_id=unit_id, name=new_unit_name, subsystem=subsystem
        )
        plan.ops += unit_ops
        work = edit.clone_with(work, unit_ops)
        plan.new_unit = True
    parts = parts or {}
    by_connector: dict[str, list[tuple[int, dict[str, str]]]] = {}
    names: dict[str, str] = {}  # casefolded connector name -> the name as first written
    order: list[str] = []
    fixed_column = "mode" in mapping and _norm(header[mapping["mode"]]) == "fixed"
    words: list[tuple[int, str]] = []  # (row, word) of the Direction words that set nothing
    team_names = project_signal_map(project)  # {} without the setting: the names as in 4.3.0

    for n, row in enumerate(table[1:], start=2):

        def cell(key: str, row: list[str] = row) -> str:
            i = mapping.get(key)
            return row[i].strip() if i is not None and i < len(row) else ""

        if not any(c.strip() for c in row):
            continue
        shown = cell("connector") or connector or "J01"
        already = _find_connector(work, unit_id, shown)  # the sheet may use the name or the ID
        name = names.setdefault((already.id if already else shown).casefold(), shown)
        record = {k: cell(k) for k, _ in FIELDS if k in mapping}
        if fixed_column:  # a "Fixed" column holds yes/no, not a mode word
            record["mode"] = "fixed" if record.get("mode", "").casefold() in _YES else ""
        if "direction" in record:  # the users' words: a role word or a direction word (3.0.0)
            said = devices.read_direction_word(record["direction"])
            typed = record.pop("direction")
            if said is None:
                words.append((n, typed))
                plan.warnings.append(
                    f"Row {n}: the Direction word '{typed}' is not one the tool reads ({WORDS}); "
                    "the pin's role and direction are not set from it."
                )
            else:
                record[said[0]] = said[1]
        if not cell("pin"):
            plan.rows.append(PinoutRow(n, False, "The pin is empty", name, ""))
            continue
        if name not in by_connector:
            by_connector[name] = []
            order.append(name)
        by_connector[name].append((n, record))

    seen_rows: list[tuple[int, PinoutRow]] = []
    for name in order:
        rows = by_connector[name]
        existing = _find_connector(work, unit_id, name)
        cid = existing.id if existing is not None else ""
        ops: list[Op] = []
        is_new = existing is None
        if existing is None:
            part_id = (
                next((r["part"] for _n, r in rows if r.get("part")), "")
                or parts.get(name, "")
                or default_part
                or ""
            )
            if not part_id:
                msg = f"No part for the new connector {name}: give one for it (--part {name}=PART) or one for all"
                plan.rows += [PinoutRow(n, False, msg, name, r.get("pin", "")) for n, r in rows]
                continue
            sheet_gender = next((r["gender"] for _n, r in rows if r.get("gender")), "") or (
                gender or ""
            )
            word = _GENDER_WORDS.get(sheet_gender.strip().casefold()) if sheet_gender else None
            if sheet_gender and word is None:
                msg = f"The gender '{sheet_gender}' is not male or female"
                plan.rows += [PinoutRow(n, False, msg, name, r.get("pin", "")) for n, r in rows]
                continue
            try:
                new_ops, cid = devices.ops_add_connector(
                    work, unit_id, part_id=part_id, name=name if _usable_name(name) else None,
                    gender=word, pin_ids=[],
                )  # fmt: skip
            except (EditError, HarnessError) as exc:
                plan.rows += [
                    PinoutRow(n, False, str(exc), name, r.get("pin", "")) for n, r in rows
                ]
                continue
            ops += new_ops
            work = edit.clone_with(work, new_ops)
        types = _types_of(work, work.connectors[cid])
        refused: dict[int, str] = {
            n: f"Pin row '{r['pin_row']}' is not a whole number from 1 (the row of the pin)"
            for n, r in rows
            if r.get("pin_row") and _row_number(r["pin_row"]) is None
        }
        with_port: list[str] = []  # pins whose signal names the port of a Port column
        written_rows: list[tuple[int, dict[str, str]]] = []
        renamed_here: list[Renamed] = []
        for n, r in rows:
            read = r.get("signal", "")
            by_map = apply_signal_map(read, team_names) if read else None
            if by_map is not None and by_map.ambiguous:
                plan.warnings.append(by_map.warning(f"{cid} pin {r['pin']}"))
            if by_map is not None and by_map.renamed:  # before the port is written into it
                r = {**r, "signal": by_map.stored}
            port = r.get("port", "")
            if port:
                signal, problem, warning = port_signal(port, r.get("signal", ""), types, cid)
                if problem:
                    refused[n] = problem
                    continue
                if warning:
                    plan.warnings.append(f"Row {n}: {warning}")
                elif is_signal_of(signal, types):
                    with_port.append(r["pin"])
                r = {**r, "signal": signal}
            if by_map is not None and by_map.renamed:
                renamed_here.append(Renamed(n, cid, r["pin"], read, r["signal"]))
            written_rows.append((n, r))
        rows = written_rows
        source, clash = _connector_source(rows)
        if clash:
            refused[clash[0]] = clash[1]
        sheet = [{k: v for k, v in r.items() if k in devices.IMPORT_ROW_COLUMNS} for _n, r in rows]
        pins = devices.plan_pin_rows(
            work, cid, sheet, replace=replace or is_new, row_numbers=[n for n, _r in rows]
        )
        if pins.issues or refused:
            bad: set[int] = set(refused)
            for n, message in refused.items():
                plan.rows.append(PinoutRow(n, False, message, name, _pin_of(by_connector[name], n)))
            for issue in pins.issues:
                src = issue.row or by_connector[name][0][0]
                bad.add(src)
                plan.rows.append(PinoutRow(src, False, issue.reason, name, issue.pin))
            for n, r in rows:  # the rows without a problem are listed too (nothing is imported)
                if n not in bad:
                    plan.rows.append(PinoutRow(n, True, "ok", name, r["pin"], r.get("signal", "")))
            continue
        try:
            set_ops = devices.ops_set_pinout(work, cid, list(pins.pins))
            if source:
                after = edit.clone_with(work, set_ops)
                set_ops += devices.ops_update_connector(after, cid, **source)
            if "pin_row" in mapping:
                set_ops += _pin_row_ops(plan, edit.clone_with(work, set_ops), cid, rows)
        except (EditError, HarnessError) as exc:
            plan.rows += [PinoutRow(n, False, str(exc), name, r.get("pin", "")) for n, r in rows]
            continue
        same = not is_new and not set_ops  # the table says what the connector already holds
        ops += set_ops
        work = edit.clone_with(work, set_ops)
        plan.ops += ops
        plan.renamed += renamed_here
        if same:
            plan.unchanged.append(cid)
        else:
            plan.connectors.append(cid)
            plan.pins += len(rows)
        if is_new:
            plan.added.append(cid)
        all_types = sorted(work.interface_types.values(), key=lambda t: t.id)
        for _n, r in rows:  # a port name reads as the signal of its type (`RS422_2_TX+`)
            sig = r.get("signal", "")
            if sig and not is_signal_of(sig, all_types):
                plan.unmatched_signals.setdefault(sig, []).append(f"{cid} pin {r['pin']}")
        _report_ports(plan, work.connectors[cid], types, with_port)
        plan.words += [
            WordConversion(n, cid, r["pin"], w) for n, r in rows for m, w in words if m == n
        ]
        for n, r in rows:
            word = "added" if is_new else "unchanged" if same else "updated"
            seen_rows.append((n, PinoutRow(n, True, word, cid, r["pin"], r.get("signal", ""))))
    plan.rows += [r for _n, r in seen_rows]
    plan.rows.sort(key=lambda r: r.row_number)
    if plan.bad_count:
        plan.ops = []  # a sheet with a bad row is not imported at all
    return plan


def _row_number(cell: str) -> int | None:
    """The row of a *Pin row* cell: a whole number from 1 (`2`, or `2.0` as a workbook may give
    it), else None."""
    text = cell.strip()
    if text.endswith(".0"):
        text = text[:-2]
    if not text.isascii() or not text.isdigit() or int(text) < 1:
        return None
    return int(text)


def _pin_row_ops(
    plan: PinoutPlan, project: Project, cid: str, rows: Sequence[tuple[int, dict[str, str]]]
) -> list[Op]:
    """The ops that give the box connector `cid` (as the import leaves its pins, in `project`) the
    rows of the *Pin row* column, or none when the column gives it no row or the rows it has now
    (section 3), compared row by row as sets of pins. Records the connector and the notes in
    `plan`."""
    c = project.connectors[cid]
    ids = {p.id.casefold(): p.id for p in c.pins}
    numbered: dict[int, list[str]] = {}
    for _n, r in rows:
        number = _row_number(r.get("pin_row", ""))
        pid = ids.get(r.get("pin", "").strip().casefold())
        if number is not None and pid is not None and pid not in numbered.get(number, []):
            numbered.setdefault(number, []).append(pid)
    if not numbered:
        return []
    now = layout_of(project, c)
    have = {k: set(row) for k, row in enumerate(now.rows, start=1) if row} if now else {}
    keys = sorted(numbered)
    closed = {k: set(numbered[n]) for k, n in enumerate(keys, start=1)}  # a gap closed up
    if have in ({k: set(v) for k, v in numbered.items()}, closed):
        return []
    layout = RowLayout(rows=[numbered[k] for k in keys], rings=now.rings if now else False)
    ops = plan_set_row_layout(project, layout, connector=cid)
    plan.row_layouts.append(cid)
    if keys != list(range(1, len(keys) + 1)):
        given = ", ".join(str(k) for k in keys)
        plan.row_notes.append(
            f"{cid}: the Pin row column gives the rows {given}; they are stored as the rows 1 to "
            f"{len(keys)} ({layout_text(layout)})."
        )
    part = project.parts.get(c.part_id)
    if part is not None and part.row_layout is None:
        plan.row_notes.append(
            f"The rows are stored on {cid} only; to use them for every connector of part "
            f"{part.id}, choose Use for every connector of this part in the Devices tab, or run "
            f"`pin-rows --connector {cid} --to-part`."
        )
    return ops


def _connector_source(
    rows: Sequence[tuple[int, dict[str, str]]],
) -> tuple[dict[str, str], tuple[int, str] | None]:
    """The source of a connector's pinout that its rows give (`CONNECTOR_COLUMNS` present in the
    sheet; an empty cell does not count), and the first row that gives a second value, with the
    reason. A column whose cells are all empty clears the value."""
    out: dict[str, str] = {}
    first: dict[str, int] = {}
    for n, r in rows:
        for key in CONNECTOR_COLUMNS:
            if key not in r:
                continue
            value = r[key]
            out.setdefault(key, "")
            if not value:
                continue
            if not out[key]:
                out[key], first[key] = value, n
            elif out[key] != value:
                word = dict(FIELDS)[key]
                return out, (
                    n,
                    f"{word} '{value}' differs from '{out[key]}' in row {first[key]}: the rows "
                    "of one connector give one value",
                )
    return out, None


def _types_of(project: Project, connector: Connector) -> list[InterfaceType]:
    """The interface types a connector can carry, in ID order: the ones it names (`carries`), or
    every type of the project when it names none."""
    named = [project.interface_types[t] for t in connector.carries if t in project.interface_types]
    return sorted(named or project.interface_types.values(), key=lambda t: t.id)


def port_signal(
    port: str, signal: str, types: Sequence[InterfaceType], connector_id: str = "the connector"
) -> tuple[str, str, str]:
    """The signal a row with the port `port` writes, as (signal, refusal, warning); a refusal or a
    warning is "" when there is none. `types` are the types the connector can carry (`_types_of`).

    - `signal` is a signal of one or more of `types`: the pin gets `PORT_SIGNAL` (`compose`), and
      the port name must read back as that port for each of these types (`port_name_problem`);
    - `signal` already reads as a signal of the port `port` (`RS422_2_TX+`, `TX+.RS422_2`): kept;
    - `signal` reads as a signal of another port only: refused;
    - `signal` is no signal of these types in any form: kept as it is, as before 2.1.0, with a
      warning (the port is not added blindly to a name the tool cannot read).
    A composed name longer than a signal name may be is refused."""
    if not signal:
        return (
            "",
            f"Port {port} has no signal on this row: give the signal or leave the port empty",
            "",
        )
    bare = [t for t in types if signal in {s.name for s in t.signals}]
    if bare:
        for t in bare:
            problem = port_name_problem(port, [s.name for s in t.signals])
            if problem:
                return signal, problem, ""
        name = compose(port, signal, [s.name for s in bare[0].signals])
    else:
        readings = [r for t in types for r in read_signal(signal, [s.name for s in t.signals])]
        if any(r.port == port for r in readings):
            name = signal
        elif readings:
            others = sorted({r.port for r in readings}, key=natural_key)
            return (
                signal,
                f"The signal {signal} names the port {' or '.join(others)}, not {port}",
                "",
            )
        elif any(signal.startswith(port + sep) for sep in SEPARATORS):
            return signal, "", ""  # it already starts with the port
        else:
            return (
                signal,
                "",
                f"{signal} is no signal of an interface type that {connector_id} can carry, so the"
                f" port {port} is not added to it; the signal is imported as it is.",
            )
    if len(name) > MAX_SIGNAL:
        return (
            signal,
            f"The signal {name} would have {len(name)} characters; a signal name has at most"
            f" {MAX_SIGNAL}",
            "",
        )
    return name, "", ""


def _pin_of(rows: list[tuple[int, dict[str, str]]], n: int) -> str:
    return next((r.get("pin", "") for m, r in rows if m == n), "")


def _report_ports(
    plan: PinoutPlan, connector: Connector, types: Sequence[InterfaceType], with_port: list[str]
) -> None:
    """The named ports of `connector` per type into `plan.ports`, their problems into the
    warnings; a warning when pins that name a port are not fixed (only fixed pins form ports)."""
    for t in types:
        found = ports_of(connector, t)
        if not found.named:
            continue
        plan.ports.append(PortReport(connector.id, t.id, t.name, found.named, found.notes))
        plan.warnings += [n for n in found.notes if n not in plan.warnings]
    loose = sorted(
        (p.id for p in connector.pins if p.id in with_port and not p.fixed), key=natural_key
    )
    if loose:
        plan.warnings.append(
            f"{connector.id}: pin{'s' if len(loose) > 1 else ''} {pin_ranges(loose)}"
            f" name{'' if len(loose) > 1 else 's'} a port but"
            f" {'are' if len(loose) > 1 else 'is'} not fixed; only fixed pins form ports, so give"
            f" {'them' if len(loose) > 1 else 'it'} the mode fixed."
        )


_NUMBERED = re.compile(r"^(.*?)([0-9]+)$")


def pin_ranges(pin_ids: Sequence[str]) -> str:
    """Pins in natural order with runs written as ranges: `1-4`, `A1-A3, B7`."""
    out: list[str] = []
    run: list[str] = []
    last: tuple[str, int] | None = None
    for pid in sorted(pin_ids, key=natural_key):
        m = _NUMBERED.match(pid)
        key = (m.group(1), int(m.group(2))) if m else None
        if run and key is not None and last is not None and key == (last[0], last[1] + 1):
            run.append(pid)
        else:
            if run:
                out.append(run[0] if len(run) == 1 else f"{run[0]}-{run[-1]}")
            run = [pid]
        last = key
    if run:
        out.append(run[0] if len(run) == 1 else f"{run[0]}-{run[-1]}")
    return ", ".join(out)


def _ports_text(ports: Sequence[Port]) -> str:
    """`RS422_1 (pins 1-4), RS422_2 (5-8)`; a port that cannot be used says so."""
    parts: list[str] = []
    for k, p in enumerate(ports):
        where = pin_ranges([pp.pin_id for pp in p.pins])
        tail = "" if p.usable else "; not usable"
        label = ("pins " if len(p.pins) > 1 else "pin ") if k == 0 else ""
        parts.append(f"{p.name} ({label}{where}{tail})")
    return ", ".join(parts)


def _usable_name(name: str) -> bool:
    return bool(name) and len(name) <= 200


def _find_connector(project: Project, unit_id: str, name: str):  # type: ignore[no-untyped-def]
    for c in edit.unit_connectors(project, unit_id):
        if name.casefold() in (c.id.casefold(), c.name.casefold()):
            return c
    return None
