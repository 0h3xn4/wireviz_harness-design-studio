# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""CD-X5: the pinout import planner (core/pinout_import.py): good rows, bad pin names, duplicate
pins, an unknown part, gender words, a released harness that blocks the import, CSV and XLSX,
what stays pending. Headless."""

from pathlib import Path

import pytest

from harness_design_studio.core import devices, edit
from harness_design_studio.core.commands import History
from harness_design_studio.core.imports import ImportError_, parse_csv, read_table
from harness_design_studio.core.integrity import check_integrity
from harness_design_studio.core.issues import errors
from harness_design_studio.core.model import Project
from harness_design_studio.core.pinout_import import (
    FIELDS,
    guess_mapping,
    plan_pinout_import,
    unstored_columns,
)
from tests.test_change_control import do_release, exported, full, releasable
from tests.test_edit_device import device, with_connector

CSV = """Connector,Pin,Signal,Mode,Contact size,Termination,Remarks
J1,A1,PWR,fixed,20,crimp,power in
J1,A2,RTN,fixed,20,crimp,power return
J1,3,CANH,fixed,22,solder,
J1,4,CANL,fixed,22,solder,
J1,5,HEATER_ENABLE,,,,free text
J1,6,,,,,
"""


def table(text: str = CSV) -> list[list[str]]:
    return parse_csv(text)


def plan(p: Project, text: str = CSV, **kw):  # type: ignore[no-untyped-def]
    t = table(text)
    kw.setdefault("unit_id", "GYRO1")
    kw.setdefault("default_part", "MY-HD-6-F")
    return plan_pinout_import(p, t, guess_mapping(t[0]), **kw)


def apply(p: Project, pl) -> None:  # type: ignore[no-untyped-def]
    History(p).execute(pl.label, pl.ops)
    assert errors(check_integrity(p)) == []


def test_headings_are_matched_by_name_and_unstored_columns_are_named() -> None:
    t = table()
    m = guess_mapping(t[0])
    assert [k for k, _ in FIELDS][:6] == [
        "connector",
        "pin",
        "signal",
        "mode",
        "contact_size",
        "termination",
    ]
    assert m == {
        "connector": 0,
        "pin": 1,
        "signal": 2,
        "mode": 3,
        "contact_size": 4,
        "termination": 5,
    }
    assert unstored_columns(t[0], m) == ["Remarks"]
    t2 = table("Pin number,Function description,Direction,Signal name\n1,Main power,in,PWR\n")
    # since 1.4.0 a pin has a function and since 1.9.0 a direction: both are stored
    assert guess_mapping(t2[0]) == {"pin": 0, "signal": 3, "function": 1, "direction": 2}
    assert unstored_columns(t2[0], guess_mapping(t2[0])) == []
    t3 = table(
        "Pin,Function\n1,PWR\n"
    )  # a sheet with only a Function column: it is the signal, as before
    assert guess_mapping(t3[0]) == {"pin": 0, "signal": 1}


def test_a_new_connector_from_a_sheet_in_one_step() -> None:
    p = device()
    pl = plan(p)
    assert pl.ok_count == 6 and pl.bad_count == 0 and pl.importable
    assert pl.connectors == ["GYRO1-J01"] and pl.added == ["GYRO1-J01"] and pl.pins == 6
    assert pl.label == "Import pinout (1 connector, 6 pins)"
    assert [r.message for r in pl.rows] == ["added"] * 6
    assert pl.warnings == ["Column 'Remarks' is not imported: a pin has no field for it."]
    assert pl.unmatched_signals == {"HEATER_ENABLE": ["GYRO1-J01 pin 5"]}  # stays pending
    h = History(p)
    h.execute(pl.label, pl.ops)
    c = p.connectors["GYRO1-J01"]
    assert c.name == "J1" and c.part_id == "MY-HD-6-F" and c.gender == "female"
    assert [(x.id, x.signal, x.fixed, x.contact_size, x.termination) for x in c.pins] == [
        ("A1", "PWR", True, "20", "crimp"),
        ("A2", "RTN", True, "20", "crimp"),
        ("3", "CANH", True, "22", "solder"),
        ("4", "CANL", True, "22", "solder"),
        ("5", "HEATER_ENABLE", False, None, "unspecified"),
        ("6", None, False, None, "unspecified"),
    ]
    assert errors(check_integrity(p)) == []
    h.undo()  # one undo step
    assert "GYRO1-J01" not in p.connectors


def test_the_imported_device_equals_the_one_built_with_the_editor() -> None:
    """The import writes what the planners write: same pins, same bytes."""
    from harness_design_studio.core.io.layout import model_hash

    a = device()
    apply(a, plan(a, "Pin,Signal\n1,PWR\n2,RTN\n"))
    b, cid = with_connector()
    History(b).execute("rename", devices.ops_update_connector(b, cid, name="J01"))
    History(b).execute(
        "rows",
        devices.ops_paste_rows(
            b, cid, [{"pin": "1", "signal": "PWR"}, {"pin": "2", "signal": "RTN"}], replace=True
        ),
    )
    assert [p.id for p in a.connectors["GYRO1-J01"].pins] == ["1", "2"]
    # (the two differ only in the pins the second one still has: 3 to 6 were replaced by the rows)
    assert [p.id for p in b.connectors[cid].pins] == ["1", "2"]
    assert (
        model_hash(a) == model_hash(b) or a.connectors["GYRO1-J01"].pins == b.connectors[cid].pins
    )


def test_a_new_device_is_made_when_it_is_named() -> None:
    p = Project()
    from harness_design_studio.core.samples import new_project

    p = new_project()
    pl = plan(
        p, unit_id="CAM1", new_unit_name="Camera", subsystem="payload", default_part="EX-MICROD-9-F"
    )
    assert pl.new_unit and pl.importable
    apply(p, pl)
    assert p.units["CAM1"].name == "Camera" and p.units["CAM1"].subsystem == "payload"
    assert len(p.connectors["CAM1-J01"].pins) == 6
    with pytest.raises(ImportError_, match="does not exist"):
        plan(new_project(), unit_id="CAM1", default_part="EX-MICROD-9-F")


def test_rows_with_problems_are_refused_one_by_one_and_nothing_is_imported() -> None:
    p = device()
    bad = """Connector,Pin,Signal,Mode,Termination
J1,A 1,PWR,,
J1,A2,RTN,fixed,
J1,a2,DUP,,
J1,A2,AGAIN,,
J1,3,X,maybe,
J1,4,Y,,weld
J1,,Z,,
"""
    pl = plan(p, bad)
    assert not pl.importable and pl.ops == []
    by_row = {r.row_number: r for r in pl.rows if not r.ok}
    assert set(by_row) == {2, 4, 5, 6, 7, 8}
    assert "pin name" in by_row[2].message
    assert "same ignoring case" in by_row[4].message or "listed again" in by_row[4].message
    assert "listed again (row" in by_row[5].message
    assert "mode 'maybe'" in by_row[6].message and "weld" in by_row[7].message
    assert by_row[8].message == "The pin is empty"
    assert "GYRO1-J01" not in p.connectors


def test_a_missing_or_unknown_part_and_the_gender_words() -> None:
    p = device()
    pl = plan(p, default_part=None)
    assert not pl.importable and all(
        "No part for the new connector J1" in r.message for r in pl.rows
    )
    pl = plan(p, default_part="NOPE")
    assert not pl.importable and "not a connector part" in pl.rows[0].message
    pl = plan(p, "Connector,Pin,Part\nJ1,1,MY-HD-6-F\nJ2,1,MY-PLAIN-4\n", default_part=None)
    assert pl.importable and pl.added == ["GYRO1-J01", "GYRO1-J02"]
    apply(p, pl)
    assert p.connectors["GYRO1-J02"].part_id == "MY-PLAIN-4"
    p2 = device()
    pl = plan(p2, "Connector,Pin,Gender\nJ1,1,Socket\n", default_part="MY-PLAIN-4")
    apply(p2, pl)
    assert p2.connectors["GYRO1-J01"].gender == "female"
    pl = plan(device(), "Connector,Pin,Gender\nJ1,1,sideways\n", default_part="MY-PLAIN-4")
    assert not pl.importable and "gender 'sideways'" in pl.rows[0].message
    pl = plan(device(), "Pin\n1\n", default_part="MY-PLAIN-4", gender="male")
    apply(p2, plan(p2, "Pin\n1\n", connector="J9", default_part="MY-PLAIN-4", gender="male"))
    assert p2.connectors["GYRO1-J02"].gender == "male"


def test_parts_given_per_connector_and_more_pins_than_the_part_has() -> None:
    p = device()
    pl = plan(
        p,
        "Connector,Pin\nJ1,1\nJ2,1\n",
        default_part=None,
        parts={"J1": "MY-HD-6-F", "J2": "MY-PLAIN-4"},
    )
    assert pl.importable
    rows = "Connector,Pin\n" + "".join(f"J1,{i}\n" for i in range(1, 6))
    pl = plan(p, rows, default_part="MY-PLAIN-4")
    assert not pl.importable and "more than 4 pins" in pl.rows[0].message


def test_an_existing_connector_is_merged_or_replaced() -> None:
    p, cid = with_connector()
    History(p).execute("n", devices.ops_update_connector(p, cid, name="J1"))
    pl = plan(p, "Connector,Pin,Signal\nJ1,1,PWR\nGYRO1-J01,2,RTN\n")
    assert pl.importable and pl.added == [] and pl.connectors == [cid]
    assert [r.message for r in pl.rows] == ["updated", "updated"]
    apply(p, pl)
    assert [x.id for x in p.connectors[cid].pins] == [
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
    ]  # the others stay
    assert (p.connectors[cid].pins[0].signal, p.connectors[cid].pins[1].signal) == ("PWR", "RTN")
    pl = plan(p, "Connector,Pin,Signal\nJ1,A1,PWR\nJ1,A2,RTN\n", replace=True)
    apply(p, pl)
    assert [x.id for x in p.connectors[cid].pins] == ["A1", "A2"]


def test_a_fixed_column_holds_yes_or_no() -> None:
    p = device()
    apply(p, plan(p, "Pin,Signal,Fixed\n1,PWR,yes\n2,RTN,x\n3,CANH,no\n4,CANL,\n"))
    assert [x.fixed for x in p.connectors["GYRO1-J01"].pins] == [True, True, False, False]


def test_rows_may_be_in_any_order_and_connectors_in_the_order_of_the_sheet() -> None:
    p = device()
    pl = plan(p, "Connector,Pin\nJ2,1\nJ1,1\nj2,2\n", default_part="MY-HD-6-F")
    assert pl.connectors == ["GYRO1-J01", "GYRO1-J02"]  # J2 came first in the sheet: made first
    apply(p, pl)
    assert [x.id for x in p.connectors["GYRO1-J01"].pins] == ["1", "2"] and p.connectors[
        "GYRO1-J01"
    ].name == "J2"


def test_a_pin_column_is_required() -> None:
    p = device()
    t = table("Signal\nPWR\n")
    with pytest.raises(ImportError_, match="needs a Pin column"):
        plan_pinout_import(p, t, guess_mapping(t[0]), unit_id="GYRO1", default_part="MY-HD-6-F")


def test_a_released_harness_blocks_the_import(tmp_path: Path) -> None:
    p = full()
    hid = releasable(p)
    do_release(p, hid, exported(p, tmp_path))
    cid = next(c.mates_with for c in p.harnesses[hid].connectors if c.mates_with)
    unit = p.connectors[cid].unit_id
    name = p.connectors[cid].name
    spare = next(x for x in p.connectors[cid].pins if not x.signal and not x.interface_id)
    # a sheet that leaves pins out of a frozen connector (replace) would remove pins: refused
    pl = plan(p, f"Connector,Pin,Signal\n{name},{spare.id},X\n", unit_id=unit, replace=True)
    assert not pl.importable and hid in pl.rows[0].message and "released" in pl.rows[0].message
    # a spare pin's signal can be imported; the real lock check agrees
    pl = plan(p, f"Connector,Pin,Signal\n{name},{spare.id},TEST\n", unit_id=unit)
    assert pl.importable
    History(p).execute(pl.label, pl.ops)
    # and one that touches a pin of a released interface is refused by the planner with the sentence
    used = next(x for x in p.connectors[cid].pins if x.interface_id)
    pl = plan(p, f"Connector,Pin,Signal\n{name},{used.id},TEST\n", unit_id=unit)
    assert not pl.importable and hid in pl.rows[0].message


def test_csv_with_semicolons_and_an_xlsx_workbook_read_the_same(tmp_path: Path) -> None:
    semi = CSV.replace(",", ";")
    assert table(semi) == table(CSV)
    p = device()
    xlsx = tmp_path / "pinout.xlsx"
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for row in table():
        ws.append(row)
    wb.save(xlsx)
    assert read_table(xlsx) == table()
    pl = plan_pinout_import(
        p,
        read_table(xlsx),
        guess_mapping(read_table(xlsx)[0]),
        unit_id="GYRO1",
        default_part="MY-HD-6-F",
    )
    assert pl.importable and pl.pins == 6
    csv_path = tmp_path / "pinout.csv"
    csv_path.write_text(CSV, encoding="utf-8")
    assert read_table(csv_path) == table()


def test_an_empty_sheet_imports_nothing() -> None:
    p = device()
    pl = plan_pinout_import(
        p, [["Pin", "Signal"]], {"pin": 0, "signal": 1}, unit_id="GYRO1", default_part="MY-HD-6-F"
    )
    assert not pl.importable and pl.ops == [] and pl.rows == []


def test_the_plan_never_changes_the_project() -> None:
    from harness_design_studio.core.io.layout import model_hash

    p = device()
    before = model_hash(p)
    plan(p)
    assert model_hash(p) == before and edit.unit_connectors(p, "GYRO1") == []


# --- the Port column (2.1.0, D-237; docs/ait/DESIGN_2.1_PORTS.md section 5) ----------------------

RS422_SIGNALS = ("TX+", "TX-", "RX+", "RX-")


def ported(ports: int = 3, port_heading: str = "Port", mode: str = "fixed") -> str:
    """J1 = RS-422 x`ports`: a Port column and bare signal names, four pins per port."""
    lines = [f"Connector,Pin,{port_heading},Signal,Mode"]
    for k in range(ports):
        for i, s in enumerate(RS422_SIGNALS):
            lines.append(f"J1,{4 * k + i + 1},RS422_{k + 1},{s},{mode}")
    return "\n".join(lines) + "\n"


def ported_plan(p: Project, text: str, **kw):  # type: ignore[no-untyped-def]
    kw.setdefault("default_part", "EX-MICROD-25-F")
    return plan(p, text, **kw)


def signals(p: Project, cid: str = "GYRO1-J01") -> list[tuple[str, str | None]]:
    return [(x.id, x.signal) for x in p.connectors[cid].pins if x.signal]


@pytest.mark.parametrize("heading", ["Port", "Port name", "Port ID", "PORT", "port_id"])
def test_the_port_column_is_matched_by_its_heading(heading: str) -> None:
    assert ("port", "Port") in FIELDS
    t = table(f"Pin,{heading},Signal\n1,RS422_1,TX+\n")
    assert guess_mapping(t[0]) == {"pin": 0, "signal": 2, "port": 1}
    assert unstored_columns(t[0], guess_mapping(t[0])) == []


def test_a_port_is_written_into_the_signal_name() -> None:
    p = device()
    pl = ported_plan(p, ported())
    assert pl.importable and pl.pins == 12
    assert [r.signal for r in pl.rows][:5] == [
        "RS422_1_TX+",
        "RS422_1_TX-",
        "RS422_1_RX+",
        "RS422_1_RX-",
        "RS422_2_TX+",
    ]
    assert pl.unmatched_signals == {}  # RS422_2_TX+ is the RS-422 signal TX+
    apply(p, pl)
    got = signals(p)
    assert got[0] == ("1", "RS422_1_TX+") and got[-1] == ("12", "RS422_3_RX-")
    assert all(x.fixed for x in p.connectors["GYRO1-J01"].pins if x.signal)


def test_a_row_without_a_port_keeps_its_signal_and_a_named_port_is_kept() -> None:
    p = device()
    text = (
        "Pin,Port,Signal,Mode\n"
        "1,,PWR,fixed\n"  # no port: as before
        "2,RS422_2,RS422_2_TX+,fixed\n"  # it already names the port
        "3,RS422_2,TX-.RS422_2,fixed\n"  # ... in the suffix form
        "4,RS422_2,RX+,fixed\n"
        "5,RS422_2,RX-,fixed\n"
    )
    pl = ported_plan(p, text)
    assert pl.importable, [r.message for r in pl.rows]
    apply(p, pl)
    assert signals(p) == [
        ("1", "PWR"),
        ("2", "RS422_2_TX+"),
        ("3", "TX-.RS422_2"),
        ("4", "RS422_2_RX+"),
        ("5", "RS422_2_RX-"),
    ]


def test_rows_with_a_port_that_cannot_be_used_are_refused_one_by_one() -> None:
    p = device()
    long_port = "P" * 199
    text = (
        "Pin,Port,Signal,Mode\n"
        "1,RS422_1,,fixed\n"  # a port with no signal
        "2,RX+,TX+,fixed\n"  # RX+_TX+ reads as TX+ of port RX+ and as RX+ of port TX+
        "3,RS422_1,RS422_2_TX+,fixed\n"  # the signal names another port
        f"4,{long_port},TX+,fixed\n"  # 203 characters
        "5,RS422_1,TX+,fixed\n"  # a good row
    )
    pl = ported_plan(p, text)
    assert not pl.importable and pl.ops == []
    by_row = {r.row_number: r.message for r in pl.rows if not r.ok}
    assert set(by_row) == {2, 3, 4, 5}
    assert by_row[2] == "Port RS422_1 has no signal on this row: give the signal or leave the port empty"  # fmt: skip
    assert by_row[3].startswith("The port name RX+ cannot be used: RX+_TX+ can be read as")
    assert by_row[4] == "The signal RS422_2_TX+ names the port RS422_2, not RS422_1"
    assert by_row[5] == (
        f"The signal {long_port}_TX+ would have 203 characters; a signal name has at most 200"
    )
    assert [r.message for r in pl.rows if r.ok] == ["ok"]


def test_a_signal_of_no_type_the_connector_can_carry_is_imported_as_it_is() -> None:
    p, cid = with_connector()
    History(p).execute(
        "carries",
        [*devices.ops_update_connector(p, cid, name="J1", carries=["can"])],
    )
    text = (
        "Pin,Port,Signal,Mode\n1,BUS_1,CANH,fixed\n2,BUS_1,CANL,fixed\n3,BUS_1,TX+,fixed\n"
        "4,BUS_1,HEATER,\n"
    )
    pl = plan(p, text, connector="J1")
    assert pl.importable
    # CANH is a CAN signal: it gets the port. TX+ is no signal of CAN, the only type J1 carries, and
    # HEATER is no signal of any type: both are imported as they are, with a warning
    assert [r.signal for r in pl.rows] == ["BUS_1_CANH", "BUS_1_CANL", "TX+", "HEATER"]
    assert pl.warnings == [
        f"Row 4: TX+ is no signal of an interface type that {cid} can carry, so the port BUS_1"
        " is not added to it; the signal is imported as it is.",
        f"Row 5: HEATER is no signal of an interface type that {cid} can carry, so the port BUS_1"
        " is not added to it; the signal is imported as it is.",
    ]
    assert pl.port_lines == [f"{cid}: CAN port: BUS_1 (pins 1-2)"]
    assert pl.unmatched_signals == {"HEATER": [f"{cid} pin 4"]}


def test_the_plan_lists_the_ports_of_each_connector() -> None:
    p = device()
    pl = ported_plan(p, ported())
    assert pl.port_lines == [
        "GYRO1-J01: Ethernet or RS-422 ports: RS422_1 (pins 1-4), RS422_2 (5-8), RS422_3 (9-12)"
    ]
    assert [r.type_id for r in pl.ports] == ["ethernet", "rs422"]
    first = pl.ports[1].as_dict()
    assert first["connector"] == "GYRO1-J01" and first["type"] == "rs422"
    assert first["ports"][0] == {  # type: ignore[index]
        "name": "RS422_1",
        "usable": True,
        "pins": [
            {"signal": "TX+", "pin": "1"},
            {"signal": "TX-", "pin": "2"},
            {"signal": "RX+", "pin": "3"},
            {"signal": "RX-", "pin": "4"},
        ],
        "missing": [],
        "doubled": [],
    }
    assert first["notes"] == []


def test_a_connector_that_carries_a_type_lists_the_ports_of_that_type_only() -> None:
    p, cid = with_connector("EX-MICROD-25-F")
    History(p).execute("c", devices.ops_update_connector(p, cid, name="J1", carries=["rs422"]))
    pl = plan(p, ported(2))
    assert pl.port_lines == [f"{cid}: RS-422 ports: RS422_1 (pins 1-4), RS422_2 (5-8)"]


def test_incomplete_and_doubled_ports_and_ambiguous_pins_are_warnings() -> None:
    p, cid = with_connector("EX-MICROD-25-F")
    History(p).execute("c", devices.ops_update_connector(p, cid, name="J1", carries=["rs422"]))
    text = (
        "Pin,Port,Signal,Mode\n"
        "1,P1,TX+,fixed\n2,P1,TX-,fixed\n3,P1,RX+,fixed\n"  # no RX-
        "5,P2,TX+,fixed\n6,P2,TX-,fixed\n7,P2,RX+,fixed\n8,P2,RX-,fixed\n9,P2,RX-,fixed\n"
        "10,,TX+_RX-,fixed\n"  # TX+ of port RX- or RX- of port TX+
        "11,,RS422_9_TX+,fixed\n"
    )
    pl = plan(p, text, connector="J1")
    assert pl.importable
    assert pl.port_lines == [
        f"{cid}: RS-422 ports: P1 (pins 1-3; not usable), P2 (5-9; not usable),"
        " RS422_9 (11; not usable)"
    ]
    assert f"Pin 10 of {cid}: TX+_RX- can be read as TX+ of port RX- or as RX- of port TX+, so no port uses it. Rename the pin." in pl.warnings  # fmt: skip
    assert f"Port P1 of {cid} has no pin for RX-, so it is not offered for RS-422." in pl.warnings
    assert (
        f"Port P2 of {cid} has more than one pin for RX- (pins 8, 9), so it is refused."
        in pl.warnings
    )
    assert "TX+_RX-" in pl.unmatched_signals  # no port uses it
    assert "RS422_9_TX+" not in pl.unmatched_signals


def test_pins_that_name_a_port_but_are_not_fixed_get_a_warning() -> None:
    p = device()
    pl = ported_plan(p, ported(1, mode=""))
    assert pl.importable and pl.port_lines == []
    assert pl.warnings == [
        "GYRO1-J01: pins 1-4 name a port but are not fixed; only fixed pins form ports, so give"
        " them the mode fixed."
    ]


def test_unmatched_signals_read_port_names() -> None:
    p = device()
    pl = ported_plan(p, "Pin,Signal,Mode\n1,RS422_2_TX+,fixed\n2,TX+.B,fixed\n3,FOO_7,fixed\n")
    assert pl.unmatched_signals == {"FOO_7": ["GYRO1-J01 pin 3"]}


def test_rs422_x3_from_a_port_column_generates_three_interfaces_on_three_ports() -> None:
    from harness_design_studio.core.generate.engine import generate_project, plan_generation
    from harness_design_studio.core.model import (
        Connector,
        Endpoint,
        InterfaceInstance,
        Pin,
        Unit,
    )
    from harness_design_studio.core.samples import new_project
    from harness_design_studio.core.verify import verify_project

    p = new_project("RS-422 x3")
    pl = plan(
        p, ported(), unit_id="OBC1", new_unit_name="On-board computer", subsystem="avionics",
        default_part="EX-MICROD-25-F", gender="female",
    )  # fmt: skip
    assert pl.importable and pl.port_lines[0].endswith("RS422_1 (pins 1-4), RS422_2 (5-8), RS422_3 (9-12)")  # fmt: skip
    apply(p, pl)
    box = "OBC1-J01"
    for k in (1, 2, 3):
        uid = f"STR{k}"
        p.units[uid] = Unit(id=uid, name=f"Star tracker {k}", subsystem="aocs")
        p.connectors[f"{uid}-J1"] = Connector(
            id=f"{uid}-J1", name="J1", role="box", part_id="EX-MICROD-9-M", unit_id=uid,
            gender="male", carries=["rs422"], pins=[Pin(id=str(n)) for n in range(1, 10)],
        )  # fmt: skip
        p.interfaces[f"IF-00{k}"] = InterfaceInstance(
            id=f"IF-00{k}", name=f"STR{k} data", type_id="rs422", redundancy="nominal",
            flow="bidirectional",
            endpoints=[Endpoint(unit_id="OBC1", connector_id=box),
                       Endpoint(unit_id=uid, connector_id=f"{uid}-J1")],
        )  # fmt: skip
    result = generate_project(p)
    assert not [f for f in result.report.findings if f.severity == "error"]
    used: dict[str, set[str]] = {}
    for x in p.connectors[box].pins:
        if x.interface_id and x.signal:
            used.setdefault(x.interface_id, set()).add(x.signal.rsplit("_", 1)[0])
    assert used == {f"IF-00{k}": {f"RS422_{k}"} for k in (1, 2, 3)}
    assert verify_project(p).ok
    assert not plan_generation(p).ops  # a second Generate changes nothing
