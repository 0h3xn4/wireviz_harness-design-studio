# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The current of a wire (format 5, part B of the design of 5.0.0, `docs/ait/DESIGN_5.0_FORMAT_5.md`
section 5.2; REQ-WIRE-10).

    currents = wire_currents(project, h)    # wire ID -> WireCurrent
    currents["W003-002"].value              # 2.0 (amperes), or None: not known
    currents["W003-002"].source             # "pins", "interface" or "" (not known)
    net_currents(project, h)                # each net of the harness and what was found in it

A device pin may state the current through its contact (`Pin.current_a`, from the ICD). The current
of a wire is worked out from the pin currents of its net (`core/nets.py`) when every end of the net
has one and they add up; else it is the current of the wire's interface, as in 4.4.0; else it is
not known. Nothing here invents a current (D-11): a missing value stays missing.

1. **The current of each end** of a net: the pin current of the device pin the end is (a wire on a
   device connector) or mates with (a cable connector's `mates_with` and the pin of the same ID).
   An end on a splice is no end (`Net.ends`); an end on a loose end or a test connector, or on a
   pin without a current, has none.
2. **When every end of the net has a current** (and the net has two ends or more) **and they add
   up** (the largest equals the sum of the others within the tolerance of `sizing.exceeds`;
   A-ONE-SOURCE): the wires between the same two pins are one branch. If the branches form a tree,
   the current of a branch is the smaller of the sums of the end currents on its two sides; a
   branch of k wires shares it equally when the k wires have one known gauge and one known length
   (A-PARALLEL-SHARE), else its wires are not worked out. If the branches do not form a tree, no
   wire of the net is worked out. A net whose currents do not add up is not worked out either; the
   codes `current_unbalanced` and `current_not_worked_out` of `check` say so
   (`integrity.current_issues`).
3. **Else** the wire takes the current of its interface (`InterfaceInstance.max_current_a`), as in
   4.4.0; else it has none.

In a project with no pin current step 2 never runs and every wire gets what 4.4.0 gives it, without
the nets being worked out (`tests/test_currents_compat_440.py` compares the rules that read it with
a word-for-word copy of 4.4.0). Generate does not read pin currents (F5): it sizes a wire from its
interface's current. Pure functions of the project; nothing here reads a file.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from .generate.lengths import end_depths, wire_length
from .generate.sizing import exceeds
from .model import Connector, Harness, Pin, Project, Wire
from .nets import Net, harness_nets, pin_order

Source = Literal["pins", "interface", ""]
# What was found in a net (`NetCurrents.status`)
WORKED = "worked"  # every end has a current, they add up and the wires were worked out
PARTIAL = "partial"  # not every end has a current: the wires take their interface's current
UNBALANCED = "unbalanced"  # every end has a current, but they do not add up
LOOP = "loop"  # the branches do not form a tree
UNEQUAL = "unequal"  # a branch of parallel wires that differ (or whose gauge or length is unknown)
NOT_WORKED_OUT = frozenset({LOOP, UNEQUAL})
ROLES_WITHOUT_CURRENT = frozenset({"test", "loose", "splice"})

PinKey = tuple[str, str]  # (connector ID, pin ID) of a pin of the harness


@dataclass(frozen=True)
class EndCurrent:
    """One end of a net and the device pin behind it: `box` and `pin` name the device pin (empty
    when the end has none), `current` its current (None when it states none)."""

    end: PinKey
    box: str
    pin: str
    current: float | None

    @property
    def label(self) -> str:
        """`PCDU1-J01.1`: the device pin, or the harness pin when there is none."""
        return f"{self.box}.{self.pin}" if self.box else f"{self.end[0]}.{self.end[1]}"


@dataclass(frozen=True)
class Branch:
    """The wires between the same two pins of a net, and the end currents on each side."""

    a: PinKey
    b: PinKey
    wires: tuple[str, ...]
    side_a: float  # the sum of the end currents on the side of `a`
    side_b: float  # ... on the side of `b`

    @property
    def current(self) -> float:
        """The current through the branch: the smaller of the two sums (the source's side holds
        the source and the loads beyond it, so it is the larger)."""
        return min(self.side_a, self.side_b)


@dataclass(frozen=True)
class WireCurrent:
    """The current of one wire: `value` in amperes or None (not known), where it came from
    (`source`: `pins`, `interface` or empty), the words of its reason, and for a current from the
    pins the ends of its net and its branch."""

    value: float | None
    source: Source
    reason: str
    ends: tuple[EndCurrent, ...] = ()
    branch: Branch | None = None
    interface_id: str = ""

    @property
    def share(self) -> int:
        """How many parallel wires share the current of the branch (1 for a wire on its own)."""
        return len(self.branch.wires) if self.branch is not None else 1


@dataclass(frozen=True)
class NetCurrents:
    """A net of a harness and what was found in it (`status`, one of the words above)."""

    net: Net
    ends: tuple[EndCurrent, ...]
    status: str
    detail: str = ""  # for LOOP and UNEQUAL: what kept the wires from being worked out
    branches: tuple[Branch, ...] = ()


def has_pin_currents(project: Project) -> bool:
    """True when some pin of a device connector of the project states a current."""
    return any(p.current_a is not None for c in project.connectors.values() for p in c.pins)


def pin_current(project: Project, connector_id: str, pin_id: str) -> float | None:
    """The current a device pin states, or None."""
    c = project.connectors.get(connector_id)
    pin = _pin(c, pin_id) if c is not None else None
    return pin.current_a if pin is not None else None


def _pin(c: Connector, pin_id: str) -> Pin | None:
    return next((p for p in c.pins if p.id == pin_id), None)


def _device_pin(project: Project, h: Harness, end: PinKey) -> EndCurrent:
    """The device pin an end of a net is or mates with, and its current."""
    cid, pid = end
    c = next((x for x in h.connectors if x.id == cid), None) or project.connectors.get(cid)
    box: Connector | None = None
    if c is not None and c.unit_id is not None:
        box = c
    elif c is not None and c.role not in ROLES_WITHOUT_CURRENT and c.mates_with:
        box = project.connectors.get(c.mates_with)
    pin = _pin(box, pid) if box is not None else None
    if box is None or pin is None:
        return EndCurrent(end, "", "", None)
    return EndCurrent(end, box.id, pin.id, pin.current_a)


def adds_up(currents: Sequence[float]) -> bool:
    """The largest current equals the sum of the others, within float rounding (A-ONE-SOURCE)."""
    if len(currents) < 2:
        return False
    largest = max(currents)
    rest = sum(currents) - largest
    return not exceeds(largest, rest) and not exceeds(rest, largest)


def _interface_current(project: Project, w: Wire) -> WireCurrent:
    i = project.interfaces.get(w.interface_id or "")
    if i is not None and i.max_current_a is not None:
        return WireCurrent(
            i.max_current_a, "interface", f"interface {i.id}: Max current", interface_id=i.id
        )
    if i is not None:
        return WireCurrent(None, "", f"interface {i.id} has no Max current", interface_id=i.id)
    return WireCurrent(None, "", "the wire has no interface")


def _same(values: Iterable[float | int | None]) -> bool:
    seen = [None if v is None else round(float(v), 9) for v in values]
    return None not in seen and len(set(seen)) == 1


def _branches(
    project: Project, h: Harness, net: Net, ends: tuple[EndCurrent, ...]
) -> tuple[str, str, tuple[Branch, ...]]:
    """(status, detail, branches) of a net whose end currents add up: WORKED with every branch, or
    LOOP or UNEQUAL with the reason."""
    in_net = set(net.wires)
    wires = {w.id: w for w in h.wires if w.id in in_net}
    groups: dict[tuple[PinKey, PinKey], list[str]] = {}
    for wid in net.wires:
        w = wires[wid]
        a, b = (w.from_connector, w.from_pin), (w.to_connector, w.to_pin)
        key = (a, b) if pin_order(a) <= pin_order(b) else (b, a)
        groups.setdefault(key, []).append(wid)
    nodes = set(net.pins)
    if any(a == b for a, b in groups) or len(groups) != len(nodes) - 1:
        return LOOP, "its wires form a loop", ()
    adjacent: dict[PinKey, list[tuple[PinKey, PinKey, PinKey]]] = {}
    for key in groups:
        a, b = key
        adjacent.setdefault(a, []).append((b, a, b))
        adjacent.setdefault(b, []).append((a, a, b))
    load = {e.end: e.current or 0.0 for e in ends}

    def side(start: PinKey, without: tuple[PinKey, PinKey]) -> float:
        total, seen, todo = 0.0, {start}, [start]
        while todo:
            node = todo.pop()
            total += load.get(node, 0.0)
            for nxt, a, b in adjacent.get(node, []):
                if (a, b) != without and nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        return total

    ends_m = end_depths(project, h)
    out: list[Branch] = []
    for (a, b), ids in sorted(groups.items(), key=lambda kv: kv[1][0]):
        ids = sorted(ids)
        if len(ids) > 1:
            parallel = [wires[i] for i in ids]
            if not (
                _same(w.gauge_awg for w in parallel)
                and _same(wire_length(h, w, ends_m) for w in parallel)
            ):
                return (
                    UNEQUAL,
                    f"the parallel wires {_and(ids)} between {a[0]}.{a[1]} and {b[0]}.{b[1]} do "
                    "not have one known gauge and one known length",
                    (),
                )
        out.append(Branch(a, b, tuple(ids), side(a, (a, b)), side(b, (a, b))))
    return WORKED, "", tuple(out)


def net_currents(project: Project, h: Harness) -> list[NetCurrents]:
    """Every net of the harness (`nets.harness_nets`) with the currents of its ends and what was
    found in it (see the module)."""
    out: list[NetCurrents] = []
    for net in harness_nets(h):
        ends = tuple(_device_pin(project, h, end) for end in net.ends)
        currents = [e.current for e in ends]
        if len(ends) < 2 or any(c is None for c in currents):
            out.append(NetCurrents(net, ends, PARTIAL))
            continue
        if not adds_up([c for c in currents if c is not None]):
            out.append(NetCurrents(net, ends, UNBALANCED))
            continue
        status, detail, branches = _branches(project, h, net, ends)
        out.append(NetCurrents(net, ends, status, detail, branches))
    return out


def wire_currents(project: Project, h: Harness) -> dict[str, WireCurrent]:
    """The current of every wire of the harness, by wire ID (see the module). Without a pin current
    in the project, the current of each wire's interface, as in 4.4.0."""
    if not has_pin_currents(project):
        return {w.id: _interface_current(project, w) for w in h.wires}
    by_id = {w.id: w for w in h.wires}
    out: dict[str, WireCurrent] = {}
    for nc in net_currents(project, h):
        if nc.status == PARTIAL:
            for wid in nc.net.wires:
                out[wid] = _interface_current(project, by_id[wid])
            continue
        if nc.status != WORKED:
            why = (
                "the pin currents of its net do not add up"
                if nc.status == UNBALANCED
                else f"the currents of its net were not worked out: {nc.detail}"
            )
            for wid in nc.net.wires:
                out[wid] = WireCurrent(None, "", why, nc.ends)
            continue
        for branch in nc.branches:
            value = branch.current / len(branch.wires)
            for wid in branch.wires:
                out[wid] = WireCurrent(value, "pins", pins_reason(nc.ends, branch), nc.ends, branch)
    for w in h.wires:  # (every wire is in a net; kept for a wire the nets could not place)
        out.setdefault(w.id, _interface_current(project, w))
    return out


def wire_current(project: Project, h: Harness, w: Wire) -> WireCurrent:
    """The current of one wire of the harness (`wire_currents`)."""
    if not has_pin_currents(project):
        return _interface_current(project, w)
    return wire_currents(project, h)[w.id]


def current_value(project: Project, h: Harness, w: Wire) -> float | None:
    """The current of one wire in amperes, or None."""
    return wire_current(project, h, w).value


def _g(x: float) -> str:
    return f"{x:g}"


def _and(items: Sequence[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def pins_text(ends: Sequence[EndCurrent]) -> str:
    """`OBC1-J01.1, .2 and .3`: the device pins of the ends, a pin on the connector of the one
    before it written with its pin only."""
    parts: list[str] = []
    last = ""
    for e in ends:
        box = e.box or e.end[0]
        pid = e.pin or e.end[1]
        parts.append(f".{pid}" if box == last else f"{box}.{pid}")
        last = box
    return _and(parts)


def currents_text(ends: Sequence[EndCurrent]) -> str:
    """`6 A at PCDU1-J01.1; 2 A, 2 A and 1.5 A at OBC1-J01.1, .2 and .3`: the largest current
    first, then the others, each with its pins."""
    known = [e for e in ends if e.current is not None]
    if not known:
        return ""
    at = max(range(len(known)), key=lambda k: (known[k].current or 0.0, -k))  # the first largest
    first = known[at]
    rest = [e for k, e in enumerate(known) if k != at]
    text = f"{_g(first.current or 0.0)} A at {pins_text([first])}"
    if rest:
        amps = _and([f"{_g(e.current or 0.0)} A" for e in rest])
        text += f"; {amps} at {pins_text(rest)}"
    return text


def pins_reason(ends: Sequence[EndCurrent], branch: Branch) -> str:
    """The reason of a current worked out from the pins, in words."""
    a = f"{branch.a[0]}.{branch.a[1]}"
    b = f"{branch.b[0]}.{branch.b[1]}"
    text = (
        f"the pin currents of its net ({currents_text(ends)}): between {a} and {b} the smaller "
        f"of {_g(branch.side_a)} A and {_g(branch.side_b)} A"
    )
    if len(branch.wires) > 1:
        text += f", shared by {len(branch.wires)} parallel wires"
    return text


__all__ = [
    "LOOP",
    "NOT_WORKED_OUT",
    "PARTIAL",
    "UNBALANCED",
    "UNEQUAL",
    "WORKED",
    "Branch",
    "EndCurrent",
    "NetCurrents",
    "WireCurrent",
    "adds_up",
    "current_value",
    "currents_text",
    "has_pin_currents",
    "net_currents",
    "pin_current",
    "pins_reason",
    "pins_text",
    "wire_current",
    "wire_currents",
]
