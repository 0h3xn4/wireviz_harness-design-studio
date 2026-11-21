# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The review view of one harness (4.3.0, milestone E3; `docs/ait/DESIGN_4.3_REVIEW_VIEW.md`).

The project's review checklist is the key `review_checklist` of `config/naming.json`: a list of
points, empty by default, because the tool invents no review content (D-11). `points` gives the
accepted list, `list_hash` names it, `points_from_text` reads the list items of a text or Markdown
file (the shipped template `design-review-checklist.md` is one), and `parse_ticked` reads which
points a person says were ticked.

`review_view` gathers, for one harness, what a reviewer checks and where each fact comes from: the
release entry of its version, the checklist, every finding about the harness (one selection,
`vcs.release.harness_findings`, which the release gate uses too), the findings of the whole
project, the values still open, the sources to look at and how a number is explained. It is pure:
no file, no style, no rule run of its own (the caller passes the findings it already has), and it
says of nothing that it passed. Every row comes from a function that already answers its question.
"""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass

from harness_design_studio.core import configcheck
from harness_design_studio.core.checks import Finding
from harness_design_studio.core.deviations import override_lines
from harness_design_studio.core.io.canonical import dumps
from harness_design_studio.core.links import natural_key
from harness_design_studio.core.model import Harness, Project
from harness_design_studio.core.outputs.buildsheet import LOOSE_CHECK, readiness
from harness_design_studio.core.vcs import release
from harness_design_studio.core.vcs.snapshot import carried_interfaces

CHECKLIST_FILE = configcheck.CHECKLIST_FILE
CHECKLIST_KEY = configcheck.CHECKLIST_KEY
MAX_FILE_BYTES = 64 * 1024  # the largest file `config --review-checklist` reads
FIRST_ITEMS = 5  # the items of an open check that are named; the count says how many there are

# ---- the checklist -------------------------------------------------------------------------


def points(project: Project) -> tuple[str, ...]:
    """The points of the project's review checklist, in order, the spaces around each left out;
    empty when the project sets none (not set, null or an empty list) or sets one the check refuses
    (`configcheck.checklist_problem`; `config-invalid` then says why)."""
    config = project.config.get(CHECKLIST_FILE)
    raw = config.values.get(CHECKLIST_KEY) if config is not None else None
    if not isinstance(raw, list) or configcheck.checklist_problem(raw) is not None:
        return ()
    return tuple(str(p).strip() for p in raw)


def list_hash(points: Sequence[str]) -> str:
    """The name of a list of points: the first 8 hexadecimal characters of the SHA-256 of the list
    as canonical JSON. `naming.json` is not frozen by a release, so the hash tells a later reader
    whether a release comment and a sheet speak of the same list."""
    return hashlib.sha256(dumps(list(points))).hexdigest()[:8]


# a list item of Markdown: a task box, a bullet or a number and a full stop, then the text
_ITEM = re.compile(r"(?:[-*+] \[[ xX]\] |[-*+] |[0-9]+\. )(.*)")


def _plain(text: str) -> str:
    """A point as written, without the bold marks and the backticks of Markdown."""
    return text.replace("**", "").replace("`", "").strip()


def points_from_text(text: str) -> list[str]:
    """The points of a text file (design of 4.3.0, section 3.2). When the file has list items (lines
    that start with `- [ ] `, `- [x] `, `- `, `* `, `+ ` or a number and `. `), each list item is a
    point and every other line is skipped (headings, a line such as *Project: ____*); else each line
    that is not empty and does not start with `#` is a point. The list mark, `**` and backticks are
    taken away; nothing else of the text changes. A line left empty by that is no point. The result
    is not checked: `configcheck.checklist_problem` says whether it is a checklist."""
    lines = [line.strip() for line in text.splitlines()]
    items = [m.group(1) for line in lines if (m := _ITEM.fullmatch(line))]
    found = items or [line for line in lines if line and not line.startswith("#")]
    return [p for p in (_plain(x) for x in found) if p]


class TickedError(ValueError):
    """`--ticked` names something that is not a point of the checklist."""

    def __init__(self, got: str, n: int) -> None:
        self.got = got
        super().__init__(
            f"--ticked must be all, none, or point numbers from 1 to {n} such as 1-5,7 "
            f"(got '{got}')."
        )


_NUMBER = re.compile(r"[0-9]+")


def parse_ticked(text: str, n: int) -> frozenset[int]:
    """The point numbers that `text` says were ticked, of a checklist of `n` points: `all`, `none`,
    or numbers and ranges joined by commas (`1-5,7,9-14`; spaces around them do not count). A
    number outside 1 to `n`, a range that runs down, an empty part or anything else raises
    `TickedError` naming the first part that is wrong."""
    word = text.strip().casefold()
    if word == "all":
        return frozenset(range(1, n + 1))
    if word == "none":
        return frozenset()
    out: set[int] = set()
    for raw in text.split(","):
        part = raw.strip()
        low, dash, high = part.partition("-")
        low, high = low.strip(), high.strip() if dash else low.strip()
        if not (_NUMBER.fullmatch(low) and _NUMBER.fullmatch(high)):
            raise TickedError(part, n)
        a, b = int(low), int(high)
        if not 1 <= a <= b <= n:
            raise TickedError(part, n)
        out.update(range(a, b + 1))
    return frozenset(out)


# ---- the view ------------------------------------------------------------------------------

Cell = str | int


@dataclass(frozen=True)
class Row:
    """One row of a block: its cells in the order of the block's columns, and `ref`, the ID the row
    is about (a finding ID, the object of an open value, a device connector or a part; for a point
    of the checklist its number), for the page's *Show* and *Explain*."""

    cells: tuple[Cell, ...]
    ref: str = ""


@dataclass(frozen=True)
class Block:
    """One block of the view: a heading, the column names (none for a block of sentences), the rows,
    and the one sentence that stands in place of the rows when there is none."""

    key: str  # "checklist", "findings", "project", "open", "sources", "how"
    heading: str
    columns: tuple[str, ...]
    rows: tuple[Row, ...]
    empty: str


@dataclass(frozen=True)
class ReviewView:
    """What a reviewer of one harness reads (design of 4.3.0, section 4.2): a head, six blocks."""

    harness_id: str
    title: str  # "Review of W002  aocs to bus"
    version: str
    status: str
    release: str  # "Release: not released yet." or the release entry of the version
    points: tuple[str, ...]
    list_hash: str  # "" without a checklist
    blocks: tuple[Block, ...]

    def block(self, key: str) -> Block:
        return next(b for b in self.blocks if b.key == key)


RELEASE_HINT = (
    "What stops the release is marked in the column Release; a release also needs current outputs, "
    "a name and a comment."
)
TICK_HINT = (
    "Tick a printout, or a copy saved outside the outputs folder: a file in outputs/ that was "
    "changed after the export stops the release (outputs_modified)."
)
STOPS = "stops the release"
REASON = "needs a written reason"
SEVERITY_WORDS = {"error": "error", "warning": "warning", "info": "note"}

CHECKLIST_COLUMNS = ("No.", "Point", "Done (x)", "Note")
FINDING_COLUMNS = ("Severity", "Rule", "Finding", "Object", "Finding text", "State", "Release")
PROJECT_COLUMNS = ("Severity", "Rule", "Finding", "Finding text", "Release")
OPEN_COLUMNS = ("What", "Open", "First items", "Where to see them all", "Release")
SOURCE_COLUMNS = ("Kind", "ID", "What", "Document", "Version", "Link")

NO_CHECKLIST = (
    "No checklist: this project sets no review_checklist in config/naming.json. Set one with "
    "harness-design-studio config DIR --review-checklist FILE, or under Settings > Project in the "
    "editor; the file design-review-checklist.md of harness-design-studio templates is a start."
)
NO_PROJECT_FINDING = "No finding is about the whole project."
NOTHING_OPEN = "Nothing is open."
HOW_LINES = (
    "Every ID on this sheet can be explained: harness-design-studio explain DIR ID shows the "
    "equation, the inputs and their sources for a wire, a connector, a part or a finding (Finding "
    "column); in the editor, select it and open Why.",
    "harness-design-studio explain DIR --all --out FOLDER writes every derivation of the project "
    "(derivations.json, derivations.csv).",
)

# where the items of an open check of *Start here* are listed one by one, by what they are
_WIRE_SHEETS = "Cut list, Production"
_PIN_SHEETS = "Connectors"
_END_SHEETS = "Production"
_PIN_CHECKS = ("Pins in use without a termination", "Pins in use without a contact part")
_PARTS_CHECK = "Parts that are not approved"  # the findings of part-unapproved name each part
_STOPPING_CHECKS = {  # the checks whose open items the release gate refuses
    "Wires without a length": STOPS,  # length_unknown
    "Wires without a gauge": STOPS,  # gauge_pending
    LOOSE_CHECK[0]: REASON,  # loose_end_blockers
}


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _first(items: Sequence[str]) -> str:
    shown = ", ".join(items[:FIRST_ITEMS])
    more = len(items) - FIRST_ITEMS
    return f"{shown} and {more} more" if more > 0 else shown


def _rank(f: Finding) -> tuple[int, str]:
    """Open errors, open warnings, open notes, then deviations, then waived, each by finding ID."""
    if f.waiver is None:
        group = {"error": 0, "warning": 1}.get(f.severity, 2)
    else:
        group = 3 if f.deviation else 4
    return group, f.id


def _state(f: Finding) -> str:
    if f.waiver is not None:
        why = f.waiver.justification.strip()
        return f"accepted as a deviation: {why}" if f.deviation else f"waived: {why}"
    if f.waiver_changed:
        return "open: its waiver no longer applies (the finding changed)"
    return "open"


def _release_word(f: Finding) -> str:
    if (
        f.rule == "part-unapproved"
    ):  # the gate's part_blockers, whether the finding is waived or not
        return REASON
    return STOPS if f.severity == "error" and f.waiver is None else ""


def _release_line(project: Project, h: Harness) -> str:
    entries = [
        e
        for e in project.changelog.values()
        if e.harness_id == h.id and e.version == h.version and e.kind == "release"
    ]
    if not entries:
        return "Release: not released yet."
    e = max(entries, key=lambda x: x.id)
    checked = f", checked by {h.checker}" if h.checker else ""
    return (
        f"Release: version {e.version} released on {e.when} by {e.by}{checked}. "
        f"Comment: {e.comment}"
    )


def _checklist_block(listed: tuple[str, ...], digest: str) -> Block:
    heading = (
        f"Checklist: {_count(len(listed), 'point', 'points')} "
        f"(config/{CHECKLIST_FILE}.json {CHECKLIST_KEY}, list {digest})"
        if listed
        else "Checklist"
    )
    rows = tuple(Row((n, p, "", ""), str(n)) for n, p in enumerate(listed, start=1))
    return Block("checklist", heading, CHECKLIST_COLUMNS, rows, NO_CHECKLIST)


def _findings_block(h: Harness, mine: list[Finding]) -> Block:
    mine = sorted(mine, key=_rank)
    open_ = [f for f in mine if f.waiver is None]
    errors = sum(1 for f in open_ if f.severity == "error")
    warnings = sum(1 for f in open_ if f.severity == "warning")
    notes = len(open_) - errors - warnings
    deviations = sum(1 for f in mine if f.deviation)
    waived = len(mine) - len(open_) - deviations
    heading = (
        f"Findings of {h.id}: {_count(errors, 'error', 'errors')}, "
        f"{_count(warnings, 'warning', 'warnings')}, {_count(notes, 'note', 'notes')} open; "
        f"{waived} waived, {deviations} accepted as "
        f"{'a deviation' if deviations == 1 else 'deviations'}"
    )
    rows = tuple(
        Row(
            (
                SEVERITY_WORDS[f.severity],
                f.rule,
                f.id,
                f.object_id,
                f.title,
                _state(f),
                _release_word(f),
            ),
            f.id,
        )  # fmt: skip
        for f in mine
    )
    empty = (
        f"No finding of the design rules, the verifier or the logical checks is about {h.id} or "
        "what it carries."
    )
    return Block("findings", heading, FINDING_COLUMNS, rows, empty)


def _project_block(findings: Sequence[Finding]) -> Block:
    whole = sorted((f for f in findings if f.rule in release.PROJECT_RULES), key=_rank)
    rows = tuple(
        Row(
            (SEVERITY_WORDS[f.severity], f.rule, f.id, f.title, _release_word(f)),
            f.id,
        )
        for f in whole
    )
    return Block("project", "For the whole project", PROJECT_COLUMNS, rows, NO_PROJECT_FINDING)


def _open_block(project: Project, h: Harness) -> Block:
    rows: list[Row] = []
    placeholders = [f"config/{n}.json" for n in project.placeholder_configs()]
    if placeholders:
        rows.append(
            Row(
                (
                    "Configuration files still placeholders",
                    len(placeholders),
                    ", ".join(placeholders),
                    "harness-design-studio config DIR",
                    REASON,
                ),
                placeholders[0],
            )  # fmt: skip
        )
    unset = [f"{n.file}.{n.key}" for n in configcheck.missing(project)]
    if unset:
        rows.append(
            Row(
                (
                    "Engineering values not set",
                    len(unset),
                    ", ".join(unset),
                    "harness-design-studio config DIR; Settings > Engineering values",
                    "",
                ),
                unset[0],
            )  # fmt: skip
        )
    for check in readiness(project, h):
        if check.label == _PARTS_CHECK or not check.items:
            continue
        where = (
            _END_SHEETS
            if check.label == LOOSE_CHECK[0]
            else _PIN_SHEETS
            if check.label in _PIN_CHECKS
            else _WIRE_SHEETS
        )
        rows.append(
            Row(
                (
                    check.label,
                    len(check.items),
                    _first(check.items),
                    where,
                    _STOPPING_CHECKS.get(check.label, ""),
                ),
                check.items[0],
            )  # fmt: skip
        )
    types = sorted(
        {
            project.interfaces[i].type_id
            for i in carried_interfaces(h)
            if i in project.interfaces
            and (t := project.interface_types.get(project.interfaces[i].type_id)) is not None
            and t.unverified
        },
        key=lambda x: (natural_key(x), x),
    )
    if types:
        rows.append(
            Row(
                (
                    "Interface types marked as example data",
                    len(types),
                    ", ".join(types),
                    "logical/interface_types.json",
                    "",
                ),
                types[0],
            )  # fmt: skip
        )
    overrides = override_lines(h)
    if overrides:
        rows.append(
            Row(
                (
                    "Values set by hand (overrides)",
                    len(overrides),
                    "; ".join(overrides[:FIRST_ITEMS])
                    + (
                        f" and {len(overrides) - FIRST_ITEMS} more"
                        if len(overrides) > FIRST_ITEMS
                        else ""
                    ),
                    "Edit wire; the release comment lists them",
                    "",
                ),
                h.id,
            )  # fmt: skip
        )
    if release.asbuilt_gate_on(project):
        state = release.asbuilt_open(project, h.id)
        if state.incomplete or state.lengths_out:
            count: Cell = (
                state.missing + state.stale + len(state.lengths_out)
                if state.started
                else "no records"
            )
            first = state.first_open or (state.lengths_out[0] if state.lengths_out else "")
            rows.append(
                Row(
                    (
                        "As-built records",
                        count,
                        first or "nothing is recorded yet",
                        "As-built",
                        REASON,
                    ),
                    h.id,
                )  # fmt: skip
            )
    return Block("open", "Values still open", OPEN_COLUMNS, tuple(rows), NOTHING_OPEN)


def _approval(project: Project, pid: str) -> str:
    """The approval of a part as the *Parts* sheet words it (`tables.bom`)."""
    part = project.parts.get(pid)
    if part is None:
        return "missing from parts list"
    return part.approval + (" (example data)" if part.unverified else "")


def _sources_block(project: Project, h: Harness) -> Block:
    rows: list[Row] = []
    boxes = {c.mates_with for c in h.connectors if c.mates_with}
    for cid in sorted(boxes, key=lambda x: (natural_key(x), x)):
        box = project.connectors.get(cid)
        if box is None:  # the verifier reports a connector that plugs into nothing (mate_missing)
            continue
        rows.append(
            Row(
                (
                    "Device connector",
                    box.id,
                    f"{box.unit_id}:{box.name}",
                    box.source_doc or "not named",
                    box.source_version or "",
                    box.source_link or "",
                ),
                box.id,
            )  # fmt: skip
        )
    used = {c.part_id for c in h.connectors} | {w.part_id for w in h.wires if w.part_id}
    for pid in sorted(used, key=lambda x: (natural_key(x), x)):
        part = project.parts.get(pid)
        link = part.link if part is not None and part.link else ""
        rows.append(Row(("Part", pid, _approval(project, pid), "", "", link), pid))
    empty = f"{h.id} plugs into no device connector and uses no part."
    return Block("sources", "Sources to look at", SOURCE_COLUMNS, tuple(rows), empty)


def review_view(project: Project, h: Harness, findings: Sequence[Finding]) -> ReviewView:
    """The review view of harness `h`: the head and the six blocks of the design of 4.3.0 (section
    4.2), as plain values. `findings` are those of `checks.find` and `drc.run` that the caller has
    already (waived ones included), so the rules are not run once per harness."""
    listed = points(project)
    digest = list_hash(listed) if listed else ""
    blocks = (
        _checklist_block(listed, digest),
        _findings_block(h, release.harness_findings(project, h, findings)),
        _project_block(findings),
        _open_block(project, h),
        _sources_block(project, h),
        Block(
            "how", "How the numbers were made", (), tuple(Row((line,)) for line in HOW_LINES), ""
        ),
    )
    return ReviewView(
        h.id,
        f"Review of {h.id}  {h.label or h.name}",
        h.version,
        h.status,
        _release_line(project, h),
        listed,
        digest,
        blocks,
    )
