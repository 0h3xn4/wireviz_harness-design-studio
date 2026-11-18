# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The nets of a harness: the pins that its wires join (format 3, M6a; section 6.3 of the design of
2.3.0, `docs/ait/DESIGN_2.3_BRANCHING.md`).

    nets = harness_nets(h)          # every net of the harness, by its first wire
    net = net_of_wire(h)["W001-002"]
    net.ends                        # (connector, pin) of each end: a pin not on a splice
    net.splices                     # the splices it runs through: ("W001-X1",)
    end_pairs(net)                  # each pair of ends once, in order
    path_wires(h, a, b)             # the wires between two pins of one net

A **net** is a set of pins joined by wires: two pins are in one net when a wire joins them, and a
pin joins every wire that ends on it. A splice (a connector of role `splice`) is the one place where
several wires end on one pin by design: each of its pins is a node that joins the wires on it. A
pin of any other connector is an **end** of its net. In a harness without a splice, and without two
wires on one pin, every net is one wire and its two ends.

The independent verifier (`core/verify.py`) and the output check (`core/outputs/verify.py`) each
work the nets out with their own code, and `tests/test_nets.py` compares the three on random
harnesses. Pure functions of one harness; nothing here reads the project.
"""

import re
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from .model import Connector, Harness
from .model.physical import SPLICE_ROLE

Pin = tuple[str, str]  # (connector ID, pin ID)


def _natural(text: str) -> tuple[tuple[int, int | str], ...]:
    """The order a person reads IDs in: `2` before `10`, `W001-P2` before `W001-P10`."""
    return tuple(
        (0, int(x)) if n % 2 else (1, x) for n, x in enumerate(re.split(r"(\d+)", text)) if x
    )


def pin_order(
    pin: Pin,
) -> tuple[tuple[tuple[int, int | str], ...], tuple[tuple[int, int | str], ...]]:
    """The order of the pins of a net: by connector, then by pin, each in natural order."""
    return _natural(pin[0]), _natural(pin[1])


def is_splice(c: Connector) -> bool:
    """True for a splice: a connector of the harness whose pins are nodes that join wires."""
    return c.role == SPLICE_ROLE


def splice_ids(h: Harness) -> set[str]:
    """The IDs of the splices of a harness."""
    return {c.id for c in h.connectors if c.role == SPLICE_ROLE}


def has_splices(h: Harness) -> bool:
    """True for a harness with at least one splice: only such a harness has the splice outputs (a
    test per pair of ends of a net, the column *Via* of the wire list, the splice block of the build
    workbook), so every other harness keeps its bytes."""
    return any(c.role == SPLICE_ROLE for c in h.connectors)


@dataclass(frozen=True)
class Net:
    """One net of a harness: its pins and wires, its ends (the pins not on a splice) and the
    splices it runs through, each sorted (`pin_order`, natural order of IDs)."""

    pins: tuple[Pin, ...]
    wires: tuple[str, ...]
    ends: tuple[Pin, ...]
    splices: tuple[str, ...]


def harness_nets(h: Harness) -> list[Net]:
    """Every net of the harness (see the module), in the order of the first wire of each by ID.
    Only pins that a wire ends on are in a net; a pin without a wire is in none."""
    parent: dict[Pin, Pin] = {}

    def find(x: Pin) -> Pin:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for w in h.wires:
        a, b = find((w.from_connector, w.from_pin)), find((w.to_connector, w.to_pin))
        if a != b:
            parent[max(a, b)] = min(a, b)
    splices = splice_ids(h)
    pins: dict[Pin, list[Pin]] = {}
    wires: dict[Pin, list[str]] = {}
    for pin in list(parent):
        pins.setdefault(find(pin), []).append(pin)
    for w in h.wires:
        wires.setdefault(find((w.from_connector, w.from_pin)), []).append(w.id)
    out = []
    for root, members in pins.items():
        ordered = tuple(sorted(members, key=pin_order))
        out.append(
            Net(
                pins=ordered,
                wires=tuple(sorted(wires.get(root, []))),
                ends=tuple(p for p in ordered if p[0] not in splices),
                splices=tuple(sorted({p[0] for p in ordered if p[0] in splices}, key=_natural)),
            )
        )
    return sorted(out, key=lambda n: n.wires)


def net_of_wire(h: Harness) -> dict[str, Net]:
    """Wire ID -> the net it belongs to."""
    return {wid: net for net in harness_nets(h) for wid in net.wires}


def end_pairs(net: Net) -> list[tuple[Pin, Pin]]:
    """Each pair of ends of a net once, the first end before the second in the net's order: the
    connections a continuity test proves."""
    ends = net.ends
    return [(ends[i], ends[j]) for i in range(len(ends)) for j in range(i + 1, len(ends))]


def path_wires(
    h: Harness, a: Pin, b: Pin, wire_ids: Iterable[str] | None = None
) -> tuple[str, ...]:
    """The wires on the shortest path from pin `a` to pin `b` through the wires of the harness (or
    of `wire_ids`), in the order they are passed; a tie goes to the wire with the smaller ID.
    Empty when they are not joined."""
    keep = None if wire_ids is None else set(wire_ids)
    graph: dict[Pin, list[tuple[str, Pin]]] = {}
    for w in sorted(h.wires, key=lambda x: x.id):
        if keep is not None and w.id not in keep:
            continue
        x, y = (w.from_connector, w.from_pin), (w.to_connector, w.to_pin)
        graph.setdefault(x, []).append((w.id, y))
        graph.setdefault(y, []).append((w.id, x))
    came: dict[Pin, tuple[str, Pin] | None] = {a: None}
    todo = deque([a])
    while todo:
        node = todo.popleft()
        if node == b:
            break
        for wid, nxt in graph.get(node, []):
            if nxt not in came:
                came[nxt] = (wid, node)
                todo.append(nxt)
    if b not in came or a == b:
        return ()
    path: list[str] = []
    node = b
    while (step := came[node]) is not None:
        path.append(step[0])
        node = step[1]
    return tuple(reversed(path))


__all__ = [
    "Net",
    "Pin",
    "end_pairs",
    "harness_nets",
    "has_splices",
    "is_splice",
    "net_of_wire",
    "path_wires",
    "pin_order",
    "splice_ids",
]
