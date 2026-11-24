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
    configcheck,
    currents,
    derive,
    device_check,
    devices,
    drc,
    integrity,
    label_format,
    library_link,
    library_pointer,
    links,
    manual_harness,
    review,
    shield_ends,
    signal_map,
    splices,
    templates,
    verify,
    wires,
)
from harness_design_studio.core.commands import History, Put, SetConfig, apply_ops
from harness_design_studio.core.configcheck import with_value
from harness_design_studio.core.derive import explain_wire
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.errors import TransactionError
from harness_design_studio.core.extensions import manager, plugins, trust
from harness_design_studio.core.generate import lengths
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.import_record import file_sha256
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import evolve
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
    "names-and-ports": frozenset(),
    "splice-by-hand": frozenset(),  # no `isolated` since part E (section 4.3)
    "splice-from-connection": frozenset(),
    "branching-harness": frozenset(),
    "loose-cable-end": frozenset(),  # the loose ends are the part-unapproved of TBD-CONNECTOR
    "shields-and-ends": frozenset(),  # the end without a place is an info of check, not of drc
    "lengths-to-the-face": frozenset(),
    "released-harness": frozenset(),
    # the waived connector-lookalike and the two deviations are accepted, not open (section 4.10)
    "overrides-and-deviations": frozenset(),
    # the cross-strap of OBC1 to the copy TTC1-R is waived; the library is not read by drc
    "device-library": frozenset(),
    "build-data-and-as-built": frozenset(),  # the value out of its limit is not a design rule's
    "imports-from-files": frozenset(),
    # the plug-in is enabled and not trusted, so it is not loaded: a warning of its own (4.14); the
    # two data rules are silent on the EXAMPLE gauges (AWG 22, 2 A: at the limit, under the table)
    "extensions": frozenset({"x-extension-problem"}),
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
    a current or a voltage (design of 5.1.0, T6). The words of `config/naming.json` (the patterns,
    the far-device names, the signal map, the review checklist) and the segmentation mode are
    choices, not numbers."""
    p = load_project(PROJECTS / name).project
    fresh = new_project("x").config
    words = {"naming": set(p.config["naming"].values), "segmentation": {"mode"}}

    def numbers(key: str, values: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in values.items() if k not in words.get(key, set())}

    if any(
        key not in fresh or numbers(key, c.values) != numbers(key, fresh[key].values)
        for key, c in p.config.items()
    ):
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


# ---- released-harness (section 4.9) -------------------------------------------------------------

RELEASE_DATES = {"review": "2026-01-12", "release": "2026-01-15", "new_version": "2026-01-20"}


def test_released_harness_holds_a_release_with_ticks_and_its_next_version() -> None:
    p = load_project(PROJECTS / "released-harness").project
    assert sorted(p.units) == ["OBC1", "PCDU1", "RW1"] and len(p.interfaces) == 2
    naming = p.config["naming"].values
    assert naming["review_checklist"] == review.template_points() and len(naming["review_checklist"]) == 26  # fmt: skip
    assert naming["release_distinct_roles"] is True
    w1, w2 = p.harnesses["W001"], p.harnesses["W002"]
    assert (w1.status, w1.version) == ("draft", "1.0.0")  # the RS-422 harness stays a draft
    assert (w2.status, w2.version, w2.author) == ("draft", "1.1.0", "Designer 1")
    assert (w2.checker, w2.approver, w2.released_on) == (None, None, None)
    assert list(p.baselines) == ["W002.1.0.0"]  # W001 has none
    base = p.baselines["W002.1.0.0"]
    assert (base.harness_id, base.version, base.by, base.released_on) == ("W002", "1.0.0", "Releaser 1", RELEASE_DATES["release"])  # fmt: skip
    [frozen] = base.snapshot.harnesses
    assert (frozen.id, frozen.status, frozen.author, frozen.checker, frozen.approver) == ("W002", "released", "Designer 1", "Checker 1", "Releaser 1")  # fmt: skip
    assert base.comment.startswith("First release of the power harness of RW1 (EXAMPLE)")
    for words in (
        "accepted by Releaser 1: EXAMPLE values for learning",
        "accepted by Releaser 1: EXAMPLE parts for learning",
        f"[Review checklist (26 points, list {review.list_hash(review.template_points())}), "
        "recorded by Releaser 1: ticked 1-20; not ticked 21",
    ):
        assert words in base.comment, words
    entries = [(e.id, e.harness_id, e.version, e.kind, e.by, e.when) for e in p.changelog.values()]
    assert entries == [
        ("C0001", "W002", "1.0.0", "review", "Designer 1", RELEASE_DATES["review"]),
        ("C0002", "W002", "1.0.0", "release", "Releaser 1", RELEASE_DATES["release"]),
        ("C0003", "W002", "1.1.0", "new_version", "Designer 1", RELEASE_DATES["new_version"]),
    ]
    # the one change of 1.1.0: the EXAMPLE segment length of segment-lengths.csv, 0.1 m longer
    assert {s.id: s.length_m for s in w2.segments} == {"W002-L1": 1.0}
    assert {s.id: s.length_m for s in frozen.segments} == {"W002-L1": 0.9}
    assert {s.id: s.length_m for s in w1.segments} == {"W001-L1": 0.85}


def test_released_harness_shows_its_history_in_log_and_diff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "p"
    assert main(["new", str(folder), "--template", "released-harness", "--no-journal"]) == 0
    log = run(capsys, "log", str(folder), "W002")
    assert [(e["version"], e["event"], e["by"], e["date"]) for e in log["entries"]] == [
        ("1.0.0", "submitted for review", "Designer 1", RELEASE_DATES["review"]),
        ("1.0.0", "released", "Releaser 1", RELEASE_DATES["release"]),
        ("1.1.0", "new version started", "Designer 1", RELEASE_DATES["new_version"]),
    ]
    diff = run(capsys, "diff", str(folder), "W002")
    assert (diff["from"], diff["to"]) == ("1.0.0", "working")
    changed = {(c["kind"], c["id"]): {f["name"]: (f["before"], f["after"]) for f in c["fields"]} for c in diff["changes"]}  # fmt: skip
    assert changed[("segment", "W002-L1")] == {"length_m": (0.9, 1.0)}
    assert changed[("harness", "W002")]["version"] == ("1.0.0", "1.1.0")
    assert changed[("harness", "W002")]["status"] == ("released", "draft")
    assert {c["change"] for c in diff["changes"]} == {"changed"}
    out = _exported(tmp_path, "released-harness")
    report = (out / "system" / "version_report.md").read_text(encoding="utf-8")
    assert "## W002 (version 1.1.0, draft)" in report
    assert "2026-01-15, Releaser 1: version 1.0.0 released: First release" in report
    assert "recorded by Releaser 1: ticked 1-20" in report


def test_released_harness_survives_new_with_a_name_and_its_next_release_freezes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A copy made with another name and annotated config files keeps the release (section 9);
    releasing 1.1.0 on it locks what W002 uses again (the page's next step)."""
    folder = tmp_path / "p"
    argv = ["new", str(folder), "--template", "released-harness", "--name", "Wheel power (EXAMPLE)"]
    assert main([*argv, "--annotate-config"]) == 0
    doc = run(capsys, "check", str(folder))
    assert doc["errors"] == 0 and doc["warnings"] == 0, doc["issues"]
    assert run(capsys, "drc", str(folder))["open_errors"] == 0
    p = load_project(folder).project
    assert p.meta.name == "Wheel power (EXAMPLE)" and list(p.baselines) == ["W002.1.0.0"]
    assert main(["export", str(folder)]) == 0
    assert main(["review", str(folder), "W002", "--by", "Designer 1", "--date", "2026-01-21"]) == 0
    same = ["release", str(folder), "W002", "--by", "Designer 1", "--checker", "Checker 1",
            "--date", "2026-01-22", "--comment", "Second release of the power harness",
            "--accept-placeholders", "EXAMPLE values for learning",
            "--accept-unapproved-parts", "EXAMPLE parts for learning", "--ticked", "all"]  # fmt: skip
    capsys.readouterr()
    assert main(same) == 1  # different people in a release: the author does not release
    assert "[same_person]" in capsys.readouterr().err
    assert main([*same[:4], "Releaser 1", *same[5:]]) == 0
    p = load_project(folder).project
    assert p.harnesses["W002"].status == "released"
    assert sorted(p.baselines) == ["W002.1.0.0", "W002.1.1.0"]
    used = next(w for w in p.harnesses["W002"].wires if w.signal == "PWR")
    box = next(c.mates_with for c in p.harnesses["W002"].connectors if c.id == used.from_connector)
    assert box is not None
    c = p.connectors[box]
    renamed = [evolve(x, signal="MOVED") if x.id == used.from_pin else x for x in c.pins]
    with pytest.raises(TransactionError, match="touches released items") as refused:
        History(p).execute("rename a pin W002 uses", [Put("connectors", evolve(c, pins=renamed))])
    assert any("W002 is released (version 1.1.0)" in why for why in refused.value.problems)


# ---- overrides-and-deviations (section 4.10) ----------------------------------------------------

OVERRIDE_REASON = "EXAMPLE: the thinner wire of a bench cable"
DEVIATION_REASON = "EXAMPLE: the bench cable carries the load for minutes only"
WAIVER_REASON = "EXAMPLE: the two connectors are keyed differently on the real unit"


def test_overrides_and_deviations_stores_the_override_the_waiver_and_the_deviations() -> None:
    p = load_project(PROJECTS / "overrides-and-deviations").project
    assert sorted(p.units) == ["OBC1", "PCDU1", "RW1"] and len(p.interfaces) == 3
    power = {i.name: (e.connector_id for e in i.endpoints) for i in p.interfaces.values()}
    assert list(power["Power of OBC1"]) == ["PCDU1-J02", "OBC1-J02"]  # both PCDU1 power connectors
    h = p.harnesses["W002"]
    assert {c.mates_with for c in h.connectors} == {"PCDU1-J02", "OBC1-J02"}
    assert {s.id: s.length_m for s in h.segments} == {"W002-L1": 2.0}  # EXAMPLE
    w1, w2 = h.wires
    assert (w1.id, w1.signal, w1.gauge_awg, w1.locked, w1.overrides) == ("W002-001", "PWR", 24, True, {"gauge_awg": OVERRIDE_REASON})  # fmt: skip
    assert (w2.id, w2.gauge_awg, w2.locked, w2.overrides) == ("W002-002", 22, False, {})  # fmt: skip
    stored = {w.id: (w.rule, w.object_id, w.justification) for w in p.waivers.values()}
    assert stored == {
        "connector-lookalike.PCDU1-J01": ("connector-lookalike", "PCDU1-J01", WAIVER_REASON),
        "current-over-wire.W002-001": ("current-over-wire", "W002-001", DEVIATION_REASON),
        "voltage-drop.W002-001": ("voltage-drop", "W002-001", DEVIATION_REASON),
    }
    found = {f.id: f for f in drc.run(p)}
    assert found["connector-lookalike.PCDU1-J01"].waiver is not None
    assert not found["connector-lookalike.PCDU1-J01"].deviation  # a warning is waived
    for fid in ("current-over-wire.W002-001", "voltage-drop.W002-001"):
        assert found[fid].severity == "error" and found[fid].deviation, fid  # accepted, not fixed


def test_overrides_and_deviations_drc_shows_two_deviations_and_exits_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "p"
    assert main(["new", str(folder), "--template", "overrides-and-deviations", "--no-journal"]) == 0
    capsys.readouterr()
    assert main(["drc", str(folder)]) == 0
    said = capsys.readouterr().out
    assert "Waived: 1. Deviations: 2." in said
    assert "Wire W002-001 (AWG 24) carries 2 A but allows 1.44 A after derating" in said
    assert "Wire W002-001 drops 0.706 V, more than the 0.5 V limit" in said
    doc = run(capsys, "drc", str(folder))
    assert doc["open_errors"] == 0 and doc["waived"] == 3
    waived = {f["id"]: (f["severity"], f["waiver_justification"]) for f in doc["findings"] if f["waived"]}  # fmt: skip
    assert waived == {
        "connector-lookalike.PCDU1-J01": ("warning", WAIVER_REASON),
        "current-over-wire.W002-001": ("error", DEVIATION_REASON),
        "voltage-drop.W002-001": ("error", DEVIATION_REASON),
    }
    shown = run(capsys, "override", str(folder), "W002-001")
    assert shown["overrides"] == [{"field": "gauge_awg", "value": 24, "reason": OVERRIDE_REASON}]
    gauges = {i["name"]: i["value"] for i in shown["derivation"]["inputs"]}
    assert gauges == {"Gauge set by the engineer": 24, "Gauge the design would give": 22}
    capsys.readouterr()
    assert main(["deviation", str(folder)]) == 0
    listed = capsys.readouterr().out
    assert listed.count("DEVIATION ") == 2 and listed.count(f"reason: {DEVIATION_REASON}") == 2
    out = _exported(tmp_path, "overrides-and-deviations")
    flags = {r["Wire"]: (r["Locked"], r["Overrides"]) for r in _table(out / "harnesses" / "W002" / "wirelist.csv")}  # fmt: skip
    assert flags == {"W002-001": ("yes", f"gauge_awg: {OVERRIDE_REASON}"), "W002-002": ("", "")}


# ---- names-and-ports (section 4.2) --------------------------------------------------------------

TEAM_RENAMES = {"TXP": "TX+", "TXN": "TX-", "RXP": "RX+", "RXN": "RX-"}


def _obc_ports(p: Any) -> dict[str, tuple[str | None, str | None]]:
    return {x.id: (x.signal, x.interface_id) for x in p.connectors["OBC1-J01"].pins}


def test_names_and_ports_gives_each_interface_the_port_of_its_far_device() -> None:
    p = load_project(PROJECTS / "names-and-ports").project
    assert sorted(p.units) == ["OBC1", "TTC1", "TTC2"]
    naming = p.config["naming"].values
    assert naming["far_device_names"] is True
    assert naming["signal_map"] == signal_map.read_file(TEMPLATE_FILES / "signal-map.csv")
    far = {i.id: [e.unit_id for e in i.endpoints] for i in p.interfaces.values()}
    assert far == {"IF-001": ["OBC1", "TTC2"], "IF-002": ["OBC1", "TTC1"]}  # TTC2 made first
    assert all(not e.auto for i in p.interfaces.values() for e in i.endpoints)
    want: dict[str, tuple[str | None, str | None]] = {
        str(n): (f"TTC1_{s}", "IF-002") for n, s in enumerate(("TX+", "TX-", "RX+", "RX-"), 1)
    }
    want |= {str(n + 4): (f"TTC2_{s}", "IF-001") for n, s in enumerate(("TX+", "TX-", "RX+", "RX-"), 1)}  # fmt: skip
    want["9"] = (None, None)
    assert _obc_ports(p) == want
    assert p.connectors["OBC1-J01"].pins[8].role == "spare"
    for uid, iid in (("TTC1", "IF-002"), ("TTC2", "IF-001")):
        pins = p.connectors[f"{uid}-J01"].pins
        assert [(x.signal, x.interface_id) for x in pins[:4]] == [(s, iid) for s in ("TX+", "TX-", "RX+", "RX-")]  # fmt: skip
        assert pins[4].role == "spare" and not any(x.signal for x in pins[4:])
    assert p.config["segmentation"].values["mode"] == "per_connector_group"
    [h] = p.harnesses.values()  # one plug on OBC1-J01, branching to TTC1 and TTC2
    assert {c.mates_with for c in h.connectors} == {"OBC1-J01", "TTC1-J01", "TTC2-J01"}
    assert len(h.branch_points) == 1 and len(h.wires) == 8


def test_names_and_ports_records_what_the_signal_map_renamed() -> None:
    p = load_project(PROJECTS / "names-and-ports").project
    records = p.import_records
    assert sorted(records) == [f"pinout:{u}-pinout.csv" for u in ("OBC1", "TTC1", "TTC2")]
    renamed = {
        (r.source_name, c.item, c.read, c.stored)
        for r in records.values()
        for c in r.rows_converted
        if c.unit == signal_map.UNIT
    }
    for n, (team, signal) in enumerate(TEAM_RENAMES.items(), 1):
        for far, pin in (("TTC1", n), ("TTC2", n + 4)):  # inside a port: TTC1_TXP is TTC1_TX+
            assert ("OBC1-pinout.csv", f"OBC1-J01 pin {pin}", f"{far}_{team}", f"{far}_{signal}") in renamed  # fmt: skip
            assert (f"{far}-pinout.csv", f"{far}-J01 pin {n}", team, signal) in renamed
    assert len(renamed) == 16 and all(r.source_path is None for r in records.values())


def test_names_and_ports_without_the_setting_takes_the_ports_in_name_order() -> None:
    """The lesson of the template on a copy: with the setting off, the pins freed and Generate run
    again, IF-001 (to TTC2) takes the first port in name order, TTC1's; with the setting on again,
    `verify` names the mismatch."""
    p = load_project(PROJECTS / "names-and-ports").project
    history = History(p)
    history.execute("off", configcheck.plan_set_far_device_names(p, False).ops)
    generate_project(p)
    assert _obc_ports(p)["1"] == ("TTC1_TX+", "IF-002")  # turning it off moves no pin
    history.execute("unassign", devices.ops_unassign_pins(p, "OBC1-J01", [str(n) for n in range(1, 9)]))  # fmt: skip
    generate_project(p)
    assert _obc_ports(p)["1"] == ("TTC1_TX+", "IF-001") and _obc_ports(p)["5"] == ("TTC2_TX+", "IF-002")  # fmt: skip
    history.execute("on", configcheck.plan_set_far_device_names(p, True).ops)
    found = [i for i in verify.verify_project(p).issues if i.code == "port_far_device"]
    assert {i.severity for i in found} == {"error"}
    assert any("Interface IF-001 goes to unit TTC2 but uses port TTC1 of OBC1-J01" in i.message for i in found)  # fmt: skip


# ---- build-data-and-as-built (section 4.12) -----------------------------------------------------


def test_build_data_and_as_built_holds_the_build_data() -> None:
    p = load_project(PROJECTS / "build-data-and-as-built").project
    assert sorted(p.units) == ["OBC1", "PCDU1", "RW1"] and sorted(p.harnesses) == ["W001", "W002"]
    assert label_format.format_of(p) == "harness_device_connector"  # the format of a new project
    assert "sheet" not in p.config["titleblock"].values["fields"]
    contact = p.parts["EX-CONTACT-22"]
    assert (contact.category, contact.unverified, contact.tool) == ("contact", True, "EXAMPLE crimp tool, setting 4")  # fmt: skip
    assert "EXAMPLE ONLY: not a real part" in (contact.description or "")
    assert all(x.approval != "approved" for x in p.parts.values())  # nothing approved (T5)
    for cid in ("PCDU1-J01", "RW1-J01", "OBC1-J01", "RW1-J02"):  # the column Cable contact
        assert {x.contact_part for x in p.connectors[cid].pins} == {"EX-CONTACT-22"}, cid
    for h in p.harnesses.values():
        assert {(w.strip_a_mm, w.strip_b_mm) for w in h.wires} == {(6.0, 5.0)}, h.id
        for c in h.connectors:  # Generate takes the contact from the device's pin
            used = {pin for w in h.wires for end, pin in ((w.from_connector, w.from_pin), (w.to_connector, w.to_pin)) if end == c.id}  # fmt: skip
            assert {x.contact_part for x in c.pins if x.id in used} == {"EX-CONTACT-22"}, c.id
    kinds = {a.id: (a.kind, a.target) for a in p.harnesses["W001"].accessories}
    assert kinds == {
        "ACC-001": ("sleeving", "W001-001"),
        "ACC-002": ("heat_shrink", "W001-P1"),
        "ACC-003": ("label", "W001-P2"),
        "ACC-004": ("backshell", "W001-P1"),
    }
    plan = p.config["harness_plan"].values
    assert plan["colour_rule"] == "pin_code"
    [code] = plan["colour_codes"]
    assert code["example"] is True and code["name"] == "example"
    assert code == templates.example_colour_code(code["parts"])  # the template's table, marked
    cable_parts = {c.part_id for h in p.harnesses.values() for c in h.connectors}
    assert cable_parts <= set(code["parts"])
    doc = p.meta.document
    assert doc is not None and (doc.system, doc.company) == ("EX-SAT", "Example Ltd")
    assert len(doc.contact) == 2 and doc.plans["W001"].number == "HP-W001"
    assert p.config["generation"].values["asbuilt_cut_tolerance_mm"] == 10.0
    assert p.config["generation"].placeholder  # the EXAMPLE values stay a placeholder


def test_build_data_and_as_built_ships_a_record_with_one_value_out_of_its_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    p = load_project(PROJECTS / "build-data-and-as-built").project
    assert {r.harness_id for r in p.asbuilt.values()} == {"W001"}
    cut = {r.subject: r.cut_length_m for r in p.asbuilt.values() if r.kind == "wire"}
    assert sorted(cut) == ["W001-001", "W001-002", "W001-003", "W001-004"]
    [record] = p.import_records.values()
    assert (record.kind, record.source_name, record.source_path) == ("asbuilt", "W001-asbuilt-EXAMPLE.csv", None)  # fmt: skip
    folder = tmp_path / "p"
    assert main(["new", str(folder), "--template", "build-data-and-as-built", "--no-journal"]) == 0
    doc = run(capsys, "asbuilt", str(folder), rc=1)  # a value out of its limit: exit code 1
    assert (doc["out_of_limit"], doc["missing"], doc["records"]) == (1, 0, len(p.asbuilt))
    [w1, w2] = doc["harnesses"]
    assert (w1["harness"], w1["complete"], w2["harness"], w2["started"]) == ("W001", True, "W002", False)  # fmt: skip
    [out] = [line for line in doc["lines"] if line["status"] == "out of limit"]
    assert (out["kind"], out["subject"], out["field"]) == ("wire", "W001-001", "cut length (m)")
    assert (out["actual"], out["designed"]) == (0.975, 0.95)  # 25 mm too long, 10 mm allowed
    assert capsys.readouterr().out == ""
    assert main(["asbuilt", str(folder)]) == 1
    said = capsys.readouterr().out
    assert "OUT OF LIMIT: W001 wire W001-001: cut length (m)" in said and "OUT OF TOLERANCE by 15 mm" in said  # fmt: skip


def test_build_data_and_as_built_writes_the_plans_and_the_labels(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "p"
    assert main(["new", str(folder), "--template", "build-data-and-as-built", "--no-journal"]) == 0
    capsys.readouterr()
    assert main(["check", str(folder)]) == 0
    assert "plan_colour_example" in capsys.readouterr().out  # the note of an example code
    doc = run(capsys, "export", str(folder), "--harness-plan")
    assert sorted(doc["harness_plans"]) == ["harnesses/W001/W001_plan.ods", "harnesses/W002/W002_plan.ods"]  # fmt: skip
    verify = run(capsys, "verify", str(folder), "--outputs")
    assert not [i for i in verify["issues"] if i["severity"] == "error"], verify["issues"]
    labels = {r["Label"]: r["Text"] for r in _table(folder / "outputs" / "harnesses" / "W001" / "labels.csv")}  # fmt: skip
    assert labels["W001-P1"] == "W001:OBC1:J01" and labels["W001-P2"] == "W001:RW1:J02"


# ---- imports-from-files (section 4.13) ----------------------------------------------------------

TEMPLATE_FILES = EXAMPLES / "templates"
# the import templates the example reads, by the kind of their record
IMPORTED = {
    "parts": "approved-parts.csv",
    "interfaces": "interfaces.csv",
    "netlist": "wheel-connectors.net",
    "pinout": "device-pinout-EXAMPLE.csv",
    "lengths": "segment-lengths.csv",
    "strip-lengths": "strip-lengths.csv",
    "accessories": "accessories.csv",
}


def test_imports_from_files_records_every_import() -> None:
    p = load_project(PROJECTS / "imports-from-files").project
    records: dict[str, Any] = {r.kind: r for r in p.import_records.values()}
    assert sorted(records) == sorted(IMPORTED) and len(p.import_records) == len(IMPORTED)
    for kind, name in IMPORTED.items():
        r = records[kind]
        assert (r.source_name, r.source_path, r.dropped_count) == (name, None, 0), kind
        assert r.sha256 == file_sha256(TEMPLATE_FILES / name), kind  # the shipped file itself
    assert records["parts"].rows_read == 5 and records["pinout"].rows_read == 9
    assert [c.stored for c in records["lengths"].rows_converted] == ["0.85 m", "0.9 m"]
    assert p.library_info.source == f"approved-parts.csv (sha256 {records['parts'].sha256[:12]})"


def test_imports_from_files_reads_every_approval_status_as_not_decided() -> None:
    """T12, D-129: the template file says Approved, Review and Rejected; the example reads them all
    as not decided yet, so no part of an example reads as approved."""
    p = load_project(PROJECTS / "imports-from-files").project
    with (TEMPLATE_FILES / "approved-parts.csv").open(newline="", encoding="utf-8") as f:
        listed = {row["part number"]: row["approval status"] for row in csv.DictReader(f)}
    assert set(listed.values()) == {"Approved", "Review", "Rejected"}
    assert {pid: p.parts[pid].approval for pid in listed} == dict.fromkeys(listed, "pending")
    assert all(x.approval != "approved" for x in p.parts.values())


def test_imports_from_files_holds_what_the_files_say() -> None:
    p = load_project(PROJECTS / "imports-from-files").project
    assert sorted(p.units) == ["GYRO1", "OBC1", "PCDU1", "RW1"]
    assert p.config["naming"].values["signal_map"] == signal_map.read_file(TEMPLATE_FILES / "signal-map.csv")  # fmt: skip
    assert {"IF-010", "IF-011"} <= set(p.interfaces)  # interfaces.csv, the tool's choice confirmed
    assert all(not e.auto for i in p.interfaces.values() for e in i.endpoints)
    assert {c: p.connectors[c].keying for c in ("PCDU1-J01", "PCDU1-J02")} == {"PCDU1-J01": "A", "PCDU1-J02": "B"}  # fmt: skip
    fixed = {c: [(x.id, x.signal) for x in p.connectors[c].pins if x.fixed] for c in ("RW1-J01", "RW1-J02")}  # fmt: skip
    assert fixed == {
        "RW1-J01": [("1", "PWR"), ("2", "RTN")],
        "RW1-J02": [("1", "TX+"), ("2", "TX-"), ("3", "RX+"), ("4", "RX-")],
    }  # the KiCad netlist
    gyro = p.connectors["GYRO1-J01"]  # device-pinout-EXAMPLE.csv
    assert (gyro.part_id, gyro.source_doc, gyro.source_version) == ("EX-MICROD-9-F", "ICD-GYRO EXAMPLE", "Issue 1")  # fmt: skip
    assert [(x.signal, x.direction, x.level, x.current_a) for x in gyro.pins[:4]] == [
        ("TX+", "out", "RS422", 0.05), ("TX-", "out", "RS422", 0.05),
        ("RX+", "in", "RS422", 0.05), ("RX-", "in", "RS422", 0.05),
    ]  # fmt: skip
    assert [x.role for x in gyro.pins[4:]] == ["spare"] * 5
    assert gyro.row_layout is not None and gyro.row_layout.rows == [["1", "2", "3", "4", "5"], ["6", "7", "8", "9"]]  # fmt: skip
    assert all(x.interface_id for x in gyro.pins[:4])
    lengths_of = {s.id: s.length_m for h in p.harnesses.values() for s in h.segments}
    assert (lengths_of["W001-L1"], lengths_of["W002-L1"]) == (0.85, 0.9)  # segment-lengths.csv
    w1 = p.harnesses["W001"]
    strips = {w.id: (w.strip_a_mm, w.strip_b_mm) for w in w1.wires if w.strip_a_mm is not None}
    assert strips == {"W001-001": (6.0, 6.0), "W001-002": (6.0, 5.0)}  # strip-lengths.csv
    assert {a.id: (a.kind, a.target) for a in w1.accessories} == {
        "ACC-001": ("sleeving", "W001-001"),
        "ACC-002": ("heat_shrink", "W001-P1"),
    }  # accessories.csv


def test_imports_from_files_sources_are_the_files_templates_copies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder, copied = tmp_path / "p", tmp_path / "templates"
    assert main(["new", str(folder), "--template", "imports-from-files", "--no-journal"]) == 0
    assert main(["templates", str(copied)]) == 0
    sources = [arg for name in IMPORTED.values() for arg in ("--source", str(copied / name))]
    doc = run(capsys, "imports", str(folder), *sources)
    assert doc["count"] == len(IMPORTED) and doc["sources_changed"] == 0
    assert {i["status"] for i in doc["imports"]} == {"unchanged"}


def test_the_pinout_template_imports_into_a_new_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The new import template (part D): every row is read, nothing is left out or refused."""
    folder = tmp_path / "p"
    assert main(["new", str(folder), "--no-journal"]) == 0
    template = TEMPLATE_FILES / "device-pinout-EXAMPLE.csv"
    args = ("import-pinout", str(folder), str(template), "--device", "GYRO1", "--new-device", "Gyroscope")  # fmt: skip
    doc = run(capsys, *args)
    assert doc["changed"] and doc["pins"] == 9 and not doc["warnings"] and not doc["unmatched_signals"]  # fmt: skip
    assert doc["connectors"] == [{"connector": "GYRO1-J01", "action": "added", "pins": 9}]
    record = doc["import"]
    assert record["record_written"] and record["dropped_count"] == 0
    assert "columns_ignored" not in record or not record["columns_ignored"]
    with template.open(newline="", encoding="utf-8") as f:
        heading = next(csv.reader(f))
    assert [c["column"] for c in record["columns_read"]] == heading  # every column is read
    p = load_project(folder).project
    assert len(p.connectors["GYRO1-J01"].pins) == p.parts["EX-MICROD-9-F"].pin_count == 9
    assert run(capsys, "check", str(folder))["errors"] == 0


# ---- device-library (section 4.11) -------------------------------------------------------------

LIBRARY = PROJECTS / "device-library" / "team-library"


def test_device_library_names_its_library_folder_and_holds_it() -> None:
    folder = PROJECTS / "device-library"
    assert library_pointer.read_pointer(folder) == ["team-library"]
    assert sorted(p.name for p in LIBRARY.iterdir()) == [
        "OBC1.device.json",
        "TTC1.device.json",
        "subsystem-power.json",
    ]
    libs = library_link.project_libraries(folder)
    assert not libs.problems
    assert [(d.unit_id, d.file) for d in libs.devices()] == [
        ("OBC1", "OBC1.device.json"),
        ("TTC1", "TTC1.device.json"),
    ]


def test_device_library_takes_its_devices_from_the_library() -> None:
    p = load_project(PROJECTS / "device-library").project
    assert sorted(p.units) == ["OBC1", "PCDU1", "TTC1", "TTC1-R"]
    assert p.units["TTC1-R"].side == "redundant"  # a number of the same device: TTC1 and a copy
    records = {r.id: r for r in p.import_records.values()}
    assert sorted(records) == [
        "devices:OBC1.device.json",
        "devices:TTC1.device.json",
        "subsystem:subsystem-power.json",
    ]
    for rid, rec in records.items():
        assert rec.source_path == f"team-library/{rec.source_name}", rid  # inside the project
        assert "Library: not a Git repository" in rec.notes or rec.kind == "subsystem", rid
    # OBC1 is as the library has it now; TTC1 was added before the team changed it
    assert records["devices:OBC1.device.json"].sha256 == file_sha256(LIBRARY / "OBC1.device.json")
    assert records["devices:TTC1.device.json"].sha256 != file_sha256(LIBRARY / "TTC1.device.json")
    sub = records["subsystem:subsystem-power.json"]
    assert sub.sha256 == file_sha256(LIBRARY / "subsystem-power.json")
    assert p.units["PCDU1"].subsystem == "Power"  # the name of the subsystem file
    ttc = p.connectors["TTC1-J02"]
    assert [(x.id, x.signal, x.fixed, x.function) for x in ttc.pins[:4]] == [
        ("1", "TX+", True, "Telecommands in, positive"),
        ("2", "TX-", True, "Telecommands in, negative"),
        ("3", "RX+", True, "Telemetry out, positive"),
        ("4", "RX-", True, "Telemetry out, negative"),
    ]
    assert [x.function for x in p.connectors["TTC1-R-J02"].pins[:4]] == [
        x.function for x in ttc.pins[:4]
    ]  # the copy has the pinout of its device
    assert len(p.interfaces) == 3 and all(not e.auto for i in p.interfaces.values() for e in i.endpoints)  # fmt: skip
    assert sorted(p.harnesses) == ["W001", "W002", "W003"]
    # OBC1 talks to both transceivers; the link to the copy joins the chains, waived with a reason
    (to_copy,) = [i.id for i in p.interfaces.values() if i.name.endswith("of TTC1-R")]
    stored = {w.id: (w.rule, w.object_id, w.justification) for w in p.waivers.values()}
    assert stored == {
        f"cross-strap.{to_copy}": (
            "cross-strap", to_copy,
            "EXAMPLE: OBC1 talks to both transceivers on purpose, so either can take over",
        )
    }  # fmt: skip


def test_device_library_obc1_is_checked_and_its_library_file_holds_the_check() -> None:
    p = load_project(PROJECTS / "device-library").project
    check = p.units["OBC1"].checked
    assert check is not None
    assert (check.by, check.on, check.icd) == (
        "Reviewer 1",
        "2026-01-15",
        "ICD-OBC EXAMPLE Issue 2",
    )
    assert device_check.check_state(p, "OBC1") == device_check.CHECKED
    assert [u for u in sorted(p.units) if p.units[u].checked is not None] == ["OBC1"]
    saved = json.loads((LIBRARY / "OBC1.device.json").read_text(encoding="utf-8"))
    (rec,) = saved["devices"]
    assert rec["unit"]["checked"] == check.model_dump(mode="json")  # saved back with its check
    by_harness = {}
    for hid, h in sorted(p.harnesses.items()):
        view = review.review_view(p, h, [])
        sources = next(b for b in view.blocks if b.key == "sources")
        by_harness[hid] = [r.cells[1:3] for r in sources.rows if r.cells[0] == "Device"]
    obc = ("OBC1", "Checked by Reviewer 1 on 2026-01-15 against ICD-OBC EXAMPLE Issue 2")
    assert sorted(by_harness.values()) == [
        [obc, ("PCDU1", "not checked")],
        [obc, ("TTC1", "not checked")],
        [obc, ("TTC1-R", "not checked")],
    ]  # the Review page and sheet of each harness


def test_device_library_a_copy_shows_the_change_of_the_library_and_takes_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "p"
    assert main(["new", str(folder), "--template", "device-library"]) == 0
    doc = run(capsys, "libraries", str(folder), "--devices")
    assert [(d["device"], d["state"]) for d in doc["devices"]] == [
        ("OBC1", "up to date"),
        ("TTC1", "library changed"),
        ("TTC1-R", "library changed"),
    ]
    assert [(lib["path"], lib["devices"]) for lib in doc["libraries"]] == [("team-library", 2)]
    doc = run(capsys, "update-device", str(folder), "TTC1")
    (dev,) = doc["devices"]
    assert [(r["device"], r["connector"], r["pin"], r["field"], r["here"], r["library"]) for r in dev["rows"]] == [
        ("TTC1", "TTC1-J02", "3", "function", "Telemetry out, positive", "Telemetry and ranging out, positive"),
        ("TTC1-R", "TTC1-R-J02", "3", "function", "Telemetry out, positive", "Telemetry and ranging out, positive"),
    ]  # fmt: skip
    assert not doc["changed"]
    assert main(["update-device", str(folder), "--check"]) == 1
    assert main(["imports", str(folder), "--check"]) == 1  # the file differs from its record
    assert main(["update-device", str(folder), "TTC1", "--apply"]) == 0
    doc = run(capsys, "libraries", str(folder), "--devices")
    assert {d["state"] for d in doc["devices"]} == {"up to date"}
    p = load_project(folder).project
    assert p.connectors["TTC1-R-J02"].pins[2].function == "Telemetry and ranging out, positive"
    assert main(["update-device", str(folder), "--check"]) == 0


def test_device_library_an_edit_of_the_checked_device_makes_its_check_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "p"
    assert main(["new", str(folder), "--template", "device-library", "--no-journal"]) == 0
    loaded = load_project(folder)
    p = loaded.project
    rows = [{"pin": "1", "signal": "WDOG", "mode": "fixed", "function": "Watchdog out"}]
    History(p).execute("pin 1 of OBC1-J04", devices.ops_paste_rows(p, "OBC1-J04", rows))
    from harness_design_studio.core.io.saver import save_project

    save_project(p, folder)
    doc = run(capsys, "check", str(folder))
    assert [i["code"] for i in doc["issues"] if i["severity"] == "warning"] == [
        "device_check_stale"
    ]
    assert (
        run(capsys, "libraries", str(folder), "--devices")["devices"][0]["state"] == "changed here"
    )


# ---- extensions (section 4.14) ---------------------------------------------------------------------

EXTENSION_EXAMPLES = Path(__file__).resolve().parents[1] / "docs" / "examples" / "extensions"


def _fresh_extensions() -> None:
    plugins.forget_loaded()
    manager._RUNTIMES.clear()


def test_extensions_ships_the_example_extensions_of_the_manual() -> None:
    shipped = files(PROJECTS / "extensions" / "extensions")
    assert shipped == {
        rel: data for rel, data in files(EXTENSION_EXAMPLES).items() if rel != "README.md"
    }  # one copy of the files: docs/examples/extensions/
    assert sorted(shipped) == [
        "enabled.json",
        "minimum-wire-gauge-power.json",
        "plugins/duplicate-signal-wires.py",
        "power-wire-table.json",
    ]


def test_extensions_runs_the_data_rules_and_table_and_not_the_untrusted_plugin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "p"
    assert main(["new", str(folder), "--template", "extensions"]) == 0
    assert not trust.store_path().exists()  # `new` trusts nothing
    _fresh_extensions()
    doc = run(capsys, "extensions", str(folder), rc=1)  # 1: a plug-in is enabled and not loaded
    assert [(f["name"], f["status"]) for f in doc["files"]] == [
        ("minimum-wire-gauge-power", "applied"),
        ("power-wire-table", "applied"),
    ]
    (plugin,) = doc["plugins"]
    assert (plugin["name"], plugin["enabled"], plugin["trusted"], plugin["state"]) == (
        "duplicate-signal-wires", True, False, "untrusted",
    )  # fmt: skip
    drc_doc = run(capsys, "drc", str(folder))
    assert drc_doc["rules_run"] == 45  # the 43 of the tool and the two x- rules of the data files
    x_rules = {f["id"] for f in drc_doc["findings"] if f["rule"].startswith("x-")}
    assert x_rules == {"x-extension-problem.duplicate-signal-wires"}
    project = load_project(folder).project
    power = [w for h in project.harnesses.values() for w in h.wires if w.signal in ("PWR", "RTN")]
    assert sorted((w.id, w.gauge_awg) for w in power) == [("W002-001", 22), ("W002-002", 22)]
    (d,) = derive.explain_finding(project, "x-min-gauge-power", "W002-001")
    assert d.check is not None and (d.check.actual, d.check.limit, d.check.margin) == (22.0, 22.0, 0.0)  # fmt: skip
    assert main(["export", str(folder)]) == 0
    table = _table(folder / "outputs" / "system" / "extensions" / "power-wires.csv")
    assert [(r["Wire"], r["Gauge (AWG)"], r["Current (A)"], r["Table ampacity (A)"]) for r in table] == [
        ("W002-001", "22", "2", "7"),
        ("W002-002", "22", "2", "7"),
    ]  # fmt: skip


def test_extensions_trusting_the_plugin_is_the_exercise(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "p"
    assert main(["new", str(folder), "--template", "extensions", "--no-journal"]) == 0
    _fresh_extensions()
    assert main(["trust", str(folder), "duplicate-signal-wires", "--yes"]) == 0
    _fresh_extensions()
    drc_doc = run(capsys, "drc", str(folder))
    assert drc_doc["rules_run"] == 46 and drc_doc["open_errors"] == 0
    assert not [f for f in drc_doc["findings"] if f["rule"].startswith("x-")]  # silent here
    assert main(["extensions", str(folder)]) == 0
    assert main(["trust", str(folder), "duplicate-signal-wires", "--revoke"]) == 0
    _fresh_extensions()
