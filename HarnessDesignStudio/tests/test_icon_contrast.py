# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The logo stays visible on the panels people use, and its three copies draw the same picture.

Owner feedback of 2026-11-17: on Ubuntu in dark mode the old icon was barely visible. The new logo
has a lighter rim for that. These tests hold the rim's contrast against the light and dark panels
of Ubuntu and Windows (WCAG 2.1: at least 3:1 for graphics), on the colours and on the icon as it
is painted at the sizes a dock and a taskbar show; and they hold the painted icon
(`gui/appicon.py`), `docs/img/logo.svg` and the Ubuntu icon
(`packaging/ubuntu/harness-design-studio.svg`) to one drawing.
"""

import re
import xml.etree.ElementTree as ET  # noqa: S405
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.gui.theme.tokens import BRAND

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "docs" / "img" / "logo.svg"
UBUNTU = ROOT / "packaging" / "ubuntu" / "harness-design-studio.svg"
SVG = "{http://www.w3.org/2000/svg}"

# the panels an icon sits on: Ubuntu's dock and header bar, Windows' taskbar and windows, in dark
# and in light mode
DARK = {"Windows 11 taskbar": "#1c1c1c", "Windows window": "#202020", "Ubuntu dock": "#2b2b2b", "Ubuntu header bar": "#303030"}  # fmt: skip
LIGHT = {"Windows light": "#f3f3f3", "Ubuntu light": "#fafafa", "white": "#ffffff"}


def _luminance(colour: str) -> float:
    """WCAG 2.1 relative luminance of `#rrggbb`."""

    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_the_contrast_formula() -> None:
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#777777", "#777777") == pytest.approx(1.0)


@pytest.mark.parametrize("panel", [*DARK.items(), *LIGHT.items()], ids=lambda p: p[0])
def test_the_rim_has_at_least_3_to_1_on_every_panel(panel: tuple[str, str]) -> None:
    name, colour = panel
    assert contrast(BRAND["rim"], colour) >= 3.0, name


def test_the_purple_tile_alone_would_vanish_on_dark_panels() -> None:
    """Why the rim is there: the tile's own purple is below 2:1 on the dark panels."""
    assert all(contrast(BRAND["purple"], c) < 2.0 for c in DARK.values())


def test_the_content_reads_on_the_purple_tile() -> None:
    """White and amber marks on the tile: at least 4.5:1, the step for small detail."""
    assert contrast(BRAND["white"], BRAND["purple"]) >= 7.0
    assert contrast(BRAND["amber"], BRAND["purple"]) >= 4.5


# ---- the icon as it is painted ------------------------------------------------------------------


def _edge_contrast(size: int, panel: str) -> float:
    """The contrast between the panel and the icon's top edge where it meets the panel, with the
    icon painted at `size` pixels and laid over the panel (anti-aliasing included)."""
    from PySide6.QtGui import QColor, QImage, QPainter

    from harness_design_studio.gui.appicon import _pixmap

    canvas = QImage(size, size, QImage.Format.Format_ARGB32)
    canvas.fill(QColor(panel))
    p = QPainter(canvas)
    p.drawPixmap(0, 0, _pixmap(size))
    p.end()
    # the topmost row that is not the panel, at the middle of the top edge
    for y in range(size // 4):
        colour = canvas.pixelColor(size // 2, y).name()
        if colour != panel:
            return contrast(colour, panel)
    raise AssertionError(f"no edge found at {size} px on {panel}")


@pytest.mark.gui
@pytest.mark.parametrize("size", [32, 48, 64])
@pytest.mark.parametrize("panel", [*DARK.items(), *LIGHT.items()], ids=lambda p: p[0])
def test_the_painted_edge_stands_out_from_the_panel(
    qapp: object, size: int, panel: tuple[str, str]
) -> None:
    """32 and 48 px are the sizes of the Ubuntu dock and the Windows taskbar."""
    pytest.importorskip("PySide6")
    name, colour = panel
    assert _edge_contrast(size, colour) >= 3.0, f"{name} at {size} px"


# ---- one drawing in three places ---------------------------------------------------------------


def _shapes(path: Path) -> list[tuple[str, tuple[tuple[str, str], ...]]]:
    """The drawing of an SVG file: every element below the root except the title, with its
    attributes (the root's size and the title's ID differ between the copies on purpose)."""
    root = ET.fromstring(path.read_text(encoding="utf-8"))  # noqa: S314
    assert root.get("viewBox") == "0 0 64 64", path.name
    shapes = []
    for el in root.iter():
        if el is root or el.tag == SVG + "title":
            continue
        shapes.append((el.tag.removeprefix(SVG), tuple(sorted(el.attrib.items()))))
    return shapes


def test_the_logo_and_the_ubuntu_icon_draw_the_same_picture() -> None:
    assert _shapes(LOGO) == _shapes(UBUNTU)


def _hex(colour: str) -> str:
    """`#fff` and `#ffffff` as one form."""
    colour = colour.lower()
    return "#" + "".join(c * 2 for c in colour[1:]) if len(colour) == 4 else colour


def test_the_svg_uses_only_the_brand_colours_and_all_of_them() -> None:
    text = LOGO.read_text(encoding="utf-8")
    used = {_hex(c) for c in re.findall(r'(?:fill|stroke)="(#[0-9a-fA-F]{3,6})"', text)}
    brand = {_hex(BRAND[k]) for k in ("purple", "amber", "white", "lavender", "orbit", "rim")}
    assert used == brand


def _numbers(d: str) -> list[float]:
    return [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]


def test_the_painted_icon_follows_the_svg() -> None:
    """The star and the three wires of `gui/appicon.py` are the paths of the SVG, point for point,
    in the same colours (the packaged program paints the icon in code, without Qt's SVG module)."""
    from harness_design_studio.gui import appicon

    root = ET.fromstring(LOGO.read_text(encoding="utf-8"))  # noqa: S314
    paths = [el for el in root.iter(SVG + "path")]
    star = next(p for p in paths if p.get("fill") and p.get("d", "").endswith("Z"))
    assert _numbers(star.get("d", "")) == [float(v) for pt in appicon._STAR for v in pt]

    def flat(start: Any, segments: tuple[Any, ...]) -> list[float]:
        out = [float(v) for v in start]
        for _kind, *points in segments:
            out += [float(v) for pt in points for v in pt]
        return out

    group = next(g for g in root.iter(SVG + "g") if g.get("stroke-width") == "3")
    wires = list(group.iter(SVG + "path"))
    assert len(wires) == len(appicon._WIRES) == 3
    for svg_wire, (colour, (start, *segments)) in zip(wires, appicon._WIRES, strict=True):
        assert _hex(svg_wire.get("stroke", "")) == _hex(colour)
        assert _numbers(svg_wire.get("d", "")) == flat(start, tuple(segments))
