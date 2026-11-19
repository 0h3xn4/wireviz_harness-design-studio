# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The search boxes of the harness plan (REQ-OUT-01; 3.1.0, the owner's decision D-250, section 25
of `docs/ait/DESIGN_3.0_HARNESS_PLAN.md`): *Column Search String* and `#` in `I2:I3` and `M2:M3`,
and on the Function and Shielding cells of every near block a conditional format that is true
where the cell contains the text of its box, without regard to case and as typed, and false for an
empty box. `ISNUMBER` and `SEARCH` are taken in a conditional format only; the plan turns regular
expressions and wildcards off. The formats are evaluated with the tests' own evaluator
(`tests/plan_support.py`); with LibreOffice installed, LibreOffice gives the same as that evaluator
for the formula of a format and reads the plan's formats as conditional formats."""

import csv
import io
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from harness_design_studio.core.outputs import harness_plan as hp
from harness_design_studio.core.outputs import ods
from harness_design_studio.core.outputs.ods import Cell, Sheet, Workbook
from tests.plan_support import (
    GOLDEN_PROJECTS,
    Conditions,
    Evaluator,
    PlanCell,
    Sheets,
    address,
    golden_project,
    marked,
    moved,
    parse_address,
    read_conditions,
    read_plan,
)
from tests.test_harness_plan import plan, straight

SEARCH = 'IF([.$I$3]="";0;ISNUMBER(SEARCH([.$I$3];[.I{row}])))'
GND = 'OR(AND([.J{row}]="GND";[.R{row}]="PWR");AND([.R{row}]="GND";[.J{row}]="PWR"))'


def _rows_with(conds: dict[tuple[int, int], tuple[tuple[str, str], ...]], col: str) -> set[int]:
    c = parse_address(f"{col}1")[1]
    return {r for (r, cc) in conds if cc == c}


def _texts(cells: dict[tuple[int, int], PlanCell], rows: set[int], col: int) -> dict[int, str]:
    out = {}
    for r in rows:
        cell = cells.get((r, col))
        value = "" if cell is None else cell.value
        out[r] = value if isinstance(value, str) else f"{value:g}"
    return out


def _with_box(sheets: Sheets, sheet: str, col: str, text: str) -> Sheets:
    out = {name: dict(cells) for name, cells in sheets.items()}
    out[sheet][parse_address(f"{col}3")] = PlanCell(text)
    return out


def _marked_rows(sheets: Sheets, conds: Conditions, sheet: str, col: str) -> set[int]:
    c = parse_address(f"{col}1")[1]
    return {
        r
        for r in _rows_with(conds[sheet], col)
        if any("SEARCH" in f for f in marked(sheets, conds, sheet, r, c))
    }


# ---- the boxes and their formats -------------------------------------------------------------


def test_the_two_boxes_stand_above_function_and_shielding() -> None:
    harness = read_plan(plan(straight()))["W001"]
    for col in "IM":
        assert harness[parse_address(f"{col}2")].value == "Column Search String"
        assert harness[parse_address(f"{col}3")].value == "#"
        assert not harness[parse_address(f"{col}3")].formula
    assert {r for r, _ in harness if r < 5} == {1, 2}  # nothing else above the header


@pytest.mark.parametrize("name", ["branching", "splices"])
def test_every_near_block_has_the_search_format_on_function_and_shielding(name: str) -> None:
    p = golden_project(name)
    for h in p.harnesses.values():
        sheet = hp.harness_sheet_name(h)
        conds = read_conditions(plan(p, h.id))[sheet]
        rows = _rows_with(conds, "J")
        assert rows, h.id
        assert _rows_with(conds, "I") == _rows_with(conds, "M") == _rows_with(conds, "R") == rows
        firsts = sorted(r for r in rows if r - 1 not in rows)
        for first in firsts:  # each block's format is read from its first row
            end = first
            while end + 1 in rows:
                end += 1
            for r in range(first, end + 1):
                i, m = parse_address(f"I{r + 1}")[1], parse_address(f"M{r + 1}")[1]
                assert conds[r, i] == ((SEARCH.format(row=first + 1), f"{sheet}.I{first + 1}"),)
                box_m = SEARCH.format(row=first + 1).replace("$I$3", "$M$3").replace(".I", ".M")
                assert conds[r, m] == ((box_m, f"{sheet}.M{first + 1}"),)
                j = parse_address(f"J{r + 1}")[1]
                assert conds[r, j] == ((GND.format(row=first + 1), f"{sheet}.J{first + 1}"),)


def test_a_plan_with_two_near_blocks_has_one_format_per_block_and_column() -> None:
    p = golden_project("branching")
    h = next(h for h in p.harnesses.values() if len(hp.plan_sides(h).near) > 1)
    with zipfile.ZipFile(io.BytesIO(plan(p, h.id))) as z:
        content = z.read("content.xml").decode()
    blocks = len(hp.plan_sides(h).near)
    # one style:map per distinct (formula, base); each block's cells share the maps of its style
    bases = set(re.findall(r'style:base-cell-address="[^"]*\.([IM][0-9]+)"', content))
    assert len(bases) == 2 * blocks


# ---- what the formats mark -------------------------------------------------------------------

NEEDLES = ["#", "", "pwr", "PWR", "tx", "+", ".", "_", "s1", "*", "?", "~", "1"]


@pytest.mark.parametrize("name", GOLDEN_PROJECTS)
def test_a_box_marks_the_cells_that_contain_its_text_without_regard_to_case(name: str) -> None:
    p = golden_project(name)
    for h in p.harnesses.values():
        data = plan(p, h.id)
        sheet = hp.harness_sheet_name(h)
        sheets, conds = read_plan(data), read_conditions(data)
        for col in "IM":
            c = parse_address(f"{col}1")[1]
            texts = _texts(sheets[sheet], _rows_with(conds[sheet], col), c)
            for needle in NEEDLES:
                got = _marked_rows(_with_box(sheets, sheet, col, needle), conds, sheet, col)
                want = {r for r, t in texts.items() if needle and needle.lower() in t.lower()}
                assert got == want, (h.id, col, needle)
        # as written, `#` marks nothing: no Function or Shielding holds it
        assert not _marked_rows(sheets, conds, sheet, "I")
        assert not _marked_rows(sheets, conds, sheet, "M")


def test_the_function_box_finds_a_signal_and_the_shielding_box_a_shield() -> None:
    data = plan(straight())
    sheets, conds = read_plan(data), read_conditions(data)
    harness = sheets["W001"]
    rows = _rows_with(conds["W001"], "I")
    functions = _texts(harness, rows, parse_address("I1")[1])
    tx = {r for r, t in functions.items() if "TX" in t}
    assert tx and _marked_rows(_with_box(sheets, "W001", "I", "tx"), conds, "W001", "I") == tx
    shielded = {r for r, t in _texts(harness, rows, parse_address("M1")[1]).items() if t}
    assert len(shielded) == 2  # the pair of W001-S1
    assert _marked_rows(_with_box(sheets, "W001", "M", "w001-s"), conds, "W001", "M") == shielded
    assert not _marked_rows(_with_box(sheets, "W001", "M", ""), conds, "W001", "M")


def test_a_format_is_read_at_each_cell_from_its_base() -> None:
    assert moved(SEARCH.format(row=34), 5, 0) == SEARCH.format(row=39)
    assert moved('[.B2]&"[.B2]"&[$Notes.$B$7:.C8]', 1, 2) == '[.D3]&"[.B2]"&[$Notes.$B$7:.E9]'


# ---- the closed list -------------------------------------------------------------------------


def test_isnumber_and_search_are_taken_in_a_conditional_format_only() -> None:
    formula = 'IF([.$I$3]="";0;ISNUMBER(SEARCH([.$I$3];[.I34])))'
    ods.check_formula(formula, ods.CONDITION_FUNCTIONS)
    for cell in (formula, "SEARCH([.A1];[.B1])", "ISNUMBER([.A1])"):
        with pytest.raises(ValueError, match="not in the closed list of functions"):
            ods.check_formula(cell)
    for other in ("FIND([.A1];[.B1])", "ISTEXT([.A1])", "REGEX([.A1];[.B1])"):
        with pytest.raises(ValueError, match="not in the closed list of functions"):
            ods.check_formula(other, ods.CONDITION_FUNCTIONS)
    book = Workbook("t", (Sheet("S", rows=((Cell(1.0, formula="ISNUMBER([.A2])"),),)),))
    with pytest.raises(ValueError, match="cell A1: ISNUMBER is not in the closed list"):
        ods.write_ods(book)


def test_the_tests_evaluator_searches_as_typed_without_regard_to_case() -> None:
    sheets: Sheets = {
        "S": {(0, 0): PlanCell("RS422_TX+"), (0, 1): PlanCell(15.0), (0, 2): PlanCell("a*b")}
    }
    ev = Evaluator(sheets)

    def search(find: str, where: str) -> object:
        return ev.evaluate(f'SEARCH("{find}";{where})', "S", condition=True)

    assert search("tx+", "[.A1]") == 7.0
    assert search("rs", "[.A1]") == 1.0
    assert repr(search("x+x", "[.A1]")) == "#VALUE!"  # not a pattern
    assert repr(search(".", "[.A1]")) == "#VALUE!"
    assert search("*", "[.C1]") == 2.0 and repr(search("a?b", "[.C1]")) == "#VALUE!"
    assert search("5", "[.B1]") == 2.0  # a number is searched as its text
    assert repr(search("", "[.A1]")) == "#VALUE!"  # as LibreOffice 24.2 gives it
    assert ev.evaluate('ISNUMBER(SEARCH("q";[.A1]))', "S", condition=True) is False
    assert ev.evaluate("ISNUMBER([.B1])", "S", condition=True) is True
    assert ev.evaluate("ISNUMBER([.A1])", "S", condition=True) is False
    assert ev.evaluate("ISNUMBER([.D9])", "S", condition=True) is False  # an empty cell
    assert ev.evaluate('ISNA(SEARCH("q";[.A1]))', "S", condition=True) is False
    assert ev.evaluate('OR(AND([.A1]="x";1);[.B1]=15)', "S", condition=True) is True
    with pytest.raises(ValueError, match="not in the closed list"):
        ev.evaluate('SEARCH("a";[.A1])', "S")


def test_the_plan_turns_regular_expressions_and_wildcards_off() -> None:
    with zipfile.ZipFile(io.BytesIO(plan(straight()))) as z:
        content = z.read("content.xml").decode()
    assert f"<office:spreadsheet>{ods.CALCULATION_SETTINGS}<table:table " in content
    assert 'table:use-regular-expressions="false"' in ods.CALCULATION_SETTINGS
    assert 'table:use-wildcards="false"' in ods.CALCULATION_SETTINGS


def test_the_notes_say_how_to_search() -> None:
    notes = read_plan(plan(straight()))["Notes"]
    assert any(str(c.value).startswith("Search: type a text into I3") for c in notes.values())


# ---- a real reader ---------------------------------------------------------------------------

SOFFICE = shutil.which("soffice")
TEXTS: list[str | float] = [
    "RS422_TX+",
    "rs422_tx-",
    "GND",
    "",
    "A.B",
    "AxB",
    "f(x)",
    "a*b",
    "a?c",
    "x~y",
    "28V",
    15,
]
FINDS = ["tx+", "TX", ".", "(", "*", "?", "~", "", "a*b", "x+", "28v", "#", "5"]


def _convert(tmp_path: Path, src: Path, target: str) -> None:
    subprocess.run(
        [
            str(SOFFICE),
            f"-env:UserInstallation={(tmp_path / 'profile').as_uri()}",
            "--headless",
            "--convert-to",
            target,
            "--outdir",
            str(tmp_path / "out"),
            str(src),
        ],
        capture_output=True,
        check=True,
        timeout=180,
    )


@pytest.mark.skipif(SOFFICE is None, reason="LibreOffice (soffice) is not installed")
def test_libreoffice_and_the_tests_evaluator_agree_on_the_search_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The formula of a search format, written into cells (only here: the writer takes it in a
    conditional format only), over texts and search texts that a pattern would read otherwise;
    LibreOffice recalculates each with the plan's calculation settings."""
    monkeypatch.setattr(ods, "FUNCTIONS", ods.CONDITION_FUNCTIONS)
    rows = [[Cell("")] + [Cell(t) for t in TEXTS]]
    for n, find in enumerate(FINDS, start=2):
        row = [Cell(find)]
        for k in range(len(TEXTS)):
            col = address(0, k + 1)[:-1]
            box = f"[.$A${n}]"
            found = f'IF({box}="";0;ISNUMBER(SEARCH({box};[.{col}$1])))'
            row.append(Cell(0, formula=f"IF({found};1;0)"))
        rows.append(row)
    book = Workbook("t", (Sheet("S", tuple(tuple(r) for r in rows)),))
    src = tmp_path / "search.ods"
    src.write_bytes(ods.write_ods(book))
    _convert(
        tmp_path,
        src,
        "csv:Text - txt - csv (StarCalc):44,34,76,1,,0,false,true,false,false,false,-1",
    )
    with (tmp_path / "out" / "search-S.csv").open(newline="", encoding="utf-8") as fh:
        shown = list(csv.reader(fh))
    sheets = read_plan(src.read_bytes())
    ev = Evaluator(sheets)
    for (r, c), cell in sorted(sheets["S"].items()):
        if cell.formula:
            want = ev.evaluate(cell.formula, "S", condition=True)
            assert shown[r][c] == f"{want:g}", (FINDS[r - 1], TEXTS[c - 1], shown[r][c])
    assert shown[1][1:3] == ["1", "0"]  # tx+ finds RS422_TX+, not rs422_tx- (no pattern)


@pytest.mark.skipif(SOFFICE is None, reason="LibreOffice (soffice) is not installed")
def test_libreoffice_reads_the_search_formats_of_a_plan(tmp_path: Path) -> None:
    data = plan(straight())
    src = tmp_path / "plan.ods"
    src.write_bytes(data)
    _convert(tmp_path, src, "fods")
    flat = (tmp_path / "out" / "plan.fods").read_text(encoding="utf-8")
    conds = read_conditions(data)["W001"]
    rows = sorted(_rows_with(conds, "I"))
    for col in "IM":
        assert (
            f'calcext:target-range-address="W001.{col}{rows[0] + 1}:W001.{col}{rows[-1] + 1}"'
            in flat
        )
    assert flat.count("ISNUMBER(SEARCH(") >= 2
    assert 'table:use-regular-expressions="false"' in flat
