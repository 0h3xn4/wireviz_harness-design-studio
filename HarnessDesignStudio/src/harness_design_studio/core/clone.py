# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""A scratch copy of a project with operations applied (moved out of `edit.py` in 2.1.0, D-237).

`generate/engine.py` needs it and `edit.py` asks the engine for the room on a connector, so the
function lives here, where neither module has to import the other. `edit.clone_with` still names
it for every other caller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .commands import Op
    from .model import Project


def clone_with(project: Project, ops: list[Op]) -> Project:
    """A scratch copy of `project` with `ops` applied (entities are immutable, so copies are
    cheap)."""
    from copy import copy

    from .commands import apply_ops

    dup = copy(project)
    for name in (
        "units",
        "interface_types",
        "interfaces",
        "links",
        "connectors",
        "harnesses",
        "parts",
        "placements",
        "waivers",
        "baselines",
        "changelog",
        "import_records",
        "asbuilt",
        "diagram_marks",
        "config",
    ):
        setattr(dup, name, dict(getattr(project, name)))
    dup.zones = list(project.zones)
    apply_ops(dup, ops)
    return dup
