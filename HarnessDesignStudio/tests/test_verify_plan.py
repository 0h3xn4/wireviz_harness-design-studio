# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The independent check of the harness plans (REQ-VER-02, REQ-OUT-01; D-242, pull request 4 of
`docs/ait/DESIGN_3.0_HARNESS_PLAN.md`, section 7.5 and the "Verifier mutation tests" bullet of
section 11): `core/outputs/verify_plan.py` reads each plan's package and XML and works out every
sheet and cell from the project on its own. Each mutation of the list gives its error; a plan of
every example as written gives none; the verifier's own copies of the sides rule, the Direction
words, the mirrored directions and the colour lookup agree with the core's on random harnesses,
splices among them (Hypothesis, pull request 6), and so does the whole plan. The verifier imports
neither the writer nor the layout."""

import io
import re
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness_design_studio.core.model import (
    ConfigFile,
    Connector,
    Harness,
    Part,
    Pin,
    Project,
    Unit,
    Wire,
)
from harness_design_studio.core.model.physical import Role
from harness_design_studio.core.outputs import harness_plan as hp
from harness_design_studio.core.outputs import verify_plan as vp
from harness_design_studio.core.outputs.build import build_outputs, write_outputs
from harness_design_studio.core.outputs.stamp import stamp_of
from harness_design_studio.core.outputs.verify import read_folder, verify_outputs
from harness_design_studio.core.samples import new_project
from harness_design_studio.core.verify import VerifyReport
from tests.plan_support import GOLDEN_PROJECTS, golden_project
from tests.static_scan import imported_names
from tests.test_harness_plan import straight, with_plan_config

SRC = Path(__file__).resolve().parents[1] / "src"
REL = "harnesses/W001/W001_plan.ods"


# ---- helpers ------------------------------------------------------------------------------------


def plan_files(p: Project, drawings: bool = False) -> dict[str, bytes]:
    """An output set with the plans, as `build_outputs` gives it (no manifest)."""
    return dict(build_outputs(p, drawings=drawings, harness_plan=True).files)


def errors(p: Project, files: dict[str, bytes]) -> list[tuple[str, str]]:
    return [(i.code, i.message) for i in verify_outputs(p, files).errors]


def plan_errors(p: Project, data: bytes, hid: str = "W001") -> list[tuple[str, str]]:
    """The findings of the plan check alone, on the bytes of one plan."""
    r = VerifyReport()
    vp.check_plan(r, p, p.harnesses[hid], f"harnesses/{hid}/{hid}_plan.ods", data, False)
    return [(i.code, i.message) for i in r.errors]


def has(found: list[tuple[str, str]], code: str, words: str = "") -> bool:
    return any(c == code and words in m for c, m in found)


Entries = list[tuple[zipfile.ZipInfo, bytes]]


def rezip(data: bytes, edit: Callable[[Entries], Entries]) -> bytes:
    """The package with its entries changed by `edit` (each entry's ZipInfo kept as it is)."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        entries = [(i, z.read(i.filename)) for i in z.infolist()]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for info, body in edit(entries):
            z.writestr(info, body)
    return out.getvalue()


def with_entry(data: bytes, name: str, fn: Callable[[str], str]) -> bytes:
    def edit(entries: Entries) -> Entries:
        return [(i, fn(b.decode()).encode() if i.filename == name else b) for i, b in entries]

    return rezip(data, edit)


def with_content(data: bytes, fn: Callable[[str], str]) -> bytes:
    return with_entry(data, "content.xml", fn)


def once(old: str, new: str) -> Callable[[str], str]:
    def fn(text: str) -> str:
        assert old in text
        return text.replace(old, new, 1)

    return fn


def table(text: str, name: str) -> re.Match[str]:
    m = re.search(rf'<table:table table:name="{name}".*?</table:table>', text)
    assert m is not None
    return m


def first_wired_row(text: str) -> re.Match[str]:
    """The first pin row with a wire on the harness sheet: the first row whose Pinout copies its
    device side (`=[.B<row>]`)."""
    sheet = table(text, "W001")
    for m in re.finditer(r"<table:table-row>.*?</table:table-row>", sheet.group()):
        if 'table:formula="of:=[.B' in m.group():
            return m
    raise AssertionError("no wired row")


# ---- a plan as written gives no error -----------------------------------------------------------


@pytest.mark.parametrize("name", GOLDEN_PROJECTS)
def test_a_plan_of_every_example_as_written_gives_no_error(name: str) -> None:
    p = golden_project(name)
    files = plan_files(p)
    assert [k for k in files if k.endswith(vp.PLAN_SUFFIX)]
    assert errors(p, files) == []


def test_a_plan_with_the_drawings_and_its_manifest_in_a_folder_gives_no_error(
    tmp_path: Path,
) -> None:
    p = golden_project("first-steps")
    write_outputs(p, tmp_path / "o", build_outputs(p, drawings=True, harness_plan=True))
    files = read_folder(tmp_path / "o")
    assert "manifest.json" in files
    assert errors(p, files) == []


def test_the_small_projects_of_the_layout_tests_give_no_error() -> None:
    p = with_plan_config(
        straight(),
        colour_rule="pin_code",
        colour_codes=[
            {"name": "c1", "parts": ["EX-MICROD-9-M"], "pins": {"1": "Black", "3": "Red"}}
        ],
        notes=["A note line."],
    )
    for project in (straight(), p):
        assert (
            plan_errors(project, hp.plan_ods(project, project.harnesses["W001"], stamp_of(project)))
            == []
        )


def test_a_set_without_plans_is_not_asked_for_them() -> None:
    p = straight()
    files = dict(build_outputs(p, drawings=False).files)
    assert not [e for e in errors(p, files) if e[0].startswith("out_plan")]


# ---- the mutations of section 11 -----------------------------------------------------------------


@pytest.fixture(scope="module")
def project() -> Project:
    return straight()


@pytest.fixture(scope="module")
def data(project: Project) -> bytes:
    return plan_files(project)[REL]


def test_a_changed_value(project: Project, data: bytes) -> None:
    bad = with_content(data, once("VERSION: v1.0.0 (draft)", "VERSION: v9.0.0 (draft)"))
    found = plan_errors(project, bad)
    assert has(found, "out_plan", "cell Q6 holds 'VERSION: v9.0.0 (draft)'")
    assert not has(found, "out_plan_formula")


def test_a_changed_formula(project: Project, data: bytes) -> None:
    # the same value by another formula: only the text differs from the design
    bad = with_content(data, once("of:=[.B6]&amp;", "of:=[.B6]&amp;&quot;&quot;&amp;"))
    found = plan_errors(project, bad)
    assert has(found, "out_plan_formula", "cell B9 has the formula")
    assert has(found, "out_plan_formula", "the design gives =[.B6]")
    assert not has(found, "out_plan")


def test_a_stored_value_that_its_formula_does_not_give(project: Project, data: bytes) -> None:
    text = zipfile.ZipFile(io.BytesIO(data)).read("content.xml").decode()
    m = re.search(
        r'table:formula="of:=\[\.B6\][^"]*" office:value-type="string" office:string-value="([^"]*)"><text:p>([^<]*)<',
        text,
    )
    assert m is not None and m.group(1) == m.group(2)
    stored = m.group()
    bad = with_content(data, once(stored, stored.replace(m.group(1), "Another 9 female")))
    found = plan_errors(project, bad)
    assert has(found, "out_plan_formula", "but the cell stores 'Another 9 female'")


def test_a_formula_outside_the_list(project: Project, data: bytes) -> None:
    bad = with_content(data, once("of:=(SUMIF(", "of:=(SUMIFS("))
    assert has(plan_errors(project, bad), "out_plan_formula", "outside the closed list")


def test_indirect_in_a_formula(project: Project, data: bytes) -> None:
    bad = with_content(data, once("of:=[.B6]&amp;", "of:=INDIRECT(&quot;B6&quot;)&amp;"))
    assert has(plan_errors(project, bad), "out_plan_formula", "INDIRECT is not allowed")


def test_a_missing_sheet(project: Project, data: bytes) -> None:
    bad = with_content(data, lambda t: t.replace(table(t, "Notes").group(), "", 1))
    assert has(plan_errors(project, bad), "out_plan", "the sheet 'Notes' is missing")


def test_an_extra_sheet(project: Project, data: bytes) -> None:
    def extra(t: str) -> str:
        about = table(t, "About").group()
        return t.replace(about, about + about.replace('table:name="About"', 'table:name="Extra"'))

    assert has(
        plan_errors(project, with_content(data, extra)), "out_plan", "'Extra' is not a sheet"
    )


def test_sheets_in_another_order(project: Project, data: bytes) -> None:
    def swap(t: str) -> str:
        notes = table(t, "Notes").group()
        about = table(t, "About").group()
        return t.replace(notes, "", 1).replace(about, about + notes, 1)

    found = plan_errors(project, with_content(data, swap))
    assert has(found, "out_plan", "the sheets are in the order")


def test_a_missing_row(project: Project, data: bytes) -> None:
    def drop(t: str) -> str:
        return t.replace(first_wired_row(t).group(), "", 1)

    found = plan_errors(project, with_content(data, drop))
    assert has(found, "out_plan", "the row of wire W001-001 (pin W001-P1.1) (row 29) is missing")


def test_a_wire_in_two_rows(project: Project, data: bytes) -> None:
    def twice(t: str) -> str:
        row = first_wired_row(t).group()
        return t.replace(row, row + row, 1)

    found = plan_errors(project, with_content(data, twice))
    assert has(found, "out_plan", "wire W001-001 (pin W001-P1.1) is in 2 rows")


def test_a_plan_of_a_harness_that_is_gone(project: Project) -> None:
    files = plan_files(project)
    files["harnesses/W009/W009_plan.ods"] = files[REL]
    assert has(
        errors(project, files), "out_plan", "the plan of W009, which is no longer in the design"
    )


def test_a_plan_of_a_harness_that_is_gone_from_the_manifest(tmp_path: Path) -> None:
    p = straight()
    write_outputs(p, tmp_path / "o", build_outputs(p, drawings=False, harness_plan=True))
    del p.harnesses["W001"]
    assert has(errors(p, read_folder(tmp_path / "o")), "out_plan", "no longer in the design")


def test_a_harness_without_its_plan() -> None:
    p = golden_project("branching")
    files = plan_files(p)
    del files["harnesses/W002/W002_plan.ods"]
    assert has(errors(p, files), "out_plan", "the export has harness plans, but none for W002")


def test_a_compressed_entry(project: Project, data: bytes) -> None:
    def deflate(entries: Entries) -> Entries:
        for info, _ in entries:
            if info.filename == "content.xml":
                info.compress_type = zipfile.ZIP_DEFLATED
        return entries

    found = plan_errors(project, rezip(data, deflate))
    assert has(found, "out_plan_package", "the entry content.xml is compressed")
    assert not has(found, "out_plan")


def test_mimetype_not_first(project: Project, data: bytes) -> None:
    bad = rezip(data, lambda e: [e[1], e[0], *e[2:]])
    found = plan_errors(project, bad)
    assert has(found, "out_plan_package", "mimetype is not its first entry")


def test_a_missing_manifest_entry(project: Project, data: bytes) -> None:
    entry = '<manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>'
    bad = with_entry(data, "META-INF/manifest.xml", once(entry, ""))
    assert has(plan_errors(project, bad), "out_plan_package", "the manifest does not list meta.xml")


def test_a_doctype_in_content_xml(project: Project, data: bytes) -> None:
    head = '<?xml version="1.0" encoding="UTF-8"?>\n'
    bad = with_content(data, once(head, head + '<!DOCTYPE x [<!ENTITY a "b">]>'))
    found = plan_errors(project, bad)
    assert has(found, "out_plan_package", "content.xml holds a DOCTYPE or entity declaration")
    assert not has(found, "out_plan")  # the XML was not read


def test_a_wrong_stamp(project: Project) -> None:
    files = plan_files(project)
    full = stamp_of(project).model_hash
    files[REL] = with_content(files[REL], once(full, "0" * len(full)))
    found = errors(project, files)
    assert has(found, "out_stamp", REL)
    assert vp.plan_stamp(files[REL]) == "0" * 12


def test_a_plan_changed_in_a_folder_fails_out_modified(tmp_path: Path) -> None:
    p = straight()
    write_outputs(p, tmp_path / "o", build_outputs(p, drawings=False, harness_plan=True))
    path = tmp_path / "o" / REL
    path.write_bytes(with_content(path.read_bytes(), once("VERSION: v1.0.0", "VERSION: v1.0.1")))
    found = errors(p, read_folder(tmp_path / "o"))
    assert has(found, "out_modified", REL) and has(found, "out_plan", "cell Q6")


def test_a_damaged_plan_is_a_finding_not_a_crash(project: Project) -> None:
    files = plan_files(project)
    files[REL] = b"PK\x03\x04 not a package"
    found = errors(project, files)
    assert has(found, "out_plan_package", "cannot be read as a zip package")


def test_a_conditional_format_is_checked_by_its_formula_text(project: Project, data: bytes) -> None:
    bad = with_content(data, once("is-true-formula(OR(", "is-true-formula(OR(FALSE();"))
    assert has(plan_errors(project, bad), "out_plan_formula", "conditional format")


# the search boxes (3.1.0, section 25 of the design)


def test_a_search_format_with_another_function(project: Project, data: bytes) -> None:
    bad = with_content(data, once("ISNUMBER(SEARCH(", "ISNUMBER(FIND("))
    found = plan_errors(project, bad)
    assert has(found, "out_plan_formula", "which is outside the closed list: FIND")
    assert has(found, "out_plan_formula", "the design gives =IF([.$I$3]")


def test_a_search_format_with_a_start_position(project: Project, data: bytes) -> None:
    bad = with_content(data, once("[.$M$3];[.M", "[.$M$3];2;[.M"))
    found = plan_errors(project, bad)
    assert has(found, "out_plan_formula", "SEARCH takes 2 to 2 arguments here, not 3")


def test_a_search_format_that_is_missing(project: Project, data: bytes) -> None:
    def drop(t: str) -> str:
        return re.sub(
            r'<style:map style:condition="is-true-formula\(IF\(\[\.\$I\$3\][^>]*/>', "", t
        )

    found = plan_errors(project, with_content(data, drop))
    assert has(found, "out_plan_formula", "has the conditional formats none")


def test_a_changed_search_text(project: Project, data: bytes) -> None:
    bad = with_content(data, once("<text:p>#</text:p>", "<text:p>TX</text:p>"))
    assert has(plan_errors(project, bad), "out_plan", "cell I3 holds 'TX'")


@pytest.mark.parametrize(
    ("settings", "words"),
    [
        ("", "no table:calculation-settings"),
        (
            '<table:calculation-settings table:use-wildcards="false"/>',
            "use-regular-expressions to 'true'",
        ),
        (
            '<table:calculation-settings table:use-regular-expressions="false" table:use-wildcards="true"/>',
            "use-wildcards to 'true'",
        ),
    ],
)
def test_a_plan_that_reads_text_as_a_pattern(
    project: Project, data: bytes, settings: str, words: str
) -> None:
    from harness_design_studio.core.outputs.ods import CALCULATION_SETTINGS

    bad = with_content(data, once(CALCULATION_SETTINGS, settings))
    found = plan_errors(project, bad)
    assert has(found, "out_plan_formula", words)
    assert not has(found, "out_plan")


def test_many_differences_are_counted_not_listed_one_by_one(project: Project, data: bytes) -> None:
    def drop(t: str) -> str:
        return t.replace(first_wired_row(t).group(), "", 1)

    found = plan_errors(project, with_content(data, drop))
    assert len([m for c, m in found if c == "out_plan"]) <= vp.MAX_MESSAGES + 1
    assert has(found, "out_plan", "more findings of this kind")


# ---- the evaluator and the closed list ----------------------------------------------------------


@pytest.mark.parametrize(
    ("formula", "why"),
    [
        ("OFFSET([.A1];1;1)", "OFFSET is not allowed"),
        ("COM.MICROSOFT.CONCAT([.A1])", "is not allowed"),
        ("SUM([.A1:.A3])", "not in the closed list"),
        ("[Sheet1!A1]", "not a reference"),
        ("[$Nowhere.A1]", "a sheet the plan does not have"),
        ("[.A1]-1", "not in the closed list"),
        ("1E5", "not in the closed list"),
        ("B13", "not in the closed list"),
        ("VLOOKUP([.A1];[.A1:.B2];2;1)", "exact match"),
        ("IF([.A1])", "takes 2 to 3 arguments"),
        ("AND([.A1]=1)", "not in the closed list"),
    ],
)
def test_the_closed_list_refuses(formula: str, why: str) -> None:
    with pytest.raises(vp.FormulaError, match=re.escape(why)):
        vp.parse_formula(formula, "S", frozenset({"S"}))


def test_and_and_or_are_taken_in_a_conditional_format_only() -> None:
    vp.parse_formula(
        'OR(AND([.A1]="GND";[.B1]="PWR"))', "S", frozenset({"S"}), vp.CONDITION_FUNCTIONS
    )


def test_isnumber_and_search_are_taken_in_a_conditional_format_only() -> None:
    found = 'IF([.$I$3]="";0;ISNUMBER(SEARCH([.$I$3];[.I34])))'
    vp.parse_formula(found, "S", frozenset({"S"}), vp.CONDITION_FUNCTIONS)
    for formula, why in (
        (found, "ISNUMBER is not in the closed list"),
        ("SEARCH([.A1];[.B1])", "SEARCH is not in the closed list"),
    ):
        with pytest.raises(vp.FormulaError, match=re.escape(why)):
            vp.parse_formula(formula, "S", frozenset({"S"}))
    for formula, why in (
        ("FIND([.A1];[.B1])", "FIND is not in the closed list"),
        ("ISTEXT([.A1])", "ISTEXT is not in the closed list"),
        ("SEARCH([.A1];[.B1];2)", "SEARCH takes 2 to 2 arguments"),
        ("SEARCH([.A1])", "SEARCH takes 2 to 2 arguments"),
        ("ISNUMBER([.A1];[.B1])", "ISNUMBER takes 1 to 1 arguments"),
    ):
        with pytest.raises(vp.FormulaError, match=re.escape(why)):
            vp.parse_formula(formula, "S", frozenset({"S"}), vp.CONDITION_FUNCTIONS)


def _ev(cells: dict[tuple[int, int], str | float], formula: str) -> object:
    got = {
        k: vp.Got("float" if isinstance(v, float) else "string", v, str(v), "", "")
        for k, v in cells.items()
    }
    ev = vp.Evaluator({"S": got})
    return ev.value(vp.parse_formula(formula, "S", frozenset({"S"})))


def test_the_evaluator_on_the_closed_list() -> None:
    cells: dict[tuple[int, int], str | float] = {
        (0, 0): "in",
        (0, 1): 3.0,
        (1, 0): "A",
        (1, 1): 2.0,
        (2, 0): "B",
        (2, 1): 5.0,
    }
    assert _ev(cells, 'IF([.A1]="IN";"OUT";IF([.A1]="OUT";"IN";[.A1]))') == "OUT"
    assert _ev(cells, '[.A2]&" "&[.B1]&"-"&[.C9]') == "A 3-"
    assert _ev(cells, "VLOOKUP([.A3];[.A2:.B3];2;0)") == 5.0
    assert _ev(cells, '"x"&IF(ISNA(MATCH("c";[.A1:.A3];0));"";1)') == "x"
    assert _ev(cells, 'MATCH("b";[.A1:.A3];0)+10') == 13.0
    assert _ev(cells, 'SUMIF([.A1:.A3];"a";[.B1:.B3])/[.B2]') == 1.0
    assert _ev(cells, 'SUMIF([.A3:.A3];"b";[.B3:.B3])') == 5.0


def _cond(cells: dict[tuple[int, int], str | float], formula: str) -> object:
    got = {
        k: vp.Got("float" if isinstance(v, float) else "string", v, str(v), "", "")
        for k, v in cells.items()
    }
    ev = vp.Evaluator({"S": got})
    return ev.value(vp.parse_formula(formula, "S", frozenset({"S"}), vp.CONDITION_FUNCTIONS))


def test_the_evaluator_on_isnumber_and_search() -> None:
    cells: dict[tuple[int, int], str | float] = {(0, 0): "RS422_TX+", (0, 1): 15.0, (0, 2): "a*b"}
    assert _cond(cells, 'SEARCH("tx+";[.A1])') == 7.0
    assert _cond(cells, 'SEARCH("x+x";[.A1])') == vp._Error("#VALUE!")  # not a pattern
    assert _cond(cells, 'SEARCH("*";[.C1])') == 2.0
    assert _cond(cells, 'SEARCH("5";[.B1])') == 2.0
    assert _cond(cells, 'SEARCH("";[.A1])') == vp._Error("#VALUE!")
    assert _cond(cells, 'ISNUMBER(SEARCH("q";[.A1]))') is False
    assert _cond(cells, "ISNUMBER([.B1])") is True
    assert _cond(cells, "ISNUMBER([.A1])") is False
    assert _cond(cells, "ISNUMBER([.D9])") is False
    found = 'IF([.D9]="";0;ISNUMBER(SEARCH([.D9];[.A1])))'
    assert _cond(cells, found) == 0.0  # an empty box marks nothing


# ---- the verifier's copies against the core's (Hypothesis) --------------------------------------

_IDS = st.sampled_from(["1", "2", "3", "01", "10", "A", "a"])
_SIGNALS = st.sampled_from(["", "GND", "RTN", "TX", "RX", "PWR_28V", "SGND", "+5V"])
_PIN = st.builds(
    Pin,
    id=_IDS,
    signal=_SIGNALS.map(lambda s: s or None),
    role=st.sampled_from(
        ["", "power", "return", "ground", "signal", "shield", "spare", "signal_ground"]
    ),
    direction=st.sampled_from(["", "in", "out", "bidir"]),
    level=st.sampled_from([None, "TTL-5V", "18V"]),
    function=st.sampled_from([None, "Supply", "a  b"]),
)
_PINS = st.lists(_PIN, min_size=1, max_size=4, unique_by=lambda p: p.id)
_PARTS = ("P-A", "P-B", "P-C")


@st.composite
def projects(draw: st.DrawFn) -> Project:
    """A project with one harness: two to four box connectors on devices, as many cable connectors
    (some loose, some on no box), up to two splices of one or two nodes, random pins, wires between
    random pins, parts and colour codes."""
    p = new_project("Random plan")
    for part in _PARTS:
        p.parts[part] = Part(
            id=part, category="connector", description=draw(st.sampled_from(["", f"Desc {part}"])) or None,
            pin_count=draw(st.sampled_from([None, 9])),
        )  # fmt: skip
    p.parts["P-W"] = Part(id="P-W", category="wire", conductors=draw(st.sampled_from([1, 2])))
    n = draw(st.integers(2, 4))
    cables = []
    for k in range(1, n + 1):
        unit = f"D{k}"
        p.units[unit] = Unit(id=unit, name=unit, subsystem="s")
        p.connectors[f"{unit}-J1"] = Connector(
            id=f"{unit}-J1", name="J1", role="box", part_id=draw(st.sampled_from(_PARTS)),
            unit_id=draw(st.sampled_from([unit, None])), pins=draw(_PINS),
        )  # fmt: skip
        kind: Role = draw(st.sampled_from(["cable", "cable", "cable", "loose", "inline"]))
        cables.append(
            Connector(
                id=f"W001-P{k}",
                name=f"P{k}",
                role=kind,
                part_id=draw(st.sampled_from(_PARTS)),
                mates_with=f"{unit}-J1" if kind == "cable" else None,
                pins=draw(_PINS),
            )  # fmt: skip
        )
    for k in range(1, draw(st.integers(0, 2)) + 1):
        cables.append(
            Connector(
                id=f"W001-X{k}",
                name=f"X{k}",
                role="splice",
                part_id="P-S",
                pins=[Pin(id=str(n)) for n in range(1, draw(st.integers(1, 2)) + 1)],
            )
        )
    ends = [(c.id, pin.id) for c in cables for pin in c.pins]
    wires = []
    for k in range(draw(st.integers(0, 8))):
        a, b = draw(st.sampled_from(ends)), draw(st.sampled_from(ends))
        wires.append(
            Wire(
                id=f"W001-{k + 1:03d}",
                from_connector=a[0],
                from_pin=a[1],
                to_connector=b[0],
                to_pin=b[1],
                part_id=draw(st.sampled_from([None, "P-W"])),
                colour=draw(st.sampled_from([None, "red", "Blue"])),
                length_m=draw(st.sampled_from([None, 1.25, 0.3])),
                gauge_awg=draw(st.sampled_from([None, 24, 26])),
            )  # fmt: skip
        )
    p.harnesses["W001"] = Harness(id="W001", name="Random", connectors=cables, wires=wires)
    if draw(st.booleans()):
        pins = draw(st.dictionaries(_IDS, st.sampled_from(["Black", "Brown", "black"]), max_size=4))
        code = {"name": "c1", "parts": [draw(st.sampled_from(_PARTS))], "pins": pins}
        p.config["harness_plan"] = ConfigFile(
            name="harness_plan", placeholder=False,
            values={"colour_rule": "pin_code", "colour_codes": [code]},
        )  # fmt: skip
    return p


_SETTINGS = settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@_SETTINGS
@given(projects())
def test_the_sides_rule_agrees_with_the_cores(p: Project) -> None:
    h = p.harnesses["W001"]
    near, far = vp.plan_sides(h)
    core = hp.plan_sides(h)
    assert [c.id for c in near] == [c.id for c in core.near]
    assert [c.id for c in far] == [c.id for c in core.far]


@_SETTINGS
@given(projects())
def test_the_direction_words_agree_with_the_cores(p: Project) -> None:
    for c in [*p.connectors.values(), *p.harnesses["W001"].connectors]:
        for pin in c.pins:
            word = vp.direction_word(p, pin, c)
            assert word == hp.direction_word(p, pin, c)
            assert vp.mirrored(word) == hp.mirrored(word)


@given(
    st.sampled_from(["IN", "OUT", "IN/OUT", "PWR", "PWR-RET", "GND", "SGND", "SHIELD", ""])
    | st.text(max_size=4)
)
def test_the_mirrored_directions_agree_with_the_cores(word: str) -> None:
    assert vp.mirrored(word) == hp.mirrored(word)


@given(
    st.lists(
        st.tuples(
            st.sampled_from([1, 2, 10, "01", "a", "A", "x"]),
            st.sampled_from(["Black", "Red", "red"]),
        ),
        max_size=6,
    ),
    st.sampled_from([1, 2, 10, "01", "1", "a", "A", "y"]),
)
def test_the_colour_lookup_agrees_with_the_cores(
    rows: list[tuple[int | str, str]], key: int | str
) -> None:
    assert vp.lookup(rows, key) == hp.lookup(rows, key)


@_SETTINGS
@given(projects(), st.booleans())
def test_a_random_plan_as_written_gives_no_error(p: Project, drawings: bool) -> None:
    h = p.harnesses["W001"]
    data = hp.plan_ods(p, h, stamp_of(p), drawings=drawings)
    r = VerifyReport()
    vp.check_plan(r, p, h, REL, data, drawings)
    assert [i.message for i in r.errors] == []


# ---- independence -------------------------------------------------------------------------------


def test_the_verifier_imports_neither_the_writer_nor_the_layout() -> None:
    names = imported_names(SRC / "harness_design_studio/core/outputs/verify_plan.py", SRC)
    banned = {
        "harness_design_studio.core.outputs.ods",
        "harness_design_studio.core.outputs.harness_plan",
    }
    assert names and not [n for n in names if any(n == b or n.startswith(b + ".") for b in banned)]
