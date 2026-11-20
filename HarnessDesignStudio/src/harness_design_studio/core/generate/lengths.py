# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Wire lengths from routing segments, and CSV import of segment lengths (from CAD exports)."""

import re
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal

from harness_design_studio.core import settings
from harness_design_studio.core.commands import Op, Put
from harness_design_studio.core.imports import Table
from harness_design_studio.core.model import Harness, Project, Segment, Wire, evolve


def _adjacency(h: Harness) -> dict[str, list[tuple[str, str, float | None]]]:
    graph: dict[str, list[tuple[str, str, float | None]]] = {}
    for s in h.segments:
        graph.setdefault(s.from_node, []).append((s.to_node, s.id, s.length_m))
        graph.setdefault(s.to_node, []).append((s.from_node, s.id, s.length_m))
    return graph


def _find_path(
    graph: dict[str, list[tuple[str, str, float | None]]], start: str, end: str, skip: str = ""
) -> list[tuple[str, float | None]] | None:
    """Segments (id, length) of a fewest-hops path from start to end that avoids segment `skip`."""
    seen = {start}
    queue: deque[tuple[str, list[tuple[str, float | None]]]] = deque([(start, [])])
    while queue:
        node, trail = queue.popleft()
        if node == end:
            return trail
        for nxt, sid, length in graph.get(node, []):
            if nxt not in seen and sid != skip:
                seen.add(nxt)
                queue.append((nxt, [*trail, (sid, length)]))
    return None


def path_trail(h: Harness, start: str, end: str) -> list[tuple[str, float | None]] | None:
    """The segments (ID, length) along the one path in the harness tree from start to end, in
    order; None if there is no path or the segments form a loop that the path can take either way.

    The one path rule of the tool (builder, tables, rules, derivations): the path must be unique,
    otherwise there is no single length and the design rule `segment-loop` reports the loop."""
    graph = _adjacency(h)
    trail = _find_path(graph, start, end)
    if trail is None:
        return None
    if any(_find_path(graph, start, end, sid) is not None for sid, _ in trail):
        return None  # a second route exists: not a tree path
    return trail


def path_length(h: Harness, start: str, end: str) -> float | None:
    """Sum of segment lengths along the path in the harness tree; None if any is unknown
    (or there is no unique path: see `path_trail`)."""
    trail = path_trail(h, start, end)
    if trail is None:
        return None
    lengths = [length for _, length in trail]
    return (
        None if any(x is None for x in lengths) else float(sum(x for x in lengths if x is not None))
    )


def loop_segments(h: Harness) -> list[str]:
    """IDs of segments that close a loop (a segment graph must be a tree or a forest), in ID order."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    closing = []
    for s in sorted(h.segments, key=lambda x: x.id):
        a, b = find(s.from_node), find(s.to_node)
        if a == b:
            closing.append(s.id)
        else:
            parent[a] = b
    return closing


_PATHS: dict[tuple[int, str, str], tuple[Harness, float | None]] = {}
_PATHS_LIMIT = (
    512  # the cache keeps its harnesses alive: bounded, so a long editing session cannot grow it
)


def clear_length_cache() -> None:
    _PATHS.clear()


def generated_length(project: Project, path_m: float, loop_m: float, construction: str) -> float:
    """The length generation gives a wire: the path through the segments plus the service loops
    (`model.service_loops_per_wire` of them, each `loop_m`). The model `path_loops_allowance_twist`
    adds the take-up of twisting for a twisted construction (a fraction of what is there so far) and
    then a cut allowance. The one function of generation and of the explanation: A-SERVICE-LOOP."""
    length = path_m + settings.service_loops(project) * loop_m
    if settings.choice(project, "model", "length_model") == "path_loops_allowance_twist":
        if construction in settings.TWISTED_CONSTRUCTIONS:
            length *= 1 + settings.number(project, "model", "twist_takeup_fraction")
        length += settings.number(project, "model", "cut_allowance_m")
    return length


def wire_length(h: Harness, w: Wire) -> float | None:
    """The wire's own length, else the sum of routing segments between its connectors.
    The one place that answers 'how long is this wire' (tables, mass, rules and the release gate)."""
    if w.length_m is not None:
        return w.length_m
    if not h.segments:
        return None
    key = (id(h), w.from_connector, w.to_connector)
    hit = _PATHS.get(key)
    if hit is None or hit[0] is not h:  # the identity check guards against reused object ids
        if len(_PATHS) >= _PATHS_LIMIT:
            _PATHS.clear()
        hit = _PATHS[key] = (h, path_length(h, w.from_connector, w.to_connector))
    return hit[1]


# Where a wire's length comes from, as the Production sheet says it (design of 4.1.0, section 6.3).
ORIGIN_ON_WIRE = "on the wire"  # `Wire.length_m`, not locked: Generate's length or an imported one
ORIGIN_LOCKED = "locked"  # a length Generate keeps: typed in on a locked wire, or overridden
ORIGIN_SEGMENTS = "segments only, no service loops"  # no length of its own: the path alone
ORIGIN_NONE = ""  # no length at all: the cell reads *to fill in*


def length_origin(h: Harness, w: Wire) -> str:
    """Where the length of a wire comes from, read from the wire and the segments only: its own
    length (`on the wire`, or `locked` when Generate keeps it, `length_is_kept`), the segments of its path
    (`segments only, no service loops`), or nothing (empty). It does not tell a generated length
    from an imported one; `derive.wire_length_derivation` does, and starts from this answer."""
    if w.length_m is not None:
        return ORIGIN_LOCKED if length_is_kept(w) else ORIGIN_ON_WIRE
    return ORIGIN_SEGMENTS if wire_length(h, w) is not None else ORIGIN_NONE


def length_is_kept(w: Wire) -> bool:
    """Whether Generate keeps the wire's length: a locked wire with no override (a person entered
    it), or one whose length is overridden. A wire locked by an override of its gauge, part or
    colour only gets the length of its path again (`engine`: "the other values follow the
    design"), so its length is not *locked*."""
    return w.locked and (not w.overrides or "length_m" in w.overrides)


def _number_text(v: float) -> str:
    """A number of the settings as the project holds it: the shortest text that reads back as the
    value, without an exponent (0.1, 2, 0.05)."""
    r = round(v, 9) + 0.0
    text = repr(r)
    if "e" in text or "E" in text:
        text = format(Decimal(text), "f")
    return text[:-2] if text.endswith(".0") else text


def reference_text(project: Project) -> str:
    """What every length of a document is measured from, in words from the settings in force
    (design of 4.1.0, section 6.1): from the rear of a connector along the segments, through the
    centre of each branch point, to the rear of the other; what Generate adds (the service loops
    of `model.service_loops_per_wire` and `generation.service_loop_m`, and under the length model
    `path_loops_allowance_twist` the take-up of twisting and the cut allowance). Every number is
    the project's; none is invented."""
    loops = settings.service_loops(project)
    raw = settings.effective(project, "generation", "service_loop_m").value
    loop = float(raw) if isinstance(raw, int | float) and not isinstance(raw, bool) else None
    if loop is None:
        added = "no service loop (config/generation.json: service_loop_m is not set)"
    elif loops == 0:
        added = "no service loop (config/model.json: service_loops_per_wire is 0)"
    else:
        added = f"{loops} service loop{'' if loops == 1 else 's'} of {_number_text(loop)} m"
    if settings.choice(project, "model", "length_model") == "path_loops_allowance_twist":
        takeup = _number_text(settings.number(project, "model", "twist_takeup_fraction"))
        cut = _number_text(settings.number(project, "model", "cut_allowance_m"))
        added += (
            f", the take-up of twisting ({takeup}) for a wire of a twisted construction, and a "
            f"cut allowance of {cut} m"
        )
    return (
        "Lengths run from the rear of a connector (where the wires leave its body or backshell) "
        "along the routing segments, through the centre of each branch point, to the rear of the "
        f'other connector. A wire Generate made adds {added}. "Locked" is a length a person '
        'typed; "segments only" has no service loops.'
    )


@dataclass
class LengthRow:
    row_number: int
    ok: bool
    message: str
    values: tuple[str, ...]
    metres: float | None = None  # the length as stored, for a row that is accepted


@dataclass
class LengthPlan:
    rows: list[LengthRow] = field(default_factory=list)
    ops: list[Op] = field(default_factory=list)
    hint: str = ""  # shown after the row messages when they all share one likely cause


_NUMBER = re.compile(r"[0-9]+([.,][0-9]+)?|[.,][0-9]+")  # no exponents, signs or underscores
MAX_LENGTH_M = 10_000.0
# the units a length file may be in, as metres per unit (`import-lengths --unit`, and the strip and
# accessory lengths of `import-build-data --unit`, which are stored in millimetres)
LENGTH_UNITS_M: dict[str, float] = {"mm": 0.001, "cm": 0.01, "m": 1.0, "in": 0.0254, "ft": 0.3048}


def plan_length_import(
    project: Project,
    table: Table,
    columns: tuple[int, int, int] = (0, 1, 2),
    scale: float = 1.0,
) -> LengthPlan:
    """Rows: harness ID, segment ID, length. `scale` converts the file's unit to metres (0.001 for
    millimetres, D-13). Applies as one undo step after confirmation."""
    plan = LengthPlan()
    if table and len(table[0]) > columns[2] and _NUMBER.fullmatch(table[0][columns[2]].strip()):
        plan.rows.append(
            LengthRow(
                1,
                False,
                "The first row must be the column headings (harness, segment, length), not data",
                tuple(table[0][c] if c < len(table[0]) else "" for c in columns),
            )
        )
        return plan
    pending: dict[str, Harness] = {}
    given: dict[
        tuple[str, str], tuple[float, int, str]
    ] = {}  # (harness, segment) -> (metres, row, text)
    for n, row in enumerate(table[1:], start=2):
        vals = tuple(row[c].strip() if c < len(row) else "" for c in columns)
        hid, sid, text = vals
        error = ""
        h = pending.get(hid) or project.harnesses.get(hid)
        if h is None:
            error = f"Harness '{hid}' does not exist"
        elif h.status == "released":
            error = f"Harness '{hid}' is released and locked"
        elif sid not in {s.id for s in h.segments}:
            error = f"Harness '{hid}' has no segment '{sid}'"
        else:
            try:
                if not _NUMBER.fullmatch(text.strip()):
                    raise ValueError
                length = round(float(text.strip().replace(",", ".")) * scale, 9)
            except ValueError:
                error = f"'{text}' is not a length (digits with a decimal point or comma)"
            else:
                if length > MAX_LENGTH_M:
                    error = f"'{text}' is too large (a length can be at most {MAX_LENGTH_M:g} m)"
                elif (hid, sid) in given and given[hid, sid][0] != length:
                    _, first, first_text = given[hid, sid]
                    error = (
                        f"Segment '{sid}' of harness '{hid}' is given again with another "
                        f"length (row {first} says '{first_text}', this row says '{text}'); "
                        "keep one of the rows"
                    )
        if not error and h is not None:
            given.setdefault((hid, sid), (length, n, text))
            segs = [evolve(s, length_m=length) if s.id == sid else s for s in h.segments]
            pending[hid] = evolve(h, segments=segs)
        plan.rows.append(LengthRow(n, not error, error, vals, None if error else length))
    plan.ops = [Put("harnesses", h) for h in pending.values()]
    if plan.rows and all(r.message.endswith("does not exist") for r in plan.rows):
        # the columns are read by position, so a file with another order fails on every row
        # with a message about the harness name, which hides the real cause
        head = ", ".join(c.strip() or "(empty)" for c in table[0][:3])
        plan.hint = (
            "Every row failed on the harness name. The columns are read by position: harness, "
            f"segment, length. The headings of the file read: {head}. If they are in another "
            "order, reorder the columns and try again."
        )
    return plan


def segment_lengths_known(h: Harness) -> bool:
    return bool(h.segments) and all(s.length_m is not None for s in h.segments)


__all__ = [
    "LENGTH_UNITS_M",
    "ORIGIN_LOCKED",
    "ORIGIN_NONE",
    "ORIGIN_ON_WIRE",
    "ORIGIN_SEGMENTS",
    "LengthPlan",
    "LengthRow",
    "Segment",
    "length_origin",
    "loop_segments",
    "path_length",
    "plan_length_import",
    "reference_text",
    "segment_lengths_known",
]
