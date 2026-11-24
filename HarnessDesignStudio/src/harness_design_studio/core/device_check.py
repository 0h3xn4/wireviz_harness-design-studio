# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The checked state of a device of the library (format 5, part E of
`docs/ait/DESIGN_5.0_FORMAT_5.md`, section 8; REQ-LIB-08; owner questions F12 and F13).

`Unit.checked` (`DeviceCheck`) says who checked a device, on which day, against which ICD, and
holds the SHA-256 of what was checked. **What was checked** (section 8.1) is the device's
library-owned fields, as `device_content` gathers them:

- of the device: `kind` and `mass_relevant` (`HASHED_UNIT_FIELDS`);
- of each box connector, keyed by its tail (`device_library.connector_tail`: `J01`, so that a copy
  `OBC1-R` and a renamed device read as the device they come from): `HASHED_CONNECTOR_FIELDS`;
- of each pin, keyed by its ID: `HASHED_PIN_FIELDS`, the pin as the device travels to a library
  (`device_library._portable`: a signal that Generate allocated for an interface is this project's,
  not the device's, so an allocation does not make a check stale);

connectors in the natural order of their tails and pins in the natural order of their IDs
(`ports.natural_key`), every value as the files write it (`model_dump(mode="json")`), the whole as
canonical JSON (`io.canonical.dumps`: sorted keys, an indent of 2, UTF-8, a line feed at the end).
Notes and labels are left out: a note does not change what a device is. The device's ID, name,
subsystem, zone and side are the project's, not the library's, and are left out too.

A check is set by a person only (`plan_set_device_checked`: the command `device-checked`, the
editor, `api.set_device_checked`), never by an import or Generate; the library brings the library's
check (`library_link`). It is **stale** when the hash of the device now differs from the stored one
(`check_state`); `check` then says `device_check_stale` (a warning, so `model-inconsistent` in the
DRC). The check is not cleared by a change: the record of who checked what stays, marked stale.
Anyone may mark a device checked, with a typed name (F13): no rule of different persons applies.

No clock is read here: the day comes from the caller (`--date`, else today's date, which the
command line and the editor read and store in the project as the person's statement).
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from harness_design_studio.core.commands import Op, Put
from harness_design_studio.core.device_library import _portable, connector_tail
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.io.canonical import dumps
from harness_design_studio.core.model import Connector, DeviceCheck, Project, Unit, evolve
from harness_design_studio.core.ports import natural_key

__all__ = [
    "CHANGED",
    "CHECKED",
    "HASHED_CONNECTOR_FIELDS",
    "HASHED_PIN_FIELDS",
    "HASHED_UNIT_FIELDS",
    "NOT_CHECKED",
    "CheckPlan",
    "any_checked",
    "check_state",
    "check_words",
    "checked_sha256",
    "device_content",
    "device_sha256",
    "plan_clear_device_checked",
    "plan_set_device_checked",
    "proposed_icd",
    "state_text",
]

# The library-owned fields that a check covers (section 8.1; `library_link.UNIT_FIELDS`,
# `CONNECTOR_FIELDS` and `PIN_FIELDS` without the notes, the labels and the check itself).
HASHED_UNIT_FIELDS = ("kind", "mass_relevant")
HASHED_CONNECTOR_FIELDS = (
    "name", "part_id", "gender", "keying", "carries", "row_layout", "source_doc", "source_version",
    "source_link",
)  # fmt: skip
HASHED_PIN_FIELDS = (
    "signal", "fixed", "function", "contact_size", "termination", "contact_part", "role",
    "direction", "level", "current_a",
)  # fmt: skip

# The three states of a device (section 8.5) and their words.
NOT_CHECKED = "not checked"
CHECKED = "checked"
CHANGED = "changed since the check"


def _fields(obj: Any, names: Sequence[str]) -> dict[str, Any]:
    dumped = obj.model_dump(mode="json")
    return {name: dumped.get(name) for name in names}


def device_content(unit: Unit, connectors: Sequence[Connector]) -> dict[str, Any]:
    """What a check of the device covers (section 8.1), as plain JSON values: the device's
    `kind` and `mass_relevant`; each box connector by its tail, with its fields and its pins (each
    pin as the device travels to a library). `connectors` are the box connectors of `unit`."""
    conns = []
    for c in connectors:
        pins = [{"id": p.id, **_fields(_portable(p), HASHED_PIN_FIELDS)} for p in c.pins]
        pins.sort(key=lambda d: natural_key(str(d["id"])))
        conns.append(
            {
                "tail": connector_tail(c.id, unit.id),
                **_fields(c, HASHED_CONNECTOR_FIELDS),
                "pins": pins,
            }  # fmt: skip
        )
    conns.sort(key=lambda d: natural_key(str(d["tail"])))
    return {"unit": _fields(unit, HASHED_UNIT_FIELDS), "connectors": conns}


def device_sha256(unit: Unit, connectors: Sequence[Connector]) -> str:
    """The SHA-256 of `device_content` as canonical JSON, 64 hexadecimal characters."""
    return hashlib.sha256(dumps(device_content(unit, connectors))).hexdigest()


def _box_connectors(project: Project, unit_id: str) -> list[Connector]:
    return [c for c in project.connectors.values() if c.unit_id == unit_id]


def checked_sha256(project: Project, unit_id: str) -> str:
    """The SHA-256 of what a check of the device `unit_id` of the project covers now."""
    return device_sha256(project.units[unit_id], _box_connectors(project, unit_id))


def any_checked(project: Project) -> bool:
    """Whether some device of the project has a check (the Review rows are shown only then)."""
    return any(u.checked is not None for u in project.units.values())


def check_state(project: Project, unit_id: str) -> str:
    """`NOT_CHECKED`, `CHECKED` (the device is what was checked) or `CHANGED` (it changed since)."""
    check = project.units[unit_id].checked
    if check is None:
        return NOT_CHECKED
    return CHECKED if check.sha256 == checked_sha256(project, unit_id) else CHANGED


def check_words(check: DeviceCheck | None) -> str:
    """A check in a few words, as `update-device` shows it: *A. Example, 2026-11-23, ICD-TTC Issue
    3*; empty for none."""
    if check is None:
        return ""
    return f"{check.by}, {check.on}, {check.icd}"


def state_text(check: DeviceCheck | None, state: str) -> str:
    """The sentence of the Devices tab, the Library window and the Review sheet (section 8.5):
    *Checked by A. Example on 2026-11-23 against ICD-TTC Issue 3*, with *; changed since the check*
    when it is stale, or *not checked*."""
    if check is None or state == NOT_CHECKED:
        return NOT_CHECKED
    text = f"Checked by {check.by} on {check.on} against {check.icd}"
    return f"{text}; {CHANGED}" if state == CHANGED else text


def proposed_icd(project: Project, unit_id: str) -> str | None:
    """The ICD the box connectors of the device name, while every one of them names the same ICD
    and version (`source_doc` and `source_version` both set): *ICD-TTC Issue 3*. None otherwise,
    and for a device without a connector."""
    found = {(c.source_doc, c.source_version) for c in _box_connectors(project, unit_id)}
    if len(found) != 1:
        return None
    doc, version = next(iter(found))
    if not doc or not version:
        return None
    return f"{doc} {version}"


@dataclass(frozen=True)
class CheckPlan:
    """The ops that mark a device checked (one `Put` of the unit, none when it holds this very
    check), the check, and whether the ICD was taken from its connectors (`proposed`)."""

    ops: list[Op]
    check: DeviceCheck
    proposed: bool


def _unit(project: Project, unit_id: str) -> Unit:
    unit = project.units.get(unit_id)
    if unit is None:
        raise EditError(f"There is no device {unit_id} in this project.")
    return unit


def plan_set_device_checked(
    project: Project, unit_id: str, *, by: str, on: str, icd: str | None = None
) -> CheckPlan:
    """Mark the device `unit_id` checked by `by` on `on` (YYYY-MM-DD) against `icd`, with the
    SHA-256 of what it is now (section 8.2). Without `icd` the ICD its connectors name is taken
    (`proposed_icd`); when they name none or several, it is refused. A released harness does not
    lock the check (`vcs.locks.COSMETIC_UNIT_FIELDS`). Refusals raise `EditError`."""
    unit = _unit(project, unit_id)
    who = by.strip()
    if not who:
        raise EditError(f"Say who checked {unit_id}: a name.")
    proposed = False
    if icd is None or not icd.strip():
        icd = proposed_icd(project, unit_id)
        if icd is None:
            raise EditError(
                f"The connectors of {unit_id} do not name one ICD and version (source_doc and "
                "source_version), so name the ICD it was checked against."
            )
        proposed = True
    try:
        check = DeviceCheck(
            by=who, on=on.strip(), icd=icd.strip(), sha256=checked_sha256(project, unit_id)
        )
    except ValidationError as exc:
        problem = exc.errors()[0]
        field = ".".join(str(x) for x in problem.get("loc", ())) or "check"
        words = {"by": "The name", "on": "The date", "icd": "The ICD"}.get(field, field)
        raise EditError(f"{words} cannot be used: {problem.get('msg', '')}.") from None
    if unit.checked == check:
        return CheckPlan([], check, proposed)
    return CheckPlan([Put("units", evolve(unit, checked=check))], check, proposed)


def plan_clear_device_checked(project: Project, unit_id: str) -> list[Op]:
    """Ops that clear the check of the device (*not checked*); none when it has none."""
    unit = _unit(project, unit_id)
    if unit.checked is None:
        return []
    return [Put("units", evolve(unit, checked=None))]
