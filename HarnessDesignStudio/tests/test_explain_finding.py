# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""`explain DIR FINDING` (design of 4.3.0, section 7; pull request 3, owner question R9).

A finding ID, as `drc --json` gives it, is explained as the editor's *Explain* explains it
(`derive.explain_finding`): the limit of a rule with a limit, what a yes/no rule compares (the
`rule-check` derivation of `derive_rules`), a logical check and a note of the checks not run alike.
An ID is looked up among the findings only when it names no object, so every object keeps its
meaning; an ID that is neither gives the list of today with *a finding* added, and exit 2.
`--json` prints the derivations as a list, as for an object: no new key."""

import json
from pathlib import Path

import pytest

from harness_design_studio import api
from harness_design_studio.cli import explain as explain_cli
from harness_design_studio.cli.main import main
from harness_design_studio.core.derive import EXPLAINABLE_RULES


@pytest.fixture(scope="module")
def flat(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """`flatsat` with a voltage-drop limit its wires break: a finding of a rule with a limit."""
    folder = tmp_path_factory.mktemp("ef") / "flat"
    api.create_project(folder, "flatsat")
    api.set_config(folder, "derating", "max_voltage_drop_v", 0.1)
    api.generate(folder)
    return folder


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    capsys.readouterr()
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def _drc_ids(capsys: pytest.CaptureFixture[str], folder: Path) -> dict[str, dict[str, str]]:
    code, out, _ = _run(capsys, "drc", str(folder), "--json")
    assert code in (0, 1)
    return {f["id"]: f for f in json.loads(out)["findings"]}


def _as_json(capsys: pytest.CaptureFixture[str], folder: Path, oid: str) -> list[dict[str, object]]:
    code, out, err = _run(capsys, "explain", str(folder), oid, "--json")
    assert code == 0, err
    data = json.loads(out)
    assert isinstance(data, list)
    return data


def test_a_finding_of_a_rule_with_a_limit_shows_the_limit(
    flat: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert "voltage-drop.W001-001" in _drc_ids(capsys, flat)
    code, out, err = _run(capsys, "explain", str(flat), "voltage-drop.W001-001")
    assert code == 0 and err == ""
    assert out.startswith("Wire W001-001. Voltage drop: ")
    assert "the limit is 0.1 V: over the limit by" in out
    assert out.rstrip().endswith("Model page: docs/models/wire-sizing.md")
    assert "History of" not in out
    data = _as_json(capsys, flat, "voltage-drop.W001-001")
    assert [d["id"] for d in data] == ["wire-voltage-drop"]
    assert data == [d.to_explain_dict() for d in api.explain_finding(flat, "voltage-drop.W001-001")]


def test_a_finding_of_a_yes_no_rule_says_what_the_rule_compares(
    flat: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fid = "part-unapproved.EX-MICROD-15-M"
    assert fid in _drc_ids(capsys, flat)
    code, out, _ = _run(capsys, "explain", str(flat), fid)
    assert code == 0
    assert out.startswith("Rule part-unapproved for EX-MICROD-15-M. Approved parts: ")
    assert "Equation: this rule is a yes/no check: it compares the approval of each part" in out
    assert "Approval = pending   [parts library: EX-MICROD-15-M]" in out
    assert out.rstrip().endswith("Model page: docs/models/rule-limits.md")
    data = _as_json(capsys, flat, fid)
    assert [d["id"] for d in data] == ["rule-check"] and data[0]["model_page"]


@pytest.mark.parametrize(
    ("fid", "head"),
    [
        ("unconfirmed.IF-001", "Rule unconfirmed for IF-001. unconfirmed: IF-001 uses connectors"),
        ("unchecked-config.emc", "Rule unchecked-config for emc. Checks not run: EMC class"),
    ],
)
def test_a_logical_check_and_a_note_of_the_checks_not_run(
    flat: Path, capsys: pytest.CaptureFixture[str], fid: str, head: str
) -> None:
    assert fid in _drc_ids(capsys, flat)
    code, out, _ = _run(capsys, "explain", str(flat), fid)
    assert code == 0 and out.startswith(head)
    assert "this rule is a yes/no check" in out
    assert "Statement of the finding = " in out


def test_every_finding_of_drc_explains_as_the_editor_does(
    flat: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _drc_ids(capsys, flat)
    one_per_rule = {f["rule"]: fid for fid, f in sorted(ids.items())}
    assert {"voltage-drop", "part-unapproved", "unconfirmed", "unchecked-config"} <= set(
        one_per_rule
    )
    for rule, fid in sorted(one_per_rule.items()):
        assert rule in EXPLAINABLE_RULES, rule
        data = _as_json(capsys, flat, fid)
        assert data and data == [d.to_explain_dict() for d in api.explain_finding(flat, fid)], fid


def test_an_object_keeps_its_meaning(flat: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert [d["id"] for d in _as_json(capsys, flat, "W001-001")][:2] == ["wire-length", "gauge"]
    assert {d["id"] for d in _as_json(capsys, flat, "EX-MICROD-15-M")} == {"part-bom"}
    assert {d["id"] for d in _as_json(capsys, flat, "IF-001")} != {"rule-check"}
    code, out, _ = _run(capsys, "explain", str(flat), "HTR1")  # a device: its library record
    assert code == 0 and "Rule " not in out


def test_an_unknown_id_is_an_error(flat: Path, capsys: pytest.CaptureFixture[str]) -> None:
    expected = (
        "error: 'no-such.finding' is not a wire, a harness or a part used in a harness, nor an "
        "interface, a connector, a pin, a shield group, a test or a finding of this project.\n"
    )
    for more in ((), ("--json",)):
        code, out, err = _run(capsys, "explain", str(flat), "no-such.finding", *more)
        assert (code, out, err) == (2, "", expected)
    # the scripting interface keeps its own words: it explains objects only
    with pytest.raises(api.EditError, match=r"or a test\.$"):
        api.explain(flat, "no-such.finding")


def test_a_finding_with_nothing_to_show_says_so(
    flat: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # an extension's rule may give no derivation (S8): the finding is named, nothing is invented
    monkeypatch.setattr(explain_cli, "explain_finding", lambda *_: [])
    code, out, _ = _run(capsys, "explain", str(flat), "unconfirmed.IF-001")
    assert code == 0
    assert out == (
        "Finding unconfirmed.IF-001 (rule unconfirmed, object IF-001): IF-001 uses connectors "
        "the tool chose for you\nThe rule gives no calculation or comparison to show for it.\n"
    )
    assert _as_json(capsys, flat, "unconfirmed.IF-001") == []


def test_the_help_names_the_finding(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(capsys, "explain", "--help")
    assert code == 0
    assert "or a finding (unconfirmed.IF-001, as drc --json gives its ID)" in " ".join(out.split())
    assert "an object keeps its meaning" in " ".join(out.split())
