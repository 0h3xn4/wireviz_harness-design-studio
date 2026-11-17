# Design of 3.0.0: the harness plan

Written on 2026-11-17 from a reading of the code at `2393ff7` (master, with pull request 2 of 2.2.0) and of the users' template `harness_plan_template.ods`, supplied by the owner on 2026-11-17. The decision that records it is D-242 (to be recorded). It is a design only: nothing of it is built. Paths are relative to `src/harness_design_studio/` unless they start with `docs/` or `tests/`.

## 0. The owner's frame

The owner decided three things on 2026-11-17. This design works inside them.

1. The output is an **`.ods` file that includes formulas**, in the users' layout.
2. The data the model lacks goes into **format 3**, released as **3.0.0**. The model refuses unknown fields (`extra="forbid"` in `core/model/base.py`), so a new field is a format change. Format 2 is frozen for 2.x (D-230).
3. **Order:** after 2.2.0 (the device library, [`DESIGN_2.2_DEVICE_LIBRARY.md`](DESIGN_2.2_DEVICE_LIBRARY.md)) and 2.3.0 (branching harnesses and splices, [`PLAN_2.0.md` section 3.6](PLAN_2.0.md#36-order-after-the-feedback-of-2026-11-16)).

## 1. Purpose and scope

**What the users get.** One more written file: the harness plan, a spreadsheet in their own layout. It has a cover, a change register, one sheet per harness with the device side and the harness side of every connector, the sums of cable lengths, the reference pinouts of the far connectors, a notes sheet with their colour code, and one sheet per device connector (`CON_…`). Formulas keep the sheet working when a person changes a cell in it: a mirrored direction, a colour looked up by pin number, a sum of lengths.

**What stays as it is.** The build workbook (`<ID>_build.xlsx`, [`OUTPUTS.md`](../OUTPUTS.md#build-workbook)) stays the file to build a harness from. Every other output stays. The plan is one more file, written only when asked for (section 9).

**One file per project, or one per harness.** The template is one document per project: one cover, one document number, one change register, and harness sheets that share the `CON_…` sheets. A file per harness would repeat the cover, the register and the shared sheets in every file. **Recommendation:** one file, `outputs/system/harness_plan.ods`, with one sheet per harness (owner question Q1). The cost: a change to one harness changes the whole file, and a project with a hundred harnesses has a hundred harness sheets (section 12).

**Not in scope.** No import of a filled-in plan. The tool never reads the plan back, as it never reads the build workbook back. No `.xlsx` copy of the plan. No picture in the first version (owner question Q12).

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

*Exists* means a field of format 2. *Derived* means worked out from fields that exist. *New* means a field of format 3 (section 4). *F* marks a cell the plan writes as a formula with its value (section 6); every other cell is a plain value.

### 3.1 Cover

| Template | Plan | Source | Kind |
|---|---|---|---|
| Doc.-No. `F2` | same cell | `ProjectMeta.document.number` | New |
| Version `F3` | same | `document.version` | New |
| Release `F4` | same | `document.release` | New |
| `PROJECT XXX` `A17` | same | `ProjectMeta.name` | Exists |
| `XXX Harness Plan` `A19` | same | `document.title`, else `<project name> Harness Plan` | New, with a derived default |
| Company `A21` | same | `document.company` | New |
| Contact Information `C36:D40` | same, one row per line | `document.contact`: a list of lines (label, value) in the order entered; a value that starts with `mailto:` or holds one `@` becomes a `mailto:` link | New |
| (none) | a line under the title: the stamp and *This file is written by Harness Design Studio. An export overwrites it; work on a copy.* | the stamp (`outputs/stamp.py`) | Derived |

An empty document field reads `to fill in` on an amber cell, as the build workbook does.

### 3.2 Change_Register

One source of truth: the change log (`project.changelog`, `ChangeEntry`; `system/changelog.csv`). The register mirrors it; nothing is typed into the plan.

| Column | Source | Kind |
|---|---|---|
| Version | `ChangeEntry.revision` (letters: `A`, `B`) | Exists |
| Sub-Version | `ChangeEntry.id` (`C0003`): the running number of the change log | Exists |
| Date | `ChangeEntry.when` (`YYYY-MM-DD`) | Exists |
| Name | `ChangeEntry.by` | Exists |
| Sheets | the sheet name of the harness (`ChangeEntry.harness_id`) | Derived |
| Description | the kind in words (*in review*, *released*, *new revision*), `: `, `ChangeEntry.comment` | Derived |

Rows in entry ID order. The users' versioning rule is not checked by the tool, and the tool's revisions are letters (owner question Q9). The register's text frame is not written; the Notes sheet says where the change log comes from.

### 3.3 The harness sheet: header and part tables

| Template | Source | Kind |
|---|---|---|
| System `H6` | `document.system`, else the project name | New, with a derived default |
| Harness number `N6` | `Harness.id` | Exists |
| `VERSION:` `Q6` | `VERSION: <revision> (<status>)`, e.g. `VERSION: B (released)` | Exists |
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
| Cable / Type `P` (far) | `=L` on a straight row; the far wires' types on a branch row (section 8) | F or value |
| Color `Q` (far) | as `K`, for the far pin and its connector's part | F or value |
| Direction `R` (far) | the mirrored word of the far pin (`=` the far `CON_…` cell, mirrored as `J`) | F |
| Function `S` (far) | the far pin's signal (`=` the far `CON_…` cell) | F |
| Pinout `T`, `U` … (far) | one column per far connector: the far pins this row reaches (section 8) | Derived |
| Far device side `W:AA`, `AD:AH` … | Pinout as a value; Function, Direction, Level, Description as direct references to the far `CON_…` row of that pin (no `OFFSET`) | F |

A device pin with no wire in this harness: the harness-side cells are empty and the row is yellow (`#ffff99`), as in row 53 of the template, with the template's sentence once per sheet. The tool has no other "deliberately not connected" mark, and this design adds none: the reason belongs in the pin's Description (`Pin.function`).

The conditional format of the template for `GND` against `PWR` is written over the `J` and `R` columns of all harness rows, with the template's formula and style.

### 3.5 Sums and reference pinouts

| Template | Source | Kind |
|---|---|---|
| *Sum of length of cable type [mm]* | one row per cable type: `SUMIF(<L range>;No.;<N range>)/<No. of wires cell>`, with every row range of the sheet that holds wires (the near rows and, on a branching harness, the further wires of section 8) | F |
| (none) | a cell beside each sum: `n wires without a length` when there are any | Derived |
| Reference pinout, per far connector | the far connector's ID, its links, `Data from CON_…`, then one row per pin: Pinout, and Function, Direction, Level, Description as references to its `CON_…` sheet | F |
| *Used in Row* | `IF(ISNA(MATCH(pin;<far pin column>;0));"";MATCH(pin;<far pin column>;0)+<row before the table>)` | F |
| Picture *BLOCK DIAGRAM incl. Lengths* | not written in 3.0.0; a text cell names the harness drawing (`harnesses/<ID>/drawing_A3.pdf`) when the export has the drawings | Q12 |

### 3.6 `CON_…` sheets

One sheet per box connector that a harness of the plan plugs into, named `CON_<box connector ID>` (the IDs are unique in the project and use only letters, digits, `_`, `-` and `.`, so they are valid sheet names). A loose end has no sheet.

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

**Notes:** each colour code of the project (section 5) as a table Pin, Color; the project's note lines (config `harness_plan.notes`, plain text, for example the users' labelling and level notes); and a fixed legend: what each Direction word means, that yellow marks a pin with no wire, which cells hold formulas, and that an export overwrites the file. **About:** the stamp, the full model hash and the notice, as on the About sheet of the workbooks, so the verifier finds the stamp where it finds it in an `.xlsx`.

Sheet order: Cover, Change_Register, the harness sheets in harness ID order, Notes, the `CON_…` sheets in connector ID order, About. A harness sheet is named after the harness ID; the template's `<system>-<harness>-<devices>` would pass 31 characters (the limit of some spreadsheet programs) with long IDs, and the devices are in the title.

## 4. New in format 3

### 4.1 The fields

| Field | Type, default | Set by | Shown in the editor | Import | Migration 2 → 3 |
|---|---|---|---|---|---|
| `Pin.level` | `Name \| None`, `None`; sparse | a person; an import | Devices tab, pin table column *Level* (box pins); the Inspector of a pin | `import-pinout` column *Level*; device library files | nothing written |
| `PinRole` value `signal_ground` | a new value of the list | a person; an import | the role choice of a pin (*Signal ground*) | the Direction word `SGND` | nothing: no pin gets it |
| `Part.link` | `WebLink \| None`, `None`; sparse | a person; the parts import | the Inspector of a part; a *Link* column in the Library window | `import-parts` column *Link* (also *URL*) | nothing |
| `Connector.source_doc`, `source_version` | `Name \| None`, `None`; sparse | a person; an import | the Devices tab, the details of a connector | `import-pinout` columns *Source* (also *ICD*) and *Source version* (also *ICD version*) | nothing |
| `Connector.source_link` | `WebLink \| None`, `None`; sparse | as above | as above | column *Source link* | nothing |
| `ProjectMeta.document` | `DocumentInfo \| None`, `None`; `ProjectMeta` becomes sparse for this one field | a person only | *Settings > Project > Document* | none | nothing |
| `config/harness_plan.json` | an optional config file, not in `default_configs`: `colour_rule` (`wire` or `pin_code`, default `wire`), `colour_codes` (default none), `notes` (default none) | a person only | *Settings > Project > Harness plan* | none | not created |

`DocumentInfo` (sparse; each text left out while empty): `number`, `version`, `release`, `system`, `title`, `company` (each `Label`, up to 200 characters), and `contact`, a list of at most eight lines `{label: Name, value: Label}`. A list keeps the template's four lines (name, phone, fax, e-mail) without a field for each, and a team without a fax leaves it out.

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

**Document data** lives in `project.json` as `meta.document`. It is part of the design, so it is in the model hash: a new phone number makes the plan out of date, as it should, because the plan shows it. It is set only in the editor (and by a command, section 9). It is written into the Cover of the plan and nowhere else: not into `export.json`, not into any other output, not into a log. **Privacy:** a contact name, phone and e-mail in `project.json` go into the project's Git history. The user manual says so and suggests a role address where a team prefers one (owner question Q14).

**The change register mirrors the change log** (section 3.2). A register kept in the plan or in a new list would be a second source for the same events, and the two would drift. The document's own version (`document.version`) is a person's field; the tool does not count it up. Not in 3.0.0: register rows that are not changes of a harness (owner question Q2).

### 4.5 Migration and compatibility

- **The step from 2 to 3** (`core/io/migrate.py`, a new `_v2_to_v3` with `V2_TO_V3_PARTS`) writes the number only. Every new field is absent, so it has its default; no pin gets `signal_ground`; no config file is created. `ProjectMeta` becomes sparse only for `document`, so `project.json` keeps its bytes apart from the number.
- **The proof** is the migration safety net (`core/io/upgrade.py`): the same model hash (the hash reads the format number as 1, `layout.schema_one`), the same content hash of released harnesses, the same findings and the same export digests before and after, for every fixture project and example, as for the step from 1 to 2. An export of a migrated project without `--harness-plan` writes the same files as 2.x apart from the version stamp (`tools.output_hashes --check docs/ui/OUTPUT_HASHES_BASELINE.json`).
- **Older tools** open a format 3 project read-only (the rule of D-226). A 2.x tool would otherwise drop `level` and the source fields on its next save, or quarantine pins with the new role.
- **The device library file** (`harness-device-library`, version 1, D-165) is read with the strict models, so a 2.2 tool refuses a pin with `level`. A 3.0 tool writes a device file as **version 2 only when one of its devices uses a new field**, else version 1 as before. A 2.2 tool then refuses that one file with *a newer version* and still offers the others (the folder rules of D-240).
- **Other outputs:** a *Level* column appears in `box_pinouts.csv`, `export-pinout` and the Devices table only while a pin has a level, by the sparse rule. `export.json` carries the new pin, part and connector fields when they are set; it never carries `document`. Every other output is unchanged.
- **The 2.2 library update** compares the connectors in portable form; the new pin and connector fields are library-owned and show in its diff.

## 5. The colour rule by pin number

Today a wire's colour is the person's, or the one `generation.wire_colour_by_signal` gives its signal (`core/wirecolours.py`, `generate/engine.py`). The template colours each **end** by its pin number, because a micro-D connector with pigtails comes with its wires coloured by pin position. One wire of the model can then have a colour at each end that differs from the other end. So the rule belongs to the plan's end columns (`K` and `Q`), not to `Wire.colour`.

**Configuration** (`config/harness_plan.json`, optional, section 4.1):

```json
{
  "name": "harness_plan",
  "placeholder": false,
  "values": {
    "colour_rule": "pin_code",
    "colour_codes": {
      "pigtail": {"parts": ["P-MDM-15S-PIG"], "colours": {"1": "Black", "2": "Brown"}}
    },
    "notes": ["The label of a line that is not connected says so (no SGND)."]
  }
}
```

- `colour_rule` `wire` (default): `K` and `Q` show `Wire.colour`, as plain values.
- `colour_rule` `pin_code`: an end whose connector part is listed in a code gets the code's colour for its pin, as a formula over the code's table on the Notes sheet (`VLOOKUP(pin;$Notes.$B$7:.$C$43;2;0)`, exact match). Any other end shows `Wire.colour`.
- Keys are pin IDs as text and match exactly: pin `01` matches only the key `01`. A pin the code does not list reads `to fill in`, and `check` warns once per connector (`plan_colour_missing`).
- A part in two codes is refused by `validate` (`config_invalid`). Colours are names as typed (`Wh / Bl / Brown`); the tool does not check them against IEC 60757 (`wirecolours.resolve` keeps an unknown colour as typed and draws it grey).
- Generation does not read the codes; `Wire.colour`, the build workbook and every other output are unchanged.

**Ship the users' table, or not.** The rule *never invent standard values* is about values the tool would make up. The template's table is the users' own code. Its title says *uD Pigtail Colour Code*; whether it follows a supplier's table or a standard is not stated, and this design does not claim it. Shipping it as a default would put a value the tool cannot vouch for into every project. **Recommendation** (owner question Q3): ship no code. *Settings > Project > Harness plan* takes a paste of two columns (pin, colour) from a spreadsheet, so a team pastes its own table in one step, and the user manual shows the JSON form. The users' table is used in the tests only, as test data.

## 6. Formulas and determinism

### 6.1 Which cells get formulas

**A formula where the cell is a pure function of other cells of the same file and a person who edits the source cell expects the cell to follow:** the device-side copies of the `CON_…` sheets, the harness-side copies (`H`, `I`, `O`), the mirrored directions (`J`, `R`), the colours by pin code (`K`, `Q`), the titles and connector descriptions, the sums per cable type and the cable type lengths, and *Used in Row*. **A plain value for everything the model holds:** the pins of the `CON_…` sheets, wire lengths, cable type numbers, shield groups, parts, document data, register rows, and the far pins of each row. The model is the source; a formula over another cell can only repeat it.

Every formula cell carries its value as well (section 6.3). An export overwrites the whole file, formulas and typed changes alike. The Cover, the Notes and the About sheet say so (owner question Q4).

### 6.2 The formula dialect

- Every formula is OpenFormula with the `of:` prefix (ODF 1.3, part 4), with references in its form (`[.B34]`, `[$Notes.$B$7:.$C$43]`, `[$'CON_DEV2-J4711'.A19]`).
- **The functions used:** `IF`, `ISNA`, `VLOOKUP` (four arguments, exact match), `MATCH` (exact match), `SUMIF`, and the operators `&`, `=`, `/`, `+`. A closed list: a formula outside it is a defect the verifier reports (section 6.5).
- **No `COM.MICROSOFT.CONCAT`, `COM.MICROSOFT.IFS`.** They are spreadsheet functions of another program stored under its prefix; they are not part of OpenFormula. LibreOffice reads them; other readers of ODF may not. `&` and nested `IF` do the same here.
- **No `INDIRECT`, `ADDRESS`, `OFFSET`.** They build references from text or numbers at recalculation time. They are volatile (recalculated on every change), they break without a word when a sheet is renamed or a row is inserted, and nobody can tell from the formula text which cell it reads, so the verifier could not check it. The template's address text also uses `!` as the sheet separator, which is the A1 syntax of another program; whether a reader accepts it depends on the reader. The tool knows every address when it writes the file, so a direct reference does the job.
- **No `HYPERLINK`.** A link is a `text:a` element in the cell, as the template's part link already is.

### 6.3 The bytes of the package

- `mimetype` first, stored (not compressed), with no extra field: `application/vnd.oasis.opendocument.spreadsheet`.
- Then `META-INF/manifest.xml`, `meta.xml`, `styles.xml`, `content.xml`, in that order. The manifest lists every file: LibreOffice refused a test package whose `meta.xml` was not listed (section 6.4).
- **Every entry is stored, not compressed.** The `.xlsx` files are deflated (`exports.normalise_xlsx`); deflate output depends on the zlib build (zlib-ng, as some Linux systems ship, writes other bytes than zlib for the same input). Stored entries remove the question. The cost is size: a plan of a large project is several megabytes instead of a few hundred kilobytes (section 12).
- Each entry: date 1980-01-01 00:00:00, `create_system` 3, `external_attr` `0o644 << 16`, set explicitly. Python's `ZipInfo` sets `create_system` from the platform (0 on Windows, 3 elsewhere).
- `meta.xml` holds the title and `meta:generator` (`Harness Design Studio <version>`) only: no dates, no creator, no editing cycles, no statistics. No `settings.xml`, no thumbnail, no `Configurations2/`.
- The XML is written by our code: UTF-8, fixed attribute order, no pretty printing, escaping as in `outputs/canvas.py` (`canvas.escape`; `xml.sax.saxutils` is not imported, because it imports network modules at import time). Automatic style names are numbered in the order of a fixed walk of the sheets. Rows are in pin order, sheets in the order of section 3.7, numbers without an exponent.
- A **formula cell** has `table:formula`, `office:value-type`, and its value: `office:value` for a number, `office:string-value` for text, and the shown text in `text:p`. Text never needs the CSV guard against formulas (`'+5V`): an `.ods` text cell is text, and only `table:formula` is a formula.
- The stamp and the notice are on the About sheet, on the Cover and in the footer of every printed sheet. `manifest.json` lists the file with its SHA-256, as every output.

### 6.4 What a reader does with the stored values

A small test package was written by hand for this design and converted to CSV with LibreOffice 24.2 in headless mode, with its default settings. Number cells showed the recalculated value even when the stored one was wrong. Text cells showed the **stored** text even when the formula gave another. The result did not change with the `meta:generator` of the file. So a reader may show either the stored value or the computed one: **the stored value must equal what the formula gives**, and the verifier checks it (section 6.5). Other readers and other settings were not tried.

### 6.5 How the verifier checks the plan

A new module `core/outputs/verify_plan.py`, called from `verify_outputs` when `manifest.json` lists the plan. It does not import the writer or the layout module.

1. **The package:** the entry order, `mimetype` first and stored, every entry stored, the fixed dates, the manifest listing exactly the entries.
2. **The XML** is parsed with `xml.etree.ElementTree` after a DOCTYPE or ENTITY declaration is refused, as `core/kicad.py` does.
3. **The cells:** the verifier derives on its own, from the project, the sheet list and for every cell the expected text, value type and value, and for formula cells the expected formula text. Its own copies of the sides rule (section 8), the Direction words and the colour lookup are compared with the core's by a test, as the ports parser of 2.1.0 was (`tests/test_ports_checks.py`).
4. **Formula and value agree:** a small evaluator for the closed list of section 6.2 computes every formula over the stored cells and compares the result with the stored value. A formula outside the list is an error.
5. Errors are `out_plan` (a cell, with its sheet and address), `out_plan_formula` (a formula that differs from the expected text, is outside the list, or does not give its stored value) and `out_plan_package`. The stamp check reads the About sheet. A plan that was edited in `outputs/` fails `out_modified`, as an edited build workbook does.

Not checked by the verifier: the styles, the column widths, the conditional formats beyond their formula text, the print set-up, and how a spreadsheet program shows the file.

## 7. Writing `.ods`: our own writer or a library

| | Our own writer (`core/outputs/ods.py`) | odfpy |
|---|---|---|
| What it is | about 500 lines: the package, the manifest, a style table, cells (text, number, formula with value, spans, `text:a`), column widths, page layout, print ranges, conditional formats | odfpy 1.4.1 (2020, the latest), Apache-2.0 or GPL-2.0-or-later (its `setup.py`; its classifiers add LGPL); needs defusedxml |
| Determinism | by construction (section 6.3) | zip dates from `time.localtime()`, picture names from `uuid4()`, its own generator in `meta.xml`: the package would be rewritten afterwards, as `normalise_xlsx` does for openpyxl |
| The offline rule | imports nothing new | `odf.opendocument` imports `odf.odfmanifest`, which imports `xml.sax.saxutils` at import time: the `core` rule forbids that (`docs/developer/agent/outputs.md`) |
| Dependency rules | none | a decision row with name, version and licence (`CLAUDE.md`, D-125), the SBOM, the licence texts in `LICENSES/`, the notices, the package and the offline audit |
| Upkeep | ours | a library without a release since 2020 |

**Recommendation:** our own writer. The subset of ODF the plan needs is small and fixed, and every byte is ours to test.

## 8. Branching

The plan has a **near end** (blocks of rows, one per connector) and a **far end** (one column group per connector). A harness's cable connectors are split into the two ends by a fixed rule:

1. Build a graph: a node per cable connector of the harness, except splices, whose pins are one net (the splice of `PLAN_2.0.md` section 2.4: role `splice`, bonded pins; the design of 2.3.0 may change this, and pull request 6 follows what 2.3.0 builds). Two connectors are joined when a net of the harness, through wires and splices, reaches both.
2. Colour the graph in two by a walk in breadth from the first connector in natural ID order, neighbours in natural ID order. A connector without a wire joins the first end.
3. The end with more connectors is the near end (rows grow better than columns); on a tie, the end of the first connector.

**Rows.** One row per pin of a near box connector. A pin has at most one wire (`A-PIN-ONE-WIRE`); that wire gives Cable / Type, Shielding, Length and the near colour. The far pins are every pin of a far connector on the same net, through splices. A row that reaches two far connectors fills a pin in each column (`T`, `U` in the template); two pins of one far connector are joined by ` + `. On such a row the far cells `P` to `S` list the values of each far wire in column order, joined by ` + `.

**Further wires.** A block under the near rows lists every wire that does not end on a near pin: wires beyond a splice, and wires between two connectors of one end (when the graph cannot be split in two, as with three connectors wired in a ring). Columns: wire, from, to, Cable / Type, Shielding, Length, colour. Every wire of the harness appears in exactly one row of the sheet; the verifier checks that, and the sums per cable type include both blocks.

**A straight harness** has one near block, one far column group and no further wires: `Harness SYS-W001: OBC1 <–> STR1`. **A branching harness** of 2.3.0, for the template's case, gives `Harness SYS-W003: DEV2 + DEV3 <–> DEV1 + DEV4`, two near blocks, two far column groups, and the wires beyond the splice under *Further wires*. A loose end is a far column headed `open end, to fill in` with no `CON_…` sheet. A harness with an inline or test connector shows it as a connector of its end; it has no device side unless it plugs into a box connector.

## 9. Editor and command line

- **Export:** `harness-design-studio export DIR --harness-plan` writes `system/harness_plan.ods`; without the option it is not written, and an export without it into a folder whose last export had it removes it and says so (as `--drawings` does, D-169). `harness_plan_exported(folder)` reads the manifest; the re-export at a release (`cli/changes.py`) keeps the choice. `--json` gets `harness_plan`. `verify DIR --outputs` checks the plan when the manifest lists it. The library call `build_outputs(project, harness_plan=False)` keeps the default off.
- **Why not always on** (owner question Q13): an always-written plan adds a file to every export, so the exports of 3.0.0 would no longer match those of 2.x apart from the stamp, and every project would pay for a file most do not use.
- **The Export window:** a second check box under *Include the PDF drawings*: *Include the harness plan (.ods)*, ticked at the start when the folder's last export had it. The result panel lists the file; there is no preview of `.ods`, and *Open* uses the system's program.
- **Settings > Project > Document:** document number, version, release, system code, title (with its default shown), company, and the contact lines (add, remove, move). Each change is one undo step and goes into the journal.
- **Settings > Project > Harness plan:** the colour rule, the codes (name, parts, the table of pins and colours with a paste of two columns), the note lines. It writes `config/harness_plan.json`; the file is created by the first value and removed when every value is back to its default.
- **Devices tab:** the pin table gets *Level*; the role choice gets *Signal ground*; the details of a connector get *Source*, *Source version* and *Source link*. The Inspector shows the same for a selected pin or connector. A cable pin does not offer Level (owner question Q5).
- **Parts:** the Inspector of a part and the Library window get *Link*, opened in the browser on a click.
- **Command line:** `document DIR [--set FIELD=VALUE]… [--contact LABEL=VALUE]… [--clear FIELD] [--json]` shows and sets the document data. Pin levels, roles and sources come in through `import-pinout`, the device library and the editor; command-line versions of the pin edits stay not built, as today. `export-pinout` writes *Level*, *Source*, *Source version* and *Source link* when used, and reads back.
- **Strings** in `gui/strings.py`; the in-app guide and a user manual page *Export the harness plan*.

## 10. Tests

- **Format 3** (`tests/test_format3.py`): the step from 2 to 3 on every fixture and example: the same model hash, content hash, findings and export digests, `project.json` changed in the number only; a format 3 project opened by a reader of format 2 is read-only (simulated by the loader's version check); each new field round-trips and is left out while default; `WebLink` refuses `file:`, `javascript:` and a path; a device file stays version 1 until a pin has a level.
- **Writer** (`tests/test_ods_writer.py`): two builds give the same bytes; `mimetype` first and stored; every entry stored with the fixed date and `create_system` 3 (also with `sys.platform` patched to `win32`); the manifest lists every entry; the XML is well formed; a formula cell has formula, value type and value; text with `<`, `&`, quotes and non-ASCII is escaped.
- **Layout** (`tests/test_harness_plan.py`): each region of section 3 on small projects; the Direction words; the mirrored directions; the colour rule both ways, an unlisted pin, a pin `01`; the yellow rows and `[no SGND*]`; the sums with wires without a length and with pair parts (D-188); the register against the change log; a released harness; a loose end; an empty document (`to fill in`).
- **Goldens:** `tests/fixtures/outputs/harness_plan/` for the four examples and the branching fixture, made by `tools.gen_output_goldens` with the plan on; the output-hash baseline without the plan stays identical.
- **Verifier mutation tests** (`tests/test_verify_plan.py`): a changed value, a changed formula, a stored value that the formula does not give, a formula outside the list, `INDIRECT` in a formula, a missing or extra sheet, sheets in another order, a row missing, a wire in two rows, a compressed entry, `mimetype` not first, a missing manifest entry, a DOCTYPE in `content.xml`, a wrong stamp: each gives its error. The verifier's copies of the sides rule, the words and the lookup agree with the core's on random harnesses (Hypothesis).
- **Imports:** `import-pinout` with the users' headings (Pinout through `--column pin=Pinout`, Function, Direction, Level, Description) and words (`PWR-RET`, `SGND`, `TEST`); `import-parts` with *Link*.
- **Branching** (after 2.3.0): a Y harness through a splice, a ring of three connectors, a harness of one connector, every wire in exactly one row.
- **End to end through the command line** (`tests/test_e2e_harness_plan.py`): a blank project; two devices with an imported pinout in the users' words; an interface; `generate`; `document --set`; the colour code; `export --harness-plan`; `verify --outputs` with 0 errors; the file read by the test's own reader and every formula evaluated; a second export byte-identical; an export without the option removes the plan.
- **A real reader:** a test converts the plan of the end-to-end case to CSV with LibreOffice when `soffice` is on the path and compares the shown values with the stored ones, and skips otherwise. No workflow installs LibreOffice today, so in CI it skips; what CI checks instead is the package rules of section 6.3, the closed formula list and the agreement of every formula with its stored value.
- **Guards:** the offline test (no network module imported by `core`), the output-hash baseline, the security tests, `docs/CLI.md` and the JSON keys in sync, `perf`: the plan of 200 devices in under a stated time (set when measured).

## 11. Pull requests

| PR | Content |
|---|---|
| 1 | Format 3: `SCHEMA_VERSION` 3, `_v2_to_v3`, the fields of section 4.1, `WebLink`, `ProjectMeta` sparse, the optional `harness_plan` config, the device file version rule, the schemas, `docs/FILE_FORMAT.md`; this page; D-242. No output yet. **Merged only after 2.3.0 is tagged**, because master writes format 3 from then on |
| 2 | `core/outputs/ods.py`: the writer and its tests. No caller yet |
| 3 | `core/outputs/harness_plan.py`: the layout of section 3 for straight harnesses (the sides rule of section 8 without splices), `build_outputs(..., harness_plan=)`, the manifest, the goldens |
| 4 | `core/outputs/verify_plan.py`: the checks of section 6.5 and the mutation tests |
| 5 | Command line and imports: `export --harness-plan`, `harness_plan_exported`, the release re-export, `document`, `import-pinout` (Level, Description, the Direction words, the source columns), `import-parts` (Link), `export-pinout`; `docs/CLI.md` |
| 6 | Branching: splices in the sides rule, *Further wires*, the branching goldens (needs 2.3.0 on master) |
| 7 | Editor: the Export check box, the two Settings pages, the Devices tab and Inspector fields, the Library *Link* column, strings, screenshots |
| 8 | The end-to-end test, `docs/OUTPUTS.md`, the user manual page, the in-app guide, CHANGELOG; then the preparation of 3.0.0 as a pull request of its own |

Order: 1, then 2, then 3 and 4 together or 3 then 4, then 5, 6 and 7 in any order, then 8.

## 12. Risks

- **2.3.0 may need a format change itself.** `PLAN_2.0.md` section 2.4 gives the splice a role `splice` and a field `Connector.bonded`; neither is in format 2, which is frozen. If the design of 2.3.0 needs them, 2.3.0 is a format change and the release numbers move (owner question Q10).
- **A reader shows the stored text** (section 6.4): a stored value that the formula does not give would show a wrong colour or direction. Held by the verifier's evaluator and its mutation tests.
- **Size.** A project of 200 devices and 100 harnesses gives about 100 harness sheets and up to 200 `CON_…` sheets, stored uncompressed. A `perf` test measures the build; a reader's opening time is not measured.
- **A person edits the plan** and exports again: the edits are gone. The file says so in three places; `verify --outputs` reports an edited plan in `outputs/`.
- **The sides rule** can split a harness in a way the users would not draw. It is fixed and documented; a per-connector override would be one more field (not in 3.0.0).
- **Contact data in Git** (section 4.4).
- **Zip bytes across platforms.** `exports.normalise_xlsx` builds each `ZipInfo` without setting `create_system`, which Python takes from the platform; whether the `.xlsx` outputs differ in that byte between Windows and Linux is not checked here. The plan's writer sets it.

## 13. Owner questions

Each with the recommendation of this design.

- **Q1. One file per project, or one per harness?** One per project, `system/harness_plan.ods`, as the template is one document. Alternative: `harnesses/<ID>/<ID>_plan.ods`, which repeats the cover, register and shared sheets.
- **Q2. Does the change register replace or mirror the change log?** It mirrors it; nothing is typed into the plan. The document version is a person's field. Register rows that are not harness changes are not in 3.0.0.
- **Q3. Ship the users' colour table as an example?** No. A paste of two columns in Settings, and the JSON form in the user manual. The table is test data only.
- **Q4. A person edits a formula cell (or any cell). What happens on the next export?** It is overwritten. The Cover, the Notes and the About sheet say so; `verify --outputs` reports an edited plan in `outputs/`; work on a copy.
- **Q5. What do Description and Level mean for a cable pin and a device pin?** They belong to the device (box) pin, which the ICD describes. A cable pin shows the values of the box pin it plugs into; the editor offers neither field on a cable pin, and `check` warns about a value there (a hand-edited file) without removing it.
- **Q6. Function and Description:** Function = `Pin.signal`, Description = `Pin.function`, no new field (section 4.2).
- **Q7. SGND:** a role value `signal_ground`, never derived from a pin name in 3.0.0 (section 4.3).
- **Q8. "no SGND" in the labels:** the plan's header shows `[no SGND*]`; `labels.csv` and the build workbook's labels do not change in 3.0.0. Adding it there is a later change of those outputs.
- **Q9. Revisions are letters; the template counts MAJOR.MINOR.PATCH and wants a new harness name for an incompatible change.** Keep the letters; the plan shows the revision as it is; the tool does not enforce the users' naming rule.
- **Q10. If 2.3.0 needs a format change** (splice role, bonded pins), make one format 3 that holds both, in whichever release comes first, and number the releases from there.
- **Q11. Other format 3 candidates** (`Unit.library` of the 2.2 design Q1, `Pin.port` of the 2.1 design Q1): not bundled, unless the owner wants them now; each needs its own proof that the migration changes nothing.
- **Q12. The block diagram picture:** not in 3.0.0; a text cell names the harness drawing. Later: the routing sketch as SVG in the package for a harness of more than two connectors (how readers show an SVG picture is not checked).
- **Q13. Always on, or an option?** An option, `--harness-plan` and a check box remembered per folder (section 9).
- **Q14. Contact data:** in `project.json`, on the Cover only, not in `export.json`; the manual names the Git history (section 4.4).
- **Q15. *Conductor* in *used Cable Types*:** `Part.specification` of the wire part. The template shows no example; the owner or the users say what they mean.
- **Q16. Words without a template example:** `IN/OUT` for `bidir`, `SHIELD` for a shield pin, an empty cell for a spare pin. The owner may name others; they are fixed words of the tool, not settings.
- **Q17. The template's conditional formats** (GND against PWR, the search strings): written as in the template.

## 14. What this design does not check

- No spreadsheet program opened the users' template; it was read as XML.
- The behaviour of section 6.4 was seen in one LibreOffice version, headless, with default settings, on a hand-made package. Other readers (Excel, Gnumeric, OnlyOffice, online spreadsheets) were not tried.
- No user has seen a plan made by the tool.
- The design of 2.3.0 does not exist yet; section 8 assumes the splice of `PLAN_2.0.md` section 2.4.
- Whether the users' colour table follows any supplier's or standard's code is not known.
