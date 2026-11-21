# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The review checklist of a project (design of 4.3.0, `docs/ait/DESIGN_4.3_REVIEW_VIEW.md`, part A,
sections 3.1 to 3.4): the key `review_checklist` of `config/naming.json`, empty by default (D-11).
The check of a list with the text of `config_invalid`; `review.points_from_text` on the shipped
template, a plain file and a file with headings; `config DIR --review-checklist FILE` and `none`;
the key is not an input of generation but is part of the content hash; a project of 4.2 with the
key loads, saves and keeps it, and the project format stays 4."""

import json
from pathlib import Path

import pytest

from harness_design_studio.cli.main import main
from harness_design_studio.core import configcheck, review, settings, templates
from harness_design_studio.core.commands import History
from harness_design_studio.core.drc import run as run_drc
from harness_design_studio.core.generation_status import generation_status, input_hash
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import ConfigFile, Project
from harness_design_studio.core.model.project import SCHEMA_VERSION
from harness_design_studio.core.vcs.hashing import content_hash
from harness_design_studio.resources import examples_path
from tests.helpers import copy_project, edit_json

TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "src/harness_design_studio/resources/examples/templates/design-review-checklist.md"
)
WHY = "must be a list of points, each one line of 1 to 300 characters, each once, at most 100"
TEXT = f"config/naming.json: review_checklist {WHY}."


def _with_list(p: Project, value: object) -> Project:
    old = p.config.get("naming")
    base = dict(old.values) if old is not None else {}
    p.config["naming"] = ConfigFile(
        name="naming", placeholder=False, values={**base, "review_checklist": value}
    )
    return p


def _issues(p: Project) -> list[str]:
    return [i.message for i in configcheck.validate(p) if i.object_id == "naming.review_checklist"]


@pytest.fixture
def flat(tmp_path: Path) -> Project:
    return templates.create_project(tmp_path / "flat", "flatsat")


# ---- the check of a list (3.1) ------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        ["One point."],
        ["a" * 300],
        ["  spaces around do not count  "],
        [f"Point {n}" for n in range(1, 101)],
        ["Wire list", "Wire list and BOM"],
        ["*auto-filled* stays as written", "tab\tinside"],
    ],  # fmt: skip
)
def test_accepted_lists(flat: Project, value: object) -> None:
    assert _issues(_with_list(flat, value)) == []


@pytest.mark.parametrize(
    "value",
    [
        "One point.",
        {"1": "One point."},
        [1],
        [None],
        [""],
        ["   "],
        ["a" * 301],
        ["two\nlines"],
        ["two\rlines"],
        ["two lines"],
        ["Same point", "same point "],
        [f"Point {n}" for n in range(1, 102)],
        [["nested"]],
    ],
)
def test_refused_lists_say_why(flat: Project, value: object) -> None:
    _with_list(flat, value)
    assert _issues(flat) == [TEXT]
    issue = next(i for i in configcheck.validate(flat) if i.object_id == "naming.review_checklist")
    assert (issue.severity, issue.code, issue.location) == ("error", "config_invalid", "config/naming.json")  # fmt: skip
    # a refused list is no list for the view, and config-invalid says why (and stops every release)
    assert review.points(flat) == ()
    assert any(f.rule == "config-invalid" and f.title == TEXT for f in run_drc(flat))


def test_points_and_the_list_hash(flat: Project) -> None:
    assert review.points(flat) == ()
    _with_list(flat, ["  First point.  ", "Second point."])
    assert review.points(flat) == ("First point.", "Second point.")
    digest = review.list_hash(review.points(flat))
    assert len(digest) == 8 and int(digest, 16) >= 0
    assert digest == review.list_hash(["First point.", "Second point."])
    assert digest != review.list_hash(["Second point.", "First point."])  # the order counts
    assert review.list_hash([]) != digest


def test_the_setting_is_registered_with_no_default_and_not_on_the_hand_over_list(
    flat: Project,
) -> None:
    s = settings.setting("naming", "review_checklist")
    assert (
        s is not None and s.kind == "names" and s.default is None and s.label == "Review checklist"
    )
    assert (
        s.range == "a list of points, each one line of 1 to 300 characters, each once, at most 100"
    )
    assert settings.effective(flat, "naming", "review_checklist").origin == "unset"
    assert configcheck.need_for("naming", "review_checklist") is None
    assert ("naming", "review_checklist") not in configcheck.FIELD_INFO
    before = configcheck.report(flat)
    assert configcheck.report(_with_list(flat, ["One point."])) == before  # `config` says the same


# ---- points_from_text (3.2) ---------------------------------------------------------------------


def test_the_template_gives_its_26_points_without_marks_and_backticks() -> None:
    found = review.points_from_text(TEMPLATE.read_text(encoding="utf-8"))
    assert len(found) == 26
    assert found[0] == "harness-design-studio check DIR prints no error."
    assert found[3] == (
        "harness-design-studio export DIR ran after the last change, and the Harness tab says the "
        "outputs are up to date."
    )
    assert found[6] == "No interface shows *auto-filled*: a person confirmed every connector the tool chose."  # fmt: skip
    assert found[-1] == "After the release: exported again, drawings show *released*, the change log has the entry."  # fmt: skip
    assert not any("`" in p or "**" in p or p.startswith(("- ", "[ ]")) for p in found)
    assert not any(p.startswith(("Project:", "These points", "Copy this")) for p in found)
    assert configcheck.checklist_problem(found) is None
    assert all(10 <= len(p) <= 300 for p in found)


def test_a_plain_file_gives_one_point_a_line() -> None:
    text = "# A heading\n\nFirst point.\n  Second point with `code`.  \n\n#also a heading\nThird.\n"
    assert review.points_from_text(text) == ["First point.", "Second point with code.", "Third."]


def test_a_file_with_list_items_skips_every_other_line() -> None:
    text = (
        "# Checklist\nProject: ____\n\n## Part one\n- [ ] **Bold** point.\n- [x] Ticked point.\n"
        "- [X] Ticked too.\n* Star point.\n+ Plus point.\n12. Numbered point.\n"
        "  - Indented point.\nA line of prose.\n-not an item\n"
    )
    assert review.points_from_text(text) == [
        "Bold point.", "Ticked point.", "Ticked too.", "Star point.", "Plus point.",
        "Numbered point.", "Indented point.",
    ]  # fmt: skip


def test_an_item_left_empty_is_no_point() -> None:
    assert review.points_from_text("- [ ] ``\n- [ ] Real point.\n") == ["Real point."]
    assert review.points_from_text("") == []
    assert review.points_from_text("# Only a heading\n") == []


# ---- plan_set_checklist ---------------------------------------------------------------------------


def test_plan_set_checklist_is_one_step_and_none_takes_the_key_out(flat: Project) -> None:
    before = flat.config["naming"]
    plan = configcheck.plan_set_checklist(flat, [" A point. ", "Another point."])
    assert plan.ok and len(plan.ops) == 1 and plan.value == ["A point.", "Another point."]
    history = History(flat)
    history.execute("Set the review checklist", plan.ops)
    assert flat.config["naming"].values["review_checklist"] == ["A point.", "Another point."]
    assert {k: v for k, v in flat.config["naming"].values.items() if k != "review_checklist"} == dict(before.values)  # fmt: skip
    assert configcheck.plan_set_checklist(flat, ["A point.", "Another point."]).ops == []
    history.undo()
    assert flat.config["naming"] == before
    history.redo()
    gone = configcheck.plan_set_checklist(flat, None)
    assert gone.ok and gone.value is None
    history.execute("Take the review checklist out", gone.ops)
    assert flat.config["naming"] == before
    assert configcheck.plan_set_checklist(flat, []).ops == []


def test_plan_set_checklist_refuses_a_list_with_the_text_of_the_check(flat: Project) -> None:
    plan = configcheck.plan_set_checklist(flat, ["Same", "same"])
    assert not plan.ok and plan.error == TEXT and plan.ops == []
    flat.read_only = True
    assert "read-only" in (configcheck.plan_set_checklist(flat, ["A point."]).error or "")


# ---- config DIR --review-checklist FILE -----------------------------------------------------------


def test_config_review_checklist_reads_the_template_and_none_takes_it_out(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "flat"
    templates.create_project(folder, "flatsat")
    naming = folder / "config" / "naming.json"
    before = naming.read_bytes()
    code_before = main(["config", str(folder)])
    capsys.readouterr()
    code = main(["config", str(folder), "--review-checklist", str(TEMPLATE)])
    out = capsys.readouterr().out
    listed = review.points_from_text(TEMPLATE.read_text(encoding="utf-8"))
    digest = review.list_hash(listed)
    assert code == code_before  # the exit code of `config` is the hand-over list's
    assert f"Review checklist: 26 points in config/naming.json (list {digest})." in out
    assert json.loads(naming.read_text(encoding="utf-8"))["values"]["review_checklist"] == listed
    assert review.points(load_project(folder).project) == tuple(listed)
    capsys.readouterr()
    main(["config", str(folder), "--review-checklist", "none", "--json"])
    doc = json.loads(capsys.readouterr().out)
    assert doc["changes"] == [
        "Review checklist: none (the key is taken out of config/naming.json)."
    ]
    assert naming.read_bytes() == before


@pytest.mark.parametrize(
    ("content", "why"),
    [
        (b"- [ ] Same point\n- [ ] same point\n", TEXT),
        (b"- [ ] " + b"x" * 301 + b"\n", TEXT),
        ("".join(f"- point {n}\n" for n in range(101)).encode(), TEXT),
        (b"\xff\xfe not text", "is not a UTF-8 text file."),
        (b"# Only a heading\n\n", "has no points"),
        (b"- " + b"x" * (64 * 1024), "is larger than 64 KiB"),
    ],
    # short IDs: pytest puts the test ID in an environment variable, which Windows limits to
    # 32,767 characters, so the file contents cannot be the ID
    ids=[
        "same-point-twice",
        "point-too-long",
        "101-points",
        "not-utf8",
        "no-points",
        "over-64-kib",
    ],
)
def test_config_review_checklist_refuses_a_file_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: bytes, why: str
) -> None:
    folder = tmp_path / "flat"
    templates.create_project(folder, "flatsat")
    naming = folder / "config" / "naming.json"
    before = naming.read_bytes()
    file = tmp_path / "list.md"
    file.write_bytes(content)
    capsys.readouterr()
    assert main(["config", str(folder), "--review-checklist", str(file)]) == 1
    err = capsys.readouterr().err
    assert why in err and "Nothing was changed." in err
    assert naming.read_bytes() == before
    assert main(["config", str(folder), "--review-checklist", str(tmp_path / "missing.md")]) == 1
    assert "is not a file" in capsys.readouterr().err


def test_settings_set_takes_the_list_as_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "flat"
    templates.create_project(folder, "flatsat")
    naming = folder / "config" / "naming.json"
    assert main(["settings", str(folder), "--set", 'naming.review_checklist=["One.", "Two."]']) == 0
    assert json.loads(naming.read_text(encoding="utf-8"))["values"]["review_checklist"] == ["One.", "Two."]  # fmt: skip
    before = naming.read_bytes()
    capsys.readouterr()
    assert main(["settings", str(folder), "--set", 'naming.review_checklist=["One.", "one."]']) == 1
    err = capsys.readouterr().err
    assert TEXT in err and "Nothing was changed." in err and naming.read_bytes() == before


# ---- generation, the content hash, a project of 4.2 (2.6, 3.4) ----------------------------------


def test_the_list_is_no_input_of_generation_but_part_of_the_content_hash(flat: Project) -> None:
    assert generation_status(flat) == "current"
    inputs, content = input_hash(flat), content_hash(flat)
    plan = configcheck.plan_set_checklist(flat, ["A point."])
    History(flat).execute("Set the review checklist", plan.ops)
    assert input_hash(flat) == inputs and generation_status(flat) == "current"
    assert content_hash(flat) != content  # the outputs are out of date until the export


def test_a_project_of_4_2_with_the_key_loads_saves_and_keeps_it(tmp_path: Path) -> None:
    root = examples_path()
    assert root is not None
    folder = copy_project(root / "projects" / "flatsat", tmp_path / "flat")
    plain = load_project(folder).project
    findings = [f.id for f in run_drc(plain)]
    naming = folder / "config" / "naming.json"
    edit_json(naming, lambda d: d["values"].__setitem__("review_checklist", ["Point one.", "Point two."]))  # fmt: skip
    p = load_project(folder).project
    assert p.meta.schema_version == SCHEMA_VERSION == 4
    assert configcheck.validate(p) == configcheck.validate(plain)
    assert generation_status(p) == generation_status(plain)
    changed = [f.id for f in run_drc(p) if not f.id.startswith("verify-mismatch.outputs_outdated")]
    assert changed == [f for f in findings if not f.startswith("verify-mismatch.outputs_outdated")]
    assert review.points(p) == ("Point one.", "Point two.")
    save_project(p, folder)
    assert json.loads(naming.read_text(encoding="utf-8"))["values"]["review_checklist"] == ["Point one.", "Point two."]  # fmt: skip
    # a change of another key of the same file keeps it
    assert main(["settings", str(folder), "--set", "naming.release_distinct_roles=true"]) == 0
    values = json.loads(naming.read_text(encoding="utf-8"))["values"]
    assert values["review_checklist"] == ["Point one.", "Point two."]
    assert values["release_distinct_roles"] is True


def test_no_example_template_or_new_project_has_a_checklist(tmp_path: Path) -> None:
    for name in ("blank", "first-steps", "minimal-satellite", "small-satellite", "flatsat"):
        p = templates.create_project(tmp_path / name, name)
        assert review.points(p) == (), name
        assert "review_checklist" not in (p.config.get("naming") or ConfigFile(name="naming", placeholder=False, values={})).values  # fmt: skip
