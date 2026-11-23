# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index,union-attr,type-arg,call-overload"
"""REQ-GUI-33. The editor's fields of format 5 (design of 5.0.0 `docs/ait/DESIGN_5.0_FORMAT_5.md` section
4.5; offscreen). Pull request 2, part A: the Inspector of a cable connector has *Lengths measured
to* (the project's, rear or face; one undo step; also on a harness Generate made, which keeps it;
off for a released harness), and the Inspector of a connector or backshell part has *Depth (mm)*
(one undo step; an empty field clears it; refused while a released harness uses the part). Pull
request 3, part B: the Devices tab's pin table has the column *Current (A)*, shown while a pin of
the connector has a current (and from the column menu), edited in place in one undo step, a value
that is not a current refused before it is sent. Pull request 4, part C: the Link window takes a
pin paired again by hand and names the junction under the table; *Create harness* asks for the
splice part of a connection with a junction (and says how to get one when the library has none);
the *Splices* list shows the pin currents of the net of each node. Pull request 5, part D: *Change
group* says where each shield end lands (*Lands on pin*, *Backshell* with *Add a backshell…*), also
for a group Generate made (its kind, wires and ends read-only), in one undo step; the Edit wire tab
names the places; deleting a backshell says which places it cleared. Pull request 6, part E: the
Devices tab says whether the device is checked (*Checked by … on … against …*, *…; changed since
the check*, *not checked*), *Mark as checked…* asks who, the day and the ICD (proposed from the
connectors) and marks it in one undo step, *Clear the check* takes it away; the Library window has
the column *Checked* and *Mark as checked…* for the project's device that follows an entry. Pull
request 7, the rest of the editor: *Settings > Project* sets where the segments are measured to
(`model.length_reference`, one undo step, off in a read-only project); the Problems list shows the
infos `current_not_worked_out`, `shield_place_not_stated` and `link_junction` as Info rows with
their own sentence (the junction under the filter Connections), and a click on a finding of a
check of format 5 goes where it is put right: the Inspector of a cable connector without a depth,
the Devices tab of a device whose check is stale, the harness and the Inspector of a shield group,
which shows where its ends land."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from harness_design_studio.core.generate.engine import generate_project  # noqa: E402
from harness_design_studio.core.io.saver import save_project  # noqa: E402
from harness_design_studio.core.model import evolve  # noqa: E402
from harness_design_studio.core.samples import mini3  # noqa: E402
from harness_design_studio.gui import strings  # noqa: E402
from tests.gui_helpers import hold_drc, make_window  # noqa: E402


def settle() -> None:
    for _ in range(3):
        QApplication.processEvents()


@pytest.fixture
def win(qtbot, tmp_path: Path):
    w = make_window(tmp_path)
    qtbot.addWidget(w)
    p = mini3()
    generate_project(p)
    save_project(p, tmp_path / "proj")
    assert w.open_project(tmp_path / "proj")
    hold_drc(w)
    return w


def steps(win) -> int:
    return len(win.ctl.history._undo)


def _connector(win, cid: str):
    return next(c for c in win.ctl.project.harnesses["W001"].connectors if c.id == cid)


def test_the_lengths_of_a_cable_connector_are_measured_to_the_choice_in_one_undo_step(win):
    ins = win.inspector
    ins.show_object("cable_end", "W001-P1")
    settle()
    box = ins.length_box
    assert box.isVisibleTo(ins) and box.choice.isEnabled()
    assert box.choice.count() == 3
    assert box.choice.itemText(0) == strings.INS_LENGTH_TO_PROJECT.format("rear")
    assert box.choice.currentData() == "" and box.choice.accessibleName() == strings.INS_LENGTH_TO
    n = steps(win)
    box.choice.setCurrentIndex(box.choice.findData("face"))
    assert box.apply()
    settle()
    assert _connector(win, "W001-P1").length_to == "face" and steps(win) == n + 1
    assert win.ctl.history._undo[-1].label == strings.STEP_SET_LENGTH_TO.format("W001-P1", "face")
    win.ctl.undo()
    settle()
    assert _connector(win, "W001-P1").length_to is None


def test_the_choice_is_off_for_a_released_harness(win):
    p = win.ctl.project
    p.harnesses["W001"] = evolve(p.harnesses["W001"], status="released")
    ins = win.inspector
    ins.show_object("cable_end", "W001-P2")
    settle()
    box = ins.length_box
    assert not box.choice.isEnabled()
    assert "released" in box.choice.toolTip()


def test_the_depth_of_a_connector_part_is_set_refused_when_it_is_not_a_number_and_cleared(win):
    ins = win.inspector
    part = _connector(win, "W001-P1").part_id
    ins.show_object("part", part)
    settle()
    box = ins.depth_box
    assert box.isVisibleTo(ins) and box.edit.text() == ""
    box.edit.setText("deep")
    assert not box.apply()
    assert box.error.isVisibleTo(box) and "deep" in box.error.text()
    n = steps(win)
    box.edit.setText("25,5")
    assert box.apply()
    settle()
    assert win.ctl.project.parts[part].depth_mm == 25.5 and steps(win) == n + 1
    box.edit.setText("")
    assert box.apply()
    assert win.ctl.project.parts[part].depth_mm is None


def test_a_part_of_another_category_shows_no_depth(win):
    ins = win.inspector
    wire_part = next(p.id for p in win.ctl.project.parts.values() if p.category == "wire")
    ins.show_object("part", wire_part)
    settle()
    assert not ins.depth_box.isVisibleTo(ins)


# ---- part B: the pin table column Current (A) (design of 5.0.0 section 5.1) ---------------------


def _devices_view(win, cid: str):
    from harness_design_studio.gui.devices_view import DevicesView

    view = win.findChild(DevicesView)
    unit = win.ctl.project.connectors[cid].unit_id
    assert view.show_unit(unit, cid)
    view.refresh()
    settle()
    return view


def test_the_current_column_shows_while_a_pin_of_the_connector_has_one_and_edits_in_one_step(win):
    p = win.ctl.project
    cid = next(c.id for c in p.connectors.values() if c.unit_id and c.pins)
    view = _devices_view(win, cid)
    col = view.pin_model.column_index("current_a")
    assert view.pin_model.columns[col].header == strings.DV_COL_CURRENT
    assert view.pin_table.isColumnHidden(col)  # no pin of the connector has a current
    pid = p.connectors[cid].pins[0].id
    row = view._pin_index[pid]
    assert view._validate_cell("current_a", {}, "two") is not None
    assert view._validate_cell("current_a", {}, "500 mA") is None
    n = steps(win)
    view.pin_model.cellEdited.emit(row, "current_a", "500 mA")
    view.refresh()
    settle()
    assert win.ctl.project.connectors[cid].pins[0].current_a == 0.5 and steps(win) == n + 1
    assert not view.pin_table.isColumnHidden(col)
    assert view.pin_model.row(view._pin_index[pid])["current_a"] == "0.5"
    win.ctl.undo()
    view.refresh()
    settle()
    assert win.ctl.project.connectors[cid].pins[0].current_a is None
    # shown from the column menu, it stays on this connector
    view.pin_table.setColumnHidden(col, False)
    view.refresh()
    settle()
    assert not view.pin_table.isColumnHidden(col)


# ---- pull request 4, part C: a splice in a harness made from a connection (section 6.4) ------


def _window_with(qtbot, tmp_path: Path, project):
    w = make_window(tmp_path)
    qtbot.addWidget(w)
    w.ctl._install(project, None, None)
    hold_drc(w)
    settle()
    return w


def test_the_link_window_takes_a_pin_paired_again_and_names_the_junction(qtbot):
    from harness_design_studio.gui.link_dialog import LinkDialog
    from harness_design_studio.gui.theme import ThemeManager
    from tests.test_link_junctions import star

    dlg = LinkDialog(None, ThemeManager(), star(), a_unit="PCDU1", b_unit="OBC1")
    qtbot.addWidget(dlg)
    dlg.show()
    assert [p for p in dlg.pairs() if p[0] == "1"] == [("1", "1")]  # the proposal: once
    for b_pin in ("2", "3"):
        dlg.a_pin.setCurrentIndex(dlg.a_pin.findData("1"))
        dlg.b_pin.setCurrentIndex(dlg.b_pin.findData(b_pin))
        dlg.add_pair.click()
    assert [p for p in dlg.pairs() if p[0] == "1"] == [("1", "1"), ("1", "2"), ("1", "3")]
    assert dlg.ok.isEnabled() and not dlg.problem.text()
    assert "Pin 1 of PCDU1-J01 is joined to pins 1, 2 and 3 of OBC1-J01 (a junction)" in dlg.review.text()  # fmt: skip


def test_create_harness_asks_for_the_splice_part_of_a_junction_and_makes_it_in_one_step(
    qtbot, tmp_path
):
    from harness_design_studio.gui.link_dialog import CreateHarnessDialog
    from tests.gui_helpers import DialogScript
    from tests.test_link_junctions import STAR, add_link, star

    p = star()
    add_link(p, STAR)
    win = _window_with(qtbot, tmp_path, p)
    shown = DialogScript(win)
    win.create_harness_flow("L1")
    dlg = shown.seen[0]
    assert isinstance(dlg, CreateHarnessDialog) and dlg.splice_part() == "EX-SPLICE-1"
    assert dlg.part is not None and dlg.part.accessibleName() == strings.LINK_HARNESS_SPLICE_PART
    assert "1 splice of EX-SPLICE-1 and 4 wires" in dlg.text.text()
    hid = win.ctl.project.links["L1"].harness_id
    h = win.ctl.project.harnesses[hid]
    assert [c.id for c in h.connectors if c.role == "splice"] == [f"{hid}-X1"]
    assert steps(win) == 1
    win.ctl.undo()
    assert not win.ctl.project.harnesses


def test_create_harness_without_a_splice_part_says_how(qtbot, tmp_path):
    from tests.gui_helpers import DialogScript
    from tests.test_link_junctions import STAR, add_link, star

    p = star()
    add_link(p, STAR)
    del p.parts["EX-SPLICE-1"]
    win = _window_with(qtbot, tmp_path, p)
    shown = DialogScript(win)
    said: list[str] = []
    win.toasts.show_message = lambda text, *a, **k: said.append(text)
    win.create_harness_flow("L1")
    assert not shown.seen and not win.ctl.project.harnesses
    assert said and "Choose a splice part (category splice)" in said[-1]


def test_the_splices_list_shows_the_pin_currents_of_each_node(qtbot, tmp_path):
    from harness_design_studio.gui.splice_panel import CURRENTS_COLUMN, splice_rows
    from tests.test_link_junctions import STAR, add_link, made, star

    p = star()
    add_link(p, STAR)
    hid = made(p, "L1")
    win = _window_with(qtbot, tmp_path, p)
    view = win.harness_view
    win.go_to("harness")
    assert view.select_harness(hid)
    view.refresh()
    settle()
    panel = view.splices
    assert panel.isVisibleTo(win) and not panel.table.isColumnHidden(CURRENTS_COLUMN)
    (row,) = splice_rows(p.harnesses[hid], p)
    assert row["currents"] == "6 A at PCDU1-J01.1; 2 A, 2 A and 2 A at OBC1-J01.1, .2 and .3: they add up"  # fmt: skip
    assert not panel.buttons["add"].isEnabled()  # F8: the connection owns the pins
    q = star(amps={})
    assert splice_rows(p.harnesses[hid], q)[0]["currents"] == ""


def test_check_my_connections_does_not_count_a_junction(qtbot, tmp_path):
    from tests.test_link_junctions import RETURN, STAR, add_link, star

    p = star()
    add_link(p, STAR + RETURN)
    win = _window_with(qtbot, tmp_path, p)
    said: list[str] = []
    win.toasts.show_message = lambda text, *a, **k: said.append(text)
    win.check_connections_flow()
    assert said[-1] == strings.LINK_CHECK_CLEAN  # the two junctions are infos, nothing to fix


# ---- pull request 5, part D: where a shield end lands (section 7.5) -----------------------------


def _shield_view(qtbot, theme):
    from tests.format5_support import format5_project
    from tests.test_ux_harness import make_view

    ctl, view = make_view(qtbot, theme, format5_project())
    view.select_harness("W001")
    view.refresh()
    ed = view.wire_editor
    ed.set_harness("W001")
    return ctl, ed


def _group(ctl, gid: str):
    return next(s for h in ctl.project.harnesses.values() for s in h.shields if s.id == gid)


def test_change_group_gives_a_generated_group_its_places_in_one_undo_step(qtbot):
    from PySide6.QtWidgets import QDialog

    from harness_design_studio.gui.harness_edit_dialogs import ChangeGroupDialog
    from harness_design_studio.gui.theme import ThemeManager

    ctl, ed = _shield_view(qtbot, ThemeManager())
    s3 = _group(ctl, "W001-S3")
    assert not s3.manual and (s3.end_a, s3.end_b) == ("pigtail", "backshell_360")
    ed.show_wires(list(s3.wire_ids))
    assert ed.change_group_btn.isVisibleTo(ed) and ed.change_group_btn.isEnabled()
    seen = []

    def run(dlg):
        seen.append(dlg)
        assert isinstance(dlg, ChangeGroupDialog)
        assert not dlg.kind.isEnabled() and not dlg.end_a.isEnabled() and not dlg.wires.isEnabled()
        assert dlg.pins["a"].isEnabled() and not dlg.pins["b"].isEnabled()  # end B: 360 degrees
        assert dlg.shells["b"].isEnabled()
        assert dlg.error.text() == strings.GD_SAME and not dlg.ok.isEnabled()
        dlg.pins["a"].setCurrentIndex(dlg.pins["a"].findData("10"))
        dlg.shells["b"].setCurrentIndex(dlg.shells["b"].findData("+"))  # Add a backshell…
        assert dlg.ok.isEnabled()
        return int(QDialog.DialogCode.Accepted)

    ed.run_dialog = run
    before = len(ctl.history._undo)
    assert ed.change_group()
    assert len(seen) == 1 and len(ctl.history._undo) == before + 1
    s3 = _group(ctl, "W001-S3")
    assert (s3.at_a.connector, s3.at_a.pin) == ("W001-P2", "10")
    assert (s3.at_b.connector, s3.at_b.backshell) == ("W001-P3", "ACC-001")
    assert any(a.id == "ACC-001" and a.kind == "backshell" for a in ctl.project.harnesses["W001"].accessories)  # fmt: skip
    ed.show_wires(list(s3.wire_ids))
    assert "end A pigtail to pin 10 at W001-P2" in ed.group_label.text()
    assert "end B backshell 360 (ACC-001) at W001-P3" in ed.group_label.text()


def test_the_place_fields_follow_the_kind_of_end_and_have_names(qtbot):
    from harness_design_studio.core.wires import plan_group_wires
    from harness_design_studio.gui.harness_edit_dialogs import ChangeGroupDialog
    from harness_design_studio.gui.theme import ThemeManager
    from tests.test_group_edit import mine

    p, hid, w = mine()
    from harness_design_studio.core.commands import apply_ops

    apply_ops(p, plan_group_wires(p, w[:2], "shielded_pair"))
    gid = p.harnesses[hid].shields[-1].id
    dlg = ChangeGroupDialog(None, ThemeManager(), p, gid)
    qtbot.addWidget(dlg)
    for box in (*dlg.pins.values(), *dlg.shells.values()):
        assert box.accessibleName() and box.toolTip(), box.objectName()
    dlg.end_a.setCurrentIndex(dlg.end_a.findData("pigtail"))
    assert dlg.pins["a"].isEnabled() and dlg.shells["a"].isEnabled()
    dlg.end_a.setCurrentIndex(dlg.end_a.findData("floating"))
    assert not dlg.pins["a"].isEnabled() and not dlg.shells["a"].isEnabled()
    dlg.end_a.setCurrentIndex(dlg.end_a.findData("pigtail"))
    dlg.kind.setCurrentIndex(dlg.kind.findData("twisted_pair"))
    assert not dlg.pins["a"].isEnabled()


def test_deleting_a_backshell_says_which_place_it_cleared(qtbot):
    from harness_design_studio.gui.accessory_editor import AccessoryEditor
    from harness_design_studio.gui.theme import ThemeManager
    from tests.format5_support import format5_project
    from tests.test_ux_harness import make_view

    ctl, _view = make_view(qtbot, ThemeManager(), format5_project())
    said = []
    ctl.message.connect(lambda text, _undo: said.append(text))
    acc = AccessoryEditor(ctl, ThemeManager())
    qtbot.addWidget(acc)
    acc.set_harness("W001")
    acc._selected = "W001-A1"
    acc.delete.setEnabled(True)
    assert acc.delete_accessory()
    assert _group(ctl, "W001-S2").at_b is None
    assert said[-1] == "W001-A1 is deleted, and the place of W001-S2 end B no longer names it."


# ---- part E: the checked state of a device (design of 5.0.0 sections 8.2 and 8.5) -------------


def test_mark_as_checked_in_the_devices_tab_in_one_undo_step_and_clear(win):
    from datetime import date

    from harness_design_studio.core import device_check as dc
    from harness_design_studio.gui.devices_dialogs import DeviceCheckDialog
    from tests.gui_helpers import DialogScript

    view = _devices_view(win, "OBC-J01")
    uid = view.unit_id()
    assert view.check_label.text() == dc.NOT_CHECKED
    assert view.check_btn.isEnabled() and not view.check_clear_btn.isVisibleTo(view)
    seen: list = []

    def fill(dlg):
        assert isinstance(dlg, DeviceCheckDialog)
        assert dlg.on.text() == date.today().isoformat() and dlg.icd.text() == ""
        assert not dlg.ok.isEnabled()  # no name, no ICD
        dlg.by.setText("A. Example")
        dlg.on.setText("2026-11-23")
        dlg.icd.setText("ICD-OBC Issue 1")
        assert dlg.ok.isEnabled()
        seen.append(dlg)

    DialogScript(win, fill)
    n = steps(win)
    view.check_btn.click()
    settle()
    assert seen and steps(win) == n + 1
    check = win.ctl.project.units[uid].checked
    assert (check.by, check.on, check.icd) == ("A. Example", "2026-11-23", "ICD-OBC Issue 1")
    assert win.ctl.history._undo[-1].label == strings.STEP_DEVICE_CHECKED.format(uid)
    view.refresh()
    settle()
    assert view.check_label.text() == "Checked by A. Example on 2026-11-23 against ICD-OBC Issue 1"
    assert view.check_clear_btn.isVisibleTo(view)
    view.check_clear_btn.click()
    settle()
    assert win.ctl.project.units[uid].checked is None and steps(win) == n + 2


def test_a_device_changed_since_the_check_says_so(win):
    from harness_design_studio.core import device_check as dc
    from harness_design_studio.core.commands import Put

    p = win.ctl.project
    uid = p.connectors["OBC-J01"].unit_id
    assert win.ctl.set_device_checked(uid, "A. Example", "2026-11-23", "ICD-OBC Issue 1")
    c = p.connectors["OBC-J01"]
    pins = [evolve(c.pins[0], function="changed"), *c.pins[1:]]
    assert win.ctl.run("edit", [Put("connectors", evolve(c, pins=pins))])
    view = _devices_view(win, "OBC-J01")
    assert view.check_label.text().endswith("; " + dc.CHANGED)
    assert view.check_label.toolTip() == strings.DV_CHECK_STALE_TIP


def test_the_check_dialog_proposes_the_icd_of_the_connectors(win):
    from harness_design_studio.gui.devices_dialogs import DeviceCheckDialog

    p = win.ctl.project
    uid = p.connectors["OBC-J01"].unit_id
    for cid in [c for c in p.connectors if p.connectors[c].unit_id == uid]:
        p.connectors[cid] = evolve(
            p.connectors[cid], source_doc="ICD-OBC", source_version="Issue 4"
        )
    dlg = DeviceCheckDialog(win, win.theme, p, uid, "2026-11-23")
    assert dlg.icd.text() == "ICD-OBC Issue 4"
    dlg.by.setText("A. Example")
    assert dlg.ok.isEnabled()
    dlg.on.setText("2026-02-30")
    assert not dlg.ok.isEnabled() and "date" in dlg.notice.text().lower()


def test_the_library_window_has_the_column_checked_and_marks_the_project_s_device(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    from harness_design_studio.cli.main import main
    from harness_design_studio.core import device_check as dc
    from harness_design_studio.gui.library_window import LibraryWindow

    lib = tmp_path / "lib"
    lib.mkdir()
    assert main(["new", str(tmp_path / "proj"), "--template", "first-steps"]) == 0
    assert main(["device-checked", str(tmp_path / "proj"), "RW1", "--by", "A. Example", "--icd", "ICD-RW Issue 2", "--date", "2026-11-23"]) == 0  # fmt: skip
    assert main(["save-device", str(tmp_path / "proj"), "RW1", "--library", str(lib)]) == 0
    w = make_window(tmp_path)
    qtbot.addWidget(w)
    assert w.open_project(tmp_path / "proj")
    hold_drc(w)
    win = LibraryWindow(w.ctl, w.theme, w.settings, w)
    qtbot.addWidget(win)
    win.set_folder(str(lib))
    qtbot.waitUntil(lambda: bool(win.list_model.rows()), timeout=5000)
    horizontal = Qt.Orientation.Horizontal
    names = [win.list_model.headerData(i, horizontal) for i in range(win.list_model.columnCount())]
    assert strings.LIB_COLUMN_CHECKED in names
    (row,) = [r for r in win.list_model.rows() if r["id"] == "RW1"]
    assert row["checked"] == "Checked by A. Example on 2026-11-23 against ICD-RW Issue 2"
    assert row["checked"] != dc.NOT_CHECKED
    asked: list[str] = []
    win.checkRequested.connect(asked.append)
    qtbot.waitUntil(lambda: win.check_btn.isEnabled(), timeout=5000)
    win.check_btn.click()
    assert asked == ["RW1"]


# ---- pull request 7: the rest of the editor (design of 5.0.0 sections 4.5, 5.3, 6.1, 7.3 to 7.5,
# 8.3 and 18) --------------------------------------------------------------------------------------


def _to_settings(win) -> None:
    win.set_area("settings")
    win.settings_page.show_section("project")
    win._show_segmentation()
    settle()


def _model(p) -> dict:
    cfg = p.config.get("model")
    return dict(cfg.values) if cfg is not None else {}


def test_settings_project_sets_where_the_segments_are_measured_to_in_one_undo_step(win):
    from harness_design_studio.core.generate.lengths import length_reference

    before = _model(win.ctl.project)
    _to_settings(win)
    page = win.settings_page
    combo = page.length_reference_combo
    assert combo.objectName() == "settings-length-reference" and combo.isEnabled()
    assert combo.accessibleName() == strings.SETTINGS_LENGTH_REFERENCE and combo.toolTip()
    assert combo.currentData() == "rear" and combo.count() == 2
    assert page.length_reference_about.text() == strings.SETTINGS_LENGTH_REFERENCE_ABOUT["rear"]
    n = steps(win)
    combo.setCurrentIndex(combo.findData("rear"))  # the choice in force: nothing is written
    assert steps(win) == n and _model(win.ctl.project) == before
    combo.setCurrentIndex(combo.findData("face"))
    settle()
    assert length_reference(win.ctl.project) == "face" and steps(win) == n + 1
    assert win.ctl.history._undo[-1].label == strings.STEP_SET_LENGTH_REFERENCE.format(
        strings.SETTINGS_LENGTH_REFERENCE_CHOICES["face"]
    )
    assert page.length_reference_about.text() == strings.SETTINGS_LENGTH_REFERENCE_ABOUT["face"]
    win.ctl.undo()
    settle()
    assert _model(win.ctl.project) == before and combo.currentData() == "rear"


def test_the_setting_is_off_in_a_read_only_project_and_a_newer_choice_is_shown(win):
    page = win.settings_page
    page.show_length_reference("middle")
    assert page.length_reference_combo.currentData() == "middle"
    assert page.length_reference_about.text() == strings.SETTINGS_LENGTH_REFERENCE_UNKNOWN.format(
        "middle"
    )
    win.ctl.project.read_only = True
    _to_settings(win)
    combo = page.length_reference_combo
    assert not combo.isEnabled() and combo.toolTip() == strings.WHY_READ_ONLY
    assert combo.count() == 2 and strings.WHY_READ_ONLY in page.length_reference_about.text()


def _format5_window(qtbot, tmp_path: Path):
    from tests.format5_support import format5_project

    win = _window_with(qtbot, tmp_path, format5_project())
    win.ctl.run_drc_now()
    win.ctl.wait_drc()
    plist = win.problems_list
    win.dock_problems.show()
    plist.refresh()
    settle()
    return win, plist


def _click(plist, pick) -> None:
    k = next(
        k for k in range(plist.table.proxy.rowCount())
        if pick(plist.table.row_at(plist.table.proxy.index(k, 0)))
    )  # fmt: skip
    plist._clicked(plist.table.proxy.index(k, 0))
    settle()


def test_the_problems_list_shows_the_infos_of_format_5_as_info_rows(qtbot, tmp_path):
    win, plist = _format5_window(qtbot, tmp_path)
    rows = plist.rows()
    infos = {(r["rule"], r["object_id"]) for r in rows if r["level"] == "info"}
    assert ("shield_place_not_stated", "W001-S2") in infos
    assert ("link_junction", "L1") in infos
    junction = next(r for r in rows if r["rule"] == "link_junction")
    assert junction["state"] == "info" and junction["why"] == strings.PROBLEMS_NOTE_WHY["link_junction"]  # fmt: skip
    assert junction["message"].startswith("Pin 1 of PCDU1-J01 is joined to pins 1, 2 and 3")
    pigtail = next(r for r in rows if r["rule"] == "shield_place_not_stated")
    assert pigtail["why"] == strings.PROBLEMS_NOTE_WHY["shield_place_not_stated"]
    # the warnings stay findings of model-inconsistent, as pull requests 2 to 6 made them
    warned = {r["object_id"] for r in rows if r["rule"] == "model-inconsistent"}
    assert {"W002-P2", "W001-009", "W002-S1", "OBC1"} <= warned
    win._update_problems_button()
    total = len(win.ctl.open_findings()) + len(win.ctl.layout_notes()) + len(win.ctl.check_notes())  # fmt: skip
    assert plist.total() == total == len(rows)
    assert win.problems_btn.text() == strings.PROBLEMS_BUTTON.format(total)
    plist.show_filter("links")  # the filter Connections keeps the info of the review
    kept = [plist.table.row_at(plist.table.proxy.index(k, 0))["rule"] for k in range(plist.table.proxy.rowCount())]  # fmt: skip
    assert "link_junction" in kept and "shield_place_not_stated" not in kept
    _click(plist, lambda r: r["rule"] == "link_junction")
    assert win.ctl.selected_link == "L1"


def test_a_net_that_was_not_worked_out_is_an_info_row(qtbot, tmp_path):
    from tests.test_pin_currents import parallel_project

    win = _window_with(qtbot, tmp_path, parallel_project(second={"gauge_awg": 20}))
    plist = win.problems_list
    win.dock_problems.show()
    plist.refresh()
    (row,) = [r for r in plist.rows() if r["rule"] == "current_not_worked_out"]
    assert row["level"] == "info" and row["object_id"] == "W001-001"
    assert row["why"] == strings.PROBLEMS_NOTE_WHY["current_not_worked_out"]
    assert "were not worked out" in row["message"]


def test_a_project_of_format_4_has_no_info_of_format_5(win):
    assert win.ctl.check_notes() == []


def test_a_click_on_a_shield_group_shows_its_harness_and_where_its_ends_land(qtbot, tmp_path):
    win, plist = _format5_window(qtbot, tmp_path)
    _click(plist, lambda r: r["rule"] == "shield_place_not_stated" and r["object_id"] == "W001-S2")
    assert win.main_tabs.currentWidget() is win.main_tabs.widget_of("harness")
    assert win.harness_view.harness_id() == "W001"
    assert win.inspector.current() == ("shield_group", "W001-S2")
    s2 = next(s for s in win.ctl.project.harnesses["W001"].shields if s.id == "W001-S2")
    assert win.harness_view.wire_editor.group_label.text().startswith(
        strings.WIRE_IN_GROUP.format(s2.kind.replace("_", " "), "W001-S2")
    )
    rows = {r["name"]: r for r in win.inspector.facts_table.source.rows()}
    assert rows[strings.INS_SG_END.format("A")]["value"] == "pigtail at W001-P3"
    assert rows[strings.INS_SG_END.format("A")]["state"] == "pending"
    assert rows[strings.INS_SG_END.format("A")]["status"] == strings.INS_SG_NOT_STATED
    assert rows[strings.INS_SG_END.format("B")]["value"] == "backshell 360 (W001-A1) at W001-P1"
    assert rows[strings.INS_SG_END.format("B")]["state"] is None
    assert win.inspector.facts_title.text() == "SHIELD GROUP W001-S2"
    # a warning about a group goes there too (the pigtail of W002-S1 on a wired pin)
    _click(plist, lambda r: r["rule"] == "model-inconsistent" and r["object_id"] == "W002-S1")
    assert win.inspector.current() == ("shield_group", "W002-S1")
    rows = {r["name"]: r for r in win.inspector.facts_table.source.rows()}
    assert rows[strings.INS_SG_END.format("A")]["value"] == "pigtail to pin 3 at W002-P1"


def test_a_place_that_names_another_connector_is_marked_in_the_inspector(qtbot, tmp_path):
    from harness_design_studio.core.model import ShieldEndPlace
    from harness_design_studio.gui.inspector import facts_for
    from tests.format5_support import format5_project

    p = format5_project()
    h = p.harnesses["W001"]
    shields = [
        evolve(s, at_a=ShieldEndPlace(connector="W001-P4", pin="9")) if s.id == "W001-S2" else s
        for s in h.shields
    ]
    p.harnesses["W001"] = evolve(h, shields=shields)
    rows = {r["name"]: r for r in facts_for(p, "shield_group", "W001-S2")}
    end_a = rows[strings.INS_SG_END.format("A")]
    assert end_a["state"] == "warning" and end_a["status"] == strings.INS_SG_MOVED.format("W001-P4")
    assert end_a["tip"] == strings.INS_SG_MOVED_TIP
    assert facts_for(p, "shield_group", "W009-S1") == []


def test_a_click_on_a_missing_depth_or_a_stale_check_goes_where_it_is_put_right(qtbot, tmp_path):
    win, plist = _format5_window(qtbot, tmp_path)
    _click(plist, lambda r: r["rule"] == "model-inconsistent" and r["object_id"] == "W002-P2")
    assert win.inspector.current() == ("cable_end", "W002-P2")
    assert win.inspector.length_box.isVisibleTo(win.inspector)  # Lengths measured to
    _click(plist, lambda r: r["rule"] == "model-inconsistent" and r["object_id"] == "OBC1")
    assert win.main_tabs.currentWidget() is win.main_tabs.widget_of("devices")
    assert win.devices_view.unit_id() == "OBC1"
    assert win.devices_view.check_btn.isVisibleTo(win.devices_view)  # Mark as checked…


def test_the_strings_of_pull_request_7_say_device_and_are_in_strings() -> None:
    names = [
        n
        for n in vars(strings)
        if n.startswith(("SETTINGS_LENGTH_REFERENCE", "INS_SG_", "PROBLEMS_NOTE_WHY"))
        or n in ("STEP_SET_LENGTH_REFERENCE", "LENGTH_REFERENCE_SET")
    ]
    assert len(names) >= 15
    for n in names:
        assert "unit" not in str(getattr(strings, n)).lower(), n
    assert set(strings.PROBLEMS_NOTE_WHY) == {
        "current_not_worked_out", "shield_place_not_stated", "link_junction",
    }  # fmt: skip
