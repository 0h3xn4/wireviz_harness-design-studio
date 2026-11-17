# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def"
"""The Git state of a device library folder, read without starting `git` (D-240, design of 2.2.0
sections 2 and 5): the commit and branch, *not committed*, and a damaged `.git` that reads as
*not readable*, never an error. The repositories are made with the `git` program (skipped when it
is not installed), as in `tests/test_gitinfo.py`."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from harness_design_studio.core import device_file as df
from harness_design_studio.core import library_git as lg
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


def library(folder: Path, commit: bool = True) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for uid in ("OBC", "RW1"):
        text = json.dumps(df.device_file_data(pinout_project(), uid), indent=2) + "\n"
        (folder / df.device_file_name(uid)).write_text(text, encoding="utf-8")
    git(folder, "init", "-q", "-b", "main")
    if commit:
        git(folder, "add", "-A")
        git(folder, "commit", "-q", "-m", "Two devices")
    return folder


def test_a_folder_in_no_repository(tmp_path: Path):
    state = lg.library_git(tmp_path)
    assert state == lg.LibraryGit("none") and state.note() == ""
    (tmp_path / "OBC.device.json").write_text("{}")
    assert lg.file_state(tmp_path, "OBC.device.json") == ""


@needs_git
def test_the_commit_and_the_branch(tmp_path: Path):
    lib = library(tmp_path / "lib")
    state = lg.library_git(lib)
    assert state.kind == "commit" and state.commit == git(lib, "rev-parse", "HEAD")
    assert state.branch == "main"
    assert state.note() == f"Git commit {state.commit[:7]} on main"
    git(lib, "checkout", "-q", "--detach")
    assert lg.library_git(lib).note() == f"Git commit {state.commit[:7]} (detached)"


@needs_git
def test_a_file_equal_to_head_is_committed_and_a_changed_or_new_one_is_not(tmp_path: Path):
    lib = library(tmp_path / "lib")
    assert lg.file_state(lib, "OBC.device.json") == lg.COMMITTED
    path = lib / "RW1.device.json"
    path.write_text(path.read_text(encoding="utf-8").replace('"notes": ""', '"notes": "x"', 1))
    assert lg.file_state(lib, "RW1.device.json") == lg.NOT_COMMITTED
    (lib / "team").mkdir()
    (lib / "team" / "PCDU.device.json").write_text("{}")
    assert lg.file_state(lib, "team/PCDU.device.json") == lg.NOT_COMMITTED
    git(lib, "add", "-A")
    git(lib, "commit", "-q", "-m", "More")
    assert lg.file_state(lib, "team/PCDU.device.json") == lg.COMMITTED
    git(lib, "gc", "-q")  # the objects in a pack are read as well
    assert lg.file_state(lib, "team/PCDU.device.json") == lg.COMMITTED
    assert lg.file_state(lib, "RW1.device.json") == lg.COMMITTED


@needs_git
def test_a_library_folder_inside_a_bigger_repository(tmp_path: Path):
    lib = library(tmp_path / "repo" / "libs" / "acme", commit=False)
    shutil.rmtree(lib / ".git")
    git(tmp_path / "repo", "init", "-q", "-b", "trunk")
    git(tmp_path / "repo", "add", "-A")
    git(tmp_path / "repo", "commit", "-q", "-m", "Libraries")
    assert lg.library_git(lib).branch == "trunk"
    assert lg.file_state(lib, "OBC.device.json") == lg.COMMITTED


@needs_git
def test_a_repository_without_a_commit(tmp_path: Path):
    lib = library(tmp_path / "lib", commit=False)
    state = lg.library_git(lib)
    assert state.kind == "empty" and state.note() == "Git: no commit yet"
    assert lg.file_state(lib, "OBC.device.json") == lg.NOT_COMMITTED


@needs_git
@pytest.mark.parametrize("damage", ["head", "objects", "ref", "garbage-object"])
def test_a_damaged_git_folder_is_not_readable_never_an_error(tmp_path: Path, damage: str):
    lib = library(tmp_path / "lib")
    dot = lib / ".git"
    sha = git(lib, "rev-parse", "HEAD")
    if damage == "head":
        (dot / "HEAD").write_bytes(b"\xff\x00 not a ref")
    elif damage == "objects":
        shutil.rmtree(dot / "objects")
    elif damage == "ref":
        (dot / "refs" / "heads" / "main").write_text("0" * 40 + "\n")
    else:
        obj = dot / "objects" / sha[:2] / sha[2:]
        obj.chmod(0o644)
        obj.write_bytes(b"not zlib at all")
    state = lg.library_git(lib)
    assert state.kind == "unreadable" and state.note() == "Git: not readable"
    assert lg.file_state(lib, "OBC.device.json") == lg.NOT_READABLE


@needs_git
def test_a_damaged_tree_or_file_object_is_not_readable(tmp_path: Path):
    lib = library(tmp_path / "lib")
    blob = git(lib, "rev-parse", "HEAD:OBC.device.json")
    obj = lib / ".git" / "objects" / blob[:2] / blob[2:]
    obj.chmod(0o644)
    obj.write_bytes(b"\x78\x9c broken")
    assert lg.library_git(lib).kind == "commit"  # the commit itself is fine
    assert lg.file_state(lib, "OBC.device.json") == lg.NOT_READABLE
    assert lg.file_state(lib, "missing.device.json") == lg.NOT_READABLE  # not on the disk


def test_a_git_file_that_points_nowhere_is_no_repository_and_no_error(tmp_path: Path):
    (tmp_path / ".git").write_text("gitdir: ../nowhere\n")
    assert lg.library_git(tmp_path).kind == "none"
    (tmp_path / ".git").unlink()
    (tmp_path / ".git").mkdir()  # a folder without HEAD
    assert lg.library_git(tmp_path).kind == "unreadable"
    assert lg.file_state(tmp_path, "x.json") == lg.NOT_READABLE
