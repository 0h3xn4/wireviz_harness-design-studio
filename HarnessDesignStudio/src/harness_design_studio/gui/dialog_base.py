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

It also runs them (`run_dialog`) as windows that move on their own. A dialog that Qt makes modal
(`exec()`) is marked modal for the window system, and GNOME (Mutter, `attach-modal-dialogs`)
then glues it to its parent: it cannot be moved apart from the main window (the owner's feedback
of 2026-11-17). `run_dialog` shows the dialog as a normal window that stays in front of its
parent instead, and waits for its answer as `exec()` did. While it waits, `InputGuard` keeps
the clicks, keys and the close button away from the windows that were open before it (the main
window, the library window, a dialog that opened this one), so the step that needs the answer
still gets it first, exactly as with a modal dialog; a click on such a window brings the dialog
to the front. A dialog that only shows something (`blocks = False`: the glossary, the
assumptions, a change log) does not wait at all: the main window stays usable beside it.

    if run_dialog(dlg) == QDialog.DialogCode.Accepted:   # waits; the window moves freely
        ...
"""

from PySide6.QtCore import QEvent, QEventLoop, QObject, QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QDialog, QScrollArea, QWidget, QWizard

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
    before = window.height()
    # (a window that is not shown yet has no height of its own: what it gives back goes to the need)
    start = before if window.isVisible() else need
    if window.minimumHeight() != need or (wide and window.minimumWidth() != wide):
        window.setMinimumSize(wide or window.minimumWidth(), need)  # (this grows a smaller window)
    if window.height() < need or (wide and window.width() < wide):
        window.resize(max(window.width(), wide), max(window.height(), need))
    height = window.height()
    if height > before + _SLACK:  # grown here: remember from what, to give it back later
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
    """A dialog that grows with its content (see the module text). `blocks` False: a dialog that
    only shows something; `run_dialog` shows it beside the main window and does not wait."""

    blocks = True

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


# ---- running a dialog as a window that moves on its own ---------------------------------------------

_GUARDED = frozenset(
    {
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonRelease,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.MouseMove,
        QEvent.Type.Wheel,
        QEvent.Type.KeyPress,
        QEvent.Type.KeyRelease,
        QEvent.Type.ShortcutOverride,
        QEvent.Type.Shortcut,
        QEvent.Type.ContextMenu,
        QEvent.Type.DragEnter,
        QEvent.Type.DragMove,
        QEvent.Type.Drop,
        QEvent.Type.TabletPress,
        QEvent.Type.TouchBegin,
        QEvent.Type.ToolTip,
        QEvent.Type.Close,
    }
)


def _window_of(obj: QObject) -> QWidget | None:
    if isinstance(obj, QWidget):
        return obj.window()
    if isinstance(obj, QAction):  # (a shortcut is delivered to its action)
        parent = obj.parent()
        return parent.window() if isinstance(parent, QWidget) else None
    return None


class InputGuard(QObject):
    """What makes a dialog that is not modal wait like one: while it is installed, the windows that
    were open when it was made (all but `dialog`) get no clicks, keys, shortcuts, wheel or drop,
    and the window system's close button does nothing on them. A press on one of them brings the
    dialog to the front. Windows that open later (the dialog's own lists and menus, a question it
    asks) are not touched. Install it on the application; `run_dialog` does."""

    def __init__(self, dialog: QWidget) -> None:
        super().__init__()
        self.dialog = dialog
        self.blocked = [
            w for w in QApplication.topLevelWidgets() if w.isVisible() and w is not dialog
        ]

    def guards(self, window: QWidget | None) -> bool:
        return window is not None and any(window is w for w in self.blocked)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind not in _GUARDED:
            return False
        window = _window_of(obj)
        if not self.guards(window):
            return False
        if kind == QEvent.Type.Close:
            if obj is not window or not event.spontaneous():
                return False  # (the program closing something itself goes on)
            event.ignore()  # the window system's close button: the answer comes first
            return True
        if kind == QEvent.Type.ShortcutOverride:
            event.accept()  # (an accepted override is what keeps the shortcut from firing)
            return True
        if kind == QEvent.Type.MouseButtonPress and self.dialog.isVisible():
            self.dialog.raise_()
            self.dialog.activateWindow()
        return True


def show_beside(dialog: QDialog) -> None:
    """Show a dialog that only shows something as a window of its own, in front of its parent and
    not modal, and return at once (the main window stays usable)."""
    dialog.setWindowModality(Qt.WindowModality.NonModal)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()


def run_dialog(dialog: QDialog) -> int:
    """Run a dialog of the program and return its result, as `exec()` does, without making it
    modal for the window system (see the module text): it stays in front of its parent and moves
    on its own. A dialog with `blocks` False is only shown (`show_beside`) and 0 is returned."""
    if not getattr(dialog, "blocks", True):
        show_beside(dialog)
        return 0
    app = QApplication.instance()
    dialog.setWindowModality(Qt.WindowModality.NonModal)
    guard = InputGuard(dialog)
    loop = QEventLoop()
    ended: list[bool] = []

    def end(*_args: object) -> None:
        ended.append(True)
        loop.quit()

    dialog.finished.connect(end)
    dialog.destroyed.connect(end)
    if app is not None:
        app.installEventFilter(guard)
    try:
        dialog.setResult(0)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        if not ended and dialog.isVisible():
            loop.exec()
    finally:
        if app is not None:
            app.removeEventFilter(guard)
    try:
        dialog.finished.disconnect(end)
        dialog.destroyed.disconnect(end)
        return int(dialog.result())
    except RuntimeError:  # (the dialog was deleted while it ran)
        return 0
