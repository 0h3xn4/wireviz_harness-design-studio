# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The note `isolated` and a harness drawn by hand (part E of the design of 5.1.0,
`docs/ait/DESIGN_5.1_FEATURE_TEMPLATES.md` sections 8 and 15, item 1; owner question T8).

A device that a harness drawn by hand plugs into is connected: the note must not say *not connected
to anything yet* and *will not appear in any harness plan* of a device that is in one. A device
joined by a cable with a loose end, or by a connection, is connected too; a device with nothing is
still `isolated`, with the words of before.
"""

from harness_design_studio.core import checks, devices, links, manual_harness, wires
from harness_design_studio.core.commands import History
from harness_design_studio.core.derive import explain_finding
from harness_design_studio.core.model import Project
from harness_design_studio.core.samples import start_project

DEVICES = ("PCDU1", "OBC1", "TTC1")


def _project() -> tuple[Project, History, dict[str, str]]:
    """Three devices, each with one connector whose pins 1 and 2 are PWR and RTN; no interface."""
    p = start_project("Isolated (example)")
    history = History(p)
    boxes = {}
    for k, uid in enumerate(DEVICES):
        ops, _ = devices.ops_add_device(p, unit_id=uid, x=100.0 * k, y=40.0)
        history.execute("device", ops)
        ops, cid = devices.ops_add_connector(p, uid, part_id="EX-MICROD-9-F")
        history.execute("connector", ops)
        rows = [{"pin": "1", "signal": "PWR"}, {"pin": "2", "signal": "RTN"}]
        history.execute("pins", devices.ops_paste_rows(p, cid, rows))
        boxes[uid] = cid
    return p, history, boxes


def isolated(p: Project) -> set[str]:
    return {f.object_id for f in checks.find(p) if f.rule == "isolated"}


def test_a_device_with_nothing_is_isolated_with_the_words_of_before() -> None:
    p, _history, _boxes = _project()
    assert isolated(p) == set(DEVICES)
    f = next(f for f in checks.find(p) if f.rule == "isolated" and f.object_id == "TTC1")
    assert f.title == "TTC1 is not connected to anything yet"
    assert f.why == (
        "Units without interfaces get no wires, so they will not appear in any harness plan."
    )
    assert checks.todos(p)[0].text == "3 devices are not connected to anything"


def test_devices_joined_only_by_a_harness_drawn_by_hand_are_not_isolated() -> None:
    p, history, boxes = _project()
    ops, hid = manual_harness.plan_new_harness(p, "Power")
    history.execute("harness", ops)
    plugs = []
    for uid in ("PCDU1", "OBC1"):
        ops, cid = manual_harness.plan_add_connector(p, hid, mates_with=boxes[uid])
        history.execute("plug", ops)
        plugs.append(cid)
    history.execute("wire", wires.plan_add_wire(p, hid, plugs[0], "1", plugs[1], "1"))
    assert isolated(p) == {"TTC1"}  # the regression: PCDU1 and OBC1 were named before part E
    assert [t.text for t in checks.todos(p)][0] == "1 device is not connected to anything"


def test_a_plug_without_wires_already_joins_its_device() -> None:
    """The harness plan shows the plug and the device it plugs into, wired or not."""
    p, history, boxes = _project()
    ops, hid = manual_harness.plan_new_harness(p, "Power")
    history.execute("harness", ops)
    ops, _cid = manual_harness.plan_add_connector(p, hid, mates_with=boxes["OBC1"])
    history.execute("plug", ops)
    assert isolated(p) == {"PCDU1", "TTC1"}


def test_a_device_joined_by_a_cable_with_a_loose_end_is_not_isolated() -> None:
    p, history, boxes = _project()
    made = manual_harness.plan_cable_from_port(p, boxes["OBC1"], name="Bench cable")
    history.execute("cable", made.ops)
    assert isolated(p) == {"PCDU1", "TTC1"}


def test_devices_joined_by_a_connection_are_not_isolated() -> None:
    p, history, boxes = _project()
    ops, _lid = links.plan_add_link(p, boxes["PCDU1"], boxes["TTC1"])
    history.execute("link", ops)
    assert isolated(p) == {"OBC1"}


def test_the_explanation_of_the_note_names_the_harnesses_it_looked_at() -> None:
    p, _history, _boxes = _project()
    found = explain_finding(p, "isolated", "TTC1")
    names = [i.name for d in found for i in d.inputs]
    assert "Harnesses that plug into the device" in names, names
