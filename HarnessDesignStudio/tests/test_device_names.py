# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Which device a pin or port name names (design of 4.4.0, `docs/ait/DESIGN_4.4_NAMES_PORTS.md`,
section 3.1, sections 10 and 11, owner questions N2, N4, N9 and N10): `device_names.named_device`
on the prefix and the suffix form, the three separators, the case, a port name equal to an ID,
the longest ID (`OBC1` and `OBC1-R`), two devices, an empty rest; `far_device`; `link_reading`;
and, by Hypothesis, `named_device` against the rules of section 3.1 as written and against the
verifier's own copy of the reading (`core/verify.py` `device_naming`, section 3.4; pull request 3),
which does not import this module."""

import re
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from harness_design_studio.core import device_names, templates, verify
from harness_design_studio.core.device_names import DeviceReading, LinkReading, named_device
from harness_design_studio.core.model import Project
from harness_design_studio.core.ports import natural_key

IDS = ("OBC1", "OBC1-R", "TTC1", "TTC2", "PCDU1", "PCDU1-R")


# ---- named_device (3.1) -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "unit", "rest", "form", "sep"),
    [
        ("TTC2_TX", "TTC2", "TX", "prefix", "_"),
        ("TTC2.TX+", "TTC2", "TX+", "prefix", "."),
        ("TTC2-PPS", "TTC2", "PPS", "prefix", "-"),
        ("TX_TTC1", "TTC1", "TX", "suffix", "_"),
        ("TX+.TTC1", "TTC1", "TX+", "suffix", "."),
        ("PPS-TTC1", "TTC1", "PPS", "suffix", "-"),
        ("TTC1_TM_TX+", "TTC1", "TM_TX+", "prefix", "_"),
        ("TTC1__TX", "TTC1", "_TX", "prefix", "_"),
    ],
    ids=["pre-us", "pre-dot", "pre-dash", "suf-us", "suf-dot", "suf-dash", "port-tm", "two-seps"],
)
def test_prefix_and_suffix_with_each_separator(
    name: str, unit: str, rest: str, form: str, sep: str
) -> None:
    assert named_device(name, IDS) == DeviceReading(unit, rest, form, sep)  # type: ignore[arg-type]
    assert named_device(name, IDS, port=True) == DeviceReading(unit, rest, form, sep)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "name",
    ["PPS", "TX+", "RS422_2_TX+", "TTC1TX", "TXTTC1", "ttc1_TX", "TX_ttc1", "Ttc1_TX", "TTC1_",
     "_TTC1", "TTC1 TX", "TTC3_TX", "", "TTC1/TX"],
    ids=["bare", "bare-sign", "port-no-device", "no-sep", "no-sep-suf", "lower", "lower-suf",
         "mixed", "empty-rest", "empty-rest-suf", "space", "unknown-id", "empty", "slash"],
)  # fmt: skip
def test_names_that_name_no_device(name: str) -> None:
    assert named_device(name, IDS) is None
    assert named_device(name, IDS, port=True) is None


def test_a_port_name_equal_to_an_id_names_it_and_a_pin_name_does_not() -> None:
    assert named_device("TTC1", IDS, port=True) == DeviceReading("TTC1", "", "whole", "")
    assert named_device("TTC1", IDS) is None
    # the longest ID is the whole name: the reading OBC1 + - + R is a part of it, for a pin too
    assert named_device("OBC1-R", IDS, port=True) == DeviceReading("OBC1-R", "", "whole", "")
    assert named_device("OBC1-R", IDS) is None
    # without the device OBC1-R, OBC1-R is the signal R of OBC1
    assert named_device("OBC1-R", ("OBC1",)) == DeviceReading("OBC1", "R", "prefix", "-")


def test_the_longest_id_wins() -> None:
    assert named_device("OBC1-R_TX", IDS) == DeviceReading("OBC1-R", "TX", "prefix", "_")
    assert named_device("OBC1_TX", IDS) == DeviceReading("OBC1", "TX", "prefix", "_")
    assert named_device("OBC1-RX", IDS) == DeviceReading("OBC1", "RX", "prefix", "-")
    assert named_device("TX_OBC1-R", IDS) == DeviceReading("OBC1-R", "TX", "suffix", "_")
    assert named_device("TX-R_PCDU1-R", IDS) == DeviceReading("PCDU1-R", "TX-R", "suffix", "_")
    # the order of the IDs does not matter
    assert named_device("OBC1-R_TX", reversed(IDS)) == named_device("OBC1-R_TX", IDS)


def test_a_name_of_two_devices_names_neither_with_its_note() -> None:
    r = named_device("TTC1_TX_TTC2", IDS)
    assert r is not None and not r.names and r.unit == ""
    assert r.note == (
        "TTC1_TX_TTC2 can be read as a name of TTC1 or of TTC2, so it names neither. Rename the pin."
    )
    # the devices in natural order, whichever is the prefix
    assert named_device("TTC2_TX_TTC1", IDS) == DeviceReading(
        "", "", None, "",
        "TTC2_TX_TTC1 can be read as a name of TTC1 or of TTC2, so it names neither. Rename the pin.",
    )  # fmt: skip
    assert not named_device("OBC1_TX-PCDU1-R", IDS, port=True).names  # type: ignore[union-attr]
    # an ID as a prefix and another as a suffix also when the two overlap
    assert not named_device("OBC1-R_TX_OBC1", IDS).names  # type: ignore[union-attr]


def test_one_device_at_both_ends_is_read_as_a_prefix() -> None:
    assert named_device("TTC1_TX_TTC1", IDS) == DeviceReading("TTC1", "TX_TTC1", "prefix", "_")


def test_a_device_id_with_separators_and_the_ids_of_a_project() -> None:
    ids = ("RS422", "A.B", "X-1")
    assert named_device("RS422_1", ids, port=True) == DeviceReading("RS422", "1", "prefix", "_")
    assert named_device("A.B.TX", ids) == DeviceReading("A.B", "TX", "prefix", ".")
    assert named_device("TX-X-1", ids) == DeviceReading("X-1", "TX", "suffix", "-")
    assert device_names.unit_ids(_project_with(["TTC10", "TTC2", "OBC1"])) == ("OBC1", "TTC2", "TTC10")  # fmt: skip


def test_the_note_names_two_devices_in_natural_order() -> None:
    assert device_names.ambiguous_note("X", ["TTC10", "TTC2"]) == (
        "X can be read as a name of TTC2 or of TTC10, so it names neither. Rename the pin."
    )


# ---- by Hypothesis: the rules of 3.1 as written -------------------------------------------------

_SEP = "_.-"
_ID = st.from_regex(re.compile(r"[A-Z][A-Z0-9]{0,3}(?:[_.-][A-Z0-9]{1,2})?"), fullmatch=True)
_NAME = st.text(alphabet="ABTX12_.-+", min_size=0, max_size=12)


def _oracle(name: str, ids: set[str], port: bool) -> DeviceReading | None:
    """Section 3.1 word for word: every reading `D<sep>rest` and `rest<sep>D` with rest not empty,
    and for a port the name itself; the longest wins; a prefix and a suffix of two devices name
    neither."""
    if name in ids:
        return DeviceReading(name, "", "whole", "") if port else None
    heads = [
        (d, name[len(d)])
        for d in ids
        if len(name) > len(d) + 1 and name.startswith(d) and name[len(d)] in _SEP
    ]
    tails = [
        (d, name[-len(d) - 1])
        for d in ids
        if len(name) > len(d) + 1 and name.endswith(d) and name[-len(d) - 1] in _SEP
    ]
    head = max(heads, key=lambda h: len(h[0]), default=None)
    tail = max(tails, key=lambda t: len(t[0]), default=None)
    if head and tail and head[0] != tail[0]:
        a, b = sorted({head[0], tail[0]}, key=natural_key)
        note = (
            f"{name} can be read as a name of {a} or of {b}, so it names neither. Rename the pin."
        )
        return DeviceReading("", "", None, "", note)
    if head:
        return DeviceReading(head[0], name[len(head[0]) + 1 :], "prefix", head[1])
    if tail:
        return DeviceReading(tail[0], name[: -len(tail[0]) - 1], "suffix", tail[1])
    return None


@settings(max_examples=400, deadline=None)
@given(st.sets(_ID, max_size=5), _NAME, st.booleans())
def test_named_device_follows_the_rules_as_written(ids: set[str], name: str, port: bool) -> None:
    assert named_device(name, ids, port=port) == _oracle(name, ids, port)


@settings(max_examples=400, deadline=None)
@given(st.sets(_ID, max_size=5), _NAME, st.booleans())
def test_the_verifiers_copy_reads_every_name_as_the_core_does(
    ids: set[str], name: str, port: bool
) -> None:
    """Section 3.4: the two copies of the reading agree (device, rest, form, separator; the device
    is "" for a name of two devices)."""
    core = named_device(name, ids, port=port)
    mine = verify.device_naming(name, ids, port=port)
    assert mine == (
        None if core is None else (core.unit, core.rest, core.form or "", core.separator)
    )


@pytest.mark.parametrize(
    "name",
    ["OBC1-R_TX", "TTC1_TX_TTC2", "TX+.TTC1", "TTC1", "TTC1_"],
    ids=["long", "two", "suf", "id", "nil"],
)
def test_the_verifiers_copy_on_the_cases_of_section_10(name: str) -> None:
    core = named_device(name, IDS, port=True)
    mine = verify.device_naming(name, IDS, port=True)
    assert mine == (
        None if core is None else (core.unit, core.rest, core.form or "", core.separator)
    )


def test_the_verifier_does_not_import_the_reading_of_the_core() -> None:
    text = Path(verify.__file__ or "").read_text(encoding="utf-8")
    assert "device_names import" not in text and "core.device_names" not in text
    assert "from .device_names" not in text and "import device_names" not in text


@settings(max_examples=300, deadline=None)
@given(
    _ID,
    st.sampled_from(list(_SEP)),
    st.text(alphabet="ABTXZ12+", min_size=1, max_size=8),
    st.booleans(),
)
def test_a_composed_name_reads_back(unit: str, sep: str, rest: str, suffix: bool) -> None:
    """A device ID and a rest without a separator, joined either way, read back as both. A rest
    equal to the ID (`A_A`) is one device at both ends, read as a prefix (a test of its own)."""
    assume(rest != unit)
    name = f"{rest}{sep}{unit}" if suffix else f"{unit}{sep}{rest}"
    r = named_device(name, {unit})
    assert r is not None and (r.unit, r.rest) == (unit, rest)
    assert r.form == ("suffix" if suffix else "prefix") and r.separator == sep


# ---- far_device -------------------------------------------------------------------------------


def _project_with(units: list[str]) -> Project:
    from harness_design_studio.core.model import Unit

    p = Project()
    for u in units:
        p.units[u] = Unit(id=u, name=u, subsystem="Example")
    return p


@pytest.fixture(scope="module")
def flat(tmp_path_factory: pytest.TempPathFactory) -> Project:
    return templates.create_project(tmp_path_factory.mktemp("flat") / "flat", "flatsat")


def test_far_device_is_the_device_at_the_other_end(flat: Project) -> None:
    i = next(
        i
        for i in sorted(flat.interfaces.values(), key=lambda x: x.id)
        if len(i.endpoints) == 2
        and i.endpoints[0].connector_id
        and i.endpoints[1].connector_id
        and i.endpoints[0].unit_id != i.endpoints[1].unit_id
    )
    a, b = i.endpoints
    assert a.connector_id and b.connector_id
    assert device_names.far_device(flat, i, a.connector_id) == b.unit_id
    assert device_names.far_device(flat, i, b.connector_id) == a.unit_id
    # by the device that owns the connector, when the endpoint has another connector or none yet
    other = next(
        c.id
        for c in sorted(flat.connectors.values(), key=lambda c: c.id)
        if c.unit_id == a.unit_id and c.id != a.connector_id
    )
    assert device_names.far_device(flat, i, other) == b.unit_id
    loose = i.model_copy(update={"endpoints": [a.model_copy(update={"connector_id": None}), b]})
    assert device_names.far_device(flat, loose, a.connector_id) == b.unit_id
    # a connector of neither device, or no connector at all: none
    stranger = next(
        c.id
        for c in sorted(flat.connectors.values(), key=lambda c: c.id)
        if c.unit_id not in (a.unit_id, b.unit_id, None)
    )
    assert device_names.far_device(flat, i, stranger) == ""
    assert device_names.far_device(flat, i, "NO-SUCH-J01") == ""


def test_no_far_device_on_one_device_or_without_two_endpoints(flat: Project) -> None:
    i = next(
        i for i in sorted(flat.interfaces.values(), key=lambda x: x.id) if len(i.endpoints) == 2
    )
    a, b = i.endpoints
    assert a.connector_id
    same = i.model_copy(update={"endpoints": [a, b.model_copy(update={"unit_id": a.unit_id})]})
    assert device_names.far_device(flat, same, a.connector_id) == ""
    one = i.model_copy(update={"endpoints": [a]})
    assert device_names.far_device(flat, one, a.connector_id) == ""


# ---- link_reading (4.1, N9, N10) --------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "reading"),
    [
        ("PPS", LinkReading("PPS")),
        ("TTC2_TX", LinkReading("TX")),
        ("TX.TTC2", LinkReading("TX")),
        ("OBC1_TX", LinkReading("OBC1_TX")),
        ("TTC1_TX", LinkReading("", third="TTC1")),
        ("OBC1-R_TX", LinkReading("", third="OBC1-R")),
        ("TTC2", LinkReading("TTC2")),
        (
            "TTC1_TX_TTC2",
            LinkReading(
                "TTC1_TX_TTC2",
                note="TTC1_TX_TTC2 can be read as a name of TTC1 or of TTC2, so it names "
                "neither. Rename the pin.",
            ),
        ),
    ],
    ids=["none", "other", "other-suf", "own", "third", "third-longest", "whole-id", "two"],
)
def test_link_reading_on_a_pin_of_obc1_in_a_link_to_ttc2(name: str, reading: LinkReading) -> None:
    r = device_names.link_reading(name, "OBC1", "TTC2", IDS)
    assert r == reading
    assert r.offered == (not reading.third)


def test_link_reading_on_the_far_side_swaps_the_devices() -> None:
    assert device_names.link_reading("OBC1_RX", "TTC2", "OBC1", IDS) == LinkReading("RX")
    assert device_names.link_reading("TTC2_TX", "TTC2", "OBC1", IDS) == LinkReading("TTC2_TX")


def test_the_module_reads_no_setting_and_no_file() -> None:
    """The callers read `naming.far_device_names`; the reading itself is pure."""
    src = Path(device_names.__file__).read_text(encoding="utf-8")
    imports = [line for line in src.splitlines() if line.startswith(("import ", "from "))]
    assert imports == [
        "from collections.abc import Iterable",
        "from dataclasses import dataclass",
        "from typing import Literal",
        "from .model import InterfaceInstance, Project",
        "from .ports import SEPARATORS, natural_key",
    ]
