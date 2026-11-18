# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index,union-attr"
"""REQ-MIGRATE-08: format 3 (D-242, design of 3.0.0 `docs/ait/DESIGN_3.0_HARNESS_PLAN.md`
sections 4, 5.5 and 5.6, pull request 1).

This tool writes `schema_version` 3. The step from 2 to 3 (`core/io/migrate.py` `_v2_to_v3`, the
parts `V2_TO_V3_PARTS`) writes the number, maps every revision letter to its version (`A` is
`1.0.0`, `B` is `2.0.0`, a version is kept, anything else is given by a person with
`migrate --set-version`) and renames the keys (`revision` to `version`, the change-log kind
`new_revision` to `new_version`, the title block field `revision` to `version`); each baseline is
named by its new ID. Every new field of format 3 is sparse and absent after the step. Unlike the
steps before it, it changes the model hash once; the migration safety net proves on the files
that nothing else changes (section 5.6): with every version read as its place in its harness's
order, the same model hash, findings and consistency of the released harnesses, and every version
the mapping of its revision. A 2.x tool opens a format 3 project read-only (the rule of D-226).
"""

import copy
import json
import re
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from harness_design_studio.cli.main import main
from harness_design_studio.core import configcheck, device_library
from harness_design_studio.core.errors import SaveError
from harness_design_studio.core.generation_status import generation_status
from harness_design_studio.core.io import canonical, layout, loader, migrate, saver, upgrade
from harness_design_studio.core.io.loader import load_project, read_tree
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import (
    SCHEMA_VERSION,
    ConfigFile,
    ContactLine,
    DocumentInfo,
    Harness,
    Part,
    Pin,
    PlanDocument,
    ProjectMeta,
    evolve,
)
from harness_design_studio.core.model.base import Version, WebLink
from harness_design_studio.core.model.config import CONFIG_NAMES, default_configs
from harness_design_studio.core.model.physical import Connector
from harness_design_studio.resources import examples_path
from tests.helpers import FIXTURES
from tests.migration_support import SCENARIOS, as_format, build, folder_bytes, full_export

# kept in an older format on purpose: format 0; 1.17.1 with a loose end; written by 0.0.1 (M1)
OLD_FIXTURES = {"v0_project": None, "v1_project": 1, "m1_project": 1}
LIGHT = ["mini3", "sat15", "fixture-mini3", "custom_device", "links", "diagram-marks", "released"]


def project_roots() -> list[Path]:
    examples = examples_path()
    assert examples is not None
    roots = [p.parent for p in FIXTURES.rglob("project.json")]
    roots += [p.parent for p in (examples / "projects").glob("*/project.json")]
    return sorted(roots)


def managed(root: Path) -> dict[str, bytes]:
    return {k: v for k, v in folder_bytes(root).items() if layout.is_managed(k)}


def as_two(name: str, dest: Path) -> Path:
    """A scenario of `tests/migration_support.py` as a 2.x tool wrote it."""
    return as_format(build(name, dest), 2)


def _harness_file(root: Path, hid: str = "W001") -> Path:
    return root / "physical" / "harnesses" / f"{hid}.json"


def _set_revision(root: Path, value: str, hid: str = "W001") -> None:
    path = _harness_file(root, hid)
    doc = json.loads(path.read_bytes())
    doc["revision"] = value
    path.write_bytes(canonical.dumps(doc))


# ---- the number ----------------------------------------------------------------------------------------


def test_this_tool_writes_format_3_and_has_a_step_for_every_older_format() -> None:
    assert SCHEMA_VERSION == 3 and migrate.current_version() == 3
    assert sorted(migrate.MIGRATIONS) == [0, 1, 2]
    assert migrate.MIGRATIONS[2] is migrate._v2_to_v3
    assert (
        migrate._v3_number,
        migrate._v3_versions,
        migrate._v3_titleblock,
    ) == migrate.V2_TO_V3_PARTS
    assert layout.HASH_SCHEMA_VERSION == 1  # the hash is of the design, never of the format


def test_every_fixture_and_every_shipped_example_is_in_format_3() -> None:
    roots = project_roots()
    assert len(roots) >= 10
    for root in roots:
        doc = json.loads((root / "project.json").read_text(encoding="utf-8"))
        assert doc.get("schema_version") == OLD_FIXTURES.get(root.name, SCHEMA_VERSION), root
        if OLD_FIXTURES.get(root.name, SCHEMA_VERSION) == SCHEMA_VERSION:
            for path in (root / "physical" / "harnesses").glob("*.json"):
                harness = json.loads(path.read_bytes())
                assert "revision" not in harness and "version" in harness, path


# ---- the step on the files -------------------------------------------------------------------------------


def test_the_step_maps_the_revisions_renames_the_keys_and_changes_nothing_else(
    tmp_path: Path,
) -> None:
    root = as_two("released", tmp_path / "p")
    files, _broken, _issues = read_tree(root)
    out = migrate.migrate_raw(copy.deepcopy(files), 2)
    assert out["project.json"] == {**files["project.json"], "schema_version": 3}
    letters = {rel: d["revision"] for rel, d in files.items() if rel.startswith("physical/harn")}
    assert set(letters.values()) == {"A", "B"}
    for rel, letter in letters.items():
        new = out[rel]
        assert "revision" not in new and new["version"] == {"A": "1.0.0", "B": "2.0.0"}[letter]
        assert {k: v for k, v in new.items() if k != "version"} == {
            k: v for k, v in files[rel].items() if k != "revision"
        }
    kinds = [e["kind"] for e in out["changelog.json"]["changelog"]]
    assert "new_version" in kinds and "new_revision" not in kinds
    assert all("revision" not in e for e in out["changelog.json"]["changelog"])
    old_baselines = sorted(r for r in files if r.startswith("baselines/"))
    new_baselines = sorted(r for r in out if r.startswith("baselines/"))
    assert [r.rsplit(".", 2)[0] for r in old_baselines] != new_baselines  # renamed
    assert all(r.endswith((".1.0.0.json", ".2.0.0.json")) for r in new_baselines)
    for rel in new_baselines:
        b = out[rel]
        assert b["id"] == f"{b['harness_id']}.{b['version']}" and "revision" not in b
        assert all("revision" not in h for h in b["snapshot"]["harnesses"])
        assert "version" in b["snapshot"]["config"]["titleblock"]["fields"]
    assert "version" in out["config/titleblock.json"]["values"]["fields"]
    assert "revision" not in out["config/titleblock.json"]["values"]["fields"]
    untouched = {r for r in files if r in out and out[r] == files[r]}
    changed = (
        {"project.json", "changelog.json", "config/titleblock.json"}
        | set(letters)
        | set(old_baselines)
    )
    assert untouched == set(files) - changed
    assert files == read_tree(root)[0]  # the input is not changed


def test_the_step_run_twice_writes_the_same_files(tmp_path: Path) -> None:
    one, two = as_two("released", tmp_path / "a"), as_two("released", tmp_path / "b")
    for root in (one, two):
        assert upgrade.upgrade_project(root) is not None
    assert managed(one) == managed(two)


def test_a_title_block_without_the_field_is_not_touched() -> None:
    files = {
        "project.json": {"schema_version": 2},
        "config/titleblock.json": {"name": "titleblock", "values": {"fields": ["project"]}},
    }
    out = migrate.migrate_raw(copy.deepcopy(files), 2)
    assert out["config/titleblock.json"] == files["config/titleblock.json"]


def test_a_new_field_is_absent_after_the_step_and_no_config_file_is_made(tmp_path: Path) -> None:
    root = as_two("sat15", tmp_path / "p")
    upgrade.upgrade_project(root)
    text = b"".join(managed(root).values())
    for key in (b'"level"', b'"source_doc"', b'"source_link"', b'"link"', b'"document"'):
        assert key not in text
    assert b"signal_ground" not in text
    assert not (root / "config" / "harness_plan.json").exists()
    assert set(json.loads((root / "project.json").read_bytes())) == {
        "description", "name", "schema_version", "tool_version",
    }  # fmt: skip


def test_the_upgrade_leaves_the_harness_plans_current(tmp_path: Path) -> None:
    """The title block field is renamed, but generation does not read the title block: the hash of
    its inputs is what it was, so a generated project is not *out of date* after the upgrade."""
    root = as_two("example-flatsat", tmp_path / "p")
    stored = json.loads((root / "generated" / "generation.json").read_bytes())["input_hash"]
    upgrade.upgrade_project(root)
    p = load_project(root).project
    assert p.generation is not None and p.generation.input_hash == stored
    assert generation_status(p) == "current"


# ---- the proof (section 5.6) ------------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_the_proof_holds_for_every_fixture_example_and_scenario(name: str, tmp_path: Path) -> None:
    root = build(name, tmp_path / "p")
    if (upgrade.format_of(root) or 0) >= 3:
        as_format(root, 2)
    before = folder_bytes(root)
    plan = upgrade.plan_upgrade(root, exports=False)
    assert folder_bytes(root) == before  # the dry run writes nothing
    assert plan is not None and plan.ok, plan.lost
    assert plan.nothing_but_versions is True and plan.versions_mapped is True


def test_the_upgrade_of_a_release_history_maps_each_letter_and_writes_the_record(
    tmp_path: Path, capsys
) -> None:
    root = as_two("released", tmp_path / "p")
    old = {
        rel: json.loads(data) for rel, data in managed(root).items() if rel.startswith("baselines/")
    }
    assert main(["migrate", str(root), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "revision B → version 2.0.0" in out and "Only the versions change" in out
    assert main(["migrate", str(root)]) == 0
    out = capsys.readouterr().out
    assert "Format 2 to 3." in out and "only the harness revisions changed" in out
    p = load_project(root).project
    released = [b for b in p.baselines.values()]
    assert {b.version for b in released} == {"1.0.0"} and len(old) == len(released)
    revised = [h for h in p.harnesses.values() if h.version == "2.0.0"]
    assert len(revised) == 1 and revised[0].status == "draft"
    for b in released:
        was = old[f"baselines/{b.harness_id}/{b.harness_id}.A.json"]
        assert b.content_hash == was["content_hash"]  # a record of the day it was released
    record = json.loads((root / ".migration-backup-v2" / upgrade.RECORD_NAME).read_bytes())
    assert record["proof"] == {"nothing_but_versions": True, "versions_mapped": True}
    assert any(" revision B → version 2.0.0" in line for line in record["versions"])
    assert not [i for i in load_project(root).issues if i.severity == "error"]


def _with_extra_part(part):
    return lambda monkeypatch: monkeypatch.setattr(
        migrate, "V2_TO_V3_PARTS", (*migrate.V2_TO_V3_PARTS, part)
    )


def _rename_project(tree):
    tree["project.json"]["name"] += " (changed)"
    return tree


def _wrong_version(tree):
    for rel, data in tree.items():
        if rel.startswith("physical/harnesses/") and data.get("version") == "2.0.0":
            data["version"] = "3.0.0"
    return tree


@pytest.mark.parametrize(
    ("part", "word"),
    [
        (_rename_project, "changes more than the versions"),
        (_wrong_version, "not the mapping"),
    ],
)
def test_a_step_that_changes_more_than_the_versions_is_refused(
    part, word: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = as_two("released", tmp_path / "p")
    files = folder_bytes(root)
    _with_extra_part(part)(monkeypatch)
    plan = upgrade.plan_upgrade(root, exports=False)
    assert plan is not None and not plan.ok and any(word in x for x in plan.lost), plan.lost
    with pytest.raises(upgrade.UpgradeError):
        upgrade.upgrade_project(root)
    assert folder_bytes(root) == files


# ---- revisions that are not letters ---------------------------------------------------------------------


@pytest.mark.parametrize("value", ["b", "A1", "-"])
def test_a_revision_that_is_not_a_letter_is_refused_and_taken_with_set_version(
    value: str, tmp_path: Path, capsys
) -> None:
    root = as_two("mini3", tmp_path / "p")
    _set_revision(root, value)
    files = managed(root)
    assert main(["migrate", str(root), "--dry-run"]) == 1
    out = capsys.readouterr().out
    assert f"revision '{value}' is not a letter" in out
    assert f"--set-version W001:{value}=VERSION" in out
    assert main(["migrate", str(root)]) == 1
    assert managed(root) == files
    assert main(["migrate", str(root), "--set-version", f"W001:{value}=1.1.0"]) == 0
    assert load_project(root).project.harnesses["W001"].version == "1.1.0"


def test_the_loader_of_an_unmapped_revision_sets_the_harness_aside_and_says_why(
    tmp_path: Path,
) -> None:
    root = as_two("mini3", tmp_path / "p")
    _set_revision(root, "A1")
    r = load_project(root)
    assert "W001" not in r.project.harnesses and r.project.recovered


def test_two_revisions_that_give_one_version_are_refused(tmp_path: Path, capsys) -> None:
    root = as_two("released", tmp_path / "p")
    hid = next(
        json.loads(p.read_bytes())["id"]
        for p in (root / "physical" / "harnesses").glob("*.json")
        if json.loads(p.read_bytes())["revision"] == "B"
    )
    assert main(["migrate", str(root), "--dry-run", "--set-version", f"{hid}:B=1.0.0"]) == 1
    assert "would both become version 1.0.0" in capsys.readouterr().out


def test_a_given_version_must_be_a_version(tmp_path: Path, capsys) -> None:
    root = as_two("mini3", tmp_path / "p")
    _set_revision(root, "A1")
    assert main(["migrate", str(root), "--dry-run", "--set-version", "W001:A1=v1.1"]) == 1
    assert "'v1.1' is not a version" in capsys.readouterr().out
    assert main(["migrate", str(root), "--set-version", "W001-A1"]) == 2
    assert "HARNESS:OLD=VERSION" in capsys.readouterr().err


def test_releases_mapped_out_of_the_order_of_the_change_log_are_refused() -> None:
    files = {
        "project.json": {"schema_version": 2},
        "physical/harnesses/W001.json": {"id": "W001", "revision": "X1"},
        "changelog.json": {
            "changelog": [
                {"id": "C0001", "harness_id": "W001", "revision": "R1", "kind": "release"},
                {"id": "C0002", "harness_id": "W001", "revision": "R2", "kind": "release"},
            ]
        },
    }
    given = {"W001": {"R1": "2.0.0", "R2": "1.0.0", "X1": "3.0.0"}}
    problems = migrate.version_problems(files, given)
    assert any("another order than its change log" in p for p in problems), problems
    assert not migrate.version_problems(files, {"W001": {"R1": "1.0.0", "R2": "2.0.0", "X1": "3.0.0"}})  # fmt: skip


def test_a_baseline_id_that_would_be_too_long_is_refused() -> None:
    hid = "H" * 60
    files = {"project.json": {}, f"physical/harnesses/{hid}.json": {"id": hid, "revision": "A"}}
    assert any("longer than 64" in p for p in migrate.version_problems(files))


# ---- older and newer tools ---------------------------------------------------------------------------------


def test_a_reader_of_format_2_opens_a_format_3_project_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a 2.x tool does with a format 3 project, simulated by the loader's own version check
    (D-226): it is newer than the reader, so it is opened read-only and nothing is saved over it."""
    root = build("mini3", tmp_path / "p")
    before = managed(root)
    for module in (loader, saver):
        monkeypatch.setattr(module, "SCHEMA_VERSION", 2)
    r = load_project(root)
    assert r.project.read_only and any(i.code == "newer_version" for i in r.issues)
    with pytest.raises(SaveError):
        save_project(r.project, root)
    assert managed(root) == before


def test_a_format_2_project_is_written_only_by_migrate(tmp_path: Path) -> None:
    root = as_two("mini3", tmp_path / "p")
    r = load_project(root)
    assert r.project.migrated_from == 2 and r.project.harnesses["W001"].version == "1.0.0"
    with pytest.raises(SaveError, match="migrate"):
        save_project(r.project, root)


def test_check_of_a_format_2_project_finds_nothing_to_rewrite(tmp_path: Path, capsys) -> None:
    root = as_two("released", tmp_path / "p")
    assert main(["check", str(root), "--json"]) in (0, 1)
    doc = json.loads(capsys.readouterr().out)
    assert [i for i in doc["issues"] if i["code"] == "not_canonical"] == []


# ---- the new fields ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["01.0.0", "v1.0.0", "1.0", "1.0.0.0", "10000.0.0", "A", ""])
def test_a_version_is_major_minor_patch(text: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Version).validate_python(text)
    assert TypeAdapter(Version).validate_python("1.10.2") == "1.10.2"


@pytest.mark.parametrize(
    "text",
    [
        "file:///home/x/icd.pdf",
        "javascript:alert(1)",
        "/srv/share/icd.pdf",
        "\\\\server\\share\\icd.pdf",
        "https://example.com/a b",
        "https://",
        "ftp://example.com/x",
        "https://example.com/" + "x" * 2000,
    ],
)
def test_a_web_link_is_http_or_https_only(text: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(WebLink).validate_python(text)


def test_a_web_link_is_kept_as_written() -> None:
    for text in ("https://example.com/datasheet.pdf?x=1#p2", "http://intranet/icd"):
        assert TypeAdapter(WebLink).validate_python(text) == text


def test_a_new_harness_starts_at_1_0_0() -> None:
    from harness_design_studio.core.samples import mini3

    assert Harness(id="W001", name="x").version == "1.0.0"
    assert {h.version for h in mini3().harnesses.values()} == {"1.0.0"}  # generated


def test_each_new_field_round_trips_and_is_left_out_while_default(tmp_path: Path) -> None:
    from harness_design_studio.core.commands import Put, apply_ops

    root = build("mini3", tmp_path / "p")
    p = load_project(root).project
    plain = managed(root)
    box = next(c for c in p.connectors.values() if c.pins)
    pin = box.pins[0]
    new_box = evolve(
        box,
        source_doc="ICD-OBC",
        source_version="4.2",
        source_link="https://example.com/icd",
        pins=[evolve(pin, level="RS422-3V3", role="signal_ground"), *box.pins[1:]],
    )
    part = next(iter(p.parts.values()))
    apply_ops(
        p,
        [
            Put("connectors", new_box),
            Put("parts", evolve(part, link="https://example.com/part")),
        ],
    )
    p.meta = evolve(
        p.meta,
        document=DocumentInfo(
            system="SYS1",
            company="Example Ltd",
            contact=[ContactLine(label="Phone", value="+00 0")],
            plans={"W001": PlanDocument(number="DOC-1", release="R1")},
        ),
    )
    save_project(p, root)
    q = load_project(root).project
    assert q.connectors[box.id] == new_box and q.parts[part.id].link == "https://example.com/part"
    assert q.meta.document == p.meta.document
    meta = json.loads((root / "project.json").read_bytes())
    assert meta["document"] == {
        "company": "Example Ltd",
        "contact": [{"label": "Phone", "value": "+00 0"}],
        "plans": {"W001": {"number": "DOC-1", "release": "R1"}},
        "system": "SYS1",
    }  # sparse: the empty texts are left out
    # back to the defaults: the files are what they were
    apply_ops(p, [Put("connectors", box), Put("parts", part)])
    p.meta = evolve(p.meta, document=None)
    save_project(p, root)
    assert managed(root) == plain


def test_the_sparse_models_leave_out_their_empty_parts() -> None:
    assert ProjectMeta().model_dump() == {
        "name": "Untitled project", "description": "", "schema_version": 3, "tool_version": "",
    }  # fmt: skip
    assert DocumentInfo().model_dump() == {} and PlanDocument().model_dump() == {}
    assert "level" not in Pin(id="1").model_dump()
    assert "link" not in Part(id="P", category="wire").model_dump()
    c = Connector(id="J1", name="J1", role="box", part_id="P")
    assert not {"source_doc", "source_version", "source_link"} & set(c.model_dump())
    with pytest.raises(ValidationError):
        DocumentInfo(contact=[ContactLine(label=f"L{n}") for n in range(9)])


def test_the_harness_plan_config_is_optional_and_checked() -> None:
    from harness_design_studio.core.samples import mini3

    assert "harness_plan" in CONFIG_NAMES and "harness_plan" not in default_configs()
    p = mini3()
    assert not configcheck.validate_harness_plan(p)
    p.config["harness_plan"] = ConfigFile(
        name="harness_plan",
        placeholder=False,
        values={
            "colour_rule": "pin_code",
            "colour_codes": [
                {"name": "Pigtail", "parts": ["P1"], "pins": {"1": "BK"}, "example": True}
            ],  # fmt: skip
            "notes": ["Labels at both ends."],
        },
    )
    assert not configcheck.validate_harness_plan(p)
    for values, word in (
        ({"colour_rule": "rainbow"}, "colour_rule"),
        ({"colour_codes": [{"name": "A", "pins": {"1": 2}}]}, "pins"),
        ({"colour_codes": [{"name": "A"}, {"name": "A"}]}, "more than once"),
        ({"notes": "one line"}, "notes"),
        ({"surprise": 1}, "surprise"),
    ):
        p.config["harness_plan"] = ConfigFile(name="harness_plan", placeholder=False, values=values)
        found = configcheck.validate_harness_plan(p)
        assert found and word in found[0].message, (values, found)


def test_the_title_block_field_is_version() -> None:
    assert "version" in configcheck.TITLEBLOCK_FIELDS
    assert "revision" not in configcheck.TITLEBLOCK_FIELDS
    assert "version" in default_configs()["titleblock"].values["fields"]


# ---- the device library file ---------------------------------------------------------------------------


def test_a_device_file_stays_version_1_until_a_device_uses_a_field_of_format_3() -> None:
    from harness_design_studio.core.samples import mini3

    p = mini3()
    uid = sorted(p.units)[0]
    plain = device_library.export_devices(p, [uid])
    assert plain["version"] == 1
    box = next(c for c in p.connectors.values() if c.unit_id == uid and c.pins)
    for change in (
        {"pins": [evolve(box.pins[0], level="TTL-5V"), *box.pins[1:]]},
        {"pins": [evolve(box.pins[0], role="signal_ground"), *box.pins[1:]]},
        {"source_doc": "ICD"},
        {"source_link": "https://example.com/icd"},
    ):
        q = mini3()
        q.connectors[box.id] = evolve(box, **change)
        content = device_library.export_devices(q, [uid])
        assert content["version"] == 2, change
        assert device_library.check_library(content)  # this program reads it
    q = mini3()
    pid = box.part_id
    q.parts[pid] = evolve(q.parts[pid], link="https://example.com/p")
    assert device_library.export_devices(q, [uid])["version"] == 2
    future = {**plain, "version": 3}
    with pytest.raises(device_library.DeviceLibraryError, match="newer program"):
        device_library.check_library(future)


def test_the_shipped_examples_are_format_3_with_versions() -> None:
    examples = examples_path()
    assert examples is not None
    p = load_project(examples / "projects" / "flatsat").project
    assert p.meta.schema_version == 3 and p.migrated_from is None
    assert {h.version for h in p.harnesses.values()} == {"1.0.0"}
    assert generation_status(p) == "current"


def test_an_export_is_the_same_before_and_after_a_round_trip_through_format_2(
    tmp_path: Path,
) -> None:
    root = build("released", tmp_path / "p")
    want = full_export(root)
    as_format(root, 2)
    assert full_export(root) == want  # read in memory through the step
    upgrade.upgrade_project(root)
    assert full_export(root) == want


# ---- the word guard (section 5.6) ----------------------------------------------------------------------

# The places that may still say *revision*: the key of `export.json` that Q29 keeps beside `version`
# through 3.0.x, and the sentences that name the word of 2.x (the migration, the older names).
EXPORT_KEY = b'"revision": '
ALLOWED_SOURCE = {
    "core/io/migrate.py",  # the step from 2 to 3 reads the old key and names it
    "core/io/upgrade.py",  # its proof and its words: "revision B → version 2.0.0"
    "core/vcs/versions.py",  # the mapping of an old letter
    "core/journal.py",  # the reason of the migration entry names the mapping
    "core/generation_status.py",  # the title block field under its old name
    "core/outputs/exports.py",  # OLD_VERSION_KEY (Q29)
    "core/outputs/verify.py",  # checks that `revision` equals `version` in export.json
    "core/extensions/fields.py",  # `harness.revision`, the older name (Q29)
    "core/commands.py",  # History.revision, the undo counter, never shown
    "cli/main.py",  # migrate --set-version and its words
    "cli/changes.py",  # `revise`, the older name of new-version, and the log key of Q29
}
ALLOWED_HELP = (
    "harness revision",  # migrate --set-version: the old revision it maps
    "`revise` is the older name",
    "older name of `new-version`",
)


def _export_texts(project) -> dict[str, str]:
    import io
    import zipfile

    from harness_design_studio.core.outputs.build import build_outputs

    out: dict[str, str] = {}
    for rel, data in build_outputs(project, drawings=True).files.items():
        if rel.endswith(".xlsx"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for n in z.namelist():
                    out[f"{rel}:{n}"] = z.read(n).decode("utf-8", "replace")
        else:
            if rel.endswith("export.json"):
                data = data.replace(EXPORT_KEY, b'"version_q29": ')
            out[rel] = data.decode("latin-1")
    return out


@pytest.mark.parametrize("name", ["example-first-steps", "example-flatsat", "released"])
def test_no_written_file_says_revision(name: str, tmp_path: Path) -> None:
    from harness_design_studio.core.generate.engine import generate_project

    root = build(name, tmp_path / "p")
    p = load_project(root).project
    if not p.harnesses:
        generate_project(p)
    data = b"".join(v for k, v in managed(root).items() if not k.startswith("journal"))
    assert b"revision" not in data.lower()  # the data hold no such word: a match is the tool's
    texts = _export_texts(p)
    assert "system/version_report.md" in texts and "system/revision" + "_report.md" not in texts
    found = sorted(rel for rel, text in texts.items() if "revision" in text.lower())
    assert found == [], found
    doc = json.loads(build_outputs_json(p))
    assert all(h["version"] == h["revision"] for h in doc["harnesses"])  # Q29


def build_outputs_json(project) -> bytes:
    from harness_design_studio.core.outputs.build import build_outputs

    return build_outputs(project, drawings=False).files["system/export.json"]


def test_no_help_text_says_revision_but_the_older_names() -> None:
    from harness_design_studio.cli.main import build_parser

    parser = build_parser()
    sub = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
    texts = {"": parser.format_help()}
    texts.update({name: p.format_help() for name, p in sub.choices.items()})
    for name, text in texts.items():
        flat = " ".join(text.split())
        for allowed in ALLOWED_HELP:
            flat = flat.replace(allowed, "")
        if name == "revise":
            continue  # the older name itself
        assert "revision" not in flat.lower().replace("revise", ""), (name, flat)


def test_no_message_of_the_core_says_revision() -> None:
    """Every text in the source of `core/` and `cli/` (string literals that are not docstrings), so
    that a message built from parts is found too; the places that name the word of 2.x are
    listed in `ALLOWED_SOURCE`."""
    import ast

    import harness_design_studio

    base = Path(harness_design_studio.__file__).parent
    found = []
    for path in sorted([*(base / "core").rglob("*.py"), *(base / "cli").rglob("*.py")]):
        rel = path.relative_to(base).as_posix()
        if rel in ALLOWED_SOURCE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = {
            id(n.body[0].value)
            for n in ast.walk(tree)
            if isinstance(n, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and n.body
            and isinstance(n.body[0], ast.Expr)
            and isinstance(n.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docs
                and not node.value.isidentifier()  # a name in `__all__`, not a message
                and "revision" in node.value.lower()
            ):
                found.append(f"{rel}:{node.lineno}: {node.value[:60]}")
    assert found == []


# The texts of the screen that may still name the word of 2.x (pull request R2): the upgrade question
# explains the mapping of the old revisions to versions.
ALLOWED_STRINGS = {"UPGRADE_DETAIL_VERSIONS"}
SCREEN_OLD_WORDS = re.compile(r"revision|revise|\brev\b", re.IGNORECASE)


def _texts(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _texts(v)]
    if isinstance(value, list | tuple | set | frozenset):
        return [t for v in value for t in _texts(v)]
    return []


def test_no_text_of_the_screen_says_revision() -> None:
    """Section 5.6, the word guard, extended by pull request R2 to the texts of `gui/strings.py`
    (Q32): no text of the screen says *revision*, *revise* or *rev*, apart from the upgrade
    question that names the word of 2.x; nor does a document name of the Outputs list."""
    pytest.importorskip("PySide6")
    from harness_design_studio.gui import export_docs, strings

    found = [
        f"{name}: {text[:60]}"
        for name, value in sorted(vars(strings).items())
        if name.isupper() and name not in ALLOWED_STRINGS
        for text in _texts(value)
        if SCREEN_OLD_WORDS.search(text)
    ]
    assert found == []
    assert "revision" in strings.UPGRADE_DETAIL_VERSIONS  # the one allowed text still needs it
    assert [d.label for d in export_docs.DOCS.values() if SCREEN_OLD_WORDS.search(d.label)] == []
    assert export_docs.DOCS["sys_version_report"].label == "Version report"


def test_the_screen_and_the_core_give_the_same_note_on_a_major_version() -> None:
    pytest.importorskip("PySide6")
    from harness_design_studio.core.vcs.release import MAJOR_NOTE
    from harness_design_studio.gui import strings

    assert strings.NV_MAJOR_NOTE == MAJOR_NOTE


def test_the_change_log_and_the_report_say_version(tmp_path: Path) -> None:
    from harness_design_studio.core.vcs.report import LOG_HEADER, version_report

    root = build("released", tmp_path / "p")
    p = load_project(root).project
    assert LOG_HEADER[2] == "Version"
    report = version_report(p, "stamp")
    assert "\n# Version report: " in report
    assert "version 2.0.0 new version started" in report


# ---- the written files of 2.x and of 3.0 (section 5.6, part 3) ---------------------------------------

OUTPUT_HASHES_2X = Path(__file__).parent.parent / "docs" / "ui" / "OUTPUT_HASHES_2.x.json"


def test_the_record_holds_the_projects_of_the_design() -> None:
    from tests import format3_support as f3

    assert f3.recorded() == [
        "custom_device", "example-first-steps", "example-flatsat", "example-minimal-satellite",
        "example-small-satellite", "mini3", "mini3-released",
    ]  # fmt: skip
    size = sum((f3.BEFORE / f"{n}.json").stat().st_size for n in f3.recorded())
    assert size < 5_000_000, size  # the record of the projects: small enough for the repository
    released = f3.record("mini3-released")["files"]
    assert "revision A to B" in released["system/revision_report.md"]["text"]


@pytest.mark.parametrize("name", ["example-first-steps", "example-minimal-satellite", "example-small-satellite", "example-flatsat", "mini3"])  # fmt: skip
def test_the_record_is_what_2x_wrote(name: str) -> None:
    """Each recorded file and each member of a recorded workbook has the digest that the output-hash
    baseline of 2.x (the examples) or the golden of 2.x (mini3) holds for it; a recorded text hashes
    to that digest itself."""
    from tests import format3_support as f3

    files = f3.record(name)["files"]
    if name.startswith("example-"):
        reference = json.loads(OUTPUT_HASHES_2X.read_text(encoding="utf-8"))[
            name.removeprefix("example-")
        ]
        key = "sha256"
    else:
        reference = json.loads((f3.BEFORE / f"golden-{name}.json").read_text(encoding="utf-8"))
        key = "golden"
    assert set(reference) == set(files) - {
        "manifest.json"
    }  # (the manifest is written by an export)
    for rel, digest in reference.items():
        assert files[rel][key] == digest, rel
        if "members" in files[rel] and key == "sha256":  # the workbook digest is of its members
            import hashlib

            parts = json.dumps(sorted(files[rel]["members"].items())).encode()
            assert hashlib.sha256(parts).hexdigest() == digest, rel
        if "text" in files[rel] and key == "sha256":
            import hashlib

            assert hashlib.sha256(files[rel]["text"].encode()).hexdigest() == digest, rel


@pytest.mark.slow
def test_the_written_files_of_3_0_are_those_of_2x_after_the_word_list() -> None:
    """Every file of every recorded project, as this tool writes it, equals the file of 2.x after
    the steps of section 5.6 (`tests/format3_support.py`): the stamp, the file name, the word
    list, the length rule and the manifest. Any other difference fails, and so does an entry of
    the list that matches nowhere in the whole set."""
    from tests import format3_support as f3

    used = [0] * len(f3.word_changes())
    problems: list[str] = []
    for name in f3.recorded():
        new, raw = f3.dump_now(name)
        rec = f3.record(name)
        found = f3.compare(rec["files"], new, raw, used, rec["tool_version"])
        problems += [f"{name}: {p}" for p in found]
    assert problems == []
    unused = [c["old"] for c, n in zip(f3.word_changes(), used, strict=True) if n == 0]
    assert unused == []


def test_a_word_change_left_out_of_the_list_fails_the_comparison(monkeypatch) -> None:
    """A mutation: without the entry for the header line of a drawing, one *Revision* stays in the
    2.x file after the list, and the comparison says so."""
    from tests import format3_support as f3

    changes = [c for c in f3.word_changes() if not c["old"].startswith("Revision {L}  status")]
    monkeypatch.setattr(f3, "word_changes", lambda: changes)
    new, raw = f3.dump_now("mini3")
    rec = f3.record("mini3")
    problems = f3.compare(rec["files"], new, raw, [0] * len(changes), rec["tool_version"])
    assert problems and all("drawing_" in p for p in problems), problems


def test_the_report_rule_moves_only_the_renamed_field() -> None:
    from tests.format3_support import _resort_field

    text = "- Harness `W001`\n  - released_on: a -> b\n  - version: 1.0.0 -> 2.0.0\n  - wires: x\n## Next\n  - name: a -> b"
    moved = _resort_field(
        text.replace("  - version: 1.0.0 -> 2.0.0\n  - wires", "  - wires").replace(
            "  - released_on", "  - version: 1.0.0 -> 2.0.0\n  - released_on"
        )
    )
    assert moved == text  # the version line goes back after released_on, before wires
    assert _resort_field("  - b: 1\n  - a: 2") == "  - b: 1\n  - a: 2"  # no version: untouched


def test_the_numbers_snapshot_keeps_every_readable_number() -> None:
    """The snapshot of 3.0 against the one of 2.x (its readable part, kept in the record): every
    gauge, length, part, colour and lock of every wire and every finding with its text is equal;
    only the digests of the files and the name of the version report changed (section 5.6)."""
    from tests import format3_support as f3

    old = json.loads((f3.BEFORE / "numbers-2.x.json").read_text(encoding="utf-8"))
    new = json.loads((FIXTURES / "numbers" / "snapshot.json").read_text(encoding="utf-8"))
    assert set(old) == set(new)
    for name in old:
        assert new[name]["wires"] == old[name]["wires"], name
        assert new[name]["findings"] == old[name]["findings"], name
        renamed = sorted(f3.NEW_REPORT if r == f3.OLD_REPORT else r for r in old[name]["files"])
        assert sorted(new[name]["files"]) == renamed, name
