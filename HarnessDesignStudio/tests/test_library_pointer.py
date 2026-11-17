# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def"
"""`device-libraries.json`, the device libraries of a project (D-240, design of 2.2.0 sections 2
and 4): read and write, relative paths only, strict; outside the project format (the loader does
not read it, a save leaves it byte-identical, it is in no hash)."""

import json
from pathlib import Path

import pytest

from harness_design_studio.core import library_pointer as lp
from harness_design_studio.core.io import layout
from harness_design_studio.core.io.loader import disk_fingerprint, load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.samples import mini3

GOOD = {"format": lp.FORMAT, "version": 1, "device_libraries": [{"path": "../acme-device-library"}]}


def write(folder: Path, data: object) -> Path:
    path = folder / lp.FILE
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_a_project_without_the_file_names_no_library(tmp_path: Path):
    assert lp.read_pointer(tmp_path) == []


def test_write_then_read(tmp_path: Path):
    paths = ["../acme-device-library", "libs/own", "./x/../y"]
    path = lp.write_pointer(tmp_path, paths)
    assert path == tmp_path / lp.FILE
    assert lp.read_pointer(tmp_path) == paths
    text = path.read_text(encoding="utf-8")
    assert text.startswith('{\n  "format": "harness-project-libraries",\n  "version": 1,')
    assert text.endswith("\n") and not (tmp_path / (lp.FILE + ".bak")).exists()
    lp.write_pointer(tmp_path, paths)
    assert path.read_text(encoding="utf-8") == text  # the same list gives the same bytes
    assert lp.library_folders(tmp_path / "proj", ["../lib", "sub/lib"]) == [
        tmp_path / "lib",
        tmp_path / "proj" / "sub" / "lib",
    ]


def test_the_file_of_the_design_is_read(tmp_path: Path):
    write(tmp_path, GOOD)
    assert lp.read_pointer(tmp_path) == ["../acme-device-library"]


@pytest.mark.parametrize(
    ("path", "words"),
    [
        ("/home/me/lib", "absolute"),
        ("C:/libs/acme", "absolute"),
        ("~/lib", "starts with '~'"),
        ("~me/lib", "starts with '~'"),
        ("..\\lib", "'/'"),
        ("", "not empty"),
        ("lib//x", "empty folder name"),
        ("lib/", "empty folder name"),
        ("lib\nx", "control character"),
        ("x" * 401, "longer than 400"),
    ],
)
def test_only_relative_paths_with_slashes_are_allowed(tmp_path: Path, path: str, words: str):
    assert words in lp.path_problem(path)
    with pytest.raises(lp.PointerError, match="(?s).*" + words.replace("(", r"\(")[:6]):
        lp.write_pointer(tmp_path, [path])
    assert not (tmp_path / lp.FILE).exists()  # nothing written
    write(tmp_path, {**GOOD, "device_libraries": [{"path": path}]})
    with pytest.raises(lp.PointerError):
        lp.read_pointer(tmp_path)


@pytest.mark.parametrize(
    ("data", "words"),
    [
        ({**GOOD, "projects": []}, "'projects'"),
        ({**GOOD, "format": "other"}, "not a list of device libraries"),
        ({**GOOD, "version": 2}, "version 2"),
        ({**GOOD, "version": True}, "version number"),
        ({**GOOD, "device_libraries": {}}, "list of records"),
        ({**GOOD, "device_libraries": ["../x"]}, "only a"),
        ({**GOOD, "device_libraries": [{"path": "../x", "name": "x"}]}, "only a"),
        ({**GOOD, "device_libraries": [{"path": "../x"}, {"path": "../x"}]}, "twice"),
        ({**GOOD, "device_libraries": [{"path": f"../l{k}"} for k in range(9)]}, "at most 8"),
        ([1], "not a list of device libraries"),
    ],
)
def test_the_file_is_strict(tmp_path: Path, data: object, words: str):
    write(tmp_path, data)
    with pytest.raises(lp.PointerError) as err:
        lp.read_pointer(tmp_path)
    assert words in str(err.value)
    assert not any(w in str(err.value) for w in ("Error", "Traceback", "dict", "list["))


def test_eight_libraries_are_allowed_and_nine_are_not(tmp_path: Path):
    lp.write_pointer(tmp_path, [f"../l{k}" for k in range(8)])
    with pytest.raises(lp.PointerError, match="at most 8"):
        lp.write_pointer(tmp_path, [f"../l{k}" for k in range(9)])
    assert len(lp.read_pointer(tmp_path)) == 8


def test_strict_json(tmp_path: Path):
    (tmp_path / lp.FILE).write_text('{"format": "x", "format": "y"}')
    with pytest.raises(lp.PointerError, match="'format' twice"):
        lp.read_pointer(tmp_path)
    (tmp_path / lp.FILE).write_text('{"format": NaN}')
    with pytest.raises(lp.PointerError, match="does not allow"):
        lp.read_pointer(tmp_path)


def test_a_link_is_refused(tmp_path: Path):
    other = write(tmp_path, GOOD).rename(tmp_path / "elsewhere.json")
    try:
        (tmp_path / lp.FILE).symlink_to(other)
    except OSError:
        pytest.skip("links cannot be made here")
    with pytest.raises(lp.PointerError, match="link"):
        lp.read_pointer(tmp_path)


# ---- outside the project format ---------------------------------------------------------------


def test_the_loader_ignores_the_file(tmp_path: Path):
    proj = tmp_path / "proj"
    save_project(mini3(), proj)
    first = load_project(proj)
    finger = disk_fingerprint(proj)
    write(proj, GOOD)
    again = load_project(proj)
    assert layout.model_hash(again.project) == layout.model_hash(first.project)
    assert again.issues == first.issues  # no issue, no "not part of the project format"
    assert not any(lp.FILE in f"{i.location} {i.message}" for i in again.issues)
    assert disk_fingerprint(proj) == finger
    assert not layout.is_managed(lp.FILE)


def test_a_save_leaves_the_file_byte_identical_and_does_not_delete_it(tmp_path: Path):
    proj = tmp_path / "proj"
    save_project(mini3(), proj)
    lp.write_pointer(proj, ["../acme-device-library"])
    before = (proj / lp.FILE).read_bytes()
    project = load_project(proj).project
    project.units["OBC"] = project.units["OBC"].model_copy(update={"name": "Renamed"})
    save_project(project, proj)
    assert (proj / lp.FILE).read_bytes() == before
    save_project(mini3(), proj)
    assert (proj / lp.FILE).read_bytes() == before
    assert lp.read_pointer(proj) == ["../acme-device-library"]


# ---- Save As (design section 5; pull request 4) -------------------------------------------------


def test_relative_path_of_a_folder(tmp_path: Path):
    proj, lib = tmp_path / "work" / "proj", tmp_path / "work" / "acme-device-library"
    proj.mkdir(parents=True)
    lib.mkdir()
    assert lp.relative_path(lib, proj) == "../acme-device-library"
    assert lp.relative_path(proj / "libs" / "acme", proj) == "libs/acme"
    assert lp.library_folders(proj, [lp.relative_path(lib, proj)]) == [lib]


def test_save_as_rewrites_the_paths_for_the_new_place(tmp_path: Path):
    old = tmp_path / "work" / "proj"
    new = tmp_path / "elsewhere" / "deeper" / "copy"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    lp.write_pointer(old, ["../acme-device-library", "libs/inside"])
    written = lp.copy_pointer(old, new)
    assert written == new / lp.FILE
    paths = lp.read_pointer(new)
    assert paths == ["../../../work/acme-device-library", "../../../work/proj/libs/inside"]
    assert lp.library_folders(new, paths) == lp.library_folders(old, lp.read_pointer(old))
    assert lp.read_pointer(old) == ["../acme-device-library", "libs/inside"]  # left as it was


def test_save_as_without_the_file_writes_none(tmp_path: Path):
    old, new = tmp_path / "a", tmp_path / "b"
    old.mkdir()
    new.mkdir()
    assert lp.copy_pointer(old, new) is None
    assert not (new / lp.FILE).exists()


def test_save_as_of_a_damaged_file_writes_nothing(tmp_path: Path):
    old, new = tmp_path / "a", tmp_path / "b"
    old.mkdir()
    new.mkdir()
    write(old, {"format": lp.FORMAT, "version": 1, "device_libraries": [{"path": "/abs"}]})
    with pytest.raises(lp.PointerError, match="absolute"):
        lp.copy_pointer(old, new)
    assert not (new / lp.FILE).exists()
