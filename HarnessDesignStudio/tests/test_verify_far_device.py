# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The independent verifier's check `port_far_device` (REQ-PIN-08, 4.4.0, D-262; design of 4.4.0
section 3.4, owner question N5): while `naming.far_device_names` is on, an interface whose pins are
in a port named after a device other than the one at its other end is an error when nobody locked
the pins (it reaches the DRC as `verify-mismatch` with the fix *Regenerate harnesses*), and a
warning when a person locked them or a released harness holds them (it does not reach the DRC).
With the setting off there is no such check. The project is the run of section 2.1, generated as
4.3.0 generates it."""

from harness_design_studio.core import drc
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.model import Project, evolve
from harness_design_studio.core.verify import verify_project
from tests.test_ports_far_device import OBC, port_of, project, switch

ERROR_001 = (
    "Interface IF-001 goes to unit TTC2 but uses port TTC1 of OBC1-J01, which is named after unit"
    " TTC1 (naming.far_device_names). Regenerate, or choose the port of TTC2."
)
FIRST = (
    "Interface IF-001 goes to unit TTC2 but uses port TTC1 of OBC1-J01, which is named after unit"
    " TTC1 (naming.far_device_names)."
)


def placed_by_4_3_0() -> Project:
    """The run of section 2.1 generated with the setting off: IF-001 (to TTC2) on port TTC1."""
    p = project([("IF-001", "TTC2"), ("IF-002", "TTC1")], on=False)
    generate_project(p)
    assert port_of(p, "IF-001") == {"TTC1"}
    return p


def found(p: Project, severity: str | None = None) -> list[str]:
    return [
        i.message
        for i in verify_project(p).issues
        if i.code == "port_far_device" and (severity is None or i.severity == severity)
    ]


def test_no_check_with_the_setting_off() -> None:
    p = placed_by_4_3_0()
    assert found(p) == [] and verify_project(p).ok


def test_an_unlocked_interface_on_another_devices_port_is_an_error() -> None:
    p = placed_by_4_3_0()
    switch(p, True)
    assert found(p, "error") == [
        ERROR_001,
        "Interface IF-002 goes to unit TTC1 but uses port TTC2 of OBC1-J01, which is named after"
        " unit TTC2 (naming.far_device_names). Regenerate, or choose the port of TTC1.",
    ]
    rows = [f for f in drc.run(p) if f.rule == "verify-mismatch" and f.title == ERROR_001]
    assert len(rows) == 1
    assert rows[0].severity == "error" and rows[0].fix_label == "Regenerate harnesses"
    generate_project(p)  # the fix: Generate gives each interface the port of its far device
    assert found(p) == [] and verify_project(p).ok


def test_locked_pins_on_another_devices_port_are_a_warning() -> None:
    p = placed_by_4_3_0()
    pins = [
        evolve(x, locked=True) if x.interface_id == "IF-001" else x for x in p.connectors[OBC].pins
    ]
    p.connectors[OBC] = evolve(p.connectors[OBC], pins=pins)
    switch(p, True)
    assert found(p, "warning")[0] == f"{FIRST} It is kept because a person locked the pins."
    assert ERROR_001 not in found(p, "error")
    assert not [f for f in drc.run(p) if FIRST in f.title]  # warnings do not reach the DRC


def test_a_released_harness_on_another_devices_port_is_a_warning() -> None:
    p = placed_by_4_3_0()
    (hid,) = sorted(p.harnesses)
    p.harnesses[hid] = evolve(p.harnesses[hid], status="released", version="1.0.0")
    switch(p, True)
    assert found(p, "error") == []
    assert found(p, "warning")[0] == (
        f"{FIRST} It is kept because harness {hid} is released; a new version takes the port of"
        " TTC2."
    )
    assert not [f for f in drc.run(p) if FIRST in f.title]


def test_ports_that_name_no_device_and_the_own_device_are_not_reported() -> None:
    p = project([("IF-001", "TTC2"), ("IF-002", "TTC1")], ports=("RS422_1", "RS422_2"))
    generate_project(p)
    assert found(p) == [] and verify_project(p).ok
    q = project([("IF-001", "TTC2"), ("IF-002", "TTC1")])
    generate_project(q)
    assert found(q) == [] and verify_project(q).ok
