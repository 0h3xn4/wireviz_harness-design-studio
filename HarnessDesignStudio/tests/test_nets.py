# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index,union-attr"
"""REQ-HARN-04. The nets of a harness (format 3, M6a; section 6.3 of the design of 2.3.0): `core/nets.py`, the
verifier's own copy (`core/verify.py` `splice_nets`) and the output check's (`core/outputs/verify.py`
`_nets`) give the same nets on random harnesses with splices, and the order of the ends and the path
between two ends are what the tests sheet writes."""

from hypothesis import given, settings
from hypothesis import strategies as st

from harness_design_studio.core.model import Connector, Harness, Pin, Wire
from harness_design_studio.core.nets import (
    end_pairs,
    harness_nets,
    has_splices,
    net_of_wire,
    path_wires,
)
from harness_design_studio.core.outputs import verify as out_verify
from harness_design_studio.core.verify import splice_nets

CONNECTORS = ("W1-P1", "W1-P2", "W1-P10", "W1-X1", "W1-X2")


def harness(wires: list[tuple[int, int, int, int]]) -> Harness:
    conns = [
        Connector(
            id=cid,
            name=cid,
            role="splice" if "-X" in cid else "cable",
            part_id="P",
            pins=[Pin(id=str(k)) for k in (1, 2, 10)],
        )
        for cid in CONNECTORS
    ]
    pins = ("1", "2", "10")
    out = []
    for n, (a, pa, b, pb) in enumerate(wires, start=1):
        if (a, pa) == (b, pb):
            continue
        out.append(
            Wire(
                id=f"W1-{n:03d}",
                from_connector=CONNECTORS[a],
                from_pin=pins[pa],
                to_connector=CONNECTORS[b],
                to_pin=pins[pb],
            )
        )
    return Harness(id="W1", name="random", connectors=conns, wires=out)


_WIRE = st.tuples(st.integers(0, 4), st.integers(0, 2), st.integers(0, 4), st.integers(0, 2))


def as_sets(nets):
    return sorted((sorted(p), sorted(w)) for p, w in nets)


@settings(max_examples=150, deadline=None)
@given(st.lists(_WIRE, max_size=14))
def test_the_three_copies_of_the_nets_agree(wires):
    h = harness(wires)
    core = [(set(n.pins), set(n.wires)) for n in harness_nets(h)]
    assert as_sets(core) == as_sets(splice_nets(h)) == as_sets(out_verify._nets(h))
    assert sorted(w for n in harness_nets(h) for w in n.wires) == sorted(w.id for w in h.wires)


@settings(max_examples=100, deadline=None)
@given(st.lists(_WIRE, max_size=12))
def test_the_order_and_the_path_agree_with_the_output_check(wires):
    h = harness(wires)
    splices = {c for c in CONNECTORS if "-X" in c}
    for net in harness_nets(h):
        assert list(net.ends) == sorted(
            (p for p in net.pins if p[0] not in splices), key=out_verify._pin_nat
        )
        for a, b in end_pairs(net):
            assert list(path_wires(h, a, b, net.wires)) == out_verify._shortest(
                h, frozenset(net.wires), a, b
            )


def test_a_y_through_one_splice_is_one_net_with_three_ends():
    h = harness([(0, 0, 3, 0), (3, 0, 1, 0), (3, 0, 2, 0)])
    (net,) = harness_nets(h)
    assert net.ends == (("W1-P1", "1"), ("W1-P2", "1"), ("W1-P10", "1"))
    assert net.splices == ("W1-X1",)
    assert end_pairs(net)[0] == (("W1-P1", "1"), ("W1-P2", "1"))
    assert path_wires(h, ("W1-P1", "1"), ("W1-P10", "1")) == ("W1-001", "W1-003")
    assert has_splices(h) and set(net_of_wire(h)) == {"W1-001", "W1-002", "W1-003"}


def test_a_harness_without_a_splice_has_one_net_per_wire():
    h = harness([(0, 0, 1, 0), (0, 1, 2, 1)])
    h = h.model_copy(update={"connectors": [c for c in h.connectors if "-X" not in c.id]})
    nets = harness_nets(h)
    assert [n.wires for n in nets] == [("W1-001",), ("W1-002",)]
    assert all(not n.splices and len(n.ends) == 2 for n in nets)
