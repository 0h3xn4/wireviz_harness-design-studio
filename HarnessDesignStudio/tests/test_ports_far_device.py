# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Generate gives an interface the port named after its far device (REQ-PIN-08, 4.4.0, D-262;
`docs/ait/DESIGN_4.4_NAMES_PORTS.md` sections 2.1, 3.2, 3.3, 3.5 and 10, owner questions N3 and N4).

With `naming.far_device_names` on, an interface on a fixed pinout takes the port named after the
device at its other end first (step 0), keeps a port held before only when it names no other device
(step 2), and never takes a port named after another device (step 4, an error when nothing else is
left). The run of section 2.1 is the first test: OBC1-J01 with the ports TTC1 and TTC2, and IF-001
(OBC1 to TTC2) added before IF-002 (OBC1 to TTC1). At 4.3.0, and with the setting off, IF-001 gets
the pins named `TTC1_*`; with it on, the pins named `TTC2_*`. Every device name here is made up."""

import pytest

from harness_design_studio.core import configcheck, edit
from harness_design_studio.core.commands import History
from harness_design_studio.core.derive_layout import pin_allocation_derivation
from harness_design_studio.core.generate import pins
from harness_design_studio.core.generate.engine import generate_project, plan_generation
from harness_design_studio.core.model import (
    Connector,
    Endpoint,
    InterfaceInstance,
    Pin,
    Project,
    Unit,
    evolve,
)
from harness_design_studio.core.samples import start_project
from harness_design_studio.core.starter import starter_interface_types

RS422 = {t.id: t for t in starter_interface_types()}["rs422"]
SIGNALS = [s.name for s in RS422.signals]  # TX+ TX- RX+ RX-
OBC = "OBC1-J01"
UNITS = ("OBC1", "TTC1", "TTC2", "TTC3")


def named(*ports: str) -> list[tuple[str, str]]:
    """The fixed pins of the ports `ports`, four each, numbered from 1 (`TTC1_TX+` ...)."""
    names = [f"{port}_{sig}" for port in ports for sig in SIGNALS]
    return [(str(k + 1), name) for k, name in enumerate(names)]


def box(pins_: list[tuple[str, str]], cid: str = OBC, unit: str = "OBC1") -> Connector:
    return Connector(
        id=cid,
        name=cid.rsplit("-", 1)[-1],
        role="box",
        part_id="EX-MICROD-25-F",
        unit_id=unit,
        gender="female",
        carries=["rs422"],
        pins=[Pin(id=pid, signal=sig, fixed=True) for pid, sig in pins_],
    )


def project(
    links: list[tuple[str, str]], ports: tuple[str, ...] = ("TTC1", "TTC2"), on: bool = True
) -> Project:
    """OBC1 with OBC1-J01 (the fixed ports `ports`), the transceivers TTC1 to TTC3 with the bare
    names TX+ TX- RX+ RX- on their J01, and the RS-422 interfaces `links` (ID, far device), OBC1 to
    the far device. The segmentation of a new project (`per_connector_group`)."""
    p = start_project("Far device")
    for uid in UNITS:
        p.units[uid] = Unit(id=uid, name=f"Device {uid}", subsystem="avionics")
    p.connectors[OBC] = box(named(*ports))
    for uid in UNITS[1:]:
        p.connectors[f"{uid}-J01"] = box(
            [(str(k + 1), s) for k, s in enumerate(SIGNALS)], f"{uid}-J01", uid
        )
    for iid, far in links:
        p.interfaces[iid] = InterfaceInstance(
            id=iid,
            name=f"RS-422 OBC1 to {far}",
            type_id="rs422",
            endpoints=[
                Endpoint(unit_id="OBC1", connector_id=OBC),
                Endpoint(unit_id=far, connector_id=f"{far}-J01"),
            ],
        )
    if on:
        switch(p, True)
    return p


def switch(p: Project, on: bool) -> None:
    History(p).execute("far", configcheck.plan_set_far_device_names(p, on).ops)


def pins_of(p: Project, cid: str = OBC) -> dict[str, str]:
    """Pin name -> the interface on it."""
    return {x.signal or x.id: x.interface_id or "" for x in p.connectors[cid].pins}


def port_of(p: Project, iid: str, cid: str = OBC) -> set[str]:
    """The ports interface `iid` uses on the connector (the name before the last `_`)."""
    return {
        (x.signal or "").rsplit("_", 1)[0] for x in p.connectors[cid].pins if x.interface_id == iid
    }


def errors(plan: object) -> list[str]:
    return [f.message for f in plan.report.findings if f.severity == "error"]  # type: ignore[attr-defined]


# --- the run of section 2.1 --------------------------------------------------------------------


def test_the_run_of_2_1_at_4_3_0_gives_if_001_the_pins_named_for_ttc1() -> None:
    p = project([("IF-001", "TTC2"), ("IF-002", "TTC1")], on=False)
    plan = generate_project(p)
    assert not errors(plan)
    assert port_of(p, "IF-001") == {"TTC1"} and port_of(p, "IF-002") == {"TTC2"}
    assert "naming:far_device_names" not in (p.generation.provenance if p.generation else {})


@pytest.mark.parametrize(
    "links",
    [[("IF-001", "TTC2"), ("IF-002", "TTC1")], [("IF-001", "TTC1"), ("IF-002", "TTC2")]],
    ids=["ttc2-first", "ttc1-first"],
)
def test_the_setting_gives_each_interface_the_port_of_its_far_device(
    links: list[tuple[str, str]],
) -> None:
    p = project(links)
    plan = generate_project(p)
    assert not errors(plan)
    for iid, far in links:
        assert port_of(p, iid) == {far}
    assert p.generation is not None
    assert p.generation.provenance["naming:far_device_names"] == [
        "on: a port named after the unit at the other end first"
    ]


def test_the_reasons_name_the_far_device_and_a_second_generate_changes_nothing() -> None:
    p = project([("IF-001", "TTC2"), ("IF-002", "TTC1")])
    generate_project(p)
    assert p.generation is not None
    assert p.generation.provenance["pin:OBC1-J01.5"] == [
        "pin-allocation: TX+ of IF-001 uses pin 5, the TX+ of port TTC2 of OBC1-J01; the port named"
        " after unit TTC2 at the other end (naming.far_device_names)"
    ]
    again = plan_generation(p)
    assert not again.ops and not again.report.changed and not again.report.added


def test_on_moves_the_ports_off_keeps_them_and_on_again_keeps_them() -> None:
    p = project([("IF-001", "TTC2"), ("IF-002", "TTC1")], on=False)
    generate_project(p)
    assert port_of(p, "IF-001") == {"TTC1"}
    switch(p, True)
    plan = generate_project(p)
    assert plan.report.changed  # the ports move at the next Generate (step 0 before step 2)
    assert port_of(p, "IF-001") == {"TTC2"} and port_of(p, "IF-002") == {"TTC1"}
    switch(p, False)
    generate_project(p)  # step 2 keeps the ports, as a change of the fit does not move pins
    assert port_of(p, "IF-001") == {"TTC2"} and port_of(p, "IF-002") == {"TTC1"}
    assert "naming:far_device_names" not in (p.generation.provenance if p.generation else {})
    switch(p, True)
    generate_project(p)
    assert port_of(p, "IF-001") == {"TTC2"} and port_of(p, "IF-002") == {"TTC1"}


# --- the allocator ---------------------------------------------------------------------------


def run(
    pins_: list[tuple[str, str]],
    links: list[tuple[str, str]],
    previous: dict[tuple[str, str], str] | None = None,
    held: dict[tuple[str, str], str] | None = None,
) -> pins.Allocation:
    reqs = [pins.Request(iid, RS422, far) for iid, far in links]
    return pins.allocate(
        box(pins_), reqs, previous or {}, 0, held or {}, far_devices=True, units=UNITS
    )


def used(res: pins.Allocation, pins_: list[tuple[str, str]], iid: str) -> set[str]:
    name = dict(pins_)
    return {name[pid].rsplit("_", 1)[0] for (i, _sig), pid in res.pins.items() if i == iid}


def test_two_ports_of_one_device_are_taken_in_name_order() -> None:
    """N4: `TTC1_TM` and `TTC1_TC` are ports of TTC1; `TTC1_TC` comes first."""
    layout = named("TTC1_TM", "TTC1_TC", "TTC2")
    res = run(layout, [("IF-001", "TTC1"), ("IF-002", "TTC2"), ("IF-003", "TTC1")])
    assert not res.errors
    assert used(res, layout, "IF-001") == {"TTC1_TC"}
    assert used(res, layout, "IF-002") == {"TTC2"}
    assert used(res, layout, "IF-003") == {"TTC1_TM"}


def test_a_new_interface_does_not_move_another_off_the_port_it_held() -> None:
    """Step 0 gives back the port of the far device held before, then the first free one."""
    layout = named("TTC1_TC", "TTC1_TM")
    before = {("IF-002", sig): str(k + 1) for k, sig in enumerate(SIGNALS)}  # TTC1_TC
    res = run(layout, [("IF-001", "TTC1"), ("IF-002", "TTC1")], previous=before)
    assert used(res, layout, "IF-002") == {"TTC1_TC"}
    assert used(res, layout, "IF-001") == {"TTC1_TM"}


def test_a_second_interface_to_one_device_takes_a_port_that_names_no_device() -> None:
    layout = named("TTC1", "TTC2", "RS422_9")
    res = run(layout, [("IF-001", "TTC1"), ("IF-002", "TTC1")])
    assert not res.errors
    assert used(res, layout, "IF-001") == {"TTC1"} and used(res, layout, "IF-002") == {"RS422_9"}
    assert res.reasons["9"] == [
        "pin-allocation: TX+ of IF-002 uses pin 9, the TX+ of port RS422_9 of OBC1-J01; an interface"
        " keeps the port it used before, else takes the first free RS-422 port (ports in name"
        " order, interfaces in ID order)"
    ]


def test_an_interface_with_no_far_device_sees_every_port() -> None:
    layout = named("TTC1", "TTC2")
    res = run(layout, [("IF-001", "")])
    assert used(res, layout, "IF-001") == {"TTC1"}


def test_a_port_held_before_that_names_another_device_is_not_kept() -> None:
    layout = named("TTC1", "TTC2", "RS422_9")
    before = {("IF-001", sig): str(k + 1) for k, sig in enumerate(SIGNALS)}  # TTC1
    res = run(layout, [("IF-001", "TTC3")], previous=before)
    assert used(res, layout, "IF-001") == {"RS422_9"}


def test_a_port_held_before_that_names_no_device_is_kept() -> None:
    layout = named("RS422_1", "RS422_2")
    before = {("IF-001", sig): str(k + 5) for k, sig in enumerate(SIGNALS)}  # RS422_2
    res = run(layout, [("IF-001", "TTC3")], previous=before)
    assert used(res, layout, "IF-001") == {"RS422_2"}


def test_a_lock_on_another_devices_port_wins() -> None:
    layout = named("TTC1", "TTC2")
    held = {("IF-001", "TX+"): "1"}  # a person locked TTC1_TX+ to the interface to TTC2
    c = box(layout)
    c = evolve(c, pins=[evolve(x, locked=True) if x.id == "1" else x for x in c.pins])
    res = pins.allocate(
        c, [pins.Request("IF-001", RS422, "TTC2")], {}, 0, held, far_devices=True, units=UNITS
    )
    assert not res.errors
    assert sorted(res.pins.values()) == ["1", "2", "3", "4"]


# --- the error of section 3.3 ----------------------------------------------------------------


def test_the_error_names_the_ports_named_after_other_devices() -> None:
    p = project([("IF-001", "TTC1"), ("IF-002", "TTC2"), ("IF-003", "TTC3")])
    plan = generate_project(p)
    assert errors(plan) == [
        "IF-003: OBC1-J01 has a fixed pinout and no free pin named TX+, TX-, RX+, RX-, and no free"
        " complete RS-422 port for unit TTC3 (port TTC1 is named after unit TTC1; port TTC2 is"
        " named after unit TTC2)."
    ]
    p = project([("IF-002", "TTC3")])
    assert errors(generate_project(p)) == [
        "IF-002: OBC1-J01 has a fixed pinout and no free pin named TX+, TX-, RX+, RX-, and no free"
        " complete RS-422 port for unit TTC3 (port TTC1 is named after unit TTC1; port TTC2 is"
        " named after unit TTC2)."
    ]


def test_the_error_says_when_the_devices_own_port_is_used() -> None:
    p = project([("IF-002", "TTC1"), ("IF-003", "TTC1")])
    found = [m for m in errors(generate_project(p)) if "OBC1-J01" in m]  # TTC1-J01 has one port
    assert found == [
        "IF-003: OBC1-J01 has a fixed pinout and no free pin named TX+, TX-, RX+, RX-, and no free"
        " complete RS-422 port for unit TTC1 (port TTC1 is used by IF-002; port TTC2 is named after"
        " unit TTC2)."
    ]


def test_without_ports_named_after_devices_the_error_is_the_one_of_4_3_0() -> None:
    layout = named("RS422_1")
    res = run(layout, [("IF-001", "TTC1"), ("IF-002", "TTC2")])
    assert res.errors == [
        (
            "IF-002",
            "OBC1-J01 has a fixed pinout and no free pin named TX+, TX-, RX+, RX-, and no free"
            " complete RS-422 port (port RS422_1 is used by IF-001)",
        )
    ]


# --- released harness, lock --------------------------------------------------------------------


def test_a_released_harness_keeps_the_port_of_another_device() -> None:
    p = project([("IF-001", "TTC2")], on=False)
    generate_project(p)
    assert port_of(p, "IF-001") == {"TTC1"}
    for hid in list(p.harnesses):
        p.harnesses[hid] = evolve(p.harnesses[hid], status="released", version="1.0.0")
    switch(p, True)
    plan = generate_project(p)
    assert not errors(plan)
    assert port_of(p, "IF-001") == {"TTC1"}  # frozen: a new version takes the port of TTC2


# --- the editor's dry run (section 3.5) --------------------------------------------------------


def test_the_room_of_a_connector_follows_the_far_device() -> None:
    p = project([("IF-001", "TTC1")])
    generate_project(p)
    room = edit.connector_room(p, OBC, "rs422", far_unit="TTC3")
    assert not room.ok
    assert room.why == (
        "OBC1-J01 cannot take another RS-422: its free RS-422 port TTC2 is named after another"
        " device"
    )
    fits = edit.connector_room(p, OBC, "rs422", far_unit="TTC2")
    assert fits.ok and fits.port == "TTC2"
    assert edit.free_ports(p, OBC, "rs422") == ("TTC2",)
    compat = edit.connector_compat(p, "rs422", OBC, far_unit="TTC3")
    assert not compat.ok and compat.why.endswith("is named after another device.")


def test_the_room_text_names_every_free_port_of_other_devices() -> None:
    p = project([("IF-001", "TTC1")], ports=("TTC1", "TTC2", "TTC3"))
    p.units["TTC4"] = Unit(id="TTC4", name="Device TTC4", subsystem="avionics")
    room = edit.connector_room(p, OBC, "rs422", far_unit="TTC4")
    assert room.why == (
        "OBC1-J01 cannot take another RS-422: its free RS-422 ports TTC2 and TTC3 are named after"
        " other devices"
    )


def test_the_room_is_the_one_of_4_3_0_with_the_setting_off() -> None:
    p = project([("IF-001", "TTC1")], on=False)
    room = edit.connector_room(p, OBC, "rs422", far_unit="TTC3")
    assert room.ok and room.port == "TTC2"


def two_connectors(on: bool) -> Project:
    """OBC1 with two free connectors: J01 with the port TTC1, J02 with the port TTC2."""
    p = project([], ports=("TTC1",), on=on)
    p.connectors["OBC1-J02"] = box(named("TTC2"), "OBC1-J02")
    return p


@pytest.mark.parametrize("on, chosen", [(True, "OBC1-J02"), (False, OBC)], ids=["on", "off"])
def test_guided_mode_goes_on_to_the_connector_of_the_far_device(on: bool, chosen: str) -> None:
    p = two_connectors(on)
    ops, iid = edit.ops_add_interface(p, "rs422", "OBC1", "TTC2")
    History(p).execute("add", ops)
    assert p.interfaces[iid].endpoints[0].connector_id == chosen
    assert edit.choose_connector(p, "OBC1", "rs422", far_unit="TTC1") is not None


def test_guided_mode_shares_a_connector_on_the_port_of_the_far_device() -> None:
    p = project([("IF-001", "TTC1")])
    p.connectors["OBC1-J02"] = box(named("TTC3"), "OBC1-J02")
    p.interfaces["IF-009"] = InterfaceInstance(
        id="IF-009",
        name="RS-422 OBC1 to TTC3",
        type_id="rs422",
        endpoints=[
            Endpoint(unit_id="OBC1", connector_id="OBC1-J02"),
            Endpoint(unit_id="TTC3", connector_id="TTC3-J01"),
        ],
    )
    assert [c.id for c in edit.shared_connectors(p, "OBC1", "rs422", "TTC2")] == [OBC]
    assert edit.shared_connectors(p, "OBC1", "rs422", "TTC3") == []
    pick = edit.choose_connector(p, "OBC1", "rs422", far_unit="TTC2")
    assert pick is not None and pick.id == OBC


# --- explain ---------------------------------------------------------------------------------


def test_explain_names_the_far_device_only_while_the_setting_is_on() -> None:
    p = project([("IF-001", "TTC2"), ("IF-002", "TTC1")])
    generate_project(p)
    d = pin_allocation_derivation(p, OBC, "5")
    step = next(s for s in d.steps if s.label == "Port of the pin")
    assert step.expression == (
        "TTC2_TX+ is the TX+ of port TTC2 of OBC1-J01; the port named after TTC2, the device at the"
        " other end of IF-001, comes first (naming.far_device_names), then ports in name order,"
        " interfaces in ID order"
    )
    assert ("Signal names name the far device", "yes", "config/naming.json: far_device_names") in {
        (x.name, x.value, x.source) for x in d.inputs
    }
    assert "A-FAR-DEVICE" in d.assumptions
    switch(p, False)
    d = pin_allocation_derivation(p, OBC, "5")
    step = next(s for s in d.steps if s.label == "Port of the pin")
    assert step.expression.endswith(
        "the pins of one port go to one interface (ports in name order, interfaces in ID order)"
    )
    assert all(x.name != "Signal names name the far device" for x in d.inputs)
    assert "A-FAR-DEVICE" not in d.assumptions
