# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-OUT-16, REQ-CC-11, REQ-GUI-31. The end-to-end walk of 4.3.0 (pull request 6 of section 16 of
`docs/ait/DESIGN_4.3_REVIEW_VIEW.md`; the tests of its section 11), through the command line and,
for the Review page, through the editor.

A reviewer on the example `flatsat` (`new --template flatsat`): `templates` copies the checklist
template, `config --review-checklist design-review-checklist.md` takes its 26 points into
`config/naming.json`, `generate` changes nothing and `export` writes the build workbooks. The
*Review* sheet of W001 is read back: the checklist with an empty tick column and the list hash,
every finding of W001 (each one that `drc --json` prints, with its state and what it means for the
release), the notes of the whole project, the values still open (the same placeholder files the
release gate names), the sources (each device connector W001 plugs into and each part it uses) and
how a number is explained. A ticked workbook in `outputs/` fails `verify --outputs` and stops the
release (`outputs_modified`); a ticked copy elsewhere does not. `release --ticked 1-20` is blocked
by the placeholders and the example parts and records nothing; `--ticked 27` is not a point; with
the two reasons the release goes ahead and its comment ends with the note of the ticks. `log`,
`log --json`, `system/changelog.csv`, `system/version_report.md`, the baseline and row 3 of the
Review sheet written again after the release show the note; `verify --outputs` finds no error.

`explain DIR FINDING` on a finding of each kind the sheet lists (pull request 3 of the design,
which reached `master` before this branch; the test runs once both are together). The editor: the
Next step page opens the Review page on the first harness not released, the reviewer ticks points
there, *Release…* shows the note under the comment and the release records it; the next export
writes it on the sheet.

Example data only: the example project `flatsat`, an example reviewer and checker."""

import csv
import io
import json
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.core import review
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import ChangeEntry, Project
from harness_design_studio.core.outputs.xlsx_env import load_workbook
from tests.test_e2e_300 import ok
from tests.test_e2e_rs422x3 import run

TEMPLATE = "design-review-checklist.md"
WHO = ["--by", "Example Reviewer", "--date", "2026-11-22"]
REASONS = [
    "--accept-placeholders", "Example data for the walk",
    "--accept-unapproved-parts", "Example parts for the walk",
]  # fmt: skip
COMMENT = "First build of the AOCS harness"
POINT_21 = "Drawing: connectors, pins and signals match the device do..."  # cut to 60 characters
HOW = (
    "Every ID on this sheet can be explained: harness-design-studio explain DIR ID shows the "
    "equation, the inputs and their sources for a wire, a connector, a part or a finding (Finding "
    "column); in the editor, select it and open Why."
)
TICK_HERE = (
    "Tick a printout, or a copy saved outside the outputs folder: a file in outputs/ that was "
    "changed after the export stops the release (outputs_modified)."
)


def sheet_rows(book: Path) -> list[list[Any]]:
    """The rows of the Review sheet of a build workbook that hold a value, with the trailing empty
    cells dropped."""
    ws = load_workbook(book)["Review"]
    rows = []
    for row in ws.iter_rows(values_only=True):
        cells = list(row)
        while cells and cells[-1] is None:
            cells.pop()
        if cells:
            rows.append(cells)
    return rows


def block(rows: list[list[Any]], columns: tuple[str, ...]) -> list[list[Any]]:
    """The rows of the block whose column row is `columns`, up to the next heading (a row of one
    cell)."""
    start = rows.index(list(columns)) + 1
    out = []
    for row in rows[start:]:
        if len(row) <= 1:
            break
        out.append(row)
    return out


def heading(rows: list[list[Any]], columns: tuple[str, ...]) -> str:
    """The heading of the block whose column row is `columns`: the row above it."""
    return str(rows[rows.index(list(columns)) - 1][0])


def blocked(out: str) -> dict[str, str]:
    """The lines `blocked: [code] text` of a refused release, by code."""
    found = {}
    for line in out.splitlines():
        if line.startswith("blocked: ["):
            code, _, text = line.removeprefix("blocked: [").partition("] ")
            found[code] = text
    return found


def last_entry(project: Project) -> ChangeEntry:
    """The newest entry of the change log (`C0001`, `C0002`, …)."""
    return project.changelog[max(project.changelog)]


def changelog_rows(outputs: Path) -> list[dict[str, str]]:
    text = (outputs / "system" / "changelog.csv").read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    return list(csv.DictReader(io.StringIO(body)))


def reviewed_flatsat(
    proj: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[str, list[str]]:
    """`flatsat` with the template's checklist, generated and exported; the list hash and the
    points."""
    ok(capsys, "new", proj, "--template", "flatsat")
    ok(capsys, "templates", tmp_path / "templates")
    template = tmp_path / "templates" / TEMPLATE
    points = review.points_from_text(template.read_text(encoding="utf-8"))
    digest = review.list_hash(points)
    # config exits 1 while engineering values are missing (flatsat leaves 4 unset); the list is set
    code, out = run(capsys, "config", str(proj), "--review-checklist", str(template))
    assert code == 1, out
    assert out.splitlines()[0] == (
        f"Review checklist: 26 points in config/naming.json (list {digest})."
    )
    naming = json.loads((proj / "config" / "naming.json").read_text(encoding="utf-8"))
    assert naming["values"]["review_checklist"] == points
    assert "0 added, 0 changed" in ok(capsys, "generate", proj)  # not an input of generation
    assert "95 files written" in ok(capsys, "export", proj)
    return digest, points


def test_a_reviewer_walks_the_review_view_of_4_3_0_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = tmp_path / "flatsat"
    outputs = proj / "outputs"
    book = outputs / "harnesses" / "W001" / "W001_build.xlsx"
    # 1. the checklist from the shipped template, generate, export
    digest, points = reviewed_flatsat(proj, tmp_path, capsys)
    assert len(points) == 26 and points[0] == "harness-design-studio check DIR prints no error."
    assert digest == "8b3d7a5b"  # the list hash the user manual and the release notes quote
    assert load_workbook(book).sheetnames[-2:] == ["Review", "About"]

    # 2. the Review sheet of W001 before the release
    rows = sheet_rows(book)
    assert rows[0] == ["Review of W001  aocs to aocs"]
    assert rows[2] == ["Release: not released yet."] and rows[4] == [TICK_HERE]
    assert heading(rows, review.CHECKLIST_COLUMNS) == (
        f"Checklist: 26 points (config/naming.json review_checklist, list {digest})"
    )
    listed = block(rows, review.CHECKLIST_COLUMNS)
    assert [r[:2] for r in listed] == [[n, p] for n, p in enumerate(points, 1)]
    assert all(len(r) == 2 for r in listed)  # Done (x) and Note are empty: nobody ticked yet
    # every finding of W001 is one that `drc --json` prints
    code, out = run(capsys, "drc", str(proj), "--json")
    drc = {f["id"]: f for f in json.loads(out)["findings"]}
    assert code == 0
    findings = block(rows, review.FINDING_COLUMNS)
    assert heading(rows, review.FINDING_COLUMNS) == (
        "Findings of W001: 0 errors, 5 warnings, 9 notes open; 0 waived, 0 accepted as deviations"
    )
    assert {r[2] for r in findings} <= set(drc) and len(findings) == 14
    for severity, rule, fid, obj, text, state, *release in findings:
        assert (rule, obj, text) == (drc[fid]["rule"], drc[fid]["object_id"], drc[fid]["title"])
        assert severity == {"warning": "warning", "info": "note"}[drc[fid]["severity"]]
        assert state == "open"
        assert release == (["needs a written reason"] if rule == "part-unapproved" else [])
    unapproved = sorted(r[3] for r in findings if r[1] == "part-unapproved")
    assert unapproved == ["EX-MICROD-9-M", "EX-WIRE-SINGLE"]
    assert [r[2] for r in block(rows, review.PROJECT_COLUMNS)] == [
        "unchecked-config.emc", "unchecked-config.separation", "unchecked-config.spare-pins",
    ]  # fmt: skip
    still_open = {r[0]: r for r in block(rows, review.OPEN_COLUMNS)}
    placeholders = still_open["Configuration files still placeholders"]
    assert placeholders[1] == 6 and placeholders[4] == "needs a written reason"
    assert still_open["Engineering values not set"][1] == 4
    assert "Wires without a gauge" not in still_open  # W001 has a gauge on every wire
    sources = block(rows, review.SOURCE_COLUMNS)
    assert [r[1] for r in sources if r[0] == "Part"] == unapproved
    assert all(r[3] == "not named" for r in sources if r[0] == "Device connector")
    assert len([r for r in sources if r[0] == "Device connector"]) == 18
    assert rows[-3:] == [["How the numbers were made"], [HOW], [review.HOW_LINES[1]]]

    # 3. where to tick: a ticked workbook in outputs/ stops the release, a copy elsewhere does not
    w003 = outputs / "harnesses" / "W003" / "W003_build.xlsx"
    exported = w003.read_bytes()
    ticked = load_workbook(w003)
    ws = ticked["Review"]
    first = next(r for r in range(1, 40) if ws.cell(r, 3).value == "Done (x)") + 1
    ws.cell(first, 3).value = "x"
    ticked.save(w003)
    code, out = run(capsys, "verify", str(proj), "--outputs")
    assert code == 1
    assert "[out_modified] harnesses/W003/W003_build.xlsx was changed after it was exported." in out
    assert "[out_review] The build workbook of W003 (Review) has ticks before anyone reviewed it." in out  # fmt: skip
    code, out = run(capsys, "release", str(proj), "W003", *WHO, "--comment", COMMENT, *REASONS)
    assert code == 1 and list(blocked(out)) == ["outputs_modified"]
    (tmp_path / "review").mkdir()
    ticked.save(tmp_path / "review" / "W003_build.xlsx")  # the reviewer's copy
    w003.write_bytes(exported)  # the release below finds the outputs as exported

    # 4. the release with the ticks: blocked by the reasons it needs, refused for a wrong point
    code, out = run(capsys, "release", str(proj), "W001", *WHO, "--comment", COMMENT, "--ticked", "1-20")  # fmt: skip
    stops = blocked(out)
    assert code == 1 and list(stops) == ["placeholder_config", "parts_unapproved"]
    assert stops["parts_unapproved"].startswith(
        "2 part(s) used by W001 are not approved (or are example data): EX-MICROD-9-M, "
        "EX-WIRE-SINGLE."
    )  # the parts the sheet marks *needs a written reason*
    assert stops["placeholder_config"].startswith(
        "These configuration files are still placeholders: derating, emc, generation, "
        "segmentation, segregation, titleblock."
    )
    assert placeholders[2] == ", ".join(
        f"config/{name}.json"
        for name in ("derating", "emc", "generation", "segmentation", "segregation", "titleblock")
    )
    assert not load_project(proj).project.changelog  # a refused release records nothing
    code, out = run(capsys, "release", str(proj), "W001", *WHO, "--comment", COMMENT, "--ticked", "27", *REASONS)  # fmt: skip
    assert code == 1 and blocked(out) == {
        "ticked_invalid": "--ticked must be all, none, or point numbers from 1 to 26 such as "
        "1-5,7 (got '27')."
    }
    out = ok(capsys, "release", proj, "W001", *WHO, "--comment", COMMENT, "--ticked", "1-20", *REASONS)  # fmt: skip
    assert "Release W001 version 1.0.0: done." in out
    note = (
        f" [Review checklist (26 points, list {digest}), recorded by Example Reviewer: ticked "
        f"1-20; not ticked 21 ({POINT_21}), 22 (Wire list, pinouts and BOM agree with the "
        "drawing.), 23 (Mass and length tables look plausible.), 24 (Test tables list the limits "
        "your programme requires.), 25 (The release comment says what this version is for, and "
        "th...) and 1 more]"
    )
    entry = last_entry(load_project(proj).project)
    assert (entry.kind, entry.harness_id, entry.version) == ("release", "W001", "1.0.0")
    assert entry.comment.startswith(COMMENT + " [Released on placeholder configuration")
    assert entry.comment.endswith(note)  # the note of the ticks comes last

    # 5. where the note is read afterwards: log, log --json, changelog.csv, the Review sheet
    out = ok(capsys, "log", proj, "W001")
    assert note.strip() in out
    logged = json.loads(ok(capsys, "log", proj, "W001", "--json"))
    assert [e["comment"] for e in logged["entries"]] == [entry.comment]
    assert changelog_rows(outputs)[-1]["Comment"] == entry.comment
    assert note.strip() in (outputs / "system" / "version_report.md").read_text(encoding="utf-8")
    baseline = json.loads((proj / "baselines" / "W001" / "W001.1.0.0.json").read_text("utf-8"))
    assert note.strip() in json.dumps(baseline, ensure_ascii=False)
    rows = sheet_rows(book)  # the release wrote the outputs again
    assert rows[1][0].startswith("Version 1.0.0   ·   status released   ·   ")
    assert rows[2] == [
        f"Release: version 1.0.0 released on 2026-11-22 by Example Reviewer. Comment: "
        f"{entry.comment}"
    ]
    assert all(len(r) == 2 for r in block(rows, review.CHECKLIST_COLUMNS))  # still not ticked
    assert "0 error(s)" in ok(capsys, "verify", proj, "--outputs")


def test_explain_takes_each_kind_of_finding_the_review_sheet_lists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = tmp_path / "flatsat"
    reviewed_flatsat(proj, tmp_path, capsys)
    rows = sheet_rows(proj / "outputs" / "harnesses" / "W001" / "W001_build.xlsx")
    listed = [r[2] for r in block(rows, review.FINDING_COLUMNS)]
    listed += [r[2] for r in block(rows, review.PROJECT_COLUMNS)]
    seen: dict[str, str] = {}
    for fid in listed:  # the first finding of each rule
        seen.setdefault(fid.split(".", 1)[0], fid)
    assert sorted(seen) == ["connector-lookalike", "part-unapproved", "unchecked-config", "unconfirmed"]  # fmt: skip
    for rule, fid in seen.items():
        out = ok(capsys, "explain", proj, fid)
        assert out.startswith(f"Rule {rule} for {fid.split('.', 1)[1]}.")
        assert "this rule is a yes/no check" in out and "Model page:" in out
        derived = json.loads(ok(capsys, "explain", proj, fid, "--json"))
        assert derived and derived[0]["subject"] == f"Rule {rule} for {fid.split('.', 1)[1]}"
    part = ok(capsys, "explain", proj, seen["part-unapproved"])
    assert "Approval = pending   [parts library: EX-MICROD-9-M]" in part


@pytest.mark.gui
def test_the_review_page_ticks_go_to_the_release_and_the_sheet(
    qtbot: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from harness_design_studio.gui.dialogs import ChangeDialog
    from tests.gui_helpers import DialogScript, hold_drc, make_window

    proj = tmp_path / "flatsat"
    digest, points = reviewed_flatsat(proj, tmp_path, capsys)
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    assert win.open_project(proj)
    hold_drc(win)
    win.ctl.run_drc_now()
    win.ctl.today = lambda: "2026-11-23"
    QApplication.processEvents()
    # the Next step page: Review and release opens the Review page on the first open harness
    win.set_area("next")
    QApplication.processEvents()
    assert win.next_page.button.text() == "Open the Review page"
    win.next_page.button.click()
    page = win.review_page
    assert win.area() == "review" and page.harness_id() == "W001"
    assert page.headings["checklist"].text().endswith(f"list {digest})")
    assert [r[1] for r in page.rows("checklist")] == points
    # the reviewer ticks points 1 to 24 and 26
    model = page.models["checklist"]
    for n in [*range(1, 25), 26]:
        model.setData(model.index(n - 1, 2), Qt.CheckState.Checked.value, Qt.ItemDataRole.CheckStateRole)  # fmt: skip
    assert win.review_ticked("W001") == frozenset([*range(1, 25), 26])
    assert "25 of 26 points ticked" in page.summary.text()

    seen: list[str] = []

    def answer(d: ChangeDialog) -> None:
        d.by.setText("Example Reviewer")
        d.checker.setText("Example Checker")
        d.comment.setPlainText(COMMENT)
        d.placeholder_reason.setText("Example data for the walk")
        d.parts_reason.setText("Example parts for the walk")
        seen.append(d.review_note.text())

    DialogScript(win, answer, accept=True)
    page.release_button.click()
    note = (
        f"[Review checklist (26 points, list {digest}), recorded by Example Reviewer: ticked 1-24, "
        "26; not ticked 25 (The release comment says what this version is for, and th...)]"
    )
    assert seen == [f"Added to the comment: {note}"]
    h = win.ctl.project.harnesses["W001"]
    assert (h.status, h.approver, h.checker) == ("released", "Example Reviewer", "Example Checker")
    entry = last_entry(win.ctl.project)
    assert entry.comment.endswith(" " + note)
    win._update_review()
    assert page.release_line.text().startswith(
        "Release: version 1.0.0 released on 2026-11-23 by Example Reviewer, checked by "
        "Example Checker."
    )
    assert not page.release_button.isEnabled()
    # released: the entry above, no tick boxes, and no word of ticks to make again
    assert page.released.isVisibleTo(page) and not page.dropped.isVisibleTo(page)
    win.ctl.save()
    win.ctl.wait_journal()
    win.ctl.release()  # the window lets the folder go
    # the next export writes the release and its note on the sheet
    ok(capsys, "export", proj)
    rows = sheet_rows(proj / "outputs" / "harnesses" / "W001" / "W001_build.xlsx")
    assert rows[2] == [
        "Release: version 1.0.0 released on 2026-11-23 by Example Reviewer, checked by Example "
        f"Checker. Comment: {entry.comment}"
    ]
    assert note in ok(capsys, "log", proj, "W001")
    assert "0 error(s)" in ok(capsys, "verify", proj, "--outputs")
