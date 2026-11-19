# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index,union-attr"
"""REQ-OUT-12: the written outputs of a connector with a row layout (format 4; design of 4.0.0
section 7, pull request 3).

The column *Pin row* of `system/box_pinouts.csv`, of the pinout table of a harness and of
`export-pinout`; the harness plan's column F of a `CON_…` sheet, the order of a near block (row by
row, then the pins in no row) and its column A; `row_layout` in `system/export.json`; each checked
again by the independent verifiers with their own reading of the rows (`verify_plan.face_rows`),
which find a wrong row, a missing or an extra column and a wrong order; the golden set; and the
outputs of a project without a layout, which keep their bytes. (`import-pinout` reading the column
back is pull request 4.)"""

import csv
import dataclasses
import io
import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness_design_studio.cli.main import main as cli_main
from harness_design_studio.core import devices
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import RowLayout, evolve
from harness_design_studio.core.outputs import harness_plan as hp
from harness_design_studio.core.outputs import tables
from harness_design_studio.core.outputs import verify_plan as vp
from harness_design_studio.core.outputs.build import build_outputs
from harness_design_studio.core.outputs.stamp import stamp_of
from harness_design_studio.core.outputs.verify import verify_outputs
from harness_design_studio.core.row_layout import layout_of, parse_text
from harness_design_studio.core.samples import mini3
from tests.helpers import FIXTURES, output_digests
from tests.plan_support import address, check_values, find, read_plan
from tests.row_layout_support import OWN, PART, golden_text_files, row_layout_project
from tests.static_scan import imported_names

SRC = Path(__file__).resolve().parents[1] / "src"
GOLDEN = FIXTURES / "outputs"


@pytest.fixture(scope="module")
def faced():
    p = row_layout_project()
    return p, dict(build_outputs(p, harness_plan=True).files)


def rows(files, rel):
    lines = files[rel].decode().splitlines()
    return [r for r in csv.reader(lines) if r and not r[0].startswith("#")]


def errors(p, files):
    return [(e.code, e.message) for e in verify_outputs(p, files).issues if e.severity == "error"]


def pin_rows(table):
    """(connector, pin) -> the Pin row cell of a pinout table."""
    at = table[0].index("Pin row")
    return {(r[0], r[4]): r[at] for r in table[1:]}


def edit_csv(files, rel, fn):
    """The set with one CSV file changed row by row (its two stamp lines kept)."""
    lines = files[rel].decode().splitlines(keepends=True)
    head = "".join(x for x in lines if x.startswith("#"))
    body = [r for r in csv.reader(x for x in lines if not x.startswith("#"))]
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(fn(body))
    return {**files, rel: (head + out.getvalue()).encode()}


def plan_of(p, hid):
    return hp.plan_ods(p, p.harnesses[hid], stamp_of(p))


def near_block(cells, box):
    """The 0-based rows of the near block of `box`: from the row under its heading row."""
    (head,) = [r for r, c in find(cells, "Pin No.") if c == hp.COL_B]
    out, r = [], head + 1
    while (r, hp.COL_B) in cells:
        out.append(r)
        r += 1
    assert cells[(head - 5, hp.COL_B)].value == box
    return head, out


# ---- the pinout tables ---------------------------------------------------------------------------


def test_the_box_pinouts_have_the_pin_row_of_each_pin_last(faced):
    _p, files = faced
    table = rows(files, "system/box_pinouts.csv")
    assert table[0][-1] == "Pin row"
    got = pin_rows(table)
    # the part's rows 1 3 / 2 on every box connector of EX-MICROD-9-F
    for cid in ("OBC-J02", "PCDU-J01", "PCDU-J02"):
        assert [got[cid, pin] for pin in ("1", "2", "3")] == ["1", "2", "1"]
    # the own rows 5 4 / 1 of RW1-J02: pins 2 and 3 in no row
    assert [got[OWN, pin] for pin in "12345"] == ["2", "", "", "1", "1"]
    # a connector without a layout: empty cells; the rows stay in pin order
    assert {got["OBC-J01", pin] for pin in "12345"} == {""}
    assert [r[4] for r in table[1:] if r[0] == OWN] == ["1", "2", "3", "4", "5"]


def test_a_harness_pinout_takes_the_part_s_rows_else_the_mated_box_connector_s(faced):
    _p, files = faced
    w1 = pin_rows(rows(files, "harnesses/W001/pinouts.csv"))
    assert [w1["W001-P2", pin] for pin in "123"] == ["1", "2", "1"]  # its part EX-MICROD-9-F
    assert [w1["W001-P1", pin] for pin in "123"] == ["1", "2", "1"]  # PCDU-J01, it plugs into
    w2 = pin_rows(rows(files, "harnesses/W002/pinouts.csv"))
    assert [w2["W002-P2", pin] for pin in "12345"] == ["2", "", "", "1", "1"]
    assert {w2["W002-P1", pin] for pin in "12345"} == {""}
    xlsx_sheet = files["harnesses/W001/W001.xlsx"]
    assert xlsx_sheet[:2] == b"PK"  # the Pinouts sheet is the same table (out_xlsx below)


def test_the_column_is_there_only_with_a_layout():
    p = mini3()
    from harness_design_studio.core.generate.engine import generate_project

    generate_project(p)
    plain = build_outputs(p).files
    for rel in ("system/box_pinouts.csv", "harnesses/W001/pinouts.csv"):
        assert "Pin row" not in rows(plain, rel)[0]
    # a layout on one box connector: box_pinouts gets the column, the harness that plugs into it
    # too, the other harness not
    p.connectors[OWN] = evolve(p.connectors[OWN], row_layout=parse_text("5 4 / 1"))
    files = build_outputs(p).files
    assert rows(files, "system/box_pinouts.csv")[0][-1] == "Pin row"
    assert rows(files, "harnesses/W002/pinouts.csv")[0][-1] == "Pin row"
    assert "Pin row" not in rows(files, "harnesses/W001/pinouts.csv")[0]
    assert rows(files, "harnesses/W001/pinouts.csv") == rows(plain, "harnesses/W001/pinouts.csv")
    assert errors(p, dict(files)) == []


def test_the_column_comes_after_the_other_sparse_columns():
    p = row_layout_project()
    c = p.connectors[OWN]
    p.connectors[OWN] = evolve(c, pins=[evolve(c.pins[0], function="Telemetry"), *c.pins[1:]])
    table = tables.box_pinouts(p)
    assert table[0][-2:] == ["Function", "Pin row"]
    assert errors(p, dict(build_outputs(p).files)) == []


# ---- export-pinout --------------------------------------------------------------------------------


def test_export_pinout_writes_the_column_while_a_connector_of_the_device_has_a_layout(
    tmp_path, capsys
):
    p = row_layout_project()
    assert devices.pinout_sheet(p, "RW1")[0][-1] == "Pin row"
    assert pin_rows(devices.pinout_sheet(p, "RW1"))[OWN, "5"] == "1"
    save_project(p, tmp_path / "p")
    assert cli_main(["export-pinout", str(tmp_path / "p"), "--device", "RW1"]) == 0
    out = capsys.readouterr().out
    assert "Connector,Role,Mates with,Part,Pin,Signal,Interface,Wires,Spare,Pin row" in out
    assert "RW1-J02,box,,EX-MICROD-15-M,5,,,,yes,1" in out
    assert "RW1-J01,box,,EX-MICROD-9-M,1,PWR,IF-PWR-RW1,W001-001,no,\n" in out


def test_export_pinout_of_a_device_without_a_layout_writes_the_file_of_3_0_0():
    p = row_layout_project()
    p.connectors[OWN] = evolve(p.connectors[OWN], row_layout=None)
    # RW1 has no layout now; the box pinouts still have the column (the part's rows elsewhere)
    assert devices.pinout_table(p, "RW1")[0][-1] == "Pin row"
    sheet = devices.pinout_sheet(p, "RW1")
    assert "Pin row" not in sheet[0]
    plain = mini3()
    from harness_design_studio.core.generate.engine import generate_project

    generate_project(plain)
    assert sheet == devices.pinout_sheet(plain, "RW1")


def test_export_pinout_puts_level_and_source_after_the_pin_row():
    p = row_layout_project()
    c = p.connectors[OWN]
    p.connectors[OWN] = evolve(
        c, source_doc="ICD-RW1", pins=[evolve(c.pins[0], level="5V"), *c.pins[1:]]
    )
    head = devices.pinout_sheet(p, "RW1")[0]
    assert head[head.index("Pin row") :] == ["Pin row", "Level", "Source"]


# ---- the harness plan -----------------------------------------------------------------------------


def test_the_con_sheet_has_the_pin_row_in_f_only_with_a_layout(faced):
    p, _files = faced
    s = read_plan(plan_of(p, "W001"))
    con = s["CON_PCDU-J01"]
    assert con[(17, hp.COL_F)].value == "Pin row"
    assert [con[(18 + n, hp.COL_F)].value for n in range(3)] == [1, 2, 1]
    assert (17, hp.COL_F) not in s["CON_RW1-J01"]  # no layout: no column
    own = read_plan(plan_of(p, "W002"))["CON_RW1-J02"]
    got = [own.get((18 + n, hp.COL_F)) for n in range(5)]
    assert [None if c is None else c.value for c in got] == [2, "", "", 1, 1]


def test_the_near_block_lists_the_pins_row_by_row_with_the_pin_row_in_a(faced):
    p, _files = faced
    s = read_plan(plan_of(p, "W001"))
    cells = s["W001"]
    head, block = near_block(cells, "PCDU-J01")
    assert cells[(head, hp.COL_A)].value == "Pin row"
    assert [cells[(r, hp.COL_B)].value for r in block] == [1, 3, 2]  # 1 3 / 2
    assert [cells[(r, hp.COL_A)].value for r in block] == [1, 1, 2]
    assert [cells[(r, hp.COL_A)].formula for r in block] == [
        "[$'CON_PCDU-J01'.F19]",
        "[$'CON_PCDU-J01'.F21]",
        "[$'CON_PCDU-J01'.F20]",
    ]
    assert check_values(s) == []


def test_pins_in_no_row_follow_the_rows_in_pin_order_with_an_empty_a():
    p = row_layout_project()
    p.connectors["PCDU-J01"] = evolve(p.connectors["PCDU-J01"], row_layout=parse_text("3 / 1"))
    s = read_plan(plan_of(p, "W001"))
    cells = s["W001"]
    _head, block = near_block(cells, "PCDU-J01")
    assert [cells[(r, hp.COL_B)].value for r in block] == [3, 1, 2]
    assert [cells.get((r, hp.COL_A)) and cells[(r, hp.COL_A)].value for r in block] == [1, 2, None]
    assert check_values(s) == []
    assert errors(p, dict(build_outputs(p, harness_plan=True).files)) == []


def test_a_plan_without_a_layout_has_no_pin_row():
    p = mini3()
    from harness_design_studio.core.generate.engine import generate_project

    generate_project(p)
    for hid in p.harnesses:
        s = read_plan(plan_of(p, hid))
        assert not any(find(cells, "Pin row") for cells in s.values())


# ---- export.json --------------------------------------------------------------------------------


def test_export_json_carries_the_rows_where_they_are_set(faced):
    _p, files = faced
    doc = json.loads(files["system/export.json"])
    parts = {x["id"]: x for x in doc["parts"]}
    boxes = {x["id"]: x for x in doc["box_connectors"]}
    assert parts[PART]["row_layout"] == {"rows": [["1", "3"], ["2"]]}
    assert boxes[OWN]["row_layout"] == {"rows": [["5", "4"], ["1"]]}
    assert "row_layout" not in boxes["PCDU-J01"]  # the part's rows are not copied to it
    assert sum("row_layout" in x for x in [*parts.values(), *boxes.values()]) == 2
    assert doc["format_version"] == 1


# ---- the independent check ------------------------------------------------------------------------


def test_the_output_check_passes_every_file_of_the_project(faced):
    p, files = faced
    assert errors(p, files) == []


def test_the_check_finds_a_wrong_pin_row_in_the_box_pinouts(faced):
    p, files = faced

    def wrong(body):
        at = body[0].index("Pin row")
        for r in body[1:]:
            if r[0] == OWN and r[4] == "5":
                r[at] = "2"
        return body

    found = errors(p, edit_csv(files, "system/box_pinouts.csv", wrong))
    assert any(c == "out_box_pinouts" and "RW1-J02/5 (Pin row)" in m for c, m in found)


def test_the_check_finds_a_wrong_pin_row_in_a_harness_pinout(faced):
    p, files = faced

    def wrong(body):
        at = body[0].index("Pin row")
        body[1][at] = "2"
        return body

    found = errors(p, edit_csv(files, "harnesses/W001/pinouts.csv", wrong))
    assert any(c == "out_pinout" and "(Pin row)" in m for c, m in found)


def test_the_check_finds_a_missing_pin_row_column(faced):
    p, files = faced
    found = errors(p, edit_csv(files, "system/box_pinouts.csv", lambda b: [r[:-1] for r in b]))
    assert ("out_box_pinouts", "The box connector pinouts has the wrong column headings.") in found
    found = errors(p, edit_csv(files, "harnesses/W002/pinouts.csv", lambda b: [r[:-1] for r in b]))
    assert any(c == "out_pinout" and "wrong column headings" in m for c, m in found)


def test_the_check_finds_a_pin_row_column_in_a_project_without_a_layout():
    p = mini3()
    from harness_design_studio.core.generate.engine import generate_project

    generate_project(p)
    files = dict(build_outputs(p).files)
    extra = edit_csv(
        files, "system/box_pinouts.csv", lambda b: [[*b[0], "Pin row"], *([*r, ""] for r in b[1:])]
    )
    found = errors(p, extra)
    assert ("out_box_pinouts", "The box connector pinouts has the wrong column headings.") in found


def test_the_check_finds_a_row_layout_missing_from_export_json(faced):
    p, files = faced
    doc = json.loads(files["system/export.json"])
    for x in doc["box_connectors"]:
        x.pop("row_layout", None)
    found = errors(p, {**files, "system/export.json": json.dumps(doc).encode()})
    assert ("out_json", "The JSON export does not match the design.") in found


def _plan_errors(p, monkeypatch, layout):
    """The findings on a plan written with `layout` in place of the core's `layout_of`."""
    monkeypatch.setattr(hp, "layout_of", layout)
    files = dict(build_outputs(p, harness_plan=True).files)
    monkeypatch.undo()
    return [m for c, m in errors(p, files) if c == "out_plan"]


def test_the_plan_check_finds_a_wrong_order_of_the_near_block(monkeypatch):
    p = row_layout_project()

    def mirrored(project, c):  # each row reversed: the same row numbers, another order
        rows = layout_of(project, c)
        return rows and dataclasses.replace(rows, rows=tuple(r[::-1] for r in rows.rows))

    found = _plan_errors(p, monkeypatch, mirrored)
    assert any("sheet 'W001', cell B28" in m for m in found), found


def test_the_plan_check_finds_a_wrong_pin_row(monkeypatch):
    p = row_layout_project()

    @dataclasses.dataclass(frozen=True)
    class OneOff:  # the rows in their order, each number one too high
        real: object

        def row_of(self, pin):
            n = self.real.row_of(pin)
            return None if n is None else n + 1

        def order(self):
            return self.real.order()

    def wrong(project, c):
        rows = layout_of(project, c)
        return rows and OneOff(rows)

    found = _plan_errors(p, monkeypatch, wrong)
    assert any("sheet 'CON_PCDU-J01', cell F19 holds 2, the design gives 1" in m for m in found)
    assert any("sheet 'W001', cell A28 holds 2, the design gives 1" in m for m in found), found


def test_the_plan_check_finds_a_missing_and_an_extra_pin_row_column(monkeypatch):
    p = row_layout_project()
    found = _plan_errors(p, monkeypatch, lambda project, c: None)
    assert any("sheet 'W001', cell A27 is empty" in m for m in found), found
    assert any("sheet 'W001', cell B29 holds 2, the design gives 3" in m for m in found), found
    plain = mini3()
    from harness_design_studio.core.generate.engine import generate_project

    generate_project(plain)
    fake = layout_of(p, p.connectors["PCDU-J01"])  # 1 3 / 2 for every connector of mini3
    found = _plan_errors(plain, monkeypatch, lambda project, c: fake)
    assert any("where the design has an empty cell" in m for m in found), found


def test_the_verifiers_read_the_rows_without_the_core_module():
    banned = "harness_design_studio.core.row_layout"
    for name in ("verify_plan.py", "verify.py"):
        names = imported_names(SRC / "harness_design_studio/core/outputs" / name, SRC)
        assert names and not [n for n in names if n == banned or n.startswith(banned + ".")]


pin_names = st.sampled_from(["1", "2", "3", "4", "5", "A1"])


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    part=st.none() | st.lists(st.lists(pin_names, min_size=1, max_size=3), min_size=1, max_size=3),
    own=st.none() | st.lists(st.lists(pin_names, min_size=1, max_size=3), min_size=1, max_size=3),
)
def test_the_verifier_s_reading_of_the_rows_is_the_core_s(part, own) -> None:
    p = row_layout_project()

    def layout(rows, have=None):
        seen, out = set(), []
        for row in rows:
            kept = []
            for n in row:
                if n not in seen and (have is None or n in have):
                    seen.add(n)
                    kept.append(n)
            if kept:
                out.append(kept)
        return RowLayout(rows=out) if out else None

    p.parts[PART] = evolve(p.parts[PART], row_layout=None if part is None else layout(part))
    box = p.connectors["PCDU-J01"]
    have = {x.id for x in box.pins}
    p.connectors["PCDU-J01"] = evolve(box, row_layout=None if own is None else layout(own, have))
    everything = [*p.connectors.values(), *(c for h in p.harnesses.values() for c in h.connectors)]
    for c in everything:
        core = layout_of(p, c)
        assert vp.face_rows(p, c) == (None if core is None else core.rows), c.id


# ---- the goldens and the projects without a layout ------------------------------------------------


def test_the_outputs_of_the_row_layout_project_match_the_golden_set():
    """`python -m tools.gen_output_goldens` writes it; renew it only on purpose and review it."""
    files = build_outputs(row_layout_project()).files
    golden = json.loads((GOLDEN / "row_layout.json").read_text(encoding="utf-8"))
    got = output_digests(files)
    assert sorted(got) == sorted(golden)
    assert [k for k in got if got[k] != golden[k]] == []
    for rel, data in golden_text_files(files).items():
        assert (GOLDEN / "row_layout" / rel).read_bytes() == data, rel


def test_a_project_without_a_layout_keeps_the_bytes_of_its_golden_set():
    """The goldens of mini3 were made before format 4; nothing in them moves."""
    p = mini3()
    from harness_design_studio.core.generate.engine import generate_project

    generate_project(p)
    golden = json.loads((GOLDEN / "mini3.json").read_text(encoding="utf-8"))
    assert output_digests(build_outputs(p).files) == golden


def test_the_project_has_both_kinds_of_layout(faced):
    p, _files = faced
    got = {c.id: (r.source, r.source_id) for c in p.connectors.values() if (r := layout_of(p, c))}
    assert got[OWN] == ("own", OWN) and got["PCDU-J01"] == ("part", PART)
    assert address(18, hp.COL_F) == "F19"
