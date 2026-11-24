# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Starting points shipped with the tool: example projects and import templates.

`create_project` makes a new project folder from an example (so a beginner can start from
something that works) with a `.gitattributes` for teams that use Git; `copy_import_templates`
copies the CSV, netlist and script templates.
Both only read the bundled files and write where the caller says; nothing is overwritten.
"""

import csv
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from harness_design_studio.core.errors import HarnessError
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.mergefix import write_gitattributes
from harness_design_studio.core.model import Project, evolve
from harness_design_studio.resources import examples_path


class TemplateError(HarnessError):
    """A template cannot be used (unknown name, folder not empty, files missing)."""


START = "start"  # the group of the five projects of 1.0.0, listed first: where a newcomer begins
FEATURE = "feature"  # the group of the small projects that show one feature each (design of 5.1.0)
GROUPS = (START, FEATURE)  # in the order of `new --list`, the New project dialog and the record


@dataclass(frozen=True)
class TemplateInfo:
    name: str
    title: str
    summary: str
    group: str  # one of GROUPS


# The one list of the examples: name, title (the project name of the shipped folder), the line of
# `new --list` and the group, in the order of the list. The folders are built by
# tools/build_examples.py, which reads the titles from here.
TEMPLATES = (
    TemplateInfo(
        "blank",
        "My project",
        "An empty project: starter parts and interface types, no devices.",
        START,
    ),
    TemplateInfo(
        "first-steps",
        "First steps: reaction wheel link",
        "Three devices, a power link and an RS-422 link. Nothing is generated yet: start here.",
        START,
    ),
    TemplateInfo(
        "minimal-satellite",
        "Minimal satellite",
        "Seven devices, nominal only: power, computer, radio, wheel and sun sensor. Adapt it.",
        START,
    ),
    TemplateInfo(
        "small-satellite",
        "Small satellite (reference)",
        "14 devices with nominal and redundant chains. Generate it to see a realistic system.",
        START,
    ),
    TemplateInfo(
        "flatsat",
        "Flatsat (EXAMPLE numbers, not engineering data)",
        "A complete bench: 23 flight and ground devices, generated, with example numbers.",
        START,
    ),
    TemplateInfo(
        "full-connectors",
        "Full connectors",
        "Three devices whose connectors have a signal on every pin: fixed pinouts, ports and pin "
        "rows; generated.",
        FEATURE,
    ),
    TemplateInfo(
        "names-and-ports",
        "Names and ports",
        "OBC1 talks to TTC1 and TTC2 on one connector; its ports are named after them, and a "
        "signal map reads the team's words.",
        FEATURE,
    ),
    TemplateInfo(
        "splice-by-hand",
        "Splice by hand (EXAMPLE)",
        "A power line drawn by hand from one output to two devices through two splices of an "
        "EXAMPLE part.",
        FEATURE,
    ),
    TemplateInfo(
        "splice-from-connection",
        "Splice from a connection (EXAMPLE)",
        "A connection that joins one pin to two (a junction), with pin currents; its harness "
        "carries the splices.",
        FEATURE,
    ),
    TemplateInfo(
        "branching-harness",
        "Branching harness (EXAMPLE)",
        "Four devices; Generate makes harnesses that branch where one connector serves two "
        "devices.",
        FEATURE,
    ),
    TemplateInfo(
        "loose-cable-end",
        "Loose cable end (EXAMPLE)",
        "A cable from a port with its far end loose, and a leg added to it; a release asks for a "
        "reason.",
        FEATURE,
    ),
    TemplateInfo(
        "shields-and-ends",
        "Shields and their ends (EXAMPLE)",
        "A grounding concept, shield groups, pigtails landed on pins and 360-degree ends on "
        "backshells.",
        FEATURE,
    ),
    TemplateInfo(
        "lengths-to-the-face",
        "Lengths to the face (EXAMPLE)",
        "Segments measured to the mating face; the depth of each connector and backshell is "
        "taken off each wire.",
        FEATURE,
    ),
    TemplateInfo(
        "released-harness",
        "Released harness (EXAMPLE)",
        "A harness reviewed and released with a checklist, then its next version started: diff, "
        "log and the version report.",
        FEATURE,
    ),
    TemplateInfo(
        "overrides-and-deviations",
        "Overrides and deviations (EXAMPLE)",
        "A value set by hand with its reason, a warning waived and two errors accepted as "
        "deviations.",
        FEATURE,
    ),
    TemplateInfo(
        "build-data-and-as-built",
        "Build data and as-built (EXAMPLE)",
        "Strip lengths, contacts, accessories, a pin colour code and a Cover for the plans; then a "
        "record of what was built.",
        FEATURE,
    ),
    TemplateInfo(
        "imports-from-files",
        "Imports from files (EXAMPLE)",
        "first-steps built from the import templates: parts, lengths, build data, a netlist and a "
        "pinout, each import recorded.",
        FEATURE,
    ),
)


def template_info(name: str) -> TemplateInfo | None:
    """The listed example of that name, or None."""
    return next((t for t in TEMPLATES if t.name == name), None)


def in_group(group: str) -> tuple[TemplateInfo, ...]:
    """The examples of one group, in the order of the list."""
    return tuple(t for t in TEMPLATES if t.group == group)


def _usable(dest: Path) -> bool:
    """A folder that does not exist yet, or exists and is empty."""
    if dest.is_symlink():  # a link (also a dangling one) is never written through
        return False
    return not dest.exists() or (dest.is_dir() and not any(dest.iterdir()))


def _root() -> Path:
    root = examples_path()
    if root is None:
        raise TemplateError("The bundled examples are missing from this installation.")
    return root


def create_project(
    dest: Path,
    template: str,
    name: str | None = None,
    *,
    journal: bool = False,
    annotate_config: bool = False,
) -> Project:
    """Write a new project to `dest` (a missing or empty folder) from the named example. With
    `journal` the project starts a change journal (`journal.jsonl`); the command `new` and the
    editor's New project ask for it, the builders of the examples and the tests do not, so that the
    files they make do not depend on the time or on who ran them. With `annotate_config` every
    config file carries its comments (`_about`: unit, range, source and use of each key; opt-in,
    off by default; `core.annotate`)."""
    known = {t.name: t for t in TEMPLATES}
    if template not in known:
        raise TemplateError(f"Unknown template '{template}'. Choose one of: {', '.join(known)}.")
    if not _usable(dest):
        raise TemplateError(f"{dest} already exists and is not an empty folder; choose a new one.")
    if name is not None and not name.strip():
        raise TemplateError("The project name must not be empty.")
    loaded = load_project(_root() / "projects" / template)
    if loaded.has_errors:
        raise TemplateError(f"The bundled example '{template}' is damaged.")
    project = loaded.project
    if name is not None:
        project.meta = evolve(project.meta, name=name.strip())
    if annotate_config:
        from harness_design_studio.core import annotate

        annotate.annotate(project)
    save_project(project, dest)
    write_gitattributes(dest)  # so that two people who both press Generate can merge (merge-fix)
    if journal:
        from harness_design_studio.core import journal as journal_module

        journal_module.start(project, "New project from the example '" + template + "'.")
        save_project(project, dest)
    return project


def copy_import_templates(dest: Path) -> list[Path]:
    """Copy the import templates into `dest` (a new or empty folder); returns the files made."""
    if not _usable(dest):
        raise TemplateError(f"{dest} already exists and is not an empty folder; choose a new one.")
    source = _root() / "templates"
    if not source.is_dir():
        raise TemplateError("The bundled templates are missing from this installation.")
    shutil.copytree(source, dest, dirs_exist_ok=True)
    return sorted(p for p in dest.rglob("*") if p.is_file())


EXAMPLE_COLOUR_CODE = "pigtail-colour-code-EXAMPLE.csv"
EXAMPLE_CODE_NAME = "example"


def example_colour_code(parts: Sequence[str]) -> dict[str, object]:
    """The colour code of the users' template (`templates/pigtail-colour-code-EXAMPLE.csv`, design
    of 3.0.0 section 6 and appendix A) as an entry of `colour_codes` in `config/harness_plan.json`,
    for the connector `parts` a person names: marked `"example": true` (Q26). It is an example, not
    a standard and not a supplier's table, and it is applied only when a person takes it."""
    path = _root() / "templates" / EXAMPLE_COLOUR_CODE
    if not path.is_file():
        raise TemplateError("The bundled example colour code is missing from this installation.")
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    pins = {pin.strip(): colour.strip() for pin, colour in rows[1:]}
    return {"name": EXAMPLE_CODE_NAME, "parts": list(parts), "pins": pins, "example": True}
