# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The settings of the harness plans, `config/harness_plan.json` (design of 3.0.0 sections 4.1, 6
and 10), as the editor's *Settings > Harness plan* changes them. Pure functions, no Qt: each change
is the operations of one undo step, which the window runs through `History`.

    values = plan_values(project)                       # the rule, the codes, the note lines
    ops = plan_settings_edit(project, colour_rule="pin_code")
    ops = plan_example_code(project, ["P-MDM-15S-PIG"])  # *Use the example colour code*
    pins = parse_colour_table("Pin\\tColour\\n1\\tBlack\\n2\\tBrown\\n")

The file is created by the first value that is not the default and removed (`DeleteConfig`) when
every value is back to its default: the rule `wire`, no code, no note line. A change that `validate`
would refuse (`configcheck.harness_plan_issues`: a part in two codes, a code named twice) is refused
here with the same words, so the editor never writes a file that stops generation. The example
colour code is added only by `plan_example_code`, when a person presses the button; nothing here
applies it by itself (D-242, Q3, Q26)."""

import csv
import io
from collections.abc import Mapping, Sequence
from typing import Any

from . import templates
from .commands import DeleteConfig, Op, SetConfig
from .configcheck import COLOUR_RULES, harness_plan_issues
from .edit import EditError
from .model import Project
from .model.config import ConfigFile

CONFIG_NAME = "harness_plan"
DEFAULT_RULE = COLOUR_RULES[0]  # "wire": each end shows the wire's colour
EXAMPLE_NAME = templates.EXAMPLE_CODE_NAME
MAX_NOTE_LINES = 20  # note lines on the Notes sheet of every plan
MAX_PINS = 500  # rows of one colour code
_PIN_HEADINGS = frozenset({"pin", "pin number", "pinout", "pin no", "pin no."})
_COLOUR_HEADINGS = frozenset({"colour", "color", "wire colour", "wire color"})


def plan_values(project: Project) -> dict[str, Any]:
    """The settings as they stand: `colour_rule`, `colour_codes` (a list of codes, each with `name`,
    `parts`, `pins` and `example`) and `notes`, the defaults filled in for what the file leaves
    out (also with no file)."""
    c = project.config.get(CONFIG_NAME)
    values = dict(c.values) if c is not None else {}
    rule = values.get("colour_rule")
    codes = values.get("colour_codes")
    notes = values.get("notes")
    return {
        "colour_rule": rule if isinstance(rule, str) and rule else DEFAULT_RULE,
        "colour_codes": [_code(x) for x in codes if isinstance(x, dict)]
        if isinstance(codes, list)
        else [],
        "notes": [n for n in notes if isinstance(n, str)] if isinstance(notes, list) else [],
    }


def _code(raw: Mapping[str, Any]) -> dict[str, Any]:
    parts = raw.get("parts", [])
    pins = raw.get("pins", {})
    return {
        "name": str(raw.get("name", "")),
        "parts": [p for p in parts if isinstance(p, str)] if isinstance(parts, list) else [],
        "pins": {str(k): v for k, v in pins.items() if isinstance(v, str)}
        if isinstance(pins, dict)
        else {},
        "example": raw.get("example") is True,
    }


def _written(code: Mapping[str, Any]) -> dict[str, Any]:
    """A code as the file holds it: the mark only while it is on."""
    out: dict[str, Any] = {
        "name": code["name"],
        "parts": list(code["parts"]),
        "pins": dict(code["pins"]),
    }
    if code.get("example"):
        out["example"] = True
    return out


def plan_settings_edit(
    project: Project,
    *,
    colour_rule: str | None = None,
    colour_codes: Sequence[Mapping[str, Any]] | None = None,
    notes: Sequence[str] | None = None,
) -> list[Op]:
    """The operations that give the settings these values (None leaves a value as it is); none when
    nothing changes. `EditError` says in words why a value is refused."""
    if project.read_only:
        raise EditError("This project is read-only (saved by a newer tool version).")
    now = plan_values(project)
    rule = now["colour_rule"] if colour_rule is None else colour_rule
    if rule not in COLOUR_RULES:
        raise EditError(f"The colour rule is one of {', '.join(COLOUR_RULES)}.")
    codes = now["colour_codes"] if colour_codes is None else [_clean_code(c) for c in colour_codes]
    lines = now["notes"] if notes is None else _clean_notes(notes)
    values: dict[str, Any] = {}
    if rule != DEFAULT_RULE:
        values["colour_rule"] = rule
    if codes:
        values["colour_codes"] = [_written(c) for c in codes]
    if lines:
        values["notes"] = lines
    issues = harness_plan_issues(values)
    if issues:
        raise EditError(issues[0].message.removeprefix("config/harness_plan.json: "))
    old = project.config.get(CONFIG_NAME)
    if not values:
        return [DeleteConfig(CONFIG_NAME)] if old is not None else []
    if old is not None and dict(old.values) == values and not old.placeholder:
        return []
    about = dict(old.about) if old is not None else {}
    return [SetConfig(ConfigFile(name=CONFIG_NAME, placeholder=False, values=values, about=about))]


def _clean_code(code: Mapping[str, Any]) -> dict[str, Any]:
    name = str(code.get("name", "")).strip()
    if not name:
        raise EditError("A colour code needs a name.")
    if len(name) > 60:
        raise EditError("The name of a colour code can have at most 60 characters.")
    parts = [str(p).strip() for p in code.get("parts", []) if str(p).strip()]
    pins = {str(k).strip(): str(v).strip() for k, v in dict(code.get("pins", {})).items()}
    if any(not k or not v for k, v in pins.items()):
        raise EditError(f"Colour code '{name}': every row needs a pin and a colour.")
    if len(pins) > MAX_PINS:
        raise EditError(f"Colour code '{name}': at most {MAX_PINS} pins.")
    return {
        "name": name,
        "parts": list(dict.fromkeys(parts)),
        "pins": pins,
        "example": bool(code.get("example", False)),
    }


def _clean_notes(notes: Sequence[str]) -> list[str]:
    lines = [n.strip() for n in notes if isinstance(n, str) and n.strip()]
    if len(lines) > MAX_NOTE_LINES:
        raise EditError(f"The plans have at most {MAX_NOTE_LINES} note lines.")
    if any(len(n) > 500 for n in lines):
        raise EditError("A note line can have at most 500 characters.")
    return lines


def plan_example_code(project: Project, parts: Sequence[str]) -> list[Op]:
    """*Use the example colour code* (section 6): the table of the users' template as the code
    `example`, marked as an example, for the connector `parts` a person names, and the rule
    `pin_code` so that the plans use it. Refused when a code of that name is there already."""
    chosen = [p.strip() for p in parts if p.strip()]
    if not chosen:
        raise EditError(
            "Name the connector parts the example colour code is for (the template names none)."
        )
    unknown = [p for p in chosen if p not in project.parts]
    if unknown:
        raise EditError(f"Part {unknown[0]} is not in the library of this project.")
    now = plan_values(project)
    if any(c["name"] == EXAMPLE_NAME for c in now["colour_codes"]):
        raise EditError(
            f"The project has a colour code named '{EXAMPLE_NAME}' already; add its parts to it."
        )
    code = templates.example_colour_code(chosen)
    return plan_settings_edit(
        project, colour_rule="pin_code", colour_codes=[*now["colour_codes"], code]
    )


def parse_colour_table(text: str) -> dict[str, str]:
    """A pasted table of two columns, pin and colour (as a spreadsheet copies it, with tabs, or as
    the example's CSV file, with commas or semicolons). A first row `Pin`, `Colour` is a heading;
    empty lines are left out. Raises `EditError` with the row that is wrong."""
    lines = [ln for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if ln.strip()]
    if not lines:
        raise EditError("There is nothing to paste: copy two columns, pin and colour.")
    sep = "\t" if "\t" in lines[0] else ";" if ";" in lines[0] and "," not in lines[0] else ","
    rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=sep))
    first = [c.strip().casefold() for c in rows[0]]
    if len(first) >= 2 and first[0] in _PIN_HEADINGS and first[1] in _COLOUR_HEADINGS:
        rows = rows[1:]
    out: dict[str, str] = {}
    for n, row in enumerate(rows, start=1):
        cells = [c.strip() for c in row]
        while len(cells) > 2 and not cells[-1]:
            cells.pop()
        if len(cells) != 2 or not cells[0] or not cells[1]:
            raise EditError(f"Row {n} does not have two cells, a pin and a colour: {sep.join(row)}")
        pin, colour = cells
        if pin in out and out[pin] != colour:
            raise EditError(f"Pin {pin} has two colours ({out[pin]} and {colour}).")
        out[pin] = colour
    if len(out) > MAX_PINS:
        raise EditError(f"A colour code has at most {MAX_PINS} pins.")
    return out


__all__ = [
    "CONFIG_NAME",
    "DEFAULT_RULE",
    "EXAMPLE_NAME",
    "MAX_NOTE_LINES",
    "parse_colour_table",
    "plan_example_code",
    "plan_settings_edit",
    "plan_values",
]
