# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Ports: which fixed pins of a connector form one port of an interface type (2.1.0, D-237).

A port is a naming convention on `Pin.signal`, not a field (`docs/ait/DESIGN_2.1_PORTS.md`,
sections 2 and 3). For an interface type T with signal names N(T), the signal s of a pin is

- **bare** when s is in N(T): the pin belongs to the unnamed port (the rule of 2.0.1). A name in
  N(T) is never read as a port, so every project that worked at 2.0.1 reads the same;
- in the **named port** P when s is `P<sep>t` (prefix form) or `t<sep>P` (suffix form), with t in
  N(T), sep one of `_`, `.`, `-` and P not empty. The port is shown as P.

Matching is exact and case-sensitive. A name that can be read in more than one way is ambiguous:
no port uses it, and the tool never guesses. Only pins with `fixed` set are read. The module is
pure: no I/O, no editor; every result is sorted, so the same pins always give the same ports.
"""

import re
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from .model import Connector, InterfaceType

Form = Literal["bare", "prefix", "suffix"]
FORMS: tuple[Form, ...] = ("bare", "prefix", "suffix")
SEPARATORS: tuple[str, ...] = ("_", ".", "-")
# `compose` writes `PORT_SIGNAL` (`RS422_2_TX+`): the form a KiCad netlist and most pinouts use.
COMPOSE_SEPARATOR = "_"

NaturalKey = tuple[tuple[tuple[int, int, str], ...], str]


def natural_key(name: str) -> NaturalKey:
    """Names in the order a person reads them: `RS422_2` before `RS422_10`. Letters are compared
    without case first and the exact text breaks a tie, so the order is total and stable."""
    parts = re.split(r"([0-9]+)", name)  # the odd places hold the runs of digits
    key = tuple(
        (0, int(p), "") if i % 2 else (1, 0, p.casefold()) for i, p in enumerate(parts) if p
    )
    return key, name


@dataclass(frozen=True, order=True)
class Reading:
    """One way to read a signal name: signal `signal` of port `port` ("" for the bare port)."""

    port: str
    signal: str
    form: Form
    separator: str  # "" for a bare name

    def text(self) -> str:
        """The reading in plain words, for a message."""
        return f"{self.signal} of port {self.port}" if self.port else f"the signal {self.signal}"


def read_signal(name: str, signals: Iterable[str]) -> tuple[Reading, ...]:
    """Every way `name` reads against the signal names `signals` of a type, sorted. No reading: the
    name is no signal of the type. One: the pin's port and signal. Two or more: ambiguous."""
    names = set(signals)
    if name in names:
        return (Reading("", name, "bare", ""),)
    found: set[Reading] = set()
    for t in names:
        if not t:
            continue
        for sep in SEPARATORS:
            tail = sep + t
            if len(name) > len(tail) and name.endswith(tail):
                found.add(Reading(name[: -len(tail)], t, "prefix", sep))
            head = t + sep
            if len(name) > len(head) and name.startswith(head):
                found.add(Reading(name[len(head) :], t, "suffix", sep))
    return tuple(sorted(found))


def compose(port: str, signal: str, signals: Collection[str] = ()) -> str:
    """The signal name of `signal` in port `port`: `RS422_2` and `TX+` give `RS422_2_TX+`. A name
    that already starts with the port and a separator is kept as it is (`RS422_2_TX+`), unless it
    is one of `signals`, the bare signal names of the type (`CAN` and `CAN_H` give `CAN_CAN_H`).
    No port: the signal as it is."""
    if not port:
        return signal
    if signal not in signals and any(
        len(signal) > len(port) + len(sep) and signal.startswith(port + sep) for sep in SEPARATORS
    ):
        return signal
    return f"{port}{COMPOSE_SEPARATOR}{signal}"


def _count(n: int) -> str:
    return {2: "two", 3: "three", 4: "four"}.get(n, str(n))


def _and(items: Sequence[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _readings_text(readings: Sequence[Reading]) -> str:
    """`TX+ of port RX- or as RX- of port TX+`; `TX+ of port TX+ in two ways` when alike."""
    texts = list(dict.fromkeys(r.text() for r in readings))
    if len(texts) == 1:
        return f"{texts[0]} in {_count(len(readings))} ways"
    return " or as ".join(texts)


def port_name_problem(port: str, signals: Sequence[str]) -> str | None:
    """Why `port` cannot be used as a port name for a type with these signal names, or None. It
    can be used when the composed name of every signal reads back as that signal of that port
    only."""
    if not port:
        return "A port needs a name."
    for t in signals:
        name = compose(port, t, signals)
        found = read_signal(name, signals)
        meant = Reading(port, t, "prefix", COMPOSE_SEPARATOR)
        if found == (meant,):
            continue
        if found and found[0].form == "bare":
            return f"The port name {port} cannot be used: {name} is a signal of the type itself."
        ordered = [meant, *(r for r in found if r != meant)]
        return (
            f"The port name {port} cannot be used: {name} can be read as {_readings_text(ordered)}."
        )
    return None


@dataclass(frozen=True)
class PortPin:
    """A pin of a port and the signal of the type it carries."""

    signal: str
    pin_id: str


@dataclass(frozen=True)
class Port:
    """The pins of one port of a connector for one interface type. The bare port has the name ""."""

    name: str
    form: Form
    separator: str
    pins: tuple[PortPin, ...]  # in the order of the type's signals, then in pin order
    missing: tuple[str, ...]  # signals of the type with no pin, in the type's order
    doubled: tuple[str, ...]  # signals with more than one pin, in the type's order
    problems: tuple[str, ...]  # why a named port cannot be used, in plain words

    @property
    def named(self) -> bool:
        return bool(self.name)

    @property
    def usable(self) -> bool:
        """A named port with exactly one pin for each signal of the type and no other problem."""
        return self.named and not self.problems

    @property
    def template(self) -> str:
        """How the port writes its names: `RS422_2_<signal>`, `<signal>.RS422_2`, `<signal>`."""
        if self.form == "prefix":
            return f"{self.name}{self.separator}<signal>"
        if self.form == "suffix":
            return f"<signal>{self.separator}{self.name}"
        return "<signal>"

    def pins_of(self, signal: str) -> tuple[str, ...]:
        """The pins that carry `signal` in this port, in pin order."""
        return tuple(p.pin_id for p in self.pins if p.signal == signal)

    def pin_of(self, signal: str) -> str | None:
        """The one pin that carries `signal` in this port; None for no pin or more than one."""
        found = self.pins_of(signal)
        return found[0] if len(found) == 1 else None


@dataclass(frozen=True)
class AmbiguousPin:
    """A fixed pin whose name reads in more than one way: no port uses it."""

    pin_id: str
    signal: str
    readings: tuple[Reading, ...]
    message: str


@dataclass(frozen=True)
class ConnectorPorts:
    """The ports of one connector for one interface type."""

    connector_id: str
    type_id: str
    bare: Port | None  # the unnamed port; None when no fixed pin has a bare signal name
    named: tuple[Port, ...]  # natural order of the names; refused ports included
    ambiguous: tuple[AmbiguousPin, ...]  # in pin order

    @property
    def usable(self) -> tuple[Port, ...]:
        """The complete named ports that are not refused, in natural order of their names."""
        return tuple(p for p in self.named if p.usable)

    def port(self, name: str) -> Port | None:
        """The named port shown as `name`; None when there is none, or two (both refused)."""
        found = [p for p in self.named if p.name == name]
        return found[0] if len(found) == 1 else None

    @property
    def notes(self) -> tuple[str, ...]:
        """Every message once: the ambiguous pins, then the problems of the ports in order."""
        out = [a.message for a in self.ambiguous]
        out += [m for p in self.named for m in p.problems]
        return tuple(dict.fromkeys(out))


def _port(
    name: str,
    form: Form,
    sep: str,
    found: Sequence[PortPin],
    order: Sequence[str],
    connector_id: str,
    type_name: str,
) -> Port:
    pins = tuple(sorted(found, key=lambda p: (order.index(p.signal), natural_key(p.pin_id))))
    count = {t: sum(1 for p in pins if p.signal == t) for t in order}
    missing = tuple(t for t in order if count[t] == 0)
    doubled = tuple(t for t in order if count[t] > 1)
    problems: list[str] = []
    if name and missing:
        problems.append(
            f"Port {name} of {connector_id} has no pin for {_and(missing)}, so it is not offered"
            f" for {type_name}."
        )
    if name and doubled:
        each = [f"{t} (pins {', '.join(p.pin_id for p in pins if p.signal == t)})" for t in doubled]
        problems.append(
            f"Port {name} of {connector_id} has more than one pin for {_and(each)},"
            " so it is refused."
        )
    return Port(name, form, sep, pins, missing, doubled, tuple(problems))


def ports_of(connector: Connector, itype: InterfaceType) -> ConnectorPorts:
    """Group the fixed pins of `connector` into the ports of `itype`. Pins that are not fixed, have
    no signal or carry no signal of the type are left out. A named port is usable when each signal
    of the type has exactly one pin; an incomplete port, a port with two pins for one signal and
    two ports written in different ways under one shown name are not, and say why (`problems`).
    Locked pins and pins that an interface uses are read like the others: the caller decides
    which ports are free (`Pin.locked`, `Pin.interface_id`)."""
    order = list(dict.fromkeys(s.name for s in itype.signals))
    groups: dict[tuple[str, Form, str], list[PortPin]] = {}
    ambiguous: list[AmbiguousPin] = []
    for pin in connector.pins:
        if not pin.fixed or not pin.signal:
            continue
        readings = read_signal(pin.signal, order)
        if len(readings) == 1:
            r = readings[0]
            groups.setdefault((r.port, r.form, r.separator), []).append(PortPin(r.signal, pin.id))
        elif readings:
            ambiguous.append(
                AmbiguousPin(
                    pin.id,
                    pin.signal,
                    readings,
                    f"Pin {pin.id} of {connector.id}: {pin.signal} can be read as"
                    f" {_readings_text(readings)}, so no port uses it. Rename the pin.",
                )
            )
    bare_pins = groups.pop(("", "bare", ""), None)
    bare = (
        _port("", "bare", "", bare_pins, order, connector.id, itype.name)
        if bare_pins is not None
        else None
    )
    keys = sorted(
        groups, key=lambda k: (natural_key(k[0]), FORMS.index(k[1]), SEPARATORS.index(k[2]))
    )
    ports = [_port(n, f, s, groups[(n, f, s)], order, connector.id, itype.name) for n, f, s in keys]
    shown: dict[str, list[Port]] = {}
    for p in ports:
        shown.setdefault(p.name, []).append(p)
    named: list[Port] = []
    for p in ports:
        alike = shown[p.name]
        if len(alike) > 1:
            clash = (
                f"Pins of {connector.id} write the port {p.name} in {_count(len(alike))} ways"
                f" ({', '.join(q.template for q in alike)}), so each is refused. Write the names"
                " of one port the same way."
            )
            p = replace(p, problems=(clash, *p.problems))
        named.append(p)
    ambiguous.sort(key=lambda a: natural_key(a.pin_id))
    return ConnectorPorts(connector.id, itype.id, bare, tuple(named), tuple(ambiguous))


def is_signal_of(name: str, types: Iterable[InterfaceType]) -> bool:
    """True when `name` reads as one signal of one of `types`: its exact name, or the name of that
    signal in one port (`RS422_2_TX+` is the RS-422 signal TX+). A name that reads in more than one
    way for a type is not a signal of that type: no port uses it. The imports use this to say which
    signals no interface type has."""
    return any(len(read_signal(name, [s.name for s in t.signals])) == 1 for t in types)
