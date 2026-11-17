# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,attr-defined,union-attr,arg-type,method-assign,assignment,func-returns-value"
"""The windows of the program move on their own (the owner's feedback of 2026-11-17 on Ubuntu:
"All breakout windows should be independently moveable").

GNOME (Mutter, `attach-modal-dialogs`) glues a *modal* dialog that has a parent to that parent: it
cannot be moved apart from the main window. A dialog that is not modal stays in front of its parent
and moves freely. So the program runs its dialogs with `dialog_base.run_dialog`, never `exec()`:
the dialog is not modal for the window system; a dialog whose answer the next step needs still
waits for it, and `InputGuard` keeps the clicks, keys and shortcuts away from the main window
meanwhile, as Qt's modality did; a dialog that only shows something does not wait at all.

Qt's offscreen platform has no window manager, so whether GNOME attaches a window cannot be seen
here; what is tested is what GNOME reads: the window's modality.
"""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QAction, QKeySequence  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from harness_design_studio.gui import (  # noqa: E402
    extensions_dialog,
    library_window,
    link_dialog,
    wire_editor,
)
from harness_design_studio.gui import main_window as main_window_module  # noqa: E402
from harness_design_studio.gui.dialog_base import Dialog, run_dialog  # noqa: E402
from harness_design_studio.gui.dialogs import GlossaryDialog, HistoryDialog  # noqa: E402
from tests.gui_helpers import make_window  # noqa: E402


class _Owner(QMainWindow):
    """A main window with a button and a shortcut, to see what reaches it while a dialog runs."""

    def __init__(self) -> None:
        super().__init__()
        self.pressed = 0
        self.shortcuts = 0
        self.button = QPushButton("press")
        self.button.clicked.connect(self._press)
        self.setCentralWidget(self.button)
        act = QAction("go", self)
        act.setShortcut(QKeySequence("Ctrl+G"))
        act.triggered.connect(self._shortcut)
        self.addAction(act)
        self.resize(400, 300)

    def _press(self) -> None:
        self.pressed += 1

    def _shortcut(self) -> None:
        self.shortcuts += 1


class _Question(Dialog):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("A question"))
        self.ok = QPushButton("OK")
        self.ok.clicked.connect(self.accept)
        lay.addWidget(self.ok)


def _activate(window) -> bool:  # type: ignore[no-untyped-def]
    """What a click on the window's title bar does: the window system makes it the active one."""
    window.activateWindow()
    for _ in range(20):
        QApplication.processEvents()
        if window.isActiveWindow():
            return True
    return False


def _while_it_runs(check) -> list[object]:  # type: ignore[no-untyped-def]
    """Run `check(dialog)` once the dialog shows (from inside its wait); returns what it noted."""
    seen: list[object] = []

    def later() -> None:
        dlg = QApplication.activeWindow()
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QDialog) and w.isVisible():
                dlg = w
        seen.append(check(dlg))

    QTimer.singleShot(50, later)
    return seen


def test_a_dialog_that_waits_is_not_modal_and_still_waits(qtbot) -> None:
    owner = _Owner()
    qtbot.addWidget(owner)
    owner.show()
    dlg = _Question(owner)
    states: list[tuple[bool, object, object, bool]] = []

    def check(shown) -> None:  # type: ignore[no-untyped-def]
        modal = (shown.isModal(), shown.windowModality(), QApplication.activeModalWidget())
        QTest.mouseClick(owner.button, Qt.MouseButton.LeftButton)  # the main window gets nothing
        active = _activate(owner)  # (even when the person makes it the active window)
        QTest.keyClick(owner.button, Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(owner.button, Qt.Key.Key_Space)
        states.append((*modal, active))
        shown.ok.click()

    _while_it_runs(check)
    result = run_dialog(dlg)  # waits here, like exec()
    assert result == QDialog.DialogCode.Accepted
    assert states == [(False, Qt.WindowModality.NonModal, None, True)]  # GNOME does not attach it
    assert owner.pressed == 0 and owner.shortcuts == 0  # the next step got the answer first
    # once it has answered, the main window takes input again
    QTest.mouseClick(owner.button, Qt.MouseButton.LeftButton)
    assert _activate(owner)
    QTest.keyClick(owner.button, Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)
    assert owner.pressed == 1 and owner.shortcuts == 1


def test_closing_the_dialog_is_a_cancel(qtbot) -> None:
    owner = _Owner()
    qtbot.addWidget(owner)
    owner.show()
    dlg = _Question(owner)
    _while_it_runs(lambda shown: shown.close())
    assert run_dialog(dlg) == QDialog.DialogCode.Rejected


def test_the_program_can_still_close_a_window_while_a_dialog_waits(qtbot) -> None:
    """Only the window system's close button is held back; the program's own close goes on."""
    owner = _Owner()
    qtbot.addWidget(owner)
    owner.show()
    other = _Owner()
    qtbot.addWidget(other)
    other.show()
    dlg = _Question(owner)

    def check(shown) -> bool:  # type: ignore[no-untyped-def]
        closed = other.close()
        shown.ok.click()
        return closed

    seen = _while_it_runs(check)
    run_dialog(dlg)
    assert seen == [True] and not other.isVisible()


@pytest.mark.parametrize(
    "make",
    [
        lambda: GlossaryDialog(None),
        lambda: HistoryDialog(None, "Change log", [["a", "b"]]),
    ],
)
def test_a_dialog_that_only_shows_something_does_not_wait(qtbot, make) -> None:
    owner = _Owner()
    qtbot.addWidget(owner)
    owner.show()
    dlg = make()
    dlg.setParent(owner, dlg.windowFlags())
    assert dlg.blocks is False
    assert run_dialog(dlg) == 0  # back at once
    assert dlg.isVisible() and not dlg.isModal()
    QTest.mouseClick(owner.button, Qt.MouseButton.LeftButton)
    assert owner.pressed == 1  # the main window stays usable beside it
    dlg.close()


def test_every_dialog_of_the_program_runs_without_being_modal(qtbot, tmp_path: Path) -> None:
    """Each dialog and wizard of the layout sweep, run as the program runs it."""
    from tests.layout_cases import cases, make_ctx
    from tests.test_ui_layout_sweep import themed

    ctx = make_ctx(themed("light", 1.0, 0), tmp_path)
    modal: list[str] = []
    ran = 0
    try:
        for case in cases():
            widget = case.make(ctx)
            if not isinstance(widget, QDialog):
                widget.deleteLater()
                continue
            qtbot.addWidget(widget)
            notes: list[bool] = []

            def check(notes=notes, widget=widget) -> None:  # type: ignore[no-untyped-def]
                notes.append(
                    widget.isModal() or widget.windowModality() != Qt.WindowModality.NonModal
                )
                if widget.isVisible():
                    widget.done(0)

            QTimer.singleShot(0, check)
            run_dialog(widget)
            ran += 1
            if notes not in ([False], []):  # ([]: a viewer that does not wait)
                modal.append(case.name)
            widget.close()
    finally:
        ctx.ctl.release()
    assert ran >= 40
    assert modal == [], f"modal for the window system (GNOME attaches them): {modal}"


def test_the_window_and_its_parts_run_their_dialogs_this_way(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    assert win.run_dialog(GlossaryDialog(win)) == 0  # (the default: shown beside, no wait)
    ran: list[QDialog] = []
    monkeypatch.setattr(main_window_module, "run_dialog", lambda dlg: ran.append(dlg) or 0)
    dlg = QDialog(win)
    win.run_dialog(dlg)  # the window's default hook goes through `dialog_base.run_dialog`
    assert ran == [dlg]
    # no part of the program runs a dialog of its own with exec() (which makes it modal)
    for module in (library_window, link_dialog, extensions_dialog, wire_editor):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "dlg.exec()" not in source and "box.exec()" not in source, module.__name__


def test_the_message_box_and_the_text_question_move_on_their_own(qtbot, tmp_path: Path) -> None:
    """`ask_choice` and `ask_text` of the window: a question whose answer the next step needs, so
    it waits; but not modal for the window system."""
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    win.ask_choice = win._ask_choice
    win.ask_text = win._ask_text
    seen: list[tuple[str, bool]] = []

    def answer() -> None:
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QMessageBox) and w.isVisible():
                seen.append(("box", w.isModal()))
                w.buttons()[0].click()
            elif isinstance(w, QInputDialog) and w.isVisible():
                seen.append(("text", w.isModal()))
                w.setTextValue("Typed")
                w.accept()

    QTimer.singleShot(50, answer)
    assert win.ask_choice("Title", "Text", ["Yes", "No"]) == 0
    QTimer.singleShot(50, answer)
    assert win.ask_text("Title", "Name", "") == "Typed"
    assert seen == [("box", False), ("text", False)]
