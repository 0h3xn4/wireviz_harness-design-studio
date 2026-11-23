# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,union-attr,type-arg,attr-defined,index"
"""REQ-LIB-08. The checked state of a library device (format 5, part E of
`docs/ait/DESIGN_5.0_FORMAT_5.md`, section 8; owner questions F12 and F13 by their
recommendations).

`Unit.checked` holds who checked a device, on which day, against which ICD, and the SHA-256 of
its library-owned fields (`core/device_check.py`). This file holds the rules of the file, what the
hash covers (a copy, a rename, a note left out, an allocated signal left out, each field in), the
plans, the command `device-checked` (`--by` required, `--icd` proposed or refused, `--date`,
`--clear`, `--json`, the journal, a read-only project), the stale check (`device_check_stale`),
the library (`save-device` writes file version 4, `add-device` brings the check, `update-device`
compares it and `--apply` takes the library's, its *not checked* too), the Review rows of the core
and of the verifier, `export-data`, the scripting functions and a project of format 4 whose
outputs do not move."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from harness_design_studio.cli.jsonout import SHAPES
from harness_design_studio.cli.main import main
from harness_design_studio.core import device_check as dc
from harness_design_studio.core import library_link as ll
from harness_design_studio.core.commands import apply_ops
from harness_design_studio.core.edit import EditError, clone_with
from harness_design_studio.core.integrity import check_integrity, device_check_issues
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import DeviceCheck, Project, Unit, evolve
from tests.format5_support import format5_project

DEVICE = "RW1"
BOX = "RW1-J01"
FILE = "RW1.device.json"
BY = "A. Example"
DAY = "2026-11-23"
ICD = "ICD-RW Issue 2"
SHA = "0" * 64


def cli(capsys: pytest.CaptureFixture[str], *argv: object) -> tuple[int, str, str]:
    rc = main([str(a) for a in argv])
    got = capsys.readouterr()
    return rc, got.out, got.err


def as_json(capsys: pytest.CaptureFixture[str], *argv: object, rc: int = 0) -> dict:
    code, out, err = cli(capsys, *argv, "--json")
    assert code == rc, (argv, out, err)
    return json.loads(out)


@pytest.fixture
def p() -> Project:
    return clone_with(format5_project(), [])


def checked(p: Project, uid: str, **kw: Any) -> Project:
    apply_ops(p, dc.plan_set_device_checked(p, uid, by=BY, on=DAY, icd=ICD, **kw).ops)
    return p


def set_pin(p: Project, cid: str, pid: str, **changes: Any) -> None:
    c = p.connectors[cid]
    p.connectors[cid] = evolve(c, pins=[evolve(x, **changes) if x.id == pid else x for x in c.pins])


# ---- the rules of the file (sections 3.1 and 3.2, rule 5) ---------------------------------------


def test_the_key_is_sparse_and_absent_by_default() -> None:
    u = Unit(id="TTC1", name="Transceiver 1", subsystem="ttc", side="nominal")
    assert u.checked is None and "checked" not in u.model_dump(mode="json")
    c = DeviceCheck(by="Reviewer 1", on=DAY, icd="ICD-TTC Issue 3", sha256=SHA)
    assert evolve(u, checked=c).model_dump(mode="json")["checked"] == {
        "by": "Reviewer 1", "on": DAY, "icd": "ICD-TTC Issue 3", "sha256": SHA,
    }  # fmt: skip


@pytest.mark.parametrize(
    "check",
    [
        {"by": BY, "on": DAY, "icd": ICD},  # all four keys
        {"by": BY, "on": "2026-02-30", "icd": ICD, "sha256": SHA},  # a date
        {"by": BY, "on": "23.11.2026", "icd": ICD, "sha256": SHA},
        {"by": BY, "on": DAY, "icd": ICD, "sha256": "0" * 63},  # 64 hexadecimal characters
        {"by": BY, "on": DAY, "icd": ICD, "sha256": "G" * 64},
        {"by": "", "on": DAY, "icd": ICD, "sha256": SHA},
        {"by": BY, "on": DAY, "icd": ICD, "sha256": SHA, "note": "x"},
    ],
)
def test_the_rules_of_the_file(check: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        Unit.model_validate({"id": "TTC1", "name": "T", "subsystem": "s", "checked": check})


def test_a_device_with_a_check_that_breaks_a_rule_is_set_aside_on_load(tmp_path: Path) -> None:
    from harness_design_studio.core.io.saver import save_project

    save_project(format5_project(), tmp_path / "p")
    path = tmp_path / "p" / "logical" / "units" / "s.json"  # the devices of subsystem s
    doc = json.loads(path.read_text(encoding="utf-8"))
    unit = next(u for u in doc["units"] if u["id"] == "PCDU1")
    assert unit["checked"]["icd"] == "ICD-PCDU Issue 2"
    assert load_project(tmp_path / "p").project.units["PCDU1"].checked is not None
    unit["checked"]["on"] = "yesterday"
    path.write_text(json.dumps(doc), encoding="utf-8")
    loaded = load_project(tmp_path / "p").project
    assert "PCDU1" not in loaded.units
    assert any("YYYY-MM-DD" in q.reason for q in loaded.quarantine)


# ---- what is checked (section 8.1) --------------------------------------------------------------


def test_the_hash_is_of_canonical_json_of_the_library_owned_fields(p: Project) -> None:
    content = dc.device_content(p.units["OBC1"], [p.connectors["OBC1-J01"]])
    assert list(content) == ["unit", "connectors"]
    assert content["unit"] == {"kind": None, "mass_relevant": True}
    (conn,) = content["connectors"]
    assert conn["tail"] == "J01" and set(conn) == {"tail", "pins", *dc.HASHED_CONNECTOR_FIELDS}
    assert [x["id"] for x in conn["pins"]] == [str(k) for k in range(1, 26)]  # natural order
    assert set(conn["pins"][0]) == {"id", *dc.HASHED_PIN_FIELDS}
    import hashlib

    from harness_design_studio.core.io.canonical import dumps

    assert dc.checked_sha256(p, "OBC1") == hashlib.sha256(dumps(content)).hexdigest()


def test_a_note_a_label_and_the_project_s_own_fields_are_left_out(p: Project) -> None:
    before = dc.checked_sha256(p, "PCDU1")
    p.units["PCDU1"] = evolve(
        p.units["PCDU1"], notes="a note", name="Power unit", subsystem="eps", zone=None
    )
    p.connectors["PCDU1-J01"] = evolve(p.connectors["PCDU1-J01"], notes="n", label="X")
    assert dc.checked_sha256(p, "PCDU1") == before


@pytest.mark.parametrize(
    ("where", "field", "value"),
    [
        ("unit", "kind", "power_unit"),
        ("unit", "mass_relevant", False),
        ("connector", "name", "J9"),
        ("connector", "gender", "male"),
        ("connector", "keying", "B"),
        ("connector", "source_doc", "ICD-OTHER"),
        ("connector", "source_version", "Issue 3"),
        ("connector", "source_link", "https://example.com/icd"),
        ("pin", "signal", "PWR2"),
        ("pin", "function", "power in"),
        ("pin", "role", "power"),
        ("pin", "direction", "in"),
        ("pin", "level", "28V"),
        ("pin", "current_a", 1.0),
    ],
)
def test_each_library_owned_field_is_in_the_hash(
    p: Project, where: str, field: str, value: object
) -> None:
    before = dc.checked_sha256(p, "PCDU1")
    if where == "unit":
        p.units["PCDU1"] = evolve(p.units["PCDU1"], **{field: value})
    elif where == "connector":
        p.connectors["PCDU1-J01"] = evolve(p.connectors["PCDU1-J01"], **{field: value})
    else:
        set_pin(p, "PCDU1-J01", "3", **{field: value})
    assert dc.checked_sha256(p, "PCDU1") != before


def test_a_signal_generate_allocated_is_the_project_s_and_is_left_out(p: Project) -> None:
    before = dc.checked_sha256(p, "PCDU1")
    set_pin(p, "PCDU1-J01", "7", signal="TX", interface_id="IF-001")
    assert dc.checked_sha256(p, "PCDU1") == before
    set_pin(p, "PCDU1-J01", "7", fixed=True)  # a fixed signal is the device's
    assert dc.checked_sha256(p, "PCDU1") != before


def test_a_copy_and_a_renamed_device_read_by_the_tail(p: Project) -> None:
    from harness_design_studio.core import copies
    from harness_design_studio.core.edit import ops_rename_unit

    checked(p, "PCDU1")
    apply_ops(p, copies.plan_copies(p, "PCDU1", 2).ops)
    (copy,) = [u for u in p.units if u.startswith("PCDU1-")]
    assert dc.checked_sha256(p, copy) == dc.checked_sha256(p, "PCDU1")
    assert p.units[copy].checked == p.units["PCDU1"].checked
    assert dc.check_state(p, copy) == dc.CHECKED
    apply_ops(p, ops_rename_unit(p, "PCDU1", "PCDU9"))
    assert dc.check_state(p, "PCDU9") == dc.CHECKED


# ---- how it is set (section 8.2) ---------------------------------------------------------------


def test_the_icd_is_proposed_from_the_connectors_or_refused(p: Project) -> None:
    assert dc.proposed_icd(p, "PCDU1") == "ICD-PCDU Issue 2"
    assert dc.proposed_icd(p, "OBC1") is None  # its connector names no ICD
    plan = dc.plan_set_device_checked(p, "PCDU1", by=BY, on=DAY)
    assert plan.proposed and plan.check.icd == "ICD-PCDU Issue 2"
    with pytest.raises(EditError, match="do not name one ICD and version"):
        dc.plan_set_device_checked(p, "OBC1", by=BY, on=DAY)
    plan = dc.plan_set_device_checked(p, "OBC1", by=BY, on=DAY, icd="ICD-OBC Issue 2")
    assert not plan.proposed and plan.check.sha256 == dc.checked_sha256(p, "OBC1")
    p.connectors["PCDU1-J01"] = evolve(p.connectors["PCDU1-J01"], source_version=None)
    assert dc.proposed_icd(p, "PCDU1") is None  # a document without its version is not one ICD


@pytest.mark.parametrize(
    ("by", "on", "words"),
    [("  ", DAY, "Say who checked"), (BY, "2026-13-01", "The date"), (BY, "", "The date")],
)
def test_the_plan_refuses_what_is_not_a_check(p: Project, by: str, on: str, words: str) -> None:
    with pytest.raises(EditError, match=words):
        dc.plan_set_device_checked(p, "OBC1", by=by, on=on, icd=ICD)
    with pytest.raises(EditError, match="no device TTC9"):
        dc.plan_set_device_checked(p, "TTC9", by=BY, on=DAY, icd=ICD)


def test_the_same_check_twice_changes_nothing_and_clear_takes_it_away(p: Project) -> None:
    checked(p, "OBC1")
    assert dc.plan_set_device_checked(p, "OBC1", by=BY, on=DAY, icd=ICD).ops == []
    apply_ops(p, dc.plan_clear_device_checked(p, "OBC1"))
    assert p.units["OBC1"].checked is None
    assert dc.plan_clear_device_checked(p, "OBC1") == []


def test_a_release_does_not_lock_the_check_and_generate_does_not_read_it(p: Project) -> None:
    from harness_design_studio.core.generation_status import input_hash
    from harness_design_studio.core.vcs.locks import COSMETIC_UNIT_FIELDS

    assert "checked" in COSMETIC_UNIT_FIELDS
    before = input_hash(p)
    checked(p, "OBC1")
    assert input_hash(p) == before


# ---- when the check is stale (section 8.3) -----------------------------------------------------


def test_the_fixture_has_one_stale_check_and_one_current(p: Project) -> None:
    assert dc.check_state(p, "PCDU1") == dc.CHECKED
    assert dc.check_state(p, "OBC1") == dc.CHANGED
    assert dc.check_state(p, "DEV1") == dc.NOT_CHECKED
    (issue,) = device_check_issues(p)
    assert (issue.severity, issue.code, issue.object_id) == (
        "warning",
        "device_check_stale",
        "OBC1",
    )
    assert issue.message == (
        "OBC1 was checked by A. Example on 2026-11-20 against ICD-OBC Issue 1; its connectors or "
        "pins changed since. Check it again (device-checked), or see what changed (the journal, "
        "update-device)."
    )


def test_a_change_makes_the_check_stale_and_keeps_it(p: Project) -> None:
    check = p.units["PCDU1"].checked
    set_pin(p, "PCDU1-J01", "1", function="supply")
    assert dc.check_state(p, "PCDU1") == dc.CHANGED and p.units["PCDU1"].checked == check
    assert [i.object_id for i in check_integrity(p) if i.code == "device_check_stale"] == [
        "OBC1", "PCDU1",
    ]  # fmt: skip
    checked(p, "PCDU1")  # checked again: current
    assert dc.check_state(p, "PCDU1") == dc.CHECKED


def test_the_stale_check_reaches_the_drc_as_model_inconsistent(p: Project) -> None:
    from harness_design_studio.core import drc

    hits = [f for f in drc.run(p) if "device_check_stale" in f.id]
    assert [(f.rule, f.severity, f.object_id) for f in hits] == [
        ("model-inconsistent", "warning", "OBC1")
    ]


def test_a_project_without_a_check_has_no_code_and_no_review_row() -> None:
    from harness_design_studio.core import review
    from harness_design_studio.core.samples import mini3

    q = mini3()
    assert device_check_issues(q) == [] and not dc.any_checked(q)
    for h in q.harnesses.values():
        rows = next(b for b in review.review_view(q, h, []).blocks if b.key == "sources").rows
        assert not [r for r in rows if r.cells[0] == "Device"]


# ---- where it shows (section 8.5) ---------------------------------------------------------------


def test_the_review_rows_of_the_core_and_the_verifier(p: Project) -> None:
    from harness_design_studio.core import review
    from harness_design_studio.core.outputs import verify_review as vr

    expected = {
        "W001": [
            ("DEV1", "not checked"),
            ("DEV2", "not checked"),
            ("DEV3", "not checked"),
            ("DEV4", "not checked"),
        ],  # fmt: skip
        "W003": [
            (
                "OBC1",
                "Checked by A. Example on 2026-11-20 against ICD-OBC Issue 1; changed since the check",
            ),  # fmt: skip
            ("PCDU1", "Checked by A. Example on 2026-11-23 against ICD-PCDU Issue 2"),
        ],
    }
    for hid, want in expected.items():
        h = p.harnesses[hid]
        rows = next(b for b in review.review_view(p, h, []).blocks if b.key == "sources").rows
        devices = [(r.cells[1], r.cells[2]) for r in rows if r.cells[0] == "Device"]
        assert devices == want
        assert rows[0].cells[0] == "Device" and rows[0].cells[3:] == ("", "", "")
        theirs = next(b for b in vr.review_rows(p, h, []).blocks if b.key == "sources").rows
        assert [r[0] for r in theirs] == [r.cells for r in rows]


def test_the_verifier_s_hash_is_the_core_s(p: Project) -> None:
    from harness_design_studio.core.outputs import verify_review as vr

    set_pin(p, "PCDU1-J01", "7", signal="TX", interface_id="IF-001")
    p.connectors["PCDU1-J01"] = evolve(p.connectors["PCDU1-J01"], carries=["T1"])
    for uid in p.units:
        assert vr._device_sha256(p, uid) == dc.checked_sha256(p, uid)
    assert (vr._CHECK_UNIT, vr._CHECK_CONNECTOR, vr._CHECK_PIN) == (
        dc.HASHED_UNIT_FIELDS, dc.HASHED_CONNECTOR_FIELDS, dc.HASHED_PIN_FIELDS,
    )  # fmt: skip


@pytest.fixture(scope="module")
def built() -> tuple[Project, dict[str, bytes]]:
    from harness_design_studio.core.outputs.build import build_outputs

    q = format5_project()
    return q, dict(build_outputs(q, drawings=False).files)


def _errors(q: Project, files: dict[str, bytes]) -> list[tuple[str, str]]:
    from harness_design_studio.core.outputs.verify import verify_outputs

    return [(i.code, i.message) for i in verify_outputs(q, files).issues if i.severity == "error"]


def _review_cells(data: bytes) -> list[list[object]]:
    import io

    from harness_design_studio.core.outputs.xlsx_env import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True)
    return [list(r) for r in wb["Review"].iter_rows(values_only=True)]


def test_the_review_sheet_shows_the_checks_and_passes_the_verifier(built: Any) -> None:
    q, files = built
    assert _errors(q, files) == []
    rows = _review_cells(files["harnesses/W003/W003_build.xlsx"])
    devices = [r[:3] for r in rows if r and r[0] == "Device"]
    assert devices == [
        [
            "Device",
            "OBC1",
            "Checked by A. Example on 2026-11-20 against ICD-OBC Issue 1; changed since the check",
        ],  # fmt: skip
        ["Device", "PCDU1", "Checked by A. Example on 2026-11-23 against ICD-PCDU Issue 2"],
    ]
    doc = json.loads(files["system/export.json"])
    units = {u["id"]: u for u in doc["units"]}
    assert units["PCDU1"]["checked"]["icd"] == "ICD-PCDU Issue 2"
    assert "checked" not in units["DEV1"]


def test_a_wrong_check_on_the_review_sheet_is_out_review(built: Any) -> None:
    import io

    from harness_design_studio.core.outputs.xlsx_env import load_workbook

    q, files = built
    rel = "harnesses/W003/W003_build.xlsx"
    wb = load_workbook(io.BytesIO(files[rel]))
    ws = wb["Review"]
    for row in ws.iter_rows():
        if row[0].value == "Device" and row[1].value == "OBC1":
            row[2].value = "Checked by A. Example on 2026-11-20 against ICD-OBC Issue 1"
    out = io.BytesIO()
    wb.save(out)
    errors = _errors(q, {**files, rel: out.getvalue()})
    assert errors and all(code == "out_review" for code, _m in errors), errors


def test_export_data_has_the_three_columns(p: Project) -> None:
    from harness_design_studio.core.open_data import devices_table

    table = devices_table(p)
    assert [c.name for c in table.cols] == [
        "Device", "Checked by", "Checked on", "Checked against", "Check",
    ]  # fmt: skip
    rows = {r["device"]: r for r in table.rows}
    assert rows["OBC1"] == {
        "device": "OBC1", "checked_by": BY, "checked_on": "2026-11-20",
        "checked_against": "ICD-OBC Issue 1", "check": dc.CHANGED,
    }  # fmt: skip
    assert rows["PCDU1"]["check"] == dc.CHECKED
    assert rows["DEV1"] == {
        "device": "DEV1", "checked_by": "", "checked_on": "", "checked_against": "",
        "check": dc.NOT_CHECKED,
    }  # fmt: skip


def test_a_project_of_format_4_keeps_its_outputs() -> None:
    """No device is checked: the Review sheet, the findings and export.json are those of 4.4."""
    from harness_design_studio.core.outputs.build import build_outputs
    from harness_design_studio.core.samples import mini3

    q = mini3()
    before = build_outputs(q, drawings=False).files
    assert not dc.any_checked(q)
    assert b'"checked"' not in before["system/export.json"]


# ---- the command line (section 8.2) ------------------------------------------------------------


@pytest.fixture
def folders(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[Path, Path]:
    """A copy of `first-steps` whose RW1 was saved to the library `lib`."""
    proj, lib = tmp_path / "p", tmp_path / "lib"
    lib.mkdir()
    assert cli(capsys, "new", proj, "--template", "first-steps")[0] == 0
    assert cli(capsys, "save-device", proj, DEVICE, "--library", lib)[0] == 0
    return proj, lib


def test_device_checked_needs_by_and_an_icd(folders, capsys) -> None:
    proj, _lib = folders
    rc, _out, err = cli(capsys, "device-checked", proj, DEVICE)
    assert rc == 2 and "--by NAME" in err
    rc, _out, err = cli(capsys, "device-checked", proj, DEVICE, "--by", BY)
    assert rc == 1 and "name the ICD with --icd" in err
    rc, _out, err = cli(capsys, "device-checked", proj, "TTC9", "--by", BY, "--icd", ICD)
    assert rc == 2 and "no device TTC9" in err
    rc, _out, err = cli(capsys, "device-checked", proj, DEVICE, "--by", BY, "--icd", ICD, "--date", "2026-02-30")  # fmt: skip
    assert rc == 1 and "The date" in err
    assert load_project(proj).project.units[DEVICE].checked is None


def test_device_checked_takes_today_and_the_icd_its_connectors_name(folders, capsys) -> None:
    proj, _lib = folders
    from harness_design_studio.core.io.saver import save_project

    q = load_project(proj).project
    for cid in ("RW1-J01", "RW1-J02"):  # every box connector of RW1 names the ICD
        q.connectors[cid] = evolve(q.connectors[cid], source_doc="ICD-RW", source_version="Issue 2")
    save_project(q, proj)
    rc, out, _err = cli(capsys, "device-checked", proj, DEVICE, "--by", BY)
    assert rc == 0
    today = date.today().isoformat()
    assert f"RW1: checked by A. Example on {today} against ICD-RW Issue 2, the ICD its connectors name." in out  # fmt: skip
    check = load_project(proj).project.units[DEVICE].checked
    assert (check.by, check.on, check.icd) == (BY, today, "ICD-RW Issue 2")
    journal = (proj / "journal.jsonl").read_text(encoding="utf-8")
    assert "checked" in journal.splitlines()[-1]


def test_device_checked_json_and_clear(folders, capsys) -> None:
    proj, _lib = folders
    found = as_json(capsys, "device-checked", proj, DEVICE, "--by", BY, "--icd", ICD, "--date", DAY)
    assert list(found) == list(SHAPES["device-checked"])
    assert found["changed"] and not found["icd_from_connectors"]
    assert found["checked"]["state"] == dc.CHECKED and found["checked"]["on"] == DAY
    again = as_json(capsys, "device-checked", proj, DEVICE, "--by", BY, "--icd", ICD, "--date", DAY)
    assert not again["changed"]
    rc, _out, err = cli(capsys, "device-checked", proj, DEVICE, "--clear", "--by", BY)
    assert rc == 2 and "--clear takes no" in err
    cleared = as_json(capsys, "device-checked", proj, DEVICE, "--clear")
    assert cleared["changed"] and cleared["checked"] is None
    assert load_project(proj).project.units[DEVICE].checked is None
    rc, out, _err = cli(capsys, "device-checked", proj, DEVICE, "--clear")
    assert rc == 0 and "is not checked; nothing was changed" in out


def test_device_checked_refuses_a_read_only_project(folders, capsys) -> None:
    proj, _lib = folders
    doc = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    doc["schema_version"] += 1
    (proj / "project.json").write_text(json.dumps(doc), encoding="utf-8")
    rc, _out, err = cli(capsys, "device-checked", proj, DEVICE, "--by", BY, "--icd", ICD)
    assert rc == 2 and "read-only" in err


def test_check_and_explain_say_the_state(folders, capsys) -> None:
    proj, _lib = folders
    assert cli(capsys, "device-checked", proj, DEVICE, "--by", BY, "--icd", ICD, "--date", DAY)[0] == 0  # fmt: skip
    rc, out, _err = cli(capsys, "explain", proj, DEVICE)
    assert rc == 0 and f"Checked by {BY} on {DAY} against {ICD}." in out
    from harness_design_studio.core.io.saver import save_project

    q = load_project(proj).project
    pins = q.connectors[BOX].pins
    q.connectors[BOX] = evolve(q.connectors[BOX], pins=[evolve(pins[0], function="changed"), *pins[1:]])  # fmt: skip
    save_project(q, proj)
    _rc, out, _err = cli(capsys, "check", proj)
    assert "device_check_stale" in out or "RW1 was checked by" in out
    _rc, out, _err = cli(capsys, "explain", proj, DEVICE)
    assert "; changed since the check." in out


# ---- the library (section 8.4) ------------------------------------------------------------------


def _library_unit(lib: Path) -> dict[str, Any]:
    data = json.loads((lib / FILE).read_text(encoding="utf-8"))
    return data


def test_save_device_writes_the_check_as_file_version_4(folders, capsys) -> None:
    proj, lib = folders
    assert _library_unit(lib)["version"] < 4
    assert cli(capsys, "device-checked", proj, DEVICE, "--by", BY, "--icd", ICD, "--date", DAY)[0] == 0  # fmt: skip
    q = load_project(proj).project
    libs = ll.project_libraries(proj, [lib])
    assert ll.link_state(q, libs, DEVICE).state == ll.CHANGED_HERE
    assert cli(capsys, "save-device", proj, DEVICE, "--library", lib, "--replace")[0] == 0
    data = _library_unit(lib)
    assert data["version"] == 4
    assert data["devices"][0]["unit"]["checked"]["by"] == BY
    q = load_project(proj).project
    assert ll.link_state(q, ll.project_libraries(proj, [lib]), DEVICE).state == ll.UP_TO_DATE


def test_add_device_brings_the_check_and_it_stays_current(folders, capsys, tmp_path) -> None:
    proj, lib = folders
    assert cli(capsys, "device-checked", proj, DEVICE, "--by", BY, "--icd", ICD, "--date", DAY)[0] == 0  # fmt: skip
    assert cli(capsys, "save-device", proj, DEVICE, "--library", lib, "--replace")[0] == 0
    other = tmp_path / "other"
    assert cli(capsys, "new", other)[0] == 0
    assert cli(capsys, "add-device", other, DEVICE, "--count", 2, "--library", lib)[0] == 0
    q = load_project(other).project
    for uid in (DEVICE, f"{DEVICE}-R"):
        assert q.units[uid].checked.by == BY
        assert dc.check_state(q, uid) == dc.CHECKED


def test_update_device_compares_the_check_and_takes_the_library_s(folders, capsys) -> None:
    proj, lib = folders
    path = lib / FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    q = load_project(proj).project
    sha = dc.checked_sha256(q, DEVICE)
    data["devices"][0]["unit"]["checked"] = {"by": BY, "on": DAY, "icd": ICD, "sha256": sha}
    data["version"] = 4
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    rc, out, _err = cli(capsys, "update-device", proj, DEVICE, "--library", lib)
    assert rc == 0 and "library changed" in out
    assert "checked" in out and f"{BY}, {DAY}, {ICD}" in out
    found = as_json(capsys, "update-device", proj, DEVICE, "--library", lib)
    rows = found["devices"][0]["rows"]
    assert [(r["field"], r["here"], r["library"]) for r in rows] == [
        ("checked", "", f"{BY}, {DAY}, {ICD}")
    ]
    assert cli(capsys, "update-device", proj, DEVICE, "--apply", "--library", lib)[0] == 0
    q = load_project(proj).project
    assert q.units[DEVICE].checked.icd == ICD and dc.check_state(q, DEVICE) == dc.CHECKED
    # the library's *not checked* is taken too
    data["devices"][0]["unit"].pop("checked")
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    assert cli(capsys, "update-device", proj, DEVICE, "--apply", "--library", lib)[0] == 0
    assert load_project(proj).project.units[DEVICE].checked is None


def test_the_library_window_s_words_of_a_library_device(folders, capsys) -> None:
    from harness_design_studio.core.library_folder import scan_folder

    proj, lib = folders
    (entry,) = [e for e in scan_folder(lib).entries if e.id == DEVICE]
    assert entry.checked == dc.NOT_CHECKED
    assert cli(capsys, "device-checked", proj, DEVICE, "--by", BY, "--icd", ICD, "--date", DAY)[0] == 0  # fmt: skip
    assert cli(capsys, "save-device", proj, DEVICE, "--library", lib, "--replace")[0] == 0
    (entry,) = [e for e in scan_folder(lib).entries if e.id == DEVICE]
    assert entry.checked == f"Checked by {BY} on {DAY} against {ICD}"
    data = _library_unit(lib)
    data["devices"][0]["connectors"][0]["pins"][0]["function"] = "edited in the file"
    (lib / FILE).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (entry,) = [e for e in scan_folder(lib).entries if e.id == DEVICE]
    assert entry.checked.endswith("; changed since the check")


# ---- the scripting interface --------------------------------------------------------------------


def test_set_and_clear_device_checked_of_the_scripting_interface(folders) -> None:
    from harness_design_studio import api

    proj, _lib = folders
    with pytest.raises(EditError, match="name the ICD"):
        api.set_device_checked(proj, DEVICE, by=BY)
    got = api.set_device_checked(proj, DEVICE, by=BY, icd=ICD, on=DAY)
    assert (got["by"], got["on"], got["icd"]) == (BY, DAY, ICD) and len(got["sha256"]) == 64
    assert load_project(proj).project.units[DEVICE].checked is not None
    assert api.clear_device_checked(proj, DEVICE) is True
    assert api.clear_device_checked(proj, DEVICE) is False
    assert load_project(proj).project.units[DEVICE].checked is None
