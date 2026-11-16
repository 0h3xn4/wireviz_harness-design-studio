# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The versions of a project file that Git keeps, read without starting Git (M7b, D-231).

After a merge stopped on a conflict, `merge-fix` needs two things Git knows: the version both
branches started from (stage 1 of the index, for a file in conflict) and the version of the branch
you are on (the file in the commit of `HEAD`), to tell which side added an entry. Like `gitinfo` and
`gitindex` this reads the repository's own files, read-only, and never starts the `git` program
(D-164): the index, `HEAD`, and the objects, loose or in a pack. Every read has a size limit; a
damaged, shallow or unknown store raises `GitUnreadable`, never a hang or a crash.

    repo = open_repo(project_folder)            # None when the folder is not in a repository
    stages(repo)                                # {"logical/links.json": {1: sha, 2: sha, 3: sha}}
    blob(repo, sha)                             # the bytes of one object
    head_file(repo, "logical/links.json")       # the file in the commit of HEAD; None if not there
"""

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from harness_design_studio.core.vcs import gitindex, gitinfo

__all__ = ["GitUnreadable", "Repo", "blob", "head_file", "open_repo", "stages"]

MAX_BLOB = 64 << 20  # the largest project file the loader reads (`loader.MAX_FILE_BYTES`)
MAX_TREE = 4 << 20
_ERRORS = (
    gitinfo._Unreadable,
    OSError,
    zlib.error,
    ValueError,
    IndexError,
    UnicodeError,
    struct.error,
)


class GitUnreadable(Exception):
    """What Git keeps could not be read (no commit, a damaged or unknown object store)."""


@dataclass(frozen=True)
class Repo:
    folder: Path  # the project folder
    git_dir: Path
    common: Path  # where the objects and the shared refs are
    prefix: str  # the project folder relative to the work tree, "" or ending in "/"


def open_repo(folder: Path) -> Repo | None:
    """The repository around the project folder, or None when there is none."""
    found = gitinfo.find_work_tree(folder)
    if found is None:
        return None
    work, git_dir, common = found
    try:
        base = folder.resolve().relative_to(work).as_posix()
    except OSError, ValueError:
        return None
    return Repo(folder, git_dir, common, "" if base == "." else base + "/")


def stages(repo: Repo) -> dict[str, dict[int, str]]:
    """The project files in conflict (relative to the project folder) and the object id of each of
    their stages (`gitindex.conflict_stages`)."""
    found = gitindex.conflict_stages(repo.folder)
    if found is None:
        raise GitUnreadable("The index of the Git repository cannot be read.")
    return found


def blob(repo: Repo, sha: str, limit: int = MAX_BLOB) -> bytes:
    """The bytes of the file object `sha`."""
    try:
        return gitinfo._read_object(repo.common, sha, gitinfo.BLOB, limit)
    except _ERRORS as exc:
        raise GitUnreadable(f"An object of the Git repository cannot be read ({exc}).") from None


def head_file(repo: Repo, rel: str, limit: int = MAX_BLOB) -> bytes | None:
    """The project file `rel` as the commit of `HEAD` holds it; None when that commit has no such
    file."""
    try:
        _branch, sha = gitinfo._head(repo.git_dir, repo.common)
        commit = gitinfo._read_object(repo.common, sha)
        first = commit.split(b"\n", 1)[0]
        if not first.startswith(b"tree "):
            raise GitUnreadable("The commit of HEAD names no tree.")
        tree = first[5:].decode("ascii").strip()
        parts = (repo.prefix + rel).split("/")
        for depth, name in enumerate(parts):
            entry = _tree_entry(
                gitinfo._read_object(repo.common, tree, gitinfo.TREE, MAX_TREE), name
            )
            if entry is None:
                return None
            mode, tree = entry
            last = depth == len(parts) - 1
            if last != (not mode.startswith(b"4")):  # 40000: a folder; 100644 and the rest: files
                return None
        return gitinfo._read_object(repo.common, tree, gitinfo.BLOB, limit)
    except _ERRORS as exc:
        raise GitUnreadable(f"The commit of HEAD cannot be read ({exc}).") from None


def _tree_entry(data: bytes, name: str) -> tuple[bytes, str] | None:
    """(mode, object id) of the entry `name` of a tree object, or None."""
    want = name.encode("utf-8")
    at = 0
    while at < len(data):
        space = data.index(b" ", at)
        nul = data.index(b"\0", space)
        mode, entry = data[at:space], data[space + 1 : nul]
        sha = data[nul + 1 : nul + 21]
        if len(sha) != 20:
            raise ValueError("a tree entry is cut short")
        if entry == want:
            return mode, sha.hex()
        at = nul + 21
    return None
