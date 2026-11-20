# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""What a length is measured from, and where a wire's length comes from (design of 4.1.0, part D,
sections 6.1 and 6.3; pull request 1).

`lengths.reference_text(project)` words the reference from the settings in force, with the
project's own numbers and none invented, as the three sentences of `lengths.reference_lines` (a
sheet prints each on a row of its own, pull request 3); `lengths.length_origin(h, w)` says `on the wire`,
`locked`, `segments only, no service loops` or nothing. `derive.wire_length_derivation` starts from
`length_origin`, so the two agree on every wire of every example, and its texts are as before."""

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
    "Lengths run from the rear of a connector (where the wires leave its body or backshell) along "
    "the routing segments, through the centre of each branch point, to the rear of the other "
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
    origin = length_origin(h, w)
    d = derive.wire_length_derivation(project, h, w)
    basis = _basis(d)
    if origin == ORIGIN_NONE:
        assert d.value is None and d.missing, w.id
    elif origin == ORIGIN_SEGMENTS:
        assert basis.startswith("the routing segments of its path"), (w.id, basis)
    elif origin == ORIGIN_LOCKED:
        assert w.locked and basis.startswith(("generated", "overridden", "entered by hand")), w.id
    else:
        assert not w.locked and basis.startswith(("generated", "a length stored")), (w.id, basis)


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
def test_the_reference_is_three_sentences_a_sheet_prints_a_row_each(name: str) -> None:
    p = golden_project(name)
    lines = reference_lines(p)
    assert len(lines) == 3 and " ".join(lines) == reference_text(p)
    assert lines[0].startswith("Lengths run from") and lines[0].endswith("the other connector.")
    assert lines[1].startswith("A wire Generate made adds ") and lines[1].endswith(".")
    assert lines[2] == '"Locked" is a length a person typed; "segments only" has no service loops.'
