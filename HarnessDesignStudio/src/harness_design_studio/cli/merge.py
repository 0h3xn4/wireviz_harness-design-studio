# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""`merge-fix`: after a Git merge, when two people each pressed Generate, each added entries to the
change journal, or each made a harness or a link with the same ID (M7b, D-231)."""

import argparse
import sys
from pathlib import Path
from typing import Any

from harness_design_studio.cli import quoted
from harness_design_studio.cli.jsonout import Report, add_json_flag
from harness_design_studio.core.errors import SaveError
from harness_design_studio.core.io.fs import atomic_write_bytes
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.issues import errors
from harness_design_studio.core.merge_ids import IdFix
from harness_design_studio.core.mergefix import (
    GENERATION_FILE,
    JOURNAL_FILE,
    current_journal,
    plan_merge_fix,
    record_journal_merge,
    record_renames,
)
from harness_design_studio.core.model import JournalError

COMMANDS = ("merge-fix",)


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "merge-fix",
        help="after a Git merge: keep this side of generated/generation.json and both sides of "
        "the journal, rename the other side of a harness or link ID that both branches made, "
        "record the merge in the journal, generate, check",
        description="After a Git merge. When two people each pressed Generate, "
        "`generated/generation.json` conflicts: this command keeps this branch's version of that "
        "file, then runs `generate` (which writes the record again for the merged design) and "
        "`check`. When both added entries to the change journal (`journal.jsonl`), Git keeps the "
        "lines of both (`merge=union` in `.gitattributes`); if it stopped on the journal instead, "
        "this command keeps both sides' lines. Then it adds one `merge` entry to the journal that "
        "names the last entry of each side. When both branches made a harness or a link with the "
        "same ID (`W005`, `L7`) and different content, this branch's keeps the ID and the other "
        "branch's gets the next free one, with the IDs inside the harness and every link, waiver "
        "and diagram mark of the other branch that names it; it prints each rename and adds one "
        "journal entry that names them. It refuses to rename a harness or link with a release "
        "history (released IDs never change). It refuses, and changes nothing, when any other file "
        "of the project is in conflict, and it writes nothing itself apart from those files, the "
        "journal and what `generate` writes. Commit the result afterwards.",
    )
    p.add_argument("project", type=Path, help="project folder")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="show what merge-fix would do (the files it resolves, the renames) and write nothing",
    )
    add_json_flag(p)


def run(args: argparse.Namespace) -> int:
    rep = Report(args.json)
    return rep.finish(_run(args, rep))


def _merge_journal(folder: Path, rep: Report) -> str:
    """Add the merge entry to the journal; "" when done or not needed, else why not."""
    try:
        merged = record_journal_merge(folder)
    except (JournalError, SaveError) as exc:
        return f"the journal: {exc}"
    if merged:
        rep.say(
            f"{JOURNAL_FILE} holds the entries of {merged} lines of work: one merge entry that "
            "names them is added."
        )
    return ""


def _journal_heads(folder: Path) -> int:
    try:
        journal = current_journal(folder)
    except JournalError:
        return 0
    return 0 if journal is None else len(journal.heads())


def _say_ids(rep: Report, ids: IdFix) -> None:
    """What the IDs part of the plan does, in the words the manual quotes."""
    for rel in ids.handled:
        how = "added" if rel.startswith("physical/harnesses/") else "changed"
        rep.say(f"{rel} is in conflict: both branches {how} it.")
    if ids.same:
        rep.say(
            "Made on both branches with the same content, kept once: " + ", ".join(ids.same) + "."
        )
    if ids.renames:
        rep.say("Renamed (the other branch's; this branch's keep their IDs):")
        for r in ids.renames:
            rep.say(f"  {r.kind} {r.old} -> {r.new}")
            for old, new in r.parts:
                rep.say(f"    {old} -> {new}")
    if ids.moved:
        rep.say("Changed to name the new ID:")
        for line in ids.moved:
            rep.say(f"  {line}")
    for note in ids.notes:
        rep.say(f"Note: {note}")


def _run(args: argparse.Namespace, rep: Report) -> int:
    from harness_design_studio.cli import main as cli

    folder: Path = args.project
    dry: bool = args.dry_run
    shown = quoted(folder)
    if not (folder / "project.json").is_file():
        print(f"error: {folder} is not a project folder.", file=sys.stderr)
        return 2
    plan = plan_merge_fix(folder)
    renamed = [r.to_dict() for r in plan.ids.renames]

    def put(result: str, conflicts: list[str], problem: str, generate: Any, check: Any) -> None:
        rep.put(
            result=result,
            conflicts=conflicts,
            problem=problem,
            generate=generate,
            check=check,
            dry_run=dry,
            renamed=renamed if result in ("planned", "fixed", "undone") else [],
        )

    if plan.nothing_to_do:
        if dry:
            heads = _journal_heads(folder)
            rep.say("No file of this project is in a Git merge conflict.")
            if heads > 1:
                rep.say(
                    f"{JOURNAL_FILE} holds the entries of {heads} lines of work: merge-fix would "
                    "add one merge entry that names them."
                )
            rep.say("Dry run: nothing was written.")
            put("planned" if heads > 1 else "nothing_to_fix", [], "", None, None)
            return 0
        journal_path = folder / JOURNAL_FILE
        before = journal_path.read_bytes() if journal_path.is_file() else None
        why = _merge_journal(folder, rep)
        if why:
            print(f"error: {why} Nothing was changed.", file=sys.stderr)
            put("refused", [], why, None, None)
            return 1
        after = journal_path.read_bytes() if journal_path.is_file() else None
        if after == before:
            rep.say("Nothing to fix: no file of this project is in a Git merge conflict.")
            put("nothing_to_fix", [], "", None, None)
        else:
            rep.say(
                "Done. Commit the journal now: `git add -A`, then `git commit` "
                "(or `git merge --continue`)."
            )
            put("journal_merged", [], "", None, None)
        return 0
    if plan.others:
        print(
            "error: these files of the project are in conflict, and merge-fix only resolves "
            f"{GENERATION_FILE}, {JOURNAL_FILE}, and harnesses, links, waivers and diagram marks "
            "that both branches made; nothing was changed:",
            file=sys.stderr,
        )
        for rel in plan.others:
            print(f"  {rel}", file=sys.stderr)
        print(
            "Resolve them by hand (the manual says how for each file), then run "
            f"`harness-design-studio merge-fix {shown}` again.",
            file=sys.stderr,
        )
        put("refused", list(plan.others), "", None, None)
        return 1
    if plan.problem:
        print(f"error: {plan.problem} Nothing was changed.", file=sys.stderr)
        put("refused", [], plan.problem, None, None)
        return 1
    record = GENERATION_FILE in plan.conflicts
    if plan.new_journal is not None:
        rep.say(f"{JOURNAL_FILE} is in conflict. Keeping the entries of both sides.")
    if record:
        rep.say(
            f"{GENERATION_FILE} is in conflict. Keeping this branch's version of it; "
            "generate writes the record again for the merged design and check tests it."
        )
    _say_ids(rep, plan.ids)
    regenerate = record or plan.ids.regenerate
    if dry:
        if regenerate:
            rep.say("Then it would run generate and check.")
        else:
            rep.say("Then it would run check.")
        rep.say("Dry run: nothing was written.")
        put("planned", list(plan.conflicts), "", None, None)
        return 0
    originals: dict[Path, bytes | None] = {}

    def write(path: Path, data: bytes) -> None:
        if path not in originals:
            originals[path] = path.read_bytes() if path.is_file() else None
        atomic_write_bytes(path, data, backup=False, root=folder)

    if plan.new_journal is not None:
        write(folder / JOURNAL_FILE, plan.new_journal)
    if record:
        path = folder / GENERATION_FILE
        originals[path] = path.read_bytes()
        if plan.new_record is not None:
            write(path, plan.new_record)
    for rel, data in plan.ids.writes:
        write(folder / rel, data)
    loaded = load_project(folder)
    if loaded.has_errors or loaded.project.recovered:
        first = errors(loaded.issues)[0].render() if loaded.has_errors else "parts set aside"
        put("undone", [], "", None, None)
        return _undo(folder, originals, f"the project has damaged files (first: {first})", 2, shown)
    journal_path = folder / JOURNAL_FILE
    if journal_path.is_file():
        originals.setdefault(journal_path, journal_path.read_bytes())
    why = _merge_journal(folder, rep)
    if not why and plan.ids.renames:
        try:
            if record_renames(folder, {r.old: r.new for r in plan.ids.renames}):
                rep.say(f"{JOURNAL_FILE}: one entry that names the renames is added.")
        except (JournalError, SaveError) as exc:
            why = f"the journal: {exc}"
    if why:
        put("undone", [], why, None, None)
        return _undo(folder, originals, why, 2, shown)
    generated = None
    if regenerate:
        steps = Report(
            rep.as_json
        )  # the data of the two steps; in text mode they print as they run
        code = cli._generate(folder, steps) if rep.as_json else cli._generate(folder)
        generated = steps.result(code) if rep.as_json else None
        if code != 0:
            put("undone", [], "", generated, None)
            return _undo(
                folder, originals, "generate did not accept the merged design", code, shown
            )
    rep.say("--- check")
    steps = Report(rep.as_json)
    code = (
        cli._validate(folder, merge_check=True, rep=steps)
        if rep.as_json
        else cli._validate(folder, merge_check=True)
    )
    checked = steps.result(code) if rep.as_json else None
    put("fixed", [], "", generated, checked)
    if code != 0:
        print(
            "check reports errors: fix them as the message says. "
            + (
                "The record is written again."
                if regenerate
                else "The IDs are renamed."
                if plan.ids.renames
                else "The journal is merged."
            ),
            file=sys.stderr,
        )
        return code
    rep.say(
        "Done. "
        + ("The record is written again for the merged design. " if regenerate else "")
        + "Commit the merge now: `git add -A`, then `git commit` (or `git merge --continue`)."
    )
    return 0


def _undo(
    folder: Path, originals: dict[Path, bytes | None], why: str, code: int, shown: str
) -> int:
    """Put the files back as they were found and remove the ones it made: a refused fix leaves no
    trace."""
    for path, data in originals.items():
        if data is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write_bytes(path, data, backup=False, root=folder)
    print(
        f"error: {why}; merge-fix changed nothing. Run `harness-design-studio check {shown}` "
        "to see the problems and fix them first.",
        file=sys.stderr,
    )
    return code
