# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-HARN-03. The end-to-end case of 2.3.0, branching harnesses (D-243, section 9 of
`docs/ait/DESIGN_2.3_BRANCHING.md`, pull request 7), through the command line wherever a command
exists, and through the plans the editor runs (`History`) where none does (the tool has no command
that adds an interface or draws a harness).

The users' harness *DEV2 + DEV3 <-> DEV1 + DEV4*: a blank project; `import-pinout` of DEV1 to DEV4,
one connector each with two RS-422 ports; four interfaces DEV2 -> DEV1, DEV2 -> DEV4, DEV3 -> DEV1,
DEV3 -> DEV4. Generate in `per_connector_pair` (the mode of a project made before 2.4.0) gives four harnesses and two plugs on every connector;
`settings --set segmentation.mode="per_connector_group"` and Generate give one harness with four
plugs, two branch points and a trunk, and no warning. Then the lengths of the five segments
(`import-lengths`, one typed in as the Routing table does), `export`, `segments.csv`, the sheets
*Routing* and *Segments*, `verify --outputs`, `routing --json`, `explain` of a segment, a branch
point, a wire and the harness; a second Generate and a second export change no byte, and the same
steps in two folders give the same project files. The RS-422 x3 case of 2.1.0 in the new mode gives
one plug on J1.

A drawn harness: a cable from DEV2-J01 to DEV1-J01, a leg to DEV4-J01, a second cable from DEV3-J01
to DEV1-J01 (two plugs on DEV1-J01), *Join into one harness*, undo and redo; the refusals a person
meets; the lengths; the three integrity warnings; the mark `branch:<ID>` through save and load
(outside the model hash) and through `merge-fix`, which renames it with its harness.

Example data only."""

import json
import shutil
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from harness_design_studio.core import branching
from harness_design_studio.core.commands import History, Put
from harness_design_studio.core.edit import EditError, ops_add_interface
from harness_design_studio.core.integrity import check_integrity
from harness_design_studio.core.io.layout import model_hash
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.manual_harness import plan_cable_from_port, plan_plug_loose_end
from harness_design_studio.core.model import DiagramMark, Project
from harness_design_studio.core.wires import plan_group_wires
from tests.test_e2e_device_library import comparable
from tests.test_e2e_rs422x3 import J1, add_interfaces, files, imported, ports_used, run
from tests.test_e2e_rs422x3 import with_port_column as rs422x3_pinout
from tests.test_gitinfo import needs_git
from tests.test_merge_fix import git

RS422 = ("TX+", "TX-", "RX+", "RX-")
DEVICES = ("DEV1", "DEV2", "DEV3", "DEV4")
EDGES = (("DEV2", "DEV1"), ("DEV2", "DEV4"), ("DEV3", "DEV1"), ("DEV3", "DEV4"))
MODE = 'segmentation.mode="per_connector_group"'
# the lengths a person measured on the mock-up, in millimetres (harness, segment, length)
LENGTHS = "harness,segment,length\n" + "".join(
    f"W001,W001-L{n},{mm}\n" for n, mm in enumerate((1500, 300, 450, 250, 350), start=1)
)
ROUTING = ("segment_tree_split", "branch_point_unused", "shield_across_branch")


def ok(capsys: pytest.CaptureFixture[str], *args: object) -> str:
    """One command that must end with exit code 0; what it printed."""
    code, out = run(capsys, *(str(a) for a in args))
    assert code == 0, out
    return out


def pinout(folder: Path) -> Path:
    """One connector J1 with two RS-422 ports, RS422_1 on pins 1-4 and RS422_2 on pins 5-8."""
    rows = ["Connector,Pin,Port,Signal,Mode"]
    for k in (1, 2):
        rows += [f"J1,{4 * (k - 1) + n + 1},RS422_{k},{s},fixed" for n, s in enumerate(RS422)]
    path = folder / "dev.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def four_devices(folder: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    """A blank project with DEV1 to DEV4, each with the connector J1 of `pinout`, in
    `per_connector_pair` as a project made before 2.4.0 (a new blank project starts in
    `per_connector_group` since then, D-247): the case of 2.3.0 switches the mode itself."""
    proj = folder / "proj"
    ok(capsys, "new", proj, "--template", "blank")
    ok(capsys, "settings", proj, "--set", 'segmentation.mode="per_connector_pair"')
    csv = pinout(folder)
    for dev in DEVICES:
        out = ok(
            capsys, "import-pinout", proj, csv, "--device", dev, "--new-device", f"Device {dev[-1]}",
            "--subsystem", "avionics", "--default-part", "EX-MICROD-25-F", "--gender", "female",
        )  # fmt: skip
        assert f"{dev}-J01: OK added (8 pin(s))" in out
    return proj


def harness_shape(p: Project, hid: str) -> tuple[Any, ...]:
    h = p.harnesses[hid]
    return (
        h.name,
        [(c.id, c.mates_with) for c in h.connectors],
        [(b.id, b.name) for b in h.branch_points],
        [(s.id, s.from_node, s.to_node) for s in h.segments],
    )


def warnings(p: Project) -> list[tuple[str, str | None]]:
    return sorted((i.code, i.object_id) for i in check_integrity(p) if i.severity == "warning")


def sheet(path: Path, name: str) -> list[tuple[Any, ...]]:
    # a read-only workbook keeps its file open until it is closed, and on Windows an open file
    # cannot be written again (the next export would fail)
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        return list(wb[name].iter_rows(values_only=True))
    finally:
        wb.close()


def sheet_names(path: Path) -> list[str]:
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


# ---- the users' harness, made by Generate ---------------------------------------------------------


def users_harness(folder: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    """The whole sequence of the users' harness in `folder`; the project folder."""
    proj = four_devices(folder, capsys)
    p = load_project(proj).project
    history = History(p)
    for n, (a, b) in enumerate(EDGES, start=1):
        ops, iid = ops_add_interface(p, "rs422", a, b)  # Guided: the tool chooses the connectors
        history.execute(f"Add {iid}", ops)
        assert iid == f"IF-00{n}"
    save_project(p, proj)

    # per_connector_pair: one harness per pair of connectors, two plugs on every connector
    out = ok(capsys, "generate", proj)
    assert "4 added" in out and out.count("[box_connector_shared]") == 4
    assert "or set segmentation.mode to per_connector_group for one harness that branches" in out
    out = ok(capsys, "check", proj)
    assert out.count("WARNING box_connector_mated_twice") == 4

    # the new choice: one harness that branches; the drafts are taken over: W001 is kept with its
    # plugs W001-P1 (DEV1-J01) and W001-P2 (DEV2-J01), and the other plugs are numbered after them
    assert "1 value(s) set." in ok(capsys, "settings", proj, "--set", MODE)
    out = ok(capsys, "generate", proj)
    assert "0 added, 1 changed, 0 unchanged, 3 removed" in out and "box_connector_shared" not in out
    p = load_project(proj).project
    assert list(p.harnesses) == ["W001"]
    assert harness_shape(p, "W001") == (
        "DEV1-J01 + DEV4-J01 to DEV2-J01 + DEV3-J01",
        [("W001-P1", "DEV1-J01"), ("W001-P2", "DEV2-J01"), ("W001-P3", "DEV4-J01"), ("W001-P4", "DEV3-J01")],
        [("W001-B1", "Branch X"), ("W001-B2", "Branch Y")],
        [("W001-L1", "W001-B1", "W001-B2"), ("W001-L2", "W001-P1", "W001-B1"), ("W001-L3", "W001-P3", "W001-B1"), ("W001-L4", "W001-P2", "W001-B2"), ("W001-L5", "W001-P4", "W001-B2")],
    )  # fmt: skip
    assert len(p.harnesses["W001"].wires) == 16
    assert "0 error(s), 0 warning(s)." in ok(capsys, "check", proj)
    out = ok(capsys, "routing", proj, "W001")
    assert "It branches at 2 branch points and has 5 segments." in out
    assert "Segments without a length: W001-L1, W001-L2, W001-L3, W001-L4, W001-L5." in out

    # the lengths: four from the mock-up's table, then one typed into the Routing table
    lengths = folder / "lengths.csv"
    lengths.write_text(LENGTHS, encoding="utf-8")
    out = ok(capsys, "import-lengths", proj, lengths, "--unit", "mm")
    assert "row 2: OK W001 / W001-L1: 1500 mm = 1.5 m" in out and "5 length(s) ready" in out
    p = load_project(proj).project
    History(p).execute("Length", branching.plan_set_segment_length(p, "W001", "W001-L5", "0.4"))
    save_project(p, proj)
    assert "0 added, 1 changed" in ok(capsys, "generate", proj)
    p = load_project(proj).project
    by_id = {s.id: s.length_m for s in p.harnesses["W001"].segments}
    assert by_id == {
        "W001-L1": 1.5,
        "W001-L2": 0.3,
        "W001-L3": 0.45,
        "W001-L4": 0.25,
        "W001-L5": 0.4,
    }
    wire = {w.id: w for w in p.harnesses["W001"].wires}
    # DEV2-J01 to DEV1-J01: L4 + L1 + L2 (no service loop set in the blank project)
    assert wire["W001-001"].length_m == pytest.approx(2.05)
    assert wire["W001-016"].length_m == pytest.approx(2.35)  # DEV3 to DEV4: L5 + L1 + L3

    # the outputs
    out = ok(capsys, "export", proj)
    assert "27 files written" in out
    first = files(proj / "outputs")
    folder_w = proj / "outputs" / "harnesses" / "W001"
    rows = (folder_w / "segments.csv").read_text(encoding="utf-8").splitlines()
    assert rows[2:] == [
        "Segment,From,To,Length (m),Number of wires,Wires",
        "W001-L1,W001-B1,W001-B2,1.5,16," + ";".join(f"W001-{n:03d}" for n in range(1, 17)),
        "W001-L2,W001-P1,W001-B1,0.3,8,W001-001;W001-002;W001-003;W001-004;W001-009;W001-010;W001-011;W001-012",
        "W001-L3,W001-P3,W001-B1,0.45,8,W001-005;W001-006;W001-007;W001-008;W001-013;W001-014;W001-015;W001-016",
        "W001-L4,W001-P2,W001-B2,0.25,8,W001-001;W001-002;W001-003;W001-004;W001-005;W001-006;W001-007;W001-008",
        "W001-L5,W001-P4,W001-B2,0.4,8,W001-009;W001-010;W001-011;W001-012;W001-013;W001-014;W001-015;W001-016",
    ]  # fmt: skip
    build = folder_w / "W001_build.xlsx"
    names = sheet_names(build)
    assert names[:5] == ["Start here", "Cut list", "Routing", "Production", "Connectors"]
    routing = sheet(build, "Routing")
    assert routing[0] == (
        "Segment", "From", "To", "Length (m), rear or branch centre", "Number of wires", "Wires"
    )  # fmt: skip
    assert str(routing[-3][0]).startswith("Lengths run from the rear of a connector")
    assert str(routing[-1][0]).startswith('"Locked" is a length a person typed')
    assert routing[1][:5] == ("W001-L1", "W001-B1", "W001-B2", 1.5, 16)
    assert routing[7][:3] == ("Branch point", "Name", "Connectors beyond it, by segment")
    assert routing[8][:3] == (
        "W001-B1",
        "Branch X",
        "W001-L1: W001-P2, W001-P4; W001-L2: W001-P1; W001-L3: W001-P3",
    )
    assert any(r[:1] == ("Routing",) for r in sheet(build, "Start here"))
    tables = folder_w / "W001.xlsx"
    assert sheet_names(tables)[-1] == "Segments"
    assert [list(map(str, r)) for r in sheet(tables, "Segments")] == [
        r.split(",") for r in rows[2:]
    ]
    out = ok(capsys, "verify", proj, "--outputs")
    assert "4 interfaces and 16 wires checked: 0 error(s)" in out
    assert "Open: 0 error(s)" in ok(capsys, "drc", proj)

    # the command line reads the tree: routing and explain
    found = json.loads(ok(capsys, "routing", proj, "W001", "--json"))
    assert found["branches"] is True and found["lengths_missing"] == []
    assert found["wires_without_route"] == []
    sources = {s["id"]: (s["source"], s["kept_by_generate"]) for s in found["segments"]}
    assert sources == {
        "W001-L1": ("imported", True),
        "W001-L2": ("imported", True),
        "W001-L3": ("imported", True),
        "W001-L4": ("imported", True),
        "W001-L5": ("entered", True),
    }
    assert [b["id"] for b in found["branch_points"]] == ["W001-B1", "W001-B2"]
    out = ok(capsys, "explain", proj, "W001-L1")
    assert out.startswith("Segment W001-L1 of harness W001. Length: 1.5 m\n")
    assert "[segment W001-L1: length_m, imported from lengths.csv, row 2, kept by Generate]" in out
    assert "Wires through it: the wires whose one path between their connectors" in out
    out = ok(capsys, "explain", proj, "W001-B2")
    assert out.startswith(
        "Branch point W001-B2 (Branch Y) of harness W001. Connectors beyond it, by segment: "
        "W001-L1: W001-P1, W001-P3; W001-L4: W001-P2; W001-L5: W001-P4\n"
    )
    out = ok(capsys, "explain", proj, "W001-001")
    assert "Path through the segments: 0.3 + 1.5 + 0.25 = 2.05 m" in out
    out = ok(capsys, "explain", proj, "W001")
    assert (
        "IF-001, IF-002, IF-003 and IF-004 share a harness because they plug into DEV1-J01, "
        "DEV2-J01, DEV3-J01 and DEV4-J01; mode per_connector_group; ends X: DEV1-J01, DEV4-J01, "
        "Y: DEV2-J01, DEV3-J01"
    ) in out

    # a second Generate changes no file; a second export writes the same bytes
    before = files(proj)
    assert "0 added, 0 changed, 1 unchanged" in ok(capsys, "generate", proj)
    assert files(proj) == before
    ok(capsys, "export", proj)
    assert files(proj / "outputs") == first
    return proj


def test_the_users_harness_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    one = users_harness(tmp_path / "one", capsys)
    two = users_harness(tmp_path / "two", capsys)
    # the same steps in two folders: the same project files (the journal without its times)
    assert comparable(two) == comparable(one)
    for name, data in files(one).items():
        assert str(tmp_path).encode() not in data, name


def test_rs422x3_in_the_new_mode_gives_one_plug_on_j1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The case of 2.1.0 (`tests/test_e2e_rs422x3.py`): with `per_connector_group` the three
    interfaces on J1 become one harness, one plug on J1 and one on each star tracker, port k for
    IF-k, and no warning of a second plug."""
    proj = imported(tmp_path, capsys, rs422x3_pinout())
    add_interfaces(proj)
    ok(capsys, "settings", proj, "--set", MODE)
    out = ok(capsys, "generate", proj)
    assert "1 added" in out and "box_connector_shared" not in out
    p = load_project(proj).project
    assert harness_shape(p, "W001") == (
        "OBC1-J01 to STR1-J01 + STR2-J01 + STR3-J01",
        [("W001-P1", J1), ("W001-P2", "STR1-J01"), ("W001-P3", "STR2-J01"), ("W001-P4", "STR3-J01")],
        [("W001-B2", "Branch Y")],
        [("W001-L1", "W001-P1", "W001-B2"), ("W001-L2", "W001-P2", "W001-B2"), ("W001-L3", "W001-P3", "W001-B2"), ("W001-L4", "W001-P4", "W001-B2")],
    )  # fmt: skip
    assert ports_used(proj) == {f"IF-00{k}": {f"RS422_{k}"} for k in (1, 2, 3)}
    ok(capsys, "export", proj)
    assert (proj / "outputs" / "harnesses" / "W001" / "segments.csv").is_file()
    assert "3 interfaces and 12 wires checked: 0 error(s)" in ok(
        capsys, "verify", proj, "--outputs"
    )
    out = ok(capsys, "drc", proj)
    assert "Open: 0 error(s)" in out and "cable plugs on it" not in out


# ---- a harness drawn by hand ----------------------------------------------------------------------


def draw(p: Project, history: History, port: str, far: str, pairs: list[tuple[str, str]]) -> str:
    """A cable from `port` (the pins of `pairs`) plugged into `far`, as the diagram does it."""
    made = plan_cable_from_port(p, port, pin_ids=[a for a, _b in pairs])
    history.execute("Cable", made.ops)
    history.execute("Plug", plan_plug_loose_end(p, made.harness_id, made.loose_id, far, pairs))
    return made.harness_id


def test_a_drawn_harness_with_a_leg_and_a_join(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = four_devices(tmp_path, capsys)
    p = load_project(proj).project
    history = History(p)
    same = [(x, x) for x in "1234"]
    assert draw(p, history, "DEV2-J01", "DEV1-J01", same) == "W001"

    # a second cable from the plugged port DEV2-J01 is a new leg of W001, plugged into DEV4-J01
    leg = branching.plan_add_leg(p, "W001", "DEV2-J01")
    history.execute("Leg", leg.ops)
    assert (leg.loose_id, leg.branch_id) == ("W001-P3", "W001-B1")
    pairs = [(x, x) for x in "5678"]
    history.execute("Plug", plan_plug_loose_end(p, "W001", leg.loose_id, "DEV4-J01", pairs))
    with pytest.raises(EditError, match="W001-P1 has no free pin with a signal for a new leg"):
        branching.plan_add_leg(p, "W001", "DEV2-J01")

    # a cable from DEV3-J01 to the free port RS422_2 of DEV1-J01: two plugs on DEV1-J01
    assert draw(p, history, "DEV3-J01", "DEV1-J01", [("1", "5"), ("2", "6"), ("3", "7"), ("4", "8")]) == "W002"  # fmt: skip
    assert ("box_connector_mated_twice", "DEV1-J01") in warnings(p)
    fix = branching.plug_fix(p, "DEV1-J01")
    assert fix is not None and (fix.kind, fix.harness_ids) == ("join", ("W001", "W002"))
    two = dict(p.harnesses)

    # Join into one harness: the users' shape, drawn: four connectors, two branch points
    history.execute("Join", branching.plan_join_harnesses(p, "W001", "W002"))
    assert list(p.harnesses) == ["W001"]
    joined = harness_shape(p, "W001")
    assert joined[1:] == (
        [("W001-P1", "DEV2-J01"), ("W001-P2", "DEV1-J01"), ("W001-P3", "DEV4-J01"), ("W002-P1", "DEV3-J01")],
        [("W001-B1", "Branch 1"), ("W001-B2", "Branch 2")],
        [("W001-L1", "W001-P1", "W001-B1"), ("W001-L2", "W001-B1", "W001-B2"), ("W001-L3", "W001-B1", "W001-P3"), ("W001-L4", "W001-P2", "W001-B2"), ("W001-L5", "W001-B2", "W002-P1")],
    )  # fmt: skip
    assert warnings(p) == []
    # undo gives the two harnesses and the warning back; redo joins them again
    history.undo()
    assert p.harnesses == two and ("box_connector_mated_twice", "DEV1-J01") in warnings(p)
    history.redo()
    assert harness_shape(p, "W001") == joined and warnings(p) == []

    # what a person meets on the tree
    with pytest.raises(EditError, match="would close a loop"):
        branching.plan_add_segment(p, "W001", "W001-P1", "W001-B2")
    with pytest.raises(EditError, match="W001-001"):  # it is on the only path of wires
        branching.plan_delete_branch_point(p, "W001", "W001-B2")
    with pytest.raises(EditError, match="end on different connectors"):
        plan_group_wires(p, ["W001-001", "W001-005"], "shielded_pair")
    history.execute("Pair", plan_group_wires(p, ["W001-001", "W001-002"], "twisted_pair"))

    # an unused branch point: two warnings until it is joined to the tree, or undone
    ops, spare = branching.plan_add_branch_point(p, "W001", "Spare")
    history.execute("Branch point", ops)
    assert warnings(p) == [("branch_point_unused", spare), ("segment_tree_split", "W001")]
    history.undo()
    assert warnings(p) == []

    # the lengths, typed in the Routing table: a drawn wire is its path, with no service loop
    for n, metres in enumerate((0.25, 1.5, 0.45, 0.3, 0.35), start=1):
        history.execute(
            "Length", branching.plan_set_segment_length(p, "W001", f"W001-L{n}", metres)
        )
    save_project(p, proj)
    out = ok(capsys, "check", proj)
    assert "0 error(s), 0 warning(s)." in out
    found = json.loads(ok(capsys, "routing", proj, "W001", "--json"))
    assert found["origin"] == "drawn" and found["lengths_missing"] == []
    assert {s["source"] for s in found["segments"]} == {"entered"}
    out = ok(capsys, "explain", proj, "W001-001")
    assert "0.25 + 1.5 + 0.3 = 2.05 m" in out
    ok(capsys, "export", proj)
    assert (proj / "outputs" / "harnesses" / "W001" / "segments.csv").is_file()
    assert "0 error(s)" in ok(capsys, "verify", proj, "--outputs")

    # the place of a branch point on the diagram: a mark, saved and read, outside the hash
    p = load_project(proj).project
    before = model_hash(p)
    History(p).execute("Move", [Put("diagram_marks", DiagramMark(id="branch:W001-B2", dx=40.0, dy=-20.0))])  # fmt: skip
    assert model_hash(p) == before
    save_project(p, proj)
    marks = json.loads((proj / "diagram" / "marks.json").read_text(encoding="utf-8"))["marks"]
    assert marks == [{"dx": 40.0, "dy": -20.0, "id": "branch:W001-B2"}]
    assert load_project(proj).project.diagram_marks["branch:W001-B2"].dx == 40.0
    assert "0 error(s)" in ok(capsys, "verify", proj, "--outputs")  # no output is out of date

    # a shield group across the branch, written into the file by hand: a warning, not an error
    path = proj / "physical" / "harnesses" / "W001.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["shields"].append({"id": "W001-S9", "kind": "shielded_pair", "wire_ids": ["W001-003", "W001-005"], "end_a": "floating", "end_b": "floating"})  # fmt: skip
    # newline="\n": on Windows the text mode would write CR LF, and the check would also warn
    # `not_canonical` (the file is not in the tool's own form)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    out = ok(capsys, "check", proj)
    assert "WARNING shield_across_branch" in out and "0 error(s), 1 warning(s)." in out


@needs_git
def test_merge_fix_renames_the_place_of_a_branch_point_with_its_harness(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two people each draw a harness with a leg on their own Git branch: both get W001 and
    W001-B1, and each drags the branch point. `merge-fix` keeps this branch's W001, renames the
    other's to W002, and its mark `branch:W001-B1` to `branch:W002-B1`."""
    git(tmp_path, "init", "-q", "-b", "main")
    proj = four_devices(tmp_path, capsys)
    shutil.move(proj, tmp_path / "design")
    proj = tmp_path / "design"
    (tmp_path / "dev.csv").unlink()
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "start")

    def one_side(name: str, port: str, far: str, dx: float) -> None:
        git(tmp_path, "checkout", "-q", "main")
        git(tmp_path, "checkout", "-q", "-b", name)
        p = load_project(proj).project
        history = History(p)
        hid = draw(p, history, port, far, [(x, x) for x in "1234"])
        leg = branching.plan_add_leg(p, hid, port)
        history.execute("Leg", leg.ops)
        mark = DiagramMark(id=f"branch:{leg.branch_id}", dx=dx, dy=0.0)
        history.execute("Move", [Put("diagram_marks", mark)])
        save_project(p, proj)
        git(tmp_path, "add", "-A")
        git(tmp_path, "commit", "-q", "-m", name)

    one_side("ann", "DEV2-J01", "DEV1-J01", 30.0)
    one_side("bob", "DEV3-J01", "DEV4-J01", -5.0)
    git(tmp_path, "checkout", "-q", "bob")
    assert git(tmp_path, "merge", "--no-edit", "ann", check=False).returncode != 0
    out = ok(capsys, "merge-fix", proj)
    assert "diagram/marks.json: diagram mark branch:W001-B1 -> branch:W002-B1" in out
    marks = {m["id"]: m["dx"] for m in json.loads((proj / "diagram" / "marks.json").read_text())["marks"]}  # fmt: skip
    assert marks == {"branch:W001-B1": -5.0, "branch:W002-B1": 30.0}
    p = load_project(proj).project
    assert [(h.id, h.connectors[0].mates_with) for h in p.harnesses.values()] == [
        ("W001", "DEV3-J01"),
        ("W002", "DEV2-J01"),
    ]
    assert [b.id for b in p.harnesses["W002"].branch_points] == ["W002-B1"]
    assert "0 error(s)" in ok(capsys, "check", proj)
