# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The rules of a one-device file `NAME.device.json` and of the optional `library.json` of a
library folder (design of 2.2.0, `docs/ait/DESIGN_2.2_DEVICE_LIBRARY.md` section 2; D-240).

    problems = device_file_problems("PCDU00.device.json", data)   # [] when the file keeps the rules
    data = device_file_data(project, "PCDU00")                     # one device, ready to write
    info = library_info(folder)                                    # the name of the library

A `NAME.device.json` file is a device library file (`harness-device-library`, version 1, unchanged,
so a 2.1 tool reads it) that keeps more rules: it holds exactly one device, `NAME` is the ID of
that device, every connector is a box connector of the device with an ID `<device>-<tail>`, the
file is complete on its own (every part, contact part and mating part it names, and every
interface type its connectors carry, is in the file), and nothing of one project is in it (no
`interface_id`, no `locked: true`, no `zone`). Every problem is one sentence in plain words.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from harness_design_studio.core import device_library as dl
from harness_design_studio.core.errors import HarnessError
from harness_design_studio.core.io import canonical
from harness_design_studio.core.model import Connector, InterfaceType, Part, Project, Unit

__all__ = [
    "DEVICE_SUFFIX",
    "FOLDER_FORMAT",
    "FOLDER_VERSION",
    "INFO_FILE",
    "LibraryInfo",
    "LibraryInfoError",
    "check_library_info",
    "device_file_data",
    "device_file_name",
    "device_file_problems",
    "is_device_file",
    "library_info",
]

DEVICE_SUFFIX = ".device.json"
FOLDER_FORMAT = "harness-device-library-folder"
FOLDER_VERSION = 1
INFO_FILE = "library.json"
TOP_KEYS = ("format", "version", "devices", "parts", "interface_types")
INFO_KEYS = ("format", "version", "name", "description")
MAX_INFO_BYTES = 64 * 1024
MAX_NAME = 200
MAX_DESCRIPTION = 2000


class LibraryInfoError(HarnessError):
    """The `library.json` of a library folder cannot be used; the message says why."""


# ---- the file name ----------------------------------------------------------------------------


def is_device_file(file_name: str) -> bool:
    """True for a file named `NAME.device.json` (the ending compared without regard to case)."""
    return file_name.casefold().endswith(DEVICE_SUFFIX) and len(file_name) > len(DEVICE_SUFFIX)


def device_file_name(unit_id: str) -> str:
    """The file name of the device `unit_id` in a library: `PCDU00.device.json`."""
    return unit_id + DEVICE_SUFFIX


# ---- the rules of one file --------------------------------------------------------------------


def _words(exc: ValidationError) -> str:
    err = exc.errors()[0]
    where = ".".join(str(x) for x in err["loc"])
    what = str(err["msg"]).removeprefix("Value error, ")
    return f"{where}: {what}" if where else what


def device_file_problems(file_name: str, data: object) -> list[str]:
    """Why the content `data` of the file `file_name` breaks the rules of a one-device file, one
    sentence each; an empty list when it keeps them all."""
    try:
        data = dl.check_library(data)
    except dl.DeviceLibraryError as exc:
        return [str(exc)]
    name = file_name[: -len(DEVICE_SUFFIX)]
    extra = sorted(set(data) - set(TOP_KEYS))
    if extra:
        return [f"The file has the key '{extra[0]}', which a device file does not have."]
    devices = data.get("devices", [])
    if len(devices) != 1:
        return [f"A .device.json file holds exactly one device; this one holds {len(devices)}."]
    rec = devices[0]
    if set(rec) - {"unit", "connectors"}:
        key = sorted(set(rec) - {"unit", "connectors"})[0]
        return [f"The device has the key '{key}', which a device record does not have."]
    raw_conns = rec.get("connectors", [])
    if not isinstance(raw_conns, list) or len(raw_conns) > dl.MAX_CONNECTORS:
        return [f"A device holds a list of up to {dl.MAX_CONNECTORS} connectors."]
    try:
        unit = Unit.model_validate(rec.get("unit"))
        conns = [Connector.model_validate(c) for c in raw_conns]
        parts = [Part.model_validate(p) for p in data.get("parts", [])]
        types = [InterfaceType.model_validate(t) for t in data.get("interface_types", [])]
    except ValidationError as exc:
        return [f"A value of the file is not valid ({_words(exc)})."]
    if name != unit.id:
        return [
            f"The file name says {name}, but the device in it is {unit.id}; "
            f"name the file {device_file_name(unit.id)}."
        ]
    return _device_problems(unit, conns, parts, types)


def _device_problems(
    unit: Unit, conns: list[Connector], parts: list[Part], types: list[InterfaceType]
) -> list[str]:
    out: list[str] = []
    if unit.zone is not None:
        out.append(f"The device {unit.id} has a zone, which belongs to a project, not a library.")
    part_ids = {p.id for p in parts}
    type_ids = {t.id for t in types}
    seen: set[str] = set()
    for c in conns:
        if c.role != "box" or c.unit_id != unit.id:
            out.append(f"The connector {c.id} is not a box connector of the device {unit.id}.")
        if not c.id.startswith(unit.id + "-") or len(c.id) == len(unit.id) + 1:
            out.append(f"The connector ID {c.id} does not start with '{unit.id}-'.")
        if c.id.casefold() in seen:
            out.append(f"The connector ID {c.id} is in the file twice.")
        seen.add(c.id.casefold())
        if c.locked:
            out.append(f"The connector {c.id} is locked, which belongs to a project.")
        if c.part_id not in part_ids:
            out.append(f"The part {c.part_id} of the connector {c.id} is not in the file.")
        for t in c.carries:
            if t not in type_ids:
                out.append(f"The interface type {t} of the connector {c.id} is not in the file.")
        for pin in c.pins:
            if pin.interface_id is not None or pin.locked:
                out.append(
                    f"The pin {c.id} {pin.id} names an interface or a lock, "
                    "which belong to a project."
                )
            if pin.contact_part and pin.contact_part not in part_ids:
                out.append(
                    f"The contact part {pin.contact_part} of the pin {c.id} {pin.id} "
                    "is not in the file."
                )
    for p in parts:
        if p.mates_with and p.mates_with not in part_ids:
            out.append(
                f"The part {p.mates_with} that the part {p.id} mates with is not in the file."
            )
    return list(dict.fromkeys(out))


# ---- the content of a one-device file ---------------------------------------------------------


def device_file_data(project: Project, unit_id: str, new_id: str | None = None) -> dict[str, Any]:
    """The device `unit_id` of the project in the form of a one-device file (`export_devices`,
    then every connector ID `<device>-<tail>` and no lock on a pin or a connector). `new_id` saves
    it under another ID. The project is not touched."""
    nid = new_id or unit_id
    data = dl.export_devices(project, [unit_id], {unit_id: nid} if nid != unit_id else None)
    rec = data["devices"][0]
    conns = []
    for c in rec["connectors"]:
        c = dict(c)
        if not str(c["id"]).startswith(nid + "-"):
            c["id"] = f"{nid}-{dl.connector_tail(str(c['id']), unit_id)}"
        c.pop("locked", None)  # a connector's lock is left out while it is False
        c["pins"] = [{**p, "locked": False} for p in c.get("pins", [])]
        conns.append(c)
    rec["connectors"] = conns
    return data


# ---- library.json -----------------------------------------------------------------------------


@dataclass(frozen=True)
class LibraryInfo:
    """The name and description of a library. `from_file` is False when the folder has no
    `library.json`: the name is then the folder's name."""

    name: str
    description: str = ""
    from_file: bool = False


def check_library_info(data: object) -> LibraryInfo:
    """The checked content of a `library.json`: strict (no other key, the format and version
    known, a name that is not empty)."""
    if not isinstance(data, dict) or data.get("format") != FOLDER_FORMAT:
        raise LibraryInfoError(f"The file is not a library description (format '{FOLDER_FORMAT}').")
    extra = sorted(set(data) - set(INFO_KEYS))
    if extra:
        raise LibraryInfoError(f"The file has the key '{extra[0]}', which it may not have.")
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise LibraryInfoError("The file has no valid version number.")
    if version > FOLDER_VERSION:
        raise LibraryInfoError(
            f"The file is version {version}; this program reads version {FOLDER_VERSION}."
        )
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME:
        raise LibraryInfoError(f"The name must be a text of 1 to {MAX_NAME} characters.")
    description = data.get("description", "")
    if not isinstance(description, str) or len(description) > MAX_DESCRIPTION:
        raise LibraryInfoError(
            f"The description must be a text of up to {MAX_DESCRIPTION} characters."
        )
    return LibraryInfo(name.strip(), description, True)


def library_info(folder: Path | str) -> LibraryInfo:
    """The name and description of the library in `folder`: from its `library.json`, else the
    folder's name. A `library.json` that cannot be used raises `LibraryInfoError`."""
    root = Path(folder)
    path = root / INFO_FILE
    fallback = LibraryInfo(root.resolve().name or str(root))
    if path.is_symlink() or not path.is_file():
        return fallback
    try:
        if path.stat().st_size > MAX_INFO_BYTES:
            raise LibraryInfoError("The file is too large to read (limit 64 KB).")
        data = canonical.loads_strict(path.read_bytes())
    except OSError as exc:
        raise LibraryInfoError(f"The file could not be read ({exc.strerror}).") from exc
    except (ValueError, RecursionError) as exc:
        raise LibraryInfoError(dl.json_problem(exc)) from exc
    return check_library_info(data)
