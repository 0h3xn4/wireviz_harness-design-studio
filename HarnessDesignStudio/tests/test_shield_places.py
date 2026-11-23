# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-call"
"""Where a shield end lands (format 5, part D of `docs/ait/DESIGN_5.0_FORMAT_5.md`, section 7;
REQ-OUT-17; owner questions F9, F10 and F11).

`ShieldGroup.at_a` and `at_b` name the connector at an end, the pin a pigtail lands on and the
backshell (an accessory of kind backshell on that connector). This file holds the rules of the
files, `wires.plan_set_shield_place` on a group Generate made and on one a person made, the places
that `plan_set_group_ends`, `plan_regroup` and the deletion of an accessory clear, Generate keeping
and dropping a place, the codes of `check` (section 7.3), the Production sheet, the *Connectors*
sheet, the drawing and `export.json` with their verifier, `import-build-data` *shield ends*, the
scripting function and a format 4 project whose outputs do not move."""

import io
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness_design_studio.core.commands import Op, apply_ops
from harness_design_studio.core.edit import EditError, clone_with
from harness_design_studio.core.integrity import check_integrity, shield_place_issues
from harness_design_studio.core.model import (
    Accessory,
    ConfigFile,
    Project,
    ShieldEndPlace,
    ShieldGroup,
    evolve,
)
from harness_design_studio.core.wires import (
    NEW_BACKSHELL,
    plan_change_group,
    plan_regroup,
    plan_set_group_ends,
    plan_set_shield_place,
)
from tests.format5_support import format5_project

PIN9 = {"connector": "W001-P1", "pin": "9"}


@pytest.fixture
def p() -> Project:
    return clone_with(format5_project(), [])


def group(p: Project, gid: str) -> ShieldGroup:
    return next(s for h in p.harnesses.values() for s in h.shields if s.id == gid)


def codes(p: Project) -> list[tuple[str, str, str | None]]:
    return [(i.severity, i.code, i.object_id) for i in shield_place_issues(p)]


# ---- the rules of the files (section 3.2, rule 4) ------------------------------------------------


def test_the_keys_are_sparse_and_absent_by_default() -> None:
    s = ShieldGroup(id="W001-S1", kind="shielded_pair", wire_ids=["W001-001"], end_a="pigtail")
    assert s.at_a is None and s.at_b is None
    assert "at_a" not in s.model_dump() and "at_b" not in s.model_dump()
    placed = evolve(s, at_a=ShieldEndPlace(connector="W001-P1", pin="9"))
    assert placed.model_dump(mode="json")["at_a"] == PIN9  # no backshell key while it is unset


@pytest.mark.parametrize(
    ("kind", "end_a", "place", "words"),
    [
        (
            "twisted_pair",
            "pigtail",
            {"connector": "W001-P1", "pin": "9"},
            "a twisted pair has no shield",
        ),  # fmt: skip
        (
            "shielded_pair",
            "floating",
            {"connector": "W001-P1", "backshell": "W001-A1"},
            "is floating",
        ),  # fmt: skip
        (
            "shielded_pair",
            "backshell_360",
            {"connector": "W001-P1", "pin": "9"},
            "only a pigtail lands on a pin",
        ),  # fmt: skip
        ("shielded_pair", "pigtail", {"connector": "W001-P1"}, "names a pin, a backshell or both"),
    ],
)
def test_the_rules_of_the_file(kind: str, end_a: str, place: dict[str, str], words: str) -> None:
    with pytest.raises(ValidationError, match=words):
        ShieldGroup.model_validate(
            {"id": "W001-S1", "kind": kind, "wire_ids": ["W001-001"], "end_a": end_a, "at_a": place}
        )


def test_the_three_places_of_section_7_1_are_valid() -> None:
    base = {"id": "W001-S2", "kind": "shielded_pair", "wire_ids": ["W001-003", "W001-004"]}
    for end, place in (
        ("pigtail", {"connector": "W001-P1", "pin": "9"}),
        ("pigtail", {"connector": "W001-P1", "backshell": "W001-A1"}),
        ("backshell_360", {"connector": "W001-P1", "backshell": "W001-A1"}),
    ):
        s = ShieldGroup.model_validate({**base, "end_b": end, "at_b": place})
        assert s.model_dump(mode="json")["at_b"] == place


def test_a_harness_with_a_place_that_breaks_a_rule_is_set_aside_on_load(tmp_path: Path) -> None:
    from harness_design_studio.core.io.loader import load_project
    from harness_design_studio.core.io.saver import save_project

    save_project(format5_project(), tmp_path / "p")
    loaded = load_project(tmp_path / "p")
    assert group(loaded.project, "W001-S1").at_a == ShieldEndPlace(connector="W001-P1", pin="9")
    path = tmp_path / "p" / "physical" / "harnesses" / "W002.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["shields"][0]["at_a"] == {"connector": "W002-P1", "pin": "3"}  # as in section 3.1
    doc["shields"][0]["end_a"] = "floating"
    path.write_text(json.dumps(doc), encoding="utf-8")
    loaded = load_project(tmp_path / "p")
    assert "W002" not in loaded.project.harnesses
    assert any("is floating, so it has no place" in q.reason for q in loaded.project.quarantine)


# ---- who sets it (section 7.2) -------------------------------------------------------------------


def test_a_place_on_a_group_generate_made_and_on_one_a_person_made(p: Project) -> None:
    s3 = group(p, "W001-S3")
    assert not s3.manual and s3.end_a == "pigtail"
    apply_ops(p, plan_set_shield_place(p, "W001-S3", "a", pin="10"))
    assert group(p, "W001-S3").at_a == ShieldEndPlace(connector="W001-P2", pin="10")
    assert plan_set_shield_place(p, "W001-S3", "A", pin="10") == []  # nothing new
    apply_ops(p, plan_set_shield_place(p, "W001-S3", "A"))  # neither: the place is cleared
    assert group(p, "W001-S3").at_a is None


def test_the_plan_refuses_what_has_no_place(p: Project) -> None:
    with pytest.raises(EditError, match="A or B"):
        plan_set_shield_place(p, "W001-S3", "C", pin="10")
    with pytest.raises(EditError, match="does not exist"):
        plan_set_shield_place(p, "W001-S99", "A", pin="10")
    with pytest.raises(EditError, match="only a pigtail lands on a pin"):
        plan_set_shield_place(p, "W001-S3", "B", pin="10")  # end B is a 360 degree backshell
    with pytest.raises(EditError, match="W001-P2 has no pin '99'"):
        plan_set_shield_place(p, "W001-S3", "A", pin="99")
    with pytest.raises(EditError, match="'W001-A1' is not a backshell on W001-P2"):
        plan_set_shield_place(p, "W001-S3", "A", backshell="W001-A1")  # it sits on W001-P1
    apply_ops(p, plan_set_group_ends_any(p, "W001-S3", end_a="floating"))
    with pytest.raises(EditError, match="is floating, so it lands nowhere"):
        plan_set_shield_place(p, "W001-S3", "A", pin="10")
    h = p.harnesses["W001"]
    p.harnesses["W001"] = evolve(h, status="released")
    with pytest.raises(EditError, match="released"):
        plan_set_shield_place(p, "W001-S1", "A", pin="10")


def plan_set_group_ends_any(p: Project, gid: str, *, end_a: str) -> list[Op]:
    """Change an end of a group Generate made the way the grounding concept would (the plans of a
    person refuse such a group): a scratch evolve of the harness."""
    from harness_design_studio.core.commands import Put

    h = next(x for x in p.harnesses.values() if any(s.id == gid for s in x.shields))
    shields = [evolve(s, end_a=end_a, at_a=None) if s.id == gid else s for s in h.shields]
    return [Put("harnesses", evolve(h, shields=shields))]


def test_a_twisted_pair_takes_no_place() -> None:
    from tests.test_group_edit import group as make_group
    from tests.test_group_edit import mine

    p, hid, w = mine()
    gid = make_group(p, hid, w[:2], "twisted_pair")
    with pytest.raises(EditError, match="twisted pair: it has no shield"):
        plan_set_shield_place(p, gid, "A", pin="1")


def test_a_person_s_group_its_ends_and_the_places_they_clear() -> None:
    from tests.test_group_edit import group as make_group
    from tests.test_group_edit import mine

    p, hid, w = mine()
    gid = make_group(p, hid, w[:2], "shielded_pair")
    h = p.harnesses[hid]
    apply_ops(p, plan_regroup(p, gid, end_a="pigtail", end_b="backshell_360"))
    a_cid = next(x for x in h.wires if x.id == min(w[:2])).from_connector
    b_cid = next(x for x in h.wires if x.id == min(w[:2])).to_connector
    apply_ops(p, plan_set_shield_place(p, gid, "A", pin="5", backshell=NEW_BACKSHELL))
    apply_ops(p, plan_set_shield_place(p, gid, "B", backshell=NEW_BACKSHELL))
    g = group(p, gid)
    h = p.harnesses[hid]
    shells = {a.id: a.target for a in h.accessories if a.kind == "backshell"}
    assert g.at_a == ShieldEndPlace(connector=a_cid, pin="5", backshell="ACC-001")
    assert g.at_b == ShieldEndPlace(connector=b_cid, backshell="ACC-002")
    assert shells == {"ACC-001": a_cid, "ACC-002": b_cid}
    # an end that becomes a 360 degree backshell keeps the backshell and loses the pin
    apply_ops(p, plan_set_group_ends(p, [gid], end_a="backshell_360"))
    assert group(p, gid).at_a == ShieldEndPlace(connector=a_cid, backshell="ACC-001")
    # a floating end has no place
    apply_ops(p, plan_regroup(p, gid, end_b="floating"))
    assert group(p, gid).at_b is None
    # a twisted pair has none at all
    apply_ops(p, plan_regroup(p, gid, kind="twisted_pair"))
    assert group(p, gid).at_a is None and group(p, gid).at_b is None


def test_the_window_s_plan_changes_a_group_and_its_places_in_one_step() -> None:
    from tests.test_group_edit import group as make_group
    from tests.test_group_edit import mine

    p, hid, w = mine()
    gid = make_group(p, hid, w[:2], "twisted_pair")
    ops = plan_change_group(
        p, gid, kind="shielded_pair", end_a="pigtail", end_b="backshell_360",
        places={"a": ("6", None), "b": (None, NEW_BACKSHELL)},
    )  # fmt: skip
    assert len(ops) == 1
    apply_ops(p, ops)
    g = group(p, gid)
    assert g.kind == "shielded_pair" and g.at_a is not None and g.at_a.pin == "6"
    assert g.at_b is not None and g.at_b.backshell == "ACC-001"
    assert plan_change_group(p, gid, places={"a": ("6", None), "b": (None, "ACC-001")}) == []


def test_deleting_a_backshell_clears_the_places_that_name_it(p: Project) -> None:
    from harness_design_studio.core.build_data import places_naming, plan_delete_accessory

    assert places_naming(p.harnesses["W001"], "W001-A1") == ["W001-S2 end B"]
    apply_ops(p, plan_set_shield_place(p, "W001-S1", "A", pin="9", backshell="W001-A1"))
    assert places_naming(p.harnesses["W001"], "W001-A1") == ["W001-S1 end A", "W001-S2 end B"]
    apply_ops(p, plan_delete_accessory(p, "W001", "W001-A1"))
    assert group(p, "W001-S2").at_b is None  # it named only the backshell
    assert group(p, "W001-S1").at_a == ShieldEndPlace(connector="W001-P1", pin="9")
    # an accessory that no place names leaves the groups as they were
    apply_ops(p, plan_set_shield_place(p, "W002-S2", "A"))
    before = p.harnesses["W002"].shields
    apply_ops(p, plan_delete_accessory(p, "W002", "W002-A1"))
    assert p.harnesses["W002"].shields == before


# ---- Generate keeps a place for an unchanged group and never fills one (F10) -------------------------


def test_generate_keeps_the_places_of_an_unchanged_group(p: Project) -> None:
    from harness_design_studio.core.generate.engine import plan_generation

    before = {s.id: (s.at_a, s.at_b) for h in p.harnesses.values() for s in h.shields}
    plan = plan_generation(p)
    apply_ops(p, plan.ops)
    after = {s.id: (s.at_a, s.at_b) for h in p.harnesses.values() for s in h.shields}
    assert after == before
    assert group(p, "W001-S1").at_a == ShieldEndPlace(connector="W001-P1", pin="9")


def test_generate_never_fills_a_place_even_from_a_shield_pin(p: Project) -> None:
    from harness_design_studio.core.generate.engine import generate_project

    c = p.connectors["DEV2-J01"]
    p.connectors["DEV2-J01"] = evolve(
        c, pins=[evolve(x, role="shield") if x.id == "9" else x for x in c.pins]
    )  # the only shield pin of the device connector at end A of W001-S2
    generate_project(p)
    assert group(p, "W001-S2").at_a is None


def test_generate_drops_a_place_whose_end_changed_with_a_note(p: Project) -> None:
    from harness_design_studio.core.generate.engine import plan_generation

    old = p.config["generation"]
    p.config["generation"] = ConfigFile(
        name="generation", placeholder=old.placeholder,
        values={**old.values, "shield_end_a": "floating"},
    )  # fmt: skip
    plan = plan_generation(p)
    apply_ops(p, plan.ops)
    assert group(p, "W001-S1").at_a is None and group(p, "W002-S2").at_a is None
    assert group(p, "W001-S2").at_b == ShieldEndPlace(connector="W001-P1", backshell="W001-A1")
    notes = [n for lines in plan.record.provenance.values() for n in lines if "was not kept" in n]
    assert "shielding: the pigtail of W001-S1 at W001-P1 pin 9 was not kept: end A is now floating" in notes  # fmt: skip
    assert "shielding: the pigtail of W002-S2 at W002-P2 (W002-A1) was not kept: end A is now floating" in notes  # fmt: skip


def test_generate_drops_a_place_whose_group_lost_its_wires(p: Project) -> None:
    from harness_design_studio.core.generate import engine

    s1 = group(p, "W001-S1")
    old = p.harnesses["W001"]
    # the group of the same ID as Generate made it before, but with other wires
    stale = evolve(s1, wire_ids=["W001-001", "W001-016"])
    made = [evolve(s, at_a=None) for s in old.shields]
    notes: list[str] = []

    class Ctx:
        def note(self, key: str, line: str) -> None:
            notes.append(line)

    kept = engine._keep_places(Ctx(), "W001", made, evolve(old, shields=[stale]))  # type: ignore[arg-type]
    assert kept == made
    assert (
        notes
        == [
            "shielding: the pigtail of W001-S1 at W001-P1 pin 9 was not kept: the wires of the group changed"  # fmt: skip
        ]
    )


# ---- the codes of check (section 7.3) ------------------------------------------------------------


def test_the_fixture_has_one_warning_and_infos_for_the_pigtails_without_a_place(p: Project) -> None:
    found = codes(p)
    assert ("warning", "shield_pin_wired", "W002-S1") in found
    assert [c for c in found if c[0] == "warning"] == [("warning", "shield_pin_wired", "W002-S1")]
    infos = sorted(c[2] or "" for c in found if c[1] == "shield_place_not_stated")
    assert infos == ["W001-S2", "W001-S3", "W001-S4", "W001-S6", "W001-S7", "W001-S8"]
    assert {i.message for i in shield_place_issues(p) if i.object_id == "W001-S3"} == {
        "W001-S3: where the pigtail at W001-P2 lands is not stated."
    }


def _with_place(p: Project, gid: str, key: str, place: ShieldEndPlace) -> None:
    h = next(x for x in p.harnesses.values() if any(s.id == gid for s in x.shields))
    p.harnesses[h.id] = evolve(
        h, shields=[evolve(s, **{key: place}) if s.id == gid else s for s in h.shields]
    )


def test_shield_end_moved(p: Project) -> None:
    _with_place(p, "W001-S3", "at_a", ShieldEndPlace(connector="W001-P1", pin="9"))
    msg = [i.message for i in shield_place_issues(p) if i.code == "shield_end_moved"]
    assert msg == [
        "W001-S3: end A is now at W001-P2 (its lowest wire changed), but its place names "
        "W001-P1. State the place again."
    ]


def test_shield_pin_missing_and_shield_backshell_missing(p: Project) -> None:
    _with_place(p, "W001-S3", "at_a", ShieldEndPlace(connector="W001-P2", pin="99"))
    _with_place(p, "W001-S4", "at_b", ShieldEndPlace(connector="W001-P2", backshell="W001-A1"))
    found = {(i.code, i.message) for i in shield_place_issues(p) if i.severity == "warning"}
    assert ("shield_pin_missing", "W001-S3: the pigtail of end A lands on pin 99, which W001-P2 does not have.") in found  # fmt: skip
    assert ("shield_backshell_missing", "W001-S4: end B names the backshell W001-A1, which is not an accessory of kind backshell on W001-P2.") in found  # fmt: skip


def test_shield_pin_role_judges_a_stored_role_only(p: Project) -> None:
    c = p.connectors["DEV1-J01"]
    p.connectors["DEV1-J01"] = evolve(
        c, pins=[evolve(x, role="power") if x.id == "9" else x for x in c.pins]
    )
    found = [i.message for i in shield_place_issues(p) if i.code == "shield_pin_role"]
    assert found == [
        f"{g}: the pigtail of end A lands on pin 9 of W001-P1, which mates with pin 9 of "
        "DEV1-J01, a pin of role power."
        for g in ("W001-S1", "W001-S5")
    ]
    p.connectors["DEV1-J01"] = evolve(
        c, pins=[evolve(x, role="shield") if x.id == "9" else x for x in c.pins]
    )
    assert not [i for i in shield_place_issues(p) if i.code == "shield_pin_role"]


def test_the_warnings_reach_the_drc_as_model_inconsistent_and_the_info_does_not(p: Project) -> None:
    from harness_design_studio.core.drc import run as run_drc

    found = [f for f in run_drc(p) if f.rule == "model-inconsistent"]
    assert any(".shield_pin_wired." in f.id for f in found)
    assert not any("shield_place_not_stated" in f.id for f in found)
    assert any(i.code == "shield_place_not_stated" for i in check_integrity(p))


def test_a_project_of_format_4_with_pigtail_ends_keeps_its_outputs() -> None:
    """F11: an end pigtail without a place is an info, so no written file changes; an end
    backshell 360 without one is not reported (the 28 such ends of flatsat)."""
    from harness_design_studio.core.outputs.build import build_outputs
    from tests.test_outputs_routing import branching_project

    p = branching_project()
    old = p.config["generation"]
    p.config["generation"] = ConfigFile(
        name="generation", placeholder=old.placeholder,
        values={**old.values, "shield_end_a": "pigtail", "shield_end_b": "backshell_360"},
    )  # fmt: skip
    from harness_design_studio.core.generate.engine import generate_project

    generate_project(p)
    assert all(s.at_a is None and s.at_b is None for h in p.harnesses.values() for s in h.shields)
    assert {i.severity for i in shield_place_issues(p)} == {"info"}
    files = build_outputs(p).files
    assert b"shield_place" not in files["system/drc_findings.csv"]
    assert b"pigtail lands here" not in files["harnesses/W001/W001_build.xlsx"]
    doc = json.loads(files["system/export.json"])
    assert not any("at_a" in s or "at_b" in s for h in doc["harnesses"] for s in h["shields"])


def test_flatsat_has_no_code_of_part_d() -> None:
    """Its 28 ends backshell 360 name no backshell and are not reported (F11); it has no pigtail."""
    from tests.plan_support import golden_project

    p = golden_project("flatsat")
    ends = [e for h in p.harnesses.values() for s in h.shields for e in (s.end_a, s.end_b)]
    assert "backshell_360" in ends and "pigtail" not in ends
    assert shield_place_issues(p) == []


# ---- the outputs (section 7.4) -------------------------------------------------------------------


@pytest.fixture(scope="module")
def files() -> tuple[Project, dict[str, bytes]]:
    from harness_design_studio.core.outputs.build import build_outputs

    q = format5_project()
    return q, dict(build_outputs(q, drawings=True, harness_plan=True).files)


def _sheet(data: bytes, name: str) -> list[list[object]]:
    from harness_design_studio.core.outputs.xlsx_env import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True)
    return [list(r) for r in wb[name].iter_rows(values_only=True)]


def _errors(p: Project, files: dict[str, bytes]) -> list[tuple[str, str]]:
    from harness_design_studio.core.outputs.verify import verify_outputs

    return [(i.code, i.message) for i in verify_outputs(p, files).issues if i.severity == "error"]


def test_the_production_sheet_names_the_places(files: tuple[Project, dict[str, bytes]]) -> None:
    p, f = files
    assert _errors(p, f) == []
    rows = _sheet(f["harnesses/W001/W001_build.xlsx"], "Production")
    cells = {str(c) for r in rows for c in r if c}
    assert "W001-S1 shielded pair: here pigtail to pin 9, far backshell 360" in cells
    assert "W001-S2 shielded pair: here backshell 360 (W001-A1), far pigtail" in cells
    assert "W001-S3 shielded pair: here pigtail, far backshell 360" in cells  # no place: as before
    nine = [r for r in rows if r and r[0] == "9"]
    assert [r[:3] for r in nine] == [["9", None, "pigtail"]]
    assert nine[0][10] == (
        "W001-S1 shielded pair: pigtail lands here; W001-S5 shielded pair: pigtail lands here"
    )
    w2 = _sheet(f["harnesses/W002/W002_build.xlsx"], "Production")
    assert "W002-S2 shielded pair: here pigtail to backshell W002-A1, far backshell 360" in {
        str(c) for r in w2 for c in r if c
    }
    three = [r[2] for r in w2 if r and r[0] == "3"]
    assert three[:2] == ["W002-002", "pigtail"]  # a wired pin: its wire, then the pigtail


def test_the_core_and_the_verifier_word_the_rows_alike(files: tuple[Project, dict[str, bytes]]) -> None:  # fmt: skip
    from harness_design_studio.core.outputs.production import production_blocks
    from harness_design_studio.core.outputs.verify_production import production_rows

    p, _f = files
    for h in p.harnesses.values():
        core = [(b.connector_id, b.heading, tuple(r.values() for r in b.rows)) for b in production_blocks(p, h)]  # fmt: skip
        mine = [(b.connector_id, b.heading, b.rows) for b in production_rows(p, h)]
        assert core == mine, h.id


def test_the_connectors_sheet_says_which_pigtail_lands_on_a_pin(files: tuple[Project, dict[str, bytes]]) -> None:  # fmt: skip
    _p, f = files
    rows = _sheet(f["harnesses/W001/W001_build.xlsx"], "Connectors")
    block = [r for r in rows if r and r[0] == "9"]
    assert block[0][3] == "(no wire)" and block[0][6] == "pigtail of W001-S1; pigtail of W001-S5"
    assert all(r[3] == "(spare)" and not r[6] for r in block[1:])  # the other connectors' pin 9


def test_the_plan_s_production_sheet_names_them_too(files: tuple[Project, dict[str, bytes]]) -> None:  # fmt: skip
    _p, f = files
    plan = f["harnesses/W001/W001_plan.ods"]
    assert b"pigtail lands here" in plan and b"here pigtail to pin 9" in plan


def test_the_drawing_and_export_json(files: tuple[Project, dict[str, bytes]]) -> None:
    _p, f = files
    drawn = b"".join(v for k, v in f.items() if k.startswith("harnesses/W002/drawing_"))
    assert b">pigtail to pin 3<" in drawn and b">pigtail to W002-A1<" in drawn
    assert b"end A pigtail to pin 3 at W002-P1" in drawn
    doc = json.loads(f["system/export.json"])
    w1 = next(h for h in doc["harnesses"] if h["id"] == "W001")
    places = {s["id"]: (s.get("at_a"), s.get("at_b")) for s in w1["shields"]}
    assert places["W001-S1"] == (PIN9, None)
    assert places["W001-S2"] == (None, {"connector": "W001-P1", "backshell": "W001-A1"})
    assert places["W001-S3"] == (None, None)


def _edit_cell(data: bytes, sheet: str, old: str, new: str) -> bytes:
    from harness_design_studio.core.outputs.xlsx_env import load_workbook

    wb = load_workbook(io.BytesIO(data))
    for row in wb[sheet].iter_rows():
        for cell in row:
            if cell.value == old:
                cell.value = new
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


@pytest.mark.parametrize(
    ("sheet", "old", "new"),
    [
        ("Production", "W001-S1 shielded pair: here pigtail to pin 9, far backshell 360",
         "W001-S1 shielded pair: here pigtail, far backshell 360"),
        ("Production", "pigtail", "(no wire)"),
        ("Connectors", "pigtail of W001-S1; pigtail of W001-S5", ""),
    ],
)  # fmt: skip
def test_a_wrong_place_in_the_build_workbook_is_out_build(
    files: tuple[Project, dict[str, bytes]], sheet: str, old: str, new: str
) -> None:
    p, f = files
    rel = "harnesses/W001/W001_build.xlsx"
    errors = _errors(p, {**f, rel: _edit_cell(f[rel], sheet, old, new)})
    assert errors and all(code == "out_build" for code, _m in errors), errors


def test_a_place_missing_from_export_json_is_out_json(files: tuple[Project, dict[str, bytes]]) -> None:  # fmt: skip
    p, f = files
    doc = json.loads(f["system/export.json"])
    for h in doc["harnesses"]:
        for s in h["shields"]:
            s.pop("at_a", None)
    changed = json.dumps(doc).encode()
    assert ("out_json", "The JSON export does not match the design.") in _errors(p, {**f, "system/export.json": changed})  # fmt: skip


# ---- import-build-data, the scripting interface, merge-fix and a join -----------------------------


def test_import_build_data_reads_the_shield_ends(p: Project) -> None:
    from harness_design_studio.core.build_data_import import detect_kind, plan_build_data_import

    table = [
        ["Harness", "Shield group", "End", "Pin", "Backshell"],
        ["W001", "W001-S3", "A", "10", ""],
        ["", "W001-S1", "a", "9", ""],
        ["", "W001-S1", "A", "", "W001-A1"],
        ["W001", "W001-S4", "B", "", ""],
    ]
    assert detect_kind(table[0])[0] == "shield_ends"
    plan = plan_build_data_import(p, table)
    assert [(r.ok, r.action, r.target, r.message) for r in plan.rows] == [
        (True, "added", "W001-S3 end A", "lands on pin 10"),
        (True, "unchanged", "W001-S1 end A", "lands on pin 9 (as it was)"),
        (True, "changed", "W001-S1 end A", "lands on pin 9 and backshell W001-A1"),
        (True, "unchanged", "W001-S4 end B", "the place as it was"),
    ]
    apply_ops(p, plan.ops)
    assert group(p, "W001-S1").at_a == ShieldEndPlace(connector="W001-P1", pin="9", backshell="W001-A1")  # fmt: skip
    bad = plan_build_data_import(p, [["Shield group", "End", "Pin"], ["W001-S3", "B", "10"]])
    assert not bad.rows[0].ok and "only a pigtail lands on a pin" in bad.rows[0].message
    assert not bad.ops


def test_set_shield_end_of_the_scripting_interface(tmp_path: Path) -> None:
    from harness_design_studio import api
    from harness_design_studio.core.io.saver import save_project

    save_project(format5_project(), tmp_path / "p")
    assert api.set_shield_end(tmp_path / "p", "W001", "W001-S3", "A", pin="10") == {
        "connector": "W001-P2",
        "pin": "10",
    }
    assert api.set_shield_end(tmp_path / "p", "W001", "W001-S3", "A") is None
    with pytest.raises(api.EditError):
        api.set_shield_end(tmp_path / "p", "W001", "W001-S3", "B", pin="10")
    with pytest.raises(api.EditError, match="not a shield group of W002"):
        api.set_shield_end(tmp_path / "p", "W002", "W001-S3", "A", pin="10")


def test_a_harness_renamed_by_merge_fix_keeps_its_places(p: Project) -> None:
    from harness_design_studio.core.merge_ids import _parts_map, _renamed_harness

    h = p.harnesses["W001"]
    new = _renamed_harness(h, "W009", _parts_map(h, "W009"))
    s = {x.id: x for x in new.shields}
    assert s["W009-S1"].at_a == ShieldEndPlace(connector="W009-P1", pin="9")
    assert s["W009-S2"].at_b == ShieldEndPlace(connector="W009-P1", backshell="W009-A1")


def test_a_place_is_never_in_a_library_file() -> None:
    from harness_design_studio.core import device_library

    assert not {"at_a", "at_b"} & device_library.FORMAT5_KEYS


def test_the_accessory_kind_of_a_new_backshell_is_backshell(p: Project) -> None:
    apply_ops(p, plan_set_shield_place(p, "W001-S3", "A", backshell=NEW_BACKSHELL))
    h = p.harnesses["W001"]
    added = [a for a in h.accessories if a.id == group(p, "W001-S3").at_a.backshell]  # type: ignore[union-attr]
    assert added == [Accessory(id="ACC-001", kind="backshell", target="W001-P2")]


def test_import_build_data_on_the_command_line_records_both_tables_of_format_5(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The kinds `shield-ends` and `cable-ends` of the import record (the record of part A's
    table had no kind before this pull request, so the command refused it)."""
    from harness_design_studio.cli.main import main
    from harness_design_studio.core.io.loader import load_project
    from harness_design_studio.core.io.saver import save_project

    root = tmp_path / "p"
    save_project(format5_project(), root)
    (tmp_path / "se.csv").write_text("Shield group,End,Pin\nW001-S3,A,10\n", encoding="utf-8")
    (tmp_path / "ce.csv").write_text("Connector,Lengths to\nW001-P3,rear\n", encoding="utf-8")
    assert main(["import-build-data", str(root), str(tmp_path / "se.csv")]) == 0
    assert main(["import-build-data", str(root), str(tmp_path / "ce.csv")]) == 0
    out = capsys.readouterr().out
    assert "Import shield ends: 1 row(s) read." in out and "row 2: OK lands on pin 10" in out
    loaded = load_project(root).project
    assert group(loaded, "W001-S3").at_a == ShieldEndPlace(connector="W001-P2", pin="10")
    kinds = sorted(r.kind for r in loaded.import_records.values())
    assert "shield-ends" in kinds and "cable-ends" in kinds


def test_the_help_of_import_build_data_names_the_table_of_shield_ends(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Fault found by the end-to-end test of 5.0.0 (pull request 8): `import-build-data` reads a
    table of shield ends since pull request 5, but its help, and so `docs/CLI.md`, named only strip
    lengths, pin contacts, accessories, crimp tools and cable ends."""
    from harness_design_studio.cli.main import main

    assert main(["import-build-data", "--help"]) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "shield ends (Shield group, End: A or B, Pin and/or Backshell" in out
    assert main(["--help"]) == 0
    assert "cable ends or shield ends" in " ".join(capsys.readouterr().out.split())
    cli_md = (Path(__file__).resolve().parents[1] / "docs" / "CLI.md").read_text(encoding="utf-8")
    assert "or shield ends (Shield group, End: A or B, Pin and/or Backshell" in cli_md
