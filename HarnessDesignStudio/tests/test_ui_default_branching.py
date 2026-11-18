# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,attr-defined,union-attr,arg-type,type-arg,assignment,index,misc,func-returns-value"
"""2.4.0 (D-247): the editor's New project starts in `per_connector_group` (the examples with
outputs keep their mode), and a project that keeps `per_connector_pair` while a device connector
has the plugs of several harnesses of Generate gets, after Generate, a one-time notice with the
button *Make one harness that branches* (one undo step, then the offer to Generate again). The
answer is remembered per project folder in the window's settings, never in the project."""

import json

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtWidgets import QApplication  # noqa: E402

from harness_design_studio.core.io.saver import save_project  # noqa: E402
from harness_design_studio.core.model import (  # noqa: E402
    Connector,
    Endpoint,
    InterfaceInstance,
    Pin,
    Unit,
)
from harness_design_studio.core.samples import new_project, start_project  # noqa: E402
from harness_design_studio.gui import strings  # noqa: E402
from tests.gui_helpers import DialogScript, hold_drc, make_window, new_project_answers  # noqa: E402
from tests.test_default_branching import MICRO_D, micro_d  # noqa: E402

GROUP = "per_connector_group"
PAIR = "per_connector_pair"


def settle() -> None:
    for _ in range(3):
        QApplication.processEvents()


def mode(win) -> object:
    return win.ctl.project.config["segmentation"].values.get("mode")


def on_disk(folder) -> object:
    return json.loads((folder / "config" / "segmentation.json").read_text())["values"]["mode"]


# ---- New project ----------------------------------------------------------------------------------


def test_the_new_project_dialog_starts_in_per_connector_group(qtbot, tmp_path):
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    new_project_answers(win, tmp_path / "blank", "Mine")
    win.new_project_flow()
    settle()
    assert mode(win) == GROUP and on_disk(tmp_path / "blank") == GROUP
    new_project_answers(win, tmp_path / "example", "Example", template="first-steps")
    win.new_project_flow()
    settle()
    assert mode(win) == PAIR and on_disk(tmp_path / "example") == PAIR  # an example keeps its mode


# ---- the notice after Generate ---------------------------------------------------------------------


def older_project(folder, *, shared: bool = True):
    """A project made before 2.4.0 (per_connector_pair), saved in `folder`: the Micro-D case, or
    two separate links with no shared connector."""
    p = new_project("older tool")
    if shared:
        micro_d(p)
    else:
        for u in ("A", "B", "C", "D"):
            p.units[u] = Unit(id=u, name=u, subsystem="s", side="nominal")
            p.connectors[f"{u}-J01"] = Connector(
                id=f"{u}-J01", name="J01", role="box", part_id="EX-MICROD-25-F", unit_id=u,
                gender="female", pins=[Pin(id=str(k + 1)) for k in range(25)],
            )  # fmt: skip
        for n, (a, b) in enumerate((("A", "B"), ("C", "D")), start=1):
            p.interfaces[f"IF-00{n}"] = InterfaceInstance(
                id=f"IF-00{n}", name=f"IF-00{n}", type_id="rs422",
                endpoints=[Endpoint(unit_id=a, connector_id=f"{a}-J01"), Endpoint(unit_id=b, connector_id=f"{b}-J01")],
            )  # fmt: skip
    save_project(p, folder)
    return folder


def opened(qtbot, tmp_path, folder):
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    hold_drc(win)
    assert win.open_project(folder)
    hold_drc(win)
    settle()
    DialogScript(win, accept=True)  # the Generate preview: OK
    return win


def generate(win) -> None:
    win.generate_flow()
    settle()


def test_the_notice_shows_once_for_an_older_project_with_a_shared_connector(qtbot, tmp_path):
    folder = older_project(tmp_path / "older")
    win = opened(qtbot, tmp_path, folder)
    assert not win.alerts.is_showing("branching")
    generate(win)
    assert sorted(win.ctl.project.harnesses) == ["W001", "W002", "W003"]
    assert win.alerts.is_showing("branching")
    banner = win.alerts.banner("branching")
    assert banner.label.text() == strings.BRANCH_NOTICE.format(
        boxes=MICRO_D, has="has", harnesses="W001, W002 and W003"
    )
    assert [b.text() for b in banner.buttons] == [strings.BRANCH_NOTICE_ACTION]
    assert mode(win) == PAIR  # nothing is switched without the person's choice
    banner.dismiss.click()
    settle()
    assert not win.alerts.is_showing("branching") and win.branching_notice_done()
    generate(win)  # nothing to change: the notice does not come back
    assert not win.alerts.is_showing("branching")
    assert mode(win) == PAIR and on_disk(folder) == PAIR  # no file of the project holds it
    win.ctl.release()  # (the folder's lock: the next window opens it)
    win.settings.sync()
    again = opened(qtbot, tmp_path, folder)  # another window on the same settings
    generate(again)
    assert len(again.ctl.project.harnesses) == 3  # the three plugs again, and no notice
    assert not again.alerts.is_showing("branching") and again.branching_notice_done()


def test_no_notice_without_a_shared_connector_or_in_per_connector_group(qtbot, tmp_path):
    win = opened(qtbot, tmp_path, older_project(tmp_path / "separate", shared=False))
    generate(win)
    assert len(win.ctl.project.harnesses) == 2
    assert not win.alerts.is_showing("branching") and not win.branching_notice_done()
    folder = tmp_path / "new"
    save_project(micro_d(start_project("new")), folder)  # the case in a new project
    win = opened(qtbot, tmp_path, folder)
    generate(win)
    assert list(win.ctl.project.harnesses) == ["W001"]  # one harness: nothing to offer
    assert not win.alerts.is_showing("branching") and not win.branching_notice_done()


def test_the_button_switches_the_mode_in_one_undo_step_and_offers_generate(qtbot, tmp_path):
    folder = older_project(tmp_path / "older")
    win = opened(qtbot, tmp_path, folder)
    generate(win)
    banner = win.alerts.banner("branching")
    steps = len(win.ctl.history._undo)
    banner.buttons[0].click()
    settle()
    assert mode(win) == GROUP and len(win.ctl.history._undo) == steps + 1
    assert win.branching_notice_done()
    assert win.alerts.is_showing("branching")
    assert banner.label.text() == strings.BRANCH_NOTICE_DONE
    assert [b.text() for b in banner.buttons] == [strings.BRANCH_NOTICE_GENERATE]
    win.ctl.undo()
    settle()
    assert mode(win) == PAIR  # one undo step puts it back
    win.ctl.redo()
    settle()
    assert mode(win) == GROUP
    banner.buttons[0].click()  # Generate again: one harness with one plug on the Micro-D
    settle()
    assert not win.alerts.is_showing("branching")
    h = win.ctl.project.harnesses
    assert list(h) == ["W001"]
    assert [c.mates_with for c in h["W001"].connectors].count(MICRO_D) == 1
    assert len(h["W001"].branch_points) == 1 and len(h["W001"].segments) == 4
