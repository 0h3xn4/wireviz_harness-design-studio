# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The port parser of 2.1.0 (`core/ports.py`, REQ-PIN-04, D-237; `docs/ait/DESIGN_2.1_PORTS.md`
section 3): which fixed pins of a connector form a port of an interface type, read from the signal
names."""

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_design_studio.core import ports
from harness_design_studio.core.model import Connector, InterfaceType, Pin, SignalDef
from harness_design_studio.core.ports import Reading
from harness_design_studio.core.starter import starter_interface_types

LIBRARY = {t.id: t for t in starter_interface_types()}
RS422 = LIBRARY["rs422"]
CAN = LIBRARY["can"]
POWER = LIBRARY["power_primary"]
# A type whose signal names hold a separator themselves (not in the library).
CAN_SPLIT = InterfaceType(
    id="can_split",
    name="CAN (split names)",
    category="data",
    signals=[
        SignalDef(name="CAN_H", direction="bidir"),
        SignalDef(name="CAN_L", direction="bidir"),
    ],
)


def names(t: InterfaceType) -> list[str]:
    return [s.name for s in t.signals]


def conn(*pins: tuple[str, str] | tuple[str, str, bool], cid: str = "J1") -> Connector:
    """A box connector with fixed pins (id, signal) or (id, signal, fixed)."""
    return Connector(
        id=cid,
        name=cid,
        role="box",
        part_id="EX-MICROD-25-F",
        unit_id="OBC1",
        pins=[Pin(id=p[0], signal=p[1], fixed=p[2] if len(p) == 3 else True) for p in pins],
    )


def port_pins(prefix: str, t: InterfaceType, first: int, sep: str = "_") -> list[tuple[str, str]]:
    """The pins of one named port in prefix form, numbered from `first`."""
    return [(str(first + i), f"{prefix}{sep}{s}") for i, s in enumerate(names(t))]


# --- reading one signal name -------------------------------------------------------------------


def test_the_types_of_the_library_are_the_ones_these_tests_assume() -> None:
    assert names(RS422) == ["TX+", "TX-", "RX+", "RX-"]
    assert len(names(CAN)) == 2 and len(names(POWER)) == 2


@pytest.mark.parametrize("t", [RS422, CAN, POWER, CAN_SPLIT], ids=lambda t: t.id)
def test_a_signal_name_of_the_type_is_a_bare_pin(t: InterfaceType) -> None:
    for s in names(t):
        assert ports.read_signal(s, names(t)) == (Reading("", s, "bare", ""),)


@pytest.mark.parametrize("sep", ports.SEPARATORS)
@pytest.mark.parametrize("t", [RS422, CAN, POWER, CAN_SPLIT], ids=lambda t: t.id)
def test_prefix_and_suffix_forms_with_every_separator(t: InterfaceType, sep: str) -> None:
    for s in names(t):
        assert ports.read_signal(f"RS422_2{sep}{s}", names(t)) == (
            Reading("RS422_2", s, "prefix", sep),
        )
        assert ports.read_signal(f"{s}{sep}P2", names(t)) == (Reading("P2", s, "suffix", sep),)


def test_the_separators_are_underscore_dot_and_hyphen() -> None:
    assert ports.SEPARATORS == ("_", ".", "-")
    assert ports.COMPOSE_SEPARATOR == "_"
    assert ports.read_signal("RS422_2 TX+", names(RS422)) == ()  # a space is not a separator
    assert ports.read_signal("RS422_2/TX+", names(RS422)) == ()
    assert ports.read_signal("RS422_2TX+", names(RS422)) == ()


def test_matching_is_exact_and_case_sensitive() -> None:
    sig = names(RS422)
    assert ports.read_signal("tx+", sig) == ()
    assert ports.read_signal("RS422_2_tx+", sig) == ()
    assert ports.read_signal("rs422_2_TX+", sig) == (Reading("rs422_2", "TX+", "prefix", "_"),)
    assert ports.read_signal(" TX+", sig) == ()
    assert ports.read_signal("RS422_2_TX", sig) == ()  # TX is not a signal of RS-422


def test_a_port_needs_a_name() -> None:
    sig = names(RS422)
    for sep in ports.SEPARATORS:
        assert ports.read_signal(f"{sep}TX+", sig) == ()
        assert ports.read_signal(f"TX+{sep}", sig) == ()


def test_a_name_with_two_readings_is_ambiguous() -> None:
    sig = names(RS422)
    # two signals and two ports
    assert ports.read_signal("TX+_RX-", sig) == (
        Reading("RX-", "TX+", "suffix", "_"),
        Reading("TX+", "RX-", "prefix", "_"),
    )
    # one signal, two ports
    assert len(ports.read_signal("TX+_X_TX+", sig)) == 2
    # the same port and signal, read as prefix and as suffix
    assert ports.read_signal("TX+.TX+", sig) == (
        Reading("TX+", "TX+", "prefix", "."),
        Reading("TX+", "TX+", "suffix", "."),
    )


def test_signal_names_with_an_underscore() -> None:
    sig = names(CAN_SPLIT)
    assert ports.read_signal("CAN_H", sig) == (Reading("", "CAN_H", "bare", ""),)
    assert ports.read_signal("CAN_H_2", sig) == (Reading("2", "CAN_H", "suffix", "_"),)
    assert ports.read_signal("2_CAN_H", sig) == (Reading("2", "CAN_H", "prefix", "_"),)
    assert ports.read_signal("BUS1-CAN_L", sig) == (Reading("BUS1", "CAN_L", "prefix", "-"),)
    # H is not a signal of this type: CAN_H is not the port CAN of a signal H
    assert ports.read_signal("CAN_X", sig) == ()


def test_a_bare_name_is_never_read_as_a_port() -> None:
    """Exact names first (today's rule): when H is a signal too, CAN_H stays the bare CAN_H."""
    sig = ["CAN_H", "CAN_L", "H"]
    assert ports.read_signal("CAN_H", sig) == (Reading("", "CAN_H", "bare", ""),)
    # a longer name reads two ways: CAN_H of port BUS, or H of port BUS_CAN
    assert ports.read_signal("BUS_CAN_H", sig) == (
        Reading("BUS", "CAN_H", "prefix", "_"),
        Reading("BUS_CAN", "H", "prefix", "_"),
    )


def test_a_name_that_is_no_signal_of_the_type_reads_as_nothing() -> None:
    assert ports.read_signal("PWR", names(RS422)) == ()
    assert ports.read_signal("RS422_2_TX+", names(CAN)) == ()
    assert ports.read_signal("", names(RS422)) == ()


# --- composing a name ---------------------------------------------------------------------------


def test_compose_writes_port_underscore_signal() -> None:
    assert ports.compose("RS422_2", "TX+") == "RS422_2_TX+"
    assert ports.compose("", "TX+") == "TX+"
    assert ports.compose("TX", "TX-") == "TX_TX-"  # TX- does not start with the port TX


def test_compose_keeps_a_name_that_already_starts_with_the_port() -> None:
    assert ports.compose("RS422_2", "RS422_2_TX+") == "RS422_2_TX+"
    assert ports.compose("RS422_2", "RS422_2_TX+", names(RS422)) == "RS422_2_TX+"
    assert ports.compose("RS422_2", "RS422_2.TX+") == "RS422_2.TX+"
    assert ports.compose("RS422_2", "RS422_2-TX+") == "RS422_2-TX+"
    # another port that only starts with the same characters
    assert ports.compose("RS422_2", "RS422_20_TX+") == "RS422_2_RS422_20_TX+"
    assert ports.compose("RS422_2", "RS422_2") == "RS422_2_RS422_2"


def test_compose_always_adds_the_port_to_a_signal_of_the_type() -> None:
    """CAN_H starts with the port CAN, but it is the bare signal: given the signals, it gets the port."""
    assert ports.compose("CAN", "CAN_H") == "CAN_H"
    assert ports.compose("CAN", "CAN_H", names(CAN_SPLIT)) == "CAN_CAN_H"
    assert ports.read_signal("CAN_CAN_H", names(CAN_SPLIT)) == (
        Reading("CAN", "CAN_H", "prefix", "_"),
    )
    assert ports.port_name_problem("CAN", names(CAN_SPLIT)) is None


def test_a_port_name_that_cannot_be_used() -> None:
    sig = names(RS422)
    assert ports.port_name_problem("RS422_2", sig) is None
    assert ports.port_name_problem("", sig) == "A port needs a name."
    assert ports.port_name_problem("TX+", sig) == (
        "The port name TX+ cannot be used: TX+_TX+ can be read as TX+ of port TX+ in two ways."
    )
    assert ports.port_name_problem("CAN", ["H", "CAN_H"]) == (
        "The port name CAN cannot be used: CAN_H is a signal of the type itself."
    )
    assert ports.port_name_problem("CAN", ["CAN_H", "H"]) == (
        "The port name CAN cannot be used: CAN_CAN_H can be read as CAN_H of port CAN"
        " or as H of port CAN_CAN."
    )
    assert ports.port_name_problem("RX-_A", sig) == (
        "The port name RX-_A cannot be used: RX-_A_TX+ can be read as TX+ of port RX-_A"
        " or as RX- of port A_TX+."
    )


SAFE = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcxyz0123456789", min_size=1, max_size=12)
TYPES = st.sampled_from([*LIBRARY.values(), CAN_SPLIT])


@settings(max_examples=300, deadline=None)
@given(port=SAFE, t=TYPES, sep=st.sampled_from(ports.SEPARATORS))
def test_round_trip_compose_then_read(port: str, t: InterfaceType, sep: str) -> None:
    """A port name of letters and digits that is not a signal of the type reads back as itself, in
    both forms and with every separator."""
    sig = names(t)
    if port in sig:
        assert ports.port_name_problem(port, sig) is not None
        return
    assert ports.port_name_problem(port, sig) is None
    for s in sig:
        assert ports.read_signal(ports.compose(port, s, sig), sig) == (
            Reading(port, s, "prefix", ports.COMPOSE_SEPARATOR),
        )
        assert ports.read_signal(f"{port}{sep}{s}", sig) == (Reading(port, s, "prefix", sep),)
        assert ports.read_signal(f"{s}{sep}{port}", sig) == (Reading(port, s, "suffix", sep),)


@settings(max_examples=300, deadline=None)
@given(port=st.text(min_size=1, max_size=12), t=TYPES)
def test_round_trip_with_any_port_name(port: str, t: InterfaceType) -> None:
    """For any port name the composed name has the intended reading; it is the only one exactly
    when `port_name_problem` finds nothing."""
    sig = names(t)
    unique = True
    for s in sig:
        name = ports.compose(port, s, sig)
        assert name == f"{port}_{s}"
        found = ports.read_signal(name, sig)
        if name in sig:
            assert found == (Reading("", name, "bare", ""),)
            unique = False
            continue
        assert Reading(port, s, "prefix", "_") in found
        unique = unique and len(found) == 1
    assert (ports.port_name_problem(port, sig) is None) == unique


# --- natural order ------------------------------------------------------------------------------


def test_natural_order_of_port_names() -> None:
    given_names = ["RS422_10", "RS422_2", "RS422_1", "AUX", "aux", "RS422_02"]
    assert sorted(given_names, key=ports.natural_key) == [
        "AUX",
        "aux",
        "RS422_1",
        "RS422_02",
        "RS422_2",
        "RS422_10",
    ]


@given(st.lists(st.text(max_size=8), max_size=8))
def test_natural_order_is_a_total_order(items: list[str]) -> None:
    shuffled = items[:]
    random.Random(0).shuffle(shuffled)
    assert sorted(items, key=ports.natural_key) == sorted(shuffled, key=ports.natural_key)


# --- the ports of one connector -----------------------------------------------------------------


def test_named_ports_in_natural_order_and_the_pin_of_each_signal() -> None:
    c = conn(
        *port_pins("RS422_10", RS422, 9),
        *port_pins("RS422_2", RS422, 5),
        *port_pins("RS422_1", RS422, 1),
    )
    found = ports.ports_of(c, RS422)
    assert found.connector_id == "J1" and found.type_id == "rs422"
    assert [p.name for p in found.usable] == ["RS422_1", "RS422_2", "RS422_10"]
    assert found.bare is None and found.ambiguous == () and found.notes == ()
    p2 = found.port("RS422_2")
    assert p2 is not None and p2.usable and p2.form == "prefix" and p2.separator == "_"
    assert [p2.pin_of(s) for s in names(RS422)] == ["5", "6", "7", "8"]
    assert p2.template == "RS422_2_<signal>"
    assert found.port("RS422_3") is None


def test_ports_in_suffix_form_and_with_another_separator() -> None:
    c = conn(("1", "PWR.MAIN"), ("2", "RTN.MAIN"), ("3", "AUX-PWR"), ("4", "AUX-RTN"))
    found = ports.ports_of(c, POWER)
    assert [(p.name, p.form, p.separator, p.template) for p in found.usable] == [
        ("AUX", "prefix", "-", "AUX-<signal>"),
        ("MAIN", "suffix", ".", "<signal>.MAIN"),
    ]


def test_the_bare_port_keeps_repeated_names() -> None:
    c = conn(("1", "TX+"), ("2", "TX-"), ("3", "RX+"), ("4", "RX-"), ("5", "TX+"))
    found = ports.ports_of(c, RS422)
    assert found.bare is not None and not found.bare.named and not found.bare.usable
    assert found.bare.pins_of("TX+") == ("1", "5")
    assert found.bare.pin_of("TX+") is None  # two pins: not one
    assert found.bare.pin_of("RX-") == "4"
    assert found.bare.doubled == ("TX+",) and found.bare.problems == ()
    assert found.usable == () and found.notes == ()


def test_bare_and_named_ports_side_by_side() -> None:
    c = conn(("1", "CANH"), ("2", "CANL"), ("3", "CAN2_CANH"), ("4", "CAN2_CANL"), ("5", "GND"))
    found = ports.ports_of(c, CAN)
    assert found.bare is not None and found.bare.missing == ()
    assert [p.name for p in found.usable] == ["CAN2"]


def test_only_fixed_pins_are_read() -> None:
    c = conn(
        ("1", "RS422_2_TX+"),
        ("2", "RS422_2_TX-"),
        ("3", "RS422_2_RX+"),
        ("4", "RS422_2_RX-", False),
        ("5", "RS422_3_TX+", False),
        ("6", "TX+", False),
    )
    found = ports.ports_of(c, RS422)
    assert [p.name for p in found.named] == ["RS422_2"]
    assert found.named[0].missing == ("RX-",) and found.usable == ()
    assert found.bare is None


def test_an_incomplete_port_is_not_offered_and_names_the_missing_signals() -> None:
    c = conn(("1", "RS422_3_TX+"), ("2", "RS422_3_RX+"))
    found = ports.ports_of(c, RS422)
    (p,) = found.named
    assert p.missing == ("TX-", "RX-") and not p.usable
    assert p.problems == (
        "Port RS422_3 of J1 has no pin for TX- and RX-, so it is not offered for RS-422.",
    )
    assert found.notes == p.problems


def test_two_pins_for_one_signal_in_a_named_port_refuse_the_port() -> None:
    c = conn(*port_pins("RS422_2", RS422, 1), ("9", "RS422_2_TX+"), ("10", "RS422_2_RX-"))
    found = ports.ports_of(c, RS422)
    (p,) = found.named
    assert p.doubled == ("TX+", "RX-") and not p.usable and found.usable == ()
    assert p.pins_of("TX+") == ("1", "9")
    assert p.problems == (
        "Port RS422_2 of J1 has more than one pin for TX+ (pins 1, 9) and RX- (pins 4, 10),"
        " so it is refused.",
    )


def test_two_templates_with_the_same_shown_name_are_both_refused() -> None:
    c = conn(
        *port_pins("RS422_2", RS422, 1),
        *[(str(5 + i), f"{s}.RS422_2") for i, s in enumerate(names(RS422))],
        *port_pins("RS422_3", RS422, 9),
    )
    found = ports.ports_of(c, RS422)
    assert [(p.name, p.template) for p in found.named] == [
        ("RS422_2", "RS422_2_<signal>"),
        ("RS422_2", "<signal>.RS422_2"),
        ("RS422_3", "RS422_3_<signal>"),
    ]
    assert [p.name for p in found.usable] == ["RS422_3"]
    assert found.port("RS422_2") is None
    message = (
        "Pins of J1 write the port RS422_2 in two ways (RS422_2_<signal>, <signal>.RS422_2),"
        " so each is refused. Write the names of one port the same way."
    )
    assert found.named[0].problems == (message,) and found.named[1].problems == (message,)
    assert found.notes == (message,)


def test_an_ambiguous_pin_gets_a_note_and_no_port_contains_it() -> None:
    c = conn(("6", "TX+.TX+"), *port_pins("P1", RS422, 1), ("5", "TX+_RX-"))
    found = ports.ports_of(c, RS422)
    assert [a.pin_id for a in found.ambiguous] == ["5", "6"]
    five, six = found.ambiguous
    assert five.signal == "TX+_RX-" and len(five.readings) == 2
    assert five.message == (
        "Pin 5 of J1: TX+_RX- can be read as TX+ of port RX- or as RX- of port TX+,"
        " so no port uses it. Rename the pin."
    )
    assert six.message == (
        "Pin 6 of J1: TX+.TX+ can be read as TX+ of port TX+ in two ways,"
        " so no port uses it. Rename the pin."
    )
    assert all(pp.pin_id not in ("5", "6") for p in found.named for pp in p.pins)
    assert [p.name for p in found.named] == [p.name for p in found.usable] == ["P1"]
    assert found.notes == (five.message, six.message)


def test_signal_names_with_an_underscore_on_a_connector() -> None:
    c = conn(("1", "CAN_H"), ("2", "CAN_L"), ("3", "CAN_H_2"), ("4", "CAN_L_2"))
    found = ports.ports_of(c, CAN_SPLIT)
    assert found.bare is not None and found.bare.pins_of("CAN_H") == ("1",)
    assert [(p.name, p.form) for p in found.usable] == [("2", "suffix")]
    assert found.usable[0].pin_of("CAN_L") == "4"


def test_pins_of_another_type_are_left_alone() -> None:
    c = conn(("1", "PWR"), ("2", "RTN"), ("3", "SPARE"), ("4", "MAIN_PWR"))
    found = ports.ports_of(c, RS422)
    assert found == ports.ConnectorPorts("J1", "rs422", None, (), ())


@settings(max_examples=50, deadline=None)
@given(seed=st.integers(0, 10_000))
def test_the_result_does_not_depend_on_the_order_of_the_pins(seed: int) -> None:
    pins = [
        *port_pins("RS422_10", RS422, 1),
        *port_pins("RS422_9", RS422, 5, "."),
        ("9", "TX+"),
        ("10", "TX+"),
        ("11", "TX+_RX-"),
        ("12", "RS422_9-RX+"),
        ("13", "RS422_4_TX+"),
    ]
    shuffled = pins[:]
    random.Random(seed).shuffle(shuffled)
    assert ports.ports_of(conn(*shuffled), RS422) == ports.ports_of(conn(*pins), RS422)


def test_the_module_is_pure() -> None:
    """No I/O and no editor: the module imports only the standard library and the model."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(ports.__file__).read_text(encoding="utf-8"))
    imported = {
        (n.module or "") if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(tree)
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in n.names
    }
    assert imported <= {"__future__", "re", "collections.abc", "dataclasses", "typing", "model"}
