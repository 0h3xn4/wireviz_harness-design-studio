# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The independent verifier's own wording of the Production sheet (design of 4.1.0, section 3.6).

`production_rows(project, h)` words every block heading and every row of the Production sheet a
second time from the project. It imports neither the rows of the core (`production.py`) nor the
workbook, the plan or the tables (`buildsheet.py`, `harness_plan.py`, `tables.py`), nor the label
rules (`core/label_format.py`) or the shield ends (`core/shield_ends.py`), nor the length rules
(`core/generate/lengths.py`): it holds its own copies of the folding of spare runs, the far end and
its brackets, the end of a shield group at a connector (`_end_at`), the length of a wire on the
one path through the segments (`_length`), where the length comes from (`_length_origin`) and the
sentences that say what a length is measured from (`_length_lines`, joined by `_length_reference`). The label texts are the
verifier's own copy in `verify_labels.py`. `tests/test_production_verify.py` reads the imports
and compares every row with the core's on the examples, the fixtures and random harnesses.

`verify.py` (`_build_production`) checks the Production sheet of the build workbook with it, row
by row, with the headings `_HEADER` stated here a second time; `verify_plan.py` takes it up with
the plan's sheet (pull request 5 of the design)."""

from dataclasses import dataclass
from decimal import Decimal
from itertools import groupby

from harness_design_studio.core import settings
from harness_design_studio.core.model import Connector, Harness, Project, ShieldGroup, Wire
from harness_design_studio.core.model.physical import LOOSE_ROLE, SPLICE_ROLE
from harness_design_studio.core.wirecolours import resolve

from .verify_labels import _OPEN_END, _connector_label_text, _label_format, _wire_label_texts

# ---- the words of the sheet, stated here a second time (never imported from production.py) ----
_TO_FILL = "to fill in"
_DOT = "   ·   "
_HEADER = (
    "Pin", "Signal", "Wire", "Goes to", "Wire part", "Colour", "AWG", "Length (m), rear to rear",
    "Length from", "Label at this end", "Shield group: here / far end",
)  # fmt: skip
_NO_WIRE = "(no wire)"
_SPARE = "(spare)"
_UNPLUGGED = "not plugged into a unit"
_NO_GENDER = "gender not set"
_LOOSE_TAG = " (loose end)"
_ACROSS = "here not defined (the group ends on more than two connectors)"
_END_TEXT = {"backshell_360": "backshell 360", "pigtail": "pigtail", "floating": "floating"}
_KIND_TEXT = {
    "twisted_pair": "twisted pair", "shielded_pair": "shielded pair",
    "overall_shield": "overall shield", "quad": "quad", "coax": "coax",
}  # fmt: skip
# where a length comes from (section 6.3)
_FROM_WIRE, _FROM_LOCKED, _FROM_SEGMENTS = (
    "on the wire",
    "locked",
    "segments only, no service loops",
)

Value = str | int | float


@dataclass(frozen=True)
class Block:
    """One block as the verifier expects it: the connector, whether it is a splice, the heading
    and the rows (each the eleven columns, the length in metres)."""

    connector_id: str
    splice: bool
    heading: str
    rows: tuple[tuple[Value, ...], ...]


def _natural(text: str) -> tuple[tuple[tuple[int, int | str], ...], str]:
    """`W001-P2` before `W001-P10`: digits as numbers, the rest as text (and the text last, so two
    IDs that read the same as numbers keep one order)."""
    parts: list[tuple[int, int | str]] = []
    for digits, chars in groupby(text, key=str.isdecimal):
        piece = "".join(chars)
        parts.append((1, int(piece)) if digits else (0, piece))
    if text[:1].isdecimal():
        parts.insert(0, (0, ""))
    return tuple(parts), text


# ---- the length of a wire, where it comes from and what it is measured from ---------------------


def _length(h: Harness, w: Wire) -> float | None:
    """The wire's own length, else the sum of the segments on the one path between its
    connectors; None when a segment on it has no length, no path joins them, or a second route
    exists (the segments form a loop the path could take either way)."""
    if w.length_m is not None:
        return w.length_m
    if not h.segments:
        return None
    start, goal = w.from_connector, w.to_connector
    if start == goal:
        return 0.0
    links: dict[str, list[tuple[str, str]]] = {}
    for s in h.segments:
        links.setdefault(s.from_node, []).append((s.id, s.to_node))
        links.setdefault(s.to_node, []).append((s.id, s.from_node))

    def route(avoid: str | None) -> list[str] | None:
        back: dict[str, tuple[str, str] | None] = {start: None}
        todo = [start]
        while todo:
            node = todo.pop()
            for sid, nxt in links.get(node, []):
                if sid != avoid and nxt not in back:
                    back[nxt] = (node, sid)
                    todo.append(nxt)
        if goal not in back:
            return None
        sids: list[str] = []
        at = goal
        while (step := back[at]) is not None:
            at, sid = step
            sids.append(sid)
        return sids[::-1]

    path = route(None)
    if path is None or any(route(sid) is not None for sid in path):
        return None
    lengths = {s.id: s.length_m for s in h.segments}
    values = [lengths[sid] for sid in path]
    return (
        None if any(v is None for v in values) else float(sum(v for v in values if v is not None))
    )


def _length_origin(h: Harness, w: Wire) -> str:
    if w.length_m is not None:
        return _FROM_LOCKED if w.locked else _FROM_WIRE
    return "" if _length(h, w) is None else _FROM_SEGMENTS


def _figure(v: float) -> str:
    """A number of the settings: the shortest text that reads back as it, with no exponent."""
    text = format(Decimal(repr(round(v, 9) + 0.0)), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _setting(project: Project, file: str, key: str) -> object:
    e = settings.effective(project, file, key)
    if e.setting.choices:
        return e.value if e.value in e.setting.choices else e.setting.default
    return e.value


def _length_reference(project: Project) -> str:
    """The sentences of `_length_lines` as one text."""
    return " ".join(_length_lines(project))


def _length_lines(project: Project) -> tuple[str, str, str]:
    """What every length of a document is measured from, worded from the settings in force, as the
    three sentences a sheet prints on a row each."""
    count = _setting(project, "model", "service_loops_per_wire")
    each = _setting(project, "generation", "service_loop_m")
    if isinstance(each, bool) or not isinstance(each, int | float):
        loops = "no service loop (config/generation.json: service_loop_m is not set)"
    elif count == 0:
        loops = "no service loop (config/model.json: service_loops_per_wire is 0)"
    else:
        n = int(count) if isinstance(count, int | float) else 0
        loops = f"{n} service loop{'s' if n != 1 else ''} of {_figure(float(each))} m"
    if _setting(project, "model", "length_model") == "path_loops_allowance_twist":
        takeup = _setting(project, "model", "twist_takeup_fraction")
        cut = _setting(project, "model", "cut_allowance_m")
        if not isinstance(takeup, int | float) or not isinstance(cut, int | float):
            raise ValueError("the take-up of twisting and the cut allowance must be numbers")
        loops = (
            f"{loops}, the take-up of twisting ({_figure(float(takeup))}) for a wire of a "
            f"twisted construction, and a cut allowance of {_figure(float(cut))} m"
        )
    return (
        "Lengths run from the rear of a connector (where the wires leave its body or backshell) "
        "along the routing segments, through the centre of each branch point, to the rear of the "
        "other connector.",
        f"A wire Generate made adds {loops}.",
        '"Locked" is a length a person typed; "segments only" has no service loops.',
    )


# ---- the shield ends --------------------------------------------------------------------------


def _end_at(h: Harness, s: ShieldGroup, cid: str) -> str | None:
    """ "a" at the `from` connector of the group's wire with the lowest ID in the harness, "b" at
    its `to` connector, None anywhere else (the verifier's copy of `shield_ends.end_at`)."""
    members = [w for w in h.wires if w.id in set(s.wire_ids)]
    if not members:
        return None
    first = min(members, key=lambda w: w.id)
    return {first.to_connector: "b", first.from_connector: "a"}.get(cid)


def _shield_cell(h: Harness, w: Wire, cid: str) -> str:
    texts = []
    for s in sorted((g for g in h.shields if w.id in g.wire_ids), key=lambda g: _natural(g.id)):
        kind = _KIND_TEXT.get(s.kind, s.kind)
        if s.kind == "twisted_pair":
            texts.append(f"{s.id} {kind}")
            continue
        end = _end_at(h, s, cid)
        if end is None:
            texts.append(f"{s.id} {kind}: {_ACROSS}")
            continue
        here, far = (s.end_a, s.end_b) if end == "a" else (s.end_b, s.end_a)
        texts.append(f"{s.id} {kind}: here {_END_TEXT[here]}, far {_END_TEXT[far]}")
    return "; ".join(texts)


# ---- the blocks -------------------------------------------------------------------------------


def _plugged(project: Project, c: Connector) -> str | None:
    box = project.connectors.get(c.mates_with or "")
    if box is None:
        return None
    return box.name if not box.unit_id else f"{box.unit_id}:{box.name}"


def _head(project: Project, h: Harness, c: Connector, fmt: str) -> str:
    if c.role == SPLICE_ROLE:
        n = len(c.pins)
        words = [c.id, c.part_id, "splice", "1 node" if n == 1 else f"{n} nodes"]
    else:
        if c.role == LOOSE_ROLE:
            words = [c.id, c.part_id + _LOOSE_TAG, f"{_OPEN_END}, {_TO_FILL}"]
        else:
            box = _plugged(project, c)
            gender = _NO_GENDER if c.gender == "unspecified" else c.gender
            plug = _UNPLUGGED if box is None else f"mates {c.mates_with} ({box})"
            words = [c.id, c.part_id, gender, plug]
        words.append("label " + _connector_label_text(project, h, c, fmt))
    places = [
        (f"label at {a.position}" if a.position else f"label, position {_TO_FILL}")
        for a in sorted(h.accessories, key=lambda x: _natural(x.id))
        if a.kind == "label" and a.target == c.id
    ]
    return _DOT.join([*words, *(["; ".join(places)] if places else [])])


def _far_end(project: Project, h: Harness, cid: str, pin: str) -> str:
    end = f"{cid}.{pin}"
    c = next((x for x in h.connectors if x.id == cid), None)
    if c is None:
        return end
    if c.role == SPLICE_ROLE:
        return f"{end} (splice)"
    if c.role == LOOSE_ROLE:
        return f"{end} ({_OPEN_END})"
    box = _plugged(project, c)
    return end if box is None else f"{end} ({box})"


def _colour(name: str | None) -> str:
    if not name:
        return _TO_FILL
    code = resolve(name)[0]
    return name if not code or code == name.upper() else f"{name} ({code})"


def _rows(project: Project, h: Harness, c: Connector, fmt: str) -> list[tuple[Value, ...]]:
    out: list[tuple[Value, ...]] = []
    spare: list[str] = []
    empty = ("",) * 8
    for p in c.pins:
        here = [(w, "a") for w in h.wires if (w.from_connector, w.from_pin) == (c.id, p.id)]
        here += [(w, "b") for w in h.wires if (w.to_connector, w.to_pin) == (c.id, p.id)]
        if not here and not (p.signal or p.interface_id):
            spare.append(p.id)
            continue
        if spare:
            out.append((spare[0] if len(spare) == 1 else f"{spare[0]} to {spare[-1]}", "", _SPARE, *empty))  # fmt: skip
            spare = []
        if not here:
            out.append((p.id, p.signal or "", _NO_WIRE, *empty))
        for w, end in sorted(here, key=lambda x: (x[0].id, x[1])):
            far_cid, far_pin = (w.to_connector, w.to_pin) if end == "a" else (w.from_connector, w.from_pin)  # fmt: skip
            length = _length(h, w)
            label_a, label_b = _wire_label_texts(project, h, w, fmt)
            out.append((
                p.id, p.signal or w.signal or "", w.id, _far_end(project, h, far_cid, far_pin),
                w.part_id or _TO_FILL, _colour(w.colour),
                _TO_FILL if w.gauge_awg is None else w.gauge_awg,
                _TO_FILL if length is None else round(length, 9) + 0.0,
                _length_origin(h, w), label_a if end == "a" else label_b,
                _shield_cell(h, w, c.id),
            ))  # fmt: skip
    if spare:
        out.append((spare[0] if len(spare) == 1 else f"{spare[0]} to {spare[-1]}", "", _SPARE, *empty))  # fmt: skip
    return out


def production_rows(project: Project, h: Harness) -> list[Block]:
    """Every block of the Production sheet of `h` as the verifier words it: the cable connectors
    in natural ID order, then the splices."""
    fmt = _label_format(project)
    order = sorted(h.connectors, key=lambda c: (c.role == SPLICE_ROLE, _natural(c.id)))
    return [
        Block(
            c.id, c.role == SPLICE_ROLE, _head(project, h, c, fmt), tuple(_rows(project, h, c, fmt))
        )  # fmt: skip
        for c in order
    ]
