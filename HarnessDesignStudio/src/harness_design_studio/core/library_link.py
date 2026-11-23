# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The link between a project device and the device library (design of 2.2.0,
`docs/ait/DESIGN_2.2_DEVICE_LIBRARY.md` sections 3 and 4; D-240).

    libs = project_libraries(project_folder)                    # the libraries the project names
    link_state(project, libs, "PCDU00").state      # "up to date", "library changed" ...
    add = plan_add_device(project, libs, "PCDU00", count=2, root=project_folder)
    History(project).execute(add.label, add.ops)   # one undo step, the record with it
    diff = library_diff(project, libs, "PCDU00")                  # the rows and the impacts
    update = plan_update_device(project, libs, "PCDU00", root=project_folder)
    saved = plan_save_device(project, libs.libraries[0], "PCDU00", root=project_folder)

**The link** needs no new field: a project device follows the library device `D` when the
project holds the import record `devices:<file name>` (kind `devices`), that file holds `D` in one
of the project's libraries, and the device's ID is `D` or a copy of it (`D-R`, `D-3` ...,
`core/copies.py`). A device added under another ID is an unlinked copy and gets no record. The
record's `sha256` is the version of the file; its `notes` hold fixed-form lines that the program
never reads back (`record_notes`).

**Library-owned** are the connectors with their pins in portable form (`device_library._portable`)
and the device's `kind`, `mass_relevant` and `notes`; **project-owned** (never a difference) are
the name, subsystem, zone, side, the placement, and on each pin `interface_id`, `locked` and an
allocated signal (a pin that is not fixed and carries an interface or a lock).

Everything here is pure except `plan_save_device`, which writes one device file into the library
folder (through `library_folder.save_devices`) and returns the operation that records it. Every
other function only reads the library folders and returns operations for `History.execute`;
nothing is applied here, and the same files and project give the same operations.
"""

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import ValidationError

from harness_design_studio import __version__
from harness_design_studio.core import copies, devices
from harness_design_studio.core import device_file as df
from harness_design_studio.core import device_library as dl
from harness_design_studio.core import library_folder as lf
from harness_design_studio.core.commands import History, Op, Put
from harness_design_studio.core.device_check import check_words
from harness_design_studio.core.edit import EditError, clone_with
from harness_design_studio.core.errors import HarnessError, TransactionError
from harness_design_studio.core.ids import ID_RE
from harness_design_studio.core.import_record import clean, project_relative, record_ops
from harness_design_studio.core.io import canonical
from harness_design_studio.core.library_git import (
    NOT_COMMITTED,
    NOT_READABLE,
    file_state,
    library_git,
)
from harness_design_studio.core.library_pointer import PointerError, library_folders, read_pointer
from harness_design_studio.core.model import (
    Connector,
    DeviceCheck,
    ImportRecord,
    InterfaceType,
    Part,
    Pin,
    Project,
    RowLayout,
    Unit,
    evolve,
)
from harness_design_studio.core.model.imports import record_id
from harness_design_studio.core.ports import natural_key
from harness_design_studio.core.row_layout import layout_text
from harness_design_studio.core.subsystem_library import with_placements
from harness_design_studio.core.vcs.locks import COSMETIC_UNIT_FIELDS, unit_design
from harness_design_studio.core.vcs.lockview import (
    LOCKED_CONNECTOR_FIELDS,
    lock_reason,
    locked_objects,
)

__all__ = [
    "AMBIGUOUS",
    "CHANGED_HERE",
    "LIBRARY_CHANGED",
    "LINKED_STATES",
    "NOT_FROM_LIBRARY",
    "NOT_IN_PROJECT",
    "SOURCE_NOT_FOUND",
    "STATES",
    "UP_TO_DATE",
    "AddPlan",
    "AmbiguousDeviceError",
    "DeviceSource",
    "DiffRow",
    "Library",
    "LibraryDevice",
    "LibraryDiff",
    "LinkError",
    "LinkState",
    "ProjectLibraries",
    "SavePlan",
    "TakenIdError",
    "UpdatePlan",
    "device_record",
    "file_library",
    "libraries_from_scan",
    "library_diff",
    "link_state",
    "link_states",
    "located_sources",
    "open_libraries",
    "plan_add_device",
    "plan_add_devices",
    "plan_save_device",
    "plan_update_device",
    "project_libraries",
    "read_device",
    "record_notes",
]

# ---- the states (design section 3) ------------------------------------------------------------

NOT_IN_PROJECT = "not in project"
UP_TO_DATE = "up to date"
LIBRARY_CHANGED = "library changed"
CHANGED_HERE = "changed here"
NOT_FROM_LIBRARY = "same ID, not from the library"
SOURCE_NOT_FOUND = "source not found"
AMBIGUOUS = "in more than one library"
STATES = (
    NOT_IN_PROJECT, UP_TO_DATE, LIBRARY_CHANGED, CHANGED_HERE, NOT_FROM_LIBRARY, SOURCE_NOT_FOUND,
    AMBIGUOUS,
)  # fmt: skip
LINKED_STATES = frozenset({UP_TO_DATE, LIBRARY_CHANGED, CHANGED_HERE})

KIND: Literal["devices"] = "devices"
# `checked` (format 5, design of 5.0.0 sections 8.4 and 9): the library holds the check of a
# device, so the diff shows it (*A. Example, 2026-11-23, ICD-TTC Issue 3*) and `--apply` takes the
# library's, its *not checked* too.
UNIT_FIELDS = ("kind", "mass_relevant", "notes", "checked")
# `row_layout` (format 4): a box connector's own rows are library-owned, and a difference shows in
# the diff like any other field (design of 4.0.0 section 5.5), in the short text form. The ICD a
# connector came from (`source_doc`, `source_version`, `source_link`) and the level of a pin
# (format 3) are library-owned too (4.4.1, design of 5.0.0 part F): a new ICD issue is a change.
# So is the current of a pin (format 5, design of 5.0.0 section 5.1).
CONNECTOR_FIELDS = (
    "name", "part_id", "gender", "keying", "carries", "notes", "label", "row_layout",
    "source_doc", "source_version", "source_link",
)  # fmt: skip
PIN_FIELDS = (
    "signal", "fixed", "function", "contact_size", "termination", "contact_part", "role",
    "direction", "level", "current_a",
)  # fmt: skip
# The order of the rows of one connector or pin: its own fields first, then the pin's (20 and on).
_FIELD_ORDER = {f: k for k, f in enumerate(("connector", "pin", *UNIT_FIELDS, *CONNECTOR_FIELDS))}
_FIELD_ORDER.update({f: 20 + k for k, f in enumerate(PIN_FIELDS)})


class LinkError(HarnessError):
    """A library device cannot be added, compared, updated or saved; the message says why."""


class AmbiguousDeviceError(LinkError):
    """A device ID is in more than one library of the project; the message names both."""


class TakenIdError(LinkError):
    """The project has a device with the ID of the library device. `linked`: it follows the
    library already (give a number of devices for copies); else it does not, and `rows` are the
    differences: adopt it (`plan_update_device(..., adopt=True)`) or add under `free_id`."""

    def __init__(
        self, message: str, unit_id: str, linked: bool, free_id: str, rows: tuple[DiffRow, ...]
    ) -> None:
        super().__init__(message)
        self.unit_id, self.linked, self.free_id, self.rows = unit_id, linked, free_id, rows


# ---- the libraries of a project ---------------------------------------------------------------


@dataclass(frozen=True)
class Library:
    """A library folder and its name (from its `library.json`, else the folder's name)."""

    folder: Path
    name: str


@dataclass(frozen=True)
class LibraryDevice:
    """A device of a library: its ID and name, and the file that holds it (inside the library
    folder, with `/`)."""

    library: Library
    unit_id: str
    name: str
    file: str

    @property
    def file_name(self) -> str:
        return PurePosixPath(self.file).name

    @property
    def path(self) -> Path:
        return self.library.folder / self.file

    @property
    def record_id(self) -> str:
        """The ID of the import record that links a project device to this file."""
        return record_id(KIND, clean(self.file_name, 150))


@dataclass
class ProjectLibraries:
    """The libraries of a project in their order, and their devices by ID. `problems` are the
    sentences of what could not be used (a pointer file, a folder, a file of a folder)."""

    libraries: list[Library] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    root: Path | None = None
    _by_id: dict[str, list[LibraryDevice]] = field(default_factory=dict, repr=False)

    def add(self, library: Library, entries: Iterable[lf.LibraryEntry]) -> None:
        self.libraries.append(library)
        for e in entries:
            if e.kind == "device":
                dev = LibraryDevice(library, e.id, e.name, e.file)
                self._by_id.setdefault(e.id.casefold(), []).append(dev)

    def devices(self) -> list[LibraryDevice]:
        """Every device of every library, sorted by ID (then library order)."""
        out = [d for found in self._by_id.values() for d in found]
        order = {id(lib): k for k, lib in enumerate(self.libraries)}
        return sorted(out, key=lambda d: (natural_key(d.unit_id), order.get(id(d.library), 0)))

    def holders(self, unit_id: str) -> list[LibraryDevice]:
        """The library devices whose ID is exactly `unit_id`, in library order."""
        return [d for d in self._by_id.get(unit_id.casefold(), []) if d.unit_id == unit_id]

    def device(self, unit_id: str) -> LibraryDevice | None:
        """The library device `unit_id`; None when no library holds it. A device in two libraries
        raises `AmbiguousDeviceError`: it is never chosen."""
        found = self.holders(unit_id)
        if len(found) > 1:
            where = ", ".join(f"{d.library.name} ({d.file})" for d in found)
            raise AmbiguousDeviceError(
                f"{unit_id} is in more than one library of this project: {where}. Keep it in one "
                "library only, or name only one of them for this project."
            )
        return found[0] if found else None

    def _one(self, unit_id: str) -> LibraryDevice:
        dev = self.device(unit_id)
        if dev is None:  # pragma: no cover - the caller has seen it
            raise LinkError(f"No library of this project holds {unit_id}.")
        return dev

    def resolve(self, name: str) -> LibraryDevice:
        """The library device that `name` means: its ID, else the same ID in another case, else a
        unique `unit.name` (the case does not count)."""
        if self.holders(name):
            return self._one(name)
        key = name.casefold()
        ids = sorted({d.unit_id for d in self._by_id.get(key, [])})
        if not ids:
            everyone = [d for found in self._by_id.values() for d in found]
            ids = sorted({d.unit_id for d in everyone if d.name.casefold() == key})
        if len(ids) > 1:
            raise LinkError(
                f"'{name}' fits more than one library device ({', '.join(ids)}); "
                "give the device ID."
            )
        if ids:
            return self._one(ids[0])
        if not self.libraries:
            raise LinkError("This project names no device library, so there is nothing to add.")
        raise LinkError(f"No library of this project holds a device '{name}' (by ID or by name).")

    def files_named(self, file_name: str) -> list[Path]:
        """The device files of every library with this file name, without repeats."""
        out = {d.path for found in self._by_id.values() for d in found if d.file_name == file_name}
        return sorted(out)


def _library_of(folder: Path, scan: lf.LibraryScan) -> Library:
    return Library(folder, scan.name or folder.name or str(folder))


def libraries_from_scan(scan: lf.LibraryScan, root: Path | str | None = None) -> ProjectLibraries:
    """One library from a scan made already (the editor's library window has one)."""
    libs = ProjectLibraries(root=Path(root) if root is not None else None)
    _add_scan(libs, scan.folder, scan)
    return libs


def _add_scan(libs: ProjectLibraries, folder: Path, scan: lf.LibraryScan) -> None:
    if scan.error:
        libs.problems.append(scan.error)
        return
    libs.problems += [f"{folder.name}: {p}" for p in scan.problems]
    libs.add(_library_of(folder, scan), scan.entries)


def open_libraries(
    folders: Sequence[Path | str], root: Path | str | None = None
) -> ProjectLibraries:
    """The libraries in these folders, in this order (a folder named twice is read once)."""
    libs = ProjectLibraries(root=Path(root) if root is not None else None)
    seen: set[Path] = set()
    for f in folders:
        folder = Path(f)
        key = folder.resolve()
        if key in seen:
            continue
        seen.add(key)
        _add_scan(libs, folder, lf.scan_folder(folder))
    return libs


def project_libraries(
    project_folder: Path | str | None,
    folders: Sequence[Path | str] | None = None,
    person_folder: Path | str | None = None,
) -> ProjectLibraries:
    """The device libraries of a project, in the order of design section 2: the `folders` the
    caller names (the command line's `--library`), which replace the rest; else the libraries of
    the project's `device-libraries.json`; else, when the project names none, `person_folder` (the
    editor passes the person's library folder; the command line never does). A pointer file that
    cannot be used is a problem, and the person's folder is then not used either."""
    root = Path(project_folder) if project_folder is not None else None
    if folders:
        return open_libraries(folders, root)
    paths: list[Path] = []
    if root is not None:
        try:
            paths = library_folders(root, read_pointer(root))
        except PointerError as exc:
            libs = ProjectLibraries(root=root)
            libs.problems.append(f"device-libraries.json: {exc}")
            return libs
    if not paths and person_folder:
        paths = [Path(person_folder)]
    return open_libraries(paths, root)


def file_library(path: Path | str, root: Path | str | None = None) -> ProjectLibraries:
    """One device library file as a library of its own, in its folder (the editor's *Add from
    library…* of the Devices tab, which opens a file, not a folder). Raises `DeviceLibraryError`
    when the file cannot be read."""
    p = Path(path)
    data = dl.read_library(p)
    try:
        name = df.library_info(p.parent).name
    except HarnessError:
        name = p.parent.resolve().name or str(p.parent)
    entries, _problems = lf._device_entries(p.name, data)
    libs = ProjectLibraries(root=Path(root) if root is not None else None)
    libs.add(Library(p.parent, name), entries)
    return libs


# ---- the file of a library device -------------------------------------------------------------


@dataclass(frozen=True)
class DeviceSource:
    """A library device as its file holds it now: the checked content of the file, the SHA-256
    of its bytes and the device's record in it."""

    device: LibraryDevice
    data: dict[str, Any]
    sha256: str
    record: dict[str, Any]

    def unit(self) -> Unit:
        return Unit.model_validate(self.record.get("unit"))

    def connectors(self) -> list[Connector]:
        """The device's connectors, the pins in portable form."""
        out = []
        for raw in self.record.get("connectors", []):
            c = Connector.model_validate(raw)
            out.append(evolve(c, pins=[dl._portable(p) for p in c.pins]))
        return out

    def parts(self) -> dict[str, Part]:
        out: dict[str, Part] = {}
        for raw in self.data.get("parts", []):
            try:
                p = Part.model_validate(raw)
            except ValidationError:
                continue
            out[p.id] = p
        return out

    def types(self) -> dict[str, InterfaceType]:
        out: dict[str, InterfaceType] = {}
        for raw in self.data.get("interface_types", []):
            try:
                t = InterfaceType.model_validate(raw)
            except ValidationError:
                continue
            out[t.id] = t
        return out

    def unit_ids(self) -> list[str]:
        """Every device ID of the file (a 2.1 file may hold more than one)."""
        return [uid for uid, _name in dl.device_names(self.data) if uid]


def read_device(device: LibraryDevice) -> DeviceSource:
    """Read the file of a library device once: its bytes give the SHA-256, the same bytes give
    the content (so the two always belong together). Raises `LinkError` in plain words."""
    path = device.path
    try:
        if path.is_symlink() or not path.is_file():
            raise LinkError(f"The file {device.file} of the library {device.library.name} is gone.")
        if path.stat().st_size > dl.MAX_BYTES:
            raise LinkError(f"The file {device.file} is too large to read (limit 8 MB).")
        raw = path.read_bytes()
    except OSError as exc:
        raise LinkError(f"The file {device.file} could not be read ({exc.strerror}).") from exc
    try:
        data = dl.check_library(canonical.loads_strict(raw))
    except (ValueError, RecursionError) as exc:
        raise LinkError(f"{device.file}: {dl.json_problem(exc)}") from exc
    except dl.DeviceLibraryError as exc:
        raise LinkError(f"{device.file}: {exc}") from exc
    rec = next(
        (
            r
            for r in data.get("devices", [])
            if isinstance(r, dict)
            and isinstance(r.get("unit"), dict)
            and r["unit"].get("id") == device.unit_id
        ),
        None,
    )
    if rec is None or dl.record_problem(rec):
        raise LinkError(f"The file {device.file} does not hold the device {device.unit_id} now.")
    try:
        Unit.model_validate(rec.get("unit"))
        for c in rec.get("connectors", []):
            Connector.model_validate(c)
    except ValidationError as exc:
        raise LinkError(
            f"The device {device.unit_id} in {device.file} is not valid: {exc.errors()[0]['msg']}"
        ) from exc  # noqa: E501
    return DeviceSource(device, data, hashlib.sha256(raw).hexdigest(), rec)


# ---- the import record (design section 4) -----------------------------------------------------


def record_notes(device: LibraryDevice) -> list[str]:
    """The fixed-form lines of a record (the program never reads them back): `Library: <name>`,
    `Library file: <path in the library>`, then `Library commit: <id> (branch <b>)` (or
    `(detached)`, `Library commit: none yet`, `Library commit: not readable`) or `Library: not a
    Git repository`, and `Library file: not committed` (or `not readable`) when the file differs
    from the one of the commit."""
    folder = device.library.folder
    lines = [f"Library: {device.library.name}", f"Library file: {device.file}"]
    git = library_git(folder)
    if git.kind == "none":
        lines.append("Library: not a Git repository")
        return lines
    if git.kind == "commit":
        where = f"branch {git.branch}" if git.branch else "detached"
        lines.append(f"Library commit: {git.commit} ({where})")
    elif git.kind == "empty":
        lines.append("Library commit: none yet")
    else:
        lines.append(f"Library commit: {NOT_READABLE}")
    state = file_state(folder, device.file)
    if state in (NOT_COMMITTED, NOT_READABLE):
        lines.append(f"Library file: {state}")
    return lines


def device_record(source: DeviceSource, root: Path | str | None = None) -> ImportRecord:
    """The import record of a library device file: kind `devices`, id `devices:<file name>`, the
    SHA-256 of the file, the fixed-form notes, and `source_path` only when the library lies inside
    the project folder `root` (relative to it)."""
    dev = source.device
    return ImportRecord(
        id=dev.record_id,
        kind=KIND,
        source_name=clean(dev.file_name, 150),
        source_path=project_relative(dev.path, root),
        sha256=source.sha256,
        tool_version=__version__,
        rows_read=len(source.unit_ids()),
        notes=[clean(n, 1000) for n in record_notes(dev)],
    )


def _record_ops(
    project: Project, source: DeviceSource, record: ImportRecord, doing: Iterable[str]
) -> tuple[list[Op], str]:
    """The op that stores `record`, and a sentence when it is not stored. A record never links a
    device of the project that it did not link before (a device with the ID of another device of
    the same file), and is not replaced while another device it links follows an earlier version
    of the file that differs; the devices `doing` are the ones this step adds or updates."""
    busy = set(doing)
    others = [
        (x, uid)
        for uid in source.unit_ids()
        for x in [uid, *copies.copy_ids(uid, copies.MAX_DEVICES)]
        if x in project.units and x not in busy
    ]
    old = project.import_records.get(record.id)
    if old is None:
        if others:
            names = ", ".join(x for x, _u in others)
            return [], (
                f"No import record was written: {names} of this project would follow "
                f"{record.source_name} although {'it was' if len(others) == 1 else 'they were'} "
                "not added from it."
            )
        return record_ops(project, record), ""
    if old.sha256 != record.sha256:
        stale = [x for x, uid in others if _family_rows(project, x, uid, source, None)]
        if stale:
            return [], (
                f"The import record of {record.source_name} is kept: {', '.join(stale)} "
                "follow an earlier version of that file; update them to bring it up to date."
            )
    return record_ops(project, record), ""


# ---- comparing a project device with its library device ---------------------------------------


def _copy_base(unit_id: str) -> str | None:
    """The device that `unit_id` would be a copy of (`D` for `D-R`, `D-3` ... `D-10`)."""
    head, dash, tail = unit_id.rpartition("-")
    if not dash or not head:
        return None
    if tail == "R" or (tail.isdigit() and str(int(tail)) == tail and 3 <= int(tail) <= 10):
        return head
    return None


def _candidates(unit_id: str) -> list[str]:
    base = _copy_base(unit_id)
    return [unit_id] if base is None else [unit_id, base]


def _family(project: Project, base: str) -> list[str]:
    """The device `base` (when the project has it) and its copies that the project has."""
    ids = [base, *copies.copy_ids(base, copies.MAX_DEVICES)]
    return [x for x in ids if x in project.units]


def _project_cid(x: str, base: str, lib_cid: str) -> str:
    """The ID that the library connector `lib_cid` has on the device `x` (`base` or its copy)."""
    if x == base:
        return (
            lib_cid
            if lib_cid.startswith(base + "-")
            else f"{base}-{dl.connector_tail(lib_cid, base)}"
        )  # noqa: E501
    return f"{x}-{lib_cid.rsplit('-', 1)[-1]}"


Pair = tuple[str, Connector | None, Connector | None]


def _pairs(project: Project, x: str, base: str, lib: Sequence[Connector]) -> list[Pair]:
    """(the connector's ID on `x`, the project's connector, the library's) for every connector of
    either side."""
    mine = sorted((c for c in project.connectors.values() if c.unit_id == x), key=lambda c: c.id)
    expected = {_project_cid(x, base, c.id): c for c in lib}
    by_id = {c.id: c for c in lib}
    used: set[str] = set()
    out: list[Pair] = []
    for pc in mine:
        found = expected.get(pc.id)
        if found is None and x == base:
            found = by_id.get(f"{base}-{dl.connector_tail(pc.id, base)}")
        if found is not None and found.id not in used:
            used.add(found.id)
            out.append((pc.id, pc, found))
        else:
            out.append((pc.id, pc, None))
    for c in lib:
        if c.id not in used:
            out.append((_project_cid(x, base, c.id), None, c))
    return out


def _own_signal(pin: Pin, lib_pin: Pin | None = None) -> bool:
    """Is the signal of this project pin the project's own (an allocation: the pin is not fixed and
    carries an interface or a lock), so that the library's signal does not replace it?"""
    if lib_pin is not None and lib_pin.fixed:
        return False
    return not pin.fixed and (pin.interface_id is not None or pin.locked)


@dataclass(frozen=True)
class DiffRow:
    """One difference: the device (the library device or a copy of it), connector and pin it is
    on ("" for a field of the device or of the connector), the field, the value in this project
    and in the library (as text; `yes`/`no` for a connector or pin that one side lacks), and the
    released harnesses that lock it ("" when none)."""

    device: str
    connector: str
    pin: str
    field: str
    here: str
    library: str
    locked_by: str = ""

    def key(self) -> tuple[Any, ...]:
        return (
            natural_key(self.connector),
            natural_key(self.pin),
            _FIELD_ORDER.get(self.field, 99),
            natural_key(self.device),
        )


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, RowLayout):
        return layout_text(value)
    if isinstance(value, DeviceCheck):
        return check_words(value)
    if isinstance(value, list | tuple):
        return ", ".join(str(v) for v in value)
    return str(value)


Locks = dict[tuple[str, str], list[Any]] | None


def _locked(locks: Locks, kind: str, oid: str) -> str:
    if not locks:
        return ""
    return ", ".join(r.harness_id for r in locks.get((kind, oid), []))


def _family_rows(
    project: Project, x: str, base: str, source: DeviceSource, locks: Locks
) -> list[DiffRow]:
    """The differences of the project device `x` (the library device `base` or its copy) from
    the library device of `source`."""
    rows: list[DiffRow] = []
    unit = project.units[x]
    lib_unit = source.unit()

    def add(cid: str, pid: str, name: str, here: object, there: object, lock: str = "") -> None:
        rows.append(DiffRow(x, cid, pid, name, _text(here), _text(there), lock))

    for name in UNIT_FIELDS:
        a, b = getattr(unit, name), getattr(lib_unit, name)
        if a != b:
            lock = "" if name in COSMETIC_UNIT_FIELDS else _locked(locks, "unit", x)
            add("", "", name, a, b, lock)
    for cid, pc, lc in _pairs(project, x, base, source.connectors()):
        if pc is None:
            add(cid, "", "connector", False, True)
            continue
        box = _locked(locks, "box_connector", cid)
        if lc is None:
            add(cid, "", "connector", True, False, box)
            continue
        for name in CONNECTOR_FIELDS:
            a, b = getattr(pc, name), getattr(lc, name)
            if a != b:
                add(cid, "", name, a, b, box if name in LOCKED_CONNECTOR_FIELDS else "")
        mine = {p.id: p for p in pc.pins}
        theirs = {p.id: p for p in lc.pins}
        for pid in sorted(set(mine) | set(theirs), key=natural_key):
            pp, lp = mine.get(pid), theirs.get(pid)
            if pp is None or lp is None:
                lock = _locked(locks, "box_pin", f"{cid}.{pid}") or box
                add(cid, pid, "pin", pp is not None, lp is not None, lock)
                continue
            for name in PIN_FIELDS:
                if name == "signal" and _own_signal(pp, lp):
                    continue
                a, b = getattr(pp, name), getattr(lp, name)
                if a != b:
                    add(cid, pid, name, a, b, _locked(locks, "box_pin", f"{cid}.{pid}"))
    return rows


# ---- the states -------------------------------------------------------------------------------


@dataclass(frozen=True)
class LinkState:
    """How a project device stands to the library (design section 3). `unit_id` is the project
    device (the library device for `not in project`), `library_id` the library device it follows
    or would follow; `message` says why for `source not found` and `in more than one library`."""

    unit_id: str
    library_id: str
    state: str
    device: LibraryDevice | None = None
    record_id: str = ""
    recorded_sha256: str = ""
    library_sha256: str = ""
    message: str = ""

    @property
    def linked(self) -> bool:
        return self.state in LINKED_STATES


Sources = dict[Path, DeviceSource | LinkError]


def _read(device: LibraryDevice, cache: Sources) -> DeviceSource:
    hit = cache.get(device.path)
    if hit is None:
        try:
            hit = read_device(device)
        except LinkError as exc:
            hit = exc
        cache[device.path] = hit
    if isinstance(hit, LinkError):
        raise hit
    return hit


def _state(
    project: Project, libraries: ProjectLibraries, unit_id: str, cache: Sources
) -> LinkState | None:
    if unit_id not in project.units:
        try:
            dev = libraries.device(unit_id)
        except AmbiguousDeviceError as exc:
            return LinkState(unit_id, unit_id, AMBIGUOUS, message=str(exc))
        return None if dev is None else LinkState(unit_id, unit_id, NOT_IN_PROJECT, dev)
    first: LinkState | None = None
    for base in _candidates(unit_id):
        try:
            dev = libraries.device(base)
        except AmbiguousDeviceError as exc:
            first = first or LinkState(unit_id, base, AMBIGUOUS, message=str(exc))
            continue
        rec = project.import_records.get(dev.record_id) if dev is not None else None
        if dev is not None and rec is not None and rec.kind == KIND:
            try:
                src = _read(dev, cache)
            except LinkError as exc:
                return LinkState(
                    unit_id, base, SOURCE_NOT_FOUND, dev, rec.id, rec.sha256, "", str(exc)
                )
            differs = bool(_family_rows(project, unit_id, base, src, None))
            same = src.sha256 == rec.sha256
            state = (CHANGED_HERE if same else LIBRARY_CHANGED) if differs else UP_TO_DATE
            return LinkState(unit_id, base, state, dev, rec.id, rec.sha256, src.sha256)
        if first is not None:
            continue
        lost = project.import_records.get(record_id(KIND, df.device_file_name(base)))
        if dev is None and lost is not None:
            first = LinkState(
                unit_id, base, SOURCE_NOT_FOUND, None, lost.id, lost.sha256, "",
                f"No library of this project holds {base} ({lost.source_name}).",
            )  # fmt: skip
        elif dev is not None:
            first = LinkState(unit_id, base, NOT_FROM_LIBRARY, dev)
    return first


def link_state(project: Project, libraries: ProjectLibraries, unit_id: str) -> LinkState | None:
    """The state of the project device `unit_id` (or of the library device `unit_id` that the
    project does not have); None when it has nothing to do with the libraries. Up to date: the
    library-owned fields are the same (the record may be of an earlier version of the file whose
    change touched another device or no field); library changed: the file's SHA-256 differs from
    the record's and so do the fields; changed here: the same SHA-256 and other fields."""
    return _state(project, libraries, unit_id, {})


def link_states(project: Project, libraries: ProjectLibraries) -> list[LinkState]:
    """The state of every project device that has to do with the libraries, and every library
    device the project does not have (`not in project`), sorted by ID."""
    cache: Sources = {}
    out = [
        st
        for uid in sorted(project.units, key=natural_key)
        if (st := _state(project, libraries, uid, cache)) is not None
    ]
    have = {u.casefold() for u in project.units}
    seen: set[str] = set()
    for dev in libraries.devices():
        if dev.unit_id.casefold() in have or dev.unit_id in seen:
            continue
        seen.add(dev.unit_id)
        st = _state(project, libraries, dev.unit_id, cache)
        if st is not None:
            out.append(st)
    return sorted(out, key=lambda s: natural_key(s.unit_id))


# ---- the diff and the impacts -----------------------------------------------------------------


@dataclass(frozen=True)
class LibraryDiff:
    """The differences of a project device and its copies from the library device, sorted by
    connector then pin; `impacts` say what an update would touch (interfaces, wires and links on
    pins or connectors that go, drafts to generate again); `notes` say what is kept (a part or an
    interface type of the project that differs from the library's)."""

    library_id: str
    devices: tuple[str, ...]
    state: LinkState | None
    rows: tuple[DiffRow, ...]
    impacts: tuple[str, ...]
    notes: tuple[str, ...]
    device: LibraryDevice
    sha256: str


def _base_of(
    project: Project, libraries: ProjectLibraries, unit_id: str
) -> tuple[str, LibraryDevice]:
    if unit_id not in project.units:
        raise LinkError(f"There is no device {unit_id} in this project.")
    for base in _candidates(unit_id):
        dev = libraries.device(base)
        if dev is not None:
            return base, dev
    raise LinkError(f"No library of this project holds {unit_id}.")


def _links_on(project: Project, cid: str, pins: Iterable[str] | None = None) -> list[str]:
    wanted = None if pins is None else set(pins)
    out = []
    for link in sorted(project.links.values(), key=lambda x: x.id):
        for at, ps in (
            (link.a_connector, [p.a_pin for p in link.pairs]),
            (link.b_connector, [p.b_pin for p in link.pairs]),
        ):
            if at == cid and (wanted is None or wanted & set(ps)):
                out.append(link.id)
                break
    return out


def _and(items: Sequence[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _impacts(project: Project, x: str, pairs: list[Pair]) -> tuple[list[str], set[str]]:
    """(sentences, generated drafts that the change makes out of date) for one device."""
    out: list[str] = []
    drafts: set[str] = set()
    for cid, pc, lc in pairs:
        if pc is None:
            continue
        if lc is None:
            ci = devices.connector_delete_impact(project, cid)
            what = []
            if ci.interfaces:
                what.append(f"{_and(ci.interfaces)} lose the connector")
            if links := _links_on(project, cid):
                verb = "are" if len(links) > 1 else "is"
                what.append(f"link{'s' if len(links) > 1 else ''} {_and(links)} {verb} deleted")
            if ci.blocked_by_harnesses:
                what.append(
                    f"{_and(ci.blocked_by_harnesses)} (made by hand or released) has wires on it"
                )  # noqa: E501
            out.append(
                f"The connector {cid} is not in the library's version"
                + (f": {'; '.join(what)}." if what else ".")
            )
            drafts.update(ci.outdated_harnesses)
            continue
        gone = sorted({p.id for p in pc.pins} - {p.id for p in lc.pins}, key=natural_key)
        if gone:
            pi = devices.pin_impact(project, cid, gone)
            what = [pi.sentence()] if pi.interfaces else []
            if links := _links_on(project, cid, gone):
                what.append(f"paired in link{'s' if len(links) > 1 else ''} {_and(links)}")
            if pi.blocked_by_harnesses:
                what.append(
                    f"{_and(pi.blocked_by_harnesses)} (made by hand or released) has wires on them"
                )  # noqa: E501
            out.append(
                f"Pin{'s' if len(gone) > 1 else ''} {_and(gone)} of {cid} "
                f"{'are' if len(gone) > 1 else 'is'} not in the library's version"
                + (f": {'; '.join(w for w in what if w)}." if any(what) else ".")
            )
        if pc.pins:
            drafts.update(
                devices.pin_impact(project, cid, [p.id for p in pc.pins]).outdated_harnesses
            )  # noqa: E501
    return out, drafts


def _family_diff(
    project: Project, base: str, source: DeviceSource
) -> tuple[list[DiffRow], list[str]]:
    locks = locked_objects(project)
    rows: list[DiffRow] = []
    impacts: list[str] = []
    drafts: set[str] = set()
    lib = source.connectors()
    for x in _family(project, base):
        here = _family_rows(project, x, base, source, locks)
        rows += here
        if here:
            words, outdated = _impacts(project, x, _pairs(project, x, base, lib))
            impacts += words
            drafts |= outdated
    if drafts:
        names = sorted(drafts, key=natural_key)
        impacts.append(
            f"Generate again: {_and(names)} {'are drafts' if len(names) > 1 else 'is a draft'} "
            "on a changed connector and will be out of date."
        )
    return sorted(rows, key=DiffRow.key), impacts


def _part_words(p: Part) -> str:
    pins = f"{p.pin_count} pins" if p.pin_count else "no pin count"
    return f"a {p.category} part with {pins}"


def _used_parts(source: DeviceSource) -> list[str]:
    """The parts the device names (connector parts, contact parts, and the parts they mate
    with), sorted."""
    file_parts = source.parts()
    todo = [
        pid
        for c in source.connectors()
        for pid in [c.part_id, *(p.contact_part for p in c.pins if p.contact_part)]
        if pid
    ]
    seen: set[str] = set()
    while todo:
        pid = todo.pop()
        if pid in seen:
            continue
        seen.add(pid)
        part = file_parts.get(pid)
        if part is not None and part.mates_with:
            todo.append(part.mates_with)
    return sorted(seen)


def _part_check(project: Project, source: DeviceSource) -> tuple[list[str], list[str]]:
    """(refusals, notes): a part the project has with another category or pin count refuses;
    any other difference of a part or an interface type is a note (the project's is kept)."""
    file_parts, refusals, notes = source.parts(), [], []
    for pid in _used_parts(source):
        mine, theirs = project.parts.get(pid), file_parts.get(pid)
        if mine is None or theirs is None or mine == theirs:
            continue
        if (mine.category, mine.pin_count) != (theirs.category, theirs.pin_count):
            refusals.append(
                f"The part {pid} is {_part_words(mine)} in this project and {_part_words(theirs)} "
                "in the library. Nothing was changed; make the two agree first."
            )
        else:
            notes.append(f"Part {pid} differs from the one in the library; the project's is kept.")
    types = source.types()
    for t in sorted({t for c in source.connectors() for t in c.carries}):
        mine_t, theirs_t = project.interface_types.get(t), types.get(t)
        if mine_t is not None and theirs_t is not None and mine_t != theirs_t:
            notes.append(
                f"Interface type {t} differs from the one in the library; the project's is kept."
            )
    return refusals, notes


def library_diff(project: Project, libraries: ProjectLibraries, unit_id: str) -> LibraryDiff:
    """The differences of the project device `unit_id` (or of the library device it is a copy of)
    and its copies from the library device. Changes nothing."""
    base, dev = _base_of(project, libraries, unit_id)
    source = read_device(dev)
    rows, impacts = _family_diff(project, base, source)
    _refusals, notes = _part_check(project, source)
    family = _family(project, base)
    state = link_state(project, libraries, family[0]) if family else None
    return LibraryDiff(
        base, tuple(family), state, tuple(rows), tuple(impacts), tuple(notes), dev, source.sha256
    )


# ---- add (design section 3, workflow 2) -------------------------------------------------------


@dataclass(frozen=True)
class AddPlan:
    """What adding a library device does, as the ops of one undo step: the device, its connectors,
    the parts and interface types the project lacks, its place, its copies and the import record
    (`record`, None when none is written; `notes` say why)."""

    ops: list[Op]
    unit_ids: tuple[str, ...]  # the devices added: the device first, then its copies
    label: str
    notes: tuple[str, ...]
    skipped: tuple[str, ...]  # links that could not be mirrored onto a copy
    record: ImportRecord | None
    device: LibraryDevice


def _one_device(source: DeviceSource, new_id: str | None) -> dict[str, Any]:
    """A library with only this device (under `new_id` when given)."""
    rec = source.record
    if new_id is not None and new_id != source.device.unit_id:
        old = source.device.unit_id
        conns = []
        for c in rec.get("connectors", []):
            cid = f"{new_id}-{dl.connector_tail(str(c.get('id', '')), old)}"
            conns.append({**c, "id": cid, "unit_id": new_id})
        rec = {**rec, "unit": {**rec["unit"], "id": new_id}, "connectors": conns}
    return {
        "format": dl.FORMAT,
        "version": dl.VERSION,
        "devices": [rec],
        "parts": source.data.get("parts", []),
        "interface_types": source.data.get("interface_types", []),
    }


def _project_id(project: Project, unit_id: str) -> str | None:
    key = unit_id.casefold()
    return next((u for u in project.units if u.casefold() == key), None)


def plan_add_device(
    project: Project,
    libraries: ProjectLibraries,
    name: str,
    count: int = 1,
    as_id: str | None = None,
    *,
    rename_taken: bool = False,
    root: Path | str | None = None,
) -> AddPlan:
    """Add the library device `name` (its ID, or a unique `unit.name`), `count` of it (the device
    and its copies `D-R`, `D-3` ...), as one undo step with the import record of its file.

    An ID the project has already is refused with `TakenIdError`: when that device follows the
    library, use `count` for copies; when it does not, adopt it (`plan_update_device(...,
    adopt=True)`) or add under another ID `as_id`. A device added under another ID (`as_id`, or
    the next free ID with `rename_taken`, which is what the editor did before 2.2) is an unlinked
    copy: no record is written for it. A part the project has with another category or pin count
    refuses the add. `root` is the project folder (for `source_path`)."""
    dev = libraries.resolve(name)
    source = read_device(dev)
    lib_id = dev.unit_id
    taken = {u.casefold() for u in project.units}
    if as_id is not None:
        if not ID_RE.fullmatch(as_id):
            raise LinkError(f"'{as_id}' cannot be used as a device ID.")
        if as_id.casefold() in taken:
            raise LinkError(f"{as_id} is taken in this project; choose another ID.")
    elif (have := _project_id(project, lib_id)) is not None:
        free = dl._free_id(lib_id, taken)
        if rename_taken:
            as_id = free
        else:
            st = link_state(project, libraries, have)
            if st is not None and st.linked:
                n = copies.device_count(project, have)
                raise TakenIdError(
                    f"{have} is in this project already and follows the library ({st.state}). "
                    f"For copies of it, ask for {n + 1} or more of these devices; to take the "
                    "library's version, update it.",
                    have, True, free, (),
                )  # fmt: skip
            rows = tuple(library_diff(project, libraries, have).rows) if have == lib_id else ()
            raise TakenIdError(
                f"{have} is in this project already but does not come from the library "
                f"({len(rows)} difference{'' if len(rows) == 1 else 's'}). Adopt it to link it to "
                f"the library, or add the library's device under another ID (for example {free}).",
                have, False, free, rows,
            )  # fmt: skip
    refusals, part_notes = _part_check(project, source)
    if refusals:
        raise LinkError(refusals[0])
    target = as_id or lib_id
    plan = dl.plan_device_import(project, _one_device(source, as_id), [target])
    row = plan.rows[0] if plan.rows else None
    if row is None or not row.ok:
        raise LinkError(f"{lib_id}: {row.message if row else 'the device cannot be read.'}")
    ops = with_placements(project, plan.ops)
    ids = [row.new_id]
    skipped: tuple[str, ...] = ()
    if count != 1:
        more = copies.plan_copies(clone_with(project, ops), row.new_id, count)
        ops += more.ops
        ids += list(more.new_ids)
        skipped = more.skipped
    notes = [n for n in plan.notes if n not in part_notes] + part_notes
    record: ImportRecord | None = None
    if as_id is None:
        record = device_record(source, root)
        written, why = _record_ops(project, source, record, ids)
        ops += written
        if why:
            notes.append(why)
            record = None
    else:
        notes.append(
            f"{as_id} is a copy of the library device {lib_id} that does not follow the library "
            "(no import record)."
        )
    label = f"Add {', '.join(ids)} from the library"
    return AddPlan(ops, tuple(ids), label, tuple(notes), skipped, record, dev)


def plan_add_devices(
    project: Project,
    libraries: ProjectLibraries,
    names: Sequence[str],
    *,
    rename_taken: bool = False,
    root: Path | str | None = None,
) -> AddPlan:
    """Several library devices as one undo step, each through `plan_add_device` (the editor's
    *Add from library…* of the Devices tab, which adds the ticked devices of one file)."""
    if not names:
        raise LinkError("Choose at least one device.")
    scratch = project
    ops: list[Op] = []
    ids: list[str] = []
    notes: list[str] = []
    skipped: list[str] = []
    record: ImportRecord | None = None
    first: LibraryDevice | None = None
    for name in dict.fromkeys(names):
        add = plan_add_device(scratch, libraries, name, rename_taken=rename_taken, root=root)
        ops += add.ops
        ids += add.unit_ids
        notes += [n for n in add.notes if n not in notes]
        skipped += add.skipped
        record = add.record or record
        first = first or add.device
        scratch = clone_with(scratch, add.ops)
    if first is None:  # pragma: no cover - names is not empty
        raise LinkError("Choose at least one device.")
    label = f"Add {', '.join(ids)} from the library"
    return AddPlan(ops, tuple(ids), label, tuple(notes), tuple(skipped), record, first)


# ---- update (design section 3, workflow 3) ----------------------------------------------------


@dataclass(frozen=True)
class UpdatePlan:
    """What taking the library's version of a device does: `ops` for one undo step (empty when
    the device and its record are as the library has them), the diff it applies, and notes."""

    library_id: str
    ops: list[Op]
    label: str
    diff: LibraryDiff
    notes: tuple[str, ...]
    record: ImportRecord | None


def _merged_pin(lib_pin: Pin, old: Pin | None) -> Pin:
    """The library's pin with the project-owned fields of the pin it replaces."""
    if old is None:
        return lib_pin
    signal = old.signal if _own_signal(old, lib_pin) else lib_pin.signal
    return evolve(lib_pin, interface_id=old.interface_id, locked=old.locked, signal=signal)


def _check_connector(project: Project, cid: str, old: Connector, new: Connector) -> None:
    """Refuse a change of a box connector that a release or a link holds (the sentences of the
    editor's own pin edits)."""
    design = ("part_id", "gender", "keying")
    if any(getattr(old, f) != getattr(new, f) for f in design) and (
        why := devices.pin_set_frozen(project, cid)
    ):
        raise LinkError(f"The library changes the part, gender or keying of {cid}. {why}")
    mine = {p.id: p for p in old.pins}
    theirs = {p.id for p in new.pins}
    gone = sorted(set(mine) - theirs, key=natural_key)
    added = sorted(theirs - set(mine), key=natural_key)
    if (gone or added) and (why := devices.pin_set_frozen(project, cid)):
        raise LinkError(f"The library adds or removes pins of {cid}. {why}")
    for p in new.pins:
        before = mine.get(p.id)
        if (
            before is not None
            and before != p
            and (why := devices.pin_lock_reason(project, cid, p.id))
        ):
            raise LinkError(f"Pin {p.id} of {cid} cannot change. {why}")
    if gone:
        if links := _links_on(project, cid, gone):
            raise LinkError(
                f"Pin {_and(gone)} of {cid} is not in the library's version, and it is paired in "
                f"link{'s' if len(links) > 1 else ''} {_and(links)}. Change the pairing of the "
                "link first."
            )
        impact = devices.pin_impact(project, cid, gone)
        if impact.locked:
            raise LinkError(impact.locked[0][1])
        if impact.blocked_by_harnesses:
            raise LinkError(
                f"Pin {_and(gone)} of {cid} is not in the library's version: "
                f"{_and(impact.blocked_by_harnesses)} (made by hand or released) has wires on it."
            )


def _device_ops(
    project: Project, scratch: Project, x: str, base: str, source: DeviceSource, types: set[str]
) -> list[Op]:
    """The ops that give the project device `x` the library's version; refusals raise."""
    unit = project.units[x]
    lib_unit = source.unit()
    ops: list[Op] = []
    new_unit = evolve(
        unit,
        kind=lib_unit.kind,
        mass_relevant=lib_unit.mass_relevant,
        notes=lib_unit.notes,
        checked=lib_unit.checked,
    )
    if new_unit != unit:
        if unit_design(new_unit) != unit_design(unit) and (why := lock_reason(project, "unit", x)):
            raise LinkError(why)
        ops.append(Put("units", new_unit))
    parts = {**source.parts(), **project.parts}
    for cid, pc, lc in _pairs(project, x, base, source.connectors()):
        if lc is None:
            try:
                ops += devices.ops_delete_connector(clone_with(scratch, ops), cid)
            except EditError as exc:
                raise LinkError(f"{cid} is not in the library's version. {exc}") from exc
            continue
        old_pins = {p.id: p for p in pc.pins} if pc is not None else {}
        pins = [_merged_pin(p, old_pins.get(p.id)) for p in lc.pins]
        pins = [
            p if not p.contact_part or p.contact_part in parts else evolve(p, contact_part=None)
            for p in pins
        ]  # noqa: E501
        new = evolve(
            lc,
            id=cid,
            unit_id=x,
            pins=pins,
            carries=[t for t in lc.carries if t in types],
            locked=pc.locked if pc is not None else False,
        )
        if pc is not None:
            if new == pc:
                continue
            _check_connector(project, cid, pc, new)
        elif cid.casefold() in {c.casefold() for c in project.all_connectors()}:
            raise LinkError(f"The connector ID {cid} is taken in this project by another device.")
        part = parts.get(new.part_id)
        if part is not None and part.pin_count and len(new.pins) > part.pin_count:
            raise LinkError(
                f"{cid} would have {len(new.pins)} pins, but its part {new.part_id} has "
                f"{part.pin_count}."
            )
        ops.append(Put("connectors", new))
    return ops


def _new_parts_and_types(project: Project, source: DeviceSource) -> list[Op]:
    """The parts (with the parts they mate with) and interface types the device names that the
    project lacks; the project's own are never replaced."""
    file_parts = source.parts()
    ops: list[Op] = [
        Put("parts", file_parts[pid])
        for pid in _used_parts(source)
        if pid not in project.parts and pid in file_parts
    ]
    types = source.types()
    wanted = sorted({t for c in source.connectors() for t in c.carries})
    ops += [
        Put("interface_types", types[t])
        for t in wanted
        if t not in project.interface_types and t in types
    ]
    return ops


def plan_update_device(
    project: Project,
    libraries: ProjectLibraries,
    unit_id: str,
    *,
    adopt: bool = False,
    root: Path | str | None = None,
) -> UpdatePlan:
    """Give the project device `unit_id` (or the library device it is a copy of) and its copies
    the library's version, as one undo step: the library-owned fields change, the project-owned
    ones stay (with the allocations of the pins that still exist), the parts and interface types
    the project lacks are added, and the record is replaced (new SHA-256 and notes, same id). All
    or nothing: a change that a released harness locks refuses the whole device and names the
    harness, and so do a removed pin that a link pairs, a part of another category or pin count,
    and whatever `History.execute` would refuse (tried on a copy of the project). A device that
    does not come from the library is refused unless `adopt`, which links it. Changes nothing
    itself; apply the ops with `History.execute`."""
    base, dev = _base_of(project, libraries, unit_id)
    source = read_device(dev)
    family = _family(project, base)
    state = link_state(project, libraries, family[0])
    if state is not None and state.state == NOT_FROM_LIBRARY and not adopt:
        raise LinkError(
            f"{family[0]} does not come from the library (the project has no import record of "
            f"{dev.file_name}). Adopt it to link it to the library, or leave it as it is."
        )
    refusals, notes = _part_check(project, source)
    if refusals:
        raise LinkError(refusals[0])
    rows, impacts = _family_diff(project, base, source)
    diff = LibraryDiff(
        base, tuple(family), state, tuple(rows), tuple(impacts), tuple(notes), dev, source.sha256
    )
    ops = _new_parts_and_types(project, source)
    types = set(project.interface_types) | set(source.types())
    for x in family:
        ops += _device_ops(project, clone_with(project, ops), x, base, source, types)
    if not rows:
        ops = []  # nothing of the device changes: no part or type is added either
    record = device_record(source, root)
    written, why = _record_ops(project, source, record, family)
    ops += written
    out_notes = list(notes)
    if why:
        out_notes.append(why)
    label = f"Take the library's version of {base}"
    if ops:
        try:
            History(clone_with(project, [])).execute(label, ops)
        except TransactionError as exc:
            detail = " ".join(exc.problems[:3])
            raise LinkError(f"{exc} {detail}".strip()) from exc
    return UpdatePlan(base, ops, label, diff, tuple(out_notes), record if written else None)


# ---- save (design section 3, workflow 1) ------------------------------------------------------


@dataclass(frozen=True)
class SavePlan:
    """A device saved into a library: the file written (`path`, and `file` inside the library
    folder), and the op that records it in the project (empty when the project holds this very
    record already)."""

    path: Path
    file: str
    ops: list[Op]
    record: ImportRecord
    notes: tuple[str, ...]


def plan_save_device(
    project: Project,
    library: Library | Path | str,
    unit_id: str,
    replace: bool = False,
    *,
    root: Path | str | None = None,
) -> SavePlan:
    """WRITES the device `unit_id` of the project into the library folder, then returns the op
    that records the written file in the project (apply it with `History.execute`).

    The file is the device file of the folder that holds the device already, else
    `<ID>.device.json` at the root of the folder (`library_folder.save_devices`); a different
    device of the same ID there raises `LibraryConflict` and writes nothing, unless `replace`. The
    tool never commits: in a Git checkout the record's notes say `Library file: not committed`.
    The project itself is not changed here."""
    if unit_id not in project.units:
        raise LinkError(f"There is no device {unit_id} in this project.")
    folder = library.folder if isinstance(library, Library) else Path(library)
    notes: list[str] = []
    written = lf.save_devices(folder, project, [unit_id], replace=replace, notes=notes)
    path = written[0]
    if isinstance(library, Library):
        lib = library
    else:
        try:
            lib = Library(folder, df.library_info(folder).name)
        except HarnessError:
            lib = Library(folder, folder.resolve().name or str(folder))
    rel = path.relative_to(folder).as_posix()
    dev = LibraryDevice(lib, unit_id, project.units[unit_id].name, rel)
    source = read_device(dev)
    record = device_record(source, root)
    return SavePlan(path, rel, record_ops(project, record), record, tuple(notes))


# ---- the sources of the records ---------------------------------------------------------------


def located_sources(project: Project, libraries: ProjectLibraries) -> dict[str, Path]:
    """Record ID -> the library file of every `devices` record whose file one library of the
    project holds (exactly one file of that name), for `import_record.check_sources(...,
    located=...)`."""
    out: dict[str, Path] = {}
    for rid in sorted(project.import_records):
        rec = project.import_records[rid]
        if rec.kind != KIND:
            continue
        found = libraries.files_named(rec.source_name)
        if len(found) == 1:
            out[rid] = found[0]
    return out
