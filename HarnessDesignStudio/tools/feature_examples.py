# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The builders of the feature examples (the group *Feature examples* of `new --list`; design of
5.1.0, `docs/ait/DESIGN_5.1_FEATURE_TEMPLATES.md` section 4): small projects that show one feature
each, made with the edit functions a person's clicks call, every step through `History.execute`,
so each project is valid by construction and in the current format.

`tools/build_examples.py` merges `BUILDERS` into its own and writes the folders; a test fails while
a shipped folder differs from what the builder writes. Every name is made up for the example. A
builder that ends with an open design rule error stops the build, so a template cannot ship one.
`BESIDE` gives, for the two examples that keep files beside their model (`extensions/`,
`device-libraries.json` and a library folder; part C of the design), those files by their path in
the example's folder; `core.templates.create_project` copies them into a new project.
"""

import csv
import json
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from harness_design_studio.core import (
    asbuilt,
    branching,
    build_data,
    build_data_import,
    checks,
    configcheck,
    connector_edit,
    device_check,
    devices,
    document,
    drc,
    edit,
    import_reports,
    kicad,
    library_folder,
    library_import,
    library_link,
    library_pointer,
    links,
    manual_harness,
    pinout_import,
    plan_config,
    review,
    row_layout_edit,
    signal_map,
    splices,
    wires,
)
from harness_design_studio.core import imports as imports_table
from harness_design_studio.core import subsystem_library as subsystems
from harness_design_studio.core.commands import History, Op, Put, SetConfig
from harness_design_studio.core.extensions import manager as extensions_manager
from harness_design_studio.core.generate import lengths
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.import_record import ImportReport, file_sha256, record_ops
from harness_design_studio.core.imports import read_table_sheet
from harness_design_studio.core.library_git import library_git
from harness_design_studio.core.model import Part, Project, RowLayout, evolve
from harness_design_studio.core.model.config import ConfigFile
from harness_design_studio.core.outputs.build import build_outputs, write_outputs
from harness_design_studio.core.samples import new_project
from harness_design_studio.core.templates import template_info
from harness_design_studio.core.vcs import release
from harness_design_studio.core.vcs.release import ReleasePlan
from harness_design_studio.resources import examples_path


def _title(name: str) -> str:
    info = template_info(name)
    assert info is not None, name
    return info.title


def _no_errors(name: str, p: Project) -> None:
    errors = [f for f in drc.run(p) if f.severity == "error" and f.waiver is None]
    if errors:  # an example must open without an open error (a deviation is accepted, not open)
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
    history.execute(f"pinout of {cid}", devices.ops_paste_rows(p, cid, rows, replace=False))
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


# ---- imports, made by the functions the import commands call --------------------------------------


def _write_table(folder: Path, name: str, rows: Sequence[Sequence[str]]) -> Path:
    """A table as a team hands it over, written into a scratch folder (CSV, `\\n` line ends), so
    that an import reads a file and records its name and SHA-256 (the same bytes each build)."""
    path = folder / name
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)
    return path


def _recorded(
    history: History, p: Project, label: str, ops: list[Op], report: ImportReport
) -> None:
    """The changes of an import and its import record (`imports/records.json`) as one step, as the
    import commands save them."""
    history.execute(label, [*ops, *record_ops(p, report.record())])


def _import_pinout(
    history: History,
    p: Project,
    path: Path,
    unit_id: str,
    *,
    new_device: str | None = None,
) -> None:
    """`import-pinout DIR FILE --device UNIT [--new-device NAME]`: the pinout read through the
    project's signal map, a row that is refused stops the build."""
    table, sheet = pinout_import.read_pinout_table(path)
    mapping = pinout_import.guess_mapping(table[0])
    plan = pinout_import.plan_pinout_import(
        p, table, mapping, unit_id=unit_id, new_unit_name=new_device
    )
    if plan.bad_count or not plan.ops:
        raise SystemExit(f"{path.name}: {[r.message for r in plan.rows if not r.ok]}")
    report = import_reports.pinout_report(path, None, table, mapping, plan, sheet=sheet)
    _recorded(history, p, plan.label, plan.ops, report)


# ---- names-and-ports: the far device in the pin name (section 4.2) -------------------------------

# The pinouts in the team's words (TXP for TX+ ...), as the ICDs of the three devices give them;
# the project's signal map (the import template `signal-map.csv`) renames them at the import, also
# inside a port (TTC1_TXP becomes TTC1_TX+). Pin 9 of OBC1-J01 and pin 5 of each TTC are spares.
_TEAM_WORDS = ("TXP", "TXN", "RXP", "RXN")
_PINOUT_HEADING = ("Connector", "Pin", "Signal", "Mode", "Direction", "Part")


def _team_pinout(part: str, signals: Sequence[str], out: Sequence[str]) -> list[list[str]]:
    """The rows of one nine-way connector J1: the signals on pins 1 onwards (fixed, a direction
    `OUT` for the names in `out`, else `IN`), the next pin a spare, the rest without a name."""
    rows = [list(_PINOUT_HEADING)]
    for n in range(1, 10):
        if n <= len(signals):
            name = signals[n - 1]
            word = "OUT" if name.split("_")[-1] in out else "IN"
            rows.append(["J1", str(n), name, "fixed", word, part])
        elif n == len(signals) + 1:
            rows.append(["J1", str(n), "", "", "SPARE", part])
        else:
            rows.append(["J1", str(n), "", "", "", part])
    return rows


def _names_and_ports() -> Project:
    """OBC1 talks RS-422 to TTC1 and TTC2 through one connector whose ports are named after them;
    the pinouts are read in the team's words through the project's signal map, and Generate gives
    each interface the port named after the device at its other end (`naming.far_device_names`)."""
    p = new_project(_title("names-and-ports"))
    p.meta = evolve(
        p.meta,
        description="OBC1-J01 holds two RS-422 ports, TTC1_... on pins 1 to 4 and TTC2_... on "
        "pins 5 to 8, named after the devices at their other ends. The interface to TTC2 was "
        "made first (IF-001), yet it uses the pins of TTC2, because the setting Signal names "
        "name the far device is on. The pinouts were read in the team's words (TXP, TXN, RXP, "
        "RXN) and the project's signal map renamed them; imports DIR lists each rename. Look at "
        "the pin table of OBC1-J01, explain DIR IF-001 and config DIR; the manual pages Define a "
        "device and Connect two connectors explain it.",
    )
    history = History(p)
    # one connector serves two devices: one harness that branches (as a new project starts)
    _setting(history, p, "segmentation", "mode", "per_connector_group")
    root = examples_path()
    assert root is not None
    team = signal_map.read_file(root / "templates" / "signal-map.csv")
    # `config DIR --signal-map signal-map.csv --far-device-names on`; each plan is made on the
    # project as the step before left it, since both change config/naming.json
    plan = configcheck.plan_set_signal_map(p, team)
    assert plan.ok, plan.error
    history.execute("signal map", plan.ops)
    plan = configcheck.plan_set_far_device_names(p, True)
    assert plan.ok, plan.error
    history.execute("far device names", plan.ops)
    _device(history, p, "OBC1", "On-board computer", 0, 40.0)
    _device(history, p, "TTC1", "Transceiver 1", 1, 40.0)
    _device(history, p, "TTC2", "Transceiver 2", 1, 280.0)
    ports = [f"{far}_{word}" for far in ("TTC1", "TTC2") for word in _TEAM_WORDS]
    with tempfile.TemporaryDirectory() as scratch:
        folder = Path(scratch)
        for uid, part, signals in (
            ("OBC1", "EX-MICROD-9-F", ports),
            ("TTC1", "EX-MICROD-9-M", list(_TEAM_WORDS)),
            ("TTC2", "EX-MICROD-9-M", list(_TEAM_WORDS)),
        ):
            rows = _team_pinout(part, signals, out=("TXP", "TXN"))
            _import_pinout(history, p, _write_table(folder, f"{uid}-pinout.csv", rows), uid)
    for far in ("TTC2", "TTC1"):  # the interface to TTC2 first: IF-001 (the run of 4.4.0)
        ops, _iid = edit.ops_add_interface(p, "rs422", "OBC1", far, "OBC1-J01", f"{far}-J01")
        history.execute(f"add interface to {far}", ops)
    generate_project(p)
    _no_errors("names-and-ports", p)
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


def _setting(
    history: History, p: Project, file: str, key: str, value: object, *, placeholder: bool = False
) -> None:
    """One value of a settings file, as `settings DIR --set FILE.KEY=VALUE` sets it (a file the
    project has no copy of yet starts empty; `placeholder` marks a new file that holds an EXAMPLE
    number)."""
    cfg = p.config.get(file) or ConfigFile(name=file, placeholder=placeholder, values={})
    history.execute(f"set {file}.{key}", [SetConfig(configcheck.with_value(cfg, key, value))])


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


# ---- branching-harness: one connector, two devices (section 4.5) -------------------------------

# EXAMPLE segment lengths in metres: from each harness's branch point to its three connectors
_BRANCH_METRES = {
    "W001-L1": 0.5, "W001-L2": 0.3, "W001-L3": 0.6,
    "W002-L1": 0.4, "W002-L2": 0.7, "W002-L3": 0.5,
}  # fmt: skip
# (type, from connector, to connector, name); both connectors named, so no `unconfirmed`
_BRANCH_LINKS = (
    ("power_primary", "PCDU1-J01", "OBC1-J02", "Power of OBC1"),
    ("power_primary", "PCDU1-J01", "TRX1-J01", "Power of TRX1"),
    ("rs422", "OBC1-J03", "TRX1-J02", "Telecommands and telemetry"),
    ("rs422", "OBC1-J03", "RW1-J02", "Wheel commands"),
)


def _units(history: History, p: Project, placed: Sequence[tuple[str, int, float]]) -> list[str]:
    """Devices from the starter device kinds (*Add device* of the diagram), placed in lanes."""
    made = []
    for kind, lane, y in placed:
        ops, uid = edit.ops_add_unit(p, kind, edit.lane_x(lane), y)
        history.execute(f"add unit {kind}", ops)
        made.append(uid)
    return made


def _segment_lengths(history: History, p: Project, metres: Mapping[str, float]) -> None:
    """EXAMPLE lengths of segments (segment ID -> metres), entered as a person types them in the
    Routing table; Generate keeps them on a harness it made."""
    done = []
    for h in sorted(p.harnesses.values(), key=lambda x: x.id):
        for s in h.segments:
            if s.id in metres:
                history.execute(
                    f"length of {s.id}",
                    branching.plan_set_segment_length(p, h.id, s.id, metres[s.id]),
                )
                done.append(s.id)
    assert sorted(done) == sorted(metres), (done, metres)  # every length has its segment


def _branching_harness() -> Project:
    """Four devices; PCDU1-J01 feeds OBC1 and TRX1, OBC1-J03 talks to TRX1 and RW1. With the
    segmentation per_connector_group Generate makes one harness per device connector that serves
    two devices, and it branches at a branch point."""
    p = new_project(_title("branching-harness"))
    p.meta = evolve(
        p.meta,
        description="One power connector of PCDU1 feeds OBC1 and TRX1, and one data connector of "
        "OBC1 talks to TRX1 and RW1. Generate (segmentation per connector group) makes one "
        "harness for each of the two connectors, and each branches at a branch point. Look at the "
        "Routing table of the Harness tab and at routing DIR W002; the manual page Branching "
        "harnesses explains it.",
    )
    history = History(p)
    _setting(history, p, "segmentation", "mode", "per_connector_group")
    _units(history, p, (("power", 0, 40.0), ("computer", 0, 280.0), ("transceiver", 1, 40.0), ("actuator", 1, 280.0)))  # fmt: skip
    for type_id, a, b, what in _BRANCH_LINKS:
        ua, ub = p.connectors[a].unit_id, p.connectors[b].unit_id
        assert ua is not None and ub is not None
        ops, _iid = edit.ops_add_interface(p, type_id, ua, ub, a, b, name=what)
        history.execute(f"add interface {what}", ops)
    generate_project(p)
    _segment_lengths(history, p, _BRANCH_METRES)
    generate_project(p)
    _no_errors("branching-harness", p)
    return p


# ---- loose-cable-end: a cable with nothing on its far end yet (section 4.6) ---------------------

# The test port of OBC1 (OBC1-J03, a 15-way Micro-D): telemetry and telecommand pairs
_TEST_PORT = (("1", "TM+"), ("2", "TM-"), ("3", "TC+"), ("4", "TC-"))
# EXAMPLE lengths (metres): from the port to the branch point, and on to each loose end
_BENCH_METRES = {"W002-L1": 0.3, "W002-L2": 1.5, "W002-L3": 1.5}


def _loose_cable_end() -> Project:
    """OBC1 and PCDU1 with one power interface, generated (W001), and a cable drawn by hand from
    the test port OBC1-J03 whose far end is loose (W002), with a second leg of the TC pins that
    ends loose too."""
    p = new_project(_title("loose-cable-end"))
    p.meta = evolve(
        p.meta,
        description="PCDU1 feeds OBC1 through the generated harness W001. W002, the Bench cable, "
        "is drawn by hand from the test port OBC1-J03: its TM wires end in the loose end W002-P2, "
        "and a leg of the TC wires ends in the loose end W002-P3 behind the branch point. Look at "
        "the loose ends in the tree and the Inspector (Plug into...), Edit > Cable ends, and "
        "release DIR W002, which asks for --accept-loose-ends; the manual page Build a harness by "
        "hand explains it.",
    )
    history = History(p)
    pcdu, obc = _units(history, p, (("power", 0, 40.0), ("computer", 1, 40.0)))
    ops, _iid = edit.ops_add_interface(
        p, "power_primary", pcdu, obc, f"{pcdu}-J01", f"{obc}-J02", name="Power of OBC1"
    )
    history.execute("add interface", ops)
    port = f"{obc}-J03"
    rows = [{"pin": pin, "signal": signal, "mode": "fixed"} for pin, signal in _TEST_PORT]
    history.execute(f"pinout of {port}", devices.ops_paste_rows(p, port, rows))  # 15 pins stay
    generate_project(p)
    cable = manual_harness.plan_cable_from_port(p, port, name="Bench cable", pin_ids=["1", "2"])
    history.execute("cable from the port", cable.ops)
    leg = branching.plan_add_leg(p, cable.harness_id, port, ["3", "4"])
    history.execute("a new leg", leg.ops)
    h = p.harnesses[cable.harness_id]
    for pins in (("1", "2"), ("3", "4")):  # each pair twisted, as its names ask
        ids = [w.id for w in h.wires if w.from_pin in pins]
        history.execute(f"twist {ids}", wires.plan_group_wires(p, ids, "twisted_pair"))
    # EXAMPLE gauge and lengths of the bench cable, so that only its loose ends stop a release
    ids = [w.id for w in h.wires]
    history.execute("gauge of the bench cable", wires.plan_wire_edit(p, ids, {"gauge_awg": 24}))
    _segment_lengths(history, p, _BENCH_METRES)
    _no_errors("loose-cable-end", p)
    return p


# ---- shields-and-ends: where a shield lands (section 4.7) ---------------------------------------

BACKSHELL_PART = "EX-BACKSHELL-MICROD"
BACKSHELL_DEPTH_MM = 30.0  # EXAMPLE: what the backshell adds behind the rear of the connector


def _backshell_part(history: History, p: Project) -> None:
    """The EXAMPLE backshell part, unverified and not approved, in the template's own library, with
    an EXAMPLE depth (the Inspector's *Depth (mm)*). The starter library has no backshell part."""
    part = Part(
        id=BACKSHELL_PART,
        category="backshell",
        manufacturer="Example Co.",
        part_number=BACKSHELL_PART,
        description="Backshell for a Micro-D, with a shield lug (EXAMPLE ONLY: not a real part)",
        unverified=True,
    )
    history.execute(f"add part {BACKSHELL_PART}", [Put("parts", part)])
    history.execute(
        f"depth of {BACKSHELL_PART}",
        build_data.plan_set_part_depth(p, BACKSHELL_PART, BACKSHELL_DEPTH_MM),
    )


def _backshell(history: History, p: Project, hid: str, aid: str, target: str) -> None:
    """A backshell of the EXAMPLE part on a cable connector (the Accessories tab)."""
    shell = {"id": aid, "kind": "backshell", "part_id": BACKSHELL_PART, "target": target}
    history.execute(f"backshell {aid}", build_data.plan_set_accessory(p, hid, shell))


def _grounding(history: History, p: Project, end_a: str, end_b: str) -> None:
    """The EXAMPLE grounding concept: how end A and end B of every generated shield end."""
    _setting(history, p, "generation", "shield_end_a", end_a)
    _setting(history, p, "generation", "shield_end_b", end_b)


# Each device connector: the pairs on pins 1 to 4 and the shield contact on pin 5 (role shield),
# pins 6 to 9 free
_RS422_SHIELDED = (("1", "TX+"), ("2", "TX-"), ("3", "RX+"), ("4", "RX-"), ("5", "SHLD"))
_CAN_SHIELDED = (("1", "CANH"), ("2", "CANL"), ("5", "SHLD"))
_TALKS = {"TX+": "out", "TX-": "out", "RX+": "in", "RX-": "in"}


def _shielded_connector(
    history: History,
    p: Project,
    uid: str,
    part: str,
    carries: Sequence[str],
    pins: Sequence[tuple[str, str]],
    keying: str | None,
) -> str:
    """A box connector whose named pins are fixed, the pin SHLD with the role shield."""
    ops, cid = devices.ops_add_connector(p, uid, part_id=part, keying=keying, carries=carries)
    history.execute(f"add connector {cid}", ops)
    rows = []
    for pin, signal in pins:
        row = {"pin": pin, "signal": signal, "mode": "fixed"}
        if signal == "SHLD":
            row["role"] = "shield"
        if signal in _TALKS:
            row["direction"] = _TALKS[signal]
        rows.append(row)
    history.execute(f"pinout of {cid}", devices.ops_paste_rows(p, cid, rows))
    return cid


def _shields_and_ends() -> Project:
    """OBC1 talks to TTC1 (RS-422, two shielded pairs) and to RW1 (CAN, a twisted pair under an
    overall shield); the EXAMPLE grounding concept ends every shield by a pigtail at end A and a
    360 degree backshell at end B, and each end says where it lands, but one."""
    p = new_project(_title("shields-and-ends"))
    p.meta = evolve(
        p.meta,
        description="The EXAMPLE grounding concept ends each shield by a pigtail at end A and "
        "bonds it all round in a backshell at end B. W001-S1 lands its pigtail on pin 5 (the "
        "shield contact) of W001-P1, W001-S2 on the lug of the backshell W001-A1 of W001-P2; the "
        "ends B are bonded in the backshells. End A of W002-S2 is left without a place, so check "
        "names it. Look at Change group..., the shield cell of the Production sheet and check "
        "DIR; the manual page Enter the build data (3a) explains it.",
    )
    history = History(p)
    _demo_values(history, p)
    _grounding(history, p, "pigtail", "backshell_360")
    _backshell_part(history, p)
    _device(history, p, "OBC1", "On-board computer", 0, 40.0)
    _device(history, p, "TTC1", "Transceiver", 1, 40.0)
    _device(history, p, "RW1", "Reaction wheel", 1, 300.0)
    links = (  # the two connectors of OBC1 are keyed A and B, so they cannot be swapped
        ("rs422", "Telecommands and telemetry", "TTC1", _RS422_SHIELDED, "A"),
        ("can", "Wheel bus", "RW1", _CAN_SHIELDED, "B"),
    )
    for type_id, what, far, pins, key in links:
        near = _shielded_connector(history, p, "OBC1", "EX-MICROD-9-F", (type_id,), pins, key)
        other = _shielded_connector(history, p, far, "EX-MICROD-9-M", (type_id,), pins, None)
        ops, _iid = edit.ops_add_interface(p, type_id, "OBC1", far, near, other, name=what)
        history.execute(f"add interface {what}", ops)
    generate_project(p)
    # W001 (RS-422): the TX pair has end A at W001-P1, the RX pair at W001-P2 (end A is the `from`
    # end of the lowest wire of a group); a backshell on each connector
    _backshell(history, p, "W001", "W001-A1", "W001-P2")
    _backshell(history, p, "W001", "W001-A2", "W001-P1")
    _backshell(history, p, "W002", "W002-A1", "W002-P2")
    for group, end, pin, shell in (
        ("W001-S1", "A", "5", None),  # a pigtail to the shield contact
        ("W001-S1", "B", None, "W001-A1"),  # a 360 degree bond in the backshell
        ("W001-S2", "A", None, "W001-A1"),  # a pigtail to the lug of the backshell
        ("W001-S2", "B", None, "W001-A2"),
        ("W002-S2", "B", None, "W002-A1"),  # end A of W002-S2 is left without a place
    ):
        history.execute(
            f"place of {group} end {end}",
            wires.plan_set_shield_place(p, group, end, pin=pin, backshell=shell),
        )
    _no_errors("shields-and-ends", p)
    return p


# ---- lengths-to-the-face: lengths measured from the mating face (section 4.8) -------------------

# EXAMPLE depths of the cable connector parts in use, from the mating face back to the rear (mm)
_DEPTHS_MM = {"EX-MICROD-9-M": 18.0, "EX-MICROD-15-M": 19.0, "EX-MICROD-21-M": 20.0}
# EXAMPLE segment lengths (metres), as measured in a mechanical model: to the mating faces
_FACE_METRES = {"W001-L1": 1.2, "W002-L1": 0.9}


def _lengths_to_the_face() -> Project:
    """PCDU1 and RW1 joined by a power interface (W001) and an RS-422 interface (W002); the
    segments run to the mating face of each cable connector but W002-P2, and the depth of each
    connector part and of the backshell on W001-P1 is taken off each wire."""
    p = new_project(_title("lengths-to-the-face"))
    p.meta = evolve(
        p.meta,
        description="The segment lengths of this project run to the mating face of the cable "
        "connectors (Settings > Project, Segments are measured to), as a mechanical model gives "
        "them; W002-P2 is measured to its rear. The depth of each connector part and of the "
        "backshell W001-A1 on W001-P1 is taken off each wire, so a wire length stays a length "
        "from rear to rear. The length model adds a cut allowance and the take-up of twisting. "
        "Look at the length note, segments.csv and explain DIR W001-001; the manual page Lengths "
        "to the face explains it.",
    )
    history = History(p)
    _demo_values(history, p)
    _setting(history, p, "model", "length_reference", "face", placeholder=True)
    _setting(history, p, "model", "length_model", "path_loops_allowance_twist", placeholder=True)
    _setting(history, p, "model", "cut_allowance_m", 0.03, placeholder=True)  # EXAMPLE
    _setting(history, p, "model", "twist_takeup_fraction", 0.02, placeholder=True)  # EXAMPLE
    _backshell_part(history, p)
    for part, mm in _DEPTHS_MM.items():
        history.execute(f"depth of {part}", build_data.plan_set_part_depth(p, part, mm))
    pcdu, rw = _units(history, p, (("power", 0, 40.0), ("actuator", 1, 40.0)))
    for type_id, a, b, what in (  # Generate numbers the power harness W001, the RS-422 W002
        ("power_primary", f"{pcdu}-J01", f"{rw}-J01", "Power of RW1"),
        ("rs422", f"{pcdu}-J03", f"{rw}-J02", "Wheel housekeeping"),
    ):
        ops, _iid = edit.ops_add_interface(p, type_id, pcdu, rw, a, b, name=what)
        history.execute(f"add interface {what}", ops)
    generate_project(p)
    _backshell(history, p, "W001", "W001-A1", "W001-P1")
    history.execute(
        "W002-P2 to its rear", connector_edit.plan_set_length_to(p, "W002", "W002-P2", "rear")
    )
    _segment_lengths(history, p, _FACE_METRES)
    generate_project(p)
    _no_errors("lengths-to-the-face", p)
    return p


# ---- the devices of first-steps, made by the same calls (sections 4.9 and 4.10) ----------------


def _first_steps_devices(history: History, p: Project) -> None:
    """PCDU1, OBC1 and RW1 with the power link (2 A, EXAMPLE) and the RS-422 link of the example
    `first-steps`, made by the calls of its builder; each interface names the two connectors that
    `first-steps` leaves to the tool, so no choice of the tool waits for a person (`unconfirmed`)."""
    _units(history, p, (("power", 0, 40.0), ("computer", 0, 280.0), ("actuator", 1, 150.0)))
    for type_id, a, b, ca, cb in (
        ("power_primary", "PCDU1", "RW1", "PCDU1-J01", "RW1-J01"),
        ("rs422", "OBC1", "RW1", "OBC1-J01", "RW1-J02"),
    ):
        ops, iid = edit.ops_add_interface(p, type_id, a, b, ca, cb)
        history.execute("add interface", ops)
        if type_id == "power_primary":
            history.execute("set current", edit.ops_update_interface(p, iid, max_current_a=2.0))


def _template_lengths() -> dict[str, float]:
    """The EXAMPLE segment lengths of the import template `segment-lengths.csv` (millimetres), in
    metres, as `import-lengths DIR segment-lengths.csv --unit mm` reads them."""
    root = examples_path()
    assert root is not None
    with (root / "templates" / "segment-lengths.csv").open(newline="", encoding="utf-8") as f:
        return {row["segment"]: float(row["length"]) / 1000 for row in csv.DictReader(f)}


def _exported(p: Project, folder: Path) -> None:
    """The outputs written into a scratch folder, as `export` writes them; the release gate reads
    them (`outputs_missing`), and no template ships `outputs/` (section 5.5)."""
    write_outputs(p, folder, build_outputs(p, drawings=False))


def _done(history: History, plan: ReleasePlan) -> None:
    """A review, release or new version, run as the Releases tab runs it; a blocker stops the
    build, so the template cannot ship without the step."""
    if plan.blockers:
        raise SystemExit(f"{plan.label}: {[b.code + ' ' + b.message for b in plan.blockers]}")
    history.execute(plan.label, plan.ops)


# ---- released-harness: a release and its next version (section 4.9) -----------------------------

# The fixed dates of the template (section 5.4): never today, so a second build gives the same bytes
EXAMPLE_DATES = {
    "review": "2026-01-12", "release": "2026-01-15", "new_version": "2026-01-20",
    "device_check": "2026-01-15",
}  # fmt: skip
_DESIGNER, _CHECKER, _RELEASER = "Designer 1", "Checker 1", "Releaser 1"
_TICKED = "1-20"  # the points of the review checklist that the person releasing says were ticked
_LONGER = {"W002-L1": 1.0}  # the one change of version 1.1.0: EXAMPLE, 0.9 m becomes 1.0 m


def _released_harness() -> Project:
    """The devices of first-steps with the EXAMPLE values and lengths, the review checklist of the
    template and different people in a release; W002 (power) reviewed and released as 1.0.0 with
    ticks, then its minor version 1.1.0 started with one change (a segment length)."""
    p = new_project(_title("released-harness"))
    p.meta = evolve(
        p.meta,
        description="The power harness W002 was reviewed by Designer 1, checked by Checker 1 and "
        "released as version 1.0.0 by Releaser 1, with points 1 to 20 of the review checklist "
        "ticked and the EXAMPLE values and parts accepted with a reason; then its version 1.1.0 "
        "was started, which makes W002-L1 0.1 m longer. Look at log DIR W002, diff DIR W002, the "
        "version report and the Review sheet after an export, and the Releases tab; the manual "
        "pages Release a harness, Change a released harness and Versions explain it.",
    )
    history = History(p)
    _demo_values(history, p)
    _first_steps_devices(history, p)
    history.execute(
        "review checklist", configcheck.plan_set_checklist(p, review.template_points()).ops
    )
    history.execute("different people", configcheck.plan_set_distinct_roles(p, True).ops)
    generate_project(p)
    _segment_lengths(history, p, _template_lengths())
    generate_project(p)
    with tempfile.TemporaryDirectory() as scratch:
        outputs = Path(scratch) / "outputs"
        _exported(p, outputs)
        when = EXAMPLE_DATES["review"]
        _done(history, release.plan_submit_review(p, "W002", by=_DESIGNER, when=when))
        _done(
            history,
            release.plan_release(
                p,
                "W002",
                by=_RELEASER,
                checker=_CHECKER,
                comment="First release of the power harness of RW1 (EXAMPLE)",
                when=EXAMPLE_DATES["release"],
                outputs_folder=outputs,
                accept_placeholders="EXAMPLE values for learning",
                accept_unapproved_parts="EXAMPLE parts for learning",
                ticked=_TICKED,
            ),
        )
    _done(
        history,
        release.plan_new_version(
            p,
            "W002",
            kind="minor",
            by=_DESIGNER,
            comment="EXAMPLE: the power segment W002-L1 is 0.1 m longer",
            when=EXAMPLE_DATES["new_version"],
        ),
    )
    _segment_lengths(history, p, _LONGER)
    generate_project(p)
    _no_errors("released-harness", p)
    return p


# ---- overrides-and-deviations: three ways to accept (section 4.10) -----------------------------

OVERRIDE_REASON = "EXAMPLE: the thinner wire of a bench cable"
DEVIATION_REASON = "EXAMPLE: the bench cable carries the load for minutes only"
WAIVER_REASON = "EXAMPLE: the two connectors are keyed differently on the real unit"
# EXAMPLE segment lengths (metres): the RS-422 and the RW1 power harness short, W002 2 m
_BENCH_POWER_METRES = {"W001-L1": 0.85, "W002-L1": 2.0, "W003-L1": 0.9}


def _overrides_and_deviations() -> Project:
    """The devices of first-steps and a second power interface from PCDU1-J02 to OBC1, with the
    EXAMPLE values and lengths; the gauge of the power wire W002-001 overridden to a thinner one,
    so two electrical errors that are accepted as deviations; the warning that the two identical
    power connectors of PCDU1 could be swapped, waived."""
    p = new_project(_title("overrides-and-deviations"))
    p.meta = evolve(
        p.meta,
        description="The gauge of W002-001 is set by hand to AWG 24 in place of the AWG 22 that "
        "Generate chose, with its reason, so the wire carries more current than it allows and "
        "drops more voltage than the limit: both errors are accepted as deviations, each with a "
        "reason. The warning that PCDU1-J01 and PCDU1-J02 could be swapped is waived. Look at "
        "override DIR, deviation DIR, drc DIR and the flags of the wire list; the manual pages "
        "Override a value and keep a history and Read and fix problems explain it.",
    )
    history = History(p)
    _demo_values(history, p)
    _first_steps_devices(history, p)
    ops, iid = edit.ops_add_interface(
        p, "power_primary", "PCDU1", "OBC1", "PCDU1-J02", "OBC1-J02", name="Power of OBC1"
    )
    history.execute("add interface Power of OBC1", ops)
    history.execute("set current", edit.ops_update_interface(p, iid, max_current_a=2.0))
    generate_project(p)
    _segment_lengths(history, p, _BENCH_POWER_METRES)
    generate_project(p)
    assert p.harnesses["W002"].wires[0].gauge_awg == 22  # what Generate chose
    history.execute(
        "override W002-001", wires.plan_override(p, "W002-001", "gauge_awg", 24, OVERRIDE_REASON)
    )
    generate_project(p)  # the override is kept, and the outputs are no longer out of date
    findings = {f.id: f for f in drc.run(p)}
    ops = [
        checks.deviate_op(findings[fid], DEVIATION_REASON)
        for fid in ("current-over-wire.W002-001", "voltage-drop.W002-001")
    ]
    history.execute("two deviations", ops)
    lookalike = findings["connector-lookalike.PCDU1-J01"]
    history.execute("waive", [checks.waive_op(lookalike, WAIVER_REASON)])
    _no_errors("overrides-and-deviations", p)
    return p


# ---- build-data-and-as-built: from the design to the bench (section 4.12) ----------------------

CONTACT_PART = "EX-CONTACT-22"
CONTACT_TOOL = "EXAMPLE crimp tool, setting 4"
_STRIP_MM = (6.0, 5.0)  # EXAMPLE strip lengths at the From and the To end of every wire
_CUT_TOLERANCE_MM = 10.0  # EXAMPLE: how far a cut length may differ from the design
_CUT_TOO_LONG_M = 0.025  # EXAMPLE: the one wire that was cut 25 mm too long
# the plug parts Generate chooses for the devices of first-steps: the example colour code is theirs
_MICRO_D_PLUGS = ("EX-MICROD-9-M", "EX-MICROD-21-M", "EX-MICROD-25-M")
_TITLE_BLOCK = ("project", "harness_id", "title", "version", "date", "author", "checker", "approver", "status")  # fmt: skip
# EXAMPLE accessories of W001 (sleeving, heat shrink, a label and a backshell), as the Accessories
# tab or the import template accessories.csv enters them
_ACCESSORIES = (
    {"id": "ACC-001", "kind": "sleeving", "target": "W001-001", "position": "whole wire"},
    {"id": "ACC-002", "kind": "heat_shrink", "target": "W001-P1", "length_mm": 30, "quantity": 2,
     "position": "50 mm from the end of the connector"},
    {"id": "ACC-003", "kind": "label", "target": "W001-P2", "position": "100 mm from the end of the connector"},
    {"id": "ACC-004", "kind": "backshell", "target": "W001-P1"},
)  # fmt: skip


def _contact_part(history: History, p: Project) -> None:
    """The EXAMPLE contact part (the contact the import template `pin-contacts.csv` names),
    unverified and not approved, with an EXAMPLE crimp tool; the starter library has no contact
    part."""
    part = Part(
        id=CONTACT_PART,
        category="contact",
        manufacturer="Example Co.",
        part_number=CONTACT_PART,
        description="Crimp contact for AWG 22 to 26 (EXAMPLE ONLY: not a real part)",
        unverified=True,
    )
    history.execute(f"add part {CONTACT_PART}", [Put("parts", part)])
    history.execute(
        f"crimp tool of {CONTACT_PART}",
        build_data.plan_set_part_tool(p, CONTACT_PART, CONTACT_TOOL),
    )


def _asbuilt_sheet(p: Project, harness_id: str) -> list[list[str]]:
    """The as-built sheet of one harness (`export-asbuilt`) as a technician fills it in: a serial
    number, who built and who inspected it (role names), the lot of each part, the crimp tool of
    each pin, every wire cut to its designed length but one, which is 25 mm too long, the strip
    lengths as designed, and every test with its result and an EXAMPLE continuity or isolation
    value within its limit."""
    rows = asbuilt.template_rows(p, harness_id)
    head = rows[0]
    col = {name: head.index(name) for name in head}
    long_one = f"{harness_id}-001"
    for row in rows[1:]:
        kind, item = row[col["Kind"]], row[col["Item"]]
        if kind == "harness":
            row[col["Serial number"]] = f"EX-{harness_id}-0001"
            row[col["Built by"]], row[col["Inspected by"]] = "Technician 1", "Inspector 1"
        elif kind == "part":
            row[col["Lot"]] = "EX-LOT-1"
        elif kind == "pin":
            row[col["Crimp tool"]] = CONTACT_TOOL
            row[col["Crimp tool calibration ID"]] = "EX-CAL-1"
        elif kind == "wire":
            designed = float(row[col["Designed length (m)"]])
            built = designed + (_CUT_TOO_LONG_M if item == long_one else 0.0)
            row[col["Cut length (m)"]] = f"{built:.3f}"
            row[col["Strip A (mm)"]] = row[col["Designed strip A (mm)"]]
            row[col["Strip B (mm)"]] = row[col["Designed strip B (mm)"]]
        elif kind == "test":
            row[col["Result"]] = "pass"
            if row[col["Test type"]] == "continuity":
                row[col["Continuity (ohm)"]] = "0.08"  # EXAMPLE, at most 0.5 ohm
            else:
                row[col["Isolation (Mohm)"]] = "550"  # EXAMPLE, at least 100 Mohm
                row[col["Test voltage (V)"]] = "100"
    return rows


def _build_data_and_as_built() -> Project:
    """The devices of first-steps with the EXAMPLE values and lengths, the label format of a new
    project and a title block without the sheet number; the build data of W001 and W002 (strip
    lengths, the EXAMPLE contact with its crimp tool, accessories, the example colour code by pin
    and the Cover of the plans), and a record of W001 as it was built."""
    p = new_project(_title("build-data-and-as-built"))
    p.meta = evolve(
        p.meta,
        description="The build data of the harnesses: a strip length at each end of every wire, "
        "the contact EX-CONTACT-22 with its crimp tool on the device pins in use, sleeving, heat "
        "shrink, a label and a backshell on W001, the example pigtail colour code by pin and the "
        "Cover of the harness plans. W001 was built and tested: its as-built record says one "
        "wire was cut 25 mm too long, out of the tolerance of 10 mm. Look at export --harness-plan, "
        "the Cut list and Connectors sheets of the build workbook and asbuilt DIR; the manual "
        "pages Enter the build data, Export the harness plans and Record what was built explain "
        "it.",
    )
    history = History(p)
    _demo_values(history, p)
    _setting(history, p, "model", "label_format", "harness_device_connector")  # a new project's
    _setting(history, p, "titleblock", "fields", list(_TITLE_BLOCK))  # the sheet number hidden
    _setting(history, p, "generation", "asbuilt_cut_tolerance_mm", _CUT_TOLERANCE_MM)
    _contact_part(history, p)
    _first_steps_devices(history, p)
    for cid in ("PCDU1-J01", "RW1-J01", "OBC1-J01", "RW1-J02"):  # the column Cable contact
        pins = [pin.id for pin in p.connectors[cid].pins]
        history.execute(f"contacts of {cid}", devices.ops_set_contacts(p, cid, pins, CONTACT_PART))
    generate_project(p)
    _segment_lengths(history, p, _template_lengths())
    generate_project(p)
    for hid in sorted(p.harnesses):
        history.execute(
            f"strip lengths of {hid}",
            build_data.plan_set_strip_all(p, hid, strip_a_mm=_STRIP_MM[0], strip_b_mm=_STRIP_MM[1]),
        )
    for accessory in _ACCESSORIES:
        history.execute(
            f"accessory {accessory['id']}", build_data.plan_set_accessory(p, "W001", accessory)
        )
    history.execute("example colour code", plan_config.plan_example_code(p, _MICRO_D_PLUGS))
    history.execute(
        document.document_label(None),
        document.plan_document_edit(
            p,
            fields={"system": "EX-SAT", "title": "EX-SAT harness plans (EXAMPLE)", "company": "Example Ltd"},
            contact=[("E-mail", "harness-plans@example.org"), ("Phone", "+00 000 000 0000 (EXAMPLE)")],
        ),
    )  # fmt: skip
    history.execute(
        document.document_label("W001"),
        document.plan_document_edit(p, harness="W001", fields={"number": "HP-W001"}),
    )
    with tempfile.TemporaryDirectory() as scratch:
        sheet = _write_table(Path(scratch), "W001-asbuilt-EXAMPLE.csv", _asbuilt_sheet(p, "W001"))
        read = asbuilt.read_import(p, sheet, None)
        if read.plan.bad_count or not read.ops:
            raise SystemExit(f"{sheet.name}: {[r.message for r in read.plan.rows if not r.ok]}")
        history.execute("Import as-built records", read.ops)
    _no_errors("build-data-and-as-built", p)
    return p


# ---- imports-from-files: a project made from files (section 4.13) -------------------------------

PINOUT_TEMPLATE = "device-pinout-EXAMPLE.csv"
# what each approval status of approved-parts.csv means here: every one is "not decided yet", so
# no part of an example reads as approved (T12, D-129); the page Import data shows --approved
_ALL_REVIEW = ("Approved", "Review", "Rejected")
# the options of templates/README.md for wheel-connectors.net
_WHEEL_CONNECTORS = {"J1": "RW1-J01", "J2": "RW1-J02"}


def _import_parts(history: History, p: Project, path: Path) -> None:
    """`import-parts DIR FILE --pending Approved --pending Review --pending Rejected`."""
    table, sheet = read_table_sheet(path)
    mapping = library_import.guess_mapping(table[0])
    plan = library_import.plan_parts_import(
        p, table, mapping, approved=[], pending=list(_ALL_REVIEW), rejected=[]
    )
    if plan.ok_count != len(plan.rows):
        raise SystemExit(f"{path.name}: {[r.message for r in plan.rows if not r.ok]}")
    report = import_reports.parts_report(
        path, None, p, table, mapping, plan, mass_unit="g", unit_given=False, sheet=sheet
    )
    source = f"{path.name} (sha256 {file_sha256(path)[:12]})"  # as the command names the source
    ops = [*plan.ops, *library_import.library_ops(p, name=None, version=None, source=source, date=None)]  # fmt: skip
    _recorded(history, p, "Import parts", ops, report)


def _import_interfaces(history: History, p: Project, path: Path) -> list[str]:
    """*File > Import > Interfaces…* (the app only): the interfaces of the file, by their IDs."""
    table, sheet = read_table_sheet(path)
    mapping = imports_table.guess_mapping(table[0])
    plan = imports_table.plan_interface_import(p, table, mapping)
    if plan.error_count:
        raise SystemExit(f"{path.name}: {[r.message for r in plan.rows if not r.ok]}")
    report = import_reports.interfaces_report(path, None, table, mapping, plan, sheet=sheet)
    _recorded(history, p, "Import interfaces", plan.ops, report)
    return [r.values[0] for r in plan.rows]


def _import_netlist(history: History, p: Project, path: Path, unit_id: str) -> None:
    """`import-netlist DIR FILE --device UNIT --prefix J --connector J1=... --connector J2=...`."""
    netlist = kicad.read_netlist(path)
    plan = kicad.plan_netlist_import(
        p, netlist, unit_id, prefix="J", connector_ids=_WHEEL_CONNECTORS
    )
    if plan.ok_count != len(plan.rows) or not plan.ops:
        raise SystemExit(f"{path.name}: {[r.message for r in plan.rows if not r.ok]}")
    report = import_reports.netlist_report(path, None, netlist, plan)
    _recorded(history, p, "Import connector pinouts from KiCad", plan.ops, report)


def _import_lengths(history: History, p: Project, path: Path) -> None:
    """`import-lengths DIR FILE --unit mm`."""
    table, sheet = read_table_sheet(path)
    plan = lengths.plan_length_import(p, table, scale=lengths.LENGTH_UNITS_M["mm"])
    if not all(r.ok for r in plan.rows):
        raise SystemExit(f"{path.name}: {[r.message for r in plan.rows if not r.ok]}")
    report = import_reports.lengths_report(path, None, table, plan, unit="mm", unit_given=True, sheet=sheet)  # fmt: skip
    _recorded(history, p, "Import segment lengths", plan.ops, report)


def _import_build_data(history: History, p: Project, path: Path) -> None:
    """`import-build-data DIR FILE` (strip lengths, accessories ...: the kind from the headings)."""
    table, sheet = read_table_sheet(path)
    plan = build_data_import.plan_build_data_import(p, table, unit="mm")
    if plan.counts()["refused"] or not plan.ops:
        raise SystemExit(f"{path.name}: {[r.message for r in plan.rows if not r.ok]}")
    report = import_reports.build_data_report(path, None, table, plan, unit="mm", unit_given=False, sheet=sheet)  # fmt: skip
    _recorded(history, p, plan.label, plan.ops, report)


def _imports_from_files() -> Project:
    """The devices of first-steps, then every import template of `templates FOLDER` that fits: the
    parts, two interfaces, the KiCad netlist of RW1, the signal map, the pinout of a fourth device
    GYRO1 (a new device), and after Generate the segment lengths, strip lengths and accessories;
    each import keeps its record in `imports/records.json`."""
    p = new_project(_title("imports-from-files"))
    p.meta = evolve(
        p.meta,
        description="The devices of first-steps, and everything else read from the import "
        "templates that harness-design-studio templates FOLDER copies: the approved parts list "
        "(every status read as not decided yet), two interfaces, the KiCad netlist of RW1, the "
        "project's signal map, the pinout of GYRO1 (a new device), and after Generate the "
        "segment lengths, strip lengths and accessories. Look at imports DIR (the record of each "
        "file) and the fixed pins of RW1 and GYRO1; the manual pages Import data and Import "
        "KiCad pinouts explain it.",
    )
    history = History(p)
    root = examples_path()
    assert root is not None
    files = root / "templates"
    _first_steps_devices(history, p)
    _import_parts(history, p, files / "approved-parts.csv")
    for iid in _import_interfaces(history, p, files / "interfaces.csv"):
        history.execute(f"confirm {iid}", edit.ops_confirm_interface(p, iid))  # the tool's choice
    # both power outputs of PCDU1 are in use now: keyed A and B, so they cannot be swapped
    for cid, key in (("PCDU1-J01", "A"), ("PCDU1-J02", "B")):
        history.execute(f"keying of {cid}", devices.ops_update_connector(p, cid, keying=key))
    _import_netlist(history, p, files / "wheel-connectors.net", "RW1")
    plan = configcheck.plan_set_signal_map(p, signal_map.read_file(files / "signal-map.csv"))
    assert plan.ok, plan.error
    history.execute("signal map", plan.ops)  # `config DIR --signal-map signal-map.csv`
    _import_pinout(history, p, files / PINOUT_TEMPLATE, "GYRO1", new_device="Gyroscope")
    # the RS-422 connectors of OBC1 are in use: one more for the gyroscope (the Devices tab), of a
    # part no other connector of OBC1 has, so that it cannot be swapped with one
    ops, port = devices.ops_add_connector(p, "OBC1", part_id="EX-MICROD-9-M", carries=("rs422",))
    history.execute(f"add connector {port}", ops)
    ops, _iid = edit.ops_add_interface(p, "rs422", "OBC1", "GYRO1", port, "GYRO1-J01", name="Gyroscope data")  # fmt: skip
    history.execute("add interface Gyroscope data", ops)
    generate_project(p)
    _import_lengths(history, p, files / "segment-lengths.csv")
    generate_project(p)
    for name in ("strip-lengths.csv", "accessories.csv"):
        _import_build_data(history, p, files / name)
    _no_errors("imports-from-files", p)
    return p


# ---- device-library: devices from a library folder (section 4.11) ------------------------------

LIBRARY_FOLDER = "team-library"  # inside the project, named by its device-libraries.json
SUBSYSTEM_NAME = "Power"
CHECKED_BY = "Reviewer 1"
CHECKED_ICD = "ICD-OBC EXAMPLE Issue 2"
CROSS_STRAP_REASON = "EXAMPLE: OBC1 talks to both transceivers on purpose, so either can take over"
# The pinout of the RS-422 port of the transceiver as its ICD gives it: pin, signal, function
_TTC_PORT = (
    ("1", "TX+", "Telecommands in, positive"), ("2", "TX-", "Telecommands in, negative"),
    ("3", "RX+", "Telemetry out, positive"), ("4", "RX-", "Telemetry out, negative"),
)  # fmt: skip
# The one change the team made in the library after the project added TTC1: a pin's function
_TTC_CHANGED = ("3", "Telemetry and ranging out, positive")
# (type, from connector, to connector, name); both connectors named, so no `unconfirmed`
_LIBRARY_LINKS = (
    ("power_primary", "PCDU1-J01", "OBC1-J02", "Power of OBC1"),
    ("rs422", "OBC1-J01", "TTC1-J02", "Telecommands and telemetry of TTC1"),
    ("rs422", "OBC1-J03", "TTC1-R-J02", "Telecommands and telemetry of TTC1-R"),
)


def _team_devices(changed: bool) -> Project:
    """The project of the team that keeps the library, where the devices were defined: OBC1,
    TTC1 with the fixed pinout and the functions of its RS-422 port, and PCDU1, all of the starter
    device kinds. With `changed`, TTC1 has the function of a pin that the team changed later."""
    p = new_project("Team devices")
    history = History(p)
    for kind, uid, name, y in (
        ("computer", "OBC1", "On-board computer", 40.0),
        ("transceiver", "TTC1", "Transceiver", 300.0),
        ("power", "PCDU1", "Power control unit", 560.0),
    ):
        ops, _uid = edit.ops_add_unit(p, kind, edit.lane_x(0), y, unit_id=uid, name=name)
        history.execute(f"add device {uid}", ops)
    function = dict([_TTC_CHANGED]) if changed else {}
    rows = [
        {"pin": pin, "signal": signal, "mode": "fixed", "function": function.get(pin, what)}
        for pin, signal, what in _TTC_PORT
    ]
    history.execute("pinout of TTC1-J02", devices.ops_paste_rows(p, "TTC1-J02", rows))
    return p


def _add_subsystem(history: History, p: Project, path: Path, root: Path) -> None:
    """`import-subsystem DIR FILE`: the devices of a subsystem file and its import record."""
    data = subsystems.read_subsystem(path)
    plan = subsystems.plan_subsystem_import(p, data)
    if not plan.ok:
        raise SystemExit(f"{path.name}: {plan.problem}")
    report = import_reports.library_file_report("subsystem", path, root, len(plan.rows), plan.notes)
    _recorded(history, p, "Add a subsystem from a library file", plan.ops, report)


def _device_library_in(root: Path) -> Project:
    """The project folder `root` with its library folder: the team saved OBC1 and TTC1 into
    `team-library/` (a device file each) and PCDU1 as the subsystem *Power*; the project names
    the folder, adds OBC1 and TTC1 with a copy (TTC1-R) from it and the subsystem from its file,
    is generated (the link of OBC1 to the copy, which is on the redundant chain, is a cross-strap,
    waived with its reason), and OBC1 is checked and saved back with its check; then the team
    changes a pin function of TTC1 in the library, so TTC1 and its copy read *library changed*."""
    p = new_project(_title("device-library"))
    p.meta = evolve(
        p.meta,
        description="The devices come from the device library team-library/ inside the project "
        "(named in device-libraries.json): OBC1 checked by Reviewer 1 against ICD-OBC EXAMPLE "
        "Issue 2 and saved back to the library with its check, TTC1 with its copy TTC1-R, and "
        "PCDU1 from the subsystem file Power. The team changed a pin function of TTC1 in the "
        "library after it was added, so update-device DIR TTC1 shows the difference and takes it "
        "with --apply. TTC1-R is on the redundant chain and OBC1 talks to both transceivers: that "
        "cross-strap is waived with its reason. Look at libraries DIR --devices and the Review "
        "page; the manual page Use the library explains it.",
    )
    library = root / LIBRARY_FOLDER
    library.mkdir(parents=True)
    if library_git(library).kind != "none":  # the record would name a commit: not the same twice
        raise SystemExit(f"{library} is inside a Git repository; build the examples elsewhere.")
    team = _team_devices(changed=False)
    library_folder.save_devices(library, team, ["OBC1", "TTC1"])  # `save-device ... --library`
    power = library / subsystems.default_file_name(SUBSYSTEM_NAME)
    subsystems.write_subsystem(
        power,
        subsystems.export_subsystem(
            team, ["PCDU1"], SUBSYSTEM_NAME, "The power control unit of the team"
        ),
    )  # `export-subsystem ... --device PCDU1 --name Power`
    library_pointer.write_pointer(root, [LIBRARY_FOLDER])  # `libraries DIR --add team-library`
    history = History(p)
    libraries = library_link.project_libraries(root)
    if libraries.problems:
        raise SystemExit(f"{LIBRARY_FOLDER}: {libraries.problems}")
    for name, count in (("OBC1", 1), ("TTC1", 2)):  # `add-device DIR OBC1`, `... TTC1 --count 2`
        add = library_link.plan_add_device(p, libraries, name, count, root=root)
        history.execute(add.label, add.ops)
    _add_subsystem(history, p, power, root)  # `import-subsystem DIR team-library/...`
    for type_id, a, b, what in _LIBRARY_LINKS:
        ua, ub = p.connectors[a].unit_id, p.connectors[b].unit_id
        assert ua is not None and ub is not None
        ops, _iid = edit.ops_add_interface(p, type_id, ua, ub, a, b, name=what)
        history.execute(f"add interface {what}", ops)
    generate_project(p)
    # the copy is on the redundant chain: its link to OBC1 joins the two chains, on purpose
    (strap,) = [f for f in checks.find(p) if f.rule == "cross-strap"]
    history.execute("waive", [checks.waive_op(strap, CROSS_STRAP_REASON)])
    check = device_check.plan_set_device_checked(
        p, "OBC1", by=CHECKED_BY, on=EXAMPLE_DATES["device_check"], icd=CHECKED_ICD
    )  # `device-checked DIR OBC1 --by ... --icd ... --date ...`
    history.execute("Mark OBC1 as checked", check.ops)
    holder = libraries.device("OBC1")
    assert holder is not None
    saved = library_link.plan_save_device(p, holder.library, "OBC1", replace=True, root=root)
    history.execute("Record the library file of OBC1", saved.ops)  # `save-device ... --replace`
    # later, in the team's project: a pin function of TTC1 changed, saved into the library
    library_folder.save_devices(library, _team_devices(changed=True), ["TTC1"], replace=True)
    _no_errors("device-library", p)
    return p


def _files_in(root: Path, rels: Sequence[str]) -> dict[str, bytes]:
    """The files (path in the example's folder -> bytes) of the files and folders `rels` of
    `root`, without the `.bak` copies a replaced file leaves."""
    out: dict[str, bytes] = {}
    for rel in rels:
        path = root / rel
        found = sorted(path.rglob("*")) if path.is_dir() else [path]
        for f in found:
            if f.is_file() and f.suffix != ".bak":
                out[f.relative_to(root).as_posix()] = f.read_bytes()
    return out


def _device_library_build() -> tuple[Project, dict[str, bytes]]:
    """The project of `device-library` and the files beside it, built in a scratch folder."""
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch) / "device-library"
        p = _device_library_in(root)
        return p, _files_in(root, [library_pointer.FILE, LIBRARY_FOLDER])


def _device_library() -> Project:
    return _device_library_build()[0]


# ---- extensions: a project that adds a rule (section 4.14) -------------------------------------

# The example extensions of the manual page Extend the tool, the one copy of their files
_EXTENSION_FILES = Path(__file__).resolve().parents[1] / "docs" / "examples" / "extensions"


def _extension_files() -> dict[str, bytes]:
    """The files of `docs/examples/extensions/` without its page, as `extensions/` of a project:
    two data files (a rule; a table, a lookup table and a rule), a Python plug-in, `enabled.json`."""
    folder = extensions_manager.FOLDER
    return {
        f"{folder}/{path.relative_to(_EXTENSION_FILES).as_posix()}": path.read_bytes()
        for path in sorted(_EXTENSION_FILES.rglob("*"))
        if path.is_file() and path.name != "README.md"
    }


def _extensions() -> Project:
    """The devices of first-steps with the EXAMPLE values and lengths, generated, and the folder
    `extensions/` with the example extensions: a rule and a table written as data, both enabled
    and applied, and a Python plug-in that is enabled but not trusted, so it does not run."""
    p = new_project(_title("extensions"))
    p.meta = evolve(
        p.meta,
        description="The folder extensions/ adds a rule (x-min-gauge-power: no power wire thinner "
        "than AWG 22), a table of the power wires with a lookup table of EXAMPLE ampacities and a "
        "rule against it (x-own-ampacity), all written as data, and a Python plug-in "
        "(duplicate-signal-wires) that stays off until you trust it. Look at extensions DIR, drc "
        "DIR and system/extensions/power-wires.csv after an export; trust DIR "
        "duplicate-signal-wires is the exercise. The manual page Extend the tool explains it.",
    )
    history = History(p)
    _demo_values(history, p)
    _first_steps_devices(history, p)
    generate_project(p)
    _segment_lengths(history, p, _template_lengths())  # so that Generate gives each wire a gauge
    generate_project(p)
    with tempfile.TemporaryDirectory() as scratch:  # the rules of the files run on the project
        root = Path(scratch)
        for rel, data in _extension_files().items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(data)
        extensions_manager.attach(p, root)
        _no_errors("extensions", p)
        p.extensions = None  # what the folder offers is read again where the project is opened
    return p


# The files an example keeps beside its model (part C): path in the example's folder -> bytes
BESIDE: dict[str, Callable[[], dict[str, bytes]]] = {
    "device-library": lambda: _device_library_build()[1],
    "extensions": _extension_files,
}


BUILDERS: dict[str, Callable[[], Project]] = {
    "full-connectors": _full_connectors,
    "names-and-ports": _names_and_ports,
    "splice-by-hand": _splice_by_hand,
    "splice-from-connection": _splice_from_connection,
    "branching-harness": _branching_harness,
    "loose-cable-end": _loose_cable_end,
    "shields-and-ends": _shields_and_ends,
    "lengths-to-the-face": _lengths_to_the_face,
    "released-harness": _released_harness,
    "overrides-and-deviations": _overrides_and_deviations,
    "device-library": _device_library,
    "build-data-and-as-built": _build_data_and_as_built,
    "imports-from-files": _imports_from_files,
    "extensions": _extensions,
}
