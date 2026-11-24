# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Which connector is end A of a shield group, and which is end B (design of 4.1.0, section 3.5).

A shield group has two ends (`ShieldGroup.end_a`, `end_b`) and names no connector. The rule that
places them is the one the drawings have always used: end A is the `from` end of the group's
reference wire, end B its `to` end, and the reference wire is the group's wire with the lowest ID
in the whole harness (not the first one on a sheet), so the ends never swap between sheets. The
drawing (`core/outputs/drawing.py`) and the Production sheet (`core/outputs/production.py`) both
take it from here; the independent verifier has its own copy (`verify_production._end_at`).

Where an end lands (format 5, design of 5.0.0 section 7): `ShieldGroup.at_a` and `at_b` name the
connector, the pin a pigtail lands on and the backshell. A place *fits* while the connector it
names is the connector of its end (`end_connector`); only a place that fits is shown in the outputs
(`place_here`, `landings`, `place_words`), and `check` names one that does not (`shield_end_moved`).
The verifier has its own copies (`verify_production._place_here`, `_landings`, `_place_words`)."""

from typing import Literal

from harness_design_studio.core.model import Harness, ShieldEndPlace, ShieldGroup, Wire

End = Literal["a", "b"]
ENDS: tuple[End, ...] = ("a", "b")


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


def end_connector(h: Harness, s: ShieldGroup, end: End) -> str | None:
    """The connector of end `end` of the group: the `from` connector of its reference wire for
    "a", the `to` connector for "b"; None when the group has no wire in the harness."""
    w = reference_wire(h, s)
    if w is None:
        return None
    return w.from_connector if end == "a" else w.to_connector


def place_of(s: ShieldGroup, end: End) -> ShieldEndPlace | None:
    """The stated place of end `end` (`at_a` or `at_b`), fitting or not."""
    return s.at_a if end == "a" else s.at_b


def kind_of_end(s: ShieldGroup, end: End) -> str:
    """How end `end` is terminated (`end_a` or `end_b`)."""
    return s.end_a if end == "a" else s.end_b


def place_here(h: Harness, s: ShieldGroup, connector_id: str) -> ShieldEndPlace | None:
    """The place of the group's end at this connector, when it names this connector (it fits);
    None when the end has no place, the place names another connector, or no end is here."""
    end = end_at(h, s, connector_id)
    if end is None:
        return None
    place = place_of(s, end)
    return place if place is not None and place.connector == connector_id else None


def landings(h: Harness) -> dict[tuple[str, str], list[ShieldGroup]]:
    """The pins a pigtail lands on, as (connector, pin) -> the groups that land there, by group ID.
    A place counts while it fits; a pin the connector lacks is still listed (the outputs list
    the pins of a connector, so it shows nowhere, and `check` says `shield_pin_missing`)."""
    out: dict[tuple[str, str], list[ShieldGroup]] = {}
    for s in sorted(h.shields, key=lambda x: x.id):
        for end in ENDS:
            place = place_of(s, end)
            if place is None or place.pin is None:
                continue
            if end_connector(h, s, end) != place.connector:
                continue
            out.setdefault((place.connector, place.pin), []).append(s)
    return out


def place_words(end: str, place: ShieldEndPlace | None) -> str:
    """The words of a place after the kind of end: "pin 9", "backshell W001-A1", both joined by
    "and"; empty without a place. The outputs write "pigtail to pin 9", "pigtail to backshell
    W001-A1" and "backshell 360 (W001-A1)" with it (design of 5.0.0 section 7.4)."""
    if place is None:
        return ""
    if end == "backshell_360":
        return place.backshell or ""
    named = [
        *([f"pin {place.pin}"] if place.pin is not None else []),
        *([f"backshell {place.backshell}"] if place.backshell is not None else []),
    ]
    return " and ".join(named)


# how an end is terminated, in the words of the outputs (the Production sheet, the drawing)
END_WORDS = {"backshell_360": "backshell 360", "pigtail": "pigtail", "floating": "floating"}


def end_text(kind: str, place: ShieldEndPlace | None) -> str:
    """How an end is terminated and where it lands, in the words of the outputs: "pigtail",
    "pigtail to pin 9", "pigtail to backshell W001-A1", "backshell 360 (W001-A1)"."""
    word = END_WORDS.get(kind, kind)
    named = place_words(kind, place)
    if not named:
        return word
    return f"{word} ({named})" if kind == "backshell_360" else f"{word} to {named}"


__all__ = [
    "END_WORDS",
    "ENDS",
    "End",
    "end_at",
    "end_connector",
    "end_text",
    "kind_of_end",
    "landings",
    "place_here",
    "place_of",
    "place_words",
    "reference_wire",
]
