# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-call"
"""REQ-MIGRATE-10, REQ-WIRE-09, REQ-WIRE-10, REQ-HARN-05, REQ-OUT-17, REQ-LIB-08, REQ-GUI-33. The
end-to-end walk of 5.0.0 (pull request 8 of section 18 of `docs/ait/DESIGN_5.0_FORMAT_5.md`; the
tests of its section 13), through the command line wherever a command exists and through the plans
the editor runs (`History`) where none does (no command makes a connection, creates a harness from
it or sets the gauge of a wire).

A project as 4.x saved it: the sample `mini3`, generated and saved, with the number 4 in
`project.json` (`tests/migration_support.as_format`; the step from 4 to 5 writes the number and
nothing else, so these are the bytes a 4.x tool writes). `generate` refuses it until the upgrade;
`migrate --dry-run` names `project.json` only and writes nothing; `migrate` writes format 5, keeps
the backup `.migration-backup-v4/` and changes no other file; `export --drawings` writes the golden
set of `mini3` (`tests/fixtures/outputs/mini3.json`), so a project without data of format 5 writes
what 4.x wrote, the stamp being the version's own.

Then the five parts, on one project:

- part A: `settings --set model.length_reference="face"` makes every cable connector measured to its
  face, and `check` names each part without a depth (`length_depth_missing`); `import-parts` gives
  the depths (a backshell part too), `import-build-data` puts W002-P2 back to the rear (a table of
  cable ends) and a backshell on W002-P1 (accessories), `import-lengths` the segment, and after
  `generate` a wire of W002 is 0.8 m less the depths of the plug and its backshell at W002-P1
  (`explain`, the wire list, the fifth sentence of the length note);
- part B: `import-pinout` gives the pins of the power line their currents (A and mA); the net of
  W001-001 does not add up (`current_unbalanced`, a finding of `model-inconsistent` in `drc`), then
  does; with a gauge and a length (the editor's wire edit) the wire carries the current of its
  pins, which `current-over-wire` and `voltage-drop` judge; a pin current is not an input of
  Generate (F5);
- part E, first half: `device-checked` refuses a device whose connectors name no ICD, then marks
  PCDU checked against the ICD given; `check` is quiet;
- part C: `import-pinout` gives two spare connectors a power line split over two contacts, which
  also changes PCDU since its check (`device_check_stale`); a connection with a junction through the
  core (`link_junction`, an info), *Create harness* refused without a splice part and made with
  `EX-SPLICE-1` (W003 with the splice W003-X1); `verify` by nets; the currents of the star (3 A on
  the trunk, 1.5 A on each branch); `current-over-contact` judges each pin on its own (the two
  pins that share the line pass, the others not), and `current-over-wire` the trunk at a gauge too
  thin for it;
- part D: the grounding concept (pigtail at end A, 360 degree backshell at end B) and
  `shield_place_not_stated`; `import-build-data` with a table of shield ends refuses a pin on a 360
  degree end and changes nothing, then lands the pigtails on the spare pins and end B on the
  backshell W002-A1;
- part E, second half: `check` and `drc` with the stale check, `device-checked` again, `--json`.

Then the outputs: `export --harness-plan --drawings`, `verify --outputs` with 0 errors, the
Production and Review sheets, the wire lists, `system/box_pinouts.csv` and `system/export.json`
with the keys of format 5, a second export byte-identical, and `export-data` with its 37 files.
Last what a 4.x tool does, where it can be tested: the loader's own version check opens the project
read-only (`generate` and `export` refuse it, nothing is written), and the verbatim copies of the
4.x code (`tests/reference/`) read the connection as `link_pin_reused`, measure the wire rear to
rear over the whole segment and see no contact overloaded. The editor's walk (offscreen) opens the
format 4 project read-only, then upgrades it, and uses the controls of format 5: *Segments are
measured to*, *Lengths measured to*, *Depth (mm)*, the pin current column, *Create harness* with the
splice part, the *Splices* list, *Change group* with the places, *Mark as checked…*, the Problems
list and a click on the stale check.

Every device, part, number and name here is made up (`EX-…`, `ICD-PCDU`, `A. Example`)."""

import csv
import io
import json
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.core.commands import History
from harness_design_studio.core.currents import wire_currents
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io import loader, migrate, saver
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.links import check_link, plan_add_link, plan_create_harness
from harness_design_studio.core.outputs.xlsx_env import load_workbook
from harness_design_studio.core.samples import mini3
from harness_design_studio.core.wires import plan_wire_edit
from tests.helpers import FIXTURES, output_digests
from tests.migration_support import as_format
from tests.test_e2e_300 import ok
from tests.test_e2e_rs422x3 import files, run

SPLICE = "EX-SPLICE-1"
BACKSHELL = "EX-BACKSHELL-25"
REASON = "the gauge and length of the example"
# part A: the depths (mm), part B: the contact rating (A) of the parts, made up for the example
PARTS = (
    "part number,manufacturer,description,category,approval status,Depth (mm),contact_current_a\n"
    "EX-MICROD-9-M,Example Ltd,Micro-D 9 plug (example),connector,Approved,18,5\n"
    "EX-MICROD-9-F,Example Ltd,Micro-D 9 socket (example),connector,Approved,18,5\n"
    "EX-MICROD-25-M,Example Ltd,Micro-D 25 plug (example),connector,Approved,22,\n"
    "EX-MICROD-15-F,Example Ltd,Micro-D 15 socket (example),connector,Approved,20,\n"
    f"{BACKSHELL},Example Ltd,Backshell for a 25-way Micro-D (example),backshell,Approved,30,\n"
    f"{SPLICE},Example Ltd,Crimp splice with one node (example),splice,Approved,,\n"
)
# the values the current rules read (config/derating.json, config/generation.json), made up
SETTINGS = (
    "derating.contact_current_factor=0.5",
    'derating.ampacity_a_by_awg={"20": 7.5, "24": 3.0, "26": 2.2}',
    "derating.bundle_derating=1.0",
    "derating.temperature_derating=1.0",
    "derating.max_voltage_drop_v=0.5",
    "generation.conductor_resistivity_ohm_m=1.72e-8",
)
UNBALANCED = (
    "WARNING current_unbalanced: The pin currents of the net of W001-001 do not add up: 2.5 A at "
    "RW1-J01.1; 2 A at PCDU-J01.1. Its wires were not checked for current. Correct the currents "
    "of the pins."
)
JUNCTION = (
    "Pin 1 of PCDU-J02 is joined to pins 1 and 2 of OBC-J02 (a junction); the harness made from "
    "the link joins them in a splice."
)
NO_SPLICE_PART = (
    "Link L1 joins pin 1 of PCDU-J02 to 2 pins of OBC-J02. Choose a splice part (category splice) "
    "for the joint; the harness gets one splice for each junction."
)
STALE = (
    "PCDU was checked by A. Example on 2026-11-23 against ICD-PCDU Issue 1; its connectors or pins "
    "changed since. Check it again (device-checked), or see what changed (the journal, "
    "update-device)."
)
NOTE_FACE = (
    "The segments run to the mating face of each connector (model.length_reference), but at "
    "W002-P2; the depth of the connector and its backshell is taken off each wire."
)


def made_by_4x(proj: Path) -> None:
    """mini3, generated, as a 4.x tool saved it."""
    p = mini3()
    generate_project(p)
    save_project(p, proj)
    as_format(proj, 4)


def project_files(proj: Path) -> dict[str, bytes]:
    """The files of the project, without the lock files a command leaves."""
    return {k: v for k, v in files(proj).items() if not k.startswith(".harness.lock")}


def sheet(tmp_path: Path, name: str, text: str) -> Path:
    f = tmp_path / name
    f.write_text(text, encoding="utf-8", newline="\n")
    return f


def table(path: Path) -> list[list[str]]:
    lines = [x for x in path.read_text(encoding="utf-8").splitlines() if not x.startswith("#")]
    return list(csv.reader(io.StringIO("\n".join(lines))))


def warnings(out: str) -> list[str]:
    """The lines of `check` that are warnings or errors."""
    return [x for x in out.splitlines() if x.startswith(("WARNING", "ERROR"))]


def infos(out: str, code: str) -> list[str]:
    return [x for x in out.splitlines() if x.startswith(f"INFO    {code}:")]


def drc(capsys: pytest.CaptureFixture[str], proj: Path) -> list[dict[str, Any]]:
    """The open findings of `drc --json`; it exits 1 while an error is open, 0 otherwise."""
    code, out = run(capsys, "drc", str(proj), "--json")
    doc = json.loads(out)
    assert doc["rules_run"] == 43  # no rule is new in 5.0.0
    assert code == (1 if doc["open_errors"] else 0), out
    found: list[dict[str, Any]] = doc["findings"]
    return found


def ids_of(found: list[dict[str, Any]], rule: str) -> set[str]:
    return {f["id"] for f in found if f["rule"] == rule}


def edit_wires(proj: Path, ids: list[str], changes: dict[str, object], reason: str | None) -> None:
    """The editor's *Edit wire* (no command sets a gauge): one undo step, saved."""
    p = load_project(proj).project
    History(p).execute("Edit wires", plan_wire_edit(p, ids, changes, reason=reason))
    save_project(p, proj)


def production(path: Path) -> list[list[Any]]:
    wb = load_workbook(io.BytesIO(path.read_bytes()), read_only=True)
    return [[c for c in row if c is not None] for row in wb["Production"].iter_rows(values_only=True)]  # fmt: skip


def review(path: Path) -> list[list[Any]]:
    wb = load_workbook(io.BytesIO(path.read_bytes()), read_only=True)
    return [[c for c in row if c is not None] for row in wb["Review"].iter_rows(values_only=True)]


def upgraded_mini3(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    """Step 1: mini3 of 4.x, upgraded; the outputs are the golden set of mini3."""
    proj = tmp_path / "proj"
    made_by_4x(proj)
    before = project_files(proj)
    code, out = run(capsys, "generate", str(proj))
    assert code != 0 and "migrate" in out  # a format 4 project is written only by migrate
    assert project_files(proj) == before
    out = ok(capsys, "migrate", proj, "--dry-run")
    assert "Project format 4; this tool writes format 5." in out
    assert "Files that would change (1):\n  changed  project.json\n" in out
    assert "(equal)" in out and "A full export before and after: identical." in out
    assert "Nothing is lost. Nothing was written." in out
    assert project_files(proj) == before
    out = ok(capsys, "migrate", proj)
    assert "Format 4 to 5. Record: .migration-backup-v4/MIGRATION.json." in out
    assert "same model hash, same findings, baselines untouched, identical export" in out
    after = {
        k: v for k, v in project_files(proj).items() if not k.startswith(".migration-backup-v4/")
    }
    changed = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    # project.json, the copy of the file it replaced, and the journal's entry of the step
    assert changed - {"journal.jsonl"} == {"project.json", "project.json.bak"}
    old, new = json.loads(before["project.json"]), json.loads(after["project.json"])
    versions = (old.pop("schema_version"), new.pop("schema_version"))
    assert versions == (4, 5)
    assert old == new
    assert (proj / ".migration-backup-v4" / "project.json").read_bytes() == before["project.json"]
    ok(capsys, "migrate", proj)  # up to date: nothing more to do
    ok(capsys, "export", proj, "--drawings")
    written = output_digests(files(proj / "outputs"))
    golden = json.loads((FIXTURES / "outputs" / "mini3.json").read_bytes())
    assert written.keys() - {"manifest.json"} == golden.keys()
    assert {k: written[k] for k in golden} == golden  # what 4.x wrote, with this version's stamp
    return proj


def test_the_whole_path_of_5_0_0_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1. a project of 4.x, upgraded: the number and nothing else
    proj = upgraded_mini3(tmp_path, capsys)
    outputs = proj / "outputs"

    # 2. part A: lengths to the face; a depth is never assumed
    ok(capsys, "settings", proj, "--set", 'model.length_reference="face"', *(x for s in SETTINGS for x in ("--set", s)))  # fmt: skip
    out = ok(capsys, "check", proj)
    assert warnings(out) == [
        f"WARNING length_depth_missing: {cid} is measured to its face, but part {part} has no "
        "depth (library: depth_mm), so the wires there have no length"
        for cid, part in (
            ("W001-P1", "EX-MICROD-9-M"), ("W001-P2", "EX-MICROD-9-F"),
            ("W002-P1", "EX-MICROD-25-M"), ("W002-P2", "EX-MICROD-15-F"),
        )
    ]  # fmt: skip
    out = ok(capsys, "import-parts", proj, sheet(tmp_path, "parts.csv", PARTS), "--approved", "Approved")  # fmt: skip
    assert "Depth (mm) -> depth_mm" in out and f"OK added {BACKSHELL}" in out
    out = ok(capsys, "import-build-data", proj, sheet(tmp_path, "ends.csv", "Connector,Lengths to\nW002-P2,rear\n"))  # fmt: skip
    assert "Read 1 row(s) of cable ends" in out and "row 2: OK lengths to rear" in out
    acc = "ID,Harness,Kind,Part,Target\nW002-A1,W002,backshell,EX-BACKSHELL-25,W002-P1\n"
    assert "row 2: OK backshell on W002-P1" in ok(capsys, "import-build-data", proj, sheet(tmp_path, "acc.csv", acc))  # fmt: skip
    ok(capsys, "import-lengths", proj, sheet(tmp_path, "lengths.csv", "harness,segment,length\nW002,W002-L1,800\n"))  # fmt: skip
    assert "0 added, 1 changed" in ok(capsys, "generate", proj)
    out = ok(capsys, "check", proj)
    assert warnings(out) == []
    out = ok(capsys, "explain", proj, "W002-001")
    assert "Wire W002-001. Length: 0.748 m" in out
    assert "    Depth of part EX-MICROD-25-M (W002-P1, measured to its face) = 22 mm" in out
    assert "    Depth of backshell part EX-BACKSHELL-25 (W002-P1, backshell W002-A1) = 30 mm" in out
    assert "    Path from rear to rear: 0.8 − 0.052 = 0.748 m" in out
    assert "EX-MICROD-15-F (W002-P2" not in out  # W002-P2 is measured to the rear
    p = load_project(proj).project
    assert [c.length_to for c in p.harnesses["W002"].connectors] == [None, "rear"]

    # 3. part B: the currents of the power line, in A and in mA; first they do not add up
    pcdu = "Connector,Pin,Signal,Current\nJ01,1,PWR,2\nJ01,2,RTN,2 A\n"
    assert "PCDU-J01: OK updated (2 pin(s))" in ok(capsys, "import-pinout", proj, sheet(tmp_path, "pcdu.csv", pcdu), "--device", "PCDU")  # fmt: skip
    rw1 = "Connector,Pin,Signal,Current (mA)\nJ01,1,PWR,2500\nJ01,2,RTN,2000\n"
    out = ok(capsys, "import-pinout", proj, sheet(tmp_path, "rw1.csv", rw1), "--device", "RW1")
    assert "Converted, row 2 (RW1-J01 pin 1): 2500 mA = 2.5 A" in out
    assert warnings(ok(capsys, "check", proj)) == [UNBALANCED]
    found = drc(capsys, proj)
    assert ids_of(found, "model-inconsistent") == {f["id"] for f in found if "current_unbalanced" in f["id"]}  # fmt: skip
    assert len(ids_of(found, "model-inconsistent")) == 1
    rw1 = "Connector,Pin,Signal,Current\nJ01,1,PWR,2\n"
    ok(capsys, "import-pinout", proj, sheet(tmp_path, "rw1b.csv", rw1), "--device", "RW1")
    assert warnings(ok(capsys, "check", proj)) == []
    assert "0 error(s)" in ok(capsys, "verify", proj)  # Generate does not read a pin current (F5)
    edit_wires(proj, ["W001-001", "W001-002"], {"gauge_awg": 24, "length_m": 1.0}, REASON)
    found = drc(capsys, proj)
    assert not ids_of(found, "current-over-contact") and not ids_of(found, "current-over-wire")
    assert not ids_of(found, "voltage-drop")  # 2 A on 24 AWG for 1 m and back: 0.336 V
    out = ok(capsys, "explain", proj, "W001-001")
    assert (
        "    Current carried = 2 A   [the pin currents of its net (2 A at PCDU-J01.1; 2 A at "
        "RW1-J01.1): between W001-P1.1 and W001-P2.1 the smaller of 2 A and 2 A]"
    ) in out
    assert "  Check: the wire carries 2 A and the limit is 3 A: within the limit, 1 A to spare" in out  # fmt: skip
    assert "  Check: the drop is 0.336052 V and the limit is 0.5 V: within the limit" in out

    # 4. part E: a person marks PCDU checked against the ICD they name
    code, out = run(capsys, "device-checked", str(proj), "PCDU", "--by", "A. Example")
    assert code != 0 and "name the ICD with --icd" in out
    out = ok(capsys, "device-checked", proj, "PCDU", "--by", "A. Example", "--icd", "ICD-PCDU Issue 1", "--date", "2026-11-23")  # fmt: skip
    assert "PCDU: checked by A. Example on 2026-11-23 against ICD-PCDU Issue 1." in out
    assert warnings(ok(capsys, "check", proj)) == []

    # 5. part C: a power line split over two contacts; the edit makes the check of PCDU stale
    pcdu = "Connector,Pin,Signal,Current\nJ02,1,PWR2,3\nJ02,2,RTN2,3\n"
    ok(capsys, "import-pinout", proj, sheet(tmp_path, "pcdu2.csv", pcdu), "--device", "PCDU")
    obc = "Connector,Pin,Signal,Current\nJ02,1,PWR2,1.5\nJ02,2,PWR2,1.5\nJ02,3,RTN2,3\n"
    ok(capsys, "import-pinout", proj, sheet(tmp_path, "obc2.csv", obc), "--device", "OBC")
    assert warnings(ok(capsys, "check", proj)) == [f"WARNING device_check_stale: {STALE}"]
    p = load_project(proj).project
    history = History(p)
    ops, lid = plan_add_link(p, "PCDU-J02", "OBC-J02", [("1", "1"), ("1", "2"), ("2", "3")])
    history.execute("Add link", ops)
    assert [(f.code, f.severity, f.message) for f in check_link(p, p.links[lid])] == [
        ("link_junction", "info", JUNCTION)
    ]
    with pytest.raises(Exception, match="Choose a splice part") as refused:
        plan_create_harness(p, lid)
    assert str(refused.value) == NO_SPLICE_PART
    ops, hid = plan_create_harness(p, lid, SPLICE)
    history.execute("Create harness", ops)
    save_project(p, proj)
    h = p.harnesses[hid]
    assert hid == "W003" and [c.id for c in h.connectors if c.role == "splice"] == ["W003-X1"]
    assert [(w.from_connector, w.from_pin, w.to_connector, w.to_pin) for w in h.wires] == [
        ("W003-P1", "1", "W003-X1", "1"), ("W003-X1", "1", "W003-P2", "1"),
        ("W003-X1", "1", "W003-P2", "2"), ("W003-P1", "2", "W003-P2", "3"),
    ]  # fmt: skip
    assert {w: c.value for w, c in wire_currents(p, h).items()} == {
        "W003-001": 3.0, "W003-002": 1.5, "W003-003": 1.5, "W003-004": 3.0,
    }  # fmt: skip
    ok(capsys, "generate", proj)  # the signals of the pins are an input of Generate
    assert "0 error(s)" in ok(capsys, "verify", proj)  # the verifier reads the link by its nets
    found = drc(capsys, proj)
    assert ids_of(found, "current-over-contact") == {
        "current-over-contact.PCDU-J02.1",
        "current-over-contact.PCDU-J02.2",
        "current-over-contact.OBC-J02.3",
    }  # fmt: skip  (OBC-J02 pins 1 and 2 share the line: 1.5 A each, within 2.5 A)
    edit_wires(proj, [f"W003-00{k}" for k in (1, 2, 3)], {"gauge_awg": 26, "length_m": 0.5}, None)
    edit_wires(proj, ["W003-004"], {"gauge_awg": 24, "length_m": 0.5}, None)
    found = drc(capsys, proj)
    assert ids_of(found, "current-over-wire") == {"current-over-wire.W003-001"}  # 3 A on 2.2 A
    notes = {f["id"]: f["title"] for f in found if f["rule"] == "unchecked-config"}
    assert notes["unchecked-config.voltage-drop-wires"].startswith(
        "Voltage drop was not checked for 4 wire(s) without an interface type to count the "
        "conductors of (first: W003-001)"
    )
    edit_wires(proj, ["W003-001"], {"gauge_awg": 24}, None)
    assert not ids_of(drc(capsys, proj), "current-over-wire")

    # 6. part D: where the shield ends land
    ok(capsys, "settings", proj, "--set", 'generation.shield_end_a="pigtail"', "--set", 'generation.shield_end_b="backshell_360"')  # fmt: skip
    ok(capsys, "generate", proj)
    out = ok(capsys, "check", proj)
    assert (
        infos(out, "shield_place_not_stated")
        == [
            "INFO    shield_place_not_stated: W002-S1: where the pigtail at W002-P1 lands is not stated.",  # fmt: skip
            "INFO    shield_place_not_stated: W002-S2: where the pigtail at W002-P2 lands is not stated.",  # fmt: skip
        ]
    )
    before = project_files(proj)
    bad = "Shield group,End,Pin,Backshell\nW002-S1,A,5,\nW002-S1,B,5,\n"
    code, out = run(capsys, "import-build-data", str(proj), str(sheet(tmp_path, "bad.csv", bad)))
    assert code != 0 and "Nothing was changed." in out
    assert "row 3: ERROR End B of W002-S1 is a 360 degree backshell: only a pigtail lands on a pin." in out  # fmt: skip
    assert project_files(proj) == before
    places = "Shield group,End,Pin,Backshell\nW002-S1,A,5,\nW002-S2,A,5,\nW002-S2,B,,W002-A1\n"
    out = ok(capsys, "import-build-data", proj, sheet(tmp_path, "places.csv", places))
    assert "Import shield ends: 3 row(s) read." in out and "row 4: OK lands on backshell W002-A1" in out  # fmt: skip
    out = ok(capsys, "check", proj)
    assert infos(out, "shield_place_not_stated") == []
    assert warnings(out) == [f"WARNING device_check_stale: {STALE}"]
    assert "0 changed" in ok(capsys, "generate", proj)  # Generate keeps the places

    # 7. part E again: the stale check in the design rule check, then checked again
    found = drc(capsys, proj)
    (stale,) = [f for f in found if f["rule"] == "model-inconsistent"]
    assert stale["title"] == STALE and ".device_check_stale." in stale["id"]
    assert ok(capsys, "explain", proj, "PCDU").splitlines()[1] == (
        "Checked by A. Example on 2026-11-23 against ICD-PCDU Issue 1; changed since the check."
    )
    _, out = run(capsys, "device-checked", str(proj), "PCDU", "--by", "A. Example", "--icd", "ICD-PCDU Issue 2", "--date", "2026-11-23", "--json")  # fmt: skip
    doc = json.loads(out)
    assert doc["ok"] and doc["checked"]["state"] == "checked" and doc["checked"]["icd"] == "ICD-PCDU Issue 2"  # fmt: skip
    assert warnings(ok(capsys, "check", proj)) == []

    # 8. the outputs, with their independent check
    ok(capsys, "export", proj, "--harness-plan", "--drawings")
    assert "0 error(s)" in ok(capsys, "verify", proj, "--outputs")
    assert [r[10] for r in table(outputs / "harnesses" / "W002" / "wirelist.csv")[1:]] == ["0.748"] * 4  # fmt: skip
    w003 = table(outputs / "harnesses" / "W003" / "wirelist.csv")
    assert w003[0][-1] == "Via" and [r[-1] for r in w003[1:]] == ["W003-X1"] * 3 + [""]
    box = table(outputs / "system" / "box_pinouts.csv")
    assert box[0][-1] == "Current (A)"
    amps = {(r[0], r[4]): r[-1] for r in box[1:]}
    assert [amps[("OBC-J02", n)] for n in "123"] == ["1.5", "1.5", "3"]
    assert amps[("OBC-J01", "1")] == ""
    rows = production(outputs / "harnesses" / "W002" / "W002_build.xlsx")
    assert ["5", "pigtail", "W002-S1 shielded pair: pigtail lands here"] in rows
    shields = {(r[0], r[-1]) for r in rows if len(r) > 10}
    assert ("1", "W002-S1 shielded pair: here pigtail to pin 5, far backshell 360") in shields
    assert ("3", "W002-S2 shielded pair: here backshell 360 (W002-A1), far pigtail") in shields
    assert [NOTE_FACE] in rows
    rows = review(outputs / "harnesses" / "W003" / "W003_build.xlsx")
    assert ["Device", "PCDU", "Checked by A. Example on 2026-11-23 against ICD-PCDU Issue 2"] in rows  # fmt: skip
    assert ["Device", "OBC", "not checked"] in rows
    export = json.loads((outputs / "system" / "export.json").read_bytes())
    assert export["format_version"] == 2
    w002 = next(h for h in export["harnesses"] if h["id"] == "W002")
    assert [c.get("length_to") for c in w002["connectors"]] == [None, "rear"]
    assert [(s.get("at_a"), s.get("at_b")) for s in w002["shields"]] == [
        ({"connector": "W002-P1", "pin": "5"}, None),
        ({"connector": "W002-P2", "pin": "5"}, {"backshell": "W002-A1", "connector": "W002-P1"}),
    ]
    assert {p["id"]: p["depth_mm"] for p in export["parts"] if "depth_mm" in p} == {
        "EX-MICROD-9-M": 18, "EX-MICROD-9-F": 18, "EX-MICROD-25-M": 22, "EX-MICROD-15-F": 20,
        BACKSHELL: 30,
    }  # fmt: skip
    (pcdu_unit,) = [u for u in export["units"] if u["id"] == "PCDU"]
    assert pcdu_unit["checked"]["icd"] == "ICD-PCDU Issue 2"
    assert export["field_units"]["box_connectors[].pins[].current_a"] == "A"
    first = files(outputs)
    ok(capsys, "export", proj, "--harness-plan", "--drawings")
    assert files(outputs) == first  # a second export: byte-identical
    out = ok(capsys, "export-data", proj, "--out", tmp_path / "data")
    assert "37 data files written" in out
    devices = table(tmp_path / "data" / "devices.csv")
    assert {"Checked by", "Checked on", "Checked against", "Check"} <= set(devices[0])

    # 9. what a tool of format 4 does with it, where it can be tested here
    from tests.reference import integrity_181, lengths_440, links_430
    from tests.reference.currents_440 import _current_over_contact

    p = load_project(proj).project
    assert "link_pin_reused" in [f.code for f in links_430.check_link(p, p.links["L1"])]
    assert [i.severity for i in integrity_181.check_integrity(p) if i.code == "link_pin_reused"] == ["error"]  # fmt: skip
    h = p.harnesses["W002"]
    w = next(x for x in h.wires if x.id == "W002-002")
    assert lengths_440.path_length(h, "W002-P1", "W002-P2") == 0.8  # 4.x: rear to rear, 0.8 m
    assert w.length_m == 0.748
    assert list(_current_over_contact(p)) == []  # 4.x: no interface states a current, no finding
    before = project_files(proj)
    for module in (migrate, loader, saver):
        monkeypatch.setattr(module, "SCHEMA_VERSION", 4)
    r = load_project(proj)
    assert r.project.read_only
    (newer,) = [i for i in r.issues if i.code == "newer_version"]
    assert "format 5; this tool understands up to 4" in newer.message
    for command in ("generate", "export"):
        code, out = run(capsys, command, str(proj))
        assert code != 0 and "read-only" in out
    assert project_files(proj) == before


@pytest.mark.gui
def test_the_editor_upgrades_and_sets_the_fields_of_format_5(
    qtbot: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The editor's walk (offscreen): the question of an older format, then the controls of format
    5 on one project, each one undo step; the command line reads what the editor saved."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QDialog

    from harness_design_studio.core import device_check as dc
    from harness_design_studio.gui import strings
    from harness_design_studio.gui.link_dialog import CreateHarnessDialog, LinkDialog
    from harness_design_studio.gui.splice_panel import splice_rows
    from tests.gui_helpers import DialogScript, hold_drc, make_window
    from tests.test_ui_format5 import _click, _devices_view, settle, steps

    proj = tmp_path / "proj"
    made_by_4x(proj)
    win = make_window(tmp_path)
    qtbot.addWidget(win)

    # 1. the question of an older format: read-only first, then the upgrade
    asked: list[tuple[int, int]] = []

    def answer(word: str) -> Any:
        def ask(old: int, new: int) -> str:
            asked.append((old, new))
            return word

        return ask

    win.ask_upgrade = answer("read_only")  # type: ignore[method-assign]
    assert win.open_project(proj)
    hold_drc(win)
    assert asked == [(4, 5)] and win.ctl.read_only
    win.set_area("settings")
    win.settings_page.show_section("project")
    win._show_segmentation()
    settle()
    assert not win.settings_page.length_reference_combo.isEnabled()
    assert json.loads((proj / "project.json").read_bytes())["schema_version"] == 4
    win.ask_upgrade = answer("upgrade")  # type: ignore[method-assign]
    assert win.open_project(proj, again=True)
    hold_drc(win)
    assert asked[-1] == (4, 5) and not win.ctl.read_only
    assert json.loads((proj / "project.json").read_bytes())["schema_version"] == 5
    assert (proj / ".migration-backup-v4" / "project.json").is_file()
    win.ctl.release()  # the window lets the folder go: the command line brings the data

    # 2. the command line: the parts (no depth of EX-MICROD-15-F yet), the grounding concept, the
    # backshell, the segment, the signals and currents of the split line
    parts = PARTS.replace("connector,Approved,20,", "connector,Approved,,")
    ok(capsys, "import-parts", proj, sheet(tmp_path, "parts.csv", parts), "--approved", "Approved")  # fmt: skip
    ok(capsys, "settings", proj, *(x for s in SETTINGS for x in ("--set", s)), "--set", 'generation.shield_end_a="pigtail"', "--set", 'generation.shield_end_b="backshell_360"')  # fmt: skip
    acc = "ID,Harness,Kind,Part,Target\nW002-A1,W002,backshell,EX-BACKSHELL-25,W002-P1\n"
    ok(capsys, "import-build-data", proj, sheet(tmp_path, "acc.csv", acc))
    ok(capsys, "import-lengths", proj, sheet(tmp_path, "lengths.csv", "harness,segment,length\nW002,W002-L1,800\n"))  # fmt: skip
    ok(capsys, "import-pinout", proj, sheet(tmp_path, "pcdu2.csv", "Connector,Pin,Signal\nJ02,1,PWR2\nJ02,2,RTN2\n"), "--device", "PCDU")  # fmt: skip
    obc = "Connector,Pin,Signal,Current\nJ02,1,PWR2,1.5\nJ02,2,PWR2,1.5\nJ02,3,RTN2,3\n"
    ok(capsys, "import-pinout", proj, sheet(tmp_path, "obc2.csv", obc), "--device", "OBC")
    ok(capsys, "generate", proj)
    assert win.open_project(proj, again=True)
    hold_drc(win)

    # 3. Settings > Project: Segments are measured to the face
    win.set_area("settings")
    win.settings_page.show_section("project")
    win._show_segmentation()
    settle()
    combo = win.settings_page.length_reference_combo
    assert combo.isEnabled() and combo.currentData() == "rear"
    n = steps(win)
    combo.setCurrentIndex(combo.findData("face"))
    settle()
    assert steps(win) == n + 1 and win.ctl.project.config["model"].values["length_reference"] == "face"  # fmt: skip
    assert win.ctl.history.next_undo_label == strings.STEP_SET_LENGTH_REFERENCE.format(
        strings.SETTINGS_LENGTH_REFERENCE_CHOICES["face"]
    )

    # 4. the Inspector: the depth of a part, and W002-P2 measured to its rear
    ins = win.inspector
    ins.show_object("part", "EX-MICROD-15-F")
    settle()
    ins.depth_box.edit.setText("20")
    assert ins.depth_box.apply()
    assert win.ctl.project.parts["EX-MICROD-15-F"].depth_mm == 20
    ins.show_object("cable_end", "W002-P2")
    settle()
    box = ins.length_box
    box.choice.setCurrentIndex(box.choice.findData("rear"))
    assert box.apply()
    assert [c.length_to for c in win.ctl.project.harnesses["W002"].connectors] == [None, "rear"]

    # 5. the Devices tab: PCDU marked as checked, then a pin current, so the check goes stale
    view = _devices_view(win, "PCDU-J02")
    assert view.check_label.text() == dc.NOT_CHECKED

    def fill(dlg: Any) -> None:
        dlg.by.setText("A. Example")
        dlg.on.setText("2026-11-23")
        dlg.icd.setText("ICD-PCDU Issue 1")

    DialogScript(win, fill)
    view.check_btn.click()
    settle()
    view.refresh()
    assert view.check_label.text() == "Checked by A. Example on 2026-11-23 against ICD-PCDU Issue 1"
    col = view.pin_model.column_index("current_a")
    for pin in ("1", "2"):
        view.pin_model.cellEdited.emit(view._pin_index[pin], "current_a", "3 A")
        view.refresh()
        settle()
    assert [x.current_a for x in win.ctl.project.connectors["PCDU-J02"].pins] == [3.0, 3.0, None]
    assert not view.pin_table.isColumnHidden(col)
    assert view.check_label.text().endswith("; " + dc.CHANGED)

    # 6. the Link window takes pin 1 of PCDU-J02 twice (a junction); Create harness asks for the
    # splice part
    def pair_again(dlg: Any) -> None:
        assert isinstance(dlg, LinkDialog)
        dlg.a_pin.setCurrentIndex(dlg.a_pin.findData("1"))
        dlg.b_pin.setCurrentIndex(dlg.b_pin.findData("2"))
        dlg.add_pair.click()
        assert JUNCTION in dlg.review.text()

    DialogScript(win, pair_again)
    win.link_flow("PCDU", "PCDU-J02", "OBC", "OBC-J02")
    (lid,) = win.ctl.project.links
    assert sorted((x.a_pin, x.b_pin) for x in win.ctl.project.links[lid].pairs) == [
        ("1", "1"),
        ("1", "2"),
        ("2", "3"),
    ]
    shown = DialogScript(win)
    win.create_harness_flow(lid)
    (dlg,) = shown.seen
    assert isinstance(dlg, CreateHarnessDialog) and dlg.splice_part() == SPLICE
    hid = win.ctl.project.links[lid].harness_id
    assert hid == "W003"
    (row,) = splice_rows(win.ctl.project.harnesses[hid], win.ctl.project)
    assert row["currents"] == "3 A at PCDU-J02.1; 1.5 A and 1.5 A at OBC-J02.1 and .2: they add up"

    # 7. Change group: where the shield ends of W002 land
    hv = win.harness_view
    win.go_to("harness")
    assert hv.select_harness("W002")
    hv.refresh()
    ed = hv.wire_editor
    ed.set_harness("W002")

    def places(group: str, pin: str | None, shell: str | None) -> None:
        s = next(x for x in win.ctl.project.harnesses["W002"].shields if x.id == group)
        ed.show_wires(list(s.wire_ids))

        def run_it(dlg: Any) -> int:
            if pin is not None:
                dlg.pins["a"].setCurrentIndex(dlg.pins["a"].findData(pin))
            if shell is not None:
                dlg.shells["b"].setCurrentIndex(dlg.shells["b"].findData(shell))
            assert dlg.ok.isEnabled()
            return int(QDialog.DialogCode.Accepted)

        ed.run_dialog = run_it
        n = steps(win)
        assert ed.change_group() and steps(win) == n + 1

    places("W002-S1", "5", None)
    places("W002-S2", "5", "W002-A1")
    s1, s2 = win.ctl.project.harnesses["W002"].shields
    assert s1.at_a is not None and (s1.at_a.connector, s1.at_a.pin) == ("W002-P1", "5")
    assert s2.at_b is not None and (s2.at_b.connector, s2.at_b.backshell) == ("W002-P1", "W002-A1")

    # 8. the Problems list: the junction is an info row, and a click on the stale check goes to the
    # Devices tab, where it is put right
    win.ctl.run_drc_now()
    win.ctl.wait_drc()
    plist = win.problems_list
    win.dock_problems.show()
    plist.refresh()
    settle()
    rows = plist.rows()
    assert ("link_junction", "info") in {(r["rule"], r["level"]) for r in rows}
    assert not [r for r in rows if r["rule"] == "shield_place_not_stated"]
    _click(plist, lambda r: r["rule"] == "model-inconsistent" and r["object_id"] == "PCDU")
    assert win.main_tabs.currentWidget() is win.main_tabs.widget_of("devices")
    assert win.devices_view.unit_id() == "PCDU"
    win.ctl.save()
    win.ctl.wait_journal()
    win.ctl.release()
    QApplication.processEvents()

    # 9. the command line reads what the editor saved
    out = ok(capsys, "check", proj)
    assert warnings(out) == [f"WARNING device_check_stale: {STALE}"]
    ok(capsys, "generate", proj)
    out = ok(capsys, "explain", proj, "W002-001")
    assert "Wire W002-001. Length: 0.748 m" in out
    assert "0 error(s)" in ok(capsys, "verify", proj)
