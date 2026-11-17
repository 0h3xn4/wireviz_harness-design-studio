# CLAUDE.md (repository root)

This repository is a fork of WireViz. The product developed here is Harness Design Studio, in
`HarnessDesignStudio/`; its own `CLAUDE.md` (conventions, commands, status) applies to all work
there. Every upstream WireViz file outside `HarnessDesignStudio/` stays byte for byte as at the fork
base (decision D-220, `HarnessDesignStudio/tests/test_upstream_unchanged.py`): never edit them,
the root `.gitignore` included.

## Backlog and release procedure

- **The backlog** is the items under `## Next release` in `HarnessDesignStudio/BACKLOG.md`.
- **The default branch.** Find it with `git symbolic-ref refs/remotes/origin/HEAD` (today it is
  `master`). Never assume it is called `main`. All work lands on the default branch.
- **How work lands on it.** A ruleset on the default branch requires a pull request (no approval
  needed) and refuses force-pushes. So for each item: make a short branch from the default branch,
  commit, `git push -u origin <branch>`, open a pull request with the GitHub tools (never the `gh`
  CLI), wait until all its check runs are complete and green, then squash-merge it with the GitHub
  tools. A failing check is fixed on the branch, never skipped or disabled.
  - If the session names one branch to push to (a scheduled run does), use that branch for every
    pull request: after its squash-merge, start it again from the default branch under the same
    name.
  - A pull request that was opened as a draft is marked ready before the merge (a draft cannot be
    merged).
  - Before each push: `python -m tools.check_commits origin/<default branch> HEAD --owner-pr` must
    report 0 problems (the CI check `commits`: a `Signed-off-by` line from `git commit -s`, a
    noreply author address).
  - To wait for CI, poll in the background (a monitor or a background loop) or schedule a
    check-in; never a long `sleep` in the foreground.
- **One item at a time:** fix, add a test, add an entry under `## Unreleased` in
  `HarnessDesignStudio/CHANGELOG.md`, commit, push, merge as above, then move the item to `## Done`
  in `BACKLOG.md` with the merge commit hash (in the next item's pull request, or in the release
  preparation).
- **First, finish what an earlier run left.** At the start, look for an open pull request of an
  earlier backlog run and for items in `## Done` that are not in a release yet (newer than the last
  tag). Finish those before new items.
- **Unclear or blocked items** move to `## Needs human` with a short reason. Skip them and go on.
- **Not for a backlog run:** a change of the project format (format 2 is frozen, D-230; format 3
  is planned for 3.0.0) and anything a design page in `docs/ait/` already plans for a release.
  Such items move to `## Needs human`.
- **Never ask questions during a backlog run.** Make reasonable choices and write them in the
  commit message.
- **Version numbers (semver).** A breaking change is a major release (a change of the project
  format is always one: format 2 is frozen for all 2.x, D-230), a new feature is a minor release,
  anything else is a patch release.
- **Commands.** From `HarnessDesignStudio/`:
  - Setup: `uv python install 3.14 && uv venv --python 3.14 .venv && . .venv/bin/activate && uv pip install -e ".[gui,dev]"`;
    on Linux the Qt libraries of `docs/INSTALL.md` ("If the app does not start") must be installed.
  - Lint and types: `ruff format --check . && ruff check . && mypy`.
  - Tests in the session: targeted runs, `pytest -n 2 -p no:cacheprovider <test files>`, each under
    ten minutes (a container restart kills longer runs). The full suite runs in CI on every pull
    request; CI green on the pull request's head is the gate for its merge.
  - Docs that must stay in sync: `python -m tools.build_guide`, `python -m tools.gen_rule_docs`,
    `python -m tools.gen_cli_docs`, `python -m tools.gen_sdd_components`.
  - Output files must not change unless the item is about them:
    `python -m tools.output_hashes --check docs/ui/OUTPUT_HASHES_BASELINE.json`.
- **Release.** When `## Next release` is empty and at least one item was done since the last tag:
  0. **Only backlog work may be released.** Before the preparation, read `## Unreleased` in
     `HarnessDesignStudio/CHANGELOG.md`. If it holds entries that are not backlog items (for
     example the parts of a planned release that is still in progress, such as 2.3.0), do not
     release: the items stay in `## Done`, and `## Needs human` gets one line: "Release held:
     `## Unreleased` also holds unfinished work of <release>". The next run after that release
     is published releases the items.
  1. Prepare the release in one pull request, as the last preparation did (`git log --oneline
     --grep "Prepare version"`, and `docs/RELEASE.md`): `HarnessDesignStudio/CHANGELOG.md` turns
     `## Unreleased` into `## X.Y.Z (date; not a statement of compliance)` and lists every item;
     the version in `pyproject.toml` and `src/harness_design_studio/__init__.py`; the files that
     record the version made again with the repository's tools; `docs/releases/X.Y.Z.md`; a
     decision row in `docs/DECISIONS.md`; the status pages. `python -m tools.release_notes check
     vX.Y.Z` must pass. Merge it when CI is green.
  2. Wait until every check run of the merge commit on the default branch is complete and green
     (with the slow tests this takes about an hour).
  3. **Publish** by starting the tag workflow `harness-tag.yml` with the GitHub tools
     (workflow_dispatch on the default branch, inputs `version` = `X.Y.Z` and `commit` = the full
     SHA of that merge commit). It checks the commit and CI again, makes the annotated tag `vX.Y.Z`
     and starts `release.yml`, which builds, signs and publishes the release page (decision D-227).
     The session itself cannot push tags (its Git proxy refuses them), so `git tag` and
     `git push --follow-tags` are not the way to publish here.
  4. Check: `git ls-remote --tags origin` shows `vX.Y.Z`, and the release page has its seven files
     (D-232). Then write the publication record as the last one did (`git log --oneline --grep
     "Publication record"`).
- **Progress.** Keep notes of a run in `HarnessDesignStudio/PROGRESS.md`. It is in
  `HarnessDesignStudio/.gitignore` and is never committed.
