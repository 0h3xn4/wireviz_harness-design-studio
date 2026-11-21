# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-DRC-06, REQ-DRC-07, REQ-DRC-08, REQ-DRC-09. The end-to-end walk of 4.2.0 (pull request 5
of section 15 of `docs/ait/DESIGN_4.2_ELECTRICAL_CHECKS.md`), through the command line wherever a
command exists and through the plans the editor runs (`History`) where none does (no command adds
a connection, makes its harness, draws a wire, moves a wire's pin or groups wires).

The pinout-first project of sections 2.7 and 10 of the design: a blank project; two RS-422 devices
whose pinouts come in through `import-pinout` with *Direction* and *Level*; a connection between
their connectors and the harness made from it (W001); `generate`, which keeps it; `drc --json`
with two `pair-untwisted`, four `signal-unshielded` and the note `levels` (the level table is
empty). Then the level table through `settings --set`, a harness drawn by hand between the same
two device connectors (W002) and `drc --json` with the counts of the corrected section 2.7: two
`pair-untwisted`, seven `signal-unshielded`, one `level-conflict`, two `wire-direction`, and the
notes `level-unknown` and `wire-direction-unknown`. `export` writes them into
`system/drc_findings.csv` and `system/drc_report.md` (*Rules run: 43.*); `explain --all` says what
each of the four rules saw. Then the fixes a person makes: the two wires moved to the pins that
fit, a gauge and a length, *Group wires* as a shielded pair; `review` and `release`, which the
level conflict alone blocks; `deviation` accepts it, the release goes on, the findings file marks
it and the build workbook's *Start here* lists it; `verify --outputs` with 0 errors. Last, an
exported `flatsat` has no finding and no note of the four rules.

Example data only: example devices DEV1 and DEV2 with example pinouts, an example reviewer."""

import csv
import io
import json
from collections import Counter
from pathlib import Path

import openpyxl
import pytest

from harness_design_studio.core.commands import History
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.links import plan_add_link, plan_create_harness
from harness_design_studio.core.manual_harness import plan_add_connector, plan_new_harness
from harness_design_studio.core.wires import plan_add_wire, plan_group_wires, plan_wire_edit
from tests.test_e2e_300 import ok
from tests.test_e2e_harness_plan import DEV1, DEV2
from tests.test_e2e_rs422x3 import run

NEW = ("pair-untwisted", "signal-unshielded", "level-conflict", "wire-direction")
NOTES = ("levels", "no-level", "level-unknown", "wire-direction-unknown")
TABLE = '[["18V", "RS422-3V3"]]'
WHO = ["--by", "Example Reviewer", "--date", "2026-11-21"]
ACCEPT = [
    "--accept-placeholders", "Example data for the test",
    "--accept-unapproved-parts", "Example data for the test",
]  # fmt: skip
REASON = "Level shifter inside DEV2, example ICD note 4"
LEVEL = (
    "Wire W002-003 in W002 joins pin 6 of DEV1-J01 (level 18V) and pin 4 of DEV2-J01 "
    "(level RS422-3V3), two levels the project keeps apart"
)
TWO_OUTPUTS = (
    "Wire W002-001 in W002 joins pin 1 of DEV1-J01 (TX+, an output) and pin 3 of DEV2-J01 "
    "(TX+, an output): two outputs drive against each other"
)
NO_DRIVER = (
    "Wire W002-002 in W002 joins pin 3 of DEV1-J01 (RX+, an input) and pin 1 of DEV2-J01 "
    "(RX+, an input): nothing drives the wire"
)


def drc_json(capsys: pytest.CaptureFixture[str], proj: Path) -> dict[str, object]:
    """`drc DIR --json`; it exits 1 while an error is open, 0 otherwise."""
    code, out = run(capsys, "drc", str(proj), "--json")
    doc: dict[str, object] = json.loads(out)
    assert code == (1 if doc["open_errors"] else 0), out
    return doc


def counts(doc: dict[str, object]) -> tuple[dict[str, int], list[str]]:
    """The findings of the four rules by rule, and the object IDs of their notes."""
    found: list[dict[str, str]] = doc["findings"]  # type: ignore[assignment]
    rules = Counter(f["rule"] for f in found if f["rule"] in NEW)
    notes = [f["object_id"] for f in found if f["rule"] == "unchecked-config"]
    return dict(rules), [n for n in notes if n in NOTES]


def findings_rows(outputs: Path) -> list[dict[str, str]]:
    """The rows of `system/drc_findings.csv`, its comment lines left out."""
    text = (outputs / "system" / "drc_findings.csv").read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    return list(csv.DictReader(io.StringIO(body)))


def pinout_first(proj: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A blank project, the two devices from their pinouts, a connection and its harness W001."""
    ok(capsys, "new", proj, "--template", "blank")
    for name, text, title in (("DEV1", DEV1, "Device one"), ("DEV2", DEV2, "Device two")):
        sheet = tmp_path / f"{name.lower()}.csv"
        sheet.write_text(text, encoding="utf-8", newline="\n")
        out = ok(
            capsys, "import-pinout", proj, sheet, "--device", name, "--new-device", title,
            "--default-part", "EX-MICROD-9-M", "--column", "pin=Pinout",
        )  # fmt: skip
        assert f"{name}-J01: OK added" in out
    p = load_project(proj).project
    pins = [x for c in p.connectors.values() for x in c.pins]
    assert (sum(1 for x in pins if x.direction), sum(1 for x in pins if x.level)) == (8, 9)
    # the editor's Connect and Create harness (no command makes a connection or its harness)
    history = History(p)
    ops, lid = plan_add_link(p, "DEV1-J01", "DEV2-J01")
    history.execute(f"Connect {lid}", ops)
    ops, hid = plan_create_harness(p, lid)
    history.execute(f"Create harness {hid}", ops)
    save_project(p, proj)
    assert (lid, hid) == ("L1", "W001")


def draw_by_hand(proj: Path) -> None:
    """A harness drawn by hand between the same two device connectors: TX+ to TX+, RX+ to RX+,
    the 18V return to TX-, TX- to RX- (section 2.7 of the design)."""
    p = load_project(proj).project
    history = History(p)
    ops, hid = plan_new_harness(p, "Drawn")
    history.execute(f"New harness {hid}", ops)
    ends = []
    for box in ("DEV1-J01", "DEV2-J01"):
        ops, cid = plan_add_connector(p, hid, mates_with=box)
        history.execute(f"Add {cid}", ops)
        ends.append(cid)
    for a, b in (("1", "3"), ("3", "1"), ("6", "4"), ("2", "2")):
        history.execute("Draw a wire", plan_add_wire(p, hid, ends[0], a, ends[1], b))
    save_project(p, proj)
    assert hid == "W002" and len(p.harnesses[hid].wires) == 4


def fix_by_hand(proj: Path) -> None:
    """What a person does about the findings in the editor: the two wires of the wrong
    directions moved to the pins that fit (TX+ to RX+, RX+ to TX+), a gauge and a length on each
    drawn wire, and the TX pair grouped as a shielded pair."""
    p = load_project(proj).project
    history = History(p)
    history.execute("Move the pin", plan_wire_edit(p, ["W002-001"], {"to_pin": "1"}))
    history.execute("Move the pin", plan_wire_edit(p, ["W002-002"], {"to_pin": "3"}))
    for w in p.harnesses["W002"].wires:
        history.execute("Edit wire", plan_wire_edit(p, [w.id], {"gauge_awg": 24, "length_m": 1.2}))
    history.execute("Group wires", plan_group_wires(p, ["W002-001", "W002-004"], "shielded_pair"))
    save_project(p, proj)


def test_the_electrical_checks_of_4_2_0_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = tmp_path / "proj"
    outputs = proj / "outputs"
    # 1. pinout first: the devices with directions and levels, a connection and its harness
    pinout_first(proj, tmp_path, capsys)
    out = ok(capsys, "generate", proj)
    assert "1 connection(s) and no interface" in out
    assert list(load_project(proj).project.harnesses) == ["W001"]  # Generate keeps it

    # 2. drc: the pairs of W001 are not twisted and not shielded; levels are not checked
    doc = drc_json(capsys, proj)
    assert doc["rules_run"] == 43
    assert counts(doc) == ({"pair-untwisted": 2, "signal-unshielded": 4}, ["levels"])
    titles = {f["object_id"]: f["title"] for f in doc["findings"]}  # type: ignore[attr-defined]
    assert titles["levels"].startswith(
        "Signal levels were not checked: 9 pin(s) have a level (18V, RS422-3V3), but no pairs"
    )

    # 3. the level table, a harness drawn by hand, drc: the counts of section 2.7
    assert "1 value(s) set." in ok(
        capsys, "settings", proj, "--set", f"segregation.level_pairs_to_separate={TABLE}"
    )
    config = json.loads((proj / "config" / "segregation.json").read_text(encoding="utf-8"))
    assert config["values"]["level_pairs_to_separate"] == [["18V", "RS422-3V3"]]
    draw_by_hand(proj)
    ok(capsys, "generate", proj)  # Generate keeps the harness a person drew
    doc = drc_json(capsys, proj)
    assert counts(doc) == (
        {"pair-untwisted": 2, "signal-unshielded": 7, "level-conflict": 1, "wire-direction": 2},
        ["level-unknown", "wire-direction-unknown"],
    )
    found: list[dict[str, str]] = doc["findings"]  # type: ignore[assignment]
    by_rule: dict[str, list[dict[str, str]]] = {}
    for f in found:
        by_rule.setdefault(f["rule"], []).append(f)
    assert sorted(f["object_id"] for f in by_rule["signal-unshielded"]) == [
        "W001-001", "W001-002", "W001-003", "W001-004", "W002-001", "W002-002", "W002-004",
    ]  # fmt: skip
    assert [f["object_id"] for f in by_rule["pair-untwisted"]] == ["W001-001", "W001-003"]
    level = by_rule["level-conflict"][0]
    assert (level["object_id"], level["severity"], level["title"]) == ("W002-003", "error", LEVEL)
    assert [f["title"] for f in by_rule["wire-direction"]] == [TWO_OUTPUTS, NO_DRIVER]
    notes = {f["object_id"]: f["title"] for f in by_rule["unchecked-config"]}
    assert "(first: wire W001-005)" in notes["level-unknown"]  # the SGND net has no level
    assert "(first: wire W002-003)" in notes["wire-direction-unknown"]  # the return pin

    # 4. export: the findings files hold them
    ok(capsys, "export", proj)
    rows = findings_rows(outputs)
    assert Counter(r["Rule"] for r in rows if r["Rule"] in NEW) == {
        "pair-untwisted": 2, "signal-unshielded": 7, "level-conflict": 1, "wire-direction": 2,
    }  # fmt: skip
    assert {r["Statement"] for r in rows} >= {LEVEL, TWO_OUTPUTS, NO_DRIVER}
    assert {"level-unknown", "wire-direction-unknown"} <= {r["Object"] for r in rows}
    report = (outputs / "system" / "drc_report.md").read_text(encoding="utf-8")
    assert "Rules run: 43." in report and LEVEL in report

    # 5. explain: what each of the four rules saw at one finding
    ok(capsys, "explain", proj, "--all", "--out", tmp_path / "derivations")
    derived = json.loads((tmp_path / "derivations" / "derivations.json").read_text("utf-8"))
    seen = {
        d["subject"]: {i["name"]: i["value"] for i in d["inputs"]}
        for d in derived["derivations"]
        if d["id"] == "rule-check"
    }
    pair = seen["Rule pair-untwisted for W001-001"]
    assert pair["Signal pair"] == "W001-001 (TX+) and W001-002 (TX-)"
    assert pair["Why they are a pair"] == "pair TX of the interface types ethernet, rs422"
    assert pair["Groups that hold them"] == "none"
    assert pair["Endings that make two signals a pair"] == "+ -, P N, H L"  # not ++-
    shield = seen["Rule signal-unshielded for W002-001"]
    assert shield["Interface types of the signal"] == "ethernet: per pair, rs422: per pair"
    assert shield["Made by Generate"] == "no"
    levels = seen["Rule level-conflict for W002-003"]
    assert levels["Levels at the device ends"] == (
        "pin 6 of DEV1-J01: 18V, pin 4 of DEV2-J01: RS422-3V3"
    )
    assert levels["Signal levels kept apart"] == "18V+RS422-3V3"
    directions = seen["Rule wire-direction for W002-001"]
    assert directions["Directions at the device ends"] == (
        "pin 1 of DEV1-J01 (TX+): out, from the pin, pin 3 of DEV2-J01 (TX+): out, from the pin"
    )

    # 6. the fixes: the directions right, the TX pair a shielded pair; the level conflict stays
    fix_by_hand(proj)
    doc = drc_json(capsys, proj)
    assert counts(doc) == (
        {"pair-untwisted": 2, "signal-unshielded": 5, "level-conflict": 1},
        ["level-unknown", "wire-direction-unknown"],
    )
    unshielded = [f for f in doc["findings"] if f["rule"] == "signal-unshielded"]  # type: ignore[attr-defined]
    assert [f["object_id"] for f in unshielded][-1] == "W002-002"  # the RX+ wire, alone

    # 7. the release of W002: blocked by the level conflict alone, until it is a deviation
    ok(capsys, "export", proj)
    ok(capsys, "review", proj, "W002", *WHO)
    code, out = run(capsys, "release", str(proj), "W002", *WHO, "--comment", "First build", *ACCEPT)
    assert code == 1
    assert [line for line in out.splitlines() if line.startswith("blocked:")] == [
        f"blocked: [rule_error] {LEVEL}"
    ]
    finding = level["id"]
    out = ok(capsys, "deviation", proj, finding, "--reason", REASON)
    assert f"DEVIATION recorded for {finding}" in out
    assert finding in ok(capsys, "deviation", proj)
    ok(capsys, "export", proj)
    out = ok(capsys, "release", proj, "W002", *WHO, "--comment", "First build", *ACCEPT)
    assert "Release W002 version 1.0.0: done." in out
    assert "0 error(s)" in ok(capsys, "verify", proj, "--outputs")

    # 8. the written files of the release: the deviation in the findings file and on Start here
    accepted = next(r for r in findings_rows(outputs) if r["Finding"] == finding)
    assert (accepted["Waived"], accepted["Justification"]) == ("deviation", REASON)
    assert not any(r["Rule"] == "wire-direction" for r in findings_rows(outputs))
    report = (outputs / "system" / "drc_report.md").read_text(encoding="utf-8")
    assert f"**DEVIATION** {LEVEL}" in report
    book = openpyxl.load_workbook(outputs / "harnesses" / "W002" / "W002_build.xlsx")
    start = [str(c.value) for row in book["Start here"].iter_rows() for c in row if c.value]
    assert "Overrides and deviations" in start
    assert any(REASON in text and "level-conflict" in text for text in start)


def test_an_exported_example_has_no_finding_of_the_four_rules(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = tmp_path / "flatsat"
    ok(capsys, "new", proj, "--template", "flatsat")
    ok(capsys, "export", proj)
    rows = findings_rows(proj / "outputs")
    assert rows  # the example has findings of other rules
    assert not [r for r in rows if r["Rule"] in NEW or r["Object"] in NOTES]
    report = (proj / "outputs" / "system" / "drc_report.md").read_text(encoding="utf-8")
    assert "Rules run: 43." in report
    assert not any(rule in report for rule in NEW)
