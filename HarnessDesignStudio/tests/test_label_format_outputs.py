# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The label formats in the written outputs (`model.label_format`, D-198, since 1.15.0).

From 1.15.0 to 4.0.0 the independent verifier knew only the standard text of a label, so `export` of a
project in the format `compact`, `descriptive` or `custom` failed its own self-check (`out_labels`,
`out_build` of the Labels sheet) and wrote nothing. Here: `export` of an example passes for every
format, a template using every field included; the verifier reads the labels of a project with
loose ends and splices as the tables write them, for random templates; it still refuses a wrong
text in every format (also the standard text where another format is in force); and its own copy
of the template rules (`verify_labels._LABEL_*`, `_label_template_usable`, `_fill_label`, moved out of
`verify.py` for 4.1.0) is the core's (`core/label_format.py`), which neither `verify.py` nor
`verify_labels.py` imports."""

import io
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness_design_studio.cli.main import main as cli_main
from harness_design_studio.core import edit, label_format
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import ConfigFile, Project, evolve
from harness_design_studio.core.outputs import tables
from harness_design_studio.core.outputs import verify as vf
from harness_design_studio.core.outputs import verify_labels as vl
from harness_design_studio.core.outputs.build import DEFAULT_FOLDER, build_outputs
from harness_design_studio.core.outputs.stamp import parse_csv
from harness_design_studio.core.outputs.xlsx_env import load_workbook
from harness_design_studio.core.samples import mini3
from harness_design_studio.resources import examples_path
from tests.helpers import copy_project
from tests.loose_support import generated_loose
from tests.splice_support import splice_project
from tests.static_scan import imported_names
from tests.test_outputs import edit_csv

SRC = Path(__file__).resolve().parents[1] / "src"

# A template of each kind that uses every one of its fields, and the braces.
WIRE_TEMPLATE = "{harness}/{wire} {end}: {name} [{signal}] {interface} <{emc}> {from} > {to} {{x}}"
CONNECTOR_TEMPLATE = "{harness}:{connector} {name} -> {mates} of {device} {{y}}"

# The settings of `config/model.json` per case: every format, and `custom` with and without templates.
CASES: dict[str, dict[str, str]] = {
    "standard": {},
    "compact": {"label_format": "compact"},
    "descriptive": {"label_format": "descriptive"},
    "custom": {
        "label_format": "custom",
        "label_wire_template": WIRE_TEMPLATE,
        "label_connector_template": CONNECTOR_TEMPLATE,
    },
    "custom-wire-only": {"label_format": "custom", "label_wire_template": WIRE_TEMPLATE},
    "custom-no-template": {"label_format": "custom"},
}
NOT_STANDARD = [k for k in CASES if CASES[k] and k != "custom-no-template"]


def test_every_format_and_every_template_field_is_a_case() -> None:
    assert {v.get("label_format", "standard") for v in CASES.values()} == set(label_format.FORMATS)
    assert label_format.check_template(WIRE_TEMPLATE, label_format.WIRE_FIELDS) is None
    assert label_format.check_template(CONNECTOR_TEMPLATE, label_format.CONNECTOR_FIELDS) is None
    for field in label_format.WIRE_FIELDS:
        assert "{" + field + "}" in WIRE_TEMPLATE, field
    for field in label_format.CONNECTOR_FIELDS:
        assert "{" + field + "}" in CONNECTOR_TEMPLATE, field


def with_model(p: Project, values: dict[str, str]) -> Project:
    """A copy of `p` with `values` in `config/model.json` (the other keys kept)."""
    q = edit.clone_with(p, [])
    old = q.config.get("model")
    keep = dict(old.values) if old is not None else {}
    q.config = {**q.config, "model": ConfigFile(name="model", placeholder=False, values={**keep, **values})}  # fmt: skip
    return q


def labelled_mini3() -> Project:
    """`mini3`, generated, with an EMC class, a wire label, a connector label and a box connector
    label, so that every field of a template has a text somewhere."""
    p = mini3()
    generate_project(p)
    p.interface_types["power_primary"] = evolve(p.interface_types["power_primary"], emc_class="P")
    h = p.harnesses["W001"]
    wires = [evolve(h.wires[0], label="MAIN"), *h.wires[1:]]
    cons = [evolve(h.connectors[0], label="Plug one"), *h.connectors[1:]]
    p.harnesses["W001"] = evolve(h, wires=wires, connectors=cons)
    box = h.connectors[1].mates_with
    assert box is not None
    p.connectors[box] = evolve(p.connectors[box], label="Wheel port")
    return p


@pytest.fixture(scope="module")
def projects(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Project]:
    loose = generated_loose(tmp_path_factory.mktemp("loose") / "loose")
    return {
        "mini3": labelled_mini3(),
        "loose": load_project(loose).project,
        "splices": splice_project(),
    }


# ---- export passes its self-check in every format -------------------------------------------------


@pytest.mark.parametrize("case", list(CASES))
def test_export_of_an_example_passes_its_self_check_in_every_label_format(
    case: str, tmp_path: Path
) -> None:
    root = examples_path()
    assert root is not None
    folder = copy_project(root / "projects" / "minimal-satellite", tmp_path / "p")
    for key, value in CASES[case].items():
        assert cli_main(["settings", str(folder), "--set", f"model.{key}={value!r}".replace("'", '"')]) == 0  # fmt: skip
    assert cli_main(["generate", str(folder)]) == 0
    assert cli_main(["export", str(folder), "--harness-plan"]) == 0, case
    p = load_project(folder).project
    assert label_format.format_of(p) == CASES[case].get("label_format", "standard")
    out = folder / DEFAULT_FOLDER / "harnesses"
    for hid, h in p.harnesses.items():
        written = parse_csv((out / hid / "labels.csv").read_bytes())
        assert written == tables.labels(p, h), hid
        book = load_workbook(io.BytesIO((out / hid / f"{hid}_build.xlsx").read_bytes()))
        sheet = [
            ["" if c is None else str(c) for c in r][1:]
            for r in book["Labels"].iter_rows(values_only=True)
        ]
        assert sheet == tables.labels(p, h), hid
    if case in NOT_STANDARD:  # the format is really in the files
        std = with_model(p, {"label_format": "standard"})
        assert any(tables.labels(p, h) != tables.labels(std, h) for h in p.harnesses.values())


@pytest.mark.parametrize("case", list(CASES))
@pytest.mark.parametrize("name", ["mini3", "loose", "splices"])
def test_the_outputs_pass_the_verifier_in_every_label_format(
    projects: dict[str, Project], name: str, case: str
) -> None:
    p = with_model(projects[name], CASES[case])
    report = vf.verify_outputs(p, build_outputs(p, harness_plan=True).files)
    assert report.ok, [i.message for i in report.errors]


# ---- a wrong text is still refused ---------------------------------------------------------------

H = "harnesses/W001"


def _row(files: dict[str, bytes], kind: str) -> int:
    table = parse_csv(files[f"{H}/labels.csv"])
    return next(n for n, r in enumerate(table) if n and r[1] == kind)


@pytest.mark.parametrize("kind", ["wire", "connector"])
@pytest.mark.parametrize("case", NOT_STANDARD)
def test_a_wrong_label_text_is_refused_in_every_format(
    projects: dict[str, Project], case: str, kind: str
) -> None:
    p = with_model(projects["mini3"], CASES[case])
    built = dict(build_outputs(p).files)
    assert vf.verify_outputs(p, built).ok
    row = _row(built, kind)
    label_id = parse_csv(built[f"{H}/labels.csv"])[row][0]
    std = {
        r[0]: r[2]
        for r in tables.labels(with_model(p, {"label_format": "standard"}), p.harnesses["W001"])[1:]
    }
    mine = {r[0]: r[2] for r in tables.labels(p, p.harnesses["W001"])[1:]}
    wrong = ["ZZZ", mine[label_id] + " "]
    if std[label_id] != mine[label_id]:
        wrong.append(std[label_id])  # the standard text where another format is in force
    for text in wrong:

        def put(t: list[list[str]], s: str = text) -> None:
            t[row][2] = s

        files = dict(built)
        edit_csv(files, f"{H}/labels.csv", put, p)
        codes = {i.code for i in vf.verify_outputs(p, files).errors}
        assert "out_labels" in codes, (case, kind, text)
        files = dict(built)
        rel = f"{H}/W001_build.xlsx"
        book = load_workbook(io.BytesIO(files[rel]))
        sheet = book["Labels"]
        at = next(r for r in range(2, sheet.max_row + 1) if sheet.cell(r, 2).value == label_id)
        sheet.cell(row=at, column=4).value = text
        raw = io.BytesIO()
        book.save(raw)
        files[rel] = raw.getvalue()
        codes = {i.code for i in vf.verify_outputs(p, files).errors}
        assert "out_build" in codes, (case, kind, text)


# ---- the verifier's own copy of the label rules ----------------------------------------------------


@pytest.mark.parametrize("module", ["verify.py", "verify_labels.py"])
def test_the_verifier_does_not_import_the_label_rules_or_the_tables(module: str) -> None:
    names = imported_names(SRC / "harness_design_studio/core/outputs" / module, SRC)
    assert names
    for banned in ("harness_design_studio.core.label_format", "harness_design_studio.core.outputs.tables"):  # fmt: skip
        assert not [n for n in names if n == banned or n.startswith(banned + ".")], banned


def test_the_label_copy_lives_in_verify_labels_and_verify_uses_it() -> None:
    names = imported_names(SRC / "harness_design_studio/core/outputs/verify.py", SRC)
    assert "harness_design_studio.core.outputs.verify_labels._connector_label_text" in names
    assert "harness_design_studio.core.outputs.verify_labels._wire_label_texts" in names
    text = (SRC / "harness_design_studio/core/outputs/verify.py").read_text(encoding="utf-8")
    for name in ("_LABEL_FIELDS =", "def _fill_label(", "def _label_template_usable("):
        assert name not in text, name  # one copy of the label rules in the verifier


def test_the_verifier_s_formats_and_fields_are_the_core_s() -> None:
    assert vl._LABEL_FORMATS == label_format.FORMATS
    assert vl._LABEL_DEFAULT == label_format.DEFAULT_FORMAT
    assert vl._LABEL_FIELDS == {"wire": label_format.WIRE_FIELDS, "connector": label_format.CONNECTOR_FIELDS}  # fmt: skip
    assert vl._LABEL_TEMPLATE_KEYS == label_format.TEMPLATE_KEYS
    assert vl._LABEL_TEMPLATE_MAX == label_format.MAX_TEMPLATE


ALL_FIELDS = sorted({*label_format.WIRE_FIELDS, *label_format.CONNECTOR_FIELDS, "colour", ""})
pieces = st.one_of(
    st.sampled_from(["{" + f + "}" for f in ALL_FIELDS]),
    st.sampled_from(["{{", "}}", "{", "}", " ", "-", "/", ".", "A", "é"]),
    st.text(alphabet="ab {}", max_size=4),
)
templates = st.lists(pieces, max_size=12).map("".join) | st.text(min_size=195, max_size=205)


@settings(max_examples=200, deadline=None)
@given(text=templates, kind=st.sampled_from(["wire", "connector"]))
def test_the_verifier_s_template_rules_are_the_core_s(text: str, kind: str) -> None:
    fields = label_format.WIRE_FIELDS if kind == "wire" else label_format.CONNECTOR_FIELDS
    usable = label_format.check_template(text, fields) is None
    assert vl._label_template_usable(text, kind) == usable
    if usable:
        values = {f: f"<{f}>" for f in fields}
        assert vl._fill_label(text, values) == label_format.fill(text, values)


wire_templates = st.lists(
    st.sampled_from(["{" + f + "}" for f in label_format.WIRE_FIELDS] + ["{{", "}}", " ", "-"]),
    max_size=10,
).map("".join)
connector_templates = st.lists(
    st.sampled_from(["{" + f + "}" for f in label_format.CONNECTOR_FIELDS] + ["{{", "}}", " "]),
    max_size=8,
).map("".join)


@settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    fmt=st.sampled_from([*label_format.FORMATS, "fancy"]),
    wire=st.none() | wire_templates | st.just("{colour}"),
    connector=st.none() | connector_templates,
)
def test_the_verifier_reads_every_label_as_the_tables_write_it(
    projects: dict[str, Project], fmt: str, wire: str | None, connector: str | None
) -> None:
    values = {"label_format": fmt}
    if wire is not None:
        values["label_wire_template"] = wire
    if connector is not None:
        values["label_connector_template"] = connector
    for base in projects.values():
        p = with_model(base, values)
        for h in p.harnesses.values():
            want = {r[0]: r for r in tables.labels(p, h)[1:]}
            got = {r[0]: r for r in vf._label_rows(p, h)}
            assert got == want, h.id
