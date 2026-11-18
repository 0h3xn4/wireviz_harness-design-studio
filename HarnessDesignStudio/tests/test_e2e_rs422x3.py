# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The end-to-end case of 2.1.0 (D-237, REQ-PIN-04, section 6 of `docs/ait/DESIGN_2.1_PORTS.md`),
through the command line wherever a command exists: a blank project; `import-pinout` of an
on-board computer OBC1 whose connector J1 is RS-422 x3 (with a Port column, and with names
`RS422_k_TX+`); three star trackers by `import-pinout`; three interfaces OBC1 -> STRk added in
Guided mode through the core (no command adds an interface), the second and third by tier 2 of the
choice because J1 is OBC1's only connector; then `generate`, `export`, `verify --outputs`, `drc`
and `explain`.

What it shows: each interface gets the pins of one port, port k for IF-k; the verifier finds no
error; the box pinouts list `RS422_k_TX+` with its interface; `explain` of a pin gives the port;
a second Generate changes no file; two exports are byte-identical. With the default segmentation
`per_connector_pair` each interface is its own harness with a plug on J1 (the warning
`box_connector_shared`; `per_connector_group`, 2.3.0, joins them: `tests/test_branch_segmentation.py`); with `per_zone_pair` and the star
trackers in one zone Generate makes one harness with one plug on J1 and three on the star trackers,
and no such warning. A port locked by a person (`devices.ops_assign_port`) is kept by Generate.
Repeated bare names (`TX+` three times) keep the assignment of 2.0.1 and give `pin_port_unknown`.
Example data only."""

from pathlib import Path

import pytest

from harness_design_studio.cli.main import main as cli_main
from harness_design_studio.core import devices, edit
from harness_design_studio.core.commands import History
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import Project

RS422 = ("TX+", "TX-", "RX+", "RX-")
J1 = "OBC1-J01"  # the import numbers connector J1 of OBC1 as OBC1-J01


def with_port_column() -> str:
    """J1 = RS-422 x3: a Port column and the bare signal names."""
    rows = ["Connector,Pin,Port,Signal,Mode"]
    for k in range(3):
        rows += [f"J1,{4 * k + n + 1},RS422_{k + 1},{s},fixed" for n, s in enumerate(RS422)]
    return "\n".join(rows) + "\n"


def with_port_names() -> str:
    """J1 = RS-422 x3: no Port column, the port written into the signal name."""
    rows = ["Connector,Pin,Signal,Mode"]
    for k in range(3):
        rows += [f"J1,{4 * k + n + 1},RS422_{k + 1}_{s},fixed" for n, s in enumerate(RS422)]
    return "\n".join(rows) + "\n"


def with_bare_names() -> str:
    """J1 with TX+, TX-, RX+, RX- three times: nothing says which pins form one port."""
    rows = ["Connector,Pin,Signal,Mode"]
    for k in range(3):
        rows += [f"J1,{4 * k + n + 1},{s},fixed" for n, s in enumerate(RS422)]
    return "\n".join(rows) + "\n"


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str]:
    """One command; its exit code and everything it printed."""
    code = cli_main(list(args))
    seen = capsys.readouterr()
    return code, seen.out + seen.err


def files(folder: Path) -> dict[str, bytes]:
    return {
        f.relative_to(folder).as_posix(): f.read_bytes()
        for f in sorted(folder.rglob("*"))
        if f.is_file()
    }


def imported(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    obc_csv: str,
    *,
    mode: str | None = "per_connector_pair",
) -> Path:
    """A blank project with OBC1 (J1 from `obc_csv`) and the star trackers STR1-STR3, each with
    one RS-422 connector, all by the command line. `mode`: the segmentation of the project; the
    case of 2.1.0 is a project in `per_connector_pair`, as every project made before 2.4.0 (a new
    blank project starts in `per_connector_group` since then, D-247); None keeps the new one."""
    proj = tmp_path / "proj"
    assert run(capsys, "new", str(proj), "--template", "blank")[0] == 0
    if mode is not None:
        code, out = run(capsys, "settings", str(proj), "--set", f'segmentation.mode="{mode}"')
        assert code == 0, out
    obc = tmp_path / "obc1.csv"
    obc.write_text(obc_csv, encoding="utf-8")
    code, out = run(
        capsys, "import-pinout", str(proj), str(obc), "--device", "OBC1",
        "--new-device", "On-board computer", "--subsystem", "avionics",
        "--default-part", "EX-MICROD-25-F", "--gender", "female",
    )  # fmt: skip
    assert code == 0, out
    assert f"{J1}: OK added (12 pin(s))" in out
    star = tmp_path / "str.csv"
    star.write_text(
        "Pin,Signal,Mode\n" + "".join(f"{n + 1},{s},fixed\n" for n, s in enumerate(RS422)),
        encoding="utf-8",
    )
    for k in (1, 2, 3):
        code, out = run(
            capsys, "import-pinout", str(proj), str(star), "--device", f"STR{k}",
            "--new-device", f"Star tracker {k}", "--subsystem", "aocs",
            "--default-part", "EX-MICROD-9-M", "--gender", "male",
        )  # fmt: skip
        assert code == 0, out
    return proj


def add_interfaces(proj: Path, *, guided: bool = True) -> Project:
    """IF-001 to IF-003, OBC1 -> STRk, through the project's history, and save. Guided: the tool
    chooses every connector; else (Expert) the ends are given."""
    p = load_project(proj).project
    h = History(p)
    for k in (1, 2, 3):
        if guided and k > 1:
            # J1 already carries an interface, so only tier 2 of the choice can find it
            assert edit.free_connectors(p, "OBC1", "rs422") == []
            assert [c.id for c in edit.shared_connectors(p, "OBC1", "rs422")] == [J1]
        ends = () if guided else (J1, f"STR{k}-J01")
        ops, iid = edit.ops_add_interface(p, "rs422", "OBC1", f"STR{k}", *ends)
        h.execute(f"Add {iid}", ops)
        assert iid == f"IF-00{k}"
        assert [(e.connector_id, e.auto) for e in p.interfaces[iid].endpoints] == [
            (J1, guided),
            (f"STR{k}-J01", guided),
        ]
    save_project(p, proj)
    return p


def ports_used(proj: Path) -> dict[str, set[str]]:
    """Interface -> the ports of the OBC1 pins it holds, read from the saved project."""
    p = load_project(proj).project
    out: dict[str, set[str]] = {}
    for pin in p.connectors[J1].pins:
        if pin.interface_id and pin.signal:
            out.setdefault(pin.interface_id, set()).add(pin.signal.rsplit("_", 1)[0])
    return out


# ---- the case of section 6 ------------------------------------------------------------------


@pytest.mark.parametrize(
    "obc_csv", [with_port_column(), with_port_names()], ids=["column", "names"]
)
def test_rs422x3_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], obc_csv: str
) -> None:
    proj = imported(tmp_path, capsys, obc_csv)
    pins = load_project(proj).project.connectors[J1].pins
    assert [x.signal for x in pins] == [f"RS422_{k}_{s}" for k in (1, 2, 3) for s in RS422]
    add_interfaces(proj)

    code, out = run(capsys, "generate", str(proj))
    assert code == 0, out
    assert "3 added" in out
    # per_connector_pair (a project made before 2.4.0): three harnesses, each with a plug on J1 (per_connector_group joins them)
    assert "[box_connector_shared] OBC1-J01 has more than one cable plug on it" in out
    assert ports_used(proj) == {f"IF-00{k}": {f"RS422_{k}"} for k in (1, 2, 3)}

    code, out = run(capsys, "export", str(proj))
    assert code == 0, out
    first = files(proj / "outputs")
    code, out = run(capsys, "verify", str(proj), "--outputs")
    assert code == 0, out
    assert "3 interfaces and 12 wires checked: 0 error(s)" in out
    code, out = run(capsys, "drc", str(proj))
    assert code == 0, out
    assert "Open: 0 error(s)" in out
    assert f"The device connector {J1} has 3 cable plugs on it" in out  # model-inconsistent

    pinouts = (proj / "outputs" / "system" / "box_pinouts.csv").read_text(encoding="utf-8")
    for k in (1, 2, 3):
        for n, s in enumerate(RS422):
            pin = 4 * (k - 1) + n + 1
            assert f"{J1},box,,EX-MICROD-25-F,{pin},RS422_{k}_{s},IF-00{k}," in pinouts

    code, out = run(capsys, "explain", str(proj), f"{J1}.5")
    assert code == 0, out
    assert f"Port of the pin: RS422_2_TX+ is the TX+ of port RS422_2 of {J1}" in out
    assert f"TX+ of IF-002 uses pin 5, the TX+ of port RS422_2 of {J1}" in out
    # the connector: one step names the three interfaces, and the equation both tiers (2.1.1)
    code, out = run(capsys, "explain", str(proj), J1)
    assert code == 0, out
    assert out.count("Connectors of OBC1 that carry rs422") == 1
    assert "Connectors of OBC1 that carry rs422, for IF-001, IF-002, IF-003: in ID order" in out
    assert "when none is free, the first connector of the device with a fixed pinout" in out

    # a second Generate changes no file of the project
    before = files(proj)
    code, out = run(capsys, "generate", str(proj))
    assert code == 0, out
    assert "0 added, 0 changed, 3 unchanged" in out
    assert files(proj) == before

    # two exports are byte-identical
    assert run(capsys, "export", str(proj))[0] == 0
    assert files(proj / "outputs") == first


# ---- variants -------------------------------------------------------------------------------


def test_per_zone_pair_makes_one_harness_with_one_plug_on_j1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With the star trackers in one zone and `segmentation.mode` = `per_zone_pair`, the three
    interfaces form one group: one harness W001 with one plug on J1 and one on each star tracker,
    so neither `box_connector_shared` nor the finding of three plugs appears."""
    proj = imported(tmp_path, capsys, with_port_column())
    p = load_project(proj).project
    star_zone = p.units["STR1"].zone
    assert star_zone != p.units["OBC1"].zone
    h = History(p)
    for k in (2, 3):  # every star tracker in the zone of STR1
        x = p.placements["STR1"].x
        h.execute("Move", edit.ops_move_unit(p, f"STR{k}", x, p.placements[f"STR{k}"].y + 400))
    assert {p.units[f"STR{k}"].zone for k in (1, 2, 3)} == {star_zone}
    save_project(p, proj)
    add_interfaces(proj)
    code, out = run(capsys, "settings", str(proj), "--set", 'segmentation.mode="per_zone_pair"')
    assert code == 0, out

    code, out = run(capsys, "generate", str(proj))
    assert code == 0, out
    assert "1 added" in out and "box_connector_shared" not in out
    q = load_project(proj).project
    assert list(q.harnesses) == ["W001"]
    assert [(c.id, c.mates_with) for c in q.harnesses["W001"].connectors] == [
        ("W001-P1", J1),
        ("W001-P2", "STR1-J01"),
        ("W001-P3", "STR2-J01"),
        ("W001-P4", "STR3-J01"),
    ]
    assert ports_used(proj) == {f"IF-00{k}": {f"RS422_{k}"} for k in (1, 2, 3)}
    assert run(capsys, "export", str(proj))[0] == 0
    code, out = run(capsys, "verify", str(proj), "--outputs")
    assert code == 0 and "0 error(s)" in out, out
    code, out = run(capsys, "drc", str(proj))
    assert code == 0 and "Open: 0 error(s)" in out, out
    assert "cable plugs on it" not in out


def test_a_port_locked_by_a_person_is_kept_by_generate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """IF-003 locked on RS422_1 (`devices.ops_assign_port`, one undo step): Generate keeps it
    there and gives IF-001 and IF-002 the next free ports in name order."""
    proj = imported(tmp_path, capsys, with_port_column())
    p = add_interfaces(proj)
    History(p).execute("Assign port", devices.ops_assign_port(p, J1, "RS422_1", "IF-003"))
    save_project(p, proj)
    code, out = run(capsys, "generate", str(proj))
    assert code == 0, out
    assert "4 locked pin(s) kept" in out
    assert ports_used(proj) == {
        "IF-001": {"RS422_2"},
        "IF-002": {"RS422_3"},
        "IF-003": {"RS422_1"},
    }
    q = load_project(proj).project
    assert [(x.id, x.locked) for x in q.connectors[J1].pins if x.interface_id == "IF-003"] == [
        (str(n), True) for n in (1, 2, 3, 4)
    ]
    end = devices.end_port(q, "IF-003", J1)
    assert end is not None and (end.port, end.how) == ("RS422_1", "locked")
    assert run(capsys, "export", str(proj))[0] == 0
    code, out = run(capsys, "verify", str(proj), "--outputs")
    assert code == 0 and "0 error(s)" in out, out


def test_repeated_bare_names_keep_201_and_warn_pin_port_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """TX+ three times and no ports: Guided does not count them as three ports, so the second
    and third interfaces are put on J1 by hand (Expert); Generate keeps the assignment of 2.0.1
    and says that it cannot tell which pins form one port."""
    proj = imported(tmp_path, capsys, with_bare_names())
    p = load_project(proj).project
    ops, _ = edit.ops_add_interface(p, "rs422", "OBC1", "STR1")
    History(p).execute("Add", ops)
    assert edit.shared_connectors(p, "OBC1", "rs422") == []  # no named port: no tier 2
    with pytest.raises(edit.EditError):
        edit.ops_add_interface(p, "rs422", "OBC1", "STR2")
    add_interfaces(proj, guided=False)
    code, out = run(capsys, "generate", str(proj))
    assert code == 0, out
    assert f"[pin_port_unknown] {J1} has more than one pin named TX+, TX-, RX+, RX-" in out
    assert "for the RS-422 interfaces IF-001, IF-002, IF-003" in out
    # 2.0.1: each signal takes the first free pin of its name, interfaces in ID order
    q = load_project(proj).project
    held = {
        k: [x.id for x in q.connectors[J1].pins if x.interface_id == f"IF-00{k}"] for k in (1, 2, 3)
    }
    assert held == {k: [str(4 * (k - 1) + n) for n in (1, 2, 3, 4)] for k in (1, 2, 3)}
