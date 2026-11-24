# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""What the review of a link said before format 5, and says since, about a pin in several pairs of
one link (part C of the design of 5.0.0, `docs/ait/DESIGN_5.0_FORMAT_5.md` section 6.1).

Before format 5 each later pair of a pin of one link was the error `link_pin_reused` (*Pin 1 of
OBC-J01 is in two pairs of link L1. Keep one pair for it.*; `check` said *… more than once. A pin
belongs to one pair.*). Since format 5 such pairs are a junction or a parallel pair: the review
says `link_junction` (an info) for a junction a harness can be made from, and `link_pin_reused`
with the word *junction* for one it cannot. Every other finding is the one of before, in the
same order. The comparisons with the verbatim copies of 1.8.1 and 4.3.0 leave out these findings
on both sides, and only these."""

import dataclasses
from collections.abc import Iterable
from typing import Any

OLD_REVIEW = "is in two pairs of link"  # the review of 1.8.1 to 4.4.x
OLD_CHECK = "more than once. A pin belongs to one pair."  # the integrity check of 1.8.1 to 4.4.x


def _junction(f: Any) -> bool:
    return f.code == "link_junction" or (f.code == "link_pin_reused" and "junction" in f.message)


def review_as_before(findings: Iterable[Any]) -> list[tuple[Any, ...]]:
    """The findings of the review of 5.0.0 without those about the pairs of a junction."""
    return [dataclasses.astuple(f) for f in findings if not _junction(f)]


def old_review_without_pairs_again(findings: Iterable[Any]) -> list[tuple[Any, ...]]:
    """The findings of an older review without its errors for a pin in two pairs of one link."""
    return [
        dataclasses.astuple(f)
        for f in findings
        if not (f.code == "link_pin_reused" and OLD_REVIEW in f.message)
    ]


def old_check_without_pairs_again(issues: Iterable[Any]) -> list[Any]:
    """The issues of an older integrity check without its errors for a pin paired twice in a link."""
    return [i for i in issues if not (i.code == "link_pin_reused" and OLD_CHECK in i.message)]
