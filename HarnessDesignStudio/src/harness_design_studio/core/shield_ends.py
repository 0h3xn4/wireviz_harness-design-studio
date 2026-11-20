# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Which connector is end A of a shield group, and which is end B (design of 4.1.0, section 3.5).

A shield group has two ends (`ShieldGroup.end_a`, `end_b`) and names no connector. The rule that
places them is the one the drawings have always used: end A is the `from` end of the group's
reference wire, end B its `to` end, and the reference wire is the group's wire with the lowest ID
in the whole harness (not the first one on a sheet), so the ends never swap between sheets. The
drawing (`core/outputs/drawing.py`) and the Production sheet (`core/outputs/production.py`) both
take it from here; the independent verifier has its own copy (`verify_production._end_at`)."""

from typing import Literal

from harness_design_studio.core.model import Harness, ShieldGroup, Wire

End = Literal["a", "b"]


def reference_wire(h: Harness, s: ShieldGroup) -> Wire | None:
    """The group's wire with the lowest ID among the wires of the harness; None when no wire of
    the group is in the harness."""
    by_id = {w.id: w for w in h.wires}
    ids = sorted(i for i in s.wire_ids if i in by_id)
    return by_id[ids[0]] if ids else None


def end_at(h: Harness, s: ShieldGroup, connector_id: str) -> End | None:
    """The end of the group at a connector: "a" at the `from` connector of its reference wire, "b"
    at its `to` connector, None at any other connector (a group whose wires end on more than two
    connectors, which the warning `shield_across_branch` names) or when the group has no wire in
    the harness."""
    w = reference_wire(h, s)
    if w is None:
        return None
    if connector_id == w.from_connector:
        return "a"
    if connector_id == w.to_connector:
        return "b"
    return None


__all__ = ["End", "end_at", "reference_wire"]
