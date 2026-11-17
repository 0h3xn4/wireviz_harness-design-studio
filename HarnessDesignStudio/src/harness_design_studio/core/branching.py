# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The routing tree of a harness that a person draws, and the join of two harnesses (D-243).

Branch points, segments, the length of a segment, a new leg and the join of two harnesses on one
device connector: 2.3.0, section 5.2 of `docs/ait/DESIGN_2.3_BRANCHING.md`.

    ops, bid = plan_add_branch_point(project, "W003")                  # W003-B1, "Branch 1"
    ops = plan_rename_branch_point(project, "W003", "W003-B1", "Branch Y")
    ops = plan_delete_branch_point(project, "W003", "W003-B1")         # its segments go with it
    ops, sid = plan_add_segment(project, "W003", "W003-P1", "W003-B1", 0.4)
    ops = plan_delete_segment(project, "W003", "W003-L1")
    ops = plan_set_segment_length(project, "W001", "W001-L2", 1.25)    # Generate's harnesses too
    leg = plan_add_leg(project, "W003", "OBC1-J01")                    # a new loose end
    ops = plan_join_harnesses(project, "W003", "W004")                 # one harness, one plug

The design calls this module `core/routing.py`; that name holds the routing of the links of the
block diagram since 1.x, so the plans live here. Pure functions, no Qt: each returns the `Op`s that
`History.execute` runs as one undo step, or raises `EditError` with a plain sentence. A released
harness refuses with `wires.released_text`. Everything is in format 2 (`BranchPoint`, `Segment`);
no field is new.

Branch points and segments of a harness that Generate made follow the design: Generate makes them
again, so only the length of a segment is entered there (Generate keeps an entered length by the
two nodes of its segment, as it keeps an imported one). Every other plan here is for a harness a
person made (`Harness.generated` False). The leg and the join also refuse a harness made from a
connection: its link owns its pairs of pins.

The segments of a harness form a tree (the design rule `segment-loop` reports a loop in a file;
`plan_add_segment` refuses to close one), so a wire has one path and one length
(`generate.lengths.wire_length`).
"""

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from pydantic import TypeAdapter, ValidationError

from .commands import Delete, Op, Put
from .edit import EditError
from .generate.lengths import loop_segments, path_trail
from .generate.naming import namer_for
from .manual_harness import tbd_part
from .model import BranchPoint, Connector, Harness, Pin, Project, Segment, Wire, evolve
from .model.base import MAX_LENGTH_M, Name
from .model.physical import LOOSE_ROLE, TBD_PART_ID
from .origin import harness_link
from .wires import released_text, used_ids

__all__ = [
    "Leg",
    "plan_add_branch_point",
    "plan_add_leg",
    "plan_add_segment",
    "plan_delete_branch_point",
    "plan_delete_segment",
    "plan_join_harnesses",
    "plan_rename_branch_point",
    "plan_set_segment_length",
]

_NAME = TypeAdapter(Name)
_MAX_SHOWN = 4


# ---- shared checks -----------------------------------------------------------------------------


def _writable(project: Project) -> None:
    if project.read_only:
        raise EditError("This project is read-only (saved by a newer tool version). Use Save as.")


def _harness(project: Project, harness_id: str) -> Harness:
    """The harness, if it exists and is not released."""
    _writable(project)
    h = project.harnesses.get(harness_id)
    if h is None:
        raise EditError(f"Harness '{harness_id}' does not exist.")
    if h.status == "released":
        raise EditError(released_text(h))
    return h


def _drawn(project: Project, harness_id: str) -> Harness:
    """The harness, if a person may draw its routing tree: it exists, is not released, and Generate
    did not make it (Generate makes the branch points and segments of its harnesses again)."""
    h = _harness(project, harness_id)
    if h.generated:
        raise EditError(
            f"{harness_id} is made by Generate, which gives it its branch points and segments "
            "from the design. Enter the length of a segment there; draw the routing tree in a "
            "harness you made."
        )
    return h


def _not_from_link(project: Project, h: Harness, what: str) -> None:
    made_from = harness_link(project, h.id)
    if made_from is not None:
        raise EditError(
            f"{h.id} was made from the connection {made_from}, which owns its pairs of pins, so "
            f"it cannot {what}. Draw a new cable from the port instead."
        )


def _shown(ids: Sequence[str]) -> str:
    more = len(ids) - _MAX_SHOWN
    return ", ".join(ids[:_MAX_SHOWN]) + (f" and {more} more" if more > 0 else "")


def _name(value: object, what: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EditError(f"{what} must be text.")
    text = value.strip()
    if not text:
        return None
    try:
        return _NAME.validate_python(text, strict=True)
    except ValidationError as exc:
        raise EditError(f"{what} can have 1 to 200 characters and no control characters.") from exc


def _metres(value: object) -> float | None:
    """A segment length in metres as typed: a number, or text with a decimal point or comma; an
    empty text or None clears it."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            raise EditError("The length must be a number of metres, for example 1.5.") from None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EditError("The length must be a number of metres, for example 1.5.")
    metres = float(value)
    if not math.isfinite(metres) or metres < 0:
        raise EditError("The length must be a number of metres, 0 or more.")
    if metres > MAX_LENGTH_M:
        raise EditError(f"A length can be at most {MAX_LENGTH_M:g} m.")
    return metres


def _free_branch_name(points: Iterable[BranchPoint]) -> str:
    names = {b.name.casefold() for b in points}
    n = 1
    while f"branch {n}" in names:
        n += 1
    return f"Branch {n}"


def _nodes(h: Harness) -> set[str]:
    return {c.id for c in h.connectors} | {b.id for b in h.branch_points}


def _branch_point(h: Harness, branch_id: str) -> BranchPoint:
    found = next((b for b in h.branch_points if b.id == branch_id), None)
    if found is None:
        raise EditError(f"'{branch_id}' is not a branch point of {h.id}.")
    return found


def _segment(h: Harness, segment_id: str) -> Segment:
    found = next((s for s in h.segments if s.id == segment_id), None)
    if found is None:
        raise EditError(f"'{segment_id}' is not a segment of {h.id}.")
    return found


# ---- branch points -----------------------------------------------------------------------------


def plan_add_branch_point(
    project: Project, harness_id: str, name: str | None = None
) -> tuple[list[Op], str]:
    """Ops that add a branch point to a harness a person made, and its ID: the next free `branch`
    ID of the naming pattern (`W003-B1`). Without a name it is called `Branch 1`, `Branch 2`, ...
    It has no segment yet (integrity warns `branch_point_unused` until it has two)."""
    h = _drawn(project, harness_id)
    title = _name(name, "A branch point name") or _free_branch_name(h.branch_points)
    if any(b.name.casefold() == title.casefold() for b in h.branch_points):
        raise EditError(f"{harness_id} has a branch point called '{title}' already.")
    bid = _Ids(project, harness_id).branch()
    point = BranchPoint(id=bid, name=title)
    return [Put("harnesses", evolve(h, branch_points=[*h.branch_points, point]))], bid


def plan_rename_branch_point(
    project: Project, harness_id: str, branch_id: str, name: str
) -> list[Op]:
    """Ops that give a branch point of a harness a person made another name (its ID stays)."""
    h = _drawn(project, harness_id)
    point = _branch_point(h, branch_id)
    title = _name(name, "A branch point name")
    if title is None:
        raise EditError("A branch point needs a name.")
    if any(b.name.casefold() == title.casefold() for b in h.branch_points if b.id != branch_id):
        raise EditError(f"{harness_id} has a branch point called '{title}' already.")
    new = evolve(point, name=title)
    points = [new if b.id == branch_id else b for b in h.branch_points]
    return [Put("harnesses", evolve(h, branch_points=points))]


def _wires_through(h: Harness, node: str) -> list[str]:
    """The wires of the harness whose one path through the segments passes `node`."""
    ends = {s.id: (s.from_node, s.to_node) for s in h.segments}
    out: list[str] = []
    for w in h.wires:
        trail = path_trail(h, w.from_connector, w.to_connector)
        if trail and any(node in ends[sid] for sid, _length in trail):
            out.append(w.id)
    return sorted(out)


def plan_delete_branch_point(project: Project, harness_id: str, branch_id: str) -> list[Op]:
    """Ops that delete a branch point of a harness a person made, and the segments that end at it.
    Refused while it is on the only path of a wire (the wires are named): the wire would lose its
    length."""
    h = _drawn(project, harness_id)
    _branch_point(h, branch_id)
    through = _wires_through(h, branch_id)
    if through:
        raise EditError(
            f"{branch_id} is on the only path of the wires {_shown(through)}, which would be "
            "left without a length. Delete those wires, or their legs, first."
        )
    return [
        Put(
            "harnesses",
            evolve(
                h,
                branch_points=[b for b in h.branch_points if b.id != branch_id],
                segments=[s for s in h.segments if branch_id not in (s.from_node, s.to_node)],
            ),
        )
    ]


# ---- segments ----------------------------------------------------------------------------------


def plan_add_segment(
    project: Project, harness_id: str, a: str, b: str, length: object = None
) -> tuple[list[Op], str]:
    """Ops that add a segment from node `a` to node `b` (connectors or branch points of a harness a
    person made), with a length in metres or none, and its ID (the next free `segment` ID of the
    naming pattern, `W003-L1`). Refused when `a` and `b` are joined by segments already: the new
    one would close a loop, and a wire would have two lengths (`loop_segments`)."""
    h = _drawn(project, harness_id)
    nodes = _nodes(h)
    for node in (a, b):
        if node not in nodes:
            raise EditError(f"'{node}' is not a connector or branch point of {harness_id}.")
    if a == b:
        raise EditError("A segment runs between two different nodes.")
    metres = _metres(length)
    sid = _Ids(project, harness_id).segment()
    segment = Segment(id=sid, from_node=a, to_node=b, length_m=metres)
    new = evolve(h, segments=[*h.segments, segment])
    if len(loop_segments(new)) > len(loop_segments(h)):
        raise EditError(
            f"{a} and {b} are joined by segments already, so a segment between them would close "
            "a loop and a wire through it would have two lengths. The segments of a harness form "
            "a tree."
        )
    return [Put("harnesses", new)], sid


def plan_delete_segment(project: Project, harness_id: str, segment_id: str) -> list[Op]:
    """Ops that delete a segment of a harness a person made. The wires whose path ran through it
    have no length until a segment joins their connectors again (integrity warns
    `segment_tree_split` for a harness with branch points)."""
    h = _drawn(project, harness_id)
    _segment(h, segment_id)
    return [Put("harnesses", evolve(h, segments=[s for s in h.segments if s.id != segment_id]))]


def plan_set_segment_length(
    project: Project, harness_id: str, segment_id: str, metres: object
) -> list[Op]:
    """Ops that enter the length of a segment in metres (None or an empty text clears it). Also on a
    harness that Generate made: Generate keeps an entered length by the two nodes of its segment,
    as it keeps one that `import-lengths` read. A released harness refuses."""
    h = _harness(project, harness_id)
    segment = _segment(h, segment_id)
    value = _metres(metres)
    if value == segment.length_m:
        return []
    new = evolve(segment, length_m=value)
    return [
        Put("harnesses", evolve(h, segments=[new if s.id == segment_id else s for s in h.segments]))
    ]


# ---- a new leg and the join ---------------------------------------------------------------------


def _legs(h: Harness, plug_id: str) -> list[Segment | str]:
    """The legs that leave `plug_id`: its segments. A harness with no segment at all whose plug
    wires go to exactly one other connector has one leg that is not drawn yet: it is given as the ID
    of that far connector (a segment to be made, with no length)."""
    drawn: list[Segment | str] = [s for s in h.segments if plug_id in (s.from_node, s.to_node)]
    if drawn or h.segments:
        return drawn
    local = {c.id for c in h.connectors}
    far = sorted(
        {
            w.to_connector if w.from_connector == plug_id else w.from_connector
            for w in h.wires
            if plug_id in (w.from_connector, w.to_connector)
        }
        & (local - {plug_id})
    )
    return [far[0]] if len(far) == 1 else []


class _Ids:
    """The next free IDs of one harness's naming pattern, for a plan that makes several (the taken
    IDs are read once)."""

    def __init__(self, project: Project, harness_id: str) -> None:
        self.namer = namer_for(project)
        self.harness_id = harness_id
        self.taken = used_ids(project)

    def _next(self, make: Callable[[int], str]) -> str:
        n = 1
        while make(n) in self.taken:
            n += 1
        made = make(n)
        self.taken.add(made)
        return made

    def segment(self) -> str:
        return self._next(lambda n: self.namer.segment(self.harness_id, n))

    def branch(self) -> str:
        return self._next(lambda n: self.namer.branch(self.harness_id, n))

    def wire(self) -> str:
        return self._next(lambda n: self.namer.wire(self.harness_id, n))

    def connector(self) -> str:
        return self._next(lambda n: self.namer.cable_connector(self.harness_id, n))


def _branch_at(
    ids: _Ids,
    plug_id: str,
    legs: list[Segment | str],
    segments: list[Segment],
    branches: list[BranchPoint],
) -> tuple[list[Segment], list[BranchPoint], str | None]:
    """Put a branch point next to `plug_id` when two or more legs leave it: a segment from the plug
    to the branch point (no length yet), and every leg moved onto the branch point (a drawn leg
    keeps its ID and its length). A leg given as a far node is new: a segment with the next free
    ID and no length. With fewer than two legs, a new one runs from the plug and nothing moves."""
    if len(legs) < 2:
        fresh = [
            Segment(id=ids.segment(), from_node=plug_id, to_node=leg)
            for leg in legs
            if isinstance(leg, str)
        ]
        return [*segments, *fresh], branches, None
    bid = ids.branch()
    point = BranchPoint(id=bid, name=_free_branch_name(branches))
    leg_ids = {leg.id for leg in legs if isinstance(leg, Segment)}

    def moved(s: Segment) -> Segment:
        if s.from_node == plug_id:
            return evolve(s, from_node=bid)
        return evolve(s, to_node=bid)

    kept = [moved(s) if s.id in leg_ids else s for s in segments]
    trunk = Segment(id=ids.segment(), from_node=plug_id, to_node=bid)
    fresh = [
        Segment(id=ids.segment(), from_node=bid, to_node=leg)
        for leg in legs
        if isinstance(leg, str)
    ]
    return [*kept, trunk, *fresh], [*branches, point], bid


@dataclass(frozen=True)
class Leg:
    """The result of `plan_add_leg`: the ops, the new loose end, the wires to it, and the branch
    point that was added (None when none was)."""

    ops: list[Op]
    loose_id: str
    wire_ids: tuple[str, ...]
    branch_id: str | None


def _plug(h: Harness, connector_id: str) -> Connector:
    """The cable connector of the harness that is `connector_id`, or that plugs into it."""
    found = next((c for c in h.connectors if c.id == connector_id), None)
    if found is None:
        found = next((c for c in h.connectors if c.mates_with == connector_id), None)
    if found is None:
        raise EditError(f"{h.id} has no connector that plugs into {connector_id}.")
    return found


def _used_pins(h: Harness, connector_id: str) -> dict[str, str]:
    """Pin of `connector_id` -> the first wire (by ID) of the harness on it."""
    out: dict[str, str] = {}
    for w in sorted(h.wires, key=lambda x: x.id):
        for cid, pin in ((w.from_connector, w.from_pin), (w.to_connector, w.to_pin)):
            if cid == connector_id:
                out.setdefault(pin, w.id)
    return out


def plan_add_leg(
    project: Project,
    harness_id: str,
    connector_id: str,
    pin_ids: Iterable[str] | None = None,
) -> Leg:
    """Ops that add a leg to a harness a person made: a new loose end, and a wire from each chosen
    pin of the harness's plug on `connector_id` (the device connector it plugs into, or the plug
    itself) to the same pin of the loose end, which carries the port pin's signal name. `pin_ids`
    default to the pins whose port pin has a signal and that no wire of the harness uses yet. A
    chosen pin with a wire already is refused with the pin named: two wires on one pin need a
    splice.

    The routing follows: when a leg left the plug before (a segment, or in a harness with no
    segment the wires to its one far connector), a branch point is added next to the plug, with a
    segment from the plug to it; the old leg moves onto it (its length stays) and the new leg runs
    from it to the loose end. When no leg left the plug, the new leg is a segment from the plug in
    a harness that has segments, and nothing in one that has none. Lengths are not invented.

    A harness made from a connection refuses (its link owns its pairs)."""
    h = _drawn(project, harness_id)
    _not_from_link(project, h, "take a new leg")
    plug = _plug(h, connector_id)
    if plug.role == LOOSE_ROLE:
        raise EditError(f"{plug.id} is a loose end; plug it in before you add a leg to it.")
    port = project.connectors.get(plug.mates_with or "")
    signal_of = {p.id: p.signal for p in (port.pins if port is not None else plug.pins)}
    used = _used_pins(h, plug.id)
    have = {p.id for p in plug.pins}
    if pin_ids is None:
        chosen = [p.id for p in plug.pins if signal_of.get(p.id) and p.id not in used]
        if not chosen:
            raise EditError(
                f"{plug.id} has no free pin with a signal for a new leg. Choose the pins."
            )
    else:
        chosen = list(dict.fromkeys(pin_ids))
        if not chosen:
            raise EditError("A leg needs at least one pin.")
        for pid in chosen:
            if pid not in have:
                raise EditError(f"{plug.id} has no pin '{pid}'.")
            if pid in used:
                raise EditError(
                    f"Pin {pid} of {plug.id} has a wire already ({used[pid]}). Two wires on one "
                    "pin need a splice, which comes with format 3."
                )
    ids = _Ids(project, harness_id)
    loose_id = ids.connector()
    names = {c.name.casefold() for c in h.connectors}
    loose_name = loose_id.rsplit("-", 1)[-1]
    if loose_name.casefold() in names:
        loose_name = loose_id
    loose = Connector(
        id=loose_id,
        name=loose_name,
        role=LOOSE_ROLE,
        part_id=TBD_PART_ID,
        pins=[Pin(id=pid, signal=signal_of.get(pid)) for pid in chosen],
    )
    wires: list[Wire] = []
    for pid in chosen:
        wires.append(
            Wire(
                id=ids.wire(),
                signal=signal_of.get(pid),
                from_connector=plug.id,
                from_pin=pid,
                to_connector=loose_id,
                to_pin=pid,
                manual=True,
            )
        )
    legs = _legs(h, plug.id)
    segments = list(h.segments)
    branches = list(h.branch_points)
    branch_id: str | None = None
    if legs or h.segments:
        segments, branches, branch_id = _branch_at(
            ids, plug.id, [*legs, loose_id], segments, branches
        )
    ops: list[Op] = []
    if TBD_PART_ID not in project.parts:
        ops.append(Put("parts", tbd_part()))
    new = evolve(
        h,
        connectors=[*h.connectors, loose],
        wires=[*h.wires, *wires],
        branch_points=branches,
        segments=segments,
    )
    ops.append(Put("harnesses", new))
    return Leg(ops, loose_id, tuple(w.id for w in wires), branch_id)


def _history(project: Project, harness_id: str) -> bool:
    return (
        any(b.harness_id == harness_id for b in project.baselines.values())
        or any(c.harness_id == harness_id for c in project.changelog.values())
        or any(r.harness_id == harness_id for r in project.asbuilt.values())
    )


def _joinable(project: Project, harness_id: str) -> Harness:
    h = _harness(project, harness_id)
    if h.generated:
        raise EditError(
            f"{harness_id} is made by Generate. Generate joins its harnesses on one device "
            "connector when segmentation.mode is per_connector_group."
        )
    _not_from_link(project, h, "be joined")
    return h


def plan_join_harnesses(project: Project, keep_id: str, other_id: str) -> list[Op]:
    """Ops that join two harnesses a person made, with plugs on one device connector, into the
    harness `keep_id`. The plug of `keep_id` on that connector stays and the wires of the other's
    plug move onto it pin by pin; every other connector, wire, shield, splice, branch point,
    segment and accessory of the other harness moves over under its ID (a connector or branch
    point whose name is taken in the kept harness is called by its ID). The legs that leave the
    joined plug meet at a new branch point next to it (see `plan_add_leg`). The other harness is
    deleted; its notes are added to the kept harness's notes.

    Refused, with the reason: a harness that Generate made, one made from a connection, a
    released one, one with a release history (the other harness is deleted), two harnesses that
    share no device connector or more than one, two plugs with different parts, and a pin that
    both harnesses wire."""
    if keep_id == other_id:
        raise EditError("Choose two different harnesses to join.")
    keep = _joinable(project, keep_id)
    other = _joinable(project, other_id)
    if _history(project, other_id):
        raise EditError(
            f"{other_id} has a release history (a baseline, change-log or as-built record), so "
            f"it is not deleted. Join {keep_id} into {other_id} instead."
        )
    mine = {c.mates_with: c for c in keep.connectors if c.mates_with}
    theirs = {c.mates_with: c for c in other.connectors if c.mates_with}
    shared = sorted(set(mine) & set(theirs))
    if not shared:
        raise EditError(
            f"{keep_id} and {other_id} have no plugs on one device connector. Two harnesses are "
            "joined where both plug into the same connector."
        )
    if len(shared) > 1:
        raise EditError(
            f"{keep_id} and {other_id} both plug into {_shown([s or '' for s in shared])}. Join "
            "two harnesses that share one device connector; the join would close a loop."
        )
    box = shared[0] or ""
    kp, op = mine[box], theirs[box]
    if kp.part_id != op.part_id:
        raise EditError(
            f"The plugs on {box} have different parts: {kp.id} is {kp.part_id}, {op.id} is "
            f"{op.part_id}. Give them the same part first."
        )
    keep_pins = _used_pins(keep, kp.id)
    other_pins = _used_pins(other, op.id)
    both = sorted(set(keep_pins) & set(other_pins))
    if both:
        listed = ", ".join(f"{p} ({keep_pins[p]} and {other_pins[p]})" for p in both[:_MAX_SHOWN])
        raise EditError(
            f"{keep_id} and {other_id} both wire pin{'s' if len(both) > 1 else ''} of {box}: "
            f"{listed}. One pin carries one wire; two wires on one pin need a splice."
        )
    # the plug: the kept one, with any pin of the other's that it lacks
    have = {p.id for p in kp.pins}
    plug = evolve(kp, pins=[*kp.pins, *(p for p in op.pins if p.id not in have)])

    def node(x: str) -> str:
        return kp.id if x == op.id else x

    names = {c.name.casefold() for c in keep.connectors}
    moved_connectors = []
    for c in other.connectors:
        if c.id == op.id:
            continue
        name = c.id if c.name.casefold() in names else c.name
        names.add(name.casefold())
        moved_connectors.append(evolve(c, name=name) if name != c.name else c)
    point_names = {b.name.casefold() for b in keep.branch_points}
    moved_points = []
    for b in other.branch_points:
        name = b.id if b.name.casefold() in point_names else b.name
        point_names.add(name.casefold())
        moved_points.append(evolve(b, name=name) if name != b.name else b)
    moved_wires = [
        evolve(w, from_connector=node(w.from_connector), to_connector=node(w.to_connector))
        if op.id in (w.from_connector, w.to_connector)
        else w
        for w in other.wires
    ]
    moved_segments = [
        evolve(s, from_node=node(s.from_node), to_node=node(s.to_node))
        if op.id in (s.from_node, s.to_node)
        else s
        for s in other.segments
    ]
    moved_accessories = [
        evolve(a, target=kp.id) if a.target == op.id else a for a in other.accessories
    ]
    # the legs that leave the joined plug, each side's own (an undrawn one counts, see `_legs`)
    legs = _legs(keep, kp.id)
    for leg in _legs(other, op.id):
        if isinstance(leg, Segment):
            leg = evolve(leg, from_node=node(leg.from_node), to_node=node(leg.to_node))
        legs.append(leg)
    segments = [*keep.segments, *moved_segments]
    ids = _Ids(project, keep_id)
    segments, branches, _bid = _branch_at(
        ids, kp.id, legs, segments, [*keep.branch_points, *moved_points]
    )
    notes = keep.notes
    if other.notes.strip():
        added = f"{other_id}: {other.notes}"
        notes = f"{keep.notes}\n\n{added}" if keep.notes else added
    joined = evolve(
        keep,
        connectors=[plug if c.id == kp.id else c for c in keep.connectors] + moved_connectors,
        wires=[*keep.wires, *moved_wires],
        splices=[*keep.splices, *other.splices],
        shields=[*keep.shields, *other.shields],
        branch_points=branches,
        segments=segments,
        accessories=[*keep.accessories, *moved_accessories],
        interfaces=sorted({*keep.interfaces, *other.interfaces}),
        notes=notes,
    )
    return [Delete("harnesses", other_id), Put("harnesses", joined)]
