# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-PIN-08, REQ-PIN-09, REQ-IMPORT-02, REQ-GUI-32. The end-to-end walk of 4.4.0 (pull request 7
of section 16 of `docs/ait/DESIGN_4.4_NAMES_PORTS.md`; the tests of its section 11), through the
command line wherever a command exists and through the plans the editor runs (`History`) where none
does (no command adds an interface, makes a connection, unassigns pins or chooses a port).

The case of section 2.1 of the design: a blank project; `import-pinout` of an on-board computer
OBC1 whose connector J1 holds the ports `TTC1_*` and `TTC2_*`, and of two transceivers TTC1 and
TTC2 with the bare names; two RS-422 interfaces in the *wrong* ID order (IF-001 to TTC2 before
IF-002 to TTC1). With the settings off, the walk shows what 4.3.0 does: IF-001 gets the pins named
for TTC1 and nothing reports it (`generate`, `verify`, `drc`, `export`, `explain`). Then
`config --far-device-names on`: the verifier reports the ports Generate gave before
(`port_far_device`, an error that reaches the DRC as `verify-mismatch`), `generate` moves them, a
second one changes nothing, `verify` and `verify --outputs` are clean, `explain` and
`system/box_pinouts.csv` show the far device; `--far-device-names off` takes the key out and the
ports stay.

Then the pairing of a connection (section 2.3 and part B): the proposal for TTC2 pairs the TTC1
pins with the setting off; a link made so is named by the review once the setting is on; the links
made again from the proposals pair each transceiver's own pins and the review is quiet. Then the
signal map (part C): `config --signal-map` takes the shipped template, `import-pinout` and
`import-netlist` write the type's names for the team's (`TTC1_TXP` becomes `TTC1_TX+`), list and
record each rename (`--json` `renamed_signals`, `imports`), and with the setting on the chain ends
with the right ports. Then the swap of two ports by hand (part E): *Unassign* keeps the names of the
fixed pins, *Choose port…* puts IF-001 on TTC2, Generate does the rest. Last the editor:
*Settings > Project* (the check box and the signal map), the Inspector's warning, Generate and
*Choose port…* with its marks.

Every device, signal and file name here is made up (`OBC1`, `TTC1`, `TTC2`)."""

import csv
import io
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.core import devices, links, signal_map
from harness_design_studio.core.commands import History
from harness_design_studio.core.edit import ops_add_interface
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from tests.test_e2e_300 import ok
from tests.test_e2e_rs422x3 import run

OBC = "OBC1-J01"  # the import numbers connector J1 of OBC1 as OBC1-J01
RS422 = ("TX+", "TX-", "RX+", "RX-")
TEAM = ("TXP", "TXN", "RXP", "RXN")  # the team's words of the shipped template signal-map.csv
PORTS_LINE = "OBC1-J01: Ethernet or RS-422 ports: TTC1 (pins 1-4), TTC2 (5-8)"
RENAMED = "Renamed by the project's signal map (config/naming.json signal_map): {} signal(s)"
ON = "Signal names name the far device: on (config/naming.json, far_device_names)."
OFF = "Signal names name the far device: off (the setting is taken out of config/naming.json)."
STALE = (
    "Generate reads this setting, so the harness plans are now out of date. Run "
    "`harness-design-studio generate` again, then export again."
)
WRONG = (
    "Interface {i} goes to unit {far} but uses port {port} of OBC1-J01, which is named after unit "
    "{port} (naming.far_device_names). Regenerate, or choose the port of {far}."
)
PORT_430 = (
    "Port of the pin: TTC1_TX+ is the TX+ of port TTC1 of OBC1-J01; the pins of one port go to one "
    "interface (ports in name order, interfaces in ID order) = port TTC1"
)
PORT_440 = (
    "Port of the pin: TTC2_TX+ is the TX+ of port TTC2 of OBC1-J01; the port named after TTC2, the "
    "device at the other end of IF-001, comes first (naming.far_device_names), then ports in name "
    "order, interfaces in ID order = port TTC2"
)
REASON_440 = (
    "pin-allocation: TX+ of IF-001 uses pin 5, the TX+ of port TTC2 of OBC1-J01; the port named "
    "after unit TTC2 at the other end (naming.far_device_names)"
)


def sheet(tmp_path: Path, name: str, rows: list[str], heading: str = "Connector,Pin,Signal,Mode") -> Path:  # fmt: skip
    f = tmp_path / name
    f.write_text("\n".join([heading, *rows]) + "\n", encoding="utf-8", newline="\n")
    return f


def obc_rows(words: tuple[str, ...] = RS422, mode: str = "fixed") -> list[str]:
    """J1 of OBC1: the port of TTC1 on pins 1 to 4, the port of TTC2 on pins 5 to 8."""
    names = [f"{d}_{s}" for d in ("TTC1", "TTC2") for s in words]
    return [f"J1,{k},{n},{mode}" for k, n in enumerate(names, start=1)]


def bare_rows(words: tuple[str, ...] = RS422) -> list[str]:
    return [f"J1,{k},{s},fixed" for k, s in enumerate(words, start=1)]


def import_pinout(
    capsys: pytest.CaptureFixture[str], proj: Path, f: Path, device: str, part: str, *more: str
) -> str:
    title = {"OBC1": "On-board computer", "TTC1": "Transceiver 1", "TTC2": "Transceiver 2"}[device]
    return ok(
        capsys, "import-pinout", proj, f, "--device", device, "--new-device", title,
        "--default-part", part, *more,
    )  # fmt: skip


def two_transceivers(proj: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A blank project, OBC1 with the ports TTC1 and TTC2 on J1, TTC1 and TTC2 with bare names."""
    ok(capsys, "new", proj, "--template", "blank")
    out = import_pinout(
        capsys, proj, sheet(tmp_path, "obc1.csv", obc_rows()), "OBC1", "EX-DSUB-9-F"
    )
    assert "OBC1-J01: OK added (8 pin(s))" in out and PORTS_LINE in out
    ttc = sheet(tmp_path, "ttc.csv", bare_rows())
    for device in ("TTC1", "TTC2"):
        assert f"{device}-J01: OK added (4 pin(s))" in import_pinout(
            capsys, proj, ttc, device, "EX-DSUB-9-M"
        )


def add_interfaces(proj: Path) -> None:
    """The editor's *Add interface* (no command adds one), in the wrong ID order: IF-001 from OBC1
    to TTC2, then IF-002 from OBC1 to TTC1. The tool chooses the connectors (each device has one)."""
    p = load_project(proj).project
    history = History(p)
    for far in ("TTC2", "TTC1"):
        ops, iid = ops_add_interface(p, "rs422", "OBC1", far)
        history.execute(f"Add {iid}", ops)
    save_project(p, proj)
    assert {i.id: i.name for i in p.interfaces.values()} == {
        "IF-001": "RS-422 OBC1 to TTC2", "IF-002": "RS-422 OBC1 to TTC1",
    }  # fmt: skip


def on_obc(proj: Path) -> dict[str, str]:
    """The pins of OBC1-J01 as saved: signal name -> the interface on it."""
    p = load_project(proj).project
    return {x.signal or x.id: x.interface_id or "" for x in p.connectors[OBC].pins}


def ports(proj: Path) -> dict[str, set[str]]:
    """Interface -> the ports it uses on OBC1-J01 (the name before the last `_`)."""
    found: dict[str, set[str]] = {}
    for name, iid in on_obc(proj).items():
        found.setdefault(iid, set()).add(name.rsplit("_", 1)[0])
    return found


def box_pinouts(proj: Path) -> dict[str, str]:
    """`system/box_pinouts.csv` read back: the signal of each pin of OBC1-J01 -> its interface."""
    text = (proj / "outputs" / "system" / "box_pinouts.csv").read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    rows = csv.DictReader(io.StringIO(body))
    return {r["Signal"]: r["Interface"] for r in rows if r["Connector"] == OBC}


def drc(capsys: pytest.CaptureFixture[str], proj: Path) -> list[dict[str, str]]:
    """The findings of `drc --json`; it exits 1 while an error is open, 0 otherwise."""
    code, out = run(capsys, "drc", str(proj), "--json")
    doc = json.loads(out)
    assert code == (1 if doc["open_errors"] else 0), out
    found: list[dict[str, str]] = doc["findings"]
    return found


def naming(proj: Path) -> dict[str, Any]:
    values: dict[str, Any] = json.loads(
        (proj / "config" / "naming.json").read_text(encoding="utf-8")
    )["values"]
    return values


BY_4_3_0 = {
    "TTC1_TX+": "IF-001", "TTC1_TX-": "IF-001", "TTC1_RX+": "IF-001", "TTC1_RX-": "IF-001",
    "TTC2_TX+": "IF-002", "TTC2_TX-": "IF-002", "TTC2_RX+": "IF-002", "TTC2_RX-": "IF-002",
}  # fmt: skip
BY_FAR_DEVICE = {
    name: {"IF-001": "IF-002", "IF-002": "IF-001"}[iid] for name, iid in BY_4_3_0.items()
}


def test_generate_gives_each_interface_the_port_of_its_far_device(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = tmp_path / "proj"
    # 1. the settings off: what 4.3.0 does, the wrong ports and nothing reported (section 2.1)
    two_transceivers(proj, tmp_path, capsys)
    add_interfaces(proj)
    out = ok(capsys, "generate", proj)
    assert "1 added, 0 changed" in out and "2 interfaces and 8 wires checked: 0 error(s)" in out
    assert on_obc(proj) == BY_4_3_0  # the interface to TTC2 has the pins named for TTC1
    assert "0 error(s)" in ok(capsys, "verify", proj)
    found = drc(capsys, proj)
    assert {f["rule"] for f in found} == {"part-unapproved", "unchecked-config", "unconfirmed"}
    assert not any(f["severity"] == "error" for f in found)
    assert "far device" not in ok(capsys, "explain", proj, f"{OBC}.1")
    assert PORT_430 in ok(capsys, "explain", proj, f"{OBC}.1")
    ok(capsys, "export", proj)
    assert box_pinouts(proj) == BY_4_3_0
    code, out = run(capsys, "config", str(proj))  # exit 1: the engineering values are not set
    assert code == 1 and "far device" not in out and "Signal map" not in out
    before = tmp_path / "before"
    shutil.copytree(proj, before)  # generated by the rules of 4.3.0, for steps 2 and 5
    naming_bytes = (proj / "config" / "naming.json").read_bytes()

    # 2. the setting on: the verifier reports the ports Generate gave before
    code, out = run(capsys, "config", str(proj), "--far-device-names", "on")
    assert code == 1 and out.splitlines()[:2] == [STALE, ON]
    assert naming(proj)["far_device_names"] is True
    code, out = run(capsys, "verify", str(proj))
    assert code == 1
    for line in (
        f"error: [port_far_device] {WRONG.format(i='IF-001', far='TTC2', port='TTC1')}",
        f"error: [port_far_device] {WRONG.format(i='IF-002', far='TTC1', port='TTC2')}",
        "error: [outputs_outdated] The model changed after the harness plans were generated. "
        "Generate again before releasing.",
    ):
        assert line in out.splitlines()
    mismatch = [f for f in drc(capsys, proj) if f["rule"] == "verify-mismatch"]
    assert sorted(f["title"] for f in mismatch if ".port_far_device." in f["id"]) == [
        WRONG.format(i="IF-001", far="TTC2", port="TTC1"),
        WRONG.format(i="IF-002", far="TTC1", port="TTC2"),
    ]
    assert all(f["severity"] == "error" for f in mismatch)

    # 3. generate moves them; a second one changes nothing; verify is clean
    out = ok(capsys, "generate", proj)
    assert "0 added, 1 changed" in out and "0 error(s)" in out
    assert on_obc(proj) == BY_FAR_DEVICE
    assert "0 added, 0 changed, 1 unchanged" in ok(capsys, "generate", proj)
    assert "0 error(s)" in ok(capsys, "verify", proj)
    record = load_project(proj).project.generation
    assert record is not None
    assert record.provenance["naming:far_device_names"] == [
        "on: a port named after the unit at the other end first"
    ]
    assert record.provenance["pin:OBC1-J01.5"] == [REASON_440]
    text = ok(capsys, "explain", proj, f"{OBC}.5")
    assert PORT_440 in text
    assert "Signal names name the far device = yes   [config/naming.json: far_device_names]" in text
    assert "A-FAR-DEVICE (setting)" in text
    assert not {f["rule"] for f in drc(capsys, proj)} & {"verify-mismatch"}
    ok(capsys, "export", proj)
    assert box_pinouts(proj) == BY_FAR_DEVICE
    assert "0 error(s)" in ok(capsys, "verify", proj, "--outputs")

    # 4. the order of the IDs does not matter: the same project with IF-001 to TTC1 first
    other = tmp_path / "other"
    two_transceivers(other, tmp_path, capsys)
    p = load_project(other).project
    history = History(p)
    for far in ("TTC1", "TTC2"):
        ops, iid = ops_add_interface(p, "rs422", "OBC1", far)
        history.execute(f"Add {iid}", ops)
    save_project(p, other)
    run(capsys, "config", str(other), "--far-device-names", "on")
    ok(capsys, "generate", other)
    assert ports(other) == {"IF-001": {"TTC1"}, "IF-002": {"TTC2"}}

    # 5. off again: the key goes, the file is as it was, and the ports stay where they are
    code, out = run(capsys, "config", str(proj), "--far-device-names", "off")
    assert code == 1 and OFF in out.splitlines()
    assert (proj / "config" / "naming.json").read_bytes() == naming_bytes
    assert "0 changed" in ok(capsys, "generate", proj)
    assert on_obc(proj) == BY_FAR_DEVICE
    # and the project of step 1, never switched on, keeps the ports of 4.3.0
    assert on_obc(before) == BY_4_3_0 and "0 changed" in ok(capsys, "generate", before)


def test_the_proposal_and_the_review_of_a_connection_read_the_far_device(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = tmp_path / "proj"
    ok(capsys, "new", proj, "--template", "blank")
    names = ["TTC1_TX", "TTC1_RX", "TTC1_PPS", "TTC2_TX", "TTC2_RX", "TTC2_PPS"]
    obc = sheet(tmp_path, "obc1.csv", [f"J1,{k},{n}" for k, n in enumerate(names, 1)], "Connector,Pin,Signal")  # fmt: skip
    import_pinout(capsys, proj, obc, "OBC1", "EX-DSUB-9-F")
    ttc = sheet(tmp_path, "ttc.csv", ["J1,1,TX", "J1,2,RX", "J1,3,PPS"], "Connector,Pin,Signal")
    for device in ("TTC1", "TTC2"):
        import_pinout(capsys, proj, ttc, device, "EX-DSUB-9-M")

    def pairs(a: str, b: str) -> tuple[list[str], tuple[str, ...]]:
        p = load_project(proj).project
        prop = links.propose_pairs(p, a, b)
        na = {x.id: x.signal for x in p.connectors[a].pins}
        nb = {x.id: x.signal for x in p.connectors[b].pins}
        return [f"{na[x.a_pin]}={nb[x.b_pin]}" for x in prop.pairs], prop.notes

    # 1. off: the proposal for TTC2 pairs the TTC1 pins (section 2.3), and a link is made of it
    for far in ("TTC1-J01", "TTC2-J01"):
        assert pairs(OBC, far) == (["TTC1_TX=RX", "TTC1_RX=TX"], ())
    p = load_project(proj).project
    ops, lid = links.plan_add_link(p, OBC, "TTC2-J01")  # the editor's Connect, with the proposal
    History(p).execute(f"Connect {lid}", ops)
    save_project(p, proj)
    review = [f for f in drc(capsys, proj) if f["rule"].startswith("link-")]
    assert {f["rule"] for f in review} == {"link-unpaired"}  # the review of 4.3.0 sees no mismatch

    # 2. on: the review names the pairs of a third device's pins
    run(capsys, "config", str(proj), "--far-device-names", "on")
    review = [f for f in drc(capsys, proj) if f["rule"].startswith("link-")]
    titles = [f["title"] for f in review]
    assert titles[:3] == [
        "Link L1 pairs pin 1 of OBC1-J01 with pin 2 of TTC2-J01, but TTC1_TX names unit TTC1, not "
        "TTC2. Pair it in a link to TTC1, or rename the pin.",
        "Link L1 pairs pin 2 of OBC1-J01 with pin 1 of TTC2-J01, but TTC1_RX names unit TTC1, not "
        "TTC2. Pair it in a link to TTC1, or rename the pin.",
        "Pin 3 of OBC1-J01 is named TTC1_PPS (unit TTC1) but no link pairs it. Link OBC1-J01 to a "
        "connector of TTC1, or set its role to Spare if it is not used.",
    ]
    assert [f["rule"] for f in review[:3]] == ["link-signal-mismatch"] * 2 + ["link-unpaired"]
    assert all(f["severity"] == "warning" for f in review)

    # 3. the person deletes L1 and connects again: each transceiver gets its own pins
    p = load_project(proj).project
    history = History(p)
    history.execute("Delete L1", links.plan_delete_link(p, "L1"))
    save_project(p, proj)
    note = (
        "Pins {pins} of OBC1-J01 name device {device}, so they are not offered in a link to {far} "
        "(Settings > Project: Signal names name the far device)."
    )
    assert pairs(OBC, "TTC1-J01") == (
        ["TTC1_TX=RX", "TTC1_RX=TX", "TTC1_PPS=PPS"],
        (note.format(pins="4, 5 and 6", device="TTC2", far="TTC1"),),
    )
    assert pairs(OBC, "TTC2-J01") == (
        ["TTC2_TX=RX", "TTC2_RX=TX", "TTC2_PPS=PPS"],
        (note.format(pins="1, 2 and 3", device="TTC1", far="TTC2"),),
    )
    # the one-click connection starts with the connector of the far device's pins and pairs them
    for far in ("TTC2", "TTC1"):
        quick = links.plan_quick_link(p, "OBC1", far)
        history.execute(f"Connect {far}", quick.ops)
    assert [(x.b_connector, len(x.pairs)) for x in sorted(p.links.values(), key=lambda x: x.id)] == [
        ("TTC2-J01", 3), ("TTC1-J01", 3),
    ]  # fmt: skip
    save_project(p, proj)
    assert not [f for f in drc(capsys, proj) if f["rule"].startswith("link-")]


def ttc_netlist(tmp_path: Path) -> Path:
    """A KiCad netlist of TTC2's connector J1, its nets in the team's words (`/TXP` …)."""
    nets = "".join(
        f'    (net (code "{k}") (name "/{n}")\n'
        f'      (node (ref "J1") (pin "{k}") (pinfunction "Pin_{k}") (pintype "passive")))\n'
        for k, n in enumerate(TEAM, start=1)
    )
    f = tmp_path / "ttc2.net"
    f.write_text(
        '(export (version "E")\n  (design\n    (source "ttc2/ttc2.kicad_sch")\n'
        '    (tool "Eeschema 10.0.6"))\n  (components\n    (comp (ref "J1")))\n  (nets\n'
        f"{nets}))\n",
        encoding="utf-8",
    )
    return f


def test_the_signal_map_renames_the_teams_names_at_import_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = tmp_path / "proj"
    ok(capsys, "new", proj, "--template", "blank")
    ok(capsys, "templates", tmp_path / "templates")
    template = tmp_path / "templates" / "signal-map.csv"
    # 1. the shipped template as the project's map
    code, out = run(capsys, "config", str(proj), "--signal-map", str(template))
    assert code == 1 and out.splitlines()[0] == "Signal map: 6 name(s) in config/naming.json."
    assert naming(proj)["signal_map"] == signal_map.read_file(template)
    assert dict(zip(TEAM, RS422, strict=True)).items() <= naming(proj)["signal_map"].items()

    # 2. import-pinout: the team's names inside a port and whole, renamed, listed and recorded
    obc = sheet(tmp_path, "obc1.csv", obc_rows(TEAM))
    lines = import_pinout(capsys, proj, obc, "OBC1", "EX-DSUB-9-F").splitlines()
    k = lines.index(RENAMED.format(8))
    assert lines[k - 1] == "OBC1-J01: OK added (8 pin(s))"
    assert lines[k + 1 : k + 10] == [
        *(f"  {d}_{t} -> {d}_{s}: OBC1-J01 pin {n}" for n, (d, t, s) in enumerate(
            ((d, t, s) for d in ("TTC1", "TTC2") for t, s in zip(TEAM, RS422, strict=True)), 1)),
        PORTS_LINE,
    ]  # fmt: skip
    assert not any(x.startswith("Signals that match") for x in lines)
    again = json.loads(ok(capsys, "import-pinout", proj, obc, "--device", "OBC1", "--json"))
    assert again["changed"] is False and len(again["renamed_signals"]) == 8
    assert again["renamed_signals"][4] == {
        "connector": OBC, "pin": "5", "read": "TTC2_TXP", "stored": "TTC2_TX+",
    }  # fmt: skip
    ttc1 = sheet(tmp_path, "ttc1.csv", bare_rows(TEAM))
    out = import_pinout(capsys, proj, ttc1, "TTC1", "EX-DSUB-9-M")
    assert RENAMED.format(4) in out and "  TXP -> TX+: TTC1-J01 pin 1" in out

    # 3. import-netlist: TTC2's connector from a sheet of pins, its names from the schematic
    pins = sheet(tmp_path, "ttc2.csv", [f"J1,{n}" for n in range(1, 5)], "Connector,Pin")
    import_pinout(capsys, proj, pins, "TTC2", "EX-DSUB-9-M")
    net = ttc_netlist(tmp_path)
    argv = ["import-netlist", proj, net, "--device", "TTC2", "--connector", "J1=TTC2-J01"]
    doc = json.loads(ok(capsys, *argv, "--dry-run", "--json"))
    assert [(r["read"], r["stored"]) for r in doc["renamed_signals"]] == list(
        zip(TEAM, RS422, strict=True)
    )
    assert doc["unmatched_signals"] == {} and doc["import"]["converted_count"] == 4
    echo = ok(capsys, *argv).splitlines()
    k = echo.index(RENAMED.format(4))
    assert echo[k - 1] == "J1: OK updated TTC2-J01 (4 signal pin(s))"
    assert echo[k + 1] == "  TXP -> TX+: TTC2-J01 pin 1"
    project = load_project(proj).project
    assert [x.signal for x in project.connectors["TTC2-J01"].pins[:4]] == list(RS422)
    record = project.import_records["netlist:ttc2.net"]
    assert [(c.field, c.read, c.unit, c.stored) for c in record.rows_converted] == [
        ("signal", t, "signal map", s) for t, s in zip(TEAM, RS422, strict=True)
    ]
    listed = ok(capsys, "imports", proj).splitlines()
    assert any(x.split()[:5] == ["netlist", "ttc2.net", "1", "0", "4"] for x in listed)
    assert any(x.split()[:5] == ["pinout", "obc1.csv", "8", "0", "8"] for x in listed)

    # 4. the chain ends with the right ports: the interfaces, the setting on, generate, verify
    add_interfaces(proj)
    run(capsys, "config", str(proj), "--far-device-names", "on")
    assert "0 error(s)" in ok(capsys, "generate", proj)
    assert on_obc(proj) == BY_FAR_DEVICE
    assert "0 error(s)" in ok(capsys, "verify", proj)

    # 5. the map acts at import only: taken out, the names stay and Generate changes nothing
    _, out = run(capsys, "config", str(proj), "--signal-map", "none")
    assert out.splitlines()[0] == "Signal map: none (the key is taken out of config/naming.json)."
    assert "signal_map" not in naming(proj)
    assert "0 changed" in ok(capsys, "generate", proj) and on_obc(proj) == BY_FAR_DEVICE


def test_unassign_and_choose_port_swap_two_ports_by_hand(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Section 2.7 and part E: with the setting off, a person moves IF-001 to the port of TTC2.
    *Unassign* frees pins 5 to 8 and keeps their names, *Choose port…* locks them for IF-001, and
    Generate gives IF-002 the port that is left."""
    proj = tmp_path / "proj"
    two_transceivers(proj, tmp_path, capsys)
    add_interfaces(proj)
    ok(capsys, "generate", proj)
    assert on_obc(proj) == BY_4_3_0
    p = load_project(proj).project
    history = History(p)
    history.execute("Unassign", devices.ops_unassign_pins(p, OBC, ["5", "6", "7", "8"]))
    freed = p.connectors[OBC].pins[4:]
    assert [(x.signal, x.interface_id, x.locked, x.fixed) for x in freed] == [
        (f"TTC2_{s}", None, False, True) for s in RS422
    ]  # the names of the fixed pins stay, so the port TTC2 is whole
    choices = devices.port_choices(p, OBC, "IF-001")
    assert [(c.port, c.why_not) for c in choices] == [("TTC1", ""), ("TTC2", "")]
    history.execute("Choose port", devices.ops_assign_port(p, OBC, "TTC2", "IF-001"))
    save_project(p, proj)
    out = ok(capsys, "generate", proj)
    assert "4 locked pin(s) kept" in out and "0 error(s)" in out
    assert on_obc(proj) == BY_FAR_DEVICE
    locked = {x.id for x in load_project(proj).project.connectors[OBC].pins if x.locked}
    assert locked == {"5", "6", "7", "8"}
    assert "0 error(s)" in ok(capsys, "verify", proj)
    # with the setting on, both ports are the far devices': nothing to report, nothing moves
    run(capsys, "config", str(proj), "--far-device-names", "on")
    _, out = run(capsys, "verify", str(proj))
    assert "port_far_device" not in out
    assert "0 changed" in ok(capsys, "generate", proj) and on_obc(proj) == BY_FAR_DEVICE


def test_a_lock_on_another_devices_port_is_kept_and_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A person's *Choose port…* wins over every name (step 1): with the setting on, the verifier
    names the lock as a warning, which the DRC does not list, and Generate gives the other
    interface no port of another device: an error that names both ports (section 3.3)."""
    proj = tmp_path / "proj"
    two_transceivers(proj, tmp_path, capsys)
    add_interfaces(proj)
    ok(capsys, "generate", proj)
    p = load_project(proj).project
    History(p).execute("Choose port", devices.ops_assign_port(p, OBC, "TTC1", "IF-001"))
    save_project(p, proj)
    run(capsys, "config", str(proj), "--far-device-names", "on")
    _, out = run(capsys, "verify", str(proj))
    first = WRONG.format(i="IF-001", far="TTC2", port="TTC1").removesuffix(
        " Regenerate, or choose the port of TTC2."
    )
    assert f"warning: [port_far_device] {first} It is kept because a person locked the pins." in out
    assert f"error: [port_far_device] {WRONG.format(i='IF-002', far='TTC1', port='TTC2')}" in out
    code, out = run(capsys, "generate", str(proj))
    assert code == 1
    assert (
        "IF-002: OBC1-J01 has a fixed pinout and no free pin named TX+, TX-, RX+, RX-, and no free "
        "complete RS-422 port for unit TTC1 (port TTC1 is used by IF-001; port TTC2 is named after "
        "unit TTC2)."
    ) in out
    assert on_obc(proj) == BY_4_3_0  # a refused Generate saves nothing


@pytest.mark.gui
def test_the_editor_sets_names_and_ports(
    qtbot: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton

    from harness_design_studio.gui import strings
    from tests.gui_helpers import DialogScript, hold_drc, make_window

    proj = tmp_path / "proj"
    two_transceivers(proj, tmp_path, capsys)
    add_interfaces(proj)
    ok(capsys, "generate", proj)  # the ports of 4.3.0
    ok(capsys, "templates", tmp_path / "templates")
    template = tmp_path / "templates" / "signal-map.csv"
    win = make_window(tmp_path)
    qtbot.addWidget(win)
    assert win.open_project(proj)
    hold_drc(win)
    win.ctl.set_mode("expert")
    QApplication.processEvents()
    k = next(n for n, e in enumerate(win.ctl.project.interfaces["IF-001"].endpoints) if e.connector_id == OBC)  # fmt: skip

    def inspector_line() -> str | None:
        win.ctl.select("interface", "IF-002")
        win.ctl.select("interface", "IF-001")
        line = win.props.findChild(QLabel, f"end-port-far-{k}")
        return line.text() if line is not None else None

    def port_rows() -> list[tuple[str, str | None]]:
        seen: list[tuple[str, str | None]] = []

        def fn(dlg: Any) -> None:
            box = dlg.port_box
            for n in range(box.count()):
                seen.append((box.itemText(n), box.itemData(n, Qt.ItemDataRole.ToolTipRole)))

        DialogScript(win, fn, accept=False)
        button = win.props.findChild(QPushButton, f"end-port-choose-{k}")
        assert button is not None
        button.click()
        return seen

    # 1. with the setting off, the Inspector says nothing and Choose port… lists the ports plainly
    assert inspector_line() is None
    assert [text for text, _ in port_rows()] == ["TTC1 (pins 1-4)", "TTC2 (pins 5-8)"]

    # 2. Settings > Project: the check box; the Inspector then names the wrong port
    win.set_area("settings")
    win.settings_page.show_section("project")
    win._show_segmentation()
    page = win.settings_page
    page.far_device_box.click()
    assert page.far_device_box.isChecked() and win.ctl.history.next_undo_label == strings.STEP_FAR_DEVICE_ON  # fmt: skip
    assert inspector_line() == (
        f"{strings.SEV_ERROR} IF-001 goes to device TTC2 but uses port TTC1 of OBC1-J01, which is "
        "named after device TTC1 (Settings > Project: Signal names name the far device). "
        "Regenerate, or choose the port of TTC2."
    )
    rows = port_rows()
    assert [text for text, _ in rows] == [
        "TTC2 (pins 5-8), named after TTC2 at the other end",
        "TTC1 (pins 1-4), named after TTC1",
    ]
    assert rows[0][1] == "Pin 5 carries IF-002; unassign it first."

    # 3. Generate in the editor moves the ports, and the warning goes
    DialogScript(win, accept=True)
    win.generate_flow()
    assert {x.signal: x.interface_id for x in win.ctl.project.connectors[OBC].pins} == BY_FAR_DEVICE
    assert inspector_line() is None
    rows = port_rows()
    assert [text for text, _ in rows] == [
        "TTC2 (pins 5-8), named after TTC2 at the other end",
        "TTC1 (pins 1-4), named after TTC1",
    ]
    assert rows[1][1] == "Pin 1 carries IF-002; unassign it first."

    # 4. the signal map: the names of the template file, then Save, one undo step
    win.ask_open_path = lambda title, filters: str(template)  # type: ignore[method-assign]
    page.signal_map_file.click()
    assert signal_map.table(win.ctl.project) == {}  # nothing is saved until Save
    page.signal_map_save.click()
    assert signal_map.table(win.ctl.project) == signal_map.read_file(template)
    assert win.ctl.history.next_undo_label == strings.STEP_SET_SIGNAL_MAP
    assert page.signal_map_state.text() == strings.SETTINGS_SIGNAL_MAP_NOW.format(6)
    win.ctl.save()
    win.ctl.wait_journal()
    win.ctl.release()  # the window lets the folder go

    # 5. the command line reads what the editor saved
    assert naming(proj)["far_device_names"] is True
    assert naming(proj)["signal_map"] == signal_map.read_file(template)
    assert "0 error(s)" in ok(capsys, "verify", proj)
    team = sheet(tmp_path, "obc1-j2.csv", ["J2,1,TTC1_TXP,fixed", "J2,2,TTC1_TXN,fixed"])
    out = ok(capsys, "import-pinout", proj, team, "--device", "OBC1", "--default-part", "EX-DSUB-9-F", "--dry-run")  # fmt: skip
    assert RENAMED.format(2) in out and "  TTC1_TXP -> TTC1_TX+: OBC1-J02 pin 1" in out
