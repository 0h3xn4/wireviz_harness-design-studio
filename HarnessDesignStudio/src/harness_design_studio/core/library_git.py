# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The Git state of a device library folder, read without starting `git` (design of 2.2.0,
`docs/ait/DESIGN_2.2_DEVICE_LIBRARY.md` sections 2 and 4; D-240).

    state = library_git(folder)          # the commit and branch of the repository around it
    state.note()                         # "Git commit 1a2b3c4 on main", "" without a repository
    file_state(folder, "PCDU00.device.json")   # "committed", "not committed", "not readable", ""

A library folder is often a Git checkout. What a project records about a device it took from the
library (the commit, *not committed*) is read with the capped readers of `core/vcs/gitinfo.py` and
`core/vcs/gitobjects.py` (D-164): nothing is run, written or fetched. A damaged `.git` reads as
*not readable*, never as an error.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from harness_design_studio.core.vcs import gitinfo, gitobjects

__all__ = [
    "COMMITTED",
    "NOT_COMMITTED",
    "NOT_READABLE",
    "LibraryGit",
    "file_state",
    "library_git",
]

COMMITTED = "committed"
NOT_COMMITTED = "not committed"
NOT_READABLE = "not readable"
MAX_FILE = 8 * 1024 * 1024  # the largest device file the library reads

Kind = Literal["none", "empty", "unreadable", "commit"]


@dataclass(frozen=True)
class LibraryGit:
    """`kind`: no repository (`none`), a repository without a commit (`empty`), one that cannot
    be read (`unreadable`), or one whose `HEAD` commit was read (`commit`)."""

    kind: Kind
    commit: str = ""  # the 40-character id
    branch: str = ""  # "" for a detached HEAD

    @property
    def short(self) -> str:
        return self.commit[:7]

    def note(self) -> str:
        """One fixed-form line: `Git commit 1a2b3c4 on main`, `Git commit 1a2b3c4 (detached)`,
        `Git: no commit yet`, `Git: not readable`; empty when there is no repository."""
        if self.kind == "commit":
            where = f"on {self.branch}" if self.branch else "(detached)"
            return f"Git commit {self.short} {where}"
        if self.kind == "empty":
            return "Git: no commit yet"
        if self.kind == "unreadable":
            return f"Git: {NOT_READABLE}"
        return ""


def library_git(folder: Path | str) -> LibraryGit:
    """The Git state of the repository around the library folder. Never raises."""
    root = Path(folder)
    try:
        if gitinfo.find_work_tree(root) is None:
            return LibraryGit("none")
        info = gitinfo.last_commit(root)
        if info is not None:
            return LibraryGit("commit", info.commit, info.branch)
        return LibraryGit("empty" if gitinfo.no_commit_yet(root) else "unreadable")
    except Exception:  # noqa: BLE001  (a promise: a damaged .git is "not readable", never an error)
        return LibraryGit("unreadable")


def file_state(folder: Path | str, rel: str) -> str:
    """Whether the file `rel` of the library folder (with `/`) is the file of the `HEAD` commit:
    `committed`, `not committed` (changed, new, or no commit yet), `not readable` (a damaged
    repository, or the file cannot be read), or "" when the folder is in no repository. Never
    raises."""
    root = Path(folder)
    state = library_git(root)
    if state.kind == "none":
        return ""
    if state.kind == "empty":
        return NOT_COMMITTED
    if state.kind == "unreadable":
        return NOT_READABLE
    try:
        repo = gitobjects.open_repo(root)
        if repo is None:
            return NOT_READABLE
        path = root / rel
        if path.is_symlink() or path.stat().st_size > MAX_FILE:
            return NOT_READABLE
        here = path.read_bytes()
        there = gitobjects.head_file(repo, rel, MAX_FILE)
    except gitobjects.GitUnreadable:
        return NOT_READABLE
    except Exception:  # noqa: BLE001  (the same promise for a file that cannot be read)
        return NOT_READABLE
    return COMMITTED if there == here else NOT_COMMITTED
