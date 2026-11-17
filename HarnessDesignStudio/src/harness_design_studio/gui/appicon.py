# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The application icon (the logo of docs/img/logo.svg), painted in code.

It is drawn with QPainter rather than loaded from the SVG because the packaged program ships
without the Qt SVG module. The shapes are the data below; docs/img/logo.svg and
packaging/ubuntu/harness-design-studio.svg hold the same shapes (tests/test_gui_icon.py compares
them), and tools/make_icons.py renders this drawing into the Windows .ico.

The tile has a margin of 4 units on the 64-unit grid and a light violet rim (BRAND "rim") that
stands out against light and dark panels alike (3:1 or more against both, WCAG 2.1 SC 1.4.11).
One thick cable joins the two connectors, a white sheath with the dashed amber core on the same
line, so it stays a line, not a hairline, at 16 to 48 pixels.
"""

from typing import NamedTuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from harness_design_studio.gui.theme.tokens import BRAND

SIZES = (16, 24, 32, 48, 64, 128, 256)
GRID = 64  # the logo is drawn on a 64 x 64 grid
PURPLE = BRAND["purple"]
AMBER = BRAND["amber"]
WHITE = BRAND["white"]
RIM = BRAND["rim"]


class Rect(NamedTuple):
    """A filled rounded rectangle (SVG `<rect>`)."""

    colour: str
    x: float
    y: float
    width: float
    height: float
    radius: float


class Curve(NamedTuple):
    """A stroked cubic Bézier curve (SVG `<path d="M.. C..">`, butt ends); `dash` in grid units."""

    colour: str
    width: float
    dash: tuple[float, ...]
    start: tuple[float, float]
    control1: tuple[float, float]
    control2: tuple[float, float]
    end: tuple[float, float]


# In drawing order. The connectors and the cable are symmetric about the centre (32, 32).
RECTS: tuple[Rect, ...] = (
    Rect(RIM, 4, 4, 56, 56, 10),  # the rim: the outer edge of the tile
    Rect(PURPLE, 7, 7, 50, 50, 7),  # the tile
    Rect(WHITE, 11, 13, 14, 14, 2),  # connector A
    Rect(WHITE, 39, 37, 14, 14, 2),  # connector B
)
CURVES: tuple[Curve, ...] = (  # one cable: a white sheath with a dashed amber core on the same line
    Curve(WHITE, 9, (), (25, 20), (37, 20), (27, 44), (39, 44)),
    Curve(AMBER, 4, (6, 4), (25, 20), (37, 20), (27, 44), (39, 44)),
)


def _pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / GRID, size / GRID)
    p.setPen(Qt.PenStyle.NoPen)
    for r in RECTS:
        p.setBrush(QColor(r.colour))
        p.drawRoundedRect(QRectF(r.x, r.y, r.width, r.height), r.radius, r.radius)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for c in CURVES:
        path = QPainterPath(QPointF(*c.start))
        path.cubicTo(QPointF(*c.control1), QPointF(*c.control2), QPointF(*c.end))
        pen = QPen(QColor(c.colour), c.width)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)  # SVG's default ends ("butt")
        if c.dash:
            pen.setDashPattern([d / c.width for d in c.dash])  # Qt counts in pen widths
        p.setPen(pen)
        p.drawPath(path)
    p.end()
    return pm


def app_icon() -> QIcon:
    """The logo at 16 to 256 pixels (needs a QGuiApplication)."""
    icon = QIcon()
    for size in SIZES:
        icon.addPixmap(_pixmap(size))
    return icon
