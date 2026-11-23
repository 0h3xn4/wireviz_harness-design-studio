# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-IMPORT-02: the project's signal map at import (4.4.0, pull request 5; design
`docs/ait/DESIGN_4.4_NAMES_PORTS.md`, part C, sections 5.2, 5.3, 10 and 11, owner questions N6, N7
and N11).

`import-netlist` and `import-pinout` with the project's map (`naming.signal_map`): whole names,
names inside a port (`TTC1_TXP` becomes `TTC1_TX+`, `TXP.TTC2` becomes `TX+.TTC2`), the Port column
(the cell is mapped first, then the port is written in), a name that reads in two ways (not
renamed, a warning), the command's `--signal-map` first (whole names, it wins per name), a mapped
name too long for a signal name (the row is refused), a locked pin (not changed); the echo, `--json`
`renamed_signals`, the import record's conversions and the import wizard's preview. Without a map
every import says and stores what 4.3.0 did: the texts of 4.3.0 word for word, and a file read into
a project without the key and one with `{}` gives the same text and the same pins. The library
imports read no map (N11), and a file `export-pinout` wrote is read back unchanged."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.cli.main import main
from harness_design_studio.core import signal_map, templates
from harness_design_studio.core.import_record import file_sha256
from harness_design_studio.core.import_reports import netlist_report, pinout_report
from harness_design_studio.core.imports import parse_csv
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.kicad import Component, Netlist, PinInfo, plan_netlist_import
from harness_design_studio.core.model import ConfigFile, Pin, Project, evolve
from harness_design_studio.core.pinout_import import guess_mapping, plan_pinout_import
from harness_design_studio.core.samples import mini3
from tests.helpers import edit_json

MAP = {"TXP": "TX+", "TXN": "TX-", "RXP": "RX+", "RXN": "RX-", "CAN_H": "CANH"}
HEADING = "Renamed by the project's signal map (config/naming.json signal_map): {} signal(s)"
TTC1_NETS = {"/TX+": "/TTC1_TXP", "/TX-": "/TTC1_TXN", "/RX+": "/TTC1_RXP", "/RX-": "/TTC1_RXN"}


def with_map(p: Project, table: object = MAP) -> Project:
    """`p` with `naming.signal_map` set to `table` (the other keys kept)."""
    old = p.config.get("naming")
    base = dict(old.values) if old is not None else {}
    values = {**base, "signal_map": table}
    p.config["naming"] = ConfigFile(name="naming", placeholder=False, values=values)
    return p


def netlist(nets: dict[str, str], part: str = "EX-MICROD-9-F") -> Netlist:
    """One connector J1 whose pin k carries the net `nets[k]`."""
    comp = Component(
        ref="J1",
        fields={"harnesspart": part},
        pins={k: PinInfo(number=k, net=v, function=f"F{k}") for k, v in nets.items()},
    )
    return Netlist(components={"J1": comp})


def signals(p: Project, cid: str) -> dict[str, str | None]:
    return {x.id: x.signal for x in p.connectors[cid].pins if x.signal}


def planned(plan: Any) -> dict[str, str | None]:
    """The signals of the connector the plan's first operation puts."""
    return {x.id: x.signal for x in plan.ops[0].obj.pins if x.signal}


def run(capsys: pytest.CaptureFixture[str], *argv: str, rc: int = 0) -> str:
    assert main(list(argv)) == rc, argv
    return capsys.readouterr().out


def take_map(capsys: pytest.CaptureFixture[str], folder: Path, file: Path) -> None:
    """`config DIR --signal-map FILE` (its exit code is the one of the hand-over list)."""
    main(["config", str(folder), "--signal-map", str(file)])
    capsys.readouterr()
    assert signal_map.table(load_project(folder).project)


def doc(capsys: pytest.CaptureFixture[str], *argv: str, rc: int = 0) -> dict[str, Any]:
    out = run(capsys, *argv, "--json", rc=rc)
    found = json.loads(out)
    assert isinstance(found, dict)
    return found


# ---- import-netlist: the plan -------------------------------------------------------------------


def test_netlist_whole_names_ports_and_two_readings() -> None:
    nets = {
        "1": "/TTC1_TXP", "2": "/io/TTC1_TXN", "3": "/RXP", "4": "/TXP.TTC2", "5": "/TXP_RXN",
        "6": "/PPS", "7": "/TX+",
    }  # fmt: skip
    plan = plan_netlist_import(with_map(mini3()), netlist(nets), "OBC")
    assert plan.rows[0].ok and plan.rows[0].connector_id == "OBC-J1"
    pins = planned(plan)
    assert pins == {
        "1": "TTC1_TX+", "2": "TTC1_TX-", "3": "RX+", "4": "TX+.TTC2", "5": "TXP_RXN",
        "6": "PPS", "7": "TX+",
    }  # fmt: skip
    assert [(r.row, r.where, r.read, r.stored) for r in plan.renamed] == [
        (1, "OBC-J1 pin 1", "TTC1_TXP", "TTC1_TX+"),
        (1, "OBC-J1 pin 2", "TTC1_TXN", "TTC1_TX-"),
        (1, "OBC-J1 pin 3", "RXP", "RX+"),
        (1, "OBC-J1 pin 4", "TXP.TTC2", "TX+.TTC2"),
    ]
    assert plan.warnings == [
        "TXP_RXN on OBC-J1 pin 5 can be read as TXP or RXN of the signal map, so it is not renamed."
    ]
    # the names after the map are the ones read for a type: a port name is a signal, the rest listed
    assert plan.unmatched_signals == {"PPS": ["OBC-J1 pin 6"], "TXP_RXN": ["OBC-J1 pin 5"]}


def test_netlist_the_commands_map_reads_whole_names_and_wins_per_name() -> None:
    nets = {"1": "/TTC1_TXP", "2": "/TTC1_TXN", "3": "/TXP"}
    given = {"TTC1_TXP": "TX+", "TXP": "TX-", "TXN": "RX-"}  # TXN is no whole name of the file
    plan = plan_netlist_import(with_map(mini3()), netlist(nets), "OBC", signal_map=given)
    pins = planned(plan)
    assert pins == {"1": "TX+", "2": "TTC1_TX-", "3": "TX-"}
    assert [(r.read, r.stored) for r in plan.renamed] == [("TTC1_TXN", "TTC1_TX-")]


def test_netlist_pin_function_names_are_mapped_too() -> None:
    comp = Component(
        ref="J1",
        fields={"harnesspart": "EX-MICROD-9-F"},
        pins={"1": PinInfo("1", "/N1", "TTC1_TXP"), "2": PinInfo("2", "/N2", "RXN")},
    )
    plan = plan_netlist_import(
        with_map(mini3()), Netlist(components={"J1": comp}), "OBC", use_pin_function=True
    )
    assert [(r.read, r.stored) for r in plan.renamed] == [("TTC1_TXP", "TTC1_TX+"), ("RXN", "RX-")]


def test_netlist_a_mapped_name_too_long_is_refused_as_a_long_net_name() -> None:
    long = {"X": "S" * 200}
    plan = plan_netlist_import(with_map(mini3(), long), netlist({"1": "/P_X"}), "OBC")
    assert not plan.rows[0].ok and not plan.ops and not plan.renamed
    assert "cannot be used as a signal name" in plan.rows[0].message


def test_netlist_a_locked_pin_is_not_changed_and_the_warning_names_the_mapped_name() -> None:
    p = with_map(mini3())
    first = plan_netlist_import(p, netlist({"1": "/TX+", "2": "/RTN"}), "OBC")
    put: Any = first.ops[0]
    conn = put.obj
    pins = [evolve(x, locked=True) if x.id == "1" else x for x in conn.pins]
    p.connectors[conn.id] = evolve(conn, pins=pins)
    plan = plan_netlist_import(p, netlist({"1": "/TTC1_TXP", "2": "/RXN"}), "OBC")
    assert plan.rows[0].ok
    assert planned(plan) == {"1": "TX+", "2": "RX-"}
    assert [(r.where, r.read) for r in plan.renamed] == [("OBC-J1 pin 2", "RXN")]
    assert (
        "OBC-J1: pin 1 is locked (signal TX+) and was not changed; the netlist says TTC1_TX+"
        in plan.warnings
    )


def test_netlist_the_record_lists_each_rename_as_a_conversion(tmp_path: Path) -> None:
    f = tmp_path / "ttc.net"
    f.write_text("x", encoding="utf-8")  # the report reads the file's SHA-256 only
    nl = netlist({"1": "/TTC1_TXP", "2": "/RTN"})
    plan = plan_netlist_import(with_map(mini3()), nl, "OBC")
    record = netlist_report(f, tmp_path, nl, plan).record()
    assert record.converted_count == 1
    got = record.rows_converted[0]
    assert (got.row, got.field, got.read, got.unit, got.stored, got.item) == (
        1, "signal", "TTC1_TXP", "signal map", "TTC1_TX+", "OBC-J1 pin 1",
    )  # fmt: skip
    # without a map: no conversion, the record of 4.3.0
    bare = plan_netlist_import(mini3(), nl, "OBC")
    assert netlist_report(f, tmp_path, nl, bare).record().converted_count == 0


@pytest.mark.parametrize(
    "table", [None, {}, {"TTC1_TXP": "TTC1_TXP"}], ids=["none", "empty", "bad"]
)
def test_netlist_without_a_usable_map_reads_names_as_4_3_0(table: object) -> None:
    """No key, an empty table or a table the check refuses: no name is read against a map."""
    nets = {"1": "/TTC1_TXP", "2": "/TXP_RXN"}
    plain = plan_netlist_import(mini3(), netlist(nets), "OBC")
    mapped = plan_netlist_import(with_map(mini3(), table), netlist(nets), "OBC")
    assert mapped.ops == plain.ops and mapped.warnings == plain.warnings
    assert mapped.unmatched_signals == plain.unmatched_signals and mapped.renamed == []


# ---- import-pinout: the plan --------------------------------------------------------------------


def pinout_plan(p: Project, text: str) -> Any:
    table = parse_csv(text)
    return plan_pinout_import(
        p, table, guess_mapping(table[0]), unit_id="OBC", default_part="EX-MICROD-9-F",
        connector="J9",
    )  # fmt: skip


PINOUT = (
    "Pin,Signal,Port,Mode\n1,TTC1_TXP,,fixed\n2,TTC1_TXN,,fixed\n3,RXP,TTC1,fixed\n"
    "4,RXN,TTC1,fixed\n5,TXP_RXN,,fixed\n6,TXP.TTC2,,fixed\n7,CAN_H,,fixed\n8,PPS,,fixed\n"
)


def test_pinout_whole_names_ports_the_port_column_and_two_readings() -> None:
    plan = pinout_plan(with_map(mini3()), PINOUT)
    assert plan.bad_count == 0 and plan.connectors == ["OBC-J04"]
    assert [(r.row, r.where, r.read, r.stored) for r in plan.renamed] == [
        (2, "OBC-J04 pin 1", "TTC1_TXP", "TTC1_TX+"),
        (3, "OBC-J04 pin 2", "TTC1_TXN", "TTC1_TX-"),
        (4, "OBC-J04 pin 3", "RXP", "TTC1_RX+"),  # the cell mapped first, then the port written in
        (5, "OBC-J04 pin 4", "RXN", "TTC1_RX-"),
        (7, "OBC-J04 pin 6", "TXP.TTC2", "TX+.TTC2"),
        (8, "OBC-J04 pin 7", "CAN_H", "CANH"),
    ]
    assert [r.signal for r in plan.rows] == [
        "TTC1_TX+", "TTC1_TX-", "TTC1_RX+", "TTC1_RX-", "TXP_RXN", "TX+.TTC2", "CANH", "PPS",
    ]  # fmt: skip
    assert (
        "TXP_RXN on OBC-J04 pin 5 can be read as TXP or RXN of the signal map, so it is not "
        "renamed." in plan.warnings
    )
    assert plan.port_lines[0].startswith("OBC-J04: ") and "TTC1 (pins 1-4)" in plan.port_lines[0]
    assert sorted(plan.unmatched_signals) == ["PPS", "TXP_RXN"]


def test_pinout_without_a_map_the_plan_is_the_plan_of_4_3_0() -> None:
    plain = pinout_plan(mini3(), PINOUT)
    empty = pinout_plan(with_map(mini3(), {}), PINOUT)
    assert plain.renamed == empty.renamed == []
    assert [r.signal for r in plain.rows][:4] == ["TTC1_TXP", "TTC1_TXN", "RXP", "RXN"]
    assert plain.ops == empty.ops and plain.warnings == empty.warnings
    assert plain.unmatched_signals == empty.unmatched_signals


def test_pinout_a_mapped_name_too_long_is_refused() -> None:
    long = {"X": "S" * 200}
    plan = pinout_plan(with_map(mini3(), long), "Pin,Signal,Mode\n1,P_X,fixed\n2,X,fixed\n")
    assert plan.bad_count == 1 and not plan.ops and not plan.renamed
    assert [r.ok for r in plan.rows] == [False, True]


def test_pinout_the_record_lists_each_rename_after_the_direction_words(tmp_path: Path) -> None:
    text = "Pin,Signal,Mode,Direction\n1,TTC1_TXP,fixed,TEST\n2,PWR,fixed,\n"
    f = tmp_path / "obc.csv"
    f.write_text(text, encoding="utf-8")
    table = parse_csv(text)
    plan = pinout_plan(with_map(mini3()), text)
    report = pinout_report(f, tmp_path, table, guess_mapping(table[0]), plan)
    got = [(c.row, c.field, c.read, c.unit, c.stored, c.item) for c in report.converted]
    assert got == [
        (2, "direction", "TEST", "Direction word", "not set", "OBC-J04 pin 1"),
        (2, "signal", "TTC1_TXP", "signal map", "TTC1_TX+", "OBC-J04 pin 1"),
    ]
    # the echo of the report leaves the renames to the importer's own lines
    lines = report.lines(listed_apart=(signal_map.UNIT,))
    assert [x for x in lines if x.startswith("Converted")] == [
        "Converted, row 2 (OBC-J04 pin 1): TEST Direction word = not set"
    ]


# ---- the command line: the design's runs (section 2.5 and 5.3) ----------------------------------


@pytest.fixture
def wheel(tmp_path: Path) -> tuple[Path, Path, Path]:
    """first-steps, the templates, and the template netlist with the RS-422 nets renamed to the
    team's words in a port (`/TTC1_TXP` ...), as in section 2.5 of the design."""
    folder = tmp_path / "fs"
    templates.create_project(folder, "first-steps")
    tpl = tmp_path / "tpl"
    templates.copy_import_templates(tpl)
    text = (tpl / "wheel-connectors.net").read_text(encoding="utf-8")
    for old, new in TTC1_NETS.items():
        text = text.replace(f'"{old}"', f'"{new}"')
    net = tmp_path / "ttc.net"
    net.write_text(text, encoding="utf-8")
    return folder, tpl, net


def netlist_text_430(net: Path) -> str:
    """What 4.3.0 prints for the dry run of the renamed netlist on first-steps (section 2.5),
    word for word, with or without `--signal-map signal-map.csv`."""
    return (
        f"Read 2 connector(s) of KiCad netlist from {net.name} (sha256 {file_sha256(net)[:12]}).\n"
        "warning: the component field 'value' is not read; its values are not imported.\n"
        "note: KiCad design source: wheel.kicad_sch\n"
        "J1: OK updated RW1-J01 (2 signal pin(s))\n"
        "J2: OK updated RW1-J02 (4 signal pin(s))\n"
        "Signals that match no interface type (map them with --signal-map, or ignore if they are "
        "not interfaces):\n"
        "  TTC1_RXN: RW1-J02 pin 4\n"
        "  TTC1_RXP: RW1-J02 pin 3\n"
        "  TTC1_TXN: RW1-J02 pin 2\n"
        "  TTC1_TXP: RW1-J02 pin 1\n"
        "Dry run: nothing was changed.\n"
    )


def test_cli_netlist_without_the_map_prints_what_4_3_0_printed(
    wheel: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    folder, tpl, net = wheel
    base = ["import-netlist", str(folder), str(net), "--device", "RW1", "--dry-run"]
    assert run(capsys, *base) == netlist_text_430(net)
    assert run(capsys, *base, "--signal-map", str(tpl / "signal-map.csv")) == netlist_text_430(net)
    assert doc(capsys, *base)["renamed_signals"] == []


def test_cli_netlist_with_the_project_map(
    wheel: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    folder, tpl, net = wheel
    take_map(capsys, folder, tpl / "signal-map.csv")
    base = ["import-netlist", str(folder), str(net), "--device", "RW1"]
    out = run(capsys, *base, "--dry-run")
    assert out.splitlines()[3:] == [
        "J1: OK updated RW1-J01 (2 signal pin(s))",
        "J2: OK updated RW1-J02 (4 signal pin(s))",
        HEADING.format(4),
        "  TTC1_TXP -> TTC1_TX+: RW1-J02 pin 1",
        "  TTC1_TXN -> TTC1_TX-: RW1-J02 pin 2",
        "  TTC1_RXP -> TTC1_RX+: RW1-J02 pin 3",
        "  TTC1_RXN -> TTC1_RX-: RW1-J02 pin 4",
        "Dry run: nothing was changed.",
    ]
    assert "Converted" not in out  # the renames are said once, in the importer's own lines
    got = doc(capsys, *base, "--dry-run")
    assert got["renamed_signals"][0] == {
        "connector": "RW1-J02", "pin": "1", "read": "TTC1_TXP", "stored": "TTC1_TX+",
    }  # fmt: skip
    assert len(got["renamed_signals"]) == 4 and got["unmatched_signals"] == {}
    assert got["import"]["converted_count"] == 4
    assert list(got)[-2:] == ["renamed_signals", "import"]
    # the command's --signal-map reads whole names and wins per name
    out = run(capsys, *base, "--signal-map", "TTC1_TXP=TX+", "--signal-map", "TXN=RX-")
    assert HEADING.format(3) in out and "TTC1_TXP ->" not in out
    pins = signals(load_project(folder).project, "RW1-J02")
    assert pins == {"1": "TX+", "2": "TTC1_TX-", "3": "TTC1_RX+", "4": "TTC1_RX-"}
    record = load_project(folder).project.import_records["netlist:ttc.net"]
    assert [(c.read, c.unit, c.stored, c.item) for c in record.rows_converted] == [
        ("TTC1_TXN", "signal map", "TTC1_TX-", "RW1-J02 pin 2"),
        ("TTC1_RXP", "signal map", "TTC1_RX+", "RW1-J02 pin 3"),
        ("TTC1_RXN", "signal map", "TTC1_RX-", "RW1-J02 pin 4"),
    ]
    imports = run(capsys, "imports", str(folder))
    assert "netlist  ttc.net  2     0        3" in imports


def test_cli_pinout_with_the_project_map(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The run of the design's end to end test (section 11): a blank project, the template map
    taken with `config --signal-map`, OBC1 imported with the team's names in a port."""
    folder = tmp_path / "p"
    templates.create_project(folder, "blank")
    tpl = tmp_path / "tpl"
    templates.copy_import_templates(tpl)
    take_map(capsys, folder, tpl / "signal-map.csv")
    names = [f"{d}_{s}" for d in ("TTC1", "TTC2") for s in ("TXP", "TXN", "RXP", "RXN")]
    rows = [f"J1,{k},{name},fixed" for k, name in enumerate(names, start=1)]
    f = tmp_path / "obc.csv"
    f.write_text("Connector,Pin,Signal,Mode\n" + "\n".join(rows) + "\n", encoding="utf-8")
    argv = ["import-pinout", str(folder), str(f), "--device", "OBC1", "--new-device", "OBC"]
    argv += ["--default-part", "EX-DSUB-9-F"]
    out = run(capsys, *argv).splitlines()
    k = out.index(HEADING.format(8))
    assert out[k - 1] == "OBC1-J01: OK added (8 pin(s))"
    assert out[k + 1 : k + 3] == [
        "  TTC1_TXP -> TTC1_TX+: OBC1-J01 pin 1",
        "  TTC1_TXN -> TTC1_TX-: OBC1-J01 pin 2",
    ]
    assert out[k + 9] == "OBC1-J01: Ethernet or RS-422 ports: TTC1 (pins 1-4), TTC2 (5-8)"
    assert not any(x.startswith(("Converted", "Signals that match")) for x in out)
    p = load_project(folder).project
    assert signals(p, "OBC1-J01")["5"] == "TTC2_TX+"
    assert p.import_records["pinout:obc.csv"].converted_count == 8
    again = doc(capsys, *argv)  # the same file again: the same names, nothing to change
    assert len(again["renamed_signals"]) == 8 and again["changed"] is False
    # a file export-pinout wrote holds the type's names: read back, nothing is renamed
    back = tmp_path / "back.csv"
    run(capsys, "export-pinout", str(folder), "--device", "OBC1", "-o", str(back))
    got = doc(capsys, "import-pinout", str(folder), str(back), "--device", "OBC1")
    assert got["renamed_signals"] == [] and got["import"]["converted_count"] == 0


def test_cli_pinout_without_the_map_prints_what_4_3_0_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "fs"
    templates.create_project(folder, "first-steps")
    f = tmp_path / "obc.csv"
    f.write_text(
        "Connector,Pin,Signal,Mode\nJ1,1,TTC1_TXP,fixed\nJ1,2,TTC1_TXN,fixed\nJ1,3,TTC1_RXP,fixed\n"
        "J1,4,TTC1_RXN,fixed\nJ1,5,TTC1_PPS,fixed\n",
        encoding="utf-8",
    )
    argv = ["import-pinout", str(folder), str(f), "--device", "OBC1", "--connector", "J9"]
    argv += ["--default-part", "EX-DSUB-9-F", "--dry-run"]
    assert run(capsys, *argv) == (
        f"Read 5 row(s) of device pinout from obc.csv (sha256 {file_sha256(f)[:12]}).\n"
        "Columns read: Connector -> connector, Pin -> pin, Signal -> signal, Mode -> mode\n"
        "OBC1-J05: OK added (5 pin(s))\n"
        "Signals that match no interface type (nothing can connect to them until a type has "
        "them):\n"
        "  TTC1_PPS: OBC1-J05 pin 5\n"
        "  TTC1_RXN: OBC1-J05 pin 4\n"
        "  TTC1_RXP: OBC1-J05 pin 3\n"
        "  TTC1_TXN: OBC1-J05 pin 2\n"
        "  TTC1_TXP: OBC1-J05 pin 1\n"
        "Dry run: nothing was changed.\n"
    )


def _files(folder: Path) -> dict[str, bytes]:
    """The project's files but the journal (it holds a time) and the config of the map."""
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file() and not p.name.startswith("journal") and "naming.json" not in p.name
    }


@pytest.mark.parametrize("kind", ["netlist", "pinout"], ids=["net", "pin"])
def test_a_project_with_an_empty_map_imports_byte_for_byte_as_one_without(
    kind: str, wheel: tuple[Path, Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder, _tpl, net = wheel
    empty = tmp_path / "empty"
    shutil.copytree(folder, empty)
    edit_json(empty / "config" / "naming.json", lambda d: d["values"].update(signal_map={}))
    f = tmp_path / "obc.csv"
    f.write_text("Pin,Signal,Mode\n1,TTC1_TXP,fixed\n2,TXP_RXN,fixed\n", encoding="utf-8")
    texts = []
    for target in (folder, empty):
        argv = (
            ["import-netlist", str(target), str(net), "--device", "RW1"]
            if kind == "netlist"
            else ["import-pinout", str(target), str(f), "--device", "OBC1", "--connector", "J9",
                  "--default-part", "EX-DSUB-9-F"]
        )  # fmt: skip
        texts.append(run(capsys, *argv).replace(str(target), "DIR"))
    assert texts[0] == texts[1] and "Renamed" not in texts[0]
    assert _files(folder) == _files(empty)


# ---- the library imports read no map (N11) ------------------------------------------------------


def test_library_devices_keep_their_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "src"
    p = mini3()
    conn = p.connectors["OBC-J01"]
    pins = [Pin(id="1", signal="TTC1_TXP", fixed=True), Pin(id="2", signal="RXN", fixed=True)]
    p.connectors["OBC-J01"] = evolve(conn, pins=pins)
    save_project(p, src)
    lib = tmp_path / "lib.json"
    run(capsys, "export-devices", str(src), str(lib), "--device", "OBC")
    dest = tmp_path / "dest"
    save_project(with_map(mini3()), dest)
    out = run(capsys, "import-devices", str(dest), str(lib))
    assert "Renamed" not in out
    got = load_project(dest).project
    obc = next(u for u in sorted(got.units) if u.startswith("OBC-"))  # OBC is taken: OBC-2
    names = {x.signal for c in got.connectors.values() if c.unit_id == obc for x in c.pins}
    assert {"TTC1_TXP", "RXN"} <= names


# ---- the import wizard's preview ----------------------------------------------------------------


def test_the_wizard_preview_shows_the_renames(tmp_path: Path) -> None:
    pytest.importorskip("PySide6")
    from harness_design_studio.gui import import_kinds

    f = tmp_path / "obc.csv"
    f.write_text(PINOUT, encoding="utf-8")
    source = import_kinds.read_source("pinout", f)
    options = import_kinds.default_options("pinout", source)
    options.device, options.default_part, options.connector = "OBC", "EX-MICROD-9-F", "J9"
    view = import_kinds.plan_import(with_map(mini3()), source, options, tmp_path)
    assert view.notes[:3] == [
        HEADING.format(6),
        "  TTC1_TXP -> TTC1_TX+: OBC-J04 pin 1",
        "  TTC1_TXN -> TTC1_TX-: OBC-J04 pin 2",
    ]
    assert [r[3] for r in view.preview][:3] == ["TTC1_TX+", "TTC1_TX-", "TTC1_RX+"]
    assert any("TXP_RXN on OBC-J04 pin 5" in r.reason for r in view.rows if r.state == "warning")
    assert view.record is not None and view.record.converted_count == 6
    plain = import_kinds.plan_import(mini3(), source, options, tmp_path)
    assert not any(n.startswith("Renamed") for n in plain.notes)
    assert plain.record is not None and plain.record.converted_count == 0
    # the netlist page: its own box of pairs acts as --signal-map and wins per name
    net = tmp_path / "unit.net"
    net.write_text(
        '(export (version "E") (components (comp (ref "J1") (fields (field (name "HarnessPart") '
        '"EX-MICROD-9-F")))) (nets (net (code "1") (name "/TTC1_TXP") (node (ref "J1") (pin "1")))'
        ' (net (code "2") (name "/RXN") (node (ref "J1") (pin "2")))))',
        encoding="utf-8",
    )
    source = import_kinds.read_source("netlist", net)
    options = import_kinds.default_options("netlist", source)
    options.unit_id, options.signal_map = "OBC", {"RXN": "TX-"}
    view = import_kinds.plan_import(with_map(mini3()), source, options, tmp_path)
    assert view.notes[:2] == [HEADING.format(1), "  TTC1_TXP -> TTC1_TX+: OBC-J1 pin 1"]


@pytest.mark.gui
def test_the_wizard_check_page_lists_the_renames(qtbot: Any, tmp_path: Path) -> None:
    """The pinout page of the import wizard: the preview shows the stored names, the check page
    the renames above the ports, as the echo of `import-pinout`."""
    pytest.importorskip("PySide6")
    from harness_design_studio.gui.controller import EditorController
    from harness_design_studio.gui.import_wizard import PAGE_CHECK, PAGE_MAP
    from tests.test_edit_device import device
    from tests.test_ux_devices_import import make, sheet
    from tests.test_ux_rel_import import next_, rows_of
    from tests.ux_rel import themed

    themed()
    ctl = EditorController()
    ctl._install(with_map(device()), None, None)
    lines = ["Connector,Pin,Port,Signal,Mode"]
    lines += [f"J1,{k},TTC1,{s},fixed" for k, s in enumerate(("TXP", "TXN", "RXP", "RXN"), 1)]
    w = make(qtbot, ctl, sheet(tmp_path, "\n".join(lines) + "\n"))
    w.browse()
    assert next_(w) == PAGE_MAP
    page = w.map_page
    unit: Any = page.pin_widgets["device"]
    unit.setCurrentIndex(unit.findData("GYRO1"))
    part: Any = page.pin_widgets["part"]
    part.setCurrentIndex(part.findData("MY-BIG-8-M"))
    assert w.plan is not None and w.plan.importable
    assert [r[3] for r in rows_of(page.model)[:4]] == [
        "TTC1_TX+",
        "TTC1_TX-",
        "TTC1_RX+",
        "TTC1_RX-",
    ]
    assert next_(w) == PAGE_CHECK
    assert w.check_page.notes.text().splitlines() == [
        HEADING.format(4),
        "  TXP -> TTC1_TX+: GYRO1-J01 pin 1",
        "  TXN -> TTC1_TX-: GYRO1-J01 pin 2",
        "  RXP -> TTC1_RX+: GYRO1-J01 pin 3",
        "  RXN -> TTC1_RX-: GYRO1-J01 pin 4",
        "GYRO1-J01: Ethernet or RS-422 port: TTC1 (pins 1-4)",
    ]
