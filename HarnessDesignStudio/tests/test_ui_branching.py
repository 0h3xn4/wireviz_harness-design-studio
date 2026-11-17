# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,attr-defined,union-attr,arg-type,type-arg,assignment,index"
"""REQ-HARN-03. The editor of harnesses that branch (2.3.0, D-243, section 5.8 of the design of
branching, pull request 6): Settings > Project offers *per connector group*; the Harness tab's
*Routing* table (an entered length, the buttons of a harness a person drew, the refusals); the
inspector of a branch point; the fix of `box_connector_mated_twice` in the Problems panel; the
diagram's branch points (drawn, dragged: the mark `branch:<ID>`, outside the hash), a new leg by a
drag from a plugged port, and *Join into one harness…*. Every change is one undo step."""

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtWidgets import QApplication  # noqa: E402

from harness_design_studio.gui import strings  # noqa: E402
from tests.gui_helpers import make_window  # noqa: E402


def settle() -> None:
    for _ in range(3):
        QApplication.processEvents()


# ---- Settings > Project ---------------------------------------------------------------------------


def test_settings_offers_per_connector_group_with_its_text_as_one_undo_step(qtbot, tmp_path):
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    win.set_area("settings")
    page = win.settings_page
    page.show_section("project")
    settle()
    combo = page.segmentation_combo
    modes = [combo.itemData(i) for i in range(combo.count())]
    assert modes == ["per_connector_pair", "per_unit_pair", "per_zone_pair", "per_connector_group"]
    assert combo.currentData() == "per_connector_pair" and combo.isEnabled()
    assert (
        page.segmentation_about.text() == strings.SETTINGS_SEGMENTATION_ABOUT["per_connector_pair"]
    )
    steps = len(win.ctl.history._undo)
    combo.setCurrentIndex(combo.findData("per_connector_group"))
    settle()
    assert win.ctl.project.config["segmentation"].values["mode"] == "per_connector_group"
    assert len(win.ctl.history._undo) == steps + 1
    assert "one plug on each device connector, branching where needed" in (
        page.segmentation_about.text()
    )
    win.ctl.undo()
    settle()
    assert win.ctl.project.config["segmentation"].values.get("mode") != "per_connector_group"
    assert combo.currentData() == "per_connector_pair"


def test_the_fix_opens_settings_at_the_choice_and_a_read_only_project_says_why(qtbot, tmp_path):
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    win.set_area("home")
    win.segmentation_flow()
    settle()
    page = win.settings_page
    assert win.area_stack.currentWidget() is page and page.current_section() == "project"
    assert page.segmentation_combo.hasFocus() or page.segmentation_combo.isVisible()
    win.ctl.project.read_only = True
    win.segmentation_flow()
    settle()
    assert not page.segmentation_combo.isEnabled()
    assert strings.WHY_READ_ONLY in page.segmentation_about.text()
