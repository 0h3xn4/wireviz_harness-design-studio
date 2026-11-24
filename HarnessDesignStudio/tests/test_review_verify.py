# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-OUT-16: the independent check of the Review sheet (design of 4.3.0, section 4.6; pull
request 4): `core/outputs/verify_review.py` and `verify._build_review`.

The verifier's copy names no builder among its imports: not the view (`core/review.py`), the
workbook (`buildsheet.py`), the tables (`tables.py`) or the release gate (`core/vcs/release.py`).
Its words are the core's; its rows are the core's on every example and fixture and on random
harnesses with random findings, waivers, deviations, checklists, parts, sources, interface types,
overrides, release entries and the as-built gate (Hypothesis); so are its checklist, list hash, the
selection of the findings of a harness and the open items of the checks of *Start here*. A sheet as
written passes; a change of each column of one row of each block, a tick, a point, the release
entry, a missing or extra finding, a count, a source, a heading, the line of *Start here* and the
sheet itself are each reported (`out_review`, or `out_build` for the sheets and *Start here*)."""

import io
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness_design_studio.core import checks, configcheck, drc, review
from harness_design_studio.core.checks import Finding
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import (
    ChangeEntry,
    ConfigFile,
    Endpoint,
    InterfaceInstance,
    InterfaceType,
    Project,
    SignalDef,
    Waiver,
)
from harness_design_studio.core.outputs import buildsheet as bs
from harness_design_studio.core.outputs import verify_review as vr
from harness_design_studio.core.outputs.build import build_outputs
from harness_design_studio.core.outputs.verify import verify_outputs
from harness_design_studio.core.outputs.xlsx_env import load_workbook
from harness_design_studio.core.samples import mini3
from harness_design_studio.core.vcs import release
from tests.loose_support import generated_loose
from tests.plan_support import GOLDEN_PROJECTS, golden_project
from tests.static_scan import imported_names
from tests.test_production_verify import production_projects
from tools.format3_record import _release_history

SRC = Path(__file__).resolve().parents[1] / "src"
PKG = "harness_design_studio.core"
NOT_IMPORTED = (
    f"{PKG}.review",
    f"{PKG}.outputs.buildsheet",
    f"{PKG}.outputs.tables",
    f"{PKG}.outputs.production",
    f"{PKG}.outputs.harness_plan",
    f"{PKG}.vcs.release",
    f"{PKG}.device_check",  # the check of a device (format 5): the verifier has its own copy
    f"{PKG}.vcs.snapshot",
    f"{PKG}.links",
)


def _core(p: Project, hid: str, found: list[Finding]) -> tuple[Any, ...]:
    v = review.review_view(p, p.harnesses[hid], found)
    blocks = tuple(
        (b.key, b.heading, b.columns, tuple((r.cells, r.ref) for r in b.rows), b.empty)
        for b in v.blocks
    )
    return (v.harness_id, v.title, v.version, v.status, v.release, v.points, v.list_hash, blocks)


def _verifier(p: Project, hid: str, found: list[Finding]) -> tuple[Any, ...]:
    v = vr.review_rows(p, p.harnesses[hid], found)
    blocks = tuple((b.key, b.heading, b.columns, b.rows, b.empty) for b in v.blocks)
    return (v.harness_id, v.title, v.version, v.status, v.release, v.points, v.list_hash, blocks)


def assert_agree(p: Project, found: list[Finding] | None = None) -> None:
    found = [*checks.find(p), *drc.run(p)] if found is None else found
    for hid, h in p.harnesses.items():
        assert _verifier(p, hid, found) == _core(p, hid, found), hid
        assert [id(f) for f in vr.about_harness(p, h, found)] == [
            id(f) for f in release.harness_findings(p, h, found)
        ], hid
        items = bs.open_items(p, h)
        loose = {c.label: c.items for c in bs.readiness(p, h) if c.label == bs.LOOSE_CHECK[0]}
        assert vr.expected_items(p, h) == {**items, **loose}, hid
    assert vr.checklist(p) == review.points(p)


# ---- independence and words -----------------------------------------------------------------------


def test_the_verifier_s_copy_imports_no_builder_no_view_and_no_gate() -> None:
    names = imported_names(SRC / "harness_design_studio/core/outputs/verify_review.py", SRC)
    assert names
    found = [n for n in names if any(n == b or n.startswith(b + ".") for b in NOT_IMPORTED)]
    assert found == []
    verify = imported_names(SRC / "harness_design_studio/core/outputs/verify.py", SRC)
    assert not [n for n in verify if n.startswith((f"{PKG}.review", f"{PKG}.vcs.release"))]


def test_the_verifier_s_words_are_the_core_s() -> None:
    assert (vr.RELEASE_HINT, vr.TICK_HINT, vr.STOPS, vr.REASON) == (
        review.RELEASE_HINT, review.TICK_HINT, review.STOPS, review.REASON,
    )  # fmt: skip
    assert vr._SEVERITY == review.SEVERITY_WORDS
    assert (vr.CHECKLIST_COLUMNS, vr.FINDING_COLUMNS, vr.PROJECT_COLUMNS) == (
        review.CHECKLIST_COLUMNS, review.FINDING_COLUMNS, review.PROJECT_COLUMNS,
    )  # fmt: skip
    assert (vr.OPEN_COLUMNS, vr.SOURCE_COLUMNS) == (review.OPEN_COLUMNS, review.SOURCE_COLUMNS)
    assert (vr._NO_CHECKLIST, vr._NO_PROJECT_FINDING, vr._NOTHING_OPEN, vr._HOW_LINES) == (
        review.NO_CHECKLIST, review.NO_PROJECT_FINDING, review.NOTHING_OPEN, review.HOW_LINES,
    )  # fmt: skip
    assert vr._PROJECT_RULES == release.PROJECT_RULES and vr._FIRST == review.FIRST_ITEMS
    assert (vr.SHEET, vr.START_LINE) == (bs.REVIEW_SHEET, bs.REVIEW_TEXT)
    assert tuple(label for label, _todo in bs.READINESS_CHECKS) == vr._CHECK_LABELS
    assert bs.LOOSE_CHECK[0] == vr.LOOSE_CHECK
    assert (vr._MAX_POINTS, vr._POINT_LENGTH) == (
        configcheck.CHECKLIST_MAX_POINTS, configcheck.CHECKLIST_POINT_LENGTH,
    )  # fmt: skip
    assert vr._BREAKS == configcheck._LINE_BREAKS


# ---- every example and fixture ----------------------------------------------------------------------


@pytest.mark.parametrize("name", GOLDEN_PROJECTS)
def test_the_verifier_words_every_example_and_fixture_as_the_core(name: str) -> None:
    assert_agree(golden_project(name))


def test_the_verifier_words_loose_ends_and_a_release_history_as_the_core(tmp_path: Path) -> None:
    assert_agree(load_project(generated_loose(tmp_path / "loose")).project)
    released = _release_history(tmp_path / "released")
    assert_agree(released)
    assert vr.release_line(released, released.harnesses["W001"]).startswith(
        "Release: version 2.0.0 released on 2026-04-02 by Ada, checked by Bob. Comment: "
    )


# ---- random harnesses, findings and checklists ---------------------------------------------------

_TEXT = st.sampled_from(["Look at the drawing.", "  Spaced point.  ", "look at the drawing.", "Two\nlines", "", "x" * 301, "x" * 300, "Point with `code` and **bold**."])  # fmt: skip
_CHECKLISTS = st.one_of(
    st.none(),
    st.just([]),
    st.lists(_TEXT, max_size=5),
    st.lists(st.text(min_size=1, max_size=8), min_size=1, max_size=4),
    st.just(["Point."] * 101),
    st.just([1, "Point."]),
    st.just("Point."),
)
_RULES = ("config-invalid", "unchecked-config", "part-unapproved", "wire-dangling", "pin-floating", "x-own-rule")  # fmt: skip


@st.composite
def review_projects(draw: st.DrawFn) -> tuple[Project, list[Finding]]:
    """The random harnesses of `tests/test_production_verify.py` with more: a checklist (accepted
    or refused), parts of every approval with links, sources on the device connectors, an interface
    of a type that may be example data, overrides, a release entry of the version or of another,
    a checker, the as-built gate; and random findings with waivers, deviations and changed
    waivers on the objects of the project and on nothing."""
    p = draw(production_projects())
    h = p.harnesses["W001"]
    naming = dict(p.config["naming"].values) if "naming" in p.config else {}
    if (listed := draw(_CHECKLISTS)) is not None:
        naming["review_checklist"] = listed
    naming["release_requires_asbuilt"] = draw(st.sampled_from([False, True, "yes"]))
    p.config["naming"] = ConfigFile(name="naming", placeholder=draw(st.booleans()), values=naming)
    for pid, part in list(p.parts.items()):
        p.parts[pid] = part.model_copy(update={
            "approval": draw(st.sampled_from(["approved", "pending", "not_approved"])),
            "unverified": draw(st.booleans()), "link": draw(st.sampled_from([None, "https://example.org/part"])),
        })  # fmt: skip
    if draw(st.booleans()):
        p.parts.pop(draw(st.sampled_from(sorted(p.parts))))  # a part missing from the parts list
    for cid, box in list(p.connectors.items()):
        p.connectors[cid] = box.model_copy(update={
            "source_doc": draw(st.sampled_from([None, "ICD-001"])),
            "source_version": draw(st.sampled_from([None, "B"])),
            "source_link": draw(st.sampled_from([None, "https://example.org/icd"])),
        })  # fmt: skip
    p.interface_types["T1"] = InterfaceType(
        id="T1", name="t", category="data", signals=[SignalDef(name="S")],
        unverified=draw(st.booleans()),
    )  # fmt: skip
    boxes = sorted(p.connectors)
    p.interfaces["IF1"] = InterfaceInstance(
        id="IF1", name="i", type_id=draw(st.sampled_from(["T1", "T9"])),
        endpoints=[Endpoint(unit_id="D1", connector_id=draw(st.sampled_from([None, *boxes])))],
    )  # fmt: skip
    wires = [
        w.model_copy(
            update={
                "interface_id": draw(st.sampled_from([None, "IF1"])),
                "overrides": draw(st.sampled_from([{}, {"gauge_awg": "Chosen by the engineer."}])),
            }
        )  # fmt: skip
        for w in h.wires
    ]
    h = h.model_copy(update={
        "wires": wires, "checker": draw(st.sampled_from([None, "Bob"])),
        "label": draw(st.sampled_from([None, "Main bus"])),
        "interfaces": draw(st.sampled_from([[], ["IF1"], ["IF9"]])),
    })  # fmt: skip
    p.harnesses["W001"] = h
    for n in range(draw(st.integers(0, 2))):
        p.changelog[f"C{n:04d}"] = ChangeEntry(
            id=f"C{n:04d}", harness_id="W001", version=draw(st.sampled_from([h.version, "9.0.0"])),
            kind=draw(st.sampled_from(["release", "review"])), by="Ada", when="2026-04-02",
            comment=f"Comment {n}.",
        )  # fmt: skip
    objects = sorted(
        {*p.units, *p.interfaces, *p.harnesses, *p.connectors, *p.parts, "P-W", "NOT-AN-ID",
         *(c.id for c in h.connectors), *(w.id for w in h.wires), *(s.id for s in h.shields),
         f"shield-parts.{h.id}.x", "wire-spec.P-W", "IF1.D1-J1", "spare-pins"}
    )  # fmt: skip
    found = []
    for n in range(draw(st.integers(0, 10))):
        rule = draw(st.sampled_from(_RULES))
        severity = draw(st.sampled_from(("error", "warning", "info")))
        oid = draw(st.sampled_from(objects))
        fid = f"{rule}.{oid}.{n}"
        waiver = (
            Waiver(id=fid, rule=rule, object_id=oid, justification=draw(st.sampled_from([" A reason. ", "Spare by design."])))
            if draw(st.booleans())
            else None
        )  # fmt: skip
        found.append(
            Finding(fid, rule, severity, oid, f"Finding {n}", "Why.", waiver=waiver,  # type: ignore[arg-type]
                    waiver_changed=draw(st.booleans()))
        )  # fmt: skip
    return p, found


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(review_projects())
def test_the_verifier_words_a_random_harness_as_the_core(made: tuple[Project, list[Finding]]) -> None:  # fmt: skip
    p, found = made
    assert_agree(p, found)


@settings(max_examples=200, deadline=None)
@given(st.lists(st.text(max_size=12), max_size=6))
def test_the_list_hash_is_the_core_s(points: list[str]) -> None:
    assert vr.list_hash(points) == review.list_hash(points)


# ---- the written sheet: the verifier can fail -------------------------------------------------------

H = "W002"
REL = f"harnesses/{H}/{H}_build.xlsx"


@pytest.fixture(scope="module")
def flatsat_built() -> tuple[Project, dict[str, bytes]]:
    p = golden_project("flatsat")
    return p, build_outputs(p, drawings=False).files


@pytest.fixture(scope="module")
def listed_built() -> tuple[Project, dict[str, bytes]]:
    """mini3 with a checklist of three points, a waived warning and an accepted error."""
    p = mini3()
    generate_project(p)
    naming = p.config["naming"]
    points = ["Look at the drawing.", "Check the wire list.", "Read the findings."]
    p.config["naming"] = ConfigFile(name="naming", placeholder=False, values={**naming.values, "review_checklist": points})  # fmt: skip
    return p, build_outputs(p, drawings=False).files


def _errors(p: Project, files: dict[str, bytes]) -> list[tuple[str, str, str]]:
    return [(i.code, i.object_id or "", i.message) for i in verify_outputs(p, files).issues if i.severity == "error"]  # fmt: skip


def _changed(built: tuple[Project, dict[str, bytes]], change: Callable[[Any], None], rel: str = REL) -> list[tuple[str, str, str]]:  # fmt: skip
    p, files = built
    wb = load_workbook(io.BytesIO(files[rel]))
    change(wb)
    out = io.BytesIO()
    wb.save(out)
    return _errors(p, {**files, rel: out.getvalue()})


def _row_of(ws: Any, first: str, col: int = 1) -> int:
    """The row of the sheet whose cell in `col` reads `first`."""
    return next(r for r in range(1, ws.max_row + 1) if ws.cell(r, col).value == first)


def _set(sheet: str, find: str, col: int, value: object, find_col: int = 1) -> Callable[[Any], None]:  # fmt: skip
    def change(wb: Any) -> None:
        ws = wb[sheet]
        ws.cell(_row_of(ws, find, find_col), col).value = value

    return change


def _review_errors(errors: list[tuple[str, str, str]]) -> list[str]:
    assert errors and all(code == "out_review" and obj.startswith("W00") for code, obj, _m in errors), errors  # fmt: skip
    return [m for _c, _o, m in errors]


def test_the_written_sheets_pass_the_verifier(flatsat_built: Any, listed_built: Any, tmp_path: Path) -> None:  # fmt: skip
    assert _errors(*flatsat_built) == []
    assert _errors(*listed_built) == []
    released = _release_history(tmp_path)
    assert _errors(released, build_outputs(released, drawings=False).files) == []


# one row of each block of flatsat W002, by the text in its first or its third column
_ROWS = {
    "findings": ("connector-lookalike.PDU2-J01", 3, 7),
    "project": ("unchecked-config.emc", 3, 5),
    "open": ("Wires without a gauge", 1, 5),
    "sources": ("PDU2-J01", 2, 6),
}


@pytest.mark.parametrize(
    ("block", "col"),
    [(b, c) for b, (_f, _k, n) in _ROWS.items() for c in range(1, n + 1)],
)
def test_a_changed_cell_of_a_row_of_each_block_is_out_review(flatsat_built: Any, block: str, col: int) -> None:  # fmt: skip
    find, find_col, _n = _ROWS[block]

    def change(wb: Any) -> None:
        ws = wb["Review"]
        cell = ws.cell(_row_of(ws, find, find_col), col)
        cell.value = cell.value + 1 if isinstance(cell.value, int) else f"{cell.value or ''}X"

    messages = _review_errors(_changed(flatsat_built, change))
    words = {
        "findings": "connector-lookalike.PDU2-J01",
        "project": "unchecked-config.emc",
        "open": "'Wires without a gauge'",
        "sources": "the source of PDU2-J01",
    }[block]
    assert any(words in m for m in messages), messages


@pytest.mark.parametrize(
    ("name", "change", "words"),
    [
        (
            "a finding left out",
            lambda wb: wb["Review"].delete_rows(
                _row_of(wb["Review"], "connector-lookalike.PDU2-J01", 3)
            ),
            "does not list the finding connector-lookalike.PDU2-J01.",
        ),  # fmt: skip
        (
            "a finding not of the harness",
            _set("Review", "connector-lookalike.PDU2-J01", 3, "x-own-rule.W009", 3),
            "lists the finding x-own-rule.W009, which is not about W002.",
        ),  # fmt: skip
        (
            "a state",
            _set("Review", "unconfirmed.IF-009", 6, "waived: done", 3),
            "gives the finding unconfirmed.IF-009 as 'waived: done', but it is open.",
        ),  # fmt: skip
        (
            "a count",
            _set("Review", "Wires without a gauge", 2, 23),
            "shows a wrong count for 'Wires without a gauge'.",
        ),  # fmt: skip
        (
            "an open value left out",
            lambda wb: wb["Review"].delete_rows(_row_of(wb["Review"], "Wires without a colour")),
            "shows a wrong count for 'Wires without a colour'.",
        ),  # fmt: skip
        (
            "a source",
            _set("Review", "PDU2-J01", 4, "ICD-9", 2),
            "does not name the source of PDU2-J01 as the design has it.",
        ),  # fmt: skip
        (
            "the release entry",
            _set("Review", "Release: not released yet.", 1, "Release: version 1.0.0 released."),
            "names the release of version 1.0.0 wrongly.",
        ),  # fmt: skip
        (
            "a heading",
            _set("Review", "Values still open", 1, "Values"),
            "does not have the heading 'Values still open'.",
        ),  # fmt: skip
        (
            "the sentence of no checklist",
            _set("Review", review.NO_CHECKLIST, 1, "No checklist."),
            "does not say 'No checklist: ",
        ),  # fmt: skip
        (
            "a column heading",
            _set("Review", "Severity", 6, "Status"),
            "has the wrong column headings in 'Findings of W002",
        ),  # fmt: skip
        (
            "a sentence of the end",
            _set("Review", review.HOW_LINES[1], 1, "Explain it."),
            "does not have the sentences of 'How the numbers were made'.",
        ),  # fmt: skip
        (
            "the tick hint",
            _set("Review", review.TICK_HINT, 1, None),
            "does not have row 5 of the design",
        ),  # fmt: skip
        (
            "a block left out",
            lambda wb: wb["Review"].delete_rows(
                _row_of(wb["Review"], "How the numbers were made") - 1, 4
            ),
            "does not have the 6 blocks of the design.",
        ),  # fmt: skip
        (
            "a cell right of the columns",
            _set("Review", "unchecked-config.emc", 7, "x", 3),
            "has cells right of the columns",
        ),  # fmt: skip
    ],
)
def test_a_wrong_review_sheet_is_out_review(flatsat_built: Any, name: str, change: Callable[[Any], None], words: str) -> None:  # fmt: skip
    messages = _review_errors(_changed(flatsat_built, change))
    assert any(words in m for m in messages), (name, messages)


@pytest.mark.parametrize(
    ("name", "change", "words"),
    [
        (
            "a tick",
            _set("Review", "Look at the drawing.", 3, "x", 2),
            "has ticks before anyone reviewed it.",
        ),  # fmt: skip
        (
            "a point",
            _set("Review", "Check the wire list.", 2, "Check the list.", 2),
            "gives point 2 as 'Check the list.', but the project's checklist says 'Check the wire list.'.",
        ),  # fmt: skip
        (
            "a point left out",
            lambda wb: wb["Review"].delete_rows(_row_of(wb["Review"], "Read the findings.", 2)),
            "lists 2 points, but config/naming.json has 3 (list ",
        ),  # fmt: skip
        (
            "a number",
            _set("Review", "Look at the drawing.", 1, 4, 2),
            "gives point 1 as 'Look at the drawing.'",
        ),  # fmt: skip
    ],
)
def test_a_wrong_checklist_is_out_review(listed_built: Any, name: str, change: Callable[[Any], None], words: str) -> None:  # fmt: skip
    messages = _review_errors(_changed(listed_built, change, "harnesses/W001/W001_build.xlsx"))
    assert any(words in m for m in messages), (name, messages)


def test_points_on_a_sheet_of_a_project_without_a_checklist_are_reported(flatsat_built: Any) -> None:  # fmt: skip
    def change(wb: Any) -> None:
        ws = wb["Review"]
        row = _row_of(ws, review.NO_CHECKLIST)
        ws.cell(row, 1).value = "No."
        ws.cell(row, 2).value = "Point"
        ws.cell(row, 3).value = "Done (x)"
        ws.cell(row, 4).value = "Note"
        ws.insert_rows(row + 1)
        ws.cell(row + 1, 1).value = 1
        ws.cell(row + 1, 2).value = "A point of my own."

    messages = _review_errors(_changed(flatsat_built, change))
    assert any("lists 1 points, but config/naming.json has none." in m for m in messages), messages


@pytest.mark.parametrize(
    ("name", "change", "words"),
    [
        (
            "the sheet removed",
            lambda wb: wb.remove(wb["Review"]),
            "has no Review sheet before About.",
        ),  # fmt: skip
        (
            "the sheet moved",
            lambda wb: wb.move_sheet("Review", offset=-3),
            "has no Review sheet before About.",
        ),  # fmt: skip
        (
            "the line of Start here removed",
            _set("Start here", "Review", 1, None),
            "(Start here) does not list the Review sheet before About.",
        ),  # fmt: skip
        (
            "the line of Start here worded otherwise",
            _set("Start here", "Review", 2, "for the reviewer"),
            "(Start here) does not list the Review sheet before About.",
        ),  # fmt: skip
    ],
)
def test_the_sheet_and_its_line_on_start_here_are_out_build(flatsat_built: Any, name: str, change: Callable[[Any], None], words: str) -> None:  # fmt: skip
    errors = _changed(flatsat_built, change)
    assert [c for c, _o, _m in errors] == ["out_build"], (name, errors)
    assert words in errors[0][2], (name, errors)


def test_a_waived_finding_reads_waived_on_the_sheet_and_the_verifier_follows(tmp_path: Path) -> None:  # fmt: skip
    """A waiver given after the export: the sheet still says open, and the verifier says so in the
    words of the design."""
    p = mini3()
    generate_project(p)
    files = build_outputs(p, drawings=False).files
    found = [*checks.find(p), *drc.run(p)]
    warning = next(f for f in found if f.can_waive and f in release.harness_findings(p, p.harnesses["W001"], found))  # fmt: skip
    from harness_design_studio.core.commands import apply_ops

    apply_ops(p, [checks.waive_op(warning, "Accepted for the test of the sheet.")])
    errors = [e for e in _errors(p, files) if e[0] == "out_review"]
    assert any(f"gives the finding {warning.id} as 'open', but it is waived: Accepted for the test of the sheet" in m for _c, _o, m in errors), errors  # fmt: skip
