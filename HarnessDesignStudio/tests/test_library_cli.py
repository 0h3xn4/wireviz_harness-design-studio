# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,union-attr,type-arg,attr-defined"
"""The command line of the device library (D-240, design of 2.2.0,
`docs/ait/DESIGN_2.2_DEVICE_LIBRARY.md` sections 3 and 5, pull request 3): `libraries`,
`add-device`, `update-device`, `save-device`, and `imports` and `explain` with the project's
libraries. Each command through `cli.main.main` with small libraries in `tmp_path`: the normal
path, the `--json` documents, a dry run that writes nothing, a diff that changes no byte, the exit
codes of `--check`, refusals that name the harness or the choices and change nothing. The Git
lines use the `git` program and are skipped without it."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.cli.jsonout import SHAPES
from harness_design_studio.cli.main import main
from harness_design_studio.core import library_folder as lf
from harness_design_studio.core import library_pointer as lp
from harness_design_studio.core.import_record import file_sha256
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
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
RECORD = "devices:RW1.device.json"


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


def make_project(folder: Path, project: Project | None = None, libraries=("../lib",)) -> Path:
    save_project(project if project is not None else new_project(), folder)
    if libraries:
        lp.write_pointer(folder, list(libraries))
    return folder


def edit_file(path: Path, change) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def pin(data: dict[str, Any], cid: str, pid: str) -> dict[str, Any]:
    c = next(x for x in data["devices"][0]["connectors"] if x["id"] == cid)
    return next(p for p in c["pins"] if p["id"] == pid)


def files(folder: Path) -> dict[str, bytes]:
    """Every file of a folder and its bytes (the lock files of a command left out: the project
    lock leaves its empty `.harness.lock.takeover`, which the project's `.gitignore` names)."""
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file() and not p.name.startswith(".harness.lock")
    }


def cli(capsys: pytest.CaptureFixture[str], *argv: object) -> tuple[int, str, str]:
    rc = main([str(a) for a in argv])
    got = capsys.readouterr()
    return rc, got.out, got.err


def doc(capsys: pytest.CaptureFixture[str], shape: str, *argv: object, rc: int = 0) -> dict:
    code, out, err = cli(capsys, *argv, "--json")
    assert code == rc, (argv, out, err)
    found = json.loads(out)
    assert list(found) == list(SHAPES[shape]), shape
    assert found["ok"] is (rc == 0)
    return found


@pytest.fixture
def lib(tmp_path: Path) -> Path:
    return make_library(tmp_path / "lib")


@pytest.fixture
def proj(tmp_path: Path, lib: Path) -> Path:
    return make_project(tmp_path / "proj")


def records(folder: Path) -> dict[str, Any]:
    return load_project(folder).project.import_records


# ---- libraries --------------------------------------------------------------------------------


def test_libraries_add_and_remove_round_trip_outside_undo(tmp_path: Path, lib: Path, capsys):
    proj = make_project(tmp_path / "proj", libraries=())
    rc, out, _ = cli(capsys, "libraries", proj)
    assert rc == 0 and "names no device library" in out
    rc, out, _ = cli(capsys, "libraries", proj, "--add", "../lib")
    assert rc == 0 and lp.read_pointer(proj) == ["../lib"]
    assert "outside undo" in out and "device-libraries.json" in out
    rc, out, _ = cli(capsys, "libraries", proj)
    assert rc == 0 and "../lib: lib, 3 devices, not a Git repository" in out
    before = files(proj)
    rc, out, _ = cli(capsys, "libraries", proj, "--add", "../lib/")
    assert rc == 0 and "already" in out and files(proj) == before
    rc, _out, err = cli(capsys, "libraries", proj, "--remove", "../other")
    assert rc == 2 and "does not name ../other" in err and files(proj) == before
    # A path for one person's home folder is refused on every system. (Not "C:\\libs": on
    # Windows that is an absolute path on the drive of the project, which --add stores as a
    # relative path, as the absolute path below shows.)
    rc, _out, err = cli(capsys, "libraries", proj, "--add", "~/libs")
    assert rc == 2 and files(proj) == before
    rc, out, _ = cli(capsys, "libraries", proj, "--remove", "../lib")
    assert rc == 0 and lp.read_pointer(proj) == []
    rc, out, _ = cli(capsys, "libraries", proj, "--add", lib.resolve())  # an absolute path
    assert rc == 0 and lp.read_pointer(proj) == ["../lib"]
    found = doc(capsys, "libraries", "libraries", proj)
    assert found["source"] == "device-libraries.json" and found["devices"] is None
    assert found["libraries"] == [
        {
            "path": "../lib",
            "name": "lib",
            "readable": True,
            "devices": 3,
            "git": "not a Git repository",
            "commit": None,
            "branch": None,
        }
    ]


def test_libraries_names_a_folder_that_cannot_be_read_without_its_absolute_path(
    tmp_path: Path, capsys
):
    proj = make_project(tmp_path / "proj", libraries=("../gone",))
    rc, out, _ = cli(capsys, "libraries", proj)
    assert rc == 0 and "../gone: cannot be read" in out
    code, text, _ = cli(capsys, "libraries", proj, "--json")
    assert code == 0 and str(tmp_path) not in text
    found = json.loads(text)
    assert found["libraries"][0]["readable"] is False and "../gone" in found["problems"][0]


def test_libraries_devices_lists_every_state(proj: Path, lib: Path, capsys):
    assert cli(capsys, "add-device", proj, "RW1")[0] == 0
    edit_file(lib / "RW1.device.json", lambda d: pin(d, "RW1-J02", "5").update(signal="SPARE"))
    rc, out, _ = cli(capsys, "libraries", proj, "--devices")
    assert rc == 0
    lines = {line.split()[0]: line for line in out.splitlines() if line.strip()}
    assert "not in project" in lines["OBC"] and "library changed" in lines["RW1"]
    assert "RW1.device.json" in lines["RW1"]
    found = doc(capsys, "libraries", "libraries", proj, "--devices")
    assert [(d["device"], d["state"]) for d in found["devices"]] == [
        ("OBC", "not in project"),
        ("PCDU", "not in project"),
        ("RW1", "library changed"),
    ]


@needs_git
def test_libraries_names_the_commit_and_the_branch(proj: Path, lib: Path, capsys):
    git(lib, "init", "-q", "-b", "main")
    git(lib, "add", "-A")
    git(lib, "commit", "-q", "-m", "Devices")
    head = git(lib, "rev-parse", "HEAD")
    rc, out, _ = cli(capsys, "libraries", proj)
    assert rc == 0 and f"Git commit {head[:7]} on main" in out
    found = doc(capsys, "libraries", "libraries", proj)
    assert found["libraries"][0]["commit"] == head and found["libraries"][0]["branch"] == "main"
    rc, out, _ = cli(capsys, "add-device", proj, "OBC")
    assert rc == 0 and f"Library commit: {head} (branch main)" in out


# ---- add-device -------------------------------------------------------------------------------


def test_add_device_dry_run_writes_nothing_then_adds_with_the_record(proj: Path, lib, capsys):
    before = files(proj)
    rc, out, _ = cli(capsys, "add-device", proj, "RW1", "--dry-run")
    assert rc == 0 and "Dry run: nothing was changed." in out and files(proj) == before
    found = doc(capsys, "add-device", "add-device", proj, "RW1", "--dry-run")
    assert found["dry_run"] and not found["changed"] and found["devices"] == ["RW1"]
    assert files(proj) == before
    rc, out, _ = cli(capsys, "add-device", proj, "RW1")
    assert rc == 0 and "Added RW1 from the library lib (RW1.device.json)." in out
    assert f"Import record: {RECORD}" in out and "Library: not a Git repository" in out
    rec = records(proj)[RECORD]
    assert rec.sha256 == file_sha256(lib / "RW1.device.json") and rec.kind == "devices"
    assert "RW1" in load_project(proj).project.units


def test_add_device_with_a_count_and_several_names(proj: Path, capsys):
    found = doc(capsys, "add-device", "add-device", proj, "OBC", "--count", "2")
    assert found["changed"] and found["devices"] == ["OBC", "OBC-R"]
    assert found["sources"] == [{"device": "OBC", "library": "lib", "file": "OBC.device.json"}]
    assert [r["id"] for r in found["records"]] == ["devices:OBC.device.json"]
    assert found["taken"] is None
    rc, out, _ = cli(capsys, "add-device", proj, "PCDU", "RW1")
    assert rc == 0 and "Added PCDU, RW1" in out
    assert set(load_project(proj).project.units) == {"OBC", "OBC-R", "PCDU", "RW1"}
    rc, _out, err = cli(capsys, "add-device", proj, "PCDU", "RW1", "--count", "2")
    assert rc == 2 and "one device" in err


def test_a_taken_id_gives_the_choices_and_changes_nothing(tmp_path: Path, lib: Path, capsys):
    proj = make_project(tmp_path / "proj")
    assert cli(capsys, "add-device", proj, "RW1")[0] == 0
    before = files(proj)
    rc, _out, err = cli(capsys, "add-device", proj, "RW1")
    assert rc == 1 and "follows the library" in err and "--count 2" in err
    assert files(proj) == before
    p = pinout_project()  # its PCDU was not added from the library, and differs from it
    c = p.connectors["PCDU-J02"]
    p.connectors["PCDU-J02"] = evolve(c, pins=[evolve(x, function="ours") for x in c.pins])
    other = make_project(tmp_path / "other", p)
    before = files(other)
    rc, out, err = cli(capsys, "add-device", other, "PCDU")
    assert rc == 1 and "does not come from the library" in err
    assert "--as PCDU-2" in err and "update-device" in err and "--adopt" in err
    assert "function" in out  # the differences are shown
    assert files(other) == before
    found = doc(capsys, "add-device", "add-device", other, "PCDU", rc=1)
    taken = found["taken"]
    assert taken["device"] == "PCDU" and taken["linked"] is False and taken["free_id"] == "PCDU-2"
    assert len(taken["rows"]) == 3 and not found["changed"]
    rc, out, _ = cli(capsys, "add-device", other, "PCDU", "--as", "PCDU9")
    assert rc == 0 and "does not follow the library" in out
    assert "PCDU9" in load_project(other).project.units and not records(other)


def test_an_unknown_name_and_an_ambiguous_device(tmp_path: Path, lib: Path, capsys):
    proj = make_project(tmp_path / "proj", libraries=("../lib", "../lib2"))
    make_library(tmp_path / "lib2", ["OBC"])
    before = files(proj)
    rc, _out, err = cli(capsys, "add-device", proj, "XYZ")
    assert rc == 2 and "No library of this project holds a device 'XYZ'" in err
    rc, _out, err = cli(capsys, "add-device", proj, "OBC")
    assert rc == 1 and "lib (OBC.device.json)" in err and "lib2 (OBC.device.json)" in err
    found = doc(capsys, "add-device", "add-device", proj, "OBC", rc=1)  # refused, still a document
    assert not found["changed"] and found["devices"] == [] and found["taken"] is None
    assert files(proj) == before
    rc, out, _ = cli(capsys, "libraries", proj, "--devices")
    assert rc == 0 and "in more than one library" in out
    rc, _out, err = cli(capsys, "add-device", proj, "RW1", "--library", tmp_path / "lib2")
    assert rc == 2 and "'RW1'" in err  # --library replaces the project's list


# ---- update-device ----------------------------------------------------------------------------


def test_update_device_shows_the_diff_and_changes_no_byte(proj: Path, lib: Path, capsys):
    assert cli(capsys, "add-device", proj, "RW1", "OBC")[0] == 0
    rc, out, _ = cli(capsys, "update-device", proj, "--check")
    assert rc == 0 and "up to date" in out
    edit_file(lib / "RW1.device.json", lambda d: pin(d, "RW1-J02", "5").update(signal="SPARE"))
    before = files(proj)
    rc, out, _ = cli(capsys, "update-device", proj)
    assert rc == 0 and files(proj) == before
    assert "RW1: library changed" in out and "RW1-J02" in out and "SPARE" in out
    assert "Nothing was changed" in out and "--apply" in out
    rc, out, _ = cli(capsys, "update-device", proj, "--check")
    assert rc == 1 and files(proj) == before
    found = doc(capsys, "update-device", "update-device", proj, "--check", rc=1)
    assert found["differ"] == 1 and not found["changed"]
    rw1 = next(d for d in found["devices"] if d["device"] == "RW1")
    assert rw1["state"] == "library changed" and rw1["result"] == "shown"
    assert rw1["rows"] == [
        {
            "device": "RW1",
            "connector": "RW1-J02",
            "pin": "5",
            "field": "signal",
            "here": "",
            "library": "SPARE",
            "locked_by": "",
        }
    ]
    assert files(proj) == before
    rc, _out, err = cli(capsys, "update-device", proj, "--apply")
    assert rc == 2 and "--all" in err and files(proj) == before
    rc, out, _ = cli(capsys, "update-device", proj, "RW1", "--apply")
    assert rc == 0 and "Took the library's version of RW1" in out
    assert records(proj)[RECORD].sha256 == file_sha256(lib / "RW1.device.json")
    project = load_project(proj).project
    assert next(p for p in project.connectors["RW1-J02"].pins if p.id == "5").signal == "SPARE"
    assert cli(capsys, "update-device", proj, "--check")[0] == 0
    assert cli(capsys, "update-device", proj, "--all", "--apply")[0] == 0  # nothing to do


def test_update_device_adopt_links_a_device_of_the_same_id(tmp_path: Path, lib: Path, capsys):
    p = pinout_project()
    c = p.connectors["RW1-J01"]
    p.connectors["RW1-J01"] = evolve(c, notes="ours")
    proj = make_project(tmp_path / "proj", p)
    before = files(proj)
    rc, out, _ = cli(capsys, "update-device", proj, "RW1")
    assert rc == 0 and "same ID, not from the library" in out and "--adopt" in out
    rc, _out, err = cli(capsys, "update-device", proj, "RW1", "--apply")
    assert rc == 1 and "does not come from the library" in err and files(proj) == before
    rc, _out, err = cli(capsys, "update-device", proj, "--all", "--adopt")
    assert rc == 2 and files(proj) == before
    rc, out, _ = cli(capsys, "update-device", proj, "RW1", "--apply", "--adopt")
    assert rc == 0 and RECORD in records(proj)
    assert load_project(proj).project.connectors["RW1-J01"].notes == ""


def test_a_refusal_names_the_harness_and_changes_nothing(tmp_path: Path, capsys):
    from harness_design_studio.core import devices
    from tests.test_change_control import do_release, exported, full, releasable

    p = full()
    hid = releasable(p)
    do_release(p, hid, exported(p, tmp_path))
    cid = next(c.mates_with for c in p.harnesses[hid].connectors if c.mates_with)
    uid = p.connectors[cid].unit_id
    locked = next(x.id for x in p.connectors[cid].pins if devices.pin_lock_reason(p, cid, x.id))
    (tmp_path / "lib").mkdir()
    proj = make_project(tmp_path / "proj", p)
    rc, out, _ = cli(capsys, "save-device", proj, uid)
    assert rc == 0 and "Commit the library to share it." in out
    path = tmp_path / "lib" / f"{uid}.device.json"
    tail = cid.rsplit("-", 1)[-1]

    def change(d):
        c = next(x for x in d["devices"][0]["connectors"] if x["id"].endswith("-" + tail))
        next(x for x in c["pins"] if x["id"] == locked)["function"] = "Changed"

    edit_file(path, change)
    before = files(proj)
    rc, out, _ = cli(capsys, "update-device", proj, uid)
    assert rc == 0 and hid in out  # the row says which harness locks it
    rc, _out, err = cli(capsys, "update-device", proj, uid, "--apply")
    assert rc == 1 and hid in err and "Nothing of" in err
    assert files(proj) == before
    found = doc(capsys, "update-device", "update-device", proj, uid, "--apply", rc=1)
    assert found["devices"][0]["result"] == "refused" and hid in found["devices"][0]["message"]
    assert files(proj) == before


# ---- save-device ------------------------------------------------------------------------------


def test_save_device_writes_the_file_and_links_it(tmp_path: Path, capsys):
    lib = tmp_path / "lib"
    lib.mkdir()
    proj = make_project(tmp_path / "proj", pinout_project())
    rc, out, _ = cli(capsys, "save-device", proj, "RW1")
    assert rc == 0 and "Saved RW1 to the library lib: RW1.device.json." in out
    assert "Commit the library to share it." in out and RECORD in records(proj)
    assert (lib / "RW1.device.json").is_file()
    rc, out, _ = cli(capsys, "update-device", proj, "RW1", "--check")
    assert rc == 0 and "up to date" in out
    project = load_project(proj).project
    c = project.connectors["RW1-J01"]
    project.connectors["RW1-J01"] = evolve(c, notes="changed here")
    save_project(project, proj)
    saved = (lib / "RW1.device.json").read_bytes()
    before = files(proj)
    rc, _out, err = cli(capsys, "save-device", proj, "RW1")
    assert rc == 1 and "--replace" in err and (lib / "RW1.device.json").read_bytes() == saved
    assert files(proj) == before
    found = doc(capsys, "save-device", "save-device", proj, "RW1", "--replace")
    assert found["file"] == "RW1.device.json" and found["library"] == "lib" and found["changed"]
    assert found["record"]["id"] == RECORD
    assert records(proj)[RECORD].sha256 == file_sha256(lib / "RW1.device.json")
    rc, _out, err = cli(capsys, "save-device", proj, "NOPE")
    assert rc == 2 and "NOPE" in err


def test_save_device_needs_a_library(tmp_path: Path, capsys):
    proj = make_project(tmp_path / "proj", pinout_project(), libraries=())
    rc, _out, err = cli(capsys, "save-device", proj, "RW1")
    assert rc == 2 and "--library" in err
    two = make_project(tmp_path / "two", pinout_project(), libraries=("../a", "../b"))
    make_library(tmp_path / "a", ["OBC"])
    make_library(tmp_path / "b", ["PCDU"])
    rc, _out, err = cli(capsys, "save-device", two, "RW1")
    assert rc == 2 and "--library" in err
    rc, out, _ = cli(capsys, "save-device", two, "OBC")  # the library that holds it
    assert rc == 0 and "Saved OBC to the library a" in out
    rc, out, _ = cli(capsys, "save-device", two, "RW1", "--library", tmp_path / "b")
    assert rc == 0 and (tmp_path / "b" / "RW1.device.json").is_file()


# ---- imports and explain ----------------------------------------------------------------------


def test_imports_check_sees_a_changed_library_file(proj: Path, lib: Path, capsys):
    assert cli(capsys, "add-device", proj, "RW1")[0] == 0
    rc, out, _ = cli(capsys, "imports", proj, "--check")
    assert rc == 0 and "unchanged" in out
    edit_file(lib / "RW1.device.json", lambda d: pin(d, "RW1-J02", "5").update(signal="SPARE"))
    rc, out, _ = cli(capsys, "imports", proj, "--check")
    assert rc == 1 and "source changed" in out
    found = doc(capsys, "imports", "imports", proj, "--check", rc=1)
    assert found["sources_changed"] == 1 and found["imports"][0]["status"] == "changed"
    rc, out, _ = cli(capsys, "imports", proj, "--library", proj)  # no library holds it there
    assert rc == 0 and "not checked" in out


def test_explain_names_the_record_and_the_state(proj: Path, lib: Path, capsys):
    assert cli(capsys, "add-device", proj, "RW1", "--count", "2")[0] == 0
    rc, out, _ = cli(capsys, "explain", proj, "RW1-R")
    assert rc == 0 and f"Import record: {RECORD}" in out
    assert "copy of RW1" in out and "up to date" in out and "Library file: RW1.device.json" in out
    found = doc(capsys, "explain DEVICE", "explain", proj, "RW1")
    assert found["state"] == "up to date" and found["record"]["id"] == RECORD
    assert found["library"] == "lib" and found["file"] == "RW1.device.json"
    project = load_project(proj).project
    project.units["OBC9"] = evolve(project.units["RW1"], id="OBC9")
    save_project(project, proj)
    rc, out, _ = cli(capsys, "explain", proj, "OBC9")
    assert rc == 0 and "not from a device library" in out


def test_the_commands_refuse_a_project_folder_that_is_not_one(tmp_path: Path, capsys):
    for argv in (
        ("libraries",),
        ("add-device", "X"),
        ("update-device",),
        ("save-device", "X"),
    ):
        rc, _out, err = cli(capsys, argv[0], tmp_path / "none", *argv[1:])
        assert rc == 2 and err, argv
