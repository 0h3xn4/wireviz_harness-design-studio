# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""*Unassign from interface* on a fixed pin (part E and pull request 1 of
`docs/ait/DESIGN_4.4_NAMES_PORTS.md`, owner question N12): `devices.ops_unassign_pins` keeps the
signal of a fixed pin, which is the device's own name, and clears only its interface and its
lock; a pin that is not fixed is freed as before. With it, the swap of two ports by hand of
section 2.7 works: *Unassign* pins 5 to 8, *Choose port…* TTC2 for IF-001, Generate. Example data
only."""

import pytest

from harness_design_studio.core import devices
from harness_design_studio.core.commands import History, Op
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.integrity import check_integrity
from harness_design_studio.core.issues import errors
from harness_design_studio.core.model import (
    Connector,
    Endpoint,
    InterfaceInstance,
    Pin,
    Project,
    Unit,
)
from harness_design_studio.core.ports import ports_of
from harness_design_studio.core.samples import new_project
from harness_design_studio.core.verify import verify_project

J01 = "OBC1-J01"
SIGNALS = ("TX+", "TX-", "RX+", "RX-")
PORT_PINS = {"TTC1": ["1", "2", "3", "4"], "TTC2": ["5", "6", "7", "8"]}


def obc_ttc() -> Project:
    """Section 2.1 of the design: OBC1-J01 with the fixed pins TTC1_TX+ ... TTC2_RX- (pins 1 to 8),
    TTC1 and TTC2 with one connector of the bare names each, and two RS-422 interfaces through the
    core, first OBC1 to TTC2 (IF-001), then OBC1 to TTC1 (IF-002)."""
    p = new_project("unassign a fixed pin (example data)")
    p.units["OBC1"] = Unit(id="OBC1", name="On-board computer", subsystem="avionics")
    names = [f"{port}_{s}" for port in ("TTC1", "TTC2") for s in SIGNALS]
    p.connectors[J01] = Connector(
        id=J01, name="J01", role="box", part_id="EX-MICROD-25-F", unit_id="OBC1",
        gender="female", carries=["rs422"],
        pins=[Pin(id=str(k + 1), signal=s, fixed=True) for k, s in enumerate(names)],
    )  # fmt: skip
    for uid in ("TTC1", "TTC2"):
        p.units[uid] = Unit(id=uid, name=f"Transceiver {uid[-1]}", subsystem="comms")
        p.connectors[f"{uid}-J01"] = Connector(
            id=f"{uid}-J01", name="J01", role="box", part_id="EX-MICROD-9-M", unit_id=uid,
            gender="male", carries=["rs422"],
            pins=[Pin(id=str(k + 1), signal=s, fixed=True) for k, s in enumerate(SIGNALS)],
        )  # fmt: skip
    for iid, far in (("IF-001", "TTC2"), ("IF-002", "TTC1")):
        p.interfaces[iid] = InterfaceInstance(
            id=iid, name=f"RS-422 OBC1 to {far}", type_id="rs422", redundancy="nominal",
            flow="bidirectional",
            endpoints=[Endpoint(unit_id="OBC1", connector_id=J01),
                       Endpoint(unit_id=far, connector_id=f"{far}-J01")],
        )  # fmt: skip
    return p


def run(p: Project, label: str, ops: list[Op]) -> History:
    h = History(p)
    h.execute(label, ops)
    assert errors(check_integrity(p)) == []
    return h


def rows(p: Project, cid: str = J01) -> list[tuple[str, str | None, str | None, bool, bool]]:
    return [(x.id, x.signal, x.interface_id, x.locked, x.fixed) for x in p.connectors[cid].pins]


def pins_of(p: Project, iid: str) -> list[str]:
    return [x.id for x in p.connectors[J01].pins if x.interface_id == iid]


def generated() -> Project:
    """The project after its first Generate: IF-001 (to TTC2) on the pins named for TTC1."""
    p = obc_ttc()
    plan = generate_project(p)
    assert not [f for f in plan.report.findings if f.severity == "error"]
    assert pins_of(p, "IF-001") == PORT_PINS["TTC1"]
    assert pins_of(p, "IF-002") == PORT_PINS["TTC2"]
    return p


def test_unassign_keeps_the_signal_of_a_fixed_pin_and_clears_its_interface_and_lock() -> None:
    p = generated()
    before = [x.model_copy() for x in p.connectors[J01].pins]
    h = run(p, "unassign", devices.ops_unassign_pins(p, J01, PORT_PINS["TTC2"]))
    assert rows(p)[4:] == [
        (str(k + 5), f"TTC2_{s}", None, False, True) for k, s in enumerate(SIGNALS)
    ]
    assert pins_of(p, "IF-001") == PORT_PINS["TTC1"]  # the other port is not touched
    # the port is whole again, so it is offered and free
    t = p.interface_types["rs422"]
    assert [x.name for x in ports_of(p.connectors[J01], t).usable] == ["TTC1", "TTC2"]
    h.undo()
    assert p.connectors[J01].pins == before


def test_unassign_clears_a_lock_and_keeps_the_name_of_a_port_chosen_by_hand() -> None:
    p = obc_ttc()
    run(p, "port", devices.ops_assign_port(p, J01, "TTC2", "IF-001"))
    assert rows(p)[4] == ("5", "TTC2_TX+", "IF-001", True, True)
    run(p, "unassign", devices.ops_unassign_pins(p, J01, ["5", "6"]))
    assert rows(p)[4:6] == [
        ("5", "TTC2_TX+", None, False, True),
        ("6", "TTC2_TX-", None, False, True),
    ]
    assert rows(p)[6] == ("7", "TTC2_RX+", "IF-001", True, True)  # a pin not selected stays


def test_a_pin_that_is_not_fixed_is_freed_as_before() -> None:
    p = obc_ttc()
    free = [Pin(id=str(k)) for k in range(1, 7)]
    p.connectors[J01] = p.connectors[J01].model_copy(update={"pins": free})
    run(p, "assign", devices.ops_assign_pins(p, J01, ["1", "2", "3", "4"], "IF-001"))
    assert rows(p)[0] == ("1", "TX+", "IF-001", True, False)
    run(p, "unassign", devices.ops_unassign_pins(p, J01, ["1", "2"]))
    assert p.connectors[J01].pins[:2] == [Pin(id="1"), Pin(id="2")]
    assert rows(p)[2] == ("3", "RX+", "IF-001", True, False)


def test_a_fixed_pin_without_an_interface_is_left_as_it_is() -> None:
    p = obc_ttc()
    assert devices.ops_unassign_pins(p, J01, ["1", "5"]) == []
    with pytest.raises(EditError, match="no pin 'Z'"):
        devices.ops_unassign_pins(p, J01, ["Z"])


def test_the_swap_of_two_ports_by_hand_then_generate() -> None:
    """Section 2.7: after the first Generate IF-001 (to TTC2) holds port TTC1. *Unassign* pins 5
    to 8, *Choose port…* TTC2 for IF-001, Generate: each interface is on the port of its device."""
    p = generated()
    run(p, "unassign", devices.ops_unassign_pins(p, J01, PORT_PINS["TTC2"]))
    run(p, "port", devices.ops_assign_port(p, J01, "TTC2", "IF-001"))
    plan = generate_project(p)
    assert not [f for f in plan.report.findings if f.severity == "error"]
    assert pins_of(p, "IF-001") == PORT_PINS["TTC2"]
    assert pins_of(p, "IF-002") == PORT_PINS["TTC1"]
    names = [f"{port}_{s}" for port in ("TTC1", "TTC2") for s in SIGNALS]
    assert [x.signal for x in p.connectors[J01].pins] == names  # every name of the device stays
    assert all(x.locked for x in p.connectors[J01].pins[4:])
    assert verify_project(p).ok
