# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""`routing DIR HARNESS` and `explain` of a segment and a branch point (2.3.0, D-243, sections 5.7
and 5.9 of `docs/ait/DESIGN_2.3_BRANCHING.md`; pull request 5).

What is checked: the text and the `--json` document of `routing` on a harness of `flatsat` that
branches (the keys of `SHAPES`, the same rows as `segments.csv` and the sheet *Routing*), a straight
harness, a harness without segments, an unknown harness, where a length came from (entered,
imported, not set; kept by Generate), the wires with no route, and `explain` of a segment and of a
branch point in text and JSON (on demand only: `explain --all` is as it was). Nothing is changed."""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from harness_design_studio.cli.jsonout import SHAPES
from harness_design_studio.cli.main import main
from harness_design_studio.core import templates
from harness_design_studio.core.derive import explain_object
from harness_design_studio.core.derive_export import explain_all
from harness_design_studio.core.derive_kinds import KINDS, ON_DEMAND
from harness_design_studio.core.derive_routing import length_source, routing_tree
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import evolve
from harness_design_studio.core.outputs import tables


@pytest.fixture(scope="module")
def flatsat(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("routing") / "flatsat"
    templates.create_project(folder, "flatsat")
    return folder


@pytest.fixture
def copy(flatsat: Path, tmp_path: Path) -> Iterator[Path]:
    """A copy of flatsat that a test may change."""
    folder = tmp_path / "flatsat"
    shutil.copytree(flatsat, folder)
    yield folder


def files(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}  # fmt: skip


def cli(capsys: pytest.CaptureFixture[str], *argv: str | Path) -> tuple[int, str, str]:
    code = main([str(a) for a in argv])
    got = capsys.readouterr()
    return code, got.out, got.err


def doc(capsys: pytest.CaptureFixture[str], *argv: str | Path) -> dict:  # type: ignore[type-arg]
    code, out, err = cli(capsys, *argv, "--json")
    assert code == 0, err
    found = json.loads(out)
    assert isinstance(found, dict)
    return found


# ---- routing ------------------------------------------------------------------------------------


def test_the_text_of_a_harness_that_branches(
    flatsat: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = files(flatsat)
    code, out, err = cli(capsys, "routing", flatsat, "W005")
    assert code == 0 and err == ""
    lines = out.splitlines()
    assert lines[:2] == [
        "Harness W005: bus to egse",
        "It branches at 2 branch points and has 7 segments.",
    ]
    assert (
        "  W005-L1: W005-B1 (Branch X) to W005-B2 (Branch Y), 0.5 m, entered, kept by Generate"
        in lines
    )
    assert "  W005-L3: W005-P2 (PCDU1-J01) to W005-B1 (Branch X), 1 m, entered, kept by Generate" in lines  # fmt: skip
    assert "    2 wires: W005-001, W005-002" in lines and "    1 wire: W005-007" in lines
    i = lines.index("Branch points (the connectors beyond it, by segment):")
    assert lines[i + 1 : i + 6] == [
        "  W005-B1 (Branch X)",
        "    W005-L1: W005-P4, W005-P5, W005-P6",
        "    W005-L2: W005-P1",
        "    W005-L3: W005-P2",
        "    W005-L4: W005-P3",
    ]
    assert "without a length" not in out and "no single path" not in out
    assert files(flatsat) == before  # read only


def test_segments_are_in_natural_order(flatsat: Path, capsys: pytest.CaptureFixture[str]) -> None:
    found = doc(capsys, "routing", flatsat, "W001")
    ids = [s["id"] for s in found["segments"]]
    assert ids[:3] == ["W001-L1", "W001-L2", "W001-L3"] and ids[-1] == "W001-L19"


def test_the_document_has_the_shape_and_the_rows_of_the_outputs(
    flatsat: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    found = doc(capsys, "routing", flatsat, "W005")
    assert list(found) == list(SHAPES["routing"])
    assert found["ok"] is True and found["harness"] == "W005" and found["origin"] == "interfaces"
    assert found["branches"] is True and found["lengths_missing"] == []
    assert found["wires_without_route"] == []
    assert found["connectors"][0] == {"id": "W005-P1", "mates_with": "OBC1-J13"}
    first = found["segments"][0]
    assert list(first) == [
        "id", "from", "to", "length_m", "source", "kept_by_generate", "source_text", "wires",
    ]  # fmt: skip
    assert first["source"] == "entered" and first["kept_by_generate"] is True
    # the same rows as segments.csv (PR 4): the command line and the outputs agree
    h = load_project(flatsat).project.harnesses["W005"]
    rows = tables.segments(h)[1:]
    assert [
        [
            s["id"],
            s["from"],
            s["to"],
            tables.data_num(s["length_m"]),
            str(len(s["wires"])),
            ";".join(s["wires"]),
        ]  # fmt: skip
        for s in found["segments"]
    ] == rows
    assert [
        (b["id"], b["name"], [(x["segment"], x["connectors"]) for x in b["sides"]])
        for b in found["branch_points"]
    ] == tables.branch_sides(h)
    # the same data the core function gives, twice the same, no path in it
    assert found == {"ok": True, **routing_tree(load_project(flatsat).project, "W005").to_dict()}
    code, again, _err = cli(capsys, "routing", flatsat, "W005", "--json")
    assert code == 0 and json.loads(again) == found and str(flatsat) not in again


def test_a_straight_harness_says_it_does_not_branch(
    flatsat: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _err = cli(capsys, "routing", flatsat, "W003")
    assert code == 0
    assert out.splitlines()[1] == "It does not branch (no branch point) and has 1 segment."
    assert "W003-L1: W003-P1 (PDU2-J11) to W003-P2 (HTR2-J01), 0.5 m" in out
    assert "Branch points" not in out
    found = doc(capsys, "routing", flatsat, "W003")
    assert found["branches"] is False and found["branch_points"] == []
    assert [s["id"] for s in found["segments"]] == ["W003-L1"]


def test_a_harness_without_segments(copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = load_project(copy).project
    project.harnesses["W003"] = evolve(project.harnesses["W003"], segments=[])
    save_project(project, copy)
    code, out, _err = cli(capsys, "routing", copy, "W003")
    assert code == 0
    assert out.splitlines()[1] == "It does not branch (no branch point) and has no segments."
    assert "Segments (" not in out
    found = doc(capsys, "routing", copy, "W003")
    assert found["segments"] == [] and found["wires_without_route"] == []


def test_an_unknown_harness_is_an_error(flatsat: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for extra in ((), ("--json",)):
        code, out, err = cli(capsys, "routing", flatsat, "W099", *extra)
        assert code == 2 and out == ""
        assert err.strip() == "error: harness W099 does not exist."


def test_where_a_length_came_from(copy: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    lengths = tmp_path / "cad-lengths.csv"
    lengths.write_text("harness,segment,length\nW005,W005-L3,1100\nW005,W005-L4,1300\n")
    assert cli(capsys, "import-lengths", copy, lengths)[0] == 0
    found = {s["id"]: s for s in doc(capsys, "routing", copy, "W005")["segments"]}
    assert found["W005-L3"]["source"] == "imported" and found["W005-L3"]["length_m"] == 1.1
    assert found["W005-L3"]["source_text"] == "imported from cad-lengths.csv, row 2, kept by Generate"  # fmt: skip
    assert found["W005-L4"]["source_text"] == "imported from cad-lengths.csv, row 3, kept by Generate"  # fmt: skip
    assert found["W005-L2"]["source"] == "entered"

    # a length changed after the import is entered; a length taken away is not set
    project = load_project(copy).project
    h = project.harnesses["W005"]
    segs = [
        evolve(s, length_m=1.2)
        if s.id == "W005-L3"
        else evolve(s, length_m=None)
        if s.id == "W005-L5"
        else s  # fmt: skip
        for s in h.segments
    ]
    project.harnesses["W005"] = evolve(h, segments=segs)
    save_project(project, copy)
    found_doc = doc(capsys, "routing", copy, "W005")
    found = {s["id"]: s for s in found_doc["segments"]}
    assert (found["W005-L3"]["source"], found["W005-L3"]["source_text"]) == ("entered", "entered, kept by Generate")  # fmt: skip
    assert (found["W005-L5"]["source"], found["W005-L5"]["kept_by_generate"]) == ("unset", False)
    assert found["W005-L5"]["source_text"] == "not set" and found["W005-L5"]["length_m"] is None
    assert found_doc["lengths_missing"] == ["W005-L5"]
    code, out, _err = cli(capsys, "routing", copy, "W005")
    assert "W005-L5: W005-P4 (GPSU1-J01) to W005-B2 (Branch Y), no length, not set" in out
    assert "Segments without a length: W005-L5." in out


def test_a_drawn_harness_has_no_length_kept_by_generate(flatsat: Path) -> None:
    project = load_project(flatsat).project
    h = evolve(project.harnesses["W005"], generated=False)
    src = length_source(project, h, h.segments[0])
    assert (src.source, src.kept_by_generate, src.text) == ("entered", False, "entered")


def test_wires_with_no_route_are_listed(copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = load_project(copy).project
    h = project.harnesses["W005"]
    project.harnesses["W005"] = evolve(h, segments=[s for s in h.segments if s.id != "W005-L3"])
    save_project(project, copy)
    found = doc(capsys, "routing", copy, "W005")
    assert found["wires_without_route"] == ["W005-001", "W005-002"]  # PCDU1-J01 is cut off
    code, out, _err = cli(capsys, "routing", copy, "W005")
    assert "Wires with no single path through the segments (no length from them): W005-001, W005-002." in out  # fmt: skip


# ---- explain ------------------------------------------------------------------------------------


def test_explain_a_segment(flatsat: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = cli(capsys, "explain", flatsat, "W005-L3")
    assert code == 0 and "Nothing could be explained" not in err
    assert out.startswith("Segment W005-L3 of harness W005. Length: 1 m\n")
    assert "    From = W005-P2 (PCDU1-J01)   [segment W005-L3: from_node]" in out
    assert "    To = W005-B1 (Branch X)   [segment W005-L3: to_node]" in out
    assert "[segment W005-L3: length_m, entered, kept by Generate]" in out
    assert "Their IDs: 2 wires = W005-001, W005-002" in out
    assert out.rstrip().endswith("Model page: docs/models/wire-length.md")
    (found,) = json.loads(cli(capsys, "explain", flatsat, "W005-L3", "--json")[1])
    assert list(found) == list(SHAPES["explain OBJECT"])
    assert found["id"] == "segment" and found["value"] == 1.0 and found["unit"] == "m"
    steps = {s["label"]: s for s in found["steps"]}
    assert steps["Wires through it"]["value"] == 2
    assert steps["Where the length came from"]["text"] == "entered, kept by Generate"
    # the harness may be named in front, as for a shield group
    assert [d.subject for d in explain_object(load_project(flatsat).project, "W005.W005-L3")] == [
        "Segment W005-L3 of harness W005"
    ]


def test_explain_a_segment_without_a_length(copy: Path, capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    project = load_project(copy).project
    h = project.harnesses["W005"]
    segs = [evolve(s, length_m=None) if s.id == "W005-L3" else s for s in h.segments]
    project.harnesses["W005"] = evolve(h, segments=segs)
    save_project(project, copy)
    (found,) = json.loads(cli(capsys, "explain", copy, "W005-L3", "--json")[1])
    assert found["value"] is None and found["missing"] == ["the length of segment W005-L3 (import-lengths)"]  # fmt: skip


def test_explain_a_branch_point(flatsat: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _err = cli(capsys, "explain", flatsat, "W005-B2")
    assert code == 0
    assert out.startswith(
        "Branch point W005-B2 (Branch Y) of harness W005. Connectors beyond it, by segment: "
        "W005-L1: W005-P1, W005-P2, W005-P3; W005-L5: W005-P4; W005-L6: W005-P5; W005-L7: W005-P6\n"
    )
    assert "    Segment W005-L1 = 0.5 m   [to W005-B1 (Branch X); length entered, kept by Generate]" in out  # fmt: skip
    assert "W005-P1 (OBC1-J13), W005-P2 (PCDU1-J01), W005-P3 (TRX1-J03)" in out
    (found,) = json.loads(cli(capsys, "explain", flatsat, "W005-B2", "--json")[1])
    assert list(found) == [*SHAPES["explain OBJECT"][:-1], "text", "model_page"]
    assert found["id"] == "branch-point" and found["value"] is None
    assert [i["name"] for i in found["inputs"]] == [f"Segment W005-L{n}" for n in (1, 5, 6, 7)]
    assert found["model_page"] == "docs/models/wire-length.md"


def test_the_two_kinds_are_on_demand_only(flatsat: Path) -> None:
    project = load_project(flatsat).project
    assert {"segment", "branch-point"} <= ON_DEMAND <= set(KINDS)
    assert not {d.id for d in explain_all(project)} & {"segment", "branch-point"}
    # a harness keeps its derivations: the segments are explained one by one
    assert not {d.id for d in explain_object(project, "W005")} & {"segment", "branch-point"}
