# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""With `naming.far_device_names` off, Generate gives what 4.3.0 gave (REQ-PIN-08, D-262; design of
4.4.0 sections 3.2 and 9). `tests/reference/pins_430.py` is the pin allocator of 4.3.0 word for
word; on random connectors with named ports (some named after a device), bare names, fillers, locks
and earlier allocations, the current `core/generate/pins.py` must give the same pins, reasons,
errors and warnings while the setting is off, whatever far device the requests carry. It must also
give them with the setting on when no port name names a device of the project."""

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from harness_design_studio.core.generate import pins
from harness_design_studio.core.model import Connector, InterfaceType, Pin
from harness_design_studio.core.starter import starter_interface_types
from tests.reference import pins_430

TYPES = sorted(starter_interface_types(), key=lambda t: t.id)
FILLERS = ("NC", "SPARE", "SHLD")
PORTS = ("TTC1", "TTC2", "OBC1", "OBC1-R", "TTC1_TM", "TTC1_TC", "RS422_1", "RS422_10", "P2")
UNITS = ("OBC1", "OBC1-R", "TTC1", "TTC2", "TTC3")
SEPARATORS = ("_", ".", "-")

Case = tuple[
    Connector,
    list[pins.Request],
    dict[tuple[str, str], str],
    dict[tuple[str, str], str],
    str,
    tuple[str, ...],
]


def _names(rnd: random.Random, types: list[InterfaceType]) -> list[str]:
    """The signal names of the connector: whole named ports (sometimes missing or doubling a
    signal, in the prefix or the suffix form), bare names and fillers, in random order."""
    out: list[str] = []
    for _ in range(rnd.randint(0, 4)):
        t = rnd.choice(types)
        port = rnd.choice(PORTS)
        sep = rnd.choice(SEPARATORS)
        sigs = [s.name for s in t.signals]
        if rnd.random() < 0.15 and len(sigs) > 1:
            sigs = sigs[:-1]  # incomplete
        if rnd.random() < 0.1:
            sigs.append(sigs[0])  # doubled
        suffix = rnd.random() < 0.2
        out += [f"{sig}{sep}{port}" if suffix else f"{port}{sep}{sig}" for sig in sigs]
    for _ in range(rnd.randint(0, 6)):
        out.append(rnd.choice([s.name for t in types for s in t.signals] + list(FILLERS)))
    rnd.shuffle(out)
    return out


def _case(seed: int) -> Case:
    rnd = random.Random(seed)
    types: list[InterfaceType] = rnd.sample(TYPES, rnd.randint(1, 2))
    names = _names(rnd, types)
    pin_ids = [str(k + 1) for k in range(len(names))]
    reqs = [
        pins.Request(f"IF-{k:03d}", rnd.choice(types), rnd.choice(("", *UNITS)))
        for k in rnd.sample(range(1, 30), rnd.randint(1, 5))
    ]
    pin_list: list[Pin] = []
    held: dict[tuple[str, str], str] = {}
    for pid, name in zip(pin_ids, names, strict=True):
        signal = name if rnd.random() < 0.95 else None
        locked = rnd.random() < 0.1
        iid = None
        if locked and signal and rnd.random() < 0.7:
            req = rnd.choice(reqs)
            iid = req.interface_id
            sigs = [s.name for s in req.itype.signals]
            held[(iid, next((x for x in sigs if signal.endswith(x)), signal))] = pid
        pin_list.append(
            Pin(id=pid, signal=signal, fixed=rnd.random() < 0.9, locked=locked, interface_id=iid)
        )
    signals = [s.name for t in types for s in t.signals]
    previous = (
        {
            (rnd.choice(reqs).interface_id, rnd.choice(signals)): rnd.choice(pin_ids)
            for _ in range(rnd.randint(0, 8))
        }
        if pin_ids
        else {}
    )
    box = Connector(id="J1", name="J1", role="box", part_id="P", unit_id="OBC1", pins=pin_list)
    return (
        box,
        reqs,
        previous,
        held,
        rnd.choice(pins.STRATEGIES),
        rnd.choice([pins.DEFAULT_ORDER, ("data",), ()]),
    )


def _as_430(reqs: list[pins.Request]) -> list[pins_430.Request]:
    return [pins_430.Request(r.interface_id, r.itype) for r in reqs]


def _same(new: pins.Allocation, old: pins_430.Allocation) -> None:
    assert new.pins == old.pins
    assert list(new.pins) == list(old.pins)  # in the same order
    assert new.reasons == old.reasons
    assert new.errors == old.errors
    assert new.warnings == old.warnings
    assert new.port_warnings == old.port_warnings


@settings(max_examples=400, deadline=None)
@given(seed=st.integers(0, 2**32 - 1))
def test_the_allocator_with_the_setting_off_gives_what_4_3_0_gave(seed: int) -> None:
    box, reqs, previous, held, fit, categories = _case(seed)
    gap = seed % 3
    new = pins.allocate(
        box, reqs, previous, gap, held, seed % 2, categories, fit, far_devices=False, units=UNITS
    )
    old = pins_430.allocate(box, _as_430(reqs), previous, gap, held, seed % 2, categories, fit)
    _same(new, old)


@settings(max_examples=200, deadline=None)
@given(seed=st.integers(0, 2**32 - 1))
def test_the_setting_on_without_device_names_gives_what_4_3_0_gave(seed: int) -> None:
    """No unit ID to read a port name against: no port names a device, so nothing moves."""
    box, reqs, previous, held, fit, categories = _case(seed)
    new = pins.allocate(
        box, reqs, previous, 0, held, 0, categories, fit, far_devices=True, units=()
    )
    old = pins_430.allocate(box, _as_430(reqs), previous, 0, held, 0, categories, fit)
    _same(new, old)


def test_the_reference_is_the_allocator_of_4_3_0_word_for_word() -> None:
    """The copy starts with its own note and then holds the module of 4.3.0 unchanged; the current
    module differs from it only by the code of the setting."""
    text = pins_430.__doc__ or ""
    assert text.startswith("The pin allocation exactly as release 4.3.0 had it")
    assert "Do not edit this file." in text
    assert not hasattr(pins_430, "far_devices") and not hasattr(pins_430, "FAR_DEVICE_SETTING")


def test_the_comparison_reaches_named_ports_device_names_and_errors() -> None:
    """The random cases are not all trivial: many have a named port that names a device, a
    request with a far device, placed pins and errors; and with the setting on, the result
    differs from 4.3.0 in some of them (so the comparison above can fail)."""
    named = with_far = placed = failed = differs = 0
    for seed in range(300):
        box, reqs, previous, held, fit, categories = _case(seed)
        res = pins.allocate(box, reqs, previous, 0, held, 0, categories, fit)
        names = [p.signal or "" for p in box.pins if p.fixed]
        named += any(n.startswith(("TTC", "OBC")) for n in names)
        with_far += any(r.far for r in reqs)
        placed += bool(res.pins)
        failed += bool(res.errors)
        on = pins.allocate(
            box, reqs, previous, 0, held, 0, categories, fit, far_devices=True, units=UNITS
        )
        differs += (on.pins, on.errors) != (res.pins, res.errors)
    assert named > 150 and with_far > 200 and placed > 100 and failed > 50 and differs > 20
