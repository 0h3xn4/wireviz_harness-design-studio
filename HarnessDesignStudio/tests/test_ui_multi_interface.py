# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,union-attr,arg-type,var-annotated,attr-defined"
"""Several interfaces on one device connector in the editor screens (D-237, pull request 5 of
`docs/ait/DESIGN_2.1_PORTS.md`): Expert mode connects to a connector in use that has room and says
the note, a full one is refused with the reason; Guided mode takes a shared port (tier 2); the
Inspector shows the port of each end with *Choose port…*; one *Confirm* per interface; the port
side on the canvas is the first interface by ID; the Devices tab has a derived Port column and
shows the port notes (CD-K9); *Assign to interface…* offers a port. Offscreen, example data."""

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton  # noqa: E402

from harness_design_studio.core import devices, edit  # noqa: E402
from harness_design_studio.core.generate.engine import generate_project  # noqa: E402
from harness_design_studio.core.model import Pin, Project  # noqa: E402
from harness_design_studio.gui import strings  # noqa: E402
from tests.gui_helpers import (  # noqa: E402
    DialogScript,
    click_unit,
    make_window,
    pick_connect_type,
)
from tests.test_multi_interface_connector import add, end_at, obc, port_pins  # noqa: E402


def window(qtbot, tmp_path, p: Project, mode: str = "expert"):
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    win.ctl._install(p, None, None)
    win.ctl.set_mode(mode)
    return win


def said(win) -> list[str]:
    out: list[str] = []
    win.ctl.message.connect(lambda text, _ok: out.append(text))
    return out


def new_ids(win, before: set[str]) -> list[str]:
    return sorted(set(win.ctl.project.interfaces) - before)


def form_label(win, name: str) -> str:
    lab = win.props.findChild(QLabel, name)
    return lab.text() if lab is not None else ""


# ---- Expert mode: a connector in use with room, and a full one ----------------------------------


def test_expert_connects_to_a_busy_connector_with_room_and_says_the_note(qtbot, tmp_path) -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    a = add(p, "OBC1", "ST1")
    win = window(qtbot, tmp_path, p)
    messages = said(win)
    pick_connect_type(win, "rs422")
    assert win.ctl.connector_compat("OBC1-J1").ok  # in use, with a free port
    before = set(win.ctl.project.interfaces)
    click_unit(win, "OBC1", port="OBC1-J1")
    # the far end is known now: the note is the one the hover tip shows
    far = edit.connector_compat(
        win.ctl.project, "rs422", "OBC1-J1", far_unit="ST2", far_connector="ST2-J02"
    )
    assert far.ok and "second harness" in far.note
    click_unit(win, "ST2", port="ST2-J02")
    (b,) = new_ids(win, before)
    assert end_at(win.ctl.project, b, "OBC1") == "OBC1-J1"
    assert messages[-1] == f"{strings.IF_ADDED.format(b)} {far.note}"
    assert f"OBC1-J1 also carries {a} to another connector" in messages[-1]


def test_expert_refuses_a_full_connector_with_the_reason(qtbot, tmp_path) -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2")), ("J2", [Pin(id=str(k)) for k in range(1, 9)]))
    a = add(p, "OBC1", "ST1")
    b = add(p, "OBC1", "ST2", "OBC1-J1", "ST2-J02")
    c = add(p, "OBC1", "ST3")
    assert end_at(p, c, "OBC1") == "OBC1-J2"
    win = window(qtbot, tmp_path, p)
    messages = said(win)
    pick_connect_type(win, "rs422")
    compat = win.ctl.connector_compat("OBC1-J1")
    why = f"OBC1-J1 cannot take another RS-422: its RS-422 ports RS422_1, RS422_2 are used by {a}, {b}."
    assert not compat.ok and compat.short == strings.CONNECTOR_FULL and compat.why == why
    before = set(win.ctl.project.interfaces)
    click_unit(win, "OBC1", port="OBC1-J1")
    assert messages[-1] == why and win.ctl.connect_from is None
    assert new_ids(win, before) == []
    # the Inspector's end list shows the full connector, not offered, with the reason
    win.ctl.end_connect()
    win.ctl.select("interface", c)
    combo = win.props.findChild(QComboBox, "end-0")
    model = combo.model()
    rows = {model.item(k).text(): model.item(k) for k in range(model.rowCount())}
    assert "J2" in rows and "J1: Full" in rows
    assert rows["J1: Full"].flags() == Qt.ItemFlag.NoItemFlags
    assert rows["J1: Full"].toolTip() == why


def test_the_end_list_offers_a_shared_connector_with_its_note(qtbot, tmp_path) -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2")), ("J2", [Pin(id=str(k)) for k in range(1, 9)]))
    add(p, "OBC1", "ST1")
    c = add(p, "OBC1", "ST2")
    assert end_at(p, c, "OBC1") == "OBC1-J2"
    win = window(qtbot, tmp_path, p)
    win.ctl.select("interface", c)
    combo = win.props.findChild(QComboBox, "end-0")
    model = combo.model()
    rows = {model.item(k).text(): model.item(k) for k in range(model.rowCount())}
    assert set(rows) == {"J1", "J2"} and combo.currentText() == "J2"
    assert "second harness" in rows["J1"].toolTip()
    combo.setCurrentIndex(combo.findText("J1"))
    combo.activated.emit(combo.currentIndex())
    assert end_at(win.ctl.project, c, "OBC1") == "OBC1-J1"


# ---- Guided mode: tier 2 ------------------------------------------------------------------------


def test_guided_takes_a_free_port_of_a_shared_connector(qtbot, tmp_path) -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    add(p, "OBC1", "ST1")
    win = window(qtbot, tmp_path, p, mode="guided")
    pick_connect_type(win, "rs422")
    assert win.ctl.unit_compat("OBC1").ok  # no free connector, a free port RS422_2
    before = set(win.ctl.project.interfaces)
    click_unit(win, "OBC1")
    click_unit(win, "ST2")
    (b,) = new_ids(win, before)
    end = next(e for e in win.ctl.project.interfaces[b].endpoints if e.unit_id == "OBC1")
    assert end.connector_id == "OBC1-J1" and end.auto
    port = devices.end_port(win.ctl.project, b, "OBC1-J1")
    assert port is not None and port.port == "RS422_2" and port.how == "planned"


# ---- the Inspector: the port of an end and Choose port… ----------------------------------------


def test_inspector_shows_the_port_and_choose_port_locks_it_and_undo_restores(
    qtbot, tmp_path
) -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2", "RS422_3")))
    a = add(p, "OBC1", "ST1")
    b = add(p, "OBC1", "ST2", "OBC1-J1", "ST2-J02")
    win = window(qtbot, tmp_path, p)
    win.ctl.select("interface", b)
    k = next(n for n, e in enumerate(p.interfaces[b].endpoints) if e.unit_id == "OBC1")
    assert (
        form_label(win, f"end-port-line-{k}") == "Port RS422_2 (pins 5-8), Generate will choose it"
    )
    generate_project(win.ctl.project)
    win.ctl._install(win.ctl.project, None, None)
    win.ctl.select("interface", b)
    assert form_label(win, f"end-port-line-{k}") == "Port RS422_2 (pins 5-8), chosen by Generate"
    seen: dict[str, object] = {}

    def fn(dlg):
        box = dlg.port_box
        seen["items"] = [box.itemText(n) for n in range(box.count())]
        seen["current"] = box.currentData()
        assert dlg.ok.isEnabled()
        box.setCurrentIndex(0)  # RS422_1: the pins of a
        assert not dlg.ok.isEnabled()
        assert dlg.notice.label.text() == f"Pin 1 carries {a}; unassign it first."
        box.setCurrentIndex(2)
        assert dlg.ok.isEnabled()

    DialogScript(win, fn)
    win.props.findChild(QPushButton, f"end-port-choose-{k}").click()
    assert seen["items"] == ["RS422_1 (pins 1-4)", "RS422_2 (pins 5-8)", "RS422_3 (pins 9-12)"]
    assert seen["current"] == "RS422_2"
    chooser = [
        x
        for x in win.inspector._field_widgets("interface", b)
        if x[0].objectName().startswith("end-port-choose-")
    ]
    assert [(kind, oid, fld) for _w, kind, oid, fld in chooser] == [("interface", b, "endpoints")]
    pins = win.ctl.project.connectors["OBC1-J1"].pins
    assert [(x.id, x.interface_id, x.locked) for x in pins[8:]] == [
        (str(n), b, True) for n in range(9, 13)
    ]
    # the pins Generate gave b before lose it in the same step (and keep their names)
    assert [(x.interface_id, x.signal) for x in pins[4:8]] == [
        (None, f"RS422_2_{s}") for s in ("TX+", "TX-", "RX+", "RX-")
    ]
    assert win.ctl.history.next_undo_label == f"Assign port RS422_3 to {b}"
    assert form_label(win, f"end-port-line-{k}") == "Port RS422_3 (pins 9-12), locked"
    win.ctl.undo()
    pins = win.ctl.project.connectors["OBC1-J1"].pins
    assert not any(x.locked for x in pins)
    assert [x.interface_id for x in pins[4:8]] == [b] * 4
    assert form_label(win, f"end-port-line-{k}") == "Port RS422_2 (pins 5-8), chosen by Generate"


def test_no_port_line_without_named_ports(qtbot, tmp_path) -> None:
    p = obc(("J1", [Pin(id=str(k)) for k in range(1, 9)]))
    a = add(p, "OBC1", "ST1")
    win = window(qtbot, tmp_path, p)
    win.ctl.select("interface", a)
    assert win.props.findChild(QPushButton, "end-port-choose-0") is None
    assert win.props.findChild(QPushButton, "end-port-choose-1") is None


# ---- one Confirm per interface ------------------------------------------------------------------


def test_one_confirm_per_interface_the_tool_chose_a_connector_for(qtbot, tmp_path) -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    a = add(p, "OBC1", "ST1")
    b = add(p, "OBC1", "ST2")  # tier 2: the free port of J1, chosen by the tool too
    assert end_at(p, b, "OBC1") == "OBC1-J1"
    win = window(qtbot, tmp_path, p)
    win.ctl.select("unit", "OBC1")
    buttons = {
        x.objectName(): x
        for x in win.props.findChildren(QPushButton)
        if x.objectName().startswith("confirm-")
    }
    assert set(buttons) == {f"confirm-OBC1-J1-{a}", f"confirm-OBC1-J1-{b}"}
    assert buttons[f"confirm-OBC1-J1-{b}"].text() == f"Confirm {b}"
    # a release that locks an interface disables its own Confirm only
    locked = {
        w.objectName(): (kind, oid, fld)
        for w, kind, oid, fld in win.inspector._field_widgets("unit", "OBC1")
        if w.objectName().startswith("confirm-")
    }
    assert locked == {
        f"confirm-OBC1-J1-{a}": ("interface", a, "endpoints"),
        f"confirm-OBC1-J1-{b}": ("interface", b, "endpoints"),
    }
    buttons[f"confirm-OBC1-J1-{b}"].click()
    ends = {
        i: e.auto
        for i in (a, b)
        for e in win.ctl.project.interfaces[i].endpoints
        if e.unit_id == "OBC1"
    }
    assert ends == {a: True, b: False}
    left = [x for x in win.props.findChildren(QPushButton) if x.objectName().startswith("confirm-")]
    assert [x.objectName() for x in left] == [f"confirm-OBC1-J1-{a}"]
    assert left[0].text() == strings.CONFIRM


# ---- the canvas: the side of a shared port ------------------------------------------------------


def test_the_port_side_follows_the_first_interface_by_id(qtbot, tmp_path) -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    a = add(p, "OBC1", "ST1")
    b = add(p, "OBC1", "ST2", "OBC1-J1", "ST2-J02")
    assert a < b
    win = window(qtbot, tmp_path, p)
    scene = win.view.dscene
    assert scene.connector_link("OBC1-J1") == a  # not the last one
    item = scene.unit_items["OBC1"]
    assert item.port_side("OBC1-J1") == item.link_side(a)


# ---- the Devices tab: the Port column, the port notes, Assign to interface… --------------------


def test_devices_tab_shows_the_port_of_each_pin_and_the_interface_on_it(qtbot, tmp_path) -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2", "RS422_3")))
    a = add(p, "OBC1", "ST1")
    b = add(p, "OBC1", "ST2", "OBC1-J1", "ST2-J02")
    generate_project(p)
    win = window(qtbot, tmp_path, p)
    win.go_actions["devices"].trigger()
    win.ctl.select("unit", "OBC1")
    dv = win.devices_view
    dv.refresh()
    m = dv.pin_model
    col = m.column_index("port")
    assert m.headerData(col, Qt.Orientation.Horizontal) == strings.DV_COL_PORT
    cells = [m.text_at(r, col) for r in range(m.rowCount())]
    assert cells == [f"RS422_1 ({a})"] * 4 + [f"RS422_2 ({b})"] * 4 + ["RS422_3"] * 4
    # derived: the project and the exported pinout do not have it
    assert "RS422_1 (" not in dv.table_bytes("csv").decode("utf-8")


def test_devices_tab_shows_the_port_notes_under_the_pin_table(qtbot, tmp_path) -> None:
    pins = port_pins("RS422_1", "RS422_2")[:7]  # RS422_2 has no RX-
    p = obc(("J1", pins), sensors=0)
    win = window(qtbot, tmp_path, p)
    win.go_actions["devices"].trigger()
    win.ctl.select("unit", "OBC1")
    dv = win.devices_view
    dv.refresh()
    notes = [(r["check"], r["message"]) for r in dv.note_model.rows()]
    assert (
        "CD-K9",
        "Port RS422_2 of OBC1-J1 has no pin for RX-, so it is not offered for RS-422.",
    ) in notes
    col = dv.pin_model.column_index("port")
    assert [dv.pin_model.text_at(r, col) for r in range(7)] == ["RS422_1"] * 4 + [""] * 3


def test_assign_to_interface_offers_the_port_the_selected_pins_form(qtbot, tmp_path) -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    a = add(p, "OBC1", "ST1")
    win = window(qtbot, tmp_path, p)
    win.go_actions["devices"].trigger()
    seen: dict[str, object] = {}

    def fn(dlg):
        box = dlg.port_box
        seen["items"] = [box.itemText(n) for n in range(box.count())]
        seen["current"] = dlg.port()
        seen["signals"] = dlg.form_host.isEnabled()
        assert dlg.ok.isEnabled()

    DialogScript(win, fn)
    win.assign_pins_flow("OBC1-J1", ["5", "6", "7", "8"])
    assert seen == {
        "items": [strings.DVD_ASSIGN_PORT_PINS, "RS422_1 (pins 1-4)", "RS422_2 (pins 5-8)"],
        "current": "RS422_2",
        "signals": False,
    }
    pins = win.ctl.project.connectors["OBC1-J1"].pins
    assert [(x.signal, x.interface_id, x.locked, x.fixed) for x in pins[4:]] == [
        (f"RS422_2_{s}", a, True, True) for s in ("TX+", "TX-", "RX+", "RX-")
    ]
    assert win.ctl.history.next_undo_label == f"Assign port RS422_2 to {a}"


def test_assign_to_interface_without_ports_has_no_port_list(qtbot, tmp_path) -> None:
    p = obc(("J1", [Pin(id=str(k)) for k in range(1, 9)]))
    a = add(p, "OBC1", "ST1")
    win = window(qtbot, tmp_path, p)

    def fn(dlg):
        assert dlg.port_box.isHidden() and dlg.port() == ""
        assert dlg.interface_id() == a

    DialogScript(win, fn, accept=False)
    win.assign_pins_flow("OBC1-J1", ["1", "2", "3", "4"])
