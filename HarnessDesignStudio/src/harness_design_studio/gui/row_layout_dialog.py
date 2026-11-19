# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The pin rows of a connector in the editor (format 4, D-251; design of 4.0.0 section 9): the
dialog *Pin rows of J1* (or *of part EX-MICROD-21-F*) and the words that say where the rows of a
connector come from.

    rows_words(project, connector)   # "1–11 / 12–21, from part EX-MICROD-21-F", "…, own rows", "none"
    dlg = PinRowsDialog(window, theme, project, connector="DEV1-J1")   # or part="EX-MICROD-21-F"
    if run_dialog(dlg) == QDialog.DialogCode.Accepted:
        dlg.action, dlg.typed_rows()     # "set" | "share" | "back", the rows typed (None: no rows)

The dialog takes the text form of section 6.1 one row per line (`1–11` on the first line, `12–21`
on the second), the row lengths with **Fill** (`11, 10`), and the ring mark as a check box. While
typing it asks the plans of `core/row_layout_edit.py` whether the rows can be stored and shows the
plan's sentence on a line under the fields, keeping **Set rows** off (*the row layout names pin
22; DEV1-J1 has no pin 22*, *pin 7 is in row 1 and in row 2*). For a part it names the connectors
of the part that would not have a pin of the rows (the warning `row_layout_pin_missing`). The
buttons *Use for every connector of this part* and *Back to the part's rows* end the dialog with
that action; *Clear* empties the box. The dialog never changes the project: the window runs the
action through the controller as one undo step.
"""

from typing import Literal

from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from harness_design_studio.core.clone import clone_with
from harness_design_studio.core.commands import Put
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.model import Connector, Project, RowLayout, evolve
from harness_design_studio.core.row_layout import (
    from_lengths,
    layout_of,
    layout_text,
    parse_lengths,
    parse_text,
)
from harness_design_studio.core.row_layout_edit import plan_set_row_layout, plan_share_with_part
from harness_design_studio.gui import strings
from harness_design_studio.gui.dialog_base import Dialog
from harness_design_studio.gui.notice import InlineNotice
from harness_design_studio.gui.theme import ThemeManager, mark_mono
from harness_design_studio.gui.wrap_label import WrapLabel

Action = Literal["set", "share", "back"]


def rows_words(project: Project, connector: Connector) -> str:
    """The rows a connector has (section 3) and where they come from, in words: *1–11 / 12–21,
    from part EX-MICROD-21-F*, *…, own rows*, *…, from DEV2-J1, the device connector it plugs
    into*, or *none*."""
    rows = layout_of(project, connector)
    if rows is None:
        return strings.ROWS_NONE
    text = layout_text(RowLayout(rows=[list(r) for r in rows.rows if r], rings=rows.rings))
    if not text:  # (no name of the rows is a pin of this connector)
        text = strings.ROWS_NONE
    if rows.source == "own":
        return strings.ROWS_OWN.format(rows=text)
    if rows.source == "part":
        return strings.ROWS_FROM_PART.format(rows=text, part=rows.source_id)
    return strings.ROWS_FROM_MATED.format(rows=text, box=rows.source_id)


def part_rows_words(project: Project, part_id: str) -> str:
    """The rows of a part in the text form, or *none*."""
    part = project.parts.get(part_id)
    return layout_text(part.row_layout) if part and part.row_layout else strings.ROWS_NONE


def row_lines(layout: RowLayout | None) -> str:
    """A layout as the dialog's box shows it: one row per line, without the ring mark."""
    if layout is None:
        return ""
    return "\n".join(layout_text(RowLayout(rows=[row])) for row in layout.rows)


def parse_lines(text: str, rings: bool) -> RowLayout | None:
    """The layout of the box's lines (empty lines left out) and the ring mark; None for no rows.
    Raises `ValueError` with the sentence of the text form (section 6.1)."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    layout = parse_text(" / ".join(lines))
    if layout is None:
        return None
    return RowLayout(rows=layout.rows, rings=rings or layout.rings) if rings else layout


class PinRowsDialog(Dialog):
    """*Pin rows of J1* (a box connector, `connector=`) or *of part …* (`part=`). See the module
    text. `action` is what ended it with OK: "set" (Set rows: the rows typed, or none), "share"
    (Use for every connector of this part) or "back" (Back to the part's rows)."""

    def __init__(
        self,
        parent: QWidget | None,
        theme: ThemeManager,
        project: Project,
        *,
        part: str | None = None,
        connector: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.theme, self.project = theme, project
        self.part_id, self.connector_id = part, connector
        self.action: Action = "set"
        box = project.connectors.get(connector or "")
        self.connector = box
        target = connector or part or ""
        title = (
            strings.PR_TITLE_CONNECTOR.format(target)
            if connector
            else strings.PR_TITLE_PART.format(target)
        )
        self.setWindowTitle(title)
        self.setObjectName("pin-rows-dialog")
        self.setAccessibleName(title)
        lay = QVBoxLayout(self)
        if box is not None:
            pins = ", ".join(p.id for p in box.pins[:24]) + (" …" if len(box.pins) > 24 else "")
            intro = strings.PR_INTRO_CONNECTOR.format(box.id, pins)
            now = rows_words(project, box)
            start = box.row_layout or (
                project.parts[box.part_id].row_layout if box.part_id in project.parts else None
            )
        else:
            intro = strings.PR_INTRO_PART
            now = part_rows_words(project, part or "")
            found = project.parts.get(part or "")
            start = found.row_layout if found is not None else None
        self.start = start
        self.intro = WrapLabel(intro)
        self.intro.setObjectName("pin-rows-intro")
        lay.addWidget(self.intro)
        self.now = WrapLabel(strings.PR_NOW.format(now))
        self.now.setObjectName("pin-rows-now")
        self.now.setProperty("muted", True)
        lay.addWidget(self.now)
        self.rows_edit = QPlainTextEdit()
        self.rows_edit.setObjectName("pin-rows-text")
        self.rows_edit.setAccessibleName(strings.PR_ROWS)
        self.rows_edit.setToolTip(strings.PR_ROWS_TIP)
        self.rows_edit.setTabChangesFocus(True)
        mark_mono(self.rows_edit)
        self.rows_edit.setPlainText(row_lines(start))
        self.rows_edit.setMinimumHeight(theme.px(96))
        lay.addWidget(self.rows_edit, 1)
        lengths = QHBoxLayout()
        self.lengths_edit = QLineEdit()
        self.lengths_edit.setObjectName("pin-rows-lengths")
        self.lengths_edit.setAccessibleName(strings.PR_LENGTHS)
        self.lengths_edit.setToolTip(strings.PR_LENGTHS_TIP)
        self.lengths_edit.setPlaceholderText(strings.PR_LENGTHS_HINT)
        self.fill_btn = QPushButton(strings.PR_FILL)
        self.fill_btn.setObjectName("pin-rows-fill")
        self.fill_btn.setAccessibleName(strings.PR_FILL)
        self.fill_btn.setToolTip(strings.PR_FILL_TIP)
        lengths.addWidget(QLabel(strings.PR_LENGTHS))
        lengths.addWidget(self.lengths_edit, 1)
        lengths.addWidget(self.fill_btn)
        lay.addLayout(lengths)
        self.rings = QCheckBox(strings.PR_RINGS)
        self.rings.setObjectName("pin-rows-rings")
        self.rings.setAccessibleName(strings.PR_RINGS)
        self.rings.setToolTip(strings.PR_RINGS_TIP)
        self.rings.setChecked(bool(start and start.rings))
        lay.addWidget(self.rings)
        self.notice = InlineNotice(theme)
        self.notice.setObjectName("pin-rows-error")
        lay.addWidget(self.notice)
        self.hint = WrapLabel()
        self.hint.setObjectName("pin-rows-hint")
        self.hint.setProperty("muted", True)
        lay.addWidget(self.hint)
        actions = QHBoxLayout()
        self.share_btn = QPushButton(strings.PR_SHARE)
        self.share_btn.setObjectName("pin-rows-share")
        self.share_btn.setAccessibleName(strings.PR_SHARE)
        self.back_btn = QPushButton(strings.PR_BACK)
        self.back_btn.setObjectName("pin-rows-back")
        self.back_btn.setAccessibleName(strings.PR_BACK)
        self.clear_btn = QPushButton(strings.PR_CLEAR)
        self.clear_btn.setObjectName("pin-rows-clear")
        self.clear_btn.setAccessibleName(strings.PR_CLEAR)
        self.clear_btn.setToolTip(strings.PR_CLEAR_TIP)
        for b in (self.share_btn, self.back_btn):
            b.setVisible(box is not None)
            actions.addWidget(b)
        actions.addWidget(self.clear_btn)
        actions.addStretch(1)
        lay.addLayout(actions)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel = QPushButton(strings.CANCEL)
        self.cancel.setObjectName("dlg-cancel")
        self.cancel.clicked.connect(self.reject)
        self.ok = QPushButton(strings.PR_OK)
        self.ok.setObjectName("dlg-ok")
        self.ok.setAccessibleName(strings.PR_OK)
        self.ok.setProperty("primary", True)
        self.ok.setAutoDefault(True)
        self.ok.setDefault(True)
        self.ok.clicked.connect(lambda: self._finish("set"))
        row.addWidget(self.cancel)
        row.addWidget(self.ok)
        lay.addLayout(row)
        self.share_btn.clicked.connect(lambda: self._finish("share"))
        self.back_btn.clicked.connect(lambda: self._finish("back"))
        self.clear_btn.clicked.connect(self.clear_rows)
        self.fill_btn.clicked.connect(self.fill)
        self.lengths_edit.returnPressed.connect(self.fill)
        self.rows_edit.textChanged.connect(self.revalidate)
        self.rings.toggled.connect(self.revalidate)
        self.lengths_edit.textChanged.connect(lambda _t: self._lengths_error(""))
        self.revalidate()

    # ---- what was typed ----------------------------------------------------------------------
    def typed_rows(self) -> RowLayout | None:
        """The rows typed, None for none. Raises `ValueError` for a text that is not rows."""
        return parse_lines(self.rows_edit.toPlainText(), self.rings.isChecked())

    def fill(self) -> bool:
        """Write the rows of the row lengths into the box (on a connector its pins in pin order,
        on a part the names 1 to N); a mistake is said on the line under the fields."""
        try:
            lengths = parse_lengths(self.lengths_edit.text())
            pins = self.connector.pins if self.connector is not None else None
            layout = from_lengths(lengths, pins)
        except ValueError as exc:
            self._lengths_error(str(exc))
            return False
        self.rows_edit.setPlainText(row_lines(layout))
        return True

    def clear_rows(self) -> None:
        """*Clear*: empty the box (Set rows then removes the rows)."""
        self.rows_edit.setPlainText("")
        self.rings.setChecked(False)

    # ---- checking ----------------------------------------------------------------------------
    def check(self) -> str | None:
        """The sentence that keeps Set rows off, or None."""
        layout = self.typed_rows()
        if layout is None:
            return None
        plan_set_row_layout(
            self.project, layout, part=self.part_id, connector=self.connector_id
        )  # (raises EditError with the plan's sentence)
        return None

    def _view_with(self, layout: RowLayout | None) -> Project:
        """The project as it would be with these rows on the object (to ask the plans and the
        resolution of section 3 about it); never stored."""
        p = self.project
        if self.connector is not None:
            c = evolve(self.connector, row_layout=layout)
            return clone_with(p, [Put("connectors", c)])
        part = evolve(p.parts[self.part_id or ""], row_layout=layout)
        return clone_with(p, [Put("parts", part)])

    def missing(self, layout: RowLayout | None) -> list[str]:
        """For a part: a sentence for each connector of the part (a box connector without rows of
        its own, a cable connector) that does not have a pin the rows name."""
        if layout is None or self.part_id is None:
            return []
        view = self._view_with(layout)
        owners = [c for c in view.connectors.values() if c.part_id == self.part_id]
        owners += [c for h in view.harnesses.values() for c in h.connectors]
        out = []
        for c in sorted(owners, key=lambda x: x.id):
            rows = layout_of(view, c)
            if rows is None or rows.source_id != self.part_id or not rows.left_out:
                continue
            out.append(
                strings.PR_MISSING.format(
                    connector=c.id,
                    pins=", ".join(rows.left_out),
                    them=strings.PR_MISSING_IT
                    if len(rows.left_out) == 1
                    else strings.PR_MISSING_THEM,
                )
            )
        return out

    def _share_problem(self, layout: RowLayout | None) -> str | None:
        """Why *Use for every connector of this part* cannot be used with these rows (None: it
        can)."""
        if self.connector is None or layout is None:
            return strings.PR_BACK_NONE.format(self.connector_id or "")
        if self.connector.part_id not in self.project.parts:
            return strings.PR_SHARE_NO_PART.format(self.connector.part_id)
        try:
            plan_share_with_part(self._view_with(layout), self.connector.id)
        except EditError as exc:
            return str(exc)
        return None

    def revalidate(self, *_: object) -> None:
        """The text changed: check it again (the reason shows at once: a box that has text is
        either rows or a mistake)."""
        try:
            problem = self.check()
            layout = self.typed_rows()
        except (EditError, ValueError) as exc:
            problem, layout = str(exc), None
        if problem:
            self.notice.show_notice("error", problem)
        else:
            self.notice.clear()
        self.ok.setEnabled(problem is None)
        hint = ""
        if problem is None and layout is None:
            has = (
                self.connector.row_layout is not None
                if self.connector is not None
                else self.start is not None
            )
            target = self.connector_id or self.part_id or ""
            if not has:
                hint = strings.PR_EMPTY_NOTHING
            elif self.connector is not None:
                hint = strings.PR_EMPTY_CONNECTOR.format(target)
            else:
                hint = strings.PR_EMPTY_PART.format(target)
        elif problem is None:
            hint = " ".join(self.missing(layout))
        self.hint.setText(hint)
        self.hint.setVisible(bool(hint))
        if self.connector is not None:
            share_why = None if problem else self._share_problem(layout)
            self.share_btn.setEnabled(problem is None and share_why is None)
            self.share_btn.setToolTip(
                share_why or problem or strings.PR_SHARE_TIP.format(self.connector.part_id)
            )
            own = self.connector.row_layout is not None
            self.back_btn.setEnabled(own)
            self.back_btn.setToolTip(
                strings.PR_BACK_TIP.format(self.connector.id)
                if own
                else strings.PR_BACK_NONE.format(self.connector.id)
            )

    def _lengths_error(self, text: str) -> None:
        if text:
            self.notice.show_notice("error", text)
        else:
            self.revalidate()

    def _finish(self, action: Action) -> None:
        self.action = action
        self.accept()
