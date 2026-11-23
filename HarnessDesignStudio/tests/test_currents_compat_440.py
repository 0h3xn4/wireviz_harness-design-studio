# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-WIRE-10: with no pin current the current rules are those of 4.4.0 (design of 5.0.0
`docs/ait/DESIGN_5.0_FORMAT_5.md` sections 5.3 and 11 (2), pull request 3).

`tests/reference/currents_440.py` is the part of `core/drc/rules.py` of the tag `v4.4.0` from the
ratings to the end of `_unchecked`, and `_bundle_current` of `core/drc/standard_rules.py`, word for
word. On random harnesses of `tests/test_production_verify.py` (splices, loose ends, loops, missing
lengths and gauges) given interfaces with and without a current, wires with and without an
interface (one that is gone too), random derating values, contact ratings and bundle bases, and no
pin current, every finding of `current-over-contact`, `current-over-wire`, `voltage-drop`,
`bundle-current` and `unchecked-config` equals the copy's, and `wire_currents` gives each wire the
current of its interface. A pin current on a pin no wire reaches changes only the contact check."""

from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness_design_studio.core.currents import has_pin_currents, wire_currents
from harness_design_studio.core.drc import rules, standard_rules
from harness_design_studio.core.generate import bundle
from harness_design_studio.core.model import (
    ConfigFile,
    InterfaceInstance,
    InterfaceType,
    Project,
    SignalDef,
    evolve,
)
from harness_design_studio.core.model.logical import Endpoint
from tests.reference import currents_440 as ref
from tests.test_production_verify import production_projects

SLOW = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
_CURRENTS = st.sampled_from([None, 0.5, 2.0, 7.5, 7.5])
_FACTORS = st.sampled_from([None, 0.5, 0.5, 1.0])


@st.composite
def current_projects(draw: st.DrawFn) -> Project:
    """A random project of `tests/test_production_verify.py` with interfaces (a power one counted
    with its return, a data one), currents, gauges, derating values and contact ratings, and no
    pin current."""
    p = draw(production_projects())
    p.interface_types["pwr"] = InterfaceType(
        id="pwr", name="Power", category="power", construction="single",
        signals=[SignalDef(name="PWR")],
    )  # fmt: skip
    p.interface_types["dat"] = InterfaceType(
        id="dat", name="Data", category="data", construction="single",
        signals=[SignalDef(name="SIG")],
    )  # fmt: skip
    boxes = sorted(p.connectors)
    for iid, tid in (("IF1", "pwr"), ("IF2", "dat"), ("IF3", "gone-type")):
        ends = draw(st.lists(st.sampled_from([*boxes, "NO-BOX"]), min_size=1, max_size=2))
        p.interfaces[iid] = InterfaceInstance(
            id=iid, type_id=tid, name=iid, max_current_a=draw(_CURRENTS),
            endpoints=[Endpoint(unit_id=f"U{k}", connector_id=c) for k, c in enumerate(ends)],
        )  # fmt: skip
    for cid in boxes:
        c = p.connectors[cid]
        pins = [
            evolve(pin, interface_id=draw(st.sampled_from([None, "IF1", "IF2"]))) for pin in c.pins
        ]
        p.connectors[cid] = evolve(c, pins=pins)
    h = p.harnesses["W001"]
    wires = [
        evolve(
            w,
            interface_id=draw(st.sampled_from([None, "IF1", "IF2", "IF3", "IF-GONE"])),
            gauge_awg=draw(st.sampled_from([None, 20, 24, 24, 26, 40])),
        )
        for w in h.wires
    ]
    p.harnesses["W001"] = evolve(h, wires=wires)
    derating: dict[str, Any] = {
        "contact_current_factor": draw(_FACTORS),
        "bundle_derating": draw(st.sampled_from([None, 0.8, 0.8])),
        "temperature_derating": draw(st.sampled_from([None, 0.9, 0.9])),
        "max_voltage_drop_v": draw(st.sampled_from([None, 0.01, 1.0])),
        "ampacity_a_by_awg": draw(
            st.sampled_from([None, {"20": 7.5, "24": 3.0, "26": 2.0}, {"24": 1.0, "26": 0.5}])
        ),
        "contact_rating_key": "contact_current_a",
    }
    if draw(st.booleans()):
        derating["bundle_factor_by_count"] = draw(
            st.sampled_from([{"1": 1.0, "2": 0.9}, {str(n): 0.5 for n in range(1, 20)}])
        )
    p.config["derating"] = ConfigFile(name="derating", placeholder=False, values=derating)
    generation = dict(p.config["generation"].values)
    generation["conductor_resistivity_ohm_m"] = draw(st.sampled_from([None, 1.72e-8]))
    p.config["generation"] = ConfigFile(name="generation", placeholder=False, values=generation)
    model = dict(p.config["model"].values)
    model["bundle_basis"] = draw(st.sampled_from(bundle.BASES))
    p.config["model"] = ConfigFile(name="model", placeholder=False, values=model)
    for pid in draw(st.lists(st.sampled_from(sorted(p.parts)), max_size=6, unique=True)):
        p.parts[pid] = evolve(p.parts[pid], ratings={"contact_current_a": draw(_CURRENTS) or 1.0})
    bundle.clear_cache()
    return p


def _same_as_440(p: Project) -> None:
    assert list(rules._current_over_contact(p)) == list(ref._current_over_contact(p))
    assert list(rules._current_over_wire(p)) == list(ref._current_over_wire(p))
    assert list(rules._voltage_drop(p)) == list(ref._voltage_drop(p))
    assert list(standard_rules._bundle_current(p)) == list(ref._bundle_current(p))
    assert list(rules._unchecked(p)) == list(ref._unchecked(p))


@SLOW
@given(current_projects())
def test_without_a_pin_current_the_current_rules_are_those_of_4_4_0(p: Project) -> None:
    assert not has_pin_currents(p)
    _same_as_440(p)
    for h in p.harnesses.values():
        for w in h.wires:
            i = p.interfaces.get(w.interface_id or "")
            got = wire_currents(p, h)[w.id]
            assert got.value == (i.max_current_a if i is not None else None)
            assert got.source == ("interface" if got.value is not None else "")


@SLOW
@given(current_projects(), st.data())
def test_a_pin_current_no_wire_reaches_changes_only_the_contact_check(
    p: Project, data: st.DataObject
) -> None:
    """A pin current on pins that no wire of a harness ends on behind (no cable connector mates
    with their connector) leaves every wire's current, and so the wire, bundle and drop checks."""
    mated = {c.mates_with for h in p.harnesses.values() for c in h.connectors if c.mates_with}
    free = [c for c in p.connectors.values() if c.unit_id and c.id not in mated and c.pins]
    if not free:
        return
    c = data.draw(st.sampled_from(free))
    p.connectors[c.id] = evolve(c, pins=[evolve(c.pins[0], current_a=1.5), *c.pins[1:]])
    assert has_pin_currents(p)
    assert list(rules._current_over_wire(p)) == list(ref._current_over_wire(p))
    assert list(rules._voltage_drop(p)) == list(ref._voltage_drop(p))
    assert list(standard_rules._bundle_current(p)) == list(ref._bundle_current(p))
