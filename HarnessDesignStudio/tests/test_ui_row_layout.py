# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,attr-defined,index,union-attr,arg-type"
"""The row layout of a connector in the editor (format 4; design of 4.0.0 section 9, pull request
5): the Devices tab's *Pin rows* row and its pin table column, the dialog *Pin rows of …* (valid
and invalid text, the row lengths, the three buttons, one undo step each), the Inspector of a
connector part and of a cable connector, and the Problems list with the checks of section 4.3.
Offscreen, on `tests.row_layout_support.row_layout_project` (the part `EX-MICROD-9-F` has the rows
`1 3 / 2`, the box connector `RW1-J02` its own rows `5 4 / 1`)."""

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtWidgets import QApplication  # noqa: E402

from harness_design_studio.core.model import evolve  # noqa: E402
from harness_design_studio.core.row_layout import parse_text  # noqa: E402
from harness_design_studio.gui import strings  # noqa: E402
from harness_design_studio.gui.inspector import facts_for  # noqa: E402
from harness_design_studio.gui.problems_panel import rows_target  # noqa: E402
from harness_design_studio.gui.row_layout_dialog import (  # noqa: E402
    PinRowsDialog,
    parse_lines,
    row_lines,
    rows_words,
)
from harness_design_studio.gui.theme import ThemeManager  # noqa: E402
from tests.gui_helpers import DialogScript, hold_drc, make_window  # noqa: E402
from tests.row_layout_support import OWN, PART, row_layout_project  # noqa: E402
from tests.test_accessibility import unnamed  # noqa: E402


def settle() -> None:
    for _ in range(3):
        QApplication.processEvents()


def window_with(tmp_path, project=None):
    win = make_window(tmp_path)
    win.ctl._install(project or row_layout_project(), None, None)
    hold_drc(win)
    settle()
    return win


def steps(win) -> int:
    return len(win.ctl.history._undo)


def devices_at(win, cid: str):
    win.go_to("devices")
    view = win.devices_view
    assert view.select_connector(cid)
    settle()
    return view


def pin_column(view) -> tuple[bool, list[str]]:
    """(hidden, the Pin row cells in pin order) of the pin table."""
    col = view.pin_model.column_index("pin_row")
    cells = [view.pin_model.text_at(r, col) for r in range(view.pin_model.rowCount())]
    return view.pin_table.isColumnHidden(col), cells


def dialog(project, **target) -> PinRowsDialog:
    return PinRowsDialog(None, ThemeManager(), project, **target)


# ---- the words ---------------------------------------------------------------------------------


def test_the_words_say_where_the_rows_come_from() -> None:
    p = row_layout_project()
    assert rows_words(p, p.connectors["OBC-J02"]) == "1 3 / 2, from part EX-MICROD-9-F"
    assert rows_words(p, p.connectors[OWN]) == "5 4 / 1, own rows"
    assert rows_words(p, p.connectors["OBC-J01"]) == strings.ROWS_NONE
    plug = next(c for c in p.harnesses["W002"].connectors if c.id == "W002-P2")
    assert rows_words(p, plug) == ("5 4 / 1, from RW1-J02, the device connector it plugs into")
    assert row_lines(parse_text("1–11 / 12–21")) == "1–11\n12–21"
    assert parse_lines("1–11\n\n12–21\n", rings=True) == parse_text("1–11 / 12–21 (rings)")
    assert parse_lines("  \n", rings=False) is None


# ---- the Devices tab: the row Pin rows and the pin table column -----------------------------------


def test_the_pin_table_line_shows_the_pin_rows_and_their_source(qtbot, tmp_path) -> None:
    win = window_with(tmp_path)
    qtbot.addWidget(win)
    view = devices_at(win, "OBC-J02")
    assert view.rows_text.text() == strings.DV_ROWS_LINE.format("1 3 / 2, from part EX-MICROD-9-F")
    assert view.rows_btn.isEnabled() and view.rows_btn.accessibleName() == strings.DV_ROWS_EDIT
    view = devices_at(win, OWN)
    assert view.rows_text.text() == strings.DV_ROWS_LINE.format("5 4 / 1, own rows")
    view = devices_at(win, "OBC-J01")
    assert view.rows_text.text() == strings.DV_ROWS_LINE.format(strings.ROWS_NONE)
    asked: list[str] = []
    view.rowsRequested.connect(asked.append)
    script = DialogScript(win, accept=False)
    view.rows_btn.click()
    assert asked == ["OBC-J01"]
    assert [d.windowTitle() for d in script.seen] == [strings.PR_TITLE_CONNECTOR.format("OBC-J01")]
    assert unnamed(view) == []
    # the line of the pin table, before Add pin; the text is cut when the window is narrow and
    # the whole of it is the tooltip, so the buttons keep their room
    view = devices_at(win, "OBC-J02")
    bar = [w.objectName() for w in (view.pins_caption, view.rows_text, view.rows_btn)]
    assert bar == ["", "devices-pin-rows", "devices-pin-rows-edit"]
    assert view.rows_btn.x() < view.pin_buttons["add"].x()
    assert view.rows_text.x() < view.rows_btn.x()
    full = view.rows_text.full_text()
    assert full in view.rows_text.toolTip()
    view.rows_text.resize(60, view.rows_text.height())
    assert view.rows_text.shown_text() != full and "…" in view.rows_text.shown_text()
    assert view.rows_text.accessibleName() == strings.DV_CARD_ROWS
    # a pane too narrow for every button with its text shows Edit rows… as its icon; a wide one
    # with its text
    win.dock_left.hide()
    win.dock_right.hide()
    qtbot.waitUntil(lambda: view.rows_btn.text() == strings.DV_ROWS_EDIT, timeout=2000)
    assert view.pins_caption.shown_text() == strings.DV_PIN_TABLE.format("J02")  # (whole)
    win.dock_left.show()
    win.dock_right.show()
    win.resize(1100, 900)
    qtbot.waitUntil(lambda: view.rows_btn.text() == "", timeout=2000)
    assert view.rows_btn.accessibleName() == strings.DV_ROWS_EDIT


def test_the_pin_table_has_the_pin_row_column_only_with_a_layout(qtbot, tmp_path) -> None:
    win = window_with(tmp_path)
    qtbot.addWidget(win)
    assert pin_column(devices_at(win, "OBC-J01"))[0]  # (no layout: hidden)
    assert pin_column(devices_at(win, "OBC-J02")) == (False, ["1", "2", "1"])  # 1 3 / 2
    assert pin_column(devices_at(win, OWN)) == (False, ["2", "", "", "1", "1"])  # 5 4 / 1
    assert pin_column(devices_at(win, "OBC-J01"))[0]


def test_a_read_only_project_offers_no_edit_of_the_rows(qtbot, tmp_path) -> None:
    p = row_layout_project()
    p.read_only = True
    win = window_with(tmp_path, p)
    qtbot.addWidget(win)
    view = devices_at(win, "OBC-J02")
    assert not view.rows_btn.isEnabled()
    assert view.rows_btn.toolTip() == strings.WHY_READ_ONLY
    assert not win.pin_rows_flow("connector", "OBC-J02")


def test_the_pin_table_keeps_four_rows_at_1440_by_900(qtbot, tmp_path) -> None:
    """The size of docs/ux/qt/29-devices-pin-rows.png: the flatsat example, a part with rows, the
    banner of plans out of date, the side panels open as they are by default and closed as in the
    picture. The rows' line must not make the card taller: the pin table shows four rows or more."""
    import shutil

    from harness_design_studio.resources import examples_path

    root = examples_path()
    assert root is not None
    shutil.copytree(root / "projects" / "flatsat", tmp_path / "flatsat")
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    assert win.open_project(tmp_path / "flatsat")
    hold_drc(win)
    assert win.ctl.set_row_layout(parse_text("1–5 / 6–9"), part="EX-MICROD-9-F")
    view = devices_at(win, "MTQ1-J01")
    for docks in (True, False):
        win.dock_left.setVisible(docks)
        win.dock_right.setVisible(docks)
        qtbot.wait(300)  # (the banner and the layout settle)
        table = view.pin_table
        rows = table.viewport().height() // table.verticalHeader().defaultSectionSize()
        assert rows >= 4, f"the pin table shows {rows} rows (side panels open: {docks})"


# ---- the dialog ----------------------------------------------------------------------------------


def test_the_dialog_starts_from_the_rows_the_connector_has(qtbot) -> None:
    p = row_layout_project()
    dlg = dialog(p, connector="OBC-J02")
    qtbot.addWidget(dlg)
    assert dlg.windowTitle() == strings.PR_TITLE_CONNECTOR.format("OBC-J02")
    assert dlg.rows_edit.toPlainText() == "1 3\n2"
    assert dlg.ok.isEnabled() and not dlg.notice.isVisibleTo(dlg)
    assert not dlg.back_btn.isEnabled()  # (no rows of its own)
    assert dlg.share_btn.isEnabled()  # the part has these rows already: only clears equal ones
    own = dialog(p, connector=OWN)
    qtbot.addWidget(own)
    assert own.rows_edit.toPlainText() == "5 4\n1" and own.back_btn.isEnabled()
    assert unnamed(own) == []


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("1 2 3 22", "OBC-J02 has no pin 22"),
        ("1 3\n2 3", "pin 3 is in row 1 and in row 2"),
        ("1-3", "has no pin 1-3"),  # (`-` is part of a name, not a range mark)
        ("1–3–5", "more than one range mark"),
    ],
)
def test_a_mistake_is_said_in_words_and_keeps_ok_off(qtbot, text, words) -> None:
    dlg = dialog(row_layout_project(), connector="OBC-J02")
    qtbot.addWidget(dlg)
    dlg.show()
    dlg.rows_edit.setPlainText(text)
    assert not dlg.ok.isEnabled()
    assert dlg.notice.isVisibleTo(dlg) and words in dlg.notice.text()
    assert not dlg.share_btn.isEnabled()
    dlg.rows_edit.setPlainText("2 3 1")
    assert dlg.ok.isEnabled() and not dlg.notice.isVisibleTo(dlg)


def test_row_lengths_fill_the_rows_and_rings_are_a_check_box(qtbot) -> None:
    p = row_layout_project()
    dlg = dialog(p, connector=OWN)  # pins 1 to 5
    qtbot.addWidget(dlg)
    dlg.show()
    dlg.lengths_edit.setText("3, 2")
    assert dlg.fill()
    assert dlg.rows_edit.toPlainText() == "1–3\n4 5"
    dlg.lengths_edit.setText("3, 4")
    assert not dlg.fill()
    assert "the connector has 5" in dlg.notice.text()
    dlg.rings.setChecked(True)
    assert dlg.typed_rows() == parse_text("1–3 / 4 5 (rings)")
    dlg.clear_btn.click()
    assert dlg.rows_edit.toPlainText() == "" and not dlg.rings.isChecked()
    assert dlg.ok.isEnabled() and dlg.typed_rows() is None
    assert dlg.hint.text() == strings.PR_EMPTY_CONNECTOR.format(OWN)
    part = dialog(p, part="EX-MICROD-25-F")
    qtbot.addWidget(part)
    part.lengths_edit.setText("13, 12")
    assert part.fill() and part.rows_edit.toPlainText() == "1–13\n14–25"


def test_the_dialog_of_a_part_names_the_connectors_that_lack_a_pin(qtbot) -> None:
    p = row_layout_project()
    dlg = dialog(p, part=PART)
    qtbot.addWidget(dlg)
    dlg.show()
    assert dlg.windowTitle() == strings.PR_TITLE_PART.format(PART)
    assert not dlg.share_btn.isVisibleTo(dlg) and not dlg.back_btn.isVisibleTo(dlg)
    assert dlg.rows_edit.toPlainText() == "1 3\n2" and not dlg.hint.isVisibleTo(dlg)
    dlg.rows_edit.setPlainText("1–5\n6–9")
    assert dlg.ok.isEnabled()  # a part has 9 contacts; its connectors here have 3 pins
    hint = dlg.hint.text()
    for cid in ("OBC-J02", "PCDU-J01", "PCDU-J02", "W001-P2"):
        assert f"{cid} has no pin 4, 5, 6, 7, 8, 9" in hint
    dlg.rows_edit.setPlainText("1–10")
    assert not dlg.ok.isEnabled() and "the part has 9" in dlg.notice.text()


def test_share_is_off_when_the_part_has_other_rows(qtbot) -> None:
    p = row_layout_project()
    p.parts["EX-MICROD-15-M"] = evolve(p.parts["EX-MICROD-15-M"], row_layout=parse_text("1 2"))
    dlg = dialog(p, connector=OWN)
    qtbot.addWidget(dlg)
    assert not dlg.share_btn.isEnabled()
    assert "has other rows" in dlg.share_btn.toolTip()
    dlg.rows_edit.setPlainText("1 2")  # the part's own rows: sharing them only clears
    assert dlg.share_btn.isEnabled()


# ---- the window runs what the dialog ends with: one undo step each --------------------------------


def test_set_rows_is_one_undo_step_and_undo_brings_them_back(qtbot, tmp_path) -> None:
    win = window_with(tmp_path)
    qtbot.addWidget(win)
    n = steps(win)
    DialogScript(win, lambda d: d.rows_edit.setPlainText("2 3 1"))
    assert win.pin_rows_flow("connector", "OBC-J02")
    assert win.ctl.project.connectors["OBC-J02"].row_layout == parse_text("2 3 1")
    assert steps(win) == n + 1
    view = devices_at(win, "OBC-J02")
    assert view.rows_text.text() == strings.DV_ROWS_LINE.format("2 3 1, own rows")
    assert pin_column(view) == (False, ["1", "1", "1"])  # (one row)
    win.ctl.undo()
    assert win.ctl.project.connectors["OBC-J02"].row_layout is None
    win.ctl.redo()
    assert win.ctl.project.connectors["OBC-J02"].row_layout == parse_text("2 3 1")


def test_ok_with_the_rows_of_the_part_adds_no_own_rows(qtbot, tmp_path) -> None:
    win = window_with(tmp_path)
    qtbot.addWidget(win)
    n = steps(win)
    DialogScript(win)  # (the box holds the part's rows: OK as it opened)
    assert win.pin_rows_flow("connector", "OBC-J02")
    assert win.ctl.project.connectors["OBC-J02"].row_layout is None and steps(win) == n


def test_back_to_the_parts_rows_and_an_empty_box_clear_the_own_rows(qtbot, tmp_path) -> None:
    win = window_with(tmp_path)
    qtbot.addWidget(win)
    n = steps(win)
    DialogScript(win, lambda d: d.back_btn.click())
    assert win.pin_rows_flow("connector", OWN)
    assert win.ctl.project.connectors[OWN].row_layout is None and steps(win) == n + 1
    win.ctl.undo()
    DialogScript(win, lambda d: d.clear_btn.click())
    assert win.pin_rows_flow("connector", OWN)
    assert win.ctl.project.connectors[OWN].row_layout is None and steps(win) == n + 1


def test_use_for_every_connector_of_this_part_is_one_undo_step(qtbot, tmp_path) -> None:
    p = row_layout_project()
    p.connectors["PCDU-J03"] = evolve(p.connectors["PCDU-J03"], row_layout=parse_text("2 1 / 3"))
    win = window_with(tmp_path, p)
    qtbot.addWidget(win)
    n = steps(win)

    def typed(d) -> None:
        d.rows_edit.setPlainText("2 1\n3")
        d.share_btn.click()

    DialogScript(win, typed)
    assert win.pin_rows_flow("connector", "OBC-J03")  # (EX-MICROD-15-F, as PCDU-J03)
    q = win.ctl.project
    assert q.parts["EX-MICROD-15-F"].row_layout == parse_text("2 1 / 3")
    assert q.connectors["OBC-J03"].row_layout is None
    assert q.connectors["PCDU-J03"].row_layout is None  # (equal own rows cleared)
    assert steps(win) == n + 1
    win.ctl.undo()
    q = win.ctl.project
    assert q.parts["EX-MICROD-15-F"].row_layout is None
    assert q.connectors["PCDU-J03"].row_layout == parse_text("2 1 / 3")


def test_the_rows_of_a_part_from_the_inspector(qtbot, tmp_path) -> None:
    win = window_with(tmp_path)
    qtbot.addWidget(win)
    win.dock_right.show()
    win.inspector.show_object("part", PART)
    settle()
    box = win.inspector.rows_box
    assert box.isVisibleTo(win.inspector) and box.text.text() == "1 3 / 2"
    facts = {r["name"]: r["value"] for r in facts_for(win.ctl.project, "part", PART)}
    assert facts[strings.INS_ROWS] == "1 3 / 2"
    n = steps(win)
    DialogScript(win, lambda d: d.rows_edit.setPlainText("2 3 1"))
    box.edit_btn.click()
    settle()
    assert win.ctl.project.parts[PART].row_layout == parse_text("2 3 1")
    assert steps(win) == n + 1
    assert box.text.text() == "2 3 1"
    win.inspector.show_object("part", "EX-WIRE-24")
    settle()
    assert not box.isVisibleTo(win.inspector)  # (a wire part has no rows)


def test_the_inspector_of_a_cable_connector_shows_its_rows_read_only(qtbot, tmp_path) -> None:
    p = row_layout_project()
    facts = {r["name"]: r["value"] for r in facts_for(p, "cable_end", "W002-P2")}
    assert facts[strings.INS_ROWS] == "5 4 / 1, from RW1-J02, the device connector it plugs into"
    facts = {r["name"]: r["value"] for r in facts_for(p, "cable_end", "W001-P2")}
    assert facts[strings.INS_ROWS] == "1 3 / 2, from part EX-MICROD-9-F"
    facts = {r["name"]: r["value"] for r in facts_for(p, "cable_end", "W002-P1")}
    assert facts[strings.INS_ROWS] == strings.ROWS_NONE
    win = window_with(tmp_path, p)
    qtbot.addWidget(win)
    win.show_connector("W002-P2")
    settle()
    assert win.inspector.current() == ("cable_end", "W002-P2")
    assert not win.inspector.rows_box.isVisibleTo(win.inspector)  # (nothing to edit there)


# ---- the Problems list: the three checks of section 4.3 ------------------------------------------


def missing_pins_project():
    """The rows of the part EX-MICROD-9-F name pin 9, which none of its connectors has."""
    p = row_layout_project()
    p.parts[PART] = evolve(p.parts[PART], row_layout=parse_text("1 3 9 / 2"))
    return p


def test_the_problems_list_shows_the_three_checks(qtbot, tmp_path) -> None:
    p = missing_pins_project()
    p.parts["EX-MICROD-9-M"] = evolve(p.parts["EX-MICROD-9-M"], row_layout=parse_text("1 2 / 3"))
    win = window_with(tmp_path, p)
    qtbot.addWidget(win)
    win.ctl.run_drc_now()
    win.ctl.wait_drc()
    plist = win.problems_list
    plist.refresh()
    rows = [r for r in plist.rows() if r.get("rows")]
    by_kind = {(r["rule"], r["object_id"]) for r in rows}
    assert ("row_layout_pins_outside", OWN) in by_kind  # the note: no finding of a rule
    assert ("row_layout_pins_outside", "W002-P2") in by_kind
    assert ("model-inconsistent", "OBC-J02") in by_kind  # pin 9 missing
    assert any("different row layouts" in r["message"] for r in rows)  # the mate differs
    note = next(r for r in rows if r["rule"] == "row_layout_pins_outside")
    assert note["level"] == "info" and note["why"] == strings.PROBLEMS_ROWS_NOTE_WHY
    win._update_problems_button()
    total = len(win.ctl.open_findings()) + len(win.ctl.layout_notes())
    assert plist.total() == total
    assert win.problems_btn.text() == strings.PROBLEMS_BUTTON.format(total)


def test_show_goes_to_the_connector_and_the_menu_edits_its_rows(qtbot, tmp_path) -> None:
    win = window_with(tmp_path, missing_pins_project())
    qtbot.addWidget(win)
    win.ctl.run_drc_now()
    win.ctl.wait_drc()
    plist = win.problems_list
    win.dock_problems.show()
    plist.refresh()
    settle()
    shown: list[str] = []
    plist.connectorRequested.connect(shown.append)
    row = next(
        k for k in range(plist.table.proxy.rowCount())
        if (r := plist.table.row_at(plist.table.proxy.index(k, 0))).get("object_id") == "OBC-J02"
        and r.get("rows")
    )  # fmt: skip
    index = plist.table.proxy.index(row, 0)
    plist._clicked(index)
    assert shown == ["OBC-J02"]
    assert win.main_tabs.currentWidget() is win.main_tabs.widget_of("devices")
    assert win.devices_view.connector_id() == "OBC-J02"
    plist._menu(plist.table.visualRect(index).center())
    act = next(a for a in plist.menu.actions() if a.objectName() == "problems-fix-rows")
    assert act.text() == strings.PROBLEMS_EDIT_ROWS.format("OBC-J02") and act.isEnabled()
    DialogScript(win, lambda d: d.rows_edit.setPlainText("1 3 / 2"))
    act.trigger()
    assert win.ctl.project.connectors["OBC-J02"].row_layout == parse_text("1 3 / 2")


def test_the_rows_of_a_check_are_edited_where_they_come_from() -> None:
    p = row_layout_project()
    assert rows_target(p, PART) == ("part", PART)
    assert rows_target(p, "OBC-J02") == ("connector", "OBC-J02")
    assert rows_target(p, "W002-P2") == ("connector", OWN)  # (the mated device connector's)
    assert rows_target(p, "W001-P2") == ("part", PART)
    assert rows_target(p, "W002-P1") is None
