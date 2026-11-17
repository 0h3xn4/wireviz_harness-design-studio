# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Several interfaces on one device connector in the editor core (D-237, pull request 4 of
`docs/ait/DESIGN_2.1_PORTS.md`): the room on a connector is a dry run of Generate's own pin
allocation, a full connector is refused with the reason, a shared connector carries notes, the
Guided choice has two tiers (the first exactly as before), the `no-connector` fix follows, and
`explain` lists every interface and the free ports of each candidate. Example data only."""

from pathlib import Path

import pytest

from harness_design_studio.core import checks, connector_choice, edit
from harness_design_studio.core.commands import History
from harness_design_studio.core.derive import render
from harness_design_studio.core.derive_layout import connector_choice_derivation
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import (
    ConfigFile,
    Connector,
    Endpoint,
    InterfaceInstance,
    Pin,
    Placement,
    Project,
    Unit,
    evolve,
)
from harness_design_studio.core.samples import mini3, new_project, sat15
from harness_design_studio.resources import examples_path

RS422 = ("TX+", "TX-", "RX+", "RX-")


def port_pins(*ports: str, start: int = 1) -> list[Pin]:
    """The fixed pins of the named RS-422 ports, numbered from `start`."""
    names = [f"{port}_{sig}" for port in ports for sig in RS422]
    return [Pin(id=str(start + k), signal=s, fixed=True) for k, s in enumerate(names)]


def obc(*connectors: tuple[str, list[Pin]], sensors: int = 3) -> Project:
    """A computer OBC1 with the given box connectors (all carry RS-422) and `sensors` star
    trackers ST1, ST2 ... from the template (each has ST<k>-J02, 15 free pins, RS-422 and RS-485)."""
    p = new_project("multi-interface connector (example data)")
    p.units["OBC1"] = Unit(id="OBC1", name="OBC", subsystem="avionics", side="nominal")
    p.placements["OBC1"] = Placement(id="OBC1", x=edit.lane_x(0), y=40)
    for name, pins in connectors:
        cid = f"OBC1-{name}"
        p.connectors[cid] = Connector(
            id=cid, name=name, role="box", part_id="EX-MICROD-15-F", unit_id="OBC1",
            gender="female", carries=["rs422"], pins=pins,
        )  # fmt: skip
    h = History(p)
    for _ in range(sensors):
        h.execute("sensor", edit.ops_add_unit(p, "sensor")[0])
    return p


def add(p: Project, *args: str | None) -> str:
    ops, iid = edit.ops_add_interface(p, "rs422", *args)  # type: ignore[arg-type]
    History(p).execute("interface", ops)
    return iid


def end_at(p: Project, iid: str, unit: str) -> str | None:
    return next(e.connector_id for e in p.interfaces[iid].endpoints if e.unit_id == unit)


def pins_of(p: Project, cid: str, iid: str) -> list[str]:
    return [x.id for x in p.connectors[cid].pins if x.interface_id == iid]


def with_model(p: Project, **values: object) -> None:
    model = p.config.get("model")
    old = dict(model.values) if model is not None else {}
    p.config["model"] = ConfigFile(name="model", placeholder=False, values={**old, **values})


# ---- room counted by the allocator -------------------------------------------------------------


def test_the_room_is_what_generate_does_on_a_fixed_pinout_with_ports() -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2", "RS422_3")))
    first = add(p, "OBC1", "ST1")
    assert end_at(p, first, "OBC1") == "OBC1-J1"
    room = edit.connector_room(p, "OBC1-J1", "rs422")
    # the first interface takes port RS422_1 in the dry run; the next one gets RS422_2
    assert room.ok and room.port == "RS422_2"
    assert dict(room.pins) == {"TX+": "5", "TX-": "6", "RX+": "7", "RX-": "8"}
    second = add(p, "OBC1", "ST2", "OBC1-J1", "ST2-J02")  # Expert: the connector is shared
    generate_project(p)
    # Generate gives the pins the dry run said, so the editor and Generate cannot disagree
    assert pins_of(p, "OBC1-J1", second) == ["5", "6", "7", "8"]
    assert pins_of(p, "OBC1-J1", first) == ["1", "2", "3", "4"]
    signals = [x.signal for x in p.connectors["OBC1-J1"].pins]
    assert signals == [f"RS422_{k}_{s}" for k in (1, 2, 3) for s in RS422]  # names are kept


def test_a_free_pinout_has_room_while_its_pins_last() -> None:
    p = obc(("J1", [Pin(id=str(k)) for k in range(1, 9)]))
    add(p, "OBC1", "ST1", "OBC1-J1", "ST1-J02")
    second = edit.connector_compat(p, "rs422", "OBC1-J1", far_unit="ST1", far_connector="ST1-J02")
    assert second.ok and second.note == ""  # 8 pins hold two RS-422; same far connector
    add(p, "OBC1", "ST1", "OBC1-J1", "ST1-J02")
    third = edit.connector_compat(p, "rs422", "OBC1-J1")
    assert not third.ok and third.short == "Full"
    assert third.why == (
        "OBC1-J1 cannot take another RS-422: too few free pins for TX+, TX- (0 free, 2 needed)."
    )


def test_the_dry_run_is_cached_while_the_project_is_the_same_objects() -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    add(p, "OBC1", "ST1")
    a = edit.connector_room(p, "OBC1-J1", "rs422")
    cache = edit._room_cache(p)
    runs = dict(cache.runs)
    assert edit.connector_room(p, "OBC1-J1", "rs422") == a
    assert edit._room_cache(p) is cache and cache.runs == runs  # nothing ran again
    add(p, "OBC1", "ST2")  # a new interface object: the cache starts again
    assert edit._room_cache(p) is not cache
    full = edit.connector_room(p, "OBC1-J1", "rs422")
    assert not full.ok and full.port == ""


# ---- refusal texts ------------------------------------------------------------------------------


def test_full_refusal_names_the_ports_and_who_uses_them() -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    a = add(p, "OBC1", "ST1")
    b = add(p, "OBC1", "ST2")
    assert end_at(p, b, "OBC1") == "OBC1-J1"  # tier 2: the free port RS422_2
    c = edit.connector_compat(p, "rs422", "OBC1-J1")
    assert not c.ok and c.short == "Full"
    assert c.why == (
        f"OBC1-J1 cannot take another RS-422: its RS-422 ports RS422_1, RS422_2 are used by {a},"
        f" {b}."
    )
    with pytest.raises(edit.EditError, match="its RS-422 ports RS422_1, RS422_2 are used by"):
        edit.ops_add_interface(p, "rs422", "OBC1", "ST3", "OBC1-J1", "ST3-J02")


def test_full_refusal_of_another_type_and_of_the_exact_names() -> None:
    bare = [Pin(id=str(k + 1), signal=s, fixed=True) for k, s in enumerate(RS422)]
    p = obc(("J1", bare))
    p.connectors["OBC1-J1"] = evolve(p.connectors["OBC1-J1"], carries=["rs422", "rs485"])
    add(p, "OBC1", "ST1")
    same = edit.connector_compat(p, "rs422", "OBC1-J1")
    assert same.why == (
        "OBC1-J1 cannot take another RS-422: it has a fixed pinout and no free pin named TX+, TX-,"
        " RX+, RX-."
    )
    other = edit.connector_compat(p, "rs485", "OBC1-J1")
    assert other.why == (
        "OBC1-J1 cannot take RS-485 as well: it has a fixed pinout and no free pin named A, B."
    )


def test_moving_an_interface_onto_a_full_connector_is_refused_with_the_reason() -> None:
    p = obc(("J1", port_pins("RS422_1")), ("J2", port_pins("RS422_1", start=5)))
    a = add(p, "OBC1", "ST1", "OBC1-J1", "ST1-J02")
    b = add(p, "OBC1", "ST2", "OBC1-J2", "ST2-J02")
    # b after a in ID order: b gets no port on J1
    with pytest.raises(edit.EditError) as exc:
        edit.ops_set_endpoint_connector(p, b, 0, "OBC1-J1")
    assert str(exc.value) == (
        f"OBC1-J1 cannot take another RS-422: its RS-422 port RS422_1 is used by {a}."
    )
    # a before b in ID order: a would take the port of b, which is refused as well
    with pytest.raises(edit.EditError) as exc:
        edit.ops_set_endpoint_connector(p, a, 0, "OBC1-J2")
    assert str(exc.value) == f"OBC1-J2 cannot take another RS-422: {b} would lose its pins to it."
    assert edit.ops_set_endpoint_connector(p, a, 0, "OBC1-J1") == []  # where it is already


# ---- notes -------------------------------------------------------------------------------------


def test_note_when_the_other_interfaces_go_to_another_far_connector() -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    a = add(p, "OBC1", "ST1")
    same = edit.connector_compat(p, "rs422", "OBC1-J1", far_unit="ST1", far_connector="ST1-J02")
    assert same.ok and same.note == ""
    other = edit.connector_compat(p, "rs422", "OBC1-J1", far_unit="ST2", far_connector="ST2-J02")
    assert other.ok
    assert other.note == (
        f"OBC1-J1 also carries {a} to another connector: Generate makes a second harness with its"
        " own plug on OBC1-J1 and warns about it, until a harness can branch (planned for 2.3.0)."
    )
    # only the far device is known (the connect tool before the far connector is picked)
    assert "second harness" in edit.connector_compat(p, "rs422", "OBC1-J1", "ST2").note
    assert edit.connector_compat(p, "rs422", "OBC1-J1", "ST1").note == ""
    # Generate says the same: two plugs on OBC1-J1
    add(p, "OBC1", "ST2", "OBC1-J1", "ST2-J02")
    codes = {f.code for f in generate_project(p).report.findings}
    assert "box_connector_shared" in codes


def test_note_when_a_released_harness_plugs_into_the_connector() -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    add(p, "OBC1", "ST1")
    generate_project(p)
    hid = next(iter(p.harnesses))
    p.harnesses[hid] = evolve(p.harnesses[hid], status="released")
    c = edit.connector_compat(p, "rs422", "OBC1-J1", far_unit="ST1", far_connector="ST1-J02")
    assert c.ok
    assert c.note == (
        f"{hid} is released and plugs into OBC1-J1: the new interface is wired only after a new"
        f" revision of {hid}."
    )
    elsewhere = edit.connector_compat(
        p, "rs422", "OBC1-J1", far_unit="ST2", far_connector="ST2-J02"
    )
    assert "second harness" in elsewhere.note and "released" not in elsewhere.note


# ---- the Guided choice: tier 1 unchanged, tier 2 -----------------------------------------------


def _tier_1(p: Project, unit_id: str, type_id: str) -> str | None:
    """The choice of 2.0.1, word for word: the first free connector in the order of the model."""
    used = {e.connector_id for i in p.interfaces.values() for e in i.endpoints}
    free = [
        c for c in edit.unit_connectors(p, unit_id) if edit.carries(c, type_id) and c.id not in used
    ]
    ranked = connector_choice.ranked(
        connector_choice.method(p), free, p.interface_types.get(type_id)
    )
    return ranked[0].id if ranked else None


def _projects() -> list[Project]:
    root = examples_path()
    assert root is not None
    names = ("first-steps", "minimal-satellite", "small-satellite", "flatsat")
    return [mini3(), sat15(), *(load_project(root / "projects" / n).project for n in names)]


@pytest.mark.parametrize("method", connector_choice.METHODS)
def test_tier_1_chooses_as_before_in_every_example(method: str) -> None:
    for p in _projects():
        with_model(p, connector_choice=method)
        for unit_id in sorted(p.units):
            for type_id in sorted(p.interface_types):
                before = _tier_1(p, unit_id, type_id)
                pick = edit.choose_connector(p, unit_id, type_id)
                assert (pick.id if pick else None) == before, (p.meta.name, unit_id, type_id)
                ok = edit.unit_compat(p, type_id, unit_id).ok
                assert ok == (before is not None), (p.meta.name, unit_id, type_id)


def test_tier_2_takes_a_connector_with_a_free_complete_port_in_the_model_order() -> None:
    p = obc(
        ("J1", port_pins("RS422_1", "RS422_2", "RS422_3")),
        ("J2", port_pins("RS422_1", "RS422_2")),
        sensors=4,
    )
    a = add(p, "OBC1", "ST1")
    b = add(p, "OBC1", "ST2")
    assert (end_at(p, a, "OBC1"), end_at(p, b, "OBC1")) == ("OBC1-J1", "OBC1-J2")  # tier 1
    assert edit.free_connectors(p, "OBC1", "rs422") == []
    shared = [c.id for c in edit.shared_connectors(p, "OBC1", "rs422")]
    assert shared == ["OBC1-J1", "OBC1-J2"]
    assert edit.choose_connector(p, "OBC1", "rs422").id == "OBC1-J1"  # type: ignore[union-attr]
    # best fit: J2 has one free port (4 pins left), J1 two (8 pins left)
    with_model(p, connector_choice="fewest_spare_pins")
    assert edit.choose_connector(p, "OBC1", "rs422").id == "OBC1-J2"  # type: ignore[union-attr]
    with_model(p, connector_choice="most_spare_pins")
    assert edit.choose_connector(p, "OBC1", "rs422").id == "OBC1-J1"  # type: ignore[union-attr]
    fit = connector_choice.fit_of(
        p.connectors["OBC1-J2"], p.interface_types["rs422"], edit.taken_pins(p, "OBC1-J2")
    )
    assert (fit.available, fit.ports, fit.fits) == (4, 1, True)
    assert edit.choose_connector(p, "OBC1", "rs422", avoid={"OBC1-J1", "OBC1-J2"}) is None


def test_tier_2_never_shares_a_connector_whose_pins_the_device_leaves_free() -> None:
    p = obc(("J1", [Pin(id=str(k)) for k in range(1, 16)]))
    add(p, "OBC1", "ST1")
    assert edit.connector_compat(p, "rs422", "OBC1-J1").ok  # Expert: room for more
    assert edit.shared_connectors(p, "OBC1", "rs422") == []
    c = edit.unit_compat(p, "rs422", "OBC1")
    assert not c.ok and c.short == "No free RS-422 connector"
    assert c.why == (
        "OBC1 has no free RS-422 connector. Use a device template that has one (for example"
        ' "Computer (many interfaces)").'
    )
    with pytest.raises(edit.EditError, match="no free RS-422 connector"):
        edit.ops_add_interface(p, "rs422", "OBC1", "ST2")


def test_repeated_bare_names_are_never_counted_as_ports_by_the_guided_choice() -> None:
    bare = [Pin(id=str(k + 1), signal=s, fixed=True) for k, s in enumerate(RS422 * 2)]
    p = obc(("J1", bare))
    add(p, "OBC1", "ST1")
    assert edit.connector_compat(p, "rs422", "OBC1-J1").ok  # Generate can place it, with a warning
    assert edit.connector_room(p, "OBC1-J1", "rs422").port == ""
    assert edit.shared_connectors(p, "OBC1", "rs422") == []


def test_the_no_connector_fix_takes_a_free_port() -> None:
    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    add(p, "OBC1", "ST1")
    p.interfaces["IF-900"] = InterfaceInstance(
        id="IF-900", name="ST2 link", type_id="rs422", redundancy="nominal",
        endpoints=[Endpoint(unit_id="OBC1"), Endpoint(unit_id="ST2")],
    )  # fmt: skip
    finding = next(f for f in checks.find(p) if f.rule == "no-connector")
    ops, msg = checks.fix_ops(p, finding)
    History(p).execute("fix", ops)
    assert msg == "Chose connectors for IF-900."
    assert end_at(p, "IF-900", "OBC1") == "OBC1-J1" and end_at(p, "IF-900", "ST2") == "ST2-J02"
    assert all(e.auto for e in p.interfaces["IF-900"].endpoints)
    generate_project(p)
    assert pins_of(p, "OBC1-J1", "IF-900") == ["5", "6", "7", "8"]
    # no free port left: the fix says so, as before
    p.interfaces["IF-901"] = evolve(p.interfaces["IF-900"], id="IF-901")
    p.interfaces["IF-901"] = evolve(
        p.interfaces["IF-901"], endpoints=[Endpoint(unit_id="OBC1"), Endpoint(unit_id="ST3")]
    )
    with pytest.raises(edit.EditError, match="OBC1 has no free connector for rs422"):
        checks._assign_connectors(p, "IF-901")


# ---- explain -----------------------------------------------------------------------------------


def test_explain_lists_every_interface_and_the_free_ports_of_each_candidate() -> None:
    p = obc(
        ("J1", port_pins("RS422_1", "RS422_2", "RS422_3")),
        ("J2", port_pins("RS422_1", "RS422_2")),
        sensors=3,
    )
    a = add(p, "OBC1", "ST1", "OBC1-J1", "ST1-J02")
    b = add(p, "OBC1", "ST2", "OBC1-J1", "ST2-J02")
    plain = render(connector_choice_derivation(p, "OBC1-J1"))
    assert "A-PORTS" in plain and "Free rs422 ports = RS422_3" in plain
    with_model(p, connector_choice="fewest_spare_pins")
    text = render(connector_choice_derivation(p, "OBC1-J1"))
    assert f"this interface and {b}, free ports RS422_3" in text
    assert "OBC1-J2: 8 pins, 8 available, 4 needed, 4 spare, free, free ports RS422_1, RS422_2" in (
        text
    )
    assert a in text and b in text


def test_explain_of_a_shared_connector_names_each_interface_once_and_both_tiers() -> None:
    """Regression (end-to-end test of 2.1.0): `explain` of a connector with three interfaces gave
    the same step three times without naming an interface, and its equation named only tier 1 of
    the Guided choice. Now the interfaces with the same choice share one step that names them, and
    the equation names both tiers."""
    p = obc(("J1", port_pins("RS422_1", "RS422_2", "RS422_3")))
    ids = [add(p, "OBC1", f"ST{k}") for k in (1, 2, 3)]  # Guided: J1 by tier 1, then by tier 2
    assert all(end_at(p, i, "OBC1") == "OBC1-J1" for i in ids)
    d = connector_choice_derivation(p, "OBC1-J1")
    assert [(s.label, s.text) for s in d.steps] == [
        ("Connectors of OBC1 that carry rs422, for IF-001, IF-002, IF-003", "OBC1-J1")
    ]
    assert "else the first with a free complete port of the type" in d.steps[0].expression
    assert d.equation == (
        "connector = the one a person picks for the interface at the device, else the first free"
        " connector of the device that carries the type; when none is free, the first connector of"
        " the device with a fixed pinout that has a free complete port of the type"
    )
    # a person picks one: that interface gets a step of its own
    p.interfaces[ids[1]] = evolve(
        p.interfaces[ids[1]],
        endpoints=[evolve(e, auto=False) for e in p.interfaces[ids[1]].endpoints],
    )
    steps = connector_choice_derivation(p, "OBC1-J1").steps
    assert [s.label for s in steps] == [
        "Connectors of OBC1 that carry rs422, for IF-001, IF-003",
        "Connectors of OBC1 that carry rs422, for IF-002",
    ]
    assert steps[1].expression.endswith("; a person picked this one")
    # another model: one ranking step per interface, each named, and both tiers in the equation
    with_model(p, connector_choice="fewest_spare_pins")
    d = connector_choice_derivation(p, "OBC1-J1")
    ranking = [s.label for s in d.steps if "in the order of" in s.label]
    assert ranking == [
        f"Connectors of OBC1 in the order of fewest_spare_pins, for {i}" for i in ids
    ]
    assert d.equation.endswith(
        "; when none is free, the connectors with a fixed pinout that have a free complete port"
        " of the type, in the same order"
    )
    assert render(d) == render(connector_choice_derivation(p, "OBC1-J1"))  # deterministic


def test_explain_of_a_connector_with_one_interface_keeps_its_step() -> None:
    """One interface on the connector: the step reads as in 2.1.0 (the user manual quotes it)."""
    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    add(p, "OBC1", "ST1")
    (step,) = connector_choice_derivation(p, "OBC1-J1").steps
    assert step.label == "Connectors of OBC1 that carry rs422"
    assert step.expression == "in ID order: OBC1-J1; the tool takes the first one that is free"


def test_assumptions_name_the_ports() -> None:
    from harness_design_studio.core.assumptions import ASSUMPTIONS

    assert "dry run" in ASSUMPTIONS["A-PORTS"].text
    assert "free complete port" in ASSUMPTIONS["A-CONNECTOR-CHOICE"].text


def test_a_shared_connector_survives_a_save_and_a_load(tmp_path: Path) -> None:
    from harness_design_studio.core.io.saver import save_project

    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    add(p, "OBC1", "ST1")
    add(p, "OBC1", "ST2")
    save_project(p, tmp_path / "proj")
    q = load_project(tmp_path / "proj").project
    assert [i.id for i in edit.interfaces_using(q, "OBC1-J1")] == ["IF-001", "IF-002"]
    assert edit.interface_using(q, "OBC1-J1").id == "IF-001"  # type: ignore[union-attr]
    assert not edit.connector_compat(q, "rs422", "OBC1-J1").ok


# ---- a port chosen by a person, pins on a shared connector (devices) ---------------------------


def test_assign_port_locks_the_pins_of_the_port_and_keeps_their_names() -> None:
    from harness_design_studio.core import devices

    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    a = add(p, "OBC1", "ST1")
    b = add(p, "OBC1", "ST2")
    ops = devices.ops_assign_port(p, "OBC1-J1", "RS422_2", a)
    assert len(ops) == 1  # the end of a is on OBC1-J1 already: the connector alone
    History(p).execute("port", ops)
    pins = p.connectors["OBC1-J1"].pins
    assert [(x.id, x.signal, x.interface_id, x.locked, x.fixed) for x in pins[4:]] == [
        (str(k + 5), f"RS422_2_{s}", a, True, True) for k, s in enumerate(RS422)
    ]
    notes = [n.check for n in devices.pinout_problems(p, "OBC1-J1")]
    assert notes == ["CD-K2"]  # 8 of 15 pins; a locked port pin is a signal of RS-422 (no CD-K6)
    # Generate keeps a on the port it was locked to and gives b the other one
    generate_project(p)
    assert pins_of(p, "OBC1-J1", a) == ["5", "6", "7", "8"]
    assert pins_of(p, "OBC1-J1", b) == ["1", "2", "3", "4"]
    # a pin of another interface is refused, with the pin and the interface named
    assert_refused = pytest.raises(edit.EditError, match="Pin 5 carries IF-001; unassign it first.")
    with assert_refused:
        devices.ops_assign_port(p, "OBC1-J1", "RS422_2", b)


def test_assign_port_clears_the_pins_generate_gave_the_interface_before() -> None:
    """The old pins of the interface lose it in the same step: before the fix they kept their
    `interface_id` until the next Generate, so the pin table and the end showed two ports."""
    from harness_design_studio.core import devices

    p = obc(("J1", port_pins("RS422_1", "RS422_2", "RS422_3")))
    a = add(p, "OBC1", "ST1")
    b = add(p, "OBC1", "ST2")
    generate_project(p)
    assert pins_of(p, "OBC1-J1", a) == ["1", "2", "3", "4"]  # Generate's pins, not locked
    assert pins_of(p, "OBC1-J1", b) == ["5", "6", "7", "8"]
    before = [x.model_copy() for x in p.connectors["OBC1-J1"].pins]
    ops = devices.ops_assign_port(p, "OBC1-J1", "RS422_3", a)
    assert len(ops) == 1  # one connector: one undo step
    h = History(p)
    h.execute("port", ops)
    pins = {x.id: x for x in p.connectors["OBC1-J1"].pins}
    assert pins_of(p, "OBC1-J1", a) == ["9", "10", "11", "12"]
    # the old pins keep everything but the interface: their names, `fixed` and no lock
    for k, sig in enumerate(RS422):
        old = pins[str(k + 1)]
        assert (old.signal, old.fixed, old.locked, old.interface_id) == (
            f"RS422_1_{sig}",
            True,
            False,
            None,
        )
    assert pins_of(p, "OBC1-J1", b) == ["5", "6", "7", "8"]  # another interface is not touched
    end = devices.end_port(p, a, "OBC1-J1")
    assert end is not None and (end.port, end.how) == ("RS422_3", "locked")
    h.undo()
    assert p.connectors["OBC1-J1"].pins == before


def test_assign_port_keeps_a_locked_pin_of_the_interface_elsewhere() -> None:
    from harness_design_studio.core import devices

    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    a = add(p, "OBC1", "ST1")
    History(p).execute("port", devices.ops_assign_port(p, "OBC1-J1", "RS422_1", a))
    History(p).execute("port", devices.ops_assign_port(p, "OBC1-J1", "RS422_2", a))
    # a lock is a person's choice: `ops_unassign_pins` takes it away, choosing a port does not
    assert pins_of(p, "OBC1-J1", a) == [str(k) for k in range(1, 9)]
    assert all(x.locked for x in p.connectors["OBC1-J1"].pins)


def test_assign_port_refusals() -> None:
    from harness_design_studio.core import devices

    pins = port_pins("RS422_1") + [Pin(id="9", signal="RS422_3_TX+", fixed=True)]
    p = obc(("J1", pins))
    a = add(p, "OBC1", "ST1")
    with pytest.raises(edit.EditError, match="OBC1-J1 has no RS-422 port RS422_9."):
        devices.ops_assign_port(p, "OBC1-J1", "RS422_9", a)
    with pytest.raises(edit.EditError, match="Port RS422_3 of OBC1-J1 has no pin for TX-, RX"):
        devices.ops_assign_port(p, "OBC1-J1", "RS422_3", a)
    with pytest.raises(edit.EditError, match="does not exist"):
        devices.ops_assign_port(p, "OBC1-J1", "RS422_1", "IF-999")


def test_assign_pins_keeps_a_fixed_pin_and_refuses_a_pin_that_reads_otherwise() -> None:
    from harness_design_studio.core import devices

    p = obc(("J1", port_pins("RS422_1", "RS422_2")))
    a = add(p, "OBC1", "ST1")
    with pytest.raises(edit.EditError) as exc:
        devices.ops_assign_pins(p, "OBC1-J1", ["2", "1", "3", "4"], a)
    assert str(exc.value) == (
        "Pin 1 is fixed as RS422_1_TX+, which is not TX- of RS-422. Choose the pin of TX-."
    )
    with pytest.raises(edit.EditError) as exc:
        devices.ops_assign_pins(p, "OBC1-J1", ["1", "2", "7", "8"], a)
    assert str(exc.value) == (
        "Pins 1 and 7 are in 2 ports (RS422_1, RS422_2); an interface uses the pins of one port."
    )
    History(p).execute("pins", devices.ops_assign_pins(p, "OBC1-J1", ["1", "2", "3", "4"], a))
    assert [(x.signal, x.fixed, x.locked, x.interface_id) for x in p.connectors["OBC1-J1"].pins][
        :2
    ] == [("RS422_1_TX+", True, True, a), ("RS422_1_TX-", True, True, a)]


def test_inline_notes_read_port_names() -> None:
    from harness_design_studio.core import devices

    pins = port_pins("RS422_1", "RS422_2")[:7] + [Pin(id="9", signal="CAN_X", fixed=True)]
    p = obc(("J1", pins), sensors=0)
    notes = devices.pinout_problems(p, "OBC1-J1")
    found = [(n.check, n.code, n.message) for n in notes]
    assert ("CD-K9", "port_problem", "Port RS422_2 of OBC1-J1 has no pin for RX-, so it is not"
            " offered for RS-422.") in found  # fmt: skip
    # a pin of a port is no unknown signal, and RS-422 is complete by port RS422_1
    assert not any(n.check in ("CD-K4", "CD-K8") and n.pin_id != "9" for n in notes)
    assert [n.pin_id for n in notes if n.check == "CD-K4"] == ["9"]
    assert devices.suggest_carries(p, "OBC1-J1") == ["ethernet", "rs422"]


# ---- speed (design section 8) ------------------------------------------------------------------


@pytest.mark.perf
def test_room_on_every_connector_is_fast_at_1000_pins_and_200_devices() -> None:
    """The dry run runs while the pointer is over a connector: asking every connector of a project
    of 200 devices, one of them with 1000 fixed pins in 100 ports and 60 interfaces on it, stays
    quick, and again (from the cache) much quicker."""
    import time

    from harness_design_studio.core.samples import stress_project
    from tests.helpers import within

    p = stress_project(units=200, interfaces=600)
    signals = [s.name for s in p.interface_types["multicore"].signals]
    big = [
        Pin(id=str(10 * k + j + 1), signal=f"P{k + 1}_{s}", fixed=True)
        for k in range(100)
        for j, s in enumerate(signals)
    ]
    p.connectors["U000-BIG"] = Connector(
        id="U000-BIG", name="BIG", role="box", part_id="EX-MDM-21-F", unit_id="U000",
        gender="female", carries=["multicore"], pins=big,
    )  # fmt: skip
    far = [u for u in sorted(p.units)[1:] if edit.free_connectors(p, u, "multicore")][:60]
    for k, unit_id in enumerate(far):
        iid = f"IF-B{k:03d}"
        p.interfaces[iid] = InterfaceInstance(
            id=iid, name=iid, type_id="multicore", redundancy="nominal",
            endpoints=[Endpoint(unit_id="U000", connector_id="U000-BIG"),
                       Endpoint(unit_id=unit_id, connector_id=edit.free_connectors(p, unit_id, "multicore")[0].id)],
        )  # fmt: skip
    assert len(p.connectors["U000-BIG"].pins) == 1000 and len(p.units) == 200
    start = time.perf_counter()
    room = edit.connector_room(p, "U000-BIG", "multicore")
    within(time.perf_counter() - start, 0.2, "one dry run of a connector of 1000 pins, s")
    assert room.ok and room.port == "P1"  # IF-001 comes first by ID; nothing generated yet

    def hover_all() -> float:
        start = time.perf_counter()
        for cid in p.connectors:
            edit.connector_compat(p, "multicore", cid, "U150")
        return time.perf_counter() - start

    within(hover_all(), 3.0, "every connector asked once, the dry runs made, s")
    within(hover_all(), 0.3, "every connector asked again, from the cache, s")
