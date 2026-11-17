# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-LIB-07. The end-to-end case of 2.2.0, the device library (D-240, section 5 of
`docs/ait/DESIGN_2.2_DEVICE_LIBRARY.md`, pull request 5), through the command line wherever a
command exists. A source project saves two devices, OBC1 and STR1, into a library folder
`acme-devices` (`save-device`), which is then made a Git repository and committed. A blank project
`orbiter` names the library (`libraries --add ../acme-devices`), adds both devices
(`add-device`), gets an interface between them through the core (no command adds an interface),
and is generated, exported and verified. The
library changes a pin function and adds a fixed pin of OBC1, and the change is committed:
`libraries --devices` says *library changed*, `imports --check` and `update-device --check` end
with 1, `update-device` shows the rows and changes no byte, `--apply` takes the library's version
with a new record. Generate and export are then stable, and the whole sequence in two folders gives
the same project files. After a release of the harness, a library change of a pin that the harness
uses is refused and nothing changes.

Needs the `git` program (skipped without it). Example data only."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.cli.main import main as cli_main
from harness_design_studio.core import edit
from harness_design_studio.core.commands import History
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project

GIT = shutil.which("git")
pytestmark = pytest.mark.skipif(GIT is None, reason="needs the git program")
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
RS422 = ("TX+", "TX-", "RX+", "RX-")
J1 = "OBC1-J01"  # import-pinout numbers connector J1 of OBC1 as OBC1-J01
OBC_RECORD = "devices:OBC1.device.json"
STR_RECORD = "devices:STR1.device.json"
REASON = "Example project: values are placeholders"
LIBRARY_JSON = {
    "format": "harness-device-library-folder",
    "version": 1,
    "name": "ACME devices",
    "description": "The devices of the example team",
}


def git(folder: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603 (tests only: fixed arguments)
        [GIT or "git", *args], cwd=folder, env=ENV, check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def run(capsys: pytest.CaptureFixture[str], *args: object) -> tuple[int, str, str]:
    """One command; its exit code, what it printed and its errors."""
    code = cli_main([str(a) for a in args])
    seen = capsys.readouterr()
    return code, seen.out, seen.err


def ok(capsys: pytest.CaptureFixture[str], *args: object) -> str:
    code, out, err = run(capsys, *args)
    assert code == 0, (args, out, err)
    return out


def files(folder: Path) -> dict[str, bytes]:
    """Every file of a folder and its bytes, the project lock's files left out (the empty
    `.harness.lock.takeover`, which the project's `.gitignore` names)."""
    return {
        f.relative_to(folder).as_posix(): f.read_bytes()
        for f in sorted(folder.rglob("*"))
        if f.is_file() and not f.name.startswith(".harness.lock")
    }


def journal_entries(data: bytes) -> list[dict[str, Any]]:
    """The change journal without what is meant to differ: the time of each entry and the chain
    that hashes it."""
    out = []
    for line in data.decode("utf-8").splitlines():
        entry = json.loads(line)
        out.append({k: v for k, v in entry.items() if k not in ("when", "chain", "parent")})
    return out


def comparable(folder: Path) -> dict[str, Any]:
    """The project files to compare across folders: every file as it is, and the journal (which
    records when each change was made) without its times."""
    found: dict[str, Any] = dict(files(folder))
    for name in ("journal.jsonl", "journal.jsonl.bak"):
        if name in found:
            found[name] = journal_entries(found[name])
    return found


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinout(path: Path, pins: list[tuple[str, str]]) -> Path:
    rows = ["Pin,Signal,Mode", *(f"{n},{s},fixed" for n, s in pins)]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def edit_device(path: Path, change: Any) -> None:
    """Change a device file of the library as a person would, in a text editor."""
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data["devices"][0]["connectors"][0]["pins"])
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def make_library(base: Path, capsys: pytest.CaptureFixture[str]) -> tuple[Path, str]:
    """A source project with OBC1 (J1: RS-422 and a ground) and STR1 (RS-422), both saved into
    the library `acme-devices` by `save-device`; the library gets `library.json` and a
    `.gitignore` with `*.bak`, and is committed. The worked example of
    `docs/user-manual/use-the-library.md` runs the same commands. The library folder and its commit."""
    lib = base / "acme-devices"
    lib.mkdir()
    (lib / "library.json").write_text(json.dumps(LIBRARY_JSON, indent=2) + "\n", encoding="utf-8")
    (lib / ".gitignore").write_text("*.bak\n", encoding="utf-8")
    src = base / "source"
    ok(capsys, "new", src, "--template", "blank")
    obc = pinout(base / "obc1.csv", [(str(n + 1), s) for n, s in enumerate((*RS422, "GND"))])
    star = pinout(base / "str1.csv", [(str(n + 1), s) for n, s in enumerate(RS422)])
    for device, csv, name, subsystem, part, gender in (
        ("OBC1", obc, "On-board computer", "avionics", "EX-MICROD-25-F", "female"),
        ("STR1", star, "Star tracker", "aocs", "EX-MICROD-9-M", "male"),
    ):
        ok(
            capsys, "import-pinout", src, csv, "--device", device, "--new-device", name,
            "--subsystem", subsystem, "--default-part", part, "--gender", gender,
        )  # fmt: skip
        out = ok(capsys, "save-device", src, device, "--library", lib)
        assert f"Saved {device} to the library ACME devices: {device}.device.json." in out
        assert "Commit the library to share it." in out
    assert sorted(p.name for p in lib.iterdir()) == [
        ".gitignore",
        "OBC1.device.json",
        "STR1.device.json",
        "library.json",
    ]
    git(lib, "init", "-q", "-b", "main")
    git(lib, "add", "-A")
    git(lib, "commit", "-q", "-m", "OBC1 and STR1")
    return lib, git(lib, "rev-parse", "HEAD")


def add_interface(proj: Path) -> None:
    """IF-001, OBC1 -> STR1, through the project's history (Guided: the tool chooses the
    connectors), and save."""
    p = load_project(proj).project
    ops, iid = edit.ops_add_interface(p, "rs422", "OBC1", "STR1")
    History(p).execute(f"Add {iid}", ops)
    assert iid == "IF-001"
    save_project(p, proj)


def change_obc1(lib: Path) -> str:
    """The library changes the function of pin 1 of J1 and adds a fixed pin 6 SYNC; committed.
    The new commit."""

    def change(pins: list[dict[str, Any]]) -> None:
        pins[0]["function"] = "Telemetry out, positive"
        pins.append(dict(pins[4], id="6", signal="SYNC"))

    edit_device(lib / "OBC1.device.json", change)
    git(lib, "commit", "-q", "-a", "-m", "OBC1: pin 1 function, pin 6 SYNC")
    return git(lib, "rev-parse", "HEAD")


def sequence(base: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    """The case of section 5 up to the update and the stable outputs, with every check on the
    way; what the release step needs."""
    base.mkdir()
    lib, first = make_library(base, capsys)
    proj = base / "orbiter"
    ok(capsys, "new", proj, "--template", "blank")

    # B names the library, relative to its own folder
    out = ok(capsys, "libraries", proj, "--add", "../acme-devices")
    assert "device-libraries.json written: 1 device library." in out and "outside undo" in out
    out = ok(capsys, "libraries", proj)
    assert f"../acme-devices: ACME devices, 2 devices, Git commit {first[:7]} on main" in out
    found = json.loads(ok(capsys, "libraries", proj, "--devices", "--json"))
    assert [(d["device"], d["state"], d["library"], d["file"]) for d in found["devices"]] == [
        ("OBC1", "not in project", "ACME devices", "OBC1.device.json"),
        ("STR1", "not in project", "ACME devices", "STR1.device.json"),
    ]
    assert found["libraries"][0]["commit"] == first and str(base) not in json.dumps(found)

    # add both, with the records that link them
    out = ok(capsys, "add-device", proj, "OBC1", "STR1")
    assert "Added OBC1, STR1 from the library ACME devices" in out
    records = load_project(proj).project.import_records
    assert set(records) == {OBC_RECORD, STR_RECORD}
    for rid, device in ((OBC_RECORD, "OBC1"), (STR_RECORD, "STR1")):
        rec = records[rid]
        assert rec.kind == "devices" and rec.source_name == f"{device}.device.json"
        assert rec.sha256 == sha256(lib / f"{device}.device.json")
        assert rec.source_path is None  # the library is outside the project
        assert rec.notes == [
            "Library: ACME devices",
            f"Library file: {device}.device.json",
            f"Library commit: {first} (branch main)",
        ]
    add_interface(proj)

    # generate, export, verify
    out = ok(capsys, "generate", proj)
    assert "1 added" in out
    ok(capsys, "export", proj)
    out = ok(capsys, "verify", proj, "--outputs")
    assert "1 interfaces and 4 wires checked: 0 error(s)" in out

    # the library changes OBC1
    second = change_obc1(lib)
    new_sha = sha256(lib / "OBC1.device.json")
    out = ok(capsys, "libraries", proj, "--devices")
    states = {line.split()[0]: line for line in out.splitlines()[3:] if line.strip()}
    assert "library changed" in states["OBC1"] and "up to date" in states["STR1"]
    code, out, _err = run(capsys, "imports", proj, "--check")
    assert code == 1 and "source changed" in out
    assert f"`update-device {proj}` shows what the library changed" in out

    # update-device shows the rows and changes no byte
    before = files(proj)
    out = ok(capsys, "update-device", proj, "OBC1")
    rows = [line.split() for line in out.splitlines() if line.strip().startswith("OBC1  ")]
    assert rows == [
        ["OBC1", J1, "1", "function", "-", "Telemetry", "out,", "positive", "-"],
        ["OBC1", J1, "6", "pin", "no", "yes", "-"],
    ]
    assert "Generate again: W001 is a draft on a changed connector" in out
    assert "Nothing was changed; add --apply" in out
    assert files(proj) == before
    code, _out, _err = run(capsys, "update-device", proj, "--check")
    assert code == 1 and files(proj) == before

    # --apply takes the library's version and replaces the record
    out = ok(capsys, "update-device", proj, "OBC1", "--apply")
    assert "Took the library's version of OBC1: 2 changes." in out
    p = load_project(proj).project
    pins = {x.id: x for x in p.connectors[J1].pins}
    assert pins["1"].function == "Telemetry out, positive"
    assert pins["1"].interface_id == "IF-001"  # the project's own field is kept
    assert (pins["6"].signal, pins["6"].fixed) == ("SYNC", True)
    rec = p.import_records[OBC_RECORD]
    assert rec.sha256 == new_sha and f"Library commit: {second} (branch main)" in rec.notes
    assert p.import_records[STR_RECORD] == records[STR_RECORD]
    assert run(capsys, "update-device", proj, "--check")[0] == 0
    assert run(capsys, "imports", proj, "--check")[0] == 0

    # Generate again; a second Generate changes no file; two exports are byte-identical
    out = ok(capsys, "generate", proj)
    assert "0 added, 1 changed" in out
    stable = files(proj)
    out = ok(capsys, "generate", proj)
    assert "0 added, 0 changed, 1 unchanged" in out
    assert files(proj) == stable
    ok(capsys, "export", proj)
    first_export = files(proj / "outputs")
    out = ok(capsys, "verify", proj, "--outputs")
    assert "0 error(s)" in out
    ok(capsys, "export", proj)
    assert files(proj / "outputs") == first_export
    return {"lib": lib, "proj": proj}


def release(proj: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Make W001 releasable (its segment length, a gauge chosen by hand on each wire), export
    and release it."""
    lengths = proj.parent / "lengths.csv"
    lengths.write_text("Harness,Segment,Length\nW001,W001-L1,1500\n", encoding="utf-8")
    ok(capsys, "import-lengths", proj, lengths)
    for k in (1, 2, 3, 4):
        ok(capsys, "override", proj, f"W001-00{k}", "gauge_awg", "26", "--reason", REASON)
    ok(capsys, "generate", proj)
    ok(capsys, "export", proj)
    out = ok(
        capsys, "release", proj, "W001", "--by", "Ada", "--checker", "Bob", "--comment",
        "First release for the CDR", "--date", "2026-03-05", "--accept-placeholders", REASON,
        "--accept-unapproved-parts", REASON,
    )  # fmt: skip
    assert "Release W001 revision A: done." in out


def test_the_device_library_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    one = sequence(tmp_path / "one", capsys)

    # the same sequence in another folder gives the same project files: no time, no path
    two = sequence(tmp_path / "two", capsys)
    assert comparable(two["proj"]) == comparable(one["proj"])
    for base in (tmp_path / "one", tmp_path / "two"):
        for name, data in files(base / "orbiter").items():
            assert str(base).encode() not in data, name

    # after a release, a library change of a pin that W001 uses is refused, naming W001
    proj, lib = one["proj"], one["lib"]
    release(proj, capsys)
    edit_device(lib / "OBC1.device.json", lambda pins: pins[0].update(function="Telemetry +"))
    git(lib, "commit", "-q", "-a", "-m", "OBC1: pin 1 function again")
    before = files(proj)
    out = ok(capsys, "update-device", proj, "OBC1")
    row = next(line for line in out.splitlines() if line.strip().startswith("OBC1  "))
    assert row.split()[-1] == "W001"  # the Locked by column
    code, _out, err = run(capsys, "update-device", proj, "OBC1", "--apply")
    assert code == 1
    assert "W001" in err and "released" in err and "Nothing of OBC1 was changed." in err
    assert files(proj) == before
    assert run(capsys, "update-device", proj, "--check")[0] == 1  # still differs
