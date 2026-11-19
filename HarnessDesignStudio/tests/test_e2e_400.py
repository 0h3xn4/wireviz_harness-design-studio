# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-call"
"""REQ-MIGRATE-09, REQ-PIN-06, REQ-PIN-07, REQ-OUT-12. The end-to-end walk of 4.0.0 (D-251, pull
request 6 of section 14 of `docs/ait/DESIGN_4.0_ROW_LAYOUT.md`), through the command line only.

A project as 3.0.x saved it: the sample `mini3`, generated and saved, with the number 3 in
`project.json` (`tests/migration_support.as_format`; the step from 3 to 4 writes the number and
nothing else, so these are the bytes a 3.0.x tool writes). `generate` refuses it until the upgrade;
`migrate --dry-run` names `project.json` only and writes nothing; `migrate` writes format 4, keeps
the backup `.migration-backup-v3/` and changes no other file (beside the journal's entry of the
step and the copy `project.json.bak` the save keeps). The project without a layout writes
what 3.0.x wrote, apart from the older names that pull request R dropped: every file of
`export --drawings` is the golden of `mini3` (`tests/fixtures/outputs/mini3.json`, which differs
from the golden of 3.0.0 in `system/export.json` only), and `system/export.json` with `revision`
put back beside each `version` and `format_version` 1 is the file of 3.0.0 byte for byte.

Then the rows: `pin-rows --part EX-MICROD-9-F --lengths 5,4` (rows of a part that names pins its
connectors lack: `row_layout_pin_missing`); `--set "1 3 / 2"` on the part and own rows `1 / 3 / 2`
on the box connector RW1-J01 (its plug W001-P2 takes the part's rows: `row_layout_mate_differs`);
`drc` with `generation.power_return_gap_pins` 1 judges the face (PCDU-J01: pins 1 and 2 neighbours
across the rows) and no longer the list pair of RW1-J01, whose pins 1 and 2 are two rows apart;
`export-pinout` read back by `import-pinout` as no change; a pinout with *Pin row* for another
connector (PCDU-J02, pin 3 in no row: `row_layout_pins_outside`); `explain` with the rows and their
source; `export --harness-plan` with the *Pin row* column, the plan's column F and the near block
row by row; `verify --outputs` with 0 errors; `export.json` with `row_layout`; a second export
byte-identical.

Example data only: the sample's devices and example rows (no real Micro-D, L3)."""

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.layout import model_hash
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.outputs import harness_plan as hp
from harness_design_studio.core.samples import mini3
from tests.helpers import FIXTURES, output_digests
from tests.migration_support import as_format
from tests.plan_support import check_values, read_plan
from tests.test_e2e_300 import ok
from tests.test_e2e_rs422x3 import files, run
from tests.test_row_layout_outputs import near_block

PART = "EX-MICROD-9-F"
# The SHA-256 of `system/export.json` of mini3 as 3.0.0 wrote it (`tests/fixtures/outputs/mini3.json`
# at the tag v3.0.0), and its model hash: the generation record names the version that generated,
# so the model hash of a generated project changes with the version (3.1.0 wrote another one), and
# `as_3x` reads the generator's version and the model hash as those of 3.0.0.
EXPORT_JSON_300 = "f53755715c033fc25963f58ef13966c27a1000c483d86bc1aa15eade67b1a04a"
MODEL_HASH_300 = "c370e71b1811953a0ea140b4c415278e171f8149143e9465c8d25aaca565845a"


def made_by_3x(proj: Path) -> None:
    """mini3, generated, as a 3.0.x tool saved it."""
    p = mini3()
    generate_project(p)
    save_project(p, proj)
    as_format(proj, 3)


def as_3x(export_json: bytes) -> bytes:
    """`system/export.json` in the form 3.0.x wrote it: `revision` beside each `version`,
    `format_version` 1, and the generator's version and the model hash read as 3.0.0's."""
    doc = json.loads(export_json)
    assert doc["format_version"] == 2
    assert all("revision" not in h for h in doc["harnesses"])
    doc["format_version"] = 1
    doc["generator"]["version"] = "3.0.0"
    doc["model_hash"] = MODEL_HASH_300
    for h in doc["harnesses"]:
        h["revision"] = h["version"]
    return (json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()


def project_files(proj: Path) -> dict[str, bytes]:
    """The files of the project, without the lock files a command leaves."""
    return {k: v for k, v in files(proj).items() if not k.startswith(".harness.lock")}


def table(path: Path) -> list[list[str]]:
    lines = [x for x in path.read_text(encoding="utf-8").splitlines() if not x.startswith("#")]
    return list(csv.reader(io.StringIO("\n".join(lines))))


def findings(out: str, rule: str) -> list[str]:
    return [line for line in out.splitlines() if f"(`{rule}." in line]


def test_the_whole_path_of_4_0_0_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = tmp_path / "proj"
    # 1. a project of 3.0.x
    made_by_3x(proj)
    before = project_files(proj)

    # 2. the upgrade: the number and nothing else
    code, out = run(capsys, "generate", str(proj))
    assert code != 0 and "migrate" in out  # a format 3 project is written only by migrate
    assert project_files(proj) == before
    out = ok(capsys, "migrate", proj, "--dry-run")
    assert "Project format 3; this tool writes format 4." in out
    assert "Files that would change (1):\n  changed  project.json\n" in out
    assert "(equal)" in out and "Nothing was written." in out
    assert project_files(proj) == before
    out = ok(capsys, "migrate", proj)
    assert "Format 3 to 4. Record: .migration-backup-v3/MIGRATION.json." in out
    after = {
        k: v for k, v in project_files(proj).items() if not k.startswith(".migration-backup-v3/")
    }
    changed = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    # project.json, the copy of the file it replaced, and the journal's entry of the step
    assert changed - {"journal.jsonl"} == {"project.json", "project.json.bak"}
    assert after["project.json.bak"] == before["project.json"]
    assert json.loads(after["project.json"])["schema_version"] == 4
    assert {
        k: v for k, v in json.loads(before["project.json"]).items() if k != "schema_version"
    } == {k: v for k, v in json.loads(after["project.json"]).items() if k != "schema_version"}
    assert (proj / ".migration-backup-v3" / "project.json").read_bytes() == before["project.json"]

    # 3. without a layout: what 3.0.x wrote, apart from the older names of R
    ok(capsys, "export", proj, "--drawings")
    outputs = proj / "outputs"
    written = output_digests(files(outputs))
    golden = json.loads((FIXTURES / "outputs" / "mini3.json").read_bytes())
    assert written.keys() - {"manifest.json"} == golden.keys()
    assert {k: written[k] for k in golden} == golden
    export_json = (outputs / "system" / "export.json").read_bytes()
    assert hashlib.sha256(as_3x(export_json)).hexdigest() == EXPORT_JSON_300
    assert "Pin row" not in (outputs / "system" / "box_pinouts.csv").read_text(encoding="utf-8")

    # 4. the rule's setting, then the pins in the order of the list (as at 3.0.x)
    ok(capsys, "settings", proj, "--set", "generation.power_return_gap_pins=1")
    ok(capsys, "generate", proj)
    code, out = run(capsys, "drc", str(proj))
    adjacent = findings(out, "power-return-adjacent")
    assert [line.split(":")[0] for line in adjacent] == ["- **PCDU-J01", "- **RW1-J01"]
    assert all("have 0 unassigned contact(s) between them" in line for line in adjacent)

    # 5. pin-rows on a part: rows that name pins its connectors lack
    out = ok(capsys, "pin-rows", proj, "--part", PART, "--lengths", "5,4")
    assert "Pin rows of part EX-MICROD-9-F: 1–5 / 6–9" in out
    out = ok(capsys, "check", proj)
    missing = [line for line in out.splitlines() if "row_layout_pin_missing" in line]
    assert {line.split("which ")[1].split(" does")[0] for line in missing} == {
        "OBC-J02", "PCDU-J01", "PCDU-J02", "W001-P1", "W001-P2"
    }  # fmt: skip
    assert all(line.startswith("WARNING") for line in missing)

    # 6. the rows of the part, and own rows on a box connector
    out = ok(capsys, "pin-rows", proj, "--part", PART, "--set", "1 3 / 2")
    assert "Row 1: 1 3\n  Row 2: 2\n" in out
    code, out = run(capsys, "pin-rows", str(proj), "--connector", "RW1-J01", "--set", "1 / 3 / 2", "--json")  # fmt: skip
    assert code == 0, out
    record = json.loads(out)
    assert (record["changed"], record["source"], record["text"]) == (True, "own", "1 / 3 / 2")
    out = ok(capsys, "pin-rows", proj, "--connector", "W001-P2")
    assert out.startswith("Pin rows of W001-P2: 1 3 / 2 (from part EX-MICROD-9-F)\n")
    out = ok(capsys, "check", proj)
    assert "row_layout_pin_missing" not in out
    assert (
        "WARNING row_layout_mate_differs: W001-P2 and the device connector RW1-J01 it plugs into "
        "have different row layouts" in out
    )

    # 7. the face rule: PCDU-J01 across the rows; RW1-J01's pins 1 and 2 are two rows apart
    code, out = run(capsys, "drc", str(proj))
    adjacent = findings(out, "power-return-adjacent")
    assert adjacent == [
        "- **PCDU-J01: PWR (pin 1) and RTN (pin 2) are neighbours on the face of the connector "
        "(rows 1 and 2), with no unassigned contact between them** "
        "(`power-return-adjacent.PCDU-J01.1_2.a335d3e6`)  "
    ]

    # 8. export-pinout read back: no change
    sheet = tmp_path / "pcdu.csv"
    ok(capsys, "export-pinout", proj, "--device", "PCDU", "--output", sheet)
    rows = table(sheet)
    at = rows[0].index("Pin row")
    assert [(r[0], r[4], r[at]) for r in rows[1:4]] == [
        ("PCDU-J01", "1", "1"), ("PCDU-J01", "2", "2"), ("PCDU-J01", "3", "1")
    ]  # fmt: skip
    model = model_hash(load_project(proj).project)
    out = ok(capsys, "import-pinout", proj, sheet, "--device", "PCDU")
    assert "Already up to date." in out and "Row layouts set" not in out
    assert model_hash(load_project(proj).project) == model

    # 9. a pinout with Pin row for another connector: own rows, pin 3 in no row
    for r in rows[1:]:
        if r[0] == "PCDU-J02":
            r[at] = {"1": "1", "2": "2", "3": ""}[r[4]]
    other = tmp_path / "pcdu-rows.csv"
    with other.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)
    out = ok(capsys, "import-pinout", proj, other, "--device", "PCDU")
    assert "note: Row layouts set: PCDU-J02." in out
    out = ok(capsys, "pin-rows", proj, "--connector", "PCDU-J02")
    assert out.startswith("Pin rows of PCDU-J02: 1 / 2 (own rows)")
    out = ok(capsys, "check", proj)
    assert "INFO    row_layout_pins_outside:" in out and "PCDU-J02" in out

    # 10. explain names the rows and where they come from
    out = ok(capsys, "explain", proj, "PCDU-J01")
    assert "    Pin rows = 1 3 / 2   [part EX-MICROD-9-F: row_layout (the rows of its part)]" in out

    # 11. generate again (the rows are design data, so the generation is out of date), then export
    # with the plans; the independent check: 0 errors
    rows_before = {c.id: c.row_layout for c in load_project(proj).project.connectors.values()}
    ok(capsys, "generate", proj)
    rows_after = {c.id: c.row_layout for c in load_project(proj).project.connectors.values()}
    assert rows_after == rows_before  # Generate does not read or write the rows (L2)
    ok(capsys, "export", proj, "--harness-plan", "--drawings")
    out = ok(capsys, "verify", proj, "--outputs")
    assert "0 error(s)" in out
    box = table(outputs / "system" / "box_pinouts.csv")
    assert box[0][-1] == "Pin row"
    by_pin = {(r[0], r[box[0].index("Pin")]): r[-1] for r in box[1:]}
    assert [by_pin[("RW1-J01", n)] for n in "123"] == ["1", "3", "2"]
    assert [by_pin[("PCDU-J02", n)] for n in "123"] == ["1", "2", ""]
    assert table(outputs / "harnesses" / "W001" / "pinouts.csv")[0][-1] == "Pin row"
    plan = read_plan((outputs / "harnesses" / "W001" / "W001_plan.ods").read_bytes())
    assert check_values(plan) == []
    con = plan["CON_PCDU-J01"]
    assert con[(17, hp.COL_F)].value == "Pin row"
    assert [con[(18 + n, hp.COL_F)].value for n in range(3)] == [1, 2, 1]
    cells = plan["W001"]
    head, block = near_block(cells, "PCDU-J01")
    assert cells[(head, hp.COL_A)].value == "Pin row"
    assert [cells[(r, hp.COL_B)].value for r in block] == [1, 3, 2]  # row by row: 1 3 / 2
    export = json.loads((outputs / "system" / "export.json").read_bytes())
    assert export["format_version"] == 2
    assert [p["row_layout"] for p in export["parts"] if p["id"] == PART] == [
        {"rows": [["1", "3"], ["2"]]}
    ]
    own = {c["id"]: c["row_layout"] for c in export["box_connectors"] if "row_layout" in c}
    assert own == {"PCDU-J02": {"rows": [["1"], ["2"]]}, "RW1-J01": {"rows": [["1"], ["3"], ["2"]]}}

    # 12. a second export: byte-identical
    first = files(outputs)
    ok(capsys, "export", proj, "--harness-plan", "--drawings")
    assert files(outputs) == first
