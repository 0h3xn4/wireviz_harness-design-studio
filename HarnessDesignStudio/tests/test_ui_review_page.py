# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,attr-defined,union-attr,arg-type,index"
"""REQ-GUI-31 (4.3.0, pull request 5; `docs/ait/DESIGN_4.3_REVIEW_VIEW.md`, parts C and F, sections
5, 6.1 and 8). The Review page: one harness at a time, reached from the rail, the Next step page,
the Releases tab, the Go menu, the command palette and the menu of a harness in the project tree,
in every role. It shows `core.review.review_view` over the window's findings (the blocks of `flatsat`
W002 of section 4.4), *Show*, *Explain*, *Waive…* and *Copy link* (the clipboard, no browser), the
library state of each device, and tick boxes kept on this computer only (QSettings, dropped when the
list or the design changes). *Release…* hands the ticks to the release dialog, which shows the note
it adds to the comment. *Settings > Project* has the review checklist and the label format. No
written file changes."""

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtGui import QAction, QDesktopServices  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from harness_design_studio.core import (  # noqa: E402
    build_data,
    configcheck,
    label_format,
    review,
    templates,
)
from harness_design_studio.core.commands import apply_ops  # noqa: E402
from harness_design_studio.core.generate.engine import generate_project  # noqa: E402
from harness_design_studio.core.io.saver import save_project  # noqa: E402
from harness_design_studio.core.library_link import LinkState  # noqa: E402
from harness_design_studio.core.samples import mini3  # noqa: E402
from harness_design_studio.core.vcs import release as core_release  # noqa: E402
from harness_design_studio.gui import areas, icons, main_window, strings  # noqa: E402
from harness_design_studio.gui.dialogs import ChangeDialog  # noqa: E402
from harness_design_studio.gui.main_window import MainWindow  # noqa: E402
from harness_design_studio.gui.review_page import summary_text  # noqa: E402
from harness_design_studio.gui.roles import AIT, ELECTRICAL, ROLES, SYSTEMS  # noqa: E402
from harness_design_studio.gui.theme import ThemeManager  # noqa: E402
from tests.gui_helpers import DialogScript, hold_drc, make_window  # noqa: E402
from tools.format3_record import _release_history  # noqa: E402

POINTS = [
    "Wire list agrees with the drawing.",
    "Pinouts agree with the ICD.",
    "Labels are readable.",
]


def _open(win: MainWindow, folder: Path) -> MainWindow:
    assert win.open_project(folder)
    hold_drc(win)
    win.ctl.run_drc_now()
    QApplication.processEvents()
    return win


@pytest.fixture
def flatsat(tmp_path: Path) -> Path:
    templates.create_project(tmp_path / "p", "flatsat")
    return tmp_path / "p"


@pytest.fixture
def win(qtbot, tmp_path: Path, flatsat: Path) -> MainWindow:
    w = make_window(tmp_path)
    qtbot.addWidget(w)
    return _open(w, flatsat)


def set_points(win: MainWindow, points: list[str] | None) -> None:
    plan = configcheck.plan_set_checklist(win.ctl.project, points)
    assert plan.ok and win.ctl.run("Checklist", plan.ops)
    QApplication.processEvents()


def files_of(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file() and ".lock" not in p.name
    }


def tick(win: MainWindow, *numbers: int) -> None:
    model = win.review_page.models["checklist"]
    for n in numbers:
        assert model.setData(model.index(n - 1, 2), Qt.CheckState.Checked.value, Qt.ItemDataRole.CheckStateRole)  # fmt: skip


# ---- the area ------------------------------------------------------------------------------


def test_the_area_is_a_page_after_asbuilt_listed_by_the_electrical_and_ait_engineers() -> None:
    assert areas.KEYS.index("review") == areas.KEYS.index("asbuilt") + 1
    assert areas.KEYS.index("review") + 1 == areas.KEYS.index("revisions")
    a = areas.area("review")
    assert a.tabs == () and "review" in areas.PAGES and a.icon == "nav-review" and a.tip
    assert a.icon in icons.ICONS and icons.ICONS["nav-review"] != icons.ICONS["nav-asbuilt"]
    assert "review" in areas.hidden_in(SYSTEMS)  # R7: as Drawings and Outputs
    assert "review" in areas.listed_areas(ELECTRICAL) and "review" in areas.listed_areas(AIT)
    assert "review" in areas.hidden_in(ELECTRICAL, quick=True)  # Quick mode lists three areas
    for role in ROLES:
        assert "act-go-review" not in areas.hidden_actions_in(role)


def test_the_page_shows_the_blocks_of_flatsat_w002_from_the_core_view(win) -> None:
    win.review_page_flow("W002")
    QApplication.processEvents()
    page = win.review_page
    assert win.area() == "review" and page.harness_id() == "W002"
    view = review.review_view(
        win.ctl.project, win.ctl.project.harnesses["W002"], win.ctl.findings()
    )
    assert page.view() == view  # the same function, the window's findings: nothing worked out twice
    for block in view.blocks:
        if block.key == "how":
            continue
        assert page.headings[block.key].text() == block.heading
        n = len(block.columns)
        shown = [tuple(r[i] for i in range(n) if i in r) for r in page.rows(block.key)]
        assert shown == [r.cells[:n] for r in block.rows]
    # section 4.4: no checklist, 18 findings, 3 of the whole project, 8 rows still open, 28 sources
    assert [len(page.rows(k)) for k in ("checklist", "findings", "project", "open", "sources")] == [0, 18, 3, 8, 28]  # fmt: skip
    assert page.empties["checklist"].isVisibleTo(page) and not page.tables["checklist"].isVisibleTo(page)  # fmt: skip
    assert page.empties["checklist"].text() == review.NO_CHECKLIST
    assert page.summary.text() == (
        "W002, version 1.0.0, draft: no checklist; 1 thing stops the release; 7 warnings and 11 "
        "notes open; 8 values still open"
    )
    assert page.release_line.text() == "Release: not released yet."
    assert [w.text() for w in page.how_lines] == list(review.HOW_LINES)
    assert page.harness.count() == len(win.ctl.project.harnesses)
    assert page.release_button.isEnabled()


def test_the_summary_counts_the_ticks_of_a_checklist() -> None:
    p = mini3()
    generate_project(p)
    apply_ops(p, configcheck.plan_set_checklist(p, POINTS).ops)
    view = review.review_view(p, p.harnesses["W001"], [])
    assert summary_text(view, frozenset({1, 3})).startswith(
        f"W001, version {view.version}, draft: 2 of 3 points ticked; "
    )
    # mini3 W001 has no gauge and no length yet: two open checks that stop the release
    assert summary_text(view, frozenset()).endswith(
        ": 0 of 3 points ticked; 2 things stop the release; no finding open; 10 values still open"
    )


def test_each_way_of_section_5_1_opens_the_page(win) -> None:
    page = win.review_page
    win.set_area("model")
    win.rail.buttons["review"].click()  # the rail
    assert win.area() == "review" and page.harness_id() is not None
    win.set_area("next")
    win.next_page._call("release")  # the Next step page: the first harness not released
    assert win.area() == "review" and page.harness_id() == "W001"
    assert strings.NEXT_RELEASE_BUTTON == "Open the Review page"
    win.go_to("releases")
    assert win.releases_panel.select_harness("W003")
    win.releases_panel.review_page.click()  # the Releases tab
    assert win.area() == "review" and page.harness_id() == "W003"
    menu = win.project_tree.build_menu("harness", "W004")  # the menu of a harness in the tree
    act = next(a for a in menu.actions() if a.objectName() == "tree-harness-review-page")
    act.trigger()
    assert win.area() == "review" and page.harness_id() == "W004"
    win.set_area("model")
    win.act_go_review.trigger()  # Go > Go to Review: the harness looked at, else the first open
    assert win.area() == "review" and page.harness_id() in win.ctl.project.harnesses
    assert strings.GO_REVIEW in {e.label for e in win.palette_entries()}  # Ctrl+K
    # the picker: another harness, shared with the Versions
    page.harness.setCurrentIndex(page.harness.findData("W005"))
    page.harness.activated.emit(page.harness.currentIndex())
    assert page.harness_id() == "W005" and win.releases_panel.current_harness() == "W005"


def test_show_explain_and_copy_link_and_no_browser(win, monkeypatch) -> None:
    opened: list[object] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url))
    shown: list[str] = []
    explained: list[tuple[str, str]] = []
    monkeypatch.setattr(win, "show_object", lambda oid: shown.append(oid))
    monkeypatch.setattr(
        win.checks_panel, "explain", lambda rule, oid: explained.append((rule, oid))
    )
    link = "https://example.com/parts/single"
    assert win.ctl.run(
        "Link", build_data.plan_set_part_link(win.ctl.project, "EX-WIRE-SINGLE", link)
    )
    win.review_page_flow("W002")
    page = win.review_page
    page.choose("findings", 0)
    first = page.rows("findings")[0]
    page.buttons["findings/show"].click()
    page.buttons["findings/explain"].click()
    assert shown == [first[3]] and explained == [(first[1], first[3])]
    page.choose("project", 0)
    page.buttons["project/explain"].click()
    assert explained[-1][0] == "unchecked-config"
    rows = page.rows("sources")
    k = next(i for i, r in enumerate(rows) if r["ref"] == "EX-WIRE-SINGLE")
    assert rows[k][5] == link and rows[k]["library"] == ""
    page.choose("sources", k)
    assert page.buttons["sources/copy"].isEnabled()
    page.buttons["sources/copy"].click()
    assert QApplication.clipboard().text() == link and opened == []
    page.choose("sources", 0)  # a device connector without a link: nothing to copy
    assert not page.buttons["sources/copy"].isEnabled()
    called: list[str] = []
    monkeypatch.setattr(win, "show_connector", lambda oid: called.append(oid))
    page.sourceRequested.disconnect()
    page.sourceRequested.connect(win.show_connector)
    page.buttons["sources/source_show"].click()
    assert called == [rows[0]["ref"]]


def test_waive_and_deviate_follow_the_chosen_finding(win, monkeypatch) -> None:
    got: list[object] = []
    monkeypatch.setattr(win, "waive_flow", lambda f: got.append(("waive", f.id)))
    page = win.review_page
    win.review_page_flow("W002")
    findings = {f.id: f for f in win.ctl.findings()}
    for i, row in enumerate(page.rows("findings")):
        page.choose("findings", i)
        f = findings[row[2]]
        assert page.buttons["findings/waive"].isEnabled() == (f.can_waive and f.waiver is None)
        assert page.buttons["findings/deviate"].isEnabled() == (f.can_deviate and f.waiver is None)
    i = next(i for i, r in enumerate(page.rows("findings")) if findings[r[2]].can_waive)
    page.choose("findings", i)
    page.waiveRequested.disconnect()
    page.waiveRequested.connect(lambda fid: win._review_finding(fid, win.waive_flow))
    page.buttons["findings/waive"].click()
    assert got == [("waive", page.rows("findings")[i][2])]


def test_the_open_values_go_to_their_place(win, monkeypatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(win, "values_flow", lambda: seen.append("values"))
    monkeypatch.setattr(win.checks_panel, "open_config", lambda f=None, k=None: seen.append(f"value {f}.{k}"))  # fmt: skip
    monkeypatch.setattr(win, "_go_to_harness", lambda hid: seen.append(f"harness {hid}"))
    win.review_page_flow("W002")
    page = win.review_page
    whats = [r[0] for r in page.rows("open")]
    page.choose("open", whats.index("Configuration files still placeholders"))
    assert not page.buttons["open/supply"].isEnabled()
    page.buttons["open/open_show"].click()
    page.choose("open", whats.index("Engineering values not set"))
    page.buttons["open/supply"].click()
    page.choose("open", whats.index("Wires without a gauge"))
    page.buttons["open/show_all"].click()
    first_value = page.rows("open")[whats.index("Engineering values not set")]["ref"]
    assert seen == ["values", f"value {first_value}", "harness W002"]


def test_the_library_column_says_the_state_of_each_device(win) -> None:
    class Info:
        def state(self, unit_id: str) -> LinkState | None:
            return LinkState(unit_id, unit_id, "library changed") if unit_id == "MTQ1" else None

    win.library_links.info = Info()
    win.review_page_flow("W002")
    rows = {r["ref"]: r["library"] for r in win.review_page.rows("sources") if r[0] == "Device connector"}  # fmt: skip
    assert rows["MTQ1-J02"] == strings.LINK_STATE_WORDS["library changed"] == "Library changed"
    assert rows["OBC1-J03"] == strings.RV_LIBRARY_NONE


def test_the_ticks_stay_on_this_computer_and_go_when_the_list_or_the_design_changes(qtbot, tmp_path, flatsat) -> None:  # fmt: skip
    win = _open(make_window(tmp_path), flatsat)
    qtbot.addWidget(win)
    set_points(win, POINTS)
    win.ctl.save()
    win.ctl.wait_journal()
    before = files_of(flatsat)
    win.review_page_flow("W002")
    page = win.review_page
    assert page.tables["checklist"].isVisibleTo(page) and len(page.rows("checklist")) == 3
    assert page.headings["checklist"].text().startswith("Checklist: 3 points (config/naming.json")
    tick(win, 1, 3)
    assert page.ticked() == frozenset({1, 3}) and "2 of 3 points ticked" in page.summary.text()
    key = win._review_key("W002")
    stored = json.loads(str(win.settings.value(key)))
    assert stored["list"] == review.list_hash(tuple(POINTS)) and stored["ticked"] == [1, 3]
    assert len(stored["design"]) == 12
    QApplication.processEvents()
    win.ctl.wait_journal()
    assert files_of(flatsat) == before  # never in the project: no file is written
    # another window on the same settings file keeps them (this computer)
    win.settings.sync()
    other = MainWindow(
        QSettings(win.settings.fileName(), QSettings.Format.IniFormat), ThemeManager()
    )
    other.ask_choice = win.ask_choice  # (no question waits for a click)
    qtbot.addWidget(other)
    win.ctl.release()  # (the first window lets the folder go)
    _open(other, flatsat)
    other.review_page_flow("W002")
    assert other.review_page.ticked() == frozenset({1, 3}) and other.review_ticked("W002") == frozenset({1, 3})  # fmt: skip
    assert not other.review_page.dropped.isVisibleTo(other.review_page)
    # the list changes: the ticks go, and the page says so
    set_points(other, [*POINTS, "A fourth point."])
    other._update_review()
    page = other.review_page
    assert page.ticked() == frozenset() and page.dropped.isVisibleTo(page)
    assert page.dropped.text() == strings.RV_DROPPED and other.review_ticked("W002") is None
    tick(other, 2)  # ticked again: the line goes
    assert not page.dropped.isVisibleTo(page) and other.review_ticked("W002") == frozenset({2})
    # the design changes (an edit that changes content_hash): the ticks go again
    p = other.ctl.project
    assert other.ctl.run("Link", build_data.plan_set_part_link(p, "EX-WIRE-SINGLE", "https://example.com/x"))  # fmt: skip
    other._update_review()
    assert page.ticked() == frozenset() and page.dropped.isVisibleTo(page)
    # Tick all and Clear
    page.buttons["checklist/tick_all"].click()
    assert other.review_ticked("W002") == frozenset({1, 2, 3, 4})
    page.buttons["checklist/clear"].click()
    assert other.review_ticked("W002") == frozenset()  # said: none ticked


def test_release_hands_the_ticks_to_the_dialog_which_shows_the_note(win, monkeypatch) -> None:
    set_points(win, POINTS)
    win.review_page_flow("W002")
    tick(win, 1, 3)
    script = DialogScript(win, accept=False)
    win.review_page.release_button.click()
    dlg = script.seen[-1]
    assert isinstance(dlg, ChangeDialog) and dlg.review_note.isVisibleTo(dlg)
    digest = review.list_hash(tuple(POINTS))
    dlg.by.setText("Ada")
    assert dlg.review_note.text() == (
        f"Added to the comment: [Review checklist (3 points, list {digest}), recorded by Ada: "
        f"ticked 1, 3; not ticked 2 (Pinouts agree with the ICD.)]"
    )
    assert dlg.review_note.text() == strings.RELEASE_REVIEW_NOTE.format(
        core_release.review_note(win.ctl.project, "Ada", frozenset({1, 3})).strip()
    )
    # OK hands them to plan_release
    seen: dict[str, object] = {}
    real = main_window.plan_release

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(main_window, "plan_release", spy)

    def answer(d) -> None:
        d.by.setText("Ada")
        d.comment.setPlainText("Released for the test of the ticks.")

    DialogScript(win, answer, accept=True)
    win.change_flow("release", "W002")
    assert seen["ticked"] == frozenset({1, 3})
    # Open the Review page from the dialog: it closes and the page opens
    win.set_area("model")
    DialogScript(win, lambda d: d.open_review.click(), accept=False)
    win.change_flow("release", "W003")
    assert win.area() == "review" and win.review_page.harness_id() == "W003"


def test_a_project_without_a_checklist_releases_as_before(win) -> None:
    script = DialogScript(win, accept=False)
    win.change_flow("release", "W002")
    dlg = script.seen[-1]
    assert not dlg.review_note.isVisibleTo(dlg) and not dlg.open_review.isVisibleTo(dlg)
    assert win.review_ticked("W002") is None


def test_a_released_harness_shows_its_release_and_no_tick_boxes(qtbot, tmp_path) -> None:
    p = _release_history(tmp_path)
    apply_ops(p, configcheck.plan_set_checklist(p, POINTS).ops)
    save_project(p, tmp_path / "released")
    win = _open(make_window(tmp_path), tmp_path / "released")
    qtbot.addWidget(win)
    win.review_page_flow("W001")
    page = win.review_page
    assert page.release_line.text().startswith(
        "Release: version 2.0.0 released on 2026-04-02 by Ada"
    )
    assert not page.release_button.isEnabled()
    assert page.release_button.toolTip() == strings.RV_RELEASE_OFF_RELEASED.format("W001")
    model = page.models["checklist"]
    assert not (model.flags(model.index(0, 2)) & Qt.ItemFlag.ItemIsUserCheckable)
    assert model.data(model.index(0, 2), Qt.ItemDataRole.CheckStateRole) is None
    assert not page.buttons["checklist/tick_all"].isVisibleTo(page)
    assert page.released.isVisibleTo(page) and "checklist of 3 points" in page.summary.text()


def test_the_running_check_is_said(win, monkeypatch) -> None:
    monkeypatch.setattr(win.ctl, "drc_busy", lambda: True)
    win.review_page_flow("W002")
    assert win.review_page.running.isVisibleTo(win.review_page)
    assert win.review_page.running.text() == strings.RV_RUNNING
    monkeypatch.setattr(win.ctl, "drc_busy", lambda: False)
    win._update_review()
    assert not win.review_page.running.isVisibleTo(win.review_page)


def test_a_project_without_a_harness_says_so(qtbot, tmp_path) -> None:
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    win.ctl.new_project(tmp_path / "blank", "Blank")
    QApplication.processEvents()
    win.review_page_flow()
    page = win.review_page
    assert win.area() == "review" and page.harness_id() is None
    assert page.none.isVisibleTo(page) and not page.body.isVisibleTo(page)
    assert not page.release_button.isEnabled()


def test_every_role_opens_the_page_and_the_systems_engineer_from_the_next_step_page(win) -> None:
    for role in ROLES:
        win.set_role(role)
        win.set_area("next")
        QApplication.processEvents()
        listed = win.rail.buttons["review"].isVisibleTo(win.rail)
        assert listed == (role != SYSTEMS), role
        win.next_page._call("release")
        assert win.area() == "review" and win.rail.buttons["review"].isVisibleTo(win.rail)
        go = next(a for a in win.findChildren(QAction) if a.objectName() == "act-go-review")
        assert go in win.menu_go.actions() and go.isVisible() and go.isEnabled()


# ---- Settings > Project: the review checklist (part A) and the label format (part F) ----------


def test_the_checklist_section_takes_the_template_a_file_and_saves_as_one_undo_step(win, tmp_path) -> None:  # fmt: skip
    page = win.settings_page
    win.checklist_flow()  # Edit the checklist… of the Review page
    assert win.area() == "settings" and page.current_section() == "project"
    assert page.checklist_box.toPlainText() == "" and page.checklist_state.text() == strings.SETTINGS_CHECKLIST_NONE  # fmt: skip
    page.checklist_template.click()
    assert page.checklist_points() == review.template_points() and len(page.checklist_points()) == 26  # fmt: skip
    assert review.points(win.ctl.project) == ()  # nothing is saved until Save
    assert strings.SETTINGS_CHECKLIST_EDITED in page.checklist_state.text()
    page.checklist_save.click()
    assert list(review.points(win.ctl.project)) == review.template_points()
    digest = review.list_hash(review.points(win.ctl.project))
    assert page.checklist_state.text() == strings.SETTINGS_CHECKLIST_NOW.format(26, digest)
    win.ctl.undo()
    QApplication.processEvents()
    win._show_segmentation()
    assert review.points(win.ctl.project) == () and page.checklist_box.toPlainText() == ""
    # a file: its list items
    f = tmp_path / "points.md"
    f.write_text("# Review\n\nProject: ____\n\n- [ ] One point.\n- [x] `Two` points.\n", encoding="utf-8")  # fmt: skip
    win.ask_open_path = lambda title, filters: str(f)
    page.checklist_file.click()
    assert page.checklist_points() == ["One point.", "Two points."]
    win.ask_open_path = lambda title, filters: str(tmp_path / "missing.md")
    page.checklist_file.click()
    assert page.checklist_error.isVisibleTo(page) and "is not a file" in page.checklist_error.text()
    # a refused list says why under the box, and nothing is saved
    page.checklist_box.setPlainText("Same point.\nsame point.")
    page.checklist_save.click()
    assert page.checklist_error.isVisibleTo(page)
    assert "review_checklist must be" in page.checklist_error.text()
    assert review.points(win.ctl.project) == ()
    # an empty box takes the list out
    set_points(win, POINTS)
    win._show_segmentation()
    assert page.checklist_points() == POINTS
    page.checklist_box.setPlainText("")
    page.checklist_save.click()
    assert review.points(win.ctl.project) == ()


def test_the_label_format_is_chosen_in_settings_as_one_undo_step(win) -> None:
    page = win.settings_page
    win.set_area("settings")
    page.show_section("project")
    combo = page.label_format_combo
    assert [combo.itemData(i) for i in range(combo.count())] == list(label_format.FORMATS)
    new = combo.findData(label_format.NEW_PROJECT_FORMAT)
    assert combo.itemText(new) == "harness_device_connector (a new project's choice)"
    assert combo.currentData() == label_format.format_of(win.ctl.project)
    combo.setCurrentIndex(combo.findData("compact"))
    assert label_format.format_of(win.ctl.project) == "compact"
    assert page.label_format_about.text() == f"Labels: {label_format.FORMAT_TEXT['compact']}."
    combo.setCurrentIndex(combo.findData("custom"))
    assert strings.SETTINGS_LABEL_FORMAT_CUSTOM in page.label_format_about.text()
    win.ctl.undo()
    win.ctl.undo()
    QApplication.processEvents()
    win._show_segmentation()
    assert combo.currentData() == label_format.format_of(win.ctl.project) != "compact"
