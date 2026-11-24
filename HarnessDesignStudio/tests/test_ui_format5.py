# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index,union-attr"
"""The editor's fields of format 5 (design of 5.0.0 `docs/ait/DESIGN_5.0_FORMAT_5.md` section
4.5; offscreen). Pull request 2, part A: the Inspector of a cable connector has *Lengths measured
to* (the project's, rear or face; one undo step; also on a harness Generate made, which keeps it;
off for a released harness), and the Inspector of a connector or backshell part has *Depth (mm)*
(one undo step; an empty field clears it; refused while a released harness uses the part). Pull
request 3, part B: the Devices tab's pin table has the column *Current (A)*, shown while a pin of
the connector has a current (and from the column menu), edited in place in one undo step, a value
that is not a current refused before it is sent. Pull request 4, part C: the Link window takes a
pin paired again by hand and names the junction under the table; *Create harness* asks for the
splice part of a connection with a junction (and says how to get one when the library has none);
the *Splices* list shows the pin currents of the net of each node. The later pull requests add
their fields here."""

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
