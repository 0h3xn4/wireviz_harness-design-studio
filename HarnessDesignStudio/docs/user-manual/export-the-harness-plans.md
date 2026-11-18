# Export the harness plans

This page shows how to write the harness plan of each harness, a spreadsheet in the layout of the users' harness plan template, from the command line, and how to fill in what its Cover shows. The editor's parts (the check box of the Export window, *Settings > Project > Document* and *Harness plan*, the *Plan document* of a harness) come with a later step of 3.0.0; until then this page is command line only.

> **New in 3.0.0** (format 3, decision D-242, [`DESIGN_3.0_HARNESS_PLAN.md`](../ait/DESIGN_3.0_HARNESS_PLAN.md)). What each sheet holds is in [`OUTPUTS.md`](../OUTPUTS.md#harness-plan).

## Contents

- [Before you start](#before-you-start)
- [1. Fill in the Cover](#1-fill-in-the-cover)
- [2. Export the plans](#2-export-the-plans)
- [3. Check the plans](#3-check-the-plans)
- [4. Colour the ends by pin number](#4-colour-the-ends-by-pin-number)
- [5. A release, and an export without the plans](#5-a-release-and-an-export-without-the-plans)
- [Common mistakes](#common-mistakes)

## Before you start

- You have a generated project ([generate harnesses](generate-harnesses.md)). The commands below use the practice project `wheel-link` (`harness-design-studio new wheel-link --template first-steps`, then `harness-design-studio generate wheel-link`).
- The build workbook stays the file to build a harness from ([export the outputs](export-the-outputs.md)). The plan is the same design in the users' form, with formulas: a mirrored direction, a colour looked up by pin number, a sum of lengths.
- The tool never reads a plan back. An export overwrites it, typed changes and all: work on a copy.
- A pinout in the users' words (the headings *Pinout*, *Function*, *Direction*, *Level* and *Description*, the words `PWR`, `PWR-RET`, `GND`, `SGND`) comes in through `import-pinout` ([import data](../IMPORTS.md#device-pinouts-and-kicad-netlists)); the *Pinout* column is read as the pin with `--column pin=Pinout`.

## 1. Fill in the Cover

The system code, title, company and contact lines are the same in every plan of the project:

```
harness-design-studio document wheel-link --set system=EX --set company="Example Ltd" --contact E-mail=plans@example.org
```

The document number, the plan document's own version, the release and the title belong to the plan of one harness:

```
harness-design-studio document wheel-link --harness W001 --set number=HP-W001
```

`harness-design-studio document wheel-link` shows what is set, and what the Cover shows for a field that is empty (the project name for the system code, the harness version for the plan document version). `--clear FIELD` empties a field, `--clear contact` removes every contact line, and `--contact LABEL=` removes one. Each change is one step, recorded in the change journal of a project that keeps one; a release does not lock it, so the Release cell of a released harness's plan can still be filled in.

**Privacy.** The document data is saved in `project.json`, so a name, a phone number or an e-mail address goes into the project's Git history. A team that prefers it can give a role address, such as a shared mailbox, instead of a person.

## 2. Export the plans

```
harness-design-studio export wheel-link --harness-plan
```

Each harness gets `outputs/harnesses/<ID>/<ID>_plan.ods`, next to its build workbook. The option is one choice for all harnesses, as `--drawings` is; without it no plan is written. With `--json` the result lists the plans under `harness_plans`. The plan opens in LibreOffice Calc and in other programs that read OpenDocument spreadsheets; every formula carries its value, so a program that does not recalculate shows the same.

## 3. Check the plans

```
harness-design-studio verify wheel-link --outputs
```

The check works out each plan again from the design and compares every sheet and cell, the formulas and the values they give. A plan changed after the export fails the check: export again.

## 4. Colour the ends by pin number

By default each end shows the wire's colour. A connector with pigtails often comes with its wires coloured by pin position; `config/harness_plan.json` can then give an end the colour of its pin from a colour code (`"colour_rule": "pin_code"`). The templates hold the users' colour code as an example, `pigtail-colour-code-EXAMPLE.csv` (`harness-design-studio templates FOLDER` copies it). It is an example, not a standard and not a supplier's table: check it against the pigtail code of your connector's supplier. While a code is marked `"example": true`, the plan heads its table as an example and `harness-design-studio check` gives the note `plan_colour_example`. A pin the code does not list reads `to fill in` in the plan, and `check` warns once per connector (`plan_colour_missing`). Neither stops generation or an export.

## 5. A release, and an export without the plans

A release writes the outputs again with the released status. It keeps the choice of the export before it: the plans are written again only if that export had them, and the register and the `VERSION:` cell of the plan follow the release. A new version (`new-version --kind minor`) and its release show in the register as rows of their own.

An export without `--harness-plan` into a folder whose last export had the plans removes them and says so:

```
The harness plans of the earlier export were removed; add --harness-plan to write them again.
```

## Common mistakes

- **The plans are gone after an export.** The export was made without `--harness-plan`. Add it and export again.
- **A Direction word such as `TEST` did not set anything.** Only `PWR`, `PWR-RET`, `GND`, `SGND`, `SHIELD`, `SPARE`, `IN`, `OUT` and `IN/OUT` (and the older words such as `bidirectional`) are read; any other word leaves the role and the direction of the pin as they are, and the import record lists it.
- **`document --harness W009` says the harness does not exist.** The plan of a harness is set by its ID; the Harness tab and the folders under `outputs/harnesses/` show the IDs.
