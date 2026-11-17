# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The application icon (the logo of docs/img/logo.svg), painted in code.

The logo shows what the tool does: a device connector with pins (left), a bundle of three
wires held by a tie, a branch point that splits the bundle to two connectors (right), a check
mark for the design-rule checks, and an orbit and a star for the spacecraft.

It is drawn with QPainter rather than loaded from the SVG because the packaged program ships
without the Qt SVG module. Keep the shapes in step with docs/img/logo.svg,
docs/img/banner.svg and packaging/ubuntu/harness-design-studio.svg.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from harness_design_studio.gui.theme.tokens import BRAND

SIZES = (16, 24, 32, 48, 64, 128, 256)
PURPLE = BRAND["purple"]
AMBER = BRAND["amber"]
WHITE = BRAND["white"]
LAVENDER = BRAND["lavender"]
ORBIT = BRAND["orbit"]

# (start, then cubic or line segments) of the three wires, in the 64 x 64 grid of the SVG
_WIRES = (
    (
        WHITE,
        (
            (18, 22),
            ("C", (24, 22), (24, 26), (30, 26)),
            ("L", (36, 26)),
            ("C", (42, 26), (42, 14), (47, 14)),
        ),
    ),
    (AMBER, ((18, 28), ("L", (36, 28)), ("C", (42, 28), (42, 20), (47, 20)))),
    (
        LAVENDER,
        (
            (18, 34),
            ("C", (24, 34), (24, 30), (30, 30)),
            ("L", (36, 30)),
            ("C", (42, 30), (42, 46), (47, 46)),
        ),
    ),
)
_STAR = ((10, 4), (11, 8), (15, 9), (11, 10), (10, 14), (9, 10), (5, 9), (9, 8))


def _path(start: tuple[float, float], *segments: tuple) -> QPainterPath:  # type: ignore[type-arg]
    path = QPainterPath(QPointF(*start))
    for kind, *points in segments:
        if kind == "L":
            path.lineTo(QPointF(*points[0]))
        else:
            path.cubicTo(*(QPointF(*pt) for pt in points))
    return path


def _pen(colour: str, width: float) -> QPen:
    pen = QPen(QColor(colour), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 64.0, size / 64.0)  # the logo is drawn on a 64 x 64 grid
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0, 0, 64, 64), 12, 12)
    p.fillPath(tile, QColor(PURPLE))
    p.setClipPath(tile)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(ORBIT), 2))
    p.drawPath(_path((-2, 50), ("C", (14, 66), (52, 58), (66, 28))))
    p.setClipping(False)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(WHITE))
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in _STAR]))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for colour, (start, *segments) in _WIRES:
        p.setPen(_pen(colour, 3))
        p.drawPath(_path(start, *segments))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(WHITE))
    p.drawRoundedRect(QRectF(27.5, 23.5, 3.5, 9), 1.2, 1.2)  # the cable tie
    p.drawRoundedRect(QRectF(5, 16, 13, 24), 3, 3)  # the device connector
    p.drawRoundedRect(QRectF(47, 9, 12, 16), 3, 3)  # branch connectors
    p.drawRoundedRect(QRectF(47, 40, 12, 12), 3, 3)
    p.setBrush(QColor(PURPLE))
    for y in (22, 28, 34):  # the pins
        p.drawEllipse(QPointF(11.5, y), 1.7, 1.7)
    p.setBrush(QColor(AMBER))
    p.drawEllipse(QPointF(13, 52), 8, 8)  # the check badge
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pen(PURPLE, 2.4))
    p.drawPolyline(QPolygonF([QPointF(9, 52), QPointF(12, 55), QPointF(17.5, 49)]))
    p.end()
    return pm


def app_icon() -> QIcon:
    """The logo at 16 to 256 pixels (needs a QGuiApplication)."""
    icon = QIcon()
    for size in SIZES:
        icon.addPixmap(_pixmap(size))
    return icon
