# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The design rules `signal-unassigned` and `direction-conflict` and the independent verifier read
port names (REQ-PIN-04, D-237; `docs/ait/DESIGN_2.1_PORTS.md` sections 1 and 3): a fixed pin
`RS422_2_TX+` carries the signal TX+. The verifier has its own copy of the reading rule, compared
here with `core/ports.py`, and the error `port_mixed` for an interface on the pins of two ports."""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from harness_design_studio.core import drc, ports, verify
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.model import Harness, Project, evolve
from harness_design_studio.core.outputs.build import build_outputs
from harness_design_studio.core.outputs.verify import verify_outputs
from harness_design_studio.core.starter import starter_interface_types
from harness_design_studio.core.verify import verify_project
from tests.test_ports_allocation import BOX, rs422x3

LIBRARY = {t.id: t for t in starter_interface_types()}


def generated() -> Project:
    p = rs422x3()
    generate_project(p)
    return p


def hits(p: Project, rule: str) -> list[str]:
    return [f.title for f in drc.run(p) if f.rule == rule]


def harness_of(p: Project, iid: str) -> Harness:
    return next(h for h in p.harnesses.values() if iid in h.interfaces)


def obc_end(h: Harness) -> str:
    return next(c.id for c in h.connectors if c.mates_with == BOX)


# --- design rules ----------------------------------------------------------------------------


def test_port_pins_pass_the_two_rules() -> None:
    p = generated()
    assert hits(p, "signal-unassigned") == [] and hits(p, "direction-conflict") == []


def test_signal_unassigned_still_finds_a_port_pin_with_no_interface() -> None:
    p = generated()
    pins = [evolve(x, interface_id=None) if x.id == "4" else x for x in p.connectors[BOX].pins]
    p.connectors[BOX] = evolve(p.connectors[BOX], pins=pins)  # RS422_1_RX- of IF-001
    assert hits(p, "signal-unassigned") == ["Signal RX- of IF-001 has no pin on OBC1-J1"]


def test_direction_conflict_reads_the_signal_of_a_port_pin() -> None:
    p = generated()
    h = harness_of(p, "IF-001")
    cable = obc_end(h)
    far = next(c for c in h.connectors if c.id != cable)
    star = p.connectors[str(far.mates_with)]
    tx_star = next(x.id for x in star.pins if x.signal == "TX+" and x.interface_id == "IF-001")
    # the wire from TX+ of port RS422_1 (pin 1) now ends on TX+ of the star tracker
    wires = []
    for w in h.wires:
        if (w.from_connector, w.from_pin) == (cable, "1"):
            w = evolve(w, to_pin=tx_star)
        elif (w.to_connector, w.to_pin) == (cable, "1"):
            w = evolve(w, from_pin=tx_star)
        wires.append(w)
    p.harnesses[h.id] = evolve(h, wires=wires)
    assert len(found := hits(p, "direction-conflict")) == 1
    assert "two outputs" in found[0]


# --- the independent verifier ----------------------------------------------------------------


def test_port_pins_pass_the_verifier_and_the_written_outputs() -> None:
    p = generated()
    report = verify_project(p)
    assert report.ok and report.interfaces_checked == 3, report.issues
    out = verify_outputs(p, dict(build_outputs(p).files))
    assert not [i for i in out.issues if i.severity == "error"], out.issues


def test_port_mixed_is_found() -> None:
    p = generated()
    # IF-001 and IF-002 swap their RX+ pins (3 of RS422_1, 7 of RS422_2), wires and all
    swap = {"3": "7", "7": "3"}
    owner = {x.id: x.interface_id for x in p.connectors[BOX].pins}
    pins = [
        evolve(x, interface_id=owner[swap[x.id]]) if x.id in swap else x
        for x in p.connectors[BOX].pins
    ]
    p.connectors[BOX] = evolve(p.connectors[BOX], pins=pins)
    for iid in ("IF-001", "IF-002"):
        h = harness_of(p, iid)
        cable = obc_end(h)

        def moved(c: str, pin: str) -> str:
            return swap.get(pin, pin) if c == cable else pin  # noqa: B023

        p.harnesses[h.id] = evolve(
            h,
            wires=[
                evolve(
                    w,
                    from_pin=moved(w.from_connector, w.from_pin),
                    to_pin=moved(w.to_connector, w.to_pin),
                )
                for w in h.wires
            ],
        )
    errors = verify_project(p).errors
    assert {e.code for e in errors} == {"port_mixed"}
    mixed = (
        "Interface {} uses the pins of 2 ports on OBC1-J1 (RS422_1, RS422_2); an interface"
        " uses the pins of one port. Regenerate, or lock the pins of one port."
    )
    assert [e.message for e in errors] == [mixed.format("IF-001"), mixed.format("IF-002")]
    assert hits(p, "verify-mismatch")  # the design rule check reports it too


def test_bare_and_port_pins_of_one_interface_are_two_ports() -> None:
    p = generated()
    pins = [evolve(x, signal="TX+") if x.id == "1" else x for x in p.connectors[BOX].pins]
    p.connectors[BOX] = evolve(p.connectors[BOX], pins=pins)
    found = [e for e in verify_project(p).errors if e.code == "port_mixed"]
    assert [e.message for e in found] == [
        "Interface IF-001 uses the pins of 2 ports on OBC1-J1 (pins named by the signal alone,"
        " RS422_1); an interface uses the pins of one port. Regenerate, or lock the pins of one"
        " port."
    ]


# --- the verifier's copy of the reading rule -------------------------------------------------

SIGNAL_SETS = [
    [s.name for s in LIBRARY["rs422"].signals],
    [s.name for s in LIBRARY["can"].signals],
    [s.name for s in LIBRARY["power_primary"].signals],
    ["CAN_H", "CAN_L"],  # names that hold a separator themselves
    ["A", "A_B", "B"],
    [""],
]
NAMES = [
    "TX+", "RS422_2_TX+", "TX+.P2", "TX+-RS422_10", "RS422.1.RX-", "_TX+", "TX+_", "TX+_TX+",
    "RX-_TX+", "CANH", "CAN_CANH", "CAN_H", "CAN_CAN_H", "CAN_H_L", "PWR", "RTN-2", "A_B",
    "A_B_C", "B_A", "X_A_B", "", "NC", "tx+", "RS422_2_tx+",
]  # fmt: skip


def core_readings(name: str, signals: list[str]) -> tuple[tuple[str, str, str, str], ...]:
    return tuple((r.port, r.signal, r.form, r.separator) for r in ports.read_signal(name, signals))


def test_the_verifier_reads_port_names_as_the_core_does() -> None:
    for signals in SIGNAL_SETS:
        for name in NAMES:
            assert verify.port_readings(name, signals) == core_readings(name, signals), name
    assert verify.port_readings("RS422_2_TX+", SIGNAL_SETS[0]) == (
        ("RS422_2", "TX+", "prefix", "_"),
    )


@settings(max_examples=300, deadline=None)
@given(
    name=st.text(alphabet="AB_.-+TXR2", max_size=10),
    signals=st.lists(st.text(alphabet="AB_.-+TX", max_size=4), max_size=4),
)
def test_the_two_copies_of_the_reading_rule_agree_on_any_name(
    name: str, signals: list[str]
) -> None:
    assert verify.port_readings(name, signals) == core_readings(name, signals)


def test_the_verifier_does_not_import_the_core_parser() -> None:
    text = Path(verify.__file__ or "").read_text(encoding="utf-8")
    assert "ports import" not in text and "core.ports" not in text and "from .ports" not in text
