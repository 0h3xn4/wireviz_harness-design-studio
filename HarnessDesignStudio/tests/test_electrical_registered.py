# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-DRC-06, REQ-DRC-07, REQ-DRC-08, REQ-DRC-09. The four electrical rules of 4.2.0 registered
(design `docs/ait/DESIGN_4.2_ELECTRICAL_CHECKS.md`, pull request 4): 43 rules in `drc.RULES`, the scripting interface and the
command line; the notes of `electrical.unchecked` under `unchecked-config` and in the per-rule states
of the Checks tab; the explanation of a finding; `level-conflict` accepted as a deviation, which
reaches *Start here* and lets the release go on, while an open one blocks the release of its
harness; and the counts of section 2.7 of the design: none of the four fires on the five examples,
the drawn harnesses of the goldens give the findings the design lists, and the pinout-first project
gives them with the registered rules. Example data only."""

import json
from collections import Counter
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from harness_design_studio import api
from harness_design_studio.cli.main import main
from harness_design_studio.core import checks, deviations, drc, templates
from harness_design_studio.core.commands import apply_ops
from harness_design_studio.core.derive import explain_finding
from harness_design_studio.core.derive_kinds import page_of_rule
from harness_design_studio.core.drc import by_rule, electrical
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.links import plan_add_link, plan_create_harness
from harness_design_studio.core.manual_harness import plan_add_connector, plan_new_harness
from harness_design_studio.core.model import ConfigFile, Project, evolve
from harness_design_studio.core.outputs.build import build_outputs
from harness_design_studio.core.outputs.buildsheet import FILE_SUFFIX
from harness_design_studio.core.vcs.release import release_blockers
from harness_design_studio.core.wires import plan_add_wire
from tests.electrical_support import hand_made, linked, set_pin

NEW = ("pair-untwisted", "signal-unshielded", "level-conflict", "wire-direction")
NOTES = ("levels", "no-level", "level-unknown", "wire-direction-unknown")
EXAMPLES = ("blank", "first-steps", "minimal-satellite", "small-satellite", "flatsat")
WHEN = "2026-11-21"


def table(p: Project, pairs: object) -> Project:
    old = p.config.get("segregation")
    values = {**(old.values if old is not None else {}), "level_pairs_to_separate": pairs}
    p.config["segregation"] = ConfigFile(name="segregation", placeholder=True, values=values)
    return p


def counts(p: Project) -> tuple[dict[str, int], list[str]]:
    """The findings of the four rules by rule, and the object IDs of their notes."""
    found = drc.run(p)
    rules = Counter(f.rule for f in found if f.rule in NEW)
    notes = [f.object_id for f in found if f.rule == "unchecked-config" and f.object_id in NOTES]
    return dict(rules), notes


def leveled() -> tuple[Project, str]:
    """A wire drawn by hand from an 18V pin to an RS422-3V3 pin, with the table that keeps them
    apart: one `level-conflict` on the wire."""
    p, hid = hand_made(["RTN"], ["TX-"], [("1", "1")])
    set_pin(p, "OBC-J03", "1", level="18V")
    set_pin(p, "RW1-J02", "1", level="RS422-3V3")
    return table(p, [["18V", "RS422-3V3"]]), hid


# ---- the registry -------------------------------------------------------------------------------


def test_the_four_rules_are_registered_after_direction_conflict() -> None:
    ids = [r.id for r in drc.RULES]
    at = ids.index("direction-conflict")
    assert len(ids) == 43 and ids[at + 1 : at + 5] == list(NEW)
    assert [r.id for r in api.list_rules()] == ids
    assert {r.id: r.can_deviate for r in drc.RULES if r.id in NEW} == {
        "pair-untwisted": False, "signal-unshielded": False, "level-conflict": True,
        "wire-direction": False,
    }  # fmt: skip
    assert [r.id for r in electrical.ELECTRICAL_RULES] == list(NEW)
    assert page_of_rule("pair-untwisted") == page_of_rule("signal-unshielded") == "shields.md"
    assert page_of_rule("level-conflict") == page_of_rule("wire-direction") == "rule-limits.md"


def test_drc_and_the_scripting_interface_run_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    p, hid = linked()
    folder = tmp_path / "p"
    save_project(p, folder)
    capsys.readouterr()
    main(["drc", str(folder), "--json"])
    doc = json.loads(capsys.readouterr().out)
    assert doc["rules_run"] == 43
    rules = Counter(f["rule"] for f in doc["findings"] if f["rule"] in NEW)
    assert rules == {"pair-untwisted": 2, "signal-unshielded": 4}
    assert any(f["id"].startswith(f"pair-untwisted.{hid}.{hid}-001_") for f in doc["findings"])
    result = api.run_checks(folder)
    assert result.rules_run == 43
    assert Counter(f.rule for f in result.findings if f.rule in NEW) == rules
    main(["drc", str(folder)])
    report = capsys.readouterr().out
    assert "Rules run: 43." in report and f"Wires {hid}-001 (TX+) and {hid}-002 (TX-)" in report


def test_explain_of_a_finding_says_what_each_rule_saw() -> None:
    p, hid = linked()
    pair = explain_finding(p, "pair-untwisted", f"{hid}-001")[0]
    seen = {i.name: i.value for i in pair.inputs}
    assert pair.id == "rule-check" and pair.assumptions == ("A-PAIR-NAMES",)
    assert seen["Signal pair"] == f"{hid}-001 (TX+) and {hid}-002 (TX-)"
    assert seen["Why they are a pair"] == "pair TX of the interface type rs422"
    assert seen["Groups that hold them"] == "none"
    assert seen["Endings that make two signals a pair"] is not None  # the setting it reads
    shield = explain_finding(p, "signal-unshielded", f"{hid}-001")[0]
    seen = {i.name: i.value for i in shield.inputs}
    assert seen["Interface types of the signal"] == "rs422: per pair"
    assert seen["Made by Generate"] == "no"
    q, wid = leveled()
    level = explain_finding(q, "level-conflict", f"{wid}-001")[0]
    seen = {i.name: i.value for i in level.inputs}
    assert seen["Levels at the device ends"] == "pin 1 of OBC-J03: 18V, pin 1 of RW1-J02: RS422-3V3"
    assert level.text.endswith("two levels the project keeps apart")
    r, did = hand_made(["TX+"], ["TX+"], [("1", "1")])
    set_pin(r, "OBC-J03", "1", direction="out")
    direction = explain_finding(r, "wire-direction", f"{did}-001")[0]
    seen = {i.name: i.value for i in direction.inputs}
    assert "pin 1 of OBC-J03 (TX+): out, from the pin" in str(seen["Directions at the device ends"])
    assert direction.assumptions == ("A-DIRECTION-AT-DEVICE",)


# ---- the notes and the Checks tab ----------------------------------------------------------------


def state(p: Project, rule_id: str) -> by_rule.RuleResult:
    return next(r for r in by_rule.run_by_rule(p) if r.rule_id == rule_id)


def test_the_notes_are_in_unchecked_config_and_in_the_states_of_the_rules() -> None:
    p, _hid = hand_made(["RTN"], ["TX-"], [("1", "1")])
    set_pin(p, "OBC-J03", "1", direction="in")  # so that wire-direction has nothing to note
    set_pin(p, "RW1-J02", "1", direction="out")
    # no level and no table: level-conflict waits for its table, on screen only; no note
    assert counts(p) == ({}, [])
    s = state(p, "level-conflict")
    assert s.status == "pending" and s.notes == ()
    assert [(m.file, m.key, m.optional) for m in s.missing] == [
        ("segregation", "level_pairs_to_separate", True)
    ]
    # a pin with a level: the note `levels`, which the gate explains
    set_pin(p, "OBC-J03", "1", level="18V")
    assert counts(p) == ({}, ["levels"])
    s = state(p, "level-conflict")
    assert s.status == "pending" and s.notes[0].startswith("Signal levels were not checked: 1 pin")
    # the table set, a pin at an end without a level: not checked, with the note of the data
    table(p, [["18V", "RS422-3V3"]])
    assert counts(p) == ({}, ["level-unknown"])
    s = state(p, "level-conflict")
    assert s.status == "not_checked" and s.missing[0].kind == "data"
    # both levels: the finding, the rule fails
    set_pin(p, "RW1-J02", "1", level="RS422-3V3")
    assert counts(p) == ({"level-conflict": 1}, [])
    assert state(p, "level-conflict").status == "fail"


def test_the_note_of_wire_direction_is_its_state_not_checked() -> None:
    p, _hid = hand_made(["1PPS+"], ["1PPS+"], [("1", "1")])  # a signal no type has, no direction
    assert counts(p) == ({}, ["wire-direction-unknown"])
    s = state(p, "wire-direction")
    assert s.status == "not_checked" and s.notes[0].startswith("Directions were not checked for 1")
    set_pin(p, "OBC-J03", "1", direction="out")
    set_pin(p, "RW1-J02", "1", direction="in")
    assert counts(p) == ({}, [])
    assert state(p, "wire-direction").status == "pass"


# ---- the deviation and the release -------------------------------------------------------------


def test_level_conflict_blocks_the_release_until_it_is_accepted_as_a_deviation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    p, hid = leveled()
    folder = tmp_path / "p"
    save_project(p, folder)
    p = load_project(folder).project
    f = next(x for x in drc.run(p) if x.rule == "level-conflict")
    assert f.severity == "error" and f.can_deviate and not f.can_waive
    assert drc.locate(p, f.object_id) == ("harness", hid)

    def blocked(q: Project) -> list[str]:
        found = release_blockers(q, hid, by="Ada", comment="long enough text", when=WHEN, outputs_folder=None)  # fmt: skip
        return [b.message for b in found if b.code == "rule_error"]

    assert f.title in blocked(p)
    with pytest.raises(EditError, match="cannot be waived"):
        checks.waive_op(f, "a long enough reason")
    capsys.readouterr()
    reason = "Level shifter inside the device, ICD note 4"
    assert main(["deviation", str(folder), f.id, "--reason", reason]) == 0
    p = load_project(folder).project
    accepted = next(x for x in drc.run(p) if x.id == f.id)
    assert accepted.deviation and accepted.waiver is not None  # still on every list
    assert f.title not in blocked(p)
    lines = deviations.deviation_lines(p, p.harnesses[hid])
    assert len(lines) == 1 and reason in lines[0]
    files = build_outputs(p, drawings=False).files
    book = load_workbook(BytesIO(files[f"harnesses/{hid}/{hid}{FILE_SUFFIX}"]))
    start = " ".join(str(c.value) for row in book["Start here"].iter_rows() for c in row if c.value)
    assert "Overrides and deviations" in start and reason in start
    assert reason in files["system/drc_findings.csv"].decode()


def test_wire_direction_is_an_error_that_takes_no_deviation() -> None:
    p, _hid = hand_made(["TX+"], ["TX+"], [("1", "1")])
    set_pin(p, "OBC-J03", "1", direction="out")
    set_pin(p, "RW1-J02", "1", direction="out")
    f = next(x for x in drc.run(p) if x.rule == "wire-direction")
    assert f.severity == "error" and not f.can_deviate and not f.can_waive
    with pytest.raises(EditError, match="cannot be accepted as a deviation"):
        checks.deviate_op(f, "a long enough reason")


def test_a_finding_on_a_connection_without_a_harness_blocks_no_harness() -> None:
    p, hid = linked()
    link = next(iter(p.links.values()))
    p.harnesses.pop(hid)
    p.links[link.id] = evolve(link, harness_id="")
    set_pin(p, "OBC-J01", "1", level="18V")
    table(p, [["18V", "RS422-3V3"]])
    for pin in ("1", "2", "3", "4"):
        set_pin(p, "RW1-J02", pin, level="RS422-3V3")
    found = [f for f in drc.run(p) if f.rule == "level-conflict"]
    assert [f.object_id for f in found] == [link.id]
    assert drc.locate(p, link.id) is None  # so no harness's release counts it


def test_the_deviation_help_names_signal_levels(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["deviation", "--help"]) == 0
    assert "signal levels" in capsys.readouterr().out
    text = (Path(__file__).resolve().parent.parent / "docs" / "CLI.md").read_text(encoding="utf-8")
    assert "temperature margin, signal levels) with a reason" in text


# ---- the counts of section 2.7 of the design -----------------------------------------------------


@pytest.mark.parametrize("name", EXAMPLES)
def test_none_of_the_four_fires_on_an_example(name: str, tmp_path: Path) -> None:
    p = templates.create_project(tmp_path / name, name)
    if not p.harnesses:
        generate_project(p)  # as `tools.output_hashes` makes the example
    assert counts(p) == ({}, [])


def test_the_drawn_harnesses_of_the_goldens_give_the_findings_of_the_design(tmp_path: Path) -> None:
    from tests.loose_support import generated_loose
    from tests.splice_support import branch_leg_project

    loose = load_project(generated_loose(tmp_path / "loose")).project
    assert counts(loose) == (
        {"pair-untwisted": 3, "signal-unshielded": 4},
        ["wire-direction-unknown"],
    )
    assert counts(branch_leg_project()) == ({}, ["wire-direction-unknown"])


DEV1 = (
    "Pinout,Function,Direction,Level,Description,Mode\n"
    "1,TX+,OUT,RS422-3V3,Telemetry out,fixed\n"
    "2,TX-,OUT,RS422-3V3,Telemetry out,fixed\n"
    "3,RX+,IN,RS422-3V3,Commands in,fixed\n"
    "4,RX-,IN,RS422-3V3,Commands in,fixed\n"
    "5,SGND,SGND,,Signal ground,fixed\n"
    "6,PWR_RTN,PWR-RET,18V,Supply return,fixed\n"
    "7,TEST1,TEST,,Factory test,fixed\n"
)
DEV2 = (
    "Pinout,Function,Direction,Level,Description,Mode\n"
    "1,RX+,IN,RS422-3V3,Telemetry in,fixed\n"
    "2,RX-,IN,RS422-3V3,Telemetry in,fixed\n"
    "3,TX+,OUT,RS422-3V3,Commands out,fixed\n"
    "4,TX-,OUT,RS422-3V3,Commands out,fixed\n"
    "5,SGND,SGND,,Signal ground,fixed\n"
)


def test_the_pinout_first_project_gives_the_counts_of_the_design(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The last two rows of section 2.7: the devices of `tests/test_e2e_harness_plan.py`, a
    connection and its harness; then a harness drawn by hand and the level table. Seven
    `signal-unshielded`, not eight: W002-003 runs from the fixed pin PWR_RTN (signal RTN of port PWR
    of `discrete`, which shields nothing) to TX- (which `rs422` and `ethernet` shield per pair), so
    the types at its ends disagree and it asks for no shield."""
    proj = tmp_path / "proj"
    assert main(["new", str(proj), "--template", "blank"]) == 0
    for name, text, title in (("DEV1", DEV1, "Device one"), ("DEV2", DEV2, "Device two")):
        sheet = tmp_path / f"{name.lower()}.csv"
        sheet.write_text(text, encoding="utf-8", newline="\n")
        assert main(["import-pinout", str(proj), str(sheet), "--device", name, "--new-device", title, "--default-part", "EX-MICROD-9-M", "--column", "pin=Pinout"]) == 0  # fmt: skip
    capsys.readouterr()
    p = load_project(proj).project
    pins = [x for c in p.connectors.values() for x in c.pins]
    assert (sum(1 for x in pins if x.direction), sum(1 for x in pins if x.level)) == (8, 9)
    ops, lid = plan_add_link(p, "DEV1-J01", "DEV2-J01")
    apply_ops(p, ops)
    ops, w1 = plan_create_harness(p, lid)
    apply_ops(p, ops)
    assert counts(p) == ({"pair-untwisted": 2, "signal-unshielded": 4}, ["levels"])
    ops, w2 = plan_new_harness(p, "Drawn")
    apply_ops(p, ops)
    ends = []
    for box in ("DEV1-J01", "DEV2-J01"):
        ops, cid = plan_add_connector(p, w2, mates_with=box)
        apply_ops(p, ops)
        ends.append(cid)
    # TX+ to TX+, RX+ to RX+, the 18V return to TX-, TX- to RX-
    for a, b in (("1", "3"), ("3", "1"), ("6", "4"), ("2", "2")):
        apply_ops(p, plan_add_wire(p, w2, ends[0], a, ends[1], b))
    table(p, [["18V", "RS422-3V3"]])
    assert counts(p) == (
        {"pair-untwisted": 2, "signal-unshielded": 7, "level-conflict": 1, "wire-direction": 2},
        ["level-unknown", "wire-direction-unknown"],
    )
    unshielded = sorted(f.object_id for f in drc.run(p) if f.rule == "signal-unshielded")
    assert unshielded == [f"{w1}-00{n}" for n in (1, 2, 3, 4)] + [f"{w2}-00{n}" for n in (1, 2, 4)]
    notes = {f.object_id: f.title for f in drc.run(p) if f.rule == "unchecked-config"}
    assert f"(first: wire {w1}-005)" in notes["level-unknown"]
    assert f"(first: wire {w2}-003)" in notes["wire-direction-unknown"]
