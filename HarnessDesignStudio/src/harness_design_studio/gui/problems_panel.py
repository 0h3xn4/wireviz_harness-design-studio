# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The Problems list: every open finding of the project in one list, at the bottom of the window.

    panel = ProblemsList(ctl, theme)
    panel.showRequested.connect(window.show_object)

Columns: severity (icon and word), rule ID, object and message. Click a row to go to the object
(the diagram, the table or the drawing it is in). The filter keeps all, the errors or the warnings.
The list is a plain model/view table, so a project with thousands of findings stays fast; it is
filled when the panel is shown and refreshed (debounced) while it is open. It reads
`ctl.open_findings()`; the window decides where it sits.

The checks of the row layouts (format 4, design of 4.0.0 sections 4.3 and 9): the two warnings
`row_layout_pin_missing` and `row_layout_mate_differs` are findings of the rule
model-inconsistent; the note `row_layout_pins_outside` is no finding of a rule, so the list adds
it from `ctl.layout_notes()` as a row of severity Info (the count says it too). A click on any of
them goes to the connector (`connectorRequested`: the Devices tab for a device connector, the
Inspector for a cable connector); the row menu has *Edit the pin rows of …* (`rowsRequested`), for
the object whose rows the connector takes (`rows_target`).

The checks of format 5 (design of 5.0.0 sections 4.5, 5.3, 6.1, 7.3 to 7.5 and 8.3): their
warnings are findings of model-inconsistent too; a click on one goes where it is put right
(`GO_CODES`: `length_depth_missing` to the cable connector's Inspector, `connectorRequested`, with
*Lengths measured to* and its part; `device_check_stale` to the Devices tab, `deviceRequested`,
with *Mark as checked…*; a finding of a shield group to its harness and its Inspector through
`showRequested`). Its infos are no finding of a rule, so the list adds them from
`ctl.check_notes()` as Info rows with their own sentence (`info_row`): `current_not_worked_out`,
`shield_place_not_stated` and the review's `link_junction`, which the filter Connections keeps.
"""

from collections.abc import Collection, Mapping
from typing import Any, Final

from PySide6.QtCore import QModelIndex, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from harness_design_studio.core.branching import PlugFix, plug_fix
from harness_design_studio.core.checks import Finding
from harness_design_studio.core.issues import Issue
from harness_design_studio.core.model import Project
from harness_design_studio.core.model.physical import TBD_PART_ID
from harness_design_studio.core.row_layout import layout_of
from harness_design_studio.gui import strings
from harness_design_studio.gui.controller import EditorController
from harness_design_studio.gui.tables import Column, DictTableModel, TableView
from harness_design_studio.gui.theme import ThemeManager

_SEVERITY_STATE: Final = {"error": "fail", "warning": "warning", "info": "info"}
_ORDER: Final = {"error": 0, "warning": 1, "info": 2}
FILTERS: Final = (("all", strings.PROBLEMS_FILTER_ALL), ("error", strings.CHECKS_SEVERITY["error"]),
                  ("warning", strings.CHECKS_SEVERITY["warning"]),
                  ("links", strings.PROBLEMS_FILTER_LINKS))  # fmt: skip
LINK_RULE_PREFIX: Final = "link-"  # the rules of the review of connections (core/links.py)

COLUMNS: Final = (
    Column(
        "severity",
        strings.PROBLEMS_COL_SEVERITY,
        state="state",
        fmt=lambda v: str(v[1]),
        sort_key=lambda v: v[0],
        width=110,
    ),
    Column("rule", strings.PROBLEMS_COL_RULE, mono=True, width=180),
    Column("object", strings.PROBLEMS_COL_OBJECT, mono=True, width=160),
    Column("message", strings.PROBLEMS_COL_MESSAGE, tooltip="why", width=520),
)


def finding_why(f: Finding) -> str:
    """Why a finding matters, as the lists, the cards and the Next step page say it. The design
    rule *Approved parts* counts the loose cable ends under their stand-in part (D-201): for them
    the sentence about approving a part would mislead, so they get their own (M4c)."""
    if f.rule == "part-unapproved" and f.object_id == TBD_PART_ID:
        return strings.LOOSE_CARD_WHY
    return f.why


def mated_twice(f: Finding) -> bool:
    """True for the finding of a device connector with plugs of several harnesses
    (`box_connector_mated_twice`, reported through the rule model-inconsistent)."""
    return f.rule == "model-inconsistent" and f.title.startswith(
        f"The device connector {f.object_id} has "
    )


def branch_fix(project: Project, f: Finding) -> PlugFix | None:
    """The fix the editor offers for such a finding (2.3.0, D-243): *Join into one harness* when
    the plugs belong to harnesses drawn by hand, *Use per_connector_group* when they are
    Generate's (`core.branching.plug_fix`); None for any other finding."""
    if f.waiver is not None or not mated_twice(f):
        return None
    return plug_fix(project, f.object_id)


ROW_LAYOUT_CODES: Final = (
    "row_layout_pin_missing", "row_layout_pins_outside", "row_layout_mate_differs",
)  # fmt: skip


def row_layout_code(f: Finding) -> str | None:
    """The check of the row layouts a finding comes from (the warnings are reported through the
    rule model-inconsistent, whose finding ID carries the code), or None."""
    return check_code(f, ROW_LAYOUT_CODES)


def check_code(f: Finding, codes: Collection[str]) -> str | None:
    """The code of `check` among `codes` that a finding of model-inconsistent comes from (its
    finding ID carries the code), or None."""
    if f.rule != "model-inconsistent":
        return None
    return next((code for code in codes if f".{code}." in f.id), None)


# where a click on a warning of format 5 goes: where it is put right (design of 5.0.0 sections
# 4.5 and 8.2): the Inspector of the cable connector (Lengths measured to, its part), the Devices
# tab (Mark as checked…)
GO_CODES: Final = {"length_depth_missing": "connector", "device_check_stale": "device"}


def rows_target(project: Project, object_id: str) -> tuple[str, str] | None:
    """Where the rows of the object of a row layout check are edited: a part as itself, a device
    connector as itself (its own rows, or the dialog that starts from its part's), a cable
    connector at the part or device connector it takes its rows from. None when there is none."""
    if object_id in project.parts:
        return "part", object_id
    box = project.connectors.get(object_id)
    if box is not None and box.unit_id is not None:
        return "connector", object_id
    for h in project.harnesses.values():
        for c in h.connectors:
            if c.id == object_id:
                rows = layout_of(project, c)
                if rows is None:
                    return None
                return ("part" if rows.source == "part" else "connector"), rows.source_id
    return None


def note_row(issue: Issue) -> dict[str, Any]:
    """A row for a note of the check of the row layouts (not a finding of a rule)."""
    return {
        "severity": (_ORDER["info"], strings.CHECKS_SEVERITY["info"]),
        "state": "info",
        "rule": issue.code,
        "object": issue.object_id or strings.CHECKS_WHOLE_DESIGN,
        "message": issue.message,
        "why": strings.PROBLEMS_ROWS_NOTE_WHY,
        "object_id": issue.object_id,
        "level": "info",
        "rows": True,
    }


def info_row(issue: Issue) -> dict[str, Any]:
    """A row for an info of format 5 (`ctl.check_notes`, not a finding of a rule): its own
    sentence under Why; an info of the review of a connection (`link_junction`) is kept by the
    filter Connections."""
    return {
        "severity": (_ORDER["info"], strings.CHECKS_SEVERITY["info"]),
        "state": "info",
        "rule": issue.code,
        "object": issue.object_id or strings.CHECKS_WHOLE_DESIGN,
        "message": issue.message,
        "why": strings.PROBLEMS_NOTE_WHY.get(issue.code, ""),
        "object_id": issue.object_id,
        "level": "info",
        "link": issue.code.startswith("link_"),
    }


def problem_row(f: Finding) -> dict[str, Any]:
    word = strings.CHECKS_SEVERITY.get(f.severity, f.severity)
    order = _ORDER.get(f.severity, 3)
    return {
        "severity": (order, word),
        "state": _SEVERITY_STATE.get(f.severity, "info"),
        "rule": f.rule,
        "object": f.object_id or strings.CHECKS_WHOLE_DESIGN,
        "message": f.title,
        "why": finding_why(f),
        "object_id": f.object_id,
        "level": f.severity,
    }


class ProblemsList(QWidget):
    showRequested = Signal(str)  # the ID of the object a row names
    detailsRequested = Signal(str)  # the same, for its problems as cards in the inspector
    joinRequested = Signal(str)  # a device connector: join the harnesses that plug into it
    segmentationRequested = Signal()  # open Settings at the segmentation choice
    connectorRequested = Signal(str)  # a row layout check: go to the connector (or part) it names
    rowsRequested = Signal(str, str)  # ("part" | "connector", ID): edit the pin rows there
    deviceRequested = Signal(str)  # a device whose check is stale: the Devices tab (5.0.0)

    def __init__(
        self, ctl: EditorController, theme: ThemeManager, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.ctl, self.theme = ctl, theme
        self.setObjectName("problems-panel")
        self.setAccessibleName(strings.PROBLEMS_PANEL_NAME)
        self._dirty = True
        self._level = "all"
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)  # typing and dragging cause many changes: read once
        self._timer.timeout.connect(self.refresh)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.space(8), theme.space(4), theme.space(8), theme.space(8))
        bar = QHBoxLayout()
        self.filters: dict[str, QToolButton] = {}
        group = QButtonGroup(self)
        for key, label in FILTERS:
            b = QToolButton()
            b.setObjectName(f"problems-filter-{key}")
            b.setText(label)
            b.setCheckable(True)
            b.setProperty("toggle", True)
            b.setAccessibleName(label)
            group.addButton(b)
            bar.addWidget(b)
            self.filters[key] = b
            b.clicked.connect(lambda _c=False, k=key: self._filter(k))
        self.filters["all"].setChecked(True)
        self.filters["links"].setToolTip(strings.PROBLEMS_FILTER_LINKS_TIP)
        self.filters["links"].setVisible(bool(ctl.project.links))
        self.count = QLabel()
        self.count.setObjectName("problems-count")
        self.count.setProperty("muted", True)
        bar.addWidget(self.count)
        bar.addStretch(1)
        outer.addLayout(bar)
        self.model = DictTableModel(COLUMNS, (), theme)
        self.table = TableView(self.model, theme, name=strings.PROBLEMS_PANEL_NAME)
        self.table.setObjectName("problems-table")
        outer.addWidget(self.table, 1)
        self.empty = QLabel(strings.PROBLEMS_EMPTY)
        self.empty.setObjectName("problems-empty")
        self.empty.setProperty("muted", True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.empty)
        self.table.clicked.connect(self._clicked)
        self.table.activated.connect(self._clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        details = QShortcut(QKeySequence("Shift+Return"), self.table)
        details.setContext(Qt.ShortcutContext.WidgetShortcut)
        details.activated.connect(lambda: self._details(self.table.currentIndex()))
        ctl.changed.connect(self._changed)
        ctl.drcStateChanged.connect(self._changed)

    # ---- data ---------------------------------------------------------------------------------
    def _changed(self, *_args: object) -> None:
        self._dirty = True
        if self.isVisible():
            self._timer.start()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        """Read the open findings now (errors first, then by rule and object)."""
        self._dirty = False
        found = sorted(
            self.ctl.open_findings(),
            key=lambda f: (_ORDER.get(f.severity, 3), f.rule, f.object_id),
        )
        project = self.ctl.project
        rows = []
        for f in found:
            row = problem_row(f)
            row["fix"] = branch_fix(project, f)
            if row_layout_code(f) is not None:
                row["rows"] = True
            go = check_code(f, GO_CODES)
            if go is not None:
                row["go"] = GO_CODES[go]
            rows.append(row)
        notes = self.ctl.layout_notes()
        rows += [note_row(n) for n in sorted(notes, key=lambda n: (n.object_id or "", n.message))]
        infos = self.ctl.check_notes()
        rows += [
            info_row(n) for n in sorted(infos, key=lambda n: (n.code, n.object_id or "", n.message))
        ]
        for row in rows:
            if row.get("rows") and row.get("object_id"):
                row["rows_fix"] = rows_target(project, str(row["object_id"]))
        self.model.update_rows(rows)
        self.filters["links"].setVisible(bool(self.ctl.project.links) or self._level == "links")
        self.empty.setVisible(not rows)
        self.table.setVisible(bool(rows))
        self._apply_filter()

    def _show_count(self) -> None:
        """ "Problems (24)", and "Problems (14 of 24)" while a filter hides some: the number in the
        window's Problems button is the whole list, so the two always agree."""
        total, shown = self.model.rowCount(), self.table.proxy.rowCount()
        self.count.setText(
            strings.PROBLEMS_BUTTON.format(total)
            if shown == total
            else strings.PROBLEMS_BUTTON_OF.format(shown, total)
        )

    def total(self) -> int:
        return self.model.rowCount()

    def rows(self) -> list[dict[str, Any]]:
        return [dict(r) if isinstance(r, dict) else {} for r in self.model.rows()]

    # ---- filter and jump ----------------------------------------------------------------------
    def _filter(self, key: str) -> None:
        self._level = key
        self._apply_filter()

    def show_filter(self, key: str) -> None:
        """Choose a filter from outside (Check my connections shows the connections)."""
        if key in self.filters:
            self.filters[key].setVisible(True)
            self.filters[key].setChecked(True)
            self._filter(key)

    def _apply_filter(self) -> None:
        level = self._level
        if level == "links":
            self.table.proxy.set_predicate(
                lambda row: (
                    isinstance(row, Mapping)
                    and (
                        str(row.get("rule", "")).startswith(LINK_RULE_PREFIX)
                        or bool(row.get("link"))
                    )
                )
            )
        else:
            self.table.proxy.set_predicate(
                None
                if level == "all"
                else lambda row: isinstance(row, Mapping) and row.get("level") == level
            )
        self._show_count()

    def _object_of(self, index: QModelIndex) -> str:
        if not index.isValid():
            return ""
        row = self.model.row(self.table.proxy.mapToSource(index).row())
        return str(row.get("object_id", "")) if isinstance(row, Mapping) else ""

    def _details(self, index: QModelIndex) -> None:
        """The inspector's Problems tab for the object: the same findings as cards, with the
        fix and waive buttons."""
        target = self._object_of(index)
        if target:
            self.detailsRequested.emit(target)

    def _menu(self, pos: QPoint) -> None:
        index = self.table.indexAt(pos)
        target = self._object_of(index)
        if not target:
            return
        menu = QMenu(self.table)
        menu.setAccessibleName(strings.PROBLEMS_MENU)
        menu.addAction(strings.PROBLEMS_GO_TO.format(target), lambda: self._clicked(index))
        menu.addAction(strings.PROBLEMS_DETAILS, lambda: self._details(index))
        row = self.model.row(self.table.proxy.mapToSource(index).row())
        fix = row.get("fix") if isinstance(row, Mapping) else None
        rows_fix = row.get("rows_fix") if isinstance(row, Mapping) else None
        if isinstance(rows_fix, tuple):
            menu.addSeparator()
            kind, ident = rows_fix
            act = menu.addAction(
                strings.PROBLEMS_EDIT_ROWS.format(ident),
                lambda: self.rowsRequested.emit(kind, ident),
            )
            act.setObjectName("problems-fix-rows")
            act.setEnabled(not self.ctl.read_only)
        if isinstance(fix, PlugFix):
            menu.addSeparator()
            if fix.kind == "join":
                act = menu.addAction(strings.FIX_JOIN, lambda: self.joinRequested.emit(fix.box_id))
            else:
                act = menu.addAction(strings.FIX_MODE, self.segmentationRequested.emit)
            act.setObjectName(f"problems-fix-{fix.kind}")
            act.setEnabled(not self.ctl.read_only)
        menu.popup(self.table.viewport().mapToGlobal(pos))
        self.menu = menu  # (kept for tests)

    def _clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        source = self.table.proxy.mapToSource(index)
        row = self.model.row(source.row())  # (a dict: this table is built from dicts)
        target = row.get("object_id", "") if isinstance(row, Mapping) else ""
        go = row.get("go") if isinstance(row, Mapping) else None
        if target and isinstance(row, Mapping) and (row.get("rows") or go == "connector"):
            self.connectorRequested.emit(str(target))  # (Show goes to the connector, section 9)
        elif target and go == "device":
            self.deviceRequested.emit(str(target))
        elif target:
            self.showRequested.emit(str(target))
