# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,attr-defined,union-attr,arg-type,index"
"""REQ-GUI-32 (4.4.0, pull request 6; `docs/ait/DESIGN_4.4_NAMES_PORTS.md` sections 3.4, 3.5, 4.3,
5.4 and 8). The editor sets both settings of names and ports: *Settings > Project* has the check
box *Signal names name the far device* (`naming.far_device_names`) and the section *Signal map*
(`naming.signal_map`: a box of `TEAM NAME = SIGNAL` lines, *Take the names of a file…*, *Save*;
the check's refusal under the box), each change one undo step through the `configcheck.plan_set_*`
functions. *Choose port…* lists the far device's ports first and marks a port named after another
device; the Inspector warns under an end on such a port, as the verifier does; the window *Link
connectors* shows the notes of the pins of a third device. No written file changes. Every device
and signal name is made up (`OBC1`, `TTC1`)."""

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from harness_design_studio.core import configcheck, devices, signal_map  # noqa: E402
from harness_design_studio.core.commands import History  # noqa: E402
from harness_design_studio.core.generate.engine import generate_project  # noqa: E402
from harness_design_studio.core.links import far_device_names_on  # noqa: E402
from harness_design_studio.core.model import Project, evolve  # noqa: E402
from harness_design_studio.core.verify import verify_project  # noqa: E402
from harness_design_studio.gui import strings  # noqa: E402
from harness_design_studio.gui.link_dialog import LinkDialog  # noqa: E402
from harness_design_studio.gui.main_window import MainWindow  # noqa: E402
from harness_design_studio.gui.settings_page import signal_map_text  # noqa: E402
from harness_design_studio.gui.theme import ThemeManager  # noqa: E402
from tests.gui_helpers import DialogScript, make_window  # noqa: E402
from tests.test_links_far_device import NOTE_TTC1, two_transceivers  # noqa: E402
from tests.test_links_far_device import OBC as OBC_PINS  # noqa: E402
from tests.test_ports_far_device import OBC, port_of, project, switch  # noqa: E402

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "src/harness_design_studio/resources/examples/templates/signal-map.csv"
)
LINKS = [("IF-001", "TTC2"), ("IF-002", "TTC1")]  # the run of section 2.1: TTC2 has the lower ID


def window(qtbot, tmp_path: Path, p: Project) -> MainWindow:
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    win.ctl._install(p, None, None)
    win.ctl.set_mode("expert")
    QApplication.processEvents()
    return win


def to_settings(win: MainWindow) -> None:
    win.set_area("settings")
    win.settings_page.show_section("project")
    win._show_segmentation()


def naming(p: Project) -> dict[str, object]:
    cfg = p.config.get("naming")
    return dict(cfg.values) if cfg is not None else {}


def placed_by_4_3_0() -> Project:
    """The run of section 2.1 generated with the setting off: IF-001 (to TTC2) on port TTC1."""
    p = project(LINKS, on=False)
    generate_project(p)
    assert port_of(p, "IF-001") == {"TTC1"}
    return p


def end_k(p: Project, iid: str) -> int:
    return next(n for n, e in enumerate(p.interfaces[iid].endpoints) if e.connector_id == OBC)


def far_line(win: MainWindow, k: int) -> QLabel | None:
    return win.props.findChild(QLabel, f"end-port-far-{k}")


# ---- Settings > Project: the check box (part A, section 8.1) ----------------------------------


def test_the_check_box_switches_the_setting_as_one_undo_step(qtbot, tmp_path) -> None:
    p = project(LINKS, on=False)
    before = naming(p)
    win = window(qtbot, tmp_path, p)
    to_settings(win)
    page = win.settings_page
    box = page.far_device_box
    assert box.objectName() == "settings-far-device-names"
    assert box.text() == strings.SETTINGS_FAR_DEVICE_BOX == "Signal names name the far device"
    assert box.accessibleName() and box.toolTip() and box.isEnabled() and not box.isChecked()
    assert page.far_device_about.text() == strings.SETTINGS_FAR_DEVICE_OFF
    box.click()
    assert far_device_names_on(win.ctl.project) and naming(win.ctl.project)["far_device_names"] is True  # fmt: skip
    assert box.isChecked() and page.far_device_about.text() == strings.SETTINGS_FAR_DEVICE_ON
    assert win.ctl.history.next_undo_label == strings.STEP_FAR_DEVICE_ON
    win.ctl.undo()
    QApplication.processEvents()
    assert not far_device_names_on(win.ctl.project) and not box.isChecked()
    assert naming(win.ctl.project) == before  # the key is out again
    # on, then off with the box: off takes the key out, so the file is as it was
    box.click()
    box.click()
    assert win.ctl.history.next_undo_label == strings.STEP_FAR_DEVICE_OFF
    assert naming(win.ctl.project) == before and not box.isChecked()


def test_the_check_box_moves_the_ports_at_the_next_generate(qtbot, tmp_path) -> None:
    win = window(qtbot, tmp_path, placed_by_4_3_0())
    to_settings(win)
    win.settings_page.far_device_box.click()
    generate_project(win.ctl.project)
    assert port_of(win.ctl.project, "IF-001") == {"TTC2"}
    assert port_of(win.ctl.project, "IF-002") == {"TTC1"}


# ---- Settings > Project: the signal map (part C, section 5.4) ---------------------------------


def test_the_signal_map_is_saved_refused_and_undone_in_one_step(qtbot, tmp_path) -> None:
    win = window(qtbot, tmp_path, project(LINKS, on=False))
    to_settings(win)
    page = win.settings_page
    box = page.signal_map_box
    assert box.objectName() == "settings-signal-map" and box.accessibleName() and box.toolTip()
    assert box.toPlainText() == "" and page.signal_map_state.text() == strings.SETTINGS_SIGNAL_MAP_NONE  # fmt: skip
    for b in (page.signal_map_file, page.signal_map_save):
        assert b.accessibleName() and b.toolTip()
    box.setPlainText("TXP = TX+\nTXN=TX-\n\n")
    assert strings.SETTINGS_SIGNAL_MAP_EDITED in page.signal_map_state.text()
    assert signal_map.table(win.ctl.project) == {}  # nothing is saved until Save
    page.signal_map_save.click()
    assert signal_map.table(win.ctl.project) == {"TXP": "TX+", "TXN": "TX-"}
    assert win.ctl.history.next_undo_label == strings.STEP_SET_SIGNAL_MAP
    assert box.toPlainText() == "TXP = TX+\nTXN = TX-"
    assert page.signal_map_state.text() == strings.SETTINGS_SIGNAL_MAP_NOW.format(2)
    # a line that is not a pair, and a table the check refuses, say why under the box
    box.setPlainText("TXP = TX+\nRXP")
    page.signal_map_save.click()
    assert page.signal_map_error.isVisibleTo(page)
    assert page.signal_map_error.text() == strings.IMP_BAD_PAIR.format(strings.SETTINGS_SIGNAL_MAP_PAIR, "RXP")  # fmt: skip
    box.setPlainText("TXP = TXP")
    page.signal_map_save.click()
    assert page.signal_map_error.text() == (f"config/naming.json: signal_map {signal_map.WHY}.")
    assert box.toPlainText() == "TXP = TXP"  # the person's text stays
    assert signal_map.table(win.ctl.project) == {"TXP": "TX+", "TXN": "TX-"}
    # undo: the map before Save, and the box follows
    win.ctl.undo()
    QApplication.processEvents()
    win._show_segmentation()
    assert signal_map.table(win.ctl.project) == {} and box.toPlainText() == ""
    assert "signal_map" not in naming(win.ctl.project)


def test_an_empty_box_takes_the_map_out(qtbot, tmp_path) -> None:
    p = project(LINKS, on=False)
    History(p).execute("map", configcheck.plan_set_signal_map(p, {"TXP": "TX+"}).ops)
    win = window(qtbot, tmp_path, p)
    to_settings(win)
    page = win.settings_page
    assert page.signal_map_box.toPlainText() == "TXP = TX+"
    assert page.signal_map_state.text() == strings.SETTINGS_SIGNAL_MAP_NOW_ONE
    page.signal_map_box.setPlainText("  ")
    page.signal_map_save.click()
    assert "signal_map" not in naming(win.ctl.project)
    assert win.ctl.history.next_undo_label == strings.STEP_CLEAR_SIGNAL_MAP
    assert page.signal_map_state.text() == strings.SETTINGS_SIGNAL_MAP_NONE


def test_the_names_of_a_file_fill_the_box_and_a_bad_file_says_why(qtbot, tmp_path) -> None:
    win = window(qtbot, tmp_path, project(LINKS, on=False))
    to_settings(win)
    page = win.settings_page
    win.ask_open_path = lambda title, filters: str(TEMPLATE)
    page.signal_map_file.click()
    pairs = signal_map.read_file(TEMPLATE)
    assert page.signal_map_box.toPlainText() == signal_map_text(pairs)
    assert signal_map.table(win.ctl.project) == {}  # nothing is saved until Save
    page.signal_map_save.click()
    assert signal_map.table(win.ctl.project) == pairs and len(pairs) == 6
    # a JSON object
    f = tmp_path / "map.json"
    f.write_text(json.dumps({"TTC_TXP": "TX+"}), encoding="utf-8")
    win.ask_open_path = lambda title, filters: str(f)
    page.signal_map_file.click()
    assert page.signal_map_box.toPlainText() == "TTC_TXP = TX+"
    # a file that is not a map, a file with no pair, and a closed chooser
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2]", encoding="utf-8")
    win.ask_open_path = lambda title, filters: str(bad)
    page.signal_map_file.click()
    assert page.signal_map_error.isVisibleTo(page)
    assert page.signal_map_error.text() == "The signal map must be a JSON object of text to text."
    empty = tmp_path / "empty.csv"
    empty.write_text("net,signal\n", encoding="utf-8")
    win.ask_open_path = lambda title, filters: str(empty)
    page.signal_map_file.click()
    assert page.signal_map_error.text() == strings.SETTINGS_SIGNAL_MAP_EMPTY_FILE.format("empty.csv")  # fmt: skip
    win.ask_open_path = lambda title, filters: ""
    page.signal_map_file.click()
    assert page.signal_map_box.toPlainText() == "TTC_TXP = TX+"


def test_a_read_only_project_turns_both_settings_off_with_the_reason(qtbot, tmp_path) -> None:
    win = window(qtbot, tmp_path, project(LINKS, on=False))
    win.ctl.project.read_only = True
    to_settings(win)
    page = win.settings_page
    for w in (page.far_device_box, page.signal_map_box, page.signal_map_file, page.signal_map_save):
        assert not w.isEnabled(), w.objectName()
    assert strings.WHY_READ_ONLY in page.far_device_about.text()
    assert strings.WHY_READ_ONLY in page.signal_map_state.text()


def test_settings_are_saved_in_the_project_and_shown_when_it_opens_again(qtbot, tmp_path) -> None:
    from harness_design_studio.core.io.saver import save_project

    p = project(LINKS)
    History(p).execute("map", configcheck.plan_set_signal_map(p, {"RXP": "RX+"}).ops)
    save_project(p, tmp_path / "p")
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    assert win.open_project(tmp_path / "p")
    to_settings(win)
    assert win.settings_page.far_device_box.isChecked()
    assert win.settings_page.signal_map_box.toPlainText() == "RXP = RX+"


# ---- Choose port… (section 3.5) ---------------------------------------------------------------


def test_choose_port_lists_the_far_devices_port_first_and_marks_the_others(qtbot, tmp_path) -> None:
    p = project(LINKS)
    win = window(qtbot, tmp_path, p)
    k = end_k(p, "IF-001")
    win.ctl.select("interface", "IF-001")
    seen: dict[str, object] = {}

    def fn(dlg) -> None:
        box = dlg.port_box
        seen["items"] = [box.itemText(n) for n in range(box.count())]
        seen["tips"] = [box.itemData(n, Qt.ItemDataRole.ToolTipRole) for n in range(box.count())]
        seen["current"] = box.currentData()
        box.setCurrentIndex(1)  # another device's port can still be chosen, and is locked
        assert dlg.ok.isEnabled()

    DialogScript(win, fn)
    win.props.findChild(QPushButton, f"end-port-choose-{k}").click()
    assert seen["items"] == [
        "TTC2 (pins 5-8), named after TTC2 at the other end",
        "TTC1 (pins 1-4), named after TTC1",
    ]
    assert seen["current"] == "TTC2"
    assert seen["tips"][0] is None
    assert seen["tips"][1] == strings.PORT_ROW_OTHER_TIP.format(device="TTC1", far="TTC2", interface="IF-001")  # fmt: skip
    pins = win.ctl.project.connectors[OBC].pins
    assert [(x.interface_id, x.locked) for x in pins[:4]] == [("IF-001", True)] * 4
    # the Inspector then warns under the end: kept because a person locked the pins
    line = far_line(win, k)
    assert line is not None and line.text() == (
        f"{strings.SEV_WARNING} IF-001 goes to device TTC2 but uses port TTC1 of OBC1-J01, which"
        " is named after device TTC1 (Settings > Project: Signal names name the far device). It"
        " is kept because a person locked the pins."
    )
    win.ctl.undo()
    QApplication.processEvents()
    assert far_line(win, k) is None


def test_with_the_setting_off_choose_port_lists_the_ports_as_before(qtbot, tmp_path) -> None:
    p = project(LINKS, on=False)
    choices = devices.port_choices(p, OBC, "IF-001")
    assert [(c.port, c.device, c.far) for c in choices] == [
        ("TTC1", "", False),
        ("TTC2", "", False),
    ]
    win = window(qtbot, tmp_path, p)
    win.ctl.select("interface", "IF-001")
    seen: dict[str, object] = {}

    def fn(dlg) -> None:
        seen["items"] = [dlg.port_box.itemText(n) for n in range(dlg.port_box.count())]
        dlg.reject()

    DialogScript(win, fn)
    win.props.findChild(QPushButton, f"end-port-choose-{end_k(p, 'IF-001')}").click()
    assert seen["items"] == ["TTC1 (pins 1-4)", "TTC2 (pins 5-8)"]


def test_the_order_of_the_ports_far_device_then_no_device_then_others() -> None:
    p = project(LINKS, ports=("TTC1", "RS422_9", "TTC2"))
    got = [(c.port, c.device, c.far, c.other_device) for c in devices.port_choices(p, OBC, "IF-001")]  # fmt: skip
    assert got == [
        ("TTC2", "TTC2", True, ""),
        ("RS422_9", "", False, ""),
        ("TTC1", "TTC1", False, "TTC1"),
    ]


# ---- the Inspector's warning (section 3.4) ----------------------------------------------------


def test_the_inspector_warns_as_the_verifier_does(qtbot, tmp_path) -> None:
    p = placed_by_4_3_0()
    win = window(qtbot, tmp_path, p)
    k = end_k(p, "IF-001")
    win.ctl.select("interface", "IF-001")
    assert far_line(win, k) is None  # the setting is off
    to_settings(win)
    win.settings_page.far_device_box.click()
    win.ctl.select("interface", "IF-002")
    win.ctl.select("interface", "IF-001")
    line = far_line(win, k)
    assert line is not None and line.text() == (
        f"{strings.SEV_ERROR} IF-001 goes to device TTC2 but uses port TTC1 of OBC1-J01, which is"
        " named after device TTC1 (Settings > Project: Signal names name the far device)."
        " Regenerate, or choose the port of TTC2."
    )
    assert line.property("error") is True
    # the same facts as the verifier's error, with *device* on the screen for *unit* in the files
    (error,) = [
        i.message
        for i in verify_project(win.ctl.project).issues
        if i.code == "port_far_device" and "IF-001" in i.message
    ]
    words = line.text().removeprefix(f"{strings.SEV_ERROR} ")
    assert error == f"Interface {words}".replace("device ", "unit ").replace(
        "Settings > Project: Signal names name the far device", "naming.far_device_names"
    )


def test_the_warning_of_a_released_harness_and_none_on_the_right_port() -> None:
    p = placed_by_4_3_0()
    (hid,) = sorted(p.harnesses)
    p.harnesses[hid] = evolve(p.harnesses[hid], status="released", version="1.0.0")
    switch(p, True)
    w = devices.far_port_warning(p, "IF-001", OBC)
    assert w is not None and (w.port, w.far, w.device, w.kept, w.harness) == ("TTC1", "TTC2", "TTC1", "released", hid)  # fmt: skip
    assert strings.END_PORT_FAR_RELEASED.format(harness=hid, far="TTC2") in [
        i.message.split("). ", 1)[1]
        for i in verify_project(p).issues
        if i.code == "port_far_device"
    ]
    q = project(LINKS)
    generate_project(q)
    assert devices.far_port_warning(q, "IF-001", OBC) is None
    assert devices.far_port_warning(q, "IF-001", "TTC2-J01") is None  # no named port there
    assert devices.far_port_warning(placed_by_4_3_0(), "IF-001", OBC) is None  # the setting is off


# ---- the window Link connectors: the notes of a third device's pins (section 4.3) --------------


def test_the_link_window_shows_the_notes_of_a_third_devices_pins(qtbot) -> None:
    _ = QApplication.instance() or QApplication([])
    p = two_transceivers(OBC_PINS, ["TX", "RX", "PPS"], on=True)
    dlg = LinkDialog(None, ThemeManager(), p, a_unit="OBC1", b_unit="TTC2")
    qtbot.addWidget(dlg)
    dlg.show()
    assert len(dlg.pairs()) == 3
    assert dlg.notes.isVisibleTo(dlg) and NOTE_TTC1 in dlg.notes.text().splitlines()
    off = two_transceivers(OBC_PINS, ["TX", "RX", "PPS"], on=False)
    plain = LinkDialog(None, ThemeManager(), off, a_unit="OBC1", b_unit="TTC2")
    qtbot.addWidget(plain)
    plain.show()
    assert NOTE_TTC1 not in plain.notes.text()


# ---- the words ----------------------------------------------------------------------------------


def test_the_screen_says_device_and_every_new_string_is_in_strings() -> None:
    names = [
        n
        for n in vars(strings)
        if n.startswith(("SETTINGS_FAR_DEVICE", "SETTINGS_SIGNAL_MAP", "END_PORT_FAR", "PORT_ROW_"))
        or n
        in (
            "STEP_FAR_DEVICE_ON",
            "STEP_FAR_DEVICE_OFF",
            "FAR_DEVICE_SET_ON",
            "FAR_DEVICE_SET_OFF",
        )  # fmt: skip
    ]
    assert len(names) >= 25
    for n in names:
        assert "unit" not in str(getattr(strings, n)).lower(), n
    assert strings.SETTINGS_FAR_DEVICE_BOX in NOTE_TTC1  # the link notes name the box
