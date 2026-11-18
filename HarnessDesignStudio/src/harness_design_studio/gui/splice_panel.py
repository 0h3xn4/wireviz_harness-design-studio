# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The *Splices* of the Harness tab: the splices of a harness a person made (format 3, M6a; section
6.6 of `docs/ait/DESIGN_2.3_BRANCHING.md`).

    panel = SplicePanel(ctl, theme)
    panel.selected_wires = view.selected_wire_ids  # the wires chosen in the wire table
    panel.show_harness(harness)                    # the Harness tab calls it on every refresh

Under the routing: one row per node of each splice (splice, node, part, how its wires are joined,
the wires on it). It is shown for a harness a person made and for any harness that has a splice.
*Add splice* places a splice of the part chosen beside it; *Splice this wire* cuts the wire chosen
in the wire table at the node chosen here; *Delete splice* removes the chosen splice and joins two
wires on a node back into one. Each is a plan of `core/splices.py` and one undo step; a refusal is
shown in the panel's error line. The diagram shows nothing new: a splice is inside the harness.
Nothing here changes the project except through `EditorController.run`.
"""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QModelIndex, QSettings
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from harness_design_studio.core import splices
from harness_design_studio.core.commands import Op
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.model import Harness, Project
from harness_design_studio.gui import strings
from harness_design_studio.gui.controller import EditorController
from harness_design_studio.gui.tables import Column, DictTableModel, TableView
from harness_design_studio.gui.theme import ThemeManager
from harness_design_studio.gui.wrap_label import FlowRow, WrapLabel, breakable

# ---- rows (pure, no Qt) ------------------------------------------------------------------------


def splice_rows(h: Harness) -> list[dict[str, Any]]:
    """One row per node of each splice of the harness, by splice ID."""
    return [
        {
            "id": f"{sid}.{node}",
            "splice": sid,
            "node": node,
            "part": part,
            "termination": "" if how == "unspecified" else how,
            "wires": ", ".join(wires) or strings.SP_NO_WIRE,
        }
        for sid, node, part, how, wires in splices.node_rows(h)
    ]


def shows_splices(project: Project, h: Harness) -> bool:
    """True for a harness that has a splice, or in which a person may place one."""
    return bool(splices.splices_of(h)) or not splices.refusal(project, h.id)


SPLICE_COLUMNS = [
    Column("splice", strings.SP_COL_SPLICE, mono=True, width=92),
    Column("node", strings.SP_COL_NODE, mono=True, width=48),
    Column("part", strings.SP_COL_PART, mono=True, width=110),
    Column("termination", strings.SP_COL_TERMINATION, width=80),
    Column("wires", strings.SP_COL_WIRES, mono=True, width=220),
]


class SplicePanel(QWidget):
    """The splices of one harness, under the routing. See the module."""

    def __init__(
        self, ctl: EditorController, theme: ThemeManager, settings: QSettings | None = None
    ) -> None:
        super().__init__()
        self.ctl, self.theme = ctl, theme
        self.setObjectName("splice-panel")
        self.selected_wires: Callable[[], list[str]] = list  # the Harness tab sets its own
        self._hid: str | None = None
        self._key: tuple[Any, ...] | None = None
        self._picked: tuple[str, str] | None = None  # (splice ID, node)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.space(4))
        title = QLabel(strings.SP_TITLE)
        title.setProperty("heading", True)
        lay.addWidget(title)
        row = QHBoxLayout()
        self.part = QComboBox()
        self.part.setObjectName("splice-part")
        self.part.setAccessibleName(strings.SP_PART)
        self.part.setToolTip(strings.SP_PART_TIP)
        row.addWidget(self.part, 1)
        lay.addLayout(row)
        bar = FlowRow()
        self.buttons: dict[str, QPushButton] = {}
        for key, text, tip, slot in (
            ("add", strings.SP_ADD, strings.SP_ADD_TIP, self.add_splice),
            ("splice_wire", strings.SP_SPLICE_WIRE, strings.SP_SPLICE_WIRE_TIP, self.splice_wire),
            ("delete", strings.SP_DELETE, strings.SP_DELETE_TIP, self.delete_splice),
        ):
            b = QPushButton(text)
            b.setObjectName(f"splice-{key.replace('_', '-')}")
            b.setAccessibleName(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            self.buttons[key] = b
            bar.addWidget(b)
        lay.addLayout(bar)
        self.note = WrapLabel()
        self.note.setObjectName("splice-note")
        self.note.setProperty("muted", True)
        lay.addWidget(self.note)
        self.error = WrapLabel()
        self.error.setObjectName("splice-error")
        self.error.setProperty("error", True)
        self.error.hide()
        lay.addWidget(self.error)
        self.model = DictTableModel(SPLICE_COLUMNS, (), theme)
        self.table = TableView(
            self.model, theme, name=strings.SP_TABLE, settings=settings, key="harness-splices"
        )
        self.table.setObjectName("splice-table")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setMinimumHeight(theme.px(56))
        lay.addWidget(self.table, 1)
        sm = self.table.selectionModel()
        if sm is not None:
            sm.currentRowChanged.connect(self._picked_row)
        self.hide()

    # ---- what is shown -----------------------------------------------------------------------
    def harness(self) -> Harness | None:
        return self.ctl.project.harnesses.get(self._hid or "")

    def why_not(self, h: Harness) -> str:
        """Why no splice of this harness can change ("" when one can)."""
        if self.ctl.read_only:
            return strings.WHY_READ_ONLY
        return splices.refusal(self.ctl.project, h.id)

    def show_harness(self, h: Harness | None) -> None:
        """Show the splices of `h` (None: nothing). Cheap when nothing changed."""
        if h is None or not shows_splices(self.ctl.project, h):
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
        rows = splice_rows(h)
        self.model.update_rows(rows)
        self.table.setVisible(bool(rows))
        parts = splices.splice_parts(self.ctl.project)
        keep = self.part.currentData()
        self.part.blockSignals(True)
        self.part.clear()
        for part in parts:
            words = f"{part.id}: {part.description}" if part.description else part.id
            self.part.addItem(words, part.id)
        at = self.part.findData(keep)
        self.part.setCurrentIndex(at if at >= 0 else 0)
        self.part.blockSignals(False)
        why = self.why_not(h)
        self.part.setVisible(bool(parts) and not why)
        if why:
            note = why
        elif not parts:
            note = strings.SP_NO_PART
        else:
            note = strings.SP_HINT if rows else strings.SP_EMPTY
        self.note.setText(breakable(note))
        if self._picked is not None and f"{self._picked[0]}.{self._picked[1]}" not in {
            r["id"] for r in rows
        }:
            self._picked = None
        self._update_buttons(why, bool(parts))
        self.show()

    def _update_buttons(self, why: str, parts: bool) -> None:
        tips = {
            "add": strings.SP_ADD_TIP,
            "splice_wire": strings.SP_SPLICE_WIRE_TIP,
            "delete": strings.SP_DELETE_TIP,
        }
        for key, b in self.buttons.items():
            need = ""
            if key == "add" and not parts:
                need = strings.SP_NO_PART
            elif key in ("splice_wire", "delete") and self._picked is None:
                need = strings.SP_PICK_NODE
            reason = why or need
            b.setEnabled(not reason)
            b.setToolTip(f"{b.text()}: {reason}" if reason else tips[key])

    def _picked_row(self, cur: QModelIndex, _prev: QModelIndex) -> None:
        if not cur.isValid():
            return
        row = self.table.row_at(cur)
        if not isinstance(row, dict):
            return
        self._picked = (str(row["splice"]), str(row["node"]))
        h = self.harness()
        if h is not None:
            self._update_buttons(self.why_not(h), bool(splices.splice_parts(self.ctl.project)))

    def picked(self) -> tuple[str, str] | None:
        return self._picked

    def pick(self, splice_id: str, node: str = "1") -> bool:
        """Choose the row of a node of a splice."""
        model = self.table.source
        for r in range(model.rowCount()):
            row = model.row(r)
            if isinstance(row, dict) and row.get("id") == f"{splice_id}.{node}":
                index = self.table.proxy.mapFromSource(model.index(r, 0))
                self.table.setCurrentIndex(index)
                self.table.selectRow(index.row())
                self._picked_row(index, QModelIndex())
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

    def add_splice(self) -> bool:
        hid = self._hid or ""
        part = self.part.currentData()
        if not isinstance(part, str):
            self._say(strings.SP_NO_PART)
            return False
        made: list[str] = []

        def build() -> list[Op]:
            ops, sid = splices.plan_add_splice(self.ctl.project, hid, part)
            made.append(sid)
            return ops

        if not self._run(strings.STEP_SP_ADD.format(hid), build):
            return False
        self.show_harness(self.harness())
        self.pick(made[0])
        return True

    def splice_wire(self) -> bool:
        wires = self.selected_wires()
        if len(wires) != 1:
            self._say(strings.SP_PICK_WIRE)
            return False
        if self._picked is None:
            self._say(strings.SP_PICK_NODE)
            return False
        sid, node = self._picked
        wire = wires[0]
        return self._run(
            strings.STEP_SP_SPLICE_WIRE.format(wire=wire, splice=sid),
            lambda: splices.plan_splice_wire(self.ctl.project, wire, sid, node)[0],
        )

    def delete_splice(self) -> bool:
        if self._picked is None:
            self._say(strings.SP_PICK_NODE)
            return False
        sid, hid = self._picked[0], self._hid or ""
        done = self._run(
            strings.STEP_SP_DELETE.format(sid),
            lambda: splices.plan_delete_splice(self.ctl.project, hid, sid),
        )
        if done:
            self._picked = None
        return done


__all__ = ["SPLICE_COLUMNS", "SplicePanel", "shows_splices", "splice_rows"]
