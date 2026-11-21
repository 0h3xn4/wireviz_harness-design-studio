# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The navigation rail: one button per area, icon above label, down the left edge of the window.

    rail = NavRail(theme)
    rail.areaSelected.connect(window.set_area)
    rail.select("model")            # without a signal
    rail.set_collapsed(True)        # icons only

Settings sits at the bottom, away from the work areas. The rail holds no logic: it says which area
the person chose. Every button has an accessible name and a tooltip, so the icons-only form is
still usable with a screen reader and by hovering.
"""

from collections.abc import Collection

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from harness_design_studio.gui import areas, icons, strings
from harness_design_studio.gui.icons import tooltip_text
from harness_design_studio.gui.theme import ThemeManager

RAIL_PX = 72  # expanded width at 100 %
RAIL_COLLAPSED_PX = 48
ICON_PX = 20  # the brief: 20 px in the navigation rail


class NavRail(QFrame):
    areaSelected = Signal(str)

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme = theme
        self.collapsed = False  # the person's choice
        self.compact = False  # icons only, whatever the choice: a short window, or a short rail
        self._short = False  # the window says it is short (`set_compact`)
        self._hidden: tuple[str, ...] = ()  # the areas the role leaves out (see `set_hidden`)
        self.setObjectName("nav-rail")
        self.setProperty("rail", True)
        self.setAccessibleName(strings.RAIL_NAME)
        lay = QVBoxLayout(self)
        self._lay = lay
        lay.setContentsMargins(theme.space(4), theme.space(8), theme.space(4), theme.space(8))
        lay.setSpacing(theme.space(4))
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QToolButton] = {}
        for a in areas.AREAS:
            button = QToolButton()
            button.setObjectName(f"rail-{a.key}")
            button.setProperty("rail", True)
            button.setCheckable(True)
            button.setText(a.title)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setAccessibleName(a.title)
            button.setAccessibleDescription(a.tip)
            button.setToolTip(a.tip)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.group.addButton(button)
            self.buttons[a.key] = button
            button.clicked.connect(lambda _c=False, key=a.key: self.areaSelected.emit(key))
            if a.key == "settings":
                lay.addStretch(1)  # Settings sits at the bottom
            lay.addWidget(button)
        self.toggle = QToolButton()
        self.toggle.setObjectName("rail-collapse")
        self.toggle.setProperty("rail", True)
        self.toggle.setProperty("iconOnly", True)
        self.toggle.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toggle.clicked.connect(lambda _c=False: self.set_collapsed(not self.collapsed))
        lay.addWidget(self.toggle)
        # a button with a label that is never shown: the height of a labelled button, measured
        # also while the rail shows icons only (`labelled_height`)
        self._probe = QToolButton(self)
        self._probe.setProperty("rail", True)
        self._probe.setText(areas.AREAS[0].title)
        self._probe.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._probe.setAccessibleName(areas.AREAS[0].title)
        self._probe.hide()
        theme.changed.connect(self._restyle)
        self.set_collapsed(False)

    # ---- state --------------------------------------------------------------------------------
    def select(self, key: str) -> None:
        """Mark an area as the current one (no signal)."""
        button = self.buttons[key]
        self.group.setExclusive(True)
        button.setChecked(True)
        self.set_hidden(self._hidden)  # (the area that is open is always listed)

    def set_hidden(self, keys: Collection[str]) -> None:
        """List every area but these (a role may leave some out; they stay reachable by their keys,
        menus and the palette). The area that is open is always listed, so the person sees where
        they are; it goes again when they leave it."""
        self._hidden = tuple(keys)
        for key, button in self.buttons.items():
            button.setVisible(key not in self._hidden or button.isChecked())
        self._fit()

    def current(self) -> str:
        for key, button in self.buttons.items():
            if button.isChecked():
                return key
        return ""

    def set_collapsed(self, collapsed: bool) -> None:
        self.collapsed = collapsed
        self._apply_style()

    def set_compact(self, compact: bool) -> None:
        """A window too short for the labels (the window calls this when it is resized)."""
        self._short = compact
        self._fit()

    def labelled_height(self) -> int:
        """The height the rail needs to show the areas it lists with their labels."""
        lay = self._lay
        m = lay.contentsMargins()
        n = sum(1 for b in self.buttons.values() if not b.isHidden())
        self._probe.ensurePolished()
        button = self._probe.sizeHint().height()
        toggle = self.toggle.sizeHint().height()
        return m.top() + m.bottom() + n * (button + lay.spacing()) + toggle

    def _fit(self) -> None:
        """Icons only when the window is short or the rail is too short for the labels of the
        areas it lists (since 4.3.0 the Electrical engineer's rail can list ten)."""
        compact = self._short or (self.height() > 0 and self.height() < self.labelled_height())
        if compact != self.compact:
            self.compact = compact
            self._apply_style()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit()

    def icons_only(self) -> bool:
        return self.collapsed or self.compact

    def _apply_style(self) -> None:
        style = (
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if self.icons_only()
            else Qt.ToolButtonStyle.ToolButtonTextUnderIcon
        )
        for button in self.buttons.values():
            button.setToolButtonStyle(style)
            button.setProperty("iconOnly", self.icons_only())
        self._restyle()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """As small as the icons-only rail: the window may be short, and then the rail is that."""
        n = len(self.buttons) + 1
        h = n * self.theme.control_height() + (n + 1) * self.theme.space(4) + self.theme.space(16)
        return QSize(self.theme.px(RAIL_COLLAPSED_PX), h)

    def _restyle(self) -> None:
        t = self.theme
        self._probe.setIcon(icons.icon(areas.AREAS[0].icon, t))
        self._probe.setIconSize(QSize(t.px(ICON_PX), t.px(ICON_PX)))
        for a in areas.AREAS:
            button = self.buttons[a.key]
            button.setIcon(icons.icon(a.icon, t))
            button.setIconSize(QSize(t.px(ICON_PX), t.px(ICON_PX)))
            button.setToolTip(tooltip_text(a.tip, ""))
        edge = t.px(RAIL_COLLAPSED_PX if self.icons_only() else RAIL_PX)
        self.setFixedWidth(edge)
        name = icons.icon("panel-open" if self.icons_only() else "panel-close", t)
        self.toggle.setIcon(name)
        self.toggle.setIconSize(QSize(t.px(16), t.px(16)))
        label = strings.RAIL_EXPAND if self.icons_only() else strings.RAIL_COLLAPSE
        self.toggle.setToolTip(label)
        self.toggle.setAccessibleName(label)
        for button in (*self.buttons.values(), self.toggle, self._probe):
            button.style().unpolish(button)
            button.style().polish(button)
