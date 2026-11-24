# Export the harness plans

This page shows how to write the harness plan of each harness, a spreadsheet in the layout of the users' harness plan template, from the command line and in the editor, and how to fill in what its Cover shows.

**Example** (since 5.1.0): `harness-design-studio new practice --template build-data-and-as-built` makes a finished example: the Cover filled in (system code, title, company, two contact lines and the document number of W001) and the ends coloured [by pin number](#4-colour-the-ends-by-pin-number) with the example colour code; `harness-design-studio export practice --harness-plan` writes the plans.

> **New in 3.0.0** (format 3, decision D-242, [`DESIGN_3.0_HARNESS_PLAN.md`](../ait/DESIGN_3.0_HARNESS_PLAN.md)). What each sheet holds is in [`OUTPUTS.md`](../OUTPUTS.md#harness-plan).

## Contents

- [Before you start](#before-you-start)
- [1. Fill in the Cover](#1-fill-in-the-cover)
- [2. Export the plans](#2-export-the-plans)
- [3. Check the plans](#3-check-the-plans)
- [4. Colour the ends by pin number](#4-colour-the-ends-by-pin-number)
- [5. A release, and an export without the plans](#5-a-release-and-an-export-without-the-plans)
- [6. In the editor](#6-in-the-editor)
- [A harness with splices](#a-harness-with-splices)
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

**The Production sheet** (since 4.1.0). After the harness sheet, the sheet *Production* is the one to print for the bench: one block per cable connector (the far ones too), so every wire is in two rows, one at each end, with where it goes, its part, colour, gauge, length in mm, where the length comes from, the label printed at that end and its shield groups with their end here and at the far end. A run of spare pins is one row (`3 to 9`). While the plan colours the ends by pin code (section 4), a column *Pigtail colour* shows the colour of the code at that end. Every length of the plan runs from the rear of a connector to the rear of the other (*Length [mm] rear to rear*); row 2 of *Production* and `H9` of the harness sheet say so in words, with the service loops of your settings.

**Print** (since 4.1.0). The harness sheet prints on A4 landscape at a fixed scale, as large as its width allows on one page wide (61 % for W001 of `flatsat`, which has nine far connectors; each far connector makes it 22 mm wider and so a little smaller), with rows 6 to 9 at the top of every page and a new page before a connector block that would not fit on the one before. *Production* prints at 100 % with its title, the length note and the headings on every page. The page breaks are worked out from the column widths and the length of the texts; a program can still break a long text elsewhere. The other sheets print on one page each, as before.

**Search a column** (since 3.1.0). On the harness sheet, above the table, type a text into `I3` (Function) or `M3` (Shielding) in place of `#`: every Function or Shielding cell of the rows of the near connectors that contains the text, without regard to case, shows in red bold. `tx` marks `RS422_TX+` and `TX`; an empty box marks nothing. LibreOffice reads the text as typed; Excel reads `*`, `?` and `~` in it as wildcards. A plan saved with a typed search text is a changed plan: search in a copy, or close it without saving.

## 3. Check the plans

```
harness-design-studio verify wheel-link --outputs
```

The check works out each plan again from the design and compares every sheet and cell, the formulas and the values they give, and (since 4.1.0) the print set-up of the harness sheet and of *Production*: the scale, the rows on every page, the print range and the page breaks. A plan changed after the export fails the check: export again.

## 4. Colour the ends by pin number

By default each end shows the wire's colour. A connector with pigtails often comes with its wires coloured by pin position; `config/harness_plan.json` can then give an end the colour of its pin from a colour code (`"colour_rule": "pin_code"`). The templates hold the users' colour code as an example, `pigtail-colour-code-EXAMPLE.csv` (`harness-design-studio templates FOLDER` copies it). It is an example, not a standard and not a supplier's table: check it against the pigtail code of your connector's supplier. While a code is marked `"example": true`, the plan heads its table as an example and `harness-design-studio check` gives the note `plan_colour_example`. A pin the code does not list reads `to fill in` in the plan, and `check` warns once per connector (`plan_colour_missing`). Neither stops generation or an export.

## 5. A release, and an export without the plans

A release writes the outputs again with the released status. It keeps the choice of the export before it: the plans are written again only if that export had them, and the register and the `VERSION:` cell of the plan follow the release. A new version (`new-version --kind minor`) and its release show in the register as rows of their own.

An export without `--harness-plan` into a folder whose last export had the plans removes them and says so:

```
The harness plans of the earlier export were removed; add --harness-plan to write them again.
```

## 6. In the editor

- **Export.** The Export window (**Export…**, Ctrl+E) has the check box **Include the harness plans (.ods), one per harness**. It starts ticked when the last export into the folder had the plans. Unticked, the export removes the plans of the earlier export and the window says so. While it is ticked, a line under it counts the notes `check` has on the plans.
- **The Cover.** **Settings > Document** (also **Design > Document data of the plans…**) holds the system code, the title, the company and the contact lines. The Inspector of a harness has **Plan document**: the document number, the plan document version, the release and the title of that harness's plan, saved with **Set**. Each change is one undo step.
- **The colours and notes.** **Settings > Harness plan** (also **Design > Harness plan settings…**) has the colour rule, the colour codes (parts, the table of pins and colours with **Paste pins and colours**, the **Example** mark), the note lines and **Use the example colour code…**, which asks for the connector parts the code is for. It lists the notes of `check` on the plans as well.
- **Pins, connectors and parts.** In the Devices tab, the pin table has **Level** and the role **Signal ground**, and the connector card has **Source**, **Source version** and **Source link** with **Copy**. A cable pin has no level: the level belongs to the device's pin. The Inspector of a part has **Link** with **Copy link**, and the library window lists the parts of a device with their links. The editor never opens a browser: **Copy** and **Copy link** put the link on the clipboard, and a double-click on a part in the library window does the same.

## A harness with splices

A harness you drew can join wires at a splice ([splices](splices.md)). Its plan follows the wires through the splices:

- **The two ends.** The connectors are split into the near end and the far end as for any harness, with the splices left out: two connectors whose wires meet at a splice are on opposite ends. A Y harness through a splice puts its two branches at one end and the trunk at the other.
- **The rows.** A near row lists every far pin its wire reaches through a splice. A row that reaches two far connectors has a pin in each far column; two pins of one far connector read `3 + 4`; the far *Cable / Type*, *Color*, *Direction* and *Function* list the values of each far wire, joined by ` + `.
- ***Further wires*** lists the wires beyond a splice with the other wires that end on no near pin, so every wire of the harness is in exactly one row, and the sums per cable type count both.

A harness without a splice gets the same plan as before. `verify --outputs` follows the splices with its own copy of the rule.

## Common mistakes

- **The plans are gone after an export.** The export was made without `--harness-plan`. Add it and export again.
- **A Direction word such as `TEST` did not set anything.** Only `PWR`, `PWR-RET`, `GND`, `SGND`, `SHIELD`, `SPARE`, `IN`, `OUT` and `IN/OUT` (and the older words such as `bidirectional`) are read; any other word leaves the role and the direction of the pin as they are, and the import record lists it.
- **`document --harness W009` says the harness does not exist.** The plan of a harness is set by its ID; the Harness tab and the folders under `outputs/harnesses/` show the IDs.
