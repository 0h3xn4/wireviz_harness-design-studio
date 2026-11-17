# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The library folder: a folder that anyone points the tool at (a shared drive, a Git checkout)
and that holds device library files and subsystem library files (workshop feedback M4, D-175).

    scan = scan_folder(Path("/mnt/shared/harness-library"))
    for e in scan.entries: print(e.kind, e.name, e.file)
    data = load_entry(scan.folder, scan.entries[0])             # re-read from disk
    paths = save_devices(folder, project, ["OBC1"])            # only when the person says so
    path = save_subsystem(folder, project, ["OBC1", "RW1"], "Wheel drive")

The tool is offline: this is plain file reading, never a network call. Sharing is the job of the
drive or the repository around the folder. The folder is only read, except by `save_devices` and
`save_subsystem`, which the person starts with *Save to library*. A file that cannot be read does
not stop the others: it is listed in `LibraryScan.problems` with a plain sentence. A file whose JSON
is not one of the two library formats (a `package.json` next to them) is skipped without a word.

Since 2.2.0 (D-240) a device is saved in a file of its own, `NAME.device.json`, which keeps the
rules of `core/device_file.py`; the multi-device files of 2.1 are still offered. Across the folder,
a device ID in two files is offered from neither (the message names both files), two device files
of the same name (in two folders, or differing only in case) are both refused, because a project
records where a device came from by the file name, and a part with different data in two files is
a warning that names the fields. An optional `library.json` gives the library its name.
"""

import os
import stat
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import ValidationError

from harness_design_studio.core import device_file as df
from harness_design_studio.core import device_library as dl
from harness_design_studio.core import subsystem_library as sl
from harness_design_studio.core.device_library import DeviceConflict, LibraryConflict
from harness_design_studio.core.errors import HarnessError
from harness_design_studio.core.io import canonical
from harness_design_studio.core.model import Part, Project

__all__ = [
    "DeviceConflict",
    "LibraryConflict",
    "LibraryEntry",
    "LibraryError",
    "LibraryProblem",
    "LibraryScan",
    "describe_entry",
    "load_entry",
    "save_devices",
    "save_targets",
    "save_subsystem",
    "scan_folder",
]

MAX_FILES = 2000  # JSON files looked at in one folder
MAX_DEPTH = 3  # folders below the library folder that are looked into

Kind = Literal["device", "subsystem"]


class LibraryError(HarnessError):
    """The library folder or a request to it cannot be used; the message says why."""


@dataclass(frozen=True)
class LibraryEntry:
    """One thing the library offers: a device of a device file, or the subsystem of a subsystem
    file. `file` is the path inside the library folder (with `/`)."""

    kind: Kind
    key: str  # unique in a scan
    id: str  # the device ID in the file; empty for a subsystem
    name: str
    description: str
    file: str
    devices: int = 1
    connectors: int = 0
    pins: int = 0
    connections: int = 0
    subsystem: str = ""  # the subsystem a device was saved with, for the search


@dataclass(frozen=True)
class LibraryProblem:
    file: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}: {self.message}"


@dataclass
class LibraryScan:
    folder: Path
    entries: list[LibraryEntry] = field(default_factory=list)
    problems: list[LibraryProblem] = field(default_factory=list)
    error: str = ""  # the folder itself cannot be used: why, in plain words
    skipped: int = 0  # JSON files that are not library files
    warnings: list[LibraryProblem] = field(default_factory=list)  # offered all the same
    name: str = ""  # the library's name: from library.json, else the folder's name
    description: str = ""
    # every device ID of a device file (compared without regard to case) -> the files that hold
    # it, the ones refused for holding it twice included
    holders: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _folder_problem(folder: Path) -> str:
    try:
        info = folder.stat()
    except FileNotFoundError:
        return f"The folder {folder} does not exist. Is the drive connected?"
    except PermissionError:
        return f"You may not open the folder {folder}."
    except OSError as exc:
        return f"The folder {folder} could not be opened ({exc.strerror})."
    if not stat.S_ISDIR(info.st_mode):
        return f"{folder} is not a folder."
    if not os.access(folder, os.R_OK | os.X_OK):
        return f"You may not read the folder {folder}."
    return ""


def _json_files(folder: Path) -> tuple[list[Path], str]:
    """The `.json` files in the folder and in the folders below it (hidden folders such as `.git`
    and links are not followed), sorted by path; and a sentence when the list was cut short."""
    found: list[Path] = []
    cut = ""

    def walk(here: Path, depth: int) -> None:
        nonlocal cut
        try:
            names = sorted(os.listdir(here), key=str.casefold)
        except OSError:
            return
        for name in names:
            if len(found) >= MAX_FILES:
                cut = f"Only the first {MAX_FILES} files were looked at."
                return
            path = here / name
            if name.startswith(".") or path.is_symlink():
                continue
            if path.is_dir():
                if depth < MAX_DEPTH:
                    walk(path, depth + 1)
            elif name.casefold().endswith(".json") and path.is_file():
                found.append(path)

    walk(folder, 1)
    return found, cut


@dataclass
class _DeviceFile:
    """A device file that gave entries, kept for the checks across the folder."""

    rel: str
    ids: list[str]
    parts: list[dict[str, Any]]


def scan_folder(folder: Path | str) -> LibraryScan:
    """Everything the library folder offers. Never raises: a folder that cannot be used gives a
    scan with `error` set; a file that cannot be used gives an entry in `problems`."""
    root = Path(folder)
    scan = LibraryScan(root)
    scan.name = root.name or str(root)
    scan.error = _folder_problem(root)
    if scan.error:
        return scan
    files, cut = _json_files(root)
    if cut:
        scan.problems.append(LibraryProblem(".", cut))
    found: list[_DeviceFile] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            _scan_file(scan, path, rel, found)
        except HarnessError as exc:
            scan.problems.append(LibraryProblem(rel, str(exc)))
        except (OSError, ValueError, UnicodeError, RecursionError) as exc:
            scan.problems.append(LibraryProblem(rel, _read_words(exc)))
        except Exception:  # noqa: BLE001  (a promise: one bad file never hides the good ones)
            scan.problems.append(LibraryProblem(rel, "The file has a form that cannot be read."))
    _across_files(scan, found)
    scan.entries.sort(key=lambda e: (e.kind, e.name.casefold(), e.id.casefold(), e.file))
    return scan


def _scan_file(scan: LibraryScan, path: Path, rel: str, found: list[_DeviceFile]) -> None:
    """Read one file (once) and add its entries, its skip or its problems to the scan."""
    data = _read_json(path)
    fmt = data.get("format") if isinstance(data, dict) else None
    if rel == df.INFO_FILE and fmt == df.FOLDER_FORMAT:
        info = df.check_library_info(data)
        scan.name, scan.description = info.name, info.description
    elif df.is_device_file(path.name):
        if fmt != dl.FORMAT:
            raise LibraryError(
                f"A file named NAME{df.DEVICE_SUFFIX} must be a device library file "
                f"(format '{dl.FORMAT}')."
            )
        rules = df.device_file_problems(path.name, data)
        if rules:
            scan.problems += [LibraryProblem(rel, text) for text in rules]
            return
        _add_device_file(scan, rel, data, found)
    elif fmt == dl.FORMAT:
        _add_device_file(scan, rel, data, found)
    elif fmt == sl.FORMAT:
        scan.entries.append(_subsystem_entry(rel, sl.check_subsystem(data)))
    else:
        scan.skipped += 1


def _add_device_file(scan: LibraryScan, rel: str, data: object, found: list[_DeviceFile]) -> None:
    entries, problems = _device_entries(rel, dl.check_library(data))
    scan.entries += entries
    scan.problems += [LibraryProblem(rel, text) for text in problems]
    parts = data.get("parts", []) if isinstance(data, dict) else []
    found.append(_DeviceFile(rel, [e.id for e in entries], parts))


# ---- the checks across the folder -------------------------------------------------------------


def _others(rels: list[str], rel: str) -> str:
    return ", ".join(r for r in rels if r != rel)


def _across_files(scan: LibraryScan, found: list[_DeviceFile]) -> None:
    """A device ID in two files, a file name twice, a part that differs between files."""
    by_name: dict[str, list[str]] = {}
    by_id: dict[str, list[str]] = {}
    for f in found:
        by_name.setdefault(PurePosixPath(f.rel).name.casefold(), []).append(f.rel)
        for uid in f.ids:
            by_id.setdefault(uid.casefold(), []).append(f.rel)
    scan.holders = {k: tuple(v) for k, v in sorted(by_id.items())}
    refused_files: set[str] = set()
    for rels in by_name.values():
        if len(rels) > 1:
            for rel in rels:
                refused_files.add(rel)
                scan.problems.append(
                    LibraryProblem(
                        rel,
                        f"Another device file has the same name ({_others(rels, rel)}), and a "
                        "project records where a device came from by the file name; neither "
                        "file is offered until one of them is renamed.",
                    )
                )
    refused_ids: set[str] = set()
    for key, rels in by_id.items():
        if len(rels) > 1:
            refused_ids.add(key)
            uid = next(e.id for e in scan.entries if e.id.casefold() == key)
            for rel in rels:
                scan.problems.append(
                    LibraryProblem(
                        rel,
                        f"The device {uid} is also in {_others(rels, rel)}, so it is offered "
                        "from neither file; keep it in one file only.",
                    )
                )
    scan.entries = [
        e
        for e in scan.entries
        if e.kind != "device"
        or (e.file not in refused_files and e.id.casefold() not in refused_ids)
    ]
    scan.warnings += _part_warnings(found)


def _part_form(rec: dict[str, Any]) -> dict[str, Any]:
    """A part record as the model writes it, so that two forms of the same data compare equal."""
    try:
        return Part.model_validate(rec).model_dump(mode="json")
    except ValidationError, ValueError:
        return rec


def _part_warnings(found: list[_DeviceFile]) -> list[LibraryProblem]:
    first: dict[str, tuple[str, dict[str, Any]]] = {}
    out: list[LibraryProblem] = []
    for f in found:
        for rec in f.parts:
            if not isinstance(rec, dict) or not isinstance(rec.get("id"), str):
                continue
            pid, form = rec["id"], _part_form(rec)
            if pid not in first:
                first[pid] = (f.rel, form)
                continue
            where, other = first[pid]
            fields = sorted(k for k in set(form) | set(other) if form.get(k) != other.get(k))
            if fields:
                out.append(
                    LibraryProblem(
                        f.rel,
                        f"The part {pid} differs from the one in {where} in "
                        f"{', '.join(fields)}; a project keeps the part it has.",
                    )
                )
    return out


def _read_words(exc: Exception) -> str:
    if isinstance(exc, OSError):
        return f"The file could not be read ({exc.strerror})."
    return dl.json_problem(exc)


def _read_json(path: Path) -> Any:
    """The content of a JSON file: strict (a key twice is refused), size checked."""
    info = path.stat()
    if info.st_size > dl.MAX_BYTES:
        raise LibraryError("The file is too large to read (limit 8 MB).")
    return canonical.loads_strict(path.read_bytes())


def _device_entries(rel: str, data: dict[str, Any]) -> tuple[list[LibraryEntry], list[str]]:
    """(the devices of a checked device file, a sentence for each device that cannot be listed)."""
    out: list[LibraryEntry] = []
    problems: list[str] = []
    seen: set[str] = set()
    for rec in data.get("devices", []):
        unit = rec.get("unit", {}) if isinstance(rec, dict) else {}
        if not isinstance(unit, dict) or not unit.get("id"):
            problems.append("A device of the file has no usable 'unit' record with an ID.")
            continue
        uid = str(unit["id"])
        bad = dl.record_problem(rec)
        if bad:
            problems.append(f"The device {uid} is not listed: {bad}")
            continue
        if uid in seen:
            problems.append(f"The device {uid} is in the file twice; only the first is listed.")
            continue
        seen.add(uid)
        conns = rec.get("connectors", [])
        out.append(
            LibraryEntry(
                "device",
                f"{rel}#{uid}",
                uid,
                str(unit.get("name", uid)),
                str(unit.get("notes", "")),
                rel,
                1,
                len(conns),
                sum(len(c.get("pins", [])) for c in conns),
                0,
                str(unit.get("subsystem", "")),
            )
        )
    return out, problems


def _subsystem_entry(rel: str, data: dict[str, Any]) -> LibraryEntry:
    n_dev, n_conn, n_links = sl.subsystem_summary(data)
    pins = sum(
        len(c.get("pins", []))
        for d in data.get("devices", [])
        for c in d.get("connectors", [])
        if isinstance(c, dict)
    )
    return LibraryEntry(
        "subsystem",
        rel,
        "",
        str(data["name"]).strip(),
        str(data.get("description", "")),
        rel,
        n_dev,
        n_conn,
        pins,
        n_links,
    )


def load_entry(folder: Path | str, entry: LibraryEntry) -> dict[str, Any]:
    """The checked data of the file an entry came from, read again from the disk."""
    path = Path(folder) / entry.file
    if entry.kind == "device":
        return dl.read_library(path)
    return sl.read_subsystem(path)


# ---- the preview ------------------------------------------------------------------------------


def _records(value: object) -> list[dict[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def describe_entry(data: dict[str, Any], entry: LibraryEntry) -> list[dict[str, str]]:
    """Rows for the preview of an entry. A device gives one row for each pin (connector, pin,
    signal, function); a subsystem gives one row for each device and for each connection (kind,
    item, detail). Plain strings, so a table can show them as they are. A record of a form that
    is not expected is left out, never an error."""
    if entry.kind == "device":
        return _device_rows(data, entry.id)
    rows: list[dict[str, str]] = []
    for rec in _records(data.get("devices", [])):
        unit = rec.get("unit", {})
        unit = unit if isinstance(unit, dict) else {}
        conns = _records(rec.get("connectors", []))
        rows.append(
            {
                "kind": "Device",
                "item": f"{unit.get('id', '')}  {unit.get('name', '')}".strip(),
                "detail": f"{len(conns)} connector(s), "
                f"{sum(len(_records(c.get('pins', []))) for c in conns)} pin(s)",
            }
        )
    for rec in _records(data.get("connections", [])):
        n = len(_records(rec.get("pairs", [])))
        rows.append(
            {
                "kind": "Connection",
                "item": f"{rec.get('a_connector', '')} - {rec.get('b_connector', '')}",
                "detail": f"{n} pair(s) of pins" + (f", {rec['name']}" if rec.get("name") else ""),
            }
        )
    return rows


def _device_rows(data: dict[str, Any], unit_id: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for rec in _records(data.get("devices", [])):
        unit = rec.get("unit", {})
        if not isinstance(unit, dict) or unit.get("id") != unit_id:
            continue
        for c in _records(rec.get("connectors", [])):
            pins = _records(c.get("pins", []))
            if not pins:
                rows.append(
                    {
                        "connector": str(c.get("name", c.get("id", ""))),
                        "pin": "",
                        "signal": "",
                        "function": "",
                    }
                )
            for p in pins:
                rows.append(
                    {
                        "connector": str(c.get("name", c.get("id", ""))),
                        "pin": str(p.get("id", "")),
                        "signal": str(p.get("signal") or ""),
                        "function": str(p.get("function") or ""),
                    }
                )
    return rows


# ---- saving (only when the person asks) ------------------------------------------------------


def _writable_folder(folder: Path) -> None:
    problem = _folder_problem(folder)
    if problem:
        raise LibraryError(problem)
    if not os.access(folder, os.W_OK):
        raise LibraryError(f"You may not write in the folder {folder}. Ask who owns the library.")


def save_targets(scan: LibraryScan | None, unit_ids: list[str]) -> list[str]:
    """The file (inside the library folder, with `/`) that each device is saved into: the device
    file that holds it already, else `<ID>.device.json` at the root of the folder."""
    out = []
    for uid in unit_ids:
        holders = scan.holders.get(uid.casefold(), ()) if scan is not None else ()
        out.append(holders[0] if len(holders) == 1 else df.device_file_name(uid))
    return out


def save_devices(
    folder: Path | str,
    project: Project,
    unit_ids: list[str],
    *,
    replace: bool = False,
    new_ids: dict[str, str] | None = None,
    notes: list[str] | None = None,
) -> list[Path]:
    """Save each device into the device file of the folder that holds it already, else into a
    file of its own, `<ID>.device.json` (D-240). A device with the same ID in that file that
    differs is not replaced: `LibraryConflict` says which and how much differs (`replace=True`
    replaces it, `new_ids={"GYRO1": "GYRO1-2"}` saves it under another ID). A part never gets a
    lower approval than the file has; what was kept is added to `notes`. All or nothing: a problem
    with one device writes no file. Returns the paths written, in the order of `unit_ids`."""
    root = Path(folder)
    _writable_folder(root)
    if not unit_ids:
        raise LibraryError("Choose at least one device.")
    scan = scan_folder(root)
    names = {uid: (new_ids or {}).get(uid, uid) for uid in dict.fromkeys(unit_ids)}
    by_file: dict[str, list[str]] = {}
    for uid, nid in names.items():
        holders = scan.holders.get(nid.casefold(), ())
        if len(holders) > 1:
            raise LibraryError(
                f"{nid} is in more than one file of the library ({', '.join(holders)}); keep it "
                "in one file only, then save again. Nothing was saved."
            )
        by_file.setdefault(save_targets(scan, [nid])[0], []).append(uid)
    writes: list[tuple[Path, dict[str, Any]]] = []
    conflicts: list[tuple[str, dl.DeviceConflict]] = []
    kept: list[str] = []
    for rel, uids in by_file.items():
        target = root / rel
        if df.is_device_file(target.name) and len(uids) > 1:
            raise LibraryError(f"{', '.join(uids)} would all be saved in {rel}. Nothing was saved.")
        if df.is_device_file(target.name):
            data = df.device_file_data(project, uids[0], names[uids[0]])
        else:
            data = dl.export_devices(project, uids, {u: names[u] for u in uids})
        existing = dl.read_library(target) if target.exists() else None
        conflicts += [(rel, c) for c in dl.find_conflicts(existing, data)]
        merged, notes_here = dl.merge_with_notes(existing, data, replace=replace)
        if df.is_device_file(target.name):
            problems = df.device_file_problems(target.name, merged)
            if problems:
                raise LibraryError(f"{rel} cannot be written as a device file: {problems[0]}")
        writes.append((target, merged))
        kept += notes_here
    if conflicts and not replace:
        raise _conflict(scan, names, conflicts)
    for target, merged in writes:
        dl.write_library(target, merged)
    if notes is not None:
        notes.extend(kept)
    return [root / rel for rel in by_file]


def _conflict(
    scan: LibraryScan, names: dict[str, str], found: list[tuple[str, dl.DeviceConflict]]
) -> LibraryConflict:
    """One `LibraryConflict` for all files, with a suggested ID that is free in the whole folder."""
    taken = set(scan.holders) | {n.casefold() for n in names.values()}
    out = []
    for _rel, c in found:
        free = dl._free_id(c.unit_id, taken)
        taken.add(free.casefold())
        out.append(replace(c, suggested_id=free))
    files = list(dict.fromkeys(rel for rel, _c in found))
    return LibraryConflict(", ".join(files), out)


def save_subsystem(
    folder: Path | str,
    project: Project,
    unit_ids: list[str],
    name: str,
    description: str = "",
    notes: str = "",
) -> Path:
    """Write a subsystem library file in the folder. A file that exists is never replaced: the
    name must be a new one. Returns the path."""
    root = Path(folder)
    _writable_folder(root)
    data = sl.export_subsystem(project, unit_ids, name, description, notes)
    path = root / sl.default_file_name(name)
    if path.exists():
        raise LibraryError(
            f"The library has a subsystem file {path.name} already. Choose another name, "
            "or delete that file if it is out of date."
        )
    sl.write_subsystem(path, data)
    return path
