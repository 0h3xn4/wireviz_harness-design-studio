# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The checks every example passes (design of 5.1.0, `docs/ait/DESIGN_5.1_FEATURE_TEMPLATES.md`
section 5.3, REQ-EX-01), and the facts of each feature example (section 4).

Every listed example opens without errors and `check` finds 0 errors in a copy made by `new`. A
feature example also gives 0 warnings in `check`, nothing to do for Generate, no open error in
`drc` and only the baseline findings plus the ones its page names, an export that `verify
--outputs` passes and a second export that is byte for byte the same. That the shipped folders are
what the builders write is `tests/test_examples.py`.
"""

import csv
import io
import json
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.cli.main import main
from harness_design_studio.core import (
    build_data,
    checks,
    currents,
    integrity,
    links,
    manual_harness,
    shield_ends,
    splices,
    templates,
    wires,
)
from harness_design_studio.core.commands import History, SetConfig, apply_ops
from harness_design_studio.core.configcheck import with_value
from harness_design_studio.core.derive import explain_wire
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.generate import lengths
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.samples import new_project
from harness_design_studio.resources import examples_path

EXAMPLES = examples_path()
assert EXAMPLES is not None
PROJECTS = EXAMPLES / "projects"
FEATURES = [t.name for t in templates.in_group(templates.FEATURE)]

# What `drc` says of every project built from example parts and placeholder files (section 5.3):
# one `part-unapproved` per EX- part in use and the notes of the placeholder values a rule needs.
BASELINE = frozenset({"part-unapproved", "unchecked-config"})
# The open findings beyond the baseline that the page of each template names (section 4).
NAMED: dict[str, frozenset[str]] = {
    "full-connectors": frozenset(),
    "splice-by-hand": frozenset(),  # no `isolated` since part E (section 4.3)
    "splice-from-connection": frozenset(),
    "branching-harness": frozenset(),
    "loose-cable-end": frozenset(),  # the loose ends are the part-unapproved of TBD-CONNECTOR
    "shields-and-ends": frozenset(),  # the end without a place is an info of check, not of drc
    "lengths-to-the-face": frozenset(),
}


def run(capsys: pytest.CaptureFixture[str], *argv: str, rc: int = 0) -> dict[str, Any]:
    capsys.readouterr()
    assert main([*argv, "--json"]) == rc, argv
    doc: dict[str, Any] = json.loads(capsys.readouterr().out)
    return doc


def files(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_every_feature_example_names_its_findings() -> None:
    assert sorted(NAMED) == sorted(FEATURES)


@pytest.mark.parametrize("name", [t.name for t in templates.TEMPLATES])
def test_every_example_opens_and_check_finds_no_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    assert not load_project(PROJECTS / name).has_errors
    folder = tmp_path / name
    assert main(["new", str(folder), "--template", name]) == 0  # with a journal, as a person
    doc = run(capsys, "check", str(folder))
    assert doc["errors"] == 0, doc["issues"]
    if name in FEATURES:
        assert doc["warnings"] == 0, doc["issues"]


def _carries_numbers(name: str) -> bool:
    """An engineering number in a template: a config value other than a new project's, a length,
    a current or a voltage (design of 5.1.0, T6)."""
    p = load_project(PROJECTS / name).project
    fresh = new_project("x").config
    if any(key not in fresh or c.values != fresh[key].values for key, c in p.config.items()):
        return True
    if any(s.length_m is not None for h in p.harnesses.values() for s in h.segments):
        return True
    if any(pin.current_a is not None for c in p.connectors.values() for pin in c.pins):
        return True
    return any(
        i.max_current_a is not None or i.voltage_v is not None for i in p.interfaces.values()
    )


@pytest.mark.parametrize("name", FEATURES)
def test_a_feature_example_with_numbers_says_example_in_its_name(name: str) -> None:
    title = templates.template_info(name).title  # type: ignore[union-attr]
    assert title.endswith("(EXAMPLE)") == _carries_numbers(name), title


@pytest.mark.parametrize("name", FEATURES)
def test_a_feature_example_passes_generate_drc_export_and_verify(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    folder = tmp_path / name
    assert main(["new", str(folder), "--template", name]) == 0
    generated = bool(load_project(folder).project.harnesses)
    doc = run(capsys, "generate", str(folder))
    if generated:  # shipped generated: Generate has nothing to do
        assert doc["added"] == [] and doc["changed"] == [] and doc["removed"] == [], doc
    drc = run(capsys, "drc", str(folder))
    assert drc["open_errors"] == 0
    open_rules = {f["rule"] for f in drc["findings"] if not f["waived"]}
    assert open_rules == BASELINE | NAMED[name], sorted(open_rules)
    assert main(["export", str(folder)]) == 0
    verify = run(capsys, "verify", str(folder), "--outputs")
    assert not [i for i in verify["issues"] if i["severity"] == "error"], verify["issues"]
    assert main(["export", str(folder), "--out", str(tmp_path / "again")]) == 0
    assert files(tmp_path / "again") == files(folder / "outputs")  # deterministic


# ---- full-connectors (section 4.1) --------------------------------------------------------------


def test_full_connectors_uses_every_pin_of_every_device_connector() -> None:
    p = load_project(PROJECTS / "full-connectors").project
    assert sorted(p.units) == ["OBC1", "PCDU1", "TTC1"]
    boxes = [c for c in p.connectors.values() if c.role == "box"]
    assert len(boxes) == 6 and {c.part_id for c in boxes} == {"EX-MICROD-9-F", "EX-MICROD-9-M"}
    wired = {
        (end_c, end_p)
        for h in p.harnesses.values()
        for w in h.wires
        for end_c, end_p in ((w.from_connector, w.from_pin), (w.to_connector, w.to_pin))
    }
    mates = {c.mates_with: c.id for h in p.harnesses.values() for c in h.connectors}
    for c in boxes:
        assert len(c.pins) == 9, c.id
        for pin in c.pins:
            assert pin.signal and pin.fixed and pin.interface_id, (c.id, pin.id)
            assert (mates[c.id], pin.id) in wired, (c.id, pin.id)  # a wire on every pin
    assert len(p.interfaces) == 14 and all(
        not e.auto for i in p.interfaces.values() for e in i.endpoints
    )  # both connectors named: no `unconfirmed`
    assert len(p.harnesses) == 3 and sum(len(h.wires) for h in p.harnesses.values()) == 27
    for part in ("EX-MICROD-9-F", "EX-MICROD-9-M"):
        rows = p.parts[part].row_layout
        assert rows is not None and rows.rows == [["1", "2", "3", "4", "5"], ["6", "7", "8", "9"]]


def test_full_connectors_puts_each_interface_on_its_port() -> None:
    """Generate gives a named port in name order (`IF-001` would take `KA_…`); the builder puts
    each power interface on its port, so the main power is on the pins `MAIN_…`."""
    p = load_project(PROJECTS / "full-connectors").project
    for cid in ("PCDU1-J01", "OBC1-J01", "PCDU1-J02", "TTC1-J01"):
        by_port: dict[str, set[str]] = {}
        for pin in p.connectors[cid].pins:
            signal = pin.signal or ""
            port = signal.split("_")[0] if "_" in signal else ""
            if port:
                by_port.setdefault(port, set()).add(p.interfaces[pin.interface_id or ""].name)
        assert {k: len(v) for k, v in by_port.items()} == {"MAIN": 1, "KA": 1, "SURV": 1}, cid
        assert all(next(iter(by_port[k])).startswith(w) for k, w in (
            ("MAIN", "Main power"), ("KA", "Keep-alive power"), ("SURV", "Survival power"),
        )), (cid, by_port)  # fmt: skip


def test_full_connectors_has_no_spare_pin_in_the_box_pinouts(tmp_path: Path) -> None:
    folder = tmp_path / "p"
    assert main(["new", str(folder), "--template", "full-connectors", "--no-journal"]) == 0
    assert main(["export", str(folder)]) == 0
    assert main(["verify", str(folder), "--outputs"]) == 0
    text = (folder / "outputs" / "system" / "box_pinouts.csv").read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO("".join(ln for ln in text.splitlines(True) if not ln.startswith("#")))))  # fmt: skip
    assert len(rows) == 54
    assert {r["Spare"] for r in rows} == {"no"}
    assert all(r["Signal"] and r["Interface"] and r["Wires"] for r in rows)
    assert {r["Pin row"] for r in rows} == {"1", "2"}


def _table(path: Path) -> list[dict[str, str]]:
    """The rows of a written CSV table, without its comment lines."""
    text = path.read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO("".join(ln for ln in text.splitlines(True) if not ln.startswith("#")))))  # fmt: skip


def _exported(tmp_path: Path, name: str) -> Path:
    folder = tmp_path / name
    assert main(["new", str(folder), "--template", name, "--no-journal"]) == 0
    assert main(["export", str(folder)]) == 0
    assert main(["verify", str(folder), "--outputs"]) == 0
    return folder / "outputs"


def _splice_part_is_an_unapproved_example(p: Any) -> None:
    part = p.parts["EX-SPLICE-1"]
    assert part.category == "splice" and part.pin_count == 1
    assert part.unverified and part.approval != "approved"
    assert "EXAMPLE ONLY: not a real part" in (part.description or "")
    assert all(x.approval != "approved" for x in p.parts.values())  # nothing approved (T5)


# ---- splice-by-hand (section 4.3) ---------------------------------------------------------------


def test_splice_by_hand_draws_a_power_y_through_two_splices() -> None:
    p = load_project(PROJECTS / "splice-by-hand").project
    assert sorted(p.units) == ["OBC1", "PCDU1", "TTC1"] and not p.interfaces and not p.links
    _splice_part_is_an_unapproved_example(p)
    assert list(p.harnesses) == ["W001"]
    h = p.harnesses["W001"]
    assert h.name == "Power Y" and not h.generated
    assert [(c.id, c.part_id) for c in splices.splices_of(h)] == [
        ("W001-X1", "EX-SPLICE-1"),
        ("W001-X2", "EX-SPLICE-1"),
    ]
    assert splices.node_rows(h) == [
        ("W001-X1", "1", "EX-SPLICE-1", "crimp", ("W001-001", "W001-002", "W001-003")),
        ("W001-X2", "1", "EX-SPLICE-1", "crimp", ("W001-004", "W001-005", "W001-006")),
    ]
    plugs = {c.id: c.mates_with for c in h.connectors if c.role == "cable"}
    assert plugs == {"W001-P1": "PCDU1-J01", "W001-P2": "OBC1-J01", "W001-P3": "TTC1-J01"}
    looks = {(w.signal, w.gauge_awg, w.colour) for w in h.wires}
    assert looks == {("PWR", 22, "red"), ("PWR", 24, "red"), ("RTN", 22, "black"), ("RTN", 24, "black")}  # fmt: skip
    assert sorted(s.length_m or 0.0 for s in h.segments) == [0.02, 0.4, 0.6, 0.8]
    for uid, want in (("PCDU1", "out"), ("OBC1", "in"), ("TTC1", "in")):
        pins = p.connectors[f"{uid}-J01"].pins
        assert len(pins) == 9  # the whole nine-way connector, not only the two pins in use
        assert [(x.signal, x.direction) for x in pins[:2]] == [("PWR", want), ("RTN", want)]
        assert all(not x.signal for x in pins[2:])  # the other pins have no name


def test_splice_by_hand_has_no_isolated_device() -> None:
    """Part E: the three devices are in the harness plan of W001, so no note says they are not."""
    p = load_project(PROJECTS / "splice-by-hand").project
    assert not [f for f in checks.find(p) if f.rule == "isolated"]


def test_splice_by_hand_writes_the_splices_into_the_wire_list_and_the_tests(tmp_path: Path) -> None:
    out = _exported(tmp_path, "splice-by-hand")
    rows = _table(out / "harnesses" / "W001" / "wirelist.csv")
    assert {r["Wire"]: r["Via"] for r in rows} == {
        "W001-001": "W001-X1", "W001-002": "W001-X1", "W001-003": "W001-X1",
        "W001-004": "W001-X2", "W001-005": "W001-X2", "W001-006": "W001-X2",
    }  # fmt: skip
    tests = _table(out / "harnesses" / "W001" / "tests.csv")
    through = [t for t in tests if t["Type"] == "continuity"]
    assert len(through) == 6 and all(" via W001-X" in t["To"] for t in through)


# ---- splice-from-connection (section 4.4) -------------------------------------------------------


def test_splice_from_connection_has_a_junction_and_its_harness_the_splices() -> None:
    p = load_project(PROJECTS / "splice-from-connection").project
    assert sorted(p.units) == ["OBC1", "PCDU1"] and not p.interfaces
    _splice_part_is_an_unapproved_example(p)
    power, data = p.links["L1"], p.links["L2"]
    assert (power.name, power.a_connector, power.b_connector) == ("Power of OBC1", "PCDU1-J01", "OBC1-J01")  # fmt: skip
    assert [(x.a_pin, x.b_pin) for x in power.pairs] == [("1", "1"), ("1", "2"), ("2", "3"), ("2", "4")]  # fmt: skip
    junctions = links.link_junctions(power)
    assert [(j.a_pins, j.b_pins) for j in junctions] == [(("1",), ("1", "2")), (("2",), ("3", "4"))]
    assert not links.link_junctions(data) and len(data.pairs) == 4
    assert (power.harness_id, data.harness_id) == ("W001", "W002")
    w1, w2 = p.harnesses["W001"], p.harnesses["W002"]
    assert [(c.id, c.part_id) for c in splices.splices_of(w1)] == [
        ("W001-X1", "EX-SPLICE-1"),
        ("W001-X2", "EX-SPLICE-1"),
    ]
    assert len(w1.wires) == 6 and not splices.splices_of(w2) and len(w2.wires) == 4
    assert {g.kind for g in w2.shields} == {"shielded_pair"} and len(w2.shields) == 2
    assert all(p.parts[c.part_id].category != "splice" for c in w2.connectors)
    used = {c.part_id for c in p.connectors.values()}
    assert {"EX-DSUB-9-F", "EX-MICROD-9-M"} <= used
    assert p.parts["EX-DSUB-9-F"].ratings["contact_current_a"] == 10.0
    assert p.parts["EX-MICROD-9-M"].ratings["contact_current_a"] == 5.0
    assert EXAMPLES is not None
    for path in sorted((EXAMPLES / "templates" / "config-demo-values").glob("*.json")):
        demo = json.loads(path.read_text(encoding="utf-8"))  # the EXAMPLE values, placeholders
        c = p.config[demo["name"]]
        assert c.placeholder and {k: c.values[k] for k in demo["values"]} == demo["values"], c.name


def test_splice_from_connection_states_the_pin_currents_and_the_wires_follow() -> None:
    """4 A on the PCDU1 pins, 2 A on each OBC1 pin; the trunk to the splice carries 4 A from its
    pins, each branch 2 A (`core/currents.py`), and `explain` says so."""
    p = load_project(PROJECTS / "splice-from-connection").project
    stated = {
        (c.id, x.id): x.current_a for c in p.connectors.values() for x in c.pins if x.current_a
    }
    assert stated == {
        ("PCDU1-J01", "1"): 4.0, ("PCDU1-J01", "2"): 4.0,
        ("OBC1-J01", "1"): 2.0, ("OBC1-J01", "2"): 2.0,
        ("OBC1-J01", "3"): 2.0, ("OBC1-J01", "4"): 2.0,
    }  # fmt: skip
    h = p.harnesses["W001"]
    found = {wid: (c.value, c.source) for wid, c in currents.wire_currents(p, h).items()}
    assert found == {
        "W001-001": (4.0, "pins"), "W001-002": (2.0, "pins"), "W001-003": (2.0, "pins"),
        "W001-004": (4.0, "pins"), "W001-005": (2.0, "pins"), "W001-006": (2.0, "pins"),
    }  # fmt: skip
    gauges = {w.id: w.gauge_awg for w in h.wires}
    assert gauges == {"W001-001": 18, "W001-002": 22, "W001-003": 22, "W001-004": 18, "W001-005": 22, "W001-006": 22}  # fmt: skip
    for wid, amperes in (("W001-001", 4), ("W001-002", 2)):
        limit = next(d for d in explain_wire(p, wid) if d.id == "wire-current-limit")
        carried = next(i for i in limit.inputs if i.name == "Current carried")
        assert carried.value == amperes and "pin currents" in carried.source, carried


def test_splice_from_connection_writes_the_currents_and_the_connections(tmp_path: Path) -> None:
    out = _exported(tmp_path, "splice-from-connection")
    pins = {(r["Connector"], r["Pin"]): r["Current (A)"] for r in _table(out / "system" / "box_pinouts.csv")}  # fmt: skip
    assert pins[("PCDU1-J01", "1")] == "4" and pins[("OBC1-J01", "2")] == "2"
    rows = _table(out / "system" / "connections.csv")
    assert [(r["Connection"], r["From pin"], r["To pin"], r["Harness"]) for r in rows if r["Connection"] == "L1"] == [
        ("L1", "1", "1", "W001"), ("L1", "1", "2", "W001"), ("L1", "2", "3", "W001"), ("L1", "2", "4", "W001"),
    ]  # fmt: skip
    via = {r["Wire"]: r["Via"] for r in _table(out / "harnesses" / "W001" / "wirelist.csv")}
    assert set(via.values()) == {"W001-X1", "W001-X2"}


@pytest.mark.parametrize("name", FEATURES)
def test_every_device_connector_has_all_the_pins_of_its_part(name: str) -> None:
    """A feature example shows whole connectors: a box connector holds every pin its part has,
    named or not (a pasted pinout must not cut it down to the pins in use)."""
    p = load_project(PROJECTS / name).project
    for cid, c in sorted(p.connectors.items()):
        part = p.parts.get(c.part_id) if c.part_id else None
        if part is None or part.pin_count is None:
            continue
        assert len(c.pins) == part.pin_count, (cid, len(c.pins), part.pin_count)


# ---- branching-harness (section 4.5) ------------------------------------------------------------


def test_branching_harness_branches_where_one_connector_serves_two_devices() -> None:
    p = load_project(PROJECTS / "branching-harness").project
    assert sorted(p.units) == ["OBC1", "PCDU1", "RW1", "TRX1"]
    assert p.config["segmentation"].values["mode"] == "per_connector_group"
    assert len(p.interfaces) == 4 and all(not e.auto for i in p.interfaces.values() for e in i.endpoints)  # fmt: skip
    want = {
        "W001": ({"PCDU1-J01", "OBC1-J02", "TRX1-J01"}, "W001-B1"),
        "W002": ({"OBC1-J03", "RW1-J02", "TRX1-J02"}, "W002-B2"),  # numbered across the project
    }
    assert sorted(p.harnesses) == sorted(want)
    for hid, (plugs, branch) in want.items():
        h = p.harnesses[hid]
        assert h.generated and {c.mates_with for c in h.connectors} == plugs
        assert [b.id for b in h.branch_points] == [branch]
        assert len(h.segments) == 3 and all(branch in (s.from_node, s.to_node) for s in h.segments)
        assert all(s.length_m is not None for s in h.segments)  # EXAMPLE lengths, kept by Generate
    lengths_of = {s.id: s.length_m for h in p.harnesses.values() for s in h.segments}
    assert lengths_of == {
        "W001-L1": 0.5, "W001-L2": 0.3, "W001-L3": 0.6,
        "W002-L1": 0.4, "W002-L2": 0.7, "W002-L3": 0.5,
    }  # fmt: skip


def test_branching_harness_routes_each_wire_through_its_branch_point(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "p"
    assert main(["new", str(folder), "--template", "branching-harness", "--no-journal"]) == 0
    doc = run(capsys, "routing", str(folder), "W002")
    assert doc["branches"] is True
    through = {s["id"]: set(s["wires"]) for s in doc["segments"]}
    assert through["W002-L1"] == through["W002-L2"] | through["W002-L3"]  # the trunk from OBC1
    assert not through["W002-L2"] & through["W002-L3"]  # each branch to one device
    p = load_project(folder).project
    length = next(d for d in explain_wire(p, "W002-001") if d.id == "wire-length")
    assert [i.name for i in length.inputs if i.name.startswith("Segment")] == [
        "Segment W002-L1", "Segment W002-L3",
    ]  # fmt: skip
    assert length.value == pytest.approx(0.9)
    out = _exported(tmp_path, "branching-harness")
    assert (out / "harnesses" / "W002" / "segments.csv").is_file()


# ---- loose-cable-end (section 4.6) --------------------------------------------------------------


def test_loose_cable_end_has_a_cable_with_two_loose_ends_and_a_branch_point() -> None:
    p = load_project(PROJECTS / "loose-cable-end").project
    assert sorted(p.units) == ["OBC1", "PCDU1"] and len(p.interfaces) == 1
    assert p.harnesses["W001"].generated
    h = p.harnesses["W002"]
    assert h.name == "Bench cable" and not h.generated
    plug = next(c for c in h.connectors if c.role == "cable")
    assert (plug.id, plug.mates_with) == ("W002-P1", "OBC1-J03")
    loose = manual_harness.loose_ends(h)
    assert [(c.id, c.part_id, c.mates_with) for c in loose] == [
        ("W002-P2", manual_harness.TBD_PART_ID, None),
        ("W002-P3", manual_harness.TBD_PART_ID, None),
    ]
    assert [[(x.id, x.signal) for x in c.pins] for c in loose] == [
        [("1", "TM+"), ("2", "TM-")],
        [("3", "TC+"), ("4", "TC-")],
    ]
    ends = {(w.from_connector, w.from_pin, w.to_connector, w.to_pin) for w in h.wires}
    assert ends == {
        ("W002-P1", "1", "W002-P2", "1"), ("W002-P1", "2", "W002-P2", "2"),
        ("W002-P1", "3", "W002-P3", "3"), ("W002-P1", "4", "W002-P3", "4"),
    }  # fmt: skip
    assert [b.id for b in h.branch_points] == ["W002-B1"]  # the leg of the TC pins branches off
    assert {(s.from_node, s.to_node) for s in h.segments} == {
        ("W002-P1", "W002-B1"), ("W002-B1", "W002-P2"), ("W002-B1", "W002-P3"),
    }  # fmt: skip
    assert {g.kind for g in h.shields} == {"twisted_pair"} and len(h.shields) == 2
    assert not [f for f in checks.find(p) if f.rule == "isolated"]


def test_loose_cable_end_names_its_loose_ends_and_a_release_asks_for_a_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "p"
    assert main(["new", str(folder), "--template", "loose-cable-end", "--no-journal"]) == 0
    drc = run(capsys, "drc", str(folder))
    loose = next(f for f in drc["findings"] if f["id"] == "part-unapproved.TBD-CONNECTOR")
    assert "2 cable end(s) have no connector chosen yet (loose end)" in loose["title"]
    assert main(["export", str(folder)]) == 0  # the release gate reads the outputs
    assert main(["review", str(folder), "W002", "--by", "Designer 1", "--date", "2026-01-12"]) == 0
    release = ["release", str(folder), "W002", "--by", "Checker 1", "--date", "2026-01-15",
               "--comment", "EXAMPLE release for learning",
               "--accept-placeholders", "EXAMPLE values for learning",
               "--accept-unapproved-parts", "EXAMPLE parts for learning"]  # fmt: skip
    capsys.readouterr()
    assert main(release) == 1
    said = capsys.readouterr()
    blocked = [ln for ln in (said.out + said.err).splitlines() if ln.startswith("blocked:")]
    assert len(blocked) == 1 and "[loose_end_unresolved]" in blocked[0], blocked  # only that
    assert "W002-P2, W002-P3" in blocked[0]
    assert main([*release, "--accept-loose-ends", "EXAMPLE: the bench end is chosen later"]) == 0
    assert load_project(folder).project.harnesses["W002"].status == "released"


# ---- shields-and-ends (section 4.7) -------------------------------------------------------------


def _places(p: Any) -> dict[tuple[str, str], tuple[str, str, str | None, str | None] | None]:
    """(group, end) -> (kind of end, connector, pin, backshell) of its place, or None."""
    out: dict[tuple[str, str], tuple[str, str, str | None, str | None] | None] = {}
    for h in p.harnesses.values():
        for s in h.shields:
            if s.kind == "twisted_pair":
                continue
            for end in shield_ends.ENDS:
                place = shield_ends.place_of(s, end)
                kind = shield_ends.kind_of_end(s, end)
                out[(s.id, end)] = None if place is None else (kind, place.connector, place.pin, place.backshell)  # fmt: skip
    return out


def test_shields_and_ends_lands_each_end_where_its_place_says() -> None:
    p = load_project(PROJECTS / "shields-and-ends").project
    assert sorted(p.units) == ["OBC1", "RW1", "TTC1"]
    gen = p.config["generation"]
    assert gen.placeholder and (gen.values["shield_end_a"], gen.values["shield_end_b"]) == ("pigtail", "backshell_360")  # fmt: skip
    part = p.parts["EX-BACKSHELL-MICROD"]
    assert part.category == "backshell" and part.depth_mm == 30.0
    assert part.unverified and "EXAMPLE ONLY: not a real part" in (part.description or "")
    assert all(x.approval != "approved" for x in p.parts.values())  # nothing approved (T5)
    shells = {
        (h.id, a.id): (a.kind, a.part_id, a.target) for h in p.harnesses.values() for a in h.accessories
    }  # fmt: skip
    assert shells == {
        ("W001", "W001-A1"): ("backshell", "EX-BACKSHELL-MICROD", "W001-P2"),
        ("W001", "W001-A2"): ("backshell", "EX-BACKSHELL-MICROD", "W001-P1"),
        ("W002", "W002-A1"): ("backshell", "EX-BACKSHELL-MICROD", "W002-P2"),
    }
    assert _places(p) == {
        ("W001-S1", "a"): ("pigtail", "W001-P1", "5", None),  # a pigtail to a pin
        ("W001-S1", "b"): ("backshell_360", "W001-P2", None, "W001-A1"),  # a 360 degree bond
        ("W001-S2", "a"): ("pigtail", "W001-P2", None, "W001-A1"),  # a pigtail to the lug
        ("W001-S2", "b"): ("backshell_360", "W001-P1", None, "W001-A2"),
        ("W002-S2", "a"): None,  # not stated, on purpose
        ("W002-S2", "b"): ("backshell_360", "W002-P2", None, "W002-A1"),
    }
    h = p.harnesses["W001"]  # end A of the two pairs of one harness at different connectors
    ends_a = {s.id: shield_ends.end_connector(h, s, "a") for s in h.shields}
    assert ends_a == {"W001-S1": "W001-P1", "W001-S2": "W001-P2"}
    pin5 = next(x for x in p.connectors["OBC1-J01"].pins if x.id == "5")
    assert (pin5.signal, pin5.role) == ("SHLD", "shield")  # the device pin the pigtail meets
    info = [i for i in integrity.check_integrity(p) if i.code.startswith("shield_")]
    assert [(i.severity, i.code, i.object_id) for i in info] == [
        ("info", "shield_place_not_stated", "W002-S2")
    ]


def test_shields_and_ends_writes_each_place_into_the_production_sheet(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    out = _exported(tmp_path, "shields-and-ends")
    cells = set()
    for hid in ("W001", "W002"):
        sheet = openpyxl.load_workbook(out / "harnesses" / hid / f"{hid}_build.xlsx")["Production"]
        cells |= {str(c) for row in sheet.iter_rows(values_only=True) for c in row if c}
    for words in (
        "W001-S1 shielded pair: here pigtail to pin 5, far backshell 360",
        "W001-S1 shielded pair: here backshell 360 (W001-A1), far pigtail",
        "W001-S2 shielded pair: here pigtail to backshell W001-A1, far backshell 360",
        "W001-S1 shielded pair: pigtail lands here",  # the row of pin 5
        "W002-S1 twisted pair; W002-S2 overall shield: here pigtail, far backshell 360",
    ):
        assert words in cells, words


def test_shields_and_ends_a_floating_end_lands_nowhere() -> None:
    """The fourth kind of end: with end B of the grounding concept floating (the exercise of the
    page, on a copy), Generate makes every end B floating, its place goes, and no place is taken."""
    p = load_project(PROJECTS / "shields-and-ends").project
    gen = p.config["generation"]
    History(p).execute("end B floating", [SetConfig(with_value(gen, "shield_end_b", "floating"))])
    generate_project(p)
    s1 = next(s for s in p.harnesses["W001"].shields if s.id == "W001-S1")
    assert (s1.end_a, s1.end_b) == ("pigtail", "floating") and s1.at_b is None
    with pytest.raises(EditError, match="floating, so it lands nowhere"):
        wires.plan_set_shield_place(p, "W001-S1", "B", backshell="W001-A1")
    assert not [f for f in checks.find(p) if f.rule == "shield-wrong-end"]


# ---- lengths-to-the-face (section 4.8) ----------------------------------------------------------


def test_lengths_to_the_face_measures_to_the_face_and_takes_the_depths_off() -> None:
    p = load_project(PROJECTS / "lengths-to-the-face").project
    assert sorted(p.units) == ["PCDU1", "RW1"]
    model = p.config["model"]
    assert model.placeholder and model.values == {
        "length_reference": "face",
        "length_model": "path_loops_allowance_twist",  # the selectable length model of 1.15.0
        "cut_allowance_m": 0.03,
        "twist_takeup_fraction": 0.02,
    }
    assert lengths.length_reference(p) == "face"
    depth = {k: p.parts[k].depth_mm for k in ("EX-MICROD-9-M", "EX-MICROD-15-M", "EX-MICROD-21-M", "EX-BACKSHELL-MICROD")}  # fmt: skip
    assert depth == {"EX-MICROD-9-M": 18.0, "EX-MICROD-15-M": 19.0, "EX-MICROD-21-M": 20.0, "EX-BACKSHELL-MICROD": 30.0}  # fmt: skip
    w1, w2 = p.harnesses["W001"], p.harnesses["W002"]
    to = {c.id: (c.length_to, lengths.measured_to(c, "face")) for h in (w1, w2) for c in h.connectors}  # fmt: skip
    assert to == {
        "W001-P1": (None, "face"), "W001-P2": (None, "face"),
        "W002-P1": (None, "face"), "W002-P2": ("rear", "rear"),  # set back to its rear
    }  # fmt: skip
    assert [(a.id, a.kind, a.part_id, a.target) for a in w1.accessories] == [
        ("W001-A1", "backshell", "EX-BACKSHELL-MICROD", "W001-P1")
    ]
    assert lengths.end_depths(p, w1).depths == {"W001-P1": 0.048, "W001-P2": 0.018}
    assert lengths.end_depths(p, w2).depths == {"W002-P1": 0.019}  # nothing at the rear end
    assert {s.id: s.length_m for h in (w1, w2) for s in h.segments} == {"W001-L1": 1.2, "W002-L1": 0.9}  # fmt: skip
    # rear to rear, two service loops of 0.05 m, the take-up of twisting and the cut allowance
    for h, rear in ((w1, 1.2 - 0.066), (w2, 0.9 - 0.019)):
        want = (rear + 2 * 0.05) * 1.02 + 0.03
        assert [w.length_m for w in h.wires] == [pytest.approx(want)] * len(h.wires), h.id
    steps = {s.label: s.expression for d in explain_wire(p, "W001-001") if d.id == "wire-length" for s in d.steps}  # fmt: skip
    assert steps["Path from rear to rear"] == "1.2 − 0.066"


def test_lengths_to_the_face_names_the_face_ends_and_a_missing_depth(tmp_path: Path) -> None:
    out = _exported(tmp_path, "lengths-to-the-face")
    p = load_project(PROJECTS / "lengths-to-the-face").project
    note = lengths.face_line(p, p.harnesses["W002"])
    assert note is not None and "but at W002-P2" in note
    exported = json.loads((out / "system" / "export.json").read_text(encoding="utf-8"))
    assert "length_to" in json.dumps(exported) and "depth_mm" in json.dumps(exported)
    # the exercise of the page: take the depth off a part at a face end, and check names it
    apply_ops(p, build_data.plan_set_part_depth(p, "EX-MICROD-15-M", None))
    missing = [i for i in integrity.check_integrity(p) if i.code == "length_depth_missing"]
    assert [(i.severity, i.object_id) for i in missing] == [("warning", "W002-P1")], missing
