# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The record of the written files of 2.x for the proof of format 3 (D-242, design of 3.0.0
`docs/ait/DESIGN_3.0_HARNESS_PLAN.md` section 5.6, part 3).

    python -m tools.format3_record OUT_DIR FIXTURES_DIR     # with the source of 2.x on PYTHONPATH

It exports a fixed set of projects (`PROJECTS`) with whichever source of the tool is on the path and
writes one file per project into OUT_DIR. The record of `tests/fixtures/format3/before/` was made
with the code of R1 (`feat/versions-r1` at 33690a7, version 2.3.1, format 2), run as

    PYTHONPATH=<checkout of R1>/HarnessDesignStudio/src:<this checkout>/HarnessDesignStudio \\
        python -m tools.format3_record tests/fixtures/format3/before <checkout of R1>/.../tests/fixtures

so that this module, the same for both sides, is what reads the files. `tests/test_format3.py` runs
`dump_project` with this tool's code and compares the two after the steps of section 5.6.

To keep the record small, a workbook is kept as the cells and the column widths of each sheet, its
document properties and the header and footer of each sheet, and the hash of each member, a drawing (PDF and SVG) as its text items with their positions and its
hash, a JSON file as its content, and every other file as its text. Each file also carries the digest that
`tools.output_hashes` (`sha256`) and the output goldens (`golden`) give it, so that a test can show
that the record is what 2.x wrote. The module uses nothing of the tests, so it runs with the
source of 2.x."""

import hashlib
import io
import json
import re
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from harness_design_studio import __version__
from harness_design_studio.core.commands import History, Put, apply_ops
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import Project, evolve
from harness_design_studio.core.outputs.build import write_outputs

BASE_VERSION = (
    "2.0.0"  # the version the 2.x output-hash baseline names (tools.output_hashes of 2.x)
)
EXAMPLES = ("first-steps", "minimal-satellite", "small-satellite", "flatsat")
REASON = "Test project: values are placeholders"
# the digest each file of a project carries: mini3 has the goldens of 2.x, the examples the
# output-hash baseline; the projects that have neither carry the digest of the baseline's kind
DIGESTS = {"mini3": "golden"}
_PDF_TEXT = re.compile(
    rb"BT /(\S+) (\S+) Tf ([0-9. ]+) rg (\S+) (\S+) Td \(((?:\\.|[^\\)])*)\) Tj ET"
)
_SVG_TEXT = re.compile(r"<text ([^>]*)>(.*?)</text>", re.S)


def _example(name: str) -> Callable[[Path], Project]:
    def make(tmp: Path) -> Project:
        from harness_design_studio.core import templates
        from harness_design_studio.core.generate.engine import generate_project

        project = templates.create_project(tmp / name, name)
        if not project.harnesses:
            generate_project(project)
        # as tools.output_hashes prepares an example, so that the digests are those of the baseline
        project.meta = evolve(project.meta, tool_version=BASE_VERSION)
        if project.generation is not None:
            project.generation = evolve(project.generation, generator_version=BASE_VERSION)
        return project

    return make


def _sample(name: str) -> Callable[[Path], Project]:
    def make(tmp: Path) -> Project:
        from harness_design_studio.core import samples
        from harness_design_studio.core.generate.engine import generate_project

        project: Project = getattr(samples, name)()
        generate_project(project)  # as tools.gen_output_goldens makes the goldens of mini3, sat15
        return project

    return make


def _fixture(name: str, fixtures: Path) -> Callable[[Path], Project]:
    return lambda tmp: load_project(fixtures / "projects" / name).project


def _release_history(tmp: Path) -> Project:
    """mini3 with W001 released at its first revision, a new revision (the major step, the letter B
    of 2.x), released again: the change log, the version report and the baselines hold both."""
    from harness_design_studio.core import samples
    from harness_design_studio.core.generate.engine import generate_project
    from harness_design_studio.core.vcs.release import plan_new_revision, plan_release

    project = samples.mini3()
    generate_project(project)
    h = project.harnesses["W001"]
    wires = [evolve(w, gauge_awg=20, length_m=1.5) for w in h.wires]
    apply_ops(project, [Put("harnesses", evolve(h, wires=wires))])
    history = History(project)
    for n, when in enumerate(("2026-03-01", "2026-04-02")):
        folder = tmp / f"release-{n}"
        write_outputs(project, folder)
        plan = plan_release(
            project, "W001", by="Ada", checker="Bob", comment="Release for the review",
            when=when, outputs_folder=folder, accept_placeholders=REASON,
            accept_unapproved_parts=REASON,
        )  # fmt: skip
        assert plan.ok, [b.message for b in plan.blockers]
        history.execute(plan.label, plan.ops)
        if n == 0:
            plan = plan_new_revision(
                project, "W001", by="Ada", comment="Change after the review", when="2026-04-01"
            )
            assert plan.ok, [b.message for b in plan.blockers]
            history.execute(plan.label, plan.ops)
    return project


def projects(fixtures: Path) -> dict[str, Callable[[Path], Project]]:
    """The projects of the record: the four examples as `tools.output_hashes` makes them, mini3 as
    the goldens make it, the fixture custom_device, and mini3 with a release history. sat15 is not
    recorded apart: the example small-satellite is the sample sat15 under another name
    (`tools.build_examples`), and a second copy would take the record past its size (5 MB)."""
    out: dict[str, Callable[[Path], Project]] = {f"example-{n}": _example(n) for n in EXAMPLES}
    out["mini3"] = _sample("mini3")
    out["custom_device"] = _fixture("custom_device", fixtures)
    out["mini3-released"] = _release_history
    return out


# ---- the dump of one written file ----------------------------------------------------------------


def as_in_base_version(data: bytes) -> bytes:
    """The bytes with the version of the tool read as `BASE_VERSION`, as tools.output_hashes of
    2.x reads them (both have the same length)."""
    if __version__ == BASE_VERSION or len(__version__) != len(BASE_VERSION):
        return data
    return data.replace(__version__.encode(), BASE_VERSION.encode())


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def baseline_digest(rel: str, data: bytes) -> str:
    """The digest of `tools.output_hashes`: a workbook by its members, anything else as bytes."""
    if rel.endswith(".xlsx"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            parts = sorted((n, _sha(as_in_base_version(z.read(n)))) for n in z.namelist())
        return _sha(json.dumps(parts).encode())
    return _sha(as_in_base_version(data))


def golden_digest(rel: str, data: bytes) -> str:
    """The digest of the output goldens (`tests.helpers.output_digests`)."""
    from harness_design_studio.core.outputs.verify import _xlsx_sheets, _xlsx_values

    if rel.endswith("_build.xlsx"):
        data = json.dumps(_xlsx_values(data), sort_keys=True).encode()
    elif rel.endswith(".xlsx"):
        data = json.dumps(_xlsx_sheets(data), sort_keys=True).encode()
    return _sha(data)


def _sheets(data: bytes) -> dict[str, dict[str, Any]]:
    """Each sheet of a workbook: its cells (as text, by reference) and its column widths."""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data))
    out: dict[str, dict[str, Any]] = {}
    for ws in wb.worksheets:
        cells = {
            c.coordinate: str(c.value) for row in ws.iter_rows() for c in row if c.value is not None
        }
        widths = {
            k: d.width for k, d in sorted(ws.column_dimensions.items()) if d.width is not None
        }
        out[ws.title] = {"cells": cells, "widths": widths}
    return out


_HEADER_FOOTER = re.compile(rb"<headerFooter>.*?</headerFooter>", re.S)


def _member_texts(z: zipfile.ZipFile) -> dict[str, str]:
    """The parts of a workbook that hold the stamp outside the cells: the document properties
    (`docProps/core.xml`) and the header and footer of each sheet, kept once under
    `xl/worksheets/*` when every sheet has the same."""
    out: dict[str, str] = {}
    sheets: dict[str, str] = {}
    for n in sorted(z.namelist()):
        data = as_in_base_version(z.read(n))
        if n == "docProps/core.xml":
            out[n] = data.decode("utf-8")
        elif n.startswith("xl/worksheets/") and (m := _HEADER_FOOTER.search(data)):
            sheets[n] = m[0].decode("utf-8")
    if sheets and len(set(sheets.values())) == 1:
        out["xl/worksheets/*"] = next(iter(sheets.values()))
    else:
        out.update(sheets)
    return out


def pdf_items(data: bytes) -> list[list[str]]:
    """The text items of a PDF of the tool's own writer: font, size, colour, x, y and the text."""
    return [
        [
            m[1].decode(),
            m[2].decode(),
            m[3].decode(),
            m[4].decode(),
            m[5].decode(),
            m[6].decode("latin-1"),
        ]
        for m in _PDF_TEXT.finditer(data)
    ]


def svg_items(text: str) -> list[list[str]]:
    """The text items of an SVG drawing: the attributes of `<text>` and its content."""
    return [[m[1], m[2]] for m in _SVG_TEXT.finditer(text)]


def dump_file(rel: str, data: bytes, digest: str = "sha256") -> dict[str, Any]:
    """One file as the record holds it, with the digest of the output-hash baseline (`sha256`) or
    of the output goldens (`golden`), whichever 2.x holds for the project (`DIGESTS`)."""
    entry: dict[str, Any] = {
        digest: baseline_digest(rel, data) if digest == "sha256" else golden_digest(rel, data)
    }
    if rel.endswith(".xlsx"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            entry["members"] = {
                n: _sha(as_in_base_version(z.read(n))) for n in sorted(z.namelist())
            }
            entry["texts"] = _member_texts(z)
        entry["sheets"] = _sheets(data)
    elif rel.endswith(".pdf"):
        entry["items"] = pdf_items(data)
    elif rel.endswith(".svg"):
        entry["items"] = svg_items(data.decode("utf-8"))
    elif rel.endswith(".json"):  # kept as its content: the formatting is the tool's canonical JSON
        entry["json"] = json.loads(as_in_base_version(data))
    else:
        entry["text"] = as_in_base_version(data).decode("utf-8")
    return entry


def written_files(project: Project, tmp: Path) -> dict[str, bytes]:
    """Every file an export into a new folder writes, the manifest included."""
    folder = tmp / "outputs"
    write_outputs(project, folder)
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def dump_project(make: Callable[[Path], Project], digest: str = "sha256") -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        project = make(Path(tmp))
        files = written_files(project, Path(tmp))
    return {
        "tool_version": __version__,
        "files": {r: dump_file(r, d, digest) for r, d in files.items()},
    }


def main(argv: list[str]) -> int:
    out, fixtures = Path(argv[0]), Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, make in projects(fixtures).items():
        doc = dump_project(make, DIGESTS.get(name, "sha256"))
        (out / f"{name}.json").write_text(
            json.dumps(doc, indent=None, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        print(name, len(doc["files"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
