# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The branch points of the cables a person drew, on the diagram (2.3.0, D-243).

`core.cable_ends.drawn_branch_points` says which there are; each is an item of the scene
(`DiagramScene.branch_items`, by branch point ID): a small diamond with its name, at the middle of
the connectors it joins (the ports their plugs sit on, the places of its loose ends) unless the
mark `branch:<branch point id>` moves it. The lines of the ends of its harness run through it
(`CableEnd.via`, `canvas_ends.CableEndItem`). A press picks it (the inspector shows it); a drag
moves it and writes the mark when it is let go, as one undo step outside the model hash, so no
written output goes out of date. Nothing else here changes the project.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QFontMetrics, QPainter, QPainterPath, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from harness_design_studio.core.cable_ends import BranchSpot, branch_mark, pos_mark
from harness_design_studio.gui import cable as cb
from harness_design_studio.gui import strings

if TYPE_CHECKING:
    from harness_design_studio.gui.canvas import DiagramScene

HALF = 8.0  # half the width of the diamond (scene units)
PAD = 30.0  # room around it for the name and the selection ring
Spot = tuple[float, float]


class BranchPointItem(QGraphicsItem):
    """One branch point of a cable drawn by hand."""

    def __init__(self, scene: DiagramScene, spot: BranchSpot) -> None:
        super().__init__()
        self.dscene = scene
        self.spot = spot
        self.at: Spot = (0.0, 0.0)  # where it is drawn now
        self._drag: QPointF | None = None  # how far it is carried, while it is
        self._press = QPointF()
        self.setZValue(1.4)  # over the lines of the ends, under the cards
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.update_place()

    @property
    def branch_id(self) -> str:
        return self.spot.branch_id

    # ---- where it is --------------------------------------------------------------------------
    def connector_spot(self, connector_id: str) -> Spot | None:
        """Where a cable connector of its harness is on the diagram: the port its plug sits on, or
        the place of a loose end (None when the diagram does not show it)."""
        sc = self.dscene
        item = sc.end_items.get(connector_id)
        if item is not None:
            e = item.end
            if e.loose:
                hx, hy = item.home()
                shift = sc.mark_shift(pos_mark(connector_id))
                return (hx + shift.x(), hy + shift.y())
            return sc.cable.port_now(cb.Port(e.target_unit, e.target)).at
        h = sc.ctl.project.harnesses.get(self.spot.harness_id)
        c = next((x for x in (h.connectors if h else []) if x.id == connector_id), None)
        box = sc.ctl.project.connectors.get(c.mates_with or "") if c is not None else None
        if box is None or not box.unit_id or box.unit_id not in sc.unit_items:
            return None
        return sc.cable.port_now(cb.Port(box.unit_id, box.id)).at

    def home(self) -> Spot | None:
        """The middle of the connectors it joins (None: none of them is on the diagram)."""
        spots = [s for c in self.spot.connectors if (s := self.connector_spot(c)) is not None]
        if not spots:
            return None
        return (sum(x for x, _ in spots) / len(spots), sum(y for _, y in spots) / len(spots))

    def placed(self) -> Spot:
        """Where it sits: the middle of its connectors moved by its mark (and by a drag)."""
        home = self.home() or self.at
        shift = self.dscene.mark_shift(branch_mark(self.branch_id))
        drag = self._drag or QPointF()
        return (home[0] + shift.x() + drag.x(), home[1] + shift.y() + drag.y())

    def set_spot(self, spot: BranchSpot) -> None:
        self.spot = spot
        self.update_place()

    def update_place(self) -> None:
        """Follow the devices, the ends and the mark; repaint only when it moved."""
        at = self.placed()
        self.setVisible(self.home() is not None)
        if at == self.at and self.pos() == QPointF(*at):
            return
        self.at = at
        self.setPos(QPointF(*at))
        self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(-PAD - 60.0, -PAD, 2 * (PAD + 60.0), 2 * PAD)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(QRectF(-HALF - 3, -HALF - 3, 2 * HALF + 6, 2 * HALF + 6))
        return path

    # ---- what it says -------------------------------------------------------------------------
    def tooltip(self) -> str:
        s = self.spot
        return strings.BRANCH_TIP.format(
            branch=s.branch_id, name=s.name, harness=s.harness_id,
            connectors=", ".join(s.connectors) or "-",
        )  # fmt: skip

    # ---- painting -----------------------------------------------------------------------------
    def paint(
        self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None
    ) -> None:
        sc = self.dscene
        th = sc.theme
        picked = sc.ctl.picked_branch == self.branch_id
        token = "primary" if picked or self._drag is not None else "text-muted"
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        diamond = QPolygonF(
            [QPointF(0, -HALF), QPointF(HALF, 0), QPointF(0, HALF), QPointF(-HALF, 0)]
        )
        painter.setPen(sc.pen(token, 2))
        painter.setBrush(QBrush(th.color("bg")))
        painter.drawPolygon(diamond)
        if picked:
            painter.setPen(sc.pen("focus", 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(0, 0), HALF + 5, HALF + 5)
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        if lod >= 0.35 or picked:
            font = sc.px_font(th.type("small"))
            painter.setFont(font)
            fm = QFontMetrics(font)
            text = self.spot.name
            painter.setPen(th.color("text-muted"))
            painter.drawText(QPointF(-fm.horizontalAdvance(text) / 2, HALF + 6 + fm.ascent()), text)

    # ---- the pointer --------------------------------------------------------------------------
    def hoverEnterEvent(self, event: object) -> None:  # noqa: N802
        self.setToolTip(self.tooltip())
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().hoverEnterEvent(event)  # type: ignore[arg-type]

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        """A press picks the branch point (the inspector shows it) and may become a drag."""
        self.dscene.ctl.pick_branch(self.branch_id)
        self._press = event.scenePos()
        self._drag = None
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        if self.dscene.ctl.read_only:
            return
        d = event.scenePos() - self._press
        if self._drag is None and abs(d.x()) + abs(d.y()) < 3.0:
            return
        self._drag = d
        self.update_place()
        self.dscene.follow_harness(self.spot.harness_id)  # its lines follow while it is carried
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        drag, self._drag = self._drag, None
        if drag is not None:
            self.move_by(drag.x(), drag.y())
        else:
            self.update_place()
        event.accept()

    def move_by(self, dx: float, dy: float) -> bool:
        """Move it by (dx, dy) from where it is: the mark `branch:<ID>` (one undo step, outside
        the model hash)."""
        shift = self.dscene.mark_shift(branch_mark(self.branch_id))
        done = self.dscene.ctl.move_mark(
            branch_mark(self.branch_id), shift.x() + dx, shift.y() + dy
        )
        self.update_place()
        self.dscene.follow_harness(self.spot.harness_id)
        return done


__all__ = ["BranchPointItem"]
