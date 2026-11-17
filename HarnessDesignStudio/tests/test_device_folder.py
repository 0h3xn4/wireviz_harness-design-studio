# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return"
"""The device library folder of 2.2.0 (D-240, `docs/ait/DESIGN_2.2_DEVICE_LIBRARY.md` sections 2
and 5): the rules of `NAME.device.json`, the checks across the folder, `library.json`, and the
folder read as data only (caps, strict JSON, no links, no hidden folders, nothing imported)."""

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.core import device_file as df
from harness_design_studio.core import device_library as dl
from harness_design_studio.core import library_folder as lf
from harness_design_studio.core.commands import History
from harness_design_studio.core.library_folder import LibraryConflict, save_devices, scan_folder
from harness_design_studio.core.model import Part
from tests.helpers import pinout_project

PYTHON_WORDS = ("Error", "Exception", "Traceback", "NoneType", "pydantic")


def one(uid: str = "OBC") -> dict[str, Any]:
    return df.device_file_data(pinout_project(), uid)


def put(folder: Path, rel: str, data: object) -> Path:
    path = folder / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def problems_of(scan: lf.LibraryScan) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for p in scan.problems:
        out.setdefault(p.file, []).append(p.message)
    return out


def device_ids(scan: lf.LibraryScan) -> list[tuple[str, str]]:
    return [(e.id, e.file) for e in scan.entries if e.kind == "device"]


def assert_words(scan: lf.LibraryScan) -> None:
    """Every problem is one sentence in plain words."""
    for p in [*scan.problems, *scan.warnings]:
        assert p.message.endswith((".", ")")), p
        assert not any(w in p.message for w in PYTHON_WORDS), p


# ---- the rules of one file -------------------------------------------------------------------


def test_a_device_file_made_from_a_project_keeps_every_rule(tmp_path: Path):
    data = one()
    assert df.device_file_problems("OBC.device.json", data) == []
    put(tmp_path, "OBC.device.json", data)
    scan = scan_folder(tmp_path)
    assert device_ids(scan) == [("OBC", "OBC.device.json")] and not scan.problems


def test_the_name_must_be_the_device_id_and_case_counts(tmp_path: Path):
    put(tmp_path, "PCDU.device.json", one())
    put(tmp_path, "obc.device.json", one())
    scan = scan_folder(tmp_path)
    assert device_ids(scan) == []
    said = problems_of(scan)
    assert "OBC.device.json" in said["PCDU.device.json"][0]
    assert "says obc" in said["obc.device.json"][0]
    assert_words(scan)


def test_a_device_file_holds_exactly_one_device(tmp_path: Path):
    two = dl.export_devices(pinout_project(), ["OBC", "RW1"])
    none = {**one(), "devices": []}
    assert "holds 2" in df.device_file_problems("OBC.device.json", two)[0]
    assert "holds 0" in df.device_file_problems("OBC.device.json", none)[0]


def test_connectors_must_be_box_connectors_of_the_device_named_after_it():
    data = one()
    conn = data["devices"][0]["connectors"][0]
    for change, words in (
        ({"role": "cable"}, "not a box connector"),
        ({"unit_id": "RW1"}, "not a box connector"),
        ({"id": "J99"}, "does not start with 'OBC-'"),
        ({"id": "RW1-J01"}, "does not start with 'OBC-'"),
    ):
        bad = json.loads(json.dumps(data))
        bad["devices"][0]["connectors"][0] = {**conn, **change}
        found = df.device_file_problems("OBC.device.json", bad)
        assert any(words in t for t in found), (change, found)


def test_a_device_file_is_complete_on_its_own():
    p = pinout_project()
    p.parts["CT-22"] = Part(id="CT-22", category="contact", approval="approved")
    c = p.connectors["OBC-J01"]
    p.connectors["OBC-J01"] = c.model_copy(
        update={"pins": [c.pins[0].model_copy(update={"contact_part": "CT-22"}), *c.pins[1:]]}
    )
    data = df.device_file_data(p, "OBC")
    assert df.device_file_problems("OBC.device.json", data) == []
    parts = data["parts"]
    for missing, words in (
        ("CT-22", "contact part CT-22"),
        (c.part_id, f"part {c.part_id} of the connector"),
    ):
        bad = {**data, "parts": [x for x in parts if x["id"] != missing]}
        assert any(words in t for t in df.device_file_problems("OBC.device.json", bad))
    mated = next(x for x in parts if x.get("mates_with"))
    bad = {**data, "parts": [x for x in parts if x["id"] != mated["mates_with"]]}
    assert any("mates with" in t for t in df.device_file_problems("OBC.device.json", bad))
    carried = data["devices"][0]["connectors"][0]["carries"][0]
    bad = {**data, "interface_types": [t for t in data["interface_types"] if t["id"] != carried]}
    assert any(
        f"interface type {carried}" in t for t in df.device_file_problems("OBC.device.json", bad)
    )


def test_nothing_of_one_project_is_in_a_device_file():
    data = one()
    unit = data["devices"][0]["unit"]
    conn = data["devices"][0]["connectors"][0]
    pin = conn["pins"][0]
    cases = [
        ({**unit, "zone": "Z1"}, None, None, "zone"),
        (None, {**conn, "locked": True}, None, "locked"),
        (None, None, {**pin, "locked": True}, "interface or a lock"),
        (None, None, {**pin, "interface_id": "IF-001"}, "interface or a lock"),
    ]
    for u, c, p, words in cases:
        bad = json.loads(json.dumps(data))
        rec = bad["devices"][0]
        if u is not None:
            rec["unit"] = u
        if c is not None:
            rec["connectors"][0] = c
        if p is not None:
            rec["connectors"][0]["pins"][0] = p
        assert any(words in t for t in df.device_file_problems("OBC.device.json", bad)), words


def test_an_unknown_key_and_a_bad_value_are_refused():
    data = one()
    assert "'source'" in df.device_file_problems("OBC.device.json", {**data, "source": 1})[0]
    bad = json.loads(json.dumps(data))
    bad["devices"][0]["unit"]["mass_relevant"] = "yes"
    (text,) = df.device_file_problems("OBC.device.json", bad)
    assert "mass_relevant" in text and not any(w in text for w in PYTHON_WORDS)
    bad = json.loads(json.dumps(data))
    bad["devices"][0]["unit"]["colour"] = "red"
    assert "colour" in df.device_file_problems("OBC.device.json", bad)[0]
    bad = json.loads(json.dumps(data))
    bad["devices"][0]["extra"] = 1
    assert "'extra'" in df.device_file_problems("OBC.device.json", bad)[0]


def test_a_version_2_file_is_refused_with_words(tmp_path: Path):
    put(tmp_path, "OBC.device.json", {**one(), "version": 2})
    (problem,) = scan_folder(tmp_path).problems
    assert "version 2" in problem.message and "newer program" in problem.message


def test_a_device_file_of_another_format_is_a_problem_not_a_skip(tmp_path: Path):
    put(tmp_path, "OBC.device.json", {"name": "x"})
    scan = scan_folder(tmp_path)
    assert scan.skipped == 0 and "must be a device library file" in scan.problems[0].message


def test_a_device_file_can_be_added_to_a_project(tmp_path: Path):
    p = pinout_project()
    save_devices(tmp_path, p, ["OBC"])
    data = dl.read_library(tmp_path / "OBC.device.json")
    q = pinout_project()
    plan = dl.plan_device_import(q, data, ["OBC"])
    assert plan.ok_count == 1
    History(q).execute("add", plan.ops)
    assert plan.rows[0].new_id in q.units


# ---- the checks across the folder --------------------------------------------------------------


def test_a_device_in_two_files_is_offered_from_neither_and_both_files_are_named(tmp_path: Path):
    put(tmp_path, "OBC.device.json", one())
    put(tmp_path, "OBC.json", dl.export_devices(pinout_project(), ["OBC", "RW1"]))  # a 2.1 file
    scan = scan_folder(tmp_path)
    assert device_ids(scan) == [("RW1", "OBC.json")]  # the other device of the file still is
    said = problems_of(scan)
    assert "OBC.json" in said["OBC.device.json"][0] and "OBC" in said["OBC.device.json"][0]
    assert "OBC.device.json" in said["OBC.json"][0]
    assert scan.holders["obc"] == ("OBC.device.json", "OBC.json")
    assert_words(scan)


def test_a_device_id_is_compared_without_regard_to_case_across_files(tmp_path: Path):
    put(tmp_path, "a.json", dl.export_devices(pinout_project(), ["OBC"]))
    put(tmp_path, "b.json", dl.export_devices(pinout_project(), ["OBC"], {"OBC": "obc"}))
    scan = scan_folder(tmp_path)
    assert device_ids(scan) == [] and set(problems_of(scan)) == {"a.json", "b.json"}


def test_the_same_file_name_in_two_folders_is_refused(tmp_path: Path):
    put(tmp_path, "OBC.device.json", one())
    put(tmp_path, "team/OBC.device.json", one())
    put(tmp_path, "RW1.device.json", one("RW1"))
    scan = scan_folder(tmp_path)
    assert device_ids(scan) == [("RW1", "RW1.device.json")]
    said = problems_of(scan)
    assert any("same name (team/OBC.device.json)" in t for t in said["OBC.device.json"])
    assert any("same name (OBC.device.json)" in t for t in said["team/OBC.device.json"])
    assert_words(scan)


def test_two_file_names_that_differ_only_in_case_are_refused(tmp_path: Path):
    put(tmp_path, "a/devices.json", dl.export_devices(pinout_project(), ["OBC"]))
    put(tmp_path, "b/Devices.json", dl.export_devices(pinout_project(), ["RW1"]))
    scan = scan_folder(tmp_path)
    assert device_ids(scan) == []
    assert set(problems_of(scan)) == {"a/devices.json", "b/Devices.json"}


def test_a_part_with_different_data_in_two_files_is_a_warning_that_names_the_fields(tmp_path):
    a, b = one(), one("RW1")
    shared = {x["id"] for x in a["parts"]} & {x["id"] for x in b["parts"]}
    pid = sorted(shared)[0]
    b["parts"] = [
        {**x, "notes": "other", "approval": "approved"} if x["id"] == pid else x for x in b["parts"]
    ]
    put(tmp_path, "OBC.device.json", a)
    put(tmp_path, "RW1.device.json", b)
    scan = scan_folder(tmp_path)
    assert {e.id for e in scan.entries} == {"OBC", "RW1"} and not scan.problems
    (warning,) = scan.warnings
    assert warning.file == "RW1.device.json"
    assert pid in warning.message and "OBC.device.json" in warning.message
    assert "approval, notes" in warning.message
    assert_words(scan)


def test_the_same_part_in_two_files_is_no_warning(tmp_path: Path):
    put(tmp_path, "OBC.device.json", one())
    put(tmp_path, "PCDU.device.json", one("PCDU"))
    put(tmp_path, "RW1.device.json", one("RW1"))
    scan = scan_folder(tmp_path)
    assert len(scan.entries) == 3 and not scan.warnings and not scan.problems


def test_a_21_multi_device_file_is_still_offered(tmp_path: Path):
    put(tmp_path, "devices.json", dl.export_devices(pinout_project(), ["OBC", "RW1", "PCDU"]))
    put(tmp_path, "GYRO.json", {**dl.export_devices(pinout_project(), ["OBC"], {"OBC": "GYRO"})})
    scan = scan_folder(tmp_path)
    assert sorted(device_ids(scan)) == [
        ("GYRO", "GYRO.json"),
        ("OBC", "devices.json"),
        ("PCDU", "devices.json"),
        ("RW1", "devices.json"),
    ]
    assert not scan.problems


# ---- library.json --------------------------------------------------------------------------


def test_library_json_names_the_library_and_the_folder_name_is_the_fallback(tmp_path: Path):
    folder = tmp_path / "acme-device-library"
    folder.mkdir()
    put(folder, "OBC.device.json", one())
    assert scan_folder(folder).name == "acme-device-library"
    assert df.library_info(folder) == df.LibraryInfo("acme-device-library")
    info = {"format": df.FOLDER_FORMAT, "version": 1, "name": "ACME devices", "description": "d"}
    put(folder, "library.json", info)
    scan = scan_folder(folder)
    assert (scan.name, scan.description) == ("ACME devices", "d")
    assert scan.skipped == 0 and not scan.problems and len(scan.entries) == 1
    assert df.library_info(folder) == df.LibraryInfo("ACME devices", "d", True)


@pytest.mark.parametrize(
    ("change", "words"),
    [
        ({"owner": "x"}, "'owner'"),
        ({"version": 2}, "version 2"),
        ({"version": "1"}, "version number"),
        ({"name": ""}, "name"),
        ({"name": 5}, "name"),
        ({"description": ["x"]}, "description"),
    ],
)
def test_library_json_is_strict(tmp_path: Path, change: dict[str, Any], words: str):
    info = {"format": df.FOLDER_FORMAT, "version": 1, "name": "ACME devices", **change}
    put(tmp_path, "library.json", info)
    put(tmp_path, "OBC.device.json", one())
    scan = scan_folder(tmp_path)
    assert [p.file for p in scan.problems] == ["library.json"]
    assert words in scan.problems[0].message
    assert scan.name == tmp_path.name and len(scan.entries) == 1
    with pytest.raises(df.LibraryInfoError, match=words.replace("'", ".")):
        df.library_info(tmp_path)


def test_a_library_json_in_a_subfolder_or_of_another_format_is_not_the_description(tmp_path):
    put(tmp_path, "team/library.json", {"format": df.FOLDER_FORMAT, "version": 1, "name": "x"})
    put(tmp_path, "library.json", dl.export_devices(pinout_project(), ["OBC"]))  # a 2.1 file
    scan = scan_folder(tmp_path)
    assert scan.name == tmp_path.name and device_ids(scan) == [("OBC", "library.json")]
    assert scan.skipped == 1


# ---- trust: the folder is data ---------------------------------------------------------------


def test_python_files_are_never_read_and_nothing_is_imported(tmp_path: Path):
    put(tmp_path, "OBC.device.json", one())
    (tmp_path / "evil.py").write_text("import sys; sys.modules['evil_ran'] = sys\n")
    (tmp_path / "evil_mod").mkdir()
    (tmp_path / "evil_mod" / "__init__.py").write_text("raise SystemExit('ran')\n")
    (tmp_path / "devices.json.py").write_text("x = 1\n")
    scan_folder(tmp_path / "evil_mod")  # one scan first, so lazy imports of the tool are done
    before = set(sys.modules)
    scan = scan_folder(tmp_path)
    assert set(sys.modules) == before and "evil_ran" not in sys.modules
    assert device_ids(scan) == [("OBC", "OBC.device.json")] and not scan.problems


def test_a_key_twice_nan_and_a_lone_surrogate_are_refused(tmp_path: Path):
    put(tmp_path, "OBC.device.json", one())
    good = json.dumps(one("RW1"))
    (tmp_path / "RW1.device.json").write_text(
        good.replace('"version": 1', '"version": 1, "version": 1')
    )
    (tmp_path / "PCDU.device.json").write_text(
        good.replace('"RW1"', '"PCDU"').replace('"notes": ""', '"notes": NaN', 1)
    )
    (tmp_path / "X.json").write_text(good.replace('"notes": ""', '"notes": "\\ud800"', 1))
    scan = scan_folder(tmp_path)
    said = problems_of(scan)
    assert "'version' twice" in said["RW1.device.json"][0]
    assert "does not allow" in said["PCDU.device.json"][0]
    assert "not valid text" in said["X.json"][0]
    assert device_ids(scan) == [("OBC", "OBC.device.json")]
    assert_words(scan)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs links")
def test_links_and_hidden_folders_are_not_followed(tmp_path: Path):
    lib, outside = tmp_path / "lib", tmp_path / "outside"
    put(outside, "RW1.device.json", one("RW1"))
    put(lib, "OBC.device.json", one())
    put(lib, ".hidden/PCDU.device.json", one("PCDU"))
    put(lib, ".git/RW1.device.json", one("RW1"))
    try:
        (lib / "linked").symlink_to(outside, target_is_directory=True)
        (lib / "RW1.device.json").symlink_to(outside / "RW1.device.json")
    except OSError:
        pytest.skip("links cannot be made here")
    scan = scan_folder(lib)
    assert device_ids(scan) == [("OBC", "OBC.device.json")] and not scan.problems


def test_the_caps_are_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    put(tmp_path, "a/b/OBC.device.json", one())  # two levels below: read
    put(tmp_path, "a/b/c/RW1.device.json", one("RW1"))  # three levels below: not looked into
    big = tmp_path / "BIG.device.json"
    big.write_bytes(b" " * (dl.MAX_BYTES + 1))
    scan = scan_folder(tmp_path)
    assert device_ids(scan) == [("OBC", "a/b/OBC.device.json")]
    assert "too large" in problems_of(scan)["BIG.device.json"][0]
    monkeypatch.setattr(lf, "MAX_FILES", 1)
    scan = scan_folder(tmp_path)
    assert any("Only the first 1 files" in p.message for p in scan.problems)


def test_one_bad_file_never_hides_the_good_ones(tmp_path: Path):
    put(tmp_path, "OBC.device.json", one())
    put(tmp_path, "RW1.device.json", {**one("RW1"), "devices": 5})
    (tmp_path / "PCDU.device.json").write_text("{nope")
    put(tmp_path, "GYRO.device.json", [1, 2])
    scan = scan_folder(tmp_path)
    assert device_ids(scan) == [("OBC", "OBC.device.json")]
    assert set(problems_of(scan)) == {"RW1.device.json", "PCDU.device.json", "GYRO.device.json"}
    assert_words(scan)


# ---- saving: one device per file -------------------------------------------------------------


def test_saving_writes_one_file_per_device(tmp_path: Path):
    paths = save_devices(tmp_path, pinout_project(), ["OBC", "RW1"])
    assert [p.name for p in paths] == ["OBC.device.json", "RW1.device.json"]
    scan = scan_folder(tmp_path)
    assert device_ids(scan) == [("OBC", "OBC.device.json"), ("RW1", "RW1.device.json")]
    assert not scan.problems and not scan.warnings
    assert dl.default_file_name(["OBC"]) == "OBC.device.json"


def test_saving_a_device_a_21_file_holds_writes_into_that_file(tmp_path: Path):
    put(tmp_path, "team/devices.json", dl.export_devices(pinout_project(), ["OBC", "RW1"]))
    (path,) = save_devices(tmp_path, pinout_project(), ["OBC"])
    assert path == tmp_path / "team" / "devices.json"
    assert not (tmp_path / "OBC.device.json").exists()
    assert lf.save_targets(scan_folder(tmp_path), ["OBC", "PCDU"]) == [
        "team/devices.json",
        "PCDU.device.json",
    ]


def test_saving_a_device_that_is_in_two_files_is_refused(tmp_path: Path):
    put(tmp_path, "OBC.device.json", one())
    put(tmp_path, "old/OBC.json", dl.export_devices(pinout_project(), ["OBC"]))
    before = (tmp_path / "OBC.device.json").read_bytes()
    with pytest.raises(lf.LibraryError, match="more than one file"):
        save_devices(tmp_path, pinout_project(), ["OBC"])
    assert (tmp_path / "OBC.device.json").read_bytes() == before


def test_a_connector_id_of_another_form_gets_the_device_id_in_the_file(tmp_path: Path):
    p = pinout_project()
    c = p.connectors.pop("OBC-J01")
    p.connectors["J1"] = c.model_copy(update={"id": "J1"})
    (path,) = save_devices(tmp_path, p, ["OBC"])
    ids = [c["id"] for c in dl.read_library(path)["devices"][0]["connectors"]]
    assert "OBC-J1" in ids and "J1" not in ids
    assert not scan_folder(tmp_path).problems


def test_a_conflict_in_two_files_is_one_question_and_nothing_is_written(tmp_path: Path):
    save_devices(tmp_path, pinout_project(), ["OBC", "RW1"])
    p = pinout_project()
    for cid in ("OBC-J01", "RW1-J02"):
        c = p.connectors[cid]
        p.connectors[cid] = c.model_copy(
            update={"pins": [c.pins[0].model_copy(update={"signal": "ZZ"}), *c.pins[1:]]}
        )
    before = {f.name: f.read_bytes() for f in tmp_path.iterdir()}
    with pytest.raises(LibraryConflict) as err:
        save_devices(tmp_path, p, ["OBC", "RW1"])
    assert [c.unit_id for c in err.value.conflicts] == ["OBC", "RW1"]
    assert {f.name: f.read_bytes() for f in tmp_path.iterdir()} == before
    put(tmp_path, "OBC-2.device.json", df.device_file_data(pinout_project(), "OBC", "OBC-2"))
    with pytest.raises(LibraryConflict) as err:
        save_devices(tmp_path, p, ["OBC"])
    assert err.value.conflicts[0].suggested_id == "OBC-3"  # free in the whole folder


def test_a_conflict_in_two_files_names_both_files(tmp_path: Path):
    save_devices(tmp_path, pinout_project(), ["OBC", "RW1"])
    p = pinout_project()
    for cid in ("OBC-J01", "RW1-J02"):
        c = p.connectors[cid]
        p.connectors[cid] = c.model_copy(
            update={"pins": [c.pins[0].model_copy(update={"signal": "ZZ"}), *c.pins[1:]]}
        )
    with pytest.raises(LibraryConflict) as err:
        save_devices(tmp_path, p, ["OBC", "RW1"])
    assert err.value.file == "OBC.device.json, RW1.device.json"
    assert str(err.value).startswith("OBC.device.json, RW1.device.json have these devices")
