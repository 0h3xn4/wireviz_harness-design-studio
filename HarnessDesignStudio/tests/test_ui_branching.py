# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,attr-defined,union-attr,arg-type,type-arg,assignment,index,misc,func-returns-value"
"""REQ-HARN-03. The editor of harnesses that branch (2.3.0, D-243, section 5.8 of the design of
branching, pull request 6): Settings > Project offers *per connector group*; the Harness tab's
*Routing* table (an entered length, the buttons of a harness a person drew, the refusals); the
inspector of a branch point; the fix of `box_connector_mated_twice` in the Problems panel; the
diagram's branch points (drawn, dragged: the mark `branch:<ID>`, outside the hash), a new leg by a
drag from a plugged port, and *Join into one harness…*. Every change is one undo step."""

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from harness_design_studio.core.manual_harness import (  # noqa: E402
    plan_cable_from_port,
    plan_plug_loose_end,
)
from harness_design_studio.core.model import evolve  # noqa: E402
from harness_design_studio.core.wires import released_text  # noqa: E402
from harness_design_studio.gui import strings  # noqa: E402
from harness_design_studio.gui.routing_panel import SegmentDialog, shows_routing  # noqa: E402
from tests.gui_helpers import DialogScript, hold_drc, make_window, show_problems  # noqa: E402
from tests.test_branching import generated_mini3, labelled  # noqa: E402


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


# ---- the Harness tab's Routing --------------------------------------------------------------------


def window_with(tmp_path, project):
    win = make_window(tmp_path)
    win.ctl._install(project, None, None)
    settle()
    return win


def drawn(win, pins=("1", "2"), box="OBC-J01", far="RW1-J02"):
    """A cable drawn by hand from `box` plugged into `far` (W001 in a fresh project)."""
    ctl = win.ctl
    made = plan_cable_from_port(ctl.project, box, pin_ids=list(pins))
    assert ctl.run("cable", made.ops)
    pairs = [(x, x) for x in pins]
    ops = plan_plug_loose_end(ctl.project, made.harness_id, made.loose_id, far, pairs)
    assert ctl.run("plug", ops)
    return made.harness_id


def routing_of(win, hid):
    view = win.harness_view
    win.go_to("harness")
    assert view.select_harness(hid)
    view.refresh()
    settle()
    return view.routing


def steps(win) -> int:
    return len(win.ctl.history._undo)


def test_a_drawn_harness_gets_the_routing_buttons_and_each_is_one_undo_step(qtbot, tmp_path):
    win = window_with(tmp_path, labelled())
    qtbot.addWidget(win)
    hid = drawn(win)
    panel = routing_of(win, hid)
    assert panel.isVisible() and panel.note.text() == strings.RT_EMPTY
    assert not panel.table.isVisible()  # no segment yet: no table
    assert all(b.isVisible() for b in panel.buttons.values())
    assert not panel.buttons["rename"].isEnabled() and not panel.buttons["delete"].isEnabled()
    n = steps(win)
    panel.buttons["add_branch"].click()
    settle()
    h = win.ctl.project.harnesses[hid]
    assert [(b.id, b.name) for b in h.branch_points] == [("W001-B1", "Branch 1")]
    assert steps(win) == n + 1 and panel.picked() == ("branch", "W001-B1")
    assert panel.buttons["rename"].isEnabled()

    def fill(dlg):
        assert isinstance(dlg, SegmentDialog)
        dlg.a.setCurrentIndex(dlg.a.findData("W001-P1"))
        dlg.b.setCurrentIndex(dlg.b.findData("W001-B1"))
        dlg.length.setText("0,4")

    DialogScript(win, fill)
    done = panel.add_segment()
    assert done
    win.harness_view.refresh()
    h = win.ctl.project.harnesses[hid]
    assert [(s.id, s.from_node, s.to_node, s.length_m) for s in h.segments] == [
        ("W001-L1", "W001-P1", "W001-B1", 0.4)
    ]
    assert steps(win) == n + 2 and panel.table.isVisible()
    assert panel.model.rows()[0]["from"] == "W001-P1"
    # the length cell: one undo step, a refusal in the panel's error line
    assert panel.model.flags(panel.model.index(0, 3)) & Qt.ItemFlag.ItemIsEditable
    assert panel.model.data(panel.model.index(0, 3), Qt.ItemDataRole.EditRole) == "0.4"
    assert panel.model.setData(panel.model.index(0, 3), "1.25")
    assert win.ctl.project.harnesses[hid].segments[0].length_m == 1.25 and steps(win) == n + 3
    assert not panel.model.setData(panel.model.index(0, 3), "long")
    assert panel.error.isVisibleTo(panel) and "number of metres" in panel.error.text()
    # rename the branch point (the window's question), then delete the segment
    win.ask_text = lambda title, label, default: "Branch Y"
    panel.pick("branch", "W001-B1")
    done = panel.rename()
    assert done
    assert win.ctl.project.harnesses[hid].branch_points[0].name == "Branch Y"
    win.harness_view.refresh()
    panel.pick("segment", "W001-L1")
    done = panel.delete()
    assert done
    assert win.ctl.project.harnesses[hid].segments == [] and steps(win) == n + 5
    win.ctl.undo()
    assert len(win.ctl.project.harnesses[hid].segments) == 1


def test_a_segment_that_closes_a_loop_is_refused_in_the_dialog(qtbot, tmp_path):
    win = window_with(tmp_path, labelled())
    qtbot.addWidget(win)
    hid = drawn(win)
    panel = routing_of(win, hid)
    for a, b in (("W001-P1", "W001-P2"), ("W001-P2", "W001-P1")):

        def fill(dlg, a=a, b=b):
            dlg.a.setCurrentIndex(dlg.a.findData(a))
            dlg.b.setCurrentIndex(dlg.b.findData(b))

        DialogScript(win, fill)
        ok = panel.add_segment()
        win.harness_view.refresh()
    assert not ok and "close a loop" in panel.error.text()
    assert len(win.ctl.project.harnesses[hid].segments) == 1


def test_deleting_a_branch_point_on_a_wires_path_is_refused_with_the_wires(qtbot, tmp_path):
    from harness_design_studio.core import branching

    p = labelled()
    win = window_with(tmp_path, p)
    qtbot.addWidget(win)
    hid = drawn(win)
    leg = branching.plan_add_leg(win.ctl.project, hid, "OBC-J01")
    assert win.ctl.run("leg", leg.ops)
    panel = routing_of(win, hid)
    assert [r["id"] for r in panel.branch_model.rows()] == ["W001-B1"]
    assert "W001-L1 (no length)" in panel.branch_model.rows()[0]["segments"]
    panel.pick("branch", "W001-B1")
    n = steps(win)
    done = panel.delete()
    assert not done
    assert "on the only path of the wires" in panel.error.text() and steps(win) == n


def test_a_generated_harness_shows_kept_by_generate_and_only_the_length_changes(qtbot, tmp_path):
    win = window_with(tmp_path, generated_mini3())
    qtbot.addWidget(win)
    panel = routing_of(win, "W002")
    assert panel.isVisible() and panel.note.text() == strings.RT_KEPT_BY_GENERATE
    assert not any(b.isVisible() for b in panel.buttons.values())
    row = panel.model.rows()[0]
    assert (
        row["length_state"] == "pending" and panel.model.index(0, 3).data() == strings.RT_NO_LENGTH
    )
    assert panel.model.setData(panel.model.index(0, 3), "2")
    assert win.ctl.project.harnesses["W002"].segments[0].length_m == 2.0
    h = win.ctl.project.harnesses["W002"]
    assert not shows_routing(evolve(h, segments=[], branch_points=[]))  # nothing to show


def test_a_released_harness_is_read_only_with_the_reason(qtbot, tmp_path):
    p = generated_mini3()
    p.harnesses["W002"] = evolve(p.harnesses["W002"], status="released", revision="A")
    win = window_with(tmp_path, p)
    qtbot.addWidget(win)
    panel = routing_of(win, "W002")
    assert panel.note.text() == released_text(p.harnesses["W002"])
    assert not panel.model.flags(panel.model.index(0, 3)) & Qt.ItemFlag.ItemIsEditable


# ---- the inspector of a branch point --------------------------------------------------------------


def test_the_inspector_shows_a_branch_point_with_its_segments_and_lengths(qtbot, tmp_path):
    from harness_design_studio.core import branching
    from harness_design_studio.gui.inspector import facts_for

    win = window_with(tmp_path, labelled())
    qtbot.addWidget(win)
    hid = drawn(win)
    leg = branching.plan_add_leg(win.ctl.project, hid, "OBC-J01")
    assert win.ctl.run("leg", leg.ops)
    assert win.ctl.run(
        "length",
        branching.plan_set_segment_length(win.ctl.project, hid, "W001-L2", "0.8"),
    )
    rows = {r["name"]: r for r in facts_for(win.ctl.project, "branch_point", "W001-B1")}
    assert rows[strings.INS_FACT_LABELS["name"]]["value"] == "Branch 1"
    assert rows[strings.INS_BP_SEGMENTS]["value"] == "3"
    assert rows["W001-L2"]["value"] == "0.8 m"
    assert (
        rows["W001-L1"]["state"] == "pending" and rows["W001-L1"]["value"] == strings.RT_NO_LENGTH
    )
    assert "runs from W001-P1 to W001-B1" in rows["W001-L1"]["tip"]
    assert facts_for(win.ctl.project, "branch_point", "W009-B9") == []
    # a branch point chosen in the Routing table is what the inspector shows
    panel = routing_of(win, hid)
    win.dock_right.show()
    panel.pick("branch", "W001-B1")
    settle()
    assert win.inspector.current() == ("branch_point", "W001-B1")
    assert win.inspector.facts_title.text().endswith("W001-B1")


# ---- the Problems panel: the fix of a device connector with two plugs ----------------------------


def two_on_one(win):
    """W001 (OBC-J01 pins 1, 2 to RW1-J02) and W002 (OBC-J01 pins 3, 4 to a loose end)."""
    hid = drawn(win)
    other = plan_cable_from_port(win.ctl.project, "OBC-J01", pin_ids=["3", "4"])
    assert win.ctl.run("cable", other.ops)
    return hid, other.harness_id


def fix_button(win, name):
    from PySide6.QtWidgets import QPushButton

    win.ctl.run_drc_now()
    win.ctl.wait_drc()
    panel = show_problems(win)
    panel.refresh()
    settle()
    found = [b for b in panel.findChildren(QPushButton) if b.objectName() == name]
    return found[0] if found else None


def test_the_problems_fix_joins_two_drawn_harnesses_in_one_undo_step(qtbot, tmp_path):
    win = window_with(tmp_path, labelled())
    qtbot.addWidget(win)
    hold_drc(win)
    keep, other = two_on_one(win)
    button = fix_button(win, "fix-join")
    assert button is not None and button.text() == strings.FIX_JOIN
    assert fix_button(win, "fix-mode") is None
    n = steps(win)
    button.click()
    settle()
    assert sorted(win.ctl.project.harnesses) == [keep] and steps(win) == n + 1
    plugs = [c for c in win.ctl.project.harnesses[keep].connectors if c.mates_with == "OBC-J01"]
    assert len(plugs) == 1
    win.ctl.undo()
    assert sorted(win.ctl.project.harnesses) == [keep, other]


def test_the_problems_list_offers_the_same_fix_in_its_menu(qtbot, tmp_path):
    from harness_design_studio.gui.problems_panel import branch_fix

    win = window_with(tmp_path, labelled())
    qtbot.addWidget(win)
    hold_drc(win)
    keep, other = two_on_one(win)
    win.ctl.run_drc_now()
    win.ctl.wait_drc()
    found = [f for f in win.ctl.open_findings() if branch_fix(win.ctl.project, f) is not None]
    assert len(found) == 1 and found[0].object_id == "OBC-J01"
    plist = win.problems_list
    plist.refresh()
    row = next(r for r in plist.rows() if r["object_id"] == "OBC-J01" and r.get("fix"))
    assert row["fix"].kind == "join" and row["fix"].harness_ids == (keep, other)
    done = win.join_flow("OBC-J01")
    assert done
    assert sorted(win.ctl.project.harnesses) == [keep]


def test_generates_plugs_get_use_per_connector_group_which_opens_settings(qtbot, tmp_path):
    p = labelled()
    win = window_with(tmp_path, p)
    qtbot.addWidget(win)
    hold_drc(win)
    keep, other = two_on_one(win)
    for hid in (keep, other):  # (as if Generate had made them)
        win.ctl.project.harnesses[hid] = evolve(win.ctl.project.harnesses[hid], generated=True)
    assert fix_button(win, "fix-join") is None
    button = fix_button(win, "fix-mode")
    assert button is not None and button.text() == strings.FIX_MODE
    button.click()
    settle()
    assert win.area_stack.currentWidget() is win.settings_page
    assert win.settings_page.current_section() == "project"
    done = win.join_flow("OBC-J01")  # Generate's harnesses are not joined by hand
    assert not done


# ---- the diagram: a new leg by a drag, the branch point drawn and dragged, the join --------------


def plugged_cable(w):
    """W001: a cable drawn by hand from OBC-J01 (pins 1, 2) plugged into RW1-J02."""
    hid = drawn(w.win)
    w.settle()
    return hid


def messages(w) -> list[str]:
    said: list[str] = []
    w.win.ctl.message.connect(lambda text, _undo: said.append(text))
    return said


def test_a_cable_dragged_from_a_plugged_port_of_a_drawn_harness_is_a_new_leg(qtbot, tmp_path):
    from PySide6.QtCore import QPointF

    from harness_design_studio.core.cable_ends import branch_mark, pos_mark
    from harness_design_studio.core.io.layout import model_hash
    from tests.test_ui_tactile_connect import expert

    w = expert(tmp_path)
    hid = plugged_cable(w)
    n = w.steps()
    w.drag(w.grab_spot(w.port("OBC", "OBC-J01")), QPointF(420, 300))
    w.settle()
    assert sorted(w.project.harnesses) == [hid] and w.steps() == n + 1  # one undo step
    h = w.project.harnesses[hid]
    loose = [c.id for c in h.connectors if c.role == "loose"]
    assert loose == ["W001-P3"] and [b.id for b in h.branch_points] == ["W001-B1"]
    assert w.win.ctl.selected_end == "W001-P3"
    assert pos_mark("W001-P3") in w.project.diagram_marks  # where it was let go
    end = w.scene.end_items["W001-P3"]
    assert end.spot == pytest.approx((420, 300), abs=1.5)
    # the branch point is drawn at the middle of its connectors, and the lines run through it
    branch = w.scene.branch_items["W001-B1"]
    assert branch.isVisible()
    spots = [branch.connector_spot(c) for c in branch.spot.connectors]
    middle = (sum(x for x, _ in spots) / 3, sum(y for _, y in spots) / 3)
    assert branch.placed() == pytest.approx(middle)
    assert end.end.via == ("W001-B1",) and branch.placed() in [tuple(p) for p in end.points]
    # dragged, it writes the mark branch:<ID>, one undo step outside the model hash
    before = model_hash(w.project)
    at = QPointF(*branch.placed())
    n = w.steps()
    w.drag(at, at + QPointF(40, -30))
    w.settle()
    mark = w.project.diagram_marks[branch_mark("W001-B1")]
    assert (mark.dx, mark.dy) == pytest.approx((40, -30), abs=1.5) and w.steps() == n + 1
    assert model_hash(w.project) == before
    assert branch.placed() == pytest.approx((middle[0] + mark.dx, middle[1] + mark.dy))
    assert w.win.ctl.picked_branch == "W001-B1"
    assert w.win.inspector.current() == ("branch_point", "W001-B1")
    assert branch.placed() in [tuple(p) for p in w.scene.end_items["W001-P3"].points]
    w.win.ctl.undo()
    w.settle()
    assert branch_mark("W001-B1") not in w.project.diagram_marks
    assert branch.placed() == pytest.approx(middle)
    w.win.ctl.undo()  # the leg
    w.settle()
    assert "W001-B1" not in w.scene.branch_items and "W001-P3" not in w.scene.end_items


def test_a_port_with_a_harness_of_a_connection_still_refuses_a_second_cable(qtbot, tmp_path):
    from PySide6.QtCore import QPointF

    from tests.test_ui_tactile_connect import expert

    w = expert(tmp_path)
    lid = w.win.ctl.add_link("OBC-J01", "RW1-J02", [("1", "1"), ("2", "2")])
    assert w.win.ctl.create_harness_from_link(lid)
    w.settle()
    before = dict(w.project.harnesses)
    said = messages(w)
    w.drag(w.grab_spot(w.port("OBC", "OBC-J01")), QPointF(420, 300))
    w.settle()
    assert w.project.harnesses == before
    name = w.project.connectors["OBC-J01"].name
    assert said[-1] == strings.CABLE_REFUSED_PLUGGED.format(name=name)


def test_a_leg_with_no_free_pin_is_refused_with_the_reason(qtbot, tmp_path):
    from PySide6.QtCore import QPointF

    from tests.test_ui_tactile_connect import expert

    w = expert(tmp_path)
    drawn(w.win, pins=("1", "2", "3", "4"))
    w.settle()
    before, n = dict(w.project.harnesses), w.steps()
    said = messages(w)
    w.drag(w.grab_spot(w.port("OBC", "OBC-J01")), QPointF(420, 300))
    w.settle()
    assert w.project.harnesses == before and w.steps() == n
    assert "no free pin with a signal for a new leg" in said[-1]


def test_the_menu_of_a_shared_port_offers_join_into_one_harness(qtbot, tmp_path):
    from PySide6.QtCore import QPointF

    from tests.test_ui_tactile_connect import expert

    w = expert(tmp_path)
    hid = plugged_cable(w)
    other = plan_cable_from_port(w.project, "OBC-J01", pin_ids=["3", "4"])
    assert w.win.ctl.run("cable", other.ops)
    w.settle()
    menu = w.view.build_context_menu("unit", "OBC", QPointF(0, 0), connector="OBC-J01")
    entry = next(a for a in menu.actions() if a.objectName() == "diagram-menu-join")
    assert entry.text() == strings.JOIN_MENU and entry.isEnabled()
    asked = []
    w.win.ask_choice = lambda title, text, buttons: asked.append(buttons) or 0
    n = w.steps()
    entry.trigger()
    w.settle()
    assert asked == [[strings.JOIN_INTO.format(other=other.harness_id, keep=hid), strings.CANCEL]]
    assert sorted(w.project.harnesses) == [hid] and w.steps() == n + 1
    # the plugged end of the joined harness offers nothing more to join
    menu = w.view.build_context_menu("unit", "OBC", QPointF(0, 0), connector="OBC-J01")
    assert not [a for a in menu.actions() if a.objectName() == "diagram-menu-join"]


def test_the_menu_of_a_plugged_end_offers_the_join_and_cancel_changes_nothing(qtbot, tmp_path):
    from PySide6.QtCore import QPointF

    from tests.test_ui_tactile_connect import expert

    w = expert(tmp_path)
    hid = plugged_cable(w)
    other = plan_cable_from_port(w.project, "OBC-J01", pin_ids=["3", "4"])
    assert w.win.ctl.run("cable", other.ops)
    w.settle()
    plugged = next(i for i in w.scene.end_items.values() if not i.end.loose)
    menu = w.view.build_context_menu("cable_end", plugged.connector_id, QPointF(0, 0))
    entry = next(a for a in menu.actions() if a.objectName() == "diagram-menu-join")
    w.win.ask_choice = lambda title, text, buttons: len(buttons) - 1  # Cancel
    entry.trigger()
    assert sorted(w.project.harnesses) == sorted([hid, other.harness_id])
