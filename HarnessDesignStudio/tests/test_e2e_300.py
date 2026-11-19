# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-MIGRATE-08, REQ-OUT-01, REQ-HARN-04. The end-to-end walk of 3.0.0 (D-242, pull request 8 of
section 12 of `docs/ait/DESIGN_3.0_HARNESS_PLAN.md`; the splices of D-243 section 6), through the
command line wherever a command exists and through the plans the editor runs (`History`) where none
does (no command places a splice or sets the signal of one pin).

A project of 2.x with a release history: the sample `mini3`, generated, its harness W001 given its
gauge and length (`override`), exported, reviewed, released and given a new version, then written
back as a 2.x tool wrote it (`tests/migration_support.as_format`: the key `revision` with the
letters A and B, the kind `new_revision`, the baseline `W001.A`). Then `migrate --dry-run` and
`migrate`, with each letter mapped to its version (A is 1.0.0, B is 2.0.0); `log --json` with
`version` and `revision`; `diff --from A`; `new-version --kind minor` on the draft, which chooses the
kind again (2.0.0 becomes 1.1.0); a harness a person drew with a splice, the splice part from the
template `splice-parts-EXAMPLE.csv` by `import-parts`; `export --harness-plan --drawings`, one plan
per harness; `verify --outputs` with 0 errors; the plans read by the tests' own reader with every
formula evaluated; the word *Version* in the written files; a second export byte-identical.

Example data only: the sample's devices, an example reviewer, the example splice part."""

import json
from pathlib import Path

import pytest

from harness_design_studio.core import devices
from harness_design_studio.core.commands import History
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.manual_harness import plan_add_connector, plan_new_harness
from harness_design_studio.core.samples import mini3
from harness_design_studio.core.splices import plan_add_splice, plan_splice_wire
from harness_design_studio.core.wires import plan_add_wire
from harness_design_studio.resources import examples_path
from tests.migration_support import as_format
from tests.plan_support import check_values, read_plan
from tests.test_e2e_rs422x3 import files, run

WHO = ["--by", "Example Reviewer"]
ACCEPT = [
    "--accept-placeholders", "Example data for the test",
    "--accept-unapproved-parts", "Example data for the test",
]  # fmt: skip
SPLICE_PARTS = Path(str(examples_path())) / "templates" / "splice-parts-EXAMPLE.csv"
POWER_ENDS = ("PCDU-J02", "OBC-J02", "OBC-J03")


def ok(capsys: pytest.CaptureFixture[str], *args: object) -> str:
    code, out = run(capsys, *(str(a) for a in args))
    assert code == 0, out
    return out


def made_by_2x(proj: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """mini3 with W001 released as A and given the new revision B, as a 2.x tool saved it."""
    p = mini3()
    generate_project(p)
    save_project(p, proj)
    for wid in [w.id for w in p.harnesses["W001"].wires]:
        ok(capsys, "override", proj, wid, "gauge_awg", "20", "--reason", "Example gauge")
        ok(capsys, "override", proj, wid, "length_m", "1.2", "--reason", "Example length")
    ok(capsys, "export", proj)
    ok(capsys, "review", proj, "W001", *WHO, "--date", "2026-03-01")
    ok(
        capsys, "release", proj, "W001", *WHO, "--date", "2026-03-01", "--comment",
        "First build of the power harness", *ACCEPT,
    )  # fmt: skip
    ok(
        capsys, "new-version", proj, "W001", *WHO, "--date", "2026-04-01", "--comment",
        "A change after the first build", "--kind", "major",
    )  # fmt: skip
    as_format(proj, 2)
    doc = json.loads((proj / "physical" / "harnesses" / "W001.json").read_bytes())
    assert (doc["revision"], doc["status"], "version" in doc) == ("B", "draft", False)
    assert (proj / "baselines" / "W001" / "W001.A.json").is_file()
    assert json.loads((proj / "project.json").read_bytes())["schema_version"] == 2


def draw_the_splice_harness(proj: Path) -> str:
    """A power line from PCDU-J02 to OBC-J02 and OBC-J03 through one splice, drawn as the editor
    draws it (*New harness*, the *Connectors* tab, *Edit wire*, the *Splices* list)."""
    p = load_project(proj).project
    history = History(p)
    for cid in POWER_ENDS:
        history.execute("signal", devices.ops_set_pin(p, cid, p.connectors[cid].pins[0].id, signal="PWR"))  # fmt: skip
    ops, hid = plan_new_harness(p, "Power Y")
    history.execute("New harness", ops)
    plugs = []
    for box in POWER_ENDS:
        ops, cid = plan_add_connector(p, hid, mates_with=box)
        history.execute("Add connector", ops)
        plugs.append(cid)
    history.execute("wire", plan_add_wire(p, hid, plugs[0], "1", plugs[1], "1", signal="PWR"))
    ops, sid = plan_add_splice(p, hid, "EX-SPLICE-1", termination="crimp")
    history.execute("Add splice", ops)
    ops, _new = plan_splice_wire(p, f"{hid}-001", sid)
    history.execute("Splice this wire", ops)
    history.execute("wire", plan_add_wire(p, hid, sid, "1", plugs[2], "1", signal="PWR"))
    save_project(p, proj)
    return hid


def test_the_whole_path_of_3_0_0_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = tmp_path / "proj"
    # 1. a project of 2.x with a release history: the letters A and B
    made_by_2x(proj, capsys)

    # 2. the upgrade: each letter mapped to its version
    code, out = run(capsys, "generate", str(proj))
    assert code != 0 and "migrate" in out  # a format 2 project is written only by migrate
    out = ok(capsys, "migrate", proj, "--dry-run")
    assert "revision A → version 1.0.0" in out and "revision B → version 2.0.0" in out
    assert "Only the versions change" in out
    assert json.loads((proj / "project.json").read_bytes())["schema_version"] == 2
    out = ok(capsys, "migrate", proj)
    assert "Format 2 to 4." in out
    p = load_project(proj).project
    assert (p.harnesses["W001"].version, p.harnesses["W001"].status) == ("2.0.0", "draft")
    assert sorted(p.baselines) == ["W001.1.0.0"]
    assert (proj / "baselines" / "W001" / "W001.1.0.0.json").is_file()
    assert not (proj / "baselines" / "W001" / "W001.A.json").exists()
    code, out = run(capsys, "log", str(proj), "W001", "--json")
    assert code == 0, out
    entries = json.loads(out)["entries"]
    assert [(e["version"], e["revision"]) for e in entries] == [
        (e["version"], e["version"]) for e in entries
    ]  # both keys through 3.0.x, with the same value
    assert {e["version"] for e in entries} == {"1.0.0", "2.0.0"}
    out = ok(capsys, "diff", proj, "W001", "--from", "A")
    assert "A is read as version 1.0.0" in out

    # 3. new-version --kind on the draft before its review: the kind chosen again
    out = ok(
        capsys, "new-version", proj, "W001", *WHO, "--date", "2026-04-02", "--comment",
        "Only a new wire colour after all", "--kind", "minor",
    )  # fmt: skip
    assert "2.0.0 of W001 becomes 1.1.0 (minor)" in out
    assert load_project(proj).project.harnesses["W001"].version == "1.1.0"

    # 4. a harness with a splice; the splice part from the template
    ok(capsys, "import-parts", proj, SPLICE_PARTS, "--pending", "Review")
    hid = draw_the_splice_harness(proj)
    ok(capsys, "generate", proj)  # Generate keeps the harness a person drew
    for command in ("validate", "check", "verify"):
        ok(capsys, command, proj)

    # 5. export with the plans: one per harness
    code, out = run(capsys, "export", str(proj), "--harness-plan", "--drawings", "--json")
    assert code == 0, out
    plans = json.loads(out)["harness_plans"]
    assert plans == [f"harnesses/{h}/{h}_plan.ods" for h in ("W001", "W002", hid)]
    # 6. the independent check: 0 errors
    out = ok(capsys, "verify", proj, "--outputs")
    assert "0 error(s)" in out
    outputs = proj / "outputs"
    for plan in plans:
        sheets = read_plan((outputs / plan).read_bytes())
        assert check_values(sheets) == [], plan  # every formula gives its stored value
    w001 = read_plan((outputs / plans[0]).read_bytes())
    assert "VERSION: v1.1.0 (draft)" in {c.value for c in w001["W001"].values()}
    spliced = read_plan((outputs / plans[2]).read_bytes())
    shown = {str(c.value) for sheet in spliced.values() for c in sheet.values()}
    # a Y through a splice: the two branches at the near end, the trunk under Further wires
    assert {"Further wires", f"{hid}-001"} <= shown and f"{hid}-002" not in shown
    tests = (outputs / "harnesses" / hid / "tests.csv").read_text(encoding="utf-8")
    assert f"{hid}-P1.1,{hid}-P3.1 via {hid}-X1" in tests
    # the word Version in the written files
    log = (outputs / "system" / "changelog.csv").read_text(encoding="utf-8")
    heading = next(line for line in log.splitlines() if not line.startswith("#"))
    assert "Version" in heading.split(",") and "Revision" not in heading
    assert "version changed" in log and "new version started" in log
    assert (outputs / "system" / "version_report.md").is_file()
    assert not (outputs / "system" / "revision_report.md").exists()
    export = json.loads((outputs / "system" / "export.json").read_bytes())
    assert all(h["version"] == h["revision"] for h in export["harnesses"])

    # 7. a second export: byte-identical
    first = files(outputs)
    ok(capsys, "export", proj, "--harness-plan", "--drawings")
    assert files(outputs) == first
