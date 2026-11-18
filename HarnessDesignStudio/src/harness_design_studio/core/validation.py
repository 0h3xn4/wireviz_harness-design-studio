# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""What `validate` and `check` look at: the files of a project folder, read the way the editor reads
them, plus the checks that need the whole project. One function, shared by the command line and the
scripting interface (`harness_design_studio.api`), so that they cannot disagree."""

from pathlib import Path

from harness_design_studio.core.io.loader import LoadResult, load_project, non_canonical_files
from harness_design_studio.core.io.migrate import SetVersions
from harness_design_studio.core.issues import Issue
from harness_design_studio.core.model import Project

NOT_CANONICAL = (
    "File differs from the tool's own formatting (hand-edited or merged). "
    "It will be rewritten on the next save."
)


def validate_folder(
    path: Path | str, *, merge_check: bool = False, set_versions: SetVersions | None = None
) -> tuple[LoadResult, list[Issue]]:
    """The loaded project and the issues found after loading it (not yet merged with the issues
    of loading). `merge_check` is what `check` adds to `validate`: files that differ from the
    tool's own formatting and released harnesses that were edited."""
    path = Path(path)
    result = load_project(path, set_versions=set_versions)
    extra: list[Issue] = []
    if merge_check:
        if result.project.read_only:
            extra.append(
                Issue(
                    "info", "skipped_canonical_check", "Format check skipped (read-only project)."
                )
            )
        elif not result.project.recovered:
            extra.extend(
                Issue(
                    "warning",
                    "not_canonical",
                    NOT_CANONICAL,
                    rel,
                )
                for rel in non_canonical_files(path, result.project)
            )
    if merge_check and not result.project.recovered:
        from harness_design_studio.core.vcs.consistency import release_integrity

        extra.extend(release_integrity(result.project))
        extra.extend(plan_notes(result.project))
    if not result.project.recovered:
        from harness_design_studio.core import configcheck
        from harness_design_studio.core.verify import link_issues

        extra.extend(link_issues(result.project))  # a harness made from a link must match it
        # a value of config/*.json that is set but cannot be used: the same check as `generate`,
        # `drc` and `config` (D-191); before, `validate` said "0 error(s)" for a value they refuse
        extra.extend(configcheck.validate(result.project))
        extra.extend(configcheck.annotation_issues(result.project))  # stale `_about`: a warning
        if result.project.extensions is not None:  # S8: a broken extension is reported, never fatal
            extra.extend(
                Issue("warning", "extension_problem", i.render(), i.file)
                for i in result.project.extensions.issues
            )
    return result, extra


def plan_notes(project: Project) -> list[Issue]:
    """What `check` says about the harness plans (3.0.0, design sections 4.1 and 6): a key of the
    document data that names no harness, and the notes on the colour codes. None of them stops
    generation or an export, so they are not issues of `configcheck.validate`; a broken
    `config/harness_plan.json` is reported there instead, and then these notes wait for it."""
    from harness_design_studio.core import configcheck
    from harness_design_studio.core.document import unknown_plan_keys
    from harness_design_studio.core.outputs.harness_plan import colour_notes

    out = [
        Issue(
            "warning",
            "plan_document_unknown",
            f"The document data has a plan of {key}, which is not a harness of the project; "
            f"`harness-design-studio document DIR --harness ID` sets the plan of a harness.",
            "project.json",
            key,
        )
        for key in unknown_plan_keys(project)
    ]
    if not configcheck.validate_harness_plan(project):
        out.extend(colour_notes(project))
    return out
