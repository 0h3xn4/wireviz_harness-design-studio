# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-WIRE-10: a current per pin and the current of a wire from the pin currents of its net
(part B of the design of 5.0.0, `docs/ait/DESIGN_5.0_FORMAT_5.md` sections 3.1, 3.2, 5, 10 and 13;
pull request 3).

The rule of the file; `core/currents.py` (two ends, the splice star of section 5.2, parallel
wires equal and unequal, a loop, an unbalanced net, a loose end, the fallback to the interface);
the four rules with pin currents (`current-over-contact` per pin, `current-over-wire`,
`bundle-current`, `voltage-drop`), the codes `current_unbalanced` and `current_not_worked_out`, the
note of the wires without an interface; `explain`; `import-pinout` *Current* (A, mA, a bad cell)
and `export-pinout` read back; the columns of section 5.4 and their check; the editor's pin edit;
a pin current is not an input of Generate (F5). Every device, number and part here is made up."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness_design_studio.core import currents, devices, integrity
from harness_design_studio.core.currents import has_pin_currents, net_currents, wire_currents
from harness_design_studio.core.drc import rules, standard_rules
from harness_design_studio.core.drc import run as run_drc
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.generation_status import input_hash
from harness_design_studio.core.model import (
    ConfigFile,
    Connector,
    Harness,
    InterfaceInstance,
    InterfaceType,
    Part,
    Pin,
    Project,
    SignalDef,
    Unit,
    Wire,
    evolve,
)
from harness_design_studio.core.model.logical import Endpoint
from harness_design_studio.core.samples import new_project

SPLICE = "EX-SPLICE-1"
BOX = "EX-BOX-9"
PLUG = "EX-PLUG-9"


def _derating(p: Project, **values: object) -> None:
    base = {
        "contact_current_factor": 0.5, "bundle_derating": 1.0, "temperature_derating": 1.0,
        "ampacity_a_by_awg": {"20": 7.5, "24": 3.0}, "contact_rating_key": "contact_current_a",
    }  # fmt: skip
    p.config["derating"] = ConfigFile(name="derating", placeholder=False, values={**base, **values})


def _box(unit: str, amps: list[float | None]) -> Connector:
    pins = [Pin(id=str(k), signal="PWR", current_a=a) for k, a in enumerate(amps, start=1)]
    return Connector(id=f"{unit}-J01", name="J01", role="box", part_id=BOX, unit_id=unit, pins=pins)


def _plug(hid: str, n: int, box: str, pins: int, role: str = "cable") -> Connector:
    return Connector(
        id=f"{hid}-P{n}", name=f"P{n}", role=role, part_id=PLUG,  # type: ignore[arg-type]
        mates_with=box if role == "cable" else None,
        pins=[Pin(id=str(k)) for k in range(1, pins + 1)],
    )  # fmt: skip


def _wire(
    hid: str, n: int, a: tuple[str, str], b: tuple[str, str], awg: int = 24, length: float = 0.5
) -> Wire:
    return Wire(
        id=f"{hid}-{n:03d}", from_connector=a[0], from_pin=a[1], to_connector=b[0], to_pin=b[1],
        gauge_awg=awg, length_m=length, manual=True, signal="PWR",
    )  # fmt: skip


def base_project(pcdu: list[float | None], obc: list[float | None]) -> Project:
    """Two devices, PCDU1 and OBC1, each with a connector J01 of part EX-BOX-9 (contacts of 3 A,
    a factor of 0.5: 1.5 A after derating), and the pin currents given."""
    p = new_project("Currents")
    p.parts[BOX] = Part(id=BOX, category="connector", ratings={"contact_current_a": 3.0})
    p.parts[PLUG] = Part(id=PLUG, category="connector")
    p.parts[SPLICE] = Part(id=SPLICE, category="splice", pin_count=1)
    for u, amps in (("PCDU1", pcdu), ("OBC1", obc)):
        p.units[u] = Unit(id=u, name=u, subsystem="power")
        p.connectors[f"{u}-J01"] = _box(u, amps)
    _derating(p)
    return p


def star_project(pcdu: float | None = 6.0, obc: tuple[float | None, ...] = (2.0, 2.0, 2.0)) -> Project:  # fmt: skip
    """The example of section 5.2: PCDU1-J01 pin 1 gives 6 A; OBC1-J01 pins 1, 2 and 3 take 2 A
    each; harness W003, drawn by hand, joins them in the splice W003-X1."""
    p = base_project([pcdu], list(obc))
    h = "W003"
    x1 = Connector(id=f"{h}-X1", name="X1", role="splice", part_id=SPLICE, pins=[Pin(id="1")])
    p.harnesses[h] = Harness(
        id=h, name="Power", connectors=[_plug(h, 1, "PCDU1-J01", 1), _plug(h, 2, "OBC1-J01", 3), x1],
        wires=[
            _wire(h, 1, (f"{h}-P1", "1"), (f"{h}-X1", "1"), awg=20, length=1.0),
            *(_wire(h, k + 1, (f"{h}-X1", "1"), (f"{h}-P2", str(k))) for k in (1, 2, 3)),
        ],
    )  # fmt: skip
    return p


def parallel_project(amps: float | None = 6.0, second: dict[str, object] | None = None) -> Project:
    """Two wires in parallel between PCDU1-J01 pin 1 and OBC1-J01 pin 1, each pin stating `amps`;
    `second` changes the second wire."""
    p = base_project([amps], [amps])
    h = "W001"
    w2 = _wire(h, 2, (f"{h}-P1", "1"), (f"{h}-P2", "1"))
    p.harnesses[h] = Harness(
        id=h, name="Parallel", connectors=[_plug(h, 1, "PCDU1-J01", 1), _plug(h, 2, "OBC1-J01", 1)],
        wires=[_wire(h, 1, (f"{h}-P1", "1"), (f"{h}-P2", "1")), evolve(w2, **(second or {}))],
    )  # fmt: skip
    return p


def _values(p: Project, hid: str) -> dict[str, tuple[float | None, str]]:
    return {k: (v.value, v.source) for k, v in wire_currents(p, p.harnesses[hid]).items()}


# ---- the field and the rule of the file (sections 3.1, 3.2, 5.1) ---------------------------------


def test_the_key_is_sparse_and_only_on_a_pin_of_a_device_connector() -> None:
    assert "current_a" not in Pin(id="1").model_dump()
    assert Pin(id="1", current_a=2.5).model_dump()["current_a"] == 2.5
    assert Pin(id="1", current_a=1000.0).current_a == 1000.0
    for bad, words in ((0.0, "greater than 0"), (-1.0, "greater than 0"), (1000.5, "less than or equal to 1000")):  # fmt: skip
        with pytest.raises(ValidationError, match=words):
            Pin(id="1", current_a=bad)
    with pytest.raises(ValidationError, match="only a pin of a device connector has a current"):
        Connector(id="W001-P1", name="P1", role="cable", part_id=PLUG, pins=[Pin(id="1", current_a=1.0)])  # fmt: skip
    assert _box("OBC1", [1.0]).pins[0].current_a == 1.0


def test_a_cable_pin_with_a_current_is_set_aside_on_load(tmp_path: Path) -> None:
    from harness_design_studio.core.io.loader import load_project
    from harness_design_studio.core.io.saver import save_project

    save_project(star_project(), tmp_path / "p")
    loaded = load_project(tmp_path / "p")
    assert loaded.project.connectors["OBC1-J01"].pins[0].current_a == 2.0
    assert "W003" in loaded.project.harnesses and not loaded.project.quarantine
    path = tmp_path / "p" / "physical" / "harnesses" / "W003.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["connectors"][0]["pins"][0]["current_a"] = 6.0
    path.write_text(json.dumps(doc), encoding="utf-8")
    loaded = load_project(tmp_path / "p")
    assert "W003" not in loaded.project.harnesses
    assert any("only a pin of a device connector" in q.reason for q in loaded.project.quarantine)


def test_a_project_without_a_pin_current_has_none_of_the_new_checks() -> None:
    p = star_project(None, (None, None, None))
    assert not has_pin_currents(p)
    assert integrity.current_issues(p) == []
    assert {v.source for v in wire_currents(p, p.harnesses["W003"]).values()} == {""}


# ---- the current of a wire (section 5.2) ---------------------------------------------------------


def test_two_ends_with_the_same_current_give_the_wire_that_current() -> None:
    p = parallel_project()
    h = p.harnesses["W001"]
    p.harnesses["W001"] = evolve(h, wires=h.wires[:1])
    got = wire_currents(p, p.harnesses["W001"])["W001-001"]
    assert (got.value, got.source) == (6.0, "pins")
    assert got.reason == (
        "the pin currents of its net (6 A at PCDU1-J01.1; 6 A at OBC1-J01.1): between W001-P1.1 "
        "and W001-P2.1 the smaller of 6 A and 6 A"
    )


def test_the_splice_star_of_section_5_2() -> None:
    p = star_project()
    assert _values(p, "W003") == {
        "W003-001": (6.0, "pins"),
        "W003-002": (2.0, "pins"),
        "W003-003": (2.0, "pins"),
        "W003-004": (2.0, "pins"),
    }
    branch = wire_currents(p, p.harnesses["W003"])["W003-002"].branch
    assert branch is not None and (branch.side_a, branch.side_b) == (2.0, 10.0)
    assert integrity.current_issues(p) == []


def test_equal_parallel_wires_share_the_current() -> None:
    p = parallel_project()
    assert _values(p, "W001") == {"W001-001": (3.0, "pins"), "W001-002": (3.0, "pins")}
    got = wire_currents(p, p.harnesses["W001"])["W001-001"]
    assert got.share == 2 and got.reason.endswith(", shared by 2 parallel wires")


@pytest.mark.parametrize(
    "second", [{"gauge_awg": 20}, {"length_m": 0.7}, {"gauge_awg": None}, {"length_m": None}]
)
def test_parallel_wires_that_differ_are_not_worked_out(second: dict[str, object]) -> None:
    p = parallel_project(second=second)
    assert _values(p, "W001") == {"W001-001": (None, ""), "W001-002": (None, "")}
    issues = integrity.current_issues(p)
    assert [(i.severity, i.code, i.object_id) for i in issues] == [
        ("info", "current_not_worked_out", "W001-001")
    ]
    assert issues[0].message == (
        "The currents of the net of W001-001 were not worked out: the parallel wires W001-001 and "
        "W001-002 between W001-P1.1 and W001-P2.1 do not have one known gauge and one known "
        "length. Its wires were not checked for current."
    )


def test_a_loop_is_not_worked_out() -> None:
    p = star_project()
    h = p.harnesses["W003"]
    extra = _wire("W003", 5, ("W003-P2", "1"), ("W003-P2", "2"))  # joins two far pins: a loop
    p.harnesses["W003"] = evolve(h, wires=[*h.wires, extra])
    assert {v for v, _s in _values(p, "W003").values()} == {None}
    [issue] = integrity.current_issues(p)
    assert (issue.code, issue.severity) == ("current_not_worked_out", "info")
    assert "its wires form a loop" in issue.message


def test_an_unbalanced_net_is_said_and_its_wires_are_not_checked() -> None:
    p = star_project(obc=(2.0, 2.0, 1.5))
    assert {v for v, _s in _values(p, "W003").values()} == {None}
    [issue] = integrity.current_issues(p)
    assert (issue.severity, issue.code, issue.object_id) == ("warning", "current_unbalanced", "W003-001")  # fmt: skip
    assert issue.message == (
        "The pin currents of the net of W003-001 do not add up: 6 A at PCDU1-J01.1; 2 A, 2 A and "
        "1.5 A at OBC1-J01.1, .2 and .3. Its wires were not checked for current. Correct the "
        "currents of the pins."
    )
    found = [f for f in run_drc(p) if f.rule == "model-inconsistent"]
    assert [f.object_id for f in found] == ["W003-001"]


def test_a_net_with_an_end_without_a_current_takes_the_interface_s_current() -> None:
    p = star_project(obc=(2.0, 2.0, None))
    p.interface_types["pwr"] = InterfaceType(
        id="pwr", name="Power", category="power", signals=[SignalDef(name="PWR")]
    )
    p.interfaces["IF-001"] = InterfaceInstance(
        id="IF-001", name="Power", type_id="pwr", max_current_a=4.0,
        endpoints=[Endpoint(unit_id="PCDU1", connector_id="PCDU1-J01")],
    )  # fmt: skip
    h = p.harnesses["W003"]
    p.harnesses["W003"] = evolve(
        h, wires=[evolve(w, interface_id="IF-001") if w.id == "W003-001" else w for w in h.wires]
    )
    assert _values(p, "W003") == {
        "W003-001": (4.0, "interface"),
        "W003-002": (None, ""),
        "W003-003": (None, ""),
        "W003-004": (None, ""),
    }
    assert [nc.status for nc in net_currents(p, p.harnesses["W003"])] == [currents.PARTIAL]


def test_a_loose_end_or_a_test_connector_has_no_current() -> None:
    p = parallel_project()
    h = p.harnesses["W001"]
    loose = _plug("W001", 2, "OBC1-J01", 1, role="loose")
    p.harnesses["W001"] = evolve(h, connectors=[h.connectors[0], loose])
    assert _values(p, "W001") == {"W001-001": (None, ""), "W001-002": (None, "")}
    assert integrity.current_issues(p) == []


# ---- the rules (section 5.3) ---------------------------------------------------------------------


def test_current_over_contact_judges_a_pin_with_a_current_on_its_own() -> None:
    p = star_project()
    hits = [(h.object_id, h.title) for h in rules._current_over_contact(p)]
    assert hits == [
        ("OBC1-J01.1", "Pin 1 of OBC1-J01 carries 2 A but its contacts allow 1.5 A after derating"),
        ("OBC1-J01.2", "Pin 2 of OBC1-J01 carries 2 A but its contacts allow 1.5 A after derating"),
        ("OBC1-J01.3", "Pin 3 of OBC1-J01 carries 2 A but its contacts allow 1.5 A after derating"),
        ("PCDU1-J01.1", "Pin 1 of PCDU1-J01 carries 6 A but its contacts allow 1.5 A after derating"),
    ]  # fmt: skip


def test_the_interface_finding_stays_for_its_pins_without_a_current() -> None:
    p = star_project(obc=(1.0, 1.0, 4.0))
    p.interface_types["pwr"] = InterfaceType(
        id="pwr", name="Power", category="power", signals=[SignalDef(name="PWR")]
    )
    p.interfaces["IF-001"] = InterfaceInstance(
        id="IF-001", name="Power", type_id="pwr", max_current_a=6.0,
        endpoints=[Endpoint(unit_id="PCDU1", connector_id="PCDU1-J01"), Endpoint(unit_id="OBC1", connector_id="OBC1-J01")],
    )  # fmt: skip
    c = p.connectors["OBC1-J01"]
    p.connectors["OBC1-J01"] = evolve(
        c,
        pins=[
            evolve(x, interface_id="IF-001", current_a=None if x.id == "3" else x.current_a)
            for x in c.pins
        ],  # fmt: skip
    )
    c = p.connectors["PCDU1-J01"]
    p.connectors["PCDU1-J01"] = evolve(c, pins=[evolve(c.pins[0], interface_id="IF-001")])
    ids = [h.object_id for h in rules._current_over_contact(p)]
    # OBC1-J01 pin 3 states no current: the interface is judged there as in 4.4.0; every pin of
    # IF-001 at PCDU1-J01 states one, so that pin is judged on its own
    assert ids == ["IF-001.OBC1-J01", "PCDU1-J01.1"]


def test_the_wires_of_a_harness_drawn_by_hand_are_judged_for_the_first_time() -> None:
    p = star_project()
    h = p.harnesses["W003"]
    p.harnesses["W003"] = evolve(h, wires=[evolve(h.wires[0], gauge_awg=24), *h.wires[1:]])
    assert [(x.object_id, x.title) for x in rules._current_over_wire(p)] == [
        ("W003-001", "Wire W003-001 (AWG 24) carries 6 A but allows 3 A after derating")
    ]
    _derating(p, bundle_factor_by_count={str(n): 0.5 for n in range(1, 9)})
    # a bundle of four: AWG 24 allows 1.5 A, so the 2 A of each far wire is over it too
    assert [x.object_id for x in standard_rules._bundle_current(p)] == [
        "W003-001", "W003-002", "W003-003", "W003-004",
    ]  # fmt: skip


def test_the_voltage_drop_needs_an_interface_type_to_count_the_conductors() -> None:
    p = star_project()
    _derating(p, max_voltage_drop_v=0.05)
    gen = dict(p.config["generation"].values)
    p.config["generation"] = ConfigFile(name="generation", placeholder=False, values={**gen, "conductor_resistivity_ohm_m": 1.72e-8})  # fmt: skip
    assert list(rules._voltage_drop(p)) == []
    notes = {x.object_id: x.title for x in rules._unchecked(p)}
    assert notes["voltage-drop-wires"] == (
        "Voltage drop was not checked for 4 wire(s) without an interface type to count the "
        "conductors of (first: W003-001)"
    )
    p.interface_types["pwr"] = InterfaceType(
        id="pwr", name="Power", category="power", signals=[SignalDef(name="PWR")]
    )
    p.interfaces["IF-001"] = InterfaceInstance(
        id="IF-001", name="Power", type_id="pwr",
        endpoints=[Endpoint(unit_id="PCDU1", connector_id="PCDU1-J01")],
    )  # fmt: skip
    h = p.harnesses["W003"]
    p.harnesses["W003"] = evolve(h, wires=[evolve(w, interface_id="IF-001") for w in h.wires])
    # the pin currents still decide (the interface states none); counted out and back
    # (A-ROUND-TRIP): 6 A over 1 m of AWG 20 drop 0.063 V, 2 A over 0.5 m of AWG 24 0.168 V
    assert [x.object_id for x in rules._voltage_drop(p)] == [
        "W003-001", "W003-002", "W003-003", "W003-004",
    ]  # fmt: skip


def test_the_note_of_the_wires_without_an_interface() -> None:
    p = star_project(None, (None, None, None))
    [note] = [x.title for x in rules._wires_without_interface(p)]
    assert note == (
        "Current, voltage-drop and bundle checks did not run for 4 wire(s) of harness W003: they "
        "have no interface to take a current from"
    )
    p = star_project()  # every wire takes a current from its pins: nothing to say
    assert list(rules._wires_without_interface(p)) == []
    p = parallel_project()
    p.harnesses["W002"] = evolve(p.harnesses["W001"], id="W002", connectors=[
        evolve(c, id=c.id.replace("W001", "W002"), mates_with=None, role="loose") for c in p.harnesses["W001"].connectors
    ], wires=[evolve(w, id=w.id.replace("W001", "W002"), from_connector=w.from_connector.replace("W001", "W002"), to_connector=w.to_connector.replace("W001", "W002")) for w in p.harnesses["W001"].wires])  # fmt: skip
    [note] = [x.title for x in rules._wires_without_interface(p)]
    assert note == (
        "Current, voltage-drop and bundle checks did not run for 2 wire(s) of harness W002: they "
        "have no interface and no current on their pins to take a current from"
    )


def test_a_pin_current_is_a_current_for_the_notes_of_what_did_not_run() -> None:
    p = star_project()
    p.config["derating"] = ConfigFile(name="derating", placeholder=True, values={"contact_rating_key": "contact_current_a"})  # fmt: skip
    ids = [x.object_id for x in rules._unchecked(p)]
    assert "derating" in ids and "voltage-drop" in ids
    assert not [x for x in rules._nothing_to_evaluate(p) if x.object_id.startswith("no-current")]
    _derating(p)
    p.parts[BOX] = evolve(p.parts[BOX], ratings={})
    notes = {x.object_id: x.title for x in rules._unchecked(p)}
    assert notes["contact-rating"] == f"Contact current was not checked for {BOX}: the part has no contact rating"  # fmt: skip


# ---- explain (section 5.3) -----------------------------------------------------------------------


def test_explain_of_a_wire_names_the_pin_currents_the_branch_and_the_share(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from harness_design_studio.cli.main import main
    from harness_design_studio.core.derive import wire_current_limit_derivation
    from harness_design_studio.core.io.saver import save_project

    p = star_project()
    h = p.harnesses["W003"]
    d = wire_current_limit_derivation(p, h, h.wires[1])
    assert d.check is not None and d.check.actual == 2.0
    assert "A-ONE-SOURCE" in d.assumptions and "A-PARALLEL-SHARE" in d.assumptions
    steps = {s.label: s.value for s in d.steps}
    assert steps["Current at PCDU1-J01.1"] == 6.0 and steps["Current at OBC1-J01.3"] == 2.0
    assert steps["Current between W003-P2.1 and W003-X1.1"] == 2.0
    save_project(p, tmp_path / "p")
    assert main(["explain", str(tmp_path / "p"), "W003-002"]) == 0
    out = capsys.readouterr().out
    assert "6 A at PCDU1-J01.1; 2 A, 2 A and 2 A at OBC1-J01.1, .2 and .3" in out
    assert "the smaller of the end currents on its two sides: min(2, 10)" in out


def test_explain_of_a_pin_finding_is_the_contact_limit_of_the_pin() -> None:
    from harness_design_studio.core.derive import explain_finding, explain_object

    p = star_project()
    [d] = explain_finding(p, "current-over-contact", "OBC1-J01.2")
    assert d.id == "contact-current" and d.subject == "Pin 2 of OBC1-J01"
    assert d.value == 1.5 and d.check is not None and not d.check.passes
    assert d.check.text.startswith("the pin carries 2 A and its contacts allow 1.5 A")
    assert any(x.id == "contact-current" for x in explain_object(p, "OBC1-J01.2"))


def test_a_pin_current_wins_over_the_interface_s_and_the_explanation_names_both() -> None:
    from harness_design_studio.core.derive import wire_current_limit_derivation

    p = star_project()
    p.interface_types["pwr"] = InterfaceType(
        id="pwr", name="Power", category="power", signals=[SignalDef(name="PWR")]
    )
    p.interfaces["IF-001"] = InterfaceInstance(
        id="IF-001", name="Power", type_id="pwr", max_current_a=4.0,
        endpoints=[Endpoint(unit_id="PCDU1", connector_id="PCDU1-J01")],
    )  # fmt: skip
    h = p.harnesses["W003"]
    p.harnesses["W003"] = evolve(h, wires=[evolve(w, interface_id="IF-001") for w in h.wires])
    h = p.harnesses["W003"]
    assert wire_currents(p, h)["W003-002"].value == 2.0
    d = wire_current_limit_derivation(p, h, h.wires[1])
    names = {i.name: i.value for i in d.inputs}
    assert names["Current carried"] == 2.0 and d.check is not None and d.check.actual == 2.0
    assert names["Current of the interface (not used: the pin currents decide)"] == 4.0


def test_the_parallel_example_explains_the_share() -> None:
    from harness_design_studio.core.derive import wire_current_limit_derivation

    p = parallel_project()
    h = p.harnesses["W001"]
    d = wire_current_limit_derivation(p, h, h.wires[0])
    steps = {s.label: s.value for s in d.steps}
    assert steps["Share of each of the 2 parallel wires"] == 3.0


# ---- the editor's edit, import-pinout and export-pinout (sections 5.1, 5.5) ---------------------


def test_a_pin_current_is_set_and_cleared_in_one_step() -> None:
    from harness_design_studio.core.commands import apply_ops

    p = base_project([None], [None])
    apply_ops(p, devices.ops_set_pin(p, "OBC1-J01", "1", current_a="500 mA"))
    assert p.connectors["OBC1-J01"].pins[0].current_a == 0.5
    assert devices.ops_set_pin(p, "OBC1-J01", "1", current_a="0.5") == []
    apply_ops(p, devices.ops_set_pin(p, "OBC1-J01", "1", current_a=""))
    assert p.connectors["OBC1-J01"].pins[0].current_a is None
    for bad in ("2,5", "0", "-1", "1001", "two"):
        with pytest.raises(EditError):
            devices.ops_set_pin(p, "OBC1-J01", "1", current_a=bad)


def _sheet(rows: list[list[str]]) -> list[list[str]]:
    return [["Connector", "Pin", "Signal", *rows[0]], *(["J01", str(k), "PWR", *r] for k, r in enumerate(rows[1:], start=1))]  # fmt: skip


def test_import_pinout_reads_a_current_column_in_amperes_and_milliamperes(tmp_path: Path) -> None:
    from harness_design_studio.core.commands import apply_ops
    from harness_design_studio.core.import_reports import pinout_report
    from harness_design_studio.core.pinout_import import guess_mapping, plan_pinout_import

    for heading in ("Current", "Current (A)", "Pin current", "Max current"):
        p = base_project([None, None, None], [None])
        table = _sheet([[heading], ["2"], ["500 mA"], [""]])
        plan = plan_pinout_import(p, table, guess_mapping(table[0]), unit_id="PCDU1")
        assert plan.bad_count == 0 and not plan.warnings, [r.message for r in plan.rows]
        apply_ops(p, plan.ops)
        assert [x.current_a for x in p.connectors["PCDU1-J01"].pins] == [2.0, 0.5, None]
    p = base_project([None, None], [None])
    table = _sheet([["Current (mA)"], ["1500"], ["2 A"]])
    plan = plan_pinout_import(p, table, guess_mapping(table[0]), unit_id="PCDU1")
    apply_ops(p, plan.ops)
    assert [x.current_a for x in p.connectors["PCDU1-J01"].pins] == [1.5, 2.0]
    (tmp_path / "pinout.csv").write_text("\n".join(",".join(r) for r in table), encoding="utf-8")
    report = pinout_report(tmp_path / "pinout.csv", tmp_path, table, guess_mapping(table[0]), plan)
    assert [c.text() for c in report.converted] == ["1500 mA = 1.5 A"]
    assert report.converted[0].field == "current_a" and report.converted[0].item == "PCDU1-J01 pin 1"  # fmt: skip


def test_a_bad_current_refuses_its_row_and_the_whole_sheet() -> None:
    from harness_design_studio.core.pinout_import import guess_mapping, plan_pinout_import

    p = base_project([None, None, None], [None])
    table = _sheet([["Current"], ["2"], ["two"], ["0"]])
    plan = plan_pinout_import(p, table, guess_mapping(table[0]), unit_id="PCDU1")
    assert not plan.ops
    bad = {r.row_number: r.message for r in plan.rows if not r.ok}
    assert bad == {
        3: "The current 'two' is not a number of amperes (2, 2 A or 500 mA)",
        4: "A current is above 0 A; leave it empty when the ICD states none",
    }


def test_export_pinout_writes_the_column_for_a_device_with_a_current_and_reads_back() -> None:
    from harness_design_studio.core.pinout_import import guess_mapping, plan_pinout_import

    p = star_project(obc=(2.0, 2.0, 2.0))
    c = p.connectors["PCDU1-J01"]
    p.connectors["PCDU1-J01"] = evolve(c, pins=[evolve(c.pins[0], current_a=None)])
    sheet = devices.pinout_sheet(p, "OBC1")
    assert sheet[0][-1] == "Current (A)" and [r[-1] for r in sheet[1:]] == ["2", "2", "2"]
    assert "Current (A)" not in devices.pinout_sheet(p, "PCDU1")[0]
    assert "Current (A)" in devices.pinout_table(p, "PCDU1")[0]  # the project's table has it
    plan = plan_pinout_import(p, sheet, guess_mapping(sheet[0]), unit_id="OBC1")
    assert plan.bad_count == 0 and not plan.ops and plan.unchanged == ["OBC1-J01"]


def test_a_current_column_was_a_column_import_pinout_left_out() -> None:
    from harness_design_studio.core.pinout_import import guess_mapping, unstored_columns

    header = ["Pin", "Signal", "Current", "Voltage"]
    assert unstored_columns(header, guess_mapping(header)) == ["Voltage"]


# ---- the library, Generate (sections 3.7, 5.1, F5) ----------------------------------------------


def test_a_pin_current_makes_the_device_file_version_4_and_is_compared_by_the_update() -> None:
    from harness_design_studio.core import device_library, library_link

    p = star_project()
    content = device_library.export_devices(p, ["OBC1"])
    assert content["version"] == 4
    assert "current_a" in library_link.PIN_FIELDS


def test_a_pin_current_is_not_an_input_of_generate() -> None:
    p = base_project([None], [None])
    before = input_hash(p)
    c = p.connectors["OBC1-J01"]
    p.connectors["OBC1-J01"] = evolve(c, pins=[evolve(c.pins[0], current_a=2.0)])
    assert input_hash(p) == before


def test_the_extension_field_and_the_open_data_take_the_current_of_the_wire() -> None:
    from harness_design_studio.core.extensions.fields import Context, _wire_current
    from harness_design_studio.core.open_data import wire_sizing

    p = star_project()
    h = p.harnesses["W003"]
    assert _wire_current(Context(p, h, h.wires[1])) == 2.0
    rows = {r["wire"]: r["current_a"] for r in wire_sizing(p).rows}
    assert rows == {"W003-001": 6, "W003-002": 2, "W003-003": 2, "W003-004": 2}


# ---- the outputs (section 5.4) -------------------------------------------------------------------


@pytest.fixture(scope="module")
def format5_files() -> tuple[Project, dict[str, bytes]]:
    from harness_design_studio.core.outputs.build import build_outputs
    from tests.format5_support import format5_project

    p = format5_project()
    return p, dict(build_outputs(p, harness_plan=True).files)


def _errors(p: Project, files: dict[str, bytes]) -> list[tuple[str, str]]:
    from harness_design_studio.core.outputs.verify import verify_outputs

    return [(i.code, i.message) for i in verify_outputs(p, files).issues if i.severity == "error"]


def test_the_pin_currents_reach_the_outputs_and_verify_finds_no_error(
    format5_files: tuple[Project, dict[str, bytes]],
) -> None:
    from tests.plan_support import parse_address, read_plan

    p, files = format5_files
    assert _errors(p, files) == []
    rows = files["system/box_pinouts.csv"].decode().splitlines()
    assert rows[2].endswith(",Current (A)")
    assert rows[3] == "DEV1-J01,box,,EX-MICROD-25-F,1,TX+,IF-001,W001-001,no,2"
    assert rows[4].endswith(",no,")
    doc = json.loads(files["system/export.json"])
    assert doc["field_units"]["box_connectors[].pins[].current_a"] == "A"
    dev1 = next(c for c in doc["box_connectors"] if c["id"] == "DEV1-J01")
    assert [x.get("current_a") for x in dev1["pins"][:5]] == [2.0, None, None, None, 1.0]
    plan = read_plan(files["harnesses/W001/W001_plan.ods"])
    con = plan["CON_DEV1-J01"]
    assert con[parse_address("F18")].value == "Current [A]"
    assert con[parse_address("F19")].value == 2
    assert con.get(parse_address("F20")) is None or con[parse_address("F20")].value in ("", None)
    assert parse_address("F18") not in plan["CON_DEV4-J01"]  # no pin of DEV4-J01 has a current
    findings = files["system/drc_findings.csv"].decode()
    assert "Pin 1 of DEV1-J01 carries 2 A but its contacts allow 1.5 A after derating" in findings
    assert "The pin currents of the net of W001-009 do not add up" in findings
    assert "Rules run: 43." in files["system/drc_report.md"].decode()


def test_a_wrong_current_in_the_box_pinouts_is_out_box_pinouts(
    format5_files: tuple[Project, dict[str, bytes]],
) -> None:
    p, files = format5_files
    rel = "system/box_pinouts.csv"
    changed = files[rel].replace(b"W001-001,no,2", b"W001-001,no,3")
    errors = _errors(p, {**files, rel: changed})
    assert errors and {code for code, _m in errors} == {"out_box_pinouts", "out_xlsx"}, errors


def test_a_wrong_current_in_a_con_sheet_is_found_by_the_plan_check(
    format5_files: tuple[Project, dict[str, bytes]],
) -> None:
    from tests.format5_support import PIN_CURRENTS

    p, files = format5_files
    q = evolve_currents(p, {**PIN_CURRENTS, ("DEV1-J01", "1"): 2.5})
    codes = {code for code, _m in _errors(q, files)}
    assert {"out_plan", "out_box_pinouts"} <= codes, codes


def evolve_currents(p: Project, amps: dict[tuple[str, str], float]) -> Project:
    """A copy of the project whose device pins state `amps`."""
    from harness_design_studio.core.edit import clone_with

    q = clone_with(p, [])
    for cid, c in list(q.connectors.items()):
        q.connectors[cid] = evolve(c, pins=[evolve(x, current_a=amps.get((cid, x.id))) for x in c.pins])  # fmt: skip
    return q


def test_without_a_pin_current_no_table_has_the_column(
    format5_files: tuple[Project, dict[str, bytes]],
) -> None:
    from harness_design_studio.core.outputs.tables import box_pinouts

    p, _files = format5_files
    q = evolve_currents(p, {})
    assert "Current (A)" not in box_pinouts(q)[0]
    assert "current_a" not in json.dumps([x.model_dump() for c in q.connectors.values() for x in c.pins])  # fmt: skip
