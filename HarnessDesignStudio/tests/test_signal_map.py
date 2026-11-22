# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The two settings of 4.4.0 (design `docs/ait/DESIGN_4.4_NAMES_PORTS.md`, sections 5.1 to 5.4, 8
and 11, owner questions N1, N6 and N7): the project's signal map `naming.signal_map` and the flag
`naming.far_device_names`, both keys of `config/naming.json`, empty or off by default (D-11).

The check of a map with the text of `config_invalid`; `signal_map.apply` on whole names, prefix and
suffix ports and names that read in two ways; `signal_map.read_file` on the template
`signal-map.csv`, a JSON object and bad files, against a word-for-word copy of the reader of 4.3.0
(`cli/data._signal_map_file`), so that `import-netlist --signal-map` reads every file as before;
`config --signal-map FILE` and `none`; `config --far-device-names on` and `off` (which takes the key
out); `settings --set` of both; the map is not an input of generation, the flag is; a project of
4.3.0 with both keys loads, saves and keeps them; no example, template or new project has either."""

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_design_studio.cli.main import main
from harness_design_studio.core import configcheck, signal_map, templates
from harness_design_studio.core import settings as registry
from harness_design_studio.core.assumptions import ASSUMPTIONS
from harness_design_studio.core.commands import History
from harness_design_studio.core.drc import run as run_drc
from harness_design_studio.core.generation_status import (
    NOT_READ_BY_GENERATION,
    generation_status,
    input_hash,
)
from harness_design_studio.core.imports import ImportError_, read_table
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import ConfigFile, Project
from harness_design_studio.core.model.project import SCHEMA_VERSION
from harness_design_studio.core.ports import read_signal
from harness_design_studio.core.samples import mini3
from harness_design_studio.core.vcs.hashing import content_hash
from harness_design_studio.resources import examples_path
from tests.helpers import copy_project, edit_json

TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "src/harness_design_studio/resources/examples/templates/signal-map.csv"
)
NETLIST = Path(__file__).parent / "fixtures" / "kicad" / "unit.net.xml"
WHY = (
    "must be a table of a team's signal name to the signal name of an interface type, each 1 to "
    "200 characters, no name mapped to itself and no signal name that is also a team name"
)
TEXT = f"config/naming.json: signal_map {WHY}."
FAR_TEXT = "config/naming.json: far_device_names must be true or false."
MAP = {"TXP": "TX+", "TXN": "TX-", "RXP": "RX+", "RXN": "RX-", "CAN_H": "CANH"}


def _with(p: Project, key: str, value: object) -> Project:
    old = p.config.get("naming")
    base = dict(old.values) if old is not None else {}
    p.config["naming"] = ConfigFile(name="naming", placeholder=False, values={**base, key: value})
    return p


def _issues(p: Project, key: str) -> list[str]:
    return [i.message for i in configcheck.validate(p) if i.object_id == f"naming.{key}"]


@pytest.fixture
def flat(tmp_path: Path) -> Project:
    return templates.create_project(tmp_path / "flat", "flatsat")


# ---- the check of a map (5.1) -------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [None, {}, {"TXP": "TX+"}, MAP, {"a" * 200: "b" * 200}, {f"T{n}": "TX+" for n in range(1000)},
     {"TX P": "TX+", "rx": "RX+"}],
    ids=["none", "empty", "one", "five", "long-200", "1000", "space-and-case"],
)  # fmt: skip
def test_accepted_maps(flat: Project, value: object) -> None:
    assert signal_map.check(value) is None
    assert _issues(_with(flat, "signal_map", value), "signal_map") == []


@pytest.mark.parametrize(
    "value",
    [[["TXP", "TX+"]], "TXP=TX+", 1, True, {"TXP": 1}, {"TXP": None}, {"TXP": ""}, {"": "TX+"},
     {"TXP": "x" * 201}, {"x" * 201: "TX+"}, {"TXP": "TXP"}, {"A": "B", "B": "C"},
     {f"T{n}": "TX+" for n in range(1001)}, {"TXP": "TX\u2028+"}, {"TXP": "TX\x00"}, {"TXP": ["TX+"]}],
    ids=["list", "text", "number", "bool", "int-value", "null-value", "empty-value", "empty-key",
         "value-201", "key-201", "to-itself", "chain", "1001", "line-sep", "control", "nested"],
)  # fmt: skip
def test_refused_maps_say_why(flat: Project, value: object) -> None:
    assert signal_map.check(value) == WHY
    _with(flat, "signal_map", value)
    assert _issues(flat, "signal_map") == [TEXT]
    issue = next(i for i in configcheck.validate(flat) if i.object_id == "naming.signal_map")
    assert (issue.severity, issue.code, issue.location) == ("error", "config_invalid", "config/naming.json")  # fmt: skip
    # a refused map is no map for the importers, and config-invalid says why
    assert signal_map.table(flat) == {}
    assert any(f.rule == "config-invalid" and f.title == TEXT for f in run_drc(flat))


def test_the_table_in_force(flat: Project) -> None:
    assert signal_map.table(flat) == {}
    assert signal_map.table(_with(flat, "signal_map", MAP)) == MAP
    assert signal_map.table(_with(flat, "signal_map", None)) == {}


@pytest.mark.parametrize(
    ("value", "ok"),
    [(None, True), (True, True), (False, True), ("true", False), (1, False), ([True], False)],
    ids=["none", "true", "false", "text", "one", "list"],
)
def test_the_flag_is_true_or_false(flat: Project, value: object, ok: bool) -> None:
    assert _issues(_with(flat, "far_device_names", value), "far_device_names") == (
        [] if ok else [FAR_TEXT]
    )


# ---- apply (5.2) ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "stored"),
    [
        ("TXP", "TX+"),
        ("CAN_H", "CANH"),
        ("TTC1_TXP", "TTC1_TX+"),
        ("TXP.TTC1", "TX+.TTC1"),
        ("TTC1-RXN", "TTC1-RX-"),
        ("RS422_2_RXP", "RS422_2_RX+"),
        ("TTC1_CAN_H", "TTC1_CANH"),
        ("TX+", "TX+"),
        ("TTC1_TX+", "TTC1_TX+"),
        ("txp", "txp"),
        ("TXPX", "TXPX"),
        ("TTC1TXP", "TTC1TXP"),
        ("_TXP", "_TXP"),
        ("PPS", "PPS"),
    ],
    ids=["whole", "whole-us", "prefix", "suffix", "dash", "port-num", "key-us", "type-name",
         "type-in-port", "case", "longer", "no-sep", "empty-port", "other"],
)  # fmt: skip
def test_apply_renames_whole_names_and_inside_a_port(name: str, stored: str) -> None:
    m = signal_map.apply(name, MAP)
    assert (m.read, m.stored, m.renamed, m.ambiguous) == (name, stored, stored != name, False)


def test_a_name_that_reads_in_two_ways_is_not_renamed() -> None:
    m = signal_map.apply("TXP_RXN", MAP)
    assert (m.stored, m.renamed, m.ambiguous, m.keys) == ("TXP_RXN", False, True, ("TXP", "RXN"))
    assert m.warning("OBC1-J01 pin 9") == (
        "TXP_RXN on OBC1-J01 pin 9 can be read as TXP or RXN of the signal map, so it is not renamed."
    )
    same = signal_map.apply("TXP_TXP", MAP)
    assert same.ambiguous and not same.renamed
    assert same.warning("OBC1-J01 pin 2") == (
        "TXP_TXP on OBC1-J01 pin 2 can be read as TXP of the signal map in two ways, so it is not "
        "renamed."
    )


@settings(max_examples=300, deadline=None)
@given(st.text(alphabet="TXPRN12_.-+", max_size=12))
def test_no_map_gives_every_name_as_it_came(name: str) -> None:
    m = signal_map.apply(name, {})
    assert (m.read, m.stored, m.renamed, m.ambiguous) == (name, name, False, False)


@settings(max_examples=300, deadline=None)
@given(st.text(alphabet="TXPRN12_.-+", max_size=12))
def test_apply_follows_the_rule_of_ports(name: str) -> None:
    """A name is renamed when it is a team name, or reads as exactly one team name in a port, and
    then the port and the separator are kept; else it comes back as it came."""
    m = signal_map.apply(name, MAP)
    readings = [r for r in read_signal(name, MAP) if r.form != "bare"]
    if name in MAP:
        assert m.stored == MAP[name]
    elif len(readings) == 1:
        r = readings[0]
        side = (r.port, r.separator, MAP[r.signal])
        assert m.stored == "".join(side if r.form == "prefix" else side[::-1])
    else:
        assert m.stored == name and m.ambiguous == (len(readings) > 1)


# ---- read_file: the reader of 4.3.0, moved (5.4) ----------------------------------------------


def _signal_map_file_430(path: Path) -> dict[str, str]:
    """`cli/data._signal_map_file` of 4.3.0, word for word (but `read_table_raw`, which was
    `read_table`). Not to be edited: `signal_map.read_file` must read every file as it did."""
    import json

    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in raw.items()
            ):
                raise ImportError_("The signal map must be a JSON object of text to text.")
            return dict(raw)
        rows = read_table(path)
    except (OSError, ValueError, RecursionError) as exc:
        raise ImportError_(f"The signal map could not be read ({exc}).") from exc
    if rows and rows[0][0].strip().lower() in ("net", "name", "kicad", "from", "net name"):
        rows = rows[1:]
    return {
        r[0].strip(): r[1].strip() for r in rows if len(r) >= 2 and r[0].strip() and r[1].strip()
    }


FILES = {
    "map.json": '{"TXP": "TX+", "28V": "PWR"}',
    "list.json": "[1, 2]",
    "numbers.json": '{"TXP": 1}',
    "broken.json": '{"TXP": ',
    "plain.csv": "TXP,TX+\nRXN,RX-\n",
    "heading.csv": "Net Name,Signal\nTXP,TX+\n",
    "from.csv": "from,to\n CAN_H , CANH \n",
    "kicad.csv": "kicad,signal\nTXP,TX+\n,RX+\nRXN,\nONE\n",
    "semi.csv": "net;signal\nTXP;TX+\n",
    "tab.tsv": "net\tsignal\nTXP\tTX+\n",
    "twice.csv": "TXP,TX+\nTXP,TX-\n",
    "empty.csv": "",
    "only-heading.csv": "net,signal\n",
}


@pytest.mark.parametrize("name", sorted(FILES), ids=sorted(FILES))
def test_read_file_reads_every_file_as_the_reader_of_4_3_0(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    path.write_text(FILES[name], encoding="utf-8")
    try:
        before: object = _signal_map_file_430(path)
    except ImportError_ as exc:
        before = ("error", str(exc))
    try:
        now: object = signal_map.read_file(path)
    except ImportError_ as exc:
        now = ("error", str(exc))
    assert now == before


def test_read_file_on_the_template_and_a_missing_file(tmp_path: Path) -> None:
    assert signal_map.read_file(TEMPLATE) == _signal_map_file_430(TEMPLATE) == {
        "CAN_H": "CANH", "CAN_L": "CANL", "TXP": "TX+", "TXN": "TX-", "RXP": "RX+", "RXN": "RX-",
    }  # fmt: skip
    assert signal_map.check(signal_map.read_file(TEMPLATE)) is None
    for missing in (tmp_path / "missing.csv", tmp_path / "missing.json"):
        with pytest.raises(ImportError_) as now:
            signal_map.read_file(missing)
        with pytest.raises(ImportError_) as before:
            _signal_map_file_430(missing)
        assert str(now.value) == str(before.value)


def _netlist_run(folder: Path, smap: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, dict[str, str | None]]:  # fmt: skip
    save_project(mini3(), folder)
    args = ["import-netlist", str(folder), str(NETLIST), "--unit", "OBC", "--ref", "J2"]
    capsys.readouterr()
    code = main([*args, "--part", "J2=EX-DSUB-9-F", *smap])
    out = capsys.readouterr().out.replace(str(folder), "DIR")
    pins = load_project(folder).project.connectors.get("OBC-J2")
    return code, out, {x.id: x.signal for x in (pins.pins if pins else [])}


def test_import_netlist_signal_map_file_reads_as_before(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`import-netlist --signal-map FILE` through the moved reader gives what the same pairs on the
    command line give, as in 4.3.0; a bad file is refused with its text and exit 2."""
    pairs = _netlist_run(tmp_path / "a", ["--signal-map", "28V=PWR", "--signal-map", "GND=RTN"], capsys)  # fmt: skip
    for name, text in (("m.json", '{"28V": "PWR", "GND": "RTN"}'), ("m.csv", "net,signal\n28V,PWR\nGND,RTN\n")):  # fmt: skip
        f = tmp_path / name
        f.write_text(text, encoding="utf-8")
        got = _netlist_run(tmp_path / name.replace(".", "-"), ["--signal-map", str(f)], capsys)
        assert got == pairs and got[0] == 0
        assert {k: got[2][k] for k in ("1", "2", "3")} == {"1": "PWR", "2": "RTN", "3": "RTN"}
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2]", encoding="utf-8")
    save_project(mini3(), tmp_path / "b")
    capsys.readouterr()
    assert main(["import-netlist", str(tmp_path / "b"), str(NETLIST), "--unit", "OBC", "--signal-map", str(bad)]) == 2  # fmt: skip
    assert "error: The signal map must be a JSON object of text to text." in capsys.readouterr().err


# ---- the settings (8.1) ---------------------------------------------------------------------------


def test_the_two_settings_are_registered_and_not_on_the_hand_over_list(flat: Project) -> None:
    far = registry.setting("naming", "far_device_names")
    assert far is not None and (far.kind, far.default, far.assumption) == ("flag", False, "A-FAR-DEVICE")  # fmt: skip
    assert far.label == "Signal names name the far device" and far.range == "true or false"
    smap = registry.setting("naming", "signal_map")
    assert smap is not None and (smap.kind, smap.default, smap.assumption) == ("table", None, "")
    assert smap.label == "The team's signal names" and smap.range == signal_map.RANGE
    assert registry.effective(flat, "naming", "far_device_names").origin == "default"
    assert registry.effective(flat, "naming", "signal_map").origin == "unset"
    for key in ("far_device_names", "signal_map"):
        assert configcheck.need_for("naming", key) is None
        assert ("naming", key) not in configcheck.FIELD_INFO
    before = configcheck.report(flat)
    _with(_with(flat, "signal_map", MAP), "far_device_names", True)
    assert configcheck.report(flat) == before  # `config` says the same


def test_the_assumption_a_far_device() -> None:
    a = ASSUMPTIONS["A-FAR-DEVICE"]
    assert a.kind == "setting" and "naming.far_device_names" in a.text
    assert (
        a.title == "A pin name that names a device belongs to that device's interface or connection"
    )
    assert "the longest ID wins, and a name that names two devices names neither" in a.text
    assert a.where.startswith("core/device_names.py")


def test_the_map_is_not_read_by_generation_and_the_flag_is(flat: Project) -> None:
    assert "signal_map" in NOT_READ_BY_GENERATION["naming"]
    assert "far_device_names" not in NOT_READ_BY_GENERATION["naming"]
    assert generation_status(flat) == "current"
    inputs, content = input_hash(flat), content_hash(flat)
    History(flat).execute("Set the signal map", configcheck.plan_set_signal_map(flat, MAP).ops)
    assert input_hash(flat) == inputs and generation_status(flat) == "current"
    assert content_hash(flat) != content  # the outputs are out of date until the export
    History(flat).execute("On", configcheck.plan_set_far_device_names(flat, "on").ops)
    assert input_hash(flat) != inputs and generation_status(flat) == "stale"
    History(flat).execute("Off", configcheck.plan_set_far_device_names(flat, "off").ops)
    assert input_hash(flat) == inputs and generation_status(flat) == "current"


# ---- plan_set_signal_map, plan_set_far_device_names (5.4, 8.2) ----------------------------------


def test_plan_set_signal_map_is_one_step_and_none_takes_the_key_out(flat: Project) -> None:
    before = flat.config["naming"]
    plan = configcheck.plan_set_signal_map(flat, MAP)
    assert plan.ok and len(plan.ops) == 1 and plan.value == MAP
    history = History(flat)
    history.execute("Set the signal map", plan.ops)
    assert flat.config["naming"].values["signal_map"] == MAP
    assert {k: v for k, v in flat.config["naming"].values.items() if k != "signal_map"} == dict(before.values)  # fmt: skip
    assert configcheck.plan_set_signal_map(flat, dict(MAP)).ops == []
    history.undo()
    assert flat.config["naming"] == before
    history.redo()
    gone = configcheck.plan_set_signal_map(flat, None)
    assert gone.ok and gone.value is None
    history.execute("Take the signal map out", gone.ops)
    assert flat.config["naming"] == before
    assert configcheck.plan_set_signal_map(flat, {}).ops == []


def test_plan_set_signal_map_refuses_a_table_with_the_text_of_the_check(flat: Project) -> None:
    plan = configcheck.plan_set_signal_map(flat, {"A": "B", "B": "C"})
    assert not plan.ok and plan.error == TEXT and plan.ops == []
    flat.read_only = True
    assert "read-only" in (configcheck.plan_set_signal_map(flat, MAP).error or "")
    assert "read-only" in (configcheck.plan_set_far_device_names(flat, "on").error or "")


def test_plan_set_far_device_names_on_writes_true_and_off_takes_it_out(flat: Project) -> None:
    before = flat.config["naming"]
    on = configcheck.plan_set_far_device_names(flat, "on")
    assert on.ok and on.value is True and len(on.ops) == 1
    history = History(flat)
    history.execute("On", on.ops)
    assert flat.config["naming"].values["far_device_names"] is True
    assert configcheck.plan_set_far_device_names(flat, True).ops == []
    off = configcheck.plan_set_far_device_names(flat, "no")
    assert off.ok and off.value is False
    history.execute("Off", off.ops)
    assert flat.config["naming"] == before
    assert configcheck.plan_set_far_device_names(flat, False).ops == []
    bad = configcheck.plan_set_far_device_names(flat, "maybe")
    assert not bad.ok and bad.error == "Signal names name the far device: say on or off."


# ---- config DIR --signal-map FILE, --far-device-names on|off -----------------------------------


def test_config_signal_map_reads_the_template_and_none_takes_it_out(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "flat"
    templates.create_project(folder, "flatsat")
    naming = folder / "config" / "naming.json"
    before = naming.read_bytes()
    code_before = main(["config", str(folder)])
    text_before = capsys.readouterr().out
    code = main(["config", str(folder), "--signal-map", str(TEMPLATE)])
    out = capsys.readouterr().out
    assert code == code_before  # the exit code of `config` is the hand-over list's
    assert out.startswith("Signal map: 6 name(s) in config/naming.json.\n")
    assert out.endswith(text_before)
    stored = json.loads(naming.read_text(encoding="utf-8"))["values"]["signal_map"]
    assert stored == signal_map.read_file(TEMPLATE)
    assert signal_map.table(load_project(folder).project) == stored
    # `config DIR` says nothing of the key: its text stays what it was
    assert main(["config", str(folder)]) == code_before
    assert capsys.readouterr().out == text_before
    assert main(["config", str(folder), "--signal-map", "none", "--json"]) == code_before
    doc = json.loads(capsys.readouterr().out)
    assert doc["changes"] == ["Signal map: none (the key is taken out of config/naming.json)."]
    assert naming.read_bytes() == before


@pytest.mark.parametrize(
    ("name", "content", "why"),
    [
        ("chain.csv", "A,B\nB,C\n", TEXT),
        ("self.json", '{"TXP": "TXP"}', TEXT),
        ("long.csv", "TXP," + "x" * 201 + "\n", TEXT),
        ("list.json", "[1, 2]", "The signal map must be a JSON object of text to text."),
        ("broken.json", '{"TXP": ', "The signal map could not be read ("),
        ("heading.csv", "net,signal\n", "has no pair of a team's signal name and a signal name"),
    ],
    ids=["chain", "to-itself", "too-long", "not-object", "broken", "no-pair"],
)
def test_config_signal_map_refuses_a_file_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, content: str, why: str
) -> None:
    folder = tmp_path / "flat"
    templates.create_project(folder, "flatsat")
    naming = folder / "config" / "naming.json"
    before = naming.read_bytes()
    file = tmp_path / name
    file.write_text(content, encoding="utf-8")
    capsys.readouterr()
    assert main(["config", str(folder), "--signal-map", str(file)]) == 1
    err = capsys.readouterr().err
    assert why in err and "Nothing was changed." in err
    assert naming.read_bytes() == before
    assert main(["config", str(folder), "--signal-map", str(tmp_path / "missing.csv")]) == 1
    assert "is not a file" in capsys.readouterr().err


def test_config_far_device_names_on_and_off_gives_the_bytes_back(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "flat"
    templates.create_project(folder, "flatsat")
    naming = folder / "config" / "naming.json"
    before = naming.read_bytes()
    code_before = main(["config", str(folder)])
    text_before = capsys.readouterr().out
    assert main(["config", str(folder), "--far-device-names", "on"]) == code_before
    out = capsys.readouterr().out
    assert out.startswith(
        "Generate reads this setting, so the harness plans are now out of date. Run "
        "`harness-design-studio generate` again, then export again.\n"
        "Signal names name the far device: on (config/naming.json, far_device_names).\n"
    )
    assert json.loads(naming.read_text(encoding="utf-8"))["values"]["far_device_names"] is True
    assert generation_status(load_project(folder).project) == "stale"
    assert main(["config", str(folder)]) == code_before
    assert capsys.readouterr().out == text_before
    assert main(["config", str(folder), "--far-device-names", "on"]) == code_before  # no change
    assert capsys.readouterr().out.startswith("Signal names name the far device: on")
    assert main(["config", str(folder), "--far-device-names", "off"]) == code_before
    assert capsys.readouterr().out.startswith(
        "Signal names name the far device: off (the setting is taken out of config/naming.json).\n"
    )
    assert naming.read_bytes() == before
    assert generation_status(load_project(folder).project) == "current"


def test_config_refuses_both_on_a_read_only_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "flat"
    templates.create_project(folder, "flatsat")
    edit_json(
        folder / "project.json", lambda d: d.__setitem__("schema_version", SCHEMA_VERSION + 1)
    )
    naming = folder / "config" / "naming.json"
    before = naming.read_bytes()
    for option, value in (("--far-device-names", "on"), ("--signal-map", str(TEMPLATE))):
        capsys.readouterr()
        assert main(["config", str(folder), option, value]) == 2
        assert "read-only" in capsys.readouterr().err
    assert naming.read_bytes() == before


# ---- settings --set (section 2.6) -----------------------------------------------------------------


def test_settings_set_takes_both_keys(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """4.3.0 refused `settings --set naming.far_device_names=true` with exit 2: the key was no
    setting of the registry. Both are settings now, and a bad value is refused by the check."""
    folder = tmp_path / "flat"
    templates.create_project(folder, "flatsat")
    naming = folder / "config" / "naming.json"
    assert main(["settings", str(folder), "--set", "naming.far_device_names=true"]) == 0
    assert main(["settings", str(folder), "--set", 'naming.signal_map={"TXP": "TX+"}']) == 0
    values = json.loads(naming.read_text(encoding="utf-8"))["values"]
    assert values["far_device_names"] is True and values["signal_map"] == {"TXP": "TX+"}
    before = naming.read_bytes()
    for item, text in (
        ('naming.signal_map={"TXP": "TXP"}', TEXT),
        ("naming.far_device_names=sometimes", FAR_TEXT),
    ):
        capsys.readouterr()
        assert main(["settings", str(folder), "--set", item]) == 1
        err = capsys.readouterr().err
        assert text in err and "Nothing was changed." in err and naming.read_bytes() == before
    capsys.readouterr()
    assert main(["settings", str(folder)]) == 0
    out = capsys.readouterr().out
    assert "  far_device_names = yes   [set by the project]" in out
    assert "  signal_map = TXP: TX+   [set by the project]" in out
    assert "A-FAR-DEVICE" in out


# ---- a project of 4.3.0 with the keys (2.6), and none in the examples (D-11) ---------------------


def test_a_project_of_4_3_with_both_keys_loads_saves_and_keeps_them(tmp_path: Path) -> None:
    root = examples_path()
    assert root is not None
    folder = copy_project(root / "projects" / "flatsat", tmp_path / "flat")
    plain = load_project(folder).project
    findings = [f.id for f in run_drc(plain)]
    naming = folder / "config" / "naming.json"

    def put(d: dict[str, dict[str, object]]) -> None:
        d["values"]["far_device_names"] = True
        d["values"]["signal_map"] = MAP

    edit_json(naming, put)
    p = load_project(folder).project
    assert p.meta.schema_version == SCHEMA_VERSION == 4
    assert configcheck.validate(p) == configcheck.validate(plain)
    changed = [f.id for f in run_drc(p) if not f.id.startswith("verify-mismatch.outputs_outdated")]
    assert changed == [f for f in findings if not f.startswith("verify-mismatch.outputs_outdated")]
    assert signal_map.table(p) == MAP
    save_project(p, folder)
    values = json.loads(naming.read_text(encoding="utf-8"))["values"]
    assert values["signal_map"] == MAP and values["far_device_names"] is True
    # a change of another key of the same file keeps them
    assert main(["settings", str(folder), "--set", "naming.release_distinct_roles=true"]) == 0
    values = json.loads(naming.read_text(encoding="utf-8"))["values"]
    assert values["signal_map"] == MAP and values["far_device_names"] is True


def test_no_example_template_or_new_project_has_either_key(tmp_path: Path) -> None:
    for name in ("blank", "first-steps", "minimal-satellite", "small-satellite", "flatsat"):
        p = templates.create_project(tmp_path / name, name)
        values = (p.config.get("naming") or ConfigFile(name="naming", placeholder=False, values={})).values  # fmt: skip
        assert "far_device_names" not in values and "signal_map" not in values, name
        assert signal_map.table(p) == {}
        assert registry.effective(p, "naming", "far_device_names").value is False
