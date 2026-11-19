# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,attr-defined,union-attr,arg-type,type-arg,assignment,index,misc,func-returns-value"
"""REQ-OUT-01, D-242: the editor of the harness plan (design of 3.0.0 section 10, pull request 7).

The Export window's check box *Include the harness plans (.ods), one per harness* (ticked when the
folder's last export had plans; an export without them removes them and says so, as the command
line does); *Settings > Document* and *Settings > Harness plan* (set, clear, the contact lines,
*Use the example colour code…*, the paste of two columns, the example mark, the note lines, the
file removed when every value is back to its default, and the notes of `check`); the Inspector's
*Plan document* of a harness and *Link* of a part; the Devices tab's *Level*, *Signal ground* and
the source of a connector's pinout (a cable pin offers no Level, Q5); the parts of a device in the
Library window with their links. Every change is one undo step. Example data only: `Example Ltd`,
`plans@example.org`."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from harness_design_studio.core import document, library_folder, plan_config  # noqa: E402
from harness_design_studio.core.commands import SetMeta  # noqa: E402
from harness_design_studio.core.generate.engine import generate_project  # noqa: E402
from harness_design_studio.core.io.saver import save_project  # noqa: E402
from harness_design_studio.core.model import DocumentInfo, PlanDocument, evolve  # noqa: E402
from harness_design_studio.core.outputs.build import harness_plans_in  # noqa: E402
from harness_design_studio.core.samples import mini3  # noqa: E402
from harness_design_studio.gui import export_docs, strings  # noqa: E402
from harness_design_studio.gui.export_dialog import ExportDialog  # noqa: E402
from harness_design_studio.gui.library_window import LibraryWindow  # noqa: E402
from harness_design_studio.gui.plan_pages import ExampleCodeDialog  # noqa: E402
from tests.gui_helpers import DialogScript, hold_drc, make_window  # noqa: E402

EXAMPLE_LINK = "https://example.org/datasheet.pdf"


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


def connector_part(win) -> str:
    h = win.ctl.project.harnesses["W001"]
    return str(h.connectors[0].part_id)


# ---- the Export window --------------------------------------------------------------------------


def export(win, *, plans: bool | None = None) -> ExportDialog:
    dlg = ExportDialog(win.ctl, win.theme, win, settings=win.settings)
    if plans is not None:
        dlg.plans.setChecked(plans)
    assert dlg.run() is not None, dlg.notice.text()
    return dlg


def test_the_plans_box_starts_off_ticks_the_plans_in_and_follows_the_last_export(win, tmp_path):
    folder = tmp_path / "proj" / "outputs"
    first = ExportDialog(win.ctl, win.theme, win, settings=win.settings)
    box = first.plans
    assert box.text() == strings.EXP_PLANS and not box.isChecked()
    assert box.accessibleName() == strings.EXP_PLANS_NAME and box.toolTip() == strings.EXP_PLANS_TIP
    top = first.model.item(0)
    keys = {str(top.child(r).data(0x0100)) for r in range(top.rowCount())}
    assert "plan" not in keys  # the planned tree holds no plan while the box is off
    box.setChecked(True)
    top = first.model.item(0)
    keys = {str(top.child(r).data(0x0100)) for r in range(top.rowCount())}
    assert "plan" in keys
    result = first.run()
    assert result is not None
    written = harness_plans_in(folder)
    assert written == [f"harnesses/{h}/{h}_plan.ods" for h in sorted(win.ctl.project.harnesses)]
    assert all((folder / rel).is_file() for rel in written)
    plan_files = [f for f in result.files if f.doc.key == "plan"]
    assert len(plan_files) == len(written) and plan_files[0].doc.label == strings.DOC_HARNESS_PLAN
    # Copy path puts the plan's path on the clipboard, to open it in a spreadsheet program
    copied: list[str] = []
    first.result_panel.copier = copied.append
    assert first.result_panel.select_file(written[0])
    assert first.result_panel.copy_path() == str((folder / written[0]).absolute())
    assert copied == [str((folder / written[0]).absolute())]
    assert not first.plans_removed
    # a window opened after an export with plans starts ticked
    again = ExportDialog(win.ctl, win.theme, win, settings=win.settings)
    assert again.plans.isChecked()


def test_an_export_without_the_plans_removes_them_and_says_so(win, tmp_path):
    folder = tmp_path / "proj" / "outputs"
    export(win, plans=True)
    assert harness_plans_in(folder)
    dlg = export(win, plans=False)
    assert harness_plans_in(folder) == []
    assert not list(folder.rglob("*_plan.ods"))
    assert dlg.plans_removed
    assert dlg.notice.text() == strings.EXP_PLANS_REMOVED
    # an export without plans into a folder that had none says nothing of them
    quiet = export(win, plans=False)
    assert not quiet.plans_removed


def test_the_quick_export_keeps_the_plans_of_the_last_export(win, tmp_path):
    folder = tmp_path / "proj" / "outputs"
    export(win, plans=True)
    before = harness_plans_in(folder)
    win.export_flow()  # the export that brings its own worker: the same set as the last one
    assert harness_plans_in(folder) == before


def test_the_plans_box_says_how_many_notes_check_has(win):
    p = win.ctl.project
    win.ctl.run("x", plan_config.plan_example_code(p, [connector_part(win)]))
    dlg = ExportDialog(win.ctl, win.theme, win, settings=win.settings)
    assert not dlg.plan_notes.isVisibleTo(dlg)
    dlg.plans.setChecked(True)
    assert dlg.plan_notes.isVisibleTo(dlg)
    assert "note" in dlg.plan_notes.text() and "Settings > Harness plan" in dlg.plan_notes.text()


def test_the_document_types_know_the_plan():
    doc = export_docs.classify("harnesses/W001/W001_plan.ods")
    assert (doc.scope, doc.key, doc.kind) == ("W001", "plan", "ODS")
    assert export_docs.PLAN_DOC not in export_docs.harness_docs(True)
    assert export_docs.harness_docs(False, True)[1] == export_docs.PLAN_DOC


# ---- Settings > Document ------------------------------------------------------------------------


def document_page(win):
    win.document_flow()
    settle()
    assert win.settings_page.current_section() == "document"
    return win.settings_page.document


def test_the_document_fields_are_set_and_cleared_each_as_one_undo_step(win):
    page = document_page(win)
    edit = page.edits["company"]
    assert edit.accessibleName() == strings.DOC_COMPANY and edit.toolTip()
    assert page.edits["system"].placeholderText() == strings.DOC_EMPTY_SHOWS.format(
        win.ctl.project.meta.name
    )
    n = steps(win)
    edit.setText("Example Ltd")
    edit.editingFinished.emit()
    settle()
    assert win.ctl.project.meta.document.company == "Example Ltd"
    assert steps(win) == n + 1
    assert win.ctl.history._undo[-1].label == strings.STEP_SET_DOCUMENT
    edit.setText("")
    edit.editingFinished.emit()
    settle()
    assert win.ctl.project.meta.document is None  # nothing left: project.json as before
    win.ctl.undo()
    settle()
    assert win.ctl.project.meta.document.company == "Example Ltd"
    assert page.edits["company"].text() == "Example Ltd"


def test_the_contact_lines_are_added_edited_moved_and_removed(win):
    page = document_page(win)
    assert page.contact_table.accessibleName() == strings.DOC_CONTACT_TABLE
    assert page.add_line()
    assert [(c.label, c.value) for c in win.ctl.project.meta.document.contact] == [("E-mail", "")]
    assert page.contact_model.set_cells([(0, 1, "plans@example.org")])
    settle()
    assert win.ctl.project.meta.document.contact[0].value == "plans@example.org"
    assert page.add_line()
    page.contact_model.set_cells([(1, 0, "Name"), (1, 1, "Example Reviewer")])
    settle()
    page.contact_table.setCurrentIndex(page.contact_table.model().index(1, 0))
    assert page.move_up()
    labels = [c.label for c in win.ctl.project.meta.document.contact]
    assert labels == ["Name", "E-mail"]
    page.contact_table.setCurrentIndex(page.contact_table.model().index(0, 0))
    assert page.remove_line()
    assert [c.label for c in win.ctl.project.meta.document.contact] == ["E-mail"]
    # a label left empty is refused, with the words of the core, and nothing changes
    n = steps(win)
    assert not page.contact_model.set_cells([(0, 0, "")])
    assert steps(win) == n
    assert win.ctl.project.meta.document.contact[0].label == "E-mail"


def test_a_plan_of_a_harness_that_is_gone_is_shown_as_the_note_of_check(win):
    p = win.ctl.project
    meta = evolve(p.meta, document=DocumentInfo(plans={"W999": PlanDocument(number="HP-9")}))
    win.ctl.run("x", [SetMeta(meta)])
    page = document_page(win)
    assert page.unknown.isVisibleTo(page)
    assert "W999" in page.unknown.text()
    notes = win.settings_page.harness_plan.check_notes()
    assert any("W999" in n for n in notes)


def test_a_read_only_project_shows_the_document_and_changes_nothing(win):
    win.ctl.project.read_only = True
    page = document_page(win)
    assert page.edits["system"].isReadOnly()
    assert not page.add_btn.isEnabled() and page.add_btn.toolTip() == strings.WHY_READ_ONLY
    assert page.why_not.isVisibleTo(page)


# ---- Settings > Harness plan --------------------------------------------------------------------


def plan_page(win):
    win.harness_plan_flow()
    settle()
    assert win.settings_page.current_section() == "harness_plan"
    return win.settings_page.harness_plan


def test_the_colour_rule_makes_the_file_and_the_default_removes_it(win):
    page = plan_page(win)
    assert "harness_plan" not in win.ctl.project.config
    assert page.rule_combo.currentData() == "wire"
    n = steps(win)
    page.rule_combo.setCurrentIndex(page.rule_combo.findData("pin_code"))
    settle()
    cfg = win.ctl.project.config["harness_plan"]
    assert cfg.values == {"colour_rule": "pin_code"} and not cfg.placeholder
    assert steps(win) == n + 1
    assert page.rule_about.text() == strings.PLAN_RULE_ABOUT["pin_code"]
    page.rule_combo.setCurrentIndex(page.rule_combo.findData("wire"))
    settle()
    assert "harness_plan" not in win.ctl.project.config  # every value at its default: no file
    win.ctl.undo()
    settle()
    assert win.ctl.project.config["harness_plan"].values["colour_rule"] == "pin_code"
    assert page.rule_combo.currentData() == "pin_code"


def test_use_the_example_colour_code_asks_for_the_parts_and_marks_the_code(win):
    page = plan_page(win)
    part = connector_part(win)
    seen: list[ExampleCodeDialog] = []

    def choose(dlg):
        seen.append(dlg)
        assert not dlg.ok_btn.isEnabled()  # nothing is ticked at the start
        assert dlg.tick(part)
        assert dlg.ok_btn.isEnabled()

    DialogScript(win, choose)
    n = steps(win)
    assert page.use_example()
    assert seen and seen[0].windowTitle() == strings.PLAN_EXAMPLE_TITLE
    values = win.ctl.project.config["harness_plan"].values
    assert values["colour_rule"] == "pin_code"
    (code,) = values["colour_codes"]
    assert code["name"] == "example" and code["example"] is True and code["parts"] == [part]
    assert len(code["pins"]) == 37 and code["pins"]["1"]
    assert steps(win) == n + 1
    assert win.ctl.history._undo[-1].label == strings.STEP_USE_EXAMPLE_CODE
    assert page.current_code_name() == "example" and page.mark_box.isChecked()
    assert page.pins_model.rowCount() == 37
    # the note of check is on the page, in the words of the screen
    assert strings.PLAN_EXAMPLE_NOTE.format("example") in page.check_notes()
    # a second time is refused: the code is there already
    DialogScript(win, lambda d: d.tick(part))
    assert not page.use_example()
    assert steps(win) == n + 1
    # cancelled: nothing changes
    DialogScript(win, accept=False)
    assert not page.use_example()


def test_the_mark_comes_off_and_the_note_goes(win):
    p = win.ctl.project
    win.ctl.run("x", plan_config.plan_example_code(p, [connector_part(win)]))
    page = plan_page(win)
    page.select_code("example")
    page.mark_box.click()
    settle()
    code = win.ctl.project.config["harness_plan"].values["colour_codes"][0]
    assert "example" not in code  # the mark is written only while it is on
    assert strings.PLAN_EXAMPLE_NOTE.format("example") not in page.check_notes()


def test_a_code_is_added_its_parts_set_and_two_columns_pasted(win):
    page = plan_page(win)
    win.ask_text = lambda _t, _l, _x: "pigtail"
    assert page.add_code()
    assert page.current_code_name() == "pigtail"
    part = connector_part(win)
    page.parts_edit.setText(part)
    page.parts_edit.editingFinished.emit()
    settle()
    assert win.ctl.project.config["harness_plan"].values["colour_codes"][0]["parts"] == [part]
    QApplication.clipboard().setText("Pin\tColour\n1\tBlack\n2\tBrown\n3\tRed\n")
    n = steps(win)
    assert page.paste_table()
    pins = win.ctl.project.config["harness_plan"].values["colour_codes"][0]["pins"]
    assert pins == {"1": "Black", "2": "Brown", "3": "Red"}
    assert steps(win) == n + 1
    # an edited cell; a colour emptied takes its row out
    assert page.pins_model.set_cells([(1, 1, "Orange")])
    assert page.pins_model.set_cells([(2, 1, "")])
    pins = win.ctl.project.config["harness_plan"].values["colour_codes"][0]["pins"]
    assert pins == {"1": "Black", "2": "Orange"}
    # a row of one cell is refused with its row, and nothing changes
    QApplication.clipboard().setText("1\tBlack\n2\n")
    assert not page.paste_table()
    assert "Row 2" in page.notice.text()
    # a part in two codes is refused with the words of validate
    win.ask_text = lambda _t, _l, _x: "second"
    assert page.add_code()
    page.parts_edit.setText(part)
    page.parts_edit.editingFinished.emit()
    settle()
    codes = win.ctl.project.config["harness_plan"].values["colour_codes"]
    assert [c["parts"] for c in codes] == [[part], []]
    # the code removed
    assert page.remove_code()
    assert [c["name"] for c in win.ctl.project.config["harness_plan"].values["colour_codes"]] == [
        "pigtail"
    ]


def test_a_pin_the_code_does_not_list_is_the_warning_of_check(win):
    p = win.ctl.project
    part = connector_part(win)
    code = {"name": "short", "parts": [part], "pins": {"1": "Black"}}
    win.ctl.run("x", plan_config.plan_settings_edit(p, colour_rule="pin_code", colour_codes=[code]))
    page = plan_page(win)
    notes = page.check_notes()
    assert any("has no colour for pin" in n and "short" in n for n in notes)
    assert page.check_table.isVisibleTo(page) and not page.check_none.isVisibleTo(page)


def test_the_note_lines_are_set_when_the_field_loses_the_focus(win):
    page = plan_page(win)
    page.notes_edit.setPlainText("The label of a line that is not connected says so.\n\n")
    page._notes_done()
    assert win.ctl.project.config["harness_plan"].values == {
        "notes": ["The label of a line that is not connected says so."]
    }
    page.notes_edit.setPlainText("")
    page._notes_done()
    assert "harness_plan" not in win.ctl.project.config


# ---- the Inspector ------------------------------------------------------------------------------


def test_the_plan_document_of_a_harness_is_one_undo_step(win):
    ins = win.inspector
    ins.show_object("harness", "W001")
    settle()
    box = ins.plan_box
    assert box.isVisibleTo(ins)
    h = win.ctl.project.harnesses["W001"]
    assert box.edits["version"].placeholderText() == strings.INS_PLAN_EMPTY.format(h.version)
    assert box.edits["number"].accessibleName() == strings.INS_PLAN_NUMBER
    n = steps(win)
    box.edits["number"].setText("HP-W001")
    box.edits["release"].setText("R1")
    assert box.apply()
    settle()
    plan = document.plan_of(win.ctl.project, "W001")
    assert (plan.number, plan.release, plan.version) == ("HP-W001", "R1", "")
    assert steps(win) == n + 1
    assert win.ctl.history._undo[-1].label == strings.STEP_SET_PLAN_DOCUMENT.format("W001")
    win.ctl.undo()
    settle()
    assert win.ctl.project.meta.document is None
    # a part shows its link box instead
    ins.show_object("part", connector_part(win))
    settle()
    assert not box.isVisibleTo(ins) and ins.link_box.isVisibleTo(ins)


def test_the_link_of_a_part_is_set_refused_when_it_is_not_a_web_link_and_copied(win):
    ins = win.inspector
    part = connector_part(win)
    ins.show_object("part", part)
    settle()
    box = ins.link_box
    copied: list[str] = []
    box.copier = copied.append
    assert not box.open_btn.isEnabled()
    box.edit.setText("file:///srv/share/datasheet.pdf")
    assert not box.apply()
    assert box.error.isVisibleTo(box) and "https://" in box.error.text()
    assert win.ctl.project.parts[part].link is None
    n = steps(win)
    box.edit.setText(EXAMPLE_LINK)
    assert box.apply()
    settle()
    assert win.ctl.project.parts[part].link == EXAMPLE_LINK and steps(win) == n + 1
    box.show_part(part)
    assert box.open_btn.isEnabled()
    done = box.copy_link()
    assert done and copied == [EXAMPLE_LINK]
    box.edit.setText("")
    assert box.apply()
    assert win.ctl.project.parts[part].link is None


# ---- the Devices tab ----------------------------------------------------------------------------


def devices_on_box_connector(win):
    p = win.ctl.project
    c = next(c for c in sorted(p.connectors.values(), key=lambda c: c.id) if c.unit_id)
    view = win.devices_view
    win.go_to("devices")
    view.show_unit(c.unit_id, c.id)
    view.refresh()
    settle()
    return view, c


def test_the_pin_table_has_level_and_the_role_list_signal_ground(win):
    view, c = devices_on_box_connector(win)
    model = view.pin_model
    col = model.column_index("level")
    assert model.headerData(col, 1, 0) == strings.DV_COL_LEVEL
    pin = c.pins[0].id
    row = next(k for k in range(model.rowCount()) if model.row(k)["pin"] == pin)
    n = steps(win)
    assert model.setData(model.index(row, col), "RS422-3V3")
    settle()
    pins = {x.id: x for x in win.ctl.project.connectors[c.id].pins}
    assert pins[pin].level == "RS422-3V3" and steps(win) == n + 1
    assert strings.LINK_ROLE_NAMES["signal_ground"] == "Signal ground"
    role = model.column_index("role")
    assert model.setData(model.index(row, role), "signal_ground")
    settle()
    pins = {x.id: x for x in win.ctl.project.connectors[c.id].pins}
    assert pins[pin].role == "signal_ground"
    view.refresh()
    settle()
    row = next(k for k in range(model.rowCount()) if model.row(k)["pin"] == pin)
    assert model.row(row)["role"] == "Signal ground" and model.row(row)["level"] == "RS422-3V3"


def test_the_role_editor_offers_signal_ground(win):
    from PySide6.QtWidgets import QComboBox, QStyleOptionViewItem

    view, _c = devices_on_box_connector(win)
    table = view.pin_table
    index = table.model().index(0, view.pin_model.column_index("role"))
    editor = table.itemDelegate().createEditor(table.viewport(), QStyleOptionViewItem(), index)
    assert isinstance(editor, QComboBox)
    assert editor.findData("signal_ground") >= 0
    assert editor.itemText(editor.findData("signal_ground")) == "Signal ground"


def test_a_cable_pin_offers_no_level(win):
    """Q5: the level belongs to the device's pin; the pin tables of the Harness tab have none."""
    from harness_design_studio.gui.tables import TableView

    win.go_to("harness")
    settle()
    headers = set()
    for table in win.harness_view.findChildren(TableView):
        m = table.source
        headers |= {str(c.header) for c in m.columns}
    assert strings.DV_COL_LEVEL not in headers


def test_the_source_of_a_connector_is_set_and_its_link_copied(win):
    view, c = devices_on_box_connector(win)
    copied: list[str] = []
    view.copier = copied.append
    edits = view.source_edits
    assert set(edits) == {"source_doc", "source_version", "source_link"}
    assert edits["source_doc"].accessibleName() == strings.DV_CARD_SOURCE
    n = steps(win)
    edits["source_doc"].setText("ICD-EX-001")
    edits["source_doc"].editingFinished.emit()
    edits["source_version"].setText("2")
    edits["source_version"].editingFinished.emit()
    settle()
    conn = win.ctl.project.connectors[c.id]
    assert (conn.source_doc, conn.source_version) == ("ICD-EX-001", "2")
    assert steps(win) == n + 2
    edits["source_link"].setText("not a link")
    edits["source_link"].editingFinished.emit()
    settle()
    assert win.ctl.project.connectors[c.id].source_link is None
    view.refresh()
    settle()
    edits["source_link"].setText(EXAMPLE_LINK)
    edits["source_link"].editingFinished.emit()
    settle()
    assert win.ctl.project.connectors[c.id].source_link == EXAMPLE_LINK
    view.refresh()
    settle()
    assert view.source_open.isEnabled()
    done = view.copy_source_link()
    assert done and copied == [EXAMPLE_LINK]
    # the Inspector of the device names the source on its connector card
    win.ctl.set_mode("expert")  # (the connector cards are in Expert mode)
    win.ctl.select("unit", c.unit_id)
    win.inspector.props.rebuild()
    settle()
    label = win.inspector.props.findChild(QLabel, f"source-{c.id}")
    assert label is not None and "ICD-EX-001" in label.text() and "version 2" in label.text()


# ---- the Library window -------------------------------------------------------------------------


def test_the_parts_of_a_device_in_the_library_window_have_their_links(win, qtbot):
    data = {
        "devices": [
            {"unit": {"id": "DEV1"}, "connectors": [{"part_id": "P-1", "pins": [{"id": "1"}]}]}
        ],
        "parts": [
            {"id": "P-1", "description": "Example connector", "link": EXAMPLE_LINK},
            {"id": "P-2", "description": "Not used by DEV1", "link": EXAMPLE_LINK},
            {"id": "P-3", "link": "file:///srv/share"},
        ],
    }
    rows = library_folder.describe_parts(data, "DEV1")
    assert rows == [{"part": "P-1", "description": "Example connector", "link": EXAMPLE_LINK}]
    lib = LibraryWindow(win.ctl, win.theme, win.settings, win)
    qtbot.addWidget(lib)
    copied: list[str] = []
    lib.copier = copied.append
    lib.part_model.set_rows(rows)
    assert [c.header for c in lib.part_model.columns] == list(strings.LIB_PREVIEW_PART_COLUMNS)
    assert lib.part_table.accessibleName() == strings.LIB_PREVIEW_TABLE_PARTS
    done = lib.copy_part_link("P-1")
    assert done and copied == [EXAMPLE_LINK]
    missing = lib.copy_part_link("P-9")
    assert not missing


def test_the_editor_copies_a_link_and_opens_no_browser(win):
    """The owner's decision of 2026-11-18, "Never open browser at all": the main window hands the
    link boxes a copier, which puts the link on the clipboard and says so in the status bar."""
    from PySide6.QtGui import QGuiApplication

    assert win.inspector.link_box.copier == win._copy_link
    assert win.devices_view.copier == win._copy_link
    win._copy_link(EXAMPLE_LINK)
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None and clipboard.text() == EXAMPLE_LINK
    assert EXAMPLE_LINK in win.statusBar().currentMessage()
