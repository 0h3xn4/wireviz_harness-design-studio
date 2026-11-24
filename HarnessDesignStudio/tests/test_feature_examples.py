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
from harness_design_studio.core import checks, currents, links, splices, templates
from harness_design_studio.core.derive import explain_wire
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
