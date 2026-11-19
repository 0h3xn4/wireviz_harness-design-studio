# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Parts library: real, qualified parts the plans refer to."""

from typing import Annotated, ClassVar, Literal

from pydantic import Field, model_validator

from harness_design_studio.core.ids import Id

from .base import MAX_PIN_COUNT, Entity, IsoDate, Name, NonNegative, SparseEntity, Text, WebLink
from .physical import RowLayout

PartCategory = Literal["connector", "contact", "backshell", "wire", "sleeving", "label", "splice"]
PART_CATEGORIES: tuple[PartCategory, ...] = (
    "connector", "contact", "backshell", "wire", "sleeving", "label", "splice",
)  # fmt: skip
# `splice` (format 3, owner answer B3 of the design of 2.3.0): the part of a splice, `pin_count` the
# number of its nodes. Its file `library/splice.json` is written only while the library holds one,
# so a project without splices keeps its files and its model hash.
SPARSE_CATEGORIES: frozenset[PartCategory] = frozenset({"splice"})
Approval = Literal["approved", "pending", "not_approved"]


class Part(SparseEntity):
    OMIT_WHEN_DEFAULT: ClassVar[frozenset[str]] = frozenset(
        {"tool", "conductors", "link", "row_layout"}
    )

    id: Id
    category: PartCategory
    manufacturer: Name | None = None
    part_number: Name | None = None
    specification: Name | None = None
    description: Name | None = None
    approval: Approval = "pending"
    unverified: bool = False  # example data that no engineer has checked
    pin_count: Annotated[int, Field(ge=1, le=MAX_PIN_COUNT)] | None = None
    mates_with: Id | None = None  # connector parts: the mating counterpart (e.g. male for female)
    mass_g: NonNegative | None = None
    mass_per_m_g: NonNegative | None = None
    ratings: dict[Name, NonNegative] = {}
    notes: Text = ""
    tool: Name | None = None  # the crimp tool or its setting for a contact part (a person's, 1.7.0)
    # Wire parts: how many conductors one metre of the part carries (a twisted pair is 2). Every
    # wire that names the part is one conductor of it, so the bill of materials and the mass count
    # the sum of their lengths divided by this number: the metres of the cable (1.11, D-188).
    conductors: Annotated[int, Field(ge=1, le=64)] = 1
    link: WebLink | None = None  # the part's page on the web (a datasheet, a shop; format 3)
    # The row layout of the part's insert (format 4, design of 4.0.0 sections 3 and 4): shared by
    # every connector of the part that has no own layout. Connector parts only.
    row_layout: RowLayout | None = None

    @model_validator(mode="after")
    def _rows_fit_the_part(self) -> Part:
        if self.row_layout is None:
            return self
        if self.category != "connector":
            raise ValueError(
                f"only a connector part has a row layout; {self.id} is a part of category "
                f"{self.category}"
            )
        named = len(self.row_layout.names())
        if self.pin_count is not None and named > self.pin_count:
            raise ValueError(f"the row layout names {named} pins; the part has {self.pin_count}")
        return self


class LibraryInfo(Entity):
    """Where the parts of the library come from. `source` and `date` are entered by a person (or
    the import records the file name); the tool never reads a clock into project data."""

    name: Name = "Project parts library"
    version: Name = "0"
    source: Name | None = None  # for example the file or database the parts were imported from
    date: IsoDate | None = None  # date of that data, YYYY-MM-DD
