# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate the golden output digests (and the readable mini3 text outputs) on purpose.
Usage: python -m tools.gen_output_goldens   (then review the diff)

`loose_ends` (M4b of the 2.0 programme, D-201) is the project with loose cable ends of
`tests/loose_support.py` (the flatsat example and five harnesses a person drew): the digest of
every file, and the text files of the drawn harnesses and the system BOM and mass to read.

`harness_plan/` (3.0.0, D-242, pull request 3 of `docs/ait/DESIGN_3.0_HARNESS_PLAN.md`): the
harness plans of the four examples and of the branching fixture, made with the plan on
(`build_outputs(..., harness_plan=True)`): the SHA-256 of each plan in `<project>.json`, and the
cells of the plans of `first-steps` and `branching` as text in `<project>/` to read in a diff."""

import json
import shutil
import tempfile
from pathlib import Path

from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.outputs.build import build_outputs
from harness_design_studio.core.samples import mini3, sat15, sat15_full
from tests.helpers import output_digests
from tests.loose_support import generated_loose, golden_text_files
from tests.plan_support import GOLDEN_PROJECTS, READABLE, golden_files, golden_project

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
