# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""JSON Schemas of the project files, made from the model itself.

For people who edit project files by hand in an editor that understands JSON Schema (completion,
checks, hover text). Nothing is downloaded; the schemas come from the same strict models the
loader uses, so they cannot drift from the format.

Two files that are not part of the project format have a schema too (D-240): a one-device file of a
device library (`NAME.device.json`) and the list of a project's device libraries
(`device-libraries.json` at the project root).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model

from harness_design_studio.core import device_library, library_pointer
from harness_design_studio.core.model import (
    PART_CATEGORIES,
    AsBuiltRecord,
    Baseline,
    ChangeEntry,
    ConfigFile,
    Connector,
    DiagramMark,
    GenerationRecord,
    Harness,
    ImportRecord,
    InterfaceInstance,
    InterfaceType,
    JournalEntry,
    LibraryInfo,
    Link,
    Part,
    Placement,
    ProjectMeta,
    Unit,
    Waiver,
)


def _list_file(name: str, key: str, item: type[BaseModel]) -> type[BaseModel]:
    fields: dict[str, Any] = {key: (list[item], ...)}  # type: ignore[valid-type]
    return create_model(name, **fields)


def _layout_file() -> type[BaseModel]:
    fields: dict[str, Any] = {"zones": (list[str], ...), "placements": (list[Placement], ...)}
    return create_model("LayoutFile", **fields)


_STRICT = ConfigDict(extra="forbid")


def _const(value: str | int) -> Any:
    return Field(json_schema_extra={"const": value})


def _device_file() -> type[BaseModel]:
    """A `NAME.device.json` of a device library: exactly one device (D-240)."""
    record: dict[str, Any] = {"unit": (Unit, ...), "connectors": (list[Connector], [])}
    device = create_model("DeviceRecord", __config__=_STRICT, **record)
    fields: dict[str, Any] = {
        "format": (str, _const(device_library.FORMAT)),
        "version": (int, _const(device_library.VERSION)),
        "devices": (list[device], Field(min_length=1, max_length=1)),
        "parts": (list[Part], []),
        "interface_types": (list[InterfaceType], []),
    }
    return create_model("DeviceFile", __config__=_STRICT, **fields)


def _device_libraries() -> type[BaseModel]:
    """`device-libraries.json` at the project root: the project's device libraries (D-240)."""
    pattern = r"^(?![~/])(?!.*//)(?!.*/$)[^\\:\x00-\x1f\x7f]+$"
    entry: dict[str, Any] = {
        "path": (
            str,
            Field(
                max_length=library_pointer.MAX_PATH,
                description="A folder relative to the project folder, with '/'.",
                json_schema_extra={"pattern": pattern},
            ),
        )
    }
    library = create_model("DeviceLibrary", __config__=_STRICT, **entry)
    fields: dict[str, Any] = {
        "format": (str, _const(library_pointer.FORMAT)),
        "version": (int, _const(library_pointer.VERSION)),
        "device_libraries": (
            list[library],
            Field(max_length=library_pointer.MAX_LIBRARIES),
        ),
    }
    return create_model("DeviceLibrariesFile", __config__=_STRICT, **fields)


# (schema name, model, description) of the files outside the project format
def _other_kinds() -> list[tuple[str, type[BaseModel], str]]:
    return [
        (
            "device-file",
            _device_file(),
            "Harness Design Studio device library file NAME.device.json (one device; not part "
            "of a project). Generated from the model.",
        ),
        (
            "device-libraries",
            _device_libraries(),
            "Harness Design Studio device-libraries.json: the device libraries of a project "
            "(not part of the project format). Generated from the model.",
        ),
    ]


# (schema name, file pattern, model)
def _kinds() -> list[tuple[str, str, type[BaseModel]]]:
    return [
        ("project", "project.json", ProjectMeta),
        ("config", "config/*.json", ConfigFile),
        ("library-info", "library/manifest.json", LibraryInfo),
        *[
            ("parts", f"library/{category}.json", _list_file("PartsFile", "parts", Part))
            for category in PART_CATEGORIES
        ],  # the parts files only: library/manifest.json has its own schema
        (
            "interface-types",
            "logical/interface_types.json",
            _list_file("InterfaceTypesFile", "interface_types", InterfaceType),
        ),  # fmt: skip
        ("layout", "logical/layout.json", _layout_file()),
        ("links", "logical/links.json", _list_file("LinksFile", "links", Link)),
        ("units", "logical/units/*.json", _list_file("UnitsFile", "units", Unit)),
        (
            "interfaces",
            "logical/interfaces/*.json",
            _list_file("InterfacesFile", "interfaces", InterfaceInstance),
        ),  # fmt: skip
        (
            "connectors",
            "physical/connectors/*.json",
            _list_file("ConnectorsFile", "connectors", Connector),
        ),  # fmt: skip
        ("harness", "physical/harnesses/*.json", Harness),
        ("generation", "generated/generation.json", GenerationRecord),
        ("waivers", "waivers.json", _list_file("WaiversFile", "waivers", Waiver)),
        ("journal", "journal.jsonl", JournalEntry),  # one entry per line (M7a, D-228)
        ("changelog", "changelog.json", _list_file("ChangeFile", "changelog", ChangeEntry)),
        (
            "import-records",
            "imports/records.json",
            _list_file("ImportRecordsFile", "imports", ImportRecord),
        ),  # fmt: skip
        (
            "asbuilt",
            "asbuilt/records.json",
            _list_file("AsBuiltRecordsFile", "asbuilt", AsBuiltRecord),
        ),  # fmt: skip
        (
            "diagram-marks",
            "diagram/marks.json",
            _list_file("DiagramMarksFile", "marks", DiagramMark),
        ),  # fmt: skip
        ("baseline", "baselines/*/*.json", Baseline),
    ]


def schemas() -> dict[str, dict[str, Any]]:
    """Schema name to JSON Schema (draft 2020-12, as pydantic writes it)."""
    out = {}
    for name, pattern, model in _kinds():
        if name in out:
            continue  # one schema for the six parts files
        schema = model.model_json_schema()
        schema.setdefault("title", name)
        shown = "library/<category>.json" if name == "parts" else pattern
        schema["description"] = (
            f"Harness Design Studio project file {shown}. Generated from the model."
            if name != "journal"
            else f"One line of the Harness Design Studio project file {shown} (one entry per "
            "line). Generated from the model."
        )
        out[name] = schema
    for name, model, description in _other_kinds():
        schema = model.model_json_schema()
        schema["title"] = name
        schema["description"] = description
        out[name] = schema
    from harness_design_studio.core.extensions import schema as extension_schema

    out.update(extension_schema.schemas())  # S8: the two files of an extensions folder
    return out


def editor_settings() -> dict[str, Any]:
    """A `.vscode/settings.json` fragment that maps the files of a project to the schemas, with
    paths relative to the project folder (the schemas folder placed inside it)."""
    return {
        "json.schemas": [
            {"fileMatch": [f"/{pattern}"], "url": f"./schemas/{name}.schema.json"}
            for name, pattern, _ in _kinds()
        ]
        + [
            {
                "fileMatch": ["/extensions/*.json", "!/extensions/enabled.json"],
                "url": "./schemas/extension.schema.json",
            },
            {
                "fileMatch": ["/extensions/enabled.json"],
                "url": "./schemas/extensions-enabled.schema.json",
            },
            {
                "fileMatch": [f"/{library_pointer.FILE}"],
                "url": "./schemas/device-libraries.schema.json",
            },
        ]
    }


def dumps(doc: object) -> str:
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"
