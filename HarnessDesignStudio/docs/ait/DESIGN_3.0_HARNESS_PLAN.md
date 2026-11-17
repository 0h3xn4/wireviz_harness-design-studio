# Design of 3.0.0: the harness plan

Written on 2026-11-17 from a reading of the code at `2393ff7` (master, with pull request 2 of 2.2.0) and of the users' template `harness_plan_template.ods`, supplied by the owner on 2026-11-17. The decision that records it is D-242 (to be recorded). It is a design only: nothing of it is built. Paths are relative to `src/harness_design_studio/` unless they start with `docs/` or `tests/`. The owner answered the 17 questions of the first version on 2026-11-17 (section 14). This version follows the answers and asks the questions they raise (Q18 to Q27).

## 0. The owner's frame

The owner decided three things on 2026-11-17. This design works inside them.

1. The output is an **`.ods` file that includes formulas**, in the users' layout.
2. The data the model lacks goes into **format 3**, released as **3.0.0**. The model refuses unknown fields (`extra="forbid"` in `core/model/base.py`), so a new field is a format change. Format 2 is frozen for 2.x (D-230).
3. **Order:** after 2.2.0 (the device library, [`DESIGN_2.2_DEVICE_LIBRARY.md`](DESIGN_2.2_DEVICE_LIBRARY.md)) and 2.3.0 (branching harnesses and splices, [`PLAN_2.0.md` section 3.6](PLAN_2.0.md#36-order-after-the-feedback-of-2026-11-16)).

**The owner's answers of 2026-11-17**, in short (section 14 has each one):

- **One plan per harness** (Q1): `harnesses/<ID>/<ID>_plan.ods`. Users sometimes make a quick test harness that is custom and unique. Each file holds its own Cover, Change register, harness sheet, `CON_…` sheets and Notes.
- **The users' colour code ships as an example** (Q3) that a project takes on purpose. It is never applied by itself (section 6).
- **Revisions become versions MAJOR.MINOR.PATCH** (Q9). A person chooses major, minor or patch at *revise*. Section 5 designs it.
- **One format 3** holds the plan's fields, the versions and, if 2.3.0 needs one, its format change, in whichever release comes first (Q10).
- *Conductor* is the wire part's specification text for now (Q15). The template's conditional formats are written as they are (Q17).
- Q2, Q4 to Q8, Q11 to Q14 and Q16: as recommended.

## 1. Purpose and scope

**What the users get.** One more written file per harness: the harness plan, a spreadsheet in their own layout. It has a cover, a change register, the harness sheet with the device side and the harness side of every connector, the sums of cable lengths, the reference pinouts of the far connectors, a notes sheet with the colour codes the harness uses, and one sheet per device connector the harness plugs into (`CON_…`). Formulas keep the sheet working when a person changes a cell in it: a mirrored direction, a colour looked up by pin number, a sum of lengths.

**What stays as it is.** The build workbook (`<ID>_build.xlsx`, [`OUTPUTS.md`](../OUTPUTS.md#build-workbook)) stays the file to build a harness from. Every other output stays. The plan is one more file per harness, written only when asked for (section 10).

**One file per harness** (the owner's answer to Q1). Users sometimes make a quick test harness that is custom and unique, so each harness gets a plan of its own: `outputs/harnesses/<ID>/<ID>_plan.ods`, next to its build workbook. Each file holds its own Cover, Change_Register, the harness sheet, the `CON_…` sheets that this harness needs, Notes and About (section 3.7). The template is one document per project, whose harness sheets share the `CON_…` sheets; the tool does not write that. The cost: the `CON_…` sheet of a box connector is repeated in the plan of every harness that plugs into it, so a change to one device changes each of those plans (section 13).

**Not in scope.** No plan of the whole project in one file. No import of a filled-in plan. The tool never reads the plan back, as it never reads the build workbook back. No `.xlsx` copy of the plan. No picture in the first version (owner question Q12).

## 2. The template, as read

The file was read from its XML (`content.xml`, `styles.xml`, `meta.xml`), not through a spreadsheet program. It was written by LibreOffice 24.2 in ODF 1.3.

**Eight sheets, not four.** `Cover`, `Change_Register`, one harness sheet `XXX-H1-DEV1-DEV2-DEV3`, `Notes`, and four device-connector sheets `CON_DEV1_J101`, `CON_DEV2_J4711`, `CON_DEV3_J402`, `CON_DEV4_J42`. The brief said the `CON_…` sheets were not in the file; they are, with example data.

**Cover.** `E2:F4` Doc.-No., Version, Release (the release cell is empty). `A17` the project (`PROJECT XXX`), `A19` the title (`XXX Harness Plan`), `A21` the company, each merged over six columns. `C36` *Contact Information*, then four lines of label and value in `C37:D40`: a name, a phone, a fax and an e-mail with a `mailto:` link. The print range is `A2:F40`.

**Change_Register.** Headings in `B4:G4`: Version, Sub-Version, Date, Name, Sheets, Description; three example rows (`1.0.0`, `x.x.x` with `SV001`, and `SV002`; dates `YYYY-MM-DD`). A text frame states the users' versioning rule: MAJOR.MINOR.PATCH; never raise MAJOR; no A/B/C variants; a change that is not backwards-compatible (a pinout change) gets a **new harness name** (TH01 becomes TH02, not TH01 V2.0.0). The print range is `B4:G7`.

**The harness sheet** (A4 landscape, fit to one page, print range `H6:U64`):

- `H6` system, `N6` harness number, `Q6` `VERSION: vx.x.x`, `T6` `[no SGND*]` in red. `H8` the title by formula: `"Harness " & system & "-" & number & ": " & DEV2 & " + " & DEV3 & " <–> " & DEV1 & " + " & DEV4`, built with `COM.MICROSOFT.CONCAT` from cell `B1` of each `CON_…` sheet.
- `I2:I3` and `M2:M3` *Column Search String*: a conditional format shows red bold text in `I34:I63` (Function) and `M34:M63` (Shielding) where the cell contains the search string.
- *used Connectors* `H10:T15` (No., Part No., Quantity, Remark; hint *FILL IN WITH INVENTREE IPN or ITEMS FROM materials_to_be_used.ods*).
- *used Cable Types* `H17:T21` (No., Part No., AWG, Conductor, Colours, No. of wires in cable, *Lenght [mm]* spelled so). The length cell is `=[.N67]`, a reference to the sum table. The hint *for currents >2A use AWG20, for all other signals AWG24* is typed into a Part No. cell.
- *used Backshells* `H23:T27` (No., Part No., Quantity, Remark; *no backshells will be used*).
- One block per near connector: `B28` its ID (`DEV2_J4711`); `H29` the part link (*Inventree Part Detail: https://…*, a `text:a` link); `B30` the ICD link by `HYPERLINK(INDIRECT(…"!B13"))`; `F31`/`H31` *Device Side* / *Harness Side*; `B32` *Data from CON_DEV2_J4711*; `F32` the connector description; `H32` `CONNECTOR TYPE PLACEHOLDER [<number>:DEV2:J4711]`.
- *Device Side* `B33:F33`: Pin No., Function, Direction, Level, Description. Each cell is `INDIRECT(CONCATENATE("CON_";B28;"!";ADDRESS(…MATCH("Pinout";…)…)))`: it finds the row *Pinout* in the `CON_…` sheet and reads the cell at the same offset.
- *Harness Side* `H33:U33`: Pinout, Function, Direction, Color, Cable / Type, Shielding / (Grouping), Length [mm], Level, then the far end mirrored: Cable / Type, Color, Direction, Function, Pinout (of DEV1), Pinout (of DEV4). Formulas: `H=B`, `I=C`; `J` mirrors `D` (IN to OUT, OUT to IN, others unchanged); `K` and `Q` look the colour up in `Notes` by pin number (`VLOOKUP(pin;$Notes.$B$7:$C$43;2)`); `O=E`; `R` and `S` take the far direction (mirrored) and function from DEV1 if set, else DEV4 (`COM.MICROSOFT.IFS`); `T` and `U` copy the far pins typed in `W` and `AD`. `L` (cable type number), `M` (`S1`, `S2`), `N` (length) and `P` are typed; `N35` and the rows below are `=$N$34`.
- The second near block (DEV3) starts in the middle of the harness-side table (`B44:F48` headings, rows `49:63`): the harness side runs on as one table over rows `34:63`.
- Far device side, per row: `W` (DEV1 pin, typed in red) and `X:AA` from `OFFSET(X$70;W34;0)`; `AD` (DEV4 pin) and `AE:AH` the same way.
- *Sum of length of cable type [mm]* `H67:N69`: `SUMIF(L34:L63; type; N34:N63) / LOOKUP(type; H19:H21; R19:R21)`, the sum of the wire lengths of a type divided by its number of wires per cable. With *No. of wires in cable* empty it shows `#DIV/0!`.
- Reference pinouts of the far connectors from row 66: `W66` and `AD66` the connector IDs, a link, *Reference Pinout Sorted from Source (usually a copy from ICD !)*, *Data from CON_…*, headings Pinout, Function, Direction, Level, Description, *Used in Row* (`MATCH(pin; W34:W63; 0) + ROW(W33)`, `#N/A` where unused), rows `71:100`.
- An image frame with the picture *BLOCK DIAGRAM incl. Lengths* and the text *(only needed when harness has more then 2 connectors)*.

**Conditional formats.** Besides the search strings: `J34:J63` and `K53:U53` show red bold text where one end is `GND` and the other `PWR` (`OR(AND(J34="GND";R34="PWR");AND(R34="GND";J34="PWR"))`).

**Colours.** Headings light blue (`#9bc2e6`); the `CON_…` pin numbers and reference rows grey (`#dddddd`); hand-typed harness cells (cable type, shielding, length) light grey (`#eeeeee`) with red text (`#ce181e`); the register headings `#83caff`. **Yellow (`#ffff99`) for a pin that is not connected is a fixed cell style set by hand**, not a conditional format: row 53 (DEV3 pin 5, `SGND`) is yellow over `H53:U53`, its harness side is empty, and `I53` says *Not connected pins will be marked yellow*.

**Notes.** *uD Pigtail Colour Code*: pins 1 to **37** in `B7:C43` (not 33). Pins 1 to 10 are typed (Black, Brown, Red, Orange, Yellow, Green, Blue, Violet, Grey, White); pins 11 to 37 are built by `CONCATENATE("Wh / "; …)`, `"Wh / Bl / "`, `"Wh / Brw / "` and `"Wh / Red / "`. *Labelling*: a line explicitly not connected shows it in its label (*SGND due to System Star Grounding → label should contain „no SGND“*). *Level*: *Data: TTL-5V, RS422-3V3, LVDS, …* and *Pwr: 18V, 3V3*.

**`CON_…` sheets.** `A1:B16`: Device, Connector ID, Interface Name, Connector Type (`SUBD`, `uD`), Number of Pins, Gender, *Connector Name/Part Number* (formula `Type & " " & Pins & " " & Gender`), *Connector Description* (formula `Device & " [" & ID & "]: " & Interface & "; " & Name`), *Link to ICD* (a `text:a` to a relative path on a file share), ICD version (`v0.5.0`), *CON sheet copied from* (`[link to other harness plan]`), *This subsheet entry's last update* (a date). From row 18 the pin table: Pinout, Function, Direction, Level, Description, pins 1 to 48 (more rows than the connector has pins).

**Words used for Direction.** In the data: `PWR`, `GND`, `SGND`, `IN`, `OUT` and once `TEST` (`CON_DEV1_J101` pin 11). `PWR-RET` appears only typed over a formula on the harness side (`J62`, `R63`).

**Things in the template that the plan does differently, and why:**

- `INDIRECT` of an empty cell gives `0`: an empty Description shows `0`. The plan writes an empty cell.
- `VLOOKUP` without its fourth argument matches the nearest lower key: a pin 38 would get the colour of pin 37. The plan matches exactly.
- `OFFSET(X$70; pin; 0)` takes the pin number as the row offset: it works only while the reference rows are pins 1, 2, 3 … in order. Pins named `A1` or a gap break it. The plan refers to the row of the pin itself.
- Formula cells were overwritten by hand (`J62`, `R63`). The plan writes the formula again on the next export (owner question Q4).
- The named `Print_Area` of the harness sheet is broken (`[.EH1]-obc-#REF!-obc-#REF!`); the table's own print range `H6:U64` works. The plan writes the table's print range only.

**What could not be read, or is unsure.** `Conductor` in *used Cable Types* has no example value: material, or construction? (owner question Q15). *Sub-Version* (`SV001`) is not explained beyond the example. The meaning of the `*` in `[no SGND*]` is taken to point to the labelling note. The template's text frames were read as text only; their place on the printed page was not checked. No spreadsheet program opened the template for this design.

## 3. Cell by cell: template to model

*Exists* means a field of format 2. *Derived* means worked out from fields that exist. *New* means a field of format 3 (section 4). *F* marks a cell the plan writes as a formula with its value (section 7); every other cell is a plain value.

### 3.1 Cover

| Template | Plan | Source | Kind |
|---|---|---|---|
| Doc.-No. `F2` | same cell | `ProjectMeta.document.plans[<harness ID>].number` (Q25) | New |
| Version `F3` | same | `plans[<harness ID>].version`, else the harness revision (Q25) | New, with a derived default |
| Release `F4` | same | `plans[<harness ID>].release` | New |
| `PROJECT XXX` `A17` | same | `ProjectMeta.name` | Exists |
| `XXX Harness Plan` `A19` | same | `plans[<harness ID>].title`, else `document.title`, else `<project name> Harness Plan` | New, with a derived default |
| Company `A21` | same | `document.company` | New |
| Contact Information `C36:D40` | same, one row per line | `document.contact`: a list of lines (label, value) in the order entered; a value that starts with `mailto:` or holds one `@` becomes a `mailto:` link | New |
| (none) | a line under the title: the stamp and *This file is written by Harness Design Studio. An export overwrites it; work on a copy.* | the stamp (`outputs/stamp.py`) | Derived |

An empty document field reads `to fill in` on an amber cell, as the build workbook does. The number, version, release and title belong to one plan, so they are kept per harness; the company, the contact lines and the system code are the same in every plan of a project (section 4.4, Q25).

### 3.2 Change_Register

One source of truth: the change log (`project.changelog`, `ChangeEntry`; `system/changelog.csv`). The register mirrors the entries of this harness; nothing is typed into the plan (Q2).

| Column | Source | Kind |
|---|---|---|
| Version | `ChangeEntry.revision`, a version from format 3 (`1.0.0`, `1.1.0`; section 5) | Exists, new type |
| Sub-Version | `ChangeEntry.id` (`C0003`): the running number of the change log | Exists |
| Date | `ChangeEntry.when` (`YYYY-MM-DD`) | Exists |
| Name | `ChangeEntry.by` | Exists |
| Sheets | the sheet name of the harness (`ChangeEntry.harness_id`) | Derived |
| Description | the kind in words (*in review*, *released*, *new revision*, and *version changed* if Q22 is taken), `: `, `ChangeEntry.comment` | Derived |

Rows: the entries of this harness, in entry ID order. The tool's revisions are versions MAJOR.MINOR.PATCH from format 3 (section 5), so the Version column reads as the template's. The users' rule that an incompatible change gets a new harness name is not enforced; section 5.3 says what the tool shows instead. The register's text frame is not written; the Notes sheet says where the change log comes from.

### 3.3 The harness sheet: header and part tables

| Template | Source | Kind |
|---|---|---|
| System `H6` | `document.system`, else the project name | New, with a derived default |
| Harness number `N6` | `Harness.id` | Exists |
| `VERSION:` `Q6` | `VERSION: v<revision> (<status>)`, e.g. `VERSION: v1.1.0 (released)`, as the template's `vx.x.x` | Exists, new type (section 5) |
| `[no SGND*]` `T6` | shown when a box pin of role `signal_ground` (new) on a connector of this harness has no wire in it; else empty | Derived |
| Title `H8` | `"Harness " & H6 & "-" & N6 & ": " & near devices & " <–> " & far devices` with direct references to cell `B1` of each `CON_…` sheet | Derived, F |
| Search strings `I2:I3`, `M2:M3` and their conditional formats | written as in the template, `#` in `I3` and `M3` | Fixed text |
| *used Connectors* rows | one row per connector part of the harness's cable connectors: No. (1, 2 …), Part No. = `Part.id` (the project's ID, which a team may make its InvenTree IPN), Quantity = the number of cable connectors with that part, Remark = the connector IDs and `Part.part_number` | Derived |
| *used Cable Types* rows | one row per wire part used by the harness: No., Part No. = `Part.id`, AWG = the gauges of its wires, Conductor = `Part.specification` (Q15), Colours = the colours of its wires, *No. of wires in cable* = `Part.conductors` (D-188), Length = `=[.N<sum row>]` | Derived; length F |
| Cable type hint | not written: it is the users' rule, not the tool's | — |
| *used Backshells* rows | the harness accessories of kind `backshell` (part, quantity, target and note in Remark); with none, `No backshells.` | Exists |
| Part link `H29` | `Part.link` of the connector's part, as a `text:a` link | New |
| ICD link `B30` | the connector's source (`Connector.source_doc`, `source_link`), a `text:a` link when `source_link` is set | New |
| `CONNECTOR TYPE PLACEHOLDER […]` `H32` | `<part description or ID> [<harness>:<device>:<box connector>]` | Derived, F (refers to the `CON_…` cells) |
| Connector description `F32` | `=$CON_….B11` | Derived, F |

### 3.4 Device side and harness side, per row

One row per pin of the near box connector, in the connector's pin order. Every pin is listed, with or without a wire. The device-side cells refer to the `CON_…` sheet of that connector, cell by cell (`=[$'CON_DEV2-J4711'.A19]`), with no `INDIRECT`.

| Column | Source | Kind |
|---|---|---|
| Pin No. `B` | `Pin.id`; a number cell when the ID is a whole number without a leading zero, else text | Exists, F |
| Function `C` | `Pin.signal` (section 4.2) | Exists, F |
| Direction `D` | the word of the pin (section 4.3): role first, then direction | Exists + New (`signal_ground`), F |
| Level `E` | `Pin.level` | New, F |
| Description `F` | `Pin.function` (section 4.2) | Exists, F |
| Pinout `H`, Function `I` | `=B`, `=C` | F |
| Direction `J` | `IF(D="IN";"OUT";IF(D="OUT";"IN";D))` | F |
| Color `K` | colour rule `pin_code` and the connector's part in a code: `IF(H="";"";VLOOKUP(H;<code range>;2;0))`; else the wire's colour `Wire.colour` | Exists + New config; F or value |
| Cable / Type `L` | the No. of the wire's part in *used Cable Types*; `to fill in` for a wire without a part | Derived |
| Shielding / (Grouping) `M` | the IDs of the shield groups that hold the wire, joined by `, ` | Exists |
| Length [mm] `N` | `Wire.length_m` × 1000, one decimal; `to fill in` without a length | Exists |
| Level `O` | `=E` | F |
| Cable / Type `P` (far) | `=L` on a straight row; the far wires' types on a branch row (section 9) | F or value |
| Color `Q` (far) | as `K`, for the far pin and its connector's part | F or value |
| Direction `R` (far) | the mirrored word of the far pin (`=` the far `CON_…` cell, mirrored as `J`) | F |
| Function `S` (far) | the far pin's signal (`=` the far `CON_…` cell) | F |
| Pinout `T`, `U` … (far) | one column per far connector: the far pins this row reaches (section 9) | Derived |
| Far device side `W:AA`, `AD:AH` … | Pinout as a value; Function, Direction, Level, Description as direct references to the far `CON_…` row of that pin (no `OFFSET`) | F |

A device pin with no wire in this harness: the harness-side cells are empty and the row is yellow (`#ffff99`), as in row 53 of the template, with the template's sentence once per sheet. The tool has no other "deliberately not connected" mark, and this design adds none: the reason belongs in the pin's Description (`Pin.function`).

The conditional format of the template for `GND` against `PWR` is written over the `J` and `R` columns of all harness rows, with the template's formula and style.

### 3.5 Sums and reference pinouts

| Template | Source | Kind |
|---|---|---|
| *Sum of length of cable type [mm]* | one row per cable type: `SUMIF(<L range>;No.;<N range>)/<No. of wires cell>`, with every row range of the sheet that holds wires (the near rows and, on a branching harness, the further wires of section 9) | F |
| (none) | a cell beside each sum: `n wires without a length` when there are any | Derived |
| Reference pinout, per far connector | the far connector's ID, its links, `Data from CON_…`, then one row per pin: Pinout, and Function, Direction, Level, Description as references to its `CON_…` sheet | F |
| *Used in Row* | `IF(ISNA(MATCH(pin;<far pin column>;0));"";MATCH(pin;<far pin column>;0)+<row before the table>)` | F |
| Picture *BLOCK DIAGRAM incl. Lengths* | not written in 3.0.0; a text cell names the harness drawing (`harnesses/<ID>/drawing_A3.pdf`) when the export has the drawings | Q12 |

### 3.6 `CON_…` sheets

One sheet per box connector that this harness plugs into, at either end, named `CON_<box connector ID>` (the IDs are unique in the project and use only letters, digits, `_`, `-` and `.`, so they are valid sheet names). A loose end has no sheet. The sheet of one box connector is the same, cell for cell, in the plan of every harness that plugs into it.

| Row | Source | Kind |
|---|---|---|
| Device `B1` | `Connector.unit_id` | Exists |
| Connector ID `B2` | `Connector.id` | Exists |
| Interface Name `B3` | the names of the interfaces that end on the connector, sorted, joined by `; ` | Derived |
| Connector Type `B6` | `Part.description` of the connector's part, else its ID | Exists |
| Number of Pins `B7` | `Part.pin_count`, else the number of pins | Exists |
| Gender `B8` | `Connector.gender` | Exists |
| Connector Name/Part Number `B9` | `B6 & " " & B7 & " " & B8`, as in the template | F |
| Connector Description `B11` | `B1 & " [" & B2 & "]: " & B3 & "; " & B9`, as in the template | F |
| Link to ICD `B13` | `Connector.source_doc`, linked to `Connector.source_link` | New |
| ICD version `B14` | `Connector.source_version` | New |
| CON sheet copied from `B15` | the device library record of 2.2.0 (`devices:<file>`, D-240): the library file and *up to date* or *library changed*; empty for a device that is not linked | Exists (2.2.0) |
| Last update `B16` | not written: the tool keeps no dates in design data | — |
| Pin table from row 18 | Pinout, Function, Direction, Level, Description: the plain values of the pins (the source of the references above) | Exists + New |

### 3.7 Notes and About

**Notes:** each colour code that an end of this harness uses (section 6) as a table Pin, Color, headed as an example while it is marked so; the project's note lines (config `harness_plan.notes`, plain text, for example the users' labelling and level notes); and a fixed legend: what each Direction word means, that yellow marks a pin with no wire, which cells hold formulas, and that an export overwrites the file. **About:** the stamp, the full model hash and the notice, as on the About sheet of the workbooks, so the verifier finds the stamp where it finds it in an `.xlsx`.

Sheet order: Cover, Change_Register, the harness sheet, Notes, the `CON_…` sheets in connector ID order, About. The harness sheet is named after the harness ID; the template's `<system>-<harness>-<devices>` would pass 31 characters (the limit of some spreadsheet programs) with long IDs, and the devices are in the title.

## 4. New in format 3

### 4.1 The fields

| Field | Type, default | Set by | Shown in the editor | Import | Migration 2 → 3 |
|---|---|---|---|---|---|
| `Pin.level` | `Name \| None`, `None`; sparse | a person; an import | Devices tab, pin table column *Level* (box pins); the Inspector of a pin | `import-pinout` column *Level*; device library files | nothing written |
| `PinRole` value `signal_ground` | a new value of the list | a person; an import | the role choice of a pin (*Signal ground*) | the Direction word `SGND` | nothing: no pin gets it |
| `Part.link` | `WebLink \| None`, `None`; sparse | a person; the parts import | the Inspector of a part; a *Link* column in the Library window | `import-parts` column *Link* (also *URL*) | nothing |
| `Connector.source_doc`, `source_version` | `Name \| None`, `None`; sparse | a person; an import | the Devices tab, the details of a connector | `import-pinout` columns *Source* (also *ICD*) and *Source version* (also *ICD version*) | nothing |
| `Connector.source_link` | `WebLink \| None`, `None`; sparse | as above | as above | column *Source link* | nothing |
| `ProjectMeta.document` | `DocumentInfo \| None`, `None`; `ProjectMeta` becomes sparse for this one field | a person only | *Settings > Project > Document*; the per-harness part in the Inspector of a harness (Q25) | none | nothing |
| `config/harness_plan.json` | an optional config file, not in `default_configs`: `colour_rule` (`wire` or `pin_code`, default `wire`), `colour_codes` (default none; each code may carry `"example": true`, Q26), `notes` (default none) | a person only; the example code only when a person takes it | *Settings > Project > Harness plan* | none | not created |
| `Harness.revision`, `Baseline.revision`, `ChangeEntry.revision` | `Version` (`MAJOR.MINOR.PATCH`) instead of free text; a new harness starts at `1.0.0` | `revise`, with the kind a person chooses; generation for a new harness | where the revision is shown today (section 5.4) | none | each value mapped (section 5.5); `Baseline.id` and its file name follow |
| `ChangeKind` value `version_changed` | a new value of the list | `revise --kind` on a draft (Q22) | the change log | none | nothing |

`DocumentInfo` (sparse; each text left out while empty): `system`, `title`, `company` (each `Label`, up to 200 characters), `contact`, a list of at most eight lines `{label: Name, value: Label}`, and `plans`, a map from harness ID to `{number, version, release, title}` (each `Label`) for the Cover of that harness's plan (Q25). A list keeps the template's four lines (name, phone, fax, e-mail) without a field for each, and a team without a fax leaves it out. A key of `plans` that names no harness gives a `check` warning; `merge-fix` renames a key with the harness (M7b, D-231). The map is project data, not part of a harness, so the release freeze does not lock it: a person can fill in the Release cell of a released harness's plan.

`WebLink` is new in `core/model/base.py`: text up to 2000 characters that starts with `https://` or `http://`, with no space and no control character. The plan writes it as a link. Any other link (a `file:` URL, a path on a share, as in the template) is refused as a link; a person writes it into `source_doc` as text. A written file that opens links to local paths is a risk the plan does not take.

### 4.2 Function and Description: no new field

The template has two text columns per pin; the model has two: `Pin.signal` and `Pin.function`.

- **Option A (recommended):** Function = `Pin.signal`, Description = `Pin.function`. This is how `import-pinout` reads a sheet today: a heading *Function* alone means the signal, and *Pin function* means `Pin.function` (`core/pinout_import.py` `_ALIASES`). *Description* is today an unstored heading named in a warning; in 3.0.0 it becomes an alias of `function`. No field is added.
- **Option B:** a new `Pin.description` (Text). Function = `Pin.function` if set, else `Pin.signal`. Three texts per pin, two of them close in meaning; the import's existing reading of *Function* would have to change.

Option A keeps the model smaller and the import consistent (owner question Q6). `Pin.function` is limited to 200 characters; a longer description is refused at import with the row named.

### 4.3 Level, SGND and the Direction words

**Level: per pin, or per interface type with a pin override.** The template's levels come from the ICD of each device (`CON_…` sheets): `RS422-3V3`, `TTL-5V`, `18V`. A level per interface type is short to enter, but one type serves devices at different levels (RS-422 at 3.3 V and at 5 V; one power type for 18 V and 3.3 V), so most pins would need the override, and two places would answer one question. A level per pin travels with the device into the device library (2.2.0) and comes from the same pinout import as the rest of the pin. **Recommendation:** `Pin.level` only, free text, no derived value; an empty level is an empty cell. `InterfaceInstance.voltage_v` stays what it is and is not shown as a level.

**SGND: a role value or a direction value.** `Pin.direction` says which way a signal runs at the pin (`in`, `out`, `bidir`); SGND says what the pin is for. `Pin.role` already holds `power`, `return`, `ground`, `signal`, `shield` and `spare`. **Recommendation:** a new role value `signal_ground` (owner question Q7). It is set only by a person or an import, never derived from a name: `links.effective_role` today reads a pin named `SGND` as `signal`, and changing that would change the findings of existing projects. The link checks treat `signal_ground` as they treat `ground` (no direction conflict, no power-without-return effect); the verifier's own copy of the role (`outputs/verify.py` `_pin_role`) returns a set role as it is. Pin allocation categories are interface categories and are not touched.

**The Direction word of a pin**, in this order: role `power` → `PWR`; `return` → `PWR-RET`; `ground` → `GND`; `signal_ground` → `SGND`; `shield` → `SHIELD`; `spare` → empty; otherwise direction `in` → `IN`, `out` → `OUT`, `bidir` → `IN/OUT` (the template has no word for it; owner question Q16), not set → empty. The role is the effective role (`links.effective_role`), so a derived power pin reads `PWR`. On the harness side `IN` and `OUT` swap; the other words stay.

**The import reads the users' words.** `import-pinout` and the device import map a Direction cell: `PWR`, `PWR-RET`, `GND`, `SGND`, `SHIELD` and `SPARE` to the role; `IN`, `OUT`, `IN/OUT` and today's words (`devices._DIRECTION_WORDS`) to the direction. Any other word (the template's `TEST`) leaves role and direction unset, and the import record lists the row and the word under converted values (`ConvertedValue`, read `TEST`, stored *not set*). The row is not refused.

### 4.4 Document data and the change register

**Document data** lives in `project.json` as `meta.document`: the company, the contact lines and the system code once per project, the number, version, release and title once per harness (Q25). It is part of the design, so it is in the model hash: a new phone number makes every plan out of date, as it should, because every plan shows it. It is set only in the editor (and by a command, section 10). It is written into the Cover of the plans and nowhere else: not into `export.json`, not into any other output, not into a log. **Privacy:** a contact name, phone and e-mail in `project.json` go into the project's Git history. The user manual says so and suggests a role address where a team prefers one (owner question Q14).

**The change register mirrors the change log** (section 3.2). A register kept in the plan or in a new list would be a second source for the same events, and the two would drift. The document's own version (`document.plans[<ID>].version`) is a person's field; the tool does not count it up. While it is empty the Cover shows the harness revision, which is now a version in the users' form (section 5, Q25). Not in 3.0.0: register rows that are not changes of a harness (owner question Q2).

### 4.5 Migration and compatibility

- **The step from 2 to 3** (`core/io/migrate.py`, a new `_v2_to_v3` with `V2_TO_V3_PARTS`) writes the number and the revisions (section 5.5). Every new field is absent, so it has its default; no pin gets `signal_ground`; no config file is created. `ProjectMeta` becomes sparse only for `document`, so `project.json` keeps its bytes apart from the number.
- **The proof** is the migration safety net (`core/io/upgrade.py`), changed for this step because the revisions change: the model hash changes once. Section 5.6 has it in full. In short: a comparison that leaves out the revisions finds the same design, the same findings and the same release consistency; every revision is checked against the mapping; and a test shows, for every fixture project and example, that an export without `--harness-plan` differs from the files of 2.x only in the stamp and the revision text. The output-hash baseline (`docs/ui/OUTPUT_HASHES_BASELINE.json`) is made again once, in the pull request of format 3.
- **Older tools** open a format 3 project read-only (the rule of D-226). A 2.x tool would otherwise drop `level` and the source fields on its next save, or quarantine pins with the new role.
- **The device library file** (`harness-device-library`, version 1, D-165) is read with the strict models, so a 2.2 tool refuses a pin with `level`. A 3.0 tool writes a device file as **version 2 only when one of its devices uses a new field**, else version 1 as before. A 2.2 tool then refuses that one file with *a newer version* and still offers the others (the folder rules of D-240).
- **Other outputs:** a *Level* column appears in `box_pinouts.csv`, `export-pinout` and the Devices table only while a pin has a level, by the sparse rule. `export.json` carries the new pin, part and connector fields when they are set; it never carries `document`. Every other output is unchanged apart from the stamp and the revision text (section 5.4).
- **The 2.2 library update** compares the connectors in portable form; the new pin and connector fields are library-owned and show in its diff.

## 5. Revisions as versions MAJOR.MINOR.PATCH

The owner decided on 2026-11-17 that the tool's revisions become versions in the users' form, MAJOR.MINOR.PATCH (Q9), and that the change joins format 3 (Q10). It is the largest change of 3.0.0: it touches the model, the change control, every output that shows a revision, the migration and the editor. This section designs it; Q18 to Q24 ask what is still open.

### 5.1 Today

- `Harness.revision` is a `Name`: any text of 1 to 200 characters, `"A"` by default (`core/model/physical.py`). Generation gives a new harness `"A"` and keeps the revision of a harness it makes again (`generate/engine.py`).
- `revise` counts letters: A, B … Z, AA, AB (`vcs/release.py` `next_revision`). A revision that is not upper-case letters is refused with *rename it before starting a new revision*. Nothing in the tool writes such a value, so only a hand-edited file or a merge can hold one.
- A baseline is named `<harness>.<revision>` (`Baseline.id`; `integrity.py` reports `baseline_id_mismatch` otherwise) and stored as `baselines/<harness>/<baseline ID>.json`. Its snapshot holds the harness with its revision. A change-log entry records the revision at the event (`ChangeEntry.revision`).
- Order: `vcs/report.py` `baselines_of` sorts by length, then text, which is the letter order. The editor's top bar shows the lowest and the highest revision of the project, sorted as text (`gui/main_window.py` `_revision_text`). `describe.py` calls a draft *revised* when its revision is not `"A"`.
- The release freeze (`vcs/locks.py` `_is_new_revision`) lets a released harness change only into its next revision: another revision, status draft, the same content.
- The revision is written into the drawings (the title block field *revision*, and `Revision A  status draft` in the header), the *Start here* sheet of the build workbook (`Revision A · status …`), `system/changelog.csv` (column *Revision*), `system/revision_report.md` (*revision A released*, *revision A to B*) and `system/export.json` (`"revision": "A"` per harness). The labels (`labels.csv` and the labels of the build workbook) show no revision.
- The model hash reads every revision, so the stamp of every output (`model <hash>`) depends on them. `content_hash` (`vcs/hashing.py`) removes the status and the names of the release, not the revision. The generation input hash (`generation_status.input_hash`) does not read revisions.

### 5.2 The field

- A new type `Version` in `core/model/base.py`: the text `MAJOR.MINOR.PATCH`, three whole numbers from 0 to 9999, written without a leading zero and without a prefix: `1.0.0` and `1.10.2`, not `01.0.0`, `v1.0.0` or `1.0`. There is one way to write each version, so two equal versions are equal text, and a file name can hold it.
- `Harness.revision`, `Baseline.revision` and `ChangeEntry.revision` take the type. The field names stay `revision`, so the file format changes in its values only.
- Versions are put in order by their three numbers, never as text: `1.10.0` comes after `1.9.0`. One function does it, `core/vcs/revisions.py` `version_key`, wherever revisions are sorted.
- A new harness starts at `1.0.0`, as the first row of the template's register. Generation gives `1.0.0` where it gives `"A"` today.
- Draft, in review and released stay the status. The version does not carry it: a draft after *revise* carries the version it will be released as (Q19).
- A baseline stays named `<harness>.<version>`: `W001.1.2.0`, a valid ID, stored as `baselines/W001/W001.1.2.0.json`. An ID has at most 64 characters, so a harness ID of more than 58 characters leaves no room for a version such as `1.0.0` (with one letter the limit is 62 today). The release names this limit as a blocker instead of failing in the model check.

### 5.3 Revise: a person chooses major, minor or patch

- `revise` asks for the kind: `--kind major|minor|patch` on the command line, required; three choices in the *New revision* dialog, none chosen at the start. The next version is worked out from the released one: from `1.4.2`, major gives `2.0.0`, minor `1.5.0`, patch `1.4.3`. The dialog shows it before the person confirms (`1.4.2 → 1.5.0`).
- The texts of the choices follow the template: *major: not compatible with the versions before it*; *minor: adds something and stays compatible*; *patch: a fix that stays compatible*.
- The new version must be higher than every baseline of the harness. A step back is refused (`version_not_higher`), also when a merge brought in a baseline.
- **No suggestion at revise** (Q20). At *revise* the draft is still the released design, so there is no diff to read yet.
- **A note at review and release** (Q20). The diff against the last baseline (`vcs/diff.py`) can show a change at an end that plugs into a device: a cable connector's part, gender or keying, the box connector it mates with, or a wire added, removed or moved at such a connector. When it does and the kind is minor or patch, the review and release dialogs and commands show a note: *This revision changes the pinout at a device. The harness plan template calls that an incompatible change.* The note changes no version and blocks nothing. Between minor and patch the tool says nothing: that difference is about intent, which a diff does not show.
- **A note at a major revise** (Q21). When a person chooses major, the dialog and the command say: *A major revision says that this harness is not compatible with its earlier versions. The harness plan template gives such a harness a new ID instead (TH01 becomes TH02, not TH01 2.0.0).* The person can go on. The tool does not enforce the naming rule in 3.0.0. What it could do later: a project setting in `config/naming.json` (`major_revision`: allowed, note or refused), and a command that copies a released harness to a new ID as a draft.
- **The kind can be chosen again** while the harness is a draft that has a baseline, before its review (Q22): `revise --kind` on such a draft works the version out again from the released one and adds one change-log entry of the new kind `version_changed`.

### 5.4 What each command and screen shows

| Where | Format 2 | Format 3 |
|---|---|---|
| `review`, `release` | `Release W001 revision B` | `Release W001 revision 1.1.0`; the note of section 5.3 |
| `revise` | the next letter | `--kind` required; the note on a major revision; `--json` adds `kind` |
| `diff --from`, `--to` | a letter | a version; an old letter is read as its version by the rule of section 5.5 (`B` is `2.0.0`), and the output says so once (Q18) |
| `log`, `system/changelog.csv` | column *Revision*, letters | column *Revision*, versions |
| `compare OLD NEW` | — | a format 2 folder is read through the step in memory, as format 1 is today, so its letters read as versions and the mapping is not shown as a change |
| change log, baselines | letters | versions; `Baseline.id` is `<harness>.<version>` |
| release freeze | the next revision: another revision, draft, the same content | the same, and the new version is higher |
| build workbook, *Start here* | `Revision B · status …` | `Revision 1.1.0 · status …` |
| drawings | title block field *revision*; `Revision B  status draft` | the same, with the version |
| labels | no revision | no revision |
| `system/revision_report.md` | `revision B released`, `revision A to B` | the same words with versions, in version order |
| `system/export.json` | `"revision": "B"` | `"revision": "1.1.0"`, still a string |
| the harness plan | — | `VERSION: v1.1.0 (released)`; the register's Version column |
| the verifier | reads the change log by entry ID | the same; its own `version_key` where it compares an order |
| the editor | the Releases panel column *Revision*, the Inspector, the top bar, *New revision…* | the same places with versions; the top bar's range in version order; the dialog of section 5.3 |

The word stays *Revision* on screen and in the written files, apart from the plan, which writes the template's *VERSION* (Q23). So a written file changes in the value only.

### 5.5 The migration from format 2

**The mapping** (Q18):

- An upper-case letter revision becomes `N.0.0`, where N is its place in the tool's letter order: `A` → `1.0.0`, `B` → `2.0.0`, `Z` → `26.0.0`, `AA` → `27.0.0`. The same rule holds for the harness, each of its baselines and each of its change-log entries, released or draft.
- A revision that is already a version (`1.2.0`, possible today only by hand) is kept.
- Any other value (`b`, `A1`, `01`, `-`, `1.0`) is not guessed. `migrate --dry-run` lists each one with its harness, and `migrate` refuses until each has a version: `migrate --revision W001:A1=1.1.0`, which can be given more than once. The editor's upgrade question shows the same list and stops.
- Also refused: two old revisions of one harness that would give the same version, and a mapping that would put a harness's baselines in another order than its change log.

**Why `N.0.0`.** The order stays: the letter order (length, then text) is the order of N. Anyone can read an old letter back: B is 2. And it claims no compatibility that nobody checked: a letter said nothing about it, while a minor or patch step says *compatible*. It does go against the template's rule *never raise MAJOR* for harnesses revised before 3.0.0; that history was made under letters. The other mapping, `A` → `1.0.0`, `B` → `1.1.0`, keeps MAJOR at 1 but says that every old revision was compatible.

**What the step writes:**

- `project.json`: the number 3.
- `physical/harnesses/<ID>.json`: `revision`.
- `changelog.json`: the `revision` of each entry.
- `baselines/<harness>/`: the file of each baseline under its new ID, and the old file removed. In it, `id`, `revision` and the revision of the harness in its snapshot change; nothing else does. Its `content_hash` stays the value recorded at the release: it is a record of that day and is not worked out again.
- The journal: old lines keep their letters, because they say what happened. The step's journal entry *migrated from format 2* lists the mapping (`W001: B → 2.0.0`), and so does the migration record (`MIGRATION.json`).

**After the step**, outputs exported before it read *out of date*: the content hash reads the revisions. The editor and `release` ask for an export, as after any change. A released harness keeps its baseline; its files, exported again, show the version.

### 5.6 The proof that only the revisions change

The step from 1 to 2 changed no hash. This step changes the model hash once, because the revision text is in the design files. The proof has three parts.

1. **Nothing but the revisions** (a check of every `migrate`, in `core/io/upgrade.py`). Both sides are read as files: the format 2 files as saved, and the format 3 files the step writes. In each, every revision value and baseline ID is replaced by its place in its harness's order, and the format number is read as 1 (`schema_one`). The two hashes must be equal. The findings of `validate` and `check` must be the same, compared by code and object, with the revision text in their messages read the same way. The consistency of the released harnesses (`release_integrity`) must give the same result. Any difference: the upgrade puts every file back, as today.
2. **The revisions are the mapping** (the same check). For every harness, baseline and change-log entry, the new version is the mapping of the old value, one by one.
3. **The written files** (a test, `tests/test_format3.py`). The run-time check cannot make an export of the old project: format 3 refuses a letter, so the old files cannot be read as they are, and the migration record says *exports not compared* with that reason, as `plan_upgrade` already does for a format it cannot read. So a test does it for every fixture project and example: it compares a 3.0 export with the goldens and the output-hash baseline of 2.x, file by file. Text files are compared line by line, the `.xlsx` files cell by cell, the SVG and PDF drawings by their text items and positions. Each difference must be the stamp (the tool version and the model hash), the revision text, or something that follows from the length of that text: a column width of the build workbook taken from its widest text, or a text cut by `fit` in a title block. Any other difference fails the test.

**Merges across the upgrade.** A branch still in format 2, merged into a branch in format 3, can bring a letter into a format 3 file. The loader refuses that file with `revision_not_version` and names the version the letter maps to; `merge-fix` rewrites such letters by the rule of section 5.5. The user manual says: upgrade on the main branch, then bring the other branches up to date before they merge.

### 5.7 Where the code changes

- `core/model/base.py` (`Version`), `core/model/physical.py`, `core/model/review.py` (the fields; `version_changed`).
- `core/vcs/revisions.py`, new: `version_key`, `bump(version, kind)`, `letter_to_version`, and the pinout test of section 5.3.
- `core/vcs/release.py`: `plan_new_revision(kind=…)`, the blocker on the ID length; `next_revision` goes.
- `core/vcs/locks.py`: `_is_new_revision` also needs a higher version. `core/integrity.py`: `version_not_higher`.
- `core/vcs/report.py` `baselines_of`, `gui/main_window.py` `_revision_text`, `core/describe.py` (a draft is *revised* when it has a baseline).
- `core/generate/engine.py`: `1.0.0` for a new harness.
- `core/io/migrate.py` and `core/io/upgrade.py`: the mapping, the checks of section 5.6, `--revision`.
- `cli/changes.py` (`--kind`; an old letter in `diff`), `cli/main.py` (`migrate --revision`), `core/merge_ids.py` or `cli/merge.py` (the letters after a merge).
- The editor: `gui/releases_panel.py`, `gui/inspector.py`, the strings.
- The schemas, `docs/FILE_FORMAT.md`, `docs/CLI.md`, and a user manual page *Revisions*.

## 6. The colour rule by pin number

Today a wire's colour is the person's, or the one `generation.wire_colour_by_signal` gives its signal (`core/wirecolours.py`, `generate/engine.py`). The template colours each **end** by its pin number, because a micro-D connector with pigtails comes with its wires coloured by pin position. One wire of the model can then have a colour at each end that differs from the other end. So the rule belongs to the plan's end columns (`K` and `Q`), not to `Wire.colour`.

**Configuration** (`config/harness_plan.json`, optional, section 4.1):

```json
{
  "name": "harness_plan",
  "placeholder": false,
  "values": {
    "colour_rule": "pin_code",
    "colour_codes": {
      "example": {"example": true, "parts": ["P-MDM-15S-PIG"], "colours": {"1": "Black", "2": "Brown"}}
    },
    "notes": ["The label of a line that is not connected says so (no SGND)."]
  }
}
```

- `colour_rule` `wire` (default): `K` and `Q` show `Wire.colour`, as plain values.
- `colour_rule` `pin_code`: an end whose connector part is listed in a code gets the code's colour for its pin, as a formula over the code's table on the Notes sheet (`VLOOKUP(pin;$Notes.$B$7:.$C$43;2;0)`, exact match). Any other end shows `Wire.colour`.
- Keys are pin IDs as text and match exactly: pin `01` matches only the key `01`. A pin the code does not list reads `to fill in`, and `check` warns once per connector (`plan_colour_missing`).
- A part in two codes is refused by `validate` (`config_invalid`). Colours are names as typed (`Wh / Bl / Brown`); the tool does not check them against IEC 60757 (`wirecolours.resolve` keeps an unknown colour as typed and draws it grey).
- Generation does not read the codes; `Wire.colour`, the build workbook and every other output are unchanged. The generation input hash (`generation_status.input_hash`) reads every config file today, so it leaves out `harness_plan`, as it leaves out the part of a loose end: a new colour code must not make the harnesses look out of date. A release does not freeze the file (it is not in `snapshot.FROZEN_CONFIG_FILES`).

**The users' colour code ships as an example** (the owner's answer to Q3). The table of the template's Notes sheet, *uD Pigtail Colour Code*, pins 1 to 37 (appendix A), ships in the program as `resources/examples/templates/pigtail-colour-code-EXAMPLE.csv`: two columns, `Pin` and `Colour`, one row per pin, with a row in the templates' `README.md` that says what it is. The file comes with the pull request that builds the colour rule (section 12); until then the table is in appendix A of this page. It is the colour code of the owner's users' template: an example, not a standard and not a supplier's table. A team checks it against the pigtail code of its connector supplier before it relies on it.

- **It is never applied by itself.** A new project has no colour code, and `colour_rule` stays `wire`. No example project uses it.
- **A person takes it on purpose.** *Settings > Project > Harness plan* has a button *Use the example colour code*. It adds the table as the code `example`, marked `"example": true`, and asks for the connector parts it applies to, because the template names none (Q26). `harness-design-studio templates FOLDER` copies the CSV file; the Settings page's paste reads it like any table of two columns.
- **It stays marked.** While the mark is on, the plan's Notes sheet heads the table *Example colour code from the users' template: check it against the supplier's pigtail code*, and `check` gives a note once (`plan_colour_example`). A person takes the mark off in Settings once the code is checked. The mark is not the placeholder flag of the config file, which would block every release for a value that only the plan shows (Q26).

**Why this keeps the rule *never invent standard values*** (D-11, D-12, `CLAUDE.md`). The rule is about values that the tool would make up, or would present as a standard's or a programme's. This table is neither. The owner supplied it, from the users' own template, and decided on 2026-11-17 that it ships as an example. The tool says where it comes from and nothing more: it does not claim that the table follows IEC 60757 or any supplier's code. It applies the table only after a person takes it, and labels it an example wherever it shows it. The demo values of D-129 ship the same way, labelled and never used without a person's step. D-242 records the decision.

## 7. Formulas and determinism

### 7.1 Which cells get formulas

**A formula where the cell is a pure function of other cells of the same file and a person who edits the source cell expects the cell to follow:** the device-side copies of the `CON_…` sheets, the harness-side copies (`H`, `I`, `O`), the mirrored directions (`J`, `R`), the colours by pin code (`K`, `Q`), the titles and connector descriptions, the sums per cable type and the cable type lengths, and *Used in Row*. **A plain value for everything the model holds:** the pins of the `CON_…` sheets, wire lengths, cable type numbers, shield groups, parts, document data, register rows, and the far pins of each row. The model is the source; a formula over another cell can only repeat it.

Every formula cell carries its value as well (section 7.3). An export overwrites the whole file, formulas and typed changes alike. The Cover, the Notes and the About sheet say so (owner question Q4).

### 7.2 The formula dialect

- Every formula is OpenFormula with the `of:` prefix (ODF 1.3, part 4), with references in its form (`[.B34]`, `[$Notes.$B$7:.$C$43]`, `[$'CON_DEV2-J4711'.A19]`).
- **The functions used:** `IF`, `ISNA`, `VLOOKUP` (four arguments, exact match), `MATCH` (exact match), `SUMIF`, and the operators `&`, `=`, `/`, `+`. A closed list: a formula outside it is a defect the verifier reports (section 7.5).
- **No `COM.MICROSOFT.CONCAT`, `COM.MICROSOFT.IFS`.** They are spreadsheet functions of another program stored under its prefix; they are not part of OpenFormula. LibreOffice reads them; other readers of ODF may not. `&` and nested `IF` do the same here.
- **No `INDIRECT`, `ADDRESS`, `OFFSET`.** They build references from text or numbers at recalculation time. They are volatile (recalculated on every change), they break without a word when a sheet is renamed or a row is inserted, and nobody can tell from the formula text which cell it reads, so the verifier could not check it. The template's address text also uses `!` as the sheet separator, which is the A1 syntax of another program; whether a reader accepts it depends on the reader. The tool knows every address when it writes the file, so a direct reference does the job.
- **No `HYPERLINK`.** A link is a `text:a` element in the cell, as the template's part link already is.

### 7.3 The bytes of the package

- `mimetype` first, stored (not compressed), with no extra field: `application/vnd.oasis.opendocument.spreadsheet`.
- Then `META-INF/manifest.xml`, `meta.xml`, `styles.xml`, `content.xml`, in that order. The manifest lists every file: LibreOffice refused a test package whose `meta.xml` was not listed (section 7.4).
- **Every entry is stored, not compressed.** The `.xlsx` files are deflated (`exports.normalise_xlsx`); deflate output depends on the zlib build (zlib-ng, as some Linux systems ship, writes other bytes than zlib for the same input). Stored entries remove the question. The cost is size: the plans of a large project together take several megabytes instead of a few hundred kilobytes (section 13).
- Each entry: date 1980-01-01 00:00:00, `create_system` 3, `external_attr` `0o644 << 16`, set explicitly. Python's `ZipInfo` sets `create_system` from the platform (0 on Windows, 3 elsewhere).
- `meta.xml` holds the title and `meta:generator` (`Harness Design Studio <version>`) only: no dates, no creator, no editing cycles, no statistics. No `settings.xml`, no thumbnail, no `Configurations2/`.
- The XML is written by our code: UTF-8, fixed attribute order, no pretty printing, escaping as in `outputs/canvas.py` (`canvas.escape`; `xml.sax.saxutils` is not imported, because it imports network modules at import time). Automatic style names are numbered in the order of a fixed walk of the sheets. Rows are in pin order, sheets in the order of section 3.7, numbers without an exponent.
- A **formula cell** has `table:formula`, `office:value-type`, and its value: `office:value` for a number, `office:string-value` for text, and the shown text in `text:p`. Text never needs the CSV guard against formulas (`'+5V`): an `.ods` text cell is text, and only `table:formula` is a formula.
- The stamp and the notice are on the About sheet, on the Cover and in the footer of every printed sheet. `manifest.json` lists each plan with its SHA-256, as every output.

### 7.4 What a reader does with the stored values

A small test package was written by hand for this design and converted to CSV with LibreOffice 24.2 in headless mode, with its default settings. Number cells showed the recalculated value even when the stored one was wrong. Text cells showed the **stored** text even when the formula gave another. The result did not change with the `meta:generator` of the file. So a reader may show either the stored value or the computed one: **the stored value must equal what the formula gives**, and the verifier checks it (section 7.5). Other readers and other settings were not tried.

### 7.5 How the verifier checks the plan

A new module `core/outputs/verify_plan.py`, called from `verify_outputs` for each plan that `manifest.json` lists. It does not import the writer or the layout module. It also reports a plan of a harness that is no longer in the design, and a harness without a plan in an export that has plans.

1. **The package:** the entry order, `mimetype` first and stored, every entry stored, the fixed dates, the manifest listing exactly the entries.
2. **The XML** is parsed with `xml.etree.ElementTree` after a DOCTYPE or ENTITY declaration is refused, as `core/kicad.py` does.
3. **The cells:** the verifier derives on its own, from the project, the sheet list and for every cell the expected text, value type and value, and for formula cells the expected formula text. Its own copies of the sides rule (section 9), the Direction words and the colour lookup are compared with the core's by a test, as the ports parser of 2.1.0 was (`tests/test_ports_checks.py`).
4. **Formula and value agree:** a small evaluator for the closed list of section 7.2 computes every formula over the stored cells and compares the result with the stored value. A formula outside the list is an error.
5. Errors are `out_plan` (a cell, with its sheet and address), `out_plan_formula` (a formula that differs from the expected text, is outside the list, or does not give its stored value) and `out_plan_package`. The stamp check reads the About sheet. A plan that was edited in `outputs/` fails `out_modified`, as an edited build workbook does.

Not checked by the verifier: the styles, the column widths, the conditional formats beyond their formula text, the print set-up, and how a spreadsheet program shows the file.

## 8. Writing `.ods`: our own writer or a library

| | Our own writer (`core/outputs/ods.py`) | odfpy |
|---|---|---|
| What it is | about 500 lines: the package, the manifest, a style table, cells (text, number, formula with value, spans, `text:a`), column widths, page layout, print ranges, conditional formats | odfpy 1.4.1 (2020, the latest), Apache-2.0 or GPL-2.0-or-later (its `setup.py`; its classifiers add LGPL); needs defusedxml |
| Determinism | by construction (section 7.3) | zip dates from `time.localtime()`, picture names from `uuid4()`, its own generator in `meta.xml`: the package would be rewritten afterwards, as `normalise_xlsx` does for openpyxl |
| The offline rule | imports nothing new | `odf.opendocument` imports `odf.odfmanifest`, which imports `xml.sax.saxutils` at import time: the `core` rule forbids that (`docs/developer/agent/outputs.md`) |
| Dependency rules | none | a decision row with name, version and licence (`CLAUDE.md`, D-125), the SBOM, the licence texts in `LICENSES/`, the notices, the package and the offline audit |
| Upkeep | ours | a library without a release since 2020 |

**Recommendation:** our own writer. The subset of ODF the plan needs is small and fixed, and every byte is ours to test.

## 9. Branching

The plan has a **near end** (blocks of rows, one per connector) and a **far end** (one column group per connector). A harness's cable connectors are split into the two ends by a fixed rule:

1. Build a graph: a node per cable connector of the harness, except splices, whose pins are one net (the splice of `PLAN_2.0.md` section 2.4: role `splice`, bonded pins; the design of 2.3.0 may change this, and pull request 6 follows what 2.3.0 builds). Two connectors are joined when a net of the harness, through wires and splices, reaches both.
2. Colour the graph in two by a walk in breadth from the first connector in natural ID order, neighbours in natural ID order. A connector without a wire joins the first end.
3. The end with more connectors is the near end (rows grow better than columns); on a tie, the end of the first connector.

**Rows.** One row per pin of a near box connector. A pin has at most one wire (`A-PIN-ONE-WIRE`); that wire gives Cable / Type, Shielding, Length and the near colour. The far pins are every pin of a far connector on the same net, through splices. A row that reaches two far connectors fills a pin in each column (`T`, `U` in the template); two pins of one far connector are joined by ` + `. On such a row the far cells `P` to `S` list the values of each far wire in column order, joined by ` + `.

**Further wires.** A block under the near rows lists every wire that does not end on a near pin: wires beyond a splice, and wires between two connectors of one end (when the graph cannot be split in two, as with three connectors wired in a ring). Columns: wire, from, to, Cable / Type, Shielding, Length, colour. Every wire of the harness appears in exactly one row of the sheet; the verifier checks that, and the sums per cable type include both blocks.

**A straight harness** has one near block, one far column group and no further wires: `Harness SYS-W001: OBC1 <–> STR1`. **A branching harness** of 2.3.0, for the template's case, gives `Harness SYS-W003: DEV2 + DEV3 <–> DEV1 + DEV4`, two near blocks, two far column groups, and the wires beyond the splice under *Further wires*. A loose end is a far column headed `open end, to fill in` with no `CON_…` sheet. A harness with an inline or test connector shows it as a connector of its end; it has no device side unless it plugs into a box connector.

## 10. Editor and command line

- **Export:** `harness-design-studio export DIR --harness-plan` writes one plan per harness, `harnesses/<ID>/<ID>_plan.ods` (Q1); without the option none is written, and an export without it into a folder whose last export had plans removes them and says so (as `--drawings` does, D-169). The option is one choice for all harnesses, as `--drawings` is (Q13, Q27). `harness_plan_exported(folder)` reads the manifest; the re-export at a release (`cli/changes.py`) keeps the choice, and the release of one harness changes its plan only (the status and the register). `--json` gets `harness_plans`, a list of the files. `verify DIR --outputs` checks each plan the manifest lists. The library call `build_outputs(project, harness_plan=False)` keeps the default off.
- **Why not always on** (owner question Q13, answered as recommended): an always-written plan adds a file per harness to every export, so the exports of 3.0.0 would no longer match those of 2.x apart from the stamp, and every project would pay for a file most do not use.
- **The Export window:** a second check box under *Include the PDF drawings*: *Include the harness plans (.ods), one per harness*, ticked at the start when the folder's last export had them. The result panel lists the files; there is no preview of `.ods`, and *Open* uses the system's program.
- **Settings > Project > Document:** what every plan of the project shares: system code, title (with its default shown), company, and the contact lines (add, remove, move). **The Inspector of a harness**, section *Plan document*: the document number, version (with the harness revision shown while it is empty), release and title of that harness's plan (Q25). Each change is one undo step and goes into the journal.
- **Settings > Project > Harness plan:** the colour rule, the codes (name, parts, the table of pins and colours with a paste of two columns, the example mark), the note lines, and the button *Use the example colour code* (section 6). It writes `config/harness_plan.json`; the file is created by the first value and removed when every value is back to its default.
- **Revisions:** the *New revision* dialog, the notes at review and release, and the places that show a revision are in sections 5.3 and 5.4.
- **Devices tab:** the pin table gets *Level*; the role choice gets *Signal ground*; the details of a connector get *Source*, *Source version* and *Source link*. The Inspector shows the same for a selected pin or connector. A cable pin does not offer Level (owner question Q5).
- **Parts:** the Inspector of a part and the Library window get *Link*, opened in the browser on a click.
- **Command line:** `document DIR [--harness ID] [--set FIELD=VALUE]… [--contact LABEL=VALUE]… [--clear FIELD] [--json]` shows and sets the document data; with `--harness` it sets the fields of that harness's plan. `revise DIR HARNESS --kind major|minor|patch` and `migrate DIR --revision HARNESS:OLD=VERSION` are in section 5. Pin levels, roles and sources come in through `import-pinout`, the device library and the editor; command-line versions of the pin edits stay not built, as today. `export-pinout` writes *Level*, *Source*, *Source version* and *Source link* when used, and reads back.
- **Strings** in `gui/strings.py`; the in-app guide and user manual pages *Export the harness plans* and *Revisions*.

## 11. Tests

- **Format 3** (`tests/test_format3.py`): the step from 2 to 3 on every fixture and example: the checks of section 5.6 (the comparison without revisions, the same findings, the same release consistency, each revision mapped), `project.json` changed in the number only, and the 3.0 export against the 2.x goldens with only the allowed differences; a revision `b`, `A1` or `-` refused without `--revision` and taken with it; two old revisions that give one version refused; the step run twice gives the same files; a format 3 project opened by a reader of format 2 is read-only (simulated by the loader's version check); each new field round-trips and is left out while default; `WebLink` refuses `file:`, `javascript:` and a path; a device file stays version 1 until a pin has a level.
- **Revisions** (`tests/test_revisions.py`): `Version` refuses `01.0.0`, `v1.0.0`, `1.0`, `1.0.0.0` and `10000.0.0`; `version_key` puts `1.10.0` after `1.9.0`; `letter_to_version` keeps the letter order for A to ZZZ (Hypothesis); `revise --kind` for each kind; a step back refused; the kind chosen again on a draft before review, refused after; the note on a major revision; the note on a pinout change with minor or patch, and none with major or without such a change; the release freeze with versions; `diff --from B` on a migrated project; `merge-fix` rewrites a letter after a merge; a new harness and a generated one start at `1.0.0`; the editor's top bar range in version order.
- **Writer** (`tests/test_ods_writer.py`): two builds give the same bytes; `mimetype` first and stored; every entry stored with the fixed date and `create_system` 3 (also with `sys.platform` patched to `win32`); the manifest lists every entry; the XML is well formed; a formula cell has formula, value type and value; text with `<`, `&`, quotes and non-ASCII is escaped.
- **Layout** (`tests/test_harness_plan.py`): each region of section 3 on small projects; the Direction words; the mirrored directions; the colour rule both ways, an unlisted pin, a pin `01`; the yellow rows and `[no SGND*]`; the sums with wires without a length and with pair parts (D-188); the register against the change log of that harness only; a released harness; a loose end; an empty document (`to fill in`), and the Cover's Version with and without a person's value; a box connector used by two harnesses gives the same `CON_…` sheet in both plans; the example colour code taken, with its heading and its `check` note, and a new project without it.
- **Goldens:** `tests/fixtures/outputs/harness_plan/` for the four examples and the branching fixture, one plan per harness, made by `tools.gen_output_goldens` with the plan on. The output-hash baseline without the plan is made again once, with format 3 (section 5.6); after that, adding the plan leaves it identical.
- **Verifier mutation tests** (`tests/test_verify_plan.py`): a changed value, a changed formula, a stored value that the formula does not give, a formula outside the list, `INDIRECT` in a formula, a missing or extra sheet, sheets in another order, a row missing, a wire in two rows, a plan of a harness that is gone, a harness without its plan, a compressed entry, `mimetype` not first, a missing manifest entry, a DOCTYPE in `content.xml`, a wrong stamp: each gives its error. The verifier's copies of the sides rule, the words and the lookup agree with the core's on random harnesses (Hypothesis).
- **Imports:** `import-pinout` with the users' headings (Pinout through `--column pin=Pinout`, Function, Direction, Level, Description) and words (`PWR-RET`, `SGND`, `TEST`); `import-parts` with *Link*.
- **Branching** (after 2.3.0): a Y harness through a splice, a ring of three connectors, a harness of one connector, every wire in exactly one row.
- **End to end through the command line** (`tests/test_e2e_harness_plan.py`): a blank project; two devices with an imported pinout in the users' words; an interface; `generate`; `document --set` and `document --harness W001 --set`; the example colour code; `export --harness-plan`, one plan per harness; `verify --outputs` with 0 errors; the file read by the test's own reader and every formula evaluated; a second export byte-identical; `release`, `revise --kind minor`, `release` again, with the register and `VERSION:` of the plan following; an export without the option removes the plans.
- **A real reader:** a test converts the plan of the end-to-end case to CSV with LibreOffice when `soffice` is on the path and compares the shown values with the stored ones, and skips otherwise. No workflow installs LibreOffice today, so in CI it skips; what CI checks instead is the package rules of section 7.3, the closed formula list and the agreement of every formula with its stored value.
- **Guards:** the offline test (no network module imported by `core`), the output-hash baseline, the security tests, `docs/CLI.md` and the JSON keys in sync, `perf`: the plans of 200 devices and 100 harnesses in under a stated time (set when measured).

## 12. Pull requests

| PR | Content |
|---|---|
| R1 | Revisions, prepared without a format change: `core/vcs/revisions.py` (`version_key`, `bump`, `letter_to_version`, the pinout test of section 5.3) and its tests; `baselines_of`, the editor's top bar and `describe` moved to one ordering function that keeps the letter order. Nothing visible changes in 2.x, so it can be merged before 2.3.0 |
| 1 | Format 3: `SCHEMA_VERSION` 3, `_v2_to_v3` with the revision mapping, the fields of section 4.1, `Version`, `WebLink`, `ProjectMeta` sparse, the optional `harness_plan` config, the device file version rule; the checks of section 5.6 in `upgrade.py` and `migrate --revision`; `revise --kind` in the core and the command line, and the smallest editor change that keeps *New revision…* working (the three choices); generation starts at `1.0.0`; the goldens and the output-hash baseline made again, with the test of the allowed differences; the schemas, `docs/FILE_FORMAT.md`; this page; D-242. No plan yet. **Merged only after 2.3.0 is tagged**, or into the release that first carries format 3 (Q24), because master writes format 3 from then on |
| R2 | Revisions, the rest: the notes on a major revision and on a pinout change, the kind chosen again (`version_changed`, Q22), `diff --from` and `--to` with an old letter, the loader's `revision_not_version` and `merge-fix` for letters after a merge, the Releases panel and the Inspector, strings, the user manual page *Revisions*, `docs/CLI.md` |
| 2 | `core/outputs/ods.py`: the writer and its tests. No caller yet |
| 3 | `core/outputs/harness_plan.py`: the layout of section 3 for straight harnesses (the sides rule of section 9 without splices), one plan per harness, `build_outputs(..., harness_plan=)`, the manifest, the goldens; the colour rule and the example file `resources/examples/templates/pigtail-colour-code-EXAMPLE.csv` with its row in the templates' README (section 6) |
| 4 | `core/outputs/verify_plan.py`: the checks of section 7.5 and the mutation tests |
| 5 | Command line and imports: `export --harness-plan`, `harness_plan_exported`, the release re-export, `document` with `--harness`, `import-pinout` (Level, Description, the Direction words, the source columns), `import-parts` (Link), `export-pinout`; `docs/CLI.md` |
| 6 | Branching: splices in the sides rule, *Further wires*, the branching goldens (needs 2.3.0 on master) |
| 7 | Editor: the Export check box, the two Settings pages with *Use the example colour code*, the Inspector's *Plan document*, the Devices tab and Inspector fields, the Library *Link* column, strings, screenshots |
| 8 | The end-to-end test, `docs/OUTPUTS.md`, the user manual pages, the in-app guide, CHANGELOG; then the preparation of 3.0.0 as a pull request of its own |

Order: R1 at any time; 1 after R1; then R2 and 2 in either order; then 3 and 4 together, or 3 then 4; then 5, 6 and 7 in any order; then 8. R1, 1 and R2 are a whole: without the plan they still make a working tool with versions, so the revision change can go into a release before the plan if the release that first carries format 3 comes first (Q24).

## 13. Risks

- **2.3.0 may need a format change itself.** `PLAN_2.0.md` section 2.4 gives the splice a role `splice` and a field `Connector.bonded`; neither is in format 2, which is frozen. If the design of 2.3.0 needs them, 2.3.0 is a format change. The owner's answer to Q10: one format 3 holds both, with the versions of section 5, in whichever release comes first, and the releases are numbered from there (Q24).
- **A reader shows the stored text** (section 7.4): a stored value that the formula does not give would show a wrong colour or direction. Held by the verifier's evaluator and its mutation tests.
- **Size.** A project of 200 devices and 100 harnesses gives 100 plans, each with one harness sheet and the `CON_…` sheets of its own connectors, stored uncompressed. A box connector used by many harnesses is written into each of their plans, so a change to one device changes all of them, and the plans of an export hold more bytes than the template's single document would. A `perf` test measures the build; a reader's opening time is not measured.
- **The revisions change every stamp once.** The model hash reads the revisions, so the upgrade to format 3 changes the stamp of every output and makes the last export *out of date*. A team exports again after the upgrade. Section 5.6 shows that nothing else changes, by a test on the fixtures and examples, not on the team's own project.
- **Old paper and other tools say *Revision B*.** A printed drawing, a purchase order or another tool may name a letter. The rule `B` → `2.0.0` can be read back by hand, `diff` takes the old letter, and the migration record lists the mapping. A tool outside that reads `export.json` gets a version string where it got a letter.
- **Branches across the upgrade.** A branch still in format 2 brings letters into a format 3 project when it merges. The loader names them and `merge-fix` rewrites them (section 5.6); the user manual says to upgrade on the main branch first.
- **`N.0.0` goes against the template's *never raise MAJOR*** for harnesses revised before 3.0.0 (section 5.5, Q18). The users see `2.0.0` where their rule would want a new name. It is the history, written under letters.
- **A person edits the plan** and exports again: the edits are gone. The file says so in three places; `verify --outputs` reports an edited plan in `outputs/`.
- **The sides rule** can split a harness in a way the users would not draw. It is fixed and documented; a per-connector override would be one more field (not in 3.0.0).
- **Contact data in Git** (section 4.4).
- **Zip bytes across platforms.** `exports.normalise_xlsx` builds each `ZipInfo` without setting `create_system`, which Python takes from the platform; whether the `.xlsx` outputs differ in that byte between Windows and Linux is not checked here. The plan's writer sets it.

## 14. Owner questions

### 14.1 The questions of the first version, with the owner's answers

Each question keeps the recommendation of the first version of this page; the owner's answer follows it. Where the owner chose otherwise, the recommendation is marked *not taken*, and the answer is what this design now follows.

- **Q1. One file per project, or one per harness?** *Not taken:* one per project, `system/harness_plan.ods`, as the template is one document. Alternative: `harnesses/<ID>/<ID>_plan.ods`, which repeats the cover, register and shared sheets.
  - **Owner's answer (2026-11-17):** the alternative, one file per harness, `harnesses/<ID>/<ID>_plan.ods`. Users sometimes want a quick test harness that is custom and unique, so each harness gets its own plan. Each file holds its own Cover, Change register, the harness sheet, the `CON_…` sheets it needs, and Notes (sections 1, 3.7 and 10).
- **Q2. Does the change register replace or mirror the change log?** It mirrors it; nothing is typed into the plan. The document version is a person's field. Register rows that are not harness changes are not in 3.0.0.
  - **Owner's answer (2026-11-17):** as recommended (sections 3.2 and 4.4).
- **Q3. Ship the users' colour table as an example?** *Not taken:* no shipped code; a paste of two columns in Settings, and the JSON form in the user manual.
  - **Owner's answer (2026-11-17):** yes, ship the users' colour code as an example that a project takes on purpose, for example with a button *Use the example colour code*. It is never applied by itself. It is the colour code of the owner's users' template, an example and not a standard, to be checked against the supplier's pigtail code (section 6, appendix A).
- **Q4. A person edits a formula cell (or any cell). What happens on the next export?** It is overwritten. The Cover, the Notes and the About sheet say so; `verify --outputs` reports an edited plan in `outputs/`; work on a copy.
  - **Owner's answer (2026-11-17):** as recommended.
- **Q5. What do Description and Level mean for a cable pin and a device pin?** They belong to the device (box) pin, which the ICD describes. A cable pin shows the values of the box pin it plugs into; the editor offers neither field on a cable pin, and `check` warns about a value there (a hand-edited file) without removing it.
  - **Owner's answer (2026-11-17):** as recommended.
- **Q6. Function and Description:** Function = `Pin.signal`, Description = `Pin.function`, no new field (section 4.2).
  - **Owner's answer (2026-11-17):** as recommended.
- **Q7. SGND:** a role value `signal_ground`, never derived from a pin name in 3.0.0 (section 4.3).
  - **Owner's answer (2026-11-17):** as recommended.
- **Q8. "no SGND" in the labels:** the plan's header shows `[no SGND*]`; `labels.csv` and the build workbook's labels do not change in 3.0.0. Adding it there is a later change of those outputs.
  - **Owner's answer (2026-11-17):** as recommended.
- **Q9. Revisions are letters; the template counts MAJOR.MINOR.PATCH and wants a new harness name for an incompatible change.** *Not taken:* no change of the revisions; the plan shows the revision as it is; the tool does not enforce the users' naming rule.
  - **Owner's answer (2026-11-17):** the alternative: the tool changes to MAJOR.MINOR.PATCH revisions. Section 5 designs it. The naming rule is not enforced in 3.0.0; the tool shows a note instead (section 5.3). The open points are Q18 to Q24.
- **Q10. If 2.3.0 needs a format change** (splice role, bonded pins), make one format 3 that holds both, in whichever release comes first, and number the releases from there.
  - **Owner's answer (2026-11-17):** as recommended. The revision change of Q9 joins the same format 3 (Q24).
- **Q11. Other format 3 candidates** (`Unit.library` of the 2.2 design Q1, `Pin.port` of the 2.1 design Q1): not bundled, unless the owner wants them now; each needs its own proof that the migration changes nothing.
  - **Owner's answer (2026-11-17):** as recommended.
- **Q12. The block diagram picture:** not in 3.0.0; a text cell names the harness drawing. Later: the routing sketch as SVG in the package for a harness of more than two connectors (how readers show an SVG picture is not checked).
  - **Owner's answer (2026-11-17):** as recommended.
- **Q13. Always on, or an option?** An option, `--harness-plan` and a check box remembered per folder (section 10).
  - **Owner's answer (2026-11-17):** as recommended. The option writes one plan per harness (Q27).
- **Q14. Contact data:** in `project.json`, on the Cover only, not in `export.json`; the manual names the Git history (section 4.4).
  - **Owner's answer (2026-11-17):** as recommended.
- **Q15. *Conductor* in *used Cable Types*:** `Part.specification` of the wire part. The template shows no example; the owner or the users say what they mean.
  - **Owner's answer (2026-11-17):** the design takes the wire part's specification text for now.
- **Q16. Words without a template example:** `IN/OUT` for `bidir`, `SHIELD` for a shield pin, an empty cell for a spare pin. The owner may name others; they are fixed words of the tool, not settings.
  - **Owner's answer (2026-11-17):** as recommended.
- **Q17. The template's conditional formats** (GND against PWR, the search strings): written as in the template.
  - **Owner's answer (2026-11-17):** yes, as in the template.

### 14.2 Follow-up questions raised by the answers

Each with the recommendation of this design.

- **Q18. How are the old revisions mapped to versions?** Recommended: an upper-case letter becomes `N.0.0` by its place in the letter order (`A` → `1.0.0`, `B` → `2.0.0`, `AA` → `27.0.0`), for the harness, its baselines and its change-log entries. A value that is already a version is kept. Any other value is not guessed: `migrate` lists it and refuses until a person gives a version (`migrate --revision W001:A1=1.1.0`). After the upgrade, `diff` still takes an old letter and says which version it is. Reason: the order stays, anyone can read a letter back, and no compatibility is claimed that nobody checked. Alternative: `A` → `1.0.0`, `B` → `1.1.0`, which keeps MAJOR at 1, as the template's *never raise MAJOR* wants, but says every old revision was compatible (section 5.5).
- **Q19. Does a draft carry a version, or a pre-release suffix?** Recommended: the version it will be released as, with no suffix (`1.1.0`, status draft). The status already says draft, in review or released, and it is shown next to the version everywhere (`VERSION: v1.1.0 (draft)`). A suffix such as `1.1.0-draft` would change the version at the release, so the files reviewed before the release would carry another version than the released ones, and the order of versions would need a second rule.
- **Q20. Does the tool suggest the kind of bump?** Recommended: no suggestion at *revise*, because the draft is still the released design and there is no diff yet. At review and release, a note when the diff changes the pinout at a device and the kind is minor or patch; nothing between minor and patch, which is about intent. The note neither changes the version nor blocks (section 5.3).
- **Q21. Does a major bump warn about the template's naming rule?** Recommended: yes, a note at *revise* when a person chooses major, naming the rule (an incompatible harness gets a new ID); the person can go on. No setting and no block in 3.0.0. Later, if the owner wants: a setting `major_revision` (allowed, note, refused) in `config/naming.json`, and a command that copies a released harness to a new ID.
- **Q22. Can a person change the kind after *revise*?** Recommended: yes, while the harness is a draft and before its review: `revise --kind` again works the version out from the released one and adds a change-log entry *version changed*. A person often knows the kind only after the edit. Not after the review starts.
- **Q23. *Revision* or *Version* in the words of the tool?** Recommended: keep *Revision* on screen, on the drawings, in the build workbook and in the CSV headings in 3.0.0, so a written file changes in its value only (section 5.6). The plan writes the template's *VERSION*. Changing the word everywhere is a later change of those outputs.
- **Q24. Is the revision change part of format 3 with the harness plan, or of the 2.3.0 format change of Q10?** Recommended: the revision change is part of format 3 as a whole, in whichever release first carries format 3 (the answer to Q10), and that release is numbered 3.0.0. One format cannot hold letters and versions both. If 2.3.0 needs a format change, that release becomes 3.0.0 and carries the versions and the plan's fields; the plan's writer can follow in a 3.x minor release, because it changes no format (pull requests R1, 1 and R2 first, section 12).
- **Q25. Which Cover fields belong to one plan, now that each harness has its own?** Recommended: the document number, version, release and title per harness (`meta.document.plans`); the company, the contact lines and the system code once per project. The Cover's Version is the person's field; while it is empty it shows the harness revision, which is now a version in the users' form. The tool does not count the person's field up (the answer to Q2).
- **Q26. How is a code taken from the example kept apart from a checked one?** Recommended: the code carries `"example": true` in `config/harness_plan.json` until a person takes the mark off. While it is on, the Notes sheet says it is the example from the users' template, to be checked against the supplier's pigtail code, and `check` gives a note. Not the placeholder flag, which would block every release for a value only the plan shows. The template names no connector parts, so a person names the parts it applies to when taking it.
- **Q27. Plans for all harnesses, or for chosen ones?** Recommended: one option for all harnesses, as `--drawings` is. A choice per harness would make the set of written files depend on a list kept somewhere, and the release re-export would need it too.

## 15. What this design does not check

- No spreadsheet program opened the users' template; it was read as XML.
- The behaviour of section 7.4 was seen in one LibreOffice version, headless, with default settings, on a hand-made package. Other readers (Excel, Gnumeric, OnlyOffice, online spreadsheets) were not tried.
- No user has seen a plan made by the tool.
- The design of 2.3.0 does not exist yet; section 9 assumes the splice of `PLAN_2.0.md` section 2.4.
- The example colour code was not compared with any supplier's pigtail code or any standard. It ships as the users' example only (section 6).
- The revision design (section 5) was not tried on a project: the claim that an export changes only in the stamp and the revision text is what the test of section 5.6 is to show, and nobody has run it. Whether a longer revision text moves a column width or cuts a title block text was not looked at.
- No user has seen versions in the tool, and nobody asked the users whether `N.0.0` for their old letters suits them (Q18).
- Other tools that read `export.json` or the change log and expect a letter were not looked for.

## Appendix A. The example colour code

The table of the Notes sheet of the users' template, *uD Pigtail Colour Code*, as its cells show it (pins 11 to 37 are formulas in the template; the values are written here). It is the colour code of the owner's users' template: an example, not a standard and not a supplier's table (section 6). Check it against the pigtail code of the connector's supplier. It goes into the program as `resources/examples/templates/pigtail-colour-code-EXAMPLE.csv` with pull request 3 (section 12).

| Pin | Colour |
|---|---|
| 1 | Black |
| 2 | Brown |
| 3 | Red |
| 4 | Orange |
| 5 | Yellow |
| 6 | Green |
| 7 | Blue |
| 8 | Violet |
| 9 | Grey |
| 10 | White |
| 11 | Wh / Black |
| 12 | Wh / Brown |
| 13 | Wh / Red |
| 14 | Wh / Orange |
| 15 | Wh / Yellow |
| 16 | Wh / Green |
| 17 | Wh / Blue |
| 18 | Wh / Violet |
| 19 | Wh / Grey |
| 20 | Wh / Bl / Brown |
| 21 | Wh / Bl / Red |
| 22 | Wh / Bl / Orange |
| 23 | Wh / Bl / Yellow |
| 24 | Wh / Bl / Green |
| 25 | Wh / Bl / Blue |
| 26 | Wh / Bl / Violet |
| 27 | Wh / Bl / Grey |
| 28 | Wh / Brw / Red |
| 29 | Wh / Brw / Orange |
| 30 | Wh / Brw / Yellow |
| 31 | Wh / Brw / Green |
| 32 | Wh / Brw / Blue |
| 33 | Wh / Brw / Violet |
| 34 | Wh / Brw / Grey |
| 35 | Wh / Red / Orange |
| 36 | Wh / Red / Yellow |
| 37 | Wh / Red / Green |
