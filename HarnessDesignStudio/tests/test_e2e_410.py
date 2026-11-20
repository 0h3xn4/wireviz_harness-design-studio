# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-OUT-13, REQ-OUT-14, REQ-OUT-15, REQ-LABEL-02. The end-to-end walk of 4.1.0 (pull request 7
of section 14 of `docs/ait/DESIGN_4.1_PRODUCTION_SHEET.md`), through the command line wherever a
command exists and through the plans the editor runs (`History`) where none does (no command adds
an interface or draws a cable from a port).

A new project (`new FOLDER`), which names the label format `harness_device_connector` in
`config/model.json`; two devices whose pinouts come in through `import-pinout`; one RS-422
interface (two shielded pairs); `generate`; a segment length (`import-lengths`) and one length a
person sets (`override`); a cable drawn from a port and left with a loose end; `export
--harness-plan`; `verify --outputs` with 0 errors. Then the written files: the build workbook's
*Production* sheet (after *Cut list*, one block per connector, both ends of every wire, the label
at each end, the shield group with its ends), its *Start here* row *Lengths* and the heading
*Length (m), rear to rear* of *Cut list*; the labels `W001:DEV1:J01` in `labels.csv`; the plan's
*Production* sheet with the same rows in mm, its print set-up (a fixed scale, the heading rows on
every page) and `B4` of a `CON_…` sheet with the device connector's name; a second export
byte-identical. Last, an existing example (`flatsat`) exported keeps the `standard` labels.

Example data only: example devices DEV1 and DEV2 with example pinouts."""

import csv
import io
import json
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from harness_design_studio.core import edit
from harness_design_studio.core.commands import History
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.manual_harness import plan_cable_from_port
from tests.plan_support import PlanCell, check_values, read_plan
from tests.test_e2e_300 import ok
from tests.test_e2e_rs422x3 import files, run
from tests.test_plan_print import setups

NEW_FORMAT = "harness_device_connector"
# DEV1 has the RS-422 port J01 and a heater port J02; DEV2 the other end of the RS-422 link
DEV1 = (
    "Connector,Pin,Signal,Mode\n"
    "J01,1,TX+,fixed\nJ01,2,TX-,fixed\nJ01,3,RX+,fixed\nJ01,4,RX-,fixed\nJ01,5,SGND,fixed\n"
    "J02,1,HTR+,fixed\nJ02,2,HTR-,fixed\n"
)
DEV2 = (
    "Connector,Pin,Signal,Mode\n"
    "J01,1,RX+,fixed\nJ01,2,RX-,fixed\nJ01,3,TX+,fixed\nJ01,4,TX-,fixed\nJ01,5,SGND,fixed\n"
)
PRODUCTION_HEADER = [
    "Pin", "Signal", "Wire", "Goes to", "Wire part", "Colour", "AWG", "Length (m), rear to rear",
    "Length from", "Label at this end", "Shield group: here / far end", "Done (x)",
]  # fmt: skip
SHIELD_S1 = "W001-S1 shielded pair: here floating, far floating"


def sheet_rows(ws: Any) -> list[list[object]]:
    """The rows of a sheet of the build workbook that hold a value, with the trailing empty cells
    dropped."""
    rows = []
    for row in ws.iter_rows(values_only=True):
        cells = list(row)
        while cells and cells[-1] is None:
            cells.pop()
        if cells:
            rows.append(cells)
    return rows


def plan_rows(cells: dict[tuple[int, int], PlanCell]) -> dict[int, list[object]]:
    """The rows of a sheet of the plan by their 0-based number, with the trailing empty cells
    dropped."""
    rows: dict[int, dict[int, object]] = {}
    for (r, c), cell in cells.items():
        rows.setdefault(r, {})[c] = cell.value
    out = {}
    for r, row in sorted(rows.items()):
        cells_ = [row.get(c, "") for c in range(max(row) + 1)]
        while cells_ and cells_[-1] in ("", None):
            cells_.pop()
        if cells_:
            out[r] = cells_
    return out


def design(proj: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Two devices from their pinouts, one RS-422 interface, Generate, a segment length and one
    length a person sets, then a cable drawn from DEV1-J02 and let go on empty ground."""
    for name, text in (("DEV1", DEV1), ("DEV2", DEV2)):
        sheet = tmp_path / f"{name.lower()}.csv"
        sheet.write_text(text, encoding="utf-8", newline="\n")
        ok(
            capsys, "import-pinout", proj, sheet, "--device", name, "--new-device",
            f"Example device {name[-1]}", "--default-part", "EX-MICROD-9-M",
        )  # fmt: skip
    p = load_project(proj).project
    ops, iid = edit.ops_add_interface(p, "rs422", "DEV1", "DEV2")  # no command adds one
    History(p).execute(f"Add {iid}", ops)
    save_project(p, proj)
    assert "1 added" in ok(capsys, "generate", proj)
    lengths = tmp_path / "lengths.csv"
    lengths.write_text("harness,segment,length\nW001,W001-L1,1200\n", encoding="utf-8")
    ok(capsys, "import-lengths", proj, lengths)
    ok(capsys, "generate", proj)
    ok(capsys, "override", proj, "W001-002", "length_m", "1.5", "--reason", "Example length")
    # the editor's drag from a port to empty ground: a harness drawn by hand with a loose end
    p = load_project(proj).project
    made = plan_cable_from_port(p, "DEV1-J02")
    History(p).execute("Cable", made.ops)
    save_project(p, proj)
    assert (made.harness_id, made.loose_id) == ("W002", "W002-P2")
    ok(capsys, "generate", proj)  # Generate keeps the harness a person drew


def test_the_whole_path_of_4_1_0_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = tmp_path / "proj"
    # 1. a new project names the label format of 4.1.0
    ok(capsys, "new", proj)
    model = json.loads((proj / "config" / "model.json").read_text(encoding="utf-8"))
    assert model == {"name": "model", "placeholder": False, "values": {"label_format": NEW_FORMAT}}

    # 2. the design: a box connector at each end of a shielded pair, a loose end
    design(proj, tmp_path, capsys)
    h = load_project(proj).project.harnesses["W001"]
    assert [(s.id, s.kind) for s in h.shields] == [
        ("W001-S1", "shielded_pair"), ("W001-S2", "shielded_pair"),
    ]  # fmt: skip

    # 3. export with the plans, and the independent check
    code, out = run(capsys, "export", str(proj), "--harness-plan", "--json")
    assert code == 0, out
    assert json.loads(out)["harness_plans"] == [
        "harnesses/W001/W001_plan.ods", "harnesses/W002/W002_plan.ods",
    ]  # fmt: skip
    assert "0 error(s)" in ok(capsys, "verify", proj, "--outputs")
    outputs = proj / "outputs"

    # 4. the build workbook: Production after Cut list, both ends of every wire
    wb = openpyxl.load_workbook(outputs / "harnesses" / "W001" / "W001_build.xlsx")
    assert wb.sheetnames[:4] == ["Start here", "Cut list", "Production", "Connectors"]
    production = wb["Production"]
    assert production.print_title_rows == "$1:$1"
    rows = sheet_rows(production)
    assert rows[0] == PRODUCTION_HEADER
    headings = [r[0] for r in rows if len(r) == 1 and "   ·   " in str(r[0])]
    assert headings == [
        "W001-P1   ·   EX-MICROD-9-F   ·   female   ·   mates DEV1-J01 (DEV1:J01)   ·   label W001:DEV1:J01",
        "W001-P2   ·   EX-MICROD-9-F   ·   female   ·   mates DEV2-J01 (DEV2:J01)   ·   label W001:DEV2:J01",
    ]  # fmt: skip
    by_end = {(r[2], r[3]): r for r in rows if len(r) > 3 and str(r[2]).startswith("W001-0")}
    assert len(by_end) == 8  # four wires, each at both ends
    near = by_end[("W001-001", "W001-P2.1 (DEV2:J01)")]
    assert near[4:] == [
        "EX-WIRE-TWISTED-SHIELDED", "to fill in", "to fill in", 1.2, "on the wire",
        "W001-001 TX+/RX+ to W001-P2.1", SHIELD_S1,
    ]  # fmt: skip
    far = by_end[("W001-001", "W001-P1.1 (DEV1:J01)")]
    assert far[9:] == ["W001-001 TX+/RX+ to W001-P1.1", SHIELD_S1]
    assert by_end[("W001-002", "W001-P2.3 (DEV2:J01)")][7:9] == [1.5, "locked"]
    assert ["5", None, "(spare)"] in rows  # the spare pin of each connector
    lines = [str(r[0]) for r in rows[-4:]]
    assert lines[0].startswith("Lengths run from the rear of a connector")
    assert "service_loop_m is not set" in lines[2]
    # Start here: the row Lengths under From the design; the guide names the sheet
    start = sheet_rows(wb["Start here"])
    at = next(i for i, r in enumerate(start) if r[0] == "Lengths")
    assert start[at][1] == lines[0] and [r[1] for r in start[at + 1 : at + 4]] == lines[1:]
    assert any(r[0] == "Production" for r in start)
    # Cut list: the length heading says what it is measured from
    cut = sheet_rows(wb["Cut list"])
    assert cut[0][5] == "Length (m), rear to rear"
    # the loose end: its heading and the far side of its wires
    loose = sheet_rows(
        openpyxl.load_workbook(outputs / "harnesses" / "W002" / "W002_build.xlsx")["Production"]
    )
    assert [
        "W002-P2   ·   TBD-CONNECTOR (loose end)   ·   open end, to fill in   ·   label W002:W002-P2 open end"
    ] in loose  # fmt: skip
    assert any(r[2:4] == ["W002-001", "W002-P2.1 (open end)"] for r in loose if len(r) > 3)

    # 5. labels.csv: HARNESS:DEVICE:NAME of the device connector
    labels = {}
    for hid in ("W001", "W002"):
        text = (outputs / "harnesses" / hid / "labels.csv").read_text(encoding="utf-8")
        body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
        labels.update({r["Label"]: r["Text"] for r in csv.DictReader(io.StringIO(body))})
    assert {k: v for k, v in labels.items() if "-P" in k and k.count("-") == 1} == {
        "W001-P1": "W001:DEV1:J01",
        "W001-P2": "W001:DEV2:J01",
        "W002-P1": "W002:DEV1:J02",
        "W002-P2": "W002:W002-P2 open end",
    }
    assert labels["W001-001-A"] == "W001-001 TX+/RX+ to W001-P2.1"  # a wire: the standard text

    # 6. the plan: the sheet Production with the same rows in mm, the print set-up, B4
    data = (outputs / "harnesses" / "W001" / "W001_plan.ods").read_bytes()
    sheets = read_plan(data)
    assert list(sheets)[2:5] == ["W001", "Production", "Notes"]
    assert check_values(sheets) == []
    plan = plan_rows(sheets["Production"])
    assert plan[0] == ["Production sheet of W001"]
    assert str(plan[1][0]).splitlines() == lines
    assert plan[2] == [*PRODUCTION_HEADER[:7], "Length [mm] rear to rear", *PRODUCTION_HEADER[8:11]]
    assert plan[3] == [headings[0]]
    assert plan[4] == [
        "1", "TX+/RX+", "W001-001", "W001-P2.1 (DEV2:J01)", "EX-WIRE-TWISTED-SHIELDED",
        "to fill in", "to fill in", 1200.0, "on the wire", "W001-001 TX+/RX+ to W001-P2.1",
        SHIELD_S1,
    ]  # fmt: skip
    printed = setups(data)
    assert (printed["W001"].fit, printed["W001"].heading) == (None, (5, 8))
    assert printed["W001"].scale is not None and printed["W001"].scale.endswith("%")
    assert (printed["Production"].fit, printed["Production"].scale) == (None, "100%")
    assert printed["Production"].heading == (0, 2)
    con = plan_rows(sheets["CON_DEV1-J01"])
    assert con[3] == ["Connector Name", "J01"]  # B4
    # the near block's header names the device connector by its name, through B4
    near_header = next(c for c in sheets["W001"].values() if "[W001:DEV1:J01]" in str(c.value))
    assert "'CON_DEV1-J01'.B4" in near_header.formula

    # 7. a second export: byte-identical
    first = files(outputs)
    ok(capsys, "export", proj, "--harness-plan")
    assert files(outputs) == first


def test_an_existing_example_keeps_the_standard_labels(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = tmp_path / "flatsat"
    ok(capsys, "new", proj, "--template", "flatsat")
    assert not (proj / "config" / "model.json").exists()
    ok(capsys, "export", proj)
    text = (proj / "outputs" / "harnesses" / "W001" / "labels.csv").read_text(encoding="utf-8")
    assert "W001-P1,connector,W001-P1 mates MTQ1-J01,1" in text.splitlines()
    assert "W001:MTQ1:J01" not in text
    wb = openpyxl.load_workbook(proj / "outputs" / "harnesses" / "W001" / "W001_build.xlsx")
    assert "Production" in wb.sheetnames  # every build workbook has the sheet
