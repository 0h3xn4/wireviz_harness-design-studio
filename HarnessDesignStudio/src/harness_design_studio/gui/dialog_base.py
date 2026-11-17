# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The base of the program's dialogs: a window that is never shorter than its content needs.

A layout that holds word-wrapped text (a note under a form, a message in an inline notice) needs a
height that depends on the width: the narrower the window, the more lines. Qt's top-level windows
do not take that into account. The smallest size a window may have is the layout's *minimum size*,
which counts a wrapped label as one line, so a window that is given its minimum (by a window
manager that opens it small, by a remembered size, by the person dragging an edge) is shorter than
its content at that width, and the layout squeezes the rows into each other: fields over the note,
a banner over the buttons. `fit_height_for_width` closes that gap: it keeps the window's minimum
height equal to what the layout needs at the window's current width and grows the window when it
is shorter. `Dialog` calls it, so every dialog that derives from it grows with its content.

    class MyDialog(Dialog):
        def __init__(self, parent):
            super().__init__(parent)
            ...
"""

from PySide6.QtCore import QEvent, QSize
from PySide6.QtWidgets import QDialog, QScrollArea, QWidget, QWizard

_REFIT = (
    QEvent.Type.Resize,
    QEvent.Type.LayoutRequest,
    QEvent.Type.Show,
    QEvent.Type.FontChange,
    QEvent.Type.StyleChange,
)


def _page_height_needed(page: QWidget) -> int:
    lay = page.layout()
    if lay is None:
        return 0
    need = lay.totalMinimumSize().height()
    if lay.hasHeightForWidth():
        need = max(need, lay.minimumHeightForWidth(page.width()))
    return need


def needed_height(window: QWidget) -> int:
    """The least height the window's layout can be laid out in at the window's width: the
    layout's minimum, or what its wrapped text needs at this width when that is more. 0 when the
    window has no layout. A wizard has its own layout, so it is the shown page that is asked, and
    the wizard needs that plus the height of what is around the page (title, buttons)."""
    if isinstance(window, QWizard):
        page = window.currentPage()
        if page is None or not window.isVisible() or page.height() <= 0:
            return 0
        return window.height() - page.height() + _page_height_needed(page)
    return _page_height_needed(window)


_SLACK = 2  # px a window system may round a height by (a scaled display) and still be "ours"


def fit_height_for_width(window: QWidget) -> None:
    """Make the window at least as high as its layout needs at its width (and keep it so when the
    width changes), and at least as wide as the layout's minimum. Setting a minimum also grows a
    window that is smaller. A minimum that the dialog set itself (`setMinimumSize`) stays as the
    floor, which also means that a size set in the code never hides what the layout needs.

    It fits both ways: the height it added (a narrow window wraps its text into more lines) is
    given back when the width grows again, down to the height the window had before it was grown
    and never below what the layout needs or the author's floor. A height that somebody else set
    after the growth (the person dragging the edge, the code) is left alone. Without this, a window
    that was narrow for a moment while it was being placed stayed tall, with gaps between its
    parts (the first-start window on a real display, 2026-11-17)."""
    if window.isMaximized() or window.isFullScreen():
        return
    need = needed_height(window)
    if need <= 0:
        return
    lay = window.layout()
    wide = lay.totalMinimumSize().width() if lay is not None else 0
    floors = getattr(window, "_author_min", None)
    if floors is None:  # the first time: a minimum that is not the layout's is the author's
        floors = (
            window.minimumWidth() if window.minimumWidth() > wide else 0,
            window.minimumHeight()
            if window.minimumHeight() > _page_height_needed(window) or isinstance(window, QWizard)
            else 0,
        )
        window._author_min = floors  # type: ignore[attr-defined]
    need = max(need, floors[1])
    wide = max(wide, floors[0])
    grown: tuple[int, int] | None = getattr(window, "_fit_grown", None)  # (before, after)
    if grown is not None and abs(window.height() - grown[1]) > _SLACK:
        grown = None  # somebody else set the height since: theirs stands
    # (a window that is not shown yet has no height of its own: what it gives back goes to the need)
    start = window.height() if window.isVisible() else need
    if window.minimumHeight() != need or (wide and window.minimumWidth() != wide):
        window.setMinimumSize(wide or window.minimumWidth(), need)  # (this grows a smaller window)
    if window.height() < need or (wide and window.width() < wide):
        window.resize(max(window.width(), wide), max(window.height(), need))
    height = window.height()
    if height > start + _SLACK:  # grown here: remember from what, to give it back later
        grown = (grown[0] if grown is not None else start, height)
    elif grown is not None and height > max(need, grown[0]) + _SLACK:
        target = max(need, grown[0])  # the width grew: give back the height that was added
        window.resize(window.width(), target)
        grown = (grown[0], window.height()) if window.height() > grown[0] + _SLACK else None
    window._fit_grown = grown  # type: ignore[attr-defined]


def refit_on(window: QWidget, e: QEvent) -> None:
    """Call from a window's `event()` after the base class has handled `e`: refits the height
    when the event is one that can change what the window needs."""
    if e.type() in _REFIT and not getattr(window, "_refitting", False):
        window._refitting = True  # type: ignore[attr-defined]  # (resizing sends events back here)
        try:
            fit_height_for_width(window)
        finally:
            window._refitting = False  # type: ignore[attr-defined]


class Dialog(QDialog):
    """A dialog that grows with its content (see the module text)."""

    def event(self, e: QEvent) -> bool:
        handled = super().event(e)
        refit_on(self, e)
        return handled


class Wizard(QWizard):
    """A wizard that grows with the page it shows (see the module text)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.currentIdChanged.connect(lambda _id: fit_height_for_width(self))

    def event(self, e: QEvent) -> bool:
        handled = super().event(e)
        refit_on(self, e)
        return handled


class HeightScrollArea(QScrollArea):
    """A scroll area that scrolls in height only: it keeps the minimum width of its content.

    A plain `QScrollArea` reports a tiny minimum size, so a window can be made narrower than the
    content needs and the content is then cut off at the right edge (a horizontal scroll bar or
    nothing at all). The tabs that sit in one keep their width, as they did before they scrolled,
    and only give up height (the layout then scrolls instead of squeezing its rows)."""

    def minimumSizeHint(self) -> QSize:
        base = super().minimumSizeHint()
        inner = self.widget()
        if inner is None:
            return base
        bar = self.verticalScrollBar().sizeHint().width() if self.verticalScrollBar() else 0
        return QSize(max(base.width(), inner.minimumSizeHint().width() + bar), base.height())
