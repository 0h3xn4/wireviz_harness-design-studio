# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate the golden output digests (and the readable mini3 text outputs) on purpose.
Usage: python -m tools.gen_output_goldens   (then review the diff)

`loose_ends` (M4b of the 2.0 programme, D-201) is the project with loose cable ends of
`tests/loose_support.py` (the flatsat example and five harnesses a person drew): the digest of
every file, and the text files of the drawn harnesses and the system BOM and mass to read.

`splices` (format 3, M6a) is the project with splices of `tests/splice_support.py`
(`branch_leg_project`: mini3 with a Y harness through two splices and a harness with a splice on a
branch point's leg): the digest of every file, and the text files of those two harnesses.

`row_layout` (format 4, pull request 3 of `docs/ait/DESIGN_4.0_ROW_LAYOUT.md`) is the project with
row layouts of `tests/row_layout_support.py` (`row_layout_project`: mini3 with the rows of a part
and the own rows of a box connector): the digest of every file, and the pinout tables and
`system/export.json` as text to read. Its plans are in `harness_plan/row_layout*`.

`format5` (format 5, pull request 2 of `docs/ait/DESIGN_5.0_FORMAT_5.md` on, section 11) is the
project with data of format 5 of `tests/format5_support.py` (`format5_project`: the branching
fixture with face ends and depths): the digest of every file, and the wire lists, the segments, a
WireViz file and `system/export.json` as text to read. Its plans are in `harness_plan/format5*`.

`harness_plan/` (3.0.0, D-242, pull requests 3 and 6 of `docs/ait/DESIGN_3.0_HARNESS_PLAN.md`):
the harness plans of the four examples, of the branching fixture, of the splice fixture
(`splices`, `branch_leg_project`) and of the row layout fixture (`row_layout`), made with the plan on (`build_outputs(..., harness_plan=True)`):
the SHA-256 of each plan in `<project>.json`, and the cells of the plans of `first-steps`,
`branching`, `splices` and `row_layout` as text in `<project>/` to read in a diff."""

import json
import shutil
import tempfile
from pathlib import Path

from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.outputs.build import build_outputs
from harness_design_studio.core.samples import mini3, sat15, sat15_full
from tests.format5_support import format5_project
from tests.format5_support import golden_text_files as format5_text_files
from tests.helpers import output_digests
from tests.loose_support import generated_loose, golden_text_files
from tests.plan_support import GOLDEN_PROJECTS, READABLE, golden_files, golden_project
from tests.row_layout_support import golden_text_files as row_layout_text_files
from tests.row_layout_support import row_layout_project
from tests.splice_support import branch_leg_project
from tests.splice_support import golden_text_files as splice_text_files

ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "outputs"


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for name, make in (("mini3", mini3), ("sat15", sat15), ("sat15_full", sat15_full)):
        p = make()
        if name != "sat15_full":
            generate_project(p)
        files = build_outputs(p).files
        (ROOT / f"{name}.json").write_text(
            json.dumps(output_digests(files), indent=1, sort_keys=True) + "\n"
        )
        if name == "mini3":
            text = ROOT / "mini3"
            shutil.rmtree(text, ignore_errors=True)
            for rel, data in files.items():
                if rel.endswith((".csv", ".svg", ".yaml", ".md", ".json")):
                    (text / rel).parent.mkdir(parents=True, exist_ok=True)
                    (text / rel).write_bytes(data)
    with tempfile.TemporaryDirectory() as tmp:
        p = load_project(generated_loose(Path(tmp) / "loose")).project
    files = build_outputs(p).files
    (ROOT / "loose_ends.json").write_text(
        json.dumps(output_digests(files), indent=1, sort_keys=True) + "\n"
    )
    text = ROOT / "loose_ends"
    shutil.rmtree(text, ignore_errors=True)
    for rel, data in golden_text_files(files).items():
        (text / rel).parent.mkdir(parents=True, exist_ok=True)
        (text / rel).write_bytes(data)
    files = build_outputs(branch_leg_project()).files
    (ROOT / "splices.json").write_text(
        json.dumps(output_digests(files), indent=1, sort_keys=True) + "\n", newline="\n"
    )
    text = ROOT / "splices"
    shutil.rmtree(text, ignore_errors=True)
    for rel, data in splice_text_files(files).items():
        (text / rel).parent.mkdir(parents=True, exist_ok=True)
        (text / rel).write_bytes(data)
    files = build_outputs(row_layout_project()).files
    (ROOT / "row_layout.json").write_text(
        json.dumps(output_digests(files), indent=1, sort_keys=True) + "\n", newline="\n"
    )
    text = ROOT / "row_layout"
    shutil.rmtree(text, ignore_errors=True)
    for rel, data in row_layout_text_files(files).items():
        (text / rel).parent.mkdir(parents=True, exist_ok=True)
        (text / rel).write_bytes(data)
    files = build_outputs(format5_project()).files
    (ROOT / "format5.json").write_text(
        json.dumps(output_digests(files), indent=1, sort_keys=True) + "\n", newline="\n"
    )
    text = ROOT / "format5"
    shutil.rmtree(text, ignore_errors=True)
    for rel, data in format5_text_files(files).items():
        (text / rel).parent.mkdir(parents=True, exist_ok=True)
        (text / rel).write_bytes(data)
    plans = ROOT / "harness_plan"
    shutil.rmtree(plans, ignore_errors=True)
    plans.mkdir()
    for name in GOLDEN_PROJECTS:
        digests, texts = golden_files(build_outputs(golden_project(name), harness_plan=True).files)
        (plans / f"{name}.json").write_text(
            json.dumps(digests, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
        for rel, body in texts.items() if name in READABLE else ():
            (plans / name / rel).parent.mkdir(parents=True, exist_ok=True)
            (plans / name / rel).write_text(body, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
