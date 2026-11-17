# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The commands of the device library (design of 2.2.0, `docs/ait/DESIGN_2.2_DEVICE_LIBRARY.md`
section 3; D-240): `libraries` (the project's libraries, `device-libraries.json`), `add-device`,
`update-device` and `save-device`. Every change of the project goes through `History` and the
functions of `core/library_link.py`, which the editor uses too; the libraries are the folders of
`--library` (repeatable; they replace the rest), else those of the project's
`device-libraries.json`. The command line never reads the person's library folder of the editor.

Exit codes as everywhere (`cli/main.py`): 0 done or shown, 1 refused or blocked and nothing
changed (a taken ID, a device in two libraries, a lock, a part conflict, a device file that
differs, `update-device --check` while a linked device differs), 2 a usage error or something that
cannot be found or read (a device name, a library, a project)."""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from harness_design_studio.cli import blocked_text
from harness_design_studio.cli.jsonout import Report, add_json_flag
from harness_design_studio.core import copies
from harness_design_studio.core import library_link as ll
from harness_design_studio.core import library_pointer as lp
from harness_design_studio.core.commands import History, Op, Put
from harness_design_studio.core.edit import clone_with
from harness_design_studio.core.errors import HarnessError, TransactionError
from harness_design_studio.core.import_record import RECORDS_FILE
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.library_folder import LibraryConflict
from harness_design_studio.core.library_git import library_git
from harness_design_studio.core.model import ImportRecord, Project

COMMANDS = ("libraries", "add-device", "update-device", "save-device")
READ_ONLY = "error: this project is read-only (saved by a newer tool version)."
OUTSIDE_UNDO = (
    "This change is outside undo and the change journal: device-libraries.json is not part of the "
    "design. Commit it with the project."
)
NO_LIBRARY = (
    "This project names no device library. Name one with `libraries DIR --add FOLDER` "
    "(written to device-libraries.json), or give --library FOLDER."
)
LIBRARY_HELP = (
    "a device library folder to use instead of the project's device-libraries.json (repeat for "
    "more; the folders given replace the project's list for this run)"
)


class _Usage(Exception):
    """A usage error of these commands: the message, exit code 2."""


class _Refused(Exception):
    """A change that was refused and changed nothing: the message, exit code 1."""


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    lb = sub.add_parser(
        "libraries",
        help="list the device libraries of a project, or name one in device-libraries.json",
        description="List the device libraries of a project: the folders of its "
        "device-libraries.json (or of --library), each with its name, its number of devices and "
        "its Git commit and branch (read from the folder; `git` is never run), and every file "
        "that could not be used. --add and --remove change device-libraries.json at once: it is "
        "not part of the design, so the change is outside undo and the change journal. With "
        "--devices every device of the libraries and of the project that has to do with them is "
        "listed with its state: not in project, up to date, library changed, changed here, same "
        "ID, not from the library, source not found, in more than one library.",
    )
    lb.add_argument("project", type=Path, help="project folder")
    lb.add_argument(
        "--add",
        action="append",
        default=[],
        metavar="FOLDER",
        help="name a library folder in device-libraries.json: relative to the project folder, "
        "written with / (an absolute path is turned into one relative to the project folder)",
    )
    lb.add_argument(
        "--remove",
        action="append",
        default=[],
        metavar="FOLDER",
        help="take a library folder out of device-libraries.json (as the file names it)",
    )
    lb.add_argument("--devices", action="store_true", help="also list every device with its state")
    _library_option(lb)
    add_json_flag(lb)

    ad = sub.add_parser(
        "add-device",
        help="add a device from the project's device libraries, with the record that links it",
        description="Add a device of the project's device libraries with its connectors, pins, "
        "the parts and interface types the project lacks, and the import record of its file "
        "(`devices:<file>`), which links the device to the library: `update-device` then shows "
        "what the library changes. NAME is the device ID or a device name that only one device "
        "has. It is one undo step. An ID the project has already is refused: when that device "
        "follows the library, ask for copies with --count; when it does not, add the library's "
        "device under another ID with --as (an unlinked copy, no record), or link the project's "
        "device with `update-device DIR ID --apply --adopt`.",
    )
    ad.add_argument("project", type=Path, help="project folder")
    ad.add_argument(
        "name", nargs="+", metavar="NAME", help="a device of the library: its ID or its name"
    )
    ad.add_argument(
        "--count",
        type=int,
        default=1,
        metavar="N",
        help=f"how many of this device the project has: the device and its copies (ID-R, "
        f"ID-3 ...; at most {copies.MAX_DEVICES}; one NAME only)",
    )
    ad.add_argument(
        "--as",
        dest="as_id",
        default=None,
        metavar="ID",
        help="add the device under another ID: a copy that does not follow the library "
        "(no import record; one NAME only)",
    )
    ad.add_argument(
        "--dry-run", action="store_true", help="show what would be added and change nothing"
    )
    _library_option(ad)
    add_json_flag(ad)

    up = sub.add_parser(
        "update-device",
        help="show what the device library changes for the project's devices, and take it",
        description="Compare the devices that follow a device library with the library: one row "
        "per changed field (device, connector, pin, field, in this project, in the library, and "
        "the released harness that locks it), what the change would touch (interfaces, wires and "
        "links on pins that go, drafts to generate again) and the notes. Without --apply nothing "
        "is changed. With --apply the library's version is taken, all or nothing per device and "
        "its copies, as one undo step each: the library-owned fields change (the connectors and "
        "pins, kind, mass relevance, notes), the project's own stay (name, subsystem, zone, side, "
        "the place, and on each pin the interface, the lock and an allocated signal), missing "
        "parts and interface types are added, and the import record is replaced. A change that a "
        "released harness locks, a pin that a link pairs, or a part of another category or pin "
        "count refuses that device; the message names it, and nothing of it is changed. Without "
        "NAME every device that follows a library is compared.",
    )
    up.add_argument("project", type=Path, help="project folder")
    up.add_argument(
        "name",
        nargs="*",
        metavar="NAME",
        help="a device of the project (a copy names its library device); default: all",
    )
    up.add_argument(
        "--all", action="store_true", help="every device that follows a library (with --apply)"
    )
    up.add_argument(
        "--apply", action="store_true", help="take the library's version (needs NAME or --all)"
    )
    up.add_argument(
        "--check",
        action="store_true",
        help="end with exit code 1 while a device that follows a library differs from it",
    )
    up.add_argument(
        "--adopt",
        action="store_true",
        help="with --apply and NAME: link a device of the same ID that was not added from the "
        "library, and take the library's version",
    )
    _library_option(up)
    add_json_flag(up)

    sv = sub.add_parser(
        "save-device",
        help="save a device of the project to a device library and link it",
        description="Write a device of the project into a device library folder: into the device "
        "file that holds it already, else `<ID>.device.json` at the root of the folder. A "
        "different device of the same ID there is refused unless --replace. The project then "
        "gets the import record of the written file, so the device follows the library. The "
        "library is the folder of --library, else the library of the project that holds the "
        "device, else the project's only library. The tool never commits: commit the library to "
        "share it.",
    )
    sv.add_argument("project", type=Path, help="project folder")
    sv.add_argument("device", metavar="DEVICE", help="the device to save, for example PCDU1")
    sv.add_argument(
        "--library",
        type=Path,
        default=None,
        metavar="FOLDER",
        help="the library folder to write into",
    )
    sv.add_argument(
        "--replace",
        action="store_true",
        help="replace a different device of the same ID in the library",
    )
    add_json_flag(sv)


def _library_option(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--library", action="append", default=[], type=Path, metavar="FOLDER", help=LIBRARY_HELP
    )


def mutates(args: argparse.Namespace) -> bool:
    """Whether the command writes the project or its `device-libraries.json` (it then takes the
    project lock)."""
    if args.command == "libraries":
        return bool(args.add or args.remove)
    if args.command == "add-device":
        return not bool(args.dry_run)
    if args.command == "update-device":
        return bool(args.apply)
    return bool(args.command == "save-device")


def run(args: argparse.Namespace) -> int:
    rep = Report(args.json)
    try:
        project = load_project(args.project).project
        if project.read_only and mutates(args):
            print(READ_ONLY, file=sys.stderr)
            return 2
        code = {
            "libraries": _libraries,
            "add-device": _add_device,
            "update-device": _update_device,
            "save-device": _save_device,
        }[args.command](project, args, rep)
    except _Usage as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except _Refused as exc:
        print(f"error: {exc}", file=sys.stderr)
        return rep.finish(1)
    except TransactionError as exc:  # blocked (for example by a release), not misused
        print(blocked_text(exc), file=sys.stderr)
        return rep.finish(1)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return rep.finish(code)


# ---- shared -----------------------------------------------------------------------------------


def _shown(folder: Path, root: Path) -> str:
    """A folder as a path relative to the project folder, with `/` (never absolute)."""
    try:
        rel = os.path.relpath(os.path.abspath(folder), os.path.abspath(root))
    except ValueError:  # another drive on Windows
        return folder.name
    return PurePosixPath(*Path(rel).parts).as_posix()


def _folders(root: Path, given: Sequence[Path]) -> tuple[list[Path], str]:
    """The library folders of this run and where they come from (`--library`,
    `device-libraries.json`, or `none`)."""
    if given:
        return list(given), "--library"
    try:
        paths = lp.read_pointer(root)
    except lp.PointerError:
        return [], lp.FILE
    return lp.library_folders(root, paths), (lp.FILE if paths else "none")


def _libraries_of(root: Path, given: Sequence[Path]) -> tuple[ll.ProjectLibraries, list[str]]:
    """The project's libraries and their problems in words, with every folder named relative to
    the project folder."""
    libs = ll.project_libraries(root, list(given) or None)
    folders, _source = _folders(root, given)
    return libs, _clean(libs.problems, folders, root)


def _clean(problems: Sequence[str], folders: Sequence[Path], root: Path) -> list[str]:
    out = []
    names = sorted(folders, key=lambda f: -len(str(f)))
    for text in problems:
        for f in names:
            text = text.replace(str(f), _shown(f, root))
        out.append(text)
    return out


def _say_problems(rep: Report, problems: Sequence[str]) -> None:
    for p in problems:
        rep.say(f"note: {p}")


def _record_dict(rec: ImportRecord | None) -> dict[str, Any] | None:
    return None if rec is None else rec.model_dump(mode="json")


def _say_record(rep: Report, rec: ImportRecord, written: bool = True) -> None:
    where = f" written to {RECORDS_FILE}" if written else ""
    rep.say(f"Import record: {rec.id} (SHA-256 {rec.sha256[:12]}){where}.")
    for note in rec.notes:
        rep.say(f"  {note}")


def _records_in(ops: Sequence[Op]) -> list[ImportRecord]:
    return [
        op.obj
        for op in ops
        if isinstance(op, Put)
        and op.collection == "import_records"
        and isinstance(op.obj, ImportRecord)
    ]


def _table(rep: Report, head: tuple[str, ...], rows: Sequence[tuple[str, ...]]) -> None:
    widths = [max(len(r[i]) for r in [head, *rows]) for i in range(len(head))]
    for r in [head, *rows]:
        rep.say("  " + "  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)).rstrip())


def _blocked(project: Project, label: str, ops: list[Op]) -> TransactionError | None:
    """What `History.execute` would say about these ops, tried on a copy of the project."""
    try:
        History(clone_with(project, [])).execute(label, ops)
    except TransactionError as exc:
        return exc
    return None


# ---- libraries --------------------------------------------------------------------------------


def _pointer_path(text: str, root: Path) -> str:
    """A folder as `device-libraries.json` names it: an absolute path relative to the project
    folder, a `/` at the end left out."""
    if Path(text).is_absolute():
        text = _shown(Path(text), root)
    return text.rstrip("/") if text not in ("", "/") else text


def _edit_pointer(args: argparse.Namespace, rep: Report) -> bool:
    """`--add` and `--remove`: write `device-libraries.json`; True when it changed."""
    if args.library:
        raise _Usage("--add and --remove change device-libraries.json; leave out --library.")
    root: Path = args.project
    try:
        paths = lp.read_pointer(root)
    except lp.PointerError as exc:
        raise _Usage(f"{lp.FILE}: {exc} Nothing was changed.") from exc
    new = list(paths)
    for text in args.remove:
        path = _pointer_path(text, root)
        if path not in new:
            raise _Usage(f"{lp.FILE} does not name {path}. Nothing was changed.")
        new.remove(path)
    for text in args.add:
        path = _pointer_path(text, root)
        if problem := lp.path_problem(path):
            raise _Usage(f"{problem} Nothing was changed.")
        if path in new:
            rep.say(f"{lp.FILE} names {path} already.")
            continue
        new.append(path)
    if new == paths:
        return False
    try:
        lp.pointer_document(new)
    except lp.PointerError as exc:
        raise _Usage(f"{exc} Nothing was changed.") from exc
    lp.write_pointer(root, new)
    n = len(new)
    rep.say(f"{lp.FILE} written: {n} device librar{'y' if n == 1 else 'ies'}.")
    rep.say(OUTSIDE_UNDO)
    return True


def _git_words(folder: Path) -> tuple[str, str | None, str | None]:
    git = library_git(folder)
    if git.kind == "none":
        return "not a Git repository", None, None
    if git.kind == "commit":
        return git.note(), git.commit, git.branch or None
    return git.note(), None, None


def _libraries(project: Project, args: argparse.Namespace, rep: Report) -> int:
    root: Path = args.project
    changed = _edit_pointer(args, rep) if (args.add or args.remove) else False
    folders, source = _folders(root, args.library)
    libs, problems = _libraries_of(root, args.library)
    found = {lib.folder: lib for lib in libs.libraries}
    counts: dict[Path, int] = {}
    for dev in libs.devices():
        counts[dev.library.folder] = counts.get(dev.library.folder, 0) + 1
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for folder in folders:
        shown = _shown(folder, root)
        if shown in seen:
            continue
        seen.add(shown)
        lib = found.get(folder)
        git, commit, branch = _git_words(folder) if lib is not None else ("", None, None)
        items.append(
            {
                "path": shown,
                "name": lib.name if lib is not None else "",
                "readable": lib is not None,
                "devices": counts.get(folder, 0),
                "git": git,
                "commit": commit,
                "branch": branch,
            }
        )
    if not items and source == "none":
        rep.say(NO_LIBRARY)
    elif items:
        rep.say(f"Device libraries of this project (from {source}):")
        for it in items:
            if not it["readable"]:
                rep.say(f"  {it['path']}: cannot be read (see below)")
                continue
            n = it["devices"]
            rep.say(f"  {it['path']}: {it['name']}, {n} device{'' if n == 1 else 's'}, {it['git']}")
    if problems:
        rep.say("Problems:")
        for p in problems:
            rep.say(f"  {p}")
    devices: list[dict[str, Any]] | None = None
    if args.devices:
        devices = _device_states(project, libs, rep)
    rep.put(source=source, changed=changed, libraries=items, problems=problems, devices=devices)
    return 0


def _device_states(
    project: Project, libs: ll.ProjectLibraries, rep: Report
) -> list[dict[str, Any]]:
    states = ll.link_states(project, libs)
    out = [
        {
            "device": st.unit_id,
            "follows": st.library_id,
            "state": st.state,
            "library": st.device.library.name if st.device else None,
            "file": st.device.file if st.device else None,
            "message": st.message,
        }
        for st in states
    ]
    if not out:
        rep.say("No device of the libraries or of this project to list.")
        return out
    rep.say("")
    rows = [
        (
            str(d["device"]),
            str(d["state"]),
            str(d["library"] or "-"),
            str(d["file"] or "-"),
            "" if d["follows"] == d["device"] else f"copy of {d['follows']}",
        )
        for d in out
    ]
    _table(rep, ("Device", "State", "Library", "File", ""), rows)
    for d in out:
        if d["message"]:
            rep.say(f"{d['device']}: {d['message']}")
    return out


# ---- add-device -------------------------------------------------------------------------------


def _resolve(libs: ll.ProjectLibraries, name: str) -> ll.LibraryDevice:
    """The library device NAME means: a device in two libraries is refused (exit 1), a name that
    finds no device or more than one is a usage error (exit 2)."""
    try:
        return libs.resolve(name)
    except ll.AmbiguousDeviceError as exc:
        raise _Refused(f"{exc} Nothing was changed.") from exc
    except ll.LinkError as exc:
        raise _Usage(str(exc)) from exc


def _row_dicts(rows: Sequence[ll.DiffRow]) -> list[dict[str, str]]:
    return [
        {
            "device": r.device,
            "connector": r.connector,
            "pin": r.pin,
            "field": r.field,
            "here": r.here,
            "library": r.library,
            "locked_by": r.locked_by,
        }
        for r in rows
    ]


def _say_rows(rep: Report, rows: Sequence[ll.DiffRow]) -> None:
    head = ("Device", "Connector", "Pin", "Field", "In this project", "In the library", "Locked by")
    _table(
        rep,
        head,
        [
            (
                r.device,
                r.connector or "-",
                r.pin or "-",
                r.field,
                r.here or "-",
                r.library or "-",
                r.locked_by or "-",
            )
            for r in rows
        ],
    )


def _taken_text(err: ll.TakenIdError, project: Project, root: Path) -> str:
    if err.linked:
        n = copies.device_count(project, err.unit_id) + 1
        return (
            f"{err}\nNothing was changed. For copies, ask for more of these devices: "
            f"--count {n} (or more). To take the library's version: `update-device {root} "
            f"{err.unit_id}`."
        )
    return (
        f"{err}\nNothing was changed. Either add the library's device under another ID as a copy "
        f"that does not follow the library (--as {err.free_id}), or link the project's device to "
        f"the library and take the library's version (`update-device {root} {err.unit_id} "
        "--apply --adopt`)."
    )


def _say_add_notes(rep: Report, plan: ll.AddPlan) -> None:
    for note in plan.notes:
        rep.say(f"note: {note}")
    for link in plan.skipped:
        rep.say(f"note: {link} could not be mirrored onto a copy (no free connector).")


def _add_device(project: Project, args: argparse.Namespace, rep: Report) -> int:
    root: Path = args.project
    names: list[str] = list(dict.fromkeys(args.name))
    if (args.count != 1 or args.as_id is not None) and len(names) > 1:
        raise _Usage("--count and --as take one device NAME only.")
    if not 1 <= args.count <= copies.MAX_DEVICES:
        raise _Usage(f"--count is a number from 1 to {copies.MAX_DEVICES}.")
    libs, problems = _libraries_of(root, args.library)
    _say_problems(rep, problems)
    if not libs.libraries:
        raise _Usage(NO_LIBRARY)
    rep.put(
        dry_run=args.dry_run,
        changed=False,
        devices=[],
        sources=[],
        records=[],
        notes=[],
        skipped=[],
        taken=None,
    )
    found = list({d.unit_id: d for d in (_resolve(libs, n) for n in names)}.values())
    names = [d.unit_id for d in found]
    rep.put(
        sources=[{"device": d.unit_id, "library": d.library.name, "file": d.file} for d in found]
    )
    try:
        if len(names) == 1:
            plan = ll.plan_add_device(project, libs, names[0], args.count, args.as_id, root=root)
        else:
            plan = ll.plan_add_devices(project, libs, names, root=root)
    except ll.TakenIdError as err:
        rep.put(
            taken={
                "device": err.unit_id,
                "linked": err.linked,
                "free_id": err.free_id,
                "rows": _row_dicts(err.rows),
            }
        )
        if err.rows:
            rep.say(f"How {err.unit_id} of this project differs from the library:")
            _say_rows(rep, err.rows)
        raise _Refused(_taken_text(err, project, root)) from err
    except ll.LinkError as exc:
        raise _Refused(f"{exc} Nothing was changed.") from exc
    recs = _records_in(plan.ops)
    libraries = list(dict.fromkeys(d.library.name for d in found))
    where = (
        f"the librar{'y' if len(libraries) == 1 else 'ies'} {', '.join(libraries)} "
        f"({', '.join(dict.fromkeys(d.file for d in found))})"
    )
    rep.put(
        devices=list(plan.unit_ids),
        records=[_record_dict(r) for r in recs],
        notes=list(plan.notes),
        skipped=list(plan.skipped),
    )
    if args.dry_run:
        rep.say(f"Would add {', '.join(plan.unit_ids)} from {where}.")
        for rec in recs:
            _say_record(rep, rec, written=False)
    _say_add_notes(rep, plan)
    if args.dry_run:
        if (blocked := _blocked(project, plan.label, plan.ops)) is not None:
            print(blocked_text(blocked), file=sys.stderr)
            rep.say("Dry run: this would be blocked. Nothing was changed.")
            return 1
        rep.say("Dry run: nothing was changed.")
        return 0
    History(project).execute(plan.label, plan.ops)
    save_project(project, root)
    rep.say(f"Added {', '.join(plan.unit_ids)} from {where}.")
    for rec in recs:
        _say_record(rep, rec)
    rep.say("Generate harnesses again to connect interfaces to them.")
    rep.put(changed=True)
    return 0


# ---- update-device ----------------------------------------------------------------------------


def _targets(project: Project, libs: ll.ProjectLibraries, args: argparse.Namespace) -> list[str]:
    """The project devices to compare, one per library device (the first of its family)."""
    out: dict[str, str] = {}
    if args.name:
        for name in dict.fromkeys(args.name):
            uid = name
            if uid not in project.units:
                try:
                    uid = libs.resolve(name).unit_id
                except ll.LinkError:
                    uid = ""
            if uid not in project.units:
                raise _Usage(f"There is no device {name} in this project.")
            st = ll.link_state(project, libs, uid)
            if st is None:
                raise _Usage(f"No library of this project holds {name}.")
            out.setdefault(st.library_id, uid)
        return list(out.values())
    for st in ll.link_states(project, libs):
        if st.state == ll.NOT_IN_PROJECT or st.unit_id not in project.units:
            continue
        if st.linked or st.state in (ll.SOURCE_NOT_FOUND, ll.AMBIGUOUS):
            out.setdefault(st.library_id, st.unit_id)
    return list(out.values())


def _entry(
    base: str, family: Sequence[str], state: str, dev: ll.LibraryDevice | None
) -> dict[str, Any]:
    return {
        "device": base,
        "devices": list(family),
        "state": state,
        "library": dev.library.name if dev else None,
        "file": dev.file if dev else None,
        "rows": [],
        "impacts": [],
        "notes": [],
        "result": "not compared",
        "message": "",
        "record": None,
    }


def _update_device(project: Project, args: argparse.Namespace, rep: Report) -> int:
    root: Path = args.project
    if args.name and args.all:
        raise _Usage("give device names or --all, not both.")
    if args.apply and not (args.name or args.all):
        raise _Usage("say which devices to update: NAME ... or --all.")
    if args.adopt and not (args.name and args.apply):
        raise _Usage("--adopt goes with --apply and the device names (not --all).")
    libs, problems = _libraries_of(root, args.library)
    _say_problems(rep, problems)
    if not libs.libraries and not project.import_records:
        raise _Usage(NO_LIBRARY)
    entries: list[dict[str, Any]] = []
    differ = refused = applied = 0
    for uid in _targets(project, libs, args):
        st = ll.link_state(project, libs, uid)
        if st is None:  # pragma: no cover - `_targets` has seen it
            continue
        message = st.message if st.state in (ll.SOURCE_NOT_FOUND, ll.AMBIGUOUS) else ""
        diff: ll.LibraryDiff | None = None
        if not message:
            try:
                diff = ll.library_diff(project, libs, uid)
            except ll.LinkError as exc:
                message = str(exc)
        if diff is None:
            entry = _entry(st.library_id, [uid], st.state, st.device)
            entry["message"] = message
            entries.append(entry)
            rep.say(f"{st.library_id}: {st.state}. {message}")
            if args.apply:  # it cannot be compared, so it is not taken either
                entry["result"] = "refused"
                refused += 1
                print(
                    f"error: {st.library_id}: {message} Nothing of {st.library_id} was changed.",
                    file=sys.stderr,
                )
            continue
        state = diff.state.state if diff.state is not None else st.state
        entry = _entry(diff.library_id, diff.devices, state, diff.device)
        entry.update(
            rows=_row_dicts(diff.rows),
            impacts=list(diff.impacts),
            notes=list(diff.notes),
            result="shown",
        )
        entries.append(entry)
        family = f" (with {', '.join(diff.devices[1:])})" if len(diff.devices) > 1 else ""
        rep.say(
            f"{diff.library_id}{family}: {state}. Library {diff.device.library.name}, "
            f"{diff.device.file}."
        )
        linked = diff.state is not None and diff.state.linked
        differs = bool(diff.rows) and linked
        differ += differs
        if diff.rows:
            _say_rows(rep, diff.rows)
            for line in diff.impacts:
                rep.say(f"  {line}")
            if not linked and not args.apply:
                rep.say(
                    f"  {diff.library_id} was not added from the library; `--apply --adopt` "
                    "links it and takes the library's version."
                )
        for note in diff.notes:
            rep.say(f"  note: {note}")
        if not args.apply:
            continue
        try:
            plan = ll.plan_update_device(project, libs, uid, adopt=args.adopt, root=root)
        except ll.LinkError as exc:
            entry.update(result="refused", message=str(exc))
            refused += 1
            hint = " Add --adopt to link it." if state == ll.NOT_FROM_LIBRARY else ""
            print(
                f"error: {diff.library_id}: {exc} Nothing of {diff.library_id} was changed.{hint}",
                file=sys.stderr,
            )
            continue
        if not plan.ops:
            entry["result"] = "up to date"
            rep.say(f"  {diff.library_id} is as the library has it; nothing to change.")
            continue
        try:
            History(project).execute(plan.label, plan.ops)
        except TransactionError as exc:  # pragma: no cover - the plan was tried on a copy
            entry.update(result="refused", message=str(exc))
            refused += 1
            print(blocked_text(exc), file=sys.stderr)
            continue
        applied += 1
        differ -= differs
        entry.update(result="applied", record=_record_dict(plan.record))
        n = len(plan.diff.rows)
        rep.say(
            f"Took the library's version of {diff.library_id}"
            f"{family}: {n} change{'' if n == 1 else 's'}."
        )
        if plan.record is not None:
            _say_record(rep, plan.record)
        for note in plan.notes:
            if note not in diff.notes:
                rep.say(f"  note: {note}")
    if applied:
        save_project(project, root)
    if not entries:
        rep.say("No device of this project follows a device library.")
    elif not args.apply and differ:
        rep.say(
            f"{differ} device{' differs' if differ == 1 else 's differ'} from the library. "
            "Nothing was changed; add --apply to take the library's version."
        )
    elif not args.apply and all(not e["rows"] and e["result"] == "shown" for e in entries):
        rep.say("Every device that follows a library is up to date.")
    rep.put(
        apply=args.apply, check=args.check, differ=differ, changed=bool(applied), devices=entries
    )
    if refused:
        return 1
    return 1 if args.check and differ else 0


# ---- save-device ------------------------------------------------------------------------------


def _target_library(project: Project, args: argparse.Namespace) -> ll.Library | Path:
    if args.library is not None:
        return Path(args.library)
    libs, _problems = _libraries_of(args.project, [])
    try:
        holder = libs.device(args.device)
    except ll.AmbiguousDeviceError as exc:
        raise _Refused(f"{exc} Nothing was changed.") from exc
    if holder is not None:
        return holder.library
    if len(libs.libraries) == 1:
        return libs.libraries[0]
    if not libs.libraries:
        raise _Usage(
            "This project names no device library; give --library FOLDER, or name one with "
            "`libraries DIR --add FOLDER`."
        )
    raise _Usage(
        f"This project names {len(libs.libraries)} device libraries; say which with "
        "--library FOLDER."
    )


def _save_device(project: Project, args: argparse.Namespace, rep: Report) -> int:
    root: Path = args.project
    if args.device not in project.units:
        raise _Usage(f"There is no device {args.device} in this project.")
    rep.put(device=args.device, library=None, file=None, changed=False, record=None, notes=[])
    target = _target_library(project, args)
    name = target.name if isinstance(target, ll.Library) else ""
    rep.put(library=name or None)
    try:
        saved = ll.plan_save_device(project, target, args.device, args.replace, root=root)
    except LibraryConflict as exc:
        rep.put(file=exc.file)
        raise _Refused(
            f"{exc} Say --replace to replace it, or save the device under another ID."
        ) from exc
    except ll.LinkError as exc:
        raise _Refused(f"{exc}") from exc
    library = saved.record.notes[0].removeprefix("Library: ") if saved.record.notes else name
    rep.put(
        library=library,
        file=saved.file,
        changed=True,
        record=_record_dict(saved.record),
        notes=list(saved.notes),
    )
    rep.say(f"Saved {args.device} to the library {library}: {saved.file}.")
    for note in saved.notes:
        rep.say(f"note: {note}")
    if saved.ops:
        History(project).execute(f"Record the library file of {args.device}", saved.ops)
        save_project(project, root)
        _say_record(rep, saved.record)
    else:
        rep.say(f"The import record {saved.record.id} is up to date.")
    rep.say("Commit the library to share it.")
    return 0


# ---- explain DEVICE ---------------------------------------------------------------------------


def explain_device(
    project: Project, root: Path, unit_id: str, given: Sequence[Path], rep: Report
) -> int:
    """`explain DIR DEVICE`: the library device a project device follows, its state and the import
    record that links it (design section 3, workflow 6). Reads, changes nothing."""
    libs, problems = _libraries_of(root, given)
    unit = project.units[unit_id]
    st = ll.link_state(project, libs, unit_id)
    rec = project.import_records.get(st.record_id) if st is not None and st.record_id else None
    rep.say(f"Device {unit_id} ({unit.name})")
    if st is None:
        rep.say(
            f"{unit_id} is not from a device library: no library of this project holds it, and "
            "no import record links it."
        )
        if not libs.libraries:
            rep.say(NO_LIBRARY)
    else:
        if st.library_id != unit_id:
            rep.say(f"{unit_id} is a copy of {st.library_id} and follows it.")
        where = (
            f"the library {st.device.library.name}, file {st.device.file}"
            if st.device is not None
            else "no library of this project"
        )
        rep.say(f"Library device {st.library_id} in {where}: {st.state}.")
        if st.message:
            rep.say(st.message)
        if st.state == ll.NOT_FROM_LIBRARY:
            rep.say(
                f"No import record links it; `update-device {root} {st.library_id} --apply "
                "--adopt` links it and takes the library's version."
            )
        elif st.state == ll.LIBRARY_CHANGED or st.state == ll.CHANGED_HERE:
            rep.say(f"`update-device {root} {st.library_id}` shows the differences.")
    if rec is not None:
        _say_record(rep, rec, written=False)
        rep.say(f"  read by version {rec.tool_version}")
    _say_problems(rep, problems)
    rep.put(
        device=unit_id,
        name=unit.name,
        follows=st.library_id if st is not None else None,
        state=st.state if st is not None else None,
        library=st.device.library.name if st is not None and st.device is not None else None,
        file=st.device.file if st is not None and st.device is not None else None,
        record=_record_dict(rec),
        message=st.message if st is not None else "",
    )
    return 0
