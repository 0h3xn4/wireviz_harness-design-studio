# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""`document`: the document data of the harness plans, the Cover of each plan (design of 3.0.0
section 10). It shows the data, and sets it through `core.document`: one undo step, recorded in the
change journal when the project keeps one."""

import argparse
import sys
from pathlib import Path

from harness_design_studio.cli import blocked_text
from harness_design_studio.cli.jsonout import Report, add_json_flag
from harness_design_studio.core import document
from harness_design_studio.core.commands import History
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.errors import TransactionError
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import Project

COMMANDS = ("document",)
CONTACT = "contact"


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "document",
        help="show or set the document data of the harness plans (the Cover: system code, title, "
        "company, contact lines; with --harness the number, version, release and title of that "
        "harness's plan)",
        description="The document data that the harness plans (`export --harness-plan`) show on "
        "their Cover. Without an option it is shown. For the project: `--set system=…`, "
        "`--set title=…`, `--set company=…` and the contact lines `--contact LABEL=VALUE` (a line "
        "with that label gets the value, else a line is added at the end; an empty VALUE removes "
        "the line; at most eight lines). With `--harness ID`: `--set number=…`, `--set version=…` "
        "(the plan document's own version; while it is empty the Cover shows the harness "
        "version), `--set release=…` and `--set title=…` of that harness's plan. `--clear FIELD` "
        "empties a field (`--clear contact` removes every contact line). The change is one step, "
        "recorded in the change journal when the project keeps one, and a release does not lock "
        "it. The data goes into project.json, so into the project's Git history: a team that "
        "prefers it can give a role address in place of a person's name and phone.",
    )
    p.add_argument("project", type=Path, help="project folder")
    p.add_argument(
        "--harness",
        default=None,
        metavar="ID",
        help="the harness whose plan the fields belong to (number, version, release, title)",
    )
    p.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help="set one field: system, title or company; with --harness number, version, release "
        "or title (repeat for several)",
    )
    p.add_argument(
        "--contact",
        action="append",
        default=[],
        metavar="LABEL=VALUE",
        help="set the contact line LABEL, for example E-mail=plans@example.org; an empty VALUE "
        "removes it (repeat for several; not with --harness)",
    )
    p.add_argument(
        "--clear",
        action="append",
        default=[],
        metavar="FIELD",
        help="empty a field (contact: every contact line); repeat for several",
    )
    add_json_flag(p)


def mutates(args: argparse.Namespace) -> bool:
    """Whether the command writes the project (it then takes the project lock)."""
    return bool(args.set or args.contact or args.clear)


def _pairs(items: list[str], option: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for item in items:
        key, eq, value = item.partition("=")
        if not eq or not key.strip():
            raise ValueError(f"{option} {item}: write it as {option[2:].upper()}=VALUE")
        out.append((key.strip(), value))
    return out


def _changes(
    project: Project, args: argparse.Namespace
) -> tuple[dict[str, str], list[tuple[str, str]] | None]:
    """The fields and the contact lines the options ask for (`ValueError` names a bad option)."""
    sets = _pairs(args.set, "--set")
    fields: dict[str, str] = {}
    for key, value in sets:
        if key in fields:
            raise ValueError(f"--set gives {key} twice")
        fields[key] = value
    clear_contact = CONTACT in args.clear
    for key in args.clear:
        if key == CONTACT:
            continue
        if key in fields:
            raise ValueError(f"{key} is both set and cleared")
        fields[key] = ""
    if args.harness is not None and (args.contact or clear_contact):
        raise ValueError(
            "the contact lines are the same in every plan of the project; give --contact and "
            "--clear contact without --harness"
        )
    if not args.contact and not clear_contact:
        return fields, None
    lines = (
        [] if clear_contact else [(c.label, c.value) for c in document.document_of(project).contact]
    )
    for label, value in _pairs(args.contact, "--contact"):
        at = next(
            (k for k, (old, _v) in enumerate(lines) if old.casefold() == label.casefold()), None
        )
        if not value.strip():
            if at is not None:
                del lines[at]
        elif at is None:
            lines.append((label, value))
        else:
            lines[at] = (lines[at][0], value)
    return fields, lines


def _show(project: Project, harness: str | None, rep: Report) -> None:
    doc = document.document_of(project)

    def line(word: str, value: str, otherwise: str = "(empty)") -> None:
        rep.say(f"  {word}: {value or otherwise}")

    if harness is None:
        rep.say("Document data of the harness plans:")
        line("System code", doc.system, f"(empty: the plans show the project name '{project.meta.name}')")  # fmt: skip
        line("Title", doc.title, f"(empty: the plans show '{project.meta.name} Harness Plan')")
        line("Company", doc.company)
        if doc.contact:
            rep.say("  Contact lines:")
            for c in doc.contact:
                rep.say(f"    {c.label}: {c.value or '(empty)'}")
        else:
            rep.say("  Contact lines: (none)")
    ids = [harness] if harness is not None else sorted(doc.plans)
    if harness is None and ids:
        rep.say("Plans:")
    for hid in ids:
        plan = document.plan_of(project, hid)
        h = project.harnesses.get(hid)
        rep.say(f"Plan of {hid}:" if harness is not None else f"  {hid}" + ("" if h else " (no such harness)"))  # fmt: skip
        indent = "  " if harness is not None else "    "
        version = f"(empty: the Cover shows the harness version {h.version})" if h else "(empty)"
        title = doc.title or f"{project.meta.name} Harness Plan"
        for key, value, otherwise in (
            ("number", plan.number, "(empty)"),
            ("version", plan.version, version),
            ("release", plan.release, "(empty)"),
            ("title", plan.title, f"(empty: the Cover shows '{title}')"),
        ):
            rep.say(f"{indent}{document.PLAN_FIELDS[key]}: {value or otherwise}")


def run(args: argparse.Namespace) -> int:
    rep = Report(args.json)
    return rep.finish(_run(args, rep))


def _run(args: argparse.Namespace, rep: Report) -> int:
    project = load_project(args.project).project
    if args.harness is not None and args.harness not in project.harnesses:
        print(f"error: harness {args.harness} does not exist.", file=sys.stderr)
        return 2
    changed = False
    if mutates(args):
        if project.read_only:
            print("error: this project is read-only (saved by a newer tool version).", file=sys.stderr)  # fmt: skip
            return 2
        try:
            fields, lines = _changes(project, args)
        except ValueError as exc:
            print(f"error: {exc}.", file=sys.stderr)
            return 2
        try:
            ops = document.plan_document_edit(
                project, harness=args.harness, fields=fields, contact=lines
            )
        except EditError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        try:
            History(project).execute(document.document_label(args.harness), ops)
        except TransactionError as exc:
            print(blocked_text(exc), file=sys.stderr)
            return 1
        changed = bool(ops)
        if changed:
            save_project(project, args.project)
            rep.say("Saved. The harness plans show it from the next `export --harness-plan`.")
        else:
            rep.say("Already up to date.")
    _show(project, args.harness, rep)
    rep.put(changed=changed, harness=args.harness, **document.document_dict(project, args.harness))
    return 0
