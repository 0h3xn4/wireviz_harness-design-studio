# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Which connector of a device carries an interface when the tool chooses (S3b, assumption
A-CONNECTOR-CHOICE).

The model of the tool until D-191 was the **first free connector** of the device that carries the
interface type, in the order of the connector IDs (`first_free`, the default). Two alternatives are
selectable with the setting `model.connector_choice`; both look at the same candidates and differ
only in the order. The candidates come in two tiers (D-237): first the free connectors that carry
the type (`edit.free_connectors`), as before 2.1.0; only when none is free, the connectors with a
fixed pinout that have a free complete port of the type (`edit.shared_connectors`). A connector
whose pins the device leaves free is never shared by the tool's choice. The orders:

- `fewest_spare_pins`: best fit. A candidate *fits* when it has at least as many pins available as
  the interface has signals; of those, the one with the fewest pins left over comes first;
- `most_spare_pins`: the opposite, the fitting candidate with the most pins left over comes first,
  so the small connectors stay free for later.

Candidates that do not fit follow in ID order (the choice then fails later, in the pin allocation,
with the message that says so, as it always did). A tie is broken by the connector ID, so the
choice is the same every time. The ranking is one pure function (`ranked`), used by the editing
operations that choose a connector and by the explanation, so the two cannot disagree.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from harness_design_studio.core import settings
from harness_design_studio.core.model import Connector, InterfaceType, Project
from harness_design_studio.core.ports import Port, ports_of

METHODS = ("first_free", "fewest_spare_pins", "most_spare_pins")
DEFAULT_METHOD = "first_free"
METHOD_TEXT = {
    "first_free": "the first free connector that carries the type, in ID order",
    "fewest_spare_pins": (
        "the free connector that carries the type and has the fewest pins left over once the "
        "interface is on it (best fit); ties by ID"
    ),
    "most_spare_pins": (
        "the free connector that carries the type and has the most pins left over once the "
        "interface is on it (the small connectors stay free); ties by ID"
    ),
}


def method(project: Project) -> str:
    """The connector choice in force: the one function the editing operations and `explain` call."""
    value = settings.effective(project, "model", "connector_choice").value
    return str(value) if value in METHODS else DEFAULT_METHOD


@dataclass(frozen=True)
class Fit:
    """How well an interface fits a connector."""

    connector_id: str
    pins: int  # all pins of the connector
    available: int  # the pins an interface could take: not locked, not typed in by a person
    needed: int  # the signals of the interface type
    fits: bool
    ports: int = 0  # the free complete named ports of the type (a fixed pinout only, D-237)

    @property
    def spare(self) -> int:
        return self.available - self.needed


def available_pins(connector: Connector, taken: Collection[str] = ()) -> int:
    """The pins an interface may take. On a connector with a fixed pinout (the device design names
    every pin) these are the named, unlocked pins; otherwise every pin that is not locked and has
    no signal typed in by a person (a pin that carries a generated assignment counts: generation
    rewrites it). The pins in `taken` are held by the other interfaces on the connector (the dry
    run of `edit.taken_pins`) and are not counted."""
    if any(p.fixed and p.signal for p in connector.pins):
        return sum(
            1 for p in connector.pins if p.fixed and p.signal and not p.locked and p.id not in taken
        )
    return sum(
        1
        for p in connector.pins
        if not p.locked and (p.interface_id is not None or not p.signal) and p.id not in taken
    )


def free_ports(
    connector: Connector, itype: InterfaceType, taken: Collection[str] = ()
) -> tuple[Port, ...]:
    """The complete named ports of the type whose pins are neither locked nor in `taken`, in
    natural order of their names (`core/ports.py`). Repeated bare names never count as a port."""
    locked = {p.id for p in connector.pins if p.locked}
    return tuple(
        port
        for port in ports_of(connector, itype).usable
        if not any(pp.pin_id in locked or pp.pin_id in taken for pp in port.pins)
    )


def fit_of(connector: Connector, itype: InterfaceType | None, taken: Collection[str] = ()) -> Fit:
    """How the interface fits: on a fixed pinout it fits when the free pins hold every signal of
    the type by its exact name, or when a complete named port of the type is free (`ports`)."""
    needed = len(itype.signals) if itype is not None else 0
    available = available_pins(connector, taken)
    ports = 0
    if itype is not None and any(p.fixed and p.signal for p in connector.pins):
        named = {
            p.signal
            for p in connector.pins
            if p.fixed and p.signal and not p.locked and p.id not in taken
        }
        ports = len(free_ports(connector, itype, taken))
        fits = all(s.name in named for s in itype.signals) or ports > 0
    else:
        fits = available >= needed
    return Fit(connector.id, len(connector.pins), available, needed, fits, ports)


def ranked(
    name: str,
    candidates: Sequence[Connector],
    itype: InterfaceType | None,
    taken: Mapping[str, Collection[str]] | None = None,
) -> list[Connector]:
    """The candidates in the order of preference of the model `name`; the first is chosen. `taken`
    gives, per connector, the pins the interfaces already on it hold (tier 2 of the choice)."""
    if name not in METHODS:
        name = DEFAULT_METHOD
    by_id = sorted(candidates, key=lambda c: c.id)
    if name == "first_free":
        return by_id
    fits = {c.id: fit_of(c, itype, (taken or {}).get(c.id, ())) for c in by_id}
    sign = 1 if name == "fewest_spare_pins" else -1

    def key(c: Connector) -> tuple[bool, int, str]:
        f = fits[c.id]
        return (not f.fits, sign * f.spare if f.fits else 0, c.id)

    return sorted(by_id, key=key)
