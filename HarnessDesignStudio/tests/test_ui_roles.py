# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,attr-defined,has-type"
"""M5 (D-176): the two roles on screen. REQ-GUI-14, REQ-GUI-15.

The question of the first start (since the owner's feedback of 2026-11-17 a section on Home, not a
window of its own), the silent role of an existing user, switching in both directions
without a restart, nothing hidden that cannot be reached, both themes, names and tooltips."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from harness_design_studio.gui import areas, roles, strings  # noqa: E402
from harness_design_studio.gui.main_window import MainWindow  # noqa: E402
from harness_design_studio.gui.theme import ThemeManager  # noqa: E402
from tests.ux_rel import themed  # noqa: E402


def settings_at(tmp_path: Path, name: str = "ui.ini", **values: object) -> QSettings:
    s = QSettings(str(tmp_path / name), QSettings.Format.IniFormat)
    for key, value in values.items():
        s.setValue(key.replace("__", "/"), value)
    s.sync()
    return s


def make(qtbot, tmp_path, *, first_run=False, name="ui.ini", theme=None, **values) -> MainWindow:
    w = MainWindow(
        settings_at(tmp_path, name, **values), theme or ThemeManager(), first_run=first_run
    )
    w.ask_choice = lambda t, x, b: 1  # type: ignore[assignment]
    qtbot.addWidget(w)
    w.resize(1440, 900)
    return w


class NoWindow:
    """The `run_dialog` hook: the first start opens no window of its own any more (the owner's
    feedback of 2026-11-17: the question is on Home, not in a window of its own)."""

    def __init__(self) -> None:
        self.dialogs: list[object] = []

    def __call__(self, dlg) -> int:
        self.dialogs.append(dlg)
        return 0


@pytest.fixture
def no_hook(monkeypatch):
    """The program as it ships: nothing sets a role for a new settings file."""
    monkeypatch.setattr(roles, "FIRST_RUN_ROLE", None)


def show(qtbot, w: MainWindow) -> MainWindow:
    w.show()
    QApplication.processEvents()
    QApplication.processEvents()
    return w


def start(qtbot, w: MainWindow, watch: NoWindow | None = None) -> MainWindow:
    """The start as `app.main` does it: the landing page, then the window."""
    if watch is not None:
        w.run_dialog = watch  # type: ignore[assignment]
    w.show_landing()
    w.show()
    for _ in range(3):
        QApplication.processEvents()
    return w


def asked(w: MainWindow) -> bool:
    """The question of the first start is on Home, on screen."""
    page = w.home_page
    return w.area() == "home" and page.role_card.isVisibleTo(w)


def choose(w: MainWindow, role: str) -> None:
    w.home_page.role_buttons[role].click()
    QApplication.processEvents()


# ---- the question of the first start -----------------------------------------------------------
def test_a_new_settings_file_without_a_hook_asks_once_on_home(qtbot, tmp_path, no_hook) -> None:
    watch = NoWindow()
    w = start(qtbot, make(qtbot, tmp_path, first_run=True), watch)
    assert asked(w) and w.landing()
    for role in roles.ROLES:
        assert w.home_page.role_buttons[role].isVisibleTo(w)
    choose(w, "systems")
    assert watch.dialogs == []  # no window: the question is on the page
    assert w.role == "systems" and w.settings.value("ui/role") == "systems"
    assert not w.home_page.role_card.isVisibleTo(w)  # answered: the section goes
    assert w.landing() and w.area() == "home" and w.ctl.root is None  # still Home, nothing open
    w.settings.sync()
    # a second start on the same file does not ask again
    w2 = start(qtbot, make(qtbot, tmp_path, first_run=True))
    assert not asked(w2) and not w2.home_page.role_card.isVisibleTo(w2) and w2.role == "systems"


def test_choosing_systems_stores_the_role_and_applies_its_layout(qtbot, tmp_path, no_hook) -> None:
    w = start(qtbot, make(qtbot, tmp_path, first_run=True))
    choose(w, "systems")
    assert w.role == "systems" and w.act_role_systems.isChecked()
    assert w.settings_page.role_combo.currentData() == "systems"
    assert not w.act_minimap.isChecked() and not w.problem_notices_on()
    # Home stays until the person goes on; then the Systems engineer's layout is there
    assert not w.top_toolbar.isVisibleTo(w) and not w.dock_left.isVisibleTo(w)
    w.set_area("next")
    assert not w.landing() and w.top_toolbar.isVisibleTo(w)
    assert not w.dock_left.isVisibleTo(w) and not w.dock_right.isVisibleTo(w)
    assert w.next_page.links.isVisibleTo(w.next_page)


def test_choosing_electrical_stores_the_role_and_shows_everything(qtbot, tmp_path, no_hook) -> None:
    w = start(qtbot, make(qtbot, tmp_path, first_run=True))
    choose(w, "electrical")
    assert w.role == "electrical" and w.settings.value("ui/role") == "electrical"
    assert w.act_role_electrical.isChecked() and w.landing() and w.area() == "home"
    assert all(w.rail.buttons[k].isVisibleTo(w.rail) for k in areas.listed_areas("electrical"))
    assert not w.rail.buttons["asbuilt"].isVisibleTo(w.rail)  # the AIT engineer's page
    assert w.problem_notices_on()


def test_choosing_ait_stores_the_role(qtbot, tmp_path, no_hook) -> None:
    w = start(qtbot, make(qtbot, tmp_path, first_run=True))
    choose(w, "ait")
    assert w.role == "ait" and w.settings.value("ui/role") == "ait" and w.landing()


def test_until_it_is_answered_the_window_is_an_electrical_engineer_and_view_role_answers_it(
    qtbot, tmp_path, no_hook
) -> None:
    w = start(qtbot, make(qtbot, tmp_path, first_run=True))
    assert asked(w) and w.role == "electrical" and not w.settings.contains("ui/role")
    w.act_role_ait.trigger()  # View > Role answers the question too
    assert w.role == "ait" and w.settings.value("ui/role") == "ait"
    w.set_area("home")
    assert not w.home_page.role_card.isVisibleTo(w)


def test_no_question_for_an_existing_user_a_hook_or_a_window_that_is_not_a_first_start(
    qtbot, tmp_path, no_hook, monkeypatch
) -> None:
    # an existing user: values and no role -> Electrical / AIT engineer, silently, stored
    w = start(qtbot, make(qtbot, tmp_path, name="old.ini", first_run=True, ui__theme="dark"))
    assert not asked(w) and w.role == "electrical"
    assert w.settings.value("ui/role") == "electrical"
    # not a first start (tools, screenshots): no question, nothing stored
    w = start(qtbot, make(qtbot, tmp_path, name="quiet.ini", first_run=False))
    assert not asked(w) and w.role == "electrical" and not w.settings.contains("ui/role")
    # the hook of tests and CI
    monkeypatch.setattr(roles, "FIRST_RUN_ROLE", "systems")
    w = start(qtbot, make(qtbot, tmp_path, name="hook.ini", first_run=True))
    assert not asked(w) and w.role == "systems" and w.settings.value("ui/role") == "systems"


def test_the_choice_of_1_7_0_carries_over_silently(qtbot, tmp_path, no_hook) -> None:
    w = start(qtbot, make(qtbot, tmp_path, name="a.ini", first_run=True, ui__workspace="simple"))
    assert not asked(w) and w.role == "systems" and w.settings.value("ui/role") == "systems"
    w = start(qtbot, make(qtbot, tmp_path, name="b.ini", first_run=True, ui__workspace="full"))
    assert not asked(w) and w.role == "electrical"


def test_a_hand_edited_role_falls_back(qtbot, tmp_path, no_hook) -> None:
    w = start(qtbot, make(qtbot, tmp_path, first_run=False, ui__role="pink", ui__theme="dark"))
    assert w.role == "electrical" and w.settings.value("ui/role") == "electrical"


def test_the_role_dialog_is_gone() -> None:
    import importlib.util

    assert importlib.util.find_spec("harness_design_studio.gui.role_dialog") is None
    assert not hasattr(MainWindow, "ask_role_flow")


# ---- the question on Home ----------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_question_on_home_in_both_themes(qtbot, tmp_path, no_hook, mode) -> None:
    theme = themed(mode)
    w = start(qtbot, make(qtbot, tmp_path, first_run=True, theme=theme))
    page = w.home_page
    assert page.role_card.accessibleName() == strings.HOME_ROLE_NAME
    texts = [label.text() for label in page.role_card.findChildren(QLabel)]
    assert strings.HOME_ROLE_TITLE in texts and strings.HOME_ROLE_LATER in texts
    assert "View > Role" in strings.HOME_ROLE_LATER
    for role, title, sentence in (
        ("systems", strings.ROLE_SYSTEMS, strings.HOME_ROLE_SYSTEMS_TEXT),
        ("electrical", strings.ROLE_ELECTRICAL, strings.HOME_ROLE_ELECTRICAL_TEXT),
        ("ait", strings.ROLE_AIT, strings.HOME_ROLE_AIT_TEXT),
    ):
        button = page.role_buttons[role]
        assert isinstance(button, QPushButton)
        assert button.accessibleName() == title and button.accessibleDescription() == sentence
        assert button.toolTip() and button.isVisibleTo(w)
        assert button.height() >= theme.control_height() * 2  # a large button
    assert not page.grab().isNull()


@pytest.mark.parametrize("width", [900, 1440])
def test_the_question_on_home_has_room_for_its_text(qtbot, tmp_path, no_hook, width) -> None:
    from tests.layout_audit import audit

    w = start(qtbot, make(qtbot, tmp_path, first_run=True))
    w.resize(width, 700)
    for _ in range(5):
        QApplication.processEvents()
    assert asked(w)
    assert audit(w.home_page.role_card) == []
    # the three buttons are one below the other, each as wide as the others
    b = [w.home_page.role_buttons[r].geometry() for r in roles.ROLES]
    assert b[0].bottom() < b[1].top() and b[1].bottom() < b[2].top()


def test_the_tab_walk_of_the_question_visits_the_three_buttons(qtbot, tmp_path, no_hook) -> None:
    w = start(qtbot, make(qtbot, tmp_path, first_run=True))
    w.activateWindow()
    w.home_page.role_buttons["systems"].setFocus()
    seen = {QApplication.focusWidget()}
    for _ in range(3):
        w.focusNextChild()
        seen.add(QApplication.focusWidget())
    assert set(w.home_page.role_buttons.values()) <= seen


# ---- switching live -----------------------------------------------------------------------------
def test_switching_in_both_directions_keeps_each_roles_layout(qtbot, tmp_path) -> None:
    w = show(qtbot, make(qtbot, tmp_path, ui__role="electrical"))
    w.act_minimap.trigger()  # Electrical: the minimap off
    w.dock_left.hide()
    w.act_role_systems.trigger()
    assert w.role == "systems" and not w.dock_right.isVisibleTo(w)
    w.show_panels(True)
    w.act_legend.trigger()  # Systems: the legend on
    w.act_role_electrical.trigger()
    assert w.role == "electrical" and not w.dock_left.isVisibleTo(w) and w.dock_right.isVisibleTo(w)
    assert not w.view.minimap_wanted and w.view.legend_wanted
    w.act_role_systems.trigger()
    assert w.dock_left.isVisibleTo(w) and w.dock_right.isVisibleTo(w)
    assert w.view.legend_wanted and not w.view.minimap_wanted
    assert w.settings.value("ui/role") == "systems"
    assert w.settings_page.role_combo.currentData() == "systems"
    assert w.act_role_systems.isChecked() and not w.act_role_electrical.isChecked()


def test_the_two_actions_are_exclusive_and_the_menu_has_them(qtbot, tmp_path) -> None:
    w = show(qtbot, make(qtbot, tmp_path, ui__role="electrical"))
    acts = w.menu_role.actions()
    assert [a.objectName() for a in acts] == [
        "act-role-systems", "act-role-electrical", "act-role-ait",
    ]  # fmt: skip
    assert all(a.isCheckable() for a in acts)
    assert w.menu_role.title() == "Role"
    view = next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == "View")
    assert w.menu_role.menuAction() in view.actions()
    assert [a.isChecked() for a in acts] == [False, True, False]
    acts[0].trigger()
    assert [a.isChecked() for a in acts] == [True, False, False]
    assert {
        w.act_role_systems.shortcut().toString(),
        w.act_role_electrical.shortcut().toString(),
        w.act_role_ait.shortcut().toString(),
    } == {""}


def test_a_second_window_on_the_same_file_restores_the_role(qtbot, tmp_path) -> None:
    first = show(qtbot, make(qtbot, tmp_path, ui__role="electrical"))
    first.act_role_systems.trigger()
    first.close()
    first.settings.sync()
    second = show(qtbot, make(qtbot, tmp_path))
    assert second.role == "systems" and second.act_role_systems.isChecked()


def test_the_role_is_never_stored_in_the_project(qtbot, tmp_path) -> None:
    w = show(qtbot, make(qtbot, tmp_path, ui__role="electrical"))
    folder = tmp_path / "proj"
    w.ctl.new_project(folder, "Blank")
    w.ctl.save()

    def files() -> dict[str, bytes]:
        return {
            str(p.relative_to(folder)): p.read_bytes()
            for p in sorted(folder.rglob("*"))
            if p.is_file()
        }

    before = files()
    w.set_role("systems")
    w.ctl.save()
    after = files()
    assert before.keys() == after.keys() and before == after
    assert not any(b"systems" in data or b'"role"' in data for data in after.values())


# ---- nothing is hidden for good -----------------------------------------------------------------
def test_every_area_the_systems_rail_leaves_out_is_still_reachable(qtbot, tmp_path) -> None:
    w = show(qtbot, make(qtbot, tmp_path, ui__role="systems"))
    left_out = areas.hidden_in("systems")
    assert left_out and all(not w.rail.buttons[k].isVisibleTo(w.rail) for k in left_out)
    for key in left_out:
        w.set_area(key)
        assert w.area() == key  # the Go menu, the keys and the Next step buttons do this
        assert w.rail.buttons[key].isVisibleTo(w.rail)
    labels = [e.label for e in w.palette_entries()]
    for label in (strings.GO_HOME, strings.A_GO_HARNESS, strings.A_GO_LISTS, strings.A_LIBRARY):
        assert label in labels, label
    # and the other role, which shows them all, is one command away
    assert strings.ROLE_ELECTRICAL in labels and strings.ROLE_SYSTEMS in labels


def test_the_command_palette_finds_the_hidden_areas(qtbot, tmp_path) -> None:
    w = show(qtbot, make(qtbot, tmp_path, ui__role="systems"))
    entries = {e.label: e for e in w.palette_entries()}
    entries[strings.A_GO_LISTS].run()
    assert w.area() == "outputs"
    entries[strings.A_GO_HARNESS].run()
    assert w.area() == "drawings"
    entries[strings.GO_HOME].run()
    assert w.area() == "home"


def test_the_next_step_page_reaches_the_library_and_the_other_role(qtbot, tmp_path) -> None:
    w = show(qtbot, make(qtbot, tmp_path, ui__role="systems"))
    w.set_area("next")
    opened: list[int] = []
    w.open_library_flow = lambda: opened.append(1)  # type: ignore[method-assign]
    assert w.next_page.library.isVisibleTo(w.next_page)
    w.next_page.library.click()
    assert opened == [1]
    w.next_page.everything.click()
    assert w.role == "electrical" and w.area() == "model"
    w.rail.buttons["next"].click()  # the page is reachable, not first
    assert w.area() == "next" and not w.next_page.links.isVisibleTo(w.next_page)


def test_the_systems_role_keeps_what_m2_and_m4_added(qtbot, tmp_path) -> None:
    w = show(qtbot, make(qtbot, tmp_path, ui__role="systems"))
    w.set_area("model")
    assert w.tool_connect.isVisibleTo(w) and w.tool_add_device.isVisibleTo(w)
    assert w.act_library.isEnabled() and w.act_check_connections.isEnabled()
    w.show_panels(True)
    assert strings.TREE_ROOTS["links"] == "Connections"
    assert w.project_tree.child_ids("links") == []  # the group exists (and is empty here)


def test_the_electrical_role_lists_every_area_and_opens_the_diagram(qtbot, tmp_path) -> None:
    w = show(qtbot, make(qtbot, tmp_path, ui__role="electrical"))
    assert all(w.rail.buttons[k].isVisibleTo(w.rail) for k in areas.listed_areas("electrical"))
    assert w.area() == "model"
    w.rail.buttons["next"].click()  # the Next step page is reachable, though not first
    assert w.area() == "next"


# ---- both themes, names and tooltips ---------------------------------------------------------------
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_both_roles_in_both_themes(qtbot, tmp_path, mode) -> None:
    w = show(
        qtbot, make(qtbot, tmp_path, name=f"{mode}.ini", theme=themed(mode), ui__role="electrical")
    )
    for role in ("systems", "electrical", "systems"):
        w.set_role(role)
        for key in areas.KEYS:
            w.set_area(key)
            QApplication.processEvents()
            assert not w.grab().isNull()
        assert w.role == role


def test_names_and_tooltips(qtbot, tmp_path) -> None:
    w = show(qtbot, make(qtbot, tmp_path, ui__role="systems"))
    for act, text in (
        (w.act_role_systems, "Systems engineer"),
        (w.act_role_electrical, "Electrical engineer"),
        (w.act_role_ait, "AIT engineer"),
    ):
        assert act.text() == text and act.toolTip() and act.toolTip() != text
    combo = w.settings_page.role_combo
    assert combo.accessibleName() == "Role" and combo.toolTip()
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "Systems engineer",
        "Electrical engineer",
        "AIT engineer",
    ]
    assert combo.objectName() == "settings-role"
    for button in (w.next_page.library, w.next_page.everything):
        assert button.accessibleName() and button.toolTip()
    for text in (strings.NEXT_SHOW_EVERYTHING_TIP, strings.SETTINGS_ROLE_HINT):
        assert "workspace" not in text.lower() and "Simple" not in text and "Full" not in text
