# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index,union-attr"
"""REQ-HARN-04. The written outputs of a harness with a splice (format 3, M6a; section 6.5 of the design of
2.3.0): the tests per pair of ends of a net, the column *Via*, no label for a splice, the BOM line,
the mass, the splice block of the build workbook, the drawn node, the WireViz style; the output
check that words each of them again and refuses a wrong one; the golden set; and the outputs of a
project without splices, which keep their bytes."""

import csv
import io
import json

import pytest
from openpyxl import load_workbook

from harness_design_studio.core.outputs import buildsheet
from harness_design_studio.core.outputs.build import build_outputs
from harness_design_studio.core.outputs.verify import verify_outputs
from harness_design_studio.core.samples import mini3
from tests.helpers import FIXTURES, output_digests
from tests.splice_support import branch_leg_project, golden_text_files


@pytest.fixture(scope="module")
def spliced():
    p = branch_leg_project()
    return p, build_outputs(p).files


def rows(files, rel):
    lines = files[rel].decode().splitlines()
    return [r for r in csv.reader(lines) if r and not r[0].startswith("#")]


def errors(p, files):
    return [e.message for e in verify_outputs(p, files).issues if e.severity == "error"]


def test_the_output_check_passes_every_file_of_the_project(spliced):
    p, files = spliced
    assert errors(p, files) == []


def test_the_tests_follow_the_nets_through_a_splice(spliced):
    _p, files = spliced
    tests = rows(files, "harnesses/W003/tests.csv")[1:]
    assert tests[0][1:4] == ["continuity", "W003-P1.1", "W003-P2.1 via W003-X1"]
    assert tests[0][7] == "W003-001;W003-002"
    assert sum(1 for t in tests if t[1] == "continuity") == 6  # three pairs per net, two nets
    iso = [t for t in tests if t[1] == "isolation"]
    assert iso[0][2:4] == ["W003-P1.1 + W003-P2.1 + W003-P3.1", "all other nets and shields"]
    mixed = rows(files, "harnesses/W004/tests.csv")[1:]
    assert mixed[3][1:4] == ["continuity", "W004-P1.2", "W004-P2.2"]  # a plain wire: as before


def test_the_wire_list_names_the_splices_of_each_wire(spliced):
    _p, files = spliced
    wl = rows(files, "harnesses/W003/wirelist.csv")
    assert wl[0][-1] == "Via"
    assert {r[0]: r[-1] for r in wl[1:]}["W003-005"] == "W003-X2"
    w4 = rows(files, "harnesses/W004/wirelist.csv")
    assert {r[0]: r[-1] for r in w4[1:]}["W004-004"] == ""
    assert rows(files, "harnesses/W001/wirelist.csv")[0][-1] != "Via"


def test_a_splice_has_no_label_and_is_no_connector_of_the_mass_table(spliced):
    _p, files = spliced
    labels = {r[0] for r in rows(files, "harnesses/W003/labels.csv")[1:]}
    assert "W003-X1" not in labels and "W003-P1" in labels
    mass = rows(files, "harnesses/W003/mass_length.csv")[1]
    assert mass[2] == "3"
    assert "splice" not in mass[9]


def test_the_bom_counts_each_splice_part(spliced):
    _p, files = spliced
    bom = {r[0]: r for r in rows(files, "system/bom.csv")[1:]}
    assert bom["EX-SPLICE-1"][1] == "splice" and bom["EX-SPLICE-1"][6] == "3"


def test_the_build_workbook_lists_the_splices_in_a_block_of_their_own(spliced):
    p, files = spliced
    wb = load_workbook(io.BytesIO(files["harnesses/W003/W003_build.xlsx"]), read_only=True)
    try:
        values = [list(r) for r in wb["Connectors"].iter_rows(values_only=True)]
    finally:
        wb.close()
    firsts = [str(r[0]) for r in values if r and r[0]]
    at = firsts.index(buildsheet.SPLICE_BLOCK)
    assert any(x.startswith("W003-P3") for x in firsts[:at])
    assert firsts[at + 1].startswith("W003-X1   ·   EX-SPLICE-1   ·   splice   ·   1 node")
    checks = {c.label: c.open for c in buildsheet.readiness(p, p.harnesses["W003"])}
    assert checks["Pins in use without a contact part"] == 6  # the six plug pins, no node


def test_the_drawing_shows_each_splice_as_a_node(spliced):
    _p, files = spliced
    svg = files["harnesses/W003/drawing_A3_s1.svg"].decode()
    assert 'data-ref="splice/W003-X1">W003-X1<' in svg
    assert 'data-ref="sig/W003-X1/1"' not in svg
    assert "W003-X1 (EX-SPLICE-1): node 1 crimp: W003-001, W003-002, W003-003" in svg


def test_the_wireviz_file_draws_a_splice_as_a_simple_connector(spliced):
    _p, files = spliced
    text = files["harnesses/W003/wireviz.yaml"].decode()
    assert '  "W003-X1":\n    pincount: 1\n    pinlabels: ["1"]\n    type: "EX-SPLICE-1"\n    style: simple\n' in text  # fmt: skip


def test_the_output_check_refuses_wrong_splice_outputs(spliced):
    p, files = spliced
    bad = dict(files)

    def swap(rel, old, new):
        data = bad[rel]
        assert old.encode() in data, (rel, old)
        bad[rel] = data.replace(old.encode(), new.encode(), 1)

    swap("harnesses/W003/wirelist.csv", ",W003-X2\n", ",W003-X1\n")
    swap("harnesses/W003/tests.csv", "W003-P2.1 via W003-X1", "W003-P2.1")
    swap("harnesses/W004/labels.csv", "W004-001-A", "W004-X1")
    swap("harnesses/W003/wireviz.yaml", "    style: simple\n", "")
    swap("harnesses/W004/drawing_A3_s1.svg", 'data-ref="splice/W004-X1"', 'data-ref=""')
    found = errors(p, bad)
    for what in (
        "Wire W003-004 in the wire list of W003 differs from the design: via",
        "The test list of W003",
        "The labels of W004",
        "The WireViz file of W003 differs from the design: style of W003-X1",
        "The drawing of W004 is wrong: the splice W004-X1 is not drawn as a splice",
    ):
        assert any(what in e for e in found), (what, found)


def test_the_output_check_refuses_a_workbook_without_the_splice_block(spliced, monkeypatch):
    p, _files = spliced
    monkeypatch.setattr(buildsheet, "SPLICE_BLOCK", "Something else")
    files = build_outputs(p).files
    monkeypatch.undo()
    assert any("splices in a block of their own" in e for e in errors(p, files))


def test_a_project_without_splices_writes_its_outputs_as_before():
    """The goldens of mini3 hold the bytes of 2.x for every file; a project without a splice keeps
    them (the output-hash baseline holds the examples)."""
    from harness_design_studio.core.generate.engine import generate_project

    p = mini3()
    generate_project(p)
    golden = json.loads((FIXTURES / "outputs" / "mini3.json").read_text(encoding="utf-8"))
    assert output_digests(build_outputs(p).files) == golden


def test_the_outputs_of_the_splice_project_match_the_golden_set(spliced):
    """`python -m tools.gen_output_goldens` writes it; renew it only on purpose and review it."""
    _p, files = spliced
    root = FIXTURES / "outputs"
    golden = json.loads((root / "splices.json").read_text(encoding="utf-8"))
    got = output_digests(files)
    assert sorted(got) == sorted(golden)
    assert [k for k in got if got[k] != golden[k]] == []
    text = golden_text_files(files)
    assert len(text) > 10
    for rel, data in text.items():
        assert (root / "splices" / rel).read_bytes() == data, rel
