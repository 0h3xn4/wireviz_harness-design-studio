# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The imports of the harness plan (REQ-PIN-01; D-242, pull request 5 of `docs/ait/DESIGN_3.0_HARNESS_PLAN.md`,
sections 4.1 to 4.3 and 10): `import-pinout` with the users' headings (Pinout through
`--column pin=Pinout`, Function, Direction, Level, Description), their Direction words (`PWR`,
`PWR-RET`, `GND`, `SGND`, `SHIELD`, `SPARE`, `IN`, `OUT`, `IN/OUT`, and `TEST`, which sets nothing
and is recorded) and the source columns; `import-parts` with *Link*; the round trip of
`export-pinout` with *Level*, *Source*, *Source version* and *Source link*. Example data only."""

import json
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.cli.main import main
from harness_design_studio.core import devices
from harness_design_studio.core.commands import Put
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.io.layout import model_hash
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import Connector
from harness_design_studio.core.outputs.tables import box_pinouts
from harness_design_studio.core.pinout_import import guess_mapping

LINK = "https://example.org/icd/dev1"
# a sheet in the users' words: the template's CON_ sheet (Pinout, Function, Direction, Level,
# Description) with the source of the pinout on its rows
USERS = (
    "Pinout,Function,Direction,Level,Description,Source,Source version,Source link\n"
    f"1,PWR_18V,PWR,18V,Main supply,ICD-DEV1,1.2,{LINK}\n"
    "2,PWR_18V_RTN,PWR-RET,18V,Main supply return,,,\n"
    "3,TX+,OUT,RS422-3V3,Telemetry,,,\n"
    "4,RX+,IN,RS422-3V3,Commands,,,\n"
    "5,CLK,IN/OUT,TTL-5V,Clock,,,\n"
    "6,SGND,SGND,,Signal ground,,,\n"
    "7,CHASSIS,GND,,Chassis,,,\n"
    "8,DRAIN,SHIELD,,Shield drain,,,\n"
    "9,TEST1,TEST,,Factory test,,,\n"
    "10,,SPARE,,,,,\n"
)
PART = "EX-MICROD-15-M"


def run(capsys: pytest.CaptureFixture[str], *args: object, rc: int = 0) -> str:
    code = main([str(a) for a in args])
    seen = capsys.readouterr()
    assert code == rc, seen.out + seen.err
    return seen.out + seen.err


def as_json(capsys: pytest.CaptureFixture[str], *args: object, rc: int = 0) -> dict[str, Any]:
    code = main([*(str(a) for a in args), "--json"])
    seen = capsys.readouterr()
    assert code == rc, seen.out + seen.err
    doc: dict[str, Any] = json.loads(seen.out)
    return doc


@pytest.fixture
def blank(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    folder = tmp_path / "p"
    run(capsys, "new", folder, "--template", "blank")
    assert PART in load_project(folder).project.parts
    return folder


def sheet(tmp_path: Path, text: str, name: str = "dev1.csv") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def import_users(
    capsys: pytest.CaptureFixture[str], folder: Path, path: Path, *extra: str, rc: int = 0
) -> str:
    return run(
        capsys, "import-pinout", folder, path, "--device", "DEV1", "--new-device", "Device one",
        "--default-part", PART, "--column", "pin=Pinout", *extra, rc=rc,
    )  # fmt: skip


def pins(folder: Path) -> dict[str, tuple[str, str, str, str, str]]:
    """pin -> (signal, function, role, direction, level) of DEV1-J01."""
    c = load_project(folder).project.connectors["DEV1-J01"]
    return {
        p.id: (p.signal or "", p.function or "", p.role, p.direction, p.level or "") for p in c.pins
    }


def test_the_users_headings_and_words(
    blank: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = sheet(tmp_path, USERS)
    text = import_users(capsys, blank, path)
    assert "Columns read: Pinout -> pin, Function -> signal, Direction -> direction" in text
    assert "Level -> level, Description -> function, Source -> source_doc" in text
    assert "DEV1-J01: OK added (10 pin(s))" in text
    assert "Row 10: the Direction word 'TEST' is not one the tool reads" in text
    assert "Converted, row 10 (DEV1-J01 pin 9): TEST Direction word = not set" in text
    assert "Description" not in text.split("Columns read:")[0]  # no longer an unstored column
    assert pins(blank) == {
        "1": ("PWR_18V", "Main supply", "power", "", "18V"),
        "2": ("PWR_18V_RTN", "Main supply return", "return", "", "18V"),
        "3": ("TX+", "Telemetry", "", "out", "RS422-3V3"),
        "4": ("RX+", "Commands", "", "in", "RS422-3V3"),
        "5": ("CLK", "Clock", "", "bidir", "TTL-5V"),
        "6": ("SGND", "Signal ground", "signal_ground", "", ""),
        "7": ("CHASSIS", "Chassis", "ground", "", ""),
        "8": ("DRAIN", "Shield drain", "shield", "", ""),
        "9": ("TEST1", "Factory test", "", "", ""),  # TEST: neither role nor direction
        "10": ("", "", "spare", "", ""),
    }
    c = load_project(blank).project.connectors["DEV1-J01"]
    assert (c.source_doc, c.source_version, c.source_link) == ("ICD-DEV1", "1.2", LINK)
    record = json.loads((blank / "imports" / "records.json").read_text(encoding="utf-8"))
    entry = next(r for r in record["imports"] if r["id"] == "pinout:dev1.csv")
    assert entry["converted_count"] == 1
    assert entry["rows_converted"] == [
        {
            "row": 10, "field": "direction", "read": "TEST", "unit": "Direction word",
            "stored": "not set", "item": "DEV1-J01 pin 9",
        }
    ]  # fmt: skip


def test_without_the_column_option_the_pinout_heading_is_not_a_pin(
    blank: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = sheet(tmp_path, USERS)
    text = run(
        capsys, "import-pinout", blank, path, "--device", "DEV1", "--new-device", "Device one",
        "--default-part", PART, rc=2,
    )  # fmt: skip
    assert "needs a Pin column" in text


def test_the_json_document_carries_the_record_and_the_same_again_changes_nothing(
    blank: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = sheet(tmp_path, USERS)
    doc = as_json(
        capsys, "import-pinout", blank, path, "--device", "DEV1", "--new-device", "Device one",
        "--default-part", PART, "--column", "pin=Pinout",
    )  # fmt: skip
    assert doc["changed"] is True and doc["pins"] == 10
    assert doc["import"]["rows_converted"][0]["read"] == "TEST"
    assert any("TEST" in w for w in doc["warnings"])
    before = model_hash(load_project(blank).project)
    text = import_users(capsys, blank, path)
    assert "Already up to date." in text
    assert model_hash(load_project(blank).project) == before


def test_a_role_word_keeps_the_direction_and_a_direction_word_keeps_the_role(
    blank: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import_users(capsys, blank, sheet(tmp_path, USERS))
    again = USERS.replace("1,PWR_18V,PWR,", "1,PWR_18V,IN,").replace("3,TX+,OUT,", "3,TX+,SGND,")
    import_users(capsys, blank, sheet(tmp_path, again, "again.csv"))
    got = pins(blank)
    assert got["1"][2:4] == ("power", "in")  # IN: the direction; the role stays
    assert got["3"][2:4] == ("signal_ground", "out")  # SGND: the role; the direction stays


@pytest.mark.parametrize(
    ("change", "said"),
    [
        (("2,PWR_18V_RTN,PWR-RET,18V,Main supply return,,,", "2,PWR_18V_RTN,PWR-RET,18V,Main supply return,ICD-DEV9,,"), "Source 'ICD-DEV9' differs from 'ICD-DEV1' in row 2"),
        ((f"1.2,{LINK}", "1.2,file:///share/icd.pdf"), "The source link must be a web link"),
        (("Main supply,", "x" * 201 + ","), "A function can have 1 to 200 characters"),
        (("RS422-3V3,Telemetry", "x" * 201 + ",Telemetry"), "A level can have 1 to 200 characters"),
    ],
)  # fmt: skip
def test_a_bad_value_refuses_the_whole_sheet(
    blank: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    change: tuple[str, str],
    said: str,
) -> None:
    text = USERS.replace(*change, 1)
    assert text != USERS
    out = import_users(capsys, blank, sheet(tmp_path, text), rc=1)
    assert said in out and "Nothing was changed." in out
    assert "DEV1" not in load_project(blank).project.units


def test_a_source_column_left_empty_clears_the_source(
    blank: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import_users(capsys, blank, sheet(tmp_path, USERS))
    empty = USERS.replace(f"ICD-DEV1,1.2,{LINK}", ",,")
    import_users(capsys, blank, sheet(tmp_path, empty, "empty.csv"))
    c = load_project(blank).project.connectors["DEV1-J01"]
    assert (c.source_doc, c.source_version, c.source_link) == (None, None, None)
    # a sheet without the columns leaves the source as it is
    import_users(capsys, blank, sheet(tmp_path, USERS, "again.csv"))
    plain = "Pinout,Function\n1,PWR_18V\n"
    import_users(capsys, blank, sheet(tmp_path, plain, "plain.csv"))
    assert load_project(blank).project.connectors["DEV1-J01"].source_doc == "ICD-DEV1"


def test_the_planner_reads_the_aliases() -> None:
    header = ["Pin", "Signal", "ICD", "ICD version", "ICD link", "Signal level", "Description"]
    m = guess_mapping(header)
    assert (m["source_doc"], m["source_version"], m["source_link"], m["level"]) == (2, 3, 4, 5)
    assert m["function"] == 6
    # with Function and Description, Function is the signal and Description the function
    m = guess_mapping(["Pin", "Function", "Description"])
    assert (m["signal"], m["function"]) == (1, 2)
    # with Signal and Function, Description is not read
    m = guess_mapping(["Pin", "Signal", "Function", "Description"])
    assert (m["signal"], m["function"]) == (1, 2) and 3 not in m.values()


def test_the_editor_ops_take_the_new_fields() -> None:
    from tests.test_edit_device import with_connector

    p, cid = with_connector()
    pin = p.connectors[cid].pins[0].id
    ops = devices.ops_set_pin(p, cid, pin, level="RS422-3V3", role="signal_ground")
    put = ops[0]
    assert isinstance(put, Put) and isinstance(put.obj, Connector)
    new = put.obj.pins[0]
    assert (new.level, new.role) == ("RS422-3V3", "signal_ground")
    put = devices.ops_update_connector(p, cid, source_doc="ICD", source_link=LINK)[0]
    assert isinstance(put, Put) and isinstance(put.obj, Connector)
    assert (put.obj.source_doc, put.obj.source_link) == ("ICD", LINK)
    with pytest.raises(EditError, match="web link"):
        devices.ops_update_connector(p, cid, source_link="file:///x")
    assert devices.read_direction_word(" pwr-ret ") == ("role", "return")
    assert devices.read_direction_word("in/out") == ("direction", "bidir")
    assert devices.read_direction_word("") == ("direction", "")
    assert devices.read_direction_word("TEST") is None


# ---- export-pinout -------------------------------------------------------------------------------


def test_export_pinout_writes_the_new_columns_and_reads_them_back(
    blank: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import_users(capsys, blank, sheet(tmp_path, USERS))
    before = model_hash(load_project(blank).project)
    out = tmp_path / "back.csv"
    run(capsys, "export-pinout", blank, "--device", "DEV1", "-o", out)
    text = out.read_text(encoding="utf-8")
    head = text.splitlines()[2]
    assert head.endswith(",Level,Source,Source version,Source link")
    assert f"DEV1-J01,box,,{PART},1,PWR_18V,,,no,Main supply," in text
    assert f",18V,ICD-DEV1,1.2,{LINK}" in text
    doc = as_json(capsys, "export-pinout", blank, "--device", "DEV1")
    assert doc["columns"][-4:] == ["Level", "Source", "Source version", "Source link"]
    assert doc["rows"][0]["Level"] == "18V" and doc["rows"][3]["Source"] == "ICD-DEV1"
    # read back: the same pinout, nothing changes
    text = run(capsys, "import-pinout", blank, out, "--device", "DEV1", "--replace")
    assert "DEV1-J01: OK unchanged (10 pin(s))" in text and "Already up to date." in text
    assert model_hash(load_project(blank).project) == before
    for xlsx in (tmp_path / "back.xlsx",):
        run(capsys, "export-pinout", blank, "--device", "DEV1", "-o", xlsx)
        text = run(capsys, "import-pinout", blank, xlsx, "--device", "DEV1", "--replace")
        assert "Already up to date." in text
    assert model_hash(load_project(blank).project) == before


def test_export_pinout_without_the_new_fields_is_as_before(
    blank: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plain = "Pinout,Function,Direction\n1,TX+,OUT\n2,RX+,IN\n"
    import_users(capsys, blank, sheet(tmp_path, plain))
    p = load_project(blank).project
    assert devices.pinout_sheet(p, "DEV1") == devices.pinout_table(p, "DEV1")
    assert devices.pinout_table(p, "DEV1") == box_pinouts(p, {"DEV1-J01"})


# ---- import-parts --------------------------------------------------------------------------------


def test_import_parts_reads_a_link(
    blank: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = sheet(
        tmp_path,
        "IPN,Category,Status,Link\n"
        "EX-PIG-15,connector,A,https://example.org/parts/ex-pig-15\n"
        "EX-PIG-25,connector,A,\n",
        "parts.csv",
    )
    run(capsys, "import-parts", blank, f, "--approved", "A")
    parts = load_project(blank).project.parts
    assert parts["EX-PIG-15"].link == "https://example.org/parts/ex-pig-15"
    assert parts["EX-PIG-25"].link is None
    g = sheet(tmp_path, "IPN,Category,Status,URL\nEX-PIG-25,connector,A,http://example.org/p\n", "u.csv")  # fmt: skip
    doc = as_json(capsys, "import-parts", blank, g, "--approved", "A")
    assert doc["changed"] is True
    assert load_project(blank).project.parts["EX-PIG-25"].link == "http://example.org/p"
    bad = sheet(tmp_path, "IPN,Category,Status,Link\nEX-PIG-9,connector,A,file:///share/p.pdf\n", "b.csv")  # fmt: skip
    doc = as_json(capsys, "import-parts", blank, bad, "--approved", "A", rc=1)
    assert doc["problems"] == 1 and doc["changed"] is False
    assert doc["rows"][0]["message"].startswith("Link: must be a web link")
    assert "EX-PIG-9" not in load_project(blank).project.parts
