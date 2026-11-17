# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,attr-defined,union-attr,call-overload"
"""REQ-LIB-06, REQ-EDIT-03. M4 of the workshop feedback: the library window (not modal, the list, the
preview, add to the project in one undo step, save the selection), the library folder setting, the
number of these devices, and the start screen; since 2.2.0 (D-240) the Status column, the source
line and the libraries the project names in device-libraries.json. Offscreen."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from harness_design_studio.core import copies, library_link  # noqa: E402
from harness_design_studio.core.commands import Put, apply_ops  # noqa: E402
from harness_design_studio.core.import_record import file_sha256  # noqa: E402
from harness_design_studio.core.io.saver import save_project  # noqa: E402
from harness_design_studio.core.library_folder import save_devices, save_subsystem  # noqa: E402
from harness_design_studio.core.library_pointer import write_pointer  # noqa: E402
from harness_design_studio.core.links import plan_add_link  # noqa: E402
from harness_design_studio.core.model import evolve  # noqa: E402
from harness_design_studio.core.samples import new_project  # noqa: E402
from harness_design_studio.gui import strings  # noqa: E402
from harness_design_studio.gui.library_review import (  # noqa: E402
    LibraryReviewDialog,
    TakenIdDialog,
)
from harness_design_studio.gui.library_window import (  # noqa: E402
    LibraryWindow,
    SaveToLibraryDialog,
)
from tests.gui_helpers import action_named, make_window  # noqa: E402
from tests.helpers import pinout_project  # noqa: E402
from tests.test_accessibility import unnamed  # noqa: E402


def source_project():
    p = pinout_project()
    for a, b in (("OBC-J01", "RW1-J02"), ("PCDU-J02", "OBC-J02")):
        ops, _ = plan_add_link(p, a, b)
        apply_ops(p, ops)
    return p


@pytest.fixture
def library(tmp_path: Path) -> Path:
    lib = tmp_path / "shared" / "library"
    lib.mkdir(parents=True)
    p = source_project()
    save_devices(lib, p, ["PCDU"])
    save_devices(lib, p, ["RW1"])
    save_subsystem(lib, p, ["OBC", "RW1"], "Wheel drive", "OBC and a reaction wheel")
    return lib


def window(qtbot, tmp_path: Path, folder: Path | None = None):
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    win.ctl._install(new_project(), None, None)
    if folder is not None:
        win.set_library_folder(str(folder))
    return win


def opened(qtbot, tmp_path: Path, folder: Path | None = None):
    win = window(qtbot, tmp_path, folder)
    action_named(win, "act-library").trigger()
    lib = win.library_window
    assert lib is not None
    qtbot.addWidget(lib)
    assert lib.jobs.wait_idle()
    return win, lib


def pick(lib: LibraryWindow, key: str) -> None:
    assert lib.select_entry(key)
    assert lib.jobs.wait_idle()


# ---- the window ---------------------------------------------------------------------------------


def test_the_window_is_not_modal_and_beside_the_editor(qtbot, tmp_path: Path, library: Path):
    win, lib = opened(qtbot, tmp_path, library)
    assert lib.isVisible() and lib.isWindow() and lib.objectName() == "library-window"
    assert lib.windowModality() == Qt.WindowModality.NonModal
    assert lib.windowTitle() == strings.LIB_TITLE
    assert action_named(win, "act-library").shortcut().toString() == "Ctrl+Shift+O"
    assert action_named(win, "act-library").text() == "Library…"
    assert win.isEnabled()  # the editor works while the window is open
    win.ctl.add_device(name="Gyro", unit_id="GYRO1")
    assert "GYRO1" in win.ctl.project.units
    action_named(win, "act-library").trigger()  # again: the same window
    assert win.library_window is lib


def test_every_control_has_a_name_and_a_tooltip(qtbot, tmp_path: Path, library: Path):
    _, lib = opened(qtbot, tmp_path, library)
    first = lib._shown[0]
    pick(lib, first.key)
    missing = [n for n in unnamed(lib) if "spinbox_lineedit" not in n]
    assert missing == []
    for w in (lib.add_btn, lib.save_btn, lib.change_btn, lib.refresh_btn, lib.close_btn):
        assert w.accessibleName() and w.toolTip()
    for w in (lib.search, lib.kind, lib.list, lib.number, lib.folder_label):
        assert w.accessibleName() and w.toolTip()


def test_the_list_search_and_filter(qtbot, tmp_path: Path, library: Path):
    _, lib = opened(qtbot, tmp_path, library)
    kinds = [(e.kind, e.id or e.name) for e in lib._shown]
    assert set(kinds) == {("device", "PCDU"), ("device", "RW1"), ("subsystem", "Wheel drive")}
    assert lib.list_model.rowCount() == 3
    lib.kind.setCurrentIndex(lib.kind.findData("subsystem"))
    assert [e.name for e in lib._shown] == ["Wheel drive"]
    lib.kind.setCurrentIndex(0)
    lib.search.setText("rw1")
    assert [e.id for e in lib._shown] == ["RW1"]
    lib.search.setText("obc and a reaction")  # the description is searched too
    assert [e.name for e in lib._shown] == ["Wheel drive"]
    lib.search.setText("nothing like this")
    assert lib.list_stack.currentIndex() == 1
    assert lib.empty_title.text() == strings.LIB_EMPTY_NOMATCH and not lib.add_btn.isEnabled()
    lib.search.setText("")
    assert lib.list_stack.currentIndex() == 0 and lib.list_model.rowCount() == 3


def test_the_preview_shows_pins_or_devices_and_connections(qtbot, tmp_path: Path, library: Path):
    _, lib = opened(qtbot, tmp_path, library)
    dev = next(e for e in lib._shown if e.id == "RW1")
    pick(lib, dev.key)
    assert lib.preview_stack.currentWidget() is lib.pin_table
    rows = lib.pin_model.rows()
    assert rows and {"connector", "pin", "signal", "function"} <= set(rows[0])
    assert "RW1" in lib.preview_title.text() and dev.file in lib.preview_text.text()
    sub = next(e for e in lib._shown if e.kind == "subsystem")
    pick(lib, sub.key)
    assert lib.preview_stack.currentWidget() is lib.sub_table
    assert [r["kind"] for r in lib.sub_model.rows()] == ["Device", "Device", "Connection"]
    assert "OBC and a reaction wheel" in lib.preview_text.text()
    assert not lib.number.isEnabled()  # a subsystem is added once


def test_add_a_device_is_one_undo_step(qtbot, tmp_path: Path, library: Path):
    win, lib = opened(qtbot, tmp_path, library)
    dev = next(e for e in lib._shown if e.id == "PCDU")
    pick(lib, dev.key)
    assert lib.add_btn.isEnabled()
    added: list[list[str]] = []
    lib.added.connect(lambda ids: added.append(ids))
    lib.add_btn.click()
    assert added == [["PCDU"]] and "PCDU" in win.ctl.project.units
    assert win.ctl.project.units["PCDU"].name and win.ctl.project.placements["PCDU"]
    assert "Added PCDU" in lib.result_notice.text()
    assert win.ctl.is_selected("unit", "PCDU")
    win.ctl.undo()
    assert "PCDU" not in win.ctl.project.units and not win.ctl.project.connectors
    win.ctl.redo()
    # again: nothing is replaced; the taken ID asks what to do (D-240), here another ID
    asked: list[QDialog] = []

    def other(dlg):
        asked.append(dlg)
        assert isinstance(dlg, TakenIdDialog) and dlg.new_id.text() == "PCDU-2"
        dlg.other.setChecked(True)
        return QDialog.DialogCode.Accepted

    lib.run_dialog = other
    lib.add_btn.click()
    assert asked and "PCDU-2" in win.ctl.project.units and "PCDU" in win.ctl.project.units


def test_add_writes_the_import_record_that_links_the_device(qtbot, tmp_path: Path, library: Path):
    """REQ-LIB-07: the window adds through `library_link.plan_add_device`, so the device gets the
    record of its library file in the same undo step (D-240)."""
    win, lib = opened(qtbot, tmp_path, library)
    pick(lib, next(e for e in lib._shown if e.id == "RW1").key)
    lib.add_btn.click()
    p = win.ctl.project
    rec = p.import_records["devices:RW1.device.json"]
    assert rec.kind == "devices" and rec.sha256 == file_sha256(library / "RW1.device.json")
    assert rec.notes[:2] == ["Library: library", "Library file: RW1.device.json"]
    libs = library_link.open_libraries([library])
    assert library_link.link_state(p, libs, "RW1").state == library_link.UP_TO_DATE
    win.ctl.undo()
    assert "RW1" not in p.units and not p.import_records
    win.ctl.redo()

    def other(dlg):  # a taken ID under another ID: an unlinked copy, no record of its own
        dlg.other.setChecked(True)
        return QDialog.DialogCode.Accepted

    lib.run_dialog = other
    lib.add_btn.click()
    assert "RW1-2" in p.units and list(p.import_records) == ["devices:RW1.device.json"]
    lib.run_dialog = lambda dlg: QDialog.DialogCode.Rejected  # cancelled: nothing changes
    lib.add_btn.click()
    assert "RW1-3" not in p.units and "RW1-R" not in p.units


def test_add_a_number_of_devices(qtbot, tmp_path: Path, library: Path):
    win, lib = opened(qtbot, tmp_path, library)
    pick(lib, next(e for e in lib._shown if e.id == "PCDU").key)
    assert lib.number.isEnabled()
    lib.number.setValue(3)
    lib.add_btn.click()
    p = win.ctl.project
    assert {"PCDU", "PCDU-R", "PCDU-3"} <= set(p.units)
    assert copies.device_count(p, "PCDU") == 3
    win.ctl.undo()  # one step for all three
    assert not any(u.startswith("PCDU") for u in p.units)


def test_add_a_subsystem_is_one_undo_step(qtbot, tmp_path: Path, library: Path):
    win, lib = opened(qtbot, tmp_path, library)
    sub = next(e for e in lib._shown if e.kind == "subsystem")
    pick(lib, sub.key)
    lib.add_btn.click()
    p = win.ctl.project
    assert set(p.units) == {"OBC", "RW1"} and len(p.links) == 1
    assert {u.subsystem for u in p.units.values()} == {"Wheel drive"}
    assert "Wheel drive" in lib.result_notice.text()
    win.ctl.undo()
    assert not p.units and not p.links
    win.ctl.redo()
    assert set(p.units) == {"OBC", "RW1"}


def test_enter_in_the_list_adds(qtbot, tmp_path: Path, library: Path):
    win, lib = opened(qtbot, tmp_path, library)
    pick(lib, next(e for e in lib._shown if e.id == "RW1").key)
    lib.list.setFocus()
    QTest.keyClick(lib.list, Qt.Key.Key_Return)
    assert "RW1" in win.ctl.project.units


def test_a_read_only_project_cannot_be_added_to(qtbot, tmp_path: Path, library: Path):
    win, lib = opened(qtbot, tmp_path, library)
    pick(lib, lib._shown[0].key)
    win.ctl.project.read_only = True
    lib._update_buttons()
    assert not lib.add_btn.isEnabled() and lib.add_btn.toolTip() == strings.LIB_ADD_READ_ONLY


def test_a_subsystem_that_cannot_be_added_says_why_and_changes_nothing(
    qtbot, tmp_path: Path, library: Path
):
    win, lib = opened(qtbot, tmp_path, library)
    sub = next(e for e in lib._shown if e.kind == "subsystem")
    pick(lib, sub.key)
    lib.entry_data["connections"][0]["pairs"][0]["a_pin"] = "99"
    lib.add_btn.click()
    assert "L1" in lib.result_notice.text() and not win.ctl.project.units


# ---- the folder -----------------------------------------------------------------------------------


def test_without_a_folder_the_window_says_what_to_do(qtbot, tmp_path: Path):
    win, lib = opened(qtbot, tmp_path)
    assert lib.list_stack.currentIndex() == 1
    assert lib.empty_title.text() == strings.LIB_EMPTY_NO_FOLDER
    assert lib.empty_choose.isVisibleTo(lib) and not lib.add_btn.isEnabled()
    assert lib.folder_label.text() == strings.LIB_FOLDER_NONE
    asked: list[str] = []

    def choose(title: str) -> str:
        asked.append(title)
        return str(tmp_path)

    win.ask_folder = choose
    lib.empty_choose.click()
    assert asked == [strings.LIB_FOLDER_TITLE] and win.library_folder() == str(tmp_path)
    assert lib.jobs.wait_idle()
    assert lib.empty_title.text() == strings.LIB_EMPTY_FOLDER  # an empty folder


def test_a_missing_folder_is_said_in_words(qtbot, tmp_path: Path):
    win, lib = opened(qtbot, tmp_path, tmp_path / "unplugged-drive")
    assert lib.folder_notice.isVisibleTo(lib)
    assert "does not exist" in lib.folder_notice.text() and "drive" in lib.folder_notice.text()
    assert lib.empty_title.text() == strings.LIB_EMPTY_UNREADABLE
    assert not lib.add_btn.isEnabled() and not lib.save_btn.isEnabled()


def test_a_damaged_file_is_named_and_the_others_are_listed(qtbot, tmp_path: Path, library: Path):
    (library / "broken.json").write_text("{nope")
    win, lib = opened(qtbot, tmp_path, library)
    assert lib.list_model.rowCount() == 3
    text = lib.folder_notice.text()
    assert "1 file in the folder" in text and "broken.json" in text and "not valid JSON" in text


def test_refresh_sees_what_a_colleague_added(qtbot, tmp_path: Path, library: Path):
    win, lib = opened(qtbot, tmp_path, library)
    assert lib.list_model.rowCount() == 3
    save_devices(library, source_project(), ["OBC"])
    lib.refresh_btn.click()
    assert lib.jobs.wait_idle() and lib.list_model.rowCount() == 4


def test_the_folder_is_a_setting_of_the_person_and_the_window_follows(
    qtbot, tmp_path: Path, library: Path
):
    win, lib = opened(qtbot, tmp_path, library)
    assert win.settings.value("library/folder") == str(library)
    assert win.settings_page.library_path.text() == str(library)
    assert win.settings_page.library_clear.isEnabled()
    win.settings_page.library_clear.click()
    assert win.library_folder() == "" and lib.folder == "" and lib.list_stack.currentIndex() == 1
    assert not win.settings_page.library_clear.isEnabled()
    action_named(win, "act-library-folder")  # the menu twin
    # a second window on the same settings file restores it
    win.set_library_folder(str(library))
    win.settings.sync()
    other = make_window(tmp_path)
    qtbot.addWidget(other)
    assert other.library_folder() == str(library)
    assert other.settings_page.library_path.text() == str(library)


# ---- save the selection ------------------------------------------------------------------------------


def test_save_selection_as_devices_and_as_a_subsystem(qtbot, tmp_path: Path, library: Path):
    win, lib = opened(qtbot, tmp_path, library)
    win.ctl._install(source_project(), None, None)
    assert not lib.save_btn.isEnabled() and lib.save_btn.toolTip() == strings.LIB_SAVE_NONE
    win.ctl.select_many([("unit", "OBC"), ("unit", "PCDU")])
    assert win.ctl.selected_ids("unit") == ["OBC", "PCDU"]
    assert lib.save_btn.isEnabled()
    seen: list[SaveToLibraryDialog] = []

    def answer(dlg):
        assert isinstance(dlg, SaveToLibraryDialog)
        seen.append(dlg)
        assert (
            dlg.is_subsystem() and not dlg.ok.isEnabled()
        )  # two devices: a subsystem needs a name
        assert dlg.notice.text() == ""  # (nothing was typed yet: the button says it is not ready)
        dlg.name.setText("x")
        dlg.name.setText("")  # typed and taken out again: now the reason shows
        assert strings.LIB_SAVE_NEEDS_NAME in dlg.notice.text()
        dlg.name.setText("Power and computer")
        assert dlg.ok.isEnabled()
        assert "subsystem-power-and-computer.json" in dlg.info.text()
        assert "connection" in dlg.info.text()
        dlg.description.setText("PCDU feeding the computer")
        assert unnamed(dlg) == []
        return QDialog.DialogCode.Accepted

    lib.run_dialog = answer
    lib.save_btn.click()
    assert seen and (library / "subsystem-power-and-computer.json").exists()
    assert "Saved the subsystem Power and computer" in lib.result_notice.text()
    assert lib.jobs.wait_idle()
    assert any(e.name == "Power and computer" for e in lib._shown)

    # the same name again is refused inline, nothing is replaced
    first = (library / "subsystem-power-and-computer.json").read_bytes()

    def again(dlg):
        dlg.name.setText("Power and computer")
        assert not dlg.ok.isEnabled() and "Choose another name" in dlg.notice.text()
        return QDialog.DialogCode.Rejected

    lib.run_dialog = again
    lib.save_btn.click()
    assert (library / "subsystem-power-and-computer.json").read_bytes() == first

    def as_devices(dlg):
        dlg.as_devices.setChecked(True)
        assert dlg.ok.isEnabled() and not dlg.name.isEnabled()
        return QDialog.DialogCode.Accepted

    lib.run_dialog = as_devices
    lib.save_btn.click()
    assert (library / "OBC.device.json").exists() and (library / "PCDU.device.json").exists()
    assert "Saved OBC, PCDU to OBC.device.json, PCDU.device.json" in lib.result_notice.text()


def test_nothing_is_written_to_the_folder_unless_the_person_saves(
    qtbot, tmp_path: Path, library: Path
):
    before = sorted((p.name, p.stat().st_mtime_ns) for p in library.iterdir())
    win, lib = opened(qtbot, tmp_path, library)
    pick(lib, lib._shown[0].key)
    lib.add_btn.click()
    lib.refresh_btn.click()
    assert lib.jobs.wait_idle()
    win.ctl.undo()
    assert sorted((p.name, p.stat().st_mtime_ns) for p in library.iterdir()) == before


# ---- the editor around it ------------------------------------------------------------------------------


def test_the_window_follows_the_theme(qtbot, tmp_path: Path, library: Path):
    win, lib = opened(qtbot, tmp_path, library)
    win.set_theme_mode("dark")
    QApplication.processEvents()
    dark = lib.palette().color(lib.backgroundRole()).name()
    assert dark == win.palette().color(win.backgroundRole()).name()
    win.set_theme_mode("light")
    QApplication.processEvents()
    light = lib.palette().color(lib.backgroundRole()).name()
    assert light == win.palette().color(win.backgroundRole()).name() and light != dark


def test_the_library_window_does_not_touch_the_editors_layout(qtbot, tmp_path: Path, library: Path):
    win, lib = opened(qtbot, tmp_path, library)
    lib.resize(700, 500)
    lib.close()
    keys = set(win.settings.allKeys())
    assert "library/geometry" in keys and "library/split" in keys
    win._save_settings()
    state = win.settings.value(win._wkey("ui/state"))
    lib.show()
    lib.close()
    win._save_settings()
    assert win.settings.value(win._wkey("ui/state")) == state
    assert not any(
        k.startswith(("ui/", "layout/")) and "library" in k for k in win.settings.allKeys()
    )
    # a new window on the same settings opens the library where it was
    win.settings.sync()
    other = make_window(tmp_path)
    qtbot.addWidget(other)
    action_named(other, "act-library").trigger()
    qtbot.addWidget(other.library_window)
    assert other.library_window.width() == lib.width()


def test_the_keyboard_reaches_every_control(qtbot, tmp_path: Path, library: Path):
    _, lib = opened(qtbot, tmp_path, library)
    pick(lib, lib._shown[0].key)
    lib.activateWindow()
    assert lib.search.hasFocus() or lib.focusWidget() is lib.search
    seen = []
    w = lib.search
    for _ in range(120):
        w = w.nextInFocusChain()
        if w.isVisibleTo(lib) and w.focusPolicy() != Qt.FocusPolicy.NoFocus:
            seen.append(w.objectName())
    for name in ("library-kind", "library-list", "library-add", "library-save", "library-close"):
        assert name in seen, name


# ---- the start screen and a blank project ---------------------------------------------------------------


def test_the_start_screen_offers_the_library_and_shows_no_subsystem(qtbot, tmp_path: Path):
    win = window(qtbot, tmp_path)
    home = win.home_page
    assert (
        home.buttons["library"].text() == strings.HOME_LIBRARY and home.buttons["library"].toolTip()
    )
    assert not win.ctl.project.units and not win.ctl.project.links
    home.buttons["library"].click()
    assert win.library_window is not None and win.library_window.isVisible()
    qtbot.addWidget(win.library_window)


# ---- the number of these devices --------------------------------------------------------------------------


def test_the_add_device_dialog_makes_a_number_of_devices_in_one_step(qtbot, tmp_path: Path):
    win = window(qtbot, tmp_path)
    seen = []

    def answer(dlg):
        seen.append(dlg)
        dlg.name.setText("Star tracker")
        assert dlg.number.value() == 1 and dlg.number.accessibleName()
        dlg.number.setValue(3)
        assert dlg.ok.isEnabled()
        return QDialog.DialogCode.Accepted

    win.run_dialog = answer
    win.add_device_flow()
    p = win.ctl.project
    assert {"STAR1", "STAR1-R", "STAR1-3"} <= set(p.units)
    assert p.units["STAR1-R"].side == "redundant"
    win.ctl.undo()  # all three at once
    assert not any(u.startswith("STAR1") for u in p.units)


def test_the_add_device_dialog_refuses_a_number_whose_ids_are_taken(qtbot, tmp_path: Path):
    win = window(qtbot, tmp_path)
    win.ctl.add_device(name="Gyro", unit_id="GYRO1-R")
    from harness_design_studio.gui.devices_dialogs import NewDeviceDialog

    dlg = NewDeviceDialog(win, win.theme, win.ctl.project)
    qtbot.addWidget(dlg)
    dlg.show()
    dlg.name.setText("Gyro")
    dlg.device_id.setText("GYRO1")
    assert dlg.ok.isEnabled()
    dlg.number.setValue(2)
    assert not dlg.ok.isEnabled() and "GYRO1-R is already used" in dlg.notice.text()


def test_the_devices_tab_sets_the_number_of_a_device(qtbot, tmp_path: Path):
    win = window(qtbot, tmp_path)
    win.ctl.add_device(name="Gyro", unit_id="GYRO1")
    win.go_to("devices")
    view = win.devices_view
    view.show_unit("GYRO1")
    assert view.number.value() == 1 and not view.copies_btn.isEnabled()
    assert view.number.accessibleName() and view.copies_btn.accessibleName()
    view.number.setValue(3)
    assert view.copies_btn.isEnabled()
    view.copies_btn.click()
    p = win.ctl.project
    assert {"GYRO1-R", "GYRO1-3"} <= set(p.units) and view.number.value() == 3
    assert not view.copies_btn.isEnabled()
    win.ctl.undo()
    assert "GYRO1-R" not in p.units and "GYRO1-3" not in p.units
    win.ctl.redo()
    view.show_unit("GYRO1-R")  # a copy has no number of its own
    assert not view.number.isEnabled() and view.number.toolTip() == strings.DV_NUMBER_COPY


def test_create_redundant_copy_still_works_as_before(qtbot, tmp_path: Path):
    win = window(qtbot, tmp_path)
    win.ctl.add_device(name="Gyro", unit_id="GYRO1")
    win.ctl.select("unit", "GYRO1")
    action_named(win, "act-redundant").trigger()
    assert "GYRO1-R" in win.ctl.project.units
    assert copies.device_count(win.ctl.project, "GYRO1") == 2


def test_two_windows_share_one_settings_file_without_losing_the_folder(qtbot, tmp_path: Path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    settings.setValue("library/folder", str(tmp_path))
    settings.sync()
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    assert win.library_folder() == str(tmp_path)


# ---- the status of each device and the source line (D-240, pull request 4) ---------------------------


def test_the_status_column_and_the_source_line(qtbot, tmp_path: Path, library: Path):
    win, lib = opened(qtbot, tmp_path, library)
    assert lib.list_model.columns[3].header == strings.LIB_COLUMN_STATUS
    status = {r["id"]: r["status"] for r in lib.list_model.rows() if r["id"]}
    assert status == {"PCDU": "Not in this project", "RW1": "Not in this project"}
    pick(lib, next(e for e in lib._shown if e.id == "RW1").key)
    lib.add_btn.click()
    assert lib.jobs.wait_idle()
    status = {r["id"]: r["status"] for r in lib.list_model.rows() if r["id"]}
    assert status["RW1"] == "Up to date" and status["PCDU"] == "Not in this project"
    assert lib.source_label.text() == "Source: library, RW1.device.json"
    assert not lib.review_btn.isEnabled()  # nothing differs
    # a device changed here can be reviewed
    p = win.ctl.project
    win.ctl.run("Notes", [Put("units", evolve(p.units["RW1"], notes="ours"))])
    assert lib.jobs.wait_idle()
    status = {r["id"]: r["status"] for r in lib.list_model.rows() if r["id"]}
    assert status["RW1"] == "Changed here"
    assert lib.review_btn.isEnabled() and lib.review_btn.toolTip() == strings.LIB_REVIEW_TIP
    seen: list[QDialog] = []

    def keep(dlg):
        seen.append(dlg)
        assert isinstance(dlg, LibraryReviewDialog) and dlg.model.rows()[0]["here"] == "ours"
        dlg.keep_btn.click()
        return QDialog.DialogCode.Rejected

    lib.run_dialog = keep
    lib.review_btn.click()
    assert seen and p.units["RW1"].notes == "ours"
    assert strings.REVIEW_KEPT.format(device="RW1") in lib.result_notice.text()


def test_every_state_has_words_and_a_tooltip():
    for state in library_link.STATES:
        assert strings.LINK_STATE_WORDS[state] and strings.LINK_STATE_TIPS[state]


# ---- the project's own libraries (device-libraries.json; D-240, pull request 5) -----------------


@pytest.fixture
def acme(tmp_path: Path) -> Path:
    """A library the project names, with a name of its own (library.json)."""
    folder = tmp_path / "work" / "acme"
    folder.mkdir(parents=True)
    (folder / "library.json").write_text(
        '{"format": "harness-device-library-folder", "version": 1, "name": "ACME devices"}\n'
    )
    p = source_project()
    for uid in ("PCDU", "RW1"):
        save_devices(folder, p, [uid])
    return folder


def project_on_disk(tmp_path: Path, paths: list[str]) -> Path:
    proj = tmp_path / "work" / "proj"
    save_project(new_project(), proj)
    if paths:
        write_pointer(proj, paths)
    return proj


def opened_project(qtbot, tmp_path: Path, proj: Path, folder: Path | None = None):
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    if folder is not None:
        win.set_library_folder(str(folder))
    assert win.open_project(proj)
    action_named(win, "act-library").trigger()
    lib = win.library_window
    assert lib is not None
    qtbot.addWidget(lib)
    assert lib.jobs.wait_idle()
    return win, lib


def cells(lib: LibraryWindow, *keys: str) -> list[tuple[str, ...]]:
    return [tuple(str(r[k]) for k in keys) for r in lib.list_model.rows()]


def test_the_window_lists_the_libraries_the_project_names_without_a_folder_of_the_person(
    qtbot, tmp_path: Path, acme: Path
):
    proj = project_on_disk(tmp_path, ["../acme"])
    win, lib = opened_project(qtbot, tmp_path, proj)
    assert win.library_folder() == "" and lib.folder_label.text() == strings.LIB_FOLDER_NONE
    assert lib.project_label.text() == "ACME devices (../acme)"
    assert lib.project_label.accessibleName() and lib.project_label.toolTip()
    assert lib.list_stack.currentIndex() == 0 and not lib.folder_notice.isVisibleTo(lib)
    assert lib.list_model.columns[4].header == strings.LIB_COLUMN_LIBRARY
    assert cells(lib, "id", "library", "status") == [
        ("PCDU", "ACME devices", "Not in this project"),
        ("RW1", "ACME devices", "Not in this project"),
    ]
    assert lib.list_model.rows()[0]["library_tip"] == (
        "ACME devices: named by this project as ../acme"
    )
    # add one: the record links it to the project's library, and the status follows
    pick(lib, next(e for e in lib._shown if e.id == "RW1").key)
    assert "RW1" in lib.preview_title.text() and lib.pin_model.rows()
    lib.add_btn.click()
    assert lib.jobs.wait_idle()
    rec = win.ctl.project.import_records["devices:RW1.device.json"]
    assert (
        rec.sha256 == file_sha256(acme / "RW1.device.json") and "Library: ACME devices" in rec.notes
    )
    assert {r["id"]: r["status"] for r in lib.list_model.rows()}["RW1"] == "Up to date"
    assert lib.source_label.text() == "Source: ACME devices, RW1.device.json"
    assert not lib.save_btn.isEnabled()  # Save writes into the person's folder, which is not set


def test_the_persons_folder_is_listed_beside_the_projects_libraries(
    qtbot, tmp_path: Path, acme: Path, library: Path
):
    proj = project_on_disk(tmp_path, ["../acme"])
    win, lib = opened_project(qtbot, tmp_path, proj, library)
    assert lib.folder_label.text() == str(library)
    assert lib.project_label.text() == "ACME devices (../acme)"
    rows = cells(lib, "kind", "id", "library")
    assert rows == [
        ("Device", "PCDU", "ACME devices"),
        ("Device", "RW1", "ACME devices"),
        ("Device", "PCDU", "library"),
        ("Device", "RW1", "library"),
        ("Subsystem", "", "library"),
    ]
    tips = {r["library_tip"] for r in lib.list_model.rows()}
    assert f"library: your library folder, {library}" in tips
    assert len({r["key"] for r in lib.list_model.rows()}) == 5  # every entry has its own key
    lib.search.setText("acme")  # the library's name is searched too
    assert {e.id for e in lib._shown} == {"PCDU", "RW1"} and len(lib._shown) == 2
    lib.search.setText("")
    # a device of the person's folder is added from that folder; the save goes there too
    mine = next(e for e in lib._shown if e.id == "PCDU" and lib.library_of(e).origin == "person")
    pick(lib, mine.key)
    assert lib.libraries().libraries[0].folder == library
    assert lib.save_btn.toolTip() == strings.LIB_SAVE_NONE  # usable, once devices are selected


def test_a_folder_named_by_the_project_and_the_person_is_listed_once(
    qtbot, tmp_path: Path, acme: Path
):
    proj = project_on_disk(tmp_path, ["../acme"])
    win, lib = opened_project(qtbot, tmp_path, proj, acme)
    assert cells(lib, "id", "library") == [("PCDU", "ACME devices"), ("RW1", "ACME devices")]
    assert lib.list_model.rows()[0]["library_tip"].startswith("ACME devices: named by this project")


def test_the_window_follows_the_projects_list_and_says_what_cannot_be_read(
    qtbot, tmp_path: Path, acme: Path
):
    proj = project_on_disk(tmp_path, [])
    win, lib = opened_project(qtbot, tmp_path, proj)
    assert lib.project_label.text() == strings.LIB_PROJECT_NONE
    assert lib.empty_title.text() == strings.LIB_EMPTY_NO_FOLDER
    win._write_project_libraries(["../acme", "../gone"])  # Settings > Project writes the file
    assert lib.jobs.wait_idle()
    assert lib.project_label.text() == "ACME devices (../acme)"
    assert [r["id"] for r in lib.list_model.rows()] == ["PCDU", "RW1"]
    assert lib.folder_notice.isVisibleTo(lib) and "gone" in lib.folder_notice.text()
    win._write_project_libraries([])
    assert lib.jobs.wait_idle()
    assert lib.project_label.text() == strings.LIB_PROJECT_NONE and not lib.list_model.rows()
