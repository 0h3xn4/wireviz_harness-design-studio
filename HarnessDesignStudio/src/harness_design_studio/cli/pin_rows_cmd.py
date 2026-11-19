# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""`pin-rows`: the row layout of a connector part or of a box connector (format 4, D-251; design
of 4.0.0 sections 6.1 and 10). It shows the rows and where they come from, and sets them through
the plans of `core/row_layout_edit.py` (the ones the editor and the scripting interface call): one
undo step, recorded in the change journal when the project keeps one. A connector of a harness has
no rows of its own; its rows are shown, read only."""

import argparse
import sys
from pathlib import Path

from harness_design_studio.cli import blocked_text
from harness_design_studio.cli.jsonout import Report, add_json_flag
from harness_design_studio.core import records
from harness_design_studio.core.commands import History, Op
from harness_design_studio.core.edit import EditError, clone_with
from harness_design_studio.core.errors import TransactionError
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import Connector, Project, RowLayout
from harness_design_studio.core.row_layout import (
    from_lengths,
    layout_of,
    layout_text,
    parse_lengths,
    parse_text,
)
from harness_design_studio.core.row_layout_edit import (
    plan_clear_row_layout,
    plan_set_row_layout,
    plan_share_with_part,
)

COMMANDS = ("pin-rows",)


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "pin-rows",
        help="show or set the row layout of a connector part or of a device connector (the rows "
        "of pins on its face, such as 1–11 / 12–21)",
        description="The row layout of a connector: the rows of pins from the top of its face, "
        "and in each row the pins in order along it. A device connector has its own rows when it "
        "has them, else those of its part; a connector of a harness has the rows of its part, "
        "else those of the device connector it plugs into, and is shown read only. Without an "
        "option the rows are shown with where they come from. `--set` takes the short form: rows "
        "separated by /, the pins of a row by spaces or commas, a run of numbered pins written "
        "1–11 (an en dash) or 1:11, and (rings) at the end for the rings of a circular insert, "
        "from the outer ring inwards; - and .. are part of a pin name, never a run. `--lengths "
        "11,10` gives rows numbered one after the other: on a part 1–11 / 12–21, on a device "
        "connector its pins in pin order, eleven then ten. `--clear` removes the part's rows, or "
        "the device connector's own rows (it then takes the rows of its part). `--to-part` moves "
        "the own rows of a device connector to its part, so that every connector of the part has "
        "them, and clears the equal own rows of the other connectors of that part; it is refused "
        "when the part has other rows. A pin twice, a name that is not a pin of the device "
        "connector or more names than the part has pins are refused with the reason. The change "
        "is one step, recorded in the change journal when the project keeps one, and a release "
        "does not lock it. A read-only project refuses it.",
    )
    p.add_argument("project", type=Path, help="project folder")
    which = p.add_mutually_exclusive_group(required=True)
    which.add_argument("--part", default=None, metavar="ID", help="a connector part of the library")
    which.add_argument(
        "--connector",
        default=None,
        metavar="ID",
        help="a device connector (GYRO1-J01), or a connector of a harness (shown read only)",
    )
    change = p.add_mutually_exclusive_group()
    change.add_argument(
        "--set",
        default=None,
        metavar="TEXT",
        help="the rows in the short form, such as '1–11 / 12–21' or '1 3 5 / 2 4 6'",
    )
    change.add_argument(
        "--lengths",
        default=None,
        metavar="N,N…",
        help="the length of each row, such as 11,10 (rows numbered one after the other)",
    )
    change.add_argument(
        "--clear",
        action="store_true",
        help="remove the rows of the part, or the own rows of the device connector",
    )
    ring = p.add_mutually_exclusive_group()
    ring.add_argument(
        "--rings",
        action="store_true",
        help="each row is a ring of a circular insert (its last pin is next to its first)",
    )
    ring.add_argument("--no-rings", action="store_true", help="the rows are straight rows")
    p.add_argument(
        "--to-part",
        action="store_true",
        help="with --connector: use its own rows for every connector of its part",
    )
    add_json_flag(p)


def mutates(args: argparse.Namespace) -> bool:
    """Whether the command writes the project (it then takes the project lock)."""
    return bool(
        args.set is not None
        or args.lengths is not None
        or args.clear
        or args.rings
        or args.no_rings
        or args.to_part
    )


def _usage(args: argparse.Namespace) -> str:
    """A combination of options that means nothing, or ""."""
    if args.to_part and args.connector is None:
        return "--to-part goes with --connector (the rows of a device connector go to its part)"
    if args.to_part and args.clear:
        return "--to-part moves rows to the part; it does not go with --clear"
    if args.clear and (args.rings or args.no_rings):
        return "--rings and --no-rings mark rows; they do not go with --clear"
    return ""


def _connector(project: Project, connector_id: str) -> Connector | None:
    found = project.connectors.get(connector_id)
    if found is not None:
        return found
    return next(
        (c for h in project.harnesses.values() for c in h.connectors if c.id == connector_id),
        None,
    )


def _rings(args: argparse.Namespace, marked: bool) -> bool:
    if args.rings:
        return True
    if args.no_rings:
        if marked:
            raise ValueError("the rows end with (rings) and --no-rings is given; choose one")
        return False
    return marked


def _wanted(project: Project, args: argparse.Namespace) -> RowLayout | None:
    """The layout the options ask for, or None when they set none (`--clear`, `--to-part`
    alone). `ValueError` or `EditError` says what is wrong."""
    target = {"part": args.part, "connector": args.connector}
    if args.set is not None:
        parsed = parse_text(args.set)
        if parsed is None:
            raise ValueError("--set needs the rows; to remove them, use --clear")
        return RowLayout(rows=parsed.rows, rings=_rings(args, parsed.rings))
    if args.lengths is not None:
        lengths = parse_lengths(args.lengths)
        # only for its refusals: an unknown part or connector, a connector of a harness
        plan_clear_row_layout(project, **target)
        pins = None if args.part is not None else project.connectors[args.connector].pins
        layout = from_lengths(lengths, pins)
        return RowLayout(rows=layout.rows, rings=_rings(args, False))
    if args.rings or args.no_rings:
        plan_clear_row_layout(project, **target)  # only for its refusals
        own = (
            project.parts[args.part].row_layout
            if args.part is not None
            else project.connectors[args.connector].row_layout
        )
        name = f"part {args.part}" if args.part is not None else args.connector
        if own is None:
            raise ValueError(
                f"{name} has no rows of its own to mark; give them with --set or --lengths"
            )
        return RowLayout(rows=own.rows, rings=args.rings)
    return None


def _ops(project: Project, args: argparse.Namespace) -> tuple[str, list[Op]]:
    """The label and the ops of the one undo step the options ask for."""
    target = {"part": args.part, "connector": args.connector}
    name = args.part or args.connector
    if args.clear:
        return f"Clear the rows of {name}", plan_clear_row_layout(project, **target)
    layout = _wanted(project, args)
    ops = [] if layout is None else plan_set_row_layout(project, layout, **target)
    if not args.to_part:
        return f"Set the rows of {name}", ops
    shared = plan_share_with_part(clone_with(project, ops), args.connector)
    part = project.connectors[args.connector].part_id
    return f"Use the rows of {name} for every connector of part {part}", [*ops, *shared]


SOURCE_WORDS = {
    "own": "own rows",
    "part": "from part {id}",
    "mated": "from {id}, the device connector it plugs into",
}


def _row_line(number: int, row: tuple[str, ...], connector: str) -> str:
    if not row:
        return f"  Row {number}: (none of its names is a pin of {connector})"
    return f"  Row {number}: {layout_text(RowLayout(rows=[list(row)]))}"


def _show(project: Project, args: argparse.Namespace, rep: Report) -> records.RowLayoutRecord:
    record = records.row_layout_record(project, part=args.part, connector=args.connector)
    if args.part is not None:
        part = project.parts[args.part]
        if part.category != "connector":
            raise EditError(
                f"Part {part.id} is a {part.category} part; only a connector part has rows"
            )
        if part.row_layout is None:
            rep.say(f"Pin rows of part {part.id}: none (give them with --set or --lengths)")
        else:
            rep.say(f"Pin rows of part {part.id}: {record.text}")
            for n, row in enumerate(record.rows, start=1):
                rep.say(_row_line(n, row, part.id))
        return record
    c = _connector(project, args.connector)
    if c is None:  # row_layout_record refuses an unknown connector already
        raise EditError(f"'{args.connector}' is not a connector of the project")
    found = layout_of(project, c)
    cable = c.unit_id is None
    if found is None:
        where = (
            "its part and the device connector it plugs into have none"
            if cable
            else "give them with --set or --lengths, or give its part rows"
        )
        rep.say(f"Pin rows of {c.id}: none ({where})")
    else:
        source = SOURCE_WORDS[found.source].format(id=found.source_id)
        rep.say(f"Pin rows of {c.id}: {record.text or '(no pin of it is in a row)'} ({source})")
        for n, row in enumerate(found.rows, start=1):
            rep.say(_row_line(n, row, c.id))
        if found.outside:
            outside = layout_text(RowLayout(rows=[list(found.outside)]))
            rep.say(f"  In no row: {outside} (listed after the rows)")
        if found.left_out:
            gone = ", ".join(found.left_out)
            rep.say(f"  Not pins of {c.id}: {gone} (left out of its rows; check warns)")
    if cable:
        rep.say(
            "  A connector of a harness has no rows of its own: set them on its part or on the "
            "device connector it plugs into."
        )
    return record


def run(args: argparse.Namespace) -> int:
    rep = Report(args.json)
    return rep.finish(_run(args, rep))


def _run(args: argparse.Namespace, rep: Report) -> int:
    if problem := _usage(args):
        print(f"error: {problem}.", file=sys.stderr)
        return 2
    project = load_project(args.project).project
    changed = False
    if mutates(args):
        try:
            label, ops = _ops(project, args)
        except (EditError, ValueError) as exc:
            print(f"error: {str(exc).rstrip('.')}.", file=sys.stderr)
            return 2
        try:
            History(project).execute(label, ops)
        except TransactionError as exc:
            print(blocked_text(exc), file=sys.stderr)
            return 1
        changed = bool(ops)
        if changed:
            save_project(project, args.project)
            rep.say("Saved.")
        else:
            rep.say("Already up to date.")
    try:
        record = _show(project, args, rep)
    except EditError as exc:
        print(f"error: {str(exc).rstrip('.')}.", file=sys.stderr)
        return 2
    rep.put(changed=changed, **record.to_dict())
    return 0
