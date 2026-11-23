# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""What a length is measured from, and where a wire's length comes from (design of 4.1.0, part D,
sections 6.1 and 6.3; pull request 1).

`lengths.reference_text(project)` words the reference from the settings in force, with the
project's own numbers and none invented, as the four short sentences of `lengths.reference_lines` (a
sheet prints each on a row of its own, pull request 3); `lengths.length_origin(h, w)` says `on the wire`,
`locked`, `segments only, no service loops` or nothing. `derive.wire_length_derivation` starts from
`length_origin`, so the two agree on every wire of every example, and its texts are as before.

REQ-WIRE-09 (format 5, design of 5.0.0 part A, pull request 2): the second half of this file holds
the face ends and the depths: the rules of the files, `end_depths`, the example of section 4.1,
Generate, the warnings of `check`, the five sentences, the face marks, the imports, `explain`, the
scripting function and the outputs of the fixture `format5`."""

from pathlib import Path

import pytest

from harness_design_studio.core import derive
from harness_design_studio.core.generate.lengths import (
    ORIGIN_LOCKED,
    ORIGIN_NONE,
    ORIGIN_ON_WIRE,
    ORIGIN_SEGMENTS,
    length_origin,
    reference_lines,
    reference_text,
)
from harness_design_studio.core.model import (
    ConfigFile,
    Connector,
    Harness,
    Pin,
    Project,
    Segment,
    Wire,
)
from harness_design_studio.core.samples import mini3, new_project
from tests.plan_support import GOLDEN_PROJECTS, golden_project

START = (
    "Lengths run from the rear of a connector, where the wires leave its body or backshell. They "
    "follow the routing segments through the centre of each branch point to the rear of the other "
    "connector. A wire Generate made adds "
)
END = '. "Locked" is a length a person typed; "segments only" has no service loops.'


def with_config(p: Project, file: str, values: dict[str, object]) -> Project:
    old = p.config.get(file)
    keep = dict(old.values) if old is not None else {}
    p.config = {**p.config, file: ConfigFile(name=file, placeholder=False, values={**keep, **values})}  # fmt: skip
    return p


def test_the_reference_of_flatsat_names_its_two_loops_of_a_tenth_of_a_metre() -> None:
    assert reference_text(golden_project("flatsat")) == START + "2 service loops of 0.1 m" + END


def test_without_a_service_loop_the_reference_says_the_setting_is_not_set() -> None:
    p = mini3()
    assert p.config["generation"].values["service_loop_m"] is None
    assert reference_text(p) == (
        START + "no service loop (config/generation.json: service_loop_m is not set)" + END
    )


@pytest.mark.parametrize(
    ("loops", "loop", "words"),
    [
        (2, 0.25, "2 service loops of 0.25 m"),
        (1, 0.1, "1 service loop of 0.1 m"),
        (4, 0.0, "4 service loops of 0 m"),
        (2, 1e-07, "2 service loops of 0.0000001 m"),
        (0, 0.1, "no service loop (config/model.json: service_loops_per_wire is 0)"),
    ],
)
def test_the_loops_are_the_project_s(loops: int, loop: float, words: str) -> None:
    p = with_config(new_project(), "generation", {"service_loop_m": loop})
    with_config(p, "model", {"service_loops_per_wire": loops})
    assert reference_text(p) == START + words + END


def test_the_length_model_with_allowance_and_twist_names_both_numbers() -> None:
    p = with_config(new_project(), "generation", {"service_loop_m": 0.1})
    with_config(
        p, "model",
        {"length_model": "path_loops_allowance_twist", "twist_takeup_fraction": 0.02, "cut_allowance_m": 0.05},
    )  # fmt: skip
    assert (
        reference_text(p)
        == START
        + (
            "2 service loops of 0.1 m, the take-up of twisting (0.02) for a wire of a twisted "
            "construction, and a cut allowance of 0.05 m"
        )
        + END
    )
    # its defaults are the tool's own zeros, said as such
    q = with_config(new_project(), "model", {"length_model": "path_loops_allowance_twist"})
    assert (
        reference_text(q)
        == START
        + (
            "no service loop (config/generation.json: service_loop_m is not set), the take-up of "
            "twisting (0) for a wire of a twisted construction, and a cut allowance of 0 m"
        )
        + END
    )


# ---- where a wire's length comes from ------------------------------------------------------------


def _harness(wires: list[Wire], segments: list[Segment]) -> Harness:
    cons = [
        Connector(id=f"W001-P{k}", name=f"P{k}", role="cable", part_id="X", pins=[Pin(id="1")])
        for k in (1, 2, 3)
    ]
    return Harness(id="W001", name="H", connectors=cons, wires=wires, segments=segments)


def _wire(n: int, to: str = "W001-P2", **kw: object) -> Wire:
    return Wire(id=f"W001-{n:03d}", from_connector="W001-P1", from_pin="1", to_connector=to, to_pin="1", **kw)  # type: ignore[arg-type]  # fmt: skip


def test_the_four_origins() -> None:
    segs = [
        Segment(id="W001-L1", from_node="W001-P1", to_node="W001-P2", length_m=1.0),
        Segment(id="W001-L2", from_node="W001-P1", to_node="W001-P3"),
    ]
    on_wire = _wire(1, length_m=2.0)
    locked = _wire(2, length_m=2.0, locked=True)
    segments = _wire(3)
    none = _wire(4, to="W001-P3")  # its segment has no length
    h = _harness([on_wire, locked, segments, none], segs)
    assert length_origin(h, on_wire) == ORIGIN_ON_WIRE == "on the wire"
    assert length_origin(h, locked) == ORIGIN_LOCKED == "locked"
    assert length_origin(h, segments) == ORIGIN_SEGMENTS == "segments only, no service loops"
    assert length_origin(h, none) == ORIGIN_NONE == ""
    assert length_origin(_harness([segments], []), segments) == ORIGIN_NONE  # no segments at all


def _basis(d: derive.Derivation) -> str:
    return d.steps[-1].expression if d.steps else ""


def _agrees(project: Project, h: Harness, w: Wire) -> None:
    from harness_design_studio.core.generate.lengths import end_depths

    origin = length_origin(h, w, end_depths(project, h))
    d = derive.wire_length_derivation(project, h, w)
    basis = _basis(d)
    if origin == ORIGIN_NONE:
        assert d.value is None and d.missing, w.id
    elif origin == ORIGIN_SEGMENTS:
        assert basis.startswith("the routing segments of its path"), (w.id, basis)
    elif origin == ORIGIN_LOCKED:
        assert w.locked and basis.startswith(("generated", "overridden", "entered by hand")), w.id
    else:
        # not locked, or locked by an override of another value (its length follows the path)
        assert "length_m" not in w.overrides and not (w.locked and not w.overrides), w.id
        assert basis.startswith(("generated", "a length stored")), (w.id, basis)


@pytest.mark.parametrize("name", GOLDEN_PROJECTS)
def test_the_origin_agrees_with_the_explanation_on_every_wire(name: str) -> None:
    p = golden_project(name)
    seen = set()
    for h in p.harnesses.values():
        for w in h.wires:
            _agrees(p, h, w)
            seen.add(length_origin(h, w))
    assert seen


def test_the_origin_agrees_with_the_explanation_in_every_case() -> None:
    p = mini3()
    segs = [
        Segment(id="W001-L1", from_node="W001-P1", to_node="W001-P2", length_m=1.0),
        Segment(id="W001-L2", from_node="W001-P1", to_node="W001-P3"),
    ]
    wires = [
        _wire(1, length_m=2.0),
        _wire(2, length_m=2.0, locked=True),
        _wire(3, length_m=2.0, locked=True, overrides={"length_m": "measured on the mock-up"}),
        _wire(4),
        _wire(5, to="W001-P3"),
    ]
    h = _harness(wires, segs)
    assert [length_origin(h, w) for w in wires] == [
        ORIGIN_ON_WIRE, ORIGIN_LOCKED, ORIGIN_LOCKED, ORIGIN_SEGMENTS, ORIGIN_NONE,
    ]  # fmt: skip
    for w in wires:
        _agrees(p, h, w)
    # the texts of the explanation are those of 4.0.1
    texts = [_basis(derive.wire_length_derivation(p, h, w)) for w in wires[:4]]
    assert texts == [
        (
            "a length stored on the wire that does not equal its path plus two service loops "
            "(entered, imported, or the segments changed since)"
        ),
        "entered by hand and locked, so generation keeps it",
        "overridden by the engineer (reason: measured on the mock-up), so generation keeps it",
        (
            "the routing segments of its path (no length is stored on the wire; no service loop is "
            "added here)"
        ),
    ]
    assert derive.wire_length_derivation(p, h, wires[4]).missing == (
        "the length of every routing segment on the path: W001-L2",
    )


@pytest.mark.parametrize("name", GOLDEN_PROJECTS)
def test_the_reference_is_four_sentences_a_sheet_prints_a_row_each(name: str) -> None:
    p = golden_project(name)
    lines = reference_lines(p)
    assert len(lines) == 4 and " ".join(lines) == reference_text(p)
    assert lines[0].startswith("Lengths run from") and lines[1].endswith("the other connector.")
    assert lines[2].startswith("A wire Generate made adds ") and lines[2].endswith(".")
    assert max(len(line) for line in lines[:2]) <= 110  # one printed line each
    assert lines[3] == '"Locked" is a length a person typed; "segments only" has no service loops.'


# ---- a wire locked by an override of another value (found by the end-to-end test of 4.1.0) ------


def test_an_override_of_the_gauge_alone_leaves_the_length_to_the_path(tmp_path: Path) -> None:
    """An override of the gauge, part or colour locks the wire, but Generate gives it the length of
    its path again ("the other values follow the design"), so its length is *on the wire*, not
    *locked*; the verifier's copy says the same, `explain` says *generated*, and a changed segment
    moves the length. An override of the length is *locked* and stays."""
    from harness_design_studio import api
    from harness_design_studio.core import change_ops
    from harness_design_studio.core.io.loader import load_project
    from harness_design_studio.core.io.saver import save_project
    from harness_design_studio.core.outputs import verify_production as vp

    p = golden_project("flatsat")
    h = p.harnesses["W001"]
    gauge, length = [w for w in h.wires if w.length_m is not None and not w.locked][:2]
    assert change_ops.set_override(p, gauge.id, "gauge_awg", 24, "Example reason")
    assert change_ops.set_override(p, length.id, "length_m", 9.5, "Example reason")
    save_project(p, tmp_path)
    assert api.generate(tmp_path).ok
    q = load_project(tmp_path).project
    hq = q.harnesses["W001"]
    g, n = (next(w for w in hq.wires if w.id == x.id) for x in (gauge, length))
    assert g.locked and n.locked and n.length_m == 9.5
    assert length_origin(hq, g) == ORIGIN_ON_WIRE == vp._length_origin(hq, g)
    assert length_origin(hq, n) == ORIGIN_LOCKED == vp._length_origin(hq, n)
    assert _basis(derive.wire_length_derivation(q, hq, g)).startswith("generated")
    assert _basis(derive.wire_length_derivation(q, hq, n)).startswith("overridden")
    for w in (g, n):
        _agrees(q, hq, w)


# ==== format 5, part A: where a length is measured to, and the depth of a part ======================
# REQ-WIRE-09 (design of 5.0.0 `docs/ait/DESIGN_5.0_FORMAT_5.md` sections 3.2, 4, 10 and 13, pull
# request 2). A cable connector says `length_to` (`face` or `rear`; unset: the setting
# `model.length_reference`, `rear` by default); a connector or backshell part has `depth_mm`. At a
# face end the depth of the connector part and of each backshell on it is taken off each wire, so
# every length stays rear to rear; with no depth the length is not known and `check` says why.


def _first_steps_face(depth: float | None = 25.0, shell: float | None = 30.0) -> Project:
    """The example of section 4.1 on the `first-steps` example: W002 has one segment W002-L1 of
    1.200 m between W002-P1 and W002-P2 (both of part EX-MICROD-9-M), both measured to the face,
    a backshell on W002-P1, and two service loops of 0.1 m."""
    from harness_design_studio.core.generate.engine import generate_project
    from harness_design_studio.core.model import Accessory, Part, evolve

    p = golden_project("first-steps")
    with_config(p, "generation", {"service_loop_m": 0.1})
    p.parts["EX-MICROD-9-M"] = evolve(p.parts["EX-MICROD-9-M"], depth_mm=depth)
    p.parts["EX-BACKSHELL-9"] = Part(id="EX-BACKSHELL-9", category="backshell", depth_mm=shell)
    h = p.harnesses["W002"]
    p.harnesses["W002"] = evolve(
        h,
        connectors=[evolve(c, length_to="face") for c in h.connectors],
        segments=[evolve(s, length_m=1.2) for s in h.segments],
        accessories=[
            Accessory(id="W002-A1", kind="backshell", part_id="EX-BACKSHELL-9", target="W002-P1")
        ],
    )
    generate_project(p)
    return p


def test_the_new_keys_are_sparse_and_absent_by_default() -> None:
    from harness_design_studio.core.model import Part

    c = Connector(id="W001-P1", name="P1", role="cable", part_id="X")
    assert c.length_to is None and "length_to" not in c.model_dump()
    assert "depth_mm" not in Part(id="X", category="connector").model_dump()
    assert Connector(id="W001-P1", name="P1", role="cable", part_id="X", length_to="face").model_dump()["length_to"] == "face"  # fmt: skip


@pytest.mark.parametrize(
    ("make", "words"),
    [
        (
            lambda: Connector(
                id="OBC-J01", name="J01", role="box", part_id="X", unit_id="OBC", length_to="face"
            ),
            "only a cable connector",
        ),  # fmt: skip
        (
            lambda: Connector(
                id="W001-X1", name="X1", role="splice", part_id="X", length_to="rear"
            ),
            "only a cable connector",
        ),  # fmt: skip
        (
            lambda: Connector(
                id="W001-P1",
                name="P1",
                role="cable",
                part_id="X",
                length_to="middle",  # type: ignore[arg-type]
            ),
            "face",
        ),  # fmt: skip
    ],
)
def test_the_rule_of_the_file_for_length_to(make: object, words: str) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match=words):
        make()  # type: ignore[operator]


@pytest.mark.parametrize(
    ("category", "depth", "words"),
    [
        ("wire", 10.0, "only a connector or backshell part has a depth"),
        ("contact", 10.0, "only a connector or backshell part has a depth"),
        ("connector", 0.0, "greater than 0"),
        ("connector", 1000.5, "less than or equal to 1000"),
        ("backshell", -1.0, "greater than 0"),
    ],
)
def test_the_rule_of_the_file_for_depth_mm(category: str, depth: float, words: str) -> None:
    from pydantic import ValidationError

    from harness_design_studio.core.model import Part

    with pytest.raises(ValidationError, match=words):
        Part(id="X", category=category, depth_mm=depth)  # type: ignore[arg-type]
    assert Part(id="X", category="backshell", depth_mm=1000.0).depth_mm == 1000.0


def test_end_depths_adds_the_connector_and_its_backshell_and_says_why_one_is_missing() -> None:
    from harness_design_studio.core.generate.lengths import NO_FACE_END, end_depths
    from harness_design_studio.core.model import Accessory, evolve

    p = _first_steps_face()
    h = p.harnesses["W002"]
    ends = end_depths(p, h)
    assert ends.depths == {"W002-P1": 0.055, "W002-P2": 0.025} and ends.missing == {}
    assert ends.faces == ("W002-P1", "W002-P2")
    assert end_depths(p, p.harnesses["W001"]) is NO_FACE_END  # no face end: the 4.4.0 lengths
    # a backshell without a part, a backshell part without a depth, a connector without one
    for acc, part_depth, reason in (
        (
            Accessory(id="W002-A2", kind="backshell", target="W002-P1"),
            25.0,
            "its backshell W002-A2 has no part",
        ),  # fmt: skip
        (
            Accessory(id="W002-A2", kind="backshell", part_id="EX-NONE", target="W002-P1"),
            25.0,
            "part EX-NONE of its backshell W002-A2 is not in the library",
        ),  # fmt: skip
        (None, None, "part EX-MICROD-9-M has no depth (library: depth_mm)"),
    ):
        q = _first_steps_face(depth=part_depth)
        hq = q.harnesses["W002"]
        if acc is not None:
            hq = evolve(hq, accessories=[*hq.accessories, acc])
        assert end_depths(q, hq).missing["W002-P1"] == reason
    q = _first_steps_face(shell=None)
    assert end_depths(q, q.harnesses["W002"]).missing == {
        "W002-P1": "part EX-BACKSHELL-9 of its backshell W002-A1 has no depth (library: depth_mm)"
    }


def test_the_example_of_section_4_1_gives_1_120_m_rear_to_rear_and_generate_stores_1_320_m() -> None:  # fmt: skip
    from harness_design_studio.core.generate.lengths import end_depths, wire_length
    from harness_design_studio.core.model import evolve

    p = _first_steps_face()
    h = p.harnesses["W002"]
    from_p1 = [w for w in h.wires if "W002-P1" in (w.from_connector, w.to_connector)]
    assert from_p1 and all(w.length_m == pytest.approx(1.32) for w in h.wires)
    bare = evolve(h, wires=[evolve(w, length_m=None) for w in h.wires])
    for w in bare.wires:
        assert wire_length(bare, w, end_depths(p, bare)) == pytest.approx(1.12)
        assert wire_length(bare, w) == pytest.approx(1.2)  # without the ends: the path, as 4.4.0
    assert derive.wire_length_derivation(p, h, h.wires[0]).value == pytest.approx(1.32)


def test_generate_keeps_length_to_and_a_change_makes_the_harnesses_out_of_date() -> None:
    from harness_design_studio.core.commands import apply_ops
    from harness_design_studio.core.connector_edit import plan_set_length_to
    from harness_design_studio.core.generate.engine import generate_project
    from harness_design_studio.core.generation_status import generation_status

    p = _first_steps_face()
    assert generation_status(p) == "current"
    assert [c.length_to for c in p.harnesses["W002"].connectors] == ["face", "face"]
    apply_ops(p, plan_set_length_to(p, "W002", "W002-P2", None))
    assert generation_status(p) == "stale"  # the length Generate stores depends on it
    generate_project(p)
    h = p.harnesses["W002"]
    assert [c.length_to for c in h.connectors] == ["face", None]
    assert all(w.length_m == pytest.approx(1.2 - 0.055 + 0.2) for w in h.wires)


def test_the_setting_face_measures_every_cable_connector_to_its_face_but_one_that_says_rear() -> None:  # fmt: skip
    from harness_design_studio.core.generate.lengths import end_depths, face_line, reference_lines
    from harness_design_studio.core.model import evolve

    p = _first_steps_face()
    with_config(p, "model", {"length_reference": "face"})
    h = p.harnesses["W002"]
    h = evolve(h, connectors=[evolve(c, length_to="rear" if c.id == "W002-P2" else None) for c in h.connectors])  # fmt: skip
    assert end_depths(p, h).faces == ("W002-P1",)
    assert face_line(p, h) == (
        "The segments run to the mating face of each connector (model.length_reference), but at "
        "W002-P2; the depth of the connector and its backshell is taken off each wire."
    )
    assert len(reference_lines(p, h)) == 5 and len(reference_lines(p)) == 4
    assert end_depths(p, p.harnesses["W001"]).faces == ("W001-P1", "W001-P2")


def test_the_fifth_sentence_names_the_face_ends() -> None:
    from harness_design_studio.core.generate.lengths import reference_lines

    p = _first_steps_face()
    assert reference_lines(p, p.harnesses["W002"])[4] == (
        "At W002-P1 and W002-P2 the segments run to the mating face; the depth of the connector "
        "and its backshell is taken off each wire there."
    )
    assert len(reference_lines(p, p.harnesses["W001"])) == 4


def test_a_missing_depth_leaves_no_length_with_a_note_and_the_warning_of_check() -> None:
    from harness_design_studio.core import drc
    from harness_design_studio.core.integrity import check_integrity

    p = _first_steps_face(depth=None)
    h = p.harnesses["W002"]
    assert all(w.length_m is None for w in h.wires)
    assert p.generation is not None
    notes = [n for lines in p.generation.provenance.values() for n in lines if "has no length" in n]
    assert any(
        "W002-P1 is measured to its face and part EX-MICROD-9-M has no depth (library: depth_mm)"
        in n
        for n in notes
    ), notes
    found = {(i.code, i.object_id, i.message) for i in check_integrity(p) if i.code.startswith("length_")}  # fmt: skip
    assert ("length_depth_missing", "W002-P1", "W002-P1 is measured to its face, but part EX-MICROD-9-M has no depth (library: depth_mm), so the wires there have no length") in found  # fmt: skip
    assert all(i.severity == "warning" for i in check_integrity(p) if i.code.startswith("length_"))
    hits = [f for f in drc.run(p) if f.rule == "model-inconsistent" and "measured to its face" in f.title]  # fmt: skip
    assert hits  # a warning of check reaches the DRC as model-inconsistent
    d = derive.wire_length_derivation(p, h, h.wires[0])
    assert d.value is None and "W002-P1: it is measured to its face" in d.missing[0]


def test_segments_shorter_than_the_depths_leave_no_length() -> None:
    from harness_design_studio.core.generate.lengths import end_depths, wire_length
    from harness_design_studio.core.integrity import check_integrity
    from harness_design_studio.core.model import evolve

    p = _first_steps_face()
    h = p.harnesses["W002"]
    p.harnesses["W002"] = h = evolve(
        h,
        segments=[evolve(s, length_m=0.05) for s in h.segments],
        wires=[evolve(w, length_m=None) for w in h.wires],
    )
    assert all(wire_length(h, w, end_depths(p, h)) is None for w in h.wires)
    below = [i for i in check_integrity(p) if i.code == "length_below_depth"]
    assert {i.object_id for i in below} == {w.id for w in h.wires}
    assert "(0.05 m) are not longer than the depths taken off at its face ends (0.08 m)" in below[0].message  # fmt: skip


def test_a_project_without_data_of_format_5_has_no_new_check() -> None:
    from harness_design_studio.core.integrity import length_issues

    for name in GOLDEN_PROJECTS:
        if name != "format5":
            assert length_issues(golden_project(name)) == [], name


def test_the_explanation_names_the_depths_and_the_path_from_rear_to_rear() -> None:
    p = _first_steps_face()
    h = p.harnesses["W002"]
    w = next(x for x in h.wires if x.from_connector == "W002-P1")
    d = derive.wire_length_derivation(p, h, w)
    names = [i.name for i in d.inputs]
    assert "Depth of part EX-MICROD-9-M (W002-P1, measured to its face)" in names
    assert "Depth of backshell part EX-BACKSHELL-9 (W002-P1, backshell W002-A1)" in names
    assert "Depth of part EX-MICROD-9-M (W002-P2, measured to its face)" in names
    step = next(s for s in d.steps if s.label == "Path from rear to rear")
    assert step.expression == "1.2 − 0.08" and step.value == pytest.approx(1.12)
    assert "A-LENGTH-TO" in d.assumptions
    assert "− depth of each face end" in d.equation
    assert _basis(d).startswith("generated")
    text = derive.render(d)
    assert "Path from rear to rear" in text


def test_the_length_to_plan_refuses_what_has_no_face_and_a_released_harness() -> None:
    from harness_design_studio.core.connector_edit import plan_set_length_to
    from harness_design_studio.core.edit import EditError
    from harness_design_studio.core.model import evolve

    p = _first_steps_face()
    assert plan_set_length_to(p, "W002", "W002-P1", "face") == []  # as it is: nothing to do
    with pytest.raises(EditError, match="face, rear"):
        plan_set_length_to(p, "W002", "W002-P1", "middle")
    p.harnesses["W002"] = evolve(p.harnesses["W002"], status="released")
    with pytest.raises(EditError, match="released"):
        plan_set_length_to(p, "W002", "W002-P1", None)


def test_the_depth_plan_refuses_another_category_and_a_part_of_a_released_harness() -> None:
    from harness_design_studio.core.build_data import plan_set_part_depth
    from harness_design_studio.core.edit import EditError
    from harness_design_studio.core.model import evolve

    p = _first_steps_face()
    with pytest.raises(EditError, match="Only a connector or backshell part"):
        plan_set_part_depth(p, "EX-WIRE-SINGLE", 10.0)
    with pytest.raises(EditError, match="at most 1000"):
        plan_set_part_depth(p, "EX-MICROD-9-M", 1001.0)
    assert plan_set_part_depth(p, "EX-MICROD-9-M", 25.0) == []
    assert plan_set_part_depth(p, "EX-MICROD-9-M", None)
    p.harnesses["W002"] = evolve(p.harnesses["W002"], status="released")
    with pytest.raises(EditError, match="W002, which is released"):
        plan_set_part_depth(p, "EX-BACKSHELL-9", 12.0)


def test_a_part_with_a_depth_makes_the_device_library_file_version_4() -> None:
    from harness_design_studio.core import device_library, subsystem_library

    p = golden_project("first-steps")
    uid = sorted(p.units)[0]
    content = device_library.export_devices(p, [uid])
    assert device_library.content_version(content) < 4
    part = content["parts"][0]
    content["parts"][0] = {**part, "depth_mm": 25.0} if isinstance(part, dict) else part.model_copy(update={"depth_mm": 25.0})  # fmt: skip
    assert device_library.content_version(content) == 4
    assert subsystem_library.content_version(content) == 3


def test_the_setting_is_rear_by_default_and_checked(tmp_path: Path) -> None:
    from harness_design_studio.cli.main import main
    from harness_design_studio.core import configcheck, settings
    from harness_design_studio.core.generate.lengths import length_reference
    from harness_design_studio.core.io.loader import load_project

    p = new_project()
    assert length_reference(p) == "rear"
    s = settings.setting("model", "length_reference")
    assert s is not None and s.choices == ("rear", "face") and s.assumption == "A-LENGTH-TO"
    with_config(p, "model", {"length_reference": "middle"})
    assert any("length_reference" in i.message for i in configcheck.validate_model(p))
    assert length_reference(p) == "rear"  # a damaged value is reported, never used
    root = tmp_path / "p"
    assert main(["new", str(root)]) == 0
    assert main(["settings", str(root), "--set", "model.length_reference=face"]) == 0
    assert length_reference(load_project(root).project) == "face"


def test_import_parts_reads_a_depth_column(tmp_path: Path) -> None:
    from harness_design_studio.core.commands import Put
    from harness_design_studio.core.library_import import guess_mapping, plan_parts_import
    from harness_design_studio.core.model import Part

    p = golden_project("first-steps")
    for heading in ("Depth (mm)", "Depth", "Connector depth"):
        table = [["Part ID", "Category", heading], ["EX-MICROD-9-M", "connector", "25,5"], ["EX-BS", "backshell", "30"], ["EX-W", "wire", ""]]  # fmt: skip
        plan = plan_parts_import(p, table, guess_mapping(table[0]), approved=["approved"])
        assert all(r.ok for r in plan.rows), [r.message for r in plan.rows]
        parts = {op.obj.id: op.obj for op in plan.ops if isinstance(op, Put) and isinstance(op.obj, Part)}  # fmt: skip
        assert parts["EX-MICROD-9-M"].depth_mm == 25.5 and parts["EX-BS"].depth_mm == 30.0
        assert parts["EX-W"].depth_mm is None
    bad = [["Part ID", "Category", "Depth (mm)"], ["EX-W", "wire", "3"], ["EX-C", "connector", "0"]]
    plan = plan_parts_import(p, bad, guess_mapping(bad[0]), approved=["approved"])
    assert [r.message for r in plan.rows] == [
        "Only a connector or backshell part has a depth; EX-W is a part of category wire",
        "Depth '0' is not a number of millimetres above 0 and at most 1000",
    ]


def test_import_build_data_reads_the_cable_ends(tmp_path: Path) -> None:
    from harness_design_studio.core.build_data_import import detect_kind, plan_build_data_import

    p = _first_steps_face()
    table = [["Connector", "Lengths to"], ["W002-P1", "rear"], ["W002-P2", ""], ["W001-P1", "Face"], ["W001-P2", "project"]]  # fmt: skip
    assert detect_kind(table[0])[0] == "cable_ends"
    plan = plan_build_data_import(p, table)
    assert [(r.ok, r.action, r.message) for r in plan.rows] == [
        (True, "changed", "lengths to rear"),
        (True, "unchanged", "lengths to face (as it was)"),
        (True, "added", "lengths to face"),
        (True, "unchanged", "lengths to the project (as it was)"),
    ]
    bad = plan_build_data_import(p, [["Harness", "Connector", "Lengths to"], ["W002", "W002-P1", "middle"]])  # fmt: skip
    assert not bad.rows[0].ok and "not face, rear or project" in bad.rows[0].message and not bad.ops


def test_set_length_reference_of_the_scripting_interface(tmp_path: Path) -> None:
    from harness_design_studio import api
    from harness_design_studio.core.io.saver import save_project

    save_project(_first_steps_face(), tmp_path / "p")
    assert api.set_length_reference(tmp_path / "p", "W002", "W002-P1", None) is None
    assert api.set_length_reference(tmp_path / "p", "W002", "W002-P1", "rear") == "rear"
    with pytest.raises(api.EditError):
        api.set_length_reference(tmp_path / "p", "W002", "W002-P1", "middle")


def test_explain_on_the_command_line_names_the_depth(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    from harness_design_studio.cli.main import main
    from harness_design_studio.core.io.saver import save_project

    p = _first_steps_face()
    save_project(p, tmp_path / "p")
    w = next(x for x in p.harnesses["W002"].wires if x.from_connector == "W002-P1")
    assert main(["explain", str(tmp_path / "p"), w.id]) == 0
    out = capsys.readouterr().out
    assert "Depth of part EX-MICROD-9-M (W002-P1, measured to its face)" in out
    assert "Path from rear to rear" in out


# ---- the outputs of a face end (section 4.4) and the golden set `format5` ------------------------


@pytest.fixture(scope="module")
def format5_files() -> tuple[Project, dict[str, bytes]]:
    from harness_design_studio.core.outputs.build import build_outputs
    from tests.format5_support import format5_project

    p = format5_project()
    return p, dict(build_outputs(p, drawings=True, harness_plan=True).files)


def _errors(p: Project, files: dict[str, bytes]) -> list[tuple[str, str]]:
    from harness_design_studio.core.outputs.verify import verify_outputs

    return [(i.code, i.message) for i in verify_outputs(p, files).issues if i.severity == "error"]


def test_the_outputs_of_the_format5_project_match_the_golden_set() -> None:
    """`python -m tools.gen_output_goldens` writes it; renew it only on purpose and review it."""
    import json

    from harness_design_studio.core.outputs.build import build_outputs
    from tests.format5_support import format5_project, golden_text_files
    from tests.helpers import FIXTURES, output_digests

    files = build_outputs(format5_project()).files
    golden = json.loads((FIXTURES / "outputs" / "format5.json").read_text(encoding="utf-8"))
    got = output_digests(files)
    assert sorted(got) == sorted(golden)
    assert [k for k in got if got[k] != golden[k]] == []
    for rel, data in golden_text_files(files).items():
        assert (FIXTURES / "outputs" / "format5" / rel).read_bytes() == data, rel


def test_the_face_ends_reach_every_output_and_verify_finds_no_error(
    format5_files: tuple[Project, dict[str, bytes]],
) -> None:
    import io

    from harness_design_studio.core.outputs.xlsx_env import load_workbook

    p, files = format5_files
    assert _errors(p, files) == []
    seg = files["harnesses/W001/segments.csv"].decode()
    assert ",W001-P1 (face),W001-B1," in seg and ",W001-P2 (face),W001-B1," in seg
    assert ",W001-P3,W001-B2," in seg  # a rear end is not marked
    wb = load_workbook(io.BytesIO(files["harnesses/W001/W001_build.xlsx"]), read_only=True)
    sentence = (
        "At W001-P1 and W001-P2 the segments run to the mating face; the depth of the connector "
        "and its backshell is taken off each wire there."
    )
    for sheet in ("Cut list", "Routing", "Production"):
        cells = [c for row in wb[sheet].iter_rows(values_only=True) for c in row if c]
        assert sentence in cells, sheet
    routing = [list(r) for r in wb["Routing"].iter_rows(values_only=True)]
    assert any(r[1] == "W001-P1 (face)" for r in routing)
    drawn = b"".join(v for k, v in files.items() if k.startswith("harnesses/W001/drawing_") and k.endswith(".svg"))  # fmt: skip
    assert drawn.count(b"lengths to the face") == 2  # the captions of W001-P1 and W001-P2
    # a project without a face end keeps the 4.4.0 words: W002 of the same project has one face
    # end without a depth, so its wires have no length
    wl = files["harnesses/W002/wirelist.csv"].decode().splitlines()[3]
    assert wl.split(",")[10] == ""


def test_a_face_mark_missing_from_the_segments_is_out_routing(
    format5_files: tuple[Project, dict[str, bytes]],
) -> None:
    p, files = format5_files
    rel = "harnesses/W001/segments.csv"
    changed = files[rel].replace(b"W001-P1 (face)", b"W001-P1")
    errors = _errors(p, {**files, rel: changed})
    assert errors and all(code == "out_routing" for code, _m in errors), errors


def test_a_length_without_the_depth_is_out_wire_differs(
    format5_files: tuple[Project, dict[str, bytes]],
) -> None:
    from harness_design_studio.core.model import evolve
    from tests.format5_support import format5_project

    _p, files = format5_files
    q = format5_project()
    h = q.harnesses["W001"]
    # the files say the generated lengths; a design whose wires lost them reads the path less the
    # depths, which the files no longer match
    q.harnesses["W001"] = evolve(h, wires=[evolve(w, length_m=None) for w in h.wires])
    assert any(code == "out_wire_differs" for code, _m in _errors(q, files))


def test_the_sentence_of_the_face_ends_is_checked_in_the_build_workbook(
    format5_files: tuple[Project, dict[str, bytes]],
) -> None:
    import io

    from harness_design_studio.core.outputs.xlsx_env import load_workbook

    p, files = format5_files
    rel = "harnesses/W001/W001_build.xlsx"
    wb = load_workbook(io.BytesIO(files[rel]))
    ws = wb["Cut list"]
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("At W001-P1 and W001-P2"):
                cell.value = None
    out = io.BytesIO()
    wb.save(out)
    errors = _errors(p, {**files, rel: out.getvalue()})
    assert errors and all(code == "out_build" for code, _m in errors), errors
