# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The project's signal map: a team's signal names (4.4.0, milestone E4, owner questions N6 and N7).

The design: `docs/ait/DESIGN_4.4_NAMES_PORTS.md`, part C, sections 5.1 to 5.4, owner question N11.

The key `signal_map` of `config/naming.json` is a table of a **team name** to a **signal name** of
an interface type (`{"TXP": "TX+", "CAN_H": "CANH"}`), the form of a JSON file of
`import-netlist --signal-map`. Each name is a valid signal name (1 to 200 characters), no name maps
to itself, no signal name is also a team name (no chains) and the table has at most 1000 entries
(`check`). Not set, `null` or `{}`: no map. The tool ships no name (D-11): no example, template or
new project sets the key.

`apply` reads one name against the table: the whole name, else a name that reads as `P<sep>k` or
`k<sep>P` with k a team name, by the rule of ports (`ports.read_signal` against the table's keys),
so `TTC1_TXP` gives `TTC1_TX+` and the port and the separator are kept (N7). A name that reads in
two ways is not renamed. Only the two importers that read a device's pins from outside apply the
map (N6, N11); generation does not read it (`generation_status.NOT_READ_BY_GENERATION`).

`Renamed` and `renamed_lines` are one rename of an import and the lines that say it (section
5.3): the echo of `import-pinout` and `import-netlist`, the import wizard's preview, and the
conversions of the import record (`UNIT`).

`read_file` reads a file of pairs as `import-netlist --signal-map FILE` always has (moved here from
`cli/data.py` without a change): a CSV of two columns with an optional heading row, or a JSON
object. The module is pure but for `read_file`.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from .imports import ImportError_, read_table
from .model import Project
from .model.base import Name
from .ports import read_signal

CONFIG_FILE, CONFIG_KEY = "naming", "signal_map"
MAX_ENTRIES = 1000
RANGE = (
    "a table of names to signal names, each 1 to 200 characters, no name mapped to itself, no "
    "signal name that is also a team name, at most 1000"
)
WHY = (
    "must be a table of a team's signal name to the signal name of an interface type, each 1 to "
    "200 characters, no name mapped to itself and no signal name that is also a team name"
)
# the heading of the first column that `read_file` skips in a CSV
HEADINGS = ("net", "name", "kicad", "from", "net name")

_NAME: TypeAdapter[str] = TypeAdapter(Name)


def _is_name(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        _NAME.validate_python(value)
    except ValidationError:
        return False
    return True


def check(value: object) -> str | None:
    """Why a value is not a signal map (None when it is one, or when it is None or empty): a table
    (a JSON object) of team names to signal names, each a valid signal name of 1 to 200
    characters, no name mapped to itself, no signal name that is also a team name, at most 1000
    entries (section 5.1). It does not ask that a signal name is one of the project's types:
    types change, and the import lists the names no type has."""
    if value is None:
        return None
    if not isinstance(value, Mapping) or len(value) > MAX_ENTRIES:
        return WHY
    for team, signal in value.items():
        if not (_is_name(team) and _is_name(signal)) or team == signal or signal in value:
            return WHY
    return None


def table(project: Project) -> dict[str, str]:
    """The project's map as the importers read it: the key of `config/naming.json` when `check`
    accepts it, else no map (a refused table is reported by `config-invalid`, never half used)."""
    cfg = project.config.get(CONFIG_FILE)
    raw = cfg.values.get(CONFIG_KEY) if cfg is not None else None
    if not isinstance(raw, Mapping) or check(raw) is not None:
        return {}
    return {str(k): str(v) for k, v in raw.items()}


@dataclass(frozen=True)
class Mapped:
    """One name read against the map: the name `read` and the name `stored`; `keys`, the team
    names it was read by (one when it is renamed, two or more when it reads in several ways);
    `readings`, how many ways it was read."""

    read: str
    stored: str
    keys: tuple[str, ...] = ()
    readings: int = 0

    @property
    def renamed(self) -> bool:
        return self.stored != self.read

    @property
    def ambiguous(self) -> bool:
        """The name reads in two or more ways, so it is not renamed."""
        return self.readings > 1

    def warning(self, where: str) -> str:
        """The warning of a name that reads in two ways (section 5.3), without `warning: `:
        `TXP_RXN on OBC1-J01 pin 9 can be read as TXP or RXN of the signal map, so it is not
        renamed.`"""
        times = "two" if self.readings == 2 else str(self.readings)
        how = (
            f"{self.keys[0]} of the signal map in {times} ways"
            if len(self.keys) == 1
            else f"{' or '.join(self.keys)} of the signal map"
        )
        return f"{self.read} on {where} can be read as {how}, so it is not renamed."


def apply(name: str, mapping: Mapping[str, str]) -> Mapped:
    """`name` as the map renames it (section 5.2): the whole name when it is a team name, else the
    one reading `P<sep>k` or `k<sep>P` of a team name k, with the port P and the separator kept
    (`TTC1_TXP` gives `TTC1_TX+`, `TXP.TTC1` gives `TX+.TTC1`). No reading, or two and more: the
    name as it came. With an empty map every name comes back as it came."""
    if not mapping:
        return Mapped(name, name)
    if name in mapping:
        return Mapped(name, mapping[name], (name,), 1)
    found = [r for r in read_signal(name, mapping) if r.form != "bare"]
    if not found:
        return Mapped(name, name)
    if len(found) > 1:
        keys = tuple(dict.fromkeys(r.signal for r in found))
        return Mapped(name, name, keys, len(found))
    r = found[0]
    signal = mapping[r.signal]
    stored = (
        f"{r.port}{r.separator}{signal}" if r.form == "prefix" else f"{signal}{r.separator}{r.port}"
    )
    return Mapped(name, stored, (r.signal,), 1)


# the unit of a rename in the import record (`import_record.Conversion`, section 5.3)
UNIT = "signal map"
FIELD = "signal"
HEADING = "Renamed by the project's signal map (config/naming.json signal_map): {} signal(s)"


@dataclass(frozen=True)
class Renamed:
    """One pin an import renamed by the project's map (section 5.3): the row of the file (the
    sheet row of `import-pinout`, the connector component of `import-netlist`), the connector and
    the pin, the name `read` in the file and the name `stored` on the pin (with the port of a Port
    column composed in)."""

    row: int
    connector: str
    pin: str
    read: str
    stored: str

    @property
    def where(self) -> str:
        return f"{self.connector} pin {self.pin}"

    def text(self) -> str:
        """`TTC1_TXP -> TTC1_TX+: OBC1-J01 pin 1`."""
        return f"{self.read} -> {self.stored}: {self.where}"

    def as_dict(self) -> dict[str, str]:
        """The rename as `--json` writes it (`renamed_signals`)."""
        return {
            "connector": self.connector,
            "pin": self.pin,
            "read": self.read,
            "stored": self.stored,
        }


def renamed_lines(renamed: Sequence[Renamed]) -> list[str]:
    """The lines of the echo and of the import wizard's preview: none without a rename, else
    `Renamed by the project's signal map (config/naming.json signal_map): 4 signal(s)` and one
    indented line per pin."""
    if not renamed:
        return []
    return [HEADING.format(len(renamed)), *(f"  {r.text()}" for r in renamed)]


def read_file(path: Path) -> dict[str, str]:
    """The pairs of a signal map file, as `import-netlist --signal-map FILE` reads it: a JSON
    object of text to text (a file ending in `.json`), else a table of two columns (CSV, TSV or
    XLSX, through `imports.read_table`) whose first row is skipped when its first cell is a
    heading (`net`, `name`, `kicad`, `from` or `net name`); rows with an empty cell are left out.
    A file that cannot be read raises `ImportError_` with the reason. It does not check the
    table: `check` does, where the table is kept."""
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in raw.items()
            ):
                raise ImportError_("The signal map must be a JSON object of text to text.")
            return dict(raw)
        rows = read_table(path)
    except (OSError, ValueError, RecursionError) as exc:
        raise ImportError_(f"The signal map could not be read ({exc}).") from exc
    if rows and rows[0][0].strip().lower() in HEADINGS:
        rows = rows[1:]
    return {
        r[0].strip(): r[1].strip() for r in rows if len(r) >= 2 and r[0].strip() and r[1].strip()
    }
