# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The device libraries of a project: `device-libraries.json` at the root of the project folder
(design of 2.2.0, `docs/ait/DESIGN_2.2_DEVICE_LIBRARY.md` section 2; D-240).

    paths = read_pointer(project_folder)              # ["../acme-device-library"]; [] without file
    write_pointer(project_folder, ["../acme-device-library"])
    folders = library_folders(project_folder, paths)  # the folders, relative to the project folder

The file is `{"format": "harness-project-libraries", "version": 1, "device_libraries":
[{"path": "../acme-device-library"}]}`. A path is relative to the project folder and written with
`/`; an absolute path, a path that starts with `~` and a `\\` are refused, so the file means the
same on every computer that has the project and its libraries side by side. At most 8 libraries;
no other key. The file is not part of the project format: the loader does not read it, a save does
not write or delete it, and it is in no hash and no output. Every problem is one sentence.
"""

import json
import os
from pathlib import Path
from typing import Any

from harness_design_studio.core.device_library import json_problem
from harness_design_studio.core.errors import HarnessError
from harness_design_studio.core.io import canonical
from harness_design_studio.core.io.fs import atomic_write_bytes

__all__ = [
    "FILE",
    "FORMAT",
    "MAX_LIBRARIES",
    "VERSION",
    "PointerError",
    "check_pointer",
    "library_folders",
    "path_problem",
    "pointer_document",
    "read_pointer",
    "write_pointer",
]

FILE = "device-libraries.json"
FORMAT = "harness-project-libraries"
VERSION = 1
MAX_LIBRARIES = 8
MAX_PATH = 400
MAX_BYTES = 64 * 1024
TOP_KEYS = ("format", "version", "device_libraries")


class PointerError(HarnessError):
    """`device-libraries.json` cannot be read or written; the message says why."""


def path_problem(path: object) -> str:
    """Why `path` cannot name a library in `device-libraries.json`; empty when it can."""
    if not isinstance(path, str) or not path.strip():
        return "A library path must be a text that is not empty."
    if len(path) > MAX_PATH:
        return f"The library path {path[:40]}… is longer than {MAX_PATH} characters."
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in path):
        return "A library path may not hold a control character."
    if "\\" in path:
        return f"The library path {path} holds a '\\'; write the folders with '/'."
    if path.startswith("~"):
        return f"The library path {path} starts with '~'; write it relative to the project folder."
    if path.startswith("/") or ":" in path:
        return f"The library path {path} is absolute; write it relative to the project folder."
    if "" in path.split("/"):
        return f"The library path {path} has an empty folder name ('//' or a '/' at the end)."
    return ""


def check_pointer(data: object) -> list[str]:
    """The library paths of the checked content of a `device-libraries.json` (strict: no other
    key, the format and version known, at most 8 paths, each one relative, none twice)."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise PointerError(f"The file is not a list of device libraries (format '{FORMAT}').")
    extra = sorted(set(data) - set(TOP_KEYS))
    if extra:
        raise PointerError(f"The file has the key '{extra[0]}', which it may not have.")
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise PointerError("The file has no valid version number.")
    if version > VERSION:
        raise PointerError(
            f"The file is version {version}; this program reads version {VERSION}. "
            "Use a newer program to read it."
        )
    entries = data.get("device_libraries", [])
    if not isinstance(entries, list):
        raise PointerError("'device_libraries' must be a list of records.")
    paths: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path"}:
            raise PointerError('Each library must be a record with only a "path".')
        paths.append(entry["path"])
    return _checked(paths)


def _checked(paths: list[Any]) -> list[str]:
    if len(paths) > MAX_LIBRARIES:
        raise PointerError(f"A project names at most {MAX_LIBRARIES} device libraries.")
    seen: set[str] = set()
    for path in paths:
        problem = path_problem(path)
        if problem:
            raise PointerError(problem)
        if path in seen:
            raise PointerError(f"The library path {path} is in the list twice.")
        seen.add(path)
    return list(paths)


def read_pointer(project_folder: Path | str) -> list[str]:
    """The library paths the project names, in the file's order; [] when it has no
    `device-libraries.json`. A file that cannot be used raises `PointerError`."""
    path = Path(project_folder) / FILE
    if path.is_symlink():
        raise PointerError(f"{FILE} is a link; it must be a file of the project folder.")
    if not path.exists():
        return []
    try:
        if not path.is_file():
            raise PointerError(f"{FILE} is not a file.")
        if path.stat().st_size > MAX_BYTES:
            raise PointerError("The file is too large to read (limit 64 KB).")
        data = canonical.loads_strict(path.read_bytes())
    except OSError as exc:
        raise PointerError(f"The file could not be read ({exc.strerror}).") from exc
    except (ValueError, RecursionError) as exc:
        raise PointerError(json_problem(exc)) from exc
    return check_pointer(data)


def pointer_document(paths: list[str]) -> dict[str, Any]:
    """The content of a `device-libraries.json` that names `paths` (checked)."""
    return {
        "format": FORMAT,
        "version": VERSION,
        "device_libraries": [{"path": p} for p in _checked(list(paths))],
    }


def write_pointer(project_folder: Path | str, paths: list[str]) -> Path:
    """Write `device-libraries.json` into the project folder (two-space indent, the keys in a
    fixed order). Nothing is written when a path is refused. Returns the path of the file."""
    root = Path(project_folder)
    text = json.dumps(pointer_document(paths), indent=2, ensure_ascii=False) + "\n"
    target = root / FILE
    atomic_write_bytes(target, text.encode("utf-8"), backup=False, root=root)
    return target


def library_folders(project_folder: Path | str, paths: list[str]) -> list[Path]:
    """The folders that the paths name, joined to the project folder (`..` taken out without
    reading the disk)."""
    root = Path(project_folder)
    return [Path(os.path.normpath(root / p)) for p in paths]
