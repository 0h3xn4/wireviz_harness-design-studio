# Design of 4.4.0: names and ports

Written on 2026-11-22 from a reading of the code at 4.3.0 (annotated tag `v4.3.0` on `20bf8f1`, the merge of the preparation, #337; the checkout reports `harness 4.3.0`) and from runs of the command line and of throw-away scripts on the five examples, the three fixture projects of `tests/fixtures/projects/` and small test projects made with `new --template blank` and `import-pinout`. It designs milestone E4 of [`ELEC_FEEDBACK_PLAN.md`](ELEC_FEEDBACK_PLAN.md) (points 10, 11 and Cb of the feedback: *automatic signal recognition and connection: an OBC with 10+ interfaces on one connector, connected to TTC1 and TTC2; the TTC1 signals go to TTC1 and the TTC2 signals to TTC2, from the signal and device names*; *read the ICDs and their README files*; *names that somebody thought are right do not fit general rules and need manual work afterwards*). Paths are relative to `src/harness_design_studio/` unless they start with `docs/`, `tests/` or `tools/`. Its form follows the designs of 4.1.0, 4.2.0 and 4.3.0 ([`DESIGN_4.1_PRODUCTION_SHEET.md`](DESIGN_4.1_PRODUCTION_SHEET.md), [`DESIGN_4.2_ELECTRICAL_CHECKS.md`](DESIGN_4.2_ELECTRICAL_CHECKS.md), [`DESIGN_4.3_REVIEW_VIEW.md`](DESIGN_4.3_REVIEW_VIEW.md)): scope, what exists, one part per feature, what changes in the written files, edge cases, tests, documents, the decision, the owner questions, the pull requests, the corrections to the plan and what was not checked. Choices that are the owner's are N1 to N12 (section 15), each with a recommendation first. Every device name, signal name and file on this page is made up for the example (`TTC1`, `OBC1`, `Example Ltd`).

**Status (2026-11-23):** built and prepared as 4.4.0, not tagged. Pull requests 1 to 7 of section 16 are written: 1 (*Unassign*) as #340; 2 (*Core and settings*) as #342; 3 (*Generate by far device*) as #343; 4 (*Pairing and the link review*) as #344; 5 (*The map at import*) as #345; 6 (*The editor*) as #346; and 7, the end-to-end test `tests/test_e2e_440.py`, the documents of section 12 and the release notes [`docs/releases/4.4.0.md`](../releases/4.4.0.md), as #347. The pull requests follow the recommendations of N1 to N12; no owner answer is recorded. What was built differently and what was found on the way is at the end of section 17 (items 8 to 14). Pull request 8 is this preparation of 4.4.0, on the branch `feat/e4-prepare` (decision D-263): the version 4.4.0, the changelog section, the decision rows, the status pages and the records made again with the repository's tools (a stamp-only renewal: `4.4.0` has five characters, as `4.3.0` and `2.4.0` have). The decision that records the design is D-262 (section 14); this preparation writes it into `docs/DECISIONS.md` as decided, on the recommendations of N1 to N12, with a note of what was built where it differs from section 14. 4.4.0 is published once it is tagged.

*Written before any code (kept as it was):* draft. No code is written. No owner answer yet; the owner has said that the work goes on by the recommendations, so each question of section 15 has the answer the pull requests follow while it is open. The decision that records the design is D-262 (section 14), proposed.

## 0. The frame

The engineer's case is one connector of an on-board computer with many interfaces, to two transceivers, whose pins say by their names which transceiver they belong to (`TTC1_TX+`, `TTC2_TX+`). The tool reads ports from names since 2.1.0 (D-237), but it gives an interface the first free port in name order, so the interface to TTC2 can get the pins named `TTC1_…`, and nothing says so (section 2.1, run). The pairing of a connection makes the same mistake (section 2.3, run). And a team's own words for a signal (`TXP` for `TX+`) can be translated today only for a KiCad netlist, by hand on every import, and only for a whole name (section 2.5, run). E4 answers this in a minor release:

1. **Format 4 stays frozen** (D-254). Nothing new is stored in a project file outside `config/`. The two new values are keys of a config file that exists, `config/naming.json`, which a 4.3.x tool reads and keeps without a word (tried, section 2.6); a new config file, or a new key of `config/model.json`, would not be (also tried).
2. **Opt-in: a project that sets nothing keeps its bytes.** Both settings are off or empty by default. With them unset, every function takes the code path of 4.3.0, and the guards of section 9 hold every written file of the examples and fixtures.
3. **The tool invents no team content** (D-11). It ships no name map and no device convention; a team states its own (a table of its words, a switch that says its pin names name the far device). Nothing is guessed from a name that reads in two ways: such a name is left as it is, and a note says why, as for ports (D-237).
4. **The tool proposes and the person confirms** (D-172). The pairing stays a proposal; Generate stays the generator it is, with one more step in its port order that a person can override with *Choose port…*.
5. **No importer for a format nobody has shown.** The plan's ICD importer waits for an example (plan question 9; section 6). What E4 does for ICDs is the map at import, for the two importers that read a device's pins from outside.

## 1. Scope

### 1.1 In scope

| Part | What is built | Points |
|---|---|---|
| A | **The port named after the far device.** With `naming.far_device_names` on, Generate gives an interface, on a device connector with named ports, the port whose name names the device at the interface's other end (`TTC2_TX+` … for the interface to TTC2), before the port it held before and before the first free port in name order; it never gives an interface a port named after another device. The editor's dry run (the room of a connector, the Guided choice), *Choose port…*, `explain` and the independent verifier follow the same rule | 10 |
| B | **Pairing that reads the far device's name.** With the same setting on, the pairing proposal of a connection reads the name of the other device off a pin name (`TTC2_TX` on OBC1 is `TX` in a link to TTC2) and leaves out the pins that name a third device, with a note; the link review reads the names the same way | 10, Cb |
| C | **The project's signal map.** The key `signal_map` of `config/naming.json`: a table of a team's own signal name to the signal name of an interface type (`TXP` to `TX+`), empty by default. `import-pinout` and `import-netlist` write the type's name, also inside a port (`TTC1_TXP` to `TTC1_TX+`), and say what they renamed; `config DIR --signal-map FILE` takes the CSV or JSON file that `import-netlist --signal-map` reads today | Cb, 11 |
| D | **ICDs: what is in scope.** No new importer. `import-pinout`'s table is the documented generic form of a pinout (its columns are in `docs/IMPORTS.md`); the team's ICD format and its README wait for an example (section 6) | 11 |
| E | **The fix of *Unassign from interface* on a fixed pin.** Found on the way (section 2.7): it clears the signal name of a pin of a fixed pinout, so a port loses its names | — (found) |

And with them: two settings (`naming.far_device_names`, `naming.signal_map`), their checks in `configcheck`, the assumption `A-FAR-DEVICE`, two options of `config` (`--far-device-names on|off`, `--signal-map FILE|none`), the verifier check `port_far_device`, and four requirements (REQ-PIN-08, REQ-PIN-09, REQ-IMPORT-02, REQ-GUI-32).

### 1.2 Not in scope

- **An importer of a team's ICD format or of an ICD's README.** No example was given (plan question 9 is open); section 6 says what waits for it.
- **The map read when Generate, the rules or the verifier compare names.** The map acts at import only (N6): the names in the project are the type's names afterwards, so every reader of 4.3.0 reads them unchanged. A map read everywhere would need a second copy in the verifier and in each rule that reads a name (`signal-unassigned`, `direction-conflict`, the four electrical rules).
- **The map on library devices** (`import-devices`, `import-subsystem`, `add-device`, `update-device`): a library holds a device as a team saved it; a map there would make every `update-device` diff show the renamed pins (N11).
- **Device names other than the ID.** A pin name is read against the device IDs (`TTC1`), not against its name (`Unit.name`, `Transceiver 1`) (N2).
- **A new design rule.** A new rule changes *Rules run: 43* in every DRC report of every project; the checks of E4 are in the verifier and in the link review, which have no such count.
- **The pairing of a loose cable end** (`manual_harness.propose_plug`): the cable side belongs to no device, so it reads names as today.
- **A reverse map on export** (`export-pinout` in the team's words).
- **Everything of E5** (format 5).

## 2. What exists at 4.3.0

### 2.1 Ports, and how Generate gives them

A port is a convention on `Pin.signal`, not a field (`core/ports.py`, design of 2.1.0): for an interface type with the signal names N, a **fixed** pin named `P<sep>t` or `t<sep>P` (t in N, sep one of `_ . -`, P not empty) carries t in the port P; a name in N is the bare port; a name that reads in two ways is in no port. Matching is exact and case-sensitive. A named port is usable when each signal of the type has exactly one pin (`ports_of`, `ConnectorPorts.usable`, in natural order of the names, `RS422_2` before `RS422_10`).

`generate/pins._allocate_fixed` gives the pins of a fixed pinout to the interfaces that end on the connector, ranked by the place of their category in `model.pin_allocation_categories` and then by interface ID, in four steps: (1) an interface whose locked pins are in a named port takes the rest of that port; (2) an interface gets back the complete named port it held before, while it is free; (3) every other interface takes the free pins of the exact names, as at 2.0.1; (4) an interface step 3 cannot place takes **the first free complete named port in natural order**. The reason of a pin says so: `…; an interface keeps the port it used before, else takes the first free RS-422 port (ports in name order, interfaces in ID order)` (`_port_why`, `PORT_ORDER_TEXT`). `Request` holds the interface ID and its type only: nothing in the allocation knows the device at the other end.

**Run.** A blank project (`new --template blank`, so `per_connector_group`); `import-pinout` of OBC1 with one connector J1 whose fixed pins are `TTC1_TX+ TTC1_TX- TTC1_RX+ TTC1_RX- TTC2_TX+ TTC2_TX- TTC2_RX+ TTC2_RX-` (pins 1 to 8); TTC1 and TTC2 each with one connector of the bare names `TX+ TX- RX+ RX-`; two RS-422 interfaces through the core (no command adds an interface), first OBC1 to TTC2 (IF-001, named `RS-422 OBC1 to TTC2`), then OBC1 to TTC1 (IF-002). The import says `OBC1-J01: Ethernet or RS-422 ports: TTC1 (pins 1-4), TTC2 (5-8)`. `generate` says `2 interfaces and 8 wires checked: 0 error(s)`, and the saved pins are:

```
1 TTC1_TX+ IF-001        5 TTC2_TX+ IF-002
2 TTC1_TX- IF-001        6 TTC2_TX- IF-002
3 TTC1_RX+ IF-001        7 TTC2_RX+ IF-002
4 TTC1_RX- IF-001        8 TTC2_RX- IF-002
```

The interface to TTC2 has the pins named for TTC1. `explain DIR OBC1-J01.1` gives the step *Port of the pin: TTC1_TX+ is the TX+ of port TTC1 of OBC1-J01; the pins of one port go to one interface (ports in name order, interfaces in ID order)*. `drc` lists 5 warnings (`part-unapproved`) and 4 notes, none about it; `verify` says `2 interfaces and 8 wires checked: 0 error(s)`. After `export`, `system/box_pinouts.csv` has the row `OBC1-J01,box,,EX-MICROD-25-F,1,TTC1_TX+,IF-001,W001-001,no`: a reader who knows that IF-001 goes to TTC2 can see it; the tool does not say it.

### 2.2 How Generate names what it makes

Generate names no port: a port is read from the pin names a person or an import gave. It names the interfaces' wires by `naming.wire` (`W001-001`), the harnesses by `naming.harness` (`W001`), the cable connectors by `naming.cable_connector` (`W001-P1`); a wire's signal is the type's signal names of its two ends (`TX+/RX+`, the crossing of TX to RX). An interface added in the editor gets the next free ID (`edit.next_interface_id`, `IF-001`) and the name `<type> <device> to <device>` (`RS-422 OBC1 to TTC2`). `import-pinout` and `import-netlist` name a device connector `<device>-J<nn>` from its reference (`J1` gives `OBC1-J01`) unless `--connector` or the symbol field `HarnessConnector` says otherwise.

### 2.3 The pairing of a connection

`links.propose_pairs` (D-173, `propose_pairs_between`) pairs the free pins of two device connectors by signal name only, case ignored: first counterparts (a word of the transmit family meets its receive word, the rest of the two names equal, from `naming.signal_counterparts` or `counterparts.DEFAULT_COUNTERPARTS`), then equal names; never two transmit names or two receive names; a direction set on a pin decides first. `Counterparts.are_counterparts` lets **a prefix be missing on one side** (`UART_TX` meets `RX`). The review of links (`check_links`, `_check_link`) words `link_signal_mismatch`, `link_pin_unpaired` and the others from the same name relation. `tests/test_links_same_as_181.py` compares both with a word-for-word copy of the 1.8.1 module.

**Run** (`import-pinout` of OBC1 with J1 = `TTC1_TX TTC1_RX TTC1_PPS TTC2_TX TTC2_RX TTC2_PPS`, not fixed, and TTC1 and TTC2 each with J1 = `TX RX PPS`; a script calls `propose_pairs` for both links):

```
OBC1-J01 <-> TTC1-J01: TTC1_TX=RX, TTC1_RX=TX | unpaired TTC1_PPS, TTC2_TX, TTC2_RX, TTC2_PPS | PPS
OBC1-J01 <-> TTC2-J01: TTC1_TX=RX, TTC1_RX=TX | unpaired TTC1_PPS, TTC2_TX, TTC2_RX, TTC2_PPS | PPS
```

So the proposal for TTC2 pairs the TTC1 lines (the first pins in reading order win), and an equal name with a prefix (`TTC1_PPS`, `PPS`) is never paired. With a prefix on both sides (`TTC1_TX` and `OBC1_RX` on TTC1) nothing is paired. A link already made to TTC1 takes its pins out of the next proposal, so the order in which a person makes the links decides the result.

### 2.4 Where signal names come from

- **Device pins:** `import-pinout` (the *Signal* column, else *Function*; a *Port* column composes `PORT_SIGNAL`, `ports.compose`), `import-netlist` (the cleaned net name, or the symbol's pin name with `--pin-function`, through `--signal-map`), the Devices tab, a device library file (`import-devices`, `add-device`, `update-device`) and a subsystem file (`import-subsystem`), which carry the pins as saved. Generate writes the type's signal names onto the pins it allocates on a connector without a fixed pinout.
- **Interface types:** `logical/interface_types.json`; the 17 starter types use `TX+ TX- RX+ RX-` (RS-422, Ethernet), `CANH CANL`, `SIG RTN`, `PWR RTN`, `DIN+ … SOUT-` (SpaceWire) and others, all marked as example data.
- **The table of counterpart words:** `naming.signal_counterparts` (1.9.0); the endings of a pair: `naming.pair_suffixes` (4.2.0). Neither renames a pin.

### 2.5 The importers

| Command | Reads | Names |
|---|---|---|
| `import-pinout DIR FILE --device D` | CSV or XLSX, one row per pin; headings by name (Connector, Pin, Signal, Mode, Port, Direction, Level, Source/ICD, Source version, Source link, Pin row …), `--column FIELD=HEADING` | as written; a *Port* column is composed in; a signal that no type has, in any port, is listed (*Signals that match no interface type (nothing can connect to them until a type has them)*) |
| `import-netlist DIR FILE --device D` | a KiCad netlist (S-expression or XML) | the cleaned net name, `--pin-function` the pin name; `--signal-map NAME=SIGNAL` (repeatable) or a CSV (*net, signal*, a heading row `net`, `name`, `kicad`, `from` or `net name` skipped) or a JSON object file: `mapping.get(raw, raw)`, **whole names only**; the unknown names are listed (*map them with --signal-map*) |
| `import-devices`, `add-device`, `update-device` | a device library file or folder (D-165, D-240) | as saved; a taken ID is renamed (`TTC1` to the next free one), the pins are not |
| `import-subsystem` | a subsystem library file (D-175) | as saved, with the links between its devices |

The template `signal-map.csv` (`templates FOLDER`) holds `CAN_H,CANH`, `TXP,TX+`, `TXN,TX-`, `RXP,RX+`, `RXN,RX-`. **Run** on `first-steps` with the template netlist `wheel-connectors.net`, its nets renamed to `/TTC1_TXP`, `/TTC1_TXN`, `/TTC1_RXP`, `/TTC1_RXN`: with and without `--signal-map signal-map.csv` the import prints the same list:

```
Signals that match no interface type (map them with --signal-map, or ignore if they are not interfaces):
  TTC1_RXN: RW1-J02 pin 4
  TTC1_RXP: RW1-J02 pin 3
  TTC1_TXN: RW1-J02 pin 2
  TTC1_TXP: RW1-J02 pin 1
```

The map knows `TXP` but not `TTC1_TXP`, and `docs/KICAD.md` warns not to map a port away (`RS422_2_TX+=TX+`). `import-pinout` has no map at all: the same names from a spreadsheet give `Signals that match no interface type (nothing can connect to them until a type has them): TTC1_PPS, TTC1_RXN …`. The map is not kept in the project; `docs/KICAD.md` lists *the signal-name mapping (today: optional `--signal-map`)* among its open owner questions. No importer reads an ICD's README or any free text.

### 2.6 Where a setting can live: tried with 4.3.0

On a copy of `flatsat` (`new --template flatsat`):

- **New keys in `config/naming.json`** (`"far_device_names": true`, `"signal_map": [["TXP", "TX+"]]`): `validate` reports nothing new (*0 error(s), 0 warning(s)*) and `settings DIR --set naming.harness="W{n:03d}"` writes the file again with both keys kept. `settings DIR --set naming.far_device_names=true` is refused by 4.3.0 with exit 2: *'naming.far_device_names=true' is not FILE.KEY=VALUE of a setting (see `settings`)*.
- **A new file `config/names.json`:** `ERROR quarantined: A configuration could not be loaded and was set aside: 'names' is not a known configuration name`.
- **A new key of `config/model.json`** (`"port_choice": "far_device"`): `ERROR config_invalid: config/model.json: port_choice is not a setting of the model`, which blocks every release.

So both values are keys of `config/naming.json`, as `signal_counterparts`, `pair_suffixes` and `review_checklist` are. Every config file is in the model hash, so a project that sets a key gets another model hash on its written files; `generation_status.input_hash` reads `naming.json` except the keys of `NOT_READ_BY_GENERATION`.

### 2.7 *Choose port…* and *Unassign* today

The way to put IF-001 of section 2.1 on port TTC2 today is *Choose port…* in the Inspector (`devices.ops_assign_port`, which locks the port's pins). It refuses a port that another interface holds: `Pin 5 carries IF-002; unassign it first.` The Devices tab's *Unassign from interface* (`devices.ops_unassign_pins`) then frees pins 5 to 8, but it also clears their signal names: after it the pins are `('5', None, None, False, True)` … (signal none, still fixed), and *Choose port…* says `OBC1-J01 has no RS-422 port TTC2.` A fixed pin's name comes from the device's design; clearing it loses the port. The only way that works today is to add the interfaces in the order of their port names, or to lock each port before the first Generate. Part E fixes *Unassign*.

### 2.8 What the examples hold

Counted with a throw-away script on the five examples and the three fixture projects:

| Project | Devices | Device connectors (fixed pinout) | Named ports | Pin names that name a device | Links | `naming.json` keys |
|---|---|---|---|---|---|---|
| `blank` | 0 | 0 | 0 | 0 | 0 | the four patterns |
| `first-steps` | 3 | 9 (0) | 0 | 0 | 0 | the four patterns |
| `minimal-satellite` | 7 | 37 (0) | 0 | 0 | 0 | the four patterns |
| `small-satellite` | 14 | 75 (0) | 0 | 0 | 0 | the four patterns |
| `flatsat` | 23 | 109 (0) | 0 | 0 of 206 signal pins | 0 | the four patterns |
| fixtures `mini3`, `sat15`, `custom_device` | 3, 14, 3 | 8, 75, 18 (0, 0, 2) | 0 | 0 | 0 | the four patterns |

No example or fixture has a named port, a pin named after a device, a link, or a key of E4. So with either setting on, nothing of them changes; and with the settings off, nothing changes by construction (section 9). `small-satellite` has the devices `OBC1` and `OBC1-R` (and `PCDU1`, `PCDU1-R`): an ID can start with another ID and a separator, which section 3.1 handles.

## 3. Part A: the port named after the far device

### 3.1 Which names name a device

One function, **`core/device_names.py`** `named_device(name, unit_ids) -> DeviceReading | None` (pure, no I/O), used by parts A and B, with an independent copy in the verifier (`core/verify.py`, as the port reading has one):

- A name **names device D** when it is `D<sep>rest` or `rest<sep>D`, with D an ID of a device of the project, sep one of `_ . -` (the separators of ports) and rest not empty. A **port name** also names D when it is D itself (port `TTC1`).
- The ID is compared exactly, with case, as port names and IDs are (N2).
- When several IDs fit, **the longest wins**: `OBC1-R_TX` names `OBC1-R`, not `OBC1` (whose reading `OBC1` + `-` + `R_TX` is part of it). When a prefix and a suffix name two different devices (`TTC1_TX_TTC2`), the name names none, and `DeviceReading` carries the note `TTC1_TX_TTC2 can be read as a name of TTC1 or of TTC2, so it names neither. Rename the pin.`
- The result is the device and the rest of the name (`TTC2_TX` gives `TTC2` and `TX`).

**The far device of an interface at a connector** (`device_names.far_device(project, interface, connector_id)`): the device of the interface's other endpoint; none when both endpoints are on one device.

**Ports of a device.** A usable named port of the type belongs to device F when its name names F: `TTC1` itself, or `TTC1_TM` and `TTC1_TC` (pins `TTC1_TM_TX+` …), so a device with two interfaces of one type has two ports (N4). A port whose name names no device (`RS422_2`) belongs to no device.

### 3.2 The steps of the allocation

`PinRules` gets `far_devices: bool` (`naming.far_device_names`, from `engine.pin_rules`), and `Request` gets `far: str = ""` (filled by `engine._allocate_pins` and by `edit._dry_run` from `far_device`). With `far_devices` false, `_allocate_fixed` runs the four steps of section 2.1 and nothing else (the code path of 4.3.0). With it true:

0. *(new, after step 1, before step 2)* Each interface with no locked pin, in the ranked order, whose far device F has usable ports here takes the first free port of F in natural order (`TTC1` before `TTC1_TC` before `TTC1_TM`). All or nothing, as every step.
1. Locked pins: unchanged; a person's lock wins over every name.
2. The port held before: taken only when it names no device other than F (an interface with no far device keeps it as today).
3. The exact names: unchanged (a bare name names no device).
4. The first free complete named port in natural order, **leaving out, for an interface with a far device F, every port that names a device other than F**. When nothing is left, the interface fails with the error of 3.3. An interface with no far device sees every port, as today.

Step 0 runs for every interface before step 2, so a project that turns the setting on gets its ports by device at the next Generate, also where an interface held another device's port before. Turning it off again leaves the ports where they are (step 2 keeps them), as a change of `model.pin_fit_strategy` does not move pins either.

**On the run of 2.1** the setting gives IF-001 (to TTC2) pins 5 to 8 and IF-002 (to TTC1) pins 1 to 4, whatever the order of the IDs.

### 3.3 The texts

The reasons of the pins are kept in `generated/generation.json` and the verifier's errors reach the DRC files, so their words say *unit* (CLAUDE.md, *Conventions*: the files say *unit*); the screens say *device*.

- **Reason of a pin** (step 0, and step 2 when the port names F): `pin-allocation: TX+ of IF-001 uses pin 5, the TX+ of port TTC2 of OBC1-J01; the port named after unit TTC2 at the other end (naming.far_device_names)`. The same words on a second Generate, so a second plan is empty (REQ-GEN-01).
- **Error** (`pin_allocation`, step 4 with nothing left): `IF-003: OBC1-J01 has a fixed pinout and no free pin named TX+, TX-, RX+, RX-, and no free complete RS-422 port for unit TTC3 (port TTC1 is named after unit TTC1; port TTC2 is named after unit TTC2).` and, when the device's own port is taken: `… (port TTC1 is used by IF-002).`
- **The generation record** gets one note while the setting is on, as a non-default `model.pin_fit_strategy` does: `naming:far_device_names` = `on: a port named after the unit at the other end first`. None while it is off.
- **`explain DIR OBC1-J01.5`**: the step *Port of the pin* says `TTC2_TX+ is the TX+ of port TTC2 of OBC1-J01; the port named after TTC2, the device at the other end of IF-001, comes first (naming.far_device_names), then ports in name order, interfaces in ID order`, and the inputs get `Signal names name the far device = yes [config/naming.json: far_device_names]`; both only while the setting is on (`derive_layout.py`).

### 3.4 The verifier

`core/verify.py` gets its own copy of 3.1 (`_named_device`, no import of `core/device_names.py`; `tests/test_device_names.py` compares the two by Hypothesis) and, while the setting is on, the check **`port_far_device`** for each interface at each device connector with named ports:

- an interface whose pins are in a port that names another device, **not locked and not frozen**: an **error**, `Interface IF-001 goes to unit TTC2 but uses port TTC1 of OBC1-J01, which is named after unit TTC1 (naming.far_device_names). Regenerate, or choose the port of TTC2.` A 4.4.0 Generate never makes this; it shows pins a 4.3.x tool placed, or pins edited by hand. As a verifier error it reaches the DRC as `verify-mismatch` with the fix *Regenerate harnesses*, and the release gate blocks the harness.
- the same with **locked pins** (a person's *Choose port…*) or in a **released** harness: a **warning** with the same first sentence and `It is kept because a person locked the pins.` or `It is kept because harness W001 is released; a new version takes the port of TTC2.` Warnings of the verifier do not reach the DRC report (`drc._verifier_findings` takes errors only), so the written files of such a project do not change for it; `verify` and the editor's Problems show it.

### 3.5 The editor's dry run and *Choose port…*

- `edit._dry_run`, `connector_room`, `free_ports`, `choose_connector` and `shared_connectors` pass the far device of the interface being placed (`connector_room(..., far_unit="")`; `ops_add_interface`, `ops_complete_chain`, `ops_set_endpoint_connector` and `checks._assign_connectors` know it), so the room the editor shows is the room Generate finds (D-237). A connector whose free ports all name other devices has no room: `OBC1-J01 cannot take another RS-422: its free RS-422 ports TTC1 and TTC2 are named after other devices.` In Guided mode the choice then goes on to the next connector.
- *Choose port…* (`gui/panels.py`, the list of `edit.free_ports`) lists the far device's ports first and marks the others: `TTC1 (named after TTC1)`. Choosing one is allowed and locks the pins, as today; the Inspector then shows the warning of 3.4 under the end.
- Strings in a block *4.4.0 E4* at the end of `gui/strings.py`.

### 3.6 What changes in written files

Nothing for a project with the setting off (section 9). For a project with it on and named ports whose names name devices: the pins of the device connectors (`physical/connectors/…`, the pin's `interface_id`), the generation record, and so every output that shows a pin's interface (`system/box_pinouts.csv`, the mating matrix, the wire lists, the harness plans). That is the purpose of the setting.

## 4. Part B: pairing that reads the far device's name

### 4.1 The proposal

With `naming.far_device_names` on, `propose_pairs_between(project, a, b)`, for two device connectors of the devices X and Y, reads each free pin's name with `named_device` before it pairs:

| The pin's name names | On X's connector | Pairing |
|---|---|---|
| no device | `PPS` | its whole name, as today |
| Y, the other device | `TTC2_TX` (Y = TTC2) | the rest of the name (`TX`) |
| X, its own device | `OBC1_TX` on OBC1 | its whole name, as today (N10) |
| a third device | `TTC1_TX` in a link to TTC2 | not offered; a note |

and on Y's connector the same with X and Y swapped. Then the pairing runs as today on the names so read: counterparts first, equal names, never transmit to transmit, directions first. The proposal's pins keep their names; only the comparison reads the rest. With the setting off, `propose_pairs_between` is the function of 4.3.0.

**Stated as written above and run with the tool's own `propose_pairs_between` on the names so read** (a throw-away script, not the tool's code), the run of 2.3 gives:

```
OBC1-J01 <-> TTC1-J01: TTC1_TX=RX, TTC1_RX=TX, TTC1_PPS=PPS | left out: TTC2_TX, TTC2_RX, TTC2_PPS (name TTC2)
OBC1-J01 <-> TTC2-J01: TTC2_TX=RX, TTC2_RX=TX, TTC2_PPS=PPS | left out: TTC1_TX, TTC1_RX, TTC1_PPS (name TTC1)
```

and with `OBC1_RX`, `OBC1_TX` on the transceivers: `TTC1_TX=OBC1_RX, TTC1_RX=OBC1_TX` in the link to TTC1 and `TTC2_TX=OBC1_RX, TTC2_RX=OBC1_TX` in the link to TTC2, where 4.3.0 pairs nothing. The order in which the links are made no longer matters. `best_connectors` and `plan_quick_link` count the pairs of this proposal, so a one-click connection between OBC1 and TTC2 starts with the connector that has the TTC2 pins.

### 4.2 The link review

`check_links` reads the names the same way while the setting is on (`_Review` carries the device IDs), so that a pair the proposal made is not reported:

- `link_signal_mismatch` compares the names so read (`TTC2_PPS` and `PPS` match in a link to TTC2), and gets one more case: a pair whose pin names a third device: `Link L1 pairs pin 1 of OBC1-J01 with pin 1 of TTC2-J01, but TTC1_TX names unit TTC1, not TTC2. Pair it in a link to TTC1, or rename the pin.` (warning, as the other cases of the code).
- `link_pin_unpaired` of a pin that names a third device, and that no link pairs: `Pin 1 of OBC1-J01 is named TTC1_TX (unit TTC1) but no link pairs it. Link OBC1-J01 to a connector of TTC1, or set its role to Spare if it is not used.` (in place of *Pair it with a pin of TTC2-J01*, which would point to the wrong device). A pin that a link to TTC1 pairs is not reported, as today.

### 4.3 The notes of the proposal

One note per connector and third device, in the window *Link connectors* (`gui/link_dialog.py` shows `Proposal.notes` already): `Pins 1, 2 and 3 of OBC1-J01 name device TTC1, so they are not offered in a link to TTC2 (Settings > Project: Signal names name the far device).` A name that names no device for a reason of 3.1 gets its note (`… can be read as a name of TTC1 or of TTC2, so it names neither …`).

### 4.4 Written files

The proposal writes nothing. A link a person confirms is saved as today (`logical/links.json`). The review's texts reach `system/drc_findings.csv` and the DRC report through the rules `link-signal-mismatch` and `link-unpaired`, only in a project with the setting on and a link whose pins name a device.

## 5. Part C: the project's signal map

### 5.1 Where it lives and its shape

```
config/naming.json
  "signal_map": {"TXP": "TX+", "TXN": "TX-", "RXP": "RX+", "RXN": "RX-", "CAN_H": "CANH"}
```

A table (an object) of a **team name** to a **signal name**, the form of a JSON file of `import-netlist --signal-map`. Each name is a valid signal name (`Name`: 1 to 200 characters); no name maps to itself; no signal name is also a team name (no chains); at most 1000 entries. Not set, `null` or `{}`: no map. The check is `configcheck.validate_signal_map` (code `config_invalid`: *config/naming.json: signal_map must be a table of a team's signal name to the signal name of an interface type, each 1 to 200 characters, no name mapped to itself and no signal name that is also a team name*). It does not ask that a signal name is one of the project's types: types change, and the import lists the names no type has, as today.

### 5.2 Where it is applied

Only by the two importers that read a device's pins from outside, before anything else reads the name (N6):

- **`import-netlist`:** the name of each pin (net name or, with `--pin-function`, pin name) is looked up in the command's `--signal-map` first, **whole names only, as today**; when it is not there, in the project's map by **`signal_map.apply(name, table)`**: the whole name, else a name that reads as `P<sep>k` or `k<sep>P` with k a team name (the rule of ports, `ports.read_signal` against the map's keys): `TTC1_TXP` gives `TTC1_TX+`, `TXP.TTC1` gives `TX+.TTC1`, the port and the separator kept (N7). A name that reads in two ways (`TXP_RXN`) is not renamed, and a warning says so.
- **`import-pinout`:** the same function on the *Signal* (or *Function*) cell, before the *Port* column is composed in: signal `TXP` with port `TTC1` gives `TTC1_TX+`.

Nothing else reads the map: not Generate (it is in `NOT_READ_BY_GENERATION`, so a changed map does not make the harness plans out of date), not the rules, not the verifier, not the link pairing, not the library imports (N11). A file imported again after the map changed gives the new names, which the import's preview shows.

### 5.3 The texts and the import record

- The echo of both commands, after the list of rows: `Renamed by the project's signal map (config/naming.json signal_map): 4 signal(s)` and one line each, `  TTC1_TXP -> TTC1_TX+: OBC1-J01 pin 1`; a name that reads in two ways: `warning: TXP_RXN on OBC1-J01 pin 9 can be read as TXP or RXN of the signal map, so it is not renamed.`
- `--json` of both commands gets the key `renamed_signals` (a list of `{"connector", "pin", "read", "stored"}`, empty without a map), in `cli/jsonout.SHAPES` and so in `docs/CLI.md`.
- The import record (`imports/records.json`, outside the model hash and every output) lists each rename as a conversion (`import_record.Conversion`: field `signal`, read `TTC1_TXP`, unit `signal map`, stored `TTC1_TX+`), so `imports DIR` says later what a pin was called in the file.
- The import wizard's preview shows the same lines (`gui/import_kinds.py` reads the report); its netlist page keeps its own box of pairs, which acts as `--signal-map`.

### 5.4 How a project sets it

- **`config DIR --signal-map FILE`** reads the file the way `import-netlist --signal-map FILE` reads it today (`cli/data._signal_map_file`, moved to `core/signal_map.read_file`: a CSV of two columns with an optional heading row, or a JSON object), refuses a table the check of 5.1 refuses with its text, and prints `Signal map: 5 name(s) in config/naming.json.` `--signal-map none` takes the key out. Then the hand-over list of `config`, whose exit code it keeps, as `--review-checklist` does. The template `signal-map.csv` is such a file.
- **`settings DIR --set naming.signal_map='{"TXP": "TX+"}'`** takes it as JSON, as every setting.
- **The editor:** *Settings > Project* gets a section *Signal map*: a text box with one `TEAM NAME = SIGNAL` per line (`import_kinds.parse_pairs`, as the netlist page reads its box), *Take the names of a file…* and *Save*, one undo step (`configcheck.plan_set_signal_map`).

### 5.5 What changes in written files

Nothing until a project sets a map, and then only `config/naming.json` and, through the config, the model hash of the written files. The pins an import writes are the project's data, as with `--signal-map` today.

## 6. Part D: ICDs, and what waits for an example

The plan's E4 row says *an importer for the team's ICD format once an example is given*, and owner question 9 of the plan asks for an example ICD with its README. **None has been given.** So 4.4.0 builds no ICD importer and invents no ICD format: a guessed format would be a format of this tool's making that no team uses, and its columns, its words and its README layout would be invented content (D-11).

What a team can do with 4.4.0:

- **A pinout table is the generic form.** `import-pinout` reads one row per pin with the columns of `docs/IMPORTS.md` (connector, pin, signal or function, mode, port, direction, level, contact size, termination, the source and version of the ICD, its link, the pin row), from CSV or XLSX, with `--column FIELD=HEADING` for other headings; the users' `CON_…` sheets of the harness plan are read in their own words since 3.0.0. An ICD that is, or contains, such a table imports today.
- **The team's names** come through the map of part C.
- **The README** of an ICD is not read; its facts (directions, levels, the ICD's version) go into the table's columns.

What waits for the example: which file types the team's ICDs are (spreadsheet, PDF, text), which headings and words they use, what the README holds beyond the table and whether any of it has a field in format 4, and whether a saved column map per team (`--column` once for the project) is worth a setting. Then a design names the importer, with the example's facts as its test data, anonymised (device names such as `TTC1`, a company such as `Example Ltd`). Until then the page `docs/IMPORTS.md` gets a short section *Reading an ICD* that says the above.

## 7. Part E: *Unassign from interface* keeps the name of a fixed pin

`devices.ops_unassign_pins` sets `signal=None` on every pin it frees (section 2.7). For a pin with `fixed` set, the signal is the device's own name (from the ICD, the import or the Devices tab), not the interface's: the fix keeps the signal of a fixed pin and clears only `interface_id` and `locked`; a pin that is not fixed is freed as today. The Devices tab's command keeps its words. With it, the swap of 2.7 works by hand: *Unassign* pins 5 to 8, *Choose port…* TTC2 for IF-001, Generate. A regression test (`tests/test_unassign_fixed.py`) holds it. No example or fixture unassigns a pin, so no written file changes.

## 8. Settings, checks, assumptions

### 8.1 Two settings (`core/settings.py`)

- `Setting("naming", "far_device_names", "Signal names name the far device", "", "flag", False, "A port or a signal name that names a device of the project (TTC1_TX+, TTC1_PPS) belongs to the interface or the connection to that device: Generate gives an interface the port named after the device at its other end, and the pairing of a connection reads the other device's name off a pin name.", "pin allocation on a fixed pinout, pairing of a connection, review of connections", _PROJECT, "true or false", assumption="A-FAR-DEVICE")`. The default is the behaviour of 4.3.0.
- `Setting("naming", "signal_map", "The team's signal names", "", "table", None, "A team's own signal name and the signal name of an interface type it stands for (TXP for TX+): import-pinout and import-netlist write the type's name, also inside a port (TTC1_TXP becomes TTC1_TX+).", "import-pinout, import-netlist", _PROJECT, "a table of names to signal names, each 1 to 200 characters, no name mapped to itself, no signal name that is also a team name, at most 1000")`. No default: the tool ships no name (D-11).

### 8.2 `configcheck`, `generation_status`, `config`

- `validate_far_device_names` (true or false) and `validate_signal_map` (5.1), both called from `validate`, code `config_invalid`.
- `generation_status.NOT_READ_BY_GENERATION["naming"]` gets `signal_map`; `far_device_names` stays an input of generation, so turning it on makes the harness plans out of date until the next Generate.
- `config DIR --far-device-names on|off` (as `--distinct-roles`): `on` writes `true`, `off` takes the key out, so a project that tried it and went back has the bytes it had. `config DIR --signal-map FILE|none` (5.4). Neither prints anything in a project that sets neither, so the text of `config DIR` stays byte for byte.

### 8.3 The assumption `A-FAR-DEVICE` (`core/assumptions.py`)

*A pin name that names a device belongs to that device's interface or connection.* `With naming.far_device_names on, a name that starts with a device ID and a separator (_ . -), or ends with a separator and a device ID, names that device; the longest ID wins, and a name that names two devices names neither. Generate gives an interface the port named after the device at its other end first and never a port named after another device; the pairing of a connection reads the other device's name off and leaves out the pins that name a third device. Off (the default): names are read as in 4.3.0.` Kind *setting*; where: `core/device_names.py`, `core/generate/pins.py (_allocate_fixed)`, `core/links.py (propose_pairs_between, check_links)`. `A-PORTS` keeps its text. Assumptions are in no written file of `export` (they show in `settings`, the Assumptions window and `explain`).

## 9. What changes in the written files, and the guards

| Written file | Change | Which projects | Guard |
|---|---|---|---|
| every file of `export`, the harness plans | nothing | a project that sets neither key: every example, template and fixture | `python -m tools.output_hashes --check docs/ui/OUTPUT_HASHES_BASELINE.json` *identical*, `python -m tools.numbers_snapshot --check`, the goldens of `tests/fixtures/outputs/` and `tests/fixtures/drc/` unchanged |
| the device connectors, `generated/generation.json`, and the outputs that show a pin's interface | the ports by far device (3.6), the note of 3.3 | a project with `far_device_names` on and named ports that name devices | `tests/test_ports_far_device.py`, `tests/test_e2e_440.py` |
| `system/drc_findings.csv`, the DRC report, the *DRC findings* sheet | `verify-mismatch` of `port_far_device` (an error only); the new texts of `link-signal-mismatch` and `link-unpaired` | a project with the setting on and such a port or link | the same tests |
| `config/naming.json` | the keys | a project that sets them | none: no example sets one |
| `export-data`'s settings table, `settings DIR` | two rows more, the values in force (`false`, not set) | every project | not a file of `export`; listed in the release notes, as the settings of 4.2.0 and 4.3.0 were |

**Byte-identical by design, and which guard shows it.** Every new code path is behind one of two tests: `rules.far_devices` (false unless `naming.far_device_names` is `true`) and an empty map. (1) Generate: with `far_devices` false, step 0 does not run and steps 2 and 4 see every port, so `_allocate_fixed` is the function of 4.3.0; `tests/test_ports_compat_430.py` compares `allocate` with a word-for-word copy of the 4.3.0 `pins.py` (`tests/reference/pins_430.py`, not to be edited) on random connectors with named ports, bare names, locks and earlier allocations (Hypothesis), as `test_ports_compat_201.py` does for 2.0.1; the generation record gets no note. (2) The verifier's check runs only with the setting on. (3) Pairing and the review: with the setting off no name is read for a device; `tests/test_links_same_as_181.py` stays green, and a new test compares `propose_pairs` and `check_links` with the setting off against the 4.3.0 functions on random connectors. (4) Imports: with no map and no `--signal-map`, `apply` returns every name as it came; `tests/test_kicad.py`, `tests/test_pinout_import.py` and the import-record tests stay as they are, and a test reads the same file into two projects, one with `{}`, byte for byte. (5) `config DIR`: no new line without the keys. (6) The explanations: no new step or input with the setting off (`tests/test_s1_build_layout.py`). So no pull request renews the baseline, the numbers snapshot or a golden; each one runs `output_hashes --check` and `numbers_snapshot --check`, both *identical*.

**The proof of 3.0.0** (`tests/format3_support.py`) needs no step: no build workbook or other written file changes.

## 10. Edge cases found in the code

| Case | Where in the code | What the design does |
|---|---|---|
| **A device ID that starts with another and a separator** (`OBC1` and `OBC1-R` in `small-satellite`; copies `ID-R`, `ID-3`, `copies.copy_ids`) | `ids.ID_RE` allows `_ . -` in an ID | The longest ID wins (3.1): `OBC1-R_TX` names `OBC1-R` |
| **A name that names two devices** (`TTC1_TX_TTC2`) | — | Names neither; a note; Generate and the pairing read it as in 4.3.0 |
| **A port name that is a device ID by chance** (a device `RS422` and ports `RS422_1`, `RS422_2`) | ports are read from names | Both ports name device `RS422`; the setting is opt-in and the assumption says how names are read; the Inspector shows *(named after RS422)* |
| **A device renamed** (`edit.ops_rename_unit`), **imported under a new ID** (`device_library.plan_device_import` renames a taken ID) or **added as a copy** (`add-device --as`) | pins keep their names | A port named after the old ID names no device and is used in name order; the tool renames no pin. The release notes say so |
| **Two interfaces of one type to one device, one port of it** | step 0 | The first by category and ID takes it; the second takes a port that names no device, else fails with the error of 3.3 |
| **An interface with both ends on one device** | `endpoints` | No far device: steps 2 to 4, leaving out no port |
| **A person's lock on another device's port** | step 1 | Kept; the verifier's warning (3.4) |
| **A released harness with a port of another device** | `frozen_interfaces` | Kept; the verifier's warning; a new version takes the device's port |
| **The setting turned on in a generated project** | step 0 before step 2 | The ports move at the next Generate; it says *N changed* and the outputs are out of date (`input_hash` reads the key) |
| **The setting turned off again** | step 2 | The ports stay; `config --far-device-names off` takes the key out |
| **A connector without a fixed pinout** | `allocate` places by groups | Not affected: no names are read |
| **Bare names repeated** (`TX+` on three pins, `pin_port_unknown`) | step 3 | Not affected: a bare name names no device |
| **A 4.3.x tool on a 4.4.0 project** | 2.6 | Keeps both keys; its Generate keeps the ports held before (its step 2) and gives a new interface the first free port in name order, which the 4.4.0 verifier then reports as `port_far_device`; its imports ignore the map; its `settings --set` refuses the keys. The release notes say: update the team together |
| **The pairing between a cable's loose end and a port** | `manual_harness.propose_plug` | Reads names as today (1.2) |
| **Equal names after the reading that both transmit** (`TTC2_TX` on OBC1, `TX` on TTC2) | `_pair_side` | Not paired, with today's note: a person decides (the vendor's point of view) |
| **A pin naming its own device** (`TTC2_TX` on TTC2) | — | Read as a whole name (N10) |
| **A link made before the setting, now with a pin of a third device** | `check_links` | The new `link_signal_mismatch` case of section 4.2 names it |
| **The map and a Port column** | `pinout_import`, `ports.compose` | The cell is mapped first, then the port is composed in |
| **The map and a name that reads in two ways** (`TXP_RXN`) | `ports.read_signal` against the map's keys | Not renamed; a warning |
| **A mapped name too long, or not a signal name** | `Pin.signal` is a `Name` | The row is refused, as a long net name is today (*rename the net or map it*) |
| **A locked pin in a netlist import** | `kicad.plan_netlist_import` | Not changed, as today; the warning names the mapped name |
| **`export-pinout` then `import-pinout` with a map** | the export writes the type's names | No key fits, so nothing is renamed: a file read back changes nothing |
| **The command's `--signal-map` and the project's map name one net** | — | The command's pair wins, as given on the command line |
| **Unassign on a fixed pin** | `devices.ops_unassign_pins` | Part E keeps its signal |
| **A read-only project** (newer format) | `project.read_only` | `config` refuses as for every setting; the editor's controls are off |

## 11. Tests to write

| File | What it holds |
|---|---|
| `tests/test_unassign_fixed.py` (pull request 1) | Unassign keeps the signal of a fixed pin and clears its interface and lock; a free pin as before; the swap of 2.7 by hand, then Generate |
| `tests/test_device_names.py` (pull request 2) | `named_device`: prefix, suffix, a port name equal to an ID, the separators, case, the longest ID (`OBC1`, `OBC1-R`), two devices, an empty rest; `far_device`; Hypothesis against the verifier's copy (pull request 3 adds the copy) |
| `tests/test_signal_map.py` (pull request 2) | The check of 5.1 (accepted and refused tables, the texts); `apply` on whole names, prefix and suffix ports, two readings; `read_file` on the template `signal-map.csv`, a JSON object and a bad file; `config --signal-map FILE`, `none`; `config --far-device-names on`, `off` takes the key out; the map is not an input of generation (`input_hash` unchanged), the flag is; a 4.3.0 project with both keys loads, saves and keeps them |
| `tests/test_ports_far_device.py` (pull request 3) | The run of 2.1 in both ID orders; ports `TTC1_TM`, `TTC1_TC`; two interfaces to one device; the error of 3.3 and its words; a lock on another device's port kept; a released harness; on and off and on again; a second Generate gives an empty plan; the reasons; `connector_room`, `free_ports` and Guided mode; `explain` |
| `tests/test_ports_compat_430.py` and `tests/reference/pins_430.py` (pull request 3) | The setting off: `allocate` equals the 4.3.0 copy on random connectors (Hypothesis) |
| `tests/test_verify_far_device.py` (pull request 3) | `port_far_device`: the error (unlocked), the warnings (locked, released), none with the setting off; the DRC finding `verify-mismatch` and its fix |
| `tests/test_links_far_device.py` (pull request 4) | The two runs of 4.1; the notes; a third device; a pin of its own device; two transmit names; `best_connectors` and `plan_quick_link`; the review's two new texts; with the setting off, `propose_pairs` and `check_links` equal the 4.3.0 results on random connectors |
| `tests/test_import_signal_map.py` (pull request 5) | `import-netlist` and `import-pinout` with the project's map: whole names, ports, the Port column, two readings, the command's map first, a long name refused, a locked pin; the echo, `--json` `renamed_signals`, the import record's conversions; without a map the bytes of 4.3.0 |
| `tests/test_ui_names_ports.py` (pull request 6) | *Settings > Project*: the check box and the signal map section (save, refuse, undo); *Choose port…* lists the far device's port first and marks the others; the Inspector's warning; the link window's notes |
| `tests/test_e2e_440.py` (pull request 7) | One project end to end through the command line: `new --template blank`, `config --signal-map signal-map.csv`, `import-pinout` of OBC1 with `TTC1_TXP` … and `TTC2_TXP` …, the renames in the echo and the record, TTC1 and TTC2, the interfaces (core) in the *wrong* ID order, `generate` with the setting off (the ports of 2.1) and on (`config --far-device-names on`: IF-001 on port TTC2), `verify`, `drc`, `export`, `system/box_pinouts.csv` read back, `explain`, and a connection through the core with its proposal |

The requirements, in `docs/REQUIREMENTS.md` and `compliance/traceability.csv` (`python -m tools.trace`): **REQ-PIN-08** (with `naming.far_device_names` on, an interface on a fixed pinout gets the port named after the device at its other end and never a port named after another device; the verifier checks it), **REQ-PIN-09** (with the setting on, the pairing proposal and the link review read the other device's name off a pin name and leave out the pins of a third device), **REQ-IMPORT-02** (the project's signal map renames a team's names at `import-pinout` and `import-netlist`, also inside a port, and the import says and records each rename), **REQ-GUI-32** (*Settings > Project* sets both).

## 12. Documents to update

- `CHANGELOG.md`, `## Unreleased`: one entry per pull request, each saying that a project without the keys keeps its bytes.
- `docs/releases/4.4.0.md`: the three parts and the fix; *Which written files change* (section 9); *For scripts*: `config` has `--far-device-names` and `--signal-map`, the imports' `--json` has `renamed_signals`, `settings DIR` and `export-data` list two settings more, the verifier has `port_far_device`; *Upgrade*: a 4.3.x tool keeps the keys and ignores them, so a team updates together; *Known limits* (section 18); *ICDs* (section 6).
- `docs/CONFIG.md` (the two keys, with examples), `docs/IMPORTS.md` (the map on both imports; the new section *Reading an ICD*), `docs/KICAD.md` (the project's map beside `--signal-map`, the port-aware reading; its open question 2 answered), `docs/CLI.md` (`python -m tools.gen_cli_docs`), `docs/models/pin-allocation.md` (step 0 and the changed steps 2 and 4), `docs/REQUIREMENTS.md`.
- `docs/developer/agent/core.md` (a paragraph under *Connections* and one under *Generation layout*: `device_names.py`, `signal_map.py`, the flag in `PinRules`, the verifier's copy and its test), `docs/developer/agent/gui.md` (the two sections of *Settings > Project*).
- User manual: `define-a-device.md` and `generate-harnesses.md` (ports named after a device), `connect-two-connectors.md` (the proposal that reads device names), `import-kicad-pinouts.md` and `import-data.md` (the map), `naming-and-title-block.md` (the two settings), `see-what-the-tool-assumes.md` (`A-FAR-DEVICE`); the in-app guide (`python -m tools.build_guide`).
- `resources/examples/templates/README.md` (`signal-map.csv` also for `config --signal-map`), `docs/GLOSSARY.md` (*Far device*, *Signal map*).
- `docs/ait/ELEC_FEEDBACK_PLAN.md`: E4 built, and the corrections of section 17.
- Not changed: `docs/FILE_FORMAT.md` (no key of a project file outside `config/`), `docs/RULES.md` (no rule), `docs/OUTPUTS.md` (no new output), the templates' files.

## 13. What does not change

The project format and `SCHEMA_VERSION` (4); `system/export.json` (`format_version` 2); every written file of a project that sets neither key; the 43 rules and the *Rules run* count; the text of every command for such a project, but `settings` and `export-data`, which list every setting; the keys of `--json` of every command but the two imports (`renamed_signals`); the scripting interface (`API_VERSION` 1, `tests/fixtures/api_snapshot.json`); the reading of ports (`core/ports.py`); `A-PORTS`; `signal_counterparts` and `pair_suffixes`; `import-netlist --signal-map` (whole names, as today); the library imports; the template files.

## 14. Proposed decision D-262

> | D-262 | **Release 4.4.0 is a minor release with names and ports (milestone E4 of `docs/ait/ELEC_FEEDBACK_PLAN.md`); no format change** (D-237, D-254, D-260; design `docs/ait/DESIGN_4.4_NAMES_PORTS.md`). (1) The setting `naming.far_device_names` (a key of `config/naming.json`, off by default): a pin or port name that starts with a device ID and a separator (`_ . -`), or ends with them, names that device (the longest ID wins; a name of two devices names neither; a port name equal to an ID names it). With it on, Generate gives an interface on a fixed pinout the first free port named after the device at its other end, before the port it held before and before the first free port in name order, and never a port named after another device (an error when none is left); the editor's dry run, *Choose port…*, `explain` and the verifier (`port_far_device`: an error for unlocked pins, a warning for locked or released ones) follow it; and the pairing proposal of a connection reads the other device's name off a pin name and leaves out the pins that name a third device, with a note, and the link review reads names the same way. (2) The project's signal map, the key `signal_map` of `config/naming.json` (empty by default; the tool ships no name, D-11): `import-pinout` and `import-netlist` write the type's name for a team's name, also inside a port (`TTC1_TXP` to `TTC1_TX+`), say and record each rename; `import-netlist --signal-map` keeps its meaning and wins per name; `config --signal-map FILE\|none`, `config --far-device-names on\|off`, *Settings > Project*. Not read by Generate, the rules, the verifier, the pairing or the library imports. (3) No ICD importer: the team's format waits for an example (plan question 9); `import-pinout`'s table is the generic form. (4) *Unassign from interface* keeps the signal of a fixed pin. **Written files:** none change for a project that sets neither key; the output-hash baseline, the numbers snapshot and the goldens stay as they are. | The owner's answers to N1 to N12. The engineer's feedback of 2026-11-20 (points 10, 11, Cb). |

The release decision of 4.4.0 is a later row (D-263), as D-261 followed D-260.

## 15. Owner questions

Each with our recommendation first. While a question is open, the pull requests follow the recommendation.

1. **N1. One switch, `naming.far_device_names`, for Generate and for the pairing, off by default?** Recommended: yes. Both read one convention of a team's names (a name that names a device belongs to it); two switches would let the generator and the pairing read one pin in two ways. Off keeps every project's bytes; a team turns it on once.
2. **N2. A name names a device by its ID only, exactly and with case, as a prefix or a suffix with `_ . -`, the longest ID winning?** Recommended: yes. Ports are read exactly and with case (D-237), IDs are unique and short; the name of a device (`Transceiver 1`) has spaces and is free text. The longest ID is not a guess: `OBC1-R_TX` contains the reading `OBC1-R`, of which `OBC1` is a part. Revisit if a team names pins after something that is not the device ID.
3. **N3. Generate never gives an interface a port named after another device (an error when nothing else is left), rather than as a last choice?** Recommended: never. A port named after TTC1 given to the interface to TTC2 is the mistake the engineer asked to avoid; an error that names the ports tells the person to add a port or to choose one by hand, which *Choose port…* allows.
4. **N4. Ports whose name starts with the device ID and a separator (`TTC1_TM`, `TTC1_TC`) are that device's ports, taken in name order?** Recommended: yes. A device with two interfaces of one type to one partner needs two ports, and the names say which device; which of the two an interface takes follows the order of today (category, then ID), and *Choose port…* sets it otherwise.
5. **N5. The verifier: an error for an unlocked interface on another device's port, a warning for a locked or released one?** Recommended: yes. Unlocked, it is a Generate of another tool or an edit by hand that *Regenerate* fixes; locked or released, it is a person's choice or a frozen record, which the tool states and does not block.
6. **N6. The signal map acts at import only, not when Generate, the rules or the verifier read names?** Recommended: yes. After the import the project holds the type's names, so every reader of 4.3.0 reads them unchanged and the verifier needs no second copy of a map. A map read everywhere would make every check depend on a config key and two copies of it.
7. **N7. The project's map reads inside a port (`TTC1_TXP` to `TTC1_TX+`), and `import-netlist --signal-map` keeps reading whole names and wins per name?** Recommended: yes. The port carries the device (part A) and must stay; a script that passes `--signal-map` today gets the same pins tomorrow.
8. **N8. No ICD importer in 4.4.0; the team's format and README wait for an example; no generic ICD format of our own?** Recommended: yes (section 6). `import-pinout`'s table is already a documented generic form; a format of our making is one no team uses. We need the example ICD with its README (plan question 9), anonymised, before an importer is designed.
9. **N9. The pairing leaves out the pins that name a third device, with a note, and the link review names a pair whose pin names a third device?** Recommended: yes. They belong to another link; offering them is the mistake of section 2.3. The person can still pair them by hand; the review then says so.
10. **N10. A pin that names its own device (`TTC2_TX` on TTC2) is read as a whole name?** Recommended: yes. Taking a device's own name off would be a second convention; no case of the feedback needs it.
11. **N11. No map on library devices (`import-devices`, `import-subsystem`, `add-device`, `update-device`)?** Recommended: yes. A library holds a device as a team saved it; a map there would change every pin `update-device` compares. A team maps when it imports the device's pinout, before it saves it to the library.
12. **N12. *Unassign from interface* keeps the signal of a fixed pin, in 4.4.0?** Recommended: yes, as pull request 1. It loses data of the device's design today, and it is the step a person needs to swap two ports by hand, with or without the setting.

## 16. Pull requests

Small, each green on its own, each with its `CHANGELOG.md` entry.

| PR | Content | Guards |
|---|---|---|
| 1 | **The fix of *Unassign* on a fixed pin** (part E). `devices.ops_unassign_pins`; `tests/test_unassign_fixed.py` | `output_hashes --check` and `numbers_snapshot --check` *identical* |
| 2 | **Core and settings, no caller.** `core/device_names.py`, `core/signal_map.py` (`apply`, `check`, `read_file`, moved from `cli/data.py`), the two settings, `configcheck` (validate, `plan_set_signal_map`), `NOT_READ_BY_GENERATION`, `config --far-device-names` and `--signal-map`, `A-FAR-DEVICE`; `docs/CONFIG.md`, `docs/CLI.md`; `tests/test_device_names.py`, `test_signal_map.py` | *identical* |
| 3 | **Generate by far device.** `generate/pins.py` (step 0, steps 2 and 4), `engine.py` (`PinRules`, `Request.far`, the note), `edit.py` (the dry run, the room text), `derive_layout.py`, the verifier's copy and `port_far_device`; `tests/test_ports_far_device.py`, `test_ports_compat_430.py` with `tests/reference/pins_430.py`, `test_verify_far_device.py`; `docs/models/pin-allocation.md`; REQ-PIN-08 | *identical*: no example or fixture sets the key |
| 4 | **Pairing and the link review.** `links.py` (`propose_pairs_between`, `_Review`, `_check_link`); `tests/test_links_far_device.py`; REQ-PIN-09 | *identical*; `tests/test_links_same_as_181.py` green |
| 5 | **The map at import.** `pinout_import.py`, `kicad.py`, `import_reports.py`, `cli/data.py` (echo, `--json` `renamed_signals`, `SHAPES`), the wizard's preview; `tests/test_import_signal_map.py`; `docs/IMPORTS.md`, `docs/KICAD.md`, `docs/CLI.md`; REQ-IMPORT-02 | *identical* |
| 6 | **The editor.** *Settings > Project* (the check box `settings-far-device-names`, the section *Signal map*), *Choose port…* and the Inspector's warning, `gui/strings.py`; `tests/test_ui_names_ports.py`; REQ-GUI-32 | *identical*: no written file |
| 7 | **End to end and documents.** `tests/test_e2e_440.py`; the pages of section 12; the guide; `docs/releases/4.4.0.md` | — |
| 8 | **The preparation of 4.4.0**: the version, the changelog section, the decision rows D-262 (as decided, with what was built where it differs) and D-263, the status pages | stamp only (`4.4.0` has five characters, as `4.3.0`) |

Order: 1 and 2 first, in any order; 3, 4 and 5 after 2, in any order; 6 after 3 and 5; 7 after 6; 8 last. **No pull request changes a written file of a project that sets neither key**, so none renews the baseline, the snapshot or a golden, and none needs the slow tests before its merge for that reason. 4.3.0 is tagged (`v4.3.0` on `20bf8f1`), so nothing waits for a tag; a 4.3.x patch is made from the tag.

Why the core comes first with no caller: the reading of 3.1 is used by three callers and copied once in the verifier; pull request 2 fixes its words and its tests before any behaviour depends on it, as 4.1.0, 4.2.0 and 4.3.0 landed their cores.

## 17. Corrections to the plan, and what was found on the way

Checked against the code at 4.3.0 and the runs of section 2.

1. **`TTC1_TX` on the OBC and `RX` on TTC1 are paired.** The plan (*D. Names and automatic connection*) says they are not. They are: a prefix may be missing on one side (`Counterparts.are_counterparts`). The fault is another: the same pins are proposed in a link to **TTC2** (section 2.3, run), and an equal name with a prefix (`TTC1_PPS`, `PPS`) is never paired.
2. **A name map exists, for KiCad only and for whole names.** The plan says *there is no table that maps a team's own names to the type's signal names*. `import-netlist --signal-map` (and the template `signal-map.csv`) is one: per command, whole names only (`TTC1_TXP` is not mapped by `TXP`, run of 2.5), not kept in the project, and `import-pinout` has none. Part C makes it a project setting that both importers read, inside a port too.
3. **Generate's wrong port goes unnoticed.** The plan says Generate *does not match the port name with the name of the far device*. Confirmed by the run of 2.1; also, nothing reports it: `generate` and `verify` give 0 errors and `drc` no finding; only `system/box_pinouts.csv` shows `TTC1_TX+` on IF-001.
4. **The order is by category, then by interface ID.** The plan says *in name order*: ports are taken in natural name order, and the interfaces in the order of their category in `model.pin_allocation_categories`, then by ID.
5. **The settings cannot be a new file of `config/` or keys of `config/model.json`.** Both stop or block a 4.3.x tool (2.6); they are keys of `config/naming.json`.
6. **Found: *Unassign from interface* clears the name of a fixed pin** (2.7), so a port is lost and the swap of two ports by hand fails (`OBC1-J01 has no RS-422 port TTC2.`). Part E fixes it.
7. **No ICD example was given**, so the importer of the E4 row is not designed (section 6).

*Added by pull request 7, after pull requests 1 to 6 were built:* what was built differently from the text above, and what the end-to-end walk found. No fault of pull requests 1 to 6 in the program was found; the walk of `tests/test_e2e_440.py` (sections 2.1, 2.3, 2.5 and 2.7 through the command line, and *Settings > Project*, the Inspector, Generate and *Choose port…* in the editor) gives the results the sections above state.

8. **Step 0 keeps the far device's port held before** (pull request 3). Section 3.2 says step 0 gives the first free port of the far device in natural order. As built, it gives the port of the far device that the interface held before while it is free, and only else the first free one, so a second Generate does not move an interface between two ports of its device (`TTC1_TC`, `TTC1_TM`) when the order of the interfaces changes. `docs/models/pin-allocation.md` states the step as built.
9. **Names in the code** (pull requests 2 to 4). `Request.far` is filled by `engine.request`, not by `engine._allocate_pins`; `PinRules` also carries the device IDs (`units`); the verifier's copy of section 3.1 is `verify.device_naming`, not `_named_device`; the reading of a pin name in a connection is a function of its own, `device_names.link_reading`, used by the proposal and the review. In the pairing, pins whose whole names are equal pair last, as they did in 4.3.0 (`TTC2_PPS` on both ends).
10. **`config --far-device-names on` first says that the harness plans are out of date** when they were current (*Generate reads this setting, so the harness plans are now out of date. …*), then `Signal names name the far device: on (config/naming.json, far_device_names).`, then the hand-over list, whose exit code it keeps, as `--review-checklist` does (section 8.2 does not give the order). A project that sets neither key prints the text of 4.3.0.
11. **`import-netlist` makes no device** (section 11 of this design names it in the walk without saying how the device comes). The command updates or adds the connectors of a device that exists; it has no `--new-device`. The walk makes the transceiver TTC2 with `import-pinout` of a sheet of its four pins without names and lets the netlist, with the team's nets `/TXP` …, name them (`J1: OK updated TTC2-J01 (4 signal pin(s))`, four renames).
12. **Found by pull request 7 in the documents: two pages still said that the readers come later.** `docs/CONFIG.md`, written with pull request 2, said for both keys that Generate, the pairing and the imports *read names as in 4.3.0* in this version; pull requests 3 to 5 did not change those sentences. Pull request 7 replaced them, and wrote the section *Reading an ICD* of `docs/IMPORTS.md` that section 6 asks for and that no earlier pull request wrote.
13. **Found on the way, not changed (it is not part of E4, and 4.3.0 does the same): *Add interface* can choose a fixed connector without the type's names.** A device whose first connector has a fixed pinout of other names (`PWR`, `RTN`) and whose second connector has `TX+` … gets a new RS-422 interface on the first one: tier 1 of `edit.choose_connector` takes the free connectors that carry the type, and an imported connector carries every type; the room of a fixed pinout is read only in tier 2. Generate then stops with *IF-001: TTC2-J01 has a fixed pinout and no free pin named TX+, TX-, RX+, RX-.* The person chooses the connector in the Inspector. Tried with the code of 4.3.0 (`20bf8f1`) with the same result; a backlog item, not a fix of this release. With `naming.far_device_names` on, pull request 3 already leaves such a connector out of tier 1 (`edit._free_tier` runs the dry run on every free connector with a fixed pinout, not only on one whose ports name devices), so the same device gets the interface on its second connector: broader than section 3.5, which names only ports named after other devices, and the room the editor shows is still the room Generate finds.
14. **The two settings in the walk.** With `naming.far_device_names` on and the map set, the chain of the engineer's case runs from the team's names to the right ports: `config --signal-map signal-map.csv` (6 names), `import-pinout` of OBC1 (`TTC1_TXP` … `TTC2_RXN`, 8 renames, the ports TTC1 and TTC2), TTC1 and TTC2 (4 renames each), the interfaces in the wrong ID order, `config --far-device-names on`, `generate` and `verify` with 0 errors, IF-001 on pins 5 to 8.

## 18. Risks and what this design does not check

- **Nobody on a team has named pins after devices in this tool.** The convention (`TTC1_…`, the separators, the ID with case) is read from the feedback's one example; a team that writes `TTC-1_TX` for the device `TTC1` gets nothing from the setting. The engineer should look at the names of a real OBC connector before 4.4.0 is tagged (N2).
- **Device IDs that look like port names.** A project with a device `RS422` reads every port `RS422_n` as that device's (section 10). The setting is opt-in and the Inspector names it, but a reader can be surprised.
- **Two tools on one project.** A 4.3.x tool ignores both keys (section 10); the 4.4.0 verifier then reports what it did. The release notes say to update together.
- **Two copies of the reading** (the core's and the verifier's) must agree; the Hypothesis test of section 11 holds them together, as for ports.
- **The map changes the project's names at import.** A wrong entry renames every pin it fits; the echo, the preview and the import record list each rename, and the import is one undo step.
- **The results of sections 4.1 and 3.2 come from scripts that state the rules as written here**, not from the tool's code. Pull requests 3 and 4 run the same cases as tests; a difference is read before the merge.
- **No code was written**; the module and function names are the plan, and the pull requests record where they differ.
