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
that is not a current refused before it is sent. The later pull requests add their fields here."""

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
