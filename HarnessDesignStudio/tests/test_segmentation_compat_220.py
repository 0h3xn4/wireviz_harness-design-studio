# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Projects that generate at 2.2 group the same at 2.3.0 (`docs/ait/DESIGN_2.3_BRANCHING.md`
sections 8 and 9, D-243). `tests/reference/segmentation_220.py` is the segmentation of 2.2 word for
word (the compatibility copy). In every mode of 2.2 (`per_connector_pair`, `per_unit_pair`,
`per_zone_pair`), and with a mode that is not known, the current `core/generate/segmentation.py`
must give the same groups, keys, names, skipped interfaces and notes, on every example project,
every test fixture, the sample projects and random projects. Only `per_connector_group` (2.3.0,
opt-in, B2) may group differently.

The copy is also what a 2.2 tool (and 2.0.x and 2.1.x, which have the same code) does with the new
value (section 8): it notes that the mode is not known and makes the pairs of
`per_connector_pair` again, so a joined draft is removed by its Generate and the pairs come back
under new numbers."""

import random
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_design_studio.core import templates
from harness_design_studio.core.generate import segmentation
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import (
    ConfigFile,
    Connector,
    Endpoint,
    InterfaceInstance,
    Pin,
    Project,
    Unit,
)
from harness_design_studio.core.samples import mini3, new_project, sat15, sat15_full, stress_project
from tests.reference import segmentation_220

OLD_MODES = ("per_connector_pair", "per_unit_pair", "per_zone_pair")
EXAMPLES = ("first-steps", "minimal-satellite", "small-satellite", "flatsat")
FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_PROJECTS = sorted(p.parent for p in FIXTURES.rglob("project.json"))


def with_config(p: Project, name: str, **values: object) -> Project:
    old = p.config.get(name)
    p.config[name] = ConfigFile(
        name=name,
        placeholder=old.placeholder if old is not None else True,
        values={**(old.values if old is not None else {}), **values},
    )
    return p


def seen(seg: object) -> tuple[object, ...]:
    """What a segmentation says, in the fields that 2.2 has."""
    return (
        seg.mode,  # type: ignore[attr-defined]
        [
            (g.key, g.mode, g.chain, g.interface_ids, g.label, g.zones)
            for g in seg.groups  # type: ignore[attr-defined]
        ],
        [(s.interface_id, s.reason, s.severity) for s in seg.skipped],  # type: ignore[attr-defined]
        list(seg.notes),  # type: ignore[attr-defined]
    )


def assert_same_as_220(p: Project) -> None:
    for mode in (*OLD_MODES, "no_such_mode"):
        with_config(p, "segmentation", mode=mode)
        new = segmentation.segment(p)
        assert seen(new) == seen(segmentation_220.segment(p)), mode
        # nothing of the new mode leaks into the old ones
        assert new.rings == [] and all(g.sides is None for g in new.groups), mode


def example(tmp_path: Path, name: str) -> Project:
    return templates.create_project(tmp_path / name, name)


# ---- the examples, the fixtures, the samples ---------------------------------------------------


@pytest.mark.parametrize("name", EXAMPLES)
def test_every_example_groups_as_in_220(tmp_path: Path, name: str) -> None:
    p = example(tmp_path, name)
    assert_same_as_220(p)
    if not p.harnesses:
        with_config(p, "segmentation", mode="per_connector_pair")
        generate_project(p)
        assert_same_as_220(p)


@pytest.mark.parametrize("folder", FIXTURE_PROJECTS, ids=lambda f: f.name)
def test_every_fixture_groups_as_in_220(folder: Path) -> None:
    assert_same_as_220(load_project(folder).project)


@pytest.mark.parametrize("make", [mini3, sat15, sat15_full], ids=lambda f: f.__name__)
def test_every_sample_groups_as_in_220(make: object) -> None:
    p = make()  # type: ignore[operator]
    assert_same_as_220(p)
    generate_project(p)
    assert_same_as_220(p)


def test_the_stress_project_groups_as_in_220() -> None:
    assert_same_as_220(stress_project(units=40, interfaces=200, zones=5))


def test_the_fixtures_cover_every_kind_of_project() -> None:
    """The fixture list is found on disk, so a new fixture is compared without a change here."""
    names = {f.name for f in FIXTURE_PROJECTS}
    assert {"mini3", "sat15", "custom_device", "v1_project"} <= names


# ---- random projects --------------------------------------------------------------------------

TYPES = ("rs422", "can", "power_primary", "pyro", "analog", "heater", "spacewire", "no_type")
ZONES = ("panel-A", "panel-B", None)


def random_project(seed: int) -> Project:
    """Devices with one to three connectors each, interfaces between them (some with no connector,
    one connector on both ends, three ends, a type that does not exist, redundant chains), random
    segregation settings, and sometimes a harness drawn by hand that routes an interface."""
    rnd = random.Random(seed)
    p = new_project("random")
    units = [f"U{n}" for n in range(rnd.randint(2, 7))]
    for u in units:
        p.units[u] = Unit(id=u, name=u, subsystem="s", zone=rnd.choice(ZONES), side="nominal")
        for k in range(rnd.randint(1, 3)):
            cid = f"{u}-J{k + 1:02d}"
            p.connectors[cid] = Connector(
                id=cid, name=f"J{k + 1:02d}", role="box", part_id="EX-MICROD-25-F", unit_id=u,
                gender="female", pins=[Pin(id=str(n + 1)) for n in range(25)],
            )  # fmt: skip
    conns = {u: [c for c in p.connectors if c.startswith(f"{u}-")] for u in units}
    for n in range(rnd.randint(1, 14)):
        iid = f"IF-{n + 1:03d}"
        ends = []
        for _ in range(3 if rnd.random() < 0.05 else 2):
            u = rnd.choice(units)
            end: str | None = rnd.choice(conns[u]) if rnd.random() < 0.92 else None
            ends.append(Endpoint(unit_id=u, connector_id=end))
        p.interfaces[iid] = InterfaceInstance(
            id=iid, name=iid, type_id=rnd.choice(TYPES),
            redundancy=rnd.choice(("nominal", "nominal", "redundant", "none")), endpoints=ends,
        )  # fmt: skip
    with_config(
        p,
        "segregation",
        forbid_nominal_with_redundant=rnd.choice((True, False, None)),
        forbid_pyro_with_other=rnd.choice((True, False, None)),
        category_pairs_to_separate=rnd.choice(
            (None, [["power", "data"]], [["data", "analog"], ["power", "pyro"]])
        ),
    )
    return p


@settings(max_examples=300, deadline=None)
@given(seed=st.integers(0, 2**32 - 1))
def test_random_projects_group_as_in_220(seed: int) -> None:
    assert_same_as_220(random_project(seed))


def test_the_random_projects_reach_every_branch_of_the_segmentation() -> None:
    """The random cases are not all trivial: groups of several interfaces, skipped interfaces of
    each kind, mixed classes and redundant chains all occur."""
    shared = skipped = mixed = redundant = 0
    for seed in range(200):
        p = with_config(random_project(seed), "segmentation", mode="per_connector_pair")
        seg = segmentation.segment(p)
        shared += any(len(g.interface_ids) > 1 for g in seg.groups)
        skipped += bool(seg.skipped)
        mixed += bool(seg.notes)
        redundant += any(g.chain == "redundant" for g in seg.groups)
    assert shared > 40 and skipped > 40 and mixed > 10 and redundant > 40


# ---- what an older tool does with the new value (section 8) -----------------------------------


def test_a_220_tool_reads_per_connector_group_as_per_connector_pair() -> None:
    """2.2 (like 2.0.x and 2.1.x) warns *not known; using per_connector_pair* and makes the pairs:
    its Generate removes a joined draft and makes the pairs again under new numbers, and reports
    what a person set on the draft as lost (`_warn_lost_data`). The release notes say to update
    the whole team."""
    p = new_project("older tool")
    for u in ("OBC1", "STR1", "STR2"):
        p.units[u] = Unit(id=u, name=u, subsystem="s", side="nominal")
        p.connectors[f"{u}-J01"] = Connector(
            id=f"{u}-J01", name="J01", role="box", part_id="EX-MICROD-25-F", unit_id=u,
            gender="female", pins=[Pin(id=str(n + 1)) for n in range(25)],
        )  # fmt: skip
    for n, far in enumerate(("STR1", "STR2"), start=1):
        p.interfaces[f"IF-00{n}"] = InterfaceInstance(
            id=f"IF-00{n}", name=f"IF-00{n}", type_id="rs422",
            endpoints=[Endpoint(unit_id="OBC1", connector_id="OBC1-J01"), Endpoint(unit_id=far, connector_id=f"{far}-J01")],
        )  # fmt: skip
    with_config(p, "segmentation", mode="per_connector_group")
    old = segmentation_220.segment(p)
    assert old.mode == "per_connector_pair"
    assert old.notes == [
        "segmentation.mode 'per_connector_group' is not known; using per_connector_pair"
    ]
    assert [g.key for g in old.groups] == ["cp|none|OBC1-J01|STR1-J01", "cp|none|OBC1-J01|STR2-J01"]
    new = segmentation.segment(p)
    assert new.notes == [] and [g.key for g in new.groups] == ["cg|none|OBC1-J01"]
