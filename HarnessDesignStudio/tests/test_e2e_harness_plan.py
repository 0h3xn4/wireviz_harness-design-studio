# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The end-to-end case of the harness plan (REQ-OUT-01; D-242, section 11 of
`docs/ait/DESIGN_3.0_HARNESS_PLAN.md`, pull request 5), through the command line wherever a command
exists, and through the plans the editor runs (`History`) where none does (the tool has no command
that adds an interface, and the example colour code is taken in the editor's *Settings > Project >
Harness plan*, pull request 7).

A blank project; two devices DEV1 and DEV2 whose pinouts come in through `import-pinout` in the
users' words (the headings Pinout, Function, Direction, Level and Description of the template's
`CON_…` sheets, Pinout read through `--column pin=Pinout`, and the words `PWR-RET`, `SGND` and
`TEST`); one RS-422 interface; `generate`; the lengths and the gauges a person gives
(`import-lengths`, `override`); `document --set` and `document --harness W001 --set`; the example
colour code, copied by `templates` and taken on purpose, with its note in `check`;
`export --harness-plan`, one plan per harness; `verify --outputs` with 0 errors; the plan read by
the tests' own reader, every formula evaluated, the Cover, the colours and the Direction words; a
second export byte-identical; `release`, `new-version --kind minor`, `release` again, with the
register and `VERSION:` of the plan following; an export without the option removes the plans.

Example data only: `Example Ltd`, `plans@example.org`, an example reviewer."""

import csv
import json
from pathlib import Path

import pytest

from harness_design_studio.core import edit, templates
from harness_design_studio.core.commands import History, SetConfig
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import ConfigFile
from tests.plan_support import PlanCell, check_values, find, read_plan
from tests.test_e2e_rs422x3 import files, run

PLAN = "harnesses/W001/W001_plan.ods"
COMPANY = "Example Ltd"
MAIL = "plans@example.org"
WHO = ["--by", "Example Reviewer"]
ACCEPT = [
    "--accept-placeholders", "Example data for the test",
    "--accept-unapproved-parts", "Example data for the test",
]  # fmt: skip
# the template's CON_ sheet: Pinout, Function, Direction, Level, Description; a Mode column says
# that the device fixes each pin
DEV1 = (
    "Pinout,Function,Direction,Level,Description,Mode\n"
    "1,TX+,OUT,RS422-3V3,Telemetry out,fixed\n"
    "2,TX-,OUT,RS422-3V3,Telemetry out,fixed\n"
    "3,RX+,IN,RS422-3V3,Commands in,fixed\n"
    "4,RX-,IN,RS422-3V3,Commands in,fixed\n"
    "5,SGND,SGND,,Signal ground,fixed\n"
    "6,PWR_RTN,PWR-RET,18V,Supply return,fixed\n"
    "7,TEST1,TEST,,Factory test,fixed\n"
)
DEV2 = (
    "Pinout,Function,Direction,Level,Description,Mode\n"
    "1,RX+,IN,RS422-3V3,Telemetry in,fixed\n"
    "2,RX-,IN,RS422-3V3,Telemetry in,fixed\n"
    "3,TX+,OUT,RS422-3V3,Commands out,fixed\n"
    "4,TX-,OUT,RS422-3V3,Commands out,fixed\n"
    "5,SGND,SGND,,Signal ground,fixed\n"
)


def ok(capsys: pytest.CaptureFixture[str], *args: object) -> str:
    code, out = run(capsys, *(str(a) for a in args))
    assert code == 0, out
    return out


def values(cells: dict[tuple[int, int], PlanCell]) -> set[object]:
    return {c.value for c in cells.values()}


def take_the_example_code(folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`templates` copies the example; a person takes it for the harness's pigtail part, as the
    editor's button *Use the example colour code* does (one undo step)."""
    copied = tmp_path / "templates"
    ok(capsys, "templates", copied)
    with (copied / templates.EXAMPLE_COLOUR_CODE).open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["Pin", "Colour"] and len(rows) == 38
    p = load_project(folder).project
    part = p.harnesses["W001"].connectors[0].part_id
    code = templates.example_colour_code([part])
    assert code["pins"] == dict((pin, colour) for pin, colour in rows[1:])
    values_ = {"colour_rule": "pin_code", "colour_codes": [code]}
    History(p).execute(
        "Use the example colour code",
        [SetConfig(ConfigFile(name="harness_plan", placeholder=False, values=values_))],
    )
    save_project(p, folder)


def test_the_harness_plan_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    proj = tmp_path / "proj"
    # 1. a blank project
    ok(capsys, "new", proj, "--template", "blank")
    # 2. two devices with an imported pinout in the users' words
    said = {}
    for name, text, title in (("DEV1", DEV1, "Device one"), ("DEV2", DEV2, "Device two")):
        sheet = tmp_path / f"{name.lower()}.csv"
        sheet.write_text(text, encoding="utf-8", newline="\n")
        said[name] = ok(
            capsys, "import-pinout", proj, sheet, "--device", name, "--new-device", title,
            "--default-part", "EX-MICROD-9-M", "--column", "pin=Pinout",
        )  # fmt: skip
        assert f"{name}-J01: OK added" in said[name]
    assert "Converted, row 8 (DEV1-J01 pin 7): TEST Direction word = not set" in said["DEV1"]
    assert "Converted" not in said["DEV2"]
    p = load_project(proj).project
    dev1 = {pin.id: pin for pin in p.connectors["DEV1-J01"].pins}
    assert (dev1["5"].role, dev1["6"].role, dev1["7"].role, dev1["7"].direction) == (
        "signal_ground", "return", "", "",
    )  # fmt: skip
    assert (dev1["1"].direction, dev1["1"].level, dev1["1"].function) == (
        "out", "RS422-3V3", "Telemetry out",
    )  # fmt: skip
    # 3. an interface (no command adds one: the plan the editor runs)
    ops, iid = edit.ops_add_interface(p, "rs422", "DEV1", "DEV2")
    History(p).execute(f"Add {iid}", ops)
    save_project(p, proj)
    # 4. generate, and the lengths and gauges a person gives
    out = ok(capsys, "generate", proj)
    assert "1 added" in out
    lengths = tmp_path / "lengths.csv"
    lengths.write_text(
        "harness,segment,length\nW001,W001-L1,1200\n", encoding="utf-8", newline="\n"
    )
    ok(capsys, "import-lengths", proj, lengths)
    wires = [w.id for w in load_project(proj).project.harnesses["W001"].wires]
    for wid in wires:
        ok(capsys, "override", proj, wid, "gauge_awg", "24", "--reason", "Example gauge")
    ok(capsys, "generate", proj)

    # 5. the document data, for the project and for the plan of W001
    ok(
        capsys, "document", proj, "--set", "system=EX", "--set", f"company={COMPANY}",
        "--contact", f"E-mail={MAIL}", "--contact", "Phone=+00 0000 000000",
    )  # fmt: skip
    ok(capsys, "document", proj, "--harness", "W001", "--set", "number=HP-W001")
    # 6. the example colour code, taken on purpose; check notes it
    take_the_example_code(proj, tmp_path, capsys)
    code, out = run(capsys, "check", str(proj))
    assert code == 0, out
    assert "plan_colour_example" in out and "plan_colour_missing" not in out

    # 7. export with the plans: one per harness
    code, out = run(capsys, "export", str(proj), "--harness-plan", "--json")
    assert code == 0, out
    doc = json.loads(out)
    assert doc["harness_plans"] == [PLAN]
    # 8. the independent check: 0 errors
    out = ok(capsys, "verify", proj, "--outputs")
    assert "0 error(s)" in out
    data = (proj / "outputs" / PLAN).read_bytes()
    sheets = read_plan(data)
    assert list(sheets) == [
        "Cover", "Change_Register", "W001", "Production", "Notes", "CON_DEV1-J01", "CON_DEV2-J01",
        "About",
    ]  # fmt: skip
    assert check_values(sheets) == []  # every formula gives its stored value
    cover = sheets["Cover"]
    assert {COMPANY, MAIL, "HP-W001", "1.0.0", "+00 0000 000000"} <= values(cover)
    assert next(c.link for c in cover.values() if c.value == MAIL) == f"mailto:{MAIL}"
    head = sheets["W001"]
    assert "VERSION: v1.0.0 (draft)" in values(head) and "EX" in values(head)
    assert "IN" in values(head) and "OUT" in values(head)  # the mirrored Direction words
    looked_up = [c for c in head.values() if c.formula.startswith("IF(") and "VLOOKUP" in c.formula]
    assert looked_up and {c.value for c in looked_up} <= {"Black", "Brown", "Red", "Orange"}
    con = sheets["CON_DEV1-J01"]
    assert {"SGND", "PWR-RET", "RS422-3V3", "Factory test"} <= values(con)
    assert find(con, "TEST1") and not find(con, "TEST")  # TEST set no word
    assert any("Example colour code" in str(v) for v in values(sheets["Notes"]))

    # 9. a second export: byte-identical
    first = files(proj / "outputs")
    ok(capsys, "export", proj, "--harness-plan")
    assert files(proj / "outputs") == first

    # 10. release, a minor version, release again: the plan follows
    ok(capsys, "review", proj, "W001", *WHO, "--date", "2026-11-18")
    out = ok(
        capsys, "release", proj, "W001", *WHO, "--date", "2026-11-18", "--comment",
        "First build", *ACCEPT,
    )  # fmt: skip
    assert "Outputs re-exported with the released status" in out
    sheets = read_plan((proj / "outputs" / PLAN).read_bytes())
    assert "VERSION: v1.0.0 (released)" in values(sheets["W001"])
    ok(capsys, "verify", proj, "--outputs")
    ok(
        capsys, "new-version", proj, "W001", *WHO, "--date", "2026-11-19", "--comment",
        "Second build", "--kind", "minor",
    )  # fmt: skip
    ok(capsys, "export", proj, "--harness-plan")
    ok(capsys, "review", proj, "W001", *WHO, "--date", "2026-11-19")
    ok(
        capsys, "release", proj, "W001", *WHO, "--date", "2026-11-19", "--comment",
        "Second build released", *ACCEPT,
    )  # fmt: skip
    out = ok(capsys, "verify", proj, "--outputs")
    assert "0 error(s)" in out
    sheets = read_plan((proj / "outputs" / PLAN).read_bytes())
    assert "VERSION: v1.1.0 (released)" in values(sheets["W001"])
    assert check_values(sheets) == []
    register = sheets["Change_Register"]
    rows: dict[int, dict[int, object]] = {}
    for (r, c), cell in register.items():
        rows.setdefault(r, {})[c] = cell.value
    listed = [
        (row[1], row[3], str(row[6]).split(":")[0]) for r, row in sorted(rows.items()) if r >= 4
    ]
    assert listed == [
        ("1.0.0", "2026-11-18", "in review"),
        ("1.0.0", "2026-11-18", "released"),
        ("1.1.0", "2026-11-19", "new version"),
        ("1.1.0", "2026-11-19", "in review"),
        ("1.1.0", "2026-11-19", "released"),
    ]
    assert "1.1.0" in values(sheets["Cover"])  # the Cover's Version follows while it is empty

    # 11. an export without the option removes the plans
    out = ok(capsys, "export", proj)
    assert "The harness plans of the earlier export were removed" in out
    assert not (proj / "outputs" / PLAN).exists()
    assert (proj / "outputs" / "harnesses" / "W001" / "W001_build.xlsx").is_file()
    out = ok(capsys, "verify", proj, "--outputs")
    assert "0 error(s)" in out
