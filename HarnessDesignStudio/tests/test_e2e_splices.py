# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-HARN-04. The end-to-end case of the splices (format 3, M6a; section 9 of `docs/ait/DESIGN_2.3_BRANCHING.md`):
a power line from one device connector to two others through one splice, through the command line
wherever a command exists and through the plans the editor runs (`History`) where none does (no
command places a splice: section 6.6). The splice part comes from the template
`splice-parts-EXAMPLE.csv` by `import-parts`. Then `validate`, `check`, `verify`, `drc`, `export
--drawings`, `verify --outputs`, `routing --json`, `explain` of the splice; a second export
changes no byte. Example data only."""

import json
from pathlib import Path

import pytest

from harness_design_studio.cli.main import main
from harness_design_studio.core.commands import History
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.manual_harness import plan_add_connector, plan_new_harness
from harness_design_studio.core.model import evolve
from harness_design_studio.core.samples import mini3
from harness_design_studio.core.splices import plan_add_splice, plan_splice_wire
from harness_design_studio.core.wires import plan_add_wire
from harness_design_studio.resources import examples_path

TEMPLATE = Path(str(examples_path())) / "templates" / "splice-parts-EXAMPLE.csv"


def _project(root: Path, capsys: pytest.CaptureFixture[str]) -> str:
    p = mini3()
    generate_project(p)
    for cid in ("PCDU-J02", "OBC-J02", "OBC-J03"):
        c = p.connectors[cid]
        p.connectors[cid] = evolve(c, pins=[evolve(c.pins[0], signal="PWR"), *c.pins[1:]])
    generate_project(p)
    save_project(p, root)
    assert main(["import-parts", str(root), str(TEMPLATE), "--pending", "Review"]) == 0
    p = load_project(root).project
    assert p.parts["EX-SPLICE-1"].category == "splice"
    history = History(p)
    ops, hid = plan_new_harness(p, "Power Y")
    history.execute("harness", ops)
    plugs = []
    for box in ("PCDU-J02", "OBC-J02", "OBC-J03"):
        ops, cid = plan_add_connector(p, hid, mates_with=box)
        history.execute("plug", ops)
        plugs.append(cid)
    history.execute("wire", plan_add_wire(p, hid, plugs[0], "1", plugs[1], "1", signal="PWR"))
    ops, sid = plan_add_splice(p, hid, "EX-SPLICE-1", termination="crimp")
    history.execute("splice", ops)
    ops, _new = plan_splice_wire(p, f"{hid}-001", sid)
    history.execute("splice the wire", ops)
    history.execute("wire", plan_add_wire(p, hid, sid, "1", plugs[2], "1", signal="PWR"))
    save_project(p, root)
    capsys.readouterr()
    return hid


def test_a_power_line_through_one_splice_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "p"
    hid = _project(root, capsys)
    assert main(["generate", str(root)]) == 0  # the parts changed; Generate keeps the harness
    assert hid in load_project(root).project.harnesses
    for argv in (["validate", str(root)], ["check", str(root)], ["verify", str(root)]):
        assert main(argv) == 0, argv
    capsys.readouterr()
    assert main(["drc", str(root), "--json"]) in (0, 1)
    findings = json.loads(capsys.readouterr().out)["findings"]
    assert not [f for f in findings if f["rule"] == "pin-shared"]
    out = root / "outputs"
    assert main(["export", str(root), "--drawings"]) == 0
    assert main(["verify", str(root), "--outputs"]) == 0
    tests = (out / "harnesses" / hid / "tests.csv").read_text(encoding="utf-8")
    assert f"{hid}-P1.1,{hid}-P3.1 via {hid}-X1" in tests
    first = {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    capsys.readouterr()
    assert main(["routing", str(root), hid, "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert [x["id"] for x in doc["splices"]] == [f"{hid}-X1"]
    assert doc["splices"][0]["nodes"][0]["wires"] == [f"{hid}-001", f"{hid}-002", f"{hid}-003"]
    assert main(["explain", str(root), f"{hid}-X1"]) == 0
    assert f"node 1: {hid}-P1.1, {hid}-P2.1, {hid}-P3.1" in capsys.readouterr().out
    assert main(["export", str(root), "--drawings"]) == 0
    again = {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    assert again == first
