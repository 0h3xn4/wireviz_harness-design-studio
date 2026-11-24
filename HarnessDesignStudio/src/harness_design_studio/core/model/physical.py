# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Physical layer: connectors, pins, wires, shields and harnesses."""

from typing import Annotated, ClassVar, Literal

from pydantic import Field, model_validator

from harness_design_studio.core.ids import Id, PinId

from .base import (
    MAX_PIN_COUNT,
    Awg,
    CurrentA,
    Entity,
    IsoDate,
    LengthM,
    LengthMm,
    Name,
    Reason,
    SparseEntity,
    Text,
    Version,
    WebLink,
)

Gender = Literal["male", "female", "unspecified"]
Role = Literal["box", "cable", "inline", "feedthrough", "test", "loose", "splice"]
# "loose" is the end of a cable that is not on a connector yet (M4, D-200, D-201): an ordinary
# connector of the harness with pins that wires attach to, no `mates_with`, and the library part
# `TBD-CONNECTOR` until a person decides.
LOOSE_ROLE: Role = "loose"
TBD_PART_ID = "TBD-CONNECTOR"  # the library part of a loose end until a person chooses one
# "splice" (format 3, M6a, design of 2.3.0 section 6.1): a joint inside a harness, a connector of
# the harness with no `mates_with` and no `unit_id` whose part is a library part of category
# `splice`. Each pin is one node, and every wire that ends on a node is joined to the others there;
# the pin's `termination` says how (`crimp` or `solder`). A splice block has a pin per node.
SPLICE_ROLE: Role = "splice"
# Where a harness came from. It is worked out from what the files already say (`generated`, and the
# connection that names the harness), never stored: `links.harness_origin` (D-201).
Origin = Literal["interfaces", "link", "drawn"]
Termination = Literal["crimp", "solder", "unspecified"]
HarnessStatus = Literal["draft", "in_review", "released"]
# Where the routing segments that end at a cable connector are measured to (format 5, design of
# 5.0.0 section 4): its rear, where the wires leave the body or backshell (the meaning of every
# length of formats 1 to 4), or its mating face. Unset on a connector: the project's setting
# `model.length_reference`.
LengthTo = Literal["face", "rear"]
LENGTH_TO: tuple[LengthTo, ...] = ("face", "rear")
ShieldKind = Literal["twisted_pair", "shielded_pair", "overall_shield", "quad", "coax"]
ShieldEnd = Literal["backshell_360", "pigtail", "floating"]
# The outer conductor of a coax carries the signal return, so it is bonded at both ends whatever the
# grounding concept of the project says about other shields (release 1.10, D-182).
COAX_SHIELD_END: ShieldEnd = "backshell_360"
PinRole = Literal["", "power", "return", "ground", "signal", "shield", "spare", "signal_ground"]
# `signal_ground` (format 3, D-242, design of 3.0.0 section 4.3): a pin that carries the ground
# reference of a signal interface (SGND). It is set by a person or an import only, never derived
# from a pin name, and the link checks treat it as they treat `ground`.
PinDirection = Literal["", "in", "out", "bidir"]  # "" = not set: the name and the type decide


class Pin(SparseEntity):
    OMIT_WHEN_DEFAULT: ClassVar[frozenset[str]] = frozenset(
        {"function", "contact_part", "role", "direction", "level", "current_a"}
    )

    id: PinId
    signal: Name | None = None
    contact_size: Name | None = None
    termination: Termination = "unspecified"
    locked: bool = False  # manual allocation that generation must never move
    interface_id: Id | None = None  # interface this pin was allocated for (set by generation)
    fixed: bool = (
        False  # signal fixed by the unit design (KiCad): interfaces connect to it, it never moves
    )
    function: Name | None = (
        None  # a person's words for what the pin does (1.4.0); no meaning to the tool
    )
    contact_part: Id | None = (
        None  # the contact (a library part of category contact) the cable side uses here (1.7.0)
    )
    role: PinRole = ""  # what the pin is for; empty = derived from the signal name (M2)
    direction: PinDirection = (
        ""  # which way the signal runs at this pin, seen from the device (1.9.0); empty = not set:
        # the link checks and the pairing proposal then take it from the interface types
    )
    level: Name | None = None  # the signal level from the device's ICD (`RS422-3V3`; format 3)
    # The current through the contact in operation, in amperes, as the device's ICD states it
    # (format 5, design of 5.0.0 section 5.1): only on a pin of a box connector; never assumed.
    current_a: CurrentA | None = None


MAX_ROWS = 64  # the most rows (or rings) a row layout has (format 4, design of 4.0.0 section 4.1)


class RowLayout(SparseEntity):
    """The row layout of a connector (format 4, D-250, design of 4.0.0 sections 1.1 and 4): the
    rows of its insert from the top of the face, each the pin names in order along the row. With
    `rings` each row is a ring of a circular insert, from the outer ring inwards, its pins in order
    round the ring, so that the last pin of a ring is next to its first. It is held by a connector
    part (`Part.row_layout`) and by a box connector whose insert differs from its part's
    (`Connector.row_layout`); `core/row_layout.py` works out the layout of a connector."""

    OMIT_WHEN_DEFAULT: ClassVar[frozenset[str]] = frozenset({"rings"})

    rows: Annotated[
        list[list[PinId]], Field(json_schema_extra={"minItems": 1, "maxItems": MAX_ROWS})
    ]
    rings: bool = False

    def names(self) -> list[str]:
        """Every pin name of the layout, row by row."""
        return [name for row in self.rows for name in row]

    @model_validator(mode="after")
    def _rows_are_a_layout(self) -> RowLayout:
        if not self.rows:
            raise ValueError("a row layout needs at least one row; leave the key out for none")
        if len(self.rows) > MAX_ROWS:
            raise ValueError(
                f"a row layout has at most {MAX_ROWS} rows; this one has {len(self.rows)}"
            )
        seen: dict[str, int] = {}  # a pin name, ignoring case (as pin names are unique), -> row
        for number, row in enumerate(self.rows, start=1):
            if not row:
                raise ValueError(f"row {number} is empty; leave it out")
            for name in row:
                was = seen.get(name.casefold())
                if was is not None:
                    where = (
                        f"twice in row {number}"
                        if was == number
                        else f"in row {was} and in row {number}"
                    )
                    raise ValueError(f"pin {name} is {where}")
                seen[name.casefold()] = number
        if len(seen) > MAX_PIN_COUNT:
            raise ValueError(
                f"a row layout names at most {MAX_PIN_COUNT} pins; this one names {len(seen)}"
            )
        return self


class Connector(SparseEntity):
    OMIT_WHEN_DEFAULT: ClassVar[frozenset[str]] = frozenset(
        {
            "label",
            "locked",
            "source_doc",
            "source_version",
            "source_link",
            "row_layout",
            "length_to",
        }
    )

    id: Id
    name: Name
    role: Role
    part_id: Id
    unit_id: Id | None = None  # box connectors only
    gender: Gender = "unspecified"
    keying: Name | None = None
    carries: list[Id] = []  # interface types this connector is meant for (empty = any)
    mates_with: Id | None = None  # cable connectors: the box connector this one plugs into
    pins: list[Pin] = []
    notes: Text = ""
    label: Name | None = (
        None  # text for the connector's label instead of its ID (a person's, 1.4.0)
    )
    locked: bool = (
        False  # a cable connector of a generated harness that a person edited: generation keeps
        # its part, gender, keying and pin details (workshop M3)
    )
    # Where the pinout of a box connector comes from (format 3, design of 3.0.0 section 4.1): the
    # interface control document by name, its version and a web link to it.
    source_doc: Name | None = None
    source_version: Name | None = None
    source_link: WebLink | None = None
    # The connector's own row layout (format 4, design of 4.0.0 section 3): a box connector only,
    # where its insert differs from its part's; every name is a pin of the connector.
    row_layout: RowLayout | None = None
    # Where the segments that end at this cable connector are measured to (format 5, design of
    # 5.0.0 section 4.2): `face` or `rear`; None follows the setting `model.length_reference`.
    length_to: LengthTo | None = None

    @model_validator(mode="after")
    def _length_to_on_a_cable_connector(self) -> Connector:
        if self.length_to is not None and self.role != "cable":
            raise ValueError(
                f"only a cable connector says where its lengths are measured to; {self.id} is a "
                f"connector of role {self.role}"
            )
        return self

    @model_validator(mode="after")
    def _current_on_a_device_pin(self) -> Connector:
        if self.unit_id is None:
            pin = next((p for p in self.pins if p.current_a is not None), None)
            if pin is not None:
                raise ValueError(
                    f"only a pin of a device connector has a current; pin {pin.id} of {self.id} "
                    "is on a connector of a harness"
                )
        return self

    @model_validator(mode="after")
    def _own_rows_name_own_pins(self) -> Connector:
        if self.row_layout is None:
            return self
        if self.unit_id is None:
            raise ValueError(
                f"only a box connector has its own row layout; {self.id} takes the rows of its "
                "part or of the box connector it plugs into"
            )
        pins = {p.id for p in self.pins}
        for name in self.row_layout.names():
            if name not in pins:
                raise ValueError(f"the row layout names pin {name}; {self.id} has no pin {name}")
        return self


# The four values of a generated wire that a person can set in place of the one generation chooses.
# Each can carry its own reason in `Wire.overrides` (S4, D-191 (3)).
OVERRIDABLE: tuple[str, ...] = ("gauge_awg", "part_id", "colour", "length_m")


class Wire(SparseEntity):
    OMIT_WHEN_DEFAULT: ClassVar[frozenset[str]] = frozenset(
        {"label", "note", "manual", "strip_a_mm", "strip_b_mm", "overrides"}
    )

    id: Id
    signal: Name | None = None
    from_connector: Id
    from_pin: PinId
    to_connector: Id
    to_pin: PinId
    gauge_awg: Awg | None = None
    part_id: Id | None = None
    colour: Name | None = None
    length_m: LengthM | None = None
    interface_id: Id | None = None
    locked: bool = False  # user-set gauge, colour, part and length: regeneration keeps them
    label: Name | None = None  # text for the wire labels instead of the signal name (a person's)
    note: Text = ""  # a person's remark; generation always keeps it
    manual: bool = False  # drawn by a person: generation keeps it as it is and never matches it
    strip_a_mm: LengthMm | None = None  # insulation stripped at the From end (a person's, 1.7.0)
    strip_b_mm: LengthMm | None = None  # insulation stripped at the To end (a person's, 1.7.0)
    # Why a person set a value of `OVERRIDABLE` in place of the one generation chooses: field name
    # -> the reason (never empty). Who and when are in the journal (`journal.jsonl`), never here, so
    # the file of a design holds no name and no time. A locked wire with no entry here is one from
    # before the reasons were kept ("locked, no reason recorded"): it keeps its meaning.
    overrides: dict[Name, Reason] = {}

    @model_validator(mode="after")
    def _overrides_are_recorded_overrides(self) -> Wire:
        for key in self.overrides:
            if key not in OVERRIDABLE:
                raise ValueError(f"'{key}' cannot be overridden (only {', '.join(OVERRIDABLE)})")
            if getattr(self, key) is None:
                raise ValueError(f"the override of '{key}' needs a value on the wire")
        if self.overrides and not self.locked:
            raise ValueError("a wire with an override must be locked")
        return self


class ShieldEndPlace(SparseEntity):
    """Where one end of a shield group lands (format 5, design of 5.0.0 sections 3.1 and 7.1): the
    cable connector at that end, the pin of it a pigtail lands on, and the backshell (an accessory
    of kind `backshell` on that connector) a 360 degree bond or a pigtail's lug is made in. The
    connector is stored with the pin, because the ends of a group follow its lowest wire ID and
    can swap; a swap is then found (`check`: `shield_end_moved`). Set by a person only."""

    OMIT_WHEN_DEFAULT: ClassVar[frozenset[str]] = frozenset({"pin", "backshell"})

    connector: Id
    pin: PinId | None = None
    backshell: Id | None = None  # the ID of an accessory of the harness

    @model_validator(mode="after")
    def _lands_somewhere(self) -> ShieldEndPlace:
        if self.pin is None and self.backshell is None:
            raise ValueError(
                f"the place of a shield end at {self.connector} names a pin, a backshell or both"
            )
        return self


# The ends of a shield group, the place of each, and the end it belongs to: ("a", at_a, end_a) ...
SHIELD_PLACE_KEYS: tuple[tuple[str, str, str], ...] = (
    ("a", "at_a", "end_a"),
    ("b", "at_b", "end_b"),
)


class ShieldGroup(SparseEntity):
    OMIT_WHEN_DEFAULT: ClassVar[frozenset[str]] = frozenset({"manual", "at_a", "at_b"})

    id: Id
    kind: ShieldKind
    wire_ids: list[Id]
    end_a: ShieldEnd = "floating"
    end_b: ShieldEnd = "floating"
    manual: bool = False  # made by a person (twisted, shielded or overall); generation keeps it
    # Where end A and end B land (format 5, design of 5.0.0 section 7): None is *not stated*. Set by
    # a person only; Generate keeps the place of an unchanged group and never fills one (F10).
    at_a: ShieldEndPlace | None = None
    at_b: ShieldEndPlace | None = None

    @model_validator(mode="after")
    def _places_fit_the_ends(self) -> ShieldGroup:
        """The rules of the file (design of 5.0.0 section 3.2, rule 4): no place on a twisted pair
        (it has no shield); none on a floating end; a pin only for a pigtail; a backshell only for a
        360 degree bond or a pigtail."""
        for which, key, end_key in SHIELD_PLACE_KEYS:
            place: ShieldEndPlace | None = getattr(self, key)
            if place is None:
                continue
            end: str = getattr(self, end_key)
            label = which.upper()
            if self.kind == "twisted_pair":
                raise ValueError(
                    f"a twisted pair has no shield, so {self.id} has no place of a shield end"
                )
            if end == "floating":
                raise ValueError(f"end {label} of {self.id} is floating, so it has no place")
            if place.pin is not None and end != "pigtail":
                raise ValueError(
                    f"only a pigtail lands on a pin; end {label} of {self.id} is {end}"
                )
        return self


class Splice(Entity):
    """The splice entry of formats 1 and 2: never created by any tool, kept readable, never written
    by this one (a splice is a connector of role `splice` since format 3). Integrity reports a
    non-empty list (`splice_stub`); the step from 2 to 3 keeps it as it is."""

    id: Id
    name: Name
    wire_ids: list[Id]


class BranchPoint(Entity):
    id: Id
    name: Name


class Segment(Entity):
    id: Id
    from_node: Id  # a connector or branch point of the same harness
    to_node: Id
    length_m: LengthM | None = None


AccessoryKind = Literal["sleeving", "heat_shrink", "label", "backshell", "other"]


class Accessory(Entity):
    """Something that goes on a harness besides its wires and connectors: sleeving, heat shrink, a
    label, a backshell (1.7.0). It says what, where (a connector or a wire of the harness, or the
    harness itself), in words how far from where, and how much. Nothing is computed from it."""

    id: Id
    kind: AccessoryKind
    part_id: Id | None = None  # a library part (sleeving, label, backshell ...), if there is one
    target: Id | None = None  # a connector or a wire of this harness; None means the harness
    position: Name | None = None  # in words: "50 mm from the P1 end"
    length_mm: LengthMm | None = None  # for sleeving and heat shrink: the length of one piece
    quantity: Annotated[int, Field(ge=1, le=9999)] = 1
    note: Text = ""


class Harness(SparseEntity):
    OMIT_WHEN_DEFAULT: ClassVar[frozenset[str]] = frozenset({"label", "accessories"})

    id: Id
    name: Name
    version: Version = "1.0.0"  # MAJOR.MINOR.PATCH (format 3; `revision`, a letter, in format 2)
    status: HarnessStatus = "draft"
    connectors: list[Connector] = []
    wires: list[Wire] = []
    splices: list[Splice] = []
    shields: list[ShieldGroup] = []
    branch_points: list[BranchPoint] = []
    segments: list[Segment] = []
    generated: bool = False  # created by generation (regeneration may replace it)
    group_key: str = ""  # segmentation key it was generated for
    interfaces: list[Id] = []  # interfaces this harness carries
    author: Name | None = None  # who put it into review (change control)
    checker: Name | None = None  # who checked it at release
    approver: Name | None = None  # who released it
    released_on: IsoDate | None = None  # date of the release (YYYY-MM-DD)
    notes: Text = ""
    label: Name | None = None  # text for the harness label instead of its name (a person's, 1.4.0)
    accessories: list[Accessory] = []  # sleeving, heat shrink, labels, backshells (1.7.0)
