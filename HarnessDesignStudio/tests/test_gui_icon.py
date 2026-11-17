# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The application icon: the window uses it, it stands out on light and dark panels, and the three
copies (gui/appicon.py, docs/img/logo.svg, packaging/ubuntu/harness-design-studio.svg) agree."""

import re
import xml.etree.ElementTree as ET  # noqa: S405
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

ROOT = Path(__file__).resolve().parents[1]
SVGS = (
    ROOT / "docs" / "img" / "logo.svg",
    ROOT / "packaging" / "ubuntu" / "harness-design-studio.svg",
)
# Representative panel colours of a dark and a light desktop (a dark dock and top bar, a light
# window or dock). They are not Ubuntu's official palette, only values in its range.
DARK_PANELS = ("#1d1d1d", "#303030")
LIGHT_PANELS = ("#fafafa", "#ffffff")
MIN_CONTRAST = 3.0  # WCAG 2.1 SC 1.4.11, non-text contrast of a graphic
DOCK_SIZES = (32, 48)


def test_the_window_and_the_application_use_the_logo(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from harness_design_studio.gui.app import create_window
    from harness_design_studio.gui.appicon import PURPLE, RIM, SIZES

    win = create_window(QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(win)
    assert not win.windowIcon().isNull()
    assert not QApplication.windowIcon().isNull()
    assert {s.width() for s in win.windowIcon().availableSizes()} == set(SIZES)
    img = win.windowIcon().pixmap(64, 64).toImage()
    assert img.pixelColor(32, 2).alpha() == 0  # the margin around the tile
    assert img.pixelColor(32, 4).name() == RIM  # the rim
    assert img.pixelColor(32, 9).name() == PURPLE  # the purple tile
    assert img.pixelColor(0, 0).alpha() == 0  # rounded corner
    assert img.pixelColor(16, 18).name() == "#ffffff"  # connector A


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG 2.1 relative luminance of an sRGB colour."""

    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    high, low = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def edge_colours(size: int) -> set[tuple[int, int, int]]:
    """The outer edge of the icon as `tools/make_icons.py` renders it: along each of the four sides
    (the middle half, away from the rounded corners) the first fully opaque pixel from outside."""
    from PySide6.QtGui import QImage

    from tools.make_icons import _png

    img = QImage.fromData(_png(size))
    assert img.width() == size
    found: set[tuple[int, int, int]] = set()
    for i in range(size // 4, size - size // 4):
        for line in (
            [(x, i) for x in range(size)],
            [(x, i) for x in reversed(range(size))],
            [(i, y) for y in range(size)],
            [(i, y) for y in reversed(range(size))],
        ):
            colour = next(c for c in (img.pixelColor(x, y) for x, y in line) if c.alpha() == 255)
            found.add((colour.red(), colour.green(), colour.blue()))
    return found


def test_the_contrast_formula_matches_wcag() -> None:
    assert contrast((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    assert contrast((0x77, 0x77, 0x77), (255, 255, 255)) == pytest.approx(4.48, abs=0.01)


@pytest.mark.parametrize("size", DOCK_SIZES)
@pytest.mark.parametrize("panel", DARK_PANELS + LIGHT_PANELS)
def test_the_edge_of_the_icon_stands_out_on_dark_and_light_panels(
    qapp: object, size: int, panel: str
) -> None:
    """Ubuntu's dark dock showed the old full-bleed purple tile at about 1.4:1 (owner, 2026-11-17)."""
    edges = edge_colours(size)
    assert edges
    worst = min(contrast(c, _rgb(panel)) for c in edges)
    assert worst >= MIN_CONTRAST, (size, panel, round(worst, 2), sorted(edges))


def test_the_icon_leaves_a_margin() -> None:
    from harness_design_studio.gui.appicon import GRID, RECTS

    outer = RECTS[0]
    assert outer.x >= 2 and outer.y >= 2
    assert outer.x + outer.width <= GRID - 2 and outer.y + outer.height <= GRID - 2


def test_the_lines_are_not_hairlines_at_dock_sizes() -> None:
    """At 32 pixels the narrowest line of the drawing is at least 2 pixels wide."""
    from harness_design_studio.gui.appicon import CURVES, GRID

    assert min(c.width for c in CURVES) * 32 / GRID >= 2


def _number(text: str | None) -> float:
    assert text is not None
    return float(text)


def _colour(text: str | None) -> str:
    assert text is not None and re.fullmatch(r"#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}", text), text
    if len(text) == 4:
        text = "#" + "".join(ch * 2 for ch in text[1:])
    return text.lower()


def svg_shapes(path: Path) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    """The rounded rectangles and the curves of an SVG copy of the logo, in drawing order."""
    root = ET.fromstring(path.read_text(encoding="utf-8"))  # noqa: S314
    assert root.get("viewBox") == "0 0 64 64"
    rects: list[tuple[object, ...]] = []
    curves: list[tuple[object, ...]] = []
    for el in root:
        tag = el.tag.split("}")[-1]
        if tag == "rect":
            assert curves == [], "a rectangle drawn after a curve"
            rects.append(
                (
                    _colour(el.get("fill")),
                    _number(el.get("x", "0")),
                    _number(el.get("y", "0")),
                    _number(el.get("width")),
                    _number(el.get("height")),
                    _number(el.get("rx")),
                )
            )
        elif tag == "path":
            d = el.get("d", "")
            m = re.fullmatch(r"M\s*([\d.\s]+?)\s*C\s*([\d.\s]+)", d.strip())
            assert m, d
            nums = [float(n) for n in (m.group(1) + " " + m.group(2)).split()]
            assert len(nums) == 8, d
            dash = tuple(float(n) for n in el.get("stroke-dasharray", "").split())
            assert el.get("fill") == "none" and el.get("stroke-linecap", "butt") == "butt"
            points = [(nums[i], nums[i + 1]) for i in range(0, 8, 2)]
            curves.append(
                (_colour(el.get("stroke")), _number(el.get("stroke-width")), dash, *points)
            )
        else:
            assert tag == "title", tag  # nothing else is drawn
    return rects, curves


@pytest.mark.parametrize("path", SVGS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_the_svg_copies_describe_the_shapes_that_appicon_paints(path: Path) -> None:
    from harness_design_studio.gui.appicon import CURVES, RECTS

    rects, curves = svg_shapes(path)
    want_rects = [(r.colour.lower(), *(float(v) for v in r[1:])) for r in RECTS]
    want_curves = [
        (
            c.colour.lower(),
            float(c.width),
            tuple(float(d) for d in c.dash),
            *(tuple(float(v) for v in pt) for pt in (c.start, c.control1, c.control2, c.end)),
        )
        for c in CURVES
    ]
    assert rects == want_rects
    assert curves == want_curves


def test_the_svg_copies_render_like_the_painted_icon(qapp: object) -> None:
    """Where Qt's SVG module is installed (the development environment; the package has none), the
    SVG files drawn at 64 pixels differ from the painted icon only by anti-aliasing."""
    qtsvg = pytest.importorskip("PySide6.QtSvg")
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter

    from harness_design_studio.gui.appicon import _pixmap

    painted = _pixmap(64).toImage().convertToFormat(QImage.Format.Format_ARGB32)
    for path in SVGS:
        img = QImage(64, 64, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        qtsvg.QSvgRenderer(str(path)).render(p, QRectF(0, 0, 64, 64))
        p.end()
        differ = 0
        for x in range(64):
            for y in range(64):
                a, b = img.pixelColor(x, y), painted.pixelColor(x, y)
                pairs = ((a.red(), b.red()), (a.green(), b.green()), (a.blue(), b.blue()))
                if max(abs(u - v) for u, v in (*pairs, (a.alpha(), b.alpha()))) > 48:
                    differ += 1
        assert differ <= 64 * 64 // 100, (path.name, differ)  # 1 % of the pixels at most
