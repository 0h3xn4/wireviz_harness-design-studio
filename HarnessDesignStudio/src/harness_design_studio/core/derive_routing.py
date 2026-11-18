# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The routing tree of a harness, for the command `routing` and for `explain` (D-243, 2.3.0).

Its segments with their lengths and where each came from, its branch points and the wires through
each segment: sections 5.7 and 5.9 of `docs/ait/DESIGN_2.3_BRANCHING.md`.

    tree = routing_tree(project, "W005")          # the command `routing DIR HARNESS`
    tree.to_dict()                                # its `--json` document (without "ok")
    explain_routing_object(project, "W005-L3")    # `explain DIR W005-L3`: a segment
    explain_routing_object(project, "W005-B1")    # `explain DIR W005-B1`: a branch point

The derivations are:

    segment         a segment: its nodes, its length and where it came from, the wires through it
    branch-point    a branch point: the segments that meet it and the connectors beyond each

Nothing here decides again. The wires through a segment and the connectors beyond a branch point are
the rows the outputs write (`outputs.tables.segment_wires`, `branch_sides`), so the command line and
the files cannot disagree. A segment has no field that says where its length came from (format 2 is
frozen), so the source is worked out from what the project holds: no length is *unset*; a length
that an import record of kind `lengths` lists with the same value is *imported* (the file and the
row are named); any other length is *entered* (in the editor or in the file). Generate keeps an
entered or imported length by the two nodes of its segment, so on a harness Generate made the length
is also *kept by Generate*. Both derivations are computed on demand: `explain --all` does not hold
them, so `derivations.json` is as it was.
"""

import math
from dataclasses import dataclass
from typing import Any, Literal

from harness_design_studio.core.derive import Derivation, Input, Step, text_step
from harness_design_studio.core.generate.lengths import path_trail
from harness_design_studio.core.model import Harness, Project, Segment
from harness_design_studio.core.model.physical import LOOSE_ROLE
from harness_design_studio.core.origin import harness_origin
from harness_design_studio.core.outputs.tables import (
    branch_sides,
    has_branches,
    natural_key,
    segment_wires,
)

Source = Literal["unset", "entered", "imported"]


@dataclass(frozen=True)
class LengthSource:
    """Where the length of a segment came from: `unset`, `entered` or `imported`, whether Generate
    keeps it, and the same in words."""

    source: Source
    kept_by_generate: bool
    text: str
    record: str | None = None  # the ID of the import record that lists the length


def _stored_metres(stored: str) -> float | None:
    """The metres of a converted value of an import record (`"1.25 m"`)."""
    number, _, unit = stored.partition(" ")
    try:
        return float(number) if unit == "m" else None
    except ValueError:
        return None


def length_source(project: Project, h: Harness, s: Segment) -> LengthSource:
    """Where the length of segment `s` of harness `h` came from (see the module text)."""
    kept = h.generated and s.length_m is not None
    tail = ", kept by Generate" if kept else ""
    if s.length_m is None:
        return LengthSource("unset", False, "not set")
    for rid in sorted(project.import_records):
        record = project.import_records[rid]
        if record.kind != "lengths":
            continue
        for row in record.rows_converted:
            harness, _, segment = row.item.partition(" / ")
            metres = _stored_metres(row.stored)
            if (
                (harness.strip(), segment.strip()) == (h.id, s.id)
                and metres is not None
                and math.isclose(metres, s.length_m, rel_tol=0, abs_tol=1e-9)
            ):
                text = f"imported from {record.source_name}, row {row.row}{tail}"
                return LengthSource("imported", kept, text, rid)
    return LengthSource("entered", kept, f"entered{tail}")


def _node_text(h: Harness, node: str) -> str:
    """A node in words: a cable connector with the device connector it plugs into, a loose end, a
    branch point with its name, or the ID alone when the harness has no such node."""
    for c in h.connectors:
        if c.id == node:
            if c.role == LOOSE_ROLE:
                return f"{c.id} (loose end)"
            return f"{c.id} ({c.mates_with})" if c.mates_with else c.id
    for b in h.branch_points:
        if b.id == node:
            return f"{b.id} ({b.name})"
    return f"{node} (not a node of the harness)"


def _unrouted(h: Harness) -> list[str]:
    """The wires with no single path through the segments (no route, or a loop): they run through
    no segment and have no length from the segments."""
    if not h.segments:
        return []
    return sorted(
        (w.id for w in h.wires if path_trail(h, w.from_connector, w.to_connector) is None),
        key=natural_key,
    )


@dataclass(frozen=True)
class RoutingTree:
    """The routing tree of one harness, as `routing DIR HARNESS` prints it."""

    harness: str
    name: str
    origin: str  # `interfaces`, `link` or `drawn` (`core.origin`)
    branches: bool  # True when the harness has a branch point
    connectors: list[dict[str, Any]]  # id, mates_with (None for a loose end)
    segments: list[
        dict[str, Any]
    ]  # id, from, to, length_m, source, kept_by_generate, source_text, wires
    branch_points: list[dict[str, Any]]  # id, name, sides (segment, connectors)
    lengths_missing: list[str]  # the segments without a length
    wires_without_route: list[str]  # the wires with no single path through the segments
    node_words: dict[str, str]  # each node of a segment in words (the text only)

    def to_dict(self) -> dict[str, Any]:
        return {
            "harness": self.harness,
            "name": self.name,
            "origin": self.origin,
            "branches": self.branches,
            "connectors": self.connectors,
            "segments": self.segments,
            "branch_points": self.branch_points,
            "lengths_missing": self.lengths_missing,
            "wires_without_route": self.wires_without_route,
        }

    def lines(self) -> list[str]:
        """The tree as text for a person."""
        n_seg = len(self.segments)
        segs = f"{n_seg} segment{'' if n_seg == 1 else 's'}"
        out = [f"Harness {self.harness}: {self.name}"]
        if self.branches:
            n_bp = len(self.branch_points)
            out.append(
                f"It branches at {n_bp} branch point{'' if n_bp == 1 else 's'} and has {segs}."
            )
        elif self.segments:
            out.append(f"It does not branch (no branch point) and has {segs}.")
        else:
            out.append("It does not branch (no branch point) and has no segments.")
        if self.segments:
            out.append("")
            out.append(
                "Segments (from, to, length, where the length came from; the wires through it):"
            )
        for s in self.segments:
            length = "no length" if s["length_m"] is None else f"{s['length_m']:g} m"
            ends = f"{self.node_words[s['from']]} to {self.node_words[s['to']]}"
            out.append(f"  {s['id']}: {ends}, {length}, {s['source_text']}")
            n = len(s["wires"])
            wires = f"{n} wire{'' if n == 1 else 's'}" + (f": {', '.join(s['wires'])}" if n else "")
            out.append(f"    {wires}")
        if self.branch_points:
            out.append("")
            out.append("Branch points (the connectors beyond it, by segment):")
        for b in self.branch_points:
            out.append(f"  {b['id']} ({b['name']})")
            if not b["sides"]:
                out.append("    no segment meets it")
            for side in b["sides"]:
                out.append(f"    {side['segment']}: {', '.join(side['connectors']) or '(none)'}")
        if self.lengths_missing:
            out.append("")
            out.append("Segments without a length: " + ", ".join(self.lengths_missing) + ".")
        if self.wires_without_route:
            out.append("")
            out.append(
                "Wires with no single path through the segments (no length from them): "
                + ", ".join(self.wires_without_route)
                + "."
            )
        return out


def routing_tree(project: Project, harness_id: str) -> RoutingTree:
    """The routing tree of the harness (`KeyError` when there is none of that ID). The wires per
    segment and the sides of a branch point are the rows of the outputs."""
    h = project.harnesses[harness_id]
    through = segment_wires(h)
    nodes = {n: _node_text(h, n) for s in h.segments for n in (s.from_node, s.to_node)}
    segments: list[dict[str, Any]] = []
    for s in sorted(h.segments, key=lambda x: natural_key(x.id)):
        src = length_source(project, h, s)
        segments.append(
            {
                "id": s.id,
                "from": s.from_node,
                "to": s.to_node,
                "length_m": s.length_m,
                "source": src.source,
                "kept_by_generate": src.kept_by_generate,
                "source_text": src.text,
                "wires": through[s.id],
            }
        )
    return RoutingTree(
        harness=h.id,
        name=h.name,
        origin=harness_origin(project, h.id),
        branches=has_branches(h),
        connectors=[
            {"id": c.id, "mates_with": None if c.role == LOOSE_ROLE else c.mates_with}
            for c in sorted(h.connectors, key=lambda x: natural_key(x.id))
        ],
        segments=segments,
        branch_points=[
            {
                "id": bid,
                "name": name,
                "sides": [{"segment": sid, "connectors": ids} for sid, ids in sides],
            }
            for bid, name, sides in branch_sides(h)
        ],
        lengths_missing=[s["id"] for s in segments if s["length_m"] is None],
        wires_without_route=_unrouted(h),
        node_words=nodes,
    )


# ---- explain ------------------------------------------------------------------------------------

_SEGMENT_EQUATION = (
    "the length between the two nodes of the segment, as stored on the segment: from the rear of a "
    "connector to the centre of a branch point, or between the centres of two branch points"
)
_SOURCE_REFERENCE = (
    "A segment has no field for the source of its length: a length that an import record "
    "(imports/records.json, kind lengths) lists with the same value is imported, any other is "
    "entered (in the editor or in the file). Generate keeps an entered or imported length by the "
    "two nodes of its segment. The wires through a segment are the rows of segments.csv and of the "
    "sheet Routing."
)


def segment_derivation(project: Project, h: Harness, s: Segment) -> Derivation:
    """A segment: its nodes, its length and where it came from, the wires through it."""
    src = length_source(project, h, s)
    wires = segment_wires(h)[s.id]
    inputs = (
        Input("From", _node_text(h, s.from_node), "", f"segment {s.id}: from_node"),
        Input("To", _node_text(h, s.to_node), "", f"segment {s.id}: to_node"),
        Input("Length", s.length_m, "m", f"segment {s.id}: length_m, {src.text}"),
    )
    steps: tuple[Step, ...] = (
        text_step(
            "Where the length came from",
            "an import record of kind lengths lists this value: imported; else entered",
            src.text,
        ),
        Step(
            "Wires through it",
            "the wires whose one path between their connectors takes this segment",
            len(wires),
            "",
        ),
        text_step(
            "Their IDs",
            f"{len(wires)} wire{'' if len(wires) == 1 else 's'}",
            ", ".join(wires) or "(none)",
        ),  # fmt: skip
    )
    return Derivation(
        "segment",
        f"Segment {s.id} of harness {h.id}",
        "Length",
        s.length_m,
        "m",
        _SEGMENT_EQUATION,
        inputs,
        steps,
        None,
        ("A-PATH-UNIQUE",),
        _SOURCE_REFERENCE,
        () if s.length_m is not None else (f"the length of segment {s.id} (import-lengths)",),
    )


def branch_point_derivation(project: Project, h: Harness, branch_id: str) -> Derivation:
    """A branch point: the segments that meet it, with their lengths, and the connectors beyond
    each (the second block of the sheet Routing)."""
    _bid, name, sides = next(x for x in branch_sides(h) if x[0] == branch_id)
    by_id = {s.id: s for s in h.segments}
    inputs: list[Input] = []
    steps: list[Step] = []
    for sid, conns in sides:
        s = by_id[sid]
        other = s.to_node if s.from_node == branch_id else s.from_node
        src = length_source(project, h, s)
        inputs.append(
            Input(
                f"Segment {sid}", s.length_m, "m",
                f"to {_node_text(h, other)}; length {src.text}",
            )
        )  # fmt: skip
        steps.append(
            text_step(
                f"Beyond {sid}",
                "the connectors reached through it without passing the branch point again",
                ", ".join(f"{c} ({m})" if m else c for c, m in _mates(h, conns)) or "(none)",
            )
        )
    text = "; ".join(f"{sid}: {', '.join(conns) or '(none)'}" for sid, conns in sides)
    return Derivation(
        "branch-point",
        f"Branch point {branch_id} ({name}) of harness {h.id}",
        "Connectors beyond it, by segment",
        None,
        "",
        "for each segment that meets the branch point: the connectors of the harness reached "
        "through it without passing the branch point again",
        tuple(inputs),
        tuple(steps),
        None,
        ("A-PATH-UNIQUE",),
        "The same rows as the second block of the sheet Routing of the build workbook. "
        + _SOURCE_REFERENCE.split(". ", 1)[0]
        + ".",
        () if sides else (f"a segment that meets branch point {branch_id}",),
        text,
    )


def _mates(h: Harness, ids: list[str]) -> list[tuple[str, str | None]]:
    conns = {c.id: c for c in h.connectors}
    return [
        (c, None if conns[c].role == LOOSE_ROLE else conns[c].mates_with) for c in ids if c in conns
    ]


def explain_routing_object(project: Project, object_id: str) -> list[Derivation]:
    """A segment (W001-L3) or a branch point (W001-B2) by its ID, or as HARNESS.ID; [] for
    anything else. The first harness in natural ID order that has it."""
    for hid in sorted(project.harnesses, key=natural_key):
        h = project.harnesses[hid]
        for s in h.segments:
            if object_id in (s.id, f"{h.id}.{s.id}"):
                return [segment_derivation(project, h, s)]
        for b in h.branch_points:
            if object_id in (b.id, f"{h.id}.{b.id}"):
                return [branch_point_derivation(project, h, b.id)]
    return []


__all__ = [
    "LengthSource",
    "RoutingTree",
    "branch_point_derivation",
    "explain_routing_object",
    "length_source",
    "routing_tree",
    "segment_derivation",
]
