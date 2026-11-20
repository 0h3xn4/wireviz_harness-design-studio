# Naming and title block

This page says how the tool makes the IDs of devices, connectors, interfaces, connections, harnesses and wires, where you see them and what text a label prints. It then shows how to change the IDs the tool gives to harnesses, connectors and wires, and which fields the title block of a drawing shows.

## Contents

- [Connector IDs and tags](#connector-ids-and-tags)
- [Before you start](#before-you-start)
- [1. Name patterns: `config/naming.json`](#1-name-patterns-confignamingjson)
- [2. Title block: `config/titleblock.json`](#2-title-block-configtitleblockjson)
- [Common mistakes](#common-mistakes)

## Connector IDs and tags

Every object of a design has an **ID** that the tool makes and that never repeats in a project. Some objects also have a **name** or a **label** that you write: these are the "tags". The ID is what the files, the tables and the checks use; the name and the label are for people.

### How the IDs are made

| Example | What it is | How the ID is made | Can you change it? |
| --- | --- | --- | --- |
| `PCDU1` | a device | the letters of its kind and the next free number, or what you type in the window *Add device* | Yes: **ID** in the Inspector (see the note below) |
| `PCDU1-J01` | a connector on a device (a *box connector*) | the device ID, `-J` and the next free number of that device, two digits. Its short **name** is `J01`. | The name, yes (Devices tab); the ID, no |
| `IF-002` | an interface: a connection of a type that you ask for between two devices | `IF-` and the next free number, three digits. An imported interface table can bring its own IDs. | No; its **name** (`RS-422 OBC1 to RW1`), yes |
| `L7` | a connection made pin by pin in the window *Link connectors* | `L` and the next free number | No; **Rename…** gives it a name |
| `W001` | a harness | the pattern `harness` of `config/naming.json` | Yes, by the pattern ([below](#1-name-patterns-confignamingjson)) |
| `W001-P1` | a connector on a harness (a *cable connector*, the plug that mates with a box connector) | the pattern `cable_connector`: the harness ID, `-P` and a number inside the harness | Yes, by the pattern |
| `W001-001` | a wire | the pattern `wire` | Yes, by the pattern |
| `W001-S1`, `W001-L1` | a shield, a routing segment | the patterns `shield` and `segment` | Yes, by the pattern |
| `1`, `A1` | a pin | the part or the pinout of the device | Yes, in the Devices tab ([define a device](define-a-device.md)) |

The numbers are the first free ones, so an ID that was deleted can come back for a new object. Generating again keeps the IDs of the harnesses and wires that stay.

**Renaming a device keeps its connector IDs.** When you rename `RW1` to `RW7`, its connectors stay `RW1-J01` and `RW1-J02`; they now belong to `RW7`. (Checked with the program's own rename step on the practice project.) For the same reason the old ID `RW1` is not free for a new device while those connectors exist.

### The tags you can give

| Tag | On | Where you set it | What it does |
| --- | --- | --- | --- |
| **Name** | a device, an interface, a connection, a device connector (`J01`) | the Inspector, **Rename…** of a connection, the Devices tab | shown on the diagram and in the tables; it does not change the ID |
| **Label** | a wire, a cable connector, a harness, a device connector | the **Edit wire** tab, the card of the connector in the Devices tab ([edit a wire](edit-a-wire.md)) | printed on the labels (below) |
| **Signal** | a pin | the Devices tab, a pinout or KiCad import | what fixed pins are matched by, and the name the labels print when a wire has no label |
| **Function** | a pin | the Devices tab | free text in the pinouts and the build workbook |
| **Kind** | a device | the Inspector | the picture of the device ([telling devices apart](telling-devices-apart.md)) |

### Where you see them

- **On the diagram:** each device card shows its ID in bold and, in Guided mode, its name. In Expert mode its connectors are ports; hold the pointer over a port to read the connector name and its free pins. Select an interface line to read its ID and name in the Inspector.
- **In the tables** (`outputs/`, [export the outputs](export-the-outputs.md)): the wire list names each wire's cable connectors and pins; `pinouts.csv` lists each cable connector with the box connector it mates with; `mating_matrix.csv` puts each box connector next to its cable connector and harness; `traceability.csv` gives the ends of each interface as `DEVICE/CONNECTOR`. From the practice project:

  ```
  Box connector,Unit,Part,Gender,Cable connector,Cable part,Cable gender,Harness
  OBC1-J01,OBC1,EX-MICROD-25-F,female,W001-P1,EX-MICROD-25-M,male,W001
  ```

  ```
  Interface,Name,Type,From,To,Harnesses,Wires,Routed
  IF-002,RS-422 OBC1 to RW1,rs422,OBC1/OBC1-J01,RW1/RW1-J02,W001,W001-001;W001-002;W001-003;W001-004,yes
  ```

  (The first lines of `system/mating_matrix.csv` and `system/traceability.csv` after the two comment lines.)
- **On the drawings** (`export --drawings`): the harness drawing shows each cable connector with the box connector it mates with, and the title block shows the harness ID.
- **On the labels:** `labels.csv` and the **Labels** sheet of the build workbook.

### What a label prints

`harnesses/<ID>/labels.csv` has one row for each cable connector, two for each wire (one for each end) and one for the harness when the harness has a label. With the practice project after `generate` and `export`:

```
Label,Kind,Text,Quantity
W001-P1,connector,W001-P1 mates OBC1-J01,1
W001-P2,connector,W001-P2 mates RW1-J02,1
W001-001-A,wire,W001-001 TX+/RX+ to W001-P2.3,1
W001-001-B,wire,W001-001 TX+/RX+ to W001-P1.1,1
```

- **A cable connector** prints its label, else the label of the box connector it plugs into, then `(W001-P1 mates OBC1-J01)`. With no label the text is `W001-P1 mates OBC1-J01`.
- **A wire** prints, at each end, its ID, its label (else its signal, here `TX+/RX+`), `to` and the connector and pin at the **other** end, and the EMC class in brackets when its interface type has one.
- **A harness** prints its label as it is, and gets no row while it has none.

This is the label format `standard`. The setting `model.label_format` chooses `compact`, `descriptive`, `harness_device_connector` or a template of your own ([labels and colours](../models/labels-and-colours.md)); `harness-design-studio explain DIR W001-P1` prints how one label was made.

**A project you start with 4.1.0 or later** is in the format `harness_device_connector`: a cable connector's label is the harness, the device and the name the device gives its connector, `W001:OBC1:J01` (a loose end `W001:W001-P2 open end`, a connector that plugs into nothing `W001:W001-P3`), and the wire labels are the text above. The label you give a connector is not printed in this format; for both, choose `custom` with the connector template `{name} {harness}:{device}:{mates_name}`. In the harness plan the `CON_…` sheet then has *Connector Name* in row 4, and the header of a near block reads `[W001:OBC1:J01]`. A project made before 4.1.0, or from one of the other templates, keeps the format it has. A 4.0.x tool refuses a project in this format, so update the whole team at the same time.

## Before you start

- Both settings are files in the project's `config/` folder. They have the usual shape (`name`, `placeholder`, `values`; see [the shape of a config file](fill-in-engineering-values.md#the-shape-of-a-config-file)).
- Change them **before** you release anything. IDs are stable once a harness is released.
- The title block layout is a placeholder: the owner's decision D-15 (the company format) is open. The tool shows a generic title block whose fields you can choose. See [`OPEN_DECISIONS.md`](../OPEN_DECISIONS.md).
- Edit the files while the project is not open in the app.
- These patterns make the **IDs**. To print other text on the labels, give a wire, a connector or the harness a *label* in the app (since 1.4.0): a wire's and the harness's in the **Edit wire** tab, a box connector's on its card in the **Devices** tab. The ID does not change; `labels.csv` prints the label ([edit a wire](edit-a-wire.md)).

## 1. Name patterns: `config/naming.json`

The shipped file:

```
{
  "name": "naming",
  "placeholder": false,
  "values": {
    "box_connector": "{unit}-J{n:02d}",
    "cable_connector": "{harness}-P{n}",
    "harness": "W{n:03d}",
    "wire": "{harness}-{n:03d}"
  }
}
```

| Key | Used for | Default |
| --- | --- | --- |
| `harness` | a harness ID (`n` counts 1, 2, ...) | `W{n:03d}`, gives `W001` |
| `cable_connector` | the connectors on a harness | `{harness}-P{n}`, gives `W001-P1` |
| `wire` | a wire | `{harness}-{n:03d}`, gives `W001-001` |
| `shield` | a shield | `{harness}-S{n}` (not in the file; the default is used) |
| `branch` | a branch point | `{harness}-B{n}` |
| `segment` | a routing segment | `{harness}-L{n}` |

Add `shield`, `branch` or `segment` to the file if you want to change them. The key `box_connector` is in the file, but the program does not read it: connectors on a device are always named like `OBC1-J01`.

The same file can also hold two settings that are not name patterns and are not in the shipped file (both since 1.9.0): `signal_counterparts`, the words that pair a transmit pin with a receive pin, and `release_distinct_roles`, which asks for three different people as author, checker and person who releases. The command `harness-design-studio config DIR --counterparts` and `--distinct-roles` set them; see [`CONFIG.md`](../CONFIG.md#namingjson).

Example. Set `"harness": "HN-{n:02d}"` and generate:

```
harness-design-studio generate wheel-link
```

The harnesses are now `HN-01` and `HN-02` (folders `outputs/harnesses/HN-01/` and so on), and their wires `HN-01-001`.

A pattern must give a different valid ID for every harness and number. If it does not, the tool says so and uses the default:

```
warning: [naming] The naming template 'naming.harness' is not valid; the default was used.
```

(That is what `"harness": "HN"` gives.) Valid IDs start with a letter and use letters, digits and `_ - .` only. The same fallback, with the same warning, happens when a pattern raises an error (`{x}` that does not exist), gives a reserved name such as `COM1`, repeats a name, or would give a name too long for the harness (the warning appears after the names are made). A pattern can no longer crash or hang the generation.

## 2. Title block: `config/titleblock.json`

The shipped file lists all ten fields, in order:

```
"fields": ["project", "harness_id", "title", "version", "date",
           "author", "checker", "approver", "sheet", "status"]
```

Remove a field to hide it (the sheet number too: the output check then does not look for it), or reorder them. A name that is not in the list, a name twice, or anything that is not text is reported as a configuration error (`harness-design-studio config` and `harness-design-studio drc` show it, for example `config/titleblock.json: fields names a field that does not exist ('sheet2'). The fields are: project, harness_id, ...`; `validate` and `check` did not report it when this page was checked, and `generate` stops with the same text, `error: [config_invalid] ...`, and does not save) and the default fields (`project`, `harness_id`, `title`, `version`, `status`, `sheet`) are drawn by `export --drawings` until it is fixed. An empty list also means the default. After a release the title block fields are frozen with the rest of the configuration ([change a released harness](change-a-released-harness.md)). With `["project", "harness_id", "version", "status", "sheet"]` the title block of `HN-01` shows:

```
PROJECT         First steps: reaction wheel link
HARNESS ID      HN-01
VERSION         1.0.0
STATUS          draft
SHEET           1 / 1
```

(These are the texts found in the SVG of a test run, label and value. The layout on the sheet is not shown here.)

The title block is part of the harness drawing, which is written only with `export --drawings` ([export the outputs](export-the-outputs.md#5-the-pdf-drawings-optional)). Date, author, checker and approver come from the harness itself. They show "-" until the harness has been reviewed and released ([release a harness](release-a-harness.md)). The build workbook shows the author, checker, approver and release date on its **Start here** sheet (`not set` until then); it has no title block.

## Common mistakes

- **Renaming after a release.** Released IDs are stable. Start from a project that has not been released, or start a new project.
- **A pattern without `{n}`.** Every harness would get the same ID. The tool falls back to the default and warns.
- **Expecting a company title block.** The format is open (D-15). Only the fields and their order are configurable.

More: [`CONFIG.md`](../CONFIG.md), [`TROUBLESHOOTING.md`](../TROUBLESHOOTING.md).

Next: [export the outputs](export-the-outputs.md), [release a harness](release-a-harness.md)
