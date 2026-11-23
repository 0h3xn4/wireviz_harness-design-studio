# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index,union-attr,type-arg"
"""REQ-PIN-07: the row layout on the command line and in the imports (design of 4.0.0 sections
6 and 10; pull request 4).

`pin-rows` shows the rows of a part or a connector with where they come from and sets them
through the plans of `core/row_layout_edit.py` (one undo step, journaled; `--json` with the keys
of `SHAPES`, the record of the scripting interface); `import-pinout` reads the *Pin row* column into
a box connector's own rows, with the note of section 6.2, and a sheet without the column changes no
rows (the other tests of `tests/test_pinout_cli.py` and `tests/test_pinout_import.py` read sheets
without it, as before); the device library commands and the subsystem file carry the rows of the
parts and of the box connectors, and `update-device` shows a change of them in its diff;
`explain` of a connector names its rows and where they come from."""

import json
from pathlib import Path

import pytest

from harness_design_studio import api
from harness_design_studio.cli.jsonout import SHAPES
from harness_design_studio.cli.main import main
from harness_design_studio.cli.pin_rows_cmd import mutates
from harness_design_studio.core import device_library as dl
from harness_design_studio.core import subsystem_library as sl
from harness_design_studio.core.commands import apply_ops
from harness_design_studio.core.io.layout import model_hash
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.links import plan_add_link
from harness_design_studio.core.model import Project, RowLayout, evolve
from harness_design_studio.core.samples import mini3, new_project
from harness_design_studio.core.templates import create_project
from tests.helpers import pinout_project
from tests.test_library_cli import edit_file, files, make_library, make_project


def cli(capsys: pytest.CaptureFixture[str], *argv: object) -> tuple[int, str, str]:
    rc = main([str(a) for a in argv])
    got = capsys.readouterr()
    return rc, got.out, got.err


def doc(capsys: pytest.CaptureFixture[str], shape: str, *argv: object, rc: int = 0) -> dict:
    code, out, err = cli(capsys, *argv, "--json")
    assert code == rc, (argv, out, err)
    found = json.loads(out)
    assert list(found) == list(SHAPES[shape]), shape
    return found


def rows(*rows: list[str], rings: bool = False) -> RowLayout:
    return RowLayout(rows=[list(r) for r in rows], rings=rings)


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    """mini3: PCDU-J01 (part EX-MICROD-9-F, pins 1 to 3) and the plug W001-P1 of W001 on it."""
    folder = tmp_path / "p"
    save_project(mini3(), folder)
    return folder


# ---- pin-rows -------------------------------------------------------------------------------


def test_pin_rows_shows_and_sets_the_rows_of_a_part(proj: Path, capsys) -> None:
    rc, out, _ = cli(capsys, "pin-rows", proj, "--part", "EX-MICROD-9-F")
    assert rc == 0
    assert out == "Pin rows of part EX-MICROD-9-F: none (give them with --set or --lengths)\n"
    rc, out, _ = cli(capsys, "pin-rows", proj, "--part", "EX-MICROD-9-F", "--lengths", "5, 4")
    assert rc == 0
    assert out == (
        "Saved.\nPin rows of part EX-MICROD-9-F: 1–5 / 6–9\n  Row 1: 1–5\n  Row 2: 6–9\n"
    )
    part = load_project(proj).project.parts["EX-MICROD-9-F"]
    assert part.row_layout == rows(["1", "2", "3", "4", "5"], ["6", "7", "8", "9"])
    rc, out, _ = cli(capsys, "pin-rows", proj, "--part", "EX-MICROD-9-F", "--set", "1:5 / 6–9")
    assert rc == 0 and out.startswith("Already up to date.\n")
    rc, out, _ = cli(capsys, "pin-rows", proj, "--part", "EX-MICROD-9-F", "--rings")
    assert rc == 0 and "Pin rows of part EX-MICROD-9-F: 1–5 / 6–9 (rings)" in out
    assert load_project(proj).project.parts["EX-MICROD-9-F"].row_layout.rings
    rc, out, _ = cli(capsys, "pin-rows", proj, "--part", "EX-MICROD-9-F", "--clear")
    assert rc == 0 and out.startswith("Saved.\n")
    assert load_project(proj).project.parts["EX-MICROD-9-F"].row_layout is None


def test_pin_rows_of_a_device_connector_and_of_the_plug_on_it(proj: Path, capsys) -> None:
    assert cli(capsys, "pin-rows", proj, "--part", "EX-MICROD-9-F", "--set", "1–5 / 6–9")[0] == 0
    rc, out, _ = cli(capsys, "pin-rows", proj, "--connector", "PCDU-J01")
    assert rc == 0
    assert out == (
        "Pin rows of PCDU-J01: 1–3 (from part EX-MICROD-9-F)\n"
        "  Row 1: 1–3\n"
        "  Row 2: (none of its names is a pin of PCDU-J01)\n"
        "  Not pins of PCDU-J01: 4, 5, 6, 7, 8, 9 (left out of its rows; check warns)\n"
    )
    rc, out, _ = cli(capsys, "pin-rows", proj, "--connector", "PCDU-J01", "--set", "3 1")
    assert rc == 0
    assert out == (
        "Saved.\nPin rows of PCDU-J01: 3 1 (own rows)\n  Row 1: 3 1\n"
        "  In no row: 2 (listed after the rows)\n"
    )
    rc, out, _ = cli(capsys, "pin-rows", proj, "--connector", "W001-P1")
    assert rc == 0
    assert out == (
        "Pin rows of W001-P1: 3 1 (from PCDU-J01, the device connector it plugs into)\n"
        "  Row 1: 3 1\n"
        "  In no row: 2 (listed after the rows)\n"
        "  A connector of a harness has no rows of its own: set them on its part or on the "
        "device connector it plugs into.\n"
    )
    rc, out, _ = cli(capsys, "pin-rows", proj, "--connector", "PCDU-J01", "--lengths", "2,1")
    assert rc == 0 and "Pin rows of PCDU-J01: 1 2 / 3 (own rows)" in out
    rc, out, _ = cli(capsys, "pin-rows", proj, "--connector", "PCDU-J01", "--clear")
    assert rc == 0 and "Pin rows of PCDU-J01: 1–3 (from part EX-MICROD-9-F)" in out


def test_pin_rows_to_part_moves_the_rows_and_clears_the_equal_ones(proj: Path, capsys) -> None:
    for cid in ("PCDU-J01", "PCDU-J02"):
        assert cli(capsys, "pin-rows", proj, "--connector", cid, "--set", "1–3")[0] == 0
    rc, out, _ = cli(capsys, "pin-rows", proj, "--connector", "PCDU-J01", "--to-part")
    assert rc == 0 and "Pin rows of PCDU-J01: 1–3 (from part EX-MICROD-9-F)" in out
    p = load_project(proj).project
    assert p.parts["EX-MICROD-9-F"].row_layout == rows(["1", "2", "3"])
    assert p.connectors["PCDU-J01"].row_layout is None
    assert p.connectors["PCDU-J02"].row_layout is None
    # --set and --to-part in one step: the part has other rows now, so it is refused
    rc, _out, err = cli(capsys, "pin-rows", proj, "--connector", "OBC-J02", "--set", "3 2 1", "--to-part")  # fmt: skip
    assert rc == 2 and "Part EX-MICROD-9-F has other rows (1–3)" in err
    assert load_project(proj).project.connectors["OBC-J02"].row_layout is None


def test_pin_rows_set_and_to_part_are_one_undo_step(tmp_path: Path, capsys) -> None:
    p = mini3()
    p.parts["EX-MICROD-9-F"] = evolve(p.parts["EX-MICROD-9-F"], row_layout=None)
    folder = tmp_path / "p"
    save_project(p, folder)
    api.start_journal(folder, author="Example Ltd")
    rc, out, _ = cli(
        capsys, "pin-rows", folder, "--connector", "OBC-J02", "--set", "1 / 2 3", "--to-part"
    )
    assert rc == 0 and "Pin rows of OBC-J02: 1 / 2 3 (from part EX-MICROD-9-F)" in out
    q = load_project(folder).project
    assert q.parts["EX-MICROD-9-F"].row_layout == rows(["1"], ["2", "3"])
    assert q.connectors["OBC-J02"].row_layout is None
    entries = api.get_journal(folder, object_id="part:EX-MICROD-9-F").entries
    assert [e.field for e in entries] == ["row_layout"]


def test_pin_rows_json_is_the_record_of_the_scripting_interface(proj: Path, capsys) -> None:
    found = doc(capsys, "pin-rows", "pin-rows", proj, "--connector", "PCDU-J01")
    assert found == {"ok": True, "changed": False, **api.row_layout_of(proj, "PCDU-J01").to_dict()}
    assert found["source"] == "none"
    found = doc(
        capsys, "pin-rows", "pin-rows", proj, "--connector", "PCDU-J01", "--set", "1 2 / 3 (rings)"
    )
    assert found == {
        "ok": True, "changed": True, "object": "PCDU-J01", "kind": "connector",
        "rows": [["1", "2"], ["3"]], "rings": True, "source": "own", "source_id": "PCDU-J01",
        "text": "1 2 / 3 (rings)",
    }  # fmt: skip
    assert found == {"ok": True, "changed": True, **api.row_layout_of(proj, "PCDU-J01").to_dict()}
    found = doc(capsys, "pin-rows", "pin-rows", proj, "--part", "EX-MICROD-9-F")
    assert (found["kind"], found["source"], found["rows"]) == ("part", "none", [])


@pytest.mark.parametrize(
    ("argv", "message"),
    [(["--connector", "W001-P1", "--set", "1 2"], "W001-P1 is a connector of a harness"),
     (["--part", "EX-MICROD-9-F", "--set", "1 / 1"], "pin 1 is in row 1 and in row 2"),
     (["--part", "EX-MICROD-9-F", "--set", "1–10"], "the part has 9"),
     (["--part", "EX-MICROD-9-F", "--set", " "], "--set needs the rows"),
     (["--part", "EX-MICROD-9-F", "--set", "1 (rings)", "--no-rings"], "choose one"),
     (["--part", "EX-MICROD-9-F", "--lengths", "5,0"], "'0' is not a row length"),
     (["--part", "EX-MICROD-9-F", "--rings"], "has no rows of its own to mark"),
     (["--connector", "PCDU-J01", "--lengths", "2,2"], "the connector has 3"),
     (["--connector", "PCDU-J01", "--set", "4"], "pin"),
     (["--connector", "PCDU-J01", "--to-part"], "no rows of its own to give to its part"),
     (["--connector", "NOPE"], "'NOPE' is not a connector of the project"),
     (["--part", "NOPE", "--set", "1"], "Part 'NOPE' does not exist"),
     (["--part", "EX-WIRE-SINGLE"], "only a connector part has rows"),
     (["--part", "EX-MICROD-9-F", "--to-part"], "--to-part goes with --connector"),
     (["--connector", "PCDU-J01", "--clear", "--to-part"], "does not go with --clear"),
     (["--part", "EX-MICROD-9-F", "--clear", "--rings"], "do not go with --clear")],
)  # fmt: skip
def test_pin_rows_refuses_with_the_reason_and_writes_nothing(
    proj: Path, capsys, argv: list[str], message: str
) -> None:
    before = files(proj)
    rc, out, err = cli(capsys, "pin-rows", proj, *argv)
    assert rc == 2 and message in err and err.startswith("error: "), err
    assert out == "" and files(proj) == before
    assert main(["pin-rows", str(proj), *argv, "--json"]) == 2
    assert capsys.readouterr().out == ""  # nothing to print: the command did not run


def test_pin_rows_needs_a_part_or_a_connector_and_refuses_a_read_only_project(
    proj: Path, capsys
) -> None:
    assert cli(capsys, "pin-rows", proj)[0] == 2
    assert cli(capsys, "pin-rows", proj, "--part", "A", "--connector", "B")[0] == 2
    raw = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    raw["schema_version"] += 1  # saved by a newer tool: read-only
    (proj / "project.json").write_text(json.dumps(raw), encoding="utf-8")
    before = files(proj)
    rc, _out, err = cli(capsys, "pin-rows", proj, "--part", "EX-MICROD-9-F", "--set", "1–9")
    assert rc == 2 and "read-only" in err and files(proj) == before
    rc, out, _ = cli(capsys, "pin-rows", proj, "--part", "EX-MICROD-9-F")  # showing is allowed
    assert rc == 0 and "none" in out


def test_only_a_change_takes_the_project_lock() -> None:
    from harness_design_studio.cli.main import build_parser

    parse = build_parser().parse_args
    assert not mutates(parse(["pin-rows", "p", "--part", "X"]))
    for extra in (["--set", "1"], ["--lengths", "1"], ["--clear"], ["--rings"], ["--no-rings"]):
        assert mutates(parse(["pin-rows", "p", "--part", "X", *extra])), extra
    assert mutates(parse(["pin-rows", "p", "--connector", "X", "--to-part"]))


# ---- explain ----------------------------------------------------------------------------------


def test_explain_of_a_connector_names_its_rows_and_where_they_come_from(proj: Path, capsys) -> None:
    out = cli(capsys, "explain", proj, "PCDU-J01")[1]
    assert "Pin rows" not in out  # no layout: the explanation of 3.0.0
    assert cli(capsys, "pin-rows", proj, "--part", "EX-MICROD-9-F", "--lengths", "5,4")[0] == 0
    out = cli(capsys, "explain", proj, "PCDU-J01")[1]
    assert "    Pin rows = 1–3   [part EX-MICROD-9-F: row_layout (the rows of its part)]" in out
    out = cli(capsys, "explain", proj, "W001-P1")[1]
    assert (
        "    Pin rows = 1–3   [connector PCDU-J01: row_layout (the device connector it plugs "
        "into)]" in out
    )
    assert cli(capsys, "pin-rows", proj, "--connector", "PCDU-J01", "--set", "1 / 2 3")[0] == 0
    out = cli(capsys, "explain", proj, "PCDU-J01")[1]
    assert "    Pin rows = 1 / 2 3   [connector PCDU-J01: row_layout (its own rows)]" in out
    found = json.loads(cli(capsys, "explain", proj, "PCDU-J01", "--json")[1])
    inputs = [i for d in found for i in d["inputs"] if i["name"] == "Pin rows"]
    assert [(i["value"], i["source"]) for i in inputs] == [
        ("1 / 2 3", "connector PCDU-J01: row_layout (its own rows)")
    ]


# ---- import-pinout with Pin row (section 6.2) ---------------------------------------------------


def pinout(tmp_path: Path, text: str) -> Path:
    f = tmp_path / "rows.csv"
    f.write_text(text, encoding="utf-8")
    return f


def test_a_pin_row_column_gives_the_connector_its_own_rows_with_the_note(
    proj: Path, tmp_path: Path, capsys
) -> None:
    sheet = pinout(tmp_path, "Connector,Pin,Pin row\nOBC-J02,1,2\nOBC-J02,3,1\nOBC-J02,2,1\n")
    before = model_hash(load_project(proj).project)
    found = doc(capsys, "import-pinout", "import-pinout", proj, sheet, "--device", "OBC", "--dry-run")  # fmt: skip
    assert found["row_layouts"] == ["OBC-J02"] and not found["changed"]
    assert model_hash(load_project(proj).project) == before
    rc, out, _ = cli(capsys, "import-pinout", proj, sheet, "--device", "OBC")
    assert rc == 0
    note = (
        "note: The rows are stored on OBC-J02 only; to use them for every connector of part "
        "EX-MICROD-9-F, choose Use for every connector of this part in the Devices tab, or run "
        "`pin-rows --connector OBC-J02 --to-part`."
    )
    assert "Columns read: Connector -> connector, Pin -> pin, Pin row -> pin_row" in out
    assert "note: Row layouts set: OBC-J02." in out and note in out
    assert "OBC-J02: OK updated (3 pin(s))" in out
    p = load_project(proj).project
    assert p.connectors["OBC-J02"].row_layout == rows(["3", "2"], ["1"])
    assert p.parts["EX-MICROD-9-F"].row_layout is None
    record = p.import_records["pinout:rows.csv"]
    assert record.notes[:2] == ["Row layouts set: OBC-J02.", note.removeprefix("note: ")]
    # the same sheet again: the rows are the ones the connector has, so nothing changes
    rc, out, _ = cli(capsys, "import-pinout", proj, sheet, "--device", "OBC")
    assert rc == 0 and "Already up to date." in out and "Row layouts set" not in out


def test_the_order_inside_a_row_is_kept_and_the_rings_mark_too(
    proj: Path, tmp_path: Path, capsys
) -> None:
    rc = cli(capsys, "pin-rows", proj, "--connector", "OBC-J02", "--set", "3 2 1 (rings)")[0]
    assert rc == 0
    same = pinout(tmp_path, "Connector,Pin,Row\nOBC-J02,1,1\nOBC-J02,2,1\nOBC-J02,3,1\n")
    before = model_hash(load_project(proj).project)
    rc, out, _ = cli(capsys, "import-pinout", proj, same, "--device", "OBC")
    assert rc == 0 and "Already up to date." in out
    assert model_hash(load_project(proj).project) == before  # equal as sets: no change
    other = pinout(tmp_path, "Connector,Pin,Contact row\nOBC-J02,1,1\nOBC-J02,2,1\nOBC-J02,3,2\n")
    assert cli(capsys, "import-pinout", proj, other, "--device", "OBC")[0] == 0
    assert load_project(proj).project.connectors["OBC-J02"].row_layout == rows(
        ["1", "2"], ["3"], rings=True
    )


def test_a_gap_is_closed_up_and_an_empty_cell_is_in_no_row(
    proj: Path, tmp_path: Path, capsys
) -> None:
    sheet = pinout(tmp_path, "Connector,Pin,Pin row\nOBC-J02,1,1\nOBC-J02,2,\nOBC-J02,3,3\n")
    rc, out, _ = cli(capsys, "import-pinout", proj, sheet, "--device", "OBC")
    assert rc == 0
    assert (
        "note: OBC-J02: the Pin row column gives the rows 1, 3; they are stored as the rows 1 to "
        "2 (1 / 3)." in out
    )
    assert load_project(proj).project.connectors["OBC-J02"].row_layout == rows(["1"], ["3"])
    rc, out, _ = cli(capsys, "import-pinout", proj, sheet, "--device", "OBC")
    assert rc == 0 and "Already up to date." in out and "stored as" not in out


@pytest.mark.parametrize("cell", ["x", "0", "-1", "1.5", "²"])
def test_a_cell_that_is_no_row_refuses_the_sheet(proj: Path, tmp_path: Path, capsys, cell) -> None:
    sheet = pinout(tmp_path, f"Connector,Pin,Pin row\nOBC-J02,1,1\nOBC-J02,2,{cell}\n")
    before = files(proj)
    rc, out, _ = cli(capsys, "import-pinout", proj, sheet, "--device", "OBC")
    assert rc == 1 and "Nothing was changed." in out
    assert f"row 3: ERROR Pin row '{cell}' is not a whole number from 1 (the row of the pin)" in out
    assert files(proj) == before


def test_a_sheet_without_the_column_leaves_every_layout_as_it_is(
    proj: Path, tmp_path: Path, capsys
) -> None:
    assert cli(capsys, "pin-rows", proj, "--connector", "OBC-J02", "--set", "1 / 2 3")[0] == 0
    sheet = pinout(tmp_path, "Connector,Pin,Signal\nOBC-J02,1,A\nOBC-J02,2,B\nOBC-J02,3,C\n")
    found = doc(capsys, "import-pinout", "import-pinout", proj, sheet, "--device", "OBC")
    assert found["row_layouts"] == [] and found["changed"]
    p = load_project(proj).project
    assert p.connectors["OBC-J02"].row_layout == rows(["1"], ["2", "3"])
    assert [x.signal for x in p.connectors["OBC-J02"].pins] == ["A", "B", "C"]
    assert not p.import_records["pinout:rows.csv"].notes


def test_a_pinout_with_the_rows_of_the_part_reads_back_as_no_change(
    proj: Path, tmp_path: Path, capsys
) -> None:
    """The file `export-pinout` writes with the column (pull request 3) holds the rows each pin
    has; read back with `import-pinout`, it changes nothing, also where the rows are the part's."""
    assert cli(capsys, "pin-rows", proj, "--part", "EX-MICROD-9-F", "--lengths", "2,7")[0] == 0
    assert cli(capsys, "pin-rows", proj, "--connector", "OBC-J02", "--set", "3 / 1 2")[0] == 0
    p = load_project(proj).project
    sheet = tmp_path / "obc.csv"
    rc, out, _ = cli(capsys, "export-pinout", proj, "--device", "OBC", "--output", sheet)
    assert rc == 0, out
    header = sheet.read_text(encoding="utf-8").splitlines()
    heading = next(line for line in header if line.startswith("Connector,"))
    assert heading.split(",").count("Pin row") == 1  # the column the export writes, once
    before = model_hash(p)
    rc, out, _ = cli(capsys, "import-pinout", proj, sheet, "--device", "OBC")
    assert rc == 0 and "Row layouts set" not in out, out
    assert model_hash(load_project(proj).project) == before


# ---- the device library and the subsystem file (section 5.5) -------------------------------------


def with_rows(p: Project) -> Project:
    """RW1-J01 with own rows; its part EX-MICROD-9-M with rows of its own."""
    p.parts["EX-MICROD-9-M"] = evolve(
        p.parts["EX-MICROD-9-M"],
        row_layout=rows([str(n) for n in range(1, 6)], ["6", "7", "8", "9"]),
    )
    c = p.connectors["RW1-J01"]
    p.connectors["RW1-J01"] = evolve(c, row_layout=rows(["2", "1"], ["3"]))
    return p


def without_part(folder: Path, part: str) -> None:
    """The project without the part and the part it mates with (it has no connector of them), so
    that a device brings them from its file."""
    p = load_project(folder).project
    mate = p.parts[part].mates_with
    for pid in (part, mate):
        p.parts.pop(pid or "", None)
    save_project(p, folder)


def test_save_device_and_add_device_carry_the_rows(tmp_path: Path, capsys) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    src = make_project(tmp_path / "src", with_rows(pinout_project()))
    rc, out, _ = cli(capsys, "save-device", src, "RW1")
    assert rc == 0, out
    data = json.loads((lib / "RW1.device.json").read_text(encoding="utf-8"))
    assert data["version"] == dl.FORMAT4_VERSION == 3
    j01 = next(c for c in data["devices"][0]["connectors"] if c["id"] == "RW1-J01")
    assert j01["row_layout"] == {"rows": [["2", "1"], ["3"]]}
    part = next(x for x in data["parts"] if x["id"] == "EX-MICROD-9-M")
    assert part["row_layout"]["rows"][1] == ["6", "7", "8", "9"]
    dst = make_project(tmp_path / "dst", new_project())
    without_part(dst, "EX-MICROD-9-M")
    rc, out, _ = cli(capsys, "add-device", dst, "RW1")
    assert rc == 0, out
    q = load_project(dst).project
    assert q.connectors["RW1-J01"].row_layout == rows(["2", "1"], ["3"])
    assert (
        q.parts["EX-MICROD-9-M"].row_layout
        == with_rows(pinout_project()).parts["EX-MICROD-9-M"].row_layout
    )
    assert api.row_layout_of(dst, "RW1-J02").source == "none"  # a part without rows
    rc, out, _ = cli(capsys, "update-device", dst, "--check")
    assert rc == 0 and "up to date" in out


def test_update_device_shows_a_change_of_the_rows_in_its_diff(tmp_path: Path, capsys) -> None:
    lib = make_library(tmp_path / "lib", units=("RW1",), source=with_rows(pinout_project()))
    proj = make_project(tmp_path / "proj", new_project())
    assert cli(capsys, "add-device", proj, "RW1")[0] == 0

    def change(data: dict) -> None:
        j01 = next(c for c in data["devices"][0]["connectors"] if c["id"] == "RW1-J01")
        j01["row_layout"] = {"rows": [["1", "2", "3"]]}

    edit_file(lib / "RW1.device.json", change)
    before = files(proj)
    found = doc(capsys, "update-device", "update-device", proj, "--check", rc=1)
    rw1 = next(d for d in found["devices"] if d["device"] == "RW1")
    assert rw1["rows"] == [
        {"device": "RW1", "connector": "RW1-J01", "pin": "", "field": "row_layout",
         "here": "2 1 / 3", "library": "1–3", "locked_by": ""},
    ]  # fmt: skip
    assert files(proj) == before
    rc, out, _ = cli(capsys, "update-device", proj, "RW1", "--apply")
    assert rc == 0, out
    assert load_project(proj).project.connectors["RW1-J01"].row_layout == rows(["1", "2", "3"])


def test_export_devices_and_import_devices_carry_the_rows(tmp_path: Path, capsys) -> None:
    src = tmp_path / "src"
    save_project(with_rows(pinout_project()), src)
    dst = tmp_path / "dst"
    create_project(dst, "blank")
    without_part(dst, "EX-MICROD-9-M")
    lib = tmp_path / "lib.json"
    assert cli(capsys, "export-devices", src, lib, "--device", "RW1")[0] == 0
    assert json.loads(lib.read_text(encoding="utf-8"))["version"] == 3
    assert cli(capsys, "import-devices", dst, lib)[0] == 0
    q = load_project(dst).project
    assert q.connectors["RW1-J01"].row_layout == rows(["2", "1"], ["3"])
    assert q.parts["EX-MICROD-9-M"].row_layout is not None
    # OBC's part EX-MICROD-9-F mates with the part with rows, so its file carries it: version 3
    obc = tmp_path / "obc.json"
    assert cli(capsys, "export-devices", src, obc, "--device", "OBC")[0] == 0
    assert json.loads(obc.read_text(encoding="utf-8"))["version"] == 3
    # a device without rows is written as before (a format 3 field or none: version 2 or 1)
    save_project(pinout_project(), tmp_path / "plain")
    plain = tmp_path / "plain.json"
    assert cli(capsys, "export-devices", tmp_path / "plain", plain, "--device", "RW1")[0] == 0
    assert json.loads(plain.read_text(encoding="utf-8"))["version"] < 3


def test_the_subsystem_file_carries_the_rows(tmp_path: Path, capsys) -> None:
    p = with_rows(pinout_project())
    ops, _ = plan_add_link(p, "OBC-J01", "RW1-J02")
    apply_ops(p, ops)
    src, dst, lib = tmp_path / "src", tmp_path / "dst", tmp_path / "wheel.json"
    save_project(p, src)
    create_project(dst, "blank")
    without_part(dst, "EX-MICROD-9-M")
    argv = ["export-subsystem", src, lib, "--device", "OBC", "--device", "RW1", "--name", "Wheel"]
    assert cli(capsys, *argv)[0] == 0
    data = json.loads(lib.read_text(encoding="utf-8"))
    assert data["version"] == sl.FORMAT4_VERSION == 2
    assert cli(capsys, "import-subsystem", dst, lib)[0] == 0
    q = load_project(dst).project
    assert q.connectors["RW1-J01"].row_layout == rows(["2", "1"], ["3"])
    assert q.parts["EX-MICROD-9-M"].row_layout == p.parts["EX-MICROD-9-M"].row_layout
    save_project(pinout_project(), tmp_path / "plain")
    plain = tmp_path / "plain.json"
    argv = ["export-subsystem", tmp_path / "plain", plain, "--device", "RW1", "--name", "Wheel"]
    assert cli(capsys, *argv)[0] == 0
    assert json.loads(plain.read_text(encoding="utf-8"))["version"] == 1
