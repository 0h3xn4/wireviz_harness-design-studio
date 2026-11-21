# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Generate makes the overall shield of an interface type of construction `single` (design of
4.2.0, sections 15 and 16.1; pull request 1; REQ-GEN-04).

The fault: `generate/shields.plan` skipped a type of construction `single` before it read its
`shielding`, so an interface of such a type that shields overall got no shield group, and the
independent verifier then refused the generated harness with `shield_missing`, reported by `drc`
as a `verify-mismatch` error whose fix, *Regenerate harnesses*, changed nothing. It is reproduced
on a copy of `flatsat` with the type `discrete` set to `shielding` `overall`: its interfaces
IF-040 (wires W002-025, W002-026) and IF-041 (W006-011, W006-012). What is checked: one
`overall_shield` per interface over all its wires, with the ends of the grounding concept as every
overall shield of the harness has them, and no twisted pair (a `single` type twists no pair, even
when its signals name one); `verify_project`, `drc` and `verify --outputs` after `export` find no
`shield_missing`; `explain` of the group says why; a second Generate changes nothing; a `single`
type that does not shield gets no group; and no example or fixture holds a `single` type that
shields, so the fix changes none of their files."""

import json
import shutil
from pathlib import Path

import pytest

from harness_design_studio.cli.main import main
from harness_design_studio.core import drc, templates
from harness_design_studio.core.derive import explain_object, render
from harness_design_studio.core.generate import shields
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import Project, SignalDef, evolve
from harness_design_studio.core.samples import mini3, sat15, sat15_full
from harness_design_studio.core.starter import starter_interface_types
from harness_design_studio.core.verify import verify_project

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {"IF-040": ("W002", ["W002-025", "W002-026"]), "IF-041": ("W006", ["W006-011", "W006-012"])}  # fmt: skip


def cli(capsys: pytest.CaptureFixture[str], *argv: str | Path) -> tuple[int, str]:
    code = main([str(a) for a in argv])
    got = capsys.readouterr()
    return code, got.out + got.err


def files(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}  # fmt: skip


@pytest.fixture(scope="module")
def flatsat(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("single") / "flatsat"
    templates.create_project(folder, "flatsat")
    return folder


def with_discrete(flatsat: Path, tmp_path: Path, **changes: object) -> Path:
    """A copy of flatsat whose type `discrete` (construction `single`) has these fields."""
    folder = tmp_path / "flatsat"
    shutil.copytree(flatsat, folder)
    p = load_project(folder).project
    p.interface_types["discrete"] = evolve(p.interface_types["discrete"], **changes)
    save_project(p, folder)
    return folder


def overall_of(p: Project, iid: str) -> list[tuple[str, str, list[str]]]:
    hid, _ = EXPECTED[iid]
    h = p.harnesses[hid]
    ids = {w.id for w in h.wires if w.interface_id == iid}
    return [(s.id, s.kind, s.wire_ids) for s in h.shields if ids & set(s.wire_ids)]


def test_the_starting_point_is_a_single_type_that_does_not_shield(flatsat: Path) -> None:
    p = load_project(flatsat).project
    t = p.interface_types["discrete"]
    assert (t.construction, t.shielding) == ("single", "none")
    for iid, (hid, wires) in EXPECTED.items():
        assert p.interfaces[iid].type_id == "discrete"
        assert sorted(w.id for w in p.harnesses[hid].wires if w.interface_id == iid) == wires
        assert overall_of(p, iid) == []  # a single type that does not shield gets no group


def test_generate_makes_the_overall_shield_and_the_verifier_finds_none_missing(
    flatsat: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = with_discrete(flatsat, tmp_path, shielding="overall")
    code, out = cli(capsys, "generate", folder)
    assert code == 0, out
    p = load_project(folder).project
    for iid, (hid, wires) in EXPECTED.items():
        groups = overall_of(p, iid)
        assert len(groups) == 1 and groups[0][1:] == ("overall_shield", wires), groups
        h = p.harnesses[hid]
        group = next(s for s in h.shields if s.id == groups[0][0])
        assert group.id.startswith(f"{hid}-S") and not group.manual
        # the ends of the grounding concept, as every other overall shield of the project has them
        a, b, _ = shields.concept_ends(dict(p.config["generation"].values))
        assert (group.end_a, group.end_b) == (a, b)
        others = [s for x in p.harnesses.values() for s in x.shields if s.kind == "overall_shield"]
        assert {(s.end_a, s.end_b) for s in others} == {(a, b)}
        text = "\n".join(render(d) for d in explain_object(p, group.id))
        assert "the type discrete shields overall" in text, text
        assert "construction single: no pair is twisted" in text, text

    assert [i for i in verify_project(p).issues if i.code == "shield_missing"] == []
    assert not any(f.rule == "verify-mismatch" and "shield" in f.title for f in drc.run(p))

    assert cli(capsys, "export", folder)[0] == 0
    code, out = cli(capsys, "verify", folder, "--outputs")
    assert code == 0 and "shield_missing" not in out and "0 error(s)" in out, out
    wire_list = (folder / "outputs" / "harnesses" / "W002" / "wirelist.csv").read_text("utf-8")
    group_id = overall_of(p, "IF-040")[0][0]
    rows = [line for line in wire_list.splitlines() if line.endswith(f",{group_id},")]
    assert [r.split(",")[0] for r in rows] == EXPECTED["IF-040"][1], wire_list

    before = files(folder)
    code, out = cli(capsys, "generate", folder)  # a second Generate changes nothing
    assert code == 0 and files(folder) == before, out


def test_a_single_type_twists_no_pair_even_when_its_signals_name_one(
    flatsat: Path, tmp_path: Path
) -> None:
    folder = with_discrete(flatsat, tmp_path, shielding="overall")
    p = load_project(folder).project
    t = p.interface_types["discrete"]
    p.interface_types["discrete"] = evolve(
        t, signals=[SignalDef(name=s.name, direction=s.direction, pair="L") for s in t.signals]
    )
    generate_project(p)
    for iid, (_hid, wires) in EXPECTED.items():
        assert [g[1:] for g in overall_of(p, iid)] == [("overall_shield", wires)]
    assert [i for i in verify_project(p).issues if i.code == "shield_missing"] == []


def test_the_plan_of_a_single_type_that_shields_overall(flatsat: Path) -> None:
    p = load_project(flatsat).project
    h = p.harnesses["W002"]
    iface = p.interfaces["IF-040"]
    wires = [w for w in h.wires if not w.manual]
    assert shields.plan(p, [iface], wires) == []  # shielding none: nothing
    p.interface_types["discrete"] = evolve(p.interface_types["discrete"], shielding="overall")
    planned = shields.plan(p, [iface], wires)
    assert [(x.kind, sorted(w.id for w in x.wires), x.interface_id) for x in planned] == [
        ("overall_shield", EXPECTED["IF-040"][1], "IF-040")
    ]
    assert planned[0].why == (
        "the type discrete shields overall: one shield over all the wires of IF-040 "
        "(construction single: no pair is twisted)"
    )


def test_no_example_or_fixture_has_a_single_type_that_shields() -> None:
    """So the fix changes no file of the examples, the templates, the fixtures or the goldens
    (design of 4.2.0, section 8): the files on disk, the starter types and the sample projects."""
    found: list[tuple[str, str, str, str]] = []
    paths = sorted(ROOT.glob("src/harness_design_studio/resources/**/interface_types.json"))
    paths += sorted(ROOT.glob("tests/fixtures/**/interface_types.json"))
    assert len(paths) > 10
    for path in paths:
        types = json.loads(path.read_text("utf-8"))["interface_types"]
        assert types, path
        found += [
            (str(path), t["id"], t.get("construction", "single"), t.get("shielding", "none"))
            for t in types
        ]
    in_memory = [("starter", t) for t in starter_interface_types()]
    for name, make in (("mini3", mini3), ("sat15", sat15), ("sat15_full", sat15_full)):
        in_memory += [(name, t) for t in make().interface_types.values()]
    found += [(name, t.id, t.construction, t.shielding) for name, t in in_memory]
    singles = [f for f in found if f[2] == "single"]
    assert singles  # discrete, i2c, ground ...
    assert [f for f in singles if f[3] not in ("none", None)] == []
