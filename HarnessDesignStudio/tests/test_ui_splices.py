# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,attr-defined,union-attr,arg-type,type-arg,assignment,index,misc,func-returns-value"
"""REQ-HARN-04. The splices in the editor (format 3, M6a; section 6.6 of the design of 2.3.0): the
Harness tab's *Splices* under the routing, for a harness a person made: *Add splice* of the chosen
splice part, *Splice this wire* (the wire chosen in the wire table, at the node chosen here) and
*Delete splice*, each one undo step; a harness of Generate shows nothing, a released one says why,
a library without a splice part says how to get one. The background design rule check is held
(`hold_drc`) so that its result cannot change the window under the test."""

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtWidgets import QApplication  # noqa: E402

from harness_design_studio.core import splices  # noqa: E402
from harness_design_studio.core.commands import Put  # noqa: E402
from harness_design_studio.core.model import evolve  # noqa: E402
from harness_design_studio.core.wires import released_text  # noqa: E402
from harness_design_studio.gui import strings  # noqa: E402
from harness_design_studio.gui.wrap_label import breakable  # noqa: E402
from tests.gui_helpers import hold_drc, make_window  # noqa: E402
from tests.splice_support import SPLICE_PART  # noqa: E402
from tests.test_splices import straight  # noqa: E402


def settle() -> None:
    for _ in range(3):
        QApplication.processEvents()


def window_with(tmp_path, project):
    win = make_window(tmp_path)
    win.ctl._install(project, None, None)
    hold_drc(win)
    settle()
    return win


def panel_of(win, hid):
    view = win.harness_view
    win.go_to("harness")
    assert view.select_harness(hid)
    view.refresh()
    settle()
    return view.splices


def steps(win) -> int:
    return len(win.ctl.history._undo)


def choose_wire(win, wire_id):
    view = win.harness_view
    table = view.wire_table
    model = table.source
    for r in range(model.rowCount()):
        row = model.row(r)
        if isinstance(row, dict) and row.get("id") == wire_id:
            table.selectRow(table.proxy.mapFromSource(model.index(r, 0)).row())
            settle()
            return
    raise AssertionError(wire_id)


def test_add_splice_this_wire_and_delete_are_each_one_undo_step(qtbot, tmp_path):
    p, hid = straight()
    win = window_with(tmp_path, p)
    qtbot.addWidget(win)
    panel = panel_of(win, hid)
    assert panel.isVisible() and panel.note.text() == breakable(strings.SP_EMPTY)
    assert panel.part.currentData() == SPLICE_PART
    assert panel.buttons["add"].isEnabled()
    assert not panel.buttons["splice_wire"].isEnabled() and not panel.buttons["delete"].isEnabled()
    n = steps(win)
    panel.buttons["add"].click()
    settle()
    h = win.ctl.project.harnesses[hid]
    assert [c.id for c in h.connectors if c.role == "splice"] == [f"{hid}-X1"]
    assert steps(win) == n + 1 and panel.picked() == (f"{hid}-X1", "1")
    assert panel.buttons["splice_wire"].isEnabled()
    # no wire chosen: the reason in the error line, nothing changes
    win.harness_view.wire_table.clearSelection()
    settle()
    assert not panel.splice_wire()
    assert panel.error.isVisibleTo(panel) and panel.error.text() == strings.SP_PICK_WIRE
    choose_wire(win, f"{hid}-001")
    win.harness_view.refresh()
    panel.pick(f"{hid}-X1")
    assert panel.splice_wire()
    settle()
    h = win.ctl.project.harnesses[hid]
    assert [(w.id, w.from_connector, w.to_connector) for w in h.wires] == [
        (f"{hid}-001", f"{hid}-P1", f"{hid}-X1"),
        (f"{hid}-002", f"{hid}-X1", f"{hid}-P2"),
    ]
    assert steps(win) == n + 2
    win.harness_view.refresh()
    settle()
    assert panel.model.rows()[0]["wires"] == f"{hid}-001, {hid}-002"
    assert panel.note.text() == breakable(strings.SP_HINT)
    panel.pick(f"{hid}-X1")
    assert panel.delete_splice()
    h = win.ctl.project.harnesses[hid]
    assert [w.id for w in h.wires] == [f"{hid}-001"] and steps(win) == n + 3
    assert all(c.role != "splice" for c in h.connectors)
    win.ctl.undo()
    assert len(win.ctl.project.harnesses[hid].wires) == 2


def test_a_wire_with_a_length_of_its_own_is_refused_in_the_error_line(qtbot, tmp_path):
    p, hid = straight()
    h = p.harnesses[hid]
    p.harnesses[hid] = evolve(h, wires=[evolve(h.wires[0], length_m=1.5)])
    win = window_with(tmp_path, p)
    qtbot.addWidget(win)
    panel = panel_of(win, hid)
    assert panel.add_splice()
    choose_wire(win, f"{hid}-001")
    win.harness_view.refresh()
    panel.pick(f"{hid}-X1")
    n = steps(win)
    assert not panel.splice_wire()
    assert "length of its own" in panel.error.text() and steps(win) == n


def test_a_harness_of_generate_shows_no_splices_and_a_released_one_says_why(qtbot, tmp_path):
    p, hid = straight()
    win = window_with(tmp_path, p)
    qtbot.addWidget(win)
    assert not panel_of(win, "W002").isVisible()  # made by Generate: no splice there
    h = win.ctl.project.harnesses[hid]
    assert win.ctl.run("release", [Put("harnesses", evolve(h, status="released"))])
    panel = panel_of(win, hid)
    assert not panel.isVisible()  # released and without a splice: nothing to place or show
    assert splices.refusal(win.ctl.project, hid) == released_text(win.ctl.project.harnesses[hid])


def test_a_library_without_a_splice_part_says_how_to_get_one(qtbot, tmp_path):
    p, hid = straight()
    del p.parts[SPLICE_PART]
    win = window_with(tmp_path, p)
    qtbot.addWidget(win)
    panel = panel_of(win, hid)
    assert panel.note.text() == breakable(strings.SP_NO_PART)
    assert not panel.buttons["add"].isEnabled() and not panel.part.isVisible()
