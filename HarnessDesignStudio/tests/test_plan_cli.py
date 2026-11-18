# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The command line of the harness plan (REQ-OUT-01, REQ-CLI-01; D-242, pull request 5 of
`docs/ait/DESIGN_3.0_HARNESS_PLAN.md`, section 10): `export --harness-plan` and the removal of the
plans by an export without it, `harness_plan_exported`, the re-export at a release, `--json` with
`harness_plans`, the scripting interface; `document` with and without `--harness` (show, set,
clear, the contact lines, one undo step, the journal, the refusals); the notes of `check` on the
colour codes and on the document data. Example data only."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio import api
from harness_design_studio.cli.jsonout import SHAPES
from harness_design_studio.cli.main import main
from harness_design_studio.core import change_ops, document, templates
from harness_design_studio.core.commands import History, SetConfig
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.io.layout import model_hash
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import ConfigFile, PlanDocument, evolve
from harness_design_studio.core.outputs.build import (
    build_outputs,
    harness_plan_exported,
    harness_plans_in,
    is_plan_path,
)
from harness_design_studio.core.validation import plan_notes, validate_folder
from tests.plan_support import read_plan

PLANS = ["harnesses/W001/W001_plan.ods", "harnesses/W002/W002_plan.ods"]
COMPANY = "Example Ltd"
MAIL = "plans@example.org"


def run(capsys: pytest.CaptureFixture[str], *args: object, rc: int = 0) -> str:
    code = main([str(a) for a in args])
    seen = capsys.readouterr()
    assert code == rc, seen.out + seen.err
    return seen.out + seen.err


def as_json(capsys: pytest.CaptureFixture[str], *args: object, rc: int = 0) -> dict[str, Any]:
    code = main([*(str(a) for a in args), "--json"])
    seen = capsys.readouterr()
    assert code == rc, seen.out + seen.err
    doc: dict[str, Any] = json.loads(seen.out)
    return doc


@pytest.fixture
def small(tmp_path: Path) -> Path:
    """first-steps, generated: two harnesses, W001 and W002."""
    folder = tmp_path / "small"
    api.create_project(folder, "first-steps")
    generated = api.generate(folder)
    assert generated.ok
    return folder


def plan_files(folder: Path) -> list[str]:
    return sorted(
        p.relative_to(folder / "outputs").as_posix()
        for p in (folder / "outputs").rglob("*_plan.ods")
    )


# ---- export --harness-plan ------------------------------------------------------------------


def test_export_with_and_without_the_plans(small: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert not harness_plan_exported(small / "outputs")  # no outputs yet
    plain = as_json(capsys, "export", small)
    assert list(plain) == list(SHAPES["export"])
    assert plain["harness_plans"] == [] and plain["harness_plans_removed"] is False
    assert plan_files(small) == [] and not harness_plan_exported(small / "outputs")

    doc = as_json(capsys, "export", small, "--harness-plan")
    assert list(doc) == list(SHAPES["export"])
    assert doc["harness_plans"] == PLANS == plan_files(small)
    assert doc["file_count"] == plain["file_count"] + 2
    assert [f["path"] for f in doc["files"] if is_plan_path(f["path"])] == PLANS
    assert harness_plan_exported(small / "outputs")
    assert harness_plans_in(small / "outputs") == PLANS
    # the other files are the same bytes with and without the plans
    same = {f["path"]: f["sha256"] for f in plain["files"]}
    assert {f["path"]: f["sha256"] for f in doc["files"] if f["path"] in same} == same
    # the plans pass the independent check of the outputs
    text = run(capsys, "verify", small, "--outputs")
    assert "0 error(s)" in text

    # an export without the option removes them and says so
    text = run(capsys, "export", small)
    assert "The harness plans of the earlier export were removed; add --harness-plan" in text
    assert plan_files(small) == [] and not harness_plan_exported(small / "outputs")
    assert not (small / "outputs" / "harnesses" / "W001" / "W001_plan.ods").exists()
    assert (small / "outputs" / "harnesses" / "W001" / "W001_build.xlsx").is_file()
    # and a second export without them says nothing about plans
    text = run(capsys, "export", small)
    assert "harness plans" not in text
    run(capsys, "export", small, "--harness-plan")
    doc = as_json(capsys, "export", small)
    assert doc["harness_plans_removed"] is True and doc["harness_plans"] == []


def test_two_exports_with_the_plans_are_byte_identical_and_the_text_names_the_choice(
    small: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = run(capsys, "export", small, "--harness-plan", "--drawings")
    assert "files written to" in text and "removed" not in text
    first = {p: (small / "outputs" / p).read_bytes() for p in PLANS}
    run(capsys, "export", small, "--harness-plan", "--drawings")
    assert {p: (small / "outputs" / p).read_bytes() for p in PLANS} == first
    text = run(capsys, "export", small)  # both options off: both are said
    assert "The PDF drawings of the earlier export were removed" in text
    assert "The harness plans of the earlier export were removed" in text
    text = run(capsys, "export", "--help")
    assert "--harness-plan" in text


def test_the_scripting_interface_and_another_folder(
    small: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = api.export(small, harness_plan=True)
    assert result.harness_plans == tuple(PLANS) and not result.harness_plans_removed
    again = api.export(small)
    assert again.harness_plans == () and again.harness_plans_removed
    elsewhere = small.parent / "elsewhere"
    doc = as_json(capsys, "export", small, "--harness-plan", "--out", elsewhere)
    assert doc["harness_plans"] == PLANS and str(small.parent) not in json.dumps(doc)
    assert harness_plan_exported(elsewhere) and not harness_plan_exported(small / "outputs")


def test_the_manifest_reading_is_strict_about_the_place() -> None:
    assert is_plan_path("harnesses/W001/W001_plan.ods")
    for rel in (
        "harnesses/W001/W002_plan.ods",
        "harnesses/W001/sub/W001_plan.ods",
        "system/W001_plan.ods",
        "harnesses/W001/W001_plan.ods.bak",
    ):
        assert not is_plan_path(rel), rel


def releasable(folder: Path) -> None:
    """Give every wire of first-steps a gauge and a length by hand, with a reason, as `override`
    does (generation keeps them), and generate again."""
    p = load_project(folder).project
    for h in sorted(p.harnesses.values(), key=lambda x: x.id):
        for w in h.wires:
            for name, value in (("gauge_awg", 24), ("length_m", 1.25)):
                changed = change_ops.set_override(p, w.id, name, value, "Example value")
                assert changed
    save_project(p, folder)
    generated = api.generate(folder)
    assert generated.ok


RELEASE = [
    "--by", "Example Reviewer", "--date", "2026-11-18", "--comment", "First release",
    "--accept-placeholders", "Example data", "--accept-unapproved-parts", "Example data",
]  # fmt: skip


def test_the_release_re_export_keeps_the_choice(
    small: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    releasable(small)
    run(capsys, "export", small, "--harness-plan")
    before = {p: (small / "outputs" / p).read_bytes() for p in PLANS}
    text = run(capsys, "release", small, "W001", *RELEASE)
    assert "Outputs re-exported with the released status" in text
    assert plan_files(small) == PLANS  # the plans are still there
    after = {p: (small / "outputs" / p).read_bytes() for p in PLANS}
    assert after[PLANS[0]] != before[PLANS[0]]  # the released harness: its status and register
    head = read_plan(after[PLANS[0]])["W001"]
    assert any("(released)" in str(c.value) for c in head.values())
    run(capsys, "verify", small, "--outputs")
    # without plans before the release, the re-export writes none
    run(capsys, "export", small)
    run(capsys, "release", small, "W002", *RELEASE)
    assert plan_files(small) == []


# ---- document ---------------------------------------------------------------------------------


def test_document_shows_sets_and_clears_the_project_fields(
    small: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hash0 = model_hash(load_project(small).project)
    files0 = (small / "project.json").read_bytes()
    text = run(capsys, "document", small)
    assert "System code: (empty: the plans show the project name" in text
    assert "Contact lines: (none)" in text
    doc = as_json(capsys, "document", small)
    assert list(doc) == list(SHAPES["document"])
    assert doc == {
        "ok": True, "changed": False, "harness": None, "system": "", "title": "",
        "company": "", "contact": [], "plans": {},
    }  # fmt: skip

    doc = as_json(
        capsys, "document", small, "--set", f"company={COMPANY}", "--set", "system=EX",
        "--contact", f"E-mail={MAIL}", "--contact", "Phone=+00 0000 000000",
    )  # fmt: skip
    assert doc["changed"] is True and doc["company"] == COMPANY and doc["system"] == "EX"
    assert doc["contact"] == [
        {"label": "E-mail", "value": MAIL},
        {"label": "Phone", "value": "+00 0000 000000"},
    ]
    p = load_project(small).project
    assert p.meta.document is not None and p.meta.document.company == COMPANY
    assert model_hash(p) != hash0  # document data is part of the design (section 4.4)
    # a line with that label gets the new value; an empty value removes it; order is kept
    doc = as_json(capsys, "document", small, "--contact", "e-mail=team@example.org")
    assert doc["contact"][0] == {"label": "E-mail", "value": "team@example.org"}
    doc = as_json(capsys, "document", small, "--contact", "Phone=")
    assert [c["label"] for c in doc["contact"]] == ["E-mail"]
    # the same values again change nothing
    text = run(capsys, "document", small, "--set", f"company={COMPANY}")
    assert "Already up to date." in text
    # cleared again, project.json is as it was before the first value
    run(capsys, "document", small, "--clear", "company", "--clear", "system", "--clear", "contact")
    assert (small / "project.json").read_bytes() == files0
    assert model_hash(load_project(small).project) == hash0


def test_document_with_a_harness_sets_the_plan_of_that_harness(
    small: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files0 = (small / "project.json").read_bytes()
    doc = as_json(
        capsys, "document", small, "--harness", "W001", "--set", "number=HP-W001",
        "--set", "version=2.1", "--set", "title=Wheel link plan",
    )  # fmt: skip
    assert doc["harness"] == "W001" and doc["changed"] is True
    assert doc["plans"] == {
        "W001": {"number": "HP-W001", "version": "2.1", "release": "", "title": "Wheel link plan"}
    }
    text = run(capsys, "document", small, "--harness", "W002")
    assert "Plan of W002:" in text and "the Cover shows the harness version 1.0.0" in text
    shown = as_json(capsys, "document", small, "--harness", "W002")
    assert shown["plans"] == {"W002": {"number": "", "version": "", "release": "", "title": ""}}
    text = run(capsys, "document", small)
    assert "Plans:" in text and "Document number: HP-W001" in text
    # the plan shows it on its Cover
    api.export(small, harness_plan=True)
    cover = read_plan((small / "outputs" / PLANS[0]).read_bytes())["Cover"]
    assert {c.value for c in cover.values()} >= {"HP-W001", "2.1", "Wheel link plan"}
    cover2 = read_plan((small / "outputs" / PLANS[1]).read_bytes())["Cover"]
    assert "HP-W001" not in {c.value for c in cover2.values()}
    # the four fields cleared: the plan entry is gone, and so is the document
    run(
        capsys, "document", small, "--harness", "W001", "--clear", "number", "--clear",
        "version", "--clear", "title",
    )  # fmt: skip
    assert (small / "project.json").read_bytes() == files0


@pytest.mark.parametrize(
    ("args", "rc", "said"),
    [
        (["--harness", "W009", "--set", "number=1"], 2, "harness W009 does not exist"),
        (["--harness", "W009"], 2, "harness W009 does not exist"),
        (["--set", "number=1"], 2, "'number' is not a field of the document data of the project"),
        (["--harness", "W001", "--set", "company=X"], 2, "the plan of W001"),
        (["--harness", "W001", "--contact", "E-mail=x"], 2, "without --harness"),
        (["--harness", "W001", "--clear", "contact"], 2, "without --harness"),
        (["--set", "company"], 2, "--set company: write it as SET=VALUE"),
        (["--set", "company=A", "--clear", "company"], 2, "company is both set and cleared"),
        (["--set", "company=A", "--set", "company=B"], 2, "--set gives company twice"),
        (["--set", "company=" + "x" * 201], 2, "at most 200 characters"),
        (["--contact", "=value"], 2, "--contact =value"),
    ],
)
def test_document_refusals(
    small: Path, capsys: pytest.CaptureFixture[str], args: list[str], rc: int, said: str
) -> None:
    before = (small / "project.json").read_bytes()
    text = run(capsys, "document", small, *args, rc=rc)
    assert said in text
    assert (small / "project.json").read_bytes() == before
    code = main(["document", str(small), *args, "--json"])
    assert code == rc
    assert capsys.readouterr().out == ""  # nothing is printed to the standard output


def test_document_has_at_most_eight_contact_lines(
    small: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lines = [x for n in range(8) for x in ("--contact", f"Line {n}=value {n}")]
    run(capsys, "document", small, *lines)
    text = run(capsys, "document", small, "--contact", "Ninth=x", rc=2)
    assert "at most 8 contact lines" in text


def test_document_is_one_undo_step_and_is_journaled(
    small: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    p = load_project(small).project
    h = History(p)
    ops = document.plan_document_edit(p, fields={"company": COMPANY, "title": "Plans"})
    assert len(ops) == 1
    h.execute(document.document_label(None), ops)
    ops = document.plan_document_edit(p, harness="W001", fields={"release": "2026-11-18"})
    h.execute(document.document_label("W001"), ops)
    assert p.meta.document is not None and p.meta.document.plans["W001"] == PlanDocument(
        release="2026-11-18"
    )
    assert h.next_undo_label == "Set the plan document of W001"
    h.undo()
    assert p.meta.document.plans == {} and p.meta.document.company == COMPANY
    h.undo()
    assert p.meta.document is None
    assert document.plan_document_edit(p, fields={"company": ""}) == []  # nothing to change

    run(capsys, "--author", "Example Person", "document", small, "--set", f"company={COMPANY}")
    run(capsys, "document", small, "--harness", "W001", "--set", "number=HP-1")
    doc = as_json(capsys, "journal", small)
    rows = [(e["object"], e["field"], e["new"]) for e in doc["entries"]][-2:]
    assert rows[0][0] == "project" and rows[0][1] == "document"
    assert rows[0][2] == {"company": COMPANY}
    assert rows[1][1] == "document.plans" and rows[1][2] == {"W001": {"number": "HP-1"}}
    assert doc["entries"][-2]["author"] == "Example Person"


def test_document_is_not_locked_by_a_release(
    small: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    releasable(small)
    run(capsys, "export", small)
    run(capsys, "release", small, "W001", *RELEASE)
    doc = as_json(capsys, "document", small, "--harness", "W001", "--set", "release=2026-11-18")
    assert doc["plans"]["W001"]["release"] == "2026-11-18"


def test_document_refuses_a_read_only_project(small: Path) -> None:
    p = load_project(small).project
    p.read_only = True
    with pytest.raises(EditError, match="read-only"):
        document.plan_document_edit(p, fields={"company": COMPANY})


# ---- the notes of check -----------------------------------------------------------------------


def with_example_code(folder: Path, *, missing: tuple[str, ...] = ()) -> None:
    """The example colour code for the pigtail part of first-steps, as a person takes it; the
    pins `missing` taken out of it."""
    p = load_project(folder).project
    part = p.harnesses["W001"].connectors[0].part_id
    code = templates.example_colour_code([part])
    pins = code["pins"]
    assert isinstance(pins, dict)
    code["pins"] = {k: v for k, v in pins.items() if k not in missing}
    values = {"colour_rule": "pin_code", "colour_codes": [code]}
    History(p).execute(
        "Take the example colour code",
        [SetConfig(ConfigFile(name="harness_plan", placeholder=False, values=values))],
    )
    save_project(p, folder)


def codes(issues: list[Any]) -> list[str]:
    return sorted(i.code for i in issues if i.code.startswith("plan_"))


def test_check_notes_the_example_code_once_and_the_missing_pins_per_connector(
    small: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert codes(plan_notes(load_project(small).project)) == []
    with_example_code(small)
    p = load_project(small).project
    notes = plan_notes(p)
    assert codes(notes) == ["plan_colour_example"]
    assert notes[0].severity == "info" and notes[0].location == "config/harness_plan.json"
    # two pins taken out of the code: one warning per harness connector with a wire on them
    with_example_code(small, missing=("1", "2"))
    p = load_project(small).project
    missing = [i for i in plan_notes(p) if i.code == "plan_colour_missing"]
    part = p.harnesses["W001"].connectors[0].part_id
    ends = {
        c
        for h in p.harnesses.values()
        for w in h.wires
        for c, pin in ((w.from_connector, w.from_pin), (w.to_connector, w.to_pin))
        if pin in ("1", "2") and next(x for x in h.connectors if x.id == c).part_id == part
    }
    assert missing and sorted(str(i.object_id).split(".", 1)[1] for i in missing) == sorted(ends)
    assert all(i.severity == "warning" for i in missing)
    assert "the harness plan reads 'to fill in' there" in missing[0].message
    # check says so; validate does not, and neither stops generation or an export
    text = run(capsys, "check", small)
    assert "plan_colour_example" in text and "plan_colour_missing" in text
    text = run(capsys, "validate", small)
    assert "plan_colour" not in text
    generated = api.generate(small)
    assert generated.ok
    result = api.export(small, harness_plan=True)
    assert result.written and result.harness_plans == tuple(PLANS)
    doc = as_json(capsys, "check", small)
    assert {"plan_colour_example", "plan_colour_missing"} <= {i["code"] for i in doc["issues"]}


def test_the_colour_notes_follow_the_rule_and_wait_for_a_valid_file(small: Path) -> None:
    with_example_code(small, missing=("1",))
    p = load_project(small).project
    cfg = p.config["harness_plan"]
    p.config["harness_plan"] = evolve(cfg, values={**cfg.values, "colour_rule": "wire"})
    assert codes(plan_notes(p)) == ["plan_colour_example"]  # no lookup, so no missing pin
    p.config["harness_plan"] = evolve(cfg, values={**cfg.values, "colour_rule": "nonsense"})
    assert codes(plan_notes(p)) == []  # validate reports the file; the notes wait for it
    marked = cfg.values["colour_codes"][0]
    p.config["harness_plan"] = evolve(
        cfg, values={**cfg.values, "colour_codes": [{**marked, "example": False}]}
    )
    assert set(codes(plan_notes(p))) == {"plan_colour_missing"}  # the mark taken off


def test_check_warns_about_a_plan_of_a_harness_that_is_gone(
    small: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(capsys, "document", small, "--harness", "W002", "--set", "number=HP-2")
    raw = json.loads((small / "project.json").read_text(encoding="utf-8"))
    raw["document"]["plans"]["W099"] = {"number": "HP-99"}
    (small / "project.json").write_text(
        json.dumps(raw, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    _result, extra = validate_folder(small, merge_check=True)
    found = [i for i in extra if i.code == "plan_document_unknown"]
    assert len(found) == 1 and found[0].object_id == "W099" and found[0].severity == "warning"
    assert document.unknown_plan_keys(load_project(small).project) == ["W099"]


def test_build_outputs_keeps_the_default_off(small: Path) -> None:
    p = load_project(small).project
    assert not any(is_plan_path(rel) for rel in build_outputs(p).files)
    shutil.rmtree(small / "outputs", ignore_errors=True)
