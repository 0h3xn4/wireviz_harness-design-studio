# Versions

Since 3.0.0 a harness has a **version** of three numbers, MAJOR.MINOR.PATCH: `1.0.0`, `1.1.0`, `2.0.0`. This page says what the numbers mean, how the next version is chosen, what the tool says about the choice, and what became of the revision letters of 2.x.

**Example** (since 5.1.0): `harness-design-studio new practice --template released-harness` makes a finished example: W002 has the baseline `W002.1.0.0` and is the draft of its minor version 1.1.0.

## Contents

- [The three numbers](#the-three-numbers)
- [Start a new version](#start-a-new-version)
- [Choose the kind again](#choose-the-kind-again)
- [The notes on the kind](#the-notes-on-the-kind)
- [Where the version shows](#where-the-version-shows)
- [The letters of 2.x](#the-letters-of-2x)
- [After a merge with a branch of 2.x](#after-a-merge-with-a-branch-of-2x)
- [Common mistakes](#common-mistakes)

## The three numbers

- A new harness starts at `1.0.0`, made by Generate or by hand.
- The status says where it stands: *draft*, *in review* or *released*. The version does not: a draft after **New version** already carries the version it will be released as (`1.1.0`, draft).
- Versions are put in order by their numbers, never as text: `1.10.0` comes after `1.9.0`.
- A version is written with no leading zero and no prefix: `1.10.2`, not `01.10.2` or `v1.10.2`. The screen shows the short form `v1.1.0` in the top bar and in the chips of the **Harness** tab (*Released · v1.1.0*); the files and the commands write `1.1.0`.
- A baseline is named `<harness>.<version>` (`W002.1.1.0`) and stored as `baselines/W002/W002.1.1.0.json`.

## Start a new version

A released harness is locked. To change it, start its next version and choose the **kind**. The tool works the version out from the released one:

| Kind | Means (the words of the harness plan template) | From `1.4.2` |
| --- | --- | --- |
| major | not compatible with the versions before it | `2.0.0` |
| minor | adds something and stays compatible | `1.5.0` |
| patch | a fix that stays compatible | `1.4.3` |

```
harness-design-studio new-version wheel-link W002 --kind minor --by "A. Engineer" --comment "Add wire colours, nothing else changes"
```

```
New version 1.1.0 of W002: done.
```

`--kind` is required; the tool does not suggest one, because at this point the draft is still the released design. `revise` is the older name of `new-version` and takes the same options. In the app: **New version…** in the **Versions** tab or the **Harness** tab, or **Start a new version…** on a banner or in the **Design** menu. The window **New version of W002** lists the three kinds, none chosen, each with the version it gives (*1.0.0 → 1.1.0*); **Start new version** stays off until you choose one. The whole walk-through is on [change a released harness](change-a-released-harness.md).

A new version must be higher than every baseline of the harness. A step back is refused with `version_not_higher`, also when a merge brought in a higher baseline.

## Choose the kind again

You often know the kind only after the change. While the harness is a draft after a release, and before its review starts, run `new-version` again with the other kind:

```
harness-design-studio new-version wheel-link W002 --kind patch --by "A. Engineer" --comment "Only the label text changed after all"
```

```
Version 1.1.0 of W002 becomes 1.0.1 (patch): done.
```

The version is worked out again from the released one (`1.0.0`), nothing else of the draft changes, and the change log gets one entry *version changed*. In the app, **New version…** on such a draft opens **Choose the kind of version of W002 again**. Choosing the kind the draft already has is refused (`kind_unchanged`). After the review starts the kind stays (`in_review`); release it, then start the next version.

## The notes on the kind

The tool gives two notes. Neither changes a version or blocks anything: the choice stays yours.

- **A major version.** When you choose major, the command and the window say: *A major version says that this harness is not compatible with its earlier versions. The harness plan template gives such a harness a new ID instead (TH01 becomes TH02, not TH01 2.0.0).* The tool does not enforce that naming rule.
- **A pinout change in a minor or patch version.** At `review` and `release`, and in their windows, the tool compares the draft with the last baseline. When the version is minor or patch and the change reaches an end that plugs into a device, it says, for example: *This version changes the pinout at a device (cable connector W002-P1). The harness plan template calls that an incompatible change.* It counts a cable connector that mates with a device connector whose part, gender or keying changed, or that mates with another device connector, and a wire added, removed or moved at such a connector. Between minor and patch it says nothing: that difference is about intent, which a diff does not show.

With `--json` both notes are in the list `notes`.

## Where the version shows

- **Screen:** the top bar (*v1.0.0*, or the lowest and the highest, *v1.0.0-2.1.0*), the **Versions** tab (the column *Version*, **Compare version … with …**), the Inspector (*Version*), the chips of the **Harness** tab, the tooltip of a harness in the project tree, and the lock on a device (*W002 1.0.0*).
- **Files:** the title block of the drawings (*VERSION*) and their header (`Version 1.1.0  status draft`), *Start here* of the build workbook, `system/changelog.csv` and the *Change log* sheet of `system/system.xlsx` (column *Version*, events *new version started* and *version changed*), `system/version_report.md`, and `system/export.json`.
- **For scripts:** `system/export.json` and `log --json` write `version`. 3.0.x kept `revision` beside it with the same value; since 4.0.0 it is gone, and `format_version` of `system/export.json` is 2. The expression field `harness.revision` of 3.0.x went at the same time: write `harness.version`. The command `revise` stays as the older name of `new-version`.

## The letters of 2.x

Up to 2.x the tool called it a **revision** and counted letters: A, B … Z, AA. The upgrade to format 3 (`migrate`, or the editor's question) turns each letter into a version by its place: **the Nth letter is N.0.0**. A is `1.0.0`, B is `2.0.0`, Z is `26.0.0`, AA is `27.0.0`. The same holds for the harness, each of its baselines and each change-log entry. A value that is neither a letter nor a version (`A1`, `-`) is not guessed: `migrate --dry-run` lists it, and `migrate --set-version W002:A1=1.1.0` gives it its version.

`diff` still takes an old letter and says which version it is:

```
harness-design-studio diff wheel-link W002 --from A
```

```
A is read as version 1.0.0: the letters of format 2 became versions at the upgrade to format 3, the Nth letter N.0.0.
# W002: working design against version 1.0.0
```

What still says *revision*: the journal lines written before the upgrade (they record what happened), files exported by 2.x, printed drawings, and the migration record, which names both words (`W002: revision B → version 2.0.0`).

## After a merge with a branch of 2.x

Upgrade on the main branch first, then bring the other branches up to date before they merge. A branch still in format 2, merged into a branch in format 3, can bring the key `revision` and a letter into a file of format 3: a harness it made, a change-log entry, a baseline. `check` and the editor then set that object aside and say, for example:

```
ERROR   revision_not_version: harness W005 holds the revision 'A' of format 2; in format 3 that is version 1.0.0. A branch in format 2 was merged into a project in format 3: `harness-design-studio merge-fix DIR` rewrites the key and the letter. [physical/harnesses/W005.json]
```

`merge-fix` rewrites each key and letter by the same rule (A is `1.0.0`), moves a baseline to its new name and prints each place; `--dry-run` shows them and writes nothing. A value that is not a letter is not guessed: write its version by hand. See [use Git and CI](use-git-and-ci.md).

## Common mistakes

- **`--kind` missing.** `new-version` and `revise` need it; the tool does not choose for you.
- **"W002 is not released, so it can be edited directly."** A draft that was never released has no version to step from; edit it, then release it as `1.0.0`.
- **"W002 is in review, so the kind of its version can no longer be chosen again".** Release it, then start the next version.
- **"Version 1.1.0 of W002 is not higher than its baseline 1.1.0".** A merge brought in a baseline of the same version; choose a larger kind.
- **Reading a version as text.** A script that sorts `1.10.0` before `1.9.0` sorts as text; sort by the three numbers.

More: [release a harness](release-a-harness.md), [change a released harness](change-a-released-harness.md), [`CLI.md`](../CLI.md#harness-design-studio-new-version), [the glossary](../GLOSSARY.md).
