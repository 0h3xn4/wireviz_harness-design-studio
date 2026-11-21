# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The Review area, a page of its own: what a reviewer of one harness checks (4.3.0, milestone E3).

    page = ReviewPage(theme)
    page.show_input(ReviewInput(harnesses=..., view=review.review_view(project, h, findings), ...))

The page shows a `core.review.ReviewView` (the blocks of the Review sheet of the build workbook,
from the same function and the findings the window already has) and calls back through its
signals; the window does the rest (`docs/ait/DESIGN_4.3_REVIEW_VIEW.md`, section 5). At the top the
harness, its state, a summary line, *Release…* and *Edit the checklist…*; then the blocks, each a
table with an empty state and the buttons that act on the row chosen in it: the checklist with a
tick box per point (*Tick all*, *Clear*), the findings of the harness and of the whole project
(*Show*, *Explain*, *Waive…*, *Accept as deviation…*), the values still open (*Show*, *Supply
value…*, *Show all*), the sources (*Copy link*, *Show*, and the column *Library* the sheet cannot
have), and how the numbers were made. The ticks are the window's to keep (on this computer only);
the page never says that a point or a finding passed.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from harness_design_studio.core import review
from harness_design_studio.core.checks import Finding
from harness_design_studio.gui import strings
from harness_design_studio.gui.pages import _page
from harness_design_studio.gui.states import StateChip
from harness_design_studio.gui.tables import Column, DictTableModel, TableView
from harness_design_studio.gui.theme import ThemeManager
from harness_design_studio.gui.wrap_label import WrapLabel

TABLE_BLOCKS = ("checklist", "findings", "project", "open", "sources")
_SEVERITY_STATE = {"error": "fail", "warning": "warning", "note": "info"}
_RELEASE_STATE = {review.STOPS: "fail", review.REASON: "warning"}
_MIN_ROWS, _MAX_ROWS = 3, 10  # the height of a block's table, in rows
# the rows of *Values still open* that are about the configuration, not about items of the harness
CONFIG_ROWS = ("Configuration files still placeholders", "Engineering values not set")


@dataclass(frozen=True)
class ReviewInput:
    """What the window hands the page: the harnesses to choose from (ID, text), the view of the one
    chosen (None for a project without a harness), the state chip of the harness, the points ticked
    on this computer, whether older ticks were dropped (the list or the design changed), whether a
    check is running, whether the project is read-only, the findings by ID (for *Waive…*) and the
    library state of each device connector the harness plugs into, in words."""

    harnesses: tuple[tuple[str, str], ...] = ()
    view: review.ReviewView | None = None
    state: str = "draft"
    ticked: frozenset[int] = frozenset()
    dropped: bool = False
    running: bool = False
    read_only: bool = False
    findings: Mapping[str, Finding] = field(default_factory=dict)
    library: Mapping[str, str] = field(default_factory=dict)


def _cells(row: review.Row) -> dict[Any, Any]:
    out: dict[Any, Any] = dict(enumerate(row.cells))
    out["ref"] = row.ref
    return out


def _count(n: int, one: str, many: str) -> str:
    return one.format(n) if n == 1 else many.format(n)


def _joined(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + strings.RV_AND + parts[-1]


def summary_text(view: review.ReviewView, ticked: frozenset[int]) -> str:
    """`W002, version 1.0.0, draft: 3 of 26 points ticked; 1 thing stops the release; 7 warnings
    and 11 notes open; 8 values still open` (design of 4.3.0, section 5.2)."""
    n = len(view.points)
    if not n:
        points = strings.RV_NO_CHECKLIST
    elif view.status == "released":
        points = _count(n, strings.RV_POINTS_ONE, strings.RV_POINTS)
    else:
        done = len([t for t in ticked if 1 <= t <= n])
        points = strings.RV_TICKED_ONE.format(done) if n == 1 else strings.RV_TICKED.format(done, n)
    stopping = sum(
        1
        for key, col in (("findings", 6), ("project", 4), ("open", 4))
        for row in view.block(key).rows
        if row.cells[col] == review.STOPS
    )
    stops = (
        strings.RV_STOPS_NONE
        if not stopping
        else _count(stopping, strings.RV_STOPS_ONE, strings.RV_STOPS)
    )
    words = {"error": 0, "warning": 0, "note": 0}
    for row in view.block("findings").rows:
        if str(row.cells[5]).startswith("open"):
            words[str(row.cells[0])] += 1
    found = [f"{k} {strings.RV_COUNT_WORDS[w][0 if k == 1 else 1]}" for w, k in words.items() if k]
    findings = (
        strings.RV_FINDINGS_OPEN.format(_joined(found)) if found else strings.RV_FINDINGS_NONE
    )
    rows = len(view.block("open").rows)
    values = (
        strings.RV_VALUES_NONE
        if not rows
        else _count(rows, strings.RV_VALUES_ONE, strings.RV_VALUES)
    )
    return strings.RV_SUMMARY.format(
        harness=view.harness_id,
        version=view.version,
        status=strings.RV_STATUS_WORDS.get(view.status, view.status),
        parts="; ".join((points, stops, findings, values)),
    )


class ChecklistModel(DictTableModel):
    """The points of the checklist with a tick box per point in the column *Done*; a tick calls
    `on_tick(number, on)`. With `checkable` off (a released harness, a read-only project) the
    column shows nothing and takes no tick."""

    def __init__(
        self, columns: list[Column], theme: ThemeManager, on_tick: Callable[[int, bool], None]
    ) -> None:
        super().__init__(columns, [], theme)
        self.on_tick = on_tick
        self.checkable = True
        self.done_column = len(columns) - 1

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        base = super().flags(index)
        if index.isValid() and self.checkable and index.column() == self.done_column:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if (
            role == Qt.ItemDataRole.CheckStateRole
            and index.isValid()
            and self.checkable
            and index.column() == self.done_column
        ):
            row = self.row(index.row())
            done = isinstance(row, Mapping) and bool(row.get("done"))
            return Qt.CheckState.Checked if done else Qt.CheckState.Unchecked
        return super().data(index, role)

    def setData(  # noqa: N802
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if role != Qt.ItemDataRole.CheckStateRole or not self.checkable or not index.isValid():
            return False
        row = self.row(index.row())
        if not isinstance(row, Mapping):
            return False
        self.on_tick(int(row["ref"]), Qt.CheckState(value) == Qt.CheckState.Checked)
        return True


def _button(text: str, tip: str, name: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName(name)
    b.setAccessibleName(text.rstrip("…"))
    b.setToolTip(tip)
    return b


def _state(col: int, states: Mapping[str, str]) -> Callable[[Any], str | None]:
    """The state chip of a cell from its words (the words stay: colour is never alone)."""
    return lambda row: states.get(str(row.get(col))) if isinstance(row, Mapping) else None


def _long(col: int) -> Callable[[Any], str]:
    """The tooltip of a long cell: its whole text (a table elides it)."""
    return lambda row: str(row.get(col, "")) if isinstance(row, Mapping) else ""


class ReviewPage(QScrollArea):
    harnessPicked = Signal(str)
    releaseRequested = Signal(str)
    checklistRequested = Signal()
    ticksChanged = Signal(str, object)  # harness ID, frozenset of point numbers
    showRequested = Signal(str)  # an object ID (a finding's object)
    explainRequested = Signal(str, str)  # rule, object ID
    waiveRequested = Signal(str)  # finding ID
    deviateRequested = Signal(str)  # finding ID
    openShowRequested = Signal(str, str)  # the row's What, its first item
    valueRequested = Signal(str)  # an engineering value, "file.key"
    showAllRequested = Signal(str, str)  # the row's What, its first item
    copyRequested = Signal(str)  # a link
    sourceRequested = Signal(str)  # a device connector or a part

    def __init__(self, theme: ThemeManager) -> None:
        super().__init__()
        self.theme = theme
        self._input = ReviewInput()
        self._ticked: frozenset[int] = frozenset()
        self._filling = False
        page, column = _page(theme, "review-page", strings.RV_TITLE)
        self.setObjectName("review-page")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidget(page.takeWidget())
        self.setAccessibleName(strings.RV_TITLE)
        intro = WrapLabel(strings.RV_INTRO)
        intro.setObjectName("review-intro")
        intro.setProperty("muted", True)
        column.addWidget(intro)
        # ---- the harness, its state, the two buttons
        head = QHBoxLayout()
        label = QLabel(strings.RV_HARNESS)
        self.harness = QComboBox()
        self.harness.setObjectName("review-harness")
        self.harness.setAccessibleName(strings.RV_HARNESS)
        self.harness.setToolTip(strings.RV_HARNESS_TIP)
        self.harness.setMinimumContentsLength(18)
        label.setBuddy(self.harness)
        self.harness.activated.connect(self._picked)
        self.state = StateChip(theme, "draft")
        self.state.setObjectName("review-state")
        self.state.setAccessibleName(strings.RV_STATE_NAME)
        self.release_button = _button(strings.RV_RELEASE, strings.RV_RELEASE_TIP, "review-release")
        self.release_button.setProperty("primary", True)
        self.release_button.clicked.connect(lambda _c=False: self._release())
        self.checklist_button = _button(
            strings.RV_EDIT_CHECKLIST, strings.RV_EDIT_CHECKLIST_TIP, "review-edit-checklist"
        )
        self.checklist_button.clicked.connect(lambda _c=False: self.checklistRequested.emit())
        head.addWidget(label)
        head.addWidget(self.harness)
        head.addWidget(self.state)
        head.addStretch(1)
        head.addWidget(self.release_button)
        head.addWidget(self.checklist_button)
        column.addLayout(head)
        self.none = WrapLabel(strings.RV_NO_HARNESS)
        self.none.setObjectName("review-none")
        self.none.setProperty("muted", True)
        column.addWidget(self.none)
        self.summary = WrapLabel("")
        self.summary.setObjectName("review-summary")
        self.release_line = WrapLabel("")
        self.release_line.setObjectName("review-release-line")
        self.release_line.setTextFormat(Qt.TextFormat.PlainText)
        self.running = WrapLabel(strings.RV_RUNNING)
        self.running.setObjectName("review-running")
        self.running.setProperty("muted", True)
        self.dropped = WrapLabel(strings.RV_DROPPED)
        self.dropped.setObjectName("review-dropped")
        self.released = WrapLabel("")
        self.released.setObjectName("review-released")
        self.released.setProperty("muted", True)
        self.body = QWidget()
        self.body.setObjectName("review-body")
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(theme.space(12))
        for w in (self.summary, self.release_line, self.running, self.dropped, self.released):
            body.addWidget(w)
        self.headings: dict[str, QLabel] = {}
        self.empties: dict[str, WrapLabel] = {}
        self.tables: dict[str, TableView] = {}
        self.models: dict[str, DictTableModel] = {}
        self.buttons: dict[str, QPushButton] = {}
        self.checklist = ChecklistModel(
            [
                Column(0, review.CHECKLIST_COLUMNS[0], numeric=True, width=48),
                Column(1, review.CHECKLIST_COLUMNS[1], tooltip=_long(1), width=560),
                Column(
                    "done",
                    strings.RV_DONE,
                    tooltip=lambda _r: strings.RV_DONE_TIP,
                    fmt=lambda _v: "",
                    width=72,
                ),  # fmt: skip
            ],
            theme,
            self._tick,
        )
        self._block(body, "checklist", self.checklist)
        self._buttons(body, "checklist", (
            ("tick_all", strings.RV_TICK_ALL, strings.RV_TICK_ALL_TIP, self._tick_all),
            ("clear", strings.RV_CLEAR, strings.RV_CLEAR_TIP, self._clear),
        ))  # fmt: skip
        finding_columns = [
            Column(
                0,
                review.FINDING_COLUMNS[0],
                state=_state(0, _SEVERITY_STATE),
                width=100,
            ),  # fmt: skip
            Column(1, review.FINDING_COLUMNS[1], mono=True),
            Column(2, review.FINDING_COLUMNS[2], mono=True, tooltip=_long(2)),
            Column(3, review.FINDING_COLUMNS[3], mono=True),
            Column(4, review.FINDING_COLUMNS[4], tooltip=_long(4), width=320),
            Column(5, review.FINDING_COLUMNS[5], tooltip=_long(5), width=160),
            Column(6, review.FINDING_COLUMNS[6], state=_state(6, _RELEASE_STATE)),
        ]
        self._block(body, "findings", DictTableModel(finding_columns, [], theme))
        self._buttons(body, "findings", self._finding_buttons("findings"))
        project_columns = [
            Column(
                0,
                review.PROJECT_COLUMNS[0],
                state=_state(0, _SEVERITY_STATE),
                width=100,
            ),  # fmt: skip
            Column(1, review.PROJECT_COLUMNS[1], mono=True),
            Column(2, review.PROJECT_COLUMNS[2], mono=True, tooltip=_long(2)),
            Column(3, review.PROJECT_COLUMNS[3], tooltip=_long(3), width=360),
            Column(4, review.PROJECT_COLUMNS[4], state=_state(4, _RELEASE_STATE)),
        ]
        self._block(body, "project", DictTableModel(project_columns, [], theme))
        self._buttons(body, "project", self._finding_buttons("project"))
        open_columns = [
            Column(0, review.OPEN_COLUMNS[0], width=240),
            Column(1, review.OPEN_COLUMNS[1], numeric=True),
            Column(2, review.OPEN_COLUMNS[2], mono=True, tooltip=_long(2), width=260),
            Column(3, review.OPEN_COLUMNS[3], tooltip=_long(3), width=200),
            Column(4, review.OPEN_COLUMNS[4], state=_state(4, _RELEASE_STATE)),
        ]
        self._block(body, "open", DictTableModel(open_columns, [], theme))
        self._buttons(body, "open", (
            ("open_show", strings.RV_SHOW, strings.RV_SHOW_TIP, self._open_show),
            ("supply", strings.RV_SUPPLY, strings.RV_SUPPLY_TIP, self._supply),
            ("show_all", strings.RV_SHOW_ALL, strings.RV_SHOW_ALL_TIP, self._show_all),
        ))  # fmt: skip
        source_columns = [
            Column(0, review.SOURCE_COLUMNS[0]),
            Column(1, review.SOURCE_COLUMNS[1], mono=True),
            Column(2, review.SOURCE_COLUMNS[2], mono=True),
            Column(3, review.SOURCE_COLUMNS[3], tooltip=_long(3)),
            Column(4, review.SOURCE_COLUMNS[4], mono=True),
            Column(5, review.SOURCE_COLUMNS[5], mono=True, tooltip=_long(5), width=200),
            Column("library", strings.RV_LIBRARY),
        ]
        self._block(body, "sources", DictTableModel(source_columns, [], theme))
        self._buttons(body, "sources", (
            ("copy", strings.RV_COPY_LINK, strings.RV_COPY_LINK_TIP, self._copy),
            ("source_show", strings.RV_SHOW, strings.RV_SHOW_SOURCE_TIP, self._source_show),
        ))  # fmt: skip
        how = QLabel()
        how.setProperty("heading", True)
        how.setObjectName("review-heading-how")
        self.headings["how"] = how
        body.addWidget(how)
        self.how_lines: list[WrapLabel] = []
        for _line in review.HOW_LINES:  # (the view's own sentences, set by show_input)
            w = WrapLabel("")
            w.setObjectName("review-how")
            w.setProperty("muted", True)
            self.how_lines.append(w)
            body.addWidget(w)
        column.addWidget(self.body)
        column.addStretch(1)
        self.show_input(ReviewInput())

    # ---- building ------------------------------------------------------------------------------
    def _block(self, body: QVBoxLayout, key: str, model: DictTableModel) -> None:
        heading = QLabel()
        heading.setObjectName(f"review-heading-{key}")
        heading.setProperty("heading", True)
        heading.setWordWrap(True)
        table = TableView(model, self.theme, name=strings.RV_TABLE_NAMES[key])
        table.setObjectName(f"review-{key}")
        table.setSelectionBehavior(TableView.SelectionBehavior.SelectRows)
        table.setSelectionMode(TableView.SelectionMode.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)
        table.activated.connect(lambda index, k=key: self._activated(k, index))
        table.doubleClicked.connect(lambda index, k=key: self._activated(k, index))
        table.selectionModel().selectionChanged.connect(lambda *_a: self._sync_buttons())
        # an empty block has its one sentence in place of the table, as on the sheet
        empty = WrapLabel("")
        empty.setObjectName(f"review-empty-{key}")
        empty.setAccessibleName(strings.RV_EMPTY_TITLES[key])
        empty.setProperty("muted", True)
        self.empties[key] = empty
        self.headings[key] = heading
        self.tables[key] = table
        self.models[key] = model
        body.addWidget(heading)
        body.addWidget(table)
        body.addWidget(empty)

    def _buttons(
        self,
        body: QVBoxLayout,
        key: str,
        specs: tuple[tuple[str, str, str, Callable[[], None]], ...],
    ) -> None:
        row = QHBoxLayout()
        for name, text, tip, call in specs:
            b = _button(text, tip, f"review-{key}-{name.replace('_', '-')}")
            b.clicked.connect(lambda _c=False, f=call: f())
            self.buttons[f"{key}/{name}"] = b
            row.addWidget(b)
        row.addStretch(1)
        body.addLayout(row)

    def _finding_buttons(self, key: str) -> tuple[tuple[str, str, str, Callable[[], None]], ...]:
        return (
            ("show", strings.RV_SHOW, strings.RV_SHOW_TIP, lambda: self._show(key)),
            ("explain", strings.RV_EXPLAIN, strings.RV_EXPLAIN_TIP, lambda: self._explain(key)),
            ("waive", strings.RV_WAIVE, strings.RV_WAIVE_TIP, lambda: self._waive(key)),
            ("deviate", strings.RV_DEVIATE, strings.RV_DEVIATE_TIP, lambda: self._deviate(key)),
        )

    def _fit(self, key: str) -> None:
        """A block's table as tall as its rows (3 to 10; a scroll bar beyond), so the page reads
        from top to bottom without a table that is mostly empty."""
        table = self.tables[key]
        n = table.model().rowCount()
        rows = max(_MIN_ROWS, min(n, _MAX_ROWS))
        head = table.horizontalHeader().sizeHint().height()
        bar = table.horizontalScrollBar().sizeHint().height()
        height = head + rows * table.verticalHeader().defaultSectionSize() + bar + 2 * table.frameWidth()  # fmt: skip
        table.setFixedHeight(height)

    # ---- showing -------------------------------------------------------------------------------
    def show_input(self, data: ReviewInput) -> None:
        """Show what the window hands over (when the page is opened, after a change, a check)."""
        self._input = data
        self._ticked = data.ticked
        self._filling = True
        try:
            self.harness.clear()
            for hid, text in data.harnesses:
                self.harness.addItem(text, hid)
            view = data.view
            if view is not None:
                i = self.harness.findData(view.harness_id)
                self.harness.setCurrentIndex(max(i, 0))
        finally:
            self._filling = False
        has = view is not None
        self.harness.setEnabled(bool(data.harnesses))
        self.none.setVisible(not has)
        self.body.setVisible(has)
        self.state.setVisible(has)
        if view is None:
            for model in self.models.values():
                model.set_rows([])
            self._sync_buttons()
            return
        self.state.set_state(data.state, strings.REL_REVISION.format(view.version))
        released = view.status == "released"
        self.release_line.setText(view.release)
        self.running.setVisible(data.running)
        self.dropped.setVisible(data.dropped and not released and bool(view.points))
        self.released.setText(strings.RV_RELEASED.format(view.harness_id))
        self.released.setVisible(released and bool(view.points))
        self.checklist.checkable = not released and not data.read_only
        for key in TABLE_BLOCKS:
            block = view.block(key)
            self.headings[key].setText(block.heading)
            self.empties[key].setText(block.empty)
            self.empties[key].setVisible(not block.rows)
            self.tables[key].setVisible(bool(block.rows))
            rows = [_cells(r) for r in block.rows]
            if key == "checklist":
                for r in rows:
                    r["done"] = int(r["ref"]) in self._ticked
            elif key == "sources":
                for r in rows:
                    r["library"] = data.library.get(str(r["ref"]), "") if r.get(0) == "Device connector" else ""  # fmt: skip
            self.models[key].set_rows(rows)
            self._fit(key)
        how = view.block("how")
        self.headings["how"].setText(how.heading)
        for label, row in zip(self.how_lines, how.rows, strict=False):
            label.setText(str(row.cells[0]))
        self.summary.setText(summary_text(view, self._ticked))
        self._sync_buttons()

    def view(self) -> review.ReviewView | None:
        return self._input.view

    def harness_id(self) -> str | None:
        view = self._input.view
        return view.harness_id if view is not None else None

    def ticked(self) -> frozenset[int]:
        return self._ticked

    def rows(self, key: str) -> list[dict[Any, Any]]:
        """The rows of a block on show (for the tests)."""
        return [dict(r) for r in self.models[key].rows() if isinstance(r, Mapping)]

    def choose(self, key: str, row: int) -> None:
        """Choose a row of a block (as a click does; for the tests and the keyboard)."""
        table = self.tables[key]
        table.selectRow(row)
        table.setCurrentIndex(table.model().index(row, 0))

    # ---- the buttons ---------------------------------------------------------------------------
    def _current(self, key: str) -> dict[Any, Any] | None:
        rows = self.tables[key].selected_rows()
        return dict(rows[0]) if rows and isinstance(rows[0], Mapping) else None

    def _finding(self, key: str) -> Finding | None:
        row = self._current(key)
        return self._input.findings.get(str(row["ref"])) if row is not None else None

    def _sync_buttons(self) -> None:
        data = self._input
        view = data.view
        released = view is not None and view.status == "released"
        live = view is not None and not data.read_only
        self.release_button.setEnabled(live and not released)
        self.release_button.setToolTip(
            strings.RV_RELEASE_OFF_READ_ONLY
            if data.read_only
            else strings.RV_RELEASE_OFF_RELEASED.format(view.harness_id)
            if view is not None and released
            else strings.RV_RELEASE_TIP
        )
        self.checklist_button.setEnabled(not data.read_only)
        ticking = live and not released and bool(view is not None and view.points)
        for name in ("tick_all", "clear"):
            self.buttons[f"checklist/{name}"].setVisible(
                not released and bool(view and view.points)
            )
            self.buttons[f"checklist/{name}"].setEnabled(ticking)
        for key in ("findings", "project"):
            f = self._finding(key)
            self.buttons[f"{key}/show"].setEnabled(f is not None and bool(f.object_id))
            self.buttons[f"{key}/explain"].setEnabled(f is not None and bool(f.object_id))
            open_ = f is not None and f.waiver is None and live
            self.buttons[f"{key}/waive"].setEnabled(open_ and f is not None and f.can_waive)
            self.buttons[f"{key}/deviate"].setEnabled(open_ and f is not None and f.can_deviate)
        row = self._current("open")
        self.buttons["open/open_show"].setEnabled(row is not None)
        self.buttons["open/supply"].setEnabled(
            row is not None and row.get(0) == CONFIG_ROWS[1] and live
        )
        self.buttons["open/show_all"].setEnabled(row is not None)
        source = self._current("sources")
        self.buttons["sources/copy"].setEnabled(source is not None and bool(source.get(5)))
        self.buttons["sources/source_show"].setEnabled(source is not None)

    def _picked(self, index: int) -> None:
        if self._filling:
            return
        hid = self.harness.itemData(index)
        if isinstance(hid, str) and hid:
            self.harnessPicked.emit(hid)

    def _release(self) -> None:
        hid = self.harness_id()
        if hid is not None and self.release_button.isEnabled():
            self.releaseRequested.emit(hid)

    def _set_ticks(self, ticked: frozenset[int]) -> None:
        hid = self.harness_id()
        view = self._input.view
        if hid is None or view is None:
            return
        self._ticked = ticked
        for r in self.models["checklist"].rows():
            if isinstance(r, dict):
                r["done"] = int(r["ref"]) in ticked
        model = self.models["checklist"]
        if model.rowCount():
            model.dataChanged.emit(model.index(0, 0), model.index(model.rowCount() - 1, 2))
        self.dropped.setVisible(False)
        self.summary.setText(summary_text(view, ticked))
        self.ticksChanged.emit(hid, ticked)

    def _tick(self, number: int, on: bool) -> None:
        self._set_ticks(self._ticked | {number} if on else self._ticked - {number})

    def _tick_all(self) -> None:
        view = self._input.view
        if view is not None:
            self._set_ticks(frozenset(range(1, len(view.points) + 1)))

    def _clear(self) -> None:
        self._set_ticks(frozenset())

    def _activated(self, key: str, _index: QModelIndex) -> None:
        """Enter or a double-click: *Show* of the block (a tick box is ticked with Space)."""
        if key in ("findings", "project"):
            self._show(key)
        elif key == "open":
            self._open_show()
        elif key == "sources":
            self._source_show()

    def _show(self, key: str) -> None:
        f = self._finding(key)
        if f is not None and f.object_id:
            self.showRequested.emit(f.object_id)

    def _explain(self, key: str) -> None:
        f = self._finding(key)
        if f is not None and f.object_id:
            self.explainRequested.emit(f.rule, f.object_id)

    def _waive(self, key: str) -> None:
        f = self._finding(key)
        if f is not None and self.buttons[f"{key}/waive"].isEnabled():
            self.waiveRequested.emit(f.id)

    def _deviate(self, key: str) -> None:
        f = self._finding(key)
        if f is not None and self.buttons[f"{key}/deviate"].isEnabled():
            self.deviateRequested.emit(f.id)

    def _open_show(self) -> None:
        row = self._current("open")
        if row is not None:
            self.openShowRequested.emit(str(row[0]), str(row["ref"]))

    def _supply(self) -> None:
        row = self._current("open")
        if row is not None and self.buttons["open/supply"].isEnabled():
            self.valueRequested.emit(str(row["ref"]))

    def _show_all(self) -> None:
        row = self._current("open")
        if row is not None:
            self.showAllRequested.emit(str(row[0]), str(row["ref"]))

    def _copy(self) -> None:
        row = self._current("sources")
        if row is not None and row.get(5):
            self.copyRequested.emit(str(row[5]))

    def _source_show(self) -> None:
        row = self._current("sources")
        if row is not None:
            self.sourceRequested.emit(str(row["ref"]))
