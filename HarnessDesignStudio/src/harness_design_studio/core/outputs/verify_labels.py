# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The independent verifier's own copy of the label texts (D-198, D-255; design of 4.1.0, section
3.6), moved here from `verify.py` word for word so that `verify.py` and `verify_production.py` can
both use it (`verify.py` imports `verify_plan.py`, so the copy could not stay in `verify.py`
without an import cycle once `verify_production.py` needs it).

The label formats (`model.label_format`: `standard`, `compact`, `descriptive`, `custom` and, since
4.1.0, `harness_device_connector`, design of 4.1.0 section 4.4) and the template rules (`_LABEL_*`, `_label_template_usable`, `_fill_label`) are stated here a second time,
never imported from `core/label_format.py` or `tables.py`; `tests/test_label_format_outputs.py`
reads the imports of this module and compares the copy with the core's."""

import re

from harness_design_studio.core import settings
from harness_design_studio.core.model import Connector, Harness, Project, Wire
from harness_design_studio.core.model.physical import LOOSE_ROLE

# A loose cable end, worded independently of tables.py, drawing.py and buildsheet.py (D-201).
_OPEN_END = "open end"

# The label formats and the template rules, stated again here, never imported from
# core/label_format.py or tables.py (D-198).
_LABEL_FORMATS = ("standard", "compact", "descriptive", "custom", "harness_device_connector")
_LABEL_DEFAULT = "standard"
_LABEL_FIELDS = {
    "wire": ("harness", "wire", "signal", "name", "interface", "emc", "end", "from", "to"),
    "connector": ("harness", "connector", "name", "mates", "device", "mates_name"),
}
_LABEL_TEMPLATE_KEYS = {"wire": "label_wire_template", "connector": "label_connector_template"}
_LABEL_TEMPLATE_MAX = 200
_LABEL_TOKEN = re.compile(r"\{\{|\}\}|\{([^{}]*)\}")


def _open(c: Connector) -> bool:
    return c.role == LOOSE_ROLE


def _emc_class(project: Project, w: Wire) -> str:
    i = project.interfaces.get(w.interface_id or "")
    t = project.interface_types.get(i.type_id) if i else None
    return (t.emc_class if t else None) or ""


def _label_format(project: Project) -> str:
    value = settings.effective(project, "model", "label_format").value
    return str(value) if value in _LABEL_FORMATS else _LABEL_DEFAULT


def _label_template_usable(text: str, kind: str) -> bool:
    """A template is used when it is at most `_LABEL_TEMPLATE_MAX` characters, names only fields
    of its kind and has no single brace (`{{` and `}}` are braces)."""
    if len(text) > _LABEL_TEMPLATE_MAX:
        return False
    fields = _LABEL_FIELDS[kind]
    if any(
        m.group(1) is not None and m.group(1) not in fields for m in _LABEL_TOKEN.finditer(text)
    ):
        return False
    return not re.search(r"[{}]", _LABEL_TOKEN.sub("", text))


def _label_template(project: Project, kind: str) -> str | None:
    """The template of `kind` in force, or None (not set, empty or not usable: the standard text)."""
    value = settings.effective(project, "model", _LABEL_TEMPLATE_KEYS[kind]).value
    if not isinstance(value, str) or not value.strip() or not _label_template_usable(value, kind):
        return None
    return value


def _fill_label(text: str, values: dict[str, str]) -> str:
    """Every `{field}` replaced by its text, `{{` and `}}` by a brace; nothing else is read."""
    return _LABEL_TOKEN.sub(
        lambda m: m.group(0)[0] if m.group(1) is None else values[m.group(1)], text
    )


def _connector_label_text(project: Project, h: Harness, c: Connector, fmt: str) -> str:
    box = project.connectors.get(c.mates_with or "")
    name = c.label or ((box.label or "") if box is not None else "")
    mates = f"{c.id} {_OPEN_END}" if _open(c) else f"{c.id} mates {c.mates_with or '-'}"
    if fmt == "compact":
        return mates
    if fmt == "harness_device_connector":
        # The harness, the device and the name the device gives its connector, colon between, and
        # never the person's label. With no device connector to name, the harness and the plug's
        # own ID; a loose end says so after its ID.
        if _open(c):
            return h.id + ":" + c.id + " " + _OPEN_END
        if box is not None:
            return ":".join((h.id, box.unit_id or "", box.name))
        return ":".join((h.id, c.id))
    if fmt == "descriptive" and box is not None and box.unit_id:
        mates = f"{mates} of {box.unit_id}"
    if fmt == "custom" and (tpl := _label_template(project, "connector")) is not None:
        values = {
            "harness": h.id, "connector": c.id, "name": name,
            "mates": _OPEN_END if _open(c) else (c.mates_with or "-"),
            "device": (box.unit_id or "") if box is not None else "",
            "mates_name": _OPEN_END if _open(c) else (box.name if box is not None else "-"),
        }  # fmt: skip
        return _fill_label(tpl, values)
    return f"{name} ({mates})" if name else mates


def _wire_label_texts(project: Project, h: Harness, w: Wire, fmt: str) -> tuple[str, str]:
    far, near = f"{w.to_connector}.{w.to_pin}", f"{w.from_connector}.{w.from_pin}"
    wname = w.label or w.signal or ""
    head = f"{w.id} {wname}" if wname else w.id
    emc = _emc_class(project, w)
    tag = f" [EMC {emc}]" if emc else ""
    if fmt == "compact":
        return f"{w.id} to {far}", f"{w.id} to {near}"
    if fmt == "descriptive" and (i := project.interfaces.get(w.interface_id or "")) is not None:
        head = f"{head} ({i.id} {i.name})"
    if fmt == "custom" and (tpl := _label_template(project, "wire")) is not None:
        values = {
            "harness": h.id, "wire": w.id, "signal": w.signal or "", "name": wname,
            "interface": w.interface_id or "", "emc": emc,
        }  # fmt: skip
        return (
            _fill_label(tpl, {**values, "end": "A", "from": near, "to": far}),
            _fill_label(tpl, {**values, "end": "B", "from": far, "to": near}),
        )
    return f"{head} to {far}{tag}", f"{head} to {near}{tag}"
