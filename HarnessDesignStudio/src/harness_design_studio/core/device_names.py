# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Which device a pin or port name names (4.4.0, milestone E4, owner questions N2, N4 and N10).

The design is `docs/ait/DESIGN_4.4_NAMES_PORTS.md`, section 3.1.

A name **names device D** when it is `D<sep>rest` (prefix form) or `rest<sep>D` (suffix form), with
D the ID of a device of the project, sep one of `_ . -` (the separators of ports, `core/ports.py`)
and rest not empty. A **port name** also names D when it is D itself (port `TTC1`). The ID is
compared exactly, with case, as port names and IDs are (N2): the name of a device (`Transceiver 1`)
is free text and is never read.

When several IDs fit, **the longest wins**: `OBC1-R_TX` names `OBC1-R`, not `OBC1`, whose reading
`OBC1` + `-` + `R_TX` is a part of it. A pin name that is a device ID itself (`OBC1-R`) names no
device: its longest reading leaves no rest, and a shorter ID that is a part of it is not read
either. When a prefix and a suffix name two different devices (`TTC1_TX_TTC2`), the name names
neither, and the reading carries a note that says so; the tool never guesses.

In a connection between a connector of device X and one of device Y, a pin of X whose name names
Y is compared by the rest of its name (`TTC2_TX` is `TX` in a link to TTC2); one that names X
itself is compared by its whole name (N10), and one that names a third device belongs to another
connection (`link_reading`).

The module is pure (no I/O, no editor) and reads nothing of the configuration: whether the reading
is used at all is the setting `naming.far_device_names` (off by default, A-FAR-DEVICE), which the
callers read. `core/verify.py` keeps an independent copy of `named_device`, as it does for the
reading of ports.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from .model import InterfaceInstance, Project
from .ports import SEPARATORS, natural_key

Form = Literal["prefix", "suffix", "whole"]


@dataclass(frozen=True)
class DeviceReading:
    """How a name names a device: the device `unit` and the `rest` of the name without the device
    and its separator (`TTC2_TX` gives `TTC2` and `TX`; a port named `TTC1` gives `TTC1` and "").
    `unit` is "" when the name fits two devices, and `note` then says why it names neither."""

    unit: str
    rest: str
    form: Form | None
    separator: str
    note: str = ""

    @property
    def names(self) -> bool:
        """Whether the name names a device (False for a name that fits two)."""
        return bool(self.unit)


def ambiguous_note(name: str, units: Iterable[str]) -> str:
    """The note of a name that fits two devices: `TTC1_TX_TTC2 can be read as a name of TTC1 or of
    TTC2, so it names neither. Rename the pin.` The devices in natural order."""
    a, b = sorted(set(units), key=natural_key)[:2]
    return f"{name} can be read as a name of {a} or of {b}, so it names neither. Rename the pin."


def _longest(name: str, ids: Iterable[str], prefix: bool) -> tuple[str, str] | None:
    """The longest device ID at the start (or the end) of `name` followed (or preceded) by a
    separator, with the separator; also an ID equal to the whole name, with no separator."""
    best: tuple[str, str] | None = None
    for d in ids:
        if not d or len(d) > len(name) or len(d) == len(name) - 1:
            continue  # an ID and a separator with nothing left is no reading
        if len(d) == len(name):
            hit = (d, "") if d == name else None
        elif prefix and name.startswith(d) and name[len(d)] in SEPARATORS:
            hit = (d, name[len(d)])
        elif not prefix and name.endswith(d) and name[-len(d) - 1] in SEPARATORS:
            hit = (d, name[-len(d) - 1])
        else:
            hit = None
        if hit is not None and (best is None or len(hit[0]) > len(best[0])):
            best = hit
    return best


def named_device(name: str, unit_ids: Iterable[str], *, port: bool = False) -> DeviceReading | None:
    """The device that `name` names among the device IDs `unit_ids`, or None when it names none
    (section 3.1). `port`: the name is a port name, which also names a device when it is the ID
    itself. A name that fits two devices gives a reading with no device and its note."""
    ids = {d for d in unit_ids if d}
    if not name:
        return None
    head = _longest(name, ids, prefix=True)
    tail = _longest(name, ids, prefix=False)
    if head is not None and head[1] == "":  # the whole name is an ID: a port, else no device
        return DeviceReading(name, "", "whole", "") if port else None
    rest_head = name[len(head[0]) + 1 :] if head is not None else ""
    rest_tail = name[: -len(tail[0]) - 1] if tail is not None else ""
    if head is not None and tail is not None and head[0] != tail[0]:
        return DeviceReading("", "", None, "", ambiguous_note(name, (head[0], tail[0])))
    if head is not None:  # the prefix form, the one `ports.compose` writes, when both are alike
        return DeviceReading(head[0], rest_head, "prefix", head[1])
    if tail is not None:
        return DeviceReading(tail[0], rest_tail, "suffix", tail[1])
    return None


def unit_ids(project: Project) -> tuple[str, ...]:
    """The IDs of the devices of the project, in natural order: what a name is read against."""
    return tuple(sorted(project.units, key=natural_key))


def far_device(project: Project, interface: InterfaceInstance, connector_id: str) -> str:
    """The device at the other end of `interface` from the connector `connector_id` (section 3.1):
    the device of the endpoint that is not on that connector. "" when the interface has not two
    endpoints, when neither endpoint is at the connector (by its connector, else by its device),
    or when both endpoints are on one device."""
    if len(interface.endpoints) != 2:
        return ""
    a, b = interface.endpoints
    here = [e for e in (a, b) if e.connector_id == connector_id]
    if not here:
        conn = project.connectors.get(connector_id)
        owner = conn.unit_id if conn is not None else None
        here = [e for e in (a, b) if owner is not None and e.unit_id == owner]
    if not here or a.unit_id == b.unit_id:
        return ""
    return b.unit_id if here[0] is a else a.unit_id


@dataclass(frozen=True)
class LinkReading:
    """A pin name as the pairing of a connection reads it (section 4.1): `compare` is the name the
    pairing compares ("" when the pin is not offered), `third` the third device it names (then it
    is not offered), and `note` the note of a name that fits two devices."""

    compare: str
    third: str = ""
    note: str = ""

    @property
    def offered(self) -> bool:
        return not self.third


def link_reading(name: str, own: str, other: str, unit_ids: Iterable[str]) -> LinkReading:
    """How a pin of device `own`, in a connection to device `other`, is read (section 4.1, N9,
    N10): a name that names no device, or its own device, by its whole name; one that names
    `other` by the rest of the name; one that names a third device is not offered. A name that
    fits two devices is read by its whole name and carries its note."""
    r = named_device(name, unit_ids)
    if r is None:
        return LinkReading(name)
    if not r.names:
        return LinkReading(name, note=r.note)
    if r.unit == other and other != own:
        return LinkReading(r.rest)
    if r.unit == own:
        return LinkReading(name)
    return LinkReading("", third=r.unit)
