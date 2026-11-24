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

from collections.abc import Callable, Sequence

from harness_design_studio.core import devices, drc, edit, row_layout_edit
from harness_design_studio.core.commands import History
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.model import Project, RowLayout, evolve
from harness_design_studio.core.samples import new_project
from harness_design_studio.core.templates import template_info


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
) -> str:
    """A box connector of `part` with every pin named and fixed (`pins`: pin, signal), pasted as
    the pin table takes a pasted pinout; `directions` gives the direction of some signals."""
    ops, cid = devices.ops_add_connector(p, uid, part_id=part, keying=keying, carries=carries)
    history.execute(f"add connector {cid}", ops)
    rows = []
    for pin, signal in pins:
        row = {"pin": pin, "signal": signal, "mode": "fixed"}
        if directions and signal in directions:
            row["direction"] = directions[signal]
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


BUILDERS: dict[str, Callable[[], Project]] = {
    "full-connectors": _full_connectors,
}
