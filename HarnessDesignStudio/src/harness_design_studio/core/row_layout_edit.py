# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The edits of a row layout (format 4, D-251; design of 4.0.0 sections 3, 9 and 10, pull
request 2): the plans the editor, the command line and the scripting interface call.

    ops = plan_set_row_layout(project, layout, part="EX-MICROD-21-F")   # the rows of a part
    ops = plan_set_row_layout(project, layout, connector="DEV1-J1")     # a box connector's own
    ops = plan_clear_row_layout(project, connector="DEV1-J1")           # back to the part's rows
    ops = plan_share_with_part(project, "DEV1-J1")                      # Use for every connector

Each plan is pure: it returns the operations of one undo step (`History.execute`), or `[]` when
nothing changes, and raises `EditError` with a plain sentence for an edit that cannot be done. The
journal records the change when the project is saved, as for every edit (`core/journal.py`). A
layout is device and library data, not harness data: a release does not lock it (section 3; the
part's `row_layout` is among the fields a release leaves editable, `vcs/locks.py`). Only a box
connector has rows of its own; a cable connector takes the rows of its part or of the box
connector it plugs into (`core/row_layout.layout_of`).
"""

from pydantic import ValidationError

from .commands import Op, Put
from .edit import EditError
from .model import Connector, Part, Project, RowLayout, evolve
from .row_layout import layout_text

__all__ = ["plan_clear_row_layout", "plan_set_row_layout", "plan_share_with_part"]


def _writable(project: Project) -> None:
    if project.read_only:
        raise EditError("This project is read-only (saved by a newer tool version). Use Save as.")


def _first_message(exc: ValidationError) -> str:
    message = str(exc.errors()[0].get("msg", ""))
    return message.removeprefix("Value error, ")


def _part(project: Project, part_id: str) -> Part:
    part = project.parts.get(part_id)
    if part is None:
        raise EditError(f"Part '{part_id}' does not exist.")
    if part.category != "connector":
        raise EditError(
            f"Part {part_id} is a {part.category} part; only a connector part has rows."
        )
    return part


def _box(project: Project, connector_id: str) -> Connector:
    c = project.connectors.get(connector_id)
    if c is not None and c.unit_id is not None:
        return c
    if c is None and not any(
        x.id == connector_id for h in project.harnesses.values() for x in h.connectors
    ):
        raise EditError(f"'{connector_id}' is not a connector of the project.")
    raise EditError(
        f"{connector_id} is a connector of a harness: it has no rows of its own and takes the "
        "rows of its part or of the device connector it plugs into."
    )


def _target(part: str | None, connector: str | None) -> None:
    if (part is None) == (connector is None):
        raise EditError("Name a part or a connector, not both.")


def _with_rows[E: (Part, Connector)](obj: E, layout: RowLayout | None) -> E:
    try:
        return evolve(obj, row_layout=layout)
    except ValidationError as exc:
        raise EditError(f"The rows cannot be stored on {obj.id}: {_first_message(exc)}.") from None


def plan_set_row_layout(
    project: Project,
    layout: RowLayout,
    *,
    part: str | None = None,
    connector: str | None = None,
) -> list[Op]:
    """Give a connector part, or a box connector, the row layout `layout` (rows and the ring
    mark). The rules of the files (section 4.2) are checked as the loader checks them: on a part
    at most its pin count of names, on a box connector only its own pins. `[]` when it has these
    rows already."""
    _writable(project)
    _target(part, connector)
    obj: Part | Connector = (
        _part(project, part) if part is not None else _box(project, connector or "")
    )
    if obj.row_layout == layout:
        return []
    if isinstance(obj, Part):
        return [Put("parts", _with_rows(obj, layout))]
    return [Put("connectors", _with_rows(obj, layout))]


def plan_clear_row_layout(
    project: Project, *, part: str | None = None, connector: str | None = None
) -> list[Op]:
    """Remove the rows of a part, or the own rows of a box connector (*Back to the part's rows*:
    the connector then takes the rows of its part, if it has any). `[]` when there are none."""
    _writable(project)
    _target(part, connector)
    if part is not None:
        p = _part(project, part)
        return [Put("parts", _with_rows(p, None))] if p.row_layout is not None else []
    c = _box(project, connector or "")
    return [Put("connectors", _with_rows(c, None))] if c.row_layout is not None else []


def plan_share_with_part(project: Project, connector_id: str) -> list[Op]:
    """*Use for every connector of this part* (`pin-rows --to-part`): move the own rows of a box
    connector to its part, and clear the own rows of every box connector of that part that equal
    them (the rows and the ring mark; the order inside a row counts). Refused when the connector
    has no rows of its own, or when the part has other rows; when the part has these rows already,
    only the equal own rows are cleared. One undo step."""
    _writable(project)
    c = _box(project, connector_id)
    layout = c.row_layout
    if layout is None:
        raise EditError(f"{c.id} has no rows of its own to give to its part.")
    part = _part(project, c.part_id)
    ops: list[Op] = []
    if part.row_layout is not None and part.row_layout != layout:
        raise EditError(
            f"Part {part.id} has other rows ({layout_text(part.row_layout)}). Clear them first, "
            f"or keep the rows of {c.id} as its own."
        )
    if part.row_layout is None:
        ops.append(Put("parts", _with_rows(part, layout)))
    for other in sorted(project.connectors.values(), key=lambda x: x.id):
        if other.part_id == part.id and other.unit_id is not None and other.row_layout == layout:
            ops.append(Put("connectors", _with_rows(other, None)))
    return ops
