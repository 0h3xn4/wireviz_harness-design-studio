# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index,union-attr"
"""REQ-HARN-04. Splices (format 3, M6a; section 6 of `docs/ait/DESIGN_2.3_BRANCHING.md`): the model and its file
form, the plans of `core/splices.py` with their refusals, undo steps and journal rows, the
integrity warnings, the design rule `pin-shared`, the independent verifier and `explain`."""

import pytest

from harness_design_studio.core import drc, journal, splices
from harness_design_studio.core.commands import History, Put, apply_ops
from harness_design_studio.core.derive import explain_object
from harness_design_studio.core.derive_routing import routing_tree
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.generate.lengths import wire_length
from harness_design_studio.core.generate.mass import harness_mass
from harness_design_studio.core.integrity import check_integrity
from harness_design_studio.core.io.layout import model_hash, serialize
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.links import plan_add_link, plan_create_harness
from harness_design_studio.core.manual_harness import plan_add_connector, plan_new_harness
from harness_design_studio.core.model import ConfigFile, InterfaceInstance, Splice, evolve
from harness_design_studio.core.model.library import PART_CATEGORIES
from harness_design_studio.core.model.physical import SPLICE_ROLE
from harness_design_studio.core.samples import mini3
from harness_design_studio.core.splices import (
    plan_add_splice,
    plan_delete_splice,
    plan_splice_wire,
    splice_parts,
)
from harness_design_studio.core.vcs.diff import diff_flat, flatten_project, kind_name
from harness_design_studio.core.verify import verify_project
from harness_design_studio.core.wires import plan_add_wire, plan_wire_edit
from tests.splice_support import (
    HARNESS,
    SPLICE_PART,
    branch_leg_project,
    splice_part,
    splice_project,
)


def warnings_of(p, code):
    return sorted(i.object_id for i in check_integrity(p) if i.code == code)


def errors(p):
    return [i.render() for i in check_integrity(p) if i.severity == "error"]


def straight():
    """mini3 with the splice part and a drawn harness W003 from PCDU-J02 to OBC-J02, one wire."""
    p = mini3()
    generate_project(p)
    apply_ops(p, [Put("parts", splice_part())])
    ops, hid = plan_new_harness(p, "Drawn")
    apply_ops(p, ops)
    for box in ("PCDU-J02", "OBC-J02"):
        ops, _cid = plan_add_connector(p, hid, mates_with=box)
        apply_ops(p, ops)
    apply_ops(p, plan_add_wire(p, hid, f"{hid}-P1", "1", f"{hid}-P2", "1", signal="PWR"))
    return p, hid


# ---- the model and the files --------------------------------------------------------------------


def test_the_role_and_the_part_category_are_new_values_of_format_3():
    assert "splice" in PART_CATEGORIES
    assert SPLICE_ROLE == "splice"


def test_a_project_without_splices_writes_no_splice_file():
    p = mini3()
    files = serialize(p)
    assert "library/splice.json" not in files
    assert all('"role": "splice"' not in data.decode() for data in files.values())


def test_a_splice_and_its_part_round_trip_through_the_files(tmp_path):
    p = splice_project()
    save_project(p, tmp_path / "p")
    assert (tmp_path / "p" / "library" / "splice.json").exists()
    q = load_project(tmp_path / "p").project
    assert q.parts[SPLICE_PART] == p.parts[SPLICE_PART]
    assert q.harnesses[HARNESS] == p.harnesses[HARNESS]
    assert model_hash(q) == model_hash(p)
    assert [c.termination for c in q.harnesses[HARNESS].connectors[-1].pins] == ["solder"]


def test_the_splice_file_goes_when_the_last_splice_part_goes(tmp_path):
    p = splice_project()
    save_project(p, tmp_path / "p")
    h = p.harnesses[HARNESS]
    del p.harnesses[HARNESS]
    del p.parts[SPLICE_PART]
    assert h.id == HARNESS
    save_project(p, tmp_path / "p")
    assert not (tmp_path / "p" / "library" / "splice.json").exists()
    assert SPLICE_PART not in load_project(tmp_path / "p").project.parts


def test_the_old_splice_entry_is_kept_and_reported(tmp_path):
    p = splice_project()
    stub = Splice(id="W003-J1", name="old", wire_ids=["W003-001"])
    p.harnesses[HARNESS] = evolve(p.harnesses[HARNESS], splices=[stub])
    assert warnings_of(p, "splice_stub") == ["W003-J1"]
    save_project(p, tmp_path / "p")
    assert load_project(tmp_path / "p").project.harnesses[HARNESS].splices == [stub]


# ---- the plans ----------------------------------------------------------------------------------


def test_add_a_splice_is_one_undo_step_and_journalled():
    p, hid = straight()
    history = History(p)
    old = serialize(p)
    ops, sid = plan_add_splice(p, hid, SPLICE_PART, termination="crimp")
    history.execute("splice", ops)
    c = next(x for x in p.harnesses[hid].connectors if x.id == sid)
    assert (sid, c.role, c.part_id, [x.id for x in c.pins]) == (f"{hid}-X1", "splice", SPLICE_PART, ["1"])  # fmt: skip
    assert c.mates_with is None and c.unit_id is None and c.pins[0].termination == "crimp"
    rows = journal.rows_for_save(p, old, serialize(p))
    assert f"connector:{sid}" in {r["object"] for r in rows}
    assert warnings_of(p, "splice_unused") == [sid]
    history.undo()
    assert all(x.id != sid for x in p.harnesses[hid].connectors)


def test_a_splice_with_several_nodes_and_the_part_limit():
    p, hid = straight()
    p.parts[SPLICE_PART] = evolve(p.parts[SPLICE_PART], pin_count=3)
    ops, sid = plan_add_splice(p, hid, SPLICE_PART, nodes=3)
    apply_ops(p, ops)
    assert [x.id for x in p.harnesses[hid].connectors[-1].pins] == ["1", "2", "3"]
    with pytest.raises(EditError, match="has 3 nodes"):
        plan_add_splice(p, hid, SPLICE_PART, nodes=4)


@pytest.mark.parametrize(
    "case, match",
    [
        ("part", "not a splice part"),
        ("generated", "made by Generate"),
        ("released", "released"),
        ("nodes", "at least one node"),
        ("termination", "crimp, solder"),
    ],
)
def test_add_a_splice_refuses(case, match):
    p, hid = straight()
    kwargs: dict[str, object] = {}
    part = SPLICE_PART
    if case == "part":
        part = "EX-MICROD-9-F"
    if case == "generated":
        hid = "W002"
    if case == "released":
        p.harnesses[hid] = evolve(p.harnesses[hid], status="released")
    if case == "nodes":
        kwargs["nodes"] = 0
    if case == "termination":
        kwargs["termination"] = "glue"
    with pytest.raises(EditError, match=match):
        plan_add_splice(p, hid, part, **kwargs)


def test_a_harness_made_from_a_connection_takes_no_splice():
    p = mini3()
    apply_ops(p, [Put("parts", splice_part())])
    for cid in ("PCDU-J02", "OBC-J02"):
        c = p.connectors[cid]
        p.connectors[cid] = evolve(c, pins=[evolve(c.pins[0], signal="PWR"), *c.pins[1:]])
    ops, lid = plan_add_link(p, "PCDU-J02", "OBC-J02", pairs=[("1", "1")])
    apply_ops(p, ops)
    ops, made = plan_create_harness(p, lid)
    apply_ops(p, ops)
    with pytest.raises(EditError, match="connection"):
        plan_add_splice(p, made, SPLICE_PART)


def test_splice_a_wire_cuts_it_in_two_at_the_node():
    p, hid = straight()
    apply_ops(p, plan_wire_edit(p, [f"{hid}-001"], {"gauge_awg": 22, "colour": "red"}))
    w = p.harnesses[hid].wires[0]
    p.harnesses[hid] = evolve(
        p.harnesses[hid], wires=[evolve(w, strip_a_mm=4.0, strip_b_mm=5.0, length_m=None)]
    )
    ops, sid = plan_add_splice(p, hid, SPLICE_PART)
    apply_ops(p, ops)
    history = History(p)
    ops, new = plan_splice_wire(p, f"{hid}-001", sid)
    history.execute("splice wire", ops)
    a, b = p.harnesses[hid].wires
    assert (a.id, a.from_connector, a.to_connector, a.to_pin, a.strip_a_mm, a.strip_b_mm) == (
        f"{hid}-001", f"{hid}-P1", sid, "1", 4.0, None,
    )  # fmt: skip
    assert (b.id, b.from_connector, b.to_connector, b.to_pin, b.strip_b_mm) == (
        new, sid, f"{hid}-P2", "1", 5.0,
    )  # fmt: skip
    assert (b.signal, b.gauge_awg, b.colour, b.manual) == ("PWR", 22, "red", True)
    assert warnings_of(p, "splice_one_wire") == []
    history.undo()
    assert [x.id for x in p.harnesses[hid].wires] == [f"{hid}-001"]


def test_splice_a_wire_refuses_a_wire_with_its_own_length_and_a_wrong_node():
    p, hid = straight()
    ops, sid = plan_add_splice(p, hid, SPLICE_PART)
    apply_ops(p, ops)
    with pytest.raises(EditError, match="no node '2'"):
        plan_splice_wire(p, f"{hid}-001", sid, "2")
    w = p.harnesses[hid].wires[0]
    p.harnesses[hid] = evolve(p.harnesses[hid], wires=[evolve(w, length_m=1.5)])
    with pytest.raises(EditError, match="length of its own"):
        plan_splice_wire(p, f"{hid}-001", sid)
    with pytest.raises(EditError, match="not a splice"):
        plan_splice_wire(p, f"{hid}-001", f"{hid}-P1")


def test_add_wire_takes_a_node_that_carries_wires_already():
    p = splice_project()
    sid = f"{HARNESS}-X1"
    on = [w for w in p.harnesses[HARNESS].wires if sid in (w.from_connector, w.to_connector)]
    assert len(on) == 3
    assert not [f for f in drc.run(p) if f.rule == "pin-shared"]


def test_delete_a_splice_joins_two_wires_back_into_one():
    p, hid = straight()
    ops, sid = plan_add_splice(p, hid, SPLICE_PART)
    apply_ops(p, ops)
    apply_ops(p, plan_splice_wire(p, f"{hid}-001", sid)[0])
    history = History(p)
    history.execute("delete splice", plan_delete_splice(p, hid, sid))
    (w,) = p.harnesses[hid].wires
    assert (w.id, w.from_connector, w.to_connector, w.to_pin) == (f"{hid}-001", f"{hid}-P1", f"{hid}-P2", "1")  # fmt: skip
    assert all(c.id != sid for c in p.harnesses[hid].connectors)
    history.undo()
    assert len(p.harnesses[hid].wires) == 2


def test_delete_a_splice_refuses_a_node_with_three_wires_and_a_segment():
    p = splice_project()
    with pytest.raises(EditError, match="segments"):
        plan_delete_splice(p, HARNESS, f"{HARNESS}-X1")
    h = p.harnesses[HARNESS]
    p.harnesses[HARNESS] = evolve(h, segments=[])
    with pytest.raises(EditError, match="joins 3 wires"):
        plan_delete_splice(p, HARNESS, f"{HARNESS}-X1")


def test_an_unused_splice_is_deleted_at_once():
    p, hid = straight()
    ops, sid = plan_add_splice(p, hid, SPLICE_PART)
    apply_ops(p, ops)
    apply_ops(p, plan_delete_splice(p, hid, sid))
    assert all(c.id != sid for c in p.harnesses[hid].connectors)


def test_the_splice_parts_are_the_ones_of_the_category():
    p, _hid = straight()
    assert [x.id for x in splice_parts(p)] == [SPLICE_PART]
    assert splices.splices_of(p.harnesses["W001"]) == []


# ---- integrity, the rules, the verifier ---------------------------------------------------------


def test_a_y_harness_through_a_splice_is_consistent():
    p = splice_project()
    assert errors(p) == []
    for code in ("splice_unused", "splice_one_wire", "splice_signals_mixed", "splice_stub"):
        assert warnings_of(p, code) == []
    rep = verify_project(p)
    assert rep.ok, [i.render() for i in rep.issues]
    assert not [i for i in rep.issues if i.code in ("pin_shared", "pin_reused")]


def test_a_splice_on_a_branch_point_leg_has_its_lengths():
    p = branch_leg_project()
    h = p.harnesses["W004"]
    lengths = {w.id: wire_length(h, w) for w in h.wires}
    assert lengths == pytest.approx(
        {"W004-001": 0.5, "W004-002": 0.8, "W004-003": 0.4, "W004-004": 0.9}
    )
    assert errors(p) == [] and verify_project(p).ok


def test_mixed_signals_on_a_node_are_reported():
    p = splice_project()
    h = p.harnesses[HARNESS]
    wires = [evolve(w, signal="RTN") if w.id == f"{HARNESS}-002" else w for w in h.wires]
    p.harnesses[HARNESS] = evolve(h, wires=wires)
    assert warnings_of(p, "splice_signals_mixed") == [f"{HARNESS}-X1"]


def test_a_splice_with_a_mate_a_connector_part_or_in_a_generated_harness_is_an_error():
    p = splice_project()
    h = p.harnesses[HARNESS]
    x1 = h.connectors[3]
    assert x1.role == "splice"
    for bad, code in (
        (evolve(x1, mates_with="OBC-J01"), "splice_mated"),
        (evolve(x1, part_id="EX-MICROD-9-F"), "wrong_part_category"),
    ):
        q = splice_project()
        conns = [bad if c.id == x1.id else c for c in h.connectors]
        q.harnesses[HARNESS] = evolve(h, connectors=conns)
        assert code in {i.code for i in check_integrity(q) if i.severity == "error"}
    q = splice_project()
    q.harnesses[HARNESS] = evolve(h, generated=True)
    assert "splice_in_generated_harness" in {i.code for i in check_integrity(q)}


def test_nets_through_a_splice_for_the_design_rules():
    """`pin-shared` leaves the nodes out, and still reports a plain pin with two wires."""
    p = splice_project()
    assert not [f for f in drc.run(p) if f.rule == "pin-shared"]
    h = p.harnesses[HARNESS]
    extra = evolve(h.wires[1], id=f"{HARNESS}-099", from_connector=f"{HARNESS}-P2", from_pin="3")
    p.harnesses[HARNESS] = evolve(h, wires=[*h.wires, extra])
    hits = [f for f in drc.run(p) if f.rule == "pin-shared"]
    assert len(hits) == 1 and f"{HARNESS}-P2" in hits[0].title and "X1" not in hits[0].title


def interface_project():
    """A drawn harness whose wires carry an interface PWR from PCDU-J02 to OBC-J02, through a
    splice, with a third end on OBC-J03 that carries no interface."""
    p = splice_project()
    itype = next(t for t in p.interface_types.values() if [s.name for s in t.signals][:1] == ["PWR"])  # fmt: skip
    names = [s.name for s in itype.signals]
    ends = [{"unit_id": "PCDU", "connector_id": "PCDU-J02"}, {"unit_id": "OBC", "connector_id": "OBC-J02"}]  # fmt: skip
    i = InterfaceInstance.model_validate({"id": "IF-SPLICE", "name": "power", "type_id": itype.id, "endpoints": ends})  # fmt: skip
    p.interfaces[i.id] = i
    for cid in ("PCDU-J02", "OBC-J02"):
        c = p.connectors[cid]
        pins = [evolve(x, signal=names[k], interface_id=i.id) if k < len(names) else x for k, x in enumerate(c.pins)]  # fmt: skip
        p.connectors[cid] = evolve(c, pins=pins)
    h = p.harnesses[HARNESS]
    far_b = f"{HARNESS}-P3"
    wires = [
        w if far_b in (w.from_connector, w.to_connector) else evolve(w, interface_id=i.id)
        for w in h.wires
    ]
    p.harnesses[HARNESS] = evolve(h, wires=wires)
    return p, i, names


def test_the_verifier_counts_an_interface_per_net_through_a_splice():
    p, i, names = interface_project()
    if names[:2] != ["PWR", "RTN"]:
        pytest.skip("the power type of mini3 has other signals")
    rep = verify_project(p)
    mine = [x for x in rep.issues if x.object_id in (i.id, *(w.id for w in p.harnesses[HARNESS].wires))]  # fmt: skip
    assert [x.render() for x in mine if x.severity == "error"] == []


def test_the_verifier_refuses_a_wrong_splice():
    """A net through a splice that joins the wrong pins (PWR of one end to RTN of the other) is a
    connection the type does not define, and the right one is missing."""
    p, i, names = interface_project()
    if names[:2] != ["PWR", "RTN"]:
        pytest.skip("the power type of mini3 has other signals")
    h = p.harnesses[HARNESS]
    wires = [evolve(w, to_pin="2") if w.id == f"{HARNESS}-002" else w for w in h.wires]
    wires = [evolve(w, to_pin="1") if w.id == f"{HARNESS}-005" else w for w in wires]
    p.harnesses[HARNESS] = evolve(h, wires=wires)
    codes = {x.code for x in verify_project(p).errors}
    assert {"wire_extra", "signal_missing"} <= codes


def test_explain_of_a_splice_names_its_nets_and_routing_lists_it():
    p = splice_project()
    (d,) = explain_object(p, f"{HARNESS}-X1")
    assert d.id == "splice"
    assert d.text == f"node 1: {HARNESS}-P1.1, {HARNESS}-P2.1, {HARNESS}-P3.1"
    tree = routing_tree(p, HARNESS)
    assert [x["id"] for x in tree.splices] == [f"{HARNESS}-X1", f"{HARNESS}-X2"]
    assert any("(splice)" in line for line in tree.lines())
    assert routing_tree(p, "W001").splices == []


def test_the_mass_counts_a_splice_only_under_full_bom():
    p = splice_project()
    h = p.harnesses[HARNESS]
    default = harness_mass(p, h)
    p.config["model"] = ConfigFile(
        name="model", placeholder=False, values={"mass_model": "full_bom"}
    )
    full = harness_mass(p, h)
    assert full.total_g == pytest.approx(default.total_g + 2 * 0.4)


def test_the_change_report_calls_it_a_splice():
    p, hid = straight()
    before = flatten_project(p)
    apply_ops(p, plan_add_splice(p, hid, SPLICE_PART)[0])
    changes = [
        c for c in diff_flat(before, flatten_project(p)).changes if c.kind == "cable_connector"
    ]
    assert [kind_name(c) for c in changes] == ["Splice"]
