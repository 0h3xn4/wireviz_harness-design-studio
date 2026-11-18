# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The two sections of the Settings page for the harness plans (3.0.0, D-242, design section 10):
*Document* (what the Cover of every plan shows) and *Harness plan* (the colour rule, the colour
codes, the note lines, the button *Use the example colour code*, and the notes of `check`).

    doc = DocumentSection(theme, set_fields=..., set_contact=...)
    doc.show_document(fields, shown_when_empty, contact, unknown, why_not)
    plan = HarnessPlanSection(theme, set_plan=..., use_example=..., ask_text=..., clipboard=...)
    plan.show_plan(values, notes, why_not)

Like the rest of the Settings page they only show and call back: the window builds the change with
`core/document.py` and `core/plan_config.py` and runs it through the controller as one undo step,
then calls `show_…` again with what the project holds. A callback returns False when the change was
refused (the window has said why), and the section then shows what the project holds again.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from harness_design_studio.core.edit import EditError
from harness_design_studio.core.plan_config import EXAMPLE_NAME, parse_colour_table
from harness_design_studio.gui import strings
from harness_design_studio.gui.dialog_base import Dialog
from harness_design_studio.gui.empty_state import attach_empty_state
from harness_design_studio.gui.sheet import install_sheet
from harness_design_studio.gui.tables import Column, DictTableModel, TableView
from harness_design_studio.gui.theme import ThemeManager, mark_mono

Cells = list[tuple[int, int, str]]
Note = tuple[str, str]  # (severity, the sentence)


class EditRows(DictTableModel):
    """A table whose cells a person edits like a spreadsheet (`gui/sheet.py`: Enter, F2, typing,
    Ctrl+V, a bulk edit): the model never changes its rows itself; `on_cells` gets the edited
    cells (source row, column, text) and the section shows the project again afterwards."""

    def __init__(
        self,
        columns: Sequence[Column],
        theme: ThemeManager,
        on_cells: Callable[[Cells], bool],
    ) -> None:
        super().__init__(columns, [], theme)
        self.on_cells = on_cells
        self.read_only = False

    def is_editable(self, column: int) -> bool:
        return not self.read_only and 0 <= column < len(self.columns)

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        base = super().flags(index)
        if index.isValid() and self.is_editable(index.column()):
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def set_cells(self, cells: Cells) -> bool:
        return self.on_cells(cells) if cells and not self.read_only else False


def _muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("muted", True)
    return label


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("heading", True)
    return label


def _button(text: str, tip: str, name: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName(name)
    b.setAccessibleName(text.rstrip("…"))
    b.setToolTip(tip)
    return b


def _line(name: str, label: str, tip: str) -> QLineEdit:
    edit = QLineEdit()
    edit.setObjectName(name)
    edit.setAccessibleName(label)
    edit.setToolTip(tip)
    edit.setClearButtonEnabled(True)
    return edit


def _set_text(edit: QLineEdit, text: str) -> None:
    """Show `text` unless the person is typing in the field."""
    if not edit.hasFocus() and edit.text() != text:
        edit.setText(text)


# ---- Settings > Document --------------------------------------------------------------------------


class DocumentSection(QWidget):
    """The system code, the title and the company of every plan of the project, and its contact
    lines (add, remove, move, edit in the table). `set_fields({key: text})` and
    `set_contact([(label, value), ...])` are the window's."""

    FIELDS = (
        ("system", strings.DOC_SYSTEM, strings.DOC_SYSTEM_TIP),
        ("title", strings.DOC_TITLE, strings.DOC_TITLE_TIP),
        ("company", strings.DOC_COMPANY, strings.DOC_COMPANY_TIP),
    )

    def __init__(
        self,
        theme: ThemeManager,
        *,
        set_fields: Callable[[dict[str, str]], bool],
        set_contact: Callable[[list[tuple[str, str]]], bool],
    ) -> None:
        super().__init__()
        self.theme = theme
        self.setObjectName("settings-document")
        self._set_fields, self._set_contact = set_fields, set_contact
        self._contact: list[tuple[str, str]] = []
        self._shown: dict[str, str] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.space(12))
        lay.addWidget(_muted(strings.DOC_PAGE_TEXT))
        self.why_not = _muted("")
        self.why_not.setObjectName("settings-document-why-not")
        self.why_not.hide()
        lay.addWidget(self.why_not)
        form = QFormLayout()
        self.edits: dict[str, QLineEdit] = {}
        for key, label, tip in self.FIELDS:
            edit = _line(f"settings-document-{key}", label, tip)
            edit.editingFinished.connect(lambda k=key: self._field_done(k))
            self.edits[key] = edit
            form.addRow(label, edit)
        lay.addLayout(form)
        lay.addWidget(_heading(strings.DOC_CONTACT))
        lay.addWidget(_muted(strings.DOC_CONTACT_TEXT))
        self.contact_model = EditRows(
            [
                Column("label", strings.DOC_CONTACT_COLUMNS[0], width=140),
                Column("value", strings.DOC_CONTACT_COLUMNS[1], width=320),
            ],
            theme,
            self._contact_cells,
        )
        self.contact_table = TableView(self.contact_model, theme, name=strings.DOC_CONTACT_TABLE)
        self.contact_table.setObjectName("settings-document-contact")
        self.contact_table.setSortingEnabled(False)  # the order is the Cover's order
        self.contact_table.horizontalHeader().setStretchLastSection(True)
        self.contact_table.setMinimumHeight(theme.px(150))
        self.contact_table.setMaximumHeight(theme.px(260))
        install_sheet(self.contact_table)
        attach_empty_state(
            self.contact_table, strings.DOC_CONTACT_EMPTY, strings.DOC_CONTACT_EMPTY_HINT
        )
        lay.addWidget(self.contact_table)
        row = QHBoxLayout()
        self.add_btn = _button(strings.DOC_CONTACT_ADD, strings.DOC_CONTACT_ADD_TIP, "settings-document-contact-add")  # fmt: skip
        self.remove_btn = _button(strings.DOC_CONTACT_REMOVE, strings.DOC_CONTACT_REMOVE_TIP, "settings-document-contact-remove")  # fmt: skip
        self.up_btn = _button(strings.DOC_CONTACT_UP, strings.DOC_CONTACT_UP_TIP, "settings-document-contact-up")  # fmt: skip
        self.down_btn = _button(strings.DOC_CONTACT_DOWN, strings.DOC_CONTACT_DOWN_TIP, "settings-document-contact-down")  # fmt: skip
        self.add_btn.clicked.connect(self.add_line)
        self.remove_btn.clicked.connect(self.remove_line)
        self.up_btn.clicked.connect(self.move_up)
        self.down_btn.clicked.connect(self.move_down)
        for b in (self.add_btn, self.remove_btn, self.up_btn, self.down_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.unknown = _muted("")
        self.unknown.setObjectName("settings-document-unknown")
        self.unknown.hide()
        lay.addWidget(self.unknown)
        self.contact_table.selectionModel().currentRowChanged.connect(
            lambda _c, _p: self._buttons()
        )
        self._why = ""
        self._buttons()

    # ---- follow the project ------------------------------------------------------------------
    def show_document(
        self,
        fields: Mapping[str, str],
        empty: Mapping[str, str],
        contact: Sequence[tuple[str, str]],
        unknown: Sequence[str] = (),
        why_not: str = "",
    ) -> None:
        """Show the document data of the project: `fields` by key, `empty` what the Cover shows
        for an empty field, the contact lines, the keys of plans that name no harness, and why
        nothing can change now ("" when it can)."""
        self._shown = {k: str(fields.get(k, "")) for k, _l, _t in self.FIELDS}
        for key, edit in self.edits.items():
            _set_text(edit, self._shown[key])
            edit.setPlaceholderText(
                strings.DOC_EMPTY_SHOWS.format(empty[key]) if empty.get(key) else ""
            )
            edit.setReadOnly(bool(why_not))
        self._contact = [(str(a), str(b)) for a, b in contact]
        current = self.contact_table.currentIndex()
        self.contact_model.set_rows([{"label": a, "value": b} for a, b in self._contact])
        if current.isValid() and current.row() < len(self._contact):
            self.contact_table.setCurrentIndex(self.contact_table.model().index(current.row(), 0))
        self.contact_model.read_only = bool(why_not)
        self.unknown.setText(" ".join(strings.DOC_UNKNOWN_PLAN.format(k) for k in unknown))
        self.unknown.setVisible(bool(unknown))
        self.why_not.setText(why_not)
        self.why_not.setVisible(bool(why_not))
        self._why = why_not
        self._buttons()

    def _buttons(self) -> None:
        row = self.current_line()
        can = not self._why
        n = len(self._contact)
        self.add_btn.setEnabled(can and n < 8)
        self.remove_btn.setEnabled(can and row is not None)
        self.up_btn.setEnabled(can and row is not None and row > 0)
        self.down_btn.setEnabled(can and row is not None and row < n - 1)
        for b, tip in (
            (self.add_btn, strings.DOC_CONTACT_ADD_TIP),
            (self.remove_btn, strings.DOC_CONTACT_REMOVE_TIP),
            (self.up_btn, strings.DOC_CONTACT_UP_TIP),
            (self.down_btn, strings.DOC_CONTACT_DOWN_TIP),
        ):
            b.setToolTip(self._why or tip)

    def current_line(self) -> int | None:
        index = self.contact_table.currentIndex()
        if not index.isValid():
            return None
        row = self.contact_table.proxy.mapToSource(index).row()
        return row if 0 <= row < len(self._contact) else None

    # ---- the person's changes ---------------------------------------------------------------
    def _field_done(self, key: str) -> None:
        text = self.edits[key].text().strip()
        if self._why or text == self._shown.get(key, ""):
            return
        if not self._set_fields({key: text}):
            self.edits[key].setText(self._shown.get(key, ""))

    def _contact_cells(self, cells: Cells) -> bool:
        lines = [list(x) for x in self._contact]
        for row, col, text in cells:
            if 0 <= row < len(lines) and col in (0, 1):
                lines[row][col] = text.strip()
        return self._set_contact([(a, b) for a, b in lines])

    def add_line(self) -> bool:
        """A new line at the end, labelled E-mail with no value; the person edits it in place."""
        if self._why or len(self._contact) >= 8:
            return False
        ok = self._set_contact([*self._contact, (strings.DOC_CONTACT_NEW_LABEL, "")])
        if ok:
            self.contact_table.setCurrentIndex(
                self.contact_table.model().index(len(self._contact) - 1, 1)
            )
        return ok

    def remove_line(self) -> bool:
        row = self.current_line()
        if self._why or row is None:
            return False
        return self._set_contact([x for k, x in enumerate(self._contact) if k != row])

    def _move(self, step: int) -> bool:
        row = self.current_line()
        if self._why or row is None or not 0 <= row + step < len(self._contact):
            return False
        lines = list(self._contact)
        lines[row], lines[row + step] = lines[row + step], lines[row]
        ok = self._set_contact(lines)
        if ok:
            self.contact_table.setCurrentIndex(self.contact_table.model().index(row + step, 0))
        return ok

    def move_up(self) -> bool:
        return self._move(-1)

    def move_down(self) -> bool:
        return self._move(1)


# ---- Settings > Harness plan ----------------------------------------------------------------------


class ExampleCodeDialog(Dialog):
    """*Use the example colour code*: which connector parts of the project the example code is for
    (the template names none, Q26). OK stays off until one is ticked."""

    def __init__(self, parent: QWidget | None, parts: Sequence[tuple[str, str]]) -> None:
        super().__init__(parent)
        self.setObjectName("example-code-dialog")
        self.setWindowTitle(strings.PLAN_EXAMPLE_TITLE)
        self.setAccessibleName(strings.PLAN_EXAMPLE_TITLE)
        lay = QVBoxLayout(self)
        text = QLabel(strings.PLAN_EXAMPLE_TEXT)
        text.setWordWrap(True)
        lay.addWidget(text)
        lay.addWidget(_heading(strings.PLAN_EXAMPLE_PARTS))
        self.parts = QListWidget()
        self.parts.setObjectName("example-code-parts")
        self.parts.setAccessibleName(strings.PLAN_EXAMPLE_PARTS)
        self.parts.setToolTip(strings.PLAN_EXAMPLE_PARTS)
        mark_mono(self.parts)
        for pid, description in parts:
            item = QListWidgetItem(f"{pid}  {description}".strip())
            item.setData(Qt.ItemDataRole.UserRole, pid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.parts.addItem(item)
        self.parts.itemChanged.connect(lambda _i: self._sync())
        lay.addWidget(self.parts, 1)
        self.hint = _muted(strings.PLAN_EXAMPLE_NONE)
        self.hint.setObjectName("example-code-hint")
        lay.addWidget(self.hint)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_btn = _button(strings.CANCEL, strings.CANCEL, "example-code-cancel")
        self.ok_btn = _button(strings.PLAN_EXAMPLE_OK, strings.PLAN_EXAMPLE_TIP, "example-code-ok")
        self.ok_btn.setProperty("primary", True)
        self.ok_btn.setDefault(True)
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self.accept)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.ok_btn)
        lay.addLayout(row)
        self._sync()

    def chosen(self) -> list[str]:
        out = []
        for k in range(self.parts.count()):
            item = self.parts.item(k)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                out.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return out

    def tick(self, part_id: str, on: bool = True) -> bool:
        for k in range(self.parts.count()):
            item = self.parts.item(k)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == part_id:
                item.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
                return True
        return False

    def _sync(self) -> None:
        some = bool(self.chosen())
        self.ok_btn.setEnabled(some)
        self.hint.setVisible(not some)


class HarnessPlanSection(QWidget):
    """The colour rule, the colour codes (name, parts, the table of pins and colours with the paste
    of two columns, the example mark), the note lines, *Use the example colour code…* and the
    notes of `check` on the plans. `set_plan(colour_rule=…, colour_codes=…, notes=…)`,
    `use_example()` and `ask_text(title, label, text)` are the window's; `clipboard()` gives the
    text the paste reads."""

    def __init__(
        self,
        theme: ThemeManager,
        *,
        set_plan: Callable[..., bool],
        use_example: Callable[[], bool],
        ask_text: Callable[[str, str, str], str | None],
        clipboard: Callable[[], str],
    ) -> None:
        super().__init__()
        self.theme = theme
        self.setObjectName("settings-harness-plan")
        self._set_plan, self._use_example = set_plan, use_example
        self._ask_text, self._clipboard = ask_text, clipboard
        self._values: dict[str, Any] = {"colour_rule": "wire", "colour_codes": [], "notes": []}
        self._why = ""
        self._syncing = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.space(12))
        lay.addWidget(_muted(strings.PLAN_PAGE_TEXT))
        self.why_not = _muted("")
        self.why_not.setObjectName("settings-plan-why-not")
        self.why_not.hide()
        lay.addWidget(self.why_not)
        self.notice = QLabel()  # why the last change was refused (a paste, a code)
        self.notice.setObjectName("settings-plan-notice")
        self.notice.setWordWrap(True)
        self.notice.setProperty("error", True)
        self.notice.hide()
        lay.addWidget(self.notice)
        # the colour rule
        self.rule_combo = QComboBox()
        self.rule_combo.setObjectName("settings-plan-rule")
        self.rule_combo.setAccessibleName(strings.PLAN_RULE)
        self.rule_combo.setToolTip(strings.PLAN_RULE_TIP)
        for value, text in strings.PLAN_RULE_CHOICES.items():
            self.rule_combo.addItem(text, value)
        self.rule_combo.currentIndexChanged.connect(lambda _i: self._rule_picked())
        form = QFormLayout()
        form.addRow(strings.PLAN_RULE, self.rule_combo)
        lay.addLayout(form)
        self.rule_about = _muted("")
        self.rule_about.setObjectName("settings-plan-rule-about")
        lay.addWidget(self.rule_about)
        # the codes
        lay.addWidget(_heading(strings.PLAN_CODES))
        lay.addWidget(_muted(strings.PLAN_CODES_TEXT))
        self.codes = QListWidget()
        self.codes.setObjectName("settings-plan-codes")
        self.codes.setAccessibleName(strings.PLAN_CODE_LIST)
        self.codes.setToolTip(strings.PLAN_CODE_LIST_TIP)
        self.codes.setMaximumHeight(theme.px(110))
        mark_mono(self.codes)
        self.codes.currentRowChanged.connect(lambda _r: self._show_code())
        lay.addWidget(self.codes)
        self.codes_none = _muted(strings.PLAN_CODE_NONE)
        self.codes_none.setObjectName("settings-plan-codes-none")
        lay.addWidget(self.codes_none)
        row = QHBoxLayout()
        self.example_btn = _button(strings.PLAN_EXAMPLE, strings.PLAN_EXAMPLE_TIP, "settings-plan-example")  # fmt: skip
        self.add_btn = _button(strings.PLAN_CODE_ADD, strings.PLAN_CODE_ADD_TIP, "settings-plan-code-add")  # fmt: skip
        self.remove_btn = _button(strings.PLAN_CODE_REMOVE, strings.PLAN_CODE_REMOVE_TIP, "settings-plan-code-remove")  # fmt: skip
        self.example_btn.clicked.connect(self.use_example)
        self.add_btn.clicked.connect(self.add_code)
        self.remove_btn.clicked.connect(self.remove_code)
        for b in (self.example_btn, self.add_btn, self.remove_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        # the code picked: its parts, its mark, its table
        self.code_box = QWidget()
        cl = QVBoxLayout(self.code_box)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(theme.space(8))
        code_form = QFormLayout()
        self.parts_edit = _line("settings-plan-parts", strings.PLAN_PARTS, strings.PLAN_PARTS_TIP)
        mark_mono(self.parts_edit)
        self.parts_edit.editingFinished.connect(self._parts_done)
        code_form.addRow(strings.PLAN_PARTS, self.parts_edit)
        cl.addLayout(code_form)
        self.mark_box = QCheckBox(strings.PLAN_MARK)
        self.mark_box.setObjectName("settings-plan-mark")
        self.mark_box.setAccessibleName(strings.PLAN_MARK)
        self.mark_box.setToolTip(strings.PLAN_MARK_TIP)
        self.mark_box.clicked.connect(self._mark_clicked)
        cl.addWidget(self.mark_box)
        self.pins_model = EditRows(
            [
                Column("pin", strings.PLAN_PINS_COLUMNS[0], mono=True, width=80),
                Column("colour", strings.PLAN_PINS_COLUMNS[1], width=200),
            ],
            theme,
            self._pin_cells,
        )
        self.pins_table = TableView(self.pins_model, theme, name=strings.PLAN_PINS_TABLE.format(""))
        self.pins_table.setObjectName("settings-plan-pins")
        self.pins_table.setSortingEnabled(False)
        self.pins_table.horizontalHeader().setStretchLastSection(True)
        self.pins_table.setMinimumHeight(theme.px(180))
        self.pins_table.setMaximumHeight(theme.px(320))
        install_sheet(self.pins_table)
        attach_empty_state(self.pins_table, strings.PLAN_PINS_EMPTY, strings.PLAN_PINS_EMPTY_HINT)
        cl.addWidget(self.pins_table)
        paste_row = QHBoxLayout()
        self.paste_btn = _button(strings.PLAN_PASTE, strings.PLAN_PASTE_TIP, "settings-plan-paste")
        self.paste_btn.clicked.connect(self.paste_table)
        paste_row.addWidget(self.paste_btn)
        paste_row.addStretch(1)
        cl.addLayout(paste_row)
        lay.addWidget(self.code_box)
        # the note lines
        lay.addWidget(_heading(strings.PLAN_NOTES))
        lay.addWidget(_muted(strings.PLAN_NOTES_TEXT))
        self.notes_edit = NotesEdit(self._notes_done)
        self.notes_edit.setObjectName("settings-plan-notes")
        self.notes_edit.setAccessibleName(strings.PLAN_NOTES)
        self.notes_edit.setToolTip(strings.PLAN_NOTES_TIP)
        self.notes_edit.setMaximumHeight(theme.px(120))
        lay.addWidget(self.notes_edit)
        # what `check` says
        lay.addWidget(_heading(strings.PLAN_CHECK_NOTES))
        self.check_model = DictTableModel(
            [
                Column("severity", strings.PLAN_CHECK_COLUMNS[0], state="state", width=96),
                Column("note", strings.PLAN_CHECK_COLUMNS[1]),
            ],
            [],
            theme,
        )
        self.check_table = TableView(self.check_model, theme, name=strings.PLAN_CHECK_TABLE)
        self.check_table.setObjectName("settings-plan-check")
        self.check_table.setWordWrap(True)
        self.check_table.horizontalHeader().setStretchLastSection(True)
        self.check_table.setMaximumHeight(theme.px(160))
        lay.addWidget(self.check_table)
        self.check_none = _muted(strings.PLAN_CHECK_NONE)
        self.check_none.setObjectName("settings-plan-check-none")
        lay.addWidget(self.check_none)
        self._buttons()

    # ---- follow the project ------------------------------------------------------------------
    def show_plan(
        self, values: Mapping[str, Any], notes: Sequence[Note] = (), why_not: str = ""
    ) -> None:
        """Show the settings (`plan_config.plan_values`), the notes of `check` on the plans
        (severity, sentence) and why nothing can change now ("" when it can)."""
        self._values = {
            "colour_rule": values.get("colour_rule", "wire"),
            "colour_codes": [dict(c) for c in values.get("colour_codes", [])],
            "notes": list(values.get("notes", [])),
        }
        self._why = why_not
        self._syncing = True
        try:
            combo = self.rule_combo
            i = combo.findData(self._values["colour_rule"])
            combo.setCurrentIndex(max(i, 0))
            combo.setEnabled(not why_not)
            keep = self.current_code_name()
            self.codes.clear()
            for code in self._values["colour_codes"]:
                word = strings.PLAN_CODE_ITEM_EXAMPLE if code.get("example") else strings.PLAN_CODE_ITEM  # fmt: skip
                item = QListWidgetItem(word.format(code["name"], len(code["pins"]), len(code["parts"])))  # fmt: skip
                item.setData(Qt.ItemDataRole.UserRole, code["name"])
                self.codes.addItem(item)
            names = [c["name"] for c in self._values["colour_codes"]]
            if names:
                self.codes.setCurrentRow(names.index(keep) if keep in names else 0)
            if not self.notes_edit.hasFocus():
                self.notes_edit.setPlainText("\n".join(self._values["notes"]))
            self.notes_edit.setReadOnly(bool(why_not))
        finally:
            self._syncing = False
        self.rule_about.setText(strings.PLAN_RULE_ABOUT.get(self._values["colour_rule"], ""))
        self.codes.setVisible(bool(self._values["colour_codes"]))
        self.codes_none.setVisible(not self._values["colour_codes"])
        self.check_model.set_rows(
            [
                {
                    "state": {"info": "info", "warning": "warning", "error": "fail"}.get(sev),
                    "severity": strings.PLAN_SEVERITY.get(sev, sev),
                    "note": text,
                }
                for sev, text in notes
            ]
        )
        self.check_table.setVisible(bool(notes))
        self.check_none.setVisible(not notes)
        self.why_not.setText(why_not)
        self.why_not.setVisible(bool(why_not))
        self._show_code()

    def check_notes(self) -> list[str]:
        """The notes of `check` the section shows, as text (for the tests and the export window)."""
        return [str(r["note"]) for r in self.check_model.rows() if isinstance(r, dict)]

    def current_code_name(self) -> str | None:
        item = self.codes.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def current_code(self) -> dict[str, Any] | None:
        name = self.current_code_name()
        return next((c for c in self._values["colour_codes"] if c["name"] == name), None)

    def select_code(self, name: str) -> bool:
        for k in range(self.codes.count()):
            item = self.codes.item(k)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == name:
                self.codes.setCurrentRow(k)
                return True
        return False

    def _show_code(self) -> None:
        code = self.current_code()
        self.code_box.setVisible(code is not None)
        if code is None:
            self.pins_model.set_rows([])
            self._buttons()
            return
        _set_text(self.parts_edit, ", ".join(code["parts"]))
        self.parts_edit.setReadOnly(bool(self._why))
        self.mark_box.setChecked(bool(code.get("example")))
        self.mark_box.setEnabled(not self._why)
        self.pins_model.read_only = bool(self._why)
        self.pins_model.set_rows([{"pin": p, "colour": c} for p, c in code["pins"].items()])
        self.pins_table.setAccessibleName(strings.PLAN_PINS_TABLE.format(code["name"]))
        self._buttons()

    def _buttons(self) -> None:
        can = not self._why
        picked = self.current_code() is not None
        for b, on, tip in (
            (self.example_btn, can, strings.PLAN_EXAMPLE_TIP),
            (self.add_btn, can, strings.PLAN_CODE_ADD_TIP),
            (self.remove_btn, can and picked, strings.PLAN_CODE_REMOVE_TIP),
            (self.paste_btn, can and picked, strings.PLAN_PASTE_TIP),
        ):
            b.setEnabled(on)
            b.setToolTip(self._why or tip)

    # ---- the person's changes ---------------------------------------------------------------
    def _say(self, text: str) -> None:
        self.notice.setText(text)
        self.notice.setVisible(bool(text))

    def _apply(self, **changes: object) -> bool:
        self._say("")
        ok = bool(self._set_plan(**changes))
        if not ok:
            self.show_plan(self._values, self._notes_now(), self._why)
        return ok

    def _notes_now(self) -> list[Note]:
        return [
            (
                {"fail": "error"}.get(str(r.get("state")), str(r.get("state") or "info")),
                str(r["note"]),
            )
            for r in self.check_model.rows()
            if isinstance(r, dict)
        ]

    def _codes_with(self, name: str, **changes: object) -> list[dict[str, Any]]:
        return [
            {**c, **changes} if c["name"] == name else dict(c) for c in self._values["colour_codes"]
        ]

    def _rule_picked(self) -> None:
        rule = self.rule_combo.currentData()
        if self._syncing or not isinstance(rule, str) or rule == self._values["colour_rule"]:
            return
        self._apply(colour_rule=rule)

    def use_example(self) -> bool:
        """*Use the example colour code…*: the window asks for the parts and adds the code."""
        if self._why:
            return False
        self._say("")
        ok = bool(self._use_example())
        if ok:
            self.select_code(EXAMPLE_NAME)
        return ok

    def add_code(self) -> bool:
        if self._why:
            return False
        name = self._ask_text(strings.PLAN_CODE_ADD.rstrip("…"), strings.PLAN_CODE_NAME_ASK, "")
        if not name or not name.strip():
            return False
        name = name.strip()
        codes = [*self._values["colour_codes"], {"name": name, "parts": [], "pins": {}}]
        ok = self._apply(colour_codes=codes)
        if ok:
            self.select_code(name)
        return ok

    def remove_code(self) -> bool:
        name = self.current_code_name()
        if self._why or name is None:
            return False
        codes = [c for c in self._values["colour_codes"] if c["name"] != name]
        return self._apply(colour_codes=codes)

    def _parts_done(self) -> None:
        code = self.current_code()
        if self._why or code is None:
            return
        parts = [p.strip() for p in self.parts_edit.text().replace(";", ",").split(",")]
        parts = [p for p in parts if p]
        if parts != code["parts"]:
            self._apply(colour_codes=self._codes_with(code["name"], parts=parts))

    def _mark_clicked(self, on: bool) -> None:
        code = self.current_code()
        if self._why or code is None or bool(code.get("example")) == on:
            return
        self._apply(colour_codes=self._codes_with(code["name"], example=on))

    def set_pins(self, pins: Mapping[str, str]) -> bool:
        code = self.current_code()
        if self._why or code is None:
            return False
        return self._apply(colour_codes=self._codes_with(code["name"], pins=dict(pins)))

    def _pin_cells(self, cells: Cells) -> bool:
        """A cell of the table edited (or a block pasted into it with Ctrl+V): a row whose pin or
        colour is emptied leaves the code."""
        code = self.current_code()
        if code is None:
            return False
        rows = [[p, c] for p, c in code["pins"].items()]
        for row, col, text in cells:
            if 0 <= row < len(rows) and col in (0, 1):
                rows[row][col] = text.strip()
        pins: dict[str, str] = {}
        for p, c in rows:
            if p and c:
                if p in pins and pins[p] != c:
                    self._say(strings.PLAN_TWO_COLOURS.format(p))
                    self._show_code()
                    return False
                pins[p] = c
        return self.set_pins(pins)

    def paste_table(self) -> bool:
        """*Paste pins and colours*: two columns from the clipboard replace the table of the code
        (`plan_config.parse_colour_table`)."""
        if self._why or self.current_code() is None:
            return False
        try:
            pins = parse_colour_table(self._clipboard())
        except EditError as exc:
            self._say(str(exc))
            return False
        return self.set_pins(pins)

    def _notes_done(self) -> None:
        if self._why:
            return
        lines = [x.strip() for x in self.notes_edit.toPlainText().split("\n") if x.strip()]
        if lines != self._values["notes"]:
            self._apply(notes=lines)


class NotesEdit(QPlainTextEdit):
    """The note lines: set when the field loses the focus (a line break is a new line)."""

    def __init__(self, done: Callable[[], None]) -> None:
        super().__init__()
        self._done = done
        self.setTabChangesFocus(True)

    def focusOutEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        super().focusOutEvent(event)
        self._done()


__all__ = [
    "DocumentSection",
    "EditRows",
    "ExampleCodeDialog",
    "HarnessPlanSection",
    "NotesEdit",
]
