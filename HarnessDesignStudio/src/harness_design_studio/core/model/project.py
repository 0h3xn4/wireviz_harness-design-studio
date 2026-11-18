# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""In-memory project: the single mutable container. Change it only through `commands`."""

from dataclasses import dataclass, field
from typing import Annotated, Any, ClassVar

from pydantic import Field

from harness_design_studio.core.ids import Id

from .asbuilt import AsBuiltRecord
from .base import Entity, Label, Name, SparseEntity, Text
from .config import ConfigFile, default_configs
from .generation import GenerationRecord
from .imports import ImportRecord
from .journal import Journal
from .library import LibraryInfo, Part
from .logical import InterfaceInstance, InterfaceType, Link, Unit
from .physical import Connector, Harness
from .review import Baseline, ChangeEntry, DiagramMark, Placement, Waiver

# Format 3 since D-242 (the versions MAJOR.MINOR.PATCH with the keys `version`, and the fields of
# the harness plan; design of 3.0.0 section 4). Format 2 (D-226) is frozen at the 2.0.0 tag.
SCHEMA_VERSION = 3
DEFAULT_ZONES = ("panel-A", "panel-B")
MAX_CONTACT_LINES = 8


class ContactLine(Entity):
    """One line of the contact information on the Cover of a harness plan: `Phone`, `+49 …`."""

    label: Name
    value: Label = ""


class PlanDocument(SparseEntity):
    """The document data of one harness's plan (the Cover of `<ID>_plan.ods`, Q25): each text is
    left out while it is empty. `version` is the plan document's own version, a person's text, not
    the harness version."""

    OMIT_WHEN_DEFAULT: ClassVar[frozenset[str]] = frozenset(
        {"number", "version", "release", "title"}
    )

    number: Label = ""
    version: Label = ""
    release: Label = ""
    title: Label = ""


class DocumentInfo(SparseEntity):
    """The document data of the harness plans (format 3, design of 3.0.0 section 4.4): the system
    code, title, company and contact lines are the same in every plan of the project; `plans` holds
    what belongs to one harness's plan, by harness ID. Set by a person only; it goes into the Cover
    of the plans and nowhere else. Each part is left out while it is empty."""

    OMIT_WHEN_DEFAULT: ClassVar[frozenset[str]] = frozenset(
        {"system", "title", "company", "contact", "plans"}
    )

    system: Label = ""
    title: Label = ""
    company: Label = ""
    contact: Annotated[list[ContactLine], Field(max_length=MAX_CONTACT_LINES)] = []
    plans: dict[Id, PlanDocument] = {}


class ProjectMeta(SparseEntity):
    # sparse for `document` only (format 3), so that `project.json` keeps its bytes apart from the
    # number while a project has no document data
    OMIT_WHEN_DEFAULT: ClassVar[frozenset[str]] = frozenset({"document"})

    name: Name = "Untitled project"
    description: Text = ""
    schema_version: Annotated[int, Field(ge=1)] = SCHEMA_VERSION
    tool_version: str = ""  # version of the tool that last saved the project
    document: DocumentInfo | None = None  # the Cover of the harness plans (format 3)


@dataclass
class QuarantinedItem:
    """Data that could not be loaded. It is reported and kept, never silently dropped."""

    file: str
    kind: str
    reason: str
    raw: Any


@dataclass
class Project:
    meta: ProjectMeta = field(default_factory=ProjectMeta)
    library_info: LibraryInfo = field(default_factory=LibraryInfo)
    parts: dict[str, Part] = field(default_factory=dict)
    interface_types: dict[str, InterfaceType] = field(default_factory=dict)
    units: dict[str, Unit] = field(default_factory=dict)
    interfaces: dict[str, InterfaceInstance] = field(default_factory=dict)
    links: dict[str, Link] = field(default_factory=dict)  # pin-to-pin links of device connectors
    connectors: dict[str, Connector] = field(default_factory=dict)  # box connectors only
    harnesses: dict[str, Harness] = field(default_factory=dict)
    zones: list[str] = field(default_factory=lambda: list(DEFAULT_ZONES))
    placements: dict[str, Placement] = field(default_factory=dict)
    waivers: dict[str, Waiver] = field(default_factory=dict)
    baselines: dict[str, Baseline] = field(default_factory=dict)
    changelog: dict[str, ChangeEntry] = field(default_factory=dict)
    # what each import read, dropped and converted (imports/records.json); not in the model hash
    import_records: dict[str, ImportRecord] = field(default_factory=dict)
    # what was built and measured (asbuilt/records.json, S9): optional like the journal and the
    # import records, so a project that has none has no such file; not in the model hash
    asbuilt: dict[str, AsBuiltRecord] = field(default_factory=dict)
    # what the person moved in the diagram off its automatic place (diagram/marks.json): optional,
    # not in the model hash
    diagram_marks: dict[str, DiagramMark] = field(default_factory=dict)
    config: dict[str, ConfigFile] = field(default_factory=default_configs)
    generation: GenerationRecord | None = None
    # The change journal (S4): None for a project that has none; the project has one if and only if
    # it has the file journal.jsonl (journal.json in format 1). Appended to when the project is
    # saved (`core.journal`).
    journal: Journal | None = None
    quarantine: list[QuarantinedItem] = field(default_factory=list)
    quarantine_files: dict[str, bytes] = field(default_factory=dict)
    read_only: bool = False  # written by a newer tool version
    migrated_from: int | None = None
    # what the project's extensions/ folder offers (S8): set by the loader from the folder, never
    # stored in the project files; None for a project without that folder
    extensions: Any = field(default=None, compare=False, repr=False)
    # release records ("baselines:<id>", "changelog:<id>") that a save has written; undo must not
    # take these away again (set by save_project, not stored in the project files)
    saved_records: frozenset[str] = field(default_factory=frozenset, compare=False, repr=False)

    @property
    def recovered(self) -> bool:
        """True if something could not be loaded; such a project cannot overwrite its folder."""
        return bool(self.quarantine or self.quarantine_files)

    def all_connectors(self) -> dict[str, Connector]:
        """Box connectors plus every harness-owned connector, keyed by ID."""
        result = dict(self.connectors)
        for harness in self.harnesses.values():
            for connector in harness.connectors:
                result.setdefault(connector.id, connector)
        return result

    def placeholder_configs(self) -> list[str]:
        return sorted(n for n, c in self.config.items() if c.placeholder)
