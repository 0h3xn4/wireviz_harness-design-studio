# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The shield group column of the wire list and of the cut list names every group of a wire.

A wire of a twisted pair inside an overall shield is in two groups (`W002-S2` the pair, `W002-S3` the
overall shield of `flatsat`). Up to 4.0.1 `tables.shield_of` kept only the last group of a wire, and
the independent verifier used the same rule, so its self-check could not see the loss (design of
4.1.0, section 15, owner question P7). Here: both tables write every group in natural ID order,
joined by `;`; the export passes its self-check; the verifier refuses a wire list or a cut list that
names one group only; and the verifier's own copy (`verify._shield_groups`) is the tables' rule."""

import io
from pathlib import Path

import pytest

from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import Harness, Project, ShieldGroup, evolve
from harness_design_studio.core.outputs import buildsheet, tables
from harness_design_studio.core.outputs import verify as vf
from harness_design_studio.core.outputs.build import build_outputs
from harness_design_studio.core.outputs.stamp import parse_csv
from harness_design_studio.core.outputs.xlsx_env import load_workbook
from harness_design_studio.resources import examples_path
from tests.test_outputs import edit_csv


def _flatsat() -> Project:
    root = examples_path()
    assert root is not None
    return load_project(Path(root) / "projects" / "flatsat").project


def _nested(h: Harness) -> dict[str, list[str]]:
    """Each wire that is in more than one shield group, with its groups in natural ID order."""
    groups: dict[str, list[str]] = {}
    for s in sorted(h.shields, key=lambda x: tables.natural_key(x.id)):
        for wid in s.wire_ids:
            groups.setdefault(wid, []).append(s.id)
    return {wid: ids for wid, ids in groups.items() if len(ids) > 1}


def test_flatsat_has_wires_in_two_groups() -> None:
    p = _flatsat()
    counts = {hid: len(_nested(h)) for hid, h in p.harnesses.items() if _nested(h)}
    assert counts == {"W002": 14, "W004": 6}
    assert _nested(p.harnesses["W002"])["W002-003"] == ["W002-S2", "W002-S3"]


def test_wire_list_and_cut_list_name_every_group() -> None:
    p = _flatsat()
    for h in p.harnesses.values():
        nested = _nested(h)
        wl = tables.wire_list(p, h)
        col = wl[0].index("Shield group")
        by_wire = {row[0]: row[col] for row in wl[1:]}
        cut = {row[0]: row[10] for row in buildsheet.cut_rows(p, h)}
        for wid, ids in nested.items():
            assert by_wire[wid] == ";".join(ids), (h.id, wid)
            assert cut[wid] == ";".join(ids), (h.id, wid)
        for s in h.shields:  # a wire in one group keeps its one ID, as before
            for wid in s.wire_ids:
                if wid not in nested:
                    assert by_wire[wid] == s.id


def test_the_order_is_natural_and_a_repeated_id_is_named_once() -> None:
    p = _flatsat()
    h = p.harnesses["W002"]
    wid = "W002-003"
    s10 = ShieldGroup(id="W002-S10", kind="overall_shield", wire_ids=[wid])
    again = next(s for s in h.shields if s.id == "W002-S2")
    h2 = evolve(h, shields=[s10, *h.shields, again])
    assert tables.shield_of(h2)[wid] == "W002-S2;W002-S3;W002-S10"
    assert vf._shield_groups(h2) == tables.shield_of(h2)


def test_the_verifier_copy_is_the_tables_rule_on_every_example() -> None:
    root = examples_path()
    assert root is not None
    for folder in sorted((Path(root) / "projects").iterdir()):
        if not (folder / "project.json").exists():
            continue
        p = load_project(folder).project
        for h in p.harnesses.values():
            assert vf._shield_groups(h) == tables.shield_of(h), (folder.name, h.id)


@pytest.fixture(scope="module")
def flatsat_files() -> tuple[Project, dict[str, bytes]]:
    p = _flatsat()
    return p, dict(build_outputs(p).files)


def test_the_export_of_flatsat_passes_its_self_check(
    flatsat_files: tuple[Project, dict[str, bytes]],
) -> None:
    p, files = flatsat_files
    rows = parse_csv(files["harnesses/W002/wirelist.csv"])
    col = rows[0].index("Shield group")
    assert {r[0]: r[col] for r in rows[1:]}["W002-003"] == "W002-S2;W002-S3"
    assert vf.verify_outputs(p, files).ok


def test_the_verifier_refuses_a_wire_list_with_one_group_only(
    flatsat_files: tuple[Project, dict[str, bytes]],
) -> None:
    p, built = flatsat_files
    files = dict(built)
    rel = "harnesses/W002/wirelist.csv"

    def one_group(table: list[list[str]]) -> None:
        col = table[0].index("Shield group")
        for row in table[1:]:
            if row[0] == "W002-003":
                row[col] = "W002-S3"

    edit_csv(files, rel, one_group, p)
    errors = vf.verify_outputs(p, files).errors
    assert any(e.code == "out_wire_differs" and "W002-003" in e.message and "shield group" in e.message for e in errors)  # fmt: skip


def test_the_verifier_refuses_a_cut_list_with_one_group_only(
    flatsat_files: tuple[Project, dict[str, bytes]],
) -> None:
    p, built = flatsat_files
    files = dict(built)
    rel = "harnesses/W002/W002_build.xlsx"
    wb = load_workbook(io.BytesIO(files[rel]))
    ws = wb["Cut list"]
    header = [c.value for c in ws[1]]
    wire, shield = header.index("Wire") + 1, header.index("Shield group") + 1
    hits = [r for r in range(2, ws.max_row + 1) if ws.cell(r, wire).value == "W002-003"]
    assert len(hits) == 1 and ws.cell(hits[0], shield).value == "W002-S2;W002-S3"
    ws.cell(hits[0], shield).value = "W002-S3"
    raw = io.BytesIO()
    wb.save(raw)
    files[rel] = raw.getvalue()
    errors = vf.verify_outputs(p, files).errors
    assert any(e.code == "out_build" and "Cut list" in e.message and "W002-003" in e.message for e in errors)  # fmt: skip
