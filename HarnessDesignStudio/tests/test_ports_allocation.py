# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Pin assignment by ports on a fixed pinout (REQ-PIN-04, D-237; `docs/ait/DESIGN_2.1_PORTS.md`
section 4): one complete named port per interface, the exact names of 2.0.1 first, the port held
before kept, a lock that names a port wins, and repeated bare names give `pin_port_unknown`."""

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from harness_design_studio.core import drc
from harness_design_studio.core.derive_layout import pin_allocation_derivation
from harness_design_studio.core.generate import pins
from harness_design_studio.core.generate.engine import generate_project, plan_generation
from harness_design_studio.core.model import (
    Connector,
    Endpoint,
    InterfaceInstance,
    InterfaceType,
    Pin,
    Project,
    Unit,
    evolve,
)
from harness_design_studio.core.ports import natural_key, ports_of
from harness_design_studio.core.samples import new_project
from harness_design_studio.core.starter import starter_interface_types
from harness_design_studio.core.verify import verify_project
from tests.reference import pins_201

LIBRARY = {t.id: t for t in starter_interface_types()}
RS422 = LIBRARY["rs422"]
SIGNALS = [s.name for s in RS422.signals]  # TX+ TX- RX+ RX-
BOX = "OBC1-J1"


def box(
    named: list[tuple[str, str]], locked: dict[str, str] | None = None, cid: str = BOX
) -> Connector:
    """A device connector whose pins are all fixed: (pin, signal). `locked` maps a pin to the
    interface that a person locked it to."""
    locked = locked or {}
    return Connector(
        id=cid,
        name=cid.rsplit("-", 1)[-1],
        role="box",
        part_id="EX-MICROD-25-F",
        unit_id="OBC1",
        pins=[
            Pin(id=pid, signal=sig, fixed=True, locked=pid in locked, interface_id=locked.get(pid))
            for pid, sig in named
        ],
    )


def port(name: str, first: int, t: InterfaceType = RS422) -> list[tuple[str, str]]:
    """The pins of the named port `name` (`RS422_2_TX+` ...), numbered from `first`."""
    return [(str(first + k), f"{name}_{s.name}") for k, s in enumerate(t.signals)]


def bare(first: int, t: InterfaceType = RS422) -> list[tuple[str, str]]:
    return [(str(first + k), s.name) for k, s in enumerate(t.signals)]


def three_ports() -> list[tuple[str, str]]:
    return port("RS422_1", 1) + port("RS422_2", 5) + port("RS422_3", 9)


def requests(*ids: str, t: InterfaceType = RS422) -> list[pins.Request]:
    return [pins.Request(i, t) for i in ids]


def as_201(reqs: list[pins.Request]) -> list[pins_201.Request]:
    """The same requests for the allocator of 2.0.1 (its own `Request` class)."""
    return [pins_201.Request(r.interface_id, r.itype) for r in reqs]


def run(
    connector: Connector,
    reqs: list[pins.Request],
    previous: dict[tuple[str, str], str] | None = None,
    held: dict[tuple[str, str], str] | None = None,
) -> pins.Allocation:
    return pins.allocate(connector, reqs, previous or {}, 0, held or {})


def port_used(connector: Connector, res: pins.Allocation, iid: str) -> set[str]:
    """The names of the ports whose pins interface `iid` got ("" for bare pins)."""
    cp = ports_of(connector, RS422)
    of = {pp.pin_id: p.name for p in (*([cp.bare] if cp.bare else []), *cp.named) for pp in p.pins}
    return {of[pid] for (i, _sig), pid in res.pins.items() if i == iid}


# --- the allocator ---------------------------------------------------------------------------


def test_three_named_ports_go_to_three_interfaces_in_id_order() -> None:
    c = box(three_ports())
    res = run(c, requests("IF-003", "IF-001", "IF-002"))
    assert not res.errors and not res.port_warnings
    assert [port_used(c, res, f"IF-00{k}") for k in (1, 2, 3)] == [
        {"RS422_1"},
        {"RS422_2"},
        {"RS422_3"},
    ]
    assert res.pins[("IF-002", "TX+")] == "5" and res.pins[("IF-002", "RX-")] == "8"


def test_ports_are_taken_in_natural_order_of_their_names() -> None:
    c = box(port("RS422_10", 1) + port("RS422_2", 5))
    res = run(c, requests("IF-001"))
    assert port_used(c, res, "IF-001") == {"RS422_2"}  # RS422_2 before RS422_10


def test_the_explanation_names_the_port_and_why() -> None:
    res = run(box(three_ports()), requests("IF-001", "IF-002"))
    assert res.reasons["5"] == [
        "pin-allocation: TX+ of IF-002 uses pin 5, the TX+ of port RS422_2 of OBC1-J1; an interface"
        " keeps the port it used before, else takes the first free RS-422 port (ports in name"
        " order, interfaces in ID order)"
    ]


def test_the_port_held_before_is_kept() -> None:
    c = box(three_ports())
    before = {("IF-001", s): str(9 + k) for k, s in enumerate(SIGNALS)}  # IF-001 had RS422_3
    res = run(c, requests("IF-001", "IF-002"), previous=before)
    assert port_used(c, res, "IF-001") == {"RS422_3"}
    assert port_used(c, res, "IF-002") == {"RS422_1"}
    assert res.reasons["9"] == [  # the same words as a port given by the order: no churn
        "pin-allocation: TX+ of IF-001 uses pin 9, the TX+ of port RS422_3 of OBC1-J1; an interface"
        " keeps the port it used before, else takes the first free RS-422 port (ports in name"
        " order, interfaces in ID order)"
    ]


def test_a_port_held_before_and_taken_by_a_lock_is_not_kept() -> None:
    c = box(three_ports(), locked={"9": "IF-002"})
    before = {("IF-001", s): str(9 + k) for k, s in enumerate(SIGNALS)}
    res = run(c, requests("IF-001", "IF-002"), previous=before, held={("IF-002", "TX+"): "9"})
    assert port_used(c, res, "IF-002") == {"RS422_3"}
    assert port_used(c, res, "IF-001") == {"RS422_1"}


def test_a_lock_overrides_the_default_order() -> None:
    c = box(three_ports(), locked={"9": "IF-001", "10": "IF-001", "11": "IF-001", "12": "IF-001"})
    held = {("IF-001", s): str(9 + k) for k, s in enumerate(SIGNALS)}
    res = run(c, requests("IF-001", "IF-002", "IF-003"), held=held)
    assert not res.errors
    assert [port_used(c, res, f"IF-00{k}") for k in (1, 2, 3)] == [
        {"RS422_3"},
        {"RS422_1"},
        {"RS422_2"},
    ]


def test_a_partial_lock_pins_the_port() -> None:
    c = box(three_ports(), locked={"10": "IF-001"})  # TX- of RS422_3 only
    res = run(c, requests("IF-001", "IF-002"), held={("IF-001", "TX-"): "10"})
    assert not res.errors
    assert {res.pins[("IF-001", s)] for s in SIGNALS} == {"9", "10", "11", "12"}
    assert res.reasons["9"] == [
        "pin-allocation: TX+ of IF-001 uses pin 9, the TX+ of port RS422_3 of OBC1-J1, the port its"
        " locked pins are in"
    ]
    assert res.reasons["10"] == [
        "pin-allocation: TX- of IF-001 stays on pin 10 because the pin is locked"
    ]
    assert port_used(c, res, "IF-002") == {"RS422_1"}


def test_a_locked_port_without_a_free_pin_fails_and_never_mixes() -> None:
    c = box(three_ports(), locked={"10": "IF-001", "12": "IF-002"})
    held = {("IF-001", "TX-"): "10", ("IF-002", "RX-"): "12"}
    res = run(c, requests("IF-001", "IF-002"), held=held)
    assert res.errors == [
        (
            "IF-001",
            "the locked pins of IF-001 on OBC1-J1 are in port RS422_3, which has no free pin for"
            " RX-; the pins of two ports are never mixed",
        ),
        (
            "IF-002",
            "the locked pins of IF-002 on OBC1-J1 are in port RS422_3, which has no free pin for"
            " TX-; the pins of two ports are never mixed",
        ),
    ]
    assert all(pid in ("10", "12") for pid in res.pins.values())  # only the locked pins


def test_locked_pins_in_two_ports_are_an_error() -> None:
    c = box(three_ports(), locked={"1": "IF-001", "6": "IF-001"})
    res = run(c, requests("IF-001"), held={("IF-001", "TX+"): "1", ("IF-001", "TX-"): "6"})
    assert res.errors == [
        (
            "IF-001",
            "the locked pins of IF-001 on OBC1-J1 are in 2 ports (RS422_1, RS422_2); an interface"
            " uses the pins of one port only, so unlock the pins of all ports but one",
        )
    ]


def test_the_exact_names_come_first_and_keep_the_text_of_2_0_1() -> None:
    c = box(bare(1) + port("RS422_1", 5))
    reqs = requests("IF-001", "IF-002")
    res = run(c, reqs)
    old = pins_201.allocate(c, as_201(reqs), {}, 0, {})
    assert port_used(c, res, "IF-001") == {""}  # the bare names, as at 2.0.1
    assert {k: v for k, v in res.pins.items() if k[0] == "IF-001"} == old.pins
    assert res.reasons["1"] == old.reasons["1"]
    assert port_used(c, res, "IF-002") == {"RS422_1"}  # 2.0.1: no free pin named TX+ ...
    assert old.errors == [
        ("IF-002", "OBC1-J1 has a fixed pinout and no free pin named TX+, TX-, RX+, RX-")
    ]


def test_an_incomplete_port_is_not_used_and_the_message_says_what_is_missing() -> None:
    c = box(port("RS422_1", 1) + port("RS422_2", 5)[:3])  # RS422_2 has no RX-
    res = run(c, requests("IF-001", "IF-002"))
    assert port_used(c, res, "IF-001") == {"RS422_1"}
    assert res.errors == [
        (
            "IF-002",
            "OBC1-J1 has a fixed pinout and no free pin named TX+, TX-, RX+, RX-, and no free"
            " complete RS-422 port (port RS422_1 is used by IF-001; port RS422_2 has no pin for"
            " RX-)",
        )
    ]
    assert not any(k[0] == "IF-002" for k in res.pins)


def test_repeated_bare_names_keep_the_assignment_of_2_0_1_and_warn() -> None:
    c = box(bare(1) + bare(5))  # TX+ TX- RX+ RX- twice: which pins form one port is not known
    reqs = requests("IF-002", "IF-001")
    res = run(c, reqs)
    old = pins_201.allocate(c, as_201(reqs), {}, 0, {})
    assert (res.pins, res.reasons, res.errors, res.warnings) == (
        old.pins,
        old.reasons,
        old.errors,
        old.warnings,
    )
    assert res.port_warnings == [
        (
            "OBC1-J1",
            "OBC1-J1 has more than one pin named TX+, TX-, RX+, RX- for the RS-422 interfaces"
            " IF-001, IF-002: the tool cannot tell which pins form one port, so each signal takes"
            " the first free pin of its name. Name the ports (P1_TX+, P2_TX+ ...) or lock the pins"
            " of each port",
        )
    ]


def test_one_interface_on_repeated_bare_names_gives_no_warning() -> None:
    res = run(box(bare(1) + bare(5)), requests("IF-001"))
    assert not res.port_warnings


@settings(max_examples=60, deadline=None)
@given(
    seed=st.integers(0, 2**32 - 1),
    n_ports=st.integers(1, 4),
    n_ifaces=st.integers(1, 4),
)
def test_every_interface_gets_the_pins_of_one_port_whatever_the_pin_order(
    seed: int, n_ports: int, n_ifaces: int
) -> None:
    rnd = random.Random(seed)
    names = rnd.sample(["RS422_1", "RS422_2", "RS422_10", "A", "B2", "port7"], n_ports)
    forms = {n: rnd.choice(["{p}_{s}", "{p}.{s}", "{s}-{p}", "{s}_{p}"]) for n in names}
    named = [(n, forms[n].format(p=n, s=s)) for n in names for s in SIGNALS]
    ids = rnd.sample(range(1, 200), len(named))
    order = list(zip(ids, named, strict=True))
    rnd.shuffle(order)
    c = box([(str(pid), sig) for pid, (_n, sig) in order])
    port_of = {str(pid): n for pid, (n, _sig) in order}
    iids = [f"IF-{k:03d}" for k in rnd.sample(range(1, 50), n_ifaces)]
    res = run(c, requests(*iids))
    got = {iid: {port_of[pid] for (i, _s), pid in res.pins.items() if i == iid} for iid in iids}
    assert all(len(ports) <= 1 for ports in got.values())  # never two ports
    placed = sorted(i for i in iids if got[i])
    assert placed == sorted(iids)[: min(n_ports, n_ifaces)]  # interfaces in ID order
    want = sorted(names, key=natural_key)
    assert [min(got[i]) for i in placed] == want[: len(placed)]  # ports in name order (one each)
    assert len(res.errors) == max(0, n_ifaces - n_ports)


# --- Generate ----------------------------------------------------------------------------------


def rs422x3(names: list[tuple[str, str]] | None = None) -> Project:
    """OBC1 with J1 = RS-422 x3 (a fixed pinout with the ports RS422_1 to RS422_3), three star
    trackers with a free 9-pin connector each, and IF-00k from OBC1-J1 to STRk-J1."""
    p = new_project("RS-422 x3")
    p.units["OBC1"] = Unit(id="OBC1", name="On-board computer", subsystem="avionics")
    p.connectors[BOX] = evolve(box(names or three_ports()), gender="female", carries=["rs422"])
    for k in (1, 2, 3):
        uid = f"STR{k}"
        p.units[uid] = Unit(id=uid, name=f"Star tracker {k}", subsystem="aocs")
        p.connectors[f"{uid}-J1"] = Connector(
            id=f"{uid}-J1", name="J1", role="box", part_id="EX-MICROD-9-M", unit_id=uid,
            gender="male", carries=["rs422"], pins=[Pin(id=str(n)) for n in range(1, 10)],
        )  # fmt: skip
        p.interfaces[f"IF-00{k}"] = InterfaceInstance(
            id=f"IF-00{k}", name=f"STR{k} data", type_id="rs422", redundancy="nominal",
            flow="bidirectional",
            endpoints=[Endpoint(unit_id="OBC1", connector_id=BOX),
                       Endpoint(unit_id=uid, connector_id=f"{uid}-J1")],
        )  # fmt: skip
    return p


def obc_ports(p: Project) -> dict[str, set[str]]:
    """The ports of OBC1-J1 each interface uses, read from the signal names of its pins."""
    out: dict[str, set[str]] = {}
    for pin in p.connectors[BOX].pins:
        if pin.interface_id and pin.signal:
            out.setdefault(pin.interface_id, set()).add(pin.signal.rsplit("_", 1)[0])
    return out


def test_generate_gives_port_k_to_if_k_and_the_checks_pass() -> None:
    p = rs422x3()
    plan = generate_project(p)
    assert not [f for f in plan.report.findings if f.severity == "error"]
    assert obc_ports(p) == {f"IF-00{k}": {f"RS422_{k}"} for k in (1, 2, 3)}
    assert all(pin.signal and pin.signal.startswith("RS422_") for pin in p.connectors[BOX].pins)
    assert verify_project(p).ok
    rules = {f.rule for f in drc.run(p)}
    assert "signal-unassigned" not in rules and "direction-conflict" not in rules


def test_a_second_generate_changes_nothing() -> None:
    p = rs422x3()
    generate_project(p)
    plan = plan_generation(p)
    assert not plan.ops
    assert plan.report.unchanged and not plan.report.changed and not plan.report.added


def test_generate_keeps_the_port_an_interface_used_before() -> None:
    p = rs422x3()
    generate_project(p)
    # a person moves IF-001 to RS422_3 by locking one pin, generates, then unlocks it
    locked = [
        evolve(x, locked=True, interface_id="IF-001") if x.id == "9" else x
        for x in p.connectors[BOX].pins
    ]
    p.connectors[BOX] = evolve(p.connectors[BOX], pins=locked)
    generate_project(p)
    assert obc_ports(p)["IF-001"] == {"RS422_3"}
    unlocked = [evolve(x, locked=False) for x in p.connectors[BOX].pins]
    p.connectors[BOX] = evolve(p.connectors[BOX], pins=unlocked)
    generate_project(p)
    # IF-002 kept RS422_2; IF-003 lost RS422_3 to the lock and took the first free port
    assert obc_ports(p) == {
        "IF-001": {"RS422_3"},
        "IF-002": {"RS422_2"},
        "IF-003": {"RS422_1"},
    }
    assert not plan_generation(p).ops  # and the next Generate keeps every port
    assert verify_project(p).ok


def test_the_explanation_of_a_pin_names_its_port() -> None:
    p = rs422x3()
    generate_project(p)
    d = pin_allocation_derivation(p, BOX, "5")
    steps = {s.label: s for s in d.steps}
    assert steps["Port of the pin"].expression == (
        "RS422_2_TX+ is the TX+ of port RS422_2 of OBC1-J1; the pins of one port go to one"
        " interface (ports in name order, interfaces in ID order)"
    )
    assert steps["Group of the signal"].expression == "TX+ of IF-002: pair TX on adjacent pins"
    recorded = [s.expression for s in d.steps if s.label == "Recorded when it was generated"]
    assert any("the first free RS-422 port" in r for r in recorded)


def test_generate_warns_pin_port_unknown_on_repeated_bare_names() -> None:
    p = rs422x3(bare(1) + bare(5) + bare(9))
    plan = generate_project(p)
    found = [f for f in plan.report.findings if f.code == "pin_port_unknown"]
    assert len(found) == 1 and found[0].object_id == BOX and found[0].severity == "warning"
    assert "IF-001, IF-002, IF-003" in found[0].message
    used = {x.id: x.interface_id for x in p.connectors[BOX].pins}
    assert used == {str(n): f"IF-00{(n - 1) // 4 + 1}" for n in range(1, 13)}  # as at 2.0.1


def test_a_project_that_fails_at_2_0_1_generates_now() -> None:
    p = rs422x3()
    reqs = requests("IF-001", "IF-002", "IF-003")
    old = pins_201.allocate(p.connectors[BOX], as_201(reqs), {}, 0, {})
    assert len(old.errors) == 3 and "no free pin named TX+" in old.errors[0][1]
    assert not run(p.connectors[BOX], reqs).errors
