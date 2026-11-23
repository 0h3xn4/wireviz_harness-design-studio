# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index,union-attr"
"""REQ-MIGRATE-10: format 5 (D-264, design of 5.0.0 `docs/ait/DESIGN_5.0_FORMAT_5.md` sections 3,
11 and 13, pull request 1).

This tool writes `schema_version` 5. The step from 4 to 5 (`core/io/migrate.py` `_v4_to_v5`, the
parts `V4_TO_V5_PARTS`) writes the number and nothing else: every new key of format 5 (section 3.1:
`length_to` of a cable connector, `depth_mm` of a part, `current_a` of a pin, `at_a` and `at_b` of a
shield group, `checked` of a device) is sparse, nobody has one before format 5, and the keys come
with the code that reads them in the later pull requests. Like the step from 3 to 4 it changes no
hash, so the migration safety net is its whole proof (section 3.4): the format 4 files read as they
are and the format 5 files the step writes give the same model hash, findings, released harnesses
and in-memory export, byte for byte. A format 3, 2 or 1 project goes through every step in one
upgrade. A 4.x tool opens a format 5 project read-only. A device library file is written as version
4 and a subsystem file as version 3 only when they hold a key of format 5
(`device_library.FORMAT5_KEYS`, each key added with its reader; section 3.7). The output-hash baseline
and the numbers snapshot stay *identical* (section 11).
"""

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.cli.main import main
from harness_design_studio.core import device_library, subsystem_library
from harness_design_studio.core.errors import SaveError
from harness_design_studio.core.io import layout, loader, migrate, saver, upgrade
from harness_design_studio.core.io.layout import is_managed, model_hash
from harness_design_studio.core.io.loader import load_project, read_tree
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import SCHEMA_VERSION
from harness_design_studio.core.outputs.build import build_outputs
from harness_design_studio.resources import examples_path
from tests.helpers import FIXTURES
from tests.migration_support import (
    HEAVY,
    SCENARIOS,
    as_format,
    build,
    folder_bytes,
    install_fake_format,
)

JOURNAL = "journal.jsonl"
# The keys of format 5 (design of 5.0.0 section 3.1); the step writes none of them.
NEW_KEYS = frozenset({"length_to", "depth_mm", "current_a", "at_a", "at_b", "checked"})
OLD_FIXTURES = {"v0_project": None, "v1_project": 1, "m1_project": 1}


def managed(root: Path) -> dict[str, bytes]:
    return {k: v for k, v in folder_bytes(root).items() if is_managed(k)}


def keys_of(data: Any) -> set[str]:
    """Every key of a JSON document, at any depth."""
    if isinstance(data, dict):
        return set(data).union(*(keys_of(v) for v in data.values()))
    if isinstance(data, list):
        return set().union(*(keys_of(v) for v in data))
    return set()


def new_keys_in(files: dict[str, bytes]) -> dict[str, set[str]]:
    """The keys of format 5 in the JSON files of a project, by file."""
    found: dict[str, set[str]] = {}
    for rel, data in files.items():
        if rel.endswith(".json") and (hit := keys_of(json.loads(data)) & NEW_KEYS):
            found[rel] = hit
    return found


def as_four(name: str, dest: Path) -> Path:
    """A scenario as a 4.x tool wrote it: a fixture kept in an older format is brought up to this
    tool's format first, then the number is written as 4 (format 4 is format 5 without its keys)."""
    root = build(name, dest)
    if (upgrade.format_of(root) or 0) < SCHEMA_VERSION:
        first = upgrade.upgrade_project(root)
        assert first is not None
        shutil.rmtree(root / first.backup)
    return as_format(root, 4)


# ---- the number ----------------------------------------------------------------------------------------


def test_this_tool_writes_format_5_and_has_a_step_for_every_older_format() -> None:
    assert SCHEMA_VERSION == 5 and migrate.current_version() == 5
    assert sorted(migrate.MIGRATIONS) == [0, 1, 2, 3, 4]
    assert migrate.MIGRATIONS[4] is migrate._v4_to_v5
    assert (migrate._v5_number,) == migrate.V4_TO_V5_PARTS
    assert migrate.MIGRATIONS[3] is migrate._v3_to_v4  # the step before is kept
    assert 4 not in migrate.TAKES_VERSIONS
    assert layout.HASH_SCHEMA_VERSION == 1  # the hash is of the design, never of the format


def test_every_fixture_and_every_shipped_example_is_in_format_5_without_a_new_key() -> None:
    examples = examples_path()
    assert examples is not None
    roots = [p.parent for p in FIXTURES.rglob("project.json")]
    roots += [p.parent for p in (examples / "projects").glob("*/project.json")]
    assert len(roots) >= 10
    for root in sorted(roots):
        doc = json.loads((root / "project.json").read_text(encoding="utf-8"))
        assert doc.get("schema_version") == OLD_FIXTURES.get(root.name, 5), root
        files = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*.json")}
        assert new_keys_in(files) == {}, root


# ---- the step on the files -------------------------------------------------------------------------------


def test_the_step_writes_the_number_and_nothing_else(tmp_path: Path) -> None:
    root = as_four("released", tmp_path / "p")
    files, _broken, _issues = read_tree(root)
    out = migrate.migrate_raw(copy.deepcopy(files), 4)
    assert out["project.json"] == {**files["project.json"], "schema_version": 5}
    assert {rel: data for rel, data in out.items() if rel != "project.json"} == {
        rel: data for rel, data in files.items() if rel != "project.json"
    }
    assert files == read_tree(root)[0]  # the input is not changed
    assert migrate._v4_to_v5(copy.deepcopy(files)) == out
    assert migrate.migrate_raw(copy.deepcopy(out), 5) == out  # nothing to do in format 5


@pytest.mark.parametrize(
    "name", [pytest.param(n, marks=pytest.mark.slow) if n in HEAVY else n for n in SCENARIOS]
)
def test_the_upgrade_from_4_changes_the_number_only_and_passes_every_check(
    name: str, tmp_path: Path
) -> None:
    """Section 3.4: the files of format 4 read as they are and the files of format 5 give the same
    model hash, findings, released harnesses and export (the run-time check of `upgrade`); after
    the step no file has a key of format 5, `project.json` differs in its number only, and every
    other project file is byte-identical (the journal has one more entry)."""
    root = as_four(name, tmp_path / "p")
    before = managed(root)
    had_journal = JOURNAL in before
    plan = upgrade.plan_upgrade(root)  # the dry run
    assert managed(root) == before  # writes nothing
    assert plan is not None and plan.ok, plan.lost
    assert (plan.from_version, plan.to_version) == (4, 5)
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
    assert old_number == 4 and new_number == 5 and old == new
    if had_journal:  # one more line: "migrated from format 4"
        assert after[JOURNAL].startswith(before[JOURNAL])
        assert after[JOURNAL].count(b"\n") == before[JOURNAL].count(b"\n") + 1
        assert b"migrated from format 4" in after[JOURNAL][len(before[JOURNAL]) :]
    assert new_keys_in(after) == {}  # no key of format 5 appears
    record = json.loads((root / done.record).read_bytes())
    assert (record["status"], record["from_version"], record["to_version"]) == ("complete", 4, 5)
    assert done.backup == ".migration-backup-v4"
    assert (root / done.backup / "project.json").read_bytes() == before["project.json"]


@pytest.mark.parametrize(
    "name", ["mini3", "example-first-steps", pytest.param("released", marks=pytest.mark.slow)]
)
def test_the_export_with_and_without_the_harness_plans_is_the_same_after_the_step(
    name: str, tmp_path: Path
) -> None:
    """Section 3.4, item 3: the export of a project read as format 4 (in memory) and after the
    upgrade is the same, byte for byte, with and without the harness plans."""
    root = as_four(name, tmp_path / "p")
    old = load_project(root, migrate=False).project  # format 4 read as it is
    assert old.meta.schema_version == 4
    want = {plan: build_outputs(old, harness_plan=plan).files for plan in (False, True)}
    in_memory = load_project(root).project  # format 4 read as format 5 in memory
    assert in_memory.migrated_from == 4
    want_hash = model_hash(old)
    assert model_hash(in_memory) == want_hash
    assert build_outputs(in_memory, harness_plan=True).files == want[True]
    upgrade.upgrade_project(root)
    new = load_project(root).project
    assert new.meta.schema_version == 5 and new.migrated_from is None
    assert model_hash(new) == want_hash  # the model hash rule: the number is not in it
    for plan in (False, True):
        assert build_outputs(new, harness_plan=plan).files == want[plan]


@pytest.mark.slow
def test_the_step_run_twice_writes_the_same_files(tmp_path: Path) -> None:
    one, two = as_four("released", tmp_path / "a"), as_four("released", tmp_path / "b")
    for root in (one, two):
        assert upgrade.upgrade_project(root) is not None
    assert managed(one) == managed(two)
    assert upgrade.upgrade_project(one) is None  # up to date


def test_migrate_dry_run_shows_the_one_change_and_writes_nothing(tmp_path: Path, capsys) -> None:
    root = as_four("mini3", tmp_path / "p")
    before = folder_bytes(root)
    assert main(["migrate", str(root), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Project format 4; this tool writes format 5." in out
    assert "changed  project.json" in out and "(equal)" in out and "identical" in out
    assert "Nothing is lost. Nothing was written." in out
    assert main(["migrate", str(root), "--dry-run", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert (doc["from_version"], doc["to_version"], doc["ok"]) == (4, 5, True)
    assert doc["files"] == [{"file": "project.json", "change": "changed"}]
    assert doc["model_hash_before"] == doc["model_hash_after"]
    assert folder_bytes(root) == before
    assert main(["migrate", str(root)]) == 0
    out = capsys.readouterr().out
    assert "Format 4 to 5." in out and "same model hash" in out
    assert "Record: .migration-backup-v4/MIGRATION.json." in out
    assert main(["migrate", str(root)]) == 0  # up to date: nothing more to do
    assert json.loads((root / "project.json").read_bytes())["schema_version"] == 5


# ---- formats 3, 2 and 1 in one upgrade -----------------------------------------------------------------


@pytest.mark.parametrize("version", [3, pytest.param(2, marks=pytest.mark.slow), 1])
def test_an_older_project_goes_through_every_step_in_one_upgrade(
    version: int, tmp_path: Path, capsys
) -> None:
    root = build("released", tmp_path / "p")
    want = managed(root)
    as_format(root, version)
    assert main(["migrate", str(root), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"Project format {version}; this tool writes format 5." in out
    if version < 3:  # the step from 2 to 3 maps the revisions
        assert "revision B → version 2.0.0" in out and "Only the versions change" in out
    assert main(["migrate", str(root)]) == 0
    assert f"Format {version} to 5." in capsys.readouterr().out
    after = managed(root)
    assert {k: v for k, v in after.items() if not k.startswith("journal")} == {
        k: v for k, v in want.items() if not k.startswith("journal")
    }  # the files of format 5 as this tool writes them, byte for byte
    assert new_keys_in(after) == {}
    record = json.loads((root / f".migration-backup-v{version}" / upgrade.RECORD_NAME).read_bytes())
    assert (record["from_version"], record["to_version"]) == (version, 5)


def test_set_version_is_still_taken_on_the_way_from_2_to_5(tmp_path: Path, capsys) -> None:
    from harness_design_studio.core.io import canonical

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


def test_a_reader_of_format_4_opens_a_format_5_project_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """What a 4.x tool does with a format 5 project (section 3.5), simulated by the loader's own
    version check (D-226): it is newer than the reader, so it is opened read-only, `validate` warns
    `newer_version`, `generate` and `export` refuse, and nothing is written."""
    root = build("mini3", tmp_path / "p")
    before = managed(root)
    for module in (migrate, loader, saver):
        monkeypatch.setattr(module, "SCHEMA_VERSION", 4)
    r = load_project(root)
    assert r.project.read_only
    (warning,) = [i for i in r.issues if i.code == "newer_version"]
    assert "format 5; this tool understands up to 4" in warning.message
    with pytest.raises(SaveError):
        save_project(r.project, root)
    assert main(["validate", str(root), "--json"]) in (0, 1)
    assert "newer_version" in capsys.readouterr().out
    assert main(["generate", str(root)]) != 0
    assert main(["export", str(root)]) != 0
    capsys.readouterr()
    assert managed(root) == before


def test_a_project_one_format_ahead_of_this_tool_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same rule one step on, with the fake format of the tests (`install_fake_format`): this
    tool writes format 5 and opens a format 6 project read-only; `migrate` does not go back."""
    root = build("mini3", tmp_path / "p")
    install_fake_format(monkeypatch)
    upgrade.upgrade_project(root)  # written as the fake format 6 by the fake tool
    assert json.loads((root / "project.json").read_bytes())["schema_version"] == 6
    monkeypatch.undo()
    before = managed(root)
    r = load_project(root)
    assert r.project.read_only and any(i.code == "newer_version" for i in r.issues)
    assert main(["migrate", str(root)]) != 0
    assert managed(root) == before


def test_a_format_4_project_is_written_only_by_migrate(tmp_path: Path) -> None:
    root = as_four("mini3", tmp_path / "p")
    r = load_project(root)
    assert r.project.migrated_from == 4 and not r.has_errors
    assert any(i.code == "migrated" for i in r.issues)
    with pytest.raises(SaveError, match="migrate"):
        save_project(r.project, root)
    out = tmp_path / "copy"
    save_project(r.project, out)  # a new folder gets the current format
    assert json.loads((out / "project.json").read_bytes())["schema_version"] == 5


def test_check_of_a_format_4_project_finds_nothing_to_rewrite(tmp_path: Path, capsys) -> None:
    root = as_four("released", tmp_path / "p")
    assert main(["check", str(root), "--json"]) in (0, 1)
    doc = json.loads(capsys.readouterr().out)
    assert [i for i in doc["issues"] if i["code"] == "not_canonical"] == []


# ---- the device library file and the subsystem file (section 3.7) ----------------------------------------


def _device_content(extra_pin_key: str | None = None) -> dict[str, Any]:
    from harness_design_studio.core.samples import mini3

    p = mini3()
    uid = p.connectors["OBC-J02"].unit_id
    assert uid is not None
    content = device_library.export_devices(p, [uid])
    if extra_pin_key is not None:
        pins = content["devices"][0]["connectors"][0]["pins"]
        pins[0] = {**pins[0], extra_pin_key: 1.5}
    return content


def test_only_the_keys_that_came_make_a_file_version_4() -> None:
    """Pull request 1 makes the rule; the keys come with their readers (pull requests 2, 3, 6):
    `depth_mm` of a part with pull request 2, `current_a` of a pin with pull request 3."""
    assert frozenset({"depth_mm", "current_a"}) == device_library.FORMAT5_KEYS
    assert device_library.VERSION == 4 and device_library.FORMAT4_VERSION == 3
    assert subsystem_library.VERSION == 3 and subsystem_library.FORMAT4_VERSION == 2
    assert device_library.content_version(_device_content()) == 1
    assert device_library.content_version(_device_content("current_a")) == 4
    assert subsystem_library.content_version(_device_content("current_a")) == 3
    assert device_library.content_version(_device_content("checked")) == 1  # not a key yet


@pytest.mark.parametrize("where", ["unit", "connector", "pin", "part"])
def test_a_key_of_format_5_makes_the_device_file_version_4(
    where: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rule of section 3.7, with a key standing in for the keys to come: version 4 wins over a
    row layout (3) and a field of format 3 (2), wherever the key is."""
    monkeypatch.setattr(device_library, "FORMAT5_KEYS", frozenset({"stand_in"}))
    content = _device_content()
    device = content["devices"][0]
    connector = device["connectors"][0]
    connector["row_layout"] = {"rows": [[connector["pins"][0]["id"]]]}
    assert device_library.content_version(content) == 3
    assert subsystem_library.content_version(content) == 2
    if where == "unit":
        device["unit"]["stand_in"] = 1
    elif where == "connector":
        connector["stand_in"] = 1
    elif where == "pin":
        connector["pins"][0]["stand_in"] = 1
    else:
        content["parts"][0] = {**content["parts"][0], "stand_in": 1}
    assert device_library.content_version(content) == 4
    assert subsystem_library.content_version(content) == 3


def test_a_4_x_reader_refuses_only_a_version_4_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 4.x tool reads versions 1 to 3 of a device library file (its `VERSION` is 3) and versions
    1 and 2 of a subsystem file (section 3.5)."""
    plain = _device_content()
    future = {**plain, "version": 4}
    assert device_library.check_library(future)  # this tool reads version 4
    monkeypatch.setattr(device_library, "VERSION", 3)
    assert device_library.check_library(plain)
    with pytest.raises(device_library.DeviceLibraryError, match="version 4; this program reads"):
        device_library.check_library(future)


def test_the_schema_of_the_device_file_takes_version_4(tmp_path: Path) -> None:
    from harness_design_studio.core.schemas import schemas

    version = schemas()["device-file"]["properties"]["version"]
    assert (version["minimum"], version["maximum"]) == (1, 4)
    assert main(["schema", str(tmp_path / "s")]) == 0


# ---- the written files (section 11) ------------------------------------------------------------------------


def test_the_output_hashes_and_the_numbers_snapshot_are_identical(capsys) -> None:
    """Section 11: no written file of a project without data of format 5 changes, so the stored
    hashes of every output of the examples and the numbers snapshot say *identical*."""
    from tools import numbers_snapshot, output_hashes

    root = Path(__file__).resolve().parents[1]
    assert output_hashes.main(["--check", str(root / "docs/ui/OUTPUT_HASHES_BASELINE.json")]) == 0
    assert capsys.readouterr().out.strip().endswith("identical")
    snap = str(root / "tests/fixtures/numbers/snapshot.json")
    assert numbers_snapshot.main(["--check", snap]) == 0
    assert capsys.readouterr().out.strip().endswith("identical")
