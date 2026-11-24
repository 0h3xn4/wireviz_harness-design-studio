# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-EX-01, REQ-EX-02. The end-to-end walk of 5.1.0 (pull request 7 of section 14 of
`docs/ait/DESIGN_5.1_FEATURE_TEMPLATES.md`; the test of its section 10), through the command line
as a person types it.

- The list: `new --list` prints the group *Start* (the five examples of 1.0.0) and then the group
  *Feature examples*, whose heading names the manual page *Examples*, with the fourteen in the order
  of the manual and the names in a column as wide as the longest name plus two; `new --list --json`
  gives the same order and each example's group; the page *Examples* lists them in that order.
- Every feature example, in a folder of its own: `new` (with a journal, as a person runs it),
  `check` with 0 errors and 0 warnings, `generate` with nothing to do (no file changes; the
  two splice examples, which have no interface, get their first generation record), `drc` with
  exit code 0 and no open error (only the baseline findings and what the example's page names),
  `export`, then `verify --outputs` with 0 errors, and a second export into another folder byte
  for byte the same; then the commands the example's manual page names (`pin-rows`, `explain`,
  `routing`, `release --accept-loose-ends`, `log`, `diff`, `deviation`, `libraries`,
  `update-device`, `asbuilt`, `imports`, `extensions`, `trust`).
- The exercises of section 4 on copies: the spare fraction and the pin gap set on
  `full-connectors`, a depth taken off in `lengths-to-the-face`. (The far-device setting turned
  off on `names-and-ports` is `tests/test_feature_examples.py`.)
- No new key (section 8): every example loads without an error, says format 5, and the fields of
  the schemas that `schema` writes are those the 5.0.0 tool writes (recorded below from a run of
  the code of the tag `v5.0.0`; that code also opened, checked and ran `drc` on every example with
  0 errors when this test was written).
- The editor (offscreen): Home says *14 feature examples*, and the window *New project* heads
  the second group with an accessible name that names the page *Examples*.

Every device, part, person and number here is made up for the examples (`EX-…`, *Designer 1*)."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.core import build_data, templates
from harness_design_studio.core.commands import History
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import SCHEMA_VERSION
from harness_design_studio.resources import examples_path
from tests.test_e2e_rs422x3 import files, run
from tests.test_feature_examples import _fresh_extensions

PROJECTS = examples_path() / "projects"  # type: ignore[operator]
START = ["blank", "first-steps", "minimal-satellite", "small-satellite", "flatsat"]
# the order of the manual (design of 5.1.0, sections 4.1 to 4.14 and 6)
FEATURES = [
    "full-connectors", "names-and-ports", "splice-by-hand", "splice-from-connection",
    "branching-harness", "loose-cable-end", "shields-and-ends", "lengths-to-the-face",
    "released-harness", "overrides-and-deviations", "device-library", "build-data-and-as-built",
    "imports-from-files", "extensions",
]  # fmt: skip
HEADING = (
    "Feature examples (small projects, one feature each; the manual page Examples lists them):"
)
# what `drc` names on every example: one part-unapproved per EX- part, the notes of the placeholder
# values a rule needs; and beyond it, what the page of an example names (section 5.3)
BASELINE = frozenset({"part-unapproved", "unchecked-config"})
NAMED = {"extensions": frozenset({"x-extension-problem"})}
# the infos of `check` that the page of an example names
INFOS = {"shields-and-ends": "shield_place_not_stated"}
# The fields of each schema file that `schema` writes, as the code of the tag v5.0.0 writes them:
# the SHA-256 (first 16 hex digits) of the sorted lines `Title.field` of every object of the file.
SCHEMA_FIELDS_500 = {
    "asbuilt": "036d5a0ddc94509e",
    "baseline": "2450dea1e1e3a8b2",
    "changelog": "7bc6f11086fe0065",
    "config": "3accc60999bb160e",
    "connectors": "a93e3e6d355baa95",
    "device-file": "78ae6447df0bdbc5",
    "device-libraries": "93148fc84c61c1e4",
    "diagram-marks": "4c7d5b504bebdd09",
    "extension": "56b324bab0c6dfa5",
    "extensions-enabled": "e84f4b65ba9e6d55",
    "generation": "659b1029d6557d86",
    "harness": "9029f8ea591580d2",
    "import-records": "39d449e6b7fd0224",
    "interface-types": "f7649dd89e639122",
    "interfaces": "f7a07bd1cc3aa07f",
    "journal": "9bb275b5a7819bd4",
    "layout": "ff21dae478265367",
    "library-info": "dff33091bbccdc00",
    "links": "e6aedc0c0c2ca9ad",
    "parts": "3eab2791b1c169a7",
    "project": "df5fd60191f18a0c",
    "units": "bf918c7a8a221403",
    "waivers": "f1125c9873c44104",
}
RELEASE = [
    "--by", "Checker 1", "--date", "2026-01-15", "--comment", "EXAMPLE release for learning",
    "--accept-placeholders", "EXAMPLE values for learning",
    "--accept-unapproved-parts", "EXAMPLE parts for learning",
]  # fmt: skip


def project_files(folder: Path) -> dict[str, bytes]:
    """The files of a project, without the lock files a command leaves."""
    return {k: v for k, v in files(folder).items() if not k.startswith(".harness.lock")}


def json_of(capsys: pytest.CaptureFixture[str], *args: str, rc: int = 0) -> Any:
    code, out = run(capsys, *args, "--json")
    assert code == rc, out
    return json.loads(out)


def said(capsys: pytest.CaptureFixture[str], *args: str, rc: int = 0) -> str:
    code, out = run(capsys, *args)
    assert code == rc, f"{args}: exit {code}\n{out}"
    return out


# ---- the list ------------------------------------------------------------------------------------


def test_new_list_shows_the_two_groups_in_the_order_of_the_manual(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lines = said(capsys, "new", "--list").splitlines()
    width = max(len(n) for n in START + FEATURES) + 2
    summary = {t.name: t.summary for t in templates.TEMPLATES}
    assert lines == [
        "Start:",
        *(f"{n:{width}}{summary[n]}" for n in START),
        HEADING,
        *(f"{n:{width}}{summary[n]}" for n in FEATURES),
    ]
    doc = json_of(capsys, "new", "--list")
    assert [(t["name"], t["group"]) for t in doc["templates"]] == [
        *((n, "start") for n in START),
        *((n, "feature") for n in FEATURES),
    ]
    assert sorted(p.name for p in PROJECTS.iterdir() if p.is_dir()) == sorted(START + FEATURES)
    page = (Path(__file__).parents[1] / "docs" / "user-manual" / "examples.md").read_text("utf-8")
    assert [page.index(f"| `{n}` |") for n in START + FEATURES] == sorted(
        page.index(f"| `{n}` |") for n in START + FEATURES
    )  # the page lists them in the same order


# ---- every feature example, end to end -----------------------------------------------------------


def _page_commands(capsys: pytest.CaptureFixture[str], name: str, d: str) -> None:
    """The commands the manual page of the example names, with what they print."""
    if name == "full-connectors":
        out = said(capsys, "pin-rows", d, "--connector", "OBC1-J01")
        assert "Pin rows of OBC1-J01: 1–5 / 6–9 (from part EX-MICROD-9-M)" in out
    elif name == "names-and-ports":
        out = said(capsys, "explain", d, "W001")
        assert "OBC1-J01 to TTC1-J01 + TTC2-J01" in out
        assert json_of(capsys, "imports", d)["count"] == 3  # the pinouts, read through the map
    elif name == "splice-by-hand":
        out = said(capsys, "routing", d, "W001")
        assert "W001-X1 (splice)" in out and "W001-X2 (splice)" in out
    elif name == "splice-from-connection":
        out = said(capsys, "explain", d, "W001-001")
        assert "Current carried = 4 A" in out and "Current at OBC1-J01.2: pin 2 of OBC1-J01: Current (A) = 2 A" in out  # fmt: skip
    elif name == "branching-harness":
        out = said(capsys, "routing", d, "W002")
        assert "It branches at 1 branch point" in out and "W002-B2" in out
    elif name == "loose-cable-end":
        said(capsys, "review", d, "W002", "--by", "Designer 1", "--date", "2026-01-12")
        out = said(capsys, "release", d, "W002", *RELEASE, rc=1)
        assert "[loose_end_unresolved]" in out and "W002-P2, W002-P3" in out
        reason = "EXAMPLE: the bench end is chosen later"
        said(capsys, "release", d, "W002", *RELEASE, "--accept-loose-ends", reason)
    elif name == "lengths-to-the-face":
        out = said(capsys, "explain", d, "W001-001")
        assert "Depth of part EX-MICROD-9-M (W001-P1, measured to its face) = 18 mm" in out
    elif name == "released-harness":
        out = said(capsys, "log", d, "W002")
        assert "| released | Releaser 1 | 2026-01-15 |" in out and "| 1.1.0 | new version started |" in out  # fmt: skip
        assert "# W002: working design against version 1.0.0" in said(capsys, "diff", d, "W002")
    elif name == "overrides-and-deviations":
        out = said(capsys, "deviation", d)
        assert "DEVIATION current-over-wire.W002-001" in out and "DEVIATION voltage-drop.W002-001" in out  # fmt: skip
        assert "Waived: 1. Deviations: 2." in said(capsys, "drc", d)
    elif name == "device-library":
        out = said(capsys, "libraries", d, "--devices")
        assert "TTC1    library changed" in out and "OBC1    up to date" in out
        out = said(capsys, "update-device", d, "TTC1")
        assert "Telemetry and ranging out, positive" in out
        said(capsys, "update-device", d, "TTC1", "--apply")
        assert "library changed" not in said(capsys, "libraries", d, "--devices")
    elif name == "build-data-and-as-built":
        out = said(capsys, "asbuilt", d, rc=1)  # one value out of its EXAMPLE limit, on purpose
        assert "1 out of limit" in out and "OUT OF TOLERANCE by 15 mm" in out
        said(capsys, "export", d, "--harness-plan")
        assert ": 0 error(s)" in said(capsys, "verify", d, "--outputs")
    elif name == "imports-from-files":
        assert "7 import record(s)" in said(capsys, "imports", d)
    elif name == "extensions":
        _fresh_extensions()
        assert "enabled, not trusted" in said(capsys, "extensions", d, rc=1)
        said(capsys, "trust", d, "duplicate-signal-wires", "--yes")  # the exercise
        _fresh_extensions()
        said(capsys, "extensions", d)
        assert json_of(capsys, "drc", d)["rules_run"] == 46
        said(capsys, "trust", d, "duplicate-signal-wires", "--revoke")
        _fresh_extensions()


@pytest.mark.parametrize("name", FEATURES)
def test_a_feature_example_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    folder = tmp_path / name
    d = str(folder)
    title = templates.template_info(name).title  # type: ignore[union-attr]
    assert f"Project '{title}' created in {d}" in said(capsys, "new", d, "--template", name)
    assert (folder / "journal.jsonl").is_file()
    if name == "extensions":
        _fresh_extensions()
    # check: 0 errors, 0 warnings; an info only where the page names it
    doc = json_of(capsys, "check", d)
    assert (doc["errors"], doc["warnings"]) == (0, 0), doc["issues"]
    if name in INFOS:
        assert INFOS[name] in {i["code"] for i in doc["issues"]}
    assert said(capsys, "check", d).rstrip().endswith("0 error(s), 0 warning(s).")
    # generate: nothing to do; no file of the project changes (an example without an interface,
    # which Generate has never run on, gets its first generation record)
    before = project_files(folder)
    out = said(capsys, "generate", d)
    assert out.startswith("0 added, 0 changed,") and " 0 removed," in out, out
    after = project_files(folder)
    if "generated/generation.json" not in before:
        assert not load_project(folder).project.interfaces, name
        after.pop("generated/generation.json")
    assert after == before
    # drc: exit 0, no open error; only the baseline and what the page names
    assert "Open: 0 error(s)" in said(capsys, "drc", d)
    drc = json_of(capsys, "drc", d)
    assert drc["open_errors"] == 0
    open_rules = {f["rule"] for f in drc["findings"] if not f["waived"]}
    assert open_rules == BASELINE | NAMED.get(name, frozenset()), sorted(open_rules)
    # export, verify --outputs, a second export byte for byte the same
    assert " files written to " in said(capsys, "export", d)
    verify = json_of(capsys, "verify", d, "--outputs")
    assert not [i for i in verify["issues"] if i["severity"] == "error"], verify["issues"]
    said(capsys, "export", d, "--out", str(tmp_path / "again"))
    assert files(tmp_path / "again") == files(folder / "outputs")
    _page_commands(capsys, name, d)


# ---- the exercises of section 4, on copies -------------------------------------------------------


def test_full_connectors_the_spare_fraction_and_the_pin_gap_make_the_rules_speak(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    d = str(tmp_path / "p")
    said(capsys, "new", d, "--template", "full-connectors", "--no-journal")
    said(capsys, "settings", d, "--set", "derating.spare_pin_fraction=0.1")
    said(capsys, "generate", d)
    drc = json_of(capsys, "drc", d)
    spare = {f["id"].split(".", 1)[1] for f in drc["findings"] if f["rule"] == "spare-pins-low"}
    assert spare == {
        "OBC1-J01",
        "OBC1-J02",
        "PCDU1-J01",
        "PCDU1-J02",
        "TTC1-J01",
        "TTC1-J02",
    }  # fmt: skip  (a full connector has no spare)
    said(capsys, "settings", d, "--set", "generation.power_return_gap_pins=1")
    said(capsys, "generate", d)
    found = json_of(capsys, "drc", d)["findings"]
    gaps = [f for f in found if f["rule"] == "power-return-adjacent"]
    assert gaps and any("row 1 of the face" in f["title"] for f in gaps)  # the rows are read


def test_lengths_to_the_face_a_depth_taken_off_is_named_by_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "p"
    said(capsys, "new", str(folder), "--template", "lengths-to-the-face", "--no-journal")
    p = load_project(folder).project
    History(p).execute("Depth", build_data.plan_set_part_depth(p, "EX-MICROD-15-M", None))
    save_project(p, folder)
    doc = json_of(capsys, "check", str(folder))
    missing = [i for i in doc["issues"] if i["code"] == "length_depth_missing"]
    assert [(i["severity"], i["object_id"]) for i in missing] == [("warning", "W002-P1")], missing


# ---- no new key: what the 5.0.0 tool reads -------------------------------------------------------


def _fields(doc: Any) -> set[str]:
    """`Title.field` of every object of a JSON schema."""
    out: set[str] = set()
    if isinstance(doc, dict):
        props = doc.get("properties")
        if isinstance(props, dict):
            out |= {f"{doc.get('title', '')}.{k}" for k in props}
        for value in doc.values():
            out |= _fields(value)
    elif isinstance(doc, list):
        for value in doc:
            out |= _fields(value)
    return out


def test_every_example_is_in_format_5_with_the_fields_of_5_0_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert SCHEMA_VERSION == 5
    for t in templates.TEMPLATES:
        assert not load_project(PROJECTS / t.name).has_errors, t.name
        meta = json.loads((PROJECTS / t.name / "project.json").read_text(encoding="utf-8"))
        assert meta["schema_version"] == 5, t.name
    said(capsys, "schema", str(tmp_path / "schemas"))
    found = {
        p.name.removesuffix(".schema.json"): hashlib.sha256(
            "\n".join(sorted(_fields(json.loads(p.read_text(encoding="utf-8"))))).encode()
        ).hexdigest()[:16]
        for p in sorted((tmp_path / "schemas").glob("*.schema.json"))
    }
    assert found == SCHEMA_FIELDS_500


# ---- the editor ----------------------------------------------------------------------------------


@pytest.mark.gui
def test_home_counts_the_feature_examples_and_the_dialog_names_the_page(
    qtbot: Any, tmp_path: Path
) -> None:
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QSettings, Qt

    from harness_design_studio.gui import strings
    from harness_design_studio.gui.main_window import MainWindow
    from harness_design_studio.gui.new_project_dialog import NewProjectDialog
    from harness_design_studio.gui.theme import ThemeManager

    theme = ThemeManager()
    win = MainWindow(QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat), theme, first_run=False)  # fmt: skip
    qtbot.addWidget(win)
    win.show_landing()
    line = win.home_page.features_line.text()
    assert line == "14 feature examples, one per feature: File > New project from an example…"
    dlg = NewProjectDialog(theme, start_folder=tmp_path)
    qtbot.addWidget(dlg)
    headings = {g: h.text() for g, h in dlg.headings.items()}
    assert headings == {templates.START: "Start", templates.FEATURE: "Feature examples"}
    name = dlg.headings[templates.FEATURE].data(Qt.ItemDataRole.AccessibleTextRole)
    assert name == strings.NP_GROUP_FEATURE_NAME and "page Examples" in name
