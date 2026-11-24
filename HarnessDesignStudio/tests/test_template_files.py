# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The files beside the model that `create_project` copies from a template (design of 5.1.0,
`docs/ait/DESIGN_5.1_FEATURE_TEMPLATES.md` part C, section 5.6, owner question T7): the folder
`extensions/`, the file `device-libraries.json` and the library folders it names inside the
template folder; nothing else, nothing out of the template folder, nothing over a file the model
wrote, and never the trust of a plug-in (that is kept in the person's settings folder)."""

import json
import os
from pathlib import Path

import pytest

from harness_design_studio.core import edit, library_folder, library_link, library_pointer
from harness_design_studio.core import templates as templates_module
from harness_design_studio.core.commands import History
from harness_design_studio.core.extensions import manager, plugins, trust
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.samples import new_project
from harness_design_studio.core.templates import TemplateInfo, create_project

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = ROOT / "docs" / "examples" / "extensions"
NAME = "beside"


def _files(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _template(base: Path, monkeypatch: pytest.MonkeyPatch, *, paths: list[str]) -> Path:
    """A template folder `projects/beside/` under `base`, listed as a template: a project with one
    device, the example extensions, a library folder `team-library/` (a device file and a
    subfolder), and a `device-libraries.json` that names `paths`."""
    folder = base / "projects" / NAME
    p = new_project("Beside the model")
    ops, _uid = edit.ops_add_unit(p, "computer", edit.lane_x(0), 40.0, unit_id="OBC1")
    History(p).execute("add OBC1", ops)
    save_project(p, folder)
    for path in sorted(EXTENSIONS.rglob("*")):
        if path.is_file() and path.name != "README.md":
            target = folder / "extensions" / path.relative_to(EXTENSIONS)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
    (folder / "team-library" / "spare").mkdir(parents=True)
    library_folder.save_devices(folder / "team-library", p, ["OBC1"])
    (folder / "team-library" / "spare" / "notes.txt").write_text("kept with the library\n")
    library_pointer.write_pointer(folder, paths)
    info = TemplateInfo(NAME, "Beside the model", "A template with files beside the model.", "x")
    monkeypatch.setattr(templates_module, "TEMPLATES", (*templates_module.TEMPLATES, info))
    monkeypatch.setattr(templates_module, "_root", lambda: base)
    return folder


def _fresh_extensions() -> None:
    plugins.forget_loaded()
    manager._RUNTIMES.clear()


def test_a_template_gives_the_new_project_its_extensions_and_its_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _template(tmp_path / "bundle", monkeypatch, paths=["team-library"])
    dest = tmp_path / "new"
    create_project(dest, NAME, "My copy", journal=True)
    got, want = _files(dest), _files(source)
    for rel in want:
        if rel.startswith(("extensions/", "team-library/")) or rel == "device-libraries.json":
            assert got.get(rel) == want[rel], rel  # byte for byte
    assert "team-library/spare/notes.txt" in got  # the whole folder, its subfolders too
    assert library_pointer.read_pointer(dest) == ["team-library"]
    libs = library_link.project_libraries(dest)
    assert not libs.problems and [d.unit_id for d in libs.devices()] == ["OBC1"]
    _fresh_extensions()
    loaded = load_project(dest)
    assert not loaded.has_errors and loaded.project.meta.name == "My copy"
    ext = loaded.project.extensions
    assert ext is not None
    assert [(f.name, f.status) for f in ext.files] == [
        ("minimum-wire-gauge-power", "applied"),
        ("power-wire-table", "applied"),
    ]


def test_a_plugin_of_a_template_stays_untrusted_in_the_new_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The trust of a plug-in is the person's, per SHA-256, in the settings folder: `new` copies
    the code and never the trust, so the plug-in does not run until the person trusts it."""
    _template(tmp_path / "bundle", monkeypatch, paths=["team-library"])
    dest = tmp_path / "new"
    create_project(dest, NAME)
    assert not trust.store_path().exists() and trust.read() == []
    _fresh_extensions()
    project = load_project(dest).project
    ext = project.extensions
    assert ext is not None
    (plugin,) = ext.plugins
    assert plugin.name == "duplicate-signal-wires" and plugin.enabled and not plugin.trusted
    assert [row[0] for row in manager.loaded(project) if row[2] == "plugin"] == []  # not run


def test_create_project_copies_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outputs, a stray file and a library folder that the pointer does not name stay behind: the
    model is still written by `save_project`, so a template cannot carry a stale file."""
    source = _template(tmp_path / "bundle", monkeypatch, paths=["team-library"])
    (source / "outputs" / "system").mkdir(parents=True)
    (source / "outputs" / "system" / "box_pinouts.csv").write_text("stale\n")
    (source / "notes.txt").write_text("not part of the project\n")
    (source / "other-library").mkdir()
    (source / "other-library" / "x.json").write_text("{}\n")
    dest = tmp_path / "new"
    create_project(dest, NAME)
    rels = set(_files(dest))
    assert not {r for r in rels if r.startswith(("outputs/", "other-library/"))}
    assert "notes.txt" not in rels
    beside = {
        r
        for r in rels
        if r.startswith(("extensions/", "team-library/")) or r == "device-libraries.json"
    }
    assert beside == {
        r
        for r in _files(source)
        if r.startswith(("extensions/", "team-library/")) or r == "device-libraries.json"
    }


def test_a_library_path_out_of_the_template_is_not_followed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path with `..` names a folder outside the template: the pointer is copied as it is, the
    folder is not (nothing is written beside the new project either)."""
    bundle = tmp_path / "bundle"
    source = _template(bundle, monkeypatch, paths=["team-library", "../outside", "team-library/.."])
    (bundle / "projects" / "outside").mkdir()
    (bundle / "projects" / "outside" / "secret.device.json").write_text("{}\n")
    dest = tmp_path / "made" / "new"
    create_project(dest, NAME)
    assert (dest / "device-libraries.json").read_bytes() == (
        source / "device-libraries.json"
    ).read_bytes()
    assert not (tmp_path / "made" / "outside").exists()
    assert sorted(p.name for p in (tmp_path / "made").iterdir()) == ["new"]
    assert (dest / "team-library").is_dir()


def test_a_library_folder_that_is_a_link_is_not_followed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _template(tmp_path / "bundle", monkeypatch, paths=["team-library", "linked"])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "far.device.json").write_text("{}\n")
    try:
        os.symlink(elsewhere, source / "linked", target_is_directory=True)
        os.symlink(elsewhere / "far.device.json", source / "team-library" / "far.device.json")
    except OSError:
        pytest.skip("this computer does not let a test make a link")
    dest = tmp_path / "new"
    create_project(dest, NAME)
    assert not (dest / "linked").exists()
    assert not (dest / "team-library" / "far.device.json").exists()


def test_create_project_writes_nothing_over_a_file_of_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pointer that names a folder the project writes itself (`config`) or the project folder
    (`.`) copies nothing into it: the model's files are the ones `save_project` wrote."""
    source = _template(tmp_path / "bundle", monkeypatch, paths=["team-library", "config", "."])
    (source / "config" / "README.txt").write_text("not a file of the model\n")
    (source / "outputs").mkdir()
    (source / "outputs" / "stale.csv").write_text("stale\n")
    dest = tmp_path / "new"
    create_project(dest, NAME, "Another name")
    assert not (dest / "config" / "README.txt").exists()
    assert not (dest / "outputs").exists()
    loaded = load_project(dest)
    assert not loaded.has_errors and loaded.project.meta.name == "Another name"
    assert json.loads((dest / "project.json").read_text())["name"] == "Another name"


def test_a_template_without_files_beside_the_model_gets_none(tmp_path: Path) -> None:
    dest = tmp_path / "new"
    create_project(dest, "first-steps")
    assert not (dest / "extensions").exists()
    assert not (dest / library_pointer.FILE).exists()
