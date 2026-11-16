# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""A project that generates at 2.0.1 generates the same at 2.1.0 (REQ-PIN-04, D-237;
`docs/ait/DESIGN_2.1_PORTS.md` section 4). `tests/reference/pins_201.py` is the pin allocator of
2.0.1 word for word; on random connectors whose fixed pins have bare signal names only, the
current `core/generate/pins.py` must give the same pins, reasons, errors and warnings."""

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from harness_design_studio.core.generate import pins
from harness_design_studio.core.model import Connector, InterfaceType, Pin
from harness_design_studio.core.ports import read_signal
from harness_design_studio.core.starter import starter_interface_types
from tests.reference import pins_201
from tests.test_ports_allocation import as_201

TYPES = sorted(starter_interface_types(), key=lambda t: t.id)
FILLERS = ("NC", "SPARE", "SHLD", "CASE")  # names that are no signal of any type


def test_no_signal_name_of_the_library_reads_as_a_port_of_another_type() -> None:
    """The premise of the comparison: with these types, bare names never form a named port."""
    names = {s.name for t in TYPES for s in t.signals} | set(FILLERS)
    for t in TYPES:
        own = [s.name for s in t.signals]
        for n in sorted(names):
            assert all(r.form == "bare" for r in read_signal(n, own)), (t.id, n)


def _case(seed: int) -> tuple[Connector, list[pins.Request], dict[tuple[str, str], str], dict[tuple[str, str], str], str, tuple[str, ...]]:  # fmt: skip
    rnd = random.Random(seed)
    types: list[InterfaceType] = rnd.sample(TYPES, rnd.randint(1, 3))
    names = [s.name for t in types for s in t.signals] + list(FILLERS)
    n = rnd.randint(1, 24)
    pin_ids = [str(k) for k in rnd.sample(range(1, 60), n)]
    if rnd.random() < 0.5:
        pin_ids.sort(key=int)
    reqs = [
        pins.Request(f"IF-{k:03d}", rnd.choice(types)) for k in rnd.sample(range(1, 40), rnd.randint(1, 5))
    ]  # fmt: skip
    fixed = rnd.random() < 0.85
    pin_list: list[Pin] = []
    held: dict[tuple[str, str], str] = {}
    for pid in pin_ids:
        signal = rnd.choice(names) if rnd.random() < 0.9 else None
        locked = rnd.random() < 0.15
        iid = None
        if locked and signal and rnd.random() < 0.7:
            req = rnd.choice(reqs)
            iid = req.interface_id
            held[(iid, signal)] = pid
        pin_list.append(
            Pin(id=pid, signal=signal, fixed=fixed and rnd.random() < 0.9, locked=locked, interface_id=iid)
        )  # fmt: skip
    previous = {
        (rnd.choice(reqs).interface_id, rnd.choice(names)): rnd.choice(pin_ids)
        for _ in range(rnd.randint(0, 8))
    }
    box = Connector(id="J1", name="J1", role="box", part_id="P", unit_id="U", pins=pin_list)
    fit = rnd.choice(pins.STRATEGIES)
    categories = rnd.choice([pins.DEFAULT_ORDER, ("data",), ()])
    return box, reqs, previous, held, fit, categories


@settings(max_examples=400, deadline=None)
@given(seed=st.integers(0, 2**32 - 1))
def test_the_allocator_gives_what_2_0_1_gave_on_bare_names(seed: int) -> None:
    box, reqs, previous, held, fit, categories = _case(seed)
    gap = seed % 3
    new = pins.allocate(box, reqs, previous, gap, held, seed % 2, categories, fit)
    old = pins_201.allocate(box, as_201(reqs), previous, gap, held, seed % 2, categories, fit)
    assert new.pins == old.pins
    assert list(new.pins) == list(old.pins)  # in the same order
    assert new.reasons == old.reasons
    assert new.errors == old.errors
    assert new.warnings == old.warnings


def test_the_comparison_reaches_fixed_pinouts_and_their_errors() -> None:
    """The random cases are not all trivial: many have a fixed pinout, placed pins and errors."""
    fixed = placed = failed = 0
    for seed in range(300):
        box, reqs, previous, held, fit, categories = _case(seed)
        res = pins.allocate(box, reqs, previous, 0, held, 0, categories, fit)
        if any(p.fixed and p.signal for p in box.pins):
            fixed += 1
            placed += bool(res.pins)
            failed += bool(res.errors)
    assert fixed > 150 and placed > 50 and failed > 50
