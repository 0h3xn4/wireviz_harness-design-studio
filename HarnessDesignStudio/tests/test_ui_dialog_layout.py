# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,attr-defined,union-attr,arg-type"
"""REQ-GUI-23. The *Add device* window of a real display: the name field lay over the note under
it and the banner over the buttons, and the banner *A device needs a name.* showed before anything
was typed.

The cause: a top-level window may be made as small as its layout's minimum size, and that counts a
word-wrapped label as one line. At that size the layout has less height than its wrapped text
needs and squeezes the rows into each other. `gui/dialog_base.py` keeps the window's minimum
height equal to what the layout needs at its width. These tests pin the cause (the window at its
smallest size, with the banner shown and hidden, at larger fonts), the banner (shown only after a
change), and that every dialog of the program has the base. The audit itself is tested here too,
so that a sweep that finds nothing can be trusted to be able to find something.
"""

import importlib
import inspect
import pkgutil

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWizard,
)

pytestmark = pytest.mark.gui

import harness_design_studio.gui as gui_package  # noqa: E402
from harness_design_studio.core.samples import new_project  # noqa: E402
from harness_design_studio.gui.devices_dialogs import (  # noqa: E402
    NewDeviceDialog,
    QuickDeviceDialog,
)
from harness_design_studio.gui.dialog_base import Dialog, Wizard, needed_height  # noqa: E402
from harness_design_studio.gui.wrap_label import WrapLabel  # noqa: E402
from tests.layout_audit import audit  # noqa: E402
from tests.layout_cases import cases  # noqa: E402
from tests.test_ui_layout_sweep import SCENARIOS, settle, themed  # noqa: E402


def open_dialog(cls, scenario: str = "light"):
    name, scale, extra = SCENARIOS[scenario]
    dlg = cls(None, themed(name, scale, extra), new_project())
    dlg.show()
    settle()
    return dlg


def at_smallest(dlg) -> None:
    """What a window manager that opens the window small, or a person dragging an edge, does."""
    dlg.resize(1, 1)
    settle()


# ---- the Add device windows --------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ["light", "font-plus-4pt", "light-150"])
@pytest.mark.parametrize("cls", [NewDeviceDialog, QuickDeviceDialog])
def test_add_device_at_its_smallest_size_has_nothing_over_anything(qtbot, cls, scenario) -> None:
    dlg = open_dialog(cls, scenario)
    qtbot.addWidget(dlg)
    assert audit(dlg) == []
    at_smallest(dlg)
    assert audit(dlg) == []
    # the smallest size is the height the wrapped note and the banner need, not one line of each
    assert dlg.height() >= needed_height(dlg) >= dlg.layout().totalMinimumSize().height()
    if cls is QuickDeviceDialog:  # (the narrow one: the layout's own minimum is 2 lines short)
        assert needed_height(dlg) > dlg.layout().totalMinimumSize().height()


@pytest.mark.parametrize("cls", [NewDeviceDialog, QuickDeviceDialog])
def test_add_device_grows_when_the_banner_appears_and_stays_whole(qtbot, cls) -> None:
    dlg = open_dialog(cls)
    qtbot.addWidget(dlg)
    before = dlg.height()
    dlg.name.setText("x")
    dlg.name.setText("")  # the person typed and took it out: the reason shows
    settle()
    assert dlg.notice.isVisibleTo(dlg) and "needs a name" in dlg.notice.text()
    assert dlg.height() > before  # the window grew by the banner
    assert audit(dlg) == []
    at_smallest(dlg)
    assert audit(dlg) == []


@pytest.mark.parametrize("cls", [NewDeviceDialog, QuickDeviceDialog])
def test_the_banner_does_not_show_before_anything_is_typed(qtbot, cls) -> None:
    dlg = open_dialog(cls)
    qtbot.addWidget(dlg)
    assert not dlg.ok.isEnabled()  # the button says it: a name is needed
    assert not dlg.notice.isVisibleTo(dlg) and dlg.notice.text() == ""
    dlg.name.setText("Star tracker")
    assert dlg.ok.isEnabled() and not dlg.notice.isVisibleTo(dlg)
    dlg.name.setText("")  # emptied again: now the banner says why the button is off
    assert not dlg.ok.isEnabled() and dlg.notice.isVisibleTo(dlg)
    dlg.name.setText("Star tracker")
    assert not dlg.notice.isVisibleTo(dlg)  # and it goes when the reason does


def test_a_window_that_gets_more_text_than_it_was_built_for_grows(qtbot) -> None:
    class Note(Dialog):
        def __init__(self) -> None:
            super().__init__()
            lay = QVBoxLayout(self)
            self.field = QLineEdit()
            self.note = QLabel("A note. " * 4)
            self.note.setWordWrap(True)
            lay.addWidget(self.field)
            lay.addWidget(self.note)

    dlg = Note()
    qtbot.addWidget(dlg)
    dlg.show()
    settle()
    assert audit(dlg) == []
    dlg.note.setText("A much longer note that needs more lines at this width. " * 6)
    settle()
    assert audit(dlg) == []
    dlg.resize(1, 1)
    settle()
    assert audit(dlg) == [] and dlg.height() >= needed_height(dlg)


# ---- the window shrinks back (the owner's feedback of 2026-11-17) -----------------------------------
# On a real display (Ubuntu, scaling 1.25) the first-start window was taller than the main window,
# with big gaps between its parts: the base had grown it while it was narrow (a wrapped text has
# many lines then) and never gave the height back once the window was wide again.

MARGIN = 8  # what "content plus a small margin" allows (rounding of a scaled display)


class _Wrapped(Dialog):
    """A window of wrapped texts and a button, nothing that wants extra height."""

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        for _ in range(3):
            label = QLabel("Pick the one that fits your work, it decides what shows first. " * 2)
            label.setWordWrap(True)
            lay.addWidget(label)
        lay.addWidget(QPushButton("OK"))


def test_a_window_made_tall_by_a_narrow_width_shrinks_back_when_it_is_wide_again(qtbot) -> None:
    dlg = _Wrapped()
    qtbot.addWidget(dlg)
    dlg.resize(520, 10)
    dlg.show()
    settle()
    normal = dlg.height()
    assert normal <= needed_height(dlg) + MARGIN
    dlg.resize(160, dlg.height())  # narrow: the texts wrap into many lines and the window grows
    settle()
    tall = dlg.height()
    assert tall > normal + 40 and audit(dlg) == []
    dlg.resize(520, dlg.height())  # wide again (what a window manager or the person does)
    settle()
    assert dlg.width() >= 520
    assert dlg.height() < tall
    assert dlg.height() <= needed_height(dlg) + MARGIN, (dlg.height(), needed_height(dlg))
    assert audit(dlg) == []


def test_a_window_never_shrinks_below_its_content_or_the_authors_floor(qtbot) -> None:
    dlg = _Wrapped()
    dlg.setMinimumHeight(400)  # the author's floor
    qtbot.addWidget(dlg)
    dlg.resize(520, 10)
    dlg.show()
    settle()
    dlg.resize(160, dlg.height())
    settle()
    dlg.resize(520, dlg.height())
    settle()
    assert dlg.height() >= 400 and dlg.height() >= needed_height(dlg)
    assert audit(dlg) == []


def test_a_height_the_person_chose_is_kept(qtbot) -> None:
    """Only the height the base added goes again: a window the person made taller stays so."""
    dlg = _Wrapped()
    qtbot.addWidget(dlg)
    dlg.resize(520, 10)
    dlg.show()
    settle()
    dlg.resize(520, dlg.height() + 150)  # the person drags the lower edge
    settle()
    chosen = dlg.height()
    dlg.resize(560, chosen)
    settle()
    assert dlg.height() == chosen


def test_a_height_the_code_set_is_kept(qtbot) -> None:
    """A dialog that its code makes larger than it needs (the glossary: `resize(560, 520)`) opens at
    that size; only a height the base itself added is given back."""
    from harness_design_studio.gui.dialogs import GlossaryDialog

    dlg = GlossaryDialog(None)
    qtbot.addWidget(dlg)
    dlg.show()
    settle()
    assert dlg.height() == 520 > needed_height(dlg) + MARGIN
    dlg.resize(dlg.width() + 100, dlg.height())
    settle()
    assert dlg.height() == 520
    plain = _Wrapped()
    qtbot.addWidget(plain)
    plain.resize(520, 600)  # (before it is shown, as a dialog's __init__ does)
    plain.show()
    settle()
    assert plain.height() == 600


@pytest.mark.parametrize("cls", [NewDeviceDialog, QuickDeviceDialog])
def test_a_dialog_of_the_program_gives_the_height_back(qtbot, cls) -> None:
    dlg = open_dialog(cls)
    qtbot.addWidget(dlg)
    width, normal = dlg.width(), dlg.height()
    dlg.resize(dlg.minimumWidth(), normal)
    settle()
    dlg.resize(width + 200, dlg.height())
    settle()
    assert dlg.height() <= max(normal, needed_height(dlg)) + MARGIN
    assert audit(dlg) == []


# ---- the first start on Home (also on the real platforms of REQ-GUI-26, at scale 1 and 1.25) ------


@pytest.mark.parametrize("size", [(1100, 700), (1440, 900)])
def test_home_with_the_role_question_fits_without_gaps(qtbot, tmp_path, monkeypatch, size) -> None:
    """The question of the first start is on Home (2026-11-17), not in a window that a window
    manager can open taller than the main window: the section has room for its text, nothing in
    it lies over anything else, each big button is as high as its text needs and no higher (no
    gaps), and it is no wider than the page."""
    from harness_design_studio.gui import roles
    from tests.gui_helpers import make_window

    monkeypatch.setattr(roles, "FIRST_RUN_ROLE", None)
    win = make_window(tmp_path, first_run=True)
    qtbot.addWidget(win)
    win.show_landing()
    win.resize(*size)
    settle()
    page = win.home_page
    assert win.landing() and page.role_card.isVisible()
    assert audit(page.role_card) == []
    for button in page.role_buttons.values():
        need = button.heightForWidth(button.width())
        floor = button.minimumHeight()  # (the style's height of a big button, 72 px at 100 %)
        top = max(need, floor) + MARGIN
        assert need <= button.height() <= top, (button.objectName(), button.height(), need, floor)
    assert page.role_card.geometry().right() <= page.viewport().width()
    assert page.role_card.height() < win.height()


def test_a_wrapped_label_in_a_split_pane_counts_all_its_lines(qtbot) -> None:
    """A splitter does not ask for height for width: the label's minimum height has to follow."""
    from PySide6.QtWidgets import QSplitter

    window = QWidget()
    split = QSplitter()
    pane = QWidget()
    lay = QVBoxLayout(pane)
    plain = QLabel("word " * 60)
    plain.setWordWrap(True)
    wrap = WrapLabel("word " * 60)
    lay.addWidget(plain)
    lay.addWidget(wrap)
    split.addWidget(pane)
    outer = QVBoxLayout(window)
    outer.addWidget(split)
    window.resize(300, 400)
    shown(qtbot, window)
    narrow = wrap.width()
    assert (
        wrap.minimumSizeHint().height()
        >= wrap.heightForWidth(narrow)
        > plain.minimumSizeHint().height()
    )


# ---- every dialog has the base ----------------------------------------------------------------------


def gui_classes() -> list[type]:
    found = []
    for mod in pkgutil.walk_packages(gui_package.__path__, "harness_design_studio.gui."):
        if ".theme" in mod.name:
            continue
        module = importlib.import_module(mod.name)
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == mod.name:
                found.append(obj)
    return found


def test_every_dialog_and_wizard_of_the_program_derives_from_the_base() -> None:
    bare = [
        f"{c.__module__}.{c.__name__}"
        for c in gui_classes()
        if (issubclass(c, QDialog) and not issubclass(c, QWizard) and not issubclass(c, Dialog))
        or (issubclass(c, QWizard) and not issubclass(c, Wizard))
    ]
    assert not bare, f"derive these from gui.dialog_base.Dialog (or Wizard): {bare}"


def test_the_sweep_has_a_case_for_every_dialog_of_the_program() -> None:
    covered = {name for case in cases() for name in case.classes}
    dialogs = {
        c.__name__
        for c in gui_classes()
        if issubclass(c, Dialog | Wizard)
        and c not in (Dialog, Wizard)
        and not c.__name__.startswith("_")
    }
    # (the base of the planner dialogs and the pages of the wizard are covered by their dialogs)
    missing = sorted(dialogs - covered - {"FilePage"})
    assert not missing, f"add these to tests/layout_cases.py: {missing}"


# ---- the audit finds what it is meant to find ---------------------------------------------------------


def shown(qtbot, widget: QWidget) -> QWidget:
    qtbot.addWidget(widget)
    widget.show()
    settle()
    return widget


def test_the_audit_sees_two_widgets_lying_over_each_other(qtbot) -> None:
    host = QWidget()
    a, b = QPushButton("first", host), QPushButton("second", host)
    host.resize(300, 200)
    a.setGeometry(10, 10, 120, 40)
    b.setGeometry(60, 20, 120, 40)
    shown(qtbot, host)
    assert [f.rule for f in audit(host)] == ["overlap"]
    b.setProperty("overlay", True)  # a widget that is meant to lie over another is not a finding
    assert audit(host) == []


def test_the_audit_sees_a_child_that_reaches_out_of_its_parent(qtbot) -> None:
    host = QWidget()
    child = QPushButton("cut off", host)
    host.resize(100, 60)
    # at least its own minimum: an earlier test of the worker may have left a larger app font,
    # and this test is about `outside` alone, not `squeezed`
    hint = child.minimumSizeHint()
    child.setGeometry(60, 10, max(100, hint.width()), max(30, hint.height()))
    shown(qtbot, host)
    assert [f.rule for f in audit(host)] == ["outside"]


def test_the_audit_sees_a_wrapped_label_that_is_too_short_and_a_cut_text(qtbot) -> None:
    host = QWidget()
    wrapped = QLabel("word " * 40, host)
    wrapped.setWordWrap(True)
    wrapped.setGeometry(0, 0, 120, 20)
    cut = QLabel("a label that does not fit its width", host)
    cut.setGeometry(0, 100, 40, 20)
    host.resize(200, 200)
    shown(qtbot, host)
    rules = sorted(f.rule for f in audit(host))
    assert "wrap-clipped" in rules and "text-cut" in rules


def test_the_audit_sees_a_window_that_is_shorter_than_its_text_needs(qtbot) -> None:
    dlg = QDialog()
    lay = QVBoxLayout(dlg)
    label = QLabel("word " * 60)
    label.setWordWrap(True)
    lay.addWidget(label)
    lay.addWidget(QLineEdit())
    shown(qtbot, dlg)
    dlg.resize(1, 1)  # a plain dialog may be made as small as its layout's minimum
    settle()
    if dlg.height() >= dlg.layout().totalMinimumSize().height() + 20:
        # (Windows keeps a window above its own smallest tracking size and may give it the
        # screen's height: the window is not short, so there is nothing for the audit to find)
        pytest.skip("this platform does not give a window as small as its layout's minimum")
    rules = {f.rule for f in audit(dlg)}
    assert "window-short" in rules, rules
    app = QApplication.instance()
    assert app is not None


def test_a_height_scroll_area_keeps_the_minimum_width_of_its_content(qapp) -> None:
    """The Harness and Devices tabs scroll in height only (REQ-GUI-23): a plain scroll area lets
    the window get narrower than the content, which is then cut off at the right edge (the
    *More* button of the Harness tab on Windows at 900 x 560)."""
    from PySide6.QtWidgets import QScrollArea

    from harness_design_studio.gui.dialog_base import HeightScrollArea

    inner = QWidget()
    lay = QVBoxLayout(inner)
    wide = QPushButton("x")
    wide.setMinimumWidth(1000)
    lay.addWidget(wide)
    plain, keeps = QScrollArea(), HeightScrollArea()
    for area in (plain, keeps):
        area.setWidgetResizable(True)
    plain.setWidget(inner)
    inner2 = QWidget()
    lay2 = QVBoxLayout(inner2)
    wide2 = QPushButton("x")
    wide2.setMinimumWidth(1000)
    lay2.addWidget(wide2)
    keeps.setWidget(inner2)
    assert plain.minimumSizeHint().width() < 1000
    assert keeps.minimumSizeHint().width() >= 1000
