# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Has the design changed since the harnesses were generated? A hash comparison, no generation
logic, so the verifier and the release checks can use it without importing the generator."""

import hashlib
import json
from typing import Any

from .model import ConfigFile, Project
from .model.config import ABOUT_KEY
from .model.physical import TBD_PART_ID
from .vcs.roles import CONFIG_FILE as ROLES_FILE
from .vcs.roles import CONFIG_KEY as ROLES_KEY

# Keys that generation does not read (who may release, what a release asks of the as-built records,
# the points of the review checklist (4.3.0), the project's signal map, which only the imports
# apply (4.4.0), what the as-built report tolerates): switching one on, off or to another value
# does not make the harness plans out of date, and without any of them the dump is what it always
# was. `naming.far_device_names` (4.4.0) is not here: Generate reads it, so turning it on makes the
# harness plans out of date until the next Generate.
NOT_READ_BY_GENERATION: dict[str, tuple[str, ...]] = {
    ROLES_FILE: (ROLES_KEY, "release_requires_asbuilt", "review_checklist", "signal_map"),
    "generation": ("asbuilt_cut_tolerance_mm", "asbuilt_strip_tolerance_mm"),
}


def _config_dump(c: ConfigFile) -> dict[str, Any]:
    """One config file as generation reads it, without the keys it does not read
    (`NOT_READ_BY_GENERATION`; `release_distinct_roles`, 1.9.0, was the first). The comments of the
    file (`_about`) are not an input either."""
    d = c.model_dump(mode="json")
    d.pop(ABOUT_KEY, None)
    fields = d["values"].get("fields") if c.name == "titleblock" else None
    if isinstance(fields, list) and "version" in fields:
        # the title block field `version` was `revision` in format 2 (D-242): it is read under its
        # old name, so that the upgrade to format 3 leaves the harness plans current (generation
        # does not read the title block; the hash of its inputs is what it was)
        d["values"] = {
            **d["values"],
            "fields": ["revision" if f == "version" else f for f in fields],
        }
    skip = NOT_READ_BY_GENERATION.get(c.name, ())
    if any(k in c.values for k in skip):
        d["values"] = {k: v for k, v in d["values"].items() if k not in skip}
    return d


def input_hash(project: Project) -> str:
    """Hash of everything generation reads. Outputs (generated pins, wires) are excluded."""

    def dump(objs: Any) -> list[object]:
        return [o.model_dump(mode="json") for o in sorted(objs, key=lambda x: x.id)]

    boxes = []
    for c in sorted(project.connectors.values(), key=lambda x: x.id):
        d = c.model_dump(mode="json")
        # the current of a pin (format 5) is not an input: Generate sizes a wire from its
        # interface's current (design of 5.0.0, F5), so a pin current leaves the plans current
        d["pins"] = [
            {
                **p.model_dump(mode="json", exclude={"current_a"}),
                "interface_id": None,
                "signal": p.signal if (p.locked or p.fixed or p.interface_id is None) else None,
            }
            for p in c.pins
        ]
        boxes.append(d)
    generated = [h for h in project.harnesses.values() if h.generated]
    payload: dict[str, Any] = {
        # the check of a device (format 5, design of 5.0.0 section 8.3) is not read by Generate
        "units": [
            u.model_dump(mode="json", exclude={"checked"})
            for u in sorted(project.units.values(), key=lambda x: x.id)
        ],
        "interfaces": dump(project.interfaces.values()),
        "interface_types": dump(project.interface_types.values()),
        # the library part of a loose end is added by the first cable a person draws out of a port;
        # Generate never reads it, so it must not make the plans look out of date
        "parts": dump(x for x in project.parts.values() if x.id != TBD_PART_ID),
        "zones": list(project.zones),
        # the harness plan's settings (format 3, design of 3.0.0 section 6) are read by the plan
        # only: a new colour code must not make the harnesses look out of date
        "config": {
            n: _config_dump(c) for n, c in sorted(project.config.items()) if n != "harness_plan"
        },
        "box_connectors": boxes,
        "locked_wires": sorted(
            (w.model_dump(mode="json") for h in generated for w in h.wires if w.locked),
            key=lambda d: d["id"],
        ),
        "segment_lengths": {
            h.id: sorted((s.id, s.length_m) for s in h.segments) for h in generated
        },
    }
    # Interfaces that manual harnesses route are left out of generation. Only added when there are
    # any, so a project without manual harnesses keeps its hash. Never the release status.
    manual = sorted(
        {
            w.interface_id
            for h in project.harnesses.values()
            if not h.generated
            for w in h.wires
            if w.interface_id
        }
    )
    if manual:
        payload["manual_interfaces"] = manual
    # Where the segments of a generated harness end at a cable connector (format 5, design of 5.0.0
    # section 4.2): Generate takes the depth of a face end off each wire. Only added when a cable
    # connector says it, so a project without data of format 5 keeps its hash.
    length_to = sorted(
        (h.id, c.mates_with or c.id, c.length_to)
        for h in generated
        for c in h.connectors
        if c.length_to is not None
    )
    if length_to:
        payload["length_to"] = length_to
    # and the backshells on a face end, whose depth is taken off as well (the rule of
    # `generate.lengths.face_ends`, stated here so that this module imports no generator)
    from harness_design_studio.core import settings

    reference = settings.choice(project, "model", "length_reference")
    shells = sorted(
        (h.id, a.id, a.target or "", a.part_id or "")
        for h in generated
        for faces in [
            {
                c.id
                for c in h.connectors
                if c.role == "cable" and (c.length_to or reference) == "face"
            }
        ]
        if faces
        for a in h.accessories
        if a.kind == "backshell" and a.target in faces
    )
    if shells:
        payload["face_backshells"] = shells
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def generation_status(project: Project) -> str:
    """ "none" (never generated), "current" or "stale" (the model changed since)."""
    if project.generation is None:
        return "none"
    return "current" if project.generation.input_hash == input_hash(project) else "stale"
