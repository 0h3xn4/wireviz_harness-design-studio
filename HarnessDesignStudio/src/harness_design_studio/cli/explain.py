# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""`explain`: how a number of the design was made (D-191); `routing`: the tree of a harness.

`explain` is step 1 of the transparency work (D-191); `routing` is 2.3.0 (D-243, section 5.9)."""

import argparse
import json
import sys
from pathlib import Path

from harness_design_studio.api import write_derivations
from harness_design_studio.cli.jsonout import Report, add_json_flag
from harness_design_studio.cli.library import explain_device
from harness_design_studio.core.derive import explain_object, render
from harness_design_studio.core.derive_routing import routing_tree
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import Project

COMMANDS = ("explain", "routing")


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "explain",
        help="explain how the numbers and decisions of a wire, harness, interface, connector, pin or part were made: equation, inputs with units and sources, steps",
        description="Show how the numbers and decisions of one object were made. For a wire: its length, "
        "the choice of its gauge (the gauges tried, the limit of each after derating, its drop, the first that passes; "
        "not part of --all), the current its gauge may carry after derating, the voltage drop over it and its share of "
        "the mass, then its label, its colour, its shield group and the pins at its ends. For a harness: its mass, "
        "whether it is ready to build and each check behind that, its test limits, why its interfaces share it, its shield groups and its connectors; "
        "HARNESS.T001 explains the limits of one test. For an interface: which harness carries it and why, its connectors, the contact current and its pins. "
        "For a connector: why it is the connector (or the mating part) and its label; for CONNECTOR.PIN: why the signal is on that pin; for a shield group (W001-S1): why it exists and its ends. For a segment of the routing (W001-L3): its two nodes, its length and where the length came from (entered or imported; kept by Generate on a harness Generate made) and the wires through it; for a branch point (W001-B2): the segments that meet it and the connectors beyond each; for a splice (W001-X1): its part and, for each node, the ends of the net it joins. "
        "For a part: why the bill of materials has its quantity. For INTERFACE.CONNECTOR (the object of a current-over-contact finding): the limit of the contacts. For each: the equation, the inputs with "
        "their units and where each comes from (a key of config/*.json, a field of the design or "
        "the program), the intermediate results, what the result is checked against, and the "
        "assumptions built into the program that it rests on. The numbers are the ones `generate` "
        "and `drc` use. The last line names the page of docs/models/ that explains the model behind each kind of number shown (`Model page: docs/models/wire-sizing.md`). `--json` prints the same as data (a list; each derivation also has the key `model_page`). With `--all --out FOLDER` it writes "
        "every derivation of the project to FOLDER as `derivations.json` and `derivations.csv`: no "
        "time, user or path is in them, so the same design gives the same files; with `--json` as "
        "well it prints how many it wrote instead of the line of text. Without `--out` nothing "
        "is written.",
    )
    p.add_argument("project", type=Path, help="project folder")
    p.add_argument(
        "object",
        nargs="?",
        metavar="OBJECT",
        help="a wire (W001-001), a harness (W001), a test (W001.T001), an interface (IF-001), a connector (GPSU1-J01), a pin (MTQ1-J01.1), a shield group (W001-S1), a segment (W001-L3), a branch point (W001-B2), a part (EX-WIRE-SINGLE) or INTERFACE.CONNECTOR (IF-001.GPSU1-J01)",
    )
    p.add_argument("--json", action="store_true", help="print the derivations as JSON")
    p.add_argument(
        "--all", action="store_true", help="every derivation of the project (instead of OBJECT)"
    )
    p.add_argument(
        "--out", type=Path, help="with --all: the folder for derivations.json and derivations.csv"
    )
    p.add_argument(
        "--library",
        action="append",
        default=[],
        type=Path,
        metavar="FOLDER",
        help="for a device: a device library folder to use instead of the project's "
        "device-libraries.json (repeat for more)",
    )

    r = sub.add_parser(
        "routing",
        help="show the routing tree of a harness: its segments with their lengths and where each "
        "length came from, its branch points and the wires through each segment",
        description="Show the routing tree of one harness, read only. For each segment (in natural "
        "ID order): its two nodes (a cable connector with the device connector it plugs into, or a "
        "branch point with its name), its length and where the length came from (entered; imported, "
        "with the file and the row of the import record; not set) and, on a harness Generate made, "
        "that Generate keeps it; then the wires through it, those whose one path between their "
        "connectors takes the segment. For each branch point: the connectors beyond it on each "
        "segment that meets it. For each splice (a node of the tree like a connector): its part and the "
        "wires on each node. The rows are those of segments.csv and of the sheet Routing that "
        "`export` writes for a harness with a branch point. A harness with no branch point prints "
        "its segments, if any, and says that it does not branch. Changes nothing. Lengths are "
        "entered in the editor or with `import-lengths`; `explain DIR SEGMENT` and `explain DIR "
        "BRANCH-POINT` explain one of them.",
    )
    r.add_argument("project", type=Path, help="project folder")
    r.add_argument("harness", metavar="HARNESS", help="the harness (W001)")
    add_json_flag(r)


def _routing(args: argparse.Namespace) -> int:
    project = load_project(args.project).project
    if args.harness not in project.harnesses:
        print(f"error: harness {args.harness} does not exist.", file=sys.stderr)
        return 2
    rep = Report(args.json)
    tree = routing_tree(project, args.harness)
    rep.put(**tree.to_dict())
    for line in tree.lines():
        rep.say(line)
    return rep.finish(0)


def _write_all(project: Project, out: Path, rep: Report) -> int:
    written = write_derivations(project, out)
    rep.say(
        f"{written.count} derivations written to {out / 'derivations.json'} and "
        f"{out / 'derivations.csv'} ({written.without_value} without a value: see the column Missing)"
    )
    rep.put(**written.to_dict())
    return 0


def _history(project: Project, object_id: str) -> None:
    """A project with a journal: who changed this object, when, from what to what, why."""
    from harness_design_studio.core import journal

    entries = journal.entries_for(project, object_id)
    if entries:
        print(f"\nHistory of {object_id} (from the change journal):\n" + journal.render(entries))


def run(args: argparse.Namespace) -> int:
    if args.command == "routing":
        return _routing(args)
    if args.all == (args.object is not None):
        print("error: give either OBJECT or --all", file=sys.stderr)
        return 2
    if args.out is not None and not args.all:
        print("error: --out goes with --all", file=sys.stderr)
        return 2
    project = load_project(args.project).project
    if args.all:
        if args.out is None:
            print("error: --all needs --out FOLDER (the files are written there)", file=sys.stderr)
            return 2
        rep = Report(args.json)
        return rep.finish(_write_all(project, args.out, rep))
    if args.object in project.units:  # a device: its library device and the record (D-240)
        rep = Report(args.json)
        code = rep.finish(explain_device(project, args.project, args.object, args.library, rep))
        if not args.json:
            _history(project, args.object)
        return code
    found = explain_object(project, args.object)
    if args.json:
        print(json.dumps([d.to_explain_dict() for d in found], indent=2, ensure_ascii=False))
        return 0
    print("\n\n".join(render(d) for d in found))
    _history(project, args.object)
    pages = list(dict.fromkeys(d.model_page for d in found if d.model_page))
    if pages:  # the last lines: where the model behind each kind of number above is explained
        print()
        print("\n".join(f"Model page: {page}" for page in pages))
    if all(not d.known for d in found):
        print("\nNothing could be explained yet: see what is not set above.", file=sys.stderr)
    return 0
