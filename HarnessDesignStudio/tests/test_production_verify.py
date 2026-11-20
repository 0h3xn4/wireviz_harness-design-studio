# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The independent verifier's own wording of the Production sheet (design of 4.1.0, section 3.6;
pull request 1: no sheet is written or read yet).

`core/outputs/verify_production.py` words every block heading and every row again from the
project. It names no builder among its imports (not `production.py`, `buildsheet.py`,
`harness_plan.py`, `tables.py`, `core/label_format.py`, `core/shield_ends.py` or the length rules of
`core/generate/lengths.py`); its labels come from the verifier's own copy in `verify_labels.py`,
which names no builder either. Its rows are the core's on every example, on the splice, loose-end
and branching fixtures and on random harnesses (Hypothesis: shield groups, segments with loops and
missing lengths, splices, loose ends, label formats and templates, the length settings), and so
are its copies of the shield end, the length, the origin of a length and the reference sentence."""

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness_design_studio.core.generate.lengths import length_origin, reference_text, wire_length
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import (
    Accessory,
    BranchPoint,
    ConfigFile,
    Project,
    Segment,
    ShieldGroup,
)
from harness_design_studio.core.outputs import production as pr
from harness_design_studio.core.outputs import verify_production as vp
from harness_design_studio.core.shield_ends import end_at
from tests.loose_support import generated_loose
from tests.plan_support import GOLDEN_PROJECTS, golden_project
from tests.static_scan import imported_names
from tests.test_production_sheet import small
from tests.test_verify_plan import projects as plan_projects

SRC = Path(__file__).resolve().parents[1] / "src"
PKG = "harness_design_studio.core"
BUILDERS = (
    f"{PKG}.outputs.production",
    f"{PKG}.outputs.buildsheet",
    f"{PKG}.outputs.harness_plan",
    f"{PKG}.outputs.tables",
    f"{PKG}.outputs.drawing",
    f"{PKG}.label_format",
    f"{PKG}.shield_ends",
    f"{PKG}.generate.lengths",
)


def core_rows(p: Project, hid: str) -> list[tuple[str, bool, str, tuple[tuple[object, ...], ...]]]:
    return [
        (b.connector_id, b.splice, b.heading, tuple(r.values() for r in b.rows))
        for b in pr.production_blocks(p, p.harnesses[hid])
    ]


def verifier_rows(p: Project, hid: str) -> list[tuple[str, bool, str, tuple[tuple[object, ...], ...]]]:  # fmt: skip
    return [(b.connector_id, b.splice, b.heading, b.rows) for b in vp.production_rows(p, p.harnesses[hid])]  # fmt: skip


def assert_agree(p: Project) -> None:
    for hid, h in p.harnesses.items():
        assert verifier_rows(p, hid) == core_rows(p, hid), hid
        for w in h.wires:
            assert vp._length(h, w) == wire_length(h, w), w.id
            assert vp._length_origin(h, w) == length_origin(h, w), w.id
        for s in h.shields:
            for c in h.connectors:
                assert vp._end_at(h, s, c.id) == end_at(h, s, c.id), (s.id, c.id)
    assert vp._length_reference(p) == reference_text(p)


# ---- independence ---------------------------------------------------------------------------------


@pytest.mark.parametrize("module", ["verify_production.py", "verify_labels.py"])
def test_the_verifier_s_copy_imports_no_builder(module: str) -> None:
    names = imported_names(SRC / "harness_design_studio/core/outputs" / module, SRC)
    assert names
    found = [n for n in names if any(n == b or n.startswith(b + ".") for b in BUILDERS)]
    assert found == [], module


def test_the_verifier_s_copy_takes_its_labels_from_verify_labels() -> None:
    names = imported_names(SRC / "harness_design_studio/core/outputs/verify_production.py", SRC)
    assert f"{PKG}.outputs.verify_labels._connector_label_text" in names
    assert f"{PKG}.outputs.verify_labels._wire_label_texts" in names


def test_the_verifier_s_words_are_the_core_s() -> None:
    assert vp._HEADER == pr.HEADER
    assert vp._PLAN_HEADER == pr.PLAN_HEADER
    assert (vp._NO_WIRE, vp._SPARE, vp._UNPLUGGED, vp._ACROSS) == (
        pr.NO_WIRE, pr.SPARE, pr.NOT_PLUGGED, pr.NOT_DEFINED,
    )  # fmt: skip
    assert vp._END_TEXT == pr.END_WORDS
    assert vp._DOT == pr.JOIN


# ---- every example and fixture ---------------------------------------------------------------------


@pytest.mark.parametrize("name", GOLDEN_PROJECTS)
def test_the_verifier_words_every_row_of_the_examples_and_fixtures_as_the_core(name: str) -> None:
    assert_agree(golden_project(name))


def test_the_verifier_words_every_row_of_the_loose_end_fixture_and_the_small_harness(
    tmp_path: Path,
) -> None:
    assert_agree(load_project(generated_loose(tmp_path / "loose")).project)
    assert_agree(small())


def test_flatsat_counts_by_the_verifier() -> None:
    p = golden_project("flatsat")
    blocks = vp.production_rows(p, p.harnesses["W001"])
    assert len(blocks) == 18
    rows = {hid: sum(len(b.rows) for b in vp.production_rows(p, h)) for hid, h in p.harnesses.items()}  # fmt: skip
    assert {k: rows[k] for k in ("W001", "W002", "W004")} == {"W001": 54, "W002": 74, "W004": 64}


# ---- random harnesses ------------------------------------------------------------------------------

_KINDS = ["twisted_pair", "shielded_pair", "overall_shield", "quad", "coax"]
_ENDS = ["backshell_360", "pigtail", "floating"]
_LENGTHS = st.sampled_from([None, 0.25, 1.0, 0.1, 2.5])
_TEMPLATES = st.sampled_from([None, "{harness}:{wire}:{end} {from}>{to}", "{name}{{x}}", "{bad}"])
_CON_TEMPLATES = st.sampled_from([None, "{harness}:{device}:{mates} {name}", "{connector}"])


@st.composite
def production_projects(draw: st.DrawFn) -> Project:
    """The random harnesses of `tests/test_verify_plan.py` (box connectors with and without a
    device, cable connectors, loose ends, plugs on no box, splices, random wires), with more: spare
    pins and pins with an interface, wire signals, labels and locks, shield groups (some naming a
    wire that is not there), branch points and segments (loops, missing lengths), label
    accessories, a label format with templates and the length settings."""
    p = draw(plan_projects())
    h = p.harnesses["W001"]
    cons = []
    for c in h.connectors:
        pins = [
            pin.model_copy(
                update={
                    "signal": pin.signal if draw(st.booleans()) else None,
                    "interface_id": draw(st.sampled_from([None, None, None, "IF1"])),
                }
            )  # fmt: skip
            for pin in c.pins
        ]
        pins += [type(c.pins[0])(id=f"2{k}") for k in range(draw(st.integers(0, 3)))]
        cons.append(c.model_copy(update={
            "pins": pins, "label": draw(st.sampled_from([None, "Plug"])),
            "gender": draw(st.sampled_from(["unspecified", "male", "female"])),
        }))  # fmt: skip
    for cid, box in list(p.connectors.items()):
        p.connectors[cid] = box.model_copy(update={"label": draw(st.sampled_from([None, "Port"]))})
    wires = [
        w.model_copy(
            update={
                "signal": draw(st.sampled_from([None, "PWR", "SIG"])),
                "locked": draw(st.booleans()),
                "label": draw(st.sampled_from([None, "MAIN"])),
            }
        )  # fmt: skip
        for w in h.wires
    ]
    wire_ids = [w.id for w in wires] + ["W001-099"]
    shields = [
        ShieldGroup(
            id=f"W001-S{k}",
            kind=draw(st.sampled_from(_KINDS)),
            wire_ids=draw(st.lists(st.sampled_from(wire_ids), min_size=1, max_size=4, unique=True)),
            end_a=draw(st.sampled_from(_ENDS)),
            end_b=draw(st.sampled_from(_ENDS)),
        )  # fmt: skip
        for k in draw(st.lists(st.sampled_from([1, 2, 10]), max_size=3, unique=True))
    ]
    branches = [BranchPoint(id=f"W001-B{k}", name=f"B{k}") for k in range(1, draw(st.integers(0, 2)) + 1)]  # fmt: skip
    nodes = [c.id for c in cons] + [b.id for b in branches]
    segments = [
        Segment(
            id=f"W001-L{k}",
            from_node=draw(st.sampled_from(nodes)),
            to_node=draw(st.sampled_from(nodes)),
            length_m=draw(_LENGTHS),
        )  # fmt: skip
        for k in range(1, draw(st.integers(0, 6)) + 1)
    ]
    accessories = [
        Accessory(
            id=f"W001-A{k}",
            kind=draw(st.sampled_from(["label", "label", "sleeving"])),
            target=draw(st.sampled_from([None, *[c.id for c in cons]])),
            position=draw(st.sampled_from([None, "50 mm from the end"])),
        )  # fmt: skip
        for k in draw(st.lists(st.sampled_from([1, 2, 10]), max_size=3, unique=True))
    ]
    p.harnesses["W001"] = h.model_copy(update={
        "connectors": cons, "wires": wires, "shields": shields, "branch_points": branches,
        "segments": segments, "accessories": accessories,
    })  # fmt: skip
    model: dict[str, object] = {
        "label_format": draw(st.sampled_from(["standard", "compact", "descriptive", "custom", "fancy"])),
        "service_loops_per_wire": draw(st.sampled_from([0, 1, 2, 4])),
        "length_model": draw(st.sampled_from(["path_plus_loops", "path_loops_allowance_twist", "odd"])),
        "twist_takeup_fraction": draw(st.sampled_from([0.0, 0.02, 0.5])),
        "cut_allowance_m": draw(st.sampled_from([0.0, 0.05, 1.25])),
    }  # fmt: skip
    if (wire := draw(_TEMPLATES)) is not None:
        model["label_wire_template"] = wire
    if (con := draw(_CON_TEMPLATES)) is not None:
        model["label_connector_template"] = con
    p.config["model"] = ConfigFile(name="model", placeholder=False, values=model)
    loop = draw(st.sampled_from([None, 0.0, 0.1, 0.15, 1e-07, 12345.678901]))
    p.config["generation"] = ConfigFile(name="generation", placeholder=False, values={"service_loop_m": loop})  # fmt: skip
    return p


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(production_projects())
def test_the_verifier_words_every_row_of_a_random_harness_as_the_core(p: Project) -> None:
    assert_agree(p)
