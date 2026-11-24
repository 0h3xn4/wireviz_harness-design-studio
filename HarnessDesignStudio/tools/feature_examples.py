# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The builders of the feature examples (the group *Feature examples* of `new --list`; design of
5.1.0, `docs/ait/DESIGN_5.1_FEATURE_TEMPLATES.md` section 4): small projects that show one feature
each, made with the edit functions a person's clicks call, every step through `History.execute`,
so each project is valid by construction and in the current format.

`tools/build_examples.py` merges `BUILDERS` into its own and writes the folders; a test fails while
a shipped folder differs from what the builder writes. Every name is made up for the example. A
builder that ends with an open design rule error stops the build, so a template cannot ship one.
"""

import json
from collections.abc import Callable, Mapping, Sequence

from harness_design_studio.core import (
    branching,
    devices,
    drc,
    edit,
    links,
    manual_harness,
    row_layout_edit,
    splices,
    wires,
)
from harness_design_studio.core.commands import History, Op, Put, SetConfig
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.model import Part, Project, RowLayout, evolve
from harness_design_studio.core.model.config import ConfigFile
from harness_design_studio.core.samples import new_project
from harness_design_studio.core.templates import template_info
from harness_design_studio.resources import examples_path


def _title(name: str) -> str:
    info = template_info(name)
    assert info is not None, name
    return info.title


def _no_errors(name: str, p: Project) -> None:
    errors = [f for f in drc.run(p) if f.severity == "error"]
    if errors:  # an example must open without errors
        raise SystemExit(f"{name} has {len(errors)} design rule errors, first: {errors[0].title}")


def _device(history: History, p: Project, uid: str, name: str, lane: int, y: float) -> None:
    """A device with no connectors yet, placed by hand in a lane (the Devices tab's *Add device*)."""
    ops, _ = devices.ops_add_device(p, unit_id=uid, name=name, x=edit.lane_x(lane), y=y)
    history.execute(f"add device {uid}", ops)


def _connector(
    history: History,
    p: Project,
    uid: str,
    part: str,
    carries: Sequence[str],
    pins: Sequence[tuple[str, str]],
    *,
    keying: str | None = None,
    directions: dict[str, str] | None = None,
    currents: Mapping[str, str] | None = None,
) -> str:
    """A box connector of `part` with every pin named and fixed (`pins`: pin, signal), pasted as
    the pin table takes a pasted pinout; `directions` gives the direction of some signals and
    `currents` the current through some pins (pin -> amperes, as the ICD states it)."""
    ops, cid = devices.ops_add_connector(p, uid, part_id=part, keying=keying, carries=carries)
    history.execute(f"add connector {cid}", ops)
    rows = []
    for pin, signal in pins:
        row = {"pin": pin, "signal": signal, "mode": "fixed"}
        if directions and signal in directions:
            row["direction"] = directions[signal]
        if currents and pin in currents:
            row["current_a"] = currents[pin]
        rows.append(row)
    history.execute(f"pinout of {cid}", devices.ops_paste_rows(p, cid, rows, replace=True))
    return cid


# ---- full-connectors: every pin used (section 4.1) ----------------------------------------------

# A nine-way Micro-D in two rows, 1 to 5 above 6 to 9: the power returns sit under their power pins.
_ROWS = RowLayout(rows=[["1", "2", "3", "4", "5"], ["6", "7", "8", "9"]])
_POWER_PINS = (
    ("1", "MAIN_PWR"), ("2", "KA_PWR"), ("3", "SURV_PWR"), ("4", "HTR+"), ("5", "GND"),
    ("6", "MAIN_RTN"), ("7", "KA_RTN"), ("8", "SURV_RTN"), ("9", "HTR-"),
)  # fmt: skip
_DATA_PINS = (
    ("1", "TX+"), ("2", "TX-"), ("3", "RX+"), ("4", "RX-"), ("5", "GND"),
    ("6", "CANH"), ("7", "CANL"), ("8", "SIG"), ("9", "RTN"),
)  # fmt: skip
_POWER_CARRIES = ("power_primary", "power_secondary", "heater", "ground")
_DATA_CARRIES = ("rs422", "can", "discrete", "ground")
# (type, port or "" for the pins named by the signal alone, name of the interface); per power line
_POWER_LINE = (
    ("power_primary", "MAIN", "Main power"),
    ("power_secondary", "KA", "Keep-alive power"),
    ("power_primary", "SURV", "Survival power"),
    ("heater", "", "Heater line"),
    ("ground", "", "Chassis ground"),
)
_DATA_LINE = (
    ("rs422", "", "Telecommands and telemetry"),
    ("can", "", "Housekeeping bus"),
    ("discrete", "", "Reset line"),
    ("ground", "", "Signal ground"),
)


def _on_port(p: Project, cid: str, port: str, iid: str) -> list:  # type: ignore[type-arg]
    """Put an interface on a port of a fixed pinout: a named port by *Assign… Port*, the pins
    named by the signal alone by *Assign pins* (`port` is "")."""
    if port:
        return devices.ops_assign_port(p, cid, port, iid)
    itype = p.interface_types[p.interfaces[iid].type_id]
    by_signal = {pin.signal: pin.id for pin in p.connectors[cid].pins}
    return devices.ops_assign_pins(p, cid, [by_signal[s.name] for s in itype.signals], iid)


def _full_connectors() -> Project:
    """Three devices whose six device connectors carry a signal on every pin: fixed pinouts with
    named ports, the pin rows of the parts, fourteen interfaces each put on its port, generated."""
    p = new_project(_title("full-connectors"))
    p.meta = evolve(
        p.meta,
        description="A power control unit feeds an on-board computer and a transceiver; the "
        "computer talks to the transceiver. Every pin of the six device connectors is fixed and "
        "named, so Generate uses them all: no spare pin is left. Each interface is put on its "
        "port by hand, because Generate gives the ports of one type in name order.",
    )
    history = History(p)
    for part in ("EX-MICROD-9-F", "EX-MICROD-9-M"):
        history.execute(
            f"pin rows of {part}", row_layout_edit.plan_set_row_layout(p, _ROWS, part=part)
        )
    _device(history, p, "PCDU1", "Power control unit", 0, 40.0)
    _device(history, p, "OBC1", "On-board computer", 1, 40.0)
    _device(history, p, "TTC1", "Transceiver", 1, 360.0)
    obc_out = {"TX+": "out", "TX-": "out", "RX+": "in", "RX-": "in"}
    ttc_in = {"TX+": "in", "TX-": "in", "RX+": "out", "RX-": "out"}
    c = {
        "PCDU1-J01": _connector(
            history, p, "PCDU1", "EX-MICROD-9-F", _POWER_CARRIES, _POWER_PINS, keying="A"
        ),  # fmt: skip
        "PCDU1-J02": _connector(
            history, p, "PCDU1", "EX-MICROD-9-F", _POWER_CARRIES, _POWER_PINS, keying="B"
        ),  # fmt: skip
        "OBC1-J01": _connector(history, p, "OBC1", "EX-MICROD-9-M", _POWER_CARRIES, _POWER_PINS),
        "OBC1-J02": _connector(
            history, p, "OBC1", "EX-MICROD-9-F", _DATA_CARRIES, _DATA_PINS, directions=obc_out
        ),  # fmt: skip
        "TTC1-J01": _connector(
            history, p, "TTC1", "EX-MICROD-9-M", _POWER_CARRIES, _POWER_PINS, keying="A"
        ),  # fmt: skip
        "TTC1-J02": _connector(
            history,
            p,
            "TTC1",
            "EX-MICROD-9-M",
            _DATA_CARRIES,
            _DATA_PINS,
            keying="B",
            directions=ttc_in,
        ),  # fmt: skip
    }
    assert sorted(c) == sorted(c.values()), c  # the IDs the builder names are the ones made
    for a, b, line in (
        ("PCDU1-J01", "OBC1-J01", _POWER_LINE),
        ("PCDU1-J02", "TTC1-J01", _POWER_LINE),
        ("OBC1-J02", "TTC1-J02", _DATA_LINE),
    ):
        ua, ub = p.connectors[a].unit_id, p.connectors[b].unit_id
        assert ua is not None and ub is not None
        for type_id, port, what in line:
            ops, iid = edit.ops_add_interface(p, type_id, ua, ub, a, b, name=f"{what} of {ub}" if ua == "PCDU1" else f"{what} to {ub}")  # fmt: skip
            history.execute("add interface", ops)
            for cid in (a, b):  # each interface on its port, not on the first free one
                history.execute(f"port of {iid} on {cid}", _on_port(p, cid, port, iid))
    generate_project(p)
    _no_errors("full-connectors", p)
    return p


# ---- the EXAMPLE parts and values of the splice templates (section 5.2, T5) ----------------------

SPLICE_PART = "EX-SPLICE-1"


def _splice_part(history: History, p: Project) -> None:
    """The EXAMPLE splice part (the row of the import template `splice-parts-EXAMPLE.csv`): one
    node, unverified and not approved, in the template's own library. The starter library has no
    splice part."""
    part = Part(
        id=SPLICE_PART,
        category="splice",  # splices.SPLICE_CATEGORY
        manufacturer="Example Co.",
        part_number=SPLICE_PART,
        description="Crimp splice, one node (EXAMPLE ONLY: not a real part)",
        pin_count=1,
        unverified=True,
    )
    history.execute(f"add part {SPLICE_PART}", [Put("parts", part)])


def _demo_values(history: History, p: Project) -> None:
    """The EXAMPLE values: the four files of `templates/config-demo-values/`, as a person copies
    them into `config/` (*Fill in the engineering values*); each file stays a placeholder."""
    root = examples_path()
    assert root is not None
    ops: list[Op] = []
    for path in sorted((root / "templates" / "config-demo-values").glob("*.json")):
        demo = json.loads(path.read_text(encoding="utf-8"))
        old = p.config[demo["name"]]
        values = {**old.values, **demo["values"]}
        ops.append(SetConfig(ConfigFile(name=old.name, placeholder=True, values=values)))
    history.execute("EXAMPLE values", ops)


def _metres_between(
    history: History, p: Project, hid: str, legs: Sequence[tuple[str, str, float]]
) -> None:
    """The segments of a harness drawn by hand, each with its EXAMPLE length in metres."""
    for a, b, metres in legs:
        ops, sid = branching.plan_add_segment(p, hid, a, b, metres)
        history.execute(f"segment {sid}", ops)


# ---- splice-by-hand: a power Y drawn by hand (section 4.3) --------------------------------------

_POWER_Y = (("1", "PWR"), ("2", "RTN"))
# The directions of the ICDs: the power output of PCDU1 drives both lines, the loads take them.
_SOURCE = {"PWR": "out", "RTN": "out"}
_LOAD = {"PWR": "in", "RTN": "in"}


def _splice_by_hand() -> Project:
    """A harness drawn by hand that takes one power output of PCDU1 to OBC1 and TTC1 through two
    splices of the EXAMPLE part `EX-SPLICE-1`: one for PWR, one for RTN."""
    p = new_project(_title("splice-by-hand"))
    p.meta = evolve(
        p.meta,
        description="One power output of PCDU1 feeds OBC1 and TTC1 through a harness drawn by "
        "hand: the PWR wires meet in the splice W001-X1 and the RTN wires in W001-X2. Look at "
        "the Splices list of the Harness tab and the column Via of the wire list; the manual "
        "page Splices explains each step.",
    )
    history = History(p)
    _splice_part(history, p)
    _device(history, p, "PCDU1", "Power control unit", 0, 40.0)
    _device(history, p, "OBC1", "On-board computer", 1, 40.0)
    _device(history, p, "TTC1", "Transceiver", 1, 360.0)
    boxes = {
        uid: _connector(history, p, uid, "EX-MICROD-9-F", (), _POWER_Y, directions=d)
        for uid, d in (("PCDU1", _SOURCE), ("OBC1", _LOAD), ("TTC1", _LOAD))
    }
    ops, hid = manual_harness.plan_new_harness(p, "Power Y")
    history.execute("new harness", ops)
    plug = {}
    for uid, box in boxes.items():
        ops, cid = manual_harness.plan_add_connector(p, hid, mates_with=box)
        history.execute(f"plug {cid}", ops)
        plug[uid] = cid
    node = {}
    for signal in ("PWR", "RTN"):
        ops, sid = splices.plan_add_splice(p, hid, SPLICE_PART, termination="crimp", name=signal)
        history.execute(f"splice {sid}", ops)
        node[signal] = sid
    colour = {"PWR": "red", "RTN": "black"}
    for pin, signal in _POWER_Y:  # AWG 22 to the splice, AWG 24 beyond it (EXAMPLE gauges)
        sid, look = node[signal], {"colour": colour[signal]}
        history.execute(
            f"wire {signal} to {sid}",
            wires.plan_add_wire(
                p, hid, plug["PCDU1"], pin, sid, "1", signal=signal, gauge_awg=22, **look
            ),
        )
        for far in ("OBC1", "TTC1"):
            history.execute(
                f"wire {signal} to {far}",
                wires.plan_add_wire(
                    p, hid, sid, "1", plug[far], pin, signal=signal, gauge_awg=24, **look
                ),
            )
    x1, x2 = node["PWR"], node["RTN"]
    _metres_between(
        history,
        p,
        hid,
        (
            (plug["PCDU1"], x1, 0.4),
            (x1, x2, 0.02),
            (x1, plug["OBC1"], 0.6),
            (x1, plug["TTC1"], 0.8),
        ),
    )  # EXAMPLE lengths: each splice is a node of the routing tree
    _no_errors("splice-by-hand", p)
    return p


# ---- splice-from-connection: a junction and the currents of its pins (section 4.4) --------------

# EXAMPLE contact ratings (amperes); with the factor 0.75 of the EXAMPLE values a contact of
# EX-DSUB-9-F may carry 7.5 A and one of EX-MICROD-9-M 3.75 A: one OBC1 contact would not carry
# the 4 A of the line, so the ICD splits it over two.
_CONTACT_RATINGS = {"EX-DSUB-9-F": 10.0, "EX-MICROD-9-M": 5.0}
_DATA = (("1", "TX+"), ("2", "TX-"), ("3", "RX+"), ("4", "RX-"))


def _splice_from_connection() -> Project:
    """Two devices joined by two connections: L1 takes the power pin of PCDU1 to two pins of OBC1
    (a junction, with the pin currents of the ICD), L2 is a data connection; the harness made
    from L1 gets a splice for each junction."""
    p = new_project(_title("splice-from-connection"))
    p.meta = evolve(
        p.meta,
        description="The connection L1 joins one PWR pin and one RTN pin of PCDU1 to two pins "
        "each of OBC1 (two junctions), so its harness W001 gets the splices W001-X1 and W001-X2; "
        "the pin currents say 4 A on the trunk and 2 A on each branch. The manual pages Connect "
        "two connectors and Splices explain it.",
    )
    history = History(p)
    _demo_values(history, p)
    _splice_part(history, p)
    for part, amperes in _CONTACT_RATINGS.items():
        rated = evolve(
            p.parts[part], ratings={**p.parts[part].ratings, "contact_current_a": amperes}
        )
        history.execute(f"rating of {part}", [Put("parts", rated)])
    _device(history, p, "PCDU1", "Power control unit", 0, 40.0)
    _device(history, p, "OBC1", "On-board computer", 1, 40.0)
    pcdu_power = _connector(
        history, p, "PCDU1", "EX-DSUB-9-F", (), (("1", "PWR"), ("2", "RTN")),
        currents={"1": "4", "2": "4"},
    )  # fmt: skip
    obc_power = _connector(
        history, p, "OBC1", "EX-MICROD-9-M", (),
        (("1", "PWR"), ("2", "PWR"), ("3", "RTN"), ("4", "RTN")),
        currents={"1": "2", "2": "2", "3": "2", "4": "2"},
    )  # fmt: skip
    pcdu_data = _connector(history, p, "PCDU1", "EX-MICROD-9-F", (), _DATA)
    obc_data = _connector(history, p, "OBC1", "EX-MICROD-9-M", (), _DATA)
    ops, power = links.plan_add_link(
        p, pcdu_power, obc_power, [("1", "1"), ("1", "2"), ("2", "3"), ("2", "4")],
        name="Power of OBC1",
    )  # fmt: skip
    history.execute(f"connection {power}", ops)
    ops, data = links.plan_add_link(p, pcdu_data, obc_data, name="Data of OBC1")  # the proposal
    history.execute(f"connection {data}", ops)
    ops, trunk_harness = links.plan_create_harness(p, power, SPLICE_PART)
    history.execute(f"harness of {power}", ops)
    ops, data_harness = links.plan_create_harness(p, data)
    history.execute(f"harness of {data}", ops)
    h = p.harnesses[trunk_harness]
    on_splice = {w.id for w in h.wires if w.to_connector in {s.id for s in splices.splices_of(h)}}
    # EXAMPLE gauges, the trunk thicker than the branches: AWG 18 carries 4 A and AWG 22 2 A with
    # the EXAMPLE derating (7 A x 0.8 x 0.9 = 5.04 A; 3 A x 0.72 = 2.16 A); AWG 22 and 24 would not
    for w in h.wires:
        gauge = 18 if w.id in on_splice else 22
        history.execute(f"gauge of {w.id}", wires.plan_wire_edit(p, [w.id], {"gauge_awg": gauge}))
    h = p.harnesses[data_harness]
    # RS-422 shields each pair (the starter type): TX+ TX- and RX+ RX- in a shielded pair each
    for pins in (("1", "2"), ("3", "4")):
        ids = [w.id for w in h.wires if w.from_pin in pins]
        history.execute(f"pair {ids}", wires.plan_group_wires(p, ids, "shielded_pair"))
    _no_errors("splice-from-connection", p)
    return p


BUILDERS: dict[str, Callable[[], Project]] = {
    "full-connectors": _full_connectors,
    "splice-by-hand": _splice_by_hand,
    "splice-from-connection": _splice_from_connection,
}
