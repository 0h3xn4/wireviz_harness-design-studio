# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The document data of the harness plans (`ProjectMeta.document`, design of 3.0.0 sections 4.4
and 10): what goes on the Cover of every plan. Pure functions, no Qt: the command `document` and
the editor's *Settings > Project > Document* and *Plan document* (pull request 7) build their change
here and run it through `History` as one undo step.

    ops = plan_document_edit(project, fields={"company": "Example Ltd"})
    ops = plan_document_edit(project, harness="W001", fields={"number": "HP-001"})
    History(project).execute(document_label(None), ops)

The system code, title, company and contact lines are the same in every plan of the project; the
number, version, release and title of one harness's plan are kept by harness ID (Q25). An empty
text clears a field. A plan entry whose four fields are all empty is left out, and so is the whole
document when nothing is left in it, so that `project.json` is as it was before the first value.
The data is project data, not part of a harness: a released harness's plan can still get its
Release cell (section 4.1), so nothing here is locked by a release."""

from collections.abc import Mapping, Sequence

from pydantic import ValidationError

from .commands import Op, SetMeta
from .edit import EditError
from .model import ContactLine, DocumentInfo, PlanDocument, Project, evolve
from .model.project import MAX_CONTACT_LINES

# the fields of the document as the command line and the editor name them, with their words
DOCUMENT_FIELDS: dict[str, str] = {"system": "System code", "title": "Title", "company": "Company"}
PLAN_FIELDS: dict[str, str] = {
    "number": "Document number",
    "version": "Plan document version",
    "release": "Release",
    "title": "Title",
}


def document_of(project: Project) -> DocumentInfo:
    """The document data of the project; an empty one when it has none."""
    return project.meta.document or DocumentInfo()


def plan_of(project: Project, harness_id: str) -> PlanDocument:
    """The document data of one harness's plan; an empty one when it has none."""
    return document_of(project).plans.get(harness_id) or PlanDocument()


def document_label(harness_id: str | None) -> str:
    """The name of the undo step and of the change."""
    if harness_id is None:
        return "Set the document data of the harness plans"
    return f"Set the plan document of {harness_id}"


def _text(field: str, word: str, value: object) -> str:
    if not isinstance(value, str):
        raise EditError(f"The {word.lower()} must be text.")
    text = value.strip()
    try:
        PlanDocument(title=text)  # the same type as every field: up to 200 characters
    except ValidationError as exc:
        raise EditError(
            f"The {word.lower()} ({field}) can have at most 200 characters and no control "
            "characters."
        ) from exc
    return text


def _lines(contact: Sequence[tuple[str, str]]) -> list[ContactLine]:
    if len(contact) > MAX_CONTACT_LINES:
        raise EditError(
            f"A plan has at most {MAX_CONTACT_LINES} contact lines; these are {len(contact)}."
        )
    out: list[ContactLine] = []
    for label, value in contact:
        label = label.strip() if isinstance(label, str) else label
        if not label:
            raise EditError("A contact line needs a label (for example Phone or E-mail).")
        try:
            out.append(ContactLine(label=label, value=_text("contact", "Contact value", value)))
        except ValidationError as exc:
            raise EditError(
                "The label of a contact line can have 1 to 200 characters and no control "
                "characters."
            ) from exc
    return out


def edited_document(
    project: Project,
    *,
    harness: str | None = None,
    fields: Mapping[str, str] | None = None,
    contact: Sequence[tuple[str, str]] | None = None,
) -> DocumentInfo | None:
    """The document data after the change, or None when nothing is left in it. `fields` are the
    project's fields (`DOCUMENT_FIELDS`), or with `harness` the fields of that harness's plan
    (`PLAN_FIELDS`); an empty text clears one. `contact` replaces every contact line (a list of
    label and value, in order); None leaves them. `EditError` says what is wrong in words."""
    fields = dict(fields or {})
    allowed = PLAN_FIELDS if harness is not None else DOCUMENT_FIELDS
    unknown = sorted(set(fields) - set(allowed))
    if unknown:
        where = f"the plan of {harness}" if harness is not None else "the project"
        raise EditError(
            f"'{unknown[0]}' is not a field of the document data of {where} ({', '.join(allowed)})."
        )
    doc = document_of(project)
    if harness is not None:
        if harness not in project.harnesses:
            raise EditError(f"Harness {harness} does not exist.")
        if contact is not None:
            raise EditError(
                "The contact lines are the same in every plan of the project; set them without "
                "a harness."
            )
        plan = plan_of(project, harness)
        plan = evolve(plan, **{k: _text(k, allowed[k], v) for k, v in fields.items()})
        plans = dict(doc.plans)
        if plan == PlanDocument():
            plans.pop(harness, None)
        else:
            plans[harness] = plan
        doc = evolve(doc, plans=dict(sorted(plans.items())))
    else:
        changes: dict[str, object] = {k: _text(k, allowed[k], v) for k, v in fields.items()}
        if contact is not None:
            changes["contact"] = _lines(contact)
        doc = evolve(doc, **changes)
    return None if doc == DocumentInfo() else doc


def plan_document_edit(
    project: Project,
    *,
    harness: str | None = None,
    fields: Mapping[str, str] | None = None,
    contact: Sequence[tuple[str, str]] | None = None,
) -> list[Op]:
    """The change of `edited_document` as the operations of one undo step (none when nothing
    changes). Refused for a read-only project."""
    if project.read_only:
        raise EditError("This project is read-only (saved by a newer tool version).")
    new = edited_document(project, harness=harness, fields=fields, contact=contact)
    if new == project.meta.document:
        return []
    return [SetMeta(evolve(project.meta, document=new))]


def shown_when_empty(project: Project, harness: str | None = None) -> dict[str, str]:
    """What the Cover shows for each field that is empty (`outputs/harness_plan.py`, `_cover`):
    the project name for the system code, `<name> Harness Plan` for the title; with `harness`,
    the harness version for the plan document version and the project's title for the plan's
    title. A field with no stand-in is left out."""
    doc = document_of(project)
    title = doc.title or f"{project.meta.name} Harness Plan"
    if harness is None:
        return {"system": project.meta.name, "title": title}
    h = project.harnesses.get(harness)
    out = {"title": title}
    if h is not None:
        out["version"] = h.version
    return out


def unknown_plan_keys(project: Project) -> list[str]:
    """The keys of `document.plans` that name no harness of the project (a `check` warning,
    section 4.1), in ID order."""
    return sorted(k for k in document_of(project).plans if k not in project.harnesses)


def document_dict(project: Project, harness: str | None = None) -> dict[str, object]:
    """The document data as `document --json` prints it: every field, empty ones as "", and the
    plans by harness ID (only the one asked for with `harness`)."""
    doc = document_of(project)
    plans = {
        h: {k: getattr(plan_of(project, h), k) for k in PLAN_FIELDS}
        for h in sorted(doc.plans)
        if harness is None or h == harness
    }
    if harness is not None and harness not in plans:
        plans[harness] = dict.fromkeys(PLAN_FIELDS, "")
    return {
        **{k: getattr(doc, k) for k in DOCUMENT_FIELDS},
        "contact": [{"label": c.label, "value": c.value} for c in doc.contact],
        "plans": plans,
    }


__all__ = [
    "DOCUMENT_FIELDS",
    "PLAN_FIELDS",
    "document_dict",
    "document_label",
    "document_of",
    "edited_document",
    "plan_document_edit",
    "plan_of",
    "shown_when_empty",
    "unknown_plan_keys",
]
