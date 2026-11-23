# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-WIRE-09: with no face end the lengths are those of 4.4.0, and the verifier's copies of the
face ends agree with the core's (design of 5.0.0 `docs/ait/DESIGN_5.0_FORMAT_5.md` sections 4.3
and 11 (1), pull request 2).

`tests/reference/lengths_440.py` is the module `core/generate/lengths.py` of the tag `v4.4.0`, word
for word. On random harnesses of `tests/test_production_verify.py` (segments with loops and missing
lengths, splices, loose ends, locked wires, the length settings) with no face end (no `length_to`
and the setting `rear`, or `length_to` `rear`), `end_depths` is empty and every wire length, origin
and the length note equal the copy's. With face ends (random `length_to`, the setting, depths of
connector and backshell parts, backshells with and without a part), the verifier's own copies
(`verify_production._end_depths`, `_length`, `_length_origin`, `_length_lines`, the copies of
`verify.py` and `verify_plan.py`) give what the core gives, and every row of the Production sheet
agrees (`tests/test_production_verify.assert_agree`)."""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness_design_studio.core.generate import lengths
from harness_design_studio.core.model import (
    Accessory,
    ConfigFile,
    Harness,
    Part,
    Project,
    Wire,
    evolve,
)
from harness_design_studio.core.outputs import verify as vf
from harness_design_studio.core.outputs import verify_plan as vpl
from harness_design_studio.core.outputs import verify_production as vp
from tests.reference import lengths_440 as ref
from tests.test_production_verify import assert_agree, production_projects

SLOW = settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@st.composite
def rear_projects(draw: st.DrawFn) -> Project:
    """A random project with no face end: some cable connectors say `rear`, the setting is `rear`
    or not set, and some parts have a depth (which a rear end never reads)."""
    p = draw(production_projects())
    h = p.harnesses["W001"]
    cons = [
        evolve(c, length_to=draw(st.sampled_from([None, "rear"]))) if c.role == "cable" else c
        for c in h.connectors
    ]
    p.harnesses["W001"] = evolve(h, connectors=cons)
    if draw(st.booleans()):
        model = dict(p.config["model"].values)
        model["length_reference"] = "rear"
        p.config["model"] = ConfigFile(name="model", placeholder=False, values=model)
    for pid in draw(st.lists(st.sampled_from(sorted(p.parts)), max_size=3, unique=True)):
        if p.parts[pid].category in ("connector", "backshell"):
            p.parts[pid] = evolve(p.parts[pid], depth_mm=25.0)
    return p


@SLOW
@given(rear_projects())
def test_with_no_face_end_every_length_is_that_of_4_4_0(p: Project) -> None:
    for h in p.harnesses.values():
        ends = lengths.end_depths(p, h)
        assert not ends and ends.faces == ()
        for w in h.wires:
            assert lengths.wire_length(h, w, ends) == ref.wire_length(h, w), w.id
            assert lengths.wire_length(h, w) == ref.wire_length(h, w), w.id
            assert lengths.length_origin(h, w, ends) == ref.length_origin(h, w), w.id
        assert lengths.reference_lines(p, h) == ref.reference_lines(p)
        assert lengths.face_line(p, h) is None
    assert lengths.reference_lines(p) == ref.reference_lines(p)


@st.composite
def face_projects(draw: st.DrawFn) -> Project:
    """A random project with face ends: `length_to` on cable connectors, the setting `face` or not,
    depths of connector parts, backshells with a part with or without a depth, or without a part."""
    p = draw(production_projects())
    shell = Part(id="EX-BACKSHELL-T", category="backshell", depth_mm=draw(st.sampled_from([None, 30.0, 1.5])))  # fmt: skip
    p.parts[shell.id] = shell
    for pid, part in list(p.parts.items()):
        if part.category == "connector":
            depth = draw(st.sampled_from([None, 25.0, 12.5, 1000.0]))
            p.parts[pid] = evolve(part, depth_mm=depth)
    h = p.harnesses["W001"]
    cons = [
        evolve(c, length_to=draw(st.sampled_from([None, "face", "rear"])))
        if c.role == "cable"
        else c
        for c in h.connectors
    ]
    targets = [c.id for c in cons] or ["W001-X"]
    shells = [
        Accessory(
            id=f"W001-BS{k}",
            kind="backshell",
            target=draw(st.sampled_from(targets)),
            part_id=draw(st.sampled_from([None, shell.id, shell.id, "EX-NOT-THERE"])),
        )  # fmt: skip
        for k in range(draw(st.integers(0, 2)))
    ]
    p.harnesses["W001"] = evolve(h, connectors=cons, accessories=[*h.accessories, *shells])
    model = dict(p.config["model"].values)
    model["length_reference"] = draw(st.sampled_from(["rear", "face", "odd"]))
    p.config["model"] = ConfigFile(name="model", placeholder=False, values=model)
    return p


@SLOW
@given(face_projects())
def test_the_verifier_s_copies_of_the_face_ends_are_the_core_s(p: Project) -> None:
    for h in p.harnesses.values():
        ends = lengths.end_depths(p, h)
        depths = vp._end_depths(p, h)
        assert depths == (ends.depths, ends.missing)
        assert vp._face_ends(p, h) == lengths.face_ends(p, h) == ends.faces
        for w in h.wires:
            want = lengths.wire_length(h, w, ends)
            assert vp._length(h, w, depths) == want, w.id
            assert vp._length_origin(h, w, depths) == lengths.length_origin(h, w, ends), w.id
            assert vf._length_of(h, w, depths) == want or _same_path_rule(h, w), w.id
            plan = vpl._length(h, w)
            if w.length_m is None:
                plan = vp._from_rear(plan, w, depths)
            assert plan == want, w.id
        assert vp._length_lines(p, h) == lengths.reference_lines(p, h)
        assert vp._length_reference(p, h) == lengths.reference_text(p, h)
    assert_agree(p)


def _same_path_rule(h: Harness, w: Wire) -> bool:
    """`verify._length_of` reads the first route it finds, does not refuse a loop and gives a wire
    from a connector to itself 0 in a harness without segments (all as in 4.4.0): only there may
    it differ from the core."""
    return bool(lengths.loop_segments(h)) or (not h.segments and w.from_connector == w.to_connector)
