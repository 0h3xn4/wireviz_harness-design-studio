# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Review, release and new-version workflow.

A release needs a comment, a name, and a design that passes the gate: no verifier or rule
errors for the harness, harness plans current, every wire sized and measured, outputs that
were exported from the current design, and engineering values that a person has reviewed (no
configuration file marked as a placeholder) and parts that are approved (D-136). A release on
placeholders or with parts that are not approved is possible only with a written reason, which is
kept in the change log and the baseline (D-135). A project that switches on `release_requires_asbuilt`
(`config/naming.json`, off by default) also needs complete as-built records and no length out of
tolerance, or a written reason of the same kind (`asbuilt_blockers`); the records are not frozen. It writes a baseline (a frozen snapshot) and a change log
entry, and locks the harness (see `locks`). The only way to change it afterwards is a new
version (major, minor or patch), which keeps the old baseline.
"""

import os
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from harness_design_studio.core import drc
from harness_design_studio.core.checks import Finding
from harness_design_studio.core.commands import Op, Put
from harness_design_studio.core.deviations import release_note
from harness_design_studio.core.errors import HarnessError
from harness_design_studio.core.generate.lengths import wire_length
from harness_design_studio.core.generation_status import generation_status
from harness_design_studio.core.model import Baseline, ChangeEntry, Harness, Project, evolve
from harness_design_studio.core.model.physical import TBD_PART_ID
from harness_design_studio.core.model.review import ChangeKind
from harness_design_studio.core.verify import verify_project

from .consistency import release_integrity
from .diff import KIND_NAMES
from .hashing import content_hash
from .report import baselines_of
from .roles import date_problem, distinct_roles_on, same_person
from .snapshot import carried_interfaces, normalize, related_ids, snapshot_for
from .versions import (
    KINDS,
    VersionKind,
    bump,
    kind_between,
    pinout_changes,
    pinout_note_due,
    version_key,
)

MIN_COMMENT = 10
MAX_COMMENT = 2000  # the baseline keeps the comment; its limit is in core/model/review.py
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")  # ASCII digits only


def valid_date(text: str) -> bool:
    """A real calendar date written 2026-03-31 (not 2026-02-30, not full-width digits)."""
    if not DATE_RE.fullmatch(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _today() -> date:
    """Today, for the one rule that looks at the clock (`roles.date_problem`); tests replace it."""
    return date.today()


class ReleaseError(HarnessError):
    """The requested change-control step is not possible."""


@dataclass(frozen=True)
class Blocker:
    code: str
    message: str
    object_id: str | None = None
    about: str | None = None  # the input it is about: "by", "comment", "checker", "reason"


@dataclass
class ReleasePlan:
    ops: list[Op] = field(default_factory=list)
    blockers: list[Blocker] = field(default_factory=list)
    label: str = ""

    @property
    def ok(self) -> bool:
        return not self.blockers


def next_version(version: str, kind: VersionKind = "major") -> str:
    """The version after a released `version` (design of 3.0.0 section 5.3): from `1.4.2`, major
    gives `2.0.0`, minor `1.5.0`, patch `1.4.3`."""
    try:
        return bump(version, kind)
    except ValueError as exc:
        raise ReleaseError(str(exc)) from exc


def _next_entry_id(project: Project) -> str:
    n = max((int(k[1:]) for k in project.changelog if re.fullmatch(r"C\d{4,}", k)), default=0)
    return f"C{n + 1:04d}"


def _entry(
    project: Project, h: Harness, kind: ChangeKind, by: str, when: str, comment: str
) -> ChangeEntry:
    return ChangeEntry(
        id=_next_entry_id(project),
        harness_id=h.id,
        version=h.version,
        kind=kind,
        by=by,
        when=when,
        comment=comment,
    )


def text_blockers(
    value: str | None, about: str, what: str, *, limit: int = 200, one_line: bool = True
) -> list[Blocker]:
    """A name, comment or reason must be plain text of a sensible length. Names are one line;
    comments may have line breaks (the reports show them as one line)."""
    if value is None:
        return []
    allowed = "" if one_line else "\n\t"  # what the data model accepts in a text
    bad = any(
        (unicodedata.category(c) in ("Cc", "Cs") and c not in allowed) or c in "\ufffe\uffff"
        for c in value
    )
    if bad:
        kind = "control characters" if not one_line else "control characters or line breaks"
        return [Blocker(f"{about}_invalid", f"{what} must not contain {kind}.", about=about)]
    if len(value.strip()) > limit:
        return [
            Blocker(
                f"{about}_long",
                f"{what} is longer than {limit} characters; shorten it.",
                about=about,
            )
        ]
    return []


def _common(project: Project, hid: str, by: str, comment: str | None, when: str) -> list[Blocker]:
    out: list[Blocker] = []
    if hid not in project.harnesses:
        return [Blocker("no_harness", f"Harness {hid} does not exist.", hid)]
    if not by.strip():
        out.append(
            Blocker("no_name", "Enter your name; it is recorded in the change log.", about="by")
        )
    else:
        out.extend(text_blockers(by, "by", "The name"))
    if comment is not None:
        if len(comment.strip()) < MIN_COMMENT:
            out.append(
                Blocker(
                    "comment_short",
                    f"The comment needs at least {MIN_COMMENT} characters: say what changed or why.",
                    about="comment",
                )
            )
        out.extend(
            text_blockers(comment, "comment", "The comment", limit=MAX_COMMENT, one_line=False)
        )
    if not valid_date(when):
        out.append(Blocker("bad_date", "The date must look like 2026-03-31.", about="date"))
    else:
        last = max((e.when for e in project.changelog.values() if e.harness_id == hid), default="")
        if valid_date(last) and when < last:  # ISO dates sort as dates
            out.append(
                Blocker(
                    "date_before_last",
                    f"The date {when} is earlier than the last change-log entry of {hid} "
                    f"({last}). Use that date or a later one.",
                    about="date",
                )
            )
        elif problem := date_problem(project, when, _today()):  # only with the setting on
            out.append(Blocker(problem[0], problem[1], about="date"))
    return out


def role_blockers(
    project: Project, h: Harness, by: str | None, checker: str | None
) -> list[Blocker]:
    """With the setting `release_distinct_roles` on (`roles.py`): the author, the checker and the
    person who releases are three named, different people. `by` or `checker` of None leaves out
    the check of that name (a dialog that has not asked for it yet). Nothing without the setting."""
    if not distinct_roles_on(project):
        return []
    out: list[Blocker] = []
    author = (h.author or "").strip()
    if not author:
        out.append(
            Blocker(
                "author_missing",
                f"Nobody is recorded as the author of {h.id}, and this project requires three "
                "different people. Submit it for review under the author's name first; someone "
                "else releases it.",
                h.id,
            )
        )
    if checker is not None and not checker.strip():
        out.append(
            Blocker(
                "checker_missing",
                "Type the name of the person who checked it: this project requires an author, a "
                "checker and a person who releases, all different, and every name is typed (none "
                "is taken from Git or from the computer).",
                about="checker",
            )
        )
    people = [("author", author, "by"), ("checker", (checker or "").strip(), "checker"),
              ("person who releases it", (by or "").strip(), "by")]  # fmt: skip
    for i, (role_a, name_a, _) in enumerate(people):
        for role_b, name_b, about in people[i + 1 :]:
            if same_person(name_a, name_b):
                out.append(
                    Blocker(
                        "same_person",
                        f"The {role_a} and the {role_b} must be different people, but both are "
                        f"'{name_a[:60]}'.",
                        about=about,
                    )
                )
    return out


def placeholder_blockers(project: Project, accept_placeholders: str | None) -> list[Blocker]:
    """Configuration files still marked as placeholders block a release unless the person
    releasing gives a written reason (kept in the change log, see `placeholder_note`)."""
    names = project.placeholder_configs()
    if not names:
        return []
    listed = ", ".join(names)
    if accept_placeholders is None:
        return [
            Blocker(
                "placeholder_config",
                f"These configuration files are still placeholders: {listed}. Have an engineer "
                'review the values and set "placeholder" to false in each file '
                "(`harness-design-studio config DIR` lists them). Or release on placeholders with a written "
                "reason (command line: --accept-placeholders REASON); the reason is kept in the "
                "change log.",
            )
        ]
    if len(accept_placeholders.strip()) < MIN_COMMENT:
        return [
            Blocker(
                "placeholder_reason_short",
                f"The reason for releasing on placeholders ({listed}) needs at least "
                f"{MIN_COMMENT} characters.",
            )
        ]
    return []


def placeholder_note(project: Project, by: str, accept_placeholders: str | None) -> str:
    """The sentence added to the comment of a release made on placeholders ('' otherwise)."""
    names = project.placeholder_configs()
    if not names or accept_placeholders is None:
        return ""
    return (
        f" [Released on placeholder configuration ({', '.join(names)}); "
        f"accepted by {by.strip()}: {accept_placeholders.strip()}]"
    )


def unapproved_parts(project: Project, h: Harness) -> list[str]:
    """Parts the harness uses that no one has approved: missing from the parts list, not
    approved, or example data nobody has verified."""
    used = {c.part_id for c in h.connectors} | {w.part_id for w in h.wires if w.part_id}
    used.discard(TBD_PART_ID)  # a loose end is judged by `loose_end_blockers`, not as a part
    out = []
    for pid in sorted(used):
        part = project.parts.get(pid)
        if part is None or part.approval != "approved" or part.unverified:
            out.append(pid)
    return out


def _listed(ids: list[str], limit: int = 5) -> str:
    more = f" and {len(ids) - limit} more" if len(ids) > limit else ""
    return ", ".join(ids[:limit]) + more


def part_blockers(project: Project, h: Harness, accept_unapproved: str | None) -> list[Blocker]:
    """Unapproved parts block a release unless the person releasing gives a written reason."""
    ids = unapproved_parts(project, h)
    if not ids:
        return []
    if accept_unapproved is None:
        return [
            Blocker(
                "parts_unapproved",
                f"{len(ids)} part(s) used by {h.id} are not approved (or are example data): "
                f"{_listed(ids)}. Approve them in the parts list, or release with a written "
                "reason (command line: --accept-unapproved-parts REASON); the reason is kept "
                "in the change log.",
                h.id,
            )
        ]
    if len(accept_unapproved.strip()) < MIN_COMMENT:
        return [
            Blocker(
                "parts_reason_short",
                f"The reason for releasing with parts that are not approved needs at least "
                f"{MIN_COMMENT} characters.",
                h.id,
            )
        ]
    return []


def part_note(project: Project, h: Harness, by: str, accept_unapproved: str | None) -> str:
    """The sentence added to the comment of a release made with unapproved parts ('' otherwise)."""
    ids = unapproved_parts(project, h)
    if not ids or accept_unapproved is None:
        return ""
    return (
        f" [Released with parts that are not approved ({_listed(ids)}); "
        f"accepted by {by.strip()}: {accept_unapproved.strip()}]"
    )


def loose_ends_of(h: Harness) -> list[str]:
    """IDs of the connectors of the harness that are still loose ends (D-200 (e), D-201)."""
    return sorted(c.id for c in h.connectors if c.role == "loose")


def loose_end_blockers(h: Harness, accept_loose_ends: str | None) -> list[Blocker]:
    """A harness with a loose end that nobody has decided cannot be released, unless the person
    releasing gives a written reason (kept in the change log). The reason is its own: the waiver for
    parts that are not approved does not cover an end that is not there yet."""
    ids = loose_ends_of(h)
    if not ids:
        return []
    if accept_loose_ends is None:
        return [
            Blocker(
                "loose_end_unresolved",
                f"{len(ids)} end(s) of {h.id} are loose (no connector chosen, not plugged into a "
                f"device): {_listed(ids)}. Plug them into a device, give them a connector part, or "
                "release with a written reason (command line: --accept-loose-ends REASON); the "
                "reason is kept in the change log.",
                h.id,
            )
        ]
    if len(accept_loose_ends.strip()) < MIN_COMMENT:
        return [
            Blocker(
                "loose_end_reason_short",
                f"The reason for releasing with a loose end needs at least {MIN_COMMENT} "
                "characters.",
                h.id,
                "reason",
            )
        ]
    return []


def loose_end_note(h: Harness, by: str, accept_loose_ends: str | None) -> str:
    """The sentence added to the comment of a release made with a loose end ('' otherwise)."""
    ids = loose_ends_of(h)
    if not ids or accept_loose_ends is None:
        return ""
    return (
        f" [Released with a loose end ({_listed(ids)}); "
        f"accepted by {by.strip()}: {accept_loose_ends.strip()}]"
    )


ASBUILT_GATE_KEY = "release_requires_asbuilt"  # config/naming.json, off by default


def asbuilt_gate_on(project: Project) -> bool:
    """Is the gate on as-built records switched on? Only the value true switches it on; a value that
    is not true or false is an error of the configuration check, and the gate stays off."""
    config = project.config.get("naming")
    return config is not None and config.values.get(ASBUILT_GATE_KEY) is True


@dataclass(frozen=True)
class AsBuiltOpen:
    """What stands between a harness and a release under the gate on as-built records."""

    started: bool  # the harness has records at all
    missing: int  # values the sheet asks of it that nobody recorded
    stale: int  # records about something the design no longer has
    first_open: str  # the first of them, in words
    lengths_out: tuple[str, ...]  # "W001-002 cut length (m)": a length out of its tolerance

    @property
    def incomplete(self) -> bool:
        return not self.started or self.missing > 0 or self.stale > 0


def asbuilt_open(project: Project, hid: str) -> AsBuiltOpen:
    """The as-built records of a harness against the 'needed values' of docs/models/asbuilt.md, from
    the report the `asbuilt` command prints: a harness with no record is incomplete (nothing is
    recorded), and a length is out when the project sets a tolerance and the record is beyond it."""
    from harness_design_studio.core import asbuilt

    report = asbuilt.asbuilt_report(project)
    status = next((x for x in report.harnesses if x.harness_id == hid), None)
    mine = [ln for ln in report.lines if ln.harness_id == hid]
    first = next((ln for ln in mine if ln.status in (asbuilt.MISSING, asbuilt.STALE)), None)
    out = tuple(
        f"{ln.subject} {ln.field}" for ln in mine if ln.status == asbuilt.OUT and ln.kind == "wire"
    )
    return AsBuiltOpen(
        started=status is not None and status.started,
        missing=status.missing if status else 0,
        stale=status.stale if status else 0,
        first_open=f"{first.kind} {first.subject}: {first.field}" if first else "",
        lengths_out=out,
    )


def asbuilt_blockers(project: Project, hid: str, accept_asbuilt: str | None) -> list[Blocker]:
    """With the setting `release_requires_asbuilt` on: a harness whose as-built records are
    incomplete, or have a length out of tolerance, is not released unless the person releasing gives
    a written reason (kept in the change log, see `asbuilt_note`). Nothing without the setting."""
    if not asbuilt_gate_on(project):
        return []
    state = asbuilt_open(project, hid)
    out: list[Blocker] = []
    accept = (
        "or release with a written reason (command line: --accept-asbuilt REASON); the reason is "
        "kept in the change log."
    )
    if state.incomplete:
        if not state.started:
            what = f"{hid} has no as-built records, and this project requires complete ones for a release"  # fmt: skip
        else:
            stale = f" and {state.stale} stale record(s)" if state.stale else ""
            what = f"The as-built records of {hid} are incomplete: {state.missing} value(s) are missing{stale} (first: {state.first_open})"  # fmt: skip
        out.append(
            Blocker(
                "asbuilt_incomplete",
                f"{what} ({ASBUILT_GATE_KEY} in config/naming.json). Record what was built "
                f"(`harness-design-studio export-asbuilt` writes the sheet, `import-asbuilt` reads "
                f"it back), {accept}",
                hid,
            )
        )
    if state.lengths_out:
        out.append(
            Blocker(
                "asbuilt_length_out",
                f"{len(state.lengths_out)} as-built length(s) of {hid} are out of tolerance (first: "
                f"{state.lengths_out[0]}). Check the length or the tolerance (asbuilt_cut_tolerance_mm, "
                f"asbuilt_strip_tolerance_mm in config/generation.json), {accept}",
                hid,
            )
        )
    if not out or accept_asbuilt is None:
        return out
    if len(accept_asbuilt.strip()) < MIN_COMMENT:
        return [
            Blocker(
                "asbuilt_reason_short",
                f"The reason for releasing {hid} without complete as-built records needs at least "
                f"{MIN_COMMENT} characters.",
                hid,
                "reason",
            )
        ]
    return []


def asbuilt_note(project: Project, hid: str, by: str, accept_asbuilt: str | None) -> str:
    """The sentence added to the comment of a release made over the gate on as-built records ('' when
    the setting is off, nothing is open, or no reason was given). It says what was open then."""
    if accept_asbuilt is None or not asbuilt_gate_on(project):
        return ""
    state = asbuilt_open(project, hid)
    parts: list[str] = []
    if state.incomplete:
        parts.append(
            "incomplete (no records)"
            if not state.started
            else f"incomplete ({state.missing} value(s) missing, {state.stale} stale)"
        )
    if state.lengths_out:
        parts.append(f"have a length out of tolerance ({_listed(list(state.lengths_out))})")
    if not parts:
        return ""
    return (
        f" [Released although the as-built records of {hid} are {' and '.join(parts)}; "
        f"accepted by {by.strip()}: {accept_asbuilt.strip()}]"
    )


# The rules whose findings are about the whole project, not about one harness: a wrong engineering
# value and a check that could not run. The review view lists them apart, on every harness, and
# the release gate counts the errors of config-invalid for every harness.
PROJECT_RULES = ("config-invalid", "unchecked-config")


def harness_findings(project: Project, h: Harness, findings: Sequence[Finding]) -> list[Finding]:
    """The findings of `findings` (those of `checks.find` and `drc.run`, waived ones included) that
    are about harness `h`, in their order: the finding's object is one of `related_ids` (the
    harness, its connectors, wires and shields, the interfaces it carries and the device connectors
    it plugs into), or `drc.locate` places it in the harness or on an interface it carries, or
    `drc.locate` places it nowhere and its object is a part the harness uses (`part-unapproved`,
    whose object is a part ID). The findings of `PROJECT_RULES` are about the whole project and
    are not listed. This is the one selection of the findings of a harness: the release gate takes
    its open errors (design of 4.3.0, section 4.3), the review view every severity."""
    related = related_ids(project, h)
    carried = carried_interfaces(h)
    used = {c.part_id for c in h.connectors} | {w.part_id for w in h.wires if w.part_id}
    out: list[Finding] = []
    for f in findings:
        if f.rule in PROJECT_RULES:
            continue
        if f.object_id in related:
            out.append(f)
            continue
        where = drc.locate(project, f.object_id)
        if (
            where == ("harness", h.id)
            or (where is not None and where[0] == "interface" and where[1] in carried)
            or (where is None and f.object_id in used)
        ):
            out.append(f)
    return out


def release_blockers(
    project: Project,
    hid: str,
    *,
    by: str,
    comment: str,
    when: str,
    outputs_folder: Path | None,
    accept_placeholders: str | None = None,
    accept_unapproved_parts: str | None = None,
    checker: str | None = None,
    check_roles: bool = True,
    accept_asbuilt: str | None = None,
    accept_loose_ends: str | None = None,
) -> list[Blocker]:
    out = _common(project, hid, by, comment, when)
    h = project.harnesses.get(hid)
    if h is None:
        return out
    if check_roles:  # a dialog that asks for the names itself leaves this to the dialog
        out.extend(role_blockers(project, h, by, checker or ""))
    out.extend(placeholder_blockers(project, accept_placeholders))
    out.extend(part_blockers(project, h, accept_unapproved_parts))
    out.extend(loose_end_blockers(h, accept_loose_ends))
    out.extend(asbuilt_blockers(project, hid, accept_asbuilt))
    notes = (
        placeholder_note(project, by, accept_placeholders)
        + part_note(project, h, by, accept_unapproved_parts)
        + loose_end_note(h, by, accept_loose_ends)
        + asbuilt_note(project, hid, by, accept_asbuilt)
        + release_note(project, h)
    )
    out.extend(text_blockers(accept_placeholders, "reason", "The reason for releasing on placeholders", limit=MAX_COMMENT, one_line=False))  # fmt: skip
    out.extend(text_blockers(accept_unapproved_parts, "reason", "The reason for releasing with parts that are not approved", limit=MAX_COMMENT, one_line=False))  # fmt: skip
    out.extend(text_blockers(accept_asbuilt, "reason", "The reason for releasing without complete as-built records", limit=MAX_COMMENT, one_line=False))  # fmt: skip
    out.extend(text_blockers(accept_loose_ends, "reason", "The reason for releasing with a loose end", limit=MAX_COMMENT, one_line=False))  # fmt: skip
    out.extend(text_blockers(checker, "checker", "The checker's name"))
    if len(comment.strip() + notes) > MAX_COMMENT and not any(
        b.code == "comment_long" for b in out
    ):
        out.append(
            Blocker(
                "comment_long",
                f"The comment (with the reason for releasing on placeholders) is longer than "
                f"{MAX_COMMENT} characters; shorten it.",
                about="comment",
            )
        )
    if h.status == "released":
        out.append(
            Blocker(
                "already_released",
                f"{hid} is already released (version {h.version}). Start a new version to change it.",
                hid,
            )
        )
    if not h.wires:
        out.append(Blocker("no_wires", f"{hid} has no wires.", hid))
    if h.generated and generation_status(project) == "stale":
        out.append(
            Blocker(
                "generation_stale",
                "The harness plans are out of date. Generate harnesses again first.",
                hid,
            )
        )
    related = related_ids(project, h)
    for issue in verify_project(project).errors:
        if issue.object_id is None or issue.object_id in related:
            out.append(Blocker("verify_error", f"Verifier: {issue.message}", issue.object_id))
    errors = [f for f in drc.run(project) if f.severity == "error" and f.waiver is None]
    mine = {id(f) for f in harness_findings(project, h, errors)}
    for f in errors:
        # a wrong engineering value (config-invalid) affects every harness
        if id(f) in mine or f.rule == "config-invalid":
            out.append(Blocker("rule_error", f.title, f.object_id))
    undecided = [w.id for w in h.wires if w.gauge_awg is None]
    if undecided:
        out.append(
            Blocker(
                "gauge_pending",
                f"{len(undecided)} wire(s) have no gauge decided (first: {undecided[0]}). Fill in the derating values (the file config/derating.json; `harness-design-studio config DIR` lists what is missing) or set the gauge by hand.",
                undecided[0],
            )
        )
    no_length = [w.id for w in h.wires if wire_length(h, w) is None]
    if no_length:
        out.append(
            Blocker(
                "length_unknown",
                f"{len(no_length)} wire(s) have no length (first: {no_length[0]}). Enter the routing segment lengths (`harness-design-studio import-lengths DIR FILE` loads them from a table).",
                no_length[0],
            )
        )
    out.extend(outputs_blockers(project, outputs_folder, hid))
    existing = f"{hid}.{h.version}"
    if existing in project.baselines:
        out.append(
            Blocker(
                "baseline_exists",
                f"Version {h.version} of {hid} already has a baseline; start a new version.",
                hid,
            )
        )
    return out


def _linked_or_read_only(folder: Path) -> str:
    """Why the outputs cannot be written again after the release (the status in the title blocks
    is stamped by a second export), or '' if they can. Checked before anything is committed."""
    if folder.is_symlink() or any(
        (Path(root) / d).is_symlink() for root, dirs, _ in os.walk(folder) for d in dirs
    ):
        return (
            "The outputs folder (or a folder in it) is a link, so the released status could not "
            "be written into the outputs. Replace the link with a real folder and export again."
        )
    if folder.is_dir() and not os.access(folder, os.W_OK | os.X_OK):
        return (
            "The outputs folder cannot be written, so the released status could not be stamped "
            "into the outputs. Make it writable and export again."
        )
    return ""


def outputs_blockers(
    project: Project, folder: Path | None, hid: str | None = None
) -> list[Blocker]:
    from harness_design_studio.core.outputs.build import (
        damaged_files,
        exported_harnesses,
        outputs_content_state,
    )

    if folder is None:
        return [
            Blocker(
                "outputs_unsaved",
                "Save the project to a folder and export the outputs before releasing.",
            )
        ]
    linked = _linked_or_read_only(folder)
    if linked:
        return [Blocker("outputs_linked", linked)]
    state = outputs_content_state(project, folder)
    if state == "none":
        return [
            Blocker(
                "outputs_missing",
                "Outputs have not been exported yet. Export them, review them, then release.",
            )
        ]
    if state != "current":
        return [
            Blocker(
                "outputs_stale",
                "The outputs are out of date (the design changed after the export). Export again.",
            )
        ]
    # the manifest alone proves nothing: the files it lists must still be there and unchanged
    damaged = damaged_files(folder)
    if damaged:
        return [
            Blocker(
                "outputs_modified",
                f"{len(damaged)} output file(s) were changed or removed after the export (first: {damaged[0]}). Export again.",
            )
        ]
    if hid is not None and hid not in (exported_harnesses(folder) or set()):
        return [
            Blocker(
                "outputs_missing",
                f"The exported outputs do not include {hid}. Export all outputs, then release.",
                hid,
            )
        ]
    return []


def plan_release(
    project: Project,
    hid: str,
    *,
    by: str,
    checker: str | None,
    comment: str,
    when: str,
    outputs_folder: Path | None,
    accept_placeholders: str | None = None,
    accept_unapproved_parts: str | None = None,
    accept_asbuilt: str | None = None,
    accept_loose_ends: str | None = None,
) -> ReleasePlan:
    blockers = release_blockers(
        project, hid, by=by, comment=comment, when=when, outputs_folder=outputs_folder,
        accept_placeholders=accept_placeholders, accept_unapproved_parts=accept_unapproved_parts,
        checker=checker, accept_asbuilt=accept_asbuilt, accept_loose_ends=accept_loose_ends,
    )  # fmt: skip
    plan = ReleasePlan(blockers=blockers, label=f"Release {hid}")
    if blockers:
        return plan
    h = project.harnesses[hid]
    released = normalize(
        evolve(
            h,
            status="released",
            author=h.author or by.strip(),
            checker=(checker or "").strip() or None,
            approver=by.strip(),
            released_on=when,
        )
    )
    snapshot = snapshot_for(project, released)
    full_comment = (
        comment.strip()
        + placeholder_note(project, by, accept_placeholders)
        + part_note(project, h, by, accept_unapproved_parts)
        + loose_end_note(h, by, accept_loose_ends)
        + asbuilt_note(project, hid, by, accept_asbuilt)
        + release_note(project, h)
    )
    entry = _entry(project, released, "release", by.strip(), when, full_comment)
    baseline = Baseline(
        id=f"{hid}.{h.version}", harness_id=hid, version=h.version, released_on=when, by=by.strip(),
        comment=full_comment, content_hash=content_hash(project), snapshot=snapshot,
    )  # fmt: skip
    plan.ops = [Put("harnesses", released), Put("baselines", baseline), Put("changelog", entry)]
    plan.label = f"Release {hid} version {h.version}"
    return plan


MAX_BASELINE_ID = 64  # the longest ID (`core.ids`); a baseline ID is `<harness>.<version>`

# ---- the notes of section 5.3 (Q20, Q21): they change no version and block nothing ----------------

MAJOR_NOTE = (
    "A major version says that this harness is not compatible with its earlier versions. The "
    "harness plan template gives such a harness a new ID instead (TH01 becomes TH02, not TH01 "
    "2.0.0)."
)
PINOUT_NOTE = (
    "This version changes the pinout at a device{0}. The harness plan template calls that an "
    "incompatible change."
)
NOTE_LISTED = 5  # the changed objects a pinout note names; the rest are counted


def last_baseline(project: Project, hid: str) -> Baseline | None:
    """The baseline of the highest version of a harness (the released one a new version is worked
    out from), or None when it has none."""
    bases = baselines_of(project, hid)
    return bases[-1] if bases else None


def draft_kind(project: Project, hid: str) -> VersionKind | None:
    """The kind of version a harness that is not released is on its way to (section 5.3): read from
    its version and the version of its last baseline (`versions.kind_between`). None for a harness
    without a baseline (its first release), for a released one, and for a version that is not
    higher than its baseline."""
    h = project.harnesses.get(hid)
    base = last_baseline(project, hid)
    if h is None or base is None or h.status == "released":
        return None
    return kind_between(base.version, h.version)


def major_note(kind: str) -> str:
    """The note of section 5.3 when a person chooses a major version (Q21); "" for minor and
    patch. The person can go on: the tool does not enforce the naming rule in 3.0.0."""
    return MAJOR_NOTE if kind == "major" else ""


def pinout_note(project: Project, hid: str) -> str:
    """The note of section 5.3 at review and release (Q20): the diff against the last baseline
    changes the pinout at a device (`versions.pinout_changes`) and the kind of the new version is
    minor or patch (`versions.pinout_note_due`). The note names the changed objects. "" when no
    note is due: no baseline, a major version, or no such change."""
    h = project.harnesses.get(hid)
    base = last_baseline(project, hid)
    kind = draft_kind(project, hid)
    if h is None or base is None or kind is None:
        return ""
    changes = pinout_changes(base.snapshot, snapshot_for(project, h))
    if not pinout_note_due(kind, changes):
        return ""
    names = [f"{KIND_NAMES.get(c.kind, c.kind).lower()} {c.id}" for c in changes]
    shown = ", ".join(names[:NOTE_LISTED])
    if len(names) > NOTE_LISTED:
        shown += f" and {len(names) - NOTE_LISTED} more"
    return PINOUT_NOTE.format(f" ({shown})")


def kind_again(project: Project, hid: str) -> bool:
    """True when `plan_new_version` on this harness chooses the kind again (Q22): a draft that has
    a baseline, before its review."""
    h = project.harnesses.get(hid)
    return h is not None and h.status == "draft" and last_baseline(project, hid) is not None


def plan_new_version(
    project: Project, hid: str, *, kind: str, by: str, comment: str, when: str
) -> ReleasePlan:
    """A new version of a released harness (design of 3.0.0 section 5.3): the person chooses the
    kind, major, minor or patch, and the next version is worked out from the released one (from
    `1.4.2`: `2.0.0`, `1.5.0`, `1.4.3`). The harness becomes a draft at that version, the
    baseline of the released version stays, and the change log gets one entry of kind
    `new_version`.

    On a draft that has a baseline, before its review, the kind is chosen again (Q22): the version
    is worked out again from the released one (the last baseline) and the change log gets one entry
    of kind `version_changed`; nothing else of the draft changes.

    Refused: a harness that is neither released nor such a draft (`not_released`, and
    `in_review` once its review has started), a kind that is not one of the three, the kind the
    draft already has (`kind_unchanged`), a version that is not higher than every baseline of the
    harness (`version_not_higher`, also when a merge brought one in) and a baseline ID that would
    be longer than an ID may be."""
    blockers = _common(project, hid, by, comment, when)
    h = project.harnesses.get(hid)
    base = last_baseline(project, hid)
    again = kind_again(project, hid)
    if h is not None and h.status == "in_review" and base is not None:
        blockers.append(
            Blocker(
                "in_review",
                f"{hid} is in review, so the kind of its version can no longer be chosen again; "
                "it can be chosen again only while the harness is a draft, before its review.",
                hid,
            )
        )
    elif h is not None and h.status != "released" and not again:
        blockers.append(
            Blocker("not_released", f"{hid} is not released, so it can be edited directly.", hid)
        )
    if kind not in KINDS:
        blockers.append(
            Blocker(
                "kind_unknown",
                f"'{kind}' is not a kind of version: choose major, minor or patch.",
                about="kind",
            )
        )
    plan = ReleasePlan(blockers=blockers, label=f"New version of {hid}")
    if blockers or h is None:
        return plan
    released = base.version if again and base is not None else h.version
    version = next_version(released, kind)  # type: ignore[arg-type]
    if again and version == h.version:
        blockers.append(
            Blocker(
                "kind_unchanged",
                f"{hid} is already version {version}, the {kind} version after {released}; "
                "choose another kind to change it.",
                hid,
                "kind",
            )
        )
        return plan
    higher = [
        b.version
        for b in project.baselines.values()
        if b.harness_id == hid and version_key(b.version) >= version_key(version)
    ]
    if higher:
        blockers.append(
            Blocker(
                "version_not_higher",
                f"Version {version} of {hid} is not higher than its baseline {max(higher, key=version_key)}; "
                "choose a larger kind (minor or major).",
                hid,
                "kind",
            )
        )
    if len(f"{hid}.{version}") > MAX_BASELINE_ID:
        blockers.append(
            Blocker(
                "baseline_id_too_long",
                f"The baseline of {hid} version {version} would be called '{hid}.{version}', "
                f"longer than {MAX_BASELINE_ID} characters; give the harness a shorter ID first.",
                hid,
            )
        )
    if blockers:
        return plan
    if again:
        new = evolve(h, version=version)
        entry = _entry(project, new, "version_changed", by.strip(), when, comment.strip())
        plan.ops = [Put("harnesses", new), Put("changelog", entry)]
        plan.label = f"Version {h.version} of {hid} becomes {version} ({kind})"
        return plan
    new = evolve(
        h,
        version=version,
        status="draft",
        checker=None,
        approver=None,
        released_on=None,
    )
    entry = _entry(project, new, "new_version", by.strip(), when, comment.strip())
    plan.ops = [Put("harnesses", new), Put("changelog", entry)]
    plan.label = f"New version {new.version} of {hid}"
    return plan


def plan_new_revision(
    project: Project, hid: str, *, by: str, comment: str, when: str
) -> ReleasePlan:
    """The older name of `plan_new_version` with the major step, which is the step a letter of
    format 2 took (A to B is 1.0.0 to 2.0.0, D-242); kept for scripts and tests."""
    return plan_new_version(project, hid, kind="major", by=by, comment=comment, when=when)


def plan_submit_review(project: Project, hid: str, *, by: str, when: str) -> ReleasePlan:
    blockers = _common(project, hid, by, None, when)
    h = project.harnesses.get(hid)
    if h is not None and h.status != "draft":
        blockers.append(
            Blocker(
                "not_draft",
                f"{hid} is {h.status.replace('_', ' ')}; only drafts can be submitted for review.",
                hid,
            )
        )
    if h is not None and not h.wires:
        blockers.append(Blocker("no_wires", f"{hid} has no wires.", hid))
    plan = ReleasePlan(blockers=blockers, label=f"Submit {hid} for review")
    if blockers or h is None:
        return plan
    new = evolve(h, status="in_review", author=by.strip())
    plan.ops = [
        Put("harnesses", new),
        Put("changelog", _entry(project, new, "review", by.strip(), when, "")),
    ]
    return plan


__all__ = [
    "MAJOR_NOTE",
    "PINOUT_NOTE",
    "Blocker",
    "ReleaseError",
    "ReleasePlan",
    "draft_kind",
    "kind_again",
    "last_baseline",
    "major_note",
    "next_version",
    "plan_new_revision",
    "plan_new_version",
    "part_blockers",
    "part_note",
    "placeholder_blockers",
    "placeholder_note",
    "plan_release",
    "plan_submit_review",
    "pinout_note",
    "release_blockers",
    "release_integrity",
    "role_blockers",
    "unapproved_parts",
]
