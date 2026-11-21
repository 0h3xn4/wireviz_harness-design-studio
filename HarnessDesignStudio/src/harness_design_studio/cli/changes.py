# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Change-control commands: review, release, new-version (older name revise), diff, compare, log."""

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any

from harness_design_studio.cli import blocked_text
from harness_design_studio.cli.jsonout import Report, add_json_flag
from harness_design_studio.core.commands import History
from harness_design_studio.core.errors import HarnessError, SaveError
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.vcs import diff as vdiff
from harness_design_studio.core.vcs.release import (
    ReleasePlan,
    major_note,
    pinout_note,
    plan_new_version,
    plan_release,
    plan_submit_review,
)
from harness_design_studio.core.vcs.report import baselines_of, changelog_rows, working_diff
from harness_design_studio.core.vcs.versions import KINDS, is_version, letter_to_version

COMMANDS = ("review", "release", "new-version", "revise", "diff", "compare", "log")
NEW_VERSION = ("new-version", "revise")  # `revise` is the older name of `new-version` (Q30)
OPTIONS = {
    "by": "--by", "comment": "--comment", "checker": "--checker", "date": "--date", "kind": "--kind",
    "reason": "--accept-placeholders / --accept-unapproved-parts / --accept-loose-ends / --accept-asbuilt",
    "ticked": "--ticked",
}  # fmt: skip


_PARSERS: dict[str, argparse.ArgumentParser] = {}


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    def add(
        name: str, text: str, *, harness: bool = True, listed: bool = True
    ) -> argparse.ArgumentParser:
        # a command that is not listed is an older name: it works, but `--help` lists the new one
        p = (
            sub.add_parser(name, help=text, description=text)
            if listed
            else sub.add_parser(name, description=text)
        )
        _PARSERS[name] = p
        p.add_argument("project", type=Path, help="project folder")
        if harness:
            p.add_argument("harness", help="harness ID, for example W001")
        add_json_flag(p)
        return p

    def who(p: argparse.ArgumentParser, comment: bool) -> None:
        p.add_argument(
            "--by",
            default=None,
            help="your name, as you type it (recorded in the change log; required: no name is "
            "taken from Git or from the computer)",
        )
        if comment:
            p.add_argument(
                "--comment", required=True, help="what changed or why (at least 10 characters)"
            )
        p.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")

    who(add("review", "submit a draft harness for review"), False)
    r = add(
        "release",
        "release a harness: baseline, change log entry and lock (blocked while checks fail)",
    )
    who(r, True)
    r.add_argument(
        "--checker",
        default=None,
        help="who checked it (title block; required in a project that requires different people)",
    )
    r.add_argument(
        "--accept-placeholders",
        metavar="REASON",
        default=None,
        help="release although configuration files are still placeholders: the reason "
        "(at least 10 characters) is kept in the change log and the baseline",
    )
    r.add_argument(
        "--accept-unapproved-parts",
        metavar="REASON",
        default=None,
        help="release although the harness uses parts that are not approved (or are example "
        "data): the reason (at least 10 characters) is kept in the change log and the baseline",
    )
    r.add_argument(
        "--accept-asbuilt",
        metavar="REASON",
        default=None,
        help="release although the as-built records of the harness are incomplete or a recorded "
        "length is out of tolerance (only asked for in a project that sets release_requires_asbuilt "
        "in config/naming.json): the reason (at least 10 characters) is kept in the change log "
        "and the baseline",
    )
    r.add_argument(
        "--accept-loose-ends",
        metavar="REASON",
        default=None,
        help="release although the harness has a loose end (a cable end with no connector chosen "
        "and not plugged into a device): the reason (at least 10 characters) is kept in the "
        "change log and the baseline",
    )
    r.add_argument(
        "--ticked",
        metavar="POINTS",
        default=None,
        help="the points of the project's review checklist (review_checklist in "
        "config/naming.json) that you say were ticked: all, none, or point numbers and ranges "
        "such as 1-5,7,9-14; the comment of the release records them with the list hash and "
        "names the points not ticked; points not ticked do not stop the release",
    )
    for name, listed in (("new-version", True), ("revise", False)):
        text = (
            "start a new version of a released harness: --kind major (not compatible with the "
            "versions before it), minor (adds something and stays compatible) or patch (a fix that "
            "stays compatible); on a draft after a release, before its review, it chooses the kind "
            "again and works the version out again from the released one; `revise` is the older "
            "name of this command"
            if listed
            else "the older name of `new-version`: start a new version of a released harness "
            "(--kind major, minor or patch)"
        )
        nv = add(name, text, listed=listed)
        who(nv, True)
        nv.add_argument(
            "--kind",
            required=True,
            choices=KINDS,
            help="major: not compatible with the versions before it; minor: adds something and "
            "stays compatible; patch: a fix that stays compatible (from 1.4.2: 2.0.0, 1.5.0 or "
            "1.4.3)",
        )
    d = add("diff", "show what changed in a harness since a baseline (or between two baselines)")
    d.add_argument(
        "--from",
        dest="rev_from",
        default=None,
        help="baseline version to compare from (default: latest); an old letter is read as its "
        "version (B is 2.0.0)",
    )
    d.add_argument(
        "--to",
        dest="rev_to",
        default=None,
        help="baseline version to compare to (default: the working design); an old letter is "
        "read as its version",
    )
    c = sub.add_parser(
        "compare",
        help="compare two project folders (for example two Git checkouts)",
        description="Compare two project folders object by object.",
    )
    c.add_argument("old", type=Path)
    c.add_argument("new", type=Path)
    add_json_flag(c)
    log = add("log", "print the change log", harness=False)
    log.add_argument("harness", nargs="?", default=None, help="limit to one harness")


NOT_COMPARED = (
    "Not compared: the generation record, the contents of baselines (only their version, date, "
    "name, comment and hash), and the files of the outputs folders."
)


def _today(value: str | None) -> str:
    """An empty --date is a mistake (the date check names it), not a request for today."""
    return date.today().isoformat() if value is None else value


def _apply(path: Path, plan: ReleasePlan, rep: Report, by: str, **extra: Any) -> int:
    if not plan.ok:
        for b in plan.blockers:
            option = OPTIONS.get(b.about or "")
            # a text that starts with its option (`--ticked must be ...`) is not prefixed twice
            where = f"{option}: " if option and not b.message.startswith(option) else ""
            print(f"blocked: [{b.code}] {where}{b.message}", file=sys.stderr)
        rep.put(
            action=plan.label,
            by=by,
            **extra,
            blockers=[
                {"code": b.code, "message": b.message, "about": b.about} for b in plan.blockers
            ],
            outputs=None,
        )
        return 2 if any(b.code == "no_harness" for b in plan.blockers) else 1
    return 0


def _diff_doc(diff: vdiff.Diff) -> dict[str, Any]:
    """A comparison as data: the counts, and each added, removed or changed object with the
    fields that differ."""
    return {
        **diff.counts(),
        "changes": [
            {
                "change": c.change,
                "kind": c.kind,
                "id": c.id,
                "fields": [
                    {"name": f.name, "before": f.before, "after": f.after} for f in c.fields
                ],
            }
            for c in diff.changes
        ],
    }


def run(args: argparse.Namespace) -> int:
    rep = Report(args.json)
    return rep.finish(_run(args, rep))


def _run(args: argparse.Namespace, rep: Report) -> int:
    cmd = args.command
    if cmd == "compare":
        diff = vdiff.diff_projects(load_project(args.old).project, load_project(args.new).project)
        rep.say(
            vdiff.render_markdown(
                "Project comparison", diff, before=str(args.old), after=str(args.new)
            ),
            end="",
        )
        rep.say(NOT_COMPARED)
        rep.put(**_diff_doc(diff), not_compared=NOT_COMPARED)
        return 0
    project = load_project(args.project).project
    if cmd == "log":
        if args.harness is not None and args.harness not in project.harnesses:
            print(f"error: harness {args.harness} does not exist.", file=sys.stderr)
            return 2
        rows = changelog_rows(project, args.harness)
        for row in rows:
            rep.say(" | ".join(row))
        if rep.as_json:
            keys = ["entry", "harness", "version", "event", "by", "date", "comment"]
            entries = [dict(zip(keys, r, strict=True)) for r in rows[1:]]
            rep.put(harness=args.harness, entries=entries)
        return 0
    if cmd == "diff":
        return _diff(project, args, rep)
    if project.read_only:
        print("error: this project is read-only (saved by a newer tool version).", file=sys.stderr)
        return 2
    by = args.by
    if by is None:  # no name is looked up (D-222): the person types it
        _PARSERS[cmd].error(
            "the following arguments are required: --by (type your name; no name is taken from "
            "Git or from the computer)"
        )
    when = _today(args.date)
    folder = args.project / "outputs"
    if cmd == "review":
        plan = plan_submit_review(project, args.harness, by=by, when=when)
    elif cmd == "release":
        plan = plan_release(
            project,
            args.harness,
            by=by,
            checker=args.checker,
            comment=args.comment,
            when=when,
            outputs_folder=folder,
            accept_placeholders=args.accept_placeholders,
            accept_unapproved_parts=args.accept_unapproved_parts,
            accept_asbuilt=args.accept_asbuilt,
            accept_loose_ends=args.accept_loose_ends,
            ticked=args.ticked,
        )
    else:  # new-version, or its older name revise
        plan = plan_new_version(
            project, args.harness, kind=args.kind, by=by, comment=args.comment, when=when
        )
    notes = _notes(project, args, cmd)
    extra: dict[str, Any] = {"kind": args.kind} if cmd in NEW_VERSION else {}  # `--json`: the kind
    extra["notes"] = notes
    blocked = _apply(args.project, plan, rep, by, **extra)
    if blocked:
        return blocked
    try:
        History(project).execute(plan.label, plan.ops)
        save_project(project, args.project)
    except HarnessError as exc:
        print(blocked_text(exc), file=sys.stderr)
        return 2 if isinstance(exc, SaveError) else 1
    rep.say(f"{plan.label}: done.")
    for note in notes:
        rep.say(f"Note: {note}")
    rep.put(action=plan.label, by=by, **extra, blockers=[], outputs=None)
    if cmd == "release":
        return _restamp(args.project, rep)
    return 0


def _notes(project: Any, args: argparse.Namespace, cmd: str) -> list[str]:
    """The notes of section 5.3 of the design of 3.0.0, which change no version and block nothing:
    at review and release, a pinout change at a device in a minor or patch version (Q20); at a new
    version, the note on a major version (Q21)."""
    if args.harness not in project.harnesses:
        return []
    at_new = cmd in NEW_VERSION
    note = major_note(args.kind) if at_new else pinout_note(project, args.harness)
    return [note] if note else []


RESTAMP_HINT = (
    "The release was recorded (see `harness-design-studio log`); only the outputs still show the old status. "
    "Fix the problem, then run `harness-design-studio export` to re-stamp them."
)


def _restamp(path: Path, rep: Report) -> int:
    """After a release the title blocks must show the new status, so write the outputs again."""
    from harness_design_studio.core.outputs.build import (
        DEFAULT_FOLDER,
        build_outputs,
        drawings_exported,
        harness_plan_exported,
        write_outputs,
    )
    from harness_design_studio.core.outputs.verify import verify_outputs

    try:
        project = load_project(path).project
        # the same set as the export before the release: with the drawings and the harness plans
        # only if it had them
        folder = path / DEFAULT_FOLDER
        built = build_outputs(
            project,
            drawings=drawings_exported(folder),
            harness_plan=harness_plan_exported(folder),
        )
        if not verify_outputs(project, built.files).ok:
            print(
                "error: the re-exported outputs failed their self-check; nothing was written.",
                file=sys.stderr,
            )
            print(RESTAMP_HINT, file=sys.stderr)
            return 1
        write_outputs(project, path / DEFAULT_FOLDER, built)
    except (HarnessError, OSError) as exc:
        print(f"error: the outputs could not be re-stamped ({_why(exc)}).", file=sys.stderr)
        print(RESTAMP_HINT, file=sys.stderr)
        return 2
    rep.say(f"Outputs re-exported with the released status ({len(built.files)} files).")
    rep.put(outputs=len(built.files))
    return 0


def _why(exc: Exception) -> str:
    if isinstance(exc, OSError):
        return exc.strerror or "file problem"
    return str(exc).rstrip(".")


def _diff(project: object, args: argparse.Namespace, rep: Report) -> int:
    from harness_design_studio.core.model import Project

    assert isinstance(project, Project)  # noqa: S101 - narrowing for the type checker
    h = project.harnesses.get(args.harness)
    if h is None:
        print(f"error: harness {args.harness} does not exist.", file=sys.stderr)
        return 2
    bases = {b.version: b for b in baselines_of(project, h.id)}
    if not bases:
        print(f"error: {h.id} has no baseline yet; release it first.", file=sys.stderr)
        return 2
    read_as: dict[str, str] = {}
    for given in (args.rev_from, args.rev_to):
        mapped = _read_as(given)
        if mapped is not None and given is not None and given not in read_as:
            read_as[given] = mapped
            rep.say(
                f"{given} is read as version {mapped}: the letters of format 2 became versions at "
                "the upgrade to format 3, the Nth letter N.0.0."
            )
    wanted_from = read_as.get(args.rev_from or "", args.rev_from)
    wanted_to = read_as.get(args.rev_to or "", args.rev_to)
    start = bases.get(wanted_from) if wanted_from else list(bases.values())[-1]
    if start is None:
        print(f"error: {h.id} has no baseline for version {wanted_from}.", file=sys.stderr)
        return 2
    if wanted_to:
        end = bases.get(wanted_to)
        if end is None:
            print(f"error: {h.id} has no baseline for version {wanted_to}.", file=sys.stderr)
            return 2
        diff = vdiff.diff_snapshots(start.snapshot, end.snapshot)
        rep.say(
            vdiff.render_markdown(f"{h.id}: version {start.version} to {end.version}", diff),
            end="",
        )
        to = end.version
    else:
        diff = working_diff(project, h, start)
        rep.say(
            vdiff.render_markdown(f"{h.id}: working design against version {start.version}", diff),
            end="",
        )
        to = "working"
    rep.put(harness=h.id, **{"from": start.version, "to": to}, read_as=read_as, **_diff_doc(diff))
    return 0


def _read_as(given: str | None) -> str | None:
    """The version an old letter given to `--from` or `--to` is read as (design of 3.0.0 section
    5.4, Q18: `B` is `2.0.0`), or None for a version, an empty value and any other text, which are
    looked up as they are."""
    if not given or is_version(given):
        return None
    return letter_to_version(given)
