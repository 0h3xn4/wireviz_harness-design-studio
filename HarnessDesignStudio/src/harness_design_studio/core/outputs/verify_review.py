# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The independent verifier's own wording of the Review sheet (design of 4.3.0, section 4.6).

`review_rows(project, h, findings)` states the head and every block of the Review sheet of the
build workbook a second time from the project. It imports neither the view of the core
(`core/review.py`) nor the workbook or the tables (`buildsheet.py`, `tables.py`), nor the release
gate (`core/vcs/release.py`): it holds its own copies of the check of a checklist and of its list
hash, of the selection of the findings of a harness (with `drc.locate`, the one place a finding is
placed, and its own rule for the objects and interfaces that belong to the harness), of the order
and the state words of a finding, of the release entry of the version, of the open items of the
readiness checks of *Start here* (`expected_items`, which `verify.py` also counts for that sheet),
of the open values and the sources, and of every heading and sentence. What it does not word a
second time is what the verifier does not word for `system/drc_findings.csv` either: the findings
themselves (the caller runs `checks.find` and `drc.run` and passes them in) and the hand-over list
of engineering values (`configcheck.missing`).

`sheet_rows` lays the expected view out as the rows of the sheet; `verify.py` (`_build_review`)
reads the sheet back and compares it block by block (`out_review`). `tests/test_review_verify.py`
reads the imports of this module and compares `review_rows` with the core's `review_view` on the
examples, the fixtures and random harnesses with random findings, waivers and checklists."""

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from harness_design_studio.core import configcheck, drc
from harness_design_studio.core.checks import Finding
from harness_design_studio.core.deviations import override_lines
from harness_design_studio.core.model import Harness, Project
from harness_design_studio.core.model.physical import LOOSE_ROLE, SPLICE_ROLE, TBD_PART_ID

from .verify_production import _length

Value = str | int

# ---- the words of the sheet, stated here a second time (never imported from core/review.py) ----
SHEET = "Review"
START_LINE = (
    "for the reviewer: the project's checklist with a column to tick, every finding and open value "
    "of this harness, and the sources to look at"
)
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
_SEVERITY = {"error": "error", "warning": "warning", "info": "note"}
CHECKLIST_COLUMNS = ("No.", "Point", "Done (x)", "Note")
FINDING_COLUMNS = ("Severity", "Rule", "Finding", "Object", "Finding text", "State", "Release")
PROJECT_COLUMNS = ("Severity", "Rule", "Finding", "Finding text", "Release")
OPEN_COLUMNS = ("What", "Open", "First items", "Where to see them all", "Release")
SOURCE_COLUMNS = ("Kind", "ID", "What", "Document", "Version", "Link")
_NO_CHECKLIST = (
    "No checklist: this project sets no review_checklist in config/naming.json. Set one with "
    "harness-design-studio config DIR --review-checklist FILE, or under Settings > Project in the "
    "editor; the file design-review-checklist.md of harness-design-studio templates is a start."
)
_NO_PROJECT_FINDING = "No finding is about the whole project."
_NOTHING_OPEN = "Nothing is open."
_HOW_LINES = (
    "Every ID on this sheet can be explained: harness-design-studio explain DIR ID shows the "
    "equation, the inputs and their sources for a wire, a connector, a part or a finding (Finding "
    "column); in the editor, select it and open Why.",
    "harness-design-studio explain DIR --all --out FOLDER writes every derivation of the project "
    "(derivations.json, derivations.csv).",
)
_FIRST = 5  # the items of an open check that are named
_PROJECT_RULES = ("config-invalid", "unchecked-config")  # about the whole project, block 3

# ---- the checklist (design of 4.3.0, section 3.1) --------------------------------------------

_CHECKLIST_FILE, _CHECKLIST_KEY = "naming", "review_checklist"
_MAX_POINTS, _POINT_LENGTH = 100, 300
_BREAKS = frozenset("\n\r\v\f\x1c\x1d\x1e\x85  ")  # what makes a text two lines


def checklist(project: Project) -> tuple[str, ...]:
    """The points of the project's checklist, trimmed, in order; none when the key is not set or
    is not a list of 1 to 100 points, each one line of 1 to 300 characters, each once (compared
    after trimming and folding the case)."""
    config = project.config.get(_CHECKLIST_FILE)
    raw = config.values.get(_CHECKLIST_KEY) if config is not None else None
    if not isinstance(raw, list) or len(raw) > _MAX_POINTS:
        return ()
    seen: set[str] = set()
    out: list[str] = []
    for point in raw:
        if not isinstance(point, str):
            return ()
        text = point.strip()
        if not 1 <= len(text) <= _POINT_LENGTH or _BREAKS.intersection(text):
            return ()
        if text.casefold() in seen:
            return ()
        seen.add(text.casefold())
        out.append(text)
    return tuple(out)


def list_hash(points: Sequence[str]) -> str:
    """The first 8 hexadecimal characters of the SHA-256 of the list as canonical JSON (sorted
    keys, an indent of 2, UTF-8, a line feed at the end)."""
    text = json.dumps(list(points), sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256((text + "\n").encode("utf-8")).hexdigest()[:8]


# ---- which findings belong to a harness (section 4.3) -----------------------------------------


def _carried(h: Harness) -> set[str]:
    return {w.interface_id for w in h.wires if w.interface_id} | set(h.interfaces)


def _belongs(project: Project, h: Harness) -> set[str]:
    """The objects of the harness: itself, its connectors, wires and shields, the interfaces it
    carries, the device connectors it plugs into and the device connectors of those interfaces."""
    carried = _carried(h)
    ids = (
        {h.id} | {c.id for c in h.connectors} | {w.id for w in h.wires} | {s.id for s in h.shields}
    )
    ids |= carried | {c.mates_with for c in h.connectors if c.mates_with}
    for i in carried:
        if i in project.interfaces:
            ids |= {e.connector_id for e in project.interfaces[i].endpoints if e.connector_id}
    return ids


def _used_parts(h: Harness) -> set[str]:
    return {c.part_id for c in h.connectors} | {w.part_id for w in h.wires if w.part_id}


def about_harness(project: Project, h: Harness, findings: Sequence[Finding]) -> list[Finding]:
    """The findings about `h`, in their order: the object is one of the harness's (`_belongs`), or
    `drc.locate` places it in the harness or on an interface it carries, or places it nowhere and
    the object is a part the harness uses. The rules of the whole project are left out."""
    mine, carried, used = _belongs(project, h), _carried(h), _used_parts(h)
    out: list[Finding] = []
    for f in findings:
        if f.rule in _PROJECT_RULES:
            continue
        if f.object_id in mine:
            out.append(f)
            continue
        where = drc.locate(project, f.object_id)
        if where is None:
            if f.object_id in used:
                out.append(f)
        elif where == ("harness", h.id) or (where[0] == "interface" and where[1] in carried):
            out.append(f)
    return out


def _order(f: Finding) -> tuple[int, str]:
    """Open errors, open warnings, open notes, deviations, waived; each by finding ID."""
    if f.waiver is not None:
        return (3 if f.severity == "error" else 4), f.id
    return {"error": 0, "warning": 1}.get(f.severity, 2), f.id


def state_text(f: Finding) -> str:
    if f.waiver is not None:
        why = f.waiver.justification.strip()
        if f.severity == "error":
            return f"accepted as a deviation: {why}"
        return f"waived: {why}"
    if f.waiver_changed:
        return "open: its waiver no longer applies (the finding changed)"
    return "open"


def _release(f: Finding) -> str:
    if f.rule == "part-unapproved":  # the parts of the gate, whether waived or not
        return REASON
    if f.severity == "error" and f.waiver is None:
        return STOPS
    return ""


def _n(count: int, one: str, many: str) -> str:
    return f"{count} {one}" if count == 1 else f"{count} {many}"


# ---- the open items of the readiness checks of *Start here* ----------------------------------

_CHECK_LABELS = (
    "Wires without a length", "Wires without a gauge", "Wires without a colour",
    "Wires without a part", "Pins in use without a termination", "Wires without strip lengths",
    "Pins in use without a contact part", "Parts that are not approved",
)  # fmt: skip
LOOSE_CHECK = "Ends not decided"  # only while the harness has a loose end


def expected_items(project: Project, h: Harness) -> dict[str, tuple[str, ...]]:
    """What is open under each check of *Start here*, in the order of the sheet: wire IDs in the
    order of the harness, CONNECTOR.PIN of each pin in use in the order of the connectors and pins,
    part IDs sorted, and the loose ends sorted (that check only while there is one). `verify.py`
    counts these for *Start here*; the Review sheet names the first of them in natural ID
    order."""
    used: set[tuple[str, str]] = set()
    for w in h.wires:
        used |= {(w.from_connector, w.from_pin), (w.to_connector, w.to_pin)}
    pins = [(c, p) for c in h.connectors for p in c.pins if (c.id, p.id) in used]
    parts = _used_parts(h) - {TBD_PART_ID}
    items: dict[str, tuple[str, ...]] = dict(
        zip(
            _CHECK_LABELS,
            (
                tuple(w.id for w in h.wires if _length(h, w) is None),
                tuple(w.id for w in h.wires if w.gauge_awg is None),
                tuple(w.id for w in h.wires if not w.colour),
                tuple(w.id for w in h.wires if not w.part_id),
                tuple(f"{c.id}.{p.id}" for c, p in pins if p.termination == "unspecified"),
                tuple(w.id for w in h.wires if w.strip_a_mm is None or w.strip_b_mm is None),
                tuple(
                    f"{c.id}.{p.id}"
                    for c, p in pins
                    if not p.contact_part and c.role != SPLICE_ROLE
                ),
                tuple(
                    sorted(
                        pid
                        for pid in parts
                        if pid not in project.parts or project.parts[pid].approval != "approved"
                    )
                ),
            ),
            strict=True,
        )
    )
    loose = tuple(sorted(c.id for c in h.connectors if c.role == LOOSE_ROLE))
    if loose:
        items[LOOSE_CHECK] = loose
    return items


# ---- the view a second time --------------------------------------------------------------------


def _natural(text: str) -> tuple[tuple[tuple[int, int, str], ...], str]:
    """2 before 10, A2 before A10 (the case folded), then the text itself."""
    parts = re.split(r"(\d+)", text)
    key = tuple((0, int(p), "") if p.isdigit() else (1, 0, p.casefold()) for p in parts if p)
    return key, text


@dataclass(frozen=True)
class Block:
    """One block as the verifier expects it: a key, the heading, the columns (none for sentences),
    the rows (each its cells and the ID it is about) and the sentence for no rows."""

    key: str
    heading: str
    columns: tuple[str, ...]
    rows: tuple[tuple[tuple[Value, ...], str], ...]
    empty: str


@dataclass(frozen=True)
class Review:
    """The head and the six blocks of the Review sheet of one harness, as the verifier words them."""

    harness_id: str
    title: str
    version: str
    status: str
    release: str
    points: tuple[str, ...]
    list_hash: str
    blocks: tuple[Block, ...]

    def block(self, key: str) -> Block:
        return next(b for b in self.blocks if b.key == key)


def release_line(project: Project, h: Harness) -> str:
    """Row 3: the change-log entry of kind release of this version (the last by ID)."""
    entries = sorted(
        (
            e
            for e in project.changelog.values()
            if e.kind == "release" and e.harness_id == h.id and e.version == h.version
        ),
        key=lambda e: e.id,
    )
    if not entries:
        return "Release: not released yet."
    e = entries[-1]
    checked = f", checked by {h.checker}" if h.checker else ""
    return f"Release: version {e.version} released on {e.when} by {e.by}{checked}. Comment: {e.comment}"  # fmt: skip


def _checklist(points: tuple[str, ...], digest: str) -> Block:
    heading = "Checklist"
    if points:
        heading = f"Checklist: {_n(len(points), 'point', 'points')} (config/naming.json review_checklist, list {digest})"  # fmt: skip
    rows = tuple(((n, text, "", ""), str(n)) for n, text in enumerate(points, start=1))
    return Block("checklist", heading, CHECKLIST_COLUMNS, rows, _NO_CHECKLIST)


def _findings(h: Harness, mine: list[Finding]) -> Block:
    mine = sorted(mine, key=_order)
    open_ = [f for f in mine if f.waiver is None]
    errors = len([f for f in open_ if f.severity == "error"])
    warnings = len([f for f in open_ if f.severity == "warning"])
    deviations = len([f for f in mine if f.waiver is not None and f.severity == "error"])
    waived = len(mine) - len(open_) - deviations
    heading = (
        f"Findings of {h.id}: {_n(errors, 'error', 'errors')}, "
        f"{_n(warnings, 'warning', 'warnings')}, "
        f"{_n(len(open_) - errors - warnings, 'note', 'notes')} open; {waived} waived, "
        f"{deviations} accepted as {'a deviation' if deviations == 1 else 'deviations'}"
    )
    rows = tuple(
        (
            (_SEVERITY[f.severity], f.rule, f.id, f.object_id, f.title, state_text(f), _release(f)),
            f.id,
        )  # fmt: skip
        for f in mine
    )
    empty = f"No finding of the design rules, the verifier or the logical checks is about {h.id} or what it carries."  # fmt: skip
    return Block("findings", heading, FINDING_COLUMNS, rows, empty)


def _whole_project(findings: Sequence[Finding]) -> Block:
    rows = tuple(
        ((_SEVERITY[f.severity], f.rule, f.id, f.title, _release(f)), f.id)
        for f in sorted((f for f in findings if f.rule in _PROJECT_RULES), key=_order)
    )
    return Block("project", "For the whole project", PROJECT_COLUMNS, rows, _NO_PROJECT_FINDING)


def _first(items: Sequence[str], joiner: str = ", ") -> str:
    shown = joiner.join(items[:_FIRST])
    return f"{shown} and {len(items) - _FIRST} more" if len(items) > _FIRST else shown


def _where(label: str) -> str:
    if label == LOOSE_CHECK:
        return "Production"
    if label.startswith("Pins in use"):
        return "Connectors"
    return "Cut list, Production"


_CHECK_RELEASE = {
    "Wires without a length": STOPS,
    "Wires without a gauge": STOPS,
    LOOSE_CHECK: REASON,
}


def _asbuilt_row(project: Project, h: Harness) -> tuple[tuple[Value, ...], str] | None:
    """The as-built row, only while `release_requires_asbuilt` is true: what is missing or stale
    and the lengths out of their tolerance, from the report of `core.asbuilt`."""
    naming = project.config.get("naming")
    if naming is None or naming.values.get("release_requires_asbuilt") is not True:
        return None
    from harness_design_studio.core import asbuilt

    report = asbuilt.asbuilt_report(project)
    status = next((x for x in report.harnesses if x.harness_id == h.id), None)
    lines = [ln for ln in report.lines if ln.harness_id == h.id]
    started = status is not None and status.started
    missing = status.missing if status is not None else 0
    stale = status.stale if status is not None else 0
    out = [
        f"{ln.subject} {ln.field}" for ln in lines if ln.status == asbuilt.OUT and ln.kind == "wire"
    ]
    if started and not missing and not stale and not out:
        return None
    gap = next((ln for ln in lines if ln.status in (asbuilt.MISSING, asbuilt.STALE)), None)
    first = f"{gap.kind} {gap.subject}: {gap.field}" if gap is not None else (out[0] if out else "")
    count: Value = missing + stale + len(out) if started else "no records"
    return ("As-built records", count, first or "nothing is recorded yet", "As-built", REASON), h.id


def _open_values(project: Project, h: Harness) -> Block:
    rows: list[tuple[tuple[Value, ...], str]] = []
    files = [f"config/{n}.json" for n in sorted(n for n, c in project.config.items() if c.placeholder)]  # fmt: skip
    if files:
        rows.append((("Configuration files still placeholders", len(files), ", ".join(files), "harness-design-studio config DIR", REASON), files[0]))  # fmt: skip
    unset = [f"{need.file}.{need.key}" for need in configcheck.missing(project)]
    if unset:
        rows.append((("Engineering values not set", len(unset), ", ".join(unset), "harness-design-studio config DIR; Settings > Engineering values", ""), unset[0]))  # fmt: skip
    for label, items in expected_items(project, h).items():
        if label == "Parts that are not approved" or not items:
            continue  # the findings of part-unapproved and the sources name every part
        named = sorted(items, key=_natural)  # natural ID order, whatever the order of the wires
        rows.append(((label, len(items), _first(named), _where(label), _CHECK_RELEASE.get(label, "")), named[0]))  # fmt: skip
    types = sorted(
        {
            project.interfaces[i].type_id
            for i in _carried(h)
            if i in project.interfaces
            and project.interfaces[i].type_id in project.interface_types
            and project.interface_types[project.interfaces[i].type_id].unverified
        },
        key=_natural,
    )
    if types:
        rows.append((("Interface types marked as example data", len(types), ", ".join(types), "logical/interface_types.json", ""), types[0]))  # fmt: skip
    marks = override_lines(h)
    if marks:
        rows.append((("Values set by hand (overrides)", len(marks), _first(marks, "; "), "Edit wire; the release comment lists them", ""), h.id))  # fmt: skip
    asbuilt_row = _asbuilt_row(project, h)
    if asbuilt_row is not None:
        rows.append(asbuilt_row)
    return Block("open", "Values still open", OPEN_COLUMNS, tuple(rows), _NOTHING_OPEN)


def _sources(project: Project, h: Harness) -> Block:
    rows: list[tuple[tuple[Value, ...], str]] = []
    for cid in sorted({c.mates_with for c in h.connectors if c.mates_with}, key=_natural):
        box = project.connectors.get(cid)
        if box is not None:
            rows.append((("Device connector", box.id, f"{box.unit_id}:{box.name}", box.source_doc or "not named", box.source_version or "", box.source_link or ""), box.id))  # fmt: skip
    for pid in sorted(_used_parts(h), key=_natural):
        part = project.parts.get(pid)
        if part is None:
            approval, link = "missing from parts list", ""
        else:
            approval = part.approval + (" (example data)" if part.unverified else "")
            link = part.link or ""
        rows.append((("Part", pid, approval, "", "", link), pid))
    empty = f"{h.id} plugs into no device connector and uses no part."
    return Block("sources", "Sources to look at", SOURCE_COLUMNS, tuple(rows), empty)


def review_rows(project: Project, h: Harness, findings: Sequence[Finding]) -> Review:
    """The Review sheet of harness `h` as the verifier words it (design of 4.3.0, section 4.2):
    `findings` are those of `checks.find` and `drc.run`, waived ones included."""
    points = checklist(project)
    digest = list_hash(points) if points else ""
    how = Block("how", "How the numbers were made", (), tuple(((line,), "") for line in _HOW_LINES), "")  # fmt: skip
    return Review(
        h.id,
        f"Review of {h.id}  {h.label or h.name}",
        h.version,
        h.status,
        release_line(project, h),
        points,
        digest,
        (
            _checklist(points, digest),
            _findings(h, about_harness(project, h, findings)),
            _whole_project(findings),
            _open_values(project, h),
            _sources(project, h),
            how,
        ),
    )


def head_rows(review: Review, stamp_line: str, notice: str) -> list[str]:
    """The first five rows of the sheet, one text each."""
    return [
        review.title,
        f"Version {review.version}   ·   status {review.status}   ·   {stamp_line}   ·   {notice}",
        review.release,
        RELEASE_HINT,
        TICK_HINT,
    ]


def block_rows(block: Block) -> list[list[str]]:
    """The rows of one block as the sheet holds them, without the empty row before it and without
    the empty cells at the end of a row: its heading; then its sentences, or the sentence for no
    rows, or its column names and its rows."""
    out = [[block.heading]]
    if not block.columns:
        return out + [[str(cells[0])] for cells, _ref in block.rows]
    if not block.rows:
        return [*out, [block.empty]]
    out.append(list(block.columns))
    for cells, _ref in block.rows:
        values = [str(v) for v in cells]
        while values and values[-1] == "":
            values.pop()
        out.append(values)
    return out


__all__ = [
    "LOOSE_CHECK", "SHEET", "START_LINE", "Block", "Review", "about_harness", "block_rows",
    "checklist", "expected_items", "head_rows", "list_hash", "release_line", "review_rows",
    "state_text",
]  # fmt: skip
