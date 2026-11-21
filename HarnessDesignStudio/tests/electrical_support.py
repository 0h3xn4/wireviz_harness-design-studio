# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Projects for the tests of the electrical rules of 4.2.0 (`core/drc/electrical.py`, design
`docs/ait/DESIGN_4.2_ELECTRICAL_CHECKS.md`). Example data only, no engineering values.

`linked()` is `tests.helpers.pinout_project` without its harnesses (mini3 with RS-422 pins TX+, TX-, RX+, RX- on OBC-J01
and RW1-J02) with a connection between the two connectors and the harness made from it (W001: four
wires drawn by the tool, no interface, no group). `hand_made()` is a harness drawn by hand between
two device connectors of mini3 (without its harnesses) whose pins carry the signals given; `spliced()` one through a splice to three
device connectors."""

from collections.abc import Sequence

from harness_design_studio.core.commands import Put, apply_ops
from harness_design_studio.core.links import plan_add_link, plan_create_harness
from harness_design_studio.core.manual_harness import plan_add_connector, plan_new_harness
from harness_design_studio.core.model import InterfaceType, Pin, Project, SignalDef, evolve
from harness_design_studio.core.samples import mini3
from harness_design_studio.core.splices import plan_add_splice
from harness_design_studio.core.wires import plan_add_wire, plan_group_wires
from tests.helpers import pinout_project
from tests.splice_support import SPLICE_PART, splice_part


def bare() -> Project:
    """mini3 without its harnesses: no net but those a test makes."""
    p = mini3()
    p.harnesses.clear()
    return p


def linked(*, carries: bool = True) -> tuple[Project, str]:
    """The pinout project with a connection OBC-J01 to RW1-J02 and its harness; `carries=False`
    takes the interface types the two connectors are meant for away, so every type that has a
    signal counts."""
    p = pinout_project()
    p.harnesses.clear()
    if not carries:
        for cid in ("OBC-J01", "RW1-J02"):
            p.connectors[cid] = evolve(p.connectors[cid], carries=[])
    ops, lid = plan_add_link(p, "OBC-J01", "RW1-J02")
    apply_ops(p, ops)
    ops, hid = plan_create_harness(p, lid)
    apply_ops(p, ops)
    return p, hid


def set_signals(
    p: Project,
    cid: str,
    signals: Sequence[str | None],
    *,
    fixed: bool = False,
    levels: Sequence[str | None] = (),
    directions: Sequence[str] = (),
) -> None:
    """Pins 1..n of a device connector with these signals (None: no signal), and the levels and
    directions given (by position; missing: none)."""
    pins = [
        Pin(
            id=str(k + 1),
            signal=s,
            fixed=fixed and s is not None,
            level=levels[k] if k < len(levels) else None,
            direction=directions[k] if k < len(directions) else "",  # type: ignore[arg-type]
        )
        for k, s in enumerate(signals)
    ]
    p.connectors[cid] = evolve(p.connectors[cid], pins=pins, carries=[])


def set_pin(p: Project, cid: str, pin_id: str, **fields: object) -> None:
    """One field or more of one pin of a device connector."""
    c = p.connectors[cid]
    pins = [evolve(x, **fields) if x.id == pin_id else x for x in c.pins]
    p.connectors[cid] = evolve(c, pins=pins)


def hand_made(
    a: Sequence[str | None],
    b: Sequence[str | None],
    wires: Sequence[tuple[str, str]],
    *,
    fixed: bool = False,
    project: Project | None = None,
) -> tuple[Project, str]:
    """A harness drawn by hand between OBC-J03 and RW1-J02 of mini3, whose pins carry the signals
    `a` and `b`; `wires` are (pin on OBC-J03, pin on RW1-J02)."""
    p = project or bare()
    set_signals(p, "OBC-J03", a, fixed=fixed)
    set_signals(p, "RW1-J02", b, fixed=fixed)
    ops, hid = plan_new_harness(p, "Drawn")
    apply_ops(p, ops)
    ends = []
    for box in ("OBC-J03", "RW1-J02"):
        ops, cid = plan_add_connector(p, hid, mates_with=box)
        apply_ops(p, ops)
        ends.append(cid)
    for x, y in wires:
        apply_ops(p, plan_add_wire(p, hid, ends[0], x, ends[1], y))
    return p, hid


def spliced(near: str | None, far_a: str | None, far_b: str | None) -> tuple[Project, str]:
    """mini3 and a harness drawn by hand from PCDU-J02 through the splice X1 to OBC-J02 and OBC-J03:
    pin 1 of each joined on the node of the splice (three wires). The arguments are the levels of
    pin 1 of the three device connectors (a level, or None), the signals TX+ on each."""
    p = bare()
    for cid, level in (("PCDU-J02", near), ("OBC-J02", far_a), ("OBC-J03", far_b)):
        set_signals(p, cid, ["TX+", None], levels=[level])
    apply_ops(p, [Put("parts", splice_part())])
    ops, hid = plan_new_harness(p, "Spliced")
    apply_ops(p, ops)
    ends = []
    for box in ("PCDU-J02", "OBC-J02", "OBC-J03"):
        ops, cid = plan_add_connector(p, hid, mates_with=box)
        apply_ops(p, ops)
        ends.append(cid)
    ops, x1 = plan_add_splice(p, hid, SPLICE_PART, termination="crimp")
    apply_ops(p, ops)
    apply_ops(p, plan_add_wire(p, hid, ends[0], "1", x1, "1"))
    for far in ends[1:]:
        apply_ops(p, plan_add_wire(p, hid, x1, "1", far, "1"))
    return p, hid


def group(p: Project, wire_ids: Sequence[str], kind: str) -> None:
    apply_ops(p, plan_group_wires(p, wire_ids, kind))


def add_type(p: Project, tid: str, signals: Sequence[tuple[str, str | None]], **kw: object) -> None:
    """An interface type of the project's own (example data)."""
    t = InterfaceType.model_validate(
        {
            "id": tid,
            "name": tid,
            "category": "data",
            "signals": [SignalDef(name=n, direction="out", pair=pair) for n, pair in signals],
            **kw,
        }
    )
    apply_ops(p, [Put("interface_types", t)])


def titles(hits: object) -> list[str]:
    return [h.title for h in hits]  # type: ignore[attr-defined]
