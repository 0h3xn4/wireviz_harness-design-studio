# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,attr-defined,union-attr,call-overload"
"""REQ-LIB-07, D-240 pull request 4: the device library in the editor. The chip on a linked device,
the notice when a project opens (never applies anything, absent without libraries), the review
dialog (one undo step, a refusal changes nothing, keep, save to the library), the choices for a
taken ID, *From library* in the pickers, Settings > Project > Device libraries of this project
(outside undo) and Save As with the pointer file. Offscreen."""

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QDialog  # noqa: E402

from harness_design_studio.core import copies  # noqa: E402
from harness_design_studio.core import library_folder as lf  # noqa: E402
from harness_design_studio.core import library_link as ll  # noqa: E402
from harness_design_studio.core import library_pointer as lp  # noqa: E402
from harness_design_studio.core.commands import History, Put  # noqa: E402
from harness_design_studio.core.import_record import file_sha256  # noqa: E402
from harness_design_studio.core.io.layout import model_hash  # noqa: E402
from harness_design_studio.core.io.saver import save_project  # noqa: E402
from harness_design_studio.core.model import evolve  # noqa: E402
from harness_design_studio.core.samples import new_project  # noqa: E402
from harness_design_studio.gui import strings  # noqa: E402
from harness_design_studio.gui.devices_dialogs import QuickDeviceDialog  # noqa: E402
from harness_design_studio.gui.library_review import (  # noqa: E402
    LibraryReviewDialog,
    TakenIdDialog,
    chip_text,
)
from tests.gui_helpers import action_named, make_window  # noqa: E402
from tests.helpers import pinout_project  # noqa: E402
from tests.test_accessibility import unnamed  # noqa: E402

PART = "EX-MICROD-9-F"


def edit_file(path: Path, change) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def unit_rec(data: dict[str, Any]) -> dict[str, Any]:
    return data["devices"][0]["unit"]  # type: ignore[no-any-return]


@pytest.fixture
def lib(tmp_path: Path) -> Path:
    folder = tmp_path / "work" / "acme"
    folder.mkdir(parents=True)
    p = pinout_project()
    for uid in ("PCDU", "RW1"):
        lf.save_devices(folder, p, [uid])
    return folder


def project_folder(tmp_path: Path, lib: Path | None, linked: tuple[str, ...] = ()) -> Path:
    """A project on disk that names `lib` in device-libraries.json and holds the library devices
    `linked` (added with their records)."""
    proj = tmp_path / "work" / "proj"
    p = new_project()
    if lib is not None:
        libs = ll.open_libraries([lib])
        for uid in linked:
            add = ll.plan_add_device(p, libs, uid, root=proj)
            History(p).execute(add.label, add.ops)
    save_project(p, proj)
    if lib is not None:
        lp.write_pointer(proj, [lp.relative_path(lib, proj)])
    return proj


def opened(qtbot, tmp_path: Path, proj: Path):
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    assert win.open_project(proj)
    assert win.library_links.wait()
    return win


def answer_with(win, fn):
    seen: list[QDialog] = []

    def run(dlg):
        seen.append(dlg)
        return fn(dlg)

    win.run_dialog = run
    return seen


# ---- the chip -----------------------------------------------------------------------------------


def test_the_chip_says_where_a_device_comes_from_and_how_it_stands(qtbot, tmp_path, lib):
    win = opened(qtbot, tmp_path, project_folder(tmp_path, lib, ("PCDU",)))
    win.ctl.select("unit", "PCDU")
    chip = win.inspector.library_chip
    assert chip.isVisibleTo(win.inspector)
    assert chip.label.text() == "From acme, PCDU.device.json, up to date"
    assert not chip.review.isVisibleTo(chip)  # nothing to review
    assert "acme" in chip.label.toolTip() and strings.LIBCHIP_NAME in chip.accessibleName()
    win.go_to("devices")
    win.devices_view.show_unit("PCDU")
    assert win.devices_view.library_chip.label.text() == chip.label.text()
    # changed here: the chip follows the edit (worked out in the helper thread)
    unit = win.ctl.project.units["PCDU"]
    assert win.ctl.run("Notes", [Put("units", evolve(unit, notes="ours"))])
    assert win.library_links.wait()
    assert chip.label.text().endswith("changed here") and chip.review.isVisibleTo(chip)
    assert win.devices_view.library_chip.label.text().endswith("changed here")
    # a device that has nothing to do with the library has no chip
    win.ctl.add_device(name="Gyro", unit_id="GYRO1")
    win.ctl.select("unit", "GYRO1")
    assert not chip.isVisibleTo(win.inspector)


def test_the_words_of_the_chip_for_each_state(lib):
    p = new_project()
    libs = ll.open_libraries([lib])
    add = ll.plan_add_device(p, libs, "RW1")
    History(p).execute(add.label, add.ops)
    q = pinout_project()
    st = ll.link_state(q, libs, "PCDU")
    assert st is not None and chip_text(st) == "Same ID as PCDU in acme, not from the library"
    (lib / "RW1.device.json").unlink()
    gone = ll.link_state(p, ll.open_libraries([lib]), "RW1")
    assert gone is not None and chip_text(gone) == "From RW1.device.json, source not found"


# ---- the notice when a project opens ----------------------------------------------------------------


def test_the_notice_names_a_device_with_a_newer_version_and_applies_nothing(qtbot, tmp_path, lib):
    proj = project_folder(tmp_path, lib, ("PCDU", "RW1"))
    edit_file(lib / "PCDU.device.json", lambda d: unit_rec(d).update(notes="newer"))
    win = opened(qtbot, tmp_path, proj)
    assert win.alerts.is_showing("library")
    banner = win.alerts.banner("library")
    assert banner.label.text() == "1 device has a newer version in the library: PCDU."
    assert strings.NOTICE_NEWER_DETAIL in banner.details.text()
    p = win.ctl.project
    assert p.units["PCDU"].notes != "newer" and not win.ctl.dirty
    assert not win.ctl.history.can_undo
    states = win.library_links.info.states
    assert states["PCDU"].state == ll.LIBRARY_CHANGED and states["RW1"].state == ll.UP_TO_DATE
    # Review… opens the review of that device; keeping it changes nothing and the notice stays
    seen = answer_with(win, lambda dlg: dlg.reject())
    action = next(b for b in banner.buttons if b.text() == strings.NOTICE_REVIEW)
    action.click()
    assert seen and isinstance(seen[0], LibraryReviewDialog)
    assert p.units["PCDU"].notes != "newer"


def test_no_notice_without_a_library_or_when_everything_is_up_to_date(qtbot, tmp_path, lib):
    win = opened(qtbot, tmp_path, project_folder(tmp_path, None))
    info = win.library_links.info
    assert (info is None or not info.libraries.libraries) and not win.alerts.is_showing("library")
    other = tmp_path / "second"
    other.mkdir()
    win2 = opened(qtbot, other, project_folder(other, lib, ("PCDU",)))
    assert win2.library_links.info is not None and not win2.alerts.is_showing("library")


# ---- the review dialog ----------------------------------------------------------------------------


def test_take_the_library_version_is_one_undo_step_and_undo_restores_device_and_record(
    qtbot, tmp_path, lib
):
    proj = project_folder(tmp_path, lib, ("PCDU",))

    def change(d):
        unit_rec(d).update(notes="newer")
        c = d["devices"][0]["connectors"][0]
        c["pins"][0]["function"] = "Changed in the library"

    edit_file(lib / "PCDU.device.json", change)
    win = opened(qtbot, tmp_path, proj)
    p = win.ctl.project
    before_unit, before_rec = p.units["PCDU"], p.import_records["devices:PCDU.device.json"]

    def take(dlg):
        assert isinstance(dlg, LibraryReviewDialog)
        rows = dlg.model.rows()
        assert {r["field"] for r in rows} == {"notes", "function"}
        assert any(r["library"] == "Changed in the library" for r in rows)
        assert "PCDU.device.json" in dlg.source.text() and "acme" in dlg.source.text()
        assert strings.LINK_STATE_WORDS[ll.LIBRARY_CHANGED] in dlg.state.text()
        assert unnamed(dlg) == []
        assert dlg.keep_btn.isDefault()
        assert dlg.take()
        return QDialog.DialogCode.Accepted

    answer_with(win, take)
    win.review_library_flow("PCDU")
    assert p.units["PCDU"].notes == "newer"
    rec = p.import_records["devices:PCDU.device.json"]
    assert rec.sha256 == file_sha256(lib / "PCDU.device.json") != before_rec.sha256
    assert win.library_links.wait()
    assert win.library_links.info.states["PCDU"].state == ll.UP_TO_DATE
    win.ctl.undo()  # one step: the device and its record
    assert p.units["PCDU"] == before_unit
    assert p.import_records["devices:PCDU.device.json"] == before_rec
    assert win.library_links.wait()
    assert win.library_links.info.states["PCDU"].state == ll.LIBRARY_CHANGED


def test_a_refusal_shows_its_reason_and_changes_nothing(qtbot, tmp_path, lib):
    proj = project_folder(tmp_path, lib, ("PCDU",))

    def change(d):
        unit_rec(d).update(notes="newer")
        next(x for x in d["parts"] if x["id"] == PART).update(pin_count=37)

    edit_file(lib / "PCDU.device.json", change)
    win = opened(qtbot, tmp_path, proj)
    p = win.ctl.project
    before = model_hash(p)
    records = dict(p.import_records)

    def refused(dlg):
        assert not dlg.take()
        assert "37 pins in the library" in dlg.notice.text()
        assert dlg.notice.text().startswith("Nothing was changed.")
        dlg.reject()
        return QDialog.DialogCode.Rejected

    answer_with(win, refused)
    win.review_library_flow("PCDU")
    assert model_hash(p) == before and dict(p.import_records) == records


def test_keep_this_projects_stores_nothing_and_the_state_stays(qtbot, tmp_path, lib):
    proj = project_folder(tmp_path, lib, ("PCDU",))
    edit_file(lib / "PCDU.device.json", lambda d: unit_rec(d).update(notes="newer"))
    win = opened(qtbot, tmp_path, proj)
    revision = win.ctl.history.revision
    answer_with(win, lambda dlg: dlg.keep_btn.click())
    win.review_library_flow("PCDU")
    assert win.ctl.history.revision == revision and not win.ctl.dirty
    assert win.library_links.info.states["PCDU"].state == ll.LIBRARY_CHANGED
    win.ctl.select("unit", "PCDU")
    assert win.inspector.library_chip.label.text().endswith("library changed")


def test_save_this_projects_to_the_library_writes_the_file_and_the_record(qtbot, tmp_path, lib):
    proj = project_folder(tmp_path, lib, ("PCDU",))
    win = opened(qtbot, tmp_path, proj)
    p = win.ctl.project
    assert win.ctl.run("Notes", [Put("units", evolve(p.units["PCDU"], notes="ours"))])
    asked: list[str] = []

    def ask(title, text, buttons):
        asked.append(text)
        return 0

    win.ask_choice = ask
    answer_with(win, lambda dlg: dlg.save_btn.click())
    win.review_library_flow("PCDU")
    assert asked and "PCDU.device.json" in asked[0] and "Undo" in asked[0]
    assert unit_rec(json.loads((lib / "PCDU.device.json").read_text()))["notes"] == "ours"
    rec = p.import_records["devices:PCDU.device.json"]
    assert rec.sha256 == file_sha256(lib / "PCDU.device.json")
    assert win.library_links.wait()
    assert win.library_links.info.states["PCDU"].state == ll.UP_TO_DATE


# ---- a taken ID ------------------------------------------------------------------------------------


def test_a_taken_id_that_follows_the_library_offers_copies(qtbot, tmp_path, lib):
    win = opened(qtbot, tmp_path, project_folder(tmp_path, lib, ("PCDU",)))

    def copy(dlg):
        assert isinstance(dlg, TakenIdDialog)
        assert not dlg.adopt.isEnabled() and dlg.copy.isChecked() and dlg.choice() == "copy"
        assert unnamed(dlg) == []
        return QDialog.DialogCode.Accepted

    answer_with(win, copy)
    win.add_library_device_flow("PCDU")
    p = win.ctl.project
    assert "PCDU-R" in p.units and copies.device_count(p, "PCDU") == 2
    win.ctl.undo()
    assert "PCDU-R" not in p.units


def test_a_taken_id_not_from_the_library_offers_adopt_and_another_id(qtbot, tmp_path, lib):
    proj = tmp_path / "work" / "proj"
    save_project(pinout_project(), proj)  # PCDU of the same ID, not added from the library
    lp.write_pointer(proj, ["../acme"])
    win = opened(qtbot, tmp_path, proj)
    p = win.ctl.project
    assert win.library_links.info.states["PCDU"].state == ll.NOT_FROM_LIBRARY

    def adopt(dlg):
        assert dlg.adopt.isEnabled() and dlg.adopt.isChecked() and dlg.choice() == "adopt"
        return QDialog.DialogCode.Accepted

    answer_with(win, adopt)
    win.add_library_device_flow("PCDU")
    assert "devices:PCDU.device.json" in p.import_records
    assert win.library_links.wait()
    assert win.library_links.info.states["PCDU"].state == ll.UP_TO_DATE
    win.ctl.undo()
    assert not p.import_records

    def other(dlg):
        dlg.new_id.setText("PCDU")  # taken: said inline, Continue stays off
        assert not dlg.ok.isEnabled() and "taken" in dlg.notice.text()
        dlg.new_id.setText("PCDU9")
        assert dlg.other.isChecked() and dlg.ok.isEnabled()
        return QDialog.DialogCode.Accepted

    answer_with(win, other)
    win.add_library_device_flow("PCDU")
    assert "PCDU9" in p.units and not p.import_records  # an unlinked copy: no record
    answer_with(win, lambda dlg: QDialog.DialogCode.Rejected)
    before = model_hash(p)
    win.add_library_device_flow("PCDU")  # cancelled: nothing
    assert model_hash(p) == before


# ---- From library in the pickers --------------------------------------------------------------------


def test_from_library_in_the_add_device_menu_adds_with_the_record(qtbot, tmp_path, lib):
    win = opened(qtbot, tmp_path, project_folder(tmp_path, lib))
    win.menu_add.aboutToShow.emit()
    texts = [a.text() for a in win.menu_add.actions()]
    assert strings.FROM_LIBRARY in texts
    act = next(a for a in win.menu_add.actions() if a.objectName() == "menu-add-library-RW1")
    assert "acme" in act.toolTip()
    act.trigger()
    p = win.ctl.project
    assert "RW1" in p.units and "devices:RW1.device.json" in p.import_records
    win.ctl.undo()
    assert "RW1" not in p.units and not p.import_records
    win.menu_add.aboutToShow.emit()  # made again each time: no section twice
    assert [a.text() for a in win.menu_add.actions()].count(strings.FROM_LIBRARY) == 1


def test_from_library_on_the_diagram_the_palette_and_the_quick_dialog(qtbot, tmp_path, lib):
    win = opened(qtbot, tmp_path, project_folder(tmp_path, lib))
    menu = win.view.build_context_menu(None, None, QPointF(800, 400))
    placed: list[tuple[float, float]] = []

    def add_here(uid: str, x: float, y: float) -> None:
        placed.append((x, y))
        win.add_library_device_flow(uid, (x, y))

    win.view.add_from_library = add_here
    add = next(a.menu() for a in menu.actions() if a.menu() and a.menu().objectName() == "diagram-menu-add")  # fmt: skip
    entry = next(a for a in add.actions() if a.objectName() == "diagram-add-library-PCDU")
    entry.trigger()
    p = win.ctl.project
    assert "PCDU" in p.units and "devices:PCDU.device.json" in p.import_records
    assert [(p.placements["PCDU"].x, p.placements["PCDU"].y)] == placed
    entries = [e.label for e in win.palette_entries()]
    run = next(
        e.run
        for e in win.palette_entries()
        if e.label.startswith(f"{strings.FROM_LIBRARY_PALETTE} RW1")
    )
    run()
    assert "RW1" in p.units and "devices:RW1.device.json" in p.import_records
    assert any(t.startswith(strings.FROM_LIBRARY_PALETTE) for t in entries)
    found = [(d.unit_id, d.name) for d in win.library_devices()]
    dlg = QuickDeviceDialog(win, win.theme, p, found)
    qtbot.addWidget(dlg)
    i = dlg.kind.findData("lib:RW1")
    assert i > 0
    dlg.kind.setCurrentIndex(i)
    assert dlg.library_id() == "RW1" and dlg.template_id() == "" and dlg.ok.isEnabled()


# ---- Settings > Project > Device libraries of this project ----------------------------------------


def test_the_settings_list_writes_the_file_at_once_outside_undo(qtbot, tmp_path, lib):
    proj = project_folder(tmp_path, None)
    win = opened(qtbot, tmp_path, proj)
    page = win.settings_page
    action_named(win, "act-project-libraries").trigger()
    assert page.current_section() == "project"
    assert page.project_libraries.count() == 0 and page.project_library_add.isEnabled()
    assert "outside undo" in page.project_libraries_text.text()
    win.ask_folder = lambda title: str(lib)
    page.project_library_add.click()
    assert lp.read_pointer(proj) == ["../acme"]
    assert [page.project_libraries.item(i).text() for i in range(page.project_libraries.count())] == ["../acme"]  # fmt: skip
    assert "outside undo" in page.project_libraries_note.text()
    assert not win.ctl.history.can_undo and not win.ctl.dirty  # not a design change
    assert win.library_links.wait()
    assert [d.unit_id for d in win.library_devices()] == ["PCDU", "RW1"]
    page.project_libraries.setCurrentRow(0)
    page.project_library_remove.click()
    assert lp.read_pointer(proj) == [] and (proj / lp.FILE).exists()
    assert not win.ctl.history.can_undo
    assert unnamed(page) == []


def test_the_settings_list_needs_a_project_folder(qtbot, tmp_path):
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    win.ctl._install(new_project(), None, None)
    win._show_project_libraries()
    page = win.settings_page
    assert not page.project_library_add.isEnabled()
    assert strings.SETTINGS_PROJECT_LIBRARIES_NO_FOLDER in page.project_libraries_note.text()


# ---- Save As -------------------------------------------------------------------------------------


def test_save_as_copies_the_list_with_its_paths_rewritten(qtbot, tmp_path, lib):
    proj = project_folder(tmp_path, lib, ("PCDU",))
    win = opened(qtbot, tmp_path, proj)
    target = tmp_path / "elsewhere" / "copy"
    win.ask_folder = lambda title: str(target)
    assert win.save_as_flow()
    assert lp.read_pointer(target) == ["../../work/acme"]
    assert lp.library_folders(target, lp.read_pointer(target)) == [lib]
    assert win.library_links.wait()
    assert win.library_links.info.states["PCDU"].state == ll.UP_TO_DATE
