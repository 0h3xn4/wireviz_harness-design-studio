# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Splices of a harness a person made (format 3, M6a; section 6.2 of the design of 2.3.0,
`docs/ait/DESIGN_2.3_BRANCHING.md`).

    ops, sid = plan_add_splice(project, "W003", "EX-SPLICE-1")      # W003-X1, one node "1"
    ops, wid = plan_splice_wire(project, "W003-001", "W003-X1")     # W003-001 cut at node 1
    ops = plan_delete_splice(project, "W003", "W003-X1")            # two wires on a node: joined

A splice is a connector of the harness with the role `splice` and a library part of category
`splice`; it plugs into nothing and belongs to no device. Each pin is a node: every wire that ends
on it is joined to the others there (`core/nets.py`). How is the node's `termination`: `crimp` for
a crimp splice, `solder` for a solder sleeve. A wire is added to a node with `wires.plan_add_wire`,
like to any pin: a node takes several wires.

Pure functions, no Qt: each returns the `Op`s that `History.execute` runs as one undo step (and one
row of the journal), or raises `EditError` with a plain sentence. A harness that Generate made, a
released one and one made from a connection refuse: Generate makes no splice (owner answer B8),
and a connection owns the pairs of its harness.
"""

from pydantic import TypeAdapter, ValidationError

from .commands import Op, Put
from .edit import EditError
from .generate.naming import namer_for
from .model import Connector, Harness, Part, Pin, Project, Wire, evolve
from .model.base import MAX_PIN_COUNT, Name
from .model.physical import SPLICE_ROLE, Termination
from .nets import is_splice
from .origin import harness_link
from .wires import find_wire, released_text, used_ids

__all__ = [
    "SPLICE_CATEGORY",
    "TERMINATIONS",
    "plan_add_splice",
    "plan_delete_splice",
    "plan_splice_wire",
    "splice_part",
    "splice_parts",
    "splices_of",
]

SPLICE_CATEGORY = "splice"  # the library category of a splice part (owner answer B3)
TERMINATIONS: tuple[Termination, ...] = ("crimp", "solder", "unspecified")
_NAME = TypeAdapter(Name)
_MAX_SHOWN = 4


def _shown(ids: list[str]) -> str:
    more = len(ids) - _MAX_SHOWN
    return ", ".join(ids[:_MAX_SHOWN]) + (f" and {more} more" if more > 0 else "")


def splice_parts(project: Project) -> list[Part]:
    """The splice parts of the library a picker offers, by ID."""
    return sorted(
        (p for p in project.parts.values() if p.category == SPLICE_CATEGORY), key=lambda p: p.id
    )


def splice_part(project: Project, part_id: str) -> Part:
    """The splice part a person chose, or `EditError`."""
    part = project.parts.get(part_id)
    if part is None or part.category != SPLICE_CATEGORY:
        raise EditError(
            f"'{part_id}' is not a splice part in the library. A splice uses a part of the "
            "category splice (import-parts, or the Library)."
        )
    return part


def splices_of(h: Harness) -> list[Connector]:
    """The splices of a harness, by ID."""
    return sorted((c for c in h.connectors if is_splice(c)), key=lambda c: c.id)


def _drawn(project: Project, harness_id: str) -> Harness:
    """The harness, if a person may place splices in it: it exists, is not released, was not made by
    Generate or from a connection."""
    if project.read_only:
        raise EditError("This project is read-only (saved by a newer tool version). Use Save as.")
    h = project.harnesses.get(harness_id)
    if h is None:
        raise EditError(f"Harness '{harness_id}' does not exist.")
    if h.status == "released":
        raise EditError(released_text(h))
    if h.generated:
        raise EditError(
            f"{harness_id} is made by Generate, which makes no splice. Place a splice in a harness "
            "you made."
        )
    made_from = harness_link(project, h.id)
    if made_from is not None:
        raise EditError(
            f"{h.id} was made from the connection {made_from}, which owns its pairs of pins, so it "
            "takes no splice. Place the splice in a harness you made by hand."
        )
    return h


def _splice(h: Harness, splice_id: str) -> Connector:
    found = next((c for c in h.connectors if c.id == splice_id), None)
    if found is None or not is_splice(found):
        raise EditError(f"'{splice_id}' is not a splice of {h.id}.")
    return found


def plan_add_splice(
    project: Project,
    harness_id: str,
    part_id: str,
    nodes: int = 1,
    *,
    termination: str = "unspecified",
    name: str | None = None,
) -> tuple[list[Op], str]:
    """Ops that add a splice to a harness a person made, and its ID (the next free `splice` ID of
    the naming pattern, `W003-X1`). It has `nodes` pins, `1` to `nodes`, each with the
    `termination` (crimp, solder or unspecified); a part with a pin count allows at most that many.
    It has no wire yet (integrity warns `splice_unused` until it has)."""
    h = _drawn(project, harness_id)
    part = splice_part(project, part_id)
    if isinstance(nodes, bool) or not isinstance(nodes, int) or nodes < 1:
        raise EditError("A splice has at least one node.")
    limit = part.pin_count or MAX_PIN_COUNT
    if nodes > limit:
        raise EditError(
            f"{part_id} has {limit} node{'s' if limit != 1 else ''}; {nodes} were asked for."
        )
    if termination not in TERMINATIONS:
        raise EditError(f"A splice is joined by {', '.join(TERMINATIONS[:2])} or not said yet.")
    namer = namer_for(project)
    taken = used_ids(project)
    n = 1
    while namer.splice(harness_id, n) in taken:
        n += 1
    sid = namer.splice(harness_id, n)
    title = sid.rsplit("-", 1)[-1]
    if name is not None and name.strip():
        try:
            title = _NAME.validate_python(name.strip(), strict=True)
        except ValidationError as exc:
            raise EditError("A splice name can have 1 to 200 characters.") from exc
    if any(c.name.casefold() == title.casefold() for c in h.connectors):
        title = sid
    splice = Connector(
        id=sid,
        name=title,
        role=SPLICE_ROLE,
        part_id=part_id,
        pins=[Pin(id=str(k), termination=termination) for k in range(1, nodes + 1)],
    )
    return [Put("harnesses", evolve(h, connectors=[*h.connectors, splice]))], sid


def _next_wire(project: Project, harness_id: str, taken: set[str]) -> str:
    namer = namer_for(project)
    n = 1
    while namer.wire(harness_id, n) in taken:
        n += 1
    return namer.wire(harness_id, n)


def plan_splice_wire(
    project: Project, wire_id: str, splice_id: str, node: str = "1"
) -> tuple[list[Op], str]:
    """Ops that cut a wire in two at a node of a splice of its harness, and the ID of the new wire.
    The wire keeps its ID, signal, interface, gauge, part, colour, label, note and the strip length
    of its From end, and now ends on the node; the new wire (the next free ID) runs from the node to
    where the wire ended, with the same signal, interface, gauge, part and colour and the strip
    length of the To end. A wire with a length of its own refuses: say how to split it first (clear
    the length; each piece then takes the length of its path). Shield groups and accessories stay
    with the wire."""
    h, w = find_wire(project, wire_id)
    h = _drawn(project, h.id)
    splice = _splice(h, splice_id)
    if node not in {p.id for p in splice.pins}:
        raise EditError(f"{splice_id} has no node '{node}'.")
    if splice_id in (w.from_connector, w.to_connector):
        raise EditError(f"{wire_id} ends on {splice_id} already.")
    if w.length_m is not None:
        raise EditError(
            f"{wire_id} has a length of its own ({w.length_m:g} m). Clear it first: each piece "
            "then takes the length of its path, or set the length of each piece."
        )
    new_id = _next_wire(project, h.id, used_ids(project))
    first = evolve(w, to_connector=splice_id, to_pin=node, strip_b_mm=None)
    rest = Wire(
        id=new_id,
        signal=w.signal,
        from_connector=splice_id,
        from_pin=node,
        to_connector=w.to_connector,
        to_pin=w.to_pin,
        gauge_awg=w.gauge_awg,
        part_id=w.part_id,
        colour=w.colour,
        interface_id=w.interface_id,
        locked=w.locked,
        manual=True,
        strip_b_mm=w.strip_b_mm,
        overrides=dict(w.overrides),
    )
    wires: list[Wire] = []
    for x in h.wires:
        wires.append(first if x.id == wire_id else x)
        if x.id == wire_id:
            wires.append(rest)
    return [Put("harnesses", evolve(h, wires=wires))], new_id


def _on_node(h: Harness, splice_id: str, node: str) -> list[Wire]:
    return sorted(
        (
            w
            for w in h.wires
            if (w.from_connector, w.from_pin) == (splice_id, node)
            or (w.to_connector, w.to_pin) == (splice_id, node)
        ),
        key=lambda w: w.id,
    )


def _far_end(w: Wire, splice_id: str, node: str) -> tuple[str, str, float | None]:
    """The other end of a wire on a node: (connector, pin, the strip length there)."""
    if (w.from_connector, w.from_pin) == (splice_id, node):
        return w.to_connector, w.to_pin, w.strip_b_mm
    return w.from_connector, w.from_pin, w.strip_a_mm


def _joined(keep: Wire, other: Wire, splice_id: str, node: str) -> Wire:
    """`keep` with its end on the node moved to where `other` goes on."""
    cid, pin, strip = _far_end(other, splice_id, node)
    if (keep.to_connector, keep.to_pin) == (splice_id, node):
        return evolve(keep, to_connector=cid, to_pin=pin, strip_b_mm=strip)
    return evolve(keep, from_connector=cid, from_pin=pin, strip_a_mm=strip)


def plan_delete_splice(project: Project, harness_id: str, splice_id: str) -> list[Op]:
    """Ops that delete a splice of a harness a person made. Refused while wires end on it, except
    on a node with exactly two wires: those two are joined back into one (the wire with the smaller
    ID keeps its values and takes the far end of the other, which is deleted). Refused while a
    segment or an accessory names the splice."""
    h = _drawn(project, harness_id)
    splice = _splice(h, splice_id)
    segments = sorted(s.id for s in h.segments if splice_id in (s.from_node, s.to_node))
    if segments:
        raise EditError(
            f"The segments {_shown(segments)} end at {splice_id}. Delete them first, or join their "
            "ends with a segment of their own."
        )
    accessories = sorted(a.id for a in h.accessories if a.target == splice_id)
    if accessories:
        raise EditError(
            f"The accessories {_shown(accessories)} belong to {splice_id}. Move or delete them "
            "first."
        )
    replaced: dict[str, Wire] = {}
    into: dict[str, str] = {}  # a deleted wire -> the wire it was joined into
    for p in splice.pins:
        on = _on_node(h, splice_id, p.id)
        if not on:
            continue
        if len(on) != 2:
            raise EditError(
                f"Node {p.id} of {splice_id} joins {len(on)} wire{'s' if len(on) != 1 else ''} "
                f"({_shown([w.id for w in on])}). Delete or move them first; a node with two "
                "wires is joined back into one wire."
            )
        keep, other = (replaced.get(on[0].id, on[0]), replaced.get(on[1].id, on[1]))
        joined = _joined(keep, other, splice_id, p.id)
        if (joined.from_connector, joined.from_pin) == (joined.to_connector, joined.to_pin):
            raise EditError(
                f"{keep.id} and {other.id} both end on pin {joined.from_pin} of "
                f"{joined.from_connector}; joined, the wire would start and end on one pin."
            )
        replaced[keep.id] = joined
        into[other.id] = keep.id
    gone = set(into)
    wires = [replaced.get(w.id, w) for w in h.wires if w.id not in gone]
    shields = [
        evolve(s, wire_ids=[i for i in s.wire_ids if i not in gone])
        for s in h.shields
        if [i for i in s.wire_ids if i not in gone]
    ]
    accessories_kept = [
        evolve(a, target=into[a.target]) if a.target in into else a for a in h.accessories
    ]
    new = evolve(
        h,
        connectors=[c for c in h.connectors if c.id != splice_id],
        wires=wires,
        shields=shields,
        accessories=accessories_kept,
    )
    return [Put("harnesses", new)]
