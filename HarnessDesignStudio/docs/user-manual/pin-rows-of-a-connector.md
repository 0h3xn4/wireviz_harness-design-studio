# Pin rows of a connector

This page shows how to tell the tool where the pins of a connector sit on its face: the rows of the insert, for example a 21-pin Micro-D with the row 1 to 11 and, under it, the row 12 to 21. It says where the rows are kept, how to enter them in the editor, on the command line and from a pinout sheet, what the checks and the rule of power and return pins then say, and what the written files show.

> **New in 4.0.0** (format 4, decision D-251, [`DESIGN_4.0_ROW_LAYOUT.md`](../ait/DESIGN_4.0_ROW_LAYOUT.md)). A project of 3.x is upgraded once first ([upgrade a project](upgrade-a-project.md#8-from-format-3-to-format-4-400)). What each written file holds for the rows is in [`OUTPUTS.md`](../OUTPUTS.md#a-row-layout); the keys of the files are in [`FILE_FORMAT.md`](../FILE_FORMAT.md#format-4-the-row-layout-of-a-connector-400).

## Contents

- [What a row layout is](#what-a-row-layout-is)
- [Where the rows are kept](#where-the-rows-are-kept)
- [Before you start](#before-you-start)
- [1. Enter the rows in the editor](#1-enter-the-rows-in-the-editor)
- [2. Enter the rows on the command line](#2-enter-the-rows-on-the-command-line)
- [3. Bring the rows in from a pinout sheet](#3-bring-the-rows-in-from-a-pinout-sheet)
- [What the checks say](#what-the-checks-say)
- [Power and return pins on the face](#power-and-return-pins-on-the-face)
- [What the written files show](#what-the-written-files-show)
- [Older versions of the tool](#older-versions-of-the-tool)
- [What is not in 4.0.0](#what-is-not-in-400)
- [Common mistakes](#common-mistakes)

## What a row layout is

- The contacts of a connector sit in its insert in a fixed pattern. The datasheet and the interface control document (ICD) of a device show it as a face view. A **row layout** is that pattern written as data: the rows in order from the top of the face, and in each row the pin names in order along the row.
- A row is a **list of pin names**, not a range: a header numbered odd and even has the rows `1 3 5 7 9 / 2 4 6 8 10`, and pins named `A1` are written as they are named.
- **Rings.** A circular insert has rings in place of rows. The mark *rings* says that each row is a ring, from the outer ring inwards, its pins in order round the ring, so that the last pin of a ring is next to its first.
- **The short form.** The editor and the command line show and take a layout as one line: rows separated by `/`, the pins of a row by spaces or commas, a run of numbered pins as `1–11` (an en dash) or `1:11`, and `(rings)` at the end for the rings of a circular insert. `-` and `..` are part of a pin name (`1-11` is one pin), not a run. A run counts down too (`5–1`).
- The tool ships **no layout**: the starter parts have none, and the rows on this page are examples of the form, not read from a datasheet. Enter the rows of your own parts from their datasheets.

## Where the rows are kept

- **On a connector part**, shared by every connector of that part: the eleven identical Micro-D 9 connectors of a power unit have one face, entered once. The part's rows travel with it into a device file and a subsystem file.
- **On a device connector, as its own rows**, where that connector differs from its part: a generic part used for inserts that differ, pins named otherwise than the part's numbers, or rows read from one device's ICD.
- **A connector of a harness** has no rows of its own. It takes the rows of its part, else those of the device connector it plugs into: pins mate by name, so the rows of the device connector are the rows of the plug, seen from the mating face.

So the rows of a device connector are its own rows, else its part's, else none. A name in the rows that is not a pin of the connector is left out for that connector (and `check` says so), and a pin that is in no row is listed after the rows, without a row. The rows are design data, like the pins: setting them is one undo step, goes into the change journal, and makes the outputs out of date until you generate and export again. A release does not lock them.

## Before you start

- The project is in format 4 (4.0.0). A project of 3.x is upgraded once with `migrate` or the editor's question ([upgrade a project](upgrade-a-project.md#8-from-format-3-to-format-4-400)).
- The examples use the practice project `wheel-link` (`harness-design-studio new wheel-link --template first-steps`), generated. Its connector `RW1-J02` is of the part `EX-MICROD-21-F`; `PCDU1-J01`, `OBC1-J02` and `RW1-J01` are of the part `EX-MICROD-9-F`; `OBC1-J03` is of the part `EX-MICROD-15-F`.

## 1. Enter the rows in the editor

In the app (GUI, not run here on a real display; the pictures `docs/ux/qt/29-devices-pin-rows.png` and `30-pin-rows-dialog.png` were made offscreen):

1. Open the **Devices** tab (Ctrl+6) and choose the device and the connector. The line over the pin table says where the rows come from: *Pins of RW1-J02  Rows: 1–11 / 12–21, from part EX-MICROD-21-F*, or *own rows*, or *none*. When the pane is narrow the text is cut; its tooltip holds all of it.
2. Press **Edit rows…** (before **Add pin**). The window **Pin rows of RW1-J02** takes one row per line (`1–11` on the first line, `12–21` on the second). The common case, rows numbered one after the other, is quicker as **Row lengths**: type `11, 10` and press **Fill**. Tick **Rings of a circular insert** for a circular insert.
3. A mistake is said on a line under the fields, and **Set rows** stays off until it is put right: *The rows cannot be stored on OBC1-J02: the row layout names pin 22; OBC1-J02 has no pin 22*, or *pin 7 is in row 1 and in row 2*.
4. **Set rows** stores the rows as the connector's own rows. **Use for every connector of this part** moves them to the part and clears the equal own rows of the part's other connectors. **Back to the part's rows** clears the connector's own rows, so that it takes the part's again. **Clear** empties the box; **Set rows** then removes the rows.

While a connector has rows, the pin table has a column **Pin row** next to **Pin**, the row of each pin (empty for a pin in no row).

The rows of a **part** are entered in the **Inspector** of the part (**Pin rows** with **Edit rows…**): the same window, which names the connectors of the part that lack a pin of the rows. The Inspector of a **connector of a harness** shows the rows it takes and where they come from, read-only.

Each change is one undo step, journaled when you save.

## 2. Enter the rows on the command line

`harness-design-studio pin-rows DIR --part ID` or `--connector ID` shows the rows and where they come from; `--set` takes the short form, `--lengths` the row lengths, `--clear` removes a part's rows or a connector's own rows. The rows of the owner's example, on the part:

```
harness-design-studio pin-rows wheel-link --part EX-MICROD-21-F --lengths 11,10
```

```
Saved.
Pin rows of part EX-MICROD-21-F: 1–11 / 12–21
  Row 1: 1–11
  Row 2: 12–21
```

The plug of the harness `W001` on `RW1-J02` takes them, read-only:

```
harness-design-studio pin-rows wheel-link --connector W001-P2
```

```
Pin rows of W001-P2: 1–11 / 12–21 (from RW1-J02, the device connector it plugs into)
  Row 1: 1–11
  Row 2: 12–21
  A connector of a harness has no rows of its own: set them on its part or on the device connector it plugs into.
```

Own rows of one device connector, and back to the part's:

```
harness-design-studio pin-rows wheel-link --part EX-MICROD-9-F --set "1–5 / 6–9"
harness-design-studio pin-rows wheel-link --connector OBC1-J02 --set "1 2 / 3"
```

```
Saved.
Pin rows of OBC1-J02: 1 2 / 3 (own rows)
  Row 1: 1 2
  Row 2: 3
  In no row: 4–9 (listed after the rows)
```

```
harness-design-studio pin-rows wheel-link --connector OBC1-J02 --clear
```

```
Saved.
Pin rows of OBC1-J02: 1–5 / 6–9 (from part EX-MICROD-9-F)
  Row 1: 1–5
  Row 2: 6–9
```

`--rings` and `--no-rings` set or clear the ring mark of the rows (`Pin rows of OBC1-J02: 1–5 (rings) (own rows)`). `--to-part` (with `--connector`) moves a device connector's own rows to its part, refuses when the part has other rows, and clears the equal own rows of the part's other connectors. A mistake is refused with the reason, exit code 2, and nothing is saved:

```
error: The rows cannot be stored on EX-MICROD-9-F: the row layout names 10 pins; the part has 9.
```

`--json` prints `ok`, `changed`, `object`, `kind`, `rows`, `rings`, `source` (`own`, `part`, `mated` or `none`), `source_id` and `text` ([`CLI.md`](../CLI.md#harness-design-studio-pin-rows)). A read-only project refuses the change. From a script, `harness_design_studio.api` has `row_layout_of`, `set_row_layout` and `clear_row_layout` ([script the tool](script-the-tool.md)).

## 3. Bring the rows in from a pinout sheet

`import-pinout` reads an optional column **Pin row** (also *Row* or *Contact row*): a whole number from 1, the row of the pin on that line; the pins of a row are in the order of the lines, and an empty cell leaves the pin out of the rows. Rows that differ from the ones the connector has become its own rows, keeping its ring mark:

```
Connector,Pin,Signal,Pin row
OBC1-J03,1,,1
...
OBC1-J03,8,,1
OBC1-J03,9,,2
...
OBC1-J03,15,,2
```

```
harness-design-studio import-pinout wheel-link obc1-rows.csv --device OBC1
```

```
Read 15 row(s) of device pinout from obc1-rows.csv (sha256 a1727b807f79).
Columns read: Connector -> connector, Pin -> pin, Signal -> signal, Pin row -> pin_row
note: Row layouts set: OBC1-J03.
note: The rows are stored on OBC1-J03 only; to use them for every connector of part EX-MICROD-15-F, choose Use for every connector of this part in the Devices tab, or run `pin-rows --connector OBC1-J03 --to-part`.
OBC1-J03: OK updated (15 pin(s))
Imported 1 connector(s), 15 pin(s). Generate harnesses again to connect interfaces to the pins.
Import record: pinout:obc1-rows.csv written to imports/records.json.
```

Then, if the rows are those of the part:

```
harness-design-studio pin-rows wheel-link --connector OBC1-J03 --to-part
```

```
Saved.
Pin rows of OBC1-J03: 1–8 / 9–15 (from part EX-MICROD-15-F)
  Row 1: 1–8
  Row 2: 9–15
```

- The rows are compared row by row as sets of pins, so a sheet with the rows the connector has already changes nothing (the order inside a row stays as stored).
- A gap in the numbers (rows 1 and 3, no 2) is closed up and noted. A cell that is not a whole number from 1 refuses the sheet with its row number, and nothing is changed. A sheet without the column leaves every layout as it is.
- **`export-pinout`** writes the column *Pin row* while a connector of the device has rows, so its file reads back through `import-pinout` with no change:

  ```
  Connector,Role,Mates with,Part,Pin,Signal,Interface,Wires,Spare,Pin row
  RW1-J01,box,,EX-MICROD-9-F,1,PWR,IF-001,W002-001,no,1
  RW1-J01,box,,EX-MICROD-9-F,2,RTN,IF-001,W002-002,no,1
  ```

- **Device files and subsystem files** (`save-device`, `add-device`, `update-device`, `export-devices`, `import-devices`, `export-subsystem`, `import-subsystem`) carry the rows of the parts and the own rows of the device connectors. A device library file with rows is written as version 3 and a subsystem file as version 2; files without rows keep their version. `update-device` shows a change of a connector's own rows in its diff, in the short form.
- `import-parts` and `import-netlist` do not read rows.

## What the checks say

`validate`, `check` and the editor give these, worked out from the rows of each connector (the warnings also show in the **Problems** panel under the design rule *Model consistency*, `model-inconsistent`; the note shows there as a row of severity Info). None of them is an error: a project with odd rows still generates and exports.

| Code | Kind | When |
| --- | --- | --- |
| `row_layout_pin_missing` | warning | the rows of a part, or of the device connector a connector of a harness plugs into, name a pin the connector does not have; the pin is left out of its rows. Typical cause: pins renamed, or a part used for an insert it does not have |
| `row_layout_pins_outside` | note | a connector has pins in no row; they are listed after the rows, and the rule of power and return pins judges them in the order of the list of pins |
| `row_layout_mate_differs` | warning | two connectors that mate (a connector of a harness and the device connector it plugs into), or two parts that are each other's mating part, both have rows, and a row of one holds other pins than the same row of the other. The order inside a row is not compared, since a mating face is seen mirrored |

For example, with the own rows `1 2 / 3` on `OBC1-J02`, and rows `1–4 / 5–9` given to the mating part `EX-MICROD-9-M`:

```
INFO    row_layout_pins_outside: Pins 4, 5, 6, 7, 8, 9 of OBC1-J02 are in no row of the own row layout of OBC1-J02; they are listed after the rows, without a row, and power-return-adjacent judges them in the order of the list of pins.
WARNING row_layout_mate_differs: The mating parts EX-MICROD-9-F and EX-MICROD-9-M have different row layouts: row 1 holds 1–5 on EX-MICROD-9-F and 1–4 on EX-MICROD-9-M. The order inside a row is not compared, since a mating face is seen mirrored.
WARNING row_layout_mate_differs: W002-P1 and the device connector PCDU1-J01 it plugs into have different row layouts (the row layout of part EX-MICROD-9-M; the row layout of part EX-MICROD-9-F): row 1 holds 1–4 on W002-P1 and 1–5 on PCDU1-J01. The order inside a row is not compared, since a mating face is seen mirrored.
```

In the Problems list a click on one of them goes to the connector, and the row menu has **Edit the pin rows of …** where the rows come from.

## Power and return pins on the face

The design rule *Power and return pins* (`power-return-adjacent`, ECSS-Q-ST-30-11C 6.11.3 a) warns when two power or ground pins of different signals on one connector have fewer free contacts between them than `generation.power_return_gap_pins` asks. On a connector without rows, *between* means the list of pins. **On a connector with rows the rule reads the face:**

- **In one row** it counts the free contacts between the two pins along the row (round a ring, the shorter way).
- **In rows next to each other**, two pins are neighbours on the face when their places differ by one place or less, the rows taken as centred on each other; there is no contact between them, so the rule warns whenever a gap is set. For a 21-pin Micro-D with the rows `1–11 / 12–21`, pin 12 sits between pins 1 and 2, and pin 21 between 10 and 11. Rows of equal length give the pin straight across and both diagonal pins, which may be one more than the real face has: the rule warns more, never less, than a face of centred rows.
- **A pair with a pin in no row** is judged in the list of pins, as before.
- **Pins of different rings** are not judged, because the rows alone do not say which contacts of two rings face each other; the note `unchecked-config` names such pairs for each connector, so the gap is written down.

An ICD that puts `RTN` on pin 6 of the Micro-D 9 `PCDU1-J01`, with `PWR` on pin 1 (`generation.power_return_gap_pins` = 1): in the list, four free pins are between them; on the face with the rows `1–5 / 6–9`, pin 6 sits under pins 1 and 2:

```
harness-design-studio drc wheel-link
```

```
- **PCDU1-J01: PWR (pin 1) and RTN (pin 6) are neighbours on the face of the connector (rows 1 and 2), with no unassigned contact between them** (`power-return-adjacent.PCDU1-J01.1_6.5e3ac225`)
  Power and return on neighbouring contacts raise the risk of a short circuit. To fix it: Leave at least one contact unassigned between them (regenerate the harness). On a connector with a row layout, a neighbour in the next row counts too; move one pin or lock the pins (Generate does not read the rows). Requirement: ECSS-Q-ST-30-11_0140052.
```

**Generate does not read the rows** (owner answer L2): its pin assignment keeps the order of the pin list, so on a connector with rows it can place a power and a return pin in rows next to each other, and the rule then warns about a real pair of contacts. Move one pin or lock the pins. The rule ID, its setting and its finding IDs stay as they were, and **a project without rows gives the same findings as at 3.0.x**. `explain` of a finding of the rule says where the pins sit on the face; `settings` and `docs/RULES.md` give the assumptions *A-RETURN-GAP* (neighbours on the face, rows centred on each other) and *A-PIN-ORDER* (Generate's order, which does not read the rows).

`explain` of a connector names its rows and where they come from, while it has rows:

```
harness-design-studio explain wheel-link RW1-J02
```

```
    Pin rows = 1–11 / 12–21   [part EX-MICROD-21-F: row_layout (the rows of its part)]
```

## What the written files show

Only a project in which some connector has rows changes; every other project writes the same files as before.

- **`system/box_pinouts.csv`** (and the Devices tab's *Pinout as exported*) gets a last column **Pin row** while some device connector of the project has rows: the row of each pin, empty for a pin in no row. The rows stay in pin order.

  ```
  Connector,Role,Mates with,Part,Pin,Signal,Interface,Wires,Spare,Pin row
  OBC1-J01,box,,EX-MICROD-25-F,1,TX+,IF-002,W001-001,no,
  ...
  PCDU1-J01,box,,EX-MICROD-9-F,1,PWR,IF-001,W002-001,no,1
  PCDU1-J01,box,,EX-MICROD-9-F,6,RTN,IF-001,W002-002,no,2
  ```

- **`harnesses/<ID>/pinouts.csv`** and its sheet of `<ID>.xlsx`: the same column while a connector of that harness has rows (a plug takes its part's rows, else those of the device connector it plugs into).
- **The harness plan** (`export --harness-plan`, [export the harness plans](export-the-harness-plans.md)): the `CON_…` sheet of a device connector with rows has **Pin row** in column F after *Description*; the near block of such a connector lists its pins row by row in the order of the rows, then the pins in no row in pin order, with **Pin row** in column A, left of *Pin No.*, each cell a formula that copies column F of the `CON_…` sheet. Column A is outside the printed range of the template.
- **`system/export.json`** holds `row_layout` of the parts and the device connectors that have rows, as in the project files.
- **The findings** (`drc_findings.csv`, `drc_report.md`): the rule of the face, above.

`verify --outputs` reads the rows again with its own code and refuses a wrong row, a missing or extra column and a wrong order of the plan. The drawings, the build workbook, the labels, the BOM, the mass and length tables, the connection list and the WireViz file do not show rows.

## Older versions of the tool

The rows are saved in format 4. Versions 3.x open a format 4 project read-only. A part or a connector with rows breaks the files of format 3, so 3.0.0 sets it aside (*quarantined: … row_layout: Extra inputs are not permitted*), and with it the connectors of such a part lose their part: `validate` lists errors, and `generate` and `export` refuse the project (*the project has damaged files*) and write nothing. Upgrade the whole team together ([upgrade a project](upgrade-a-project.md#8-from-format-3-to-format-4-400)).

## What is not in 4.0.0

- **No picture of the face.** The drawings keep their connector pictures; no face view is drawn.
- **No positions.** No pitch, no offset of a row, no clocking of a circular insert. The rule takes the rows as centred on each other.
- **Generate does not place pins by the face** (L2).
- **No rows in the starter library or the examples** (L3), and `import-parts` reads none.
- **The far side of the harness plan** and its reference pinouts keep their columns; the `CON_…` sheet of the far connector shows the rows.

## Common mistakes

- **`row_layout_pin_missing` on many connectors after `--lengths`.** The part's rows name pins its connectors do not have (for example rows of nine pins on connectors with three). Give the part the rows of its insert, or give the connector rows of its own.
- **"pin 7 is in row 1 and in row 2".** A pin is in at most one row; names are compared without regard to case.
- **"the row layout names 10 pins; the part has 9".** A part's rows name at most its pin count.
- **Rows on a connector of a harness.** It has none of its own: set them on its part or on the device connector it plugs into.
- **The rows of every connector of a part came in one by one from the ICDs.** Use **Use for every connector of this part**, or `pin-rows --connector ID --to-part`, once the rows are those of the part.
- **The finding stays after you entered the rows.** Generate does not read the rows: move one pin or lock the pins, then generate again.

Next: [define a device](define-a-device.md), [export the harness plans](export-the-harness-plans.md), [read and fix problems](read-and-fix-problems.md)
