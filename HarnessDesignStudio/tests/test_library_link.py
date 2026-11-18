# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,union-attr,type-arg,attr-defined"
"""REQ-LIB-07. The link between a project device and the device library (D-240, design of 2.2.0,
`docs/ait/DESIGN_2.2_DEVICE_LIBRARY.md` sections 3 to 5): the libraries of a project, every state,
add with the import record, the diff of each kind of field, project-owned fields kept, copies
follow, adopt, an ambiguous name, a part conflict, approvals, a locked pin, a pin that a link
pairs, undo, and the same inputs giving the same ops and bytes. Real small libraries in
`tmp_path`; the Git notes use the `git` program and are skipped without it."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.core import copies, devices
from harness_design_studio.core import library_folder as lf
from harness_design_studio.core import library_link as ll
from harness_design_studio.core import library_pointer as lp
from harness_design_studio.core.commands import History, Put, apply_ops
from harness_design_studio.core.import_record import (
    UNCHANGED,
    UNCHECKED,
    check_sources,
    file_sha256,
)
from harness_design_studio.core.library_folder import LibraryConflict
from harness_design_studio.core.links import plan_add_link
from harness_design_studio.core.model import Project, evolve
from harness_design_studio.core.samples import new_project
from tests.helpers import pinout_project

GIT = shutil.which("git")
needs_git = pytest.mark.skipif(GIT is None, reason="needs the git program")
ENV = {
    "GIT_AUTHOR_NAME": "Ada Lovelace",
    "GIT_AUTHOR_EMAIL": "ada@example.org",
    "GIT_COMMITTER_NAME": "Bob Committer",
    "GIT_COMMITTER_EMAIL": "bob@example.org",
    "GIT_AUTHOR_DATE": "2026-03-04T05:06:07+0000",
    "GIT_COMMITTER_DATE": "2026-03-04T05:06:07+0000",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "HOME": "/nonexistent",
    "PATH": "/usr/bin:/bin:/usr/local/bin",
}


def git(folder: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603 (tests only: fixed arguments)
        [GIT or "git", *args], cwd=folder, env=ENV, check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def make_library(folder: Path, units=("OBC", "PCDU", "RW1"), source: Project | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = source or pinout_project()
    for uid in units:
        lf.save_devices(folder, p, [uid])
    return folder


def edit_file(path: Path, change) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def device_rec(data: dict[str, Any]) -> dict[str, Any]:
    return data["devices"][0]


def conn(data: dict[str, Any], cid: str) -> dict[str, Any]:
    return next(c for c in device_rec(data)["connectors"] if c["id"] == cid)


def pin(data: dict[str, Any], cid: str, pid: str) -> dict[str, Any]:
    return next(p for p in conn(data, cid)["pins"] if p["id"] == pid)


def added(project: Project, libs: ll.ProjectLibraries, name: str, **kw) -> History:
    hist = History(project)
    add = ll.plan_add_device(project, libs, name, **kw)
    hist.execute(add.label, add.ops)
    return hist


def state(project, libs, uid) -> str:
    st = ll.link_state(project, libs, uid)
    return st.state if st is not None else ""


@pytest.fixture
def lib(tmp_path: Path) -> Path:
    return make_library(tmp_path / "lib")


# ---- the libraries of a project ---------------------------------------------------------------


def test_the_libraries_of_a_project_in_their_order(tmp_path: Path):
    a = make_library(tmp_path / "acme", ["OBC"])
    b = make_library(tmp_path / "team", ["RW1"])
    person = make_library(tmp_path / "mine", ["PCDU"])
    proj = tmp_path / "proj"
    proj.mkdir()
    assert [x.unit_id for x in ll.project_libraries(proj, person_folder=person).devices()] == [
        "PCDU"
    ]  # the project names none: the person's folder (the editor only)
    lp.write_pointer(proj, ["../acme", "../team"])
    libs = ll.project_libraries(proj, person_folder=person)
    assert [lib.name for lib in libs.libraries] == ["acme", "team"]
    assert [x.unit_id for x in libs.devices()] == ["OBC", "RW1"]
    only = ll.project_libraries(proj, [b])  # the folders the caller names replace the rest
    assert [x.unit_id for x in only.devices()] == ["RW1"]
    (a / "library.json").write_text(
        '{"format": "harness-device-library-folder", "version": 1, "name": "ACME devices"}'
    )
    assert ll.project_libraries(proj).libraries[0].name == "ACME devices"
    (proj / lp.FILE).write_text('{"format": "nope"}')
    broken = ll.project_libraries(proj, person_folder=person)
    assert not broken.libraries and "device-libraries.json" in broken.problems[0]


def test_a_device_in_two_libraries_is_ambiguous_and_both_are_named(tmp_path: Path):
    libs = ll.open_libraries([make_library(tmp_path / "a"), make_library(tmp_path / "b")])
    with pytest.raises(ll.AmbiguousDeviceError) as exc:
        ll.plan_add_device(new_project(), libs, "OBC")
    assert "a (OBC.device.json)" in str(exc.value) and "b (OBC.device.json)" in str(exc.value)
    assert state(new_project(), libs, "OBC") == ll.AMBIGUOUS


def test_a_name_is_the_id_or_a_unique_device_name(lib: Path):
    libs = ll.open_libraries([lib])
    assert libs.resolve("RW1").unit_id == "RW1"
    assert libs.resolve("rw1").unit_id == "RW1"
    assert libs.resolve("reaction WHEEL 1").unit_id == "RW1"
    with pytest.raises(ll.LinkError, match="No library of this project holds a device 'XYZ'"):
        libs.resolve("XYZ")
    p = pinout_project()
    p.units["RW1"] = evolve(p.units["RW1"], name="Same name")
    p.units["OBC"] = evolve(p.units["OBC"], name="Same name")
    two = ll.open_libraries([make_library(lib.parent / "two", ["OBC", "RW1"], p)])
    with pytest.raises(ll.LinkError, match=r"fits more than one library device \(OBC, RW1\)"):
        two.resolve("same name")


# ---- add --------------------------------------------------------------------------------------


def test_add_is_one_undo_step_and_writes_the_record(lib: Path):
    libs = ll.open_libraries([lib])
    p = new_project()
    add = ll.plan_add_device(p, libs, "PCDU")
    kinds = [(op.collection, op.obj.id) for op in add.ops if isinstance(op, Put)]
    assert ("units", "PCDU") in kinds and ("placements", "PCDU") in kinds
    assert ("connectors", "PCDU-J01") in kinds and kinds[-1][0] == "import_records"
    rec = add.record
    assert rec is not None and rec.id == "devices:PCDU.device.json" and rec.kind == "devices"
    assert rec.source_name == "PCDU.device.json" and rec.source_path is None
    assert rec.sha256 == file_sha256(lib / "PCDU.device.json") and rec.rows_read == 1
    assert rec.notes == ["Library: lib", "Library file: PCDU.device.json", "Library: not a Git repository"]  # fmt: skip
    hist = History(p)
    hist.execute(add.label, add.ops)
    assert p.import_records[rec.id] == rec
    assert state(p, libs, "PCDU") == ll.UP_TO_DATE
    hist.undo()
    assert "PCDU" not in p.units and not p.import_records and not p.connectors


def test_a_library_inside_the_project_folder_records_its_path(tmp_path: Path):
    proj = tmp_path / "proj"
    make_library(proj / "libs" / "acme", ["RW1"])
    libs = ll.project_libraries(proj, [proj / "libs" / "acme"])
    add = ll.plan_add_device(new_project(), libs, "RW1", root=proj)
    assert add.record is not None and add.record.source_path == "libs/acme/RW1.device.json"


@needs_git
def test_the_record_notes_name_the_commit_and_a_file_that_is_not_committed(lib: Path):
    git(lib, "init", "-q", "-b", "main")
    git(lib, "add", "-A")
    git(lib, "commit", "-q", "-m", "Devices")
    libs = ll.open_libraries([lib])
    head = git(lib, "rev-parse", "HEAD")
    rec = ll.plan_add_device(new_project(), libs, "OBC").record
    assert rec is not None
    assert rec.notes == [
        "Library: lib",
        "Library file: OBC.device.json",
        f"Library commit: {head} (branch main)",
    ]
    edit_file(lib / "OBC.device.json", lambda d: device_rec(d)["unit"].update(notes="new"))
    rec = ll.plan_add_device(new_project(), libs, "OBC").record
    assert rec is not None and rec.notes[-1] == "Library file: not committed"


def test_a_taken_id_says_whether_it_follows_the_library(lib: Path):
    libs = ll.open_libraries([lib])
    p = new_project()
    added(p, libs, "PCDU")
    with pytest.raises(ll.TakenIdError) as linked:
        ll.plan_add_device(p, libs, "PCDU")
    assert linked.value.linked and "ask for 2 or more" in str(linked.value)
    q = pinout_project()  # its PCDU was not added from the library
    q.connectors["PCDU-J02"] = evolve(
        q.connectors["PCDU-J02"],
        pins=[evolve(x, function="changed") for x in q.connectors["PCDU-J02"].pins],
    )
    with pytest.raises(ll.TakenIdError) as other:
        ll.plan_add_device(q, libs, "PCDU")
    err = other.value
    assert not err.linked and err.free_id == "PCDU-2" and len(err.rows) == 3
    assert "Adopt it" in str(err) and "PCDU-2" in str(err)
    copy = ll.plan_add_device(q, libs, "PCDU", as_id="PCDU9")
    assert copy.unit_ids == ("PCDU9",) and copy.record is None
    assert not any(isinstance(o, Put) and o.collection == "import_records" for o in copy.ops)
    assert "does not follow the library" in copy.notes[-1]
    renamed = ll.plan_add_device(q, libs, "PCDU", rename_taken=True)
    assert renamed.unit_ids == ("PCDU-2",) and renamed.record is None
    with pytest.raises(ll.LinkError, match="taken"):
        ll.plan_add_device(q, libs, "RW1", as_id="OBC")


def test_a_number_of_devices_adds_copies_that_follow_the_library(lib: Path):
    libs = ll.open_libraries([lib])
    p = new_project()
    hist = added(p, libs, "PCDU", count=3)
    assert copies.device_count(p, "PCDU") == 3
    assert [state(p, libs, u) for u in ("PCDU", "PCDU-R", "PCDU-3")] == [ll.UP_TO_DATE] * 3
    edit_file(lib / "PCDU.device.json", lambda d: pin(d, "PCDU-J02", "3").update(function="Spare"))
    assert [state(p, libs, u) for u in ("PCDU", "PCDU-R", "PCDU-3")] == [ll.LIBRARY_CHANGED] * 3
    diff = ll.library_diff(p, libs, "PCDU-R")  # a copy names its library device
    assert diff.library_id == "PCDU" and diff.devices == ("PCDU", "PCDU-R", "PCDU-3")
    assert [(r.connector, r.pin, r.field) for r in diff.rows] == [
        ("PCDU-3-J02", "3", "function"),  # sorted by connector ID (`ports.natural_key`)
        ("PCDU-J02", "3", "function"),
        ("PCDU-R-J02", "3", "function"),
    ]
    up = ll.plan_update_device(p, libs, "PCDU")
    hist.execute(up.label, up.ops)
    for cid in ("PCDU-J02", "PCDU-R-J02", "PCDU-3-J02"):
        assert next(x for x in p.connectors[cid].pins if x.id == "3").function == "Spare"
    assert p.units["PCDU-R"].name.endswith("(redundant)") and p.units["PCDU-R"].side == "redundant"
    assert [state(p, libs, u) for u in ("PCDU", "PCDU-R", "PCDU-3")] == [ll.UP_TO_DATE] * 3


def test_a_part_of_another_pin_count_refuses_and_an_approval_never_changes(lib: Path):
    libs = ll.open_libraries([lib])
    p = new_project()
    part_id = "EX-MICROD-9-F"
    p.parts[part_id] = evolve(p.parts[part_id], pin_count=37)
    with pytest.raises(ll.LinkError, match=f"The part {part_id} is a connector part with 37 pins"):
        ll.plan_add_device(p, libs, "PCDU")
    p = new_project()
    p.parts[part_id] = evolve(p.parts[part_id], approval="pending", notes="ours")
    edit_file(
        lib / "PCDU.device.json",
        lambda d: next(x for x in d["parts"] if x["id"] == part_id).update(approval="approved"),
    )
    add = ll.plan_add_device(p, libs, "PCDU")
    assert (
        f"Part {part_id} differs from the one in the library; the project's is kept." in add.notes
    )
    assert not any(isinstance(o, Put) and o.collection == "parts" and o.obj.id == part_id for o in add.ops)  # fmt: skip
    History(p).execute(add.label, add.ops)
    assert p.parts[part_id].approval == "pending"
    edit_file(lib / "PCDU.device.json", lambda d: device_rec(d)["unit"].update(notes="later"))
    up = ll.plan_update_device(p, libs, "PCDU")
    History(p).execute(up.label, up.ops)
    assert p.parts[part_id].approval == "pending" and p.units["PCDU"].notes == "later"
    p.parts[part_id] = evolve(p.parts[part_id], category="contact")
    with pytest.raises(ll.LinkError, match="is a contact part"):
        ll.plan_update_device(p, libs, "PCDU")


# ---- the states -------------------------------------------------------------------------------


def test_every_state(lib: Path):
    libs = ll.open_libraries([lib])
    p = new_project()
    assert state(p, libs, "OBC") == ll.NOT_IN_PROJECT
    added(p, libs, "OBC")
    added(p, libs, "RW1")
    assert state(p, libs, "OBC") == ll.UP_TO_DATE
    edit_file(lib / "OBC.device.json", lambda d: device_rec(d)["unit"].update(notes="new notes"))
    assert state(p, libs, "OBC") == ll.LIBRARY_CHANGED
    c = p.connectors["RW1-J02"]
    apply_ops(p, [Put("connectors", evolve(c, name="J2 here"))])
    assert state(p, libs, "RW1") == ll.CHANGED_HERE
    q = pinout_project()
    assert state(q, libs, "PCDU") == ll.NOT_FROM_LIBRARY
    (lib / "OBC.device.json").unlink()
    st = ll.link_state(p, ll.open_libraries([lib]), "OBC")
    assert st is not None and st.state == ll.SOURCE_NOT_FOUND and st.record_id
    assert ll.link_state(p, libs, "nothing-here") is None
    found = ll.link_states(p, ll.open_libraries([lib]))
    assert [(s.unit_id, s.state) for s in found] == [
        ("OBC", ll.SOURCE_NOT_FOUND),
        ("PCDU", ll.NOT_IN_PROJECT),
        ("RW1", ll.CHANGED_HERE),
    ]


def test_a_new_version_of_the_file_that_changes_no_field_is_up_to_date(lib: Path):
    libs = ll.open_libraries([lib])
    p = new_project()
    added(p, libs, "RW1")
    path = lib / "RW1.device.json"
    path.write_text(json.dumps(json.loads(path.read_text()), indent=4) + "\n")
    st = ll.link_state(p, libs, "RW1")
    assert st is not None and st.state == ll.UP_TO_DATE and st.recorded_sha256 != st.library_sha256
    up = ll.plan_update_device(p, libs, "RW1")  # only the record is brought up to date
    assert [(o.collection) for o in up.ops] == ["import_records"]


# ---- the diff ---------------------------------------------------------------------------------


def test_the_diff_of_each_kind_of_field_sorted_by_connector_then_pin(lib: Path):
    libs = ll.open_libraries([lib])
    p = new_project()
    added(p, libs, "OBC")

    def change(d):
        unit = device_rec(d)["unit"]
        unit.update(notes="Flight model", kind="computer", mass_relevant=False)
        conn(d, "OBC-J01").update(name="J1", notes="front")
        pin(d, "OBC-J01", "2").update(signal="TXB", termination="crimp")
        conn(d, "OBC-J01")["pins"].append({"id": "6", "signal": "GND"})
        conn(d, "OBC-J02")["pins"] = [x for x in conn(d, "OBC-J02")["pins"] if x["id"] != "3"]
        device_rec(d)["connectors"] = [
            x for x in device_rec(d)["connectors"] if x["id"] != "OBC-J03"
        ] + [{**conn(d, "OBC-J03"), "id": "OBC-J10", "name": "J10"}]

    edit_file(lib / "OBC.device.json", change)
    diff = ll.library_diff(p, libs, "OBC")
    got = [(r.connector, r.pin, r.field, r.here, r.library) for r in diff.rows]
    assert got == [
        ("", "", "kind", "", "computer"),
        ("", "", "mass_relevant", "yes", "no"),
        ("", "", "notes", "", "Flight model"),
        ("OBC-J01", "", "name", "J01", "J1"),
        ("OBC-J01", "", "notes", "", "front"),
        ("OBC-J01", "2", "signal", "TX-", "TXB"),
        ("OBC-J01", "2", "termination", "unspecified", "crimp"),
        ("OBC-J01", "6", "pin", "no", "yes"),
        ("OBC-J02", "3", "pin", "yes", "no"),
        ("OBC-J03", "", "connector", "yes", "no"),
        ("OBC-J10", "", "connector", "no", "yes"),
    ]
    assert all(r.locked_by == "" for r in diff.rows)
    assert diff.state is not None and diff.state.state == ll.LIBRARY_CHANGED
    assert diff.impacts == (
        "Pin 3 of OBC-J02 is not in the library's version.",
        "The connector OBC-J03 is not in the library's version.",
    )
    hist = History(p)
    up = ll.plan_update_device(p, libs, "OBC")
    hist.execute(up.label, up.ops)
    assert "OBC-J03" not in p.connectors and "OBC-J10" in p.connectors
    assert [x.id for x in p.connectors["OBC-J01"].pins][-1] == "6"
    assert not ll.library_diff(p, libs, "OBC").rows and state(p, libs, "OBC") == ll.UP_TO_DATE


def test_project_owned_fields_are_kept_and_never_a_difference(lib: Path):
    libs = ll.open_libraries([lib])
    p = new_project()
    hist = added(p, libs, "OBC")
    u = p.units["OBC"]
    c = p.connectors["OBC-J01"]
    pins = [
        evolve(x, interface_id="IF-9", signal="ALLOC") if x.id == "5" else x
        for x in c.pins  # pin 5 has no signal in the library: an allocation of this project
    ]
    pins = [evolve(x, locked=True) if x.id == "1" else x for x in pins]
    apply_ops(
        p,
        [
            Put("units", evolve(u, name="Main computer", subsystem="cdh", side="redundant")),
            Put("connectors", evolve(c, pins=pins)),
        ],
    )
    assert state(p, libs, "OBC") == ll.UP_TO_DATE  # name, subsystem, side, allocations, locks
    edit_file(lib / "OBC.device.json", lambda d: pin(d, "OBC-J01", "5").update(function="Spare"))
    up = ll.plan_update_device(p, libs, "OBC")
    hist.execute(up.label, up.ops)
    u2, c2 = p.units["OBC"], p.connectors["OBC-J01"]
    assert (u2.name, u2.subsystem, u2.side) == ("Main computer", "cdh", "redundant")
    five = next(x for x in c2.pins if x.id == "5")
    assert (five.interface_id, five.signal, five.function) == ("IF-9", "ALLOC", "Spare")
    assert next(x for x in c2.pins if x.id == "1").locked
    assert p.placements["OBC"]


def test_adopt_links_a_device_of_the_same_id_that_has_no_record(lib: Path):
    libs = ll.open_libraries([lib])
    p = pinout_project()
    c = p.connectors["RW1-J01"]
    apply_ops(p, [Put("connectors", evolve(c, notes="ours"))])
    assert state(p, libs, "RW1") == ll.NOT_FROM_LIBRARY
    with pytest.raises(ll.LinkError, match="does not come from the library"):
        ll.plan_update_device(p, libs, "RW1")
    up = ll.plan_update_device(p, libs, "RW1", adopt=True)
    assert [r.field for r in up.diff.rows] == ["notes"] and up.record is not None
    hist = History(p)
    hist.execute(up.label, up.ops)
    assert p.connectors["RW1-J01"].notes == "" and up.record.id in p.import_records
    assert state(p, libs, "RW1") == ll.UP_TO_DATE
    hist.undo()  # the device and the record as they were
    assert p.connectors["RW1-J01"].notes == "ours" and not p.import_records


def test_undo_of_an_update_restores_the_device_and_the_record(lib: Path):
    libs = ll.open_libraries([lib])
    p = new_project()
    hist = added(p, libs, "RW1")
    before_conn, before_rec = dict(p.connectors), dict(p.import_records)
    edit_file(lib / "RW1.device.json", lambda d: pin(d, "RW1-J02", "5").update(signal="SPARE"))
    up = ll.plan_update_device(p, libs, "RW1")
    hist.execute(up.label, up.ops)
    rec = p.import_records["devices:RW1.device.json"]
    assert rec.sha256 == file_sha256(lib / "RW1.device.json") != before_rec[rec.id].sha256
    hist.undo()
    assert p.connectors == before_conn and p.import_records == before_rec


def test_a_removed_pin_that_a_link_pairs_names_the_link(tmp_path: Path):
    p = pinout_project()
    ops, _ = plan_add_link(p, "OBC-J01", "RW1-J02")
    apply_ops(p, ops)
    link_id = next(iter(p.links))
    lib = tmp_path / "lib"
    lib.mkdir()
    saved = ll.plan_save_device(p, lib, "OBC")
    History(p).execute("Save", saved.ops)
    libs = ll.open_libraries([lib])
    assert state(p, libs, "OBC") == ll.UP_TO_DATE
    edit_file(
        lib / "OBC.device.json",
        lambda d: conn(d, "OBC-J01").update(
            pins=[x for x in conn(d, "OBC-J01")["pins"] if x["id"] != "1"]
        ),
    )
    diff = ll.library_diff(p, libs, "OBC")
    assert any(link_id in line and "Pin 1 of OBC-J01" in line for line in diff.impacts)
    before = p.connectors["OBC-J01"]
    with pytest.raises(ll.LinkError, match=f"paired in link {link_id}"):
        ll.plan_update_device(p, libs, "OBC")
    assert p.connectors["OBC-J01"] == before


def test_a_pin_that_a_released_harness_locks_refuses_the_device_and_names_it(tmp_path: Path):
    from tests.test_change_control import do_release, exported, full, releasable

    p = full()
    hid = releasable(p)
    do_release(p, hid, exported(p, tmp_path))
    cid = next(c.mates_with for c in p.harnesses[hid].connectors if c.mates_with)
    assert cid is not None
    uid = p.connectors[cid].unit_id
    assert uid is not None
    locked = next(x.id for x in p.connectors[cid].pins if devices.pin_lock_reason(p, cid, x.id))
    lib = tmp_path / "lib"
    lib.mkdir()
    saved = ll.plan_save_device(p, lib, uid)
    History(p).execute("Record", saved.ops)
    libs = ll.open_libraries([lib])
    assert state(p, libs, uid) == ll.UP_TO_DATE
    tail = cid.rsplit("-", 1)[-1]

    def change(d):
        c = next(x for x in device_rec(d)["connectors"] if x["id"].endswith("-" + tail))
        next(x for x in c["pins"] if x["id"] == locked)["function"] = "Changed"

    edit_file(saved.path, change)
    diff = ll.library_diff(p, libs, uid)
    row = next(r for r in diff.rows if r.pin == locked and r.field == "function")
    assert row.locked_by == hid
    before = (dict(p.connectors), dict(p.import_records))
    with pytest.raises(ll.LinkError) as exc:
        ll.plan_update_device(p, libs, uid)
    assert hid in str(exc.value) and "start a new version" in str(exc.value)
    assert (dict(p.connectors), dict(p.import_records)) == before


# ---- save -------------------------------------------------------------------------------------


def test_save_writes_the_file_and_returns_the_record_that_links_it(tmp_path: Path):
    lib = tmp_path / "lib"
    lib.mkdir()
    p = pinout_project()
    saved = ll.plan_save_device(p, lib, "RW1")
    assert saved.path == lib / "RW1.device.json" and saved.file == "RW1.device.json"
    assert [o.collection for o in saved.ops] == ["import_records"]
    assert saved.record.sha256 == file_sha256(saved.path)
    History(p).execute("Save", saved.ops)
    libs = ll.open_libraries([lib])
    assert state(p, libs, "RW1") == ll.UP_TO_DATE
    c = p.connectors["RW1-J01"]
    apply_ops(p, [Put("connectors", evolve(c, notes="changed"))])
    with pytest.raises(LibraryConflict):
        ll.plan_save_device(p, lib, "RW1")
    again = ll.plan_save_device(p, libs.libraries[0], "RW1", replace=True)
    assert again.ops and again.record.sha256 != saved.record.sha256
    History(p).execute("Save", again.ops)
    assert state(p, libs, "RW1") == ll.UP_TO_DATE


@needs_git
def test_a_save_into_a_git_checkout_says_not_committed(lib: Path):
    git(lib, "init", "-q", "-b", "main")
    git(lib, "add", "-A")
    git(lib, "commit", "-q", "-m", "Devices")
    p = pinout_project()
    apply_ops(p, [Put("units", evolve(p.units["RW1"], notes="new"))])
    saved = ll.plan_save_device(p, lib, "RW1", replace=True)
    assert saved.record.notes[-1] == "Library file: not committed"


def test_the_sources_of_device_records_are_found_in_the_libraries(lib: Path):
    libs = ll.open_libraries([lib])
    p = new_project()
    added(p, libs, "RW1")
    located = ll.located_sources(p, libs)
    assert located == {"devices:RW1.device.json": lib / "RW1.device.json"}
    assert [c.status for c in check_sources(p, None)] == [UNCHECKED]
    assert [c.status for c in check_sources(p, None, located=located)] == [UNCHANGED]


# ---- the same inputs, the same result ---------------------------------------------------------


def test_the_same_inputs_give_the_same_ops_and_bytes(tmp_path: Path):
    def run(base: Path) -> tuple[bytes, list, list]:
        lib = base / "lib"
        lib.mkdir(parents=True)
        p = pinout_project()
        saved = ll.plan_save_device(p, lib, "OBC")
        q = new_project()
        libs = ll.open_libraries([lib])
        add = ll.plan_add_device(q, libs, "OBC", count=2)
        History(q).execute(add.label, add.ops)
        edit_file(lib / "OBC.device.json", lambda d: device_rec(d)["unit"].update(notes="x"))
        up = ll.plan_update_device(q, libs, "OBC")
        return saved.path.read_bytes(), add.ops, up.ops

    one, two = run(tmp_path / "one"), run(tmp_path / "two")
    assert one == two


# ---- one file as a library, and files that cannot be read ---------------------------------------


def test_one_file_is_a_library_of_its_own_and_several_devices_are_one_step(tmp_path: Path):
    shelf = tmp_path / "shelf"
    shelf.mkdir()
    path = shelf / "devices.json"
    from harness_design_studio.core import device_library as dl

    dl.save_devices_to_file(path, pinout_project(), ["OBC", "RW1"])
    libs = ll.file_library(path)
    assert [lib.name for lib in libs.libraries] == ["shelf"]
    assert [d.file for d in libs.devices()] == ["devices.json", "devices.json"]
    p = new_project()
    add = ll.plan_add_devices(p, libs, ["OBC", "RW1", "OBC"])
    assert add.unit_ids == ("OBC", "RW1")
    recs = [o for o in add.ops if isinstance(o, Put) and o.collection == "import_records"]
    assert len(recs) == 1 and recs[0].obj.rows_read == 2  # one record for the file
    hist = History(p)
    hist.execute(add.label, add.ops)
    assert [state(p, libs, u) for u in ("OBC", "RW1")] == [ll.UP_TO_DATE] * 2
    again = ll.plan_add_devices(p, libs, ["OBC"], rename_taken=True)
    assert again.unit_ids == ("OBC-2",) and again.record is None
    with pytest.raises(ll.LinkError, match="Choose at least one device"):
        ll.plan_add_devices(p, libs, [])
    q = pinout_project()  # its OBC is not from the file: adding RW1 alone writes no record
    del q.units["RW1"]
    q.connectors = {k: v for k, v in q.connectors.items() if v.unit_id != "RW1"}
    alone = ll.plan_add_device(q, libs, "RW1")
    assert alone.record is None and "No import record was written: OBC" in alone.notes[-1]


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("{not json", "not valid JSON"),
        ('{"format": "other"}', "not a device library file"),
        ('{"format": "harness-device-library", "version": 1, "devices": []}', "does not hold"),
    ],
)
def test_a_file_that_cannot_be_read_is_source_not_found_in_words(lib: Path, text: str, words: str):
    libs = ll.open_libraries([lib])
    p = new_project()
    added(p, libs, "RW1")
    (lib / "RW1.device.json").write_text(text)
    st = ll.link_state(p, libs, "RW1")
    assert st is not None and st.state == ll.SOURCE_NOT_FOUND and words in st.message
    with pytest.raises(ll.LinkError, match=words):
        ll.plan_update_device(p, libs, "RW1")


@needs_git
def test_a_repository_without_a_commit_says_so_in_the_record(lib: Path):
    git(lib, "init", "-q", "-b", "main")
    rec = ll.plan_add_device(new_project(), ll.open_libraries([lib]), "RW1").record
    assert rec is not None and rec.notes[2:] == [
        "Library commit: none yet",
        "Library file: not committed",
    ]


def test_a_copy_whose_device_is_gone_and_names_that_fit_nothing(lib: Path):
    libs = ll.open_libraries([lib])
    p = new_project()
    added(p, libs, "RW1", count=2)
    apply_ops(p, [Put("units", evolve(p.units["RW1-R"], notes="x"))])
    assert state(p, libs, "RW1-R") == ll.CHANGED_HERE
    with pytest.raises(ll.LinkError, match="There is no device NOPE"):
        ll.library_diff(p, libs, "NOPE")
    with pytest.raises(ll.LinkError, match="This project names no device library"):
        ll.plan_add_device(p, ll.open_libraries([]), "RW1")
    with pytest.raises(ll.LinkError, match="cannot be used as a device ID"):
        ll.plan_add_device(p, libs, "OBC", as_id="9 bad")
