# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The *Routing* of the Harness tab: the segments and branch points of one harness (2.3.0, D-243).

    panel = RoutingPanel(ctl, theme)
    panel.show_harness(harness)          # the Harness tab calls it on every refresh

Under the wire table: one row per segment (segment, from, to, length, the wires through it) and one
row per branch point (its name, its segments with their lengths). It is shown only for a harness
with segments or branch points, and for a harness a person made (whose tree can be drawn here).

* The length cell is edited in place (`branching.plan_set_segment_length`, one undo step). On a
  harness that Generate made the note says that Generate keeps an entered length; a released
  harness and a read-only project show why nothing can change.
* A harness a person made also gets *Add branch point*, *Add segment…* (`SegmentDialog`),
  *Rename…* and *Delete*, each a plan of `core/branching.py`. A refusal is shown in the panel's
  error line, as the Connectors and Accessories tabs show theirs.

The rows are worked out by `routing_rows` and `branch_rows` (no Qt). Nothing here changes the
project except through `EditorController.run`.
"""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from harness_design_studio.core import branching
from harness_design_studio.core.commands import Op
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.model import Harness, Project
from harness_design_studio.core.outputs.tables import natural_key, segment_wires
from harness_design_studio.core.wires import released_text
from harness_design_studio.gui import strings
from harness_design_studio.gui.controller import EditorController
from harness_design_studio.gui.dialog_base import Dialog, run_dialog
from harness_design_studio.gui.tables import Column, DictTableModel, Row, TableView
from harness_design_studio.gui.theme import ThemeManager
from harness_design_studio.gui.wrap_label import FlowRow, WrapLabel, breakable

# ---- rows (pure, no Qt) ------------------------------------------------------------------------


def node_names(h: Harness) -> dict[str, str]:
    """ID -> name of every connector and branch point of the harness."""
    out = {c.id: c.name for c in h.connectors}
    out.update({b.id: b.name for b in h.branch_points})
    return out


def length_text(metres: float | None) -> str:
    return strings.RT_NO_LENGTH if metres is None else f"{metres:g} m"


def routing_rows(h: Harness) -> list[dict[str, Any]]:
    """One row per segment of the harness, in natural ID order (as the written *Routing*)."""
    through = segment_wires(h)
    names = node_names(h)
    rows: list[dict[str, Any]] = []
    for s in sorted(h.segments, key=lambda x: natural_key(x.id)):
        ids = through.get(s.id, [])
        rows.append({
            "id": s.id, "from": s.from_node, "to": s.to_node,
            "from_tip": strings.RT_NODE_TIP.format(id=s.from_node, name=names.get(s.from_node, "")),
            "to_tip": strings.RT_NODE_TIP.format(id=s.to_node, name=names.get(s.to_node, "")),
            "length": s.length_m,
            "length_state": "pending" if s.length_m is None else None,
            "length_tip": strings.RT_NO_LENGTH_TIP if s.length_m is None
            else strings.RT_LENGTH_TIP.format(m=s.length_m),
            "wires": ", ".join(ids),
            "wires_tip": strings.RT_WIRES_TIP.format(n=len(ids), segment=s.id, ids=", ".join(ids)),
        })  # fmt: skip
    return rows


def branch_segments(h: Harness, branch_id: str) -> list[tuple[str, float | None]]:
    """The segments that meet a branch point, in natural ID order, with their lengths."""
    return [
        (s.id, s.length_m)
        for s in sorted(h.segments, key=lambda x: natural_key(x.id))
        if branch_id in (s.from_node, s.to_node)
    ]


def segments_text(pairs: list[tuple[str, float | None]]) -> str:
    return ", ".join(
        strings.RT_SEGMENT_NO_LENGTH.format(segment=sid)
        if m is None
        else strings.RT_SEGMENT_LENGTH.format(segment=sid, length=length_text(m))
        for sid, m in pairs
    )


def branch_rows(h: Harness) -> list[dict[str, Any]]:
    """One row per branch point: its ID, its name and its segments with their lengths."""
    return [
        {"id": b.id, "name": b.name, "segments": segments_text(branch_segments(h, b.id))}
        for b in sorted(h.branch_points, key=lambda x: natural_key(x.id))
    ]


def shows_routing(h: Harness) -> bool:
    """The panel is shown for a harness with a routing tree, and for one a person made."""
    return bool(h.segments or h.branch_points) or not h.generated


def _length_fmt(value: Any) -> str:
    return length_text(value if isinstance(value, int | float) else None)


SEGMENT_COLUMNS = [
    Column("id", strings.RT_COL_SEGMENT, mono=True, width=92),
    Column("from", strings.RT_COL_FROM, mono=True, tooltip="from_tip", width=92),
    Column("to", strings.RT_COL_TO, mono=True, tooltip="to_tip", width=92),
    Column("length", strings.RT_COL_LENGTH, numeric=True, state="length_state",
           fmt=_length_fmt, tooltip="length_tip", width=96),
    Column("wires", strings.RT_COL_WIRES, mono=True, tooltip="wires_tip", width=220),
]  # fmt: skip
BRANCH_COLUMNS = [
    Column("id", strings.RT_COL_BRANCH, mono=True, width=92),
    Column("name", strings.RT_COL_NAME, width=120),
    Column("segments", strings.RT_COL_SEGMENTS, tooltip="segments", width=260),
]
LENGTH_COLUMN = 3


class _SegmentModel(DictTableModel):
    """The segment rows; the length cell is editable while `editable` is set."""

    def __init__(self, theme: ThemeManager, on_length: Callable[[str, str], bool]) -> None:
        super().__init__(SEGMENT_COLUMNS, (), theme)
        self.editable = False
        self.on_length = on_length

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        base = super().flags(index)
        if self.editable and index.isValid() and index.column() == LENGTH_COLUMN:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if role == Qt.ItemDataRole.EditRole and index.isValid() and index.column() == LENGTH_COLUMN:
            value = _get_length(self.row(index.row()))
            return "" if value is None else f"{value:g}"  # text: no spin box that rounds
        return super().data(index, role)

    def setData(  # noqa: N802
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: object,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if role != Qt.ItemDataRole.EditRole or index.column() != LENGTH_COLUMN:
            return False
        row = self.row(index.row())
        if not isinstance(row, dict):
            return False
        return self.on_length(str(row["id"]), "" if value is None else str(value))


def _get_length(row: Row) -> float | None:
    value = row.get("length") if isinstance(row, dict) else None
    return float(value) if isinstance(value, int | float) else None


# ---- the dialog of a new segment ------------------------------------------------------------------


class SegmentDialog(Dialog):
    """*Add segment…*: the two nodes (connectors or branch points of the harness) and an optional
    length. OK asks `branching.plan_add_segment`; a refusal stays in the dialog, under the form."""

    def __init__(
        self, parent: QWidget | None, theme: ThemeManager, project: Project, harness_id: str
    ) -> None:
        super().__init__(parent)
        self.project, self.harness_id = project, harness_id
        self._ops: list[Op] = []
        self.segment_id = ""
        h = project.harnesses[harness_id]
        title = strings.SEG_DIALOG_TITLE.format(harness_id)
        self.setObjectName("segment-dialog")
        self.setWindowTitle(title)
        self.setAccessibleName(title)
        self.setMinimumWidth(theme.px(420))
        lay = QVBoxLayout(self)
        intro = QLabel(strings.SEG_DIALOG_INTRO)
        intro.setWordWrap(True)
        intro.setProperty("muted", True)
        lay.addWidget(intro)
        form = QFormLayout()
        names = node_names(h)
        nodes = sorted(names, key=natural_key)
        self.a, self.b = QComboBox(), QComboBox()
        for box in (self.a, self.b):
            for nid in nodes:
                box.addItem(strings.SEG_NODE.format(id=nid, name=names[nid]), nid)
        if self.b.count() > 1:
            self.b.setCurrentIndex(1)
        self.length = QLineEdit()
        self.length.setPlaceholderText(strings.RT_NO_LENGTH)
        for widget, name, text, tip in (
            (self.a, "segment-from", strings.SEG_FROM, strings.SEG_FROM_TIP),
            (self.b, "segment-to", strings.SEG_TO, strings.SEG_TO_TIP),
            (self.length, "segment-length", strings.SEG_LENGTH, strings.SEG_LENGTH_TIP),
        ):
            widget.setObjectName(name)
            widget.setAccessibleName(text)
            widget.setToolTip(tip)
            form.addRow(text, widget)
        lay.addLayout(form)
        self.error = QLabel()
        self.error.setObjectName("segment-error")
        self.error.setWordWrap(True)
        self.error.setProperty("error", True)
        self.error.hide()
        lay.addWidget(self.error)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton(strings.CANCEL)
        cancel.setObjectName("dlg-cancel")
        cancel.setAccessibleName(strings.CANCEL)
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton(strings.SEG_OK)
        self.ok.setObjectName("dlg-ok")
        self.ok.setAccessibleName(strings.SEG_OK)
        self.ok.setToolTip(strings.SEG_OK_TIP)
        self.ok.setProperty("primary", True)
        self.ok.setDefault(True)
        self.ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(self.ok)
        lay.addLayout(row)

    def plan(self) -> bool:
        """Work the segment out from the form; False (and the reason under the form) when the plan
        refuses."""
        try:
            self._ops, self.segment_id = branching.plan_add_segment(
                self.project,
                self.harness_id,
                str(self.a.currentData()),
                str(self.b.currentData()),
                self.length.text(),
            )
        except EditError as exc:
            self._ops, self.segment_id = [], ""
            self.error.setText(str(exc))
            self.error.show()
            return False
        self.error.hide()
        return True

    def accept(self) -> None:
        if self.plan():
            super().accept()

    def ops(self) -> list[Op]:
        return list(self._ops)


# ---- the panel ------------------------------------------------------------------------------------


class RoutingPanel(QWidget):
    """The segments and branch points of one harness, under the wire table. See the module.

    `branchPicked(harness_id, branch_id)` when a branch point row is chosen (the inspector shows
    it)."""

    branchPicked = Signal(str, str)

    def __init__(
        self, ctl: EditorController, theme: ThemeManager, settings: QSettings | None = None
    ) -> None:
        super().__init__()
        self.ctl, self.theme = ctl, theme
        self.setObjectName("routing-panel")
        self.run_dialog: Callable[[QDialog], int] = run_dialog  # (the window sets its hook)
        self.ask_text: Callable[[str, str, str], str | None] = self._ask_text
        self._hid: str | None = None
        self._key: tuple[Any, ...] | None = None
        self._picked: tuple[str, str] | None = None  # ("segment" | "branch", ID)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.space(4))
        title = QLabel(strings.RT_TITLE)
        title.setProperty("heading", True)
        lay.addWidget(title)
        bar = FlowRow()  # the buttons go on in a second line in a narrow column
        self.buttons: dict[str, QPushButton] = {}
        for key, text, tip, slot in (
            ("add_branch", strings.RT_ADD_BRANCH, strings.RT_ADD_BRANCH_TIP, self.add_branch_point),
            ("add_segment", strings.RT_ADD_SEGMENT, strings.RT_ADD_SEGMENT_TIP, self.add_segment),
            ("rename", strings.RT_RENAME, strings.RT_RENAME_TIP, self.rename),
            ("delete", strings.RT_DELETE, strings.RT_DELETE_TIP, self.delete),
        ):
            b = QPushButton(text)
            b.setObjectName(f"routing-{key.replace('_', '-')}")
            b.setAccessibleName(text.rstrip("…"))
            b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, f=slot: f())
            self.buttons[key] = b
            bar.addWidget(b)
        lay.addLayout(bar)
        self.note = WrapLabel()
        self.note.setObjectName("routing-note")
        self.note.setProperty("muted", True)
        lay.addWidget(self.note)
        self.error = WrapLabel()
        self.error.setObjectName("routing-error")
        self.error.setProperty("error", True)
        self.error.hide()
        lay.addWidget(self.error)
        self.model = _SegmentModel(theme, self.set_length)
        self.table = TableView(
            self.model, theme, name=strings.RT_TABLE, settings=settings, key="harness-routing"
        )
        self.table.setObjectName("routing-table")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.setMinimumHeight(theme.px(56))  # a few rows; the panel scrolls with the tab
        lay.addWidget(self.table, 2)
        self.branch_model = DictTableModel(BRANCH_COLUMNS, (), theme)
        self.branch_table = TableView(
            self.branch_model,
            theme,
            name=strings.RT_BRANCH_TABLE,
            settings=settings,
            key="harness-branch-points",
        )
        self.branch_table.setObjectName("routing-branch-table")
        self.branch_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.branch_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.branch_table.setMinimumHeight(theme.px(56))
        lay.addWidget(self.branch_table, 1)
        for table, kind in ((self.table, "segment"), (self.branch_table, "branch")):
            sm = table.selectionModel()
            if sm is not None:
                sm.currentRowChanged.connect(
                    lambda cur, _prev, t=table, k=kind: self._picked_row(t, k, cur)
                )
        self.hide()

    # ---- what is shown -----------------------------------------------------------------------
    def harness(self) -> Harness | None:
        return self.ctl.project.harnesses.get(self._hid or "")

    def why_not(self, h: Harness) -> str:
        """Why nothing of this harness's routing can change ("" when it can)."""
        if self.ctl.read_only:
            return strings.WHY_READ_ONLY
        if h.status == "released":
            return released_text(h)
        return ""

    def show_harness(self, h: Harness | None) -> None:
        """Show the routing of `h` (None: nothing). Cheap when nothing changed."""
        if h is None or not shows_routing(h):
            self._hid, self._key = (h.id if h else None), None
            self.hide()
            return
        key = (self.ctl.state_token, h.id, self.ctl.read_only)
        if key == self._key and not self.isHidden():
            return
        if h.id != self._hid:
            self._picked = None
            self._say("")
        self._hid, self._key = h.id, key
        why = self.why_not(h)
        self.model.editable = not why
        segments, points = routing_rows(h), branch_rows(h)
        self.model.update_rows(segments)
        self.branch_model.update_rows(points)
        self.table.setVisible(bool(segments))
        self.branch_table.setVisible(bool(points))
        if why:
            note = why
        elif h.generated:
            note = strings.RT_KEPT_BY_GENERATE
        else:
            note = strings.RT_DRAWN_HINT if segments or points else strings.RT_EMPTY
        self.note.setText(breakable(note))
        if self._picked is not None and not self._exists(h, *self._picked):
            self._picked = None
        self._update_buttons(h, why)
        self.show()

    def _exists(self, h: Harness, kind: str, ident: str) -> bool:
        items = h.segments if kind == "segment" else h.branch_points
        return any(x.id == ident for x in items)

    def _update_buttons(self, h: Harness, why: str) -> None:
        drawn = not h.generated
        picked = self._picked
        for key, b in self.buttons.items():
            b.setVisible(drawn)
            need = ""
            if key == "rename" and (picked is None or picked[0] != "branch"):
                need = strings.RT_RENAME_WHY
            elif key == "delete" and picked is None:
                need = strings.RT_DELETE_WHY
            reason = why or need
            b.setEnabled(drawn and not reason)
            tip = {
                "add_branch": strings.RT_ADD_BRANCH_TIP,
                "add_segment": strings.RT_ADD_SEGMENT_TIP,
                "rename": strings.RT_RENAME_TIP,
                "delete": strings.RT_DELETE_TIP,
            }[key]
            b.setToolTip(f"{b.text()}: {reason}" if reason else tip)

    def _picked_row(self, table: TableView, kind: str, cur: QModelIndex) -> None:
        if not cur.isValid():
            return
        row = table.row_at(cur)
        if not isinstance(row, dict):
            return
        self._picked = (kind, str(row["id"]))
        other = self.branch_table if table is self.table else self.table
        other.clearSelection()
        h = self.harness()
        if h is not None:
            self._update_buttons(h, self.why_not(h))
        if kind == "branch" and self._hid:
            self.branchPicked.emit(self._hid, str(row["id"]))

    def picked(self) -> tuple[str, str] | None:
        return self._picked

    def pick(self, kind: str, ident: str) -> bool:
        """Choose a row of the segment ("segment") or branch point ("branch") table."""
        table = self.table if kind == "segment" else self.branch_table
        model = table.source
        for r in range(model.rowCount()):
            row = model.row(r)
            if isinstance(row, dict) and row.get("id") == ident:
                index = table.proxy.mapFromSource(model.index(r, 0))
                table.setCurrentIndex(index)
                table.selectRow(index.row())
                self._picked_row(table, kind, index)  # (also when it was the current row)
                return True
        return False

    def _say(self, text: str) -> None:
        self.error.setText(breakable(text))
        self.error.setVisible(bool(text))

    # ---- the changes ------------------------------------------------------------------------
    def _run(self, label: str, build: Callable[[], list[Op]]) -> bool:
        try:
            ops = build()
        except EditError as exc:
            self._say(str(exc))
            return False
        self._say("")
        return self.ctl.run(label, ops)

    def set_length(self, segment_id: str, text: str) -> bool:
        """Enter the length of a segment in metres ("" clears it), as one undo step."""
        hid = self._hid or ""
        return self._run(
            strings.STEP_RT_LENGTH.format(segment_id),
            lambda: branching.plan_set_segment_length(self.ctl.project, hid, segment_id, text),
        )

    def add_branch_point(self) -> bool:
        hid = self._hid or ""
        made: list[str] = []

        def build() -> list[Op]:
            ops, bid = branching.plan_add_branch_point(self.ctl.project, hid)
            made.append(bid)
            return ops

        if not self._run(strings.STEP_RT_ADD_BRANCH.format(hid), build):
            return False
        self.show_harness(self.harness())
        self.pick("branch", made[0])
        return True

    def add_segment(self) -> bool:
        h = self.harness()
        if h is None:
            return False
        why = self.why_not(h)
        if why:
            self._say(why)
            return False
        dlg = SegmentDialog(self.window(), self.theme, self.ctl.project, h.id)
        if self.run_dialog(dlg) != QDialog.DialogCode.Accepted:
            return False
        if not dlg.ops() and not dlg.plan():  # (a scripted test answers OK without a click)
            self._say(dlg.error.text())
            return False
        sid = dlg.segment_id
        if not self.ctl.run(strings.STEP_RT_ADD_SEGMENT.format(sid), dlg.ops()):
            return False
        self._say("")
        self.show_harness(self.harness())
        self.pick("segment", sid)
        return True

    def rename(self) -> bool:
        picked, hid = self._picked, self._hid or ""
        if picked is None or picked[0] != "branch":
            self._say(strings.RT_RENAME_WHY)
            return False
        bid = picked[1]
        h = self.harness()
        old = next((b.name for b in (h.branch_points if h else []) if b.id == bid), "")
        name = self.ask_text(strings.RT_RENAME_TITLE.format(bid), strings.RT_RENAME_LABEL, old)
        if name is None:
            return False
        return self._run(
            strings.STEP_RT_RENAME.format(bid),
            lambda: branching.plan_rename_branch_point(self.ctl.project, hid, bid, name),
        )

    def delete(self) -> bool:
        picked, hid = self._picked, self._hid or ""
        if picked is None:
            self._say(strings.RT_DELETE_WHY)
            return False
        kind, ident = picked
        project = self.ctl.project
        done = self._run(
            strings.STEP_RT_DELETE.format(ident),
            lambda: (
                branching.plan_delete_segment(project, hid, ident)
                if kind == "segment"
                else branching.plan_delete_branch_point(project, hid, ident)
            ),
        )
        if done:
            self._picked = None
        return done

    def _ask_text(self, title: str, label: str, default: str) -> str | None:
        from PySide6.QtWidgets import QInputDialog

        dlg = QInputDialog(self.window())  # (not the static getText: that one is modal)
        dlg.setWindowTitle(title)
        dlg.setLabelText(label)
        dlg.setTextValue(default)
        ok = self.run_dialog(dlg) == QDialog.DialogCode.Accepted
        text = dlg.textValue()
        return text if ok and text.strip() else None


__all__ = [
    "RoutingPanel",
    "SegmentDialog",
    "branch_rows",
    "branch_segments",
    "routing_rows",
    "segments_text",
    "shows_routing",
]
