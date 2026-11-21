# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The settings of the electrical rules of 4.2.0 (design `docs/ait/DESIGN_4.2_ELECTRICAL_CHECKS.md`,
section 7): `naming.pair_suffixes`, the endings that make two signal names a pair. Accepted and
refused values with the texts of `config_invalid`, `settings --set`, the Assumptions page, and a
project of 4.1 that holds the key: it loads, saves and keeps it, and nothing else changes (the
project format stays 4, no rule reads the key in a written file yet)."""

import json
from pathlib import Path

import pytest

from harness_design_studio.cli.main import main
from harness_design_studio.core import configcheck, settings, templates
from harness_design_studio.core.drc import run as run_drc
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import ConfigFile, Project
from harness_design_studio.core.model.project import SCHEMA_VERSION
from harness_design_studio.resources import examples_path
from tests.helpers import copy_project, edit_json


def _with_naming(p: Project, **values: object) -> Project:
    old = p.config.get("naming")
    base = dict(old.values) if old is not None else {}
    p.config["naming"] = ConfigFile(name="naming", placeholder=False, values={**base, **values})
    return p


def _issues(p: Project) -> list[str]:
    return [i.message for i in configcheck.validate(p) if i.object_id == "naming.pair_suffixes"]


@pytest.fixture
def flat(tmp_path: Path) -> Project:
    return templates.create_project(tmp_path / "flat", "flatsat")


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        [["+", "-"]],
        [["A", "B"], ["P1", "N1"], ["POS", "NEG"]],
        [["+", "-"], ["P", "N"], ["H", "L"]],
        [["p", "P"]],
    ],  # fmt: skip
)
def test_accepted_endings(flat: Project, value: object) -> None:
    assert _issues(_with_naming(flat, pair_suffixes=value)) == []


@pytest.mark.parametrize(
    ("value", "why"),
    [
        ("+-", 'must be a list of pairs of endings, for example [["+", "-"], ["P", "N"]]'),
        ([["P"]], 'must be a list of pairs of two endings of 1 to 3 characters (letters, digits, + and -), for example ["P", "N"]'),
        ([["PLUS", "N"]], 'must be a list of pairs of two endings of 1 to 3 characters (letters, digits, + and -), for example ["P", "N"]'),
        ([["*", "-"]], 'must be a list of pairs of two endings of 1 to 3 characters (letters, digits, + and -), for example ["P", "N"]'),
        ([["", "-"]], 'must be a list of pairs of two endings of 1 to 3 characters (letters, digits, + and -), for example ["P", "N"]'),
        ([["P", "P"]], "has the pair 'P' and 'P', which is one ending twice"),
        ([["P", "N"], ["N", "Q"]], "uses the ending 'N' in two pairs; an ending meets one other ending"),
        ([["P", "N"], ["N", "P"]], "uses the ending 'N' in two pairs; an ending meets one other ending"),
    ],
)  # fmt: skip
def test_refused_endings_say_why(flat: Project, value: object, why: str) -> None:
    _with_naming(flat, pair_suffixes=value)
    assert _issues(flat) == [f"config/naming.json: pair_suffixes {why}."]
    issue = next(i for i in configcheck.validate(flat) if i.object_id == "naming.pair_suffixes")
    assert (issue.severity, issue.code, issue.location) == ("error", "config_invalid", "config/naming.json")  # fmt: skip


def test_the_setting_is_in_the_registry_with_its_default_and_not_on_the_hand_over_list(
    flat: Project,
) -> None:
    s = settings.setting("naming", "pair_suffixes")
    assert s is not None and s.kind == "pairs" and s.assumption == "A-PAIR-NAMES"
    assert s.default == (("+", "-"), ("P", "N"), ("H", "L"))
    e = settings.effective(flat, "naming", "pair_suffixes")
    assert e.origin == "default"
    assert settings.display_of(s, e.value) == "+ -, P N, H L"
    assert configcheck.need_for("naming", "pair_suffixes") is None
    assert ("naming", "pair_suffixes") not in configcheck.FIELD_INFO
    assert "pair_suffixes = + -, P N, H L   [the tool's own default]" in settings.render(flat)
    before = configcheck.report(flat)
    assert configcheck.report(_with_naming(flat, pair_suffixes=[["A", "B"]])) == before


def test_settings_set_writes_the_endings_and_refuses_a_wrong_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "flat"
    templates.create_project(folder, "flatsat")
    naming = folder / "config" / "naming.json"
    assert main(["settings", str(folder), "--set", 'naming.pair_suffixes=[["+", "-"], ["A", "B"]]']) == 0  # fmt: skip
    assert json.loads(naming.read_text(encoding="utf-8"))["values"]["pair_suffixes"] == [["+", "-"], ["A", "B"]]  # fmt: skip
    before = naming.read_bytes()
    capsys.readouterr()
    assert main(["settings", str(folder), "--set", 'naming.pair_suffixes=[["A", "A"]]']) == 1
    err = capsys.readouterr().err
    assert "pair_suffixes has the pair 'A' and 'A', which is one ending twice" in err
    assert "Nothing was changed." in err and naming.read_bytes() == before


def test_a_project_of_4_1_with_the_key_loads_saves_and_keeps_it(tmp_path: Path) -> None:
    root = examples_path()
    assert root is not None
    folder = copy_project(root / "projects" / "flatsat", tmp_path / "flat")
    plain = load_project(folder).project
    findings = [f.id for f in run_drc(plain)]
    assert not any(f.startswith("verify-mismatch.outputs_outdated") for f in findings)
    naming = folder / "config" / "naming.json"
    edit_json(naming, lambda d: d["values"].__setitem__("pair_suffixes", [["+", "-"], ["P", "N"]]))
    p = load_project(folder).project
    assert p.meta.schema_version == SCHEMA_VERSION == 4
    assert configcheck.validate(p) == configcheck.validate(plain)
    # no registered rule reads the key yet; the outputs are older than a changed config file, as
    # for any change of a value
    changed = [f.id for f in run_drc(p) if not f.id.startswith("verify-mismatch.outputs_outdated")]
    assert changed == findings
    save_project(p, folder)
    assert json.loads(naming.read_text(encoding="utf-8"))["values"]["pair_suffixes"] == [["+", "-"], ["P", "N"]]  # fmt: skip
    # a change of another key of the same file keeps it
    assert main(["settings", str(folder), "--set", "naming.release_distinct_roles=true"]) == 0
    values = json.loads(naming.read_text(encoding="utf-8"))["values"]
    assert values["pair_suffixes"] == [["+", "-"], ["P", "N"]] and values["release_distinct_roles"] is True  # fmt: skip
