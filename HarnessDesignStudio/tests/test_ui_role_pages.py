# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,attr-defined,union-attr,arg-type"
"""S9 (R6): the roles are tested on every page. A table, per role, of the pages the rail lists and the
entries the menus list; nothing is hidden in every role; everything a role leaves out is still reached
by the command palette; every page opens in every role. The hidden-link problem of the Systems
engineer role (the pending-values link) is fixed on the Next step page."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from harness_design_studio.core import templates  # noqa: E402
from harness_design_studio.gui import areas, strings  # noqa: E402
from harness_design_studio.gui.roles import AIT, ELECTRICAL, ROLES, SYSTEMS  # noqa: E402
from tests.gui_helpers import make_window  # noqa: E402


def listed(win) -> set[str]:
    """The object names of the entries a person sees in the menus (submenus included)."""
    out: set[str] = set()

    def walk(menu: QMenu) -> None:
        for a in menu.actions():
            if a.menu() is not None:
                if a.isVisible():
                    walk(a.menu())
            elif a.isVisible() and not a.isSeparator() and a.objectName():
                out.add(a.objectName())

    for top in win.menuBar().actions():
        walk(top.menu())
    return out


def every_action(win) -> set[str]:
    return {a.objectName() for a in win.findChildren(QAction) if a.objectName().startswith(("act-", "menu-"))}  # fmt: skip


@pytest.fixture
def table(qtbot, tmp_path: Path):
    """For each role: the pages the rail lists and the entries of the menus, read from the window."""
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    rows: dict[str, dict[str, set[str]]] = {}
    for role in ROLES:
        win.set_role(role)
        win.set_area("next")  # (the rail always lists the area that is open: leave the Model one)
        QApplication.processEvents()
        rows[role] = {
            "rail": {k for k, b in win.rail.buttons.items() if b.isVisibleTo(win.rail)},
            "menus": listed(win),
        }
    return win, rows


def test_the_rail_of_each_role_is_the_table_of_the_areas(table) -> None:
    _win, rows = table
    assert rows[SYSTEMS]["rail"] == {"next", "model", "checks", "revisions", "settings"}
    assert rows[ELECTRICAL]["rail"] == set(areas.KEYS)  # every area (As-built too since 5.1.0)
    assert rows[AIT]["rail"] == {"next", "home", "checks", "drawings", "outputs", "asbuilt", "review", "revisions", "settings"}  # fmt: skip
    for role in ROLES:  # the window agrees with the pure table
        assert rows[role]["rail"] == set(areas.listed_areas(role))


def test_no_page_and_no_menu_entry_is_hidden_in_every_role(table) -> None:
    win, rows = table
    assert set.union(*(r["rail"] for r in rows.values())) == set(areas.KEYS)
    assert areas.unlisted_everywhere() == ()
    known = every_action(win)
    union = set.union(*(r["menus"] for r in rows.values()))
    # the actions that are not in a menu on purpose: the toolbar and the context actions, the
    # diagram's own, Show side panels (Systems only: it is hidden and disabled in the others)
    not_menus = known - union
    assert not [n for n in not_menus if n in areas.SYSTEMS_HIDDEN_ACTIONS + areas.AIT_HIDDEN_ACTIONS + areas.ASBUILT_ACTIONS], not_menus  # fmt: skip
    # every entry a role leaves out is listed by another role
    for role in ROLES:
        left_out = {n for n in areas.hidden_actions_in(role) if not n.startswith("menu:")}
        assert left_out <= every_action(win), role
        assert not (left_out & rows[role]["menus"]), role
        assert left_out <= union, (role, left_out - union)


def test_each_role_lists_what_it_works_with(table) -> None:
    _win, rows = table
    for name in ("act-add-device", "act-generate", "act-check", "act-export", "act-save", "act-open", "act-library", "act-undo", "act-guide", "act-commands"):  # fmt: skip
        for role in ROLES:
            assert name in rows[role]["menus"], (role, name)
    for role in (AIT, ELECTRICAL):
        assert {"act-go-asbuilt", "act-import-asbuilt", "act-export-asbuilt"} <= rows[role]["menus"]
    # the Systems engineer leaves out the two files of the sheet, as it leaves out the other imports
    assert not ({"act-import-asbuilt", "act-export-asbuilt"} & rows[SYSTEMS]["menus"])
    assert areas.hidden_actions_in(ELECTRICAL) == ()  # the Electrical engineer lists every entry
    for role in ROLES:  # the Review page is in every role's Go menu (REQ-GUI-31)
        assert "act-go-review" in rows[role]["menus"], role
    # every role's Go menu offers the As-built page, and the AIT engineer's offers the Devices tab
    # (5.1.0, the owner's instruction of 2026-11-24: no feature hidden from a role's own work)
    for role in ROLES:
        assert "act-go-asbuilt" in rows[role]["menus"], role
        assert "asbuilt" in rows[role]["rail"] or "act-go-asbuilt" in rows[role]["menus"], role
    assert "act-go-devices" in rows[AIT]["menus"]
    # the Electrical engineer lists everything the old role listed; the AIT engineer leaves out the diagram edits
    gone = (
        rows[ELECTRICAL]["menus"] - rows[AIT]["menus"]
    )  # (the submenu "Connect with an interface type" goes whole)
    named = {n for n in areas.AIT_HIDDEN_ACTIONS if not n.startswith("menu:")}
    assert gone == named | {n for n in gone if n.startswith("menu-connect-")}, gone ^ named
    assert len(areas.SYSTEMS_HIDDEN_ACTIONS) == 40 and len(areas.AIT_HIDDEN_ACTIONS) == 28


def test_what_a_role_leaves_out_is_still_in_the_command_palette(table) -> None:
    win, rows = table
    for role in ROLES:
        win.set_role(role)
        QApplication.processEvents()
        labels = {e.label for e in win.palette_entries()}
        for name in areas.hidden_actions_in(role):
            if name.startswith("menu:"):
                continue
            act = next(a for a in win.findChildren(QAction) if a.objectName() == name)
            if act.isEnabled():  # (an action that needs a selection waits for one)
                assert act.text().replace("&", "") in labels, (role, name)
        assert strings.GO_ASBUILT in labels and strings.A_IMPORT_ASBUILT in labels  # every role
        assert strings.GO_REVIEW in labels  # the Review page (4.3.0, REQ-GUI-31), every role


def test_every_page_opens_in_every_role(table) -> None:
    win, _rows = table
    for role in ROLES:
        win.set_role(role)
        for key in areas.KEYS:
            win.set_area(key)
            QApplication.processEvents()
            assert win.area() == key
            assert win.rail.buttons[key].isVisibleTo(win.rail)  # the one that is open is listed
            assert not win.grab().isNull()
        assert win.role == role


def test_the_ait_role_opens_a_project_on_the_next_step_page_with_the_asbuilt_button(qtbot, tmp_path) -> None:  # fmt: skip
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    win.set_role(AIT)
    folder = tmp_path / "p"
    templates.create_project(folder, "flatsat")
    win.open_project(folder)
    QApplication.processEvents()
    assert win.area() == "next" and win.next_page.asbuilt.isVisibleTo(win.next_page)
    assert not win.next_page.links.isVisibleTo(win.next_page)
    win.next_page.asbuilt.click()
    assert win.area() == "asbuilt"
    win.set_role(ELECTRICAL)
    win.set_area("next")
    assert not win.next_page.asbuilt.isVisibleTo(win.next_page)


def test_the_pending_values_are_said_on_the_next_step_page_in_every_role(qtbot, tmp_path) -> None:
    """The hidden-link problem: the status bar's link is a problem notice and the Systems engineer has
    them off; the page that role starts on says it, with a button that opens the values."""
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    folder = tmp_path / "p"
    templates.create_project(folder, "flatsat")  # four engineering values are not set
    win.open_project(folder)
    opened: list[int] = []
    win.values_flow = lambda: opened.append(1)  # type: ignore[method-assign]
    for role in ROLES:
        win.set_role(role)
        win.set_area("next")
        QApplication.processEvents()
        assert win.next_page.pending.isVisibleTo(win.next_page), role
        assert "4 engineering values are still to set" in win.next_page.pending_text.text()
    win.set_role(SYSTEMS)
    assert (
        not win.pending_link.isVisibleTo(win) or win.pending_link.suppressed
    )  # the old link is off
    win.next_page.pending_button.click()
    assert opened == [1]


def disabled_without_reason(win) -> list[str]:
    """The visible, disabled menu entries (submenus included) whose tooltip gives no reason. A reason
    is a sentence: the tooltip, without the shortcut in brackets at its end, ends with a full stop
    (the action's own name, or a tooltip that only says what the entry does, is not a reason)."""
    out: list[str] = []

    def reason(a: QAction) -> bool:
        tip = a.toolTip().strip()
        key = a.shortcut().toString()
        if key and tip.endswith(f" ({key})"):
            tip = tip[: -len(key) - 3].strip()
        return tip.endswith(".") and tip != a.text().replace("&", "")

    def walk(menu: QMenu) -> None:
        for a in menu.actions():
            if a.isSeparator() or not a.isVisible():
                continue
            if not a.isEnabled() and not reason(a):
                out.append(f"{a.text()!r} ({a.objectName() or 'submenu'}): {a.toolTip()!r}")
            if a.menu() is not None:
                walk(a.menu())

    for top in win.menuBar().actions():
        walk(top.menu())
    return out


def test_no_visible_disabled_menu_entry_lacks_a_reason(qtbot, tmp_path: Path) -> None:
    """F10 of the feature audit of 5.1.0: every entry that is off says why in its tooltip, and the
    menus show the tooltips (a project with harnesses and no release: *Show changes of harness…* is
    off; nothing is selected: the *Selected connection* submenu is off; nothing to undo)."""
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    assert win.ctl.project.harnesses and not win.ctl.project.baselines
    for role in ROLES:
        for quick in (False, True):
            win.set_role(role)
            if win.quick_on() != quick:
                win.act_quick.trigger()
            QApplication.processEvents()
            assert disabled_without_reason(win) == [], (role, quick)
    if win.quick_on():
        win.act_quick.trigger()
    assert not win.act_changes.isEnabled() and win.act_changes.toolTip() == strings.CHANGES_NONE_TIP  # fmt: skip
    assert not win.menu_connection.isEnabled()
    assert win.menu_connection.menuAction().toolTip() == strings.WHY_SELECT_CONNECTION
    assert win.act_link_edit.toolTip() == strings.WHY_SELECT_CONNECTION
    menus = [t.menu() for t in win.menuBar().actions() if t.menu() is not None]
    while menus:  # every menu of the menu bar and every submenu shows the tooltips
        menu = menus.pop()
        assert menu.toolTipsVisible(), menu.title()
        menus.extend(a.menu() for a in menu.actions() if a.menu() is not None)


def test_every_area_has_a_go_entry_in_every_role_with_quick_mode_off_and_on(qtbot, tmp_path: Path) -> None:  # fmt: skip
    """A role hides tools, never places (the owner's instruction of 2026-11-24): the Go menu of every
    role lists an entry for every area (the Model: Diagram and Devices), Quick mode or not, each
    enabled and in the command palette; *Go to Next step* opens the Next step page."""
    assert set(areas.GO_ACTIONS) == set(areas.KEYS)
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    go_menu = win.menu_go
    for role in ROLES:
        for quick in (False, True):
            win.set_role(role)
            if win.quick_on() != quick:
                win.act_quick.trigger()
            QApplication.processEvents()
            shown = {a.objectName() for a in go_menu.actions() if a.isVisible()}
            labels = {e.label for e in win.palette_entries()}
            for key, names in areas.GO_ACTIONS.items():
                for name in names:
                    assert name in shown, (role, quick, key, name)
                    act = next(a for a in win.findChildren(QAction) if a.objectName() == name)
                    assert act.isEnabled() and act.text().replace("&", "") in labels, (role, quick, name)  # fmt: skip
            win.set_area("home")
            win.act_go_next.trigger()
            QApplication.processEvents()
            assert win.area() == "next", (role, quick)
