# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index,union-attr"
"""REQ-MIGRATE-09: format 4 (D-250, D-251, design of 4.0.0 `docs/ait/DESIGN_4.0_ROW_LAYOUT.md`
sections 4 and 5, pull request 1).

This tool writes `schema_version` 5 since D-264 (`tests/test_format5.py`); the step from 3 to 4 is
still one of its steps, and an upgrade from format 3 takes it and then the step from 4 to 5, which
writes the number only. The step from 3 to 4 (`core/io/migrate.py` `_v3_to_v4`, the
parts `V3_TO_V4_PARTS`) writes the number and nothing else: the one new key of format 4,
`row_layout` of a connector part and of a box connector, is sparse, and nobody has a layout before
format 4. Like the step from 1 to 2 it changes no hash, so the migration safety net is its whole
proof (section 5.2): the format 3 files read as they are and the format 4 files the step writes give
the same model hash, findings, released harnesses and in-memory export, byte for byte. A format 2 or
format 1 project goes through every step in one upgrade. A 3.x tool opens a format 4 project
read-only. A device library file is written as version 3 and a subsystem file as version 2 only
when they hold a layout (section 5.5). The output-hash baseline and the numbers snapshot stay as
they are (`tests/test_output_hashes.py`, `tests/test_numbers_snapshot.py`).
"""

import copy
import json
import shutil
from pathlib import Path

import pytest

from harness_design_studio.cli.main import main
from harness_design_studio.core import device_library, subsystem_library
from harness_design_studio.core.errors import SaveError
from harness_design_studio.core.io import canonical, layout, loader, migrate, saver, upgrade
from harness_design_studio.core.io.layout import is_managed, model_hash
from harness_design_studio.core.io.loader import load_project, read_tree
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.mergefix import plan_version_fix
from harness_design_studio.core.model import SCHEMA_VERSION, RowLayout, evolve
from harness_design_studio.core.outputs.build import build_outputs
from harness_design_studio.resources import examples_path
from tests.helpers import FIXTURES
from tests.migration_support import HEAVY, SCENARIOS, as_format, build, folder_bytes

JOURNAL = "journal.jsonl"
LAYOUT = b'"row_layout"'
OLD_FIXTURES = {"v0_project": None, "v1_project": 1, "m1_project": 1}


def managed(root: Path) -> dict[str, bytes]:
    return {k: v for k, v in folder_bytes(root).items() if is_managed(k)}


def as_three(name: str, dest: Path) -> Path:
    """A scenario as a 3.0.x tool wrote it: a fixture kept in an older format is brought up to this
    tool's format first, then the number is written as 3 (format 3 is format 4 without a layout)."""
    root = build(name, dest)
    if (upgrade.format_of(root) or 0) < SCHEMA_VERSION:
        first = upgrade.upgrade_project(root)
        assert first is not None
        shutil.rmtree(root / first.backup)
    return as_format(root, 3)


def _rows() -> RowLayout:
    return RowLayout(rows=[["1", "2"], ["3"]])


# ---- the number ----------------------------------------------------------------------------------------


def test_the_step_from_3_to_4_is_still_a_step_of_this_tool() -> None:
    assert SCHEMA_VERSION == 5 and migrate.current_version() == 5  # format 5 since D-264
    assert sorted(migrate.MIGRATIONS) == [0, 1, 2, 3, 4]
    assert migrate.MIGRATIONS[3] is migrate._v3_to_v4
    assert (migrate._v4_number,) == migrate.V3_TO_V4_PARTS
    assert upgrade.VERSIONS_FORMAT == migrate.VERSIONS_FORMAT == 3
    assert layout.HASH_SCHEMA_VERSION == 1  # the hash is of the design, never of the format


# The feature example of pin rows (design of 5.1.0, section 4.1) sets a layout on its own EXAMPLE
# parts; the starter library and every other example still ship none (L3).
SHOWS_ROW_LAYOUT = {"full-connectors", "imports-from-files"}  # the latter: as its pinout file says


def test_every_fixture_and_example_is_in_the_current_format_without_a_layout() -> None:
    examples = examples_path()
    assert examples is not None
    roots = [p.parent for p in FIXTURES.rglob("project.json")]
    roots += [p.parent for p in (examples / "projects").glob("*/project.json")]
    assert len(roots) >= 10
    for root in sorted(roots):
        doc = json.loads((root / "project.json").read_text(encoding="utf-8"))
        assert doc.get("schema_version") == OLD_FIXTURES.get(root.name, SCHEMA_VERSION), root
        found = [path for path in root.rglob("*.json") if LAYOUT in path.read_bytes()]
        if root.parent.name == "projects" and root.name in SHOWS_ROW_LAYOUT:
            assert found, root  # the example of pin rows keeps its layout
        else:
            assert not found, found  # the starter parts ship no layout (L3)


# ---- the step on the files -------------------------------------------------------------------------------


def test_the_step_writes_the_number_and_nothing_else(tmp_path: Path) -> None:
    root = as_three("released", tmp_path / "p")
    files, _broken, _issues = read_tree(root)
    out = migrate.migrate_raw(copy.deepcopy(files), 3, to_version=4)
    assert out["project.json"] == {**files["project.json"], "schema_version": 4}
    assert {rel: data for rel, data in out.items() if rel != "project.json"} == {
        rel: data for rel, data in files.items() if rel != "project.json"
    }
    assert files == read_tree(root)[0]  # the input is not changed


@pytest.mark.parametrize(
    "name", [pytest.param(n, marks=pytest.mark.slow) if n in HEAVY else n for n in SCENARIOS]
)
def test_the_upgrade_from_3_changes_the_number_only_and_passes_every_check(
    name: str, tmp_path: Path
) -> None:
    """Section 5.2: the files of format 3 read as they are and the files the upgrade writes give the
    same model hash, findings, released harnesses and export (the run-time check of `upgrade`); after
    the step no part and no connector has a layout, `project.json` differs in its number only, and
    every other project file is byte-identical (the journal has one more entry)."""
    root = as_three(name, tmp_path / "p")
    before = managed(root)
    had_journal = JOURNAL in before
    plan = upgrade.plan_upgrade(root)  # the dry run
    assert managed(root) == before  # writes nothing
    assert plan is not None and plan.ok, plan.lost
    assert (plan.from_version, plan.to_version) == (3, 5)  # and on through the step from 4 to 5
    assert plan.hash_equal is True and plan.exports_equal is True and plan.baselines_intact
    assert plan.nothing_but_versions is None and plan.versions == []  # no step 2 to 3 here
    assert set(plan.files) == {"project.json", *([JOURNAL] if had_journal else [])}
    done = upgrade.upgrade_project(root)
    assert done is not None and all(done.self_check.values()), done.self_check
    after = managed(root)
    assert set(after) == set(before)
    changed = {rel for rel in after if after[rel] != before[rel]}
    assert changed == {"project.json", *([JOURNAL] if had_journal else [])}
    old, new = json.loads(before["project.json"]), json.loads(after["project.json"])
    old_number, new_number = old.pop("schema_version"), new.pop("schema_version")
    assert old_number == 3 and new_number == 5 and old == new
    if had_journal:  # one more line: "migrated from format 3"
        assert after[JOURNAL].startswith(before[JOURNAL])
        assert after[JOURNAL].count(b"\n") == before[JOURNAL].count(b"\n") + 1
    assert not [rel for rel, data in after.items() if LAYOUT in data]  # no layout appears
    record = json.loads((root / done.record).read_bytes())
    assert (record["status"], record["from_version"], record["to_version"]) == ("complete", 3, 5)
    assert done.backup == ".migration-backup-v3"


@pytest.mark.parametrize(
    "name", ["mini3", "example-first-steps", pytest.param("released", marks=pytest.mark.slow)]
)
def test_the_export_with_the_harness_plans_is_the_same_after_the_step(
    name: str, tmp_path: Path
) -> None:
    root = as_three(name, tmp_path / "p")
    old = load_project(root, migrate=False).project  # format 3 read as it is
    assert old.meta.schema_version == 3
    want = build_outputs(old, harness_plan=True).files
    want_hash = model_hash(old)
    upgrade.upgrade_project(root)
    new = load_project(root).project
    assert model_hash(new) == want_hash  # the model hash rule: the number is not in it
    assert build_outputs(new, harness_plan=True).files == want


@pytest.mark.slow
def test_the_step_run_twice_writes_the_same_files(tmp_path: Path) -> None:
    one, two = as_three("released", tmp_path / "a"), as_three("released", tmp_path / "b")
    for root in (one, two):
        assert upgrade.upgrade_project(root) is not None
    assert managed(one) == managed(two)
    assert upgrade.upgrade_project(one) is None  # up to date


def test_migrate_dry_run_shows_the_one_change_and_writes_nothing(tmp_path: Path, capsys) -> None:
    root = as_three("mini3", tmp_path / "p")
    before = folder_bytes(root)
    assert main(["migrate", str(root), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Project format 3; this tool writes format 5." in out
    assert "changed  project.json" in out and "(equal)" in out and "identical" in out
    assert "Nothing is lost. Nothing was written." in out
    assert main(["migrate", str(root), "--dry-run", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert (doc["from_version"], doc["to_version"], doc["ok"]) == (3, 5, True)
    assert doc["files"] == [{"file": "project.json", "change": "changed"}]
    assert doc["model_hash_before"] == doc["model_hash_after"]
    assert folder_bytes(root) == before
    assert main(["migrate", str(root)]) == 0
    out = capsys.readouterr().out
    assert "Format 3 to 5." in out and "same model hash" in out


# ---- format 2 and format 1 in one upgrade -----------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("version", [1, 2])
def test_an_older_project_goes_through_every_step_in_one_upgrade(
    version: int, tmp_path: Path, capsys
) -> None:
    root = build("released", tmp_path / "p")
    want = managed(root)
    as_format(root, version)
    assert main(["migrate", str(root), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"Project format {version}; this tool writes format 5." in out
    assert "revision B → version 2.0.0" in out and "Only the versions change" in out
    assert main(["migrate", str(root)]) == 0
    assert f"Format {version} to 5." in capsys.readouterr().out
    after = managed(root)
    assert {k: v for k, v in after.items() if not k.startswith("journal")} == {
        k: v for k, v in want.items() if not k.startswith("journal")
    }  # the files of the current format as this tool writes them, byte for byte
    record = json.loads((root / f".migration-backup-v{version}" / upgrade.RECORD_NAME).read_bytes())
    assert record["to_version"] == 5
    assert record["proof"] == {"nothing_but_versions": True, "versions_mapped": True}


def test_set_version_is_still_taken_on_the_way_from_2_to_5(tmp_path: Path, capsys) -> None:
    root = as_format(build("mini3", tmp_path / "p"), 2)
    path = root / "physical" / "harnesses" / "W001.json"
    doc = json.loads(path.read_bytes())
    doc["revision"] = "A1"
    path.write_bytes(canonical.dumps(doc))
    assert main(["migrate", str(root)]) == 1
    capsys.readouterr()
    assert main(["migrate", str(root), "--set-version", "W001:A1=1.1.0"]) == 0
    p = load_project(root).project
    assert p.meta.schema_version == 5 and p.harnesses["W001"].version == "1.1.0"


# ---- older and newer tools ---------------------------------------------------------------------------------


def test_a_reader_of_format_3_opens_a_format_4_project_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a 3.0.x tool does with a format 4 project, simulated by the loader's own version check
    (D-226): it is newer than the reader, so it is opened read-only and nothing is saved over it."""
    root = as_format(build("mini3", tmp_path / "p"), 4)
    before = managed(root)
    for module in (loader, saver):
        monkeypatch.setattr(module, "SCHEMA_VERSION", 3)
    r = load_project(root)
    assert r.project.read_only and any(i.code == "newer_version" for i in r.issues)
    with pytest.raises(SaveError):
        save_project(r.project, root)
    assert managed(root) == before


def test_a_format_3_project_is_written_only_by_migrate(tmp_path: Path) -> None:
    root = as_three("mini3", tmp_path / "p")
    r = load_project(root)
    assert r.project.migrated_from == 3 and not r.has_errors
    with pytest.raises(SaveError, match="migrate"):
        save_project(r.project, root)
    out = tmp_path / "copy"
    save_project(r.project, out)  # a new folder gets the current format
    assert json.loads((out / "project.json").read_bytes())["schema_version"] == SCHEMA_VERSION


def test_check_of_a_format_3_project_finds_nothing_to_rewrite(tmp_path: Path, capsys) -> None:
    root = as_three("released", tmp_path / "p")
    assert main(["check", str(root), "--json"]) in (0, 1)
    doc = json.loads(capsys.readouterr().out)
    assert [i for i in doc["issues"] if i["code"] == "not_canonical"] == []


def test_a_format_2_key_merged_into_a_format_3_project_is_named_and_rewritten(
    tmp_path: Path,
) -> None:
    """A format 3 project that a branch of format 2 was merged into (design of 3.0.0 section 5.6)
    is still named by the loader of a format 4 tool and rewritten by `merge-fix`, so that `migrate`
    can then upgrade it."""
    root = as_three("mini3", tmp_path / "p")
    path = root / "physical" / "harnesses" / "W001.json"
    doc = json.loads(path.read_bytes())
    doc.pop("version")
    doc["revision"] = "A"  # the letter of version 1.0.0
    path.write_bytes(canonical.dumps(doc))
    r = load_project(root)
    assert any(i.code == migrate.LEFTOVER_CODE for i in r.issues)
    fix = plan_version_fix(root)
    assert fix.writes and not fix.problem
    for rel, data in fix.writes:
        assert data is not None
        (root / rel).write_bytes(data)
    assert json.loads((root / "project.json").read_bytes())["schema_version"] == 3  # kept
    assert upgrade.upgrade_project(root) is not None
    assert load_project(root).project.harnesses["W001"].version == "1.0.0"


# ---- the device library file and the subsystem file (section 5.5) ----------------------------------------


def _project_with_rows(own: bool, part: bool):
    from harness_design_studio.core.samples import mini3

    p = mini3()
    cid = "OBC-J02"  # pins 1 to 3
    if own:
        p.connectors[cid] = evolve(p.connectors[cid], row_layout=_rows())
    if part:
        pid = p.connectors[cid].part_id
        p.parts[pid] = evolve(p.parts[pid], row_layout=_rows())
    return p, p.connectors[cid].unit_id


@pytest.mark.parametrize(("own", "part"), [(True, False), (False, True), (True, True)])
def test_a_device_file_with_a_layout_is_version_3(own: bool, part: bool) -> None:
    p, uid = _project_with_rows(own, part)
    content = device_library.export_devices(p, [uid])
    assert content["version"] == 3 and device_library.check_library(content)
    plan = device_library.plan_device_import(_project_with_rows(False, False)[0], content)
    assert plan is not None


def test_a_device_file_without_a_layout_keeps_its_version() -> None:
    p, uid = _project_with_rows(False, False)
    assert device_library.export_devices(p, [uid])["version"] == 1
    box = next(c for c in p.connectors.values() if c.unit_id == uid)
    p.connectors[box.id] = evolve(box, source_doc="ICD")
    assert device_library.export_devices(p, [uid])["version"] == 2


def test_a_3_0_reader_refuses_only_the_version_3_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 3.0 tool reads versions 1 and 2 of a device library file (its `VERSION` is 2)."""
    with_rows = device_library.export_devices(*_flat(_project_with_rows(True, False)))
    plain = device_library.export_devices(*_flat(_project_with_rows(False, False)))
    monkeypatch.setattr(device_library, "VERSION", 2)
    assert device_library.check_library(plain)
    with pytest.raises(device_library.DeviceLibraryError, match="version 3; this program reads"):
        device_library.check_library(with_rows)


def _flat(pair):
    p, uid = pair
    return p, [uid]


def test_a_subsystem_file_with_a_layout_is_version_2(monkeypatch: pytest.MonkeyPatch) -> None:
    p, uid = _project_with_rows(False, False)
    plain = subsystem_library.export_subsystem(p, [uid], "Computer", "")
    assert plain["version"] == 1
    p, uid = _project_with_rows(True, False)
    with_rows = subsystem_library.export_subsystem(p, [uid], "Computer", "")
    assert with_rows["version"] == 2 and subsystem_library.check_subsystem(with_rows)
    p.connectors["OBC-J02"] = evolve(p.connectors["OBC-J02"], row_layout=None, source_doc="ICD")
    assert subsystem_library.export_subsystem(p, [uid], "Computer", "")["version"] == 1  # (as 3.0)
    monkeypatch.setattr(subsystem_library, "VERSION", 1)  # a 3.0 reader
    assert subsystem_library.check_subsystem(plain)
    with pytest.raises(subsystem_library.SubsystemError, match="version 2; this program reads"):
        subsystem_library.check_subsystem(with_rows)


def test_the_schemas_hold_the_new_key(tmp_path: Path) -> None:
    from harness_design_studio.core.schemas import schemas

    found = schemas()
    defs = found["connectors"]["$defs"]
    assert "row_layout" in defs["Connector"]["properties"] and "RowLayout" in defs
    assert "row_layout" in found["parts"]["$defs"]["Part"]["properties"]
    rows = defs["RowLayout"]["properties"]["rows"]
    assert (rows["minItems"], rows["maxItems"]) == (1, 64)
    device = found["device-file"]["properties"]["version"]
    assert device["maximum"] == device_library.VERSION >= 3  # 4 since format 5 (D-264)
    assert main(["schema", str(tmp_path / "s")]) == 0
    assert "RowLayout" in (tmp_path / "s" / "connectors.schema.json").read_text(encoding="utf-8")
