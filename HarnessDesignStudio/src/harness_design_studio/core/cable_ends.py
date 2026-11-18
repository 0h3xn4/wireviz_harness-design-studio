# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The ends of the cables a person drew, as the diagram shows them (M4c of the programme, D-201).

    ends = drawn_ends(project)           # every end the block diagram draws, by harness and ID
    box = free_port(project, "OBC")      # the connector of a device a new cable goes into
    box = plug_port(project, "W009", "W009-P2", "RW1")   # the connector a loose end plugs into
    hid = harness_of(project, "W009-P2") # the harness a cable connector belongs to

A cable drawn by hand is a harness (`core/manual_harness.py`); it has no `Link`, so the lines of
connections do not show it. The diagram draws it from what this module says: each **loose end**
of a harness that is plugged in somewhere hangs on a dashed line out of the port the harness
plugs into (its *anchor*), and each further connector of a harness drawn by hand that is plugged
into another device is a line from that anchor to its port. A harness made from a connection is
drawn by the connection's own line, so only its loose ends are added here; a harness Generate made
has neither. A loose end of a harness that is plugged in nowhere has no place on the diagram: it is
listed in the project tree and reached from the menu.

Where an end hangs is the diagram mark `pos:<connector id>` (an offset from the place the diagram
gives it, outside the model hash; `core/io/layout.py` drops it when the connector goes). Pure
functions of the project; they change nothing and know nothing of a screen.

A harness drawn by hand that branches (2.3.0, D-243) has branch points: `drawn_branch_points`
names each one with the connectors it sits between (the diagram puts it at their middle, moved by
the mark `branch:<branch point id>`), and each end lists the branch points its line runs through
(`CableEnd.via`, from the anchor's plug along the segments).
"""

from collections import deque
from dataclasses import dataclass

from .edit import EditError, unit_connectors
from .integrity import mating_plugs
from .manual_harness import plan_plug_loose_end, propose_plug
from .model import Connector, Harness, Project
from .model.physical import LOOSE_ROLE

POS_KIND = "pos"
BRANCH_KIND = "branch"


def pos_mark(connector_id: str) -> str:
    """The ID of the diagram mark that keeps where a loose end hangs."""
    return f"{POS_KIND}:{connector_id}"


def branch_mark(branch_id: str) -> str:
    """The ID of the diagram mark that keeps where a branch point sits."""
    return f"{BRANCH_KIND}:{branch_id}"


@dataclass(frozen=True)
class CableEnd:
    """One end the diagram draws. `anchor` is the device connector the harness is plugged into
    (where the line starts) and `anchor_unit` its device; a loose end (`loose`) hangs in the air
    at its `index` among the loose ends of the same anchor, a plugged end sits on `target` (a
    device connector) of `target_unit`."""

    harness_id: str
    connector_id: str
    name: str
    loose: bool
    anchor: str
    anchor_unit: str
    target: str = ""
    target_unit: str = ""
    index: int = 0
    pins: int = 0
    via: tuple[str, ...] = ()  # the branch points the line runs through, from the anchor on


@dataclass(frozen=True)
class BranchSpot:
    """A branch point the diagram draws: on a harness drawn by hand that `drawn_ends` draws, between
    the cable connectors of the harness it joins (`connectors`, every side of it)."""

    harness_id: str
    branch_id: str
    name: str
    connectors: tuple[str, ...]


def _graph(h: Harness) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for s in sorted(h.segments, key=lambda x: x.id):
        graph.setdefault(s.from_node, []).append(s.to_node)
        graph.setdefault(s.to_node, []).append(s.from_node)
    return graph


def path_branches(h: Harness, start: str, end: str) -> tuple[str, ...]:
    """The branch points on the path of segments from node `start` to node `end`, in order (none
    when the segments do not join them)."""
    graph = _graph(h)
    came: dict[str, str] = {start: start}
    todo = deque([start])
    while todo:
        node = todo.popleft()
        if node == end:
            break
        for nxt in graph.get(node, []):
            if nxt not in came:
                came[nxt] = node
                todo.append(nxt)
    if end not in came or start == end:
        return ()
    points = {b.id for b in h.branch_points}
    path = []
    node = came[end]
    while node != start:
        path.append(node)
        node = came[node]
    return tuple(n for n in reversed(path) if n in points)


def drawn_branch_points(project: Project) -> list[BranchSpot]:
    """The branch points of the harnesses drawn by hand that the diagram draws (a harness plugged
    in somewhere that Generate did not make), by harness and ID; each with the cable connectors it
    joins (those reached through its segments, natural order of IDs)."""
    out: list[BranchSpot] = []
    for hid in sorted(project.harnesses):
        h = project.harnesses[hid]
        if h.generated or not h.branch_points or not _plugged(project, h):
            continue
        graph = _graph(h)
        connectors = {c.id for c in h.connectors}
        for b in sorted(h.branch_points, key=lambda x: x.id):
            seen = {b.id}
            todo = list(graph.get(b.id, []))
            seen.update(todo)
            while todo:
                for nxt in graph.get(todo.pop(), []):
                    if nxt not in seen:
                        seen.add(nxt)
                        todo.append(nxt)
            out.append(BranchSpot(hid, b.id, b.name, tuple(sorted(seen & connectors))))
    return out


def harness_of(project: Project, connector_id: str) -> Harness | None:
    """The harness that holds the cable connector `connector_id`, or None."""
    for h in project.harnesses.values():
        if any(c.id == connector_id for c in h.connectors):
            return h
    return None


def connector_of(project: Project, connector_id: str) -> tuple[Harness, Connector] | None:
    """(harness, connector) of a cable connector, or None."""
    for h in project.harnesses.values():
        for c in h.connectors:
            if c.id == connector_id:
                return h, c
    return None


def all_loose_ends(project: Project) -> list[tuple[str, Connector]]:
    """Every loose end of the project as (harness ID, connector), by harness and connector ID."""
    out: list[tuple[str, Connector]] = []
    for hid in sorted(project.harnesses):
        for c in sorted(project.harnesses[hid].connectors, key=lambda x: x.id):
            if c.role == LOOSE_ROLE:
                out.append((hid, c))
    return out


def _plugged(project: Project, h: Harness) -> list[tuple[Connector, Connector]]:
    """The connectors of a harness that sit on a connector of a device, with that connector."""
    out = []
    for c in sorted(h.connectors, key=lambda x: x.id):
        box = project.connectors.get(c.mates_with or "")
        if box is not None and box.role == "box" and box.unit_id in project.units:
            out.append((c, box))
    return out


def drawn_ends(project: Project) -> list[CableEnd]:
    """The ends of cables drawn by hand that the diagram draws (see the module)."""
    linked = {x.harness_id for x in project.links.values() if x.harness_id}
    out: list[CableEnd] = []
    for hid in sorted(project.harnesses):
        h = project.harnesses[hid]
        if h.generated:
            continue
        plugged = _plugged(project, h)
        if not plugged:
            continue
        anchor_plug, anchor = plugged[0]
        index = 0
        for c in sorted(h.connectors, key=lambda x: x.id):
            if c.role != LOOSE_ROLE:
                continue
            out.append(
                CableEnd(
                    hid,
                    c.id,
                    c.name,
                    True,
                    anchor.id,
                    anchor.unit_id or "",
                    index=index,
                    pins=len(c.pins),
                    via=path_branches(h, anchor_plug.id, c.id),
                )
            )
            index += 1
        if hid in linked:  # the connection's own line shows the plugged ends
            continue
        for c, box in plugged[1:]:
            out.append(
                CableEnd(
                    hid,
                    c.id,
                    c.name,
                    False,
                    anchor.id,
                    anchor.unit_id or "",
                    box.id,
                    box.unit_id or "",
                    pins=len(c.pins),
                    via=path_branches(h, anchor_plug.id, c.id),
                )
            )
    return out


def free_port(project: Project, unit_id: str) -> str | None:
    """The connector of a device a new cable from the device as a whole goes into (Guided and
    Quick show one port per device): the first by ID that has pins and no cable plug on it yet;
    None when there is none."""
    plugs = mating_plugs(project.harnesses.values())
    for c in unit_connectors(project, unit_id):
        if c.pins and c.id not in plugs:
            return c.id
    return None


def plug_port(project: Project, harness_id: str, loose_id: str, unit_id: str) -> str:
    """The connector of the device `unit_id` that the loose end plugs into when it is dropped on
    the device as a whole: the first by ID with no cable plug on it whose pins pair with the end's
    (by name; else by number with no names that disagree). Raises `EditError` with the reason the
    first candidate gives when none does."""
    plugs = mating_plugs(project.harnesses.values())
    candidates = [c.id for c in unit_connectors(project, unit_id) if c.id not in plugs and c.pins]
    if not candidates:
        raise EditError(f"{unit_id} has no connector a cable end can plug into.")
    proposals = {}
    for cid in candidates:
        try:
            proposals[cid] = propose_plug(project, harness_id, loose_id, cid)
        except EditError:
            continue
    for wanted in ("signal", "number"):  # a connector whose pin names fit comes first
        for cid, prop in proposals.items():
            if prop.by == wanted and prop.pairs and not prop.disagreements:
                return cid
    plan_plug_loose_end(project, harness_id, loose_id, candidates[0])  # raises with the reason
    return candidates[0]  # pragma: no cover - the plan above refuses


__all__ = [
    "BRANCH_KIND",
    "POS_KIND",
    "BranchSpot",
    "CableEnd",
    "all_loose_ends",
    "branch_mark",
    "connector_of",
    "drawn_branch_points",
    "drawn_ends",
    "free_port",
    "harness_of",
    "path_branches",
    "plug_port",
    "pos_mark",
]
